"""The instrument and its marks — a registered rule's call priced as one single. [st-uc23]

WHAT
    A rule calls ``up`` or ``down`` at its fire minute. The scoreboard is the
    0DTE SPXW single about 10 points in the money on that side (``itm-single-
    10``, st-g0jo decision 3): a call struck ~10 below SPX for ``up``, a put
    ~10 above for ``down``, strike on the 5-point grid, bought at the first
    print at or after the fire minute. The declared exit (``rule.exit``) is
    resolved on the mark path, first touch wins; the stop x target grid is
    swept beside it.

THREE ENTRY SOURCES, TWO MARK PATHS — and the row says which.

    prints      the day holds the OPRA tape: SPX at the fire minute from
                0DTE put-call parity on the prints, the entry is the symbol's
                first print at or after the fire minute (within a grace
                window), the marks are its own prints to the close. This is
                the same construction ``final_hour_premium.py`` used for the
                08-29 scoreboard, generalised from a fixed entry to the
                rule's fire minute.
    estimated   no OPRA tape, but the 14:45 Schwab chain snapshot
                (``schwab.jsonl``, stage "late") holds the symbol: the entry
                is the snapshot's ASK (the marketable limit at the ask that
                ``strader/execution/compose.py`` composes today), SPX and ES
                are the snapshot's own, and the marks are the ES->premium
                proxy (``strader/marks/estimated.py``) from that entry. The
                row is ``estimated: true`` and resolves ``time`` ONLY; what
                the proxy would have resolved rides beside in
                ``estimated_exit`` (the standing contract, counter §5.1-5.2).
    none        neither — the fire is recorded as unpriceable, with the
                reason, so a day list can say how many calls had no price.

    Everything is a pure function of the day's files; nothing reads a clock.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from market.corpus.paths import resolve_existing
from strader.blotter.rows import MARK_ESTIMATED, MARK_PRINTS
from strader.marks.estimated import (
    Calibration, CoverageError, LegEntry, MarkPoint, MinuteBar, Uncalibrated,
    SESSION_CLOSE_CT, estimate_path, minute_index, minute_label,
)
from strader.marks.minute_paths import (
    OpraDay, es_at, es_minute_bars, parity_spx, read_es_day, read_opra_day,
)

__all__ = [
    "ENTRY_GRACE_S", "SNAPSHOT_GRACE_S", "MIN_PRINTS", "GRID_STOPS_PTS", "GRID_TARGETS_PCT",
    "PROXY_WINDOW_CT", "SchwabChain", "DayMarket", "Priced", "Unpriced",
    "read_day_market", "read_schwab_chain", "strike_for", "occ_symbol", "price_call",
    "resolve_exit", "sweep_grid", "hms",
]

CT = ZoneInfo("America/Chicago")

ENTRY_GRACE_S = 180        # the entry print must land within 3 minutes of the fire minute
SNAPSHOT_GRACE_S = 300     # the Schwab snapshot must sit within 5 minutes of the fire minute
MIN_PRINTS = 5             # fewer prints after the entry: too thin to score (final_hour_premium's floor)
PROXY_WINDOW_CT = ("13:00", "15:00")   # the estimated mark path's calibrated window

#: The premium grid swept beside the declared exit on printed rows. Stops in
#: premium points below the entry; targets as a percent of the entry.
GRID_STOPS_PTS = (0.20, 0.30, 0.50, 1.00)
GRID_TARGETS_PCT = (10, 25, 50, 100)


def hms(sec_ct: int) -> str:
    return f"{sec_ct // 3600:02d}:{sec_ct % 3600 // 60:02d}:{sec_ct % 60:02d}"


def strike_for(call: str, spx: float, offset_spx: int) -> tuple[str, float]:
    """(right, strike): a call ~offset below SPX for ``up``, a put ~offset above for ``down``."""
    if call == "up":
        return "C", float(int(round((spx - offset_spx) / 5.0)) * 5)
    if call == "down":
        return "P", float(int(round((spx + offset_spx) / 5.0)) * 5)
    raise ValueError(f"call must be 'up' or 'down', got {call!r}")


def occ_symbol(day: str, right: str, strike: float) -> str:
    y, m, d = day.split("-")
    return f"SPXW  {y[2:]}{m}{d}{right}{int(round(strike * 1000)):08d}"


# ------------------------------------------------------------ Schwab chain ---

@dataclass(frozen=True)
class SchwabChain:
    """One ``schwab.jsonl`` snapshot's 0DTE chain window."""

    day: str
    sec_ct: int
    stage: str
    spot_spx: float
    spot_es: float | None
    quotes: dict[tuple[str, float], dict]     # (right, strike) -> {bid, ask, mark, delta, ...}

    def quote(self, right: str, strike: float) -> dict | None:
        return self.quotes.get((right, float(strike)))


