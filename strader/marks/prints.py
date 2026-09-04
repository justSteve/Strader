"""The OPRA print path — minute marks for 0DTE SPXW singles from corpus day
files. [st-9hhc]

Ported from ``scripts/measurement/final_hour_premium.py`` (st-g0jo) so the
same parsing is importable, tested, and shared by calibration, validation and
the blotter instead of living in one script.

Facts this module depends on, measured 2026-09-01 on four corpus days
(2025-05-27, 2025-11-14, 2026-04-15, 2026-08-14):

* The usable timestamp is ``provenance.ts_event`` (ISO 8601, UTC); the
  payload sits under ``data`` (``symbol``, ``price``, ``size``). There is no
  top-level ``ts_event``.
* Prints cover 13:00-15:00 CT only, on every day checked, summer and winter
  UTC offsets both. There is no option print path before 13:00 CT.
* Files are plain ``.jsonl`` on most days and ``.jsonl.gz`` on the seven the
  compactor gzipped — always read both forms (the co-8p9nn lesson).

All times in this module are CT seconds since midnight unless a name says
otherwise. Rendering back to a clock string is ``ct_hms``.
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import statistics
from datetime import datetime
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")

#: The measured print-coverage window, CT seconds. Prints exist only inside
#: this on every corpus day; anything outside is extrapolation by definition.
WINDOW_START_S = 13 * 3600
WINDOW_END_S = 15 * 3600


def ct_hms(ct_s: int) -> str:
    """CT seconds since midnight -> ``HH:MM:SS``."""
    return f"{ct_s // 3600:02d}:{ct_s % 3600 // 60:02d}:{ct_s % 60:02d}"


def open_day(path: str):
    """Plain or gzipped corpus stream file."""
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def utc_offset_hours(day: str) -> int:
    """UTC offset for a corpus day (``YYYY-MM-DD``), e.g. -5 summer, -6 winter."""
    y, m, d = map(int, day.split("-"))
    return int(datetime(y, m, d, 12, tzinfo=CT).utcoffset().total_seconds() // 3600)


def parse_occ(sym: str):
    """``"SPXW  250807C06345000"`` -> ``("250807", "C", 6345.0)`` or None."""
    parts = sym.split()
    if len(parts) != 2 or parts[0] != "SPXW":
        return None
    body = parts[1]
    if len(body) != 15 or body[6] not in "CP":
        return None
    try:
        return body[:6], body[6], int(body[7:]) / 1000.0
    except ValueError:
        return None


def opra_path(day: str, root: str = "data/corpus") -> str | None:
    """The day's OPRA prints file, plain or gzipped, or None."""
    for suffix in (".jsonl", ".jsonl.gz"):
        p = os.path.join(root, day, "databento_opra" + suffix)
        if os.path.exists(p):
            return p
    return None


def es_path(day: str, root: str = "data/corpus") -> str | None:
    """The day's ES trade tape, plain or gzipped, or None."""
    for suffix in (".jsonl", ".jsonl.gz"):
        p = os.path.join(root, day, "databento_glbx_es" + suffix)
        if os.path.exists(p):
            return p
    return None


def corpus_days(root: str = "data/corpus") -> list[str]:
    """Sorted days holding BOTH an OPRA prints file and an ES tape."""
    found = glob.glob(os.path.join(root, "20*", "databento_opra.jsonl")) + glob.glob(
        os.path.join(root, "20*", "databento_opra.jsonl.gz")
    )
    days = sorted({os.path.basename(os.path.dirname(p)) for p in found})
    return [d for d in days if es_path(d, root)]


def load_day_prints(path: str, day: str,
                    start_s: int = WINDOW_START_S,
                    end_s: int = WINDOW_END_S) -> dict[str, list[tuple[int, float]]]:
    """Every 0DTE SPXW print in [start_s, end_s) CT -> ``{symbol: [(ct_s, price), ...]}``.

    Prints are returned sorted by time per symbol. Non-0DTE symbols are
    dropped (expiry must equal the day).
    """
    y, m, d = map(int, day.split("-"))
    exp = f"{y % 100:02d}{m:02d}{d:02d}"
    off = utc_offset_hours(day)
    tag = f"SPXW  {exp}"
    out: dict[str, list[tuple[int, float]]] = {}
    with open_day(path) as f:
        for line in f:
            if tag not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r.get("provenance", {}).get("ts_event", "")
            if len(ts) < 19:
                continue
            utc_s = int(ts[11:13]) * 3600 + int(ts[14:16]) * 60 + int(ts[17:19])
            ct_s = utc_s + off * 3600
            if not start_s <= ct_s < end_s:
                continue
            data = r.get("data", {})
            sym = data.get("symbol", "")
            occ = parse_occ(sym)
            if not occ or occ[0] != exp:
                continue
            out.setdefault(sym, []).append((ct_s, float(data["price"])))
    for sym in out:
        out[sym].sort()
    return out


