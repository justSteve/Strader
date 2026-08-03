#!/usr/bin/env python3
"""VIX depth pass — de-seasoned slope, beta residual, quadrants, term. [st-40fv]

Steve's direction (2026-08-03): VIX has no tape, but structure beyond
rising/falling exists. Four refinements measured against the st-cdwe labeled
minutes (joined from morning_flush_continuation.json on (date, minute) —
the label loop is NOT reimplemented; a parity assertion guards the join):

  vix_deseason   raw 5-min VIX slope minus the leave-one-day-out per-minute-
                 of-day median (VIX opens rich and decays mechanically; the
                 seasonal median is the clock, the residual is information),
                 oriented x (-dir)
  vix_beta_resid dVIX_5m minus the LOO OLS fit a + b*dES%_5m — VIX moving
                 MORE than the ES move justifies = protection demand (dn) /
                 vol crush (up), oriented x (-dir)
  vix_resid_ds   both corrections: de-seasoned dVIX regressed on dES% (LOO),
                 residual oriented x (-dir)
  term_slope5    5-min change of (VIX9D - VIX) x (-dir) — the front of the
                 curve stressing faster than the 30-day point
  quadrants      sign(dES_5m) x sign(dVIX_5m) occupancy and P(CONT), split
                 by move direction (monetization / spot-up-vol-up reads)

Usage:
    .venv/bin/python3 scripts/measurement/morning_flush_vix_depth.py

Output: data/measurement/morning_flush_vix_depth.json + stderr summary.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from market.orderflow.replay import read_corpus_day  # noqa: E402
from morning_flush_continuation import (  # noqa: E402
    CT, CORPUS, auc, load_internals, minute_bars)

CONT_JSON = ROOT / "data" / "measurement" / "morning_flush_continuation.json"
OUT = ROOT / "data" / "measurement" / "morning_flush_vix_depth.json"
SLOPE_MIN = 5   # the 5-minute change window every VIX metric uses


def vix_series(day: date) -> dict[str, dict[datetime, float]]:
    ints = load_internals(day)
    return {s: ints.get(s, {}) for s in ("$VIX", "$VIX9D", "$VIX3M")}


def d5(series: dict[datetime, float], m: datetime):
    a, b = series.get(m), series.get(m - timedelta(minutes=SLOPE_MIN))
    return None if a is None or b is None else a - b


def ols(pairs):
    """least squares y = a + b*x; returns (a, b, r2) or None."""
    n = len(pairs)
    if n < 30:
        return None
    sx = sum(x for x, _ in pairs); sy = sum(y for _, y in pairs)
    sxx = sum(x * x for x, _ in pairs); sxy = sum(x * y for x, y in pairs)
    den = n * sxx - sx * sx
    if den == 0:
        return None
    b = (n * sxy - sx * sy) / den
    a = (sy - b * sx) / n
    ybar = sy / n
    ss_tot = sum((y - ybar) ** 2 for _, y in pairs)
    ss_res = sum((y - a - b * x) ** 2 for x, y in pairs)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return a, b, r2


def main():
    stored = json.loads(CONT_JSON.read_text())
    samples = stored["minute_samples"]
    days = sorted({s["date"] for s in samples})
    assert len(samples) == stored["samples"], "stored sample count mismatch"

    # --- seasonality table: dVIX_5m per minute-of-day, per day (all VIX days)
    season: dict[str, dict[str, float]] = {}   # day -> minute-of-day -> dVIX
    for p in sorted(CORPUS.iterdir()):
        if not p.name.startswith("20"):
            continue
        try:
            dte = date.fromisoformat(p.name)
        except ValueError:
            continue
        vix = vix_series(dte)["$VIX"]
        if not vix:
            continue
        row = {}
        for m in sorted(vix):
            if time(8, 35) <= m.time() <= time(10, 15):
                dv = d5(vix, m)
                if dv is not None:
                    row[m.strftime("%H:%M")] = dv
        if row:
            season[p.name] = row

    def seasonal_median(day: str, hhmm: str):
        vals = sorted(r[hhmm] for d_, r in season.items()
                      if d_ != day and hhmm in r)
        return vals[len(vals) // 2] if vals else None

    # --- per-minute raw ingredients for every labeled minute
    rows = []
    for dstr in days:
        dte = date.fromisoformat(dstr)
        vs = vix_series(dte)
        trades = read_corpus_day(dte)
        w = [t for t in trades if time(8, 30) <= t.ts.time() < time(10, 30)]
        bars = minute_bars(w, datetime.combine(dte, time(8, 30), CT),
                           datetime.combine(dte, time(10, 30), CT))
        es_close = {m: b["close"] for m, b in bars.items()}
        day_samps = [s for s in samples if s["date"] == dstr]
        for s in day_samps:
            m = datetime.combine(dte, time.fromisoformat(s["minute"]), CT)
            dvix = d5(vs["$VIX"], m)
            term = {mm: vs["$VIX9D"][mm] - vs["$VIX"][mm]
                    for mm in vs["$VIX9D"] if mm in vs["$VIX"]}
            dterm = d5(term, m)
            e0 = es_close.get(m - timedelta(minutes=SLOPE_MIN))
            e1 = es_close.get(m)
            des_pct = (100 * (e1 - e0) / e0) if e0 and e1 else None
            des_pts = (e1 - e0) if e0 is not None and e1 is not None else None
            rows.append(dict(
                date=dstr, minute=s["minute"], cont=s["cont"],
                dvix=dvix, dterm=dterm, des_pct=des_pct, des_pts=des_pts,
                tick_aligned=s["tick_aligned"], add_slope10=s["add_slope10"],
                vix_slope5=s["vix_slope5"]))

    # move direction per day from the study spans
    study = json.loads((ROOT / "data" / "measurement" /
                        "morning_flush_study.json").read_text())
    day_dir = {x["date"]: (1 if x["move"]["dir"] == "up" else -1)
               for x in study if "move" in x}
    for r in rows:
        r["dir"] = day_dir[r["date"]]

    # --- LOO beta fits and traces
    fit_pairs = defaultdict(list)   # day -> (x, y) pairs from OTHER days
    all_pairs = [(r["des_pct"], r["dvix"]) for r in rows
                 if r["des_pct"] is not None and r["dvix"] is not None]
    global_fit = ols(all_pairs)
    for dstr in days:
        pairs = [(r["des_pct"], r["dvix"]) for r in rows
                 if r["date"] != dstr and r["des_pct"] is not None
                 and r["dvix"] is not None]
        fit_pairs[dstr] = ols(pairs)

    # de-seasoned pairs for the combined fit
    def deseason(r):
        if r["dvix"] is None:
            return None
        med = seasonal_median(r["date"], r["minute"])
        return None if med is None else r["dvix"] - med

    fit_ds = {}
    for dstr in days:
        pairs = [(r["des_pct"], deseason(r)) for r in rows if r["date"] != dstr]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        fit_ds[dstr] = ols(pairs)

    for r in rows:
        d_ = r["dir"]
        ds = deseason(r)
        r["vix_deseason"] = ds * -d_ if ds is not None else None
        f = fit_pairs[r["date"]]
        if f and r["des_pct"] is not None and r["dvix"] is not None:
            a, b, _ = f
            r["vix_beta_resid"] = (r["dvix"] - (a + b * r["des_pct"])) * -d_
        else:
            r["vix_beta_resid"] = None
        f2 = fit_ds[r["date"]]
        if f2 and r["des_pct"] is not None and ds is not None:
            a, b, _ = f2
            r["vix_resid_ds"] = (ds - (a + b * r["des_pct"])) * -d_
        else:
            r["vix_resid_ds"] = None
        r["term_slope5"] = (r["dterm"] * -d_) if r["dterm"] is not None else None

    # --- AUC table (raw slope recomputed on the same minute subset per metric)
    def summarize(key, baseline_subset=None):
        sub = [r for r in rows if r[key] is not None]
        cont = [r[key] for r in sub if r["cont"]]
        term = [r[key] for r in sub if not r["cont"]]
        a = auc(cont, term)
        per_day = []
        for dstr in days:
            c = [r[key] for r in sub if r["date"] == dstr and r["cont"]]
            t = [r[key] for r in sub if r["date"] == dstr and not r["cont"]]
            x = auc(c, t)
            if x is not None:
                per_day.append(x)
        per_day.sort()
        base = None
        if baseline_subset:
            bc = [r["vix_slope5"] for r in sub
                  if r["cont"] and r["vix_slope5"] is not None]
            bt = [r["vix_slope5"] for r in sub
                  if not r["cont"] and r["vix_slope5"] is not None]
            base = auc(bc, bt)
        return dict(auc=round(a, 3) if a else None,
                    auc_day_median=(round(per_day[len(per_day) // 2], 3)
                                    if per_day else None),
                    n=len(sub),
                    raw_slope_auc_same_subset=(round(base, 3) if base else None))

    metrics = {k: summarize(k, baseline_subset=True)
               for k in ("vix_deseason", "vix_beta_resid", "vix_resid_ds",
                         "term_slope5")}

    # --- quadrants
    quad = defaultdict(lambda: [0, 0])
    for r in rows:
        if not r["des_pts"] or r["dvix"] is None or r["dvix"] == 0:
            continue
        ctx = "dn_move" if r["dir"] == -1 else "up_move"
        q = ("es+" if r["des_pts"] > 0 else "es-") + \
            ("vix+" if r["dvix"] > 0 else "vix-")
        c = quad[(ctx, q)]
        c[0] += 1
        c[1] += r["cont"]
    quad_table = {f"{ctx}|{q}": dict(n=n, p_cont=round(k / n, 3))
                  for (ctx, q), (n, k) in sorted(quad.items())}

    # --- re-scored convergence with the best VIX variant
    best = max(metrics, key=lambda k: metrics[k]["auc"] or 0)
    combo = defaultdict(lambda: [0, 0])
    sc_c, sc_t = [], []
    for r in rows:
        vals = [r["tick_aligned"], r["add_slope10"], r[best]]
        if any(v is None for v in vals):
            continue
        score = sum(1 for v in vals if v > 0)
        c = combo[score]
        c[0] += 1
        c[1] += r["cont"]
        (sc_c if r["cont"] else sc_t).append(score)
    combo_table = {str(s): dict(n=n, p_cont=round(k / n, 3))
                   for s, (n, k) in sorted(combo.items())}
    combo_auc = auc(sc_c, sc_t)

    out = dict(
        n_rows=len(rows),
        global_beta_fit=dict(a=round(global_fit[0], 4),
                             b=round(global_fit[1], 4),
                             r2=round(global_fit[2], 3)) if global_fit else None,
        season_days=len(season),
        metrics=metrics, quadrants=quad_table,
        combo=dict(vix_variant=best, table=combo_table,
                   auc=round(combo_auc, 3) if combo_auc else None))
    OUT.write_text(json.dumps(out, indent=1))
    print(f"rows: {len(rows)} (parity with stored: "
          f"{len(rows) == stored['samples']})", file=sys.stderr)
    print(json.dumps(out, indent=1)[:2500], file=sys.stderr)
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
