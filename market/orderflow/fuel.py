"""Trapped-seller fuel — the five measured components at entry consideration. [st-aq1n]

Codifies ``knowledge/trapped-seller-fuel.md``: when price approaches a level,
measure what the tape actually shows about accumulation at it — never the
cohorts-and-stops story. Long side written out (trapped sellers under a
ceiling being approached from below); the short side mirrors.

THE EPISTEMIC RULE IS BINDING. Every field this module emits is arithmetic
over the bars it was fed: hit-bid volume that is underwater once the level
holds, rejection counts, higher lows with positive delta, volume-by-price
thinness, and the level-state file's touch/defense record. The ceiling claim
is "consistent with trapped sellers." No field names who is holding or where
a stop sits, and the render says "no lid yet" rather than inventing one.

INTEGRATION CONTRACT (same as ``gex_context``): this is display context, not
recognition. The feeder computes it AFTER the run log has recorded the bar's
emissions and appends it only to the page payload's ``ev`` list, stamped
``context: true`` — so live/replay parity over the run log is untouched and
graders can filter it. ``FuelTracker.on_bar`` must never raise into the
feeder: any internal failure resolves to ``None`` and one rate-limited log
line.

Determinism: the tracker is a pure function of (constructor inputs, bar
stream). No wall clock, no randomness — cadence counts bars, windows use the
bars' own timestamps.
"""
from __future__ import annotations

import json
import logging
from collections import namedtuple
from dataclasses import dataclass
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
LEVEL_STATE = ROOT / "data" / "level_state"
CT = timezone(timedelta(hours=-5))


@dataclass(frozen=True)
class FuelKnobs:
    """Every threshold in the read. One place, so a change is a diff."""
    engage_pts: float = 4.0       # price within this of a level -> compute
    trap_near: float = 3.0        # underwater band: [L - near, L + far] (long)
    trap_far: float = 1.0
    lid_pts: float = 2.0          # a high this close under L that fails = rejection
    window_s: float = 40 * 60.0   # rolling window for lid/underwater/dips
    refresh_bars: int = 10        # re-emit cadence while engaged
    roll_s: float = 300.0         # lid/dips read on 5-min groups — the bridge's
                                  # rolled view, the granularity the concept
                                  # (worked example) was written at
    shelf_frac: float = 0.5       # node run / shelf threshold, x level-zone peak
    thin_scan_pts: float = 15.0   # how far past the level to look for the shelf
    min_lid_rej: int = 2          # render "no lid yet" below this


# ---------------------------------------------------------------- history

def load_level_history(day: _date, path: Path | None = None) -> dict[float, dict]:
    """The day's ``data/level_state`` record as {price: row}. Never raises.

    The level-state artifact (Schwab 5m candles, prior evening through now)
    already counts touches and defenses per Mancini level — the measured form
    of "how long has this level been leaned on." Missing/unreadable file is a
    normal morning state and resolves to {}.
    """
    p = path or (LEVEL_STATE / f"{day.isoformat()}.json")
    try:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        out: dict[float, dict] = {}
        for row in doc.get("levels", []):
            price = row.get("price")
            if isinstance(price, (int, float)):
                out[float(price)] = row
        return out
    except (OSError, ValueError, TypeError) as e:
        logger.info("fuel: no level history for %s (%s)", day, e)
        return {}


def _history_phrase(row: dict | None) -> str | None:
    if not row:
        return None
    t, d = row.get("n_touches"), row.get("n_defenses")
    if not isinstance(t, int) or not isinstance(d, int):
        return None
    since = ""
    ft = row.get("first_touch")
    if isinstance(ft, str):
        try:
            dt = datetime.fromisoformat(ft).astimezone(CT)
            since = f" since {dt.strftime('%a %H:%M')} CT"
        except ValueError:
            pass
    state = row.get("state")
    tail = f", {state}" if isinstance(state, str) and state else ""
    return f"touched {t}x / defended {d}x{since}{tail}"


# ---------------------------------------------------------------- components

def _fmt_k(v: int) -> str:
    return f"{v / 1000:.1f}K" if abs(v) >= 1000 else str(v)


def _underwater(bars: list, level: float, read: str, k: FuelKnobs) -> int:
    """Aggression in the trap band over the window, from bar cells.

    Long read: hit-bid (sell-aggressor) volume in [L - trap_near, L + trap_far]
    — sellers who sold there recently and are underwater the moment price
    holds above. Short read mirrors with lift-ask volume above the level.
    """
    if read == "long":
        lo, hi = level - k.trap_near, level + k.trap_far
    else:
        lo, hi = level - k.trap_far, level + k.trap_near
    total = 0
    for b in bars:
        for c in b.cells:
            if lo <= c.price <= hi:
                total += c.bid_vol if read == "long" else c.ask_vol
    return total


def _lid_rejections(bars: list, level: float, read: str, k: FuelKnobs) -> int:
    """Rows that pressed to within lid_pts of the level — or through it — and
    closed rejected on the far side. A spike through that closes back under is
    a rejection too (the failed-breakout press), so there is no upper bound."""
    n = 0
    for b in bars:
        if read == "long":
            if b.high >= level - k.lid_pts and b.close <= level:
                n += 1
        else:
            if b.low <= level + k.lid_pts and b.close >= level:
                n += 1
    return n


