#!/usr/bin/env python3
"""Calibrate absorption floors against a purchased MBP-1 corpus day. [st-9vl]

Streams the day through AbsorptionTracker with the emission floors dropped
(vol >= --min-vol, refills >= 0) so EVERY episode with meaningful aggression
surfaces, then reports:

  - distribution of per-episode aggressive volume and refill counts
  - an emission-count grid over candidate (ABSORPTION_VOL_MIN,
    ABSORPTION_REFILL_MIN) floors — pick the cell whose daily count means
    "rare enough to mean something" (the large-lot/sweep lesson, st-wnc:
    ~30-40/session, not thousands)
  - the top episodes by volume, with timestamps, for eyeball verification
    against the chart

Usage:
    .venv/bin/python scripts/measurement/absorption_calibrate.py --date 2026-07-02
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import market.orderflow.absorption as _abs  # noqa: E402
from market.orderflow.absorption import AbsorptionTracker  # noqa: E402
from market.orderflow.quotes import read_mbp1_day  # noqa: E402

VOL_CANDIDATES = (100, 200, 300, 500, 750, 1_000, 1_500)
REFILL_CANDIDATES = (1, 2, 3, 4, 6)


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def main() -> int:
    parser = argparse.ArgumentParser(description="Absorption floor calibration")
    parser.add_argument("--date", required=True)
    parser.add_argument("--min-vol", type=int, default=50,
                        help="episode aggressive-volume floor for collection (default 50)")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--vol-floor", type=int, default=100,
                        help="candidate ABSORPTION_VOL_MIN for the hit list")
    parser.add_argument("--refill-floor", type=int, default=2,
                        help="candidate ABSORPTION_REFILL_MIN for the hit list")
    args = parser.parse_args()

    # drop the emission floors so calibration sees the raw episode population
    _abs.ABSORPTION_VOL_MIN = args.min_vol
    _abs.ABSORPTION_REFILL_MIN = 0

    day = _date.fromisoformat(args.date)
    tracker = AbsorptionTracker()
    reads = []
    n_events = 0
    for e in read_mbp1_day(day):
        n_events += 1
        reads.extend(tracker.process(e))
    reads.extend(tracker.flush())

    print(f"# absorption calibration — {day} ({n_events:,} book events)")
    print(f"  episodes with aggr_vol >= {args.min_vol}: {len(reads):,}")

    vols = sorted(r.aggressive_vol for r in reads)
    refs = sorted(r.refill_events for r in reads)
    print("\n## per-episode distributions")
    for name, vals in (("aggr_vol", vols), ("refill_events", refs)):
        print(f"  {name:14s} p50={pct(vals, .50):>6} p75={pct(vals, .75):>6} "
              f"p90={pct(vals, .90):>6} p99={pct(vals, .99):>6} max={vals[-1] if vals else 0:>6}")

    print("\n## emissions/day at candidate floors (vol_min rows x refill_min cols)")
    header = "  vol_min  " + "".join(f"r>={r:<6}" for r in REFILL_CANDIDATES)
    print(header)
    for v in VOL_CANDIDATES:
        cells = []
        for r in REFILL_CANDIDATES:
            n = sum(1 for x in reads if x.aggressive_vol >= v and x.refill_events >= r)
            cells.append(f"{n:<8}")
        print(f"  {v:<9}" + "".join(cells))

    print(f"\n## top {args.top} episodes by aggressive volume")
    for r in sorted(reads, key=lambda x: -x.aggressive_vol)[:args.top]:
        print(f"  {r.timestamp.strftime('%H:%M:%S')} CT  {r.side:3s} {r.price:>9.2f}  "
              f"vol={r.aggressive_vol:<6} refills={r.refill_events:<3} "
              f"disp={r.displacement_ticks:+d}")

    print(f"\n## every episode clearing (vol>={args.vol_floor}, refills>={args.refill_floor})")
    hits = [r for r in reads if r.aggressive_vol >= args.vol_floor
            and r.refill_events >= args.refill_floor]
    for r in sorted(hits, key=lambda x: x.timestamp):
        print(f"  {r.timestamp.strftime('%H:%M:%S')} CT  {r.side:3s} {r.price:>9.2f}  "
              f"vol={r.aggressive_vol:<6} refills={r.refill_events:<3} "
              f"disp={r.displacement_ticks:+d}")

    hours = Counter(r.timestamp.strftime("%H") for r in hits)
    print(f"\n## hourly count at those floors")
    for h in sorted(hours):
        print(f"  {h}:00 CT  {hours[h]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
