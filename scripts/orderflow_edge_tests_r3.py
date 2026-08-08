#!/usr/bin/env python3
"""Orderflow edge tests, round 3 — Freddy-faithful. [st-gkbo]

Tests the two-signal the way Freddy teaches it (level first, flow as
the confirm) plus his untested post-entry momentum rule. 1s hist
archive, matched controls, final 2 minutes of RTH excluded.

1. Level-conditioned two-signal: round-2 strong-print events bucketed
   by |spot - nearest 0DTE wall| (zero_mcall / zero_mput) at event
   time. Hypothesis: proximity concentrates the aligned-reversal effect.
2. Post-entry momentum rule (Part 3, 24:00-25:30): after a two-signal,
   a convexity DOWN-spike (options sold = liquidity provided = fuel)
   within 10 minutes should mark follow-through vs events without one.

Outputs:
  docs/measurement/orderflow-edge-tests-r3-<run date>.md
  data/derived/acuity-sweep/edge-tests-r3-raw.json
"""

from __future__ import annotations

import importlib.util
import json
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_s1 = importlib.util.spec_from_file_location(
    "sweep", REPO / "scripts" / "orderflow_hist_sweep.py")
sw = importlib.util.module_from_spec(_s1)
_s1.loader.exec_module(sw)
_s2 = importlib.util.spec_from_file_location(
    "r2", REPO / "scripts" / "orderflow_edge_tests.py")
r2 = importlib.util.module_from_spec(_s2)
_s2.loader.exec_module(r2)

RND = random.Random(20260808)
FUEL_WINDOW_S = 600
SPIKE_DEFS = {"p95x6": ("p95", 6.0), "fix2000": ("fix", 2000.0)}


def med(vals):
    return round(statistics.median(vals), 2) if vals else None


def frac_pos(vals):
    return (f"{100 * sum(1 for v in vals if v > 0) / len(vals):.0f}%"
            if vals else "n/a")


def collect_events(days_data: dict) -> tuple[dict, list]:
    """Two-signal events per definition, with wall distance and
    post-entry fuel-spike flag; plus the matched random control."""
    per_def = {d: [] for d in SPIKE_DEFS}
    control = []
    for day, pulls in days_data.items():
        spots = [(p["epoch"], p["spot"]) for p in pulls]
        end_epoch = pulls[-1]["epoch"] - r2.CLOSE_CUTOFF
        cvr = [p["cvr_of"] for p in pulls]
        gex = [p["gex_of"] for p in pulls]
        p95c = r2.rolling_bar(cvr)
        p95g = r2.rolling_bar(gex)
        epochs = [p["epoch"] for p in pulls]
        for name, (kind, k) in SPIKE_DEFS.items():
            brakes, gexsp, downspikes = [], [], []
            for i, p in enumerate(pulls):
                if p["epoch"] > end_epoch:
                    break
                bc = k * p95c[i] if kind == "p95" and p95c[i] else (
                    k if kind == "fix" else None)
                bg = k * p95g[i] if kind == "p95" and p95g[i] else (
                    k if kind == "fix" else None)
                if bc and cvr[i] > bc:
                    brakes.append(i)
                if bc and cvr[i] < -bc:
                    downspikes.append(p["epoch"])
                if bg and abs(gex[i]) > bg:
                    gexsp.append(i)
            gset = {epochs[i]: gex[i] for i in gexsp}
            last_pair = -10**9
            for bi in brakes:
                t_b = epochs[bi]
                near = [(abs(t_b - tg), tg, gv) for tg, gv in gset.items()
                        if abs(t_b - tg) <= r2.PAIR_WINDOW_S]
                if not near:
                    continue
                _, tg, gv = min(near)
                t0 = max(t_b, tg)
                if t0 - last_pair < r2.PAIR_COOLDOWN_S:
                    continue
                last_pair = t0
                pi = next(j for j, e in enumerate(epochs) if e >= t0)
                p0 = pulls[pi]
                s0 = p0["spot"]
                trend = s0 - next(
                    (s for t, s in reversed(spots)
                     if t <= t0 - r2.TREND_LOOKBACK_S), s0)
                wall_d = min(abs(s0 - p0["m_call"]), abs(s0 - p0["m_put"]))
                fuel = any(t0 < t <= t0 + FUEL_WINDOW_S for t in downspikes)
                row = {"day": day, "trend": round(trend, 2),
                       "gex_side": "call" if gv > 0 else "put",
                       "wall_d": round(wall_d, 2), "fuel": fuel}
                for m in (15, 30):
                    f = r2.fwd_delta(spots, t0, s0, m)
                    row[f"al_{m}"] = (round(-f, 2) if trend > 0 else
                                      round(f, 2)) if f is not None else None
                per_def[name].append(row)
        for _ in range(6):
            t0 = RND.randint(pulls[0]["epoch"] + r2.TREND_LOOKBACK_S,
                             end_epoch - 1800)
            s0 = next(s for t, s in spots if t >= t0)
            trend = s0 - next(
                (s for t, s in reversed(spots)
                 if t <= t0 - r2.TREND_LOOKBACK_S), s0)
            row = {}
            for m in (15, 30):
                f = r2.fwd_delta(spots, t0, s0, m)
                row[f"al_{m}"] = (round(-f, 2) if trend > 0 else
                                  round(f, 2)) if f is not None else None
            control.append(row)
    return per_def, control


