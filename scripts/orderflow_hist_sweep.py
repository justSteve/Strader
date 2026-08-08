#!/usr/bin/env python3
"""Orderflow acuity sweep — hist-replay measurement lane. [st-yirc]

Steps through the gexbot-hist 1-second orderflow archive (62+ days,
plain JSON despite the .json.gz names — st-kr4a) and measures the
Orderflow Doctrine Monitor's acuity. Measurement only: no trade logic,
no alerting, no config changes.

The detector (imported unmodified from orderflow_monitor.py) runs at
the LIVE poll cadence (hist series downsampled to 75s), because that is
the instrument whose acuity we are grading. The raw 1-second arrays
serve as ground truth for what the poll cannot see:

  A. coverage    — what fraction of 1s spike prints the 75s poll observes
  B. baseline    — events/day under the current config, chatter check
  C. sweep       — threshold grid, events/day per family per combo
  D. lead-lag    — VTURN/TWO_SIGNAL timing vs the 1s spot path
  E. close       — final-2-minute flush signature distribution

Outputs:
  docs/measurement/orderflow-acuity-sweep-<run date>.md   (the report)
  data/derived/acuity-sweep/raw.json                      (all numbers)

Usage:
  .venv/bin/python3 scripts/orderflow_hist_sweep.py [--days N] [--grid]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HIST_LOCAL = REPO / "data" / "corpus" / "gexbot-hist"
HIST_ARCHIVE = Path("/mnt/z/Harvest/gexbot-hist")
POLL_SECONDS = 75          # measured effective live cadence (60s + pull time)
RTH = (13, 30, 20, 0)      # UTC open/close

_spec = importlib.util.spec_from_file_location(
    "orderflow_monitor", REPO / "scripts" / "orderflow_monitor.py")
_mon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mon)

CFG_PATH = REPO / "scripts" / "orderflow_monitor.config.json"
BASE_CFG = json.loads(CFG_PATH.read_text())

SPIKE_FAMILY = ("CVR_SPIKE_UP", "CVR_SPIKE_DOWN",
                "GEX_SPIKE_CALL", "GEX_SPIKE_PUT")
NETCVX_FAMILY = ("NETCVX_DUMP_START", "NETCVX_DUMP_END", "NETCVX_VTURN",
                 "NETCVX_RAMP_START", "NETCVX_RAMP_END")


# ---------------------------------------------------------------- loading

def hist_days() -> list[str]:
    days = set()
    for root in (HIST_LOCAL, HIST_ARCHIVE):
        if root.exists():
            for p in root.glob("*/orderflow_orderflow.json.gz"):
                days.add(p.parent.name)
    return sorted(days)


def load_day(day: str) -> list[dict]:
    """1s records -> monitor pull dicts, RTH-clipped, time-ordered."""
    for root in (HIST_LOCAL, HIST_ARCHIVE):
        p = root / day / "orderflow_orderflow.json.gz"
        if p.exists():
            recs = json.loads(p.read_text())
            break
    else:
        return []
    o_h, o_m, c_h, c_m = RTH
    lo = o_h * 3600 + o_m * 60
    hi = c_h * 3600 + c_m * 60
    pulls = []
    for r in recs:
        try:
            ts = int(r["timestamp"])
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            sec = dt.hour * 3600 + dt.minute * 60 + dt.second
            if not (lo <= sec < hi):
                continue
            pulls.append({
                "ts": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "epoch": ts,
                "spot": float(r["spot"]),
                "cvr_of": float(r["cvroflow"]),
                "gex_of": float(r["gexoflow"]),
                "netcvx": float(r["zcvr"]),
                "m_call": float(r["zero_mcall"]),
                "m_put": float(r["zero_mput"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    pulls.sort(key=lambda p: p["epoch"])
    # dedupe identical seconds (rare vendor repeats)
    out, last = [], None
    for p in pulls:
        if p["epoch"] != last:
            out.append(p)
            last = p["epoch"]
    return out


def downsample(pulls: list[dict], period: int = POLL_SECONDS) -> list[dict]:
    out, next_t = [], None
    for p in pulls:
        if next_t is None or p["epoch"] >= next_t:
            out.append(p)
            next_t = p["epoch"] + period
    return out


def run_detector(pulls: list[dict], cfg: dict) -> list[dict]:
    det = _mon.Detector(cfg)
    events = []
    for p in pulls:
        for ev in det.feed(p):
            ev["epoch"] = p["epoch"]
            events.append(ev)
    return events


# ---------------------------------------------------------------- analyses

def coverage(pulls_1s: list[dict], sampled_epochs: set[int]) -> dict:
    """Of the 1s prints exceeding each magnitude, how many landed on a
    sampled instant?  (prints are instantaneous — a 75s poll sees only
    the second it happens to hit)"""
    out = {}
    for field, label in (("cvr_of", "cvr"), ("gex_of", "gex")):
        for thr in (300, 500, 1000):
            total = obs = 0
            for p in pulls_1s:
                if abs(p[field]) >= thr:
                    total += 1
                    if p["epoch"] in sampled_epochs:
                        obs += 1
            out[f"{label}_ge{thr}"] = {"prints_1s": total, "observed": obs}
    return out


def chatter(events: list[dict]) -> int:
    """END followed by a START within 3 pulls (the re-arm defect)."""
    n = 0
    idx = [(i, e) for i, e in enumerate(events) if e["type"] in NETCVX_FAMILY]
    for (_, a), (_, b) in zip(idx, idx[1:]):
        if a["type"].endswith("_END") and b["type"].endswith("_START") \
                and 0 <= b["epoch"] - a["epoch"] <= 3 * POLL_SECONDS:
            n += 1
    return n


def leadlag_vturn(events: list[dict], pulls_1s: list[dict]) -> list[dict]:
    """For each VTURN: on the 1s spot path, where was the spot minimum in
    the following 30 minutes, and what came after it?"""
    spots = [(p["epoch"], p["spot"]) for p in pulls_1s]
    rows = []
    for ev in events:
        if ev["type"] != "NETCVX_VTURN":
            continue
        t0 = ev["epoch"]
        w = [(t, s) for t, s in spots if t0 <= t <= t0 + 1800]
        if len(w) < 10:
            continue
        t_min, s_min = min(w, key=lambda x: x[1])
        after = [(t, s) for t, s in spots if t_min <= t <= t_min + 1800]
        s_reb = max(s for _, s in after) if after else s_min
        rows.append({
            "ts": ev["ts"], "spot_at_vturn": ev["spot"],
            "min_lead_s": t_min - t0,
            "drawdown_pts": round(ev["spot"] - s_min, 2),
            "rebound_pts": round(s_reb - s_min, 2),
        })
    return rows


def leadlag_two_signal(events: list[dict], pulls_1s: list[dict]) -> list[dict]:
    spots = [(p["epoch"], p["spot"]) for p in pulls_1s]
    rows = []
    for ev in events:
        if ev["type"] != "TWO_SIGNAL":
            continue
        t0, s0 = ev["epoch"], ev["spot"]
        row = {"ts": ev["ts"], "gex_side": ev["gex_side"],
               "trend_pts": ev["trend_pts"]}
        for mins in (5, 15, 30):
            w = [s for t, s in spots if abs(t - (t0 + mins * 60)) <= 40]
            row[f"fwd_{mins}m_pts"] = round(w[0] - s0, 2) if w else None
        rows.append(row)
    return rows


def close_signature(pulls_1s: list[dict]) -> dict | None:
    if not pulls_1s:
        return None
    end = pulls_1s[-1]["epoch"]
    tail = [p for p in pulls_1s if p["epoch"] >= end - 120]
    if len(tail) < 10:
        return None
    return {
        "max_abs_cvr": round(max(abs(p["cvr_of"]) for p in tail), 1),
        "max_abs_gex": round(max(abs(p["gex_of"]) for p in tail), 1),
        "zcvr_delta": round(tail[-1]["netcvx"] - tail[0]["netcvx"], 1),
    }


def sweep_grid(day_pulls_75: dict[str, list[dict]]) -> list[dict]:
    combos = []
    for floor in (100.0, 150.0, 250.0):
        for mult in (1.3, 1.6, 2.0):
            for drop in (1000.0, 1500.0, 2500.0):
                cfg = json.loads(json.dumps(BASE_CFG))
                cfg["spike"]["cvr_abs_floor"] = floor
                cfg["spike"]["gex_abs_floor"] = floor
                cfg["spike"]["pctl_mult"] = mult
                cfg["netcvx"]["dump_drop"] = drop
                cfg["netcvx"]["ramp_rise"] = drop
                cfg["netcvx"]["dump_clear"] = drop / 2
                cfg["netcvx"]["ramp_clear"] = drop / 2
                per_day = {"spike": [], "netcvx": [], "two": [], "chat": []}
                for day, pulls in day_pulls_75.items():
                    evs = run_detector(pulls, cfg)
                    per_day["spike"].append(
                        sum(e["type"] in SPIKE_FAMILY for e in evs))
                    per_day["netcvx"].append(
                        sum(e["type"] in NETCVX_FAMILY for e in evs))
                    per_day["two"].append(
                        sum(e["type"] == "TWO_SIGNAL" for e in evs))
                    per_day["chat"].append(chatter(evs))
                combos.append({
                    "floor": floor, "mult": mult, "drop": drop,
                    "spikes_per_day_med": statistics.median(per_day["spike"]),
                    "netcvx_per_day_med": statistics.median(per_day["netcvx"]),
                    "two_signal_total": sum(per_day["two"]),
                    "chatter_total": sum(per_day["chat"]),
                })
    return combos


# ---------------------------------------------------------------- report

def fmt_pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0,
                    help="limit to the most recent N hist days (0 = all)")
    ap.add_argument("--grid", action="store_true",
                    help="include the threshold sweep grid (slower)")
    args = ap.parse_args()

    days = hist_days()
    if args.days:
        days = days[-args.days:]
    print(f"sweep over {len(days)} hist days ({days[0]}..{days[-1]})",
          flush=True)

    cov_tot: dict[str, dict] = {}
    base_events_per_day = {"spike": [], "netcvx": [], "two": []}
    chatter_total = 0
    vturn_rows: list[dict] = []
    two_rows: list[dict] = []
    close_rows: list[dict] = []
    day_pulls_75: dict[str, list[dict]] = {}
    skipped_days = []

    for day in days:
        pulls = load_day(day)
        if len(pulls) < 1000:
            skipped_days.append((day, len(pulls)))
            continue
        p75 = downsample(pulls)
        day_pulls_75[day] = p75
        sampled = {p["epoch"] for p in p75}
        for k, v in coverage(pulls, sampled).items():
            agg = cov_tot.setdefault(k, {"prints_1s": 0, "observed": 0})
            agg["prints_1s"] += v["prints_1s"]
            agg["observed"] += v["observed"]
        evs = run_detector(p75, BASE_CFG)
        base_events_per_day["spike"].append(
            sum(e["type"] in SPIKE_FAMILY for e in evs))
        base_events_per_day["netcvx"].append(
            sum(e["type"] in NETCVX_FAMILY for e in evs))
        base_events_per_day["two"].append(
            sum(e["type"] == "TWO_SIGNAL" for e in evs))
        chatter_total += chatter(evs)
        vturn_rows += leadlag_vturn(evs, pulls)
        two_rows += leadlag_two_signal(evs, pulls)
        sig = close_signature(pulls)
        if sig:
            sig["day"] = day
            close_rows.append(sig)
        print(f"  {day}: {len(pulls)} pulls(1s) {len(p75)} pulls(75s) "
              f"{len(evs)} events", flush=True)

    grid = sweep_grid(day_pulls_75) if args.grid else []

    raw = {
        "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days_used": sorted(day_pulls_75), "days_skipped": skipped_days,
        "coverage": cov_tot, "base_events_per_day": base_events_per_day,
        "chatter_total": chatter_total, "vturn": vturn_rows,
        "two_signal": two_rows, "close": close_rows, "grid": grid,
    }
    out_dir = REPO / "data" / "derived" / "acuity-sweep"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw.json").write_text(json.dumps(raw, indent=1))

    # ---- report ----------------------------------------------------------
    run_day = datetime.now(timezone.utc).date().isoformat()
    L = []
    L.append(f"# Orderflow acuity sweep — {run_day} [st-yirc]\n")
    L.append(f"{len(day_pulls_75)} hist days at 1s resolution "
             f"({min(day_pulls_75)} .. {max(day_pulls_75)}); detector run at "
             f"the live 75s cadence; 1s arrays as ground truth. "
             f"Skipped thin days: {skipped_days or 'none'}.\n")

    L.append("## A. What the 75s poll actually observes (instantaneous prints)\n")
    L.append("| print magnitude | 1s prints (all days) | seen by 75s poll | coverage |")
    L.append("|---|---|---|---|")
    for k in sorted(cov_tot):
        v = cov_tot[k]
        L.append(f"| {k} | {v['prints_1s']} | {v['observed']} "
                 f"| {fmt_pct(v['observed'], v['prints_1s'])} |")
    L.append("")

    L.append("## B. Baseline config, events/day over the archive\n")
    for fam, vals in base_events_per_day.items():
        if vals:
            L.append(f"- **{fam}**: median {statistics.median(vals)}, "
                     f"p90 {sorted(vals)[int(0.9 * (len(vals) - 1))]}, "
                     f"max {max(vals)}")
    L.append(f"- **re-arm chatter across all days**: {chatter_total}\n")

    L.append("## C. VTURN lead-lag vs the 1s spot path\n")
    if vturn_rows:
        leads = [r["min_lead_s"] for r in vturn_rows]
        led = sum(1 for r in vturn_rows if r["min_lead_s"] > 60)
        rebs = [r["rebound_pts"] for r in vturn_rows]
        L.append(f"{len(vturn_rows)} VTURN events. Spot's 30-min-forward low "
                 f"came >1 min AFTER the VTURN in {led}/{len(vturn_rows)} "
                 f"({fmt_pct(led, len(vturn_rows))}) — the 2026-08-07 "
                 f"'flow led price' observation tested across the archive.")
        L.append(f"- median time from VTURN to the spot low: "
                 f"{statistics.median(leads) / 60:.1f} min")
        L.append(f"- median rebound off that low within 30 min: "
                 f"{statistics.median(rebs):.1f} pts "
                 f"(p25 {sorted(rebs)[len(rebs) // 4]:.1f}, "
                 f"p75 {sorted(rebs)[3 * len(rebs) // 4]:.1f})\n")
    else:
        L.append("No VTURN events emitted over the archive.\n")

    L.append("## D. TWO_SIGNAL forward spot deltas\n")
    if two_rows:
        L.append(f"{len(two_rows)} TWO_SIGNAL events "
                 f"({sum(1 for r in two_rows if r['gex_side'] == 'put')} put-side).")
        for mins in (5, 15, 30):
            vals = [r[f"fwd_{mins}m_pts"] for r in two_rows
                    if r[f"fwd_{mins}m_pts"] is not None]
            if vals:
                L.append(f"- +{mins}m: median {statistics.median(vals):+.1f} pts, "
                         f"mean {statistics.mean(vals):+.1f}, n={len(vals)}")
        L.append("")
    else:
        L.append("No TWO_SIGNAL events emitted over the archive.\n")

    L.append("## E. Close signature (final 120s of RTH)\n")
    if close_rows:
        for key, label in (("max_abs_cvr", "max |cvroflow|"),
                           ("max_abs_gex", "max |gexoflow|"),
                           ("zcvr_delta", "zcvr net change")):
            vals = sorted(r[key] for r in close_rows)
            L.append(f"- {label}: median {vals[len(vals) // 2]:.0f}, "
                     f"p90 {vals[int(0.9 * (len(vals) - 1))]:.0f}, "
                     f"max {vals[-1]:.0f}")
        L.append("")

    if grid:
        L.append("## F. Threshold grid (75s cadence, all days)\n")
        L.append("| floor | mult | drop | spikes/day med | netcvx/day med "
                 "| two-signals total | chatter |")
        L.append("|---|---|---|---|---|---|---|")
        for c in grid:
            L.append(f"| {c['floor']:.0f} | {c['mult']} | {c['drop']:.0f} "
                     f"| {c['spikes_per_day_med']} | {c['netcvx_per_day_med']} "
                     f"| {c['two_signal_total']} | {c['chatter_total']} |")
        L.append("")

    L.append("Raw numbers: `data/derived/acuity-sweep/raw.json`. "
             "Measurement only — config unchanged pending review [st-yirc].")
    report = REPO / "docs" / "measurement" / f"orderflow-acuity-sweep-{run_day}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(L) + "\n")
    print(f"report -> {report}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
