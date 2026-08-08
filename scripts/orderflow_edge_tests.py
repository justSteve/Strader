#!/usr/bin/env python3
"""Orderflow edge tests, round 2. [st-mvvf]

Three studies over the 63-day 1-second hist archive, each against a
matched control. Measurement only. Close-mechanics window (final 2 min)
excluded from event samples.

1. TWO_SIGNAL at 1s — spikes defined on the full print population
   (rolling p95 bar recomputed every 60s over a trailing hour, three
   definitions), brake+gex pairing within 120s, 300s cooldown.
   Outcome: REVERSAL-ALIGNED forward spot delta — the doctrine says the
   pair marks reversal, so the aligned delta is -sign(trend)*fwd.
   Control: random timestamps, SAME alignment rule (this bakes generic
   mean-reversion into the baseline, which a naive control would miss).

2. Conditioned V-turn — VTURN events (75s detector, base config)
   bucketed by dump depth and time of day; time-to-low / rebound /
   aligned forward delta vs random control with the same metrics.

3. Vanna thresholds — the canonical claim (orderflow-intended-read.md
   §2.5): net -vanna matters beyond $800MM (last hour) / $1000MM (last
   two hours); extreme days feature extreme reversals. Days partitioned
   by peak |zvanna|; per-day last-hour drift and backtrack measured.
   Sign semantics of "net -vanna" vs the zvanna field are ambiguous in
   the docs, so the directional cut is reported both ways and flagged.

Outputs:
  docs/measurement/orderflow-edge-tests-<run date>.md
  data/derived/acuity-sweep/edge-tests-raw.json
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
_spec = importlib.util.spec_from_file_location(
    "sweep", REPO / "scripts" / "orderflow_hist_sweep.py")
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)

RND = random.Random(20260808)
CLOSE_CUTOFF = 120        # exclude final 2 min of RTH from event samples
PAIR_WINDOW_S = 120
PAIR_COOLDOWN_S = 300
TREND_LOOKBACK_S = 1800
SPIKE_DEFS = {"p95x3": ("p95", 3.0), "p95x6": ("p95", 6.0),
              "fix2000": ("fix", 2000.0)}


# ---------------------------------------------------------------- shared

def med(vals):
    return round(statistics.median(vals), 2) if vals else None


def frac_pos(vals):
    return (f"{100 * sum(1 for v in vals if v > 0) / len(vals):.0f}%"
            if vals else "n/a")


def fwd_delta(spots, t0, s0, mins):
    w = [s for t, s in spots if abs(t - (t0 + mins * 60)) <= 40]
    return (w[0] - s0) if w else None


def rolling_bar(series: list[float], every: int = 60,
                window: int = 3600, min_n: int = 600) -> list[float | None]:
    """Per-index p95 of |trailing window|, recomputed every `every` samples."""
    bars: list[float | None] = [None] * len(series)
    cur = None
    for i in range(len(series)):
        if i % every == 0 and i >= min_n:
            lo = max(0, i - window)
            chunk = sorted(abs(v) for v in series[lo:i])
            cur = chunk[int(0.95 * (len(chunk) - 1))]
        bars[i] = cur
    return bars


# ---------------------------------------------------------------- study 1

def study_two_signal(days_data: dict) -> dict:
    per_def: dict[str, dict] = {d: {"events": []} for d in SPIKE_DEFS}
    control_rows = []
    for day, pulls in days_data.items():
        spots = [(p["epoch"], p["spot"]) for p in pulls]
        end_epoch = pulls[-1]["epoch"] - CLOSE_CUTOFF
        cvr = [p["cvr_of"] for p in pulls]
        gex = [p["gex_of"] for p in pulls]
        p95c = rolling_bar(cvr)
        p95g = rolling_bar(gex)
        for name, (kind, k) in SPIKE_DEFS.items():
            brakes, gexsp = [], []
            for i, p in enumerate(pulls):
                if p["epoch"] > end_epoch:
                    break
                bc = k * p95c[i] if kind == "p95" and p95c[i] else (
                    k if kind == "fix" else None)
                bg = k * p95g[i] if kind == "p95" and p95g[i] else (
                    k if kind == "fix" else None)
                if bc and cvr[i] > bc:                    # brake: UP only
                    brakes.append(i)
                if bg and abs(gex[i]) > bg:
                    gexsp.append(i)
            gset = {pulls[i]["epoch"]: gex[i] for i in gexsp}
            last_pair = -10**9
            for bi in brakes:
                t_b = pulls[bi]["epoch"]
                near = [(abs(t_b - tg), tg, gv) for tg, gv in gset.items()
                        if abs(t_b - tg) <= PAIR_WINDOW_S]
                if not near:
                    continue
                _, tg, gv = min(near)
                t0 = max(t_b, tg)
                if t0 - last_pair < PAIR_COOLDOWN_S:
                    continue
                last_pair = t0
                s0 = next(s for t, s in spots if t >= t0)
                trend = s0 - next(
                    (s for t, s in reversed(spots) if t <= t0 - TREND_LOOKBACK_S),
                    s0)
                row = {"day": day, "gex_side": "call" if gv > 0 else "put",
                       "trend": round(trend, 2)}
                for m in (5, 15, 30):
                    f = fwd_delta(spots, t0, s0, m)
                    row[f"fwd_{m}"] = round(f, 2) if f is not None else None
                    row[f"al_{m}"] = (round(-f, 2) if trend > 0 else
                                      round(f, 2)) if f is not None else None
                per_def[name]["events"].append(row)
        # matched control: 6 random times/day, same alignment rule
        for _ in range(6):
            t0 = RND.randint(pulls[0]["epoch"] + TREND_LOOKBACK_S,
                             end_epoch - 1800)
            s0 = next(s for t, s in spots if t >= t0)
            trend = s0 - next(
                (s for t, s in reversed(spots) if t <= t0 - TREND_LOOKBACK_S), s0)
            row = {}
            for m in (5, 15, 30):
                f = fwd_delta(spots, t0, s0, m)
                row[f"al_{m}"] = (round(-f, 2) if trend > 0 else
                                  round(f, 2)) if f is not None else None
            control_rows.append(row)
    return {"defs": per_def, "control": control_rows}


# ---------------------------------------------------------------- study 2

def study_vturn(days_data: dict) -> dict:
    rows, control = [], []
    for day, pulls in days_data.items():
        spots = [(p["epoch"], p["spot"]) for p in pulls]
        p75 = sw.downsample(pulls)
        evs = sw.run_detector(p75, sw.BASE_CFG)
        open_epoch = pulls[0]["epoch"]
        last_dump = None
        for ev in evs:
            if ev["type"] == "NETCVX_DUMP_START":
                last_dump = ev
            if ev["type"] != "NETCVX_VTURN":
                continue
            depth = (last_dump["from_rolling_max"] - ev["off_min"]
                     if last_dump else None)
            t0, s0 = ev["epoch"], ev["spot"]
            w = [(t, s) for t, s in spots if t0 <= t <= t0 + 1800]
            if len(w) < 10:
                continue
            t_min, s_min = min(w, key=lambda x: x[1])
            after = [s for t, s in spots if t_min <= t <= t_min + 1800]
            rows.append({
                "day": day, "depth": round(depth, 0) if depth else None,
                "mins_into_day": (t0 - open_epoch) // 60,
                "lead_s": t_min - t0,
                "rebound": round((max(after) if after else s_min) - s_min, 2),
                "fwd_15": fwd_delta(spots, t0, s0, 15),
                "fwd_30": fwd_delta(spots, t0, s0, 30),
            })
        for _ in range(4):
            t0 = RND.randint(pulls[0]["epoch"], pulls[-1]["epoch"] - 1800)
            w = [(t, s) for t, s in spots if t0 <= t <= t0 + 1800]
            if len(w) < 10:
                continue
            s0 = w[0][1]
            t_min, s_min = min(w, key=lambda x: x[1])
            after = [s for t, s in spots if t_min <= t <= t_min + 1800]
            control.append({
                "lead_s": t_min - t0,
                "rebound": round((max(after) if after else s_min) - s_min, 2),
                "fwd_15": fwd_delta(spots, t0, s0, 15),
                "fwd_30": fwd_delta(spots, t0, s0, 30),
            })
    return {"vturns": rows, "control": control}


# ---------------------------------------------------------------- study 3

def load_vanna_day(day: str):
    for root in (sw.HIST_LOCAL, sw.HIST_ARCHIVE):
        p = root / day / "orderflow_orderflow.json.gz"
        if p.exists():
            recs = json.loads(p.read_text())
            break
    else:
        return None
    out = []
    for r in recs:
        try:
            out.append((int(r["timestamp"]), float(r["spot"]),
                        float(r["zvanna"])))
        except (KeyError, TypeError, ValueError):
            continue
    out.sort()
    return out


def study_vanna(days: list[str]) -> list[dict]:
    rows = []
    for day in days:
        data = load_vanna_day(day)
        if not data or len(data) < 1000:
            continue
        end = data[-1][0]
        last2h = [d for d in data if d[0] >= end - 7200]
        lasth = [d for d in data if d[0] >= end - 3600]
        if len(lasth) < 100:
            continue
        peak2 = max(last2h, key=lambda d: abs(d[2]))
        peak1 = max(lasth, key=lambda d: abs(d[2]))
        spots_h = [s for _, s, _ in lasth]
        drift = spots_h[-1] - spots_h[0]
        backtrack = (max(spots_h) - min(spots_h)) - abs(drift)
        rows.append({
            "day": day,
            "peak_absvanna_2h": round(abs(peak2[2]), 0),
            "peak_absvanna_1h": round(abs(peak1[2]), 0),
            "vanna_sign_1h": 1 if peak1[2] > 0 else -1,
            "lasthour_drift": round(drift, 2),
            "lasthour_backtrack": round(backtrack, 2),
        })
    return rows


# ---------------------------------------------------------------- report

def main() -> int:
    days = sw.hist_days()
    days_data = {}
    for day in days:
        pulls = sw.load_day(day)
        if len(pulls) >= 1000:
            days_data[day] = pulls
    print(f"{len(days_data)} days loaded", flush=True)

    s1 = study_two_signal(days_data)
    print("study 1 done", flush=True)
    s2 = study_vturn(days_data)
    print("study 2 done", flush=True)
    s3 = study_vanna(list(days_data))
    print("study 3 done", flush=True)

    out_dir = REPO / "data" / "derived" / "acuity-sweep"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "edge-tests-raw.json").write_text(json.dumps(
        {"run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "two_signal": s1, "vturn": s2, "vanna": s3}, indent=1))

    run_day = datetime.now(timezone.utc).date().isoformat()
    L = [f"# Orderflow edge tests, round 2 — {run_day} [st-mvvf]\n",
         f"{len(days_data)} hist days at 1s. Controls are matched and use "
         f"the same alignment rules as the tested events. Final 2 minutes "
         f"of RTH excluded from event samples.\n"]

    L.append("## 1. Two-signal at 1-second resolution\n")
    L.append("Aligned forward delta = reversal-aligned spot move "
             "(-sign(30-min trend) x forward delta); positive = the "
             "doctrine's predicted reversal happened.\n")
    ctl = s1["control"]
    L.append("| definition | n | aligned +15m med | %pos | aligned +30m med | %pos |")
    L.append("|---|---|---|---|---|---|")
    for name, d in s1["defs"].items():
        evs = d["events"]
        for label, rows in ((name, evs),):
            a15 = [r["al_15"] for r in rows if r.get("al_15") is not None]
            a30 = [r["al_30"] for r in rows if r.get("al_30") is not None]
            L.append(f"| {label} | {len(rows)} | {med(a15)} | {frac_pos(a15)} "
                     f"| {med(a30)} | {frac_pos(a30)} |")
    c15 = [r["al_15"] for r in ctl if r.get("al_15") is not None]
    c30 = [r["al_30"] for r in ctl if r.get("al_30") is not None]
    L.append(f"| **random control** | {len(ctl)} | {med(c15)} | {frac_pos(c15)} "
             f"| {med(c30)} | {frac_pos(c30)} |")
    L.append("")
    # put-side-in-downtrend cut (the canonical reversal case), largest def
    for name in ("p95x6",):
        rows = [r for r in s1["defs"][name]["events"]
                if r["gex_side"] == "put" and r["trend"] < -2]
        a15 = [r["al_15"] for r in rows if r.get("al_15") is not None]
        a30 = [r["al_30"] for r in rows if r.get("al_30") is not None]
        L.append(f"Canonical cut ({name}, put-side, trend < -2 pts): n={len(rows)}, "
                 f"aligned +15m med {med(a15)} ({frac_pos(a15)} pos), "
                 f"+30m med {med(a30)} ({frac_pos(a30)} pos).\n")

    L.append("## 2. Conditioned V-turn\n")
    vt, vc = s2["vturns"], s2["control"]
    L.append("| condition | n | med rebound | med fwd_30 | %fwd_30 pos |")
    L.append("|---|---|---|---|---|")

    def vrow(label, rows):
        rb = [r["rebound"] for r in rows if r["rebound"] is not None]
        f30 = [r["fwd_30"] for r in rows if r["fwd_30"] is not None]
        L.append(f"| {label} | {len(rows)} | {med(rb)} | {med(f30)} "
                 f"| {frac_pos(f30)} |")
    vrow("all VTURN", vt)
    vrow("depth >= 3000", [r for r in vt if (r["depth"] or 0) >= 3000])
    vrow("depth >= 5000", [r for r in vt if (r["depth"] or 0) >= 5000])
    vrow("first 90 min", [r for r in vt if r["mins_into_day"] <= 90])
    vrow("after first 90 min", [r for r in vt if r["mins_into_day"] > 90])
    vrow("**random control**", vc)
    L.append("")

    L.append("## 3. Vanna thresholds (canonical: -800/-1000 $MM)\n")
    L.append("Vendor self-caveat applies: this layer is flagged 'still "
             "learning best practices'. Sign mapping of doc 'net -vanna' to "
             "the zvanna field is ambiguous; magnitude cuts are primary.\n")
    L.append("| partition | n days | med last-hour |drift| | med backtrack |")
    L.append("|---|---|---|---|")

    def vanrow(label, rows):
        dr = [abs(r["lasthour_drift"]) for r in rows]
        bt = [r["lasthour_backtrack"] for r in rows]
        L.append(f"| {label} | {len(rows)} | {med(dr)} | {med(bt)} |")
    vanrow("peak |zvanna| last-1h >= 800",
           [r for r in s3 if r["peak_absvanna_1h"] >= 800])
    vanrow("peak |zvanna| last-1h < 800",
           [r for r in s3 if r["peak_absvanna_1h"] < 800])
    vanrow("peak |zvanna| last-2h >= 1000",
           [r for r in s3 if r["peak_absvanna_2h"] >= 1000])
    vanrow("peak |zvanna| last-2h < 1000",
           [r for r in s3 if r["peak_absvanna_2h"] < 1000])
    sgn = [r["vanna_sign_1h"] * r["lasthour_drift"] for r in s3]
    L.append(f"\nDirectional (exploratory, sign-ambiguous): "
             f"sign(zvanna)*drift med {med(sgn)} pts, {frac_pos(sgn)} positive, "
             f"n={len(sgn)}; flip the sign convention to read the opposite claim.\n")

    L.append("Raw: `data/derived/acuity-sweep/edge-tests-raw.json`. "
             "Measurement only [st-mvvf].")
    report = REPO / "docs" / "measurement" / f"orderflow-edge-tests-{run_day}.md"
    report.write_text("\n".join(L) + "\n")
    print(f"report -> {report}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
