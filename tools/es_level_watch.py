#!/usr/bin/env python3
"""ES level watch over the live Databento tape — one line per event, CT stamps. [st-d7qe st-bpry]

Built 2026-09-10 while Steve traded the open and asked for eyes on ES. Reads
the day's ES trades file as it is written (no network, no Schwab), and prints:

  * a trade CLEARING a Mancini level or a GEX major — hysteresis of ``--band``
    points on the far side, so ticks oscillating on the level are not events,
    and a ``--cooldown`` per level so a chop is counted, not narrated (the
    count lands in the next 15-minute summary);
  * a GEX major that moved — only when the new value holds two consecutive
    polls and was not seen in the last 30 minutes (the vendor toggles between
    near-equal clusters poll to poll; 7525/7540 vs 7580/7600 on 09-10);
  * a stale tape — no print for 90 s inside RTH;
  * a 15-minute summary — last, range, open, delta, volume, basis, chop counts.

GEX levels are SPX strikes; the tape is ES. Every GEX level is moved to ES by
the live basis before comparison, and both numbers are printed on the line:
``ES 7670 UP through 7669 ES (GEX long-gamma 7665 SPX, basis +4.1)``. The
basis is measured, never assumed: the median of the last five GexBot polls'
``spot`` against the ES print at that same second (gexbot.jsonl vs the tape),
falling back to the latest RTH ``es_minus_spx_basis`` in schwab.jsonl. With no
basis at all, GEX levels are NOT watched and one [ALERT] says so — on 09-11
the watch compared raw SPX strikes to ES prints and every GEX clear was a
phantom (measured basis that day: median +4.07, +8.25 at the 08:30 open while
SPX spot lagged; the Schwab premarket row reads +49 and is excluded).
Mancini levels are ES already and are used as written.

Delta is ask-hit volume minus bid-hit volume (Databento side A/B). It is
pressure, not progress: on 09-10 the morning sold off on POSITIVE delta and
bounced on negative delta. The line carries the number; the read is Steve's.

Run (tmux target on the moocity socket, or under Monitor in a session):

    .venv/bin/python tools/es_level_watch.py                 # today, live, CT
    .venv/bin/python tools/es_level_watch.py --date 2026-09-11 --replay --start 08:25
                                                             # the day's tape, as fast as it reads
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import statistics
import sys
import time
from collections import deque
from math import inf
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
CT = ZoneInfo("America/Chicago")
RTH_OPEN, RTH_CLOSE = 8 * 60 + 30, 15 * 60
STALE_S = 90
SUMMARY_S = 900
GEX_POLL_S = 60
GEX_REPEAT_S = 1800
BASIS_WINDOW = 5          # polls in the rolling median
BASIS_MIN = 3             # fewer than this and the GexBot median is not trusted
BASIS_MAX_AGE_S = 1800    # a sample older than this no longer counts
BASIS_PAIR_S = 10.0       # ES print must be within this of the GexBot spot time
PRINT_MEMORY_S = 300      # recent prints kept for pairing
SCHWAB_UNUSABLE = ("premarket", "open")   # SPX quote not yet a live index at these pulls


class Clock:
    """Wall clock live; the tape's own time in replay."""

    def __init__(self) -> None:
        self.t: float | None = None

    def now(self) -> float:
        return time.time() if self.t is None else self.t


CLOCK = Clock()


