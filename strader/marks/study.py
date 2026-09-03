"""The leg-day study behind the proxy: build legs from a corpus day, feed the
fit, score the proxy against the prints. [st-9hhc]

WHAT
    Per corpus day holding both an OPRA file and an ES file, and per entry time
    in :data:`ENTRY_TIMES_CT`, fourteen hypothetical 0DTE singles are bought
    at the first print at or after the entry time: put and call at each ITM
    distance in :data:`OFFSETS_SPX` (negative = OTM), strikes rounded to the
    5-point grid around the parity-inferred SPX. Each leg carries its own print
    path to the close and the ES minute bars from its entry minute.

    :func:`calibration_rows` turns a leg-day into the minute rows
    :func:`strader.marks.estimated.fit_bin` consumes. :func:`validate_leg`
    marks the leg with a calibration and scores it: the close residual, the
    excursion residuals, and — the number the blotter depends on — whether the
    proxy fires a stop in the minute the prints do.

    Everything here is offline and deterministic: corpus files in, sorted
    rows out, no clock, no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from strader.marks.estimated import (
    Calibration, CalibrationRow, CoverageError, LegEntry, MinuteBar, Uncalibrated,
    SESSION_CLOSE_CT, bin_lower_edge, estimate_path, intrinsic_pts, minute_index, minute_label,
)
from strader.marks.minute_paths import (
    OpraDay, PrintMinute, es_at, es_minute_bars, parity_spx, print_minute_marks,
    read_es_day, read_opra_day, resolve_day_file,
)

__all__ = [
    "ENTRY_TIMES_CT", "OFFSETS_SPX", "ENTRY_GRACE_S", "MIN_MARK_MINUTES",
    "STOP_ABS_PTS", "STOP_PCT", "TARGET_PCT", "RIGHT_DIRECTION_PTS",
    "LegDay", "DayResult", "build_day", "calibration_rows", "validate_leg",
    "corpus_days",
]

ENTRY_TIMES_CT = ("13:00", "13:30", "14:00", "14:30")
OFFSETS_SPX = (-15, -10, -5, 0, 5, 10, 15)      # ITM distance; negative = OTM
ENTRY_GRACE_S = 180          # the entry print must land within 3 minutes of the entry time
MIN_MARK_MINUTES = 5         # a leg with fewer marked minutes is thin and skipped
STOP_ABS_PTS = 0.30          # Steve's 08-26 yardstick: 0.30 on a 10.10 single
STOP_PCT = 0.10
TARGET_PCT = 0.25
RIGHT_DIRECTION_PTS = 5.0    # ES finished 5+ points the option's way (the 08-29 convention)


@dataclass
class LegDay:
    leg_id: str
    day: str
    entry_ct: str
    offset_spx: int
    leg: LegEntry
    entry_sec: int
    marks: dict[str, PrintMinute]           # minute -> the leg's own prints
    close_fav_move: float                   # ES move in the leg's favour, entry -> last bar

    @property
    def bin_lo(self) -> int:
        return bin_lower_edge(self.leg.moneyness)


@dataclass
class DayResult:
    day: str
    legs: list[LegDay] = field(default_factory=list)
    bars: dict[str, MinuteBar] = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    skips: dict[str, int] = field(default_factory=dict)   # reason -> count
    skip: str | None = None                                # whole-day skip


def corpus_days(corpus: Path) -> list[tuple[str, Path]]:
    """(day, day_dir) for every corpus day holding both an OPRA file and an ES
    file, plain or gzipped, sorted by day."""
    out = []
    for d in sorted(corpus.iterdir()) if corpus.exists() else []:
        if not d.is_dir() or len(d.name) != 10 or d.name[4] != "-":
            continue
        if resolve_day_file(d, "databento_opra.jsonl") and resolve_day_file(d, "databento_glbx_es.jsonl"):
            out.append((d.name, d))
    return out


def _strike(right: str, spx: float, offset: int) -> float:
    target = spx + offset if right == "P" else spx - offset
    return float(int(round(target / 5.0)) * 5)


def _symbol(day: str, right: str, strike: float) -> str:
    y, m, d = day.split("-")
    return f"SPXW  {y[2:]}{m}{d}{right}{int(round(strike * 1000)):08d}"


def build_day(day: str, day_dir: Path, window_ct: tuple[str, str], *,
              entry_times: Sequence[str] = ENTRY_TIMES_CT,
              offsets: Sequence[int] = OFFSETS_SPX,
              close: str = SESSION_CLOSE_CT) -> DayResult:
    """Read one corpus day and build every leg it supports."""
    res = DayResult(day=day)
    opra_path = resolve_day_file(day_dir, "databento_opra.jsonl")
    es_path = resolve_day_file(day_dir, "databento_glbx_es.jsonl")
    if opra_path is None or es_path is None:
        res.skip = "missing-file"
        return res
    opra: OpraDay = read_opra_day(opra_path, day)
    res.coverage = opra.coverage.to_dict()
    es = read_es_day(es_path, day, window_ct)
    if not es:
        res.skip = "no-es-in-window"
        return res
    res.bars = es_minute_bars(es)
    strikes = opra.strikes()
    for entry_ct in entry_times:
        entry_target = minute_index(entry_ct) * 60
        spx = parity_spx(strikes, entry_target)
        if spx is None:
            res.skips["no-parity"] = res.skips.get("no-parity", 0) + 1
            continue
        for offset in offsets:
            for right in ("P", "C"):
                k = _strike(right, spx, offset)
                sym = _symbol(day, right, k)
                ps = opra.prints.get(sym, [])
                entry = next(((s, p) for s, p in ps if s >= entry_target), None)
                if entry is None or entry[0] - entry_target > ENTRY_GRACE_S:
                    res.skips["no-entry-print"] = res.skips.get("no-entry-print", 0) + 1
                    continue
                entry_sec, entry_pts = entry
                entry_es = es_at(es, entry_sec)
                if entry_es is None:
                    res.skips["no-es-at-entry"] = res.skips.get("no-es-at-entry", 0) + 1
                    continue
                marks = print_minute_marks(ps, from_sec=entry_sec, to_minute=close)
                if len(marks) < MIN_MARK_MINUTES:
                    res.skips["thin"] = res.skips.get("thin", 0) + 1
                    continue
                leg = LegEntry(right=right, strike=k, entry_premium_pts=entry_pts,
                               entry_spx=spx, entry_es=entry_es,
                               entry_minute=minute_label(entry_sec // 60))
                last_bar = res.bars[max(res.bars, key=minute_index)]
                res.legs.append(LegDay(
                    leg_id=f"{day}|{entry_ct}|{right}|{offset:+d}", day=day, entry_ct=entry_ct,
                    offset_spx=offset, leg=leg, entry_sec=entry_sec, marks=marks,
                    close_fav_move=round(leg.fav_sign * (last_bar.close - entry_es), 2)))
    return res


def calibration_rows(ld: LegDay, bars: dict[str, MinuteBar], *,
                     close: str = SESSION_CLOSE_CT) -> list[CalibrationRow]:
    """One row per minute where the leg printed and ES traded."""
    leg = ld.leg
    close_idx = minute_index(close)
    entry_idx = minute_index(leg.entry_minute)
    tau_entry = close_idx - entry_idx
    tv = leg.time_value_pts
    rows = []
    for minute in sorted(ld.marks, key=minute_index):
        bar = bars.get(minute)
        if bar is None:
            continue
        idx = minute_index(minute)
        tau_ratio = max(0, close_idx - (idx + 1)) / tau_entry
        spx_now = leg.entry_spx + (bar.close - leg.entry_es)
        rows.append(CalibrationRow(
            leg_id=ld.leg_id, right=leg.right, bin_lo=ld.bin_lo,
            fav_move=leg.fav_sign * (bar.close - leg.entry_es),
            tau_ratio=tau_ratio, tv_entry_pts=tv,
            y_pts=ld.marks[minute].close - leg.entry_premium_pts,
            entry_premium_pts=leg.entry_premium_pts,
            intrinsic_now_pts=intrinsic_pts(leg.right, leg.strike, spx_now)))
    return rows


def _first_at_or_below(series: list[tuple[str, float]], level: float) -> str | None:
    for minute, v in series:
        if v <= level:
            return minute
    return None


def _first_at_or_above(series: list[tuple[str, float]], level: float) -> str | None:
    for minute, v in series:
        if v >= level:
            return minute
    return None


def validate_leg(ld: LegDay, bars: dict[str, MinuteBar], cal: Calibration) -> dict:
    """Score the proxy for one leg-day against its prints.

    Returns a flat, JSON-ready row. ``skip`` is set (and the metrics absent)
    when the calibration has no fit for the leg's bin or the leg's minutes
    fall outside the calibrated window.
    """
    leg = ld.leg
    base = {
        "leg_id": ld.leg_id, "day": ld.day, "entry_ct": ld.entry_ct, "right": leg.right,
        "offset_spx": ld.offset_spx, "bin_lo": ld.bin_lo, "strike": leg.strike,
        "entry_pts": leg.entry_premium_pts, "entry_spx": round(leg.entry_spx, 2),
        "entry_es": leg.entry_es, "tv_entry_pts": round(leg.time_value_pts, 4),
        "moneyness_spx": round(leg.moneyness, 2),
        "in_sample": ld.day in set(cal.days),
        "close_fav_move": ld.close_fav_move,
        "right_direction": ld.close_fav_move >= RIGHT_DIRECTION_PTS,
    }
    try:
        path = estimate_path(leg, list(bars.values()), cal)
    except Uncalibrated as e:
        return {**base, "skip": "uncalibrated", "why": str(e)}
    except CoverageError as e:
        return {**base, "skip": "coverage", "why": str(e)}
    proxy = {p.minute: p for p in path}
    minutes = [m for m in sorted(ld.marks, key=minute_index) if m in proxy]
    if len(minutes) < MIN_MARK_MINUTES:
        return {**base, "skip": "thin-overlap", "n_minutes": len(minutes)}

    print_close = ld.marks[minutes[-1]].close
    proxy_close = proxy[minutes[-1]].premium_pts
    print_mfe = max(ld.marks[m].high for m in minutes)
    print_mae = min(ld.marks[m].low for m in minutes)
    proxy_mfe = max(proxy[m].favourable_pts for m in minutes)
    proxy_mae = min(proxy[m].adverse_pts for m in minutes)
    entry = leg.entry_premium_pts

    print_low = [(m, ld.marks[m].low) for m in minutes]
    print_high = [(m, ld.marks[m].high) for m in minutes]
    prox_close = [(m, proxy[m].premium_pts) for m in minutes]
    prox_adv = [(m, proxy[m].adverse_pts) for m in minutes]
    prox_fav = [(m, proxy[m].favourable_pts) for m in minutes]

    row = {
        **base, "n_minutes": len(minutes), "last_minute": minutes[-1],
        "print_close": print_close, "proxy_close": proxy_close,
        "close_resid_pts": round(proxy_close - print_close, 4),
        "close_resid_pct": round((proxy_close - print_close) / entry, 4) if entry else None,
        "print_mfe": print_mfe, "proxy_mfe": proxy_mfe, "mfe_resid_pts": round(proxy_mfe - print_mfe, 4),
        "print_mae": print_mae, "proxy_mae": proxy_mae, "mae_resid_pts": round(proxy_mae - print_mae, 4),
        "target25_print": _first_at_or_above(print_high, entry * (1 + TARGET_PCT)),
        "target25_proxy": _first_at_or_above(prox_fav, entry * (1 + TARGET_PCT)),
    }
    for name, level in (("abs30", entry - STOP_ABS_PTS), ("pct10", entry * (1 - STOP_PCT))):
        row[f"stop_{name}_print"] = _first_at_or_below(print_low, level)
        row[f"stop_{name}_proxy_close"] = _first_at_or_below(prox_close, level)
        row[f"stop_{name}_proxy_adverse"] = _first_at_or_below(prox_adv, level)
    return row
