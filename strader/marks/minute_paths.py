"""Minute paths from the corpus — prints and ES tape, on one CT minute grid. [st-9hhc]

WHY
    The proxy in :mod:`strader.marks.estimated` needs, per leg-day, the leg's
    own print path (the truth it is scored against) and the ES minute bars it
    is driven by. Both live in ``data/corpus/<day>/`` as JSONL, plain or
    gzipped, and both carry the same two traps: the usable timestamp is
    ``provenance.ts_event`` (ISO 8601, UTC, nanoseconds), never a top-level
    ``ts_event``; and the payload sits under ``data``. A naive top-level read
    returns nothing and looks like an empty file. This module is the one
    place those shapes are known.

WHAT
    * :func:`read_opra_day` — every 0DTE SPXW print on the day, keyed by
      symbol, as (seconds-since-midnight CT, price), plus the measured print
      coverage of the whole file: first and last print minute and a count per
      CT hour. The coverage is measured on every row, inside the window or
      not, because the coverage bound is the claim and it is measured, not
      assumed.
    * :func:`read_es_day` — every ES print in a CT window as (second, price).
    * :func:`es_minute_bars` — OHLC per CT minute from those prints.
    * :func:`es_at` — the last ES print at or before a second.
    * :func:`parity_spx` — SPX at an instant from 0DTE put-call parity on the
      prints within a few minutes of it (SPX ~= K + C - P, carry ignored).
    * :func:`print_minute_marks` — per minute, the leg's last print, low and
      high, from its own prints.

    Time is CT throughout. The corpus stores UTC; the day's offset is taken
    from America/Chicago once per day so DST is right on both sides of it.
"""
from __future__ import annotations

import gzip
import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from strader.marks.estimated import MinuteBar, minute_index, minute_label

__all__ = [
    "CT", "OpraDay", "PrintCoverage", "read_opra_day", "read_es_day",
    "es_minute_bars", "es_at", "parity_spx", "print_minute_marks", "parse_symbol",
    "ct_offset_seconds", "open_text", "resolve_day_file",
]

CT = ZoneInfo("America/Chicago")
_TS_KEY = '"ts_event": "'


def ct_offset_seconds(day: str) -> int:
    """UTC offset of America/Chicago at noon on ``day`` (YYYY-MM-DD), seconds."""
    y, m, d = (int(x) for x in day.split("-"))
    return int(datetime(y, m, d, 12, tzinfo=CT).utcoffset().total_seconds())


def open_text(path: Path):
    """Plain or gzipped JSONL, read as text."""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def resolve_day_file(day_dir: Path, name: str) -> Path | None:
    """``name`` or ``name.gz`` under ``day_dir``, plain preferred; None if neither."""
    p = day_dir / name
    if p.exists():
        return p
    gz = day_dir / (name + ".gz")
    return gz if gz.exists() else None


def _utc_seconds_from_line(line: str) -> int | None:
    """Seconds since UTC midnight from the ts_event substring, without a full
    JSON parse. The corpus writes ``"ts_event": "YYYY-MM-DDTHH:MM:SS.…"``;
    None when the key is absent or malformed."""
    i = line.find(_TS_KEY)
    if i < 0:
        return None
    j = i + len(_TS_KEY) + 11          # past "YYYY-MM-DDT"
    hms = line[j:j + 8]
    if len(hms) != 8 or hms[2] != ":" or hms[5] != ":":
        return None
    try:
        return int(hms[:2]) * 3600 + int(hms[3:5]) * 60 + int(hms[6:8])
    except ValueError:
        return None


def parse_symbol(sym: str) -> tuple[str, str, float] | None:
    """"SPXW  250807C06345000" -> ("250807", "C", 6345.0); None if not SPXW."""
    parts = sym.split()
    if len(parts) != 2 or parts[0] != "SPXW":
        return None
    body = parts[1]
    if len(body) < 8 or body[6] not in ("C", "P"):
        return None
    try:
        return body[:6], body[6], int(body[7:]) / 1000.0
    except ValueError:
        return None


