#!/usr/bin/env python3
"""Orderflow edge tests, round 4 — scalp-metric re-score. [st-a2cj]

Target application (Steve 2026-08-08): singletons — single-leg SPX
options as a futures-scalp proxy. Median drift is the wrong metric.
Scores everything by what a 5-15 minute directional hold cares about:
favorable excursion, adverse excursion, and fast-move tail frequency.

1. Two-signal (frozen r3 p95x6 defs): MFE/MAE in the fade direction
   within 5/10/15 min; P(MFE>=5), P(MFE>=10), P(MAE>=5 before MFE>=5);
   near-wall cut; matched random control scored identically (control
   "fade direction" = against its own 30-min trend, same rule).
2. Regime baseline: P(a >=5 / >=10 pt move within 15 min, either
   direction) conditional on the 75s detector's netcvx state at the
   time (DUMP / RAMP / NEUTRAL) vs unconditional — when do fast moves
   happen at all?

Spot metrics only; the options layer (0DTE theta/gamma) is a later
refinement. Close-censoring: events within 15 min of the bell are
excluded from event scoring; regime sampling covers full RTH minus the
final 15 min.
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


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sw = _load("sweep", "orderflow_hist_sweep.py")
r2 = _load("r2", "orderflow_edge_tests.py")

RND = random.Random(20260808)
HOLD_S = 900                      # 15-min scalp window
CENSOR_S = 900                    # exclude events in final 15 min


def med(vals):
    return round(statistics.median(vals), 2) if vals else None


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "n/a"


def excursions(spots_arr, i0, direction, hold_s):
    """MFE/MAE (pts) in `direction` (+1 up / -1 down) over hold_s from
    index i0, plus whether MAE>=5 occurred before MFE>=5."""
    t0, s0 = spots_arr[i0]
    mfe = mae = 0.0
    mae5_first = None
    for t, s in spots_arr[i0:]:
        if t - t0 > hold_s:
            break
        d = (s - s0) * direction
        if d > mfe:
            mfe = d
            if mfe >= 5 and mae5_first is None:
                mae5_first = False
        if -d > mae:
            mae = -d
            if mae >= 5 and mae5_first is None:
                mae5_first = True
    return mfe, mae, bool(mae5_first)


def two_signal_events(day, pulls):
    """Frozen r3 p95x6 collection, returning (index, fade_dir, wall_d)."""
    spots = [(p["epoch"], p["spot"]) for p in pulls]
    end_epoch = pulls[-1]["epoch"] - CENSOR_S
    cvr = [p["cvr_of"] for p in pulls]
    gex = [p["gex_of"] for p in pulls]
    p95c = r2.rolling_bar(cvr)
    p95g = r2.rolling_bar(gex)
    epochs = [p["epoch"] for p in pulls]
    brakes, gexsp = [], []
    for i, p in enumerate(pulls):
        if p["epoch"] > end_epoch:
            break
        bc = 6.0 * p95c[i] if p95c[i] else None
        bg = 6.0 * p95g[i] if p95g[i] else None
        if bc and cvr[i] > bc:
            brakes.append(i)
        if bg and abs(gex[i]) > bg:
            gexsp.append(i)
    gset = {epochs[i]: gex[i] for i in gexsp}
    out, last_pair = [], -10**9
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
        trend = s0 - next((s for t, s in reversed(spots)
                           if t <= t0 - r2.TREND_LOOKBACK_S), s0)
        fade = -1 if trend > 0 else 1
        wall_d = min(abs(s0 - p0["m_call"]), abs(s0 - p0["m_put"]))
        out.append((pi, fade, wall_d))
    return out


def score(rows):
    if not rows:
        return dict(n=0)
    mfes = [r[0] for r in rows]
    maes = [r[1] for r in rows]
    return dict(
        n=len(rows), mfe_med=med(mfes), mae_med=med(maes),
        p_mfe5=pct(sum(m >= 5 for m in mfes), len(rows)),
        p_mfe10=pct(sum(m >= 10 for m in mfes), len(rows)),
        p_stopped_first=pct(sum(r[2] for r in rows), len(rows)),
    )


def main() -> int:
    days_data = {}
    for day in sw.hist_days():
        pulls = sw.load_day(day)
        if len(pulls) >= 1000:
            days_data[day] = pulls
    print(f"{len(days_data)} days", flush=True)

    ev_all, ev_wall5, ctl = [], [], []
    regime = {"DUMP": [0, 0, 0], "RAMP": [0, 0, 0], "NEUTRAL": [0, 0, 0]}
    for day, pulls in days_data.items():
        spots_arr = [(p["epoch"], p["spot"]) for p in pulls]
        for pi, fade, wall_d in two_signal_events(day, pulls):
            row = excursions(spots_arr, pi, fade, HOLD_S)
            ev_all.append(row)
            if wall_d <= 5:
                ev_wall5.append(row)
        end_epoch = pulls[-1]["epoch"] - CENSOR_S
        for _ in range(6):
            t0 = RND.randint(pulls[0]["epoch"] + r2.TREND_LOOKBACK_S, end_epoch)
            i0 = next(j for j, (t, _) in enumerate(spots_arr) if t >= t0)
            s0 = spots_arr[i0][1]
            trend = s0 - next((s for t, s in reversed(spots_arr)
                               if t <= t0 - r2.TREND_LOOKBACK_S), s0)
            ctl.append(excursions(spots_arr, i0, -1 if trend > 0 else 1,
                                  HOLD_S))
        # regime fast-move sampling at 75s cadence
        p75 = sw.downsample(pulls)
        det = sw._mon.Detector(sw.BASE_CFG)
        e_to_i = {p["epoch"]: i for i, p in enumerate(pulls)}
        for p in p75:
            det.feed(p)
            if p["epoch"] > end_epoch:
                continue
            i0 = e_to_i[p["epoch"]]
            t0, s0 = spots_arr[i0]
            hi = lo = s0
            for t, s in spots_arr[i0:]:
                if t - t0 > HOLD_S:
                    break
                hi, lo = max(hi, s), min(lo, s)
            move = max(hi - s0, s0 - lo)
            cell = regime[det.netcvx_state]
            cell[0] += 1
            cell[1] += move >= 5
            cell[2] += move >= 10
        print(f"  {day} done", flush=True)

    out = {"run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "event_all": score(ev_all), "event_wall5": score(ev_wall5),
           "control": score(ctl),
           "regime": {k: {"samples": v[0], "p_move5": pct(v[1], v[0]),
                          "p_move10": pct(v[2], v[0])}
                      for k, v in regime.items()}}
    (REPO / "data/derived/acuity-sweep/edge-tests-r4-raw.json").write_text(
        json.dumps(out, indent=1))

    run_day = datetime.now(timezone.utc).date().isoformat()
    L = [f"# Orderflow edge tests, round 4 — scalp metrics — {run_day} [st-a2cj]\n",
         f"{len(days_data)} hist days at 1s. Target: single-leg SPX "
         f"scalp-proxy, 15-min hold. MFE/MAE in the fade direction; "
         f"control scored by the identical rule. Events in the final "
         f"15 min excluded.\n",
         "## 1. Two-signal under scalp metrics (15-min hold)\n",
         "| sample | n | MFE med | MAE med | P(MFE>=5) | P(MFE>=10) | P(stopped first: MAE>=5 before MFE>=5) |",
         "|---|---|---|---|---|---|---|"]
    for label, s in (("all events", out["event_all"]),
                     ("wall <= 5", out["event_wall5"]),
                     ("**random control**", out["control"])):
        L.append(f"| {label} | {s['n']} | {s.get('mfe_med')} | {s.get('mae_med')} "
                 f"| {s.get('p_mfe5')} | {s.get('p_mfe10')} "
                 f"| {s.get('p_stopped_first')} |")
    L += ["", "## 2. When do fast moves happen at all? (netcvx regime, "
          "75s sampling, either direction)\n",
          "| regime | samples | P(>=5 pt move in 15 min) | P(>=10 pt) |",
          "|---|---|---|---|"]
    for k, v in out["regime"].items():
        L.append(f"| {k} | {v['samples']} | {v['p_move5']} | {v['p_move10']} |")
    L += ["", "Raw: `data/derived/acuity-sweep/edge-tests-r4-raw.json`. "
          "Spot metrics only; options layer is a future refinement. "
          "Measurement only [st-a2cj]."]
    report = REPO / "docs" / "measurement" / f"orderflow-edge-tests-r4-{run_day}.md"
    report.write_text("\n".join(L) + "\n")
    print(f"report -> {report}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