def load_day_es_minutes(path: str, day: str,
                        start_s: int = WINDOW_START_S,
                        end_s: int = WINDOW_END_S) -> list[tuple[int, float]]:
    """ES last-trade price at each whole CT minute in [start_s, end_s].

    Reads the trade tape once, keeps the last price at or before each minute
    boundary. Minutes before the first trade in the window are absent rather
    than invented.
    """
    off = utc_offset_hours(day)
    last_by_minute: dict[int, float] = {}
    with open_day(path) as f:
        for line in f:
            i = line.find('"ts_event": "')
            if i < 0:
                continue
            try:
                utc_s = int(line[i + 24:i + 26]) * 3600 + int(line[i + 27:i + 29]) * 60 + int(line[i + 30:i + 32])
            except ValueError:
                continue
            ct_s = utc_s + off * 3600
            if not start_s - 60 <= ct_s <= end_s:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            price = r["data"]["price"]
            # last write for the minute this trade belongs to wins (tape is
            # time-ordered per stream file)
            minute = ((ct_s + 59) // 60) * 60  # the boundary this trade marks
            last_by_minute[minute] = float(price)
    # forward-fill to a contiguous minute grid
    grid: list[tuple[int, float]] = []
    price = None
    for minute in range(((start_s + 59) // 60) * 60, end_s + 1, 60):
        if minute in last_by_minute:
            price = last_by_minute[minute]
        if price is not None:
            grid.append((minute, price))
    return grid


def infer_spx(prints: dict[str, list[tuple[int, float]]],
              entry_s: int, half_window_s: int = 180) -> float | None:
    """SPX near ``entry_s`` from 0DTE put-call parity (SPX ~= K + C - P).

    Median C and P per strike over [entry_s - half_window_s, entry_s +
    half_window_s) clipped to the coverage window; the five strikes with the
    smallest |C - P| (nearest the money) give the estimate. None when fewer
    than three strikes have both sides. Same method as final_hour_premium.py.
    """
    lo = max(entry_s - half_window_s, WINDOW_START_S)
    hi = entry_s + half_window_s
    by_strike: dict[float, dict[str, list[float]]] = {}
    for sym, path in prints.items():
        occ = parse_occ(sym)
        if not occ:
            continue
        window = [p for t, p in path if lo <= t < hi]
        if not window:
            continue
        by_strike.setdefault(occ[2], {"C": [], "P": []})[occ[1]].extend(window)
    diffs = []
    for k, cp in by_strike.items():
        if cp["C"] and cp["P"]:
            diffs.append((k, statistics.median(cp["C"]) - statistics.median(cp["P"])))
    if len(diffs) < 3:
        return None
    diffs.sort(key=lambda x: (abs(x[1]), x[0]))
    return statistics.median([k + delta for k, delta in diffs[:5]])


def minute_marks(path: list[tuple[int, float]],
                 start_s: int, end_s: int) -> list[tuple[int, float]]:
    """Last print at or before each whole CT minute in [start_s, end_s].

    Minutes before the first print carry nothing (absent, not zero); after
    the first print the last observation is carried forward.
    """
    grid: list[tuple[int, float]] = []
    i = 0
    price = None
    for minute in range(((start_s + 59) // 60) * 60, end_s + 1, 60):
        while i < len(path) and path[i][0] <= minute:
            price = path[i][1]
            i += 1
        if price is not None:
            grid.append((minute, price))
    return grid


def first_print_at_or_below(path: list[tuple[int, float]], level: float,
                            after_s: int) -> tuple[int, float] | None:
    """First raw print at/below ``level`` strictly after ``after_s`` — the
    print-resolution stop fire. Raw prints, not minute samples: a within-
    minute touch counts, which is exactly what a resting stop would see."""
    for t, p in path:
        if t > after_s and p <= level:
            return t, p
    return None


def first_print_at_or_above(path: list[tuple[int, float]], level: float,
                            after_s: int) -> tuple[int, float] | None:
    """First raw print at/above ``level`` strictly after ``after_s`` — the
    print-resolution target touch."""
    for t, p in path:
        if t > after_s and p >= level:
            return t, p
    return None
