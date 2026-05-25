#!/usr/bin/env python3
"""Classify non-pivot days with drops >= 15pts into day types.

Categories:
  - CONSOLIDATION_THEN_DROP: Price established a trading range before the drop.
    Detected by finding a stretch >= 10 minutes where range < 40% of total pre-trough range.
  - TREND_DOWN: Price declined steadily from window start to trough.
    Detected by linear regression R^2 > 0.7 with negative slope.
  - OTHER: Doesn't fit either pattern.

Data:
  - v_days.jsonl: dates, trough times, v_down.depth
  - confirmed_v_days_v0.txt: confirmed pivot days to exclude
  - ES trades: data/corpus/{date}/databento_glbx_es.jsonl

Output: data/measurement/day_types.jsonl — one JSON line per classified day.

Usage:
    .venv/bin/python scripts/measurement/day_type_classifier.py
    .venv/bin/python scripts/measurement/day_type_classifier.py --dry-run --limit 5

[st-745]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import date as _date, datetime, time as _time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def get_ts_event_iso(provenance: dict) -> str | None:
    """Extract ts_event as ISO string, handling both string and nanosecond formats."""
    if "ts_event" in provenance:
        return provenance["ts_event"]
    if "ts_event_ns" in provenance:
        ns = provenance["ts_event_ns"]
        dt = datetime.fromtimestamp(ns / 1e9, tz=UTC)
        return dt.isoformat()
    return None


PROJECT_ROOT = Path("/root/projects/Strader")
CORPUS_DIR = PROJECT_ROOT / "data" / "corpus"
V_DAYS_PATH = PROJECT_ROOT / "data" / "measurement" / "v_days.jsonl"
CONFIRMED_PATH = PROJECT_ROOT / "data" / "measurement" / "confirmed_v_days_v0.txt"
OUTPUT_PATH = PROJECT_ROOT / "data" / "measurement" / "day_types.jsonl"

# Classification parameters
MIN_DEPTH_PTS = 15.0
CONSOLIDATION_MIN_MINUTES = 10
CONSOLIDATION_RANGE_RATIO = 0.40  # consol range < 40% of total pre-trough range
TREND_R2_THRESHOLD = 0.70


def load_confirmed_v_days() -> set[str]:
    """Load confirmed V-day dates to exclude."""
    confirmed = set()
    if not CONFIRMED_PATH.exists():
        return confirmed
    with CONFIRMED_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                confirmed.add(line)
    return confirmed


def load_candidate_days() -> list[dict]:
    """Load days from v_days.jsonl with v_down.depth >= 15 pts, excluding confirmed V-days."""
    confirmed = load_confirmed_v_days()
    candidates = []

    with V_DAYS_PATH.open() as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            # Must have v_down with sufficient depth
            v_down = rec.get("v_down")
            if not v_down:
                continue
            depth = v_down.get("depth", 0)
            if depth < MIN_DEPTH_PTS:
                continue
            # Exclude confirmed V-days
            if rec["date"] in confirmed:
                continue
            candidates.append(rec)

    return candidates


def build_1min_ohlc(es_path: Path, start_utc: datetime, end_utc: datetime) -> list[dict]:
    """Build 1-minute OHLC bars from ES trade ticks in [start_utc, end_utc).

    Returns list of dicts: {minute: datetime, open, high, low, close, volume}
    """
    start_iso = start_utc.isoformat()
    end_iso = end_utc.isoformat()

    # Group trades by minute
    minute_trades: dict[str, list[tuple[float, int, str]]] = defaultdict(list)

    with es_path.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_event = get_ts_event_iso(rec["provenance"])
            if ts_event is None:
                continue
            if ts_event < start_iso:
                continue
            if ts_event >= end_iso:
                break

            price = rec["data"]["price"]
            size = rec["data"]["size"]
            # Truncate to minute key
            minute_key = ts_event[:16]  # "YYYY-MM-DDTHH:MM"
            minute_trades[minute_key].append((price, size, ts_event))

    # Convert to OHLC
    bars = []
    for minute_key in sorted(minute_trades.keys()):
        trades = minute_trades[minute_key]
        # Sort by timestamp to get proper open/close
        trades.sort(key=lambda t: t[2])
        prices = [t[0] for t in trades]
        volumes = [t[1] for t in trades]
        bars.append({
            "minute": minute_key,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum(volumes),
        })

    return bars


def detect_consolidation(bars: list[dict], total_range: float) -> tuple[bool, float | None, int | None]:
    """Detect consolidation phase: stretch >= 10 minutes where range < 40% of total pre-trough range.

    Returns: (found, consolidation_range_pts, consolidation_duration_min)
    """
    if not bars or total_range <= 0:
        return False, None, None

    threshold = CONSOLIDATION_RANGE_RATIO * total_range
    n = len(bars)

    best_duration = 0
    best_range = None

    # Sliding window: find longest stretch where rolling range < threshold
    for start_idx in range(n):
        running_high = bars[start_idx]["high"]
        running_low = bars[start_idx]["low"]

        for end_idx in range(start_idx, n):
            running_high = max(running_high, bars[end_idx]["high"])
            running_low = min(running_low, bars[end_idx]["low"])
            window_range = running_high - running_low

            if window_range >= threshold:
                break

            duration = end_idx - start_idx + 1
            if duration > best_duration:
                best_duration = duration
                best_range = window_range

    if best_duration >= CONSOLIDATION_MIN_MINUTES:
        return True, round(best_range, 2) if best_range is not None else None, best_duration

    return False, None, None


def compute_linear_regression(closes: list[float]) -> tuple[float, float]:
    """Compute R^2 and slope of linear regression for close prices vs minute index.

    Returns: (r_squared, slope_pts_per_min)
    """
    n = len(closes)
    if n < 3:
        return 0.0, 0.0

    # x = 0, 1, 2, ..., n-1 (minute index)
    x_mean = (n - 1) / 2.0
    y_mean = statistics.mean(closes)

    # Compute slope and R^2
    ss_xx = sum((i - x_mean) ** 2 for i in range(n))
    ss_yy = sum((y - y_mean) ** 2 for y in closes)
    ss_xy = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))

    if ss_xx == 0 or ss_yy == 0:
        return 0.0, 0.0

    slope = ss_xy / ss_xx
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy)

    return r_squared, slope


def classify_day(day_rec: dict, es_path: Path) -> dict | None:
    """Classify a single day as consolidation_then_drop, trend_down, or other."""
    d = _date.fromisoformat(day_rec["date"])
    depth = day_rec["v_down"]["depth"]

    # Parse trough time (stored in CT with offset)
    trough_t_str = day_rec["trough_t"]
    trough_dt = datetime.fromisoformat(trough_t_str)
    # Convert to UTC for comparison with file timestamps
    trough_utc = trough_dt.astimezone(UTC)

    # Window start: 13:00 CT
    start_ct = datetime.combine(d, _time(13, 0), tzinfo=CENTRAL)
    start_utc = start_ct.astimezone(UTC)

    # Sanity: trough must be after start
    if trough_utc <= start_utc:
        return None

    # Build 1-minute OHLC from window start to trough
    bars = build_1min_ohlc(es_path, start_utc, trough_utc)
    if len(bars) < 5:
        return None

    # Total pre-trough range
    all_highs = [b["high"] for b in bars]
    all_lows = [b["low"] for b in bars]
    pre_trough_range = max(all_highs) - min(all_lows)

    if pre_trough_range <= 0:
        return None

    # Classification 1: Consolidation detection
    has_consol, consol_range, consol_duration = detect_consolidation(bars, pre_trough_range)

    # Classification 2: Trend-down detection (linear regression on closes)
    closes = [b["close"] for b in bars]
    r2, slope = compute_linear_regression(closes)
    is_trend_down = r2 > TREND_R2_THRESHOLD and slope < 0

    # Determine day type
    # Trend-down takes priority: if price declined in a straight line (R2>0.7),
    # any brief quiet period was part of the trend, not a true consolidation zone.
    if is_trend_down:
        day_type = "trend_down"
    elif has_consol:
        day_type = "consolidation_then_drop"
    else:
        day_type = "other"

    return {
        "date": day_rec["date"],
        "day_type": day_type,
        "r2_to_trough": round(r2, 4),
        "slope_pts_per_min": round(slope, 4),
        "consolidation_range_pts": consol_range,
        "consolidation_duration_min": consol_duration,
        "pre_trough_range_pts": round(pre_trough_range, 2),
        "depth_pts": round(depth, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Classify non-pivot days by pattern type")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing file")
    parser.add_argument("--limit", type=int, default=0, help="Process only N days (0=all)")
    args = parser.parse_args()

    candidates = load_candidate_days()
    if args.limit:
        candidates = candidates[:args.limit]

    print(f"Classifying {len(candidates)} days with v_down.depth >= {MIN_DEPTH_PTS} pts "
          f"(excluding confirmed V-days)...", file=sys.stderr)

    results: list[dict] = []
    skipped = 0

    for day_rec in candidates:
        date_str = day_rec["date"]
        es_path = CORPUS_DIR / date_str / "databento_glbx_es.jsonl"

        if not es_path.exists():
            skipped += 1
            print(f"  SKIP {date_str}: no ES data", file=sys.stderr)
            continue

        result = classify_day(day_rec, es_path)
        if result is None:
            skipped += 1
            print(f"  SKIP {date_str}: insufficient bars", file=sys.stderr)
            continue

        results.append(result)
        print(f"  {date_str}: {result['day_type']:>25} "
              f"(R2={result['r2_to_trough']:.3f} slope={result['slope_pts_per_min']:.3f} "
              f"consol={result['consolidation_duration_min'] or '-'}min "
              f"depth={result['depth_pts']:.1f})",
              file=sys.stderr)

    # Summary
    if results:
        from collections import Counter
        type_counts = Counter(r["day_type"] for r in results)
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"DAY TYPE CLASSIFICATION SUMMARY", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"  Total classified: {len(results)} (skipped: {skipped})", file=sys.stderr)
        print(f"  consolidation_then_drop: {type_counts.get('consolidation_then_drop', 0)}", file=sys.stderr)
        print(f"  trend_down:              {type_counts.get('trend_down', 0)}", file=sys.stderr)
        print(f"  other:                   {type_counts.get('other', 0)}", file=sys.stderr)

        # Depth stats by type
        for dtype in ["consolidation_then_drop", "trend_down", "other"]:
            subset = [r for r in results if r["day_type"] == dtype]
            if subset:
                depths = [r["depth_pts"] for r in subset]
                print(f"\n  {dtype}:", file=sys.stderr)
                print(f"    Mean depth: {statistics.mean(depths):.1f} pts", file=sys.stderr)
                print(f"    Median depth: {statistics.median(depths):.1f} pts", file=sys.stderr)

    # Write output
    if not args.dry_run and results:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_PATH.open("w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"\nWrote {len(results)} records to {OUTPUT_PATH}", file=sys.stderr)
    elif args.dry_run:
        for r in results[:5]:
            print(json.dumps(r, indent=2))
        if len(results) > 5:
            print(f"... ({len(results)} total)")


if __name__ == "__main__":
    main()
