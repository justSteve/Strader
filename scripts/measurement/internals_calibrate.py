#!/usr/bin/env python3
"""Seed the MI gauge's TICK percentile scale from the internals corpus. [st-3fr]

Reads every `data/corpus/*/internals.jsonl`, buckets $TICK minute candles by
time-of-day, and reports the distribution of per-minute extremes (candle
high for positive, low for negative — the wick IS the climax; closes
understate it). The gauge's "climax" thresholds are seeded from these
percentiles per bucket, replacing folklore constants like +/-1000 with the
tape's actual recent distribution.

Buckets follow the drill/session vocabulary (CT):
    open-drive 08:30-09:15 | morning 09:15-11:00 | midday 11:00-13:00
    | afternoon 13:00-15:00

Usage:
    .venv/bin/python scripts/measurement/internals_calibrate.py
    .venv/bin/python scripts/measurement/internals_calibrate.py --symbol $TICK
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import time as _time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

CORPUS = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"

BUCKETS = (
    ("open-drive", _time(8, 30), _time(9, 15)),
    ("morning", _time(9, 15), _time(11, 0)),
    ("midday", _time(11, 0), _time(13, 0)),
    ("afternoon", _time(13, 0), _time(15, 0)),
)


def bucket_of(t: _time) -> str | None:
    for name, lo, hi in BUCKETS:
        if lo <= t < hi:
            return name
    return None


def pctl(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def main() -> int:
    ap = argparse.ArgumentParser(description="MI gauge TICK seed calibration")
    ap.add_argument("--symbol", default="$TICK")
    args = ap.parse_args()

    highs: dict[str, list[float]] = defaultdict(list)   # positive climaxes
    lows: dict[str, list[float]] = defaultdict(list)    # negative climaxes
    day_max: list[float] = []
    day_min: list[float] = []
    sessions = 0

    for day_dir in sorted(CORPUS.iterdir()):
        f = day_dir / "internals.jsonl"
        if not f.exists():
            continue
        dmax, dmin, seen = float("-inf"), float("inf"), False
        for line in f.open(encoding="utf-8"):
            row = json.loads(line)
            if row["data"]["symbol"] != args.symbol:
                continue
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(row["provenance"]["ts_candle"])
            b = bucket_of(ts.time())
            if b is None:
                continue
            hi, lo = row["data"]["high"], row["data"]["low"]
            if hi is None or lo is None:
                continue
            seen = True
            highs[b].append(hi)
            lows[b].append(lo)
            dmax, dmin = max(dmax, hi), min(dmin, lo)
        if seen:
            sessions += 1
            day_max.append(dmax)
            day_min.append(dmin)

    print(f"# {args.symbol} seed calibration — {sessions} sessions")
    print(f"\n## per-minute extreme percentiles by bucket")
    print(f"  {'bucket':<12} {'side':<4} " +
          "".join(f"p{int(q*100):<7}" for q in (.5, .75, .9, .95, .99)))
    for name, _, _ in BUCKETS:
        hs = sorted(highs[name])
        ls = sorted(lows[name], reverse=True)  # most negative = highest rank
        print(f"  {name:<12} high " +
              "".join(f"{pctl(hs, q):<8.0f}" for q in (.5, .75, .9, .95, .99)))
        print(f"  {'':<12} low  " +
              "".join(f"{pctl(ls, q):<8.0f}" for q in (.5, .75, .9, .95, .99)))

    day_max.sort()
    day_min.sort(reverse=True)
    print(f"\n## session extremes across {sessions} sessions")
    print(f"  daily max TICK: median {pctl(day_max, .5):.0f}, "
          f"p90 {pctl(day_max, .9):.0f}, max {day_max[-1]:.0f}")
    print(f"  daily min TICK: median {pctl(day_min, .5):.0f}, "
          f"p90 {pctl(day_min, .9):.0f}, min {day_min[-1]:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