def parse_utc(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def stamp() -> str:
    return datetime.fromtimestamp(CLOCK.now(), CT).strftime("%H:%M:%S")


def say(s: str) -> None:
    print(f"{stamp()} {s}", flush=True)


def load_mancini_levels(day: str) -> dict[str, tuple[float, str]]:
    """'<price>' -> (price, 'Mancini <kind>[ MAJOR]') from the day's in-session parse."""
    p = REPO / "runbook" / "mancini" / "parsed" / f"{day}.json"
    out: dict[str, tuple[float, str]] = {}
    for lv in json.loads(p.read_text())["levels"]:
        major = str(lv.get("label", "")).startswith("major")
        price = float(lv["price"])
        out[f"{price:g}"] = (price, f"Mancini {lv['kind']}{' MAJOR' if major else ''}")
    return out


class LevelCrosser:
    """Per-level above/below state with hysteresis and a per-level cooldown.

    ``levels`` is ``{id: (price, name)}`` — the id is what the cooldown and
    the chop count key on, so a GEX level whose price drifts with the basis
    (or toggles 7664/7665 SPX poll to poll) is still ONE level. A level whose
    price jumps by more than the band is re-seeded silently: a major that
    moves across price is not a cross. ``update(px, levels, t)`` returns the
    crossings to REPORT as (price, name, direction); crossings inside the
    cooldown are counted in ``chop`` instead.
    """

    def __init__(self, band: float, cooldown: float) -> None:
        self.band = band
        self.cooldown = cooldown
        self.state: dict[str, str] = {}
        self.price: dict[str, float] = {}
        self.last_cross: dict[str, float] = {}
        self.chop: dict[str, int] = {}

    def update(self, px: float, levels: dict[str, tuple[float, str]], t: float) -> list[tuple[float, str, str]]:
        out = []
        for lid, (lv, name) in levels.items():
            st = self.state.get(lid)
            prev = self.price.get(lid)
            if prev is not None and abs(lv - prev) > self.band:
                st = None
            self.price[lid] = lv
            if px >= lv + self.band:
                new = "above"
            elif px <= lv - self.band:
                new = "below"
            else:
                new = st
            if st is None:
                self.state[lid] = new
            elif new is not None and new != st:
                self.state[lid] = new
                direction = "UP through" if new == "above" else "DOWN through"
                if t - self.last_cross.get(lid, -inf) < self.cooldown:
                    self.chop[lid] = self.chop.get(lid, 0) + 1
                else:
                    out.append((lv, name, direction))
                self.last_cross[lid] = t
        return out

    def take_chop(self) -> dict[str, int]:
        c, self.chop = self.chop, {}
        return c


class Basis:
    """ES minus SPX, measured — the number every GEX strike is moved by.

    Primary: each new GexBot poll's ``spot`` paired with the ES print at the
    vendor's spot time (within BASIS_PAIR_S); the median of the last
    BASIS_WINDOW samples no older than BASIS_MAX_AGE_S, once BASIS_MIN have
    landed (the first poll after 08:30 catches SPX still opening: +8.5 on
    09-11 against +4.1 for the day). Fallback: the latest ``afternoon`` or
    ``close-watch`` ``es_minus_spx_basis`` row in schwab.jsonl — ``premarket``
    pairs a prior-close SPX quote with overnight ES (+49 on 09-11) and
    ``open`` is pulled one second into the open (+7.8). ``value(t)`` is
    (basis, source) or None — None means refuse, not zero.
    """

    def __init__(self, schwab_path: Path | None = None) -> None:
        self.schwab_path = schwab_path
        self.samples: deque[tuple[float, float]] = deque()
        self.prints: deque[tuple[float, float]] = deque()   # (ts_event, px)
        self.last_spot_ts: float | None = None

    def add_print(self, ts: float, px: float) -> None:
        self.prints.append((ts, px))
        while self.prints and ts - self.prints[0][0] > PRINT_MEMORY_S:
            self.prints.popleft()

    def es_at(self, ts: float) -> float | None:
        """The last ES print at or before ``ts``, if within BASIS_PAIR_S."""
        if not self.prints:
            return None
        keys = [p[0] for p in self.prints]
        i = bisect.bisect_right(keys, ts)
        cands = []
        if i > 0:
            cands.append(self.prints[i - 1])
        if i < len(self.prints):
            cands.append(self.prints[i])
        best = min(cands, key=lambda p: abs(p[0] - ts))
        return best[1] if abs(best[0] - ts) <= BASIS_PAIR_S else None

    def sample_gex(self, spot: float | None, spot_ts: float | None, t: float) -> float | None:
        """Add one sample from a GexBot poll; returns the sample or None."""
        if spot is None or spot_ts is None or spot_ts == self.last_spot_ts:
            return None
        self.last_spot_ts = spot_ts
        es = self.es_at(spot_ts)
        if es is None:
            return None
        b = es - spot
        self.samples.append((t, b))
        while len(self.samples) > BASIS_WINDOW:
            self.samples.popleft()
        return b

    def schwab(self, t: float) -> tuple[float, str] | None:
        if self.schwab_path is None:
            return None
        try:
            rows = [json.loads(l) for l in self.schwab_path.read_text().splitlines() if l.strip()]
        except (OSError, ValueError):
            return None
        best = None
        for r in rows:
            try:
                ts = parse_utc(r["ts_pull_utc"])
                b = r["data"]["es_minus_spx_basis"]
            except (KeyError, TypeError, ValueError):
                continue
            if b is None or r.get("stage") in SCHWAB_UNUSABLE or ts > t:
                continue
            if best is None or ts > best[0]:
                best = (ts, float(b), str(r.get("stage", "?")))
        if best is None:
            return None
        return best[1], f"schwab {best[2]} {datetime.fromtimestamp(best[0], CT).strftime('%H:%M')}"

    def value(self, t: float) -> tuple[float, str] | None:
        live = [b for (ts, b) in self.samples if t - ts <= BASIS_MAX_AGE_S]
        if len(live) >= BASIS_MIN:
            return statistics.median(live), f"gexbot×{len(live)}"
        return self.schwab(t)


def gex_last_row(path: Path):
    """Live source: the last line of gexbot.jsonl, parsed, or None."""
    try:
        last = None
        with path.open() as f:
            for line in f:
                if line.strip():
                    last = line
        return json.loads(last) if last else None
    except (OSError, ValueError):
        return None


class GexReplay:
    """Replay source: gexbot.jsonl rows in order, the last one pulled at or before t."""

    def __init__(self, path: Path) -> None:
        self.rows: list[tuple[float, dict]] = []
        try:
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    self.rows.append((parse_utc(r["ts_pull_utc"]), r))
                except (ValueError, KeyError, TypeError):
                    continue
        except OSError:
            pass
        self.keys = [k for k, _ in self.rows]

    def __call__(self, t: float):
        i = bisect.bisect_right(self.keys, t)
        return self.rows[i - 1][1] if i else None


class GexMajors:
    """Damped GEX summary: a major is reported when it holds two polls and its
    new value was not reported in the last GEX_REPEAT_S seconds. Levels are
    SPX; ``as_levels(basis)`` moves them to ES and refuses without one."""

    KEYS = {"gamma-zero": "spot_at_gamma_zero", "major +": "major_positive",
            "major −": "major_negative", "long-gamma": "major_long_gamma",
            "short-gamma": "major_short_gamma"}
    DAMPED = ("major +", "major −")

    def __init__(self, source) -> None:
        self.source = source            # callable(t) -> parsed gexbot row or None
        self.levels: dict[str, float | None] = {}
        self.pending: dict[str, float] = {}
        self.recent: dict[str, dict[float, float]] = {}
        self.spot: float | None = None
        self.spot_ts: float | None = None

    def poll(self, t: float) -> list[str]:
        row = self.source(t)
        if not row:
            return []
        try:
            s = row["data"]["summary"]
        except (KeyError, TypeError):
            return []
        self.spot = s.get("spot_at_gamma_zero")
        try:
            resp_ts = row["data"]["responses"]["/SPX/state/gamma_zero"]["timestamp"]
            self.spot_ts = float(resp_ts) if resp_ts else parse_utc(row["ts_pull_utc"])
        except (KeyError, TypeError, ValueError):
            self.spot_ts = parse_utc(row["ts_pull_utc"]) if row.get("ts_pull_utc") else None
        new = {k: (None if s.get(v) is None else round(float(s[v]))) for k, v in self.KEYS.items()}
        return self.apply(new, t)

    def apply(self, new: dict[str, float | None], t: float) -> list[str]:
        msgs = []
        if not self.levels:
            self.levels = dict(new)
            msgs.append("GEX (SPX): " + ", ".join(f"{k} {v}" for k, v in new.items()))
            return msgs
        for k in self.DAMPED:
            v = new[k]
            if v == self.levels.get(k):
                self.pending.pop(k, None)
                continue
            if self.pending.get(k) == v:
                seen = self.recent.setdefault(k, {})
                if t - seen.get(v, -inf) > GEX_REPEAT_S:
                    msgs.append(f"GEX {k} moved {self.levels.get(k)} → {v} SPX (held two polls)")
                seen[v] = t
                seen[self.levels.get(k)] = t
                self.levels[k] = v
                self.pending.pop(k, None)
            else:
                self.pending[k] = v
        for k in self.KEYS:
            if k not in self.DAMPED:
                self.levels[k] = new[k]
        return msgs

    def as_levels(self, basis: float | None) -> dict[str, tuple[float, str]]:
        """ES-priced GEX levels, keyed by 'GEX <kind>' (price to the tick) — empty without a basis."""
        if basis is None:
            return {}
        out: dict[str, tuple[float, str]] = {}
        for k, v in self.levels.items():
            if v is None or k == "gamma-zero":
                continue
            es = round((v + basis) * 4) / 4
            out[f"GEX {k}"] = (float(es), f"GEX {k} {v:g} SPX, basis {basis:+.1f}")
        return out


def follow(path: Path):
    """Yield new lines appended to ``path`` from its current end; None when idle."""
    with path.open() as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            yield line or None


def replay(path: Path, start_ct: str | None):
    """Yield the day's lines from the start (from ``start_ct`` HH:MM CT if given)."""
    start_t = None
    if start_ct:
        day = path.parent.name
        start_t = datetime.strptime(f"{day} {start_ct}", "%Y-%m-%d %H:%M").replace(tzinfo=CT).timestamp()
    with path.open() as f:
        for line in f:
            if start_t is not None:
                try:
                    if parse_utc(json.loads(line)["provenance"]["ts_event"]) < start_t:
                        continue
                except (ValueError, KeyError, TypeError):
                    continue
            yield line


def print_time(r: dict, fallback: float) -> float:
    try:
        return parse_utc(r["provenance"]["ts_event"])
    except (KeyError, TypeError, ValueError):
        return fallback


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ES level watch over the live tape")
    ap.add_argument("--date", default=datetime.now(CT).strftime("%Y-%m-%d"))
    ap.add_argument("--band", type=float, default=1.0, help="points a level must be cleared by")
    ap.add_argument("--cooldown", type=float, default=300, help="seconds before the same level reports again")
    ap.add_argument("--replay", action="store_true", help="read the day's tape from the start on its own clock")
    ap.add_argument("--start", default=None, help="replay only: first print at/after HH:MM CT")
    args = ap.parse_args(argv)

    day_dir = REPO / "data" / "corpus" / args.date
    tape = day_dir / "databento_glbx_es.jsonl"
    if not tape.exists():
        print(f"no live tape at {tape}", file=sys.stderr)
        return 3
    if args.replay:
        CLOCK.t = 0.0
        source = GexReplay(day_dir / "gexbot.jsonl")
        lines = replay(tape, args.start)
    else:
        source = lambda t: gex_last_row(day_dir / "gexbot.jsonl")  # noqa: E731
        lines = follow(tape)

    try:
        mancini = load_mancini_levels(args.date)
    except (OSError, ValueError, KeyError) as e:
        if not args.replay:
            say(f"[ALERT] no Mancini levels for {args.date}: {e}")
        mancini = {}
    gex = GexMajors(source)
    basis = Basis(day_dir / "schwab.jsonl")
    crosser = LevelCrosser(args.band, args.cooldown)

    last_px = None
    last_print = CLOCK.now()
    stale = False
    last_gex = -inf
    win_start = CLOCK.now()
    w_hi = w_lo = w_open = None
    w_buy = w_sell = w_vol = 0
    basis_now: tuple[float, str] | None = None
    basis_state: str | None = None     # "on" / "off"
    started = not args.replay
    if started:
        say(f"watching {tape} — {len(mancini)} Mancini levels loaded")

    def tick(t: float) -> None:
        nonlocal last_gex, basis_now, basis_state, win_start, w_hi, w_lo, w_open, w_buy, w_sell, w_vol
        if t - last_gex > GEX_POLL_S:
            for m in gex.poll(t):
                say(m)
            basis.sample_gex(gex.spot, gex.spot_ts, t)
            basis_now = basis.value(t)
            last_gex = t
            if basis_now is None and basis_state != "off":
                say(f"[ALERT] no ES/SPX basis (fewer than {BASIS_MIN} GexBot spots paired with a print, "
                    "no afternoon Schwab pull) — GEX levels NOT watched until one arrives")
                basis_state = "off"
            elif basis_now is not None and basis_state != "on":
                b, src = basis_now
                say(f"basis {b:+.2f} ({src}) — GEX levels watched at ES = SPX {b:+.1f}")
                basis_state = "on"
        if t - win_start >= SUMMARY_S and w_hi is not None:
            chop = crosser.take_chop()
            chop_s = ("  chop: " + ", ".join(f"{lid}×{n}" for lid, n in sorted(chop.items()))) if chop else ""
            b_s = f"basis {basis_now[0]:+.2f} ({basis_now[1]})" if basis_now else "basis NONE"
            say(f"15-min: last {last_px}  range {w_lo}–{w_hi}  open {w_open}  "
                f"delta {w_buy - w_sell:+,}  vol {w_vol:,}  {b_s}{chop_s}")
            win_start = t
            w_hi = w_lo = w_open = None
            w_buy = w_sell = w_vol = 0

    for line in lines:
        if line is None:
            time.sleep(0.5)
            t = CLOCK.now()
            now = datetime.fromtimestamp(t, CT)
            minute = now.hour * 60 + now.minute
            if not stale and t - last_print > STALE_S and RTH_OPEN <= minute <= RTH_CLOSE:
                say(f"[ALERT] ES tape stale: no print for {STALE_S} s inside RTH")
                stale = True
            tick(t)
            continue
        try:
            r = json.loads(line)
            d = r["data"]
            px = d.get("price")
        except (ValueError, KeyError, TypeError):
            continue
        if px is None:
            continue
        if args.replay:
            CLOCK.t = print_time(r, CLOCK.t or 0.0)
            if not started:
                last_print = win_start = CLOCK.t
                say(f"replaying {tape} — {len(mancini)} Mancini levels loaded")
                started = True
        t = CLOCK.now()
        sz = d.get("size") or 0
        side = d.get("side")
        basis.add_print(print_time(r, t), px)
        if args.replay and not stale and t - last_print > STALE_S:
            gap_min = datetime.fromtimestamp(last_print, CT)
            if RTH_OPEN <= gap_min.hour * 60 + gap_min.minute <= RTH_CLOSE:
                say(f"[ALERT] ES tape stale: no print for {t - last_print:.0f} s inside RTH")
                stale = True
        last_print = t
        if stale:
            say("ES tape live again")
            stale = False
        tick(t)
        if w_open is None:
            w_open = px
        w_hi = px if w_hi is None or px > w_hi else w_hi
        w_lo = px if w_lo is None or px < w_lo else w_lo
        w_vol += sz
        if side == "A":
            w_buy += sz
        elif side == "B":
            w_sell += sz
        levels = {**mancini, **gex.as_levels(basis_now[0] if basis_now else None)}
        for lv, name, direction in crosser.update(px, levels, t):
            unit = " ES" if name.startswith("GEX") else ""
            say(f"ES {px} {direction} {lv:g}{unit} ({name})  15-min delta so far {w_buy - w_sell:+,}  vol {w_vol:,}")
        last_px = px
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