def read_schwab_chain(path: Path, day: str) -> list[SchwabChain]:
    """Every snapshot in the day's ``schwab.jsonl`` that carries a chain window, sorted."""
    out: list[SchwabChain] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            data = r.get("data") or {}
            cw = data.get("chain_window")
            ts = r.get("ts_pull_utc")
            if not cw or not ts or data.get("spot_spx") is None:
                continue
            try:
                t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(CT)
            except ValueError:
                continue
            if t.strftime("%Y-%m-%d") != day:
                continue
            quotes: dict[tuple[str, float], dict] = {}
            for q in cw:
                side = str(q.get("side", "")).upper()[:1]
                if side not in ("C", "P") or q.get("strike") is None:
                    continue
                quotes[(side, float(q["strike"]))] = q
            out.append(SchwabChain(day=day, sec_ct=t.hour * 3600 + t.minute * 60 + t.second,
                                   stage=str(r.get("stage") or ""), spot_spx=float(data["spot_spx"]),
                                   spot_es=(None if data.get("spot_es") is None else float(data["spot_es"])),
                                   quotes=quotes))
    out.sort(key=lambda c: c.sec_ct)
    return out


# --------------------------------------------------------------- the day ---

@dataclass
class DayMarket:
    """What pricing needs from one corpus day, read once."""

    day: str
    opra: OpraDay | None
    es: list[tuple[int, float]]              # ES prints in the proxy window, (sec_ct, price)
    bars: dict[str, MinuteBar]
    chains: list[SchwabChain]
    close_ct: str = SESSION_CLOSE_CT

    @property
    def close_sec(self) -> int:
        return minute_index(self.close_ct) * 60

    def chain_near(self, sec_ct: int, grace_s: int = SNAPSHOT_GRACE_S) -> SchwabChain | None:
        """The snapshot nearest ``sec_ct`` within the grace, the earliest on a tie."""
        best = None
        for c in self.chains:
            d = abs(c.sec_ct - sec_ct)
            if d <= grace_s and (best is None or d < abs(best.sec_ct - sec_ct)):
                best = c
        return best


def read_day_market(day: str, corpus: Path, *, window_ct: tuple[str, str] = PROXY_WINDOW_CT) -> DayMarket:
    day_dir = Path(corpus) / day
    opra_path = resolve_existing(day_dir / "databento_opra.jsonl")
    es_path = resolve_existing(day_dir / "databento_glbx_es.jsonl")
    opra = read_opra_day(opra_path, day) if opra_path else None
    es = read_es_day(es_path, day, window_ct) if es_path else []
    chain_path = day_dir / "schwab.jsonl"
    chains = read_schwab_chain(chain_path, day) if chain_path.is_file() else []
    return DayMarket(day=day, opra=opra, es=es, bars=es_minute_bars(es), chains=chains)


# ------------------------------------------------------------- resolution ---

def resolve_exit(path: Sequence[tuple[int, float]], entry_pts: float, *, stop_pts: float,
                 target_pct: float) -> tuple[str, int, float]:
    """Walk the marks after the entry; the first touch wins.

    ``path`` is ``(sec_ct, price)`` strictly after the entry and before the
    close, in order. A mark at or below ``entry - stop_pts`` exits ``stop`` at
    that mark; at or above ``entry * (1 + target_pct/100)`` exits ``target``
    there; otherwise the last mark is the ``time`` exit. The same mark cannot
    be both (stop is below the entry, target above).
    """
    stop_level = entry_pts - stop_pts
    target_level = entry_pts * (1.0 + target_pct / 100.0)
    for sec, px in path:
        if px <= stop_level:
            return "stop", sec, px
        if px >= target_level:
            return "target", sec, px
    sec, px = path[-1]
    return "time", sec, px


def sweep_grid(path: Sequence[tuple[int, float]], entry_pts: float, *,
               stops: Sequence[float] = GRID_STOPS_PTS,
               targets: Sequence[float] = GRID_TARGETS_PCT) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for s in stops:
        for t in targets:
            reason, sec, px = resolve_exit(path, entry_pts, stop_pts=s, target_pct=t)
            out[f"{s:.2f}x{int(t)}"] = {"exit_reason": reason, "exit_ts": hms(sec),
                                        "exit_premium_pts": px, "pnl_pts": round(px - entry_pts, 4)}
    return out