@dataclass
class PrintCoverage:
    """What the OPRA file actually holds, measured over every row."""

    n_rows: int = 0
    n_0dte: int = 0
    first_minute_ct: str | None = None
    last_minute_ct: str | None = None
    rows_per_hour_ct: dict[str, int] = field(default_factory=dict)

    def note(self, sec_ct: int) -> None:
        minute = minute_label(sec_ct // 60)
        if self.first_minute_ct is None or minute < self.first_minute_ct:
            self.first_minute_ct = minute
        if self.last_minute_ct is None or minute > self.last_minute_ct:
            self.last_minute_ct = minute
        hour = f"{sec_ct // 3600:02d}"
        self.rows_per_hour_ct[hour] = self.rows_per_hour_ct.get(hour, 0) + 1

    def to_dict(self) -> dict:
        return {
            "n_rows": self.n_rows, "n_0dte": self.n_0dte,
            "first_minute_ct": self.first_minute_ct, "last_minute_ct": self.last_minute_ct,
            "rows_per_hour_ct": dict(sorted(self.rows_per_hour_ct.items())),
        }


@dataclass
class OpraDay:
    day: str
    prints: dict[str, list[tuple[int, float]]]      # symbol -> [(sec_ct, price)] sorted
    coverage: PrintCoverage

    def strikes(self) -> dict[float, dict[str, list[tuple[int, float]]]]:
        """strike -> {"C": prints, "P": prints} for the day's 0DTE symbols."""
        out: dict[float, dict[str, list[tuple[int, float]]]] = {}
        for sym, ps in self.prints.items():
            parsed = parse_symbol(sym)
            if parsed is None:
                continue
            _, cp, k = parsed
            out.setdefault(k, {"C": [], "P": []})[cp] = ps
        return out


def read_opra_day(path: Path, day: str) -> OpraDay:
    """All 0DTE SPXW prints on ``day`` plus the file's measured coverage.

    Coverage counts every row in the file, 0DTE or not, inside the window or
    not; ``prints`` keeps only the day's own expiry.
    """
    off = ct_offset_seconds(day)
    y, m, d = day.split("-")
    exp = f"{y[2:]}{m}{d}"
    tag = f"SPXW  {exp}"
    cov = PrintCoverage()
    prints: dict[str, list[tuple[int, float]]] = {}
    with open_text(path) as f:
        for line in f:
            utc = _utc_seconds_from_line(line)
            if utc is None:
                continue
            sec_ct = utc + off
            if sec_ct < 0:
                sec_ct += 86400
            cov.n_rows += 1
            cov.note(sec_ct)
            if tag not in line:
                continue
            try:
                r = json.loads(line)
                data = r["data"]
                sym = data["symbol"]
                price = float(data["price"])
            except (ValueError, KeyError, TypeError):
                continue
            parsed = parse_symbol(sym)
            if parsed is None or parsed[0] != exp:
                continue
            cov.n_0dte += 1
            prints.setdefault(sym, []).append((sec_ct, price))
    for ps in prints.values():
        ps.sort()
    return OpraDay(day=day, prints=prints, coverage=cov)


def read_es_day(path: Path, day: str, window_ct: tuple[str, str]) -> list[tuple[int, float]]:
    """ES prints in [window_ct[0], window_ct[1]) as (sec_ct, price), sorted."""
    off = ct_offset_seconds(day)
    lo = minute_index(window_ct[0]) * 60
    hi = minute_index(window_ct[1]) * 60
    out: list[tuple[int, float]] = []
    with open_text(path) as f:
        for line in f:
            utc = _utc_seconds_from_line(line)
            if utc is None:
                continue
            sec_ct = utc + off
            if sec_ct < 0:
                sec_ct += 86400
            if sec_ct < lo or sec_ct >= hi:
                continue
            try:
                price = float(json.loads(line)["data"]["price"])
            except (ValueError, KeyError, TypeError):
                continue
            out.append((sec_ct, price))
    out.sort()
    return out


def es_minute_bars(prints: Sequence[tuple[int, float]]) -> dict[str, MinuteBar]:
    """OHLC per CT minute. Minutes with no print are absent, not filled."""
    bars: dict[str, MinuteBar] = {}
    cur: str | None = None
    o = h = l = c = 0.0
    n = 0
    for sec, price in prints:
        minute = minute_label(sec // 60)
        if minute != cur:
            if cur is not None:
                bars[cur] = MinuteBar(cur, o, h, l, c, n)
            cur, o, h, l, c, n = minute, price, price, price, price, 0
        h = max(h, price)
        l = min(l, price)
        c = price
        n += 1
    if cur is not None:
        bars[cur] = MinuteBar(cur, o, h, l, c, n)
    return bars


def es_at(prints: Sequence[tuple[int, float]], sec_ct: int) -> float | None:
    """Last ES print at or before ``sec_ct``; None if nothing precedes it."""
    import bisect
    i = bisect.bisect_right(prints, (sec_ct, float("inf")))
    return prints[i - 1][1] if i else None


def parity_spx(strikes: Mapping[float, Mapping[str, Sequence[tuple[int, float]]]],
               sec_ct: int, *, half_window_s: int = 180, min_strikes: int = 3,
               use_nearest: int = 5) -> float | None:
    """SPX at ``sec_ct`` from 0DTE put-call parity on nearby prints.

    For each strike with both a call and a put print inside +-half_window_s,
    S_k = K + median(C) - median(P). The ``use_nearest`` strikes with the
    smallest |C - P| (closest to the money, cleanest) vote; the median wins.
    None when fewer than ``min_strikes`` strikes qualify.
    """
    lo, hi = sec_ct - half_window_s, sec_ct + half_window_s
    diffs: list[tuple[float, float]] = []
    for k in sorted(strikes):
        cp = strikes[k]
        c = [p for s, p in cp.get("C", ()) if lo <= s <= hi]
        p = [q for s, q in cp.get("P", ()) if lo <= s <= hi]
        if c and p:
            diffs.append((k, statistics.median(c) - statistics.median(p)))
    if len(diffs) < min_strikes:
        return None
    diffs.sort(key=lambda x: (abs(x[1]), x[0]))
    return statistics.median([k + d for k, d in diffs[:use_nearest]])


@dataclass(frozen=True)
class PrintMinute:
    minute: str
    close: float
    low: float
    high: float
    n: int


def print_minute_marks(prints: Sequence[tuple[int, float]], *, from_sec: int,
                       to_minute: str) -> dict[str, PrintMinute]:
    """The leg's own prints per CT minute, from ``from_sec`` (exclusive: the
    entry print itself is not a mark) up to but excluding ``to_minute``."""
    end = minute_index(to_minute)
    out: dict[str, PrintMinute] = {}
    cur: str | None = None
    lo = hi = close = 0.0
    n = 0
    for sec, price in prints:
        if sec <= from_sec:
            continue
        idx = sec // 60
        if idx >= end:
            break
        minute = minute_label(idx)
        if minute != cur:
            if cur is not None:
                out[cur] = PrintMinute(cur, close, lo, hi, n)
            cur, lo, hi, close, n = minute, price, price, price, 0
        lo = min(lo, price)
        hi = max(hi, price)
        close = price
        n += 1
    if cur is not None:
        out[cur] = PrintMinute(cur, close, lo, hi, n)
    return out