def _absorbed(rows: list, read: str) -> tuple[int, int]:
    """(rows, summed delta) of the trailing run of consecutive higher lows
    (long) / lower highs (short) ending at the newest row — the concept's
    "structure building into the level" (7720.75 → 7726.5 → 7728.75 →
    7731.5 in the worked example). Under 3 rows there is no structure yet.

    The summed delta EXCLUDES the run's earliest row: that row is the
    low-maker — the flush whose selling created the dip — and the absorption
    claim is about the rows that then held above it."""
    if len(rows) < 3:
        return 0, 0
    i = len(rows) - 1
    run, d = 1, rows[-1].delta
    while i > 0:
        prev, cur = rows[i - 1], rows[i]
        ok = prev.low < cur.low if read == "long" else prev.high > cur.high
        if not ok:
            break
        run += 1
        d += prev.delta
        i -= 1
    if run < 3:
        return 0, 0
    return run, d - rows[i].delta      # drop the low-maker's own delta


Rolled = namedtuple("Rolled", "low high close delta")


def _roll(bars: list, roll_s: float) -> list[Rolled]:
    """Group bars into fixed wall-time buckets of their end_ts — the bridge's
    rolled view. Lid rejections and absorbed dips are read at this
    granularity; a 2,000-lot bar every 40 seconds makes both twitchy."""
    rows: list[Rolled] = []
    key = None
    lo = hi = cl = None
    d = 0
    for b in bars:
        bk = int(b.end_ts.timestamp() // roll_s)
        if bk != key:
            if key is not None:
                rows.append(Rolled(lo, hi, cl, d))
            key, lo, hi, d = bk, b.low, b.high, 0
        lo = min(lo, b.low)
        hi = max(hi, b.high)
        cl = b.close
        d += b.delta
    if key is not None:
        rows.append(Rolled(lo, hi, cl, d))
    return rows


def _thin_above(vol_by_price: dict[float, int], level: float, read: str,
                k: FuelKnobs) -> tuple[float | None, float | None]:
    """(thin_ratio, shelf_price) from session volume-by-price, 1-pt buckets.

    Seed = the heaviest of the three buckets around the level. The NODE is
    the contiguous run of buckets past the level (in the read direction)
    still holding >= shelf_frac x seed — the lid's own traded shoulder. The
    SHELF is the next bucket beyond the run at >= shelf_frac x seed within
    thin_scan_pts; thin_ratio = mean of the gap buckets (empties included)
    over the seed. (1.0, None) = the run never thins inside the scan range —
    heavy above, no thin stretch. (None, None) = profile has nothing to say.
    """
    if not vol_by_price:
        return None, None
    b: dict[int, int] = {}
    for p, v in vol_by_price.items():
        b[int(p // 1)] = b.get(int(p // 1), 0) + v
    lb = int(level // 1)
    seed = max(b.get(lb - 1, 0), b.get(lb, 0), b.get(lb + 1, 0))
    if seed <= 0:
        return None, None
    sign = 1 if read == "long" else -1
    thr = k.shelf_frac * seed
    p = lb + sign
    scan_end = lb + sign * int(k.thin_scan_pts)
    while sign * (scan_end - p) >= 0 and b.get(p, 0) >= thr:
        p += sign                      # still on the node's shoulder
    if sign * (scan_end - p) < 0:
        return 1.0, None               # heavy the whole way — no thin stretch
    between: list[int] = []
    while sign * (scan_end - p) >= 0:
        v = b.get(p, 0)
        if v >= thr:
            ratio = (sum(between) / len(between) / seed) if between else 0.0
            return round(ratio, 2), float(p)
        between.append(v)
        p += sign
    ratio = (sum(between) / len(between) / seed) if between else 0.0
    return round(ratio, 2), None       # thin as far as the scan reaches


# ---------------------------------------------------------------- tracker

class FuelTracker:
    """Feed closed bars; get a fuel context event when a level is engaged.

    Emits on engagement start (first bar whose close is within ``engage_pts``
    of a level after being outside) and every ``refresh_bars`` bars while it
    stays engaged. One level per bar — the nearest. Read direction is
    mechanical: close below the level = long read (trapped sellers under a
    ceiling), close above = short read (mirror).
    """

    def __init__(self, levels: list[float], *,
                 history: dict[float, dict] | None = None,
                 history_loader=None,
                 knobs: FuelKnobs = FuelKnobs()):
        """``history_loader``: optional zero-arg callable returning the
        level-history map. The level-state artifact generates at 08:20 CT —
        AFTER a feeder that boots at midnight or pre-open — so while
        ``history`` is empty the tracker retries the loader at most every 15
        minutes of bar time until it yields rows (the gex_context live-file
        contract: absent is a normal state, never an error)."""
        self.levels = sorted({float(p) for p in levels})
        self.history = history or {}
        self._loader = history_loader
        self._next_load_ts = None
        self.k = knobs
        self._window: list = []          # bars inside knobs.window_s of newest
        self._vol_by_price: dict[float, int] = {}
        self._engaged: float | None = None
        # Global bars-since-last-emission, seeded so the first engagement
        # emits at once. One floor for BOTH cadence and engagement changes:
        # adjacent Mancini levels sit 2-6 pts apart, so a close oscillating
        # between two engage bands would otherwise emit on every flip and
        # bury the emissions row (measured 15 events in 26 overnight bars).
        self._gap = knobs.refresh_bars
        self._warned = False

    # -- internals -------------------------------------------------------
    def _push(self, bar) -> None:
        # Touch the fields BEFORE appending: a malformed bar must fail here
        # and never enter the window, or it would re-raise on every later
        # eviction pass and one bad object would disable fuel for the session.
        cutoff = bar.end_ts - timedelta(seconds=self.k.window_s)
        float(bar.close); iter(bar.cells)  # noqa: B018 — validation by access
        self._window.append(bar)
        while self._window and self._window[0].end_ts < cutoff:
            self._window.pop(0)
        for c in bar.cells:
            self._vol_by_price[c.price] = (
                self._vol_by_price.get(c.price, 0) + c.bid_vol + c.ask_vol)

    def _nearest(self, price: float) -> float | None:
        best, dist = None, self.k.engage_pts
        for lv in self.levels:
            d = abs(lv - price)
            if d <= dist:
                best, dist = lv, d
        return best

    def _compute(self, level: float, bar) -> dict:
        read = "long" if bar.close < level else "short"
        if not self.history and self._loader is not None:
            if self._next_load_ts is None or bar.end_ts >= self._next_load_ts:
                self._next_load_ts = bar.end_ts + timedelta(minutes=15)
                self.history = self._loader() or {}
                if self.history:
                    logger.info("fuel: level history arrived — %d rows",
                                len(self.history))
        hist_row = self.history.get(level)
        hist = _history_phrase(hist_row)
        uw = _underwater(self._window, level, read, self.k)
        rolled = _roll(self._window, self.k.roll_s)
        lid = _lid_rejections(rolled, level, read, self.k)
        n_hl, d_hl = _absorbed(rolled, read)
        thin, shelf = _thin_above(self._vol_by_price, level, read, self.k)
        win_min = 0.0
        if self._window:
            win_min = (self._window[-1].end_ts
                       - self._window[0].start_ts).total_seconds() / 60.0

        parts = [hist or "no level history"]
        parts.append(f"{lid} lid rejections in {win_min:.0f}m"
                     if lid >= self.k.min_lid_rej else "no lid yet")
        side = "sold" if read == "long" else "bought"
        held = "underwater on reclaim" if read == "long" else "underwater on loss"
        parts.append(f"{_fmt_k(uw)} {side} at the level, {held}" if uw > 0
                     else "no aggression at the level yet")
        if n_hl >= 2 and (d_hl > 0 if read == "long" else d_hl < 0):
            bought = "dips bought" if read == "long" else "pops sold"
            parts.append(f"{bought} {d_hl:+d} over {n_hl} "
                         + ("higher lows" if read == "long" else "lower highs"))
        else:
            parts.append("no absorbed dips" if read == "long" else "no absorbed pops")
        ahead = "above" if read == "long" else "below"
        if thin is not None and shelf is not None:
            parts.append(f"thin x{thin:.2f} to {shelf:.0f}")
        elif thin == 1.0:
            parts.append(f"heavy {ahead} — no thin stretch")
        elif thin is not None:
            parts.append(f"thin x{thin:.2f} {ahead}, no shelf within "
                         f"{self.k.thin_scan_pts:.0f} pts")
        else:
            parts.append("no profile read")

        return {
            "type": "Fuel",
            "context": True,
            "level": level,
            "read": read,
            "history": ({"n_touches": hist_row.get("n_touches"),
                         "n_defenses": hist_row.get("n_defenses"),
                         "first_touch": hist_row.get("first_touch"),
                         "state": hist_row.get("state")} if hist_row else None),
            "underwater_vol": uw,
            "lid_rejections": lid,
            "window_min": round(win_min, 1),
            "absorbed_swings": n_hl,
            "absorbed_delta": d_hl,
            "thin_ratio": thin,
            "shelf_price": shelf,
            "reason": f"{read} @ {level:.2f} — " + " · ".join(parts),
        }

    # -- public ----------------------------------------------------------
    def on_bar(self, bar) -> dict | None:
        """Fold one closed bar in; return a fuel event dict or None.

        Never raises: any failure logs once and returns None — a broken read
        must not take the feeder down (the gex_context contract).
        """
        try:
            self._push(bar)
            self._gap += 1
            level = self._nearest(bar.close)
            if level is None:
                self._engaged = None
                return None
            self._engaged = level
            if self._gap >= self.k.refresh_bars:
                self._gap = 0
                return self._compute(level, bar)
            return None
        except Exception:  # noqa: BLE001 — display context must never kill the feed
            if not self._warned:
                self._warned = True
                logger.exception("fuel: compute failed; fuel line disabled for this error")
            return None