# ---------------------------------------------------------------- pricing ---

@dataclass
class Priced:
    mark_path: str
    right: str
    strike: float
    symbol: str
    entry_sec: int
    entry_pts: float
    spx_at_entry: float
    es_at_entry: float
    exit_reason: str
    exit_sec: int
    exit_pts: float
    mfe_pts: float
    mae_pts: float
    n_marks: int
    grid: dict | None = None
    estimated_exit: dict | None = None
    extrapolated: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def pnl_pts(self) -> float:
        return round(self.exit_pts - self.entry_pts, 4)


@dataclass(frozen=True)
class Unpriced:
    reason: str
    detail: str = ""


def _first_at_or_below(points: Sequence[tuple[str, float]], level: float) -> str | None:
    for minute, v in points:
        if v <= level:
            return minute
    return None


def _first_at_or_above(points: Sequence[tuple[str, float]], level: float) -> str | None:
    for minute, v in points:
        if v >= level:
            return minute
    return None


def price_call(market: DayMarket, call: str, fire_ct: str, *, offset_spx: int, stop_pts: float,
               target_pct: float, cal: Calibration | None,
               entry_grace_s: int = ENTRY_GRACE_S, min_prints: int = MIN_PRINTS) -> Priced | Unpriced:
    """Price one call at ``fire_ct`` on ``market``: prints if the day has them,
    the Schwab-ask entry plus the proxy path if not, else :class:`Unpriced`."""
    fire_sec = minute_index(fire_ct) * 60
    close_sec = market.close_sec
    if fire_sec >= close_sec:
        return Unpriced("fire-after-close", fire_ct)

    if market.opra is not None and market.opra.prints:
        return _price_from_prints(market, call, fire_sec, offset_spx=offset_spx, stop_pts=stop_pts,
                                  target_pct=target_pct, entry_grace_s=entry_grace_s, min_prints=min_prints)

    chain = market.chain_near(fire_sec)
    if chain is None:
        return Unpriced("no-entry-source", "no OPRA prints and no Schwab chain within the grace of the fire minute")
    if cal is None:
        return Unpriced("no-calibration", "an estimated row needs the estimated-mark calibration")
    return _price_from_snapshot(market, chain, call, fire_sec, offset_spx=offset_spx, stop_pts=stop_pts,
                                target_pct=target_pct, cal=cal)


def _price_from_prints(market: DayMarket, call: str, fire_sec: int, *, offset_spx: int, stop_pts: float,
                       target_pct: float, entry_grace_s: int, min_prints: int) -> Priced | Unpriced:
    opra = market.opra
    assert opra is not None
    spx = parity_spx(opra.strikes(), fire_sec)
    if spx is None:
        return Unpriced("no-parity", "fewer than three strikes printed both sides around the fire minute")
    right, strike = strike_for(call, spx, offset_spx)
    sym = occ_symbol(market.day, right, strike)
    prints = opra.prints.get(sym, [])
    entry = next(((s, p) for s, p in prints if s >= fire_sec), None)
    if entry is None or entry[0] - fire_sec > entry_grace_s:
        return Unpriced("no-entry-print", f"{sym}: no print within {entry_grace_s}s of the fire minute")
    entry_sec, entry_pts = entry
    es_entry = es_at(market.es, entry_sec)
    if es_entry is None:
        return Unpriced("no-es-at-entry", f"no ES print at or before {hms(entry_sec)}")
    path = [(s, p) for s, p in prints if entry_sec < s < market.close_sec]
    if len(path) < min_prints:
        return Unpriced("thin", f"{sym}: {len(path)} prints after the entry (< {min_prints})")
    reason, exit_sec, exit_pts = resolve_exit(path, entry_pts, stop_pts=stop_pts, target_pct=target_pct)
    highs = max(p for _, p in path)
    lows = min(p for _, p in path)
    return Priced(mark_path=MARK_PRINTS, right=right, strike=strike, symbol=sym, entry_sec=entry_sec,
                  entry_pts=entry_pts, spx_at_entry=round(spx, 2), es_at_entry=es_entry,
                  exit_reason=reason, exit_sec=exit_sec, exit_pts=exit_pts,
                  mfe_pts=round(highs - entry_pts, 4), mae_pts=round(lows - entry_pts, 4),
                  n_marks=len(path), grid=sweep_grid(path, entry_pts, stops=GRID_STOPS_PTS, targets=GRID_TARGETS_PCT))