def main() -> int:
    days_data = {}
    for day in sw.hist_days():
        pulls = sw.load_day(day)
        if len(pulls) >= 1000:
            days_data[day] = pulls
    print(f"{len(days_data)} days loaded", flush=True)
    per_def, control = collect_events(days_data)
    print("events collected", flush=True)

    out_dir = REPO / "data" / "derived" / "acuity-sweep"
    (out_dir / "edge-tests-r3-raw.json").write_text(json.dumps(
        {"run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "defs": per_def, "control": control}, indent=1))

    run_day = datetime.now(timezone.utc).date().isoformat()
    L = [f"# Orderflow edge tests, round 3 — Freddy-faithful — {run_day} [st-gkbo]\n",
         f"{len(days_data)} hist days at 1s. Wall = nearest of 0DTE "
         f"zero_mcall/zero_mput at event time. Aligned delta = "
         f"-sign(30-min trend) x forward move (positive = reversal "
         f"happened). Control uses the same alignment rule.\n"]

    L.append("## 1. Level-conditioned two-signal\n")
    L.append("Events within 30 min of the close have no +30m outcome — "
             "n15/n30 columns give the actually-measurable counts; judge "
             "each cell by its own n, not the event count.\n")
    L.append("| definition | band | events | n15 | n30/days | al +15m med | %pos | al +30m med | %pos |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for name, rows in per_def.items():
        bands = [("all", lambda r: True),
                 ("wall <= 3", lambda r: r["wall_d"] <= 3),
                 ("wall <= 5", lambda r: r["wall_d"] <= 5),
                 ("wall <= 10", lambda r: r["wall_d"] <= 10),
                 ("wall > 10", lambda r: r["wall_d"] > 10)]
        for label, pred in bands:
            sel = [r for r in rows if pred(r)]
            a15 = [r["al_15"] for r in sel if r["al_15"] is not None]
            a30 = [r["al_30"] for r in sel if r["al_30"] is not None]
            d30 = len({r["day"] for r in sel if r["al_30"] is not None})
            L.append(f"| {name} | {label} | {len(sel)} | {len(a15)} | "
                     f"{len(a30)}/{d30}d | {med(a15)} "
                     f"| {frac_pos(a15)} | {med(a30)} | {frac_pos(a30)} |")
    c15 = [r["al_15"] for r in control if r["al_15"] is not None]
    c30 = [r["al_30"] for r in control if r["al_30"] is not None]
    L.append(f"| — | **random control** | {len(control)} | {len(c15)} | "
             f"{len(c30)}/{len(days_data)}d "
             f"| {med(c15)} | {frac_pos(c15)} | {med(c30)} | {frac_pos(c30)} |")
    L.append("")

    L.append("## 2. Post-entry momentum rule (fuel = convexity DOWN-spike "
             "within 10 min of entry)\n")
    L.append("| definition | group | n | al +30m med | %pos |")
    L.append("|---|---|---|---|---|")
    for name, rows in per_def.items():
        for label, pred in (("fuel present", lambda r: r["fuel"]),
                            ("no fuel", lambda r: not r["fuel"])):
            sel = [r for r in rows if pred(r)]
            a30 = [r["al_30"] for r in sel if r["al_30"] is not None]
            L.append(f"| {name} | {label} | {len(a30)} | {med(a30)} "
                     f"| {frac_pos(a30)} |")
    L.append("")
    L.append("Raw: `data/derived/acuity-sweep/edge-tests-r3-raw.json`. "
             "Measurement only [st-gkbo].")
    report = REPO / "docs" / "measurement" / f"orderflow-edge-tests-r3-{run_day}.md"
    report.write_text("\n".join(L) + "\n")
    print(f"report -> {report}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
