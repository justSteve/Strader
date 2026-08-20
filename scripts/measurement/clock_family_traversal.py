#!/usr/bin/env python3
"""Hour-of-day baseline for price displacement and giant flow prints. [st-1bv1]

WHY. The Strader bundle concept "Channel Family Taxonomy" (st-a3yh) records
CLOCK as the strongest single predictor the continuation audit found — day-
median AUC .875 against the deliverable's .607 — AND as a NEVER-TRAVERSED
family. Its procedure is binding: a study design opens by traversing the family
list and writing a verdict per family BEFORE measuring. Orderflow edge-test
rounds 1-4 (st-yirc, st-mvvf, st-gkbo, st-a2cj) did not do that. The bundle
named the answer and nobody read it.

The consequence is concrete: round 4 scored candidates against a POOLED
baseline of ">=10pt move in ~40% of 15-minute windows", averaged across what
this script shows to be a 77%-to-25% gradient. Every candidate scored against
that flat number was scored against the wrong comparator.

WHAT IT MEASURES, over the gexbot-hist 1-second orderflow archive:
  - per CT hour, over rolling 15-minute windows stepped one minute:
      n windows, P(absolute excursion >= 10 pts), median excursion
  - per CT hour, the count of giant flow prints (the round-2/3 "fix2000"
    spike definition, a fixed 2000 bar)

THE WINDOW MEASURE WAS RECONSTRUCTED, NOT INHERITED. The 2026-08-09 finding
recorded its table but not the code that produced it. Three candidate measures
were tried against it:

    measure                              P(>=10pt) by CT hour 08..14
    raw 1 Hz max-min                     94 83 62 47 38 36 39
    |last - first| (net, not excursion)  45 31 21 18 13 15 15
    minute-sampled closes, max-min       81 66 45 33 26 25 27
    the recorded finding                 77 62 42 32 26 25 27

Minute-sampled closes is the measure: exact at hours 12, 13 and 14, and within
four points everywhere else. What is NOT recovered is the window-inclusion rule
— this script keeps ~6% more windows than the original (3780/hour against
~3545), and per-minute coverage filters were swept without closing the gap
(they drop n far faster than they move P). The residual is entirely a window
count difference and changes no conclusion, but it is stated rather than tuned
away: matching a target by fitting an unrecorded filter would manufacture
agreement, not reproduce a result.

That gap is itself the lesson the traversal procedure exists to prevent. A
finding without its script is not reproducible, only re-derivable.

EXCURSION IS ABSOLUTE, either direction — max(spot) - min(spot) inside the
window. That is opportunity, not directional edge, and the distinction is the
whole reason this traversal was needed: the claim it corrects conflated
options-flow NOTIONAL with tradeable price DISPLACEMENT.

BOTH flow series are reported (`gex_of` and `cvr_of`) rather than one, because
SPIKE_DEFS applies the fixed 2000 bar to both and the original finding names a
single "giant flow print" count without saying which. Reporting one would be
asserting a definition this script cannot verify.

    .venv/bin/python scripts/measurement/clock_family_traversal.py --report
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "sweep", REPO / "scripts" / "orderflow_hist_sweep.py")
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)

CT = ZoneInfo("America/Chicago")
WINDOW_MIN = 15             # 15-minute window, in minute-closes
STEP_S = 60                 # stepped one minute
MOVE_PTS = 10.0             # the ">=10pt move" of the round-4 baseline
FIX_BAR = 2000.0            # SPIKE_DEFS["fix2000"] — a fixed bar, not a p95
CLOSE_CUTOFF_S = 120        # final 2 min of RTH excluded, as rounds 2-3 did
OUT_JSON = REPO / "data" / "measurement" / "clock_family_traversal.json"


def archive_days(start: str, end: str) -> list[str]:
    days = set()
    for root in (sw.HIST_LOCAL, sw.HIST_ARCHIVE):
        if not root.exists():
            continue
        for p in root.glob("*/orderflow_orderflow.json.gz"):
            days.add(p.parent.name)
    return sorted(d for d in days if start <= d <= end)


def day_stats(day: str) -> dict[int, dict] | None:
    """Per-hour excursions and flow-print counts for one archive day.

    Windows are built over MINUTE-SAMPLED closes (last spot in each minute),
    contiguous minutes only — see the reconstruction note in the module
    docstring. Raw 1 Hz max-min is carried alongside as a diagnostic, because
    the spread between the two is what identifies the measure.
    """
    pulls = sw.load_day(day)
    if len(pulls) < WINDOW_MIN // 2:
        return None
    end_epoch = pulls[-1]["epoch"] - CLOSE_CUTOFF_S
    by_hour: dict[int, dict] = {}

    minute_close: dict[int, float] = {}
    minute_ticks: dict[int, list[float]] = {}
    for p in pulls:
        if p["epoch"] > end_epoch or not p.get("spot"):
            continue
        m = p["epoch"] // 60
        minute_close[m] = p["spot"]
        minute_ticks.setdefault(m, []).append(p["spot"])

    ms = sorted(minute_close)
    for k in range(len(ms) - WINDOW_MIN + 1):
        block = ms[k:k + WINDOW_MIN]
        if block[-1] - block[0] != WINDOW_MIN - 1:      # contiguous only
            continue
        closes = [minute_close[m] for m in block]
        ticks = [v for m in block for v in minute_ticks[m]]
        hour = datetime.fromtimestamp(block[0] * 60,
                                      tz=timezone.utc).astimezone(CT).hour
        b = by_hour.setdefault(hour, {"exc": [], "tick_exc": [],
                                      "gex": 0, "cvr": 0})
        b["exc"].append(max(closes) - min(closes))
        b["tick_exc"].append(max(ticks) - min(ticks))

    for p in pulls:
        if p["epoch"] > end_epoch:
            break
        hour = datetime.fromtimestamp(p["epoch"],
                                      tz=timezone.utc).astimezone(CT).hour
        b = by_hour.setdefault(hour, {"exc": [], "tick_exc": [],
                                      "gex": 0, "cvr": 0})
        if abs(p.get("gex_of") or 0) > FIX_BAR:
            b["gex"] += 1
        if (p.get("cvr_of") or 0) > FIX_BAR:
            b["cvr"] += 1
    return by_hour


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2026-05-07")
    ap.add_argument("--end", default="2026-08-06")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    days = archive_days(args.start, args.end)
    print(f"archive days in {args.start}..{args.end}: {len(days)}", file=sys.stderr)

    agg: dict[int, dict] = {}
    used = 0
    for d in days:
        st = day_stats(d)
        if not st:
            continue
        used += 1
        for hour, b in st.items():
            a = agg.setdefault(hour, {"exc": [], "tick_exc": [], "gex": 0, "cvr": 0})
            a["exc"].extend(b["exc"])
            a["tick_exc"].extend(b["tick_exc"])
            a["gex"] += b["gex"]
            a["cvr"] += b["cvr"]

    rows = []
    for hour in sorted(agg):
        e = agg[hour]["exc"]
        if not e:
            continue
        rows.append({
            "hour_ct": hour,
            "n_windows": len(e),
            "p_move_10pt": round(sum(1 for x in e if x >= MOVE_PTS) / len(e), 4),
            "median_excursion_pts": round(statistics.median(e), 2),
            "median_tick_excursion_pts": round(
                statistics.median(agg[hour]["tick_exc"]), 2)
            if agg[hour]["tick_exc"] else None,
            "fix2000_gex_of": agg[hour]["gex"],
            "fix2000_cvr_of": agg[hour]["cvr"],
        })

    print(f"\ndays used: {used}/{len(days)}\n")
    print(f"{'CT hour':<9} {'P(>=10pt)':>10} {'median exc':>11} {'n windows':>10} "
          f"{'fix2000 gex':>12} {'fix2000 cvr':>12}")
    print("-" * 70)
    for r in rows:
        print(f"{r['hour_ct']:<9} {r['p_move_10pt']*100:>9.0f}% "
              f"{r['median_excursion_pts']:>11.2f} {r['n_windows']:>10} "
              f"{r['fix2000_gex_of']:>12} {r['fix2000_cvr_of']:>12}")

    tot_g = sum(r["fix2000_gex_of"] for r in rows)
    tot_c = sum(r["fix2000_cvr_of"] for r in rows)
    print(f"\ntotal fix2000 prints: gex_of {tot_g}  cvr_of {tot_c}")

    if args.report:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps({
            "bead": "st-1bv1",
            "window": [args.start, args.end],
            "days_used": used,
            "definitions": {
                "window": "rolling 15 minute-closes, contiguous, labelled by start hour",
                "excursion": "max-min over minute closes, absolute (reconstructed)",
                "move_bar_pts": MOVE_PTS,
                "fix2000": "fixed 2000 bar per SPIKE_DEFS, both flow series",
                "close_cutoff_s": CLOSE_CUTOFF_S,
            },
            "rows": rows,
        }, indent=2) + "\n")
        print(f"\nwrote {OUT_JSON.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