def _price_from_snapshot(market: DayMarket, chain: SchwabChain, call: str, fire_sec: int, *, offset_spx: int,
                         stop_pts: float, target_pct: float, cal: Calibration) -> Priced | Unpriced:
    right, strike = strike_for(call, chain.spot_spx, offset_spx)
    sym = occ_symbol(market.day, right, strike)
    q = chain.quote(right, strike)
    if q is None or q.get("ask") in (None, 0, 0.0):
        return Unpriced("no-snapshot-quote", f"{sym}: not in the {chain.stage or 'schwab'} chain window at {hms(chain.sec_ct)}")
    entry_pts = float(q["ask"])
    entry_sec = chain.sec_ct
    es_entry = es_at(market.es, entry_sec)
    if es_entry is None:
        es_entry = chain.spot_es
    if es_entry is None:
        return Unpriced("no-es-at-entry", f"no ES print at or before {hms(entry_sec)} and no spot_es on the snapshot")
    leg = LegEntry(right=right, strike=strike, entry_premium_pts=entry_pts, entry_spx=chain.spot_spx,
                   entry_es=es_entry, entry_minute=minute_label(entry_sec // 60))
    # The entry minute's own bar is included: its close is after the entry
    # second, the same convention the calibration's rows were built on.
    bars = [b for b in market.bars.values() if minute_index(b.minute) >= entry_sec // 60]
    if not bars:
        return Unpriced("no-es-bars-after-entry", f"no ES minute bars after {hms(entry_sec)}")
    try:
        path: list[MarkPoint] = estimate_path(leg, bars, cal, allow_extrapolation=True)
    except Uncalibrated as e:
        return Unpriced("uncalibrated", str(e))
    except CoverageError as e:  # cannot happen with allow_extrapolation, kept for the contract
        return Unpriced("coverage", str(e))
    if not path:
        return Unpriced("no-proxy-path", "the proxy produced no minutes before the close")
    last = path[-1]
    exit_sec = (minute_index(last.minute) + 1) * 60 - 1     # the bar's last second
    closes = [(p.minute, p.premium_pts) for p in path]
    adverse = [(p.minute, p.adverse_pts) for p in path]
    favourable = [(p.minute, p.favourable_pts) for p in path]
    stop_level = entry_pts - stop_pts
    target_level = entry_pts * (1.0 + target_pct / 100.0)
    stop_adv = _first_at_or_below(adverse, stop_level)
    tgt_fav = _first_at_or_above(favourable, target_level)
    stop_close = _first_at_or_below(closes, stop_level)
    tgt_close = _first_at_or_above(closes, target_level)

    def _would(stop_m: str | None, tgt_m: str | None) -> str:
        if stop_m and (not tgt_m or stop_m <= tgt_m):
            return "stop"
        if tgt_m:
            return "target"
        return "time"

    estimated_exit = {
        "basis": "adverse/favourable = the minute's ES extreme against/for the leg; close = the minute's closing ES",
        "stop_minute_adverse": stop_adv, "target_minute_favourable": tgt_fav,
        "stop_minute_close": stop_close, "target_minute_close": tgt_close,
        "would_exit_reason_extreme": _would(stop_adv, tgt_fav),
        "would_exit_reason_close": _would(stop_close, tgt_close),
        "proxy_close_pts": last.premium_pts,
    }
    return Priced(mark_path=MARK_ESTIMATED, right=right, strike=strike, symbol=sym, entry_sec=entry_sec,
                  entry_pts=entry_pts, spx_at_entry=round(chain.spot_spx, 2), es_at_entry=es_entry,
                  exit_reason="time", exit_sec=exit_sec, exit_pts=last.premium_pts,
                  mfe_pts=round(max(p.favourable_pts for p in path) - entry_pts, 4),
                  mae_pts=round(min(p.adverse_pts for p in path) - entry_pts, 4),
                  n_marks=len(path), grid=None, estimated_exit=estimated_exit,
                  extrapolated=any(p.extrapolated for p in path),
                  notes=[f"entry = Schwab {chain.stage or 'snapshot'} ask at {hms(chain.sec_ct)} CT; marks = ES->premium proxy"])
