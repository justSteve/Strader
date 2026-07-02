#!/usr/bin/env python3
"""Detect V-days in the ES.c.0 corpus per docs/measurement/v_day_definition.md [st-r2o].

Streams each day's ES trades from data/corpus/YYYY-MM-DD/databento_glbx_es.jsonl,
computes per-day pre-V baseline (VWAP_p) and action-window extrema, scales by
LATR_20, and applies the v0 V-day criteria (V-down and V-up symmetric). Writes one
row per day to data/measurement/v_days.jsonl.

Usage:
    .venv/bin/python scripts/measurement/detect_v_days.py
    .venv/bin/python scripts/measurement/detect_v_days.py --dry-run --limit 10
    .venv/bin/python scripts/measurement/detect_v_days.py --start-date 2026-05-01

See docs/measurement/v_day_definition.md for criteria + parameter rationale.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date as _date, datetime, time as _time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")

# Window definitions (CT)
P_START = _time(13, 0)
P_END = _time(13, 30)
A_START = _time(13, 30)
A_END = _time(15, 0)
CLOSE_START = _time(14, 55)
CLOSE_END = _time(15, 0)
LATE_START, LATE_END = P_START, A_END  # full late-day window for LATR

# Starting parameter values — see docs/measurement/v_day_definition.md
DEPTH_COEF = 0.6      # depth >= DEPTH_COEF * LATR_20
RECOVERY_FRAC = 0.5   # recovery >= RECOVERY_FRAC * depth
LANDING_COEF = 0.3    # |close - vwap_p| <= LANDING_COEF * LATR_20
LATR_WINDOW = 20      # prior trading days for LATR


@dataclass
class DayStats:
    date: _date
    trade_count: int = 0
    vwap_p: float | None = None
    range_p: float | None = None
    p_low: float | None = None
    p_high: float | None = None
    a_low: float | None = None       # trough_p
    a_low_t: datetime | None = None
    a_high: float | None = None      # peak_p
    a_high_t: datetime | None = None
    close_p: float | None = None
    late_range: float | None = None


def compute_day_stats(d: _date, es_path: Path) -> DayStats:
    """Single-pass streaming computation of per-day stats — constant memory."""
    s = DayStats(date=d)
    p_pv = 0.0
    p_v = 0
    p_low: float | None = None
    p_high: float | None = None
    a_low_p: float | None = None
    a_low_t: datetime | None = None
    a_high_p: float | None = None
    a_high_t: datetime | None = None
    close_p: float | None = None
    late_low: float | None = None
    late_high: float | None = None

    with es_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ts_event_str = rec["provenance"]["ts_event"]
                price = rec["data"]["price"]
                size = rec["data"]["size"]
                if price is None or size is None:
                    continue
                price = float(price)
                size = int(size)
                ts_utc = datetime.fromisoformat(ts_event_str)
                ts_ct = ts_utc.astimezone(CENTRAL)
            except (KeyError, ValueError, TypeError):
                continue

            tod = ts_ct.time()
            s.trade_count += 1

            if LATE_START <= tod < LATE_END:
                late_low = price if late_low is None else min(late_low, price)
                late_high = price if late_high is None else max(late_high, price)

            if P_START <= tod < P_END:
                p_pv += price * size
                p_v += size
                p_low = price if p_low is None else min(p_low, price)
                p_high = price if p_high is None else max(p_high, price)
            elif A_START <= tod < A_END:
                if a_low_p is None or price < a_low_p:
                    a_low_p, a_low_t = price, ts_ct
                if a_high_p is None or price > a_high_p:
                    a_high_p, a_high_t = price, ts_ct

            if CLOSE_START <= tod < CLOSE_END:
                close_p = price  # last assignment wins → last close-window tick

    if p_v > 0:
        s.vwap_p = p_pv / p_v
        s.p_low = p_low
        s.p_high = p_high
        s.range_p = p_high - p_low  # type: ignore[operator]
    s.a_low = a_low_p
    s.a_low_t = a_low_t
    s.a_high = a_high_p
    s.a_high_t = a_high_t
    s.close_p = close_p
    if late_low is not None and late_high is not None:
        s.late_range = late_high - late_low
    return s


def compute_latr_20(target: _date, late_ranges: dict[_date, float]) -> float | None:
    """LATR_20 = mean of late-day range over the prior LATR_WINDOW trading days."""
    prior: list[float] = []
    cursor = target
    safety = 0
    while len(prior) < LATR_WINDOW and safety < 90:
        cursor -= timedelta(days=1)
        safety += 1
        if cursor in late_ranges:
            prior.append(late_ranges[cursor])
    if len(prior) < LATR_WINDOW:
        return None
    return sum(prior) / len(prior)


def label_day(s: DayStats, latr_20: float | None) -> dict:
    row: dict = {
        "date": s.date.isoformat(),
        "label": "unlabeled",
        "vwap_p": s.vwap_p,
        "range_p": s.range_p,
        "trough_p": s.a_low,
        "trough_t": s.a_low_t.isoformat() if s.a_low_t else None,
        "peak_p": s.a_high,
        "peak_t": s.a_high_t.isoformat() if s.a_high_t else None,
        "close_p": s.close_p,
        "latr_20": latr_20,
        "trade_count": s.trade_count,
    }

    if latr_20 is None:
        row["reason"] = "insufficient prior days for LATR_20"
        return row
    if s.vwap_p is None:
        row["label"] = "none"
        row["reason"] = "no trades in pre-V window P [13:00, 13:30) CT"
        return row
    if s.close_p is None:
        row["label"] = "none"
        row["reason"] = "no trades in close window [14:55, 15:00) CT"
        return row
    if s.a_low is None or s.a_high is None:
        row["label"] = "none"
        row["reason"] = "no trades in action window A [13:30, 15:00) CT"
        return row

    depth_thresh = DEPTH_COEF * latr_20
    landing_thresh = LANDING_COEF * latr_20
    landing = abs(s.close_p - s.vwap_p)

    # V-down arm
    depth_down = s.vwap_p - s.a_low
    recovery_down = s.close_p - s.a_low
    v_down_crit = {
        "in_A": True,
        "below_vwap": s.a_low < s.vwap_p,
        "depth_ok": depth_down >= depth_thresh,
        "recovery_ok": depth_down > 0 and recovery_down >= RECOVERY_FRAC * depth_down,
        "landing_ok": landing <= landing_thresh,
    }
    v_down_fires = all(v_down_crit.values())
    row["v_down"] = {
        "depth": depth_down, "recovery": recovery_down, "landing": landing,
        "criteria": v_down_crit,
    }

    # V-up arm (symmetric)
    depth_up = s.a_high - s.vwap_p
    recovery_up = s.a_high - s.close_p
    v_up_crit = {
        "in_A": True,
        "above_vwap": s.a_high > s.vwap_p,
        "depth_ok": depth_up >= depth_thresh,
        "recovery_ok": depth_up > 0 and recovery_up >= RECOVERY_FRAC * depth_up,
        "landing_ok": landing <= landing_thresh,
    }
    v_up_fires = all(v_up_crit.values())
    row["v_up"] = {
        "depth": depth_up, "recovery": recovery_up, "landing": landing,
        "criteria": v_up_crit,
    }

    if v_down_fires and v_up_fires:
        row["label"] = "v_both"
    elif v_down_fires:
        row["label"] = "v_down"
    elif v_up_fires:
        row["label"] = "v_up"
    else:
        row["label"] = "none"
    return row


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    corpus_root = repo_root / "data" / "corpus"
    output_path = repo_root / "data" / "measurement" / "v_days.jsonl"

    parser = argparse.ArgumentParser(description="Detect V-days in the ES corpus")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N days")
    parser.add_argument("--dry-run", action="store_true", help="Print stats, don't write")
    args = parser.parse_args()

    # Enumerate dated dirs with an ES file
    candidates = []
    for p in corpus_root.iterdir():
        if not p.is_dir() or p.name.startswith("_"):
            continue
        if not (p / "databento_glbx_es.jsonl").exists():
            continue
        try:
            candidates.append(_date.fromisoformat(p.name))
        except ValueError:
            continue
    candidates.sort()
    if args.start_date:
        sd = _date.fromisoformat(args.start_date)
        candidates = [d for d in candidates if d >= sd]
    if args.end_date:
        ed = _date.fromisoformat(args.end_date)
        candidates = [d for d in candidates if d <= ed]
    if args.limit:
        candidates = candidates[: args.limit]

    if not candidates:
        print("# No corpus days matched the filters")
        return 1

    print(f"# V-day detection — {len(candidates)} day(s)", flush=True)

    # Pass 1: per-day stats (streaming)
    stats_by_date: dict[_date, DayStats] = {}
    late_ranges: dict[_date, float] = {}
    for i, d in enumerate(candidates):
        es_path = corpus_root / d.isoformat() / "databento_glbx_es.jsonl"
        s = compute_day_stats(d, es_path)
        stats_by_date[d] = s
        if s.late_range is not None:
            late_ranges[d] = s.late_range
        if (i + 1) % 25 == 0 or (i + 1) == len(candidates):
            print(f"  parsed {i+1}/{len(candidates)} days", flush=True)

    # Pass 2: labels
    rows = [label_day(stats_by_date[d], compute_latr_20(d, late_ranges))
            for d in candidates]

    # Summary
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["label"]] = counts.get(r["label"], 0) + 1
    n = len(rows)
    print("\n# Label distribution")
    for label in ("v_down", "v_up", "v_both", "none", "unlabeled"):
        c = counts.get(label, 0)
        pct = 100.0 * c / n if n else 0
        print(f"  {label:11s} {c:4d}  ({pct:5.1f}%)")

    if args.dry_run:
        print("\n# Dry run — not writing output")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"\n# Wrote {n} rows -> {output_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
