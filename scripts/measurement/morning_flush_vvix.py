#!/usr/bin/env python3
"""VVIX continuation test — does vol-of-vol add info beyond VIX? [st-lru8]

VVIX (implied vol of ~30-day VIX options — the quoted price of crash-tail
convexity) joined against the st-cdwe labeled minutes. The st-40fv lesson
applies: the raw slope is expected to be coupled to VIX; the residual of
dVVIX_5m on dVIX_5m (leave-one-day-out OLS) is the actual test of whether
tail demand carries anything the VIX print doesn't.

Traces (oriented x (-dir), higher = confirms the move):
  vvix_slope5      raw 5-min VVIX change
  vvix_resid_vix   dVVIX residual on dVIX (LOO)
  ratio_slope5     5-min change of VVIX/VIX
Quadrants: sign(dVIX_5m) x sign(dVVIX_5m) by move direction — the cell of
interest is VIX-/VVIX+ (near-dated vol sold while tails stay bid).

Usage:
    .venv/bin/python3 scripts/measurement/morning_flush_vvix.py

Output: data/measurement/morning_flush_vvix.json + stderr summary.
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

from morning_flush_continuation import CT, auc, load_internals  # noqa: E402
from morning_flush_vix_depth import ols  # noqa: E402

CONT_JSON = ROOT / "data" / "measurement" / "morning_flush_continuation.json"
STUDY = ROOT / "data" / "measurement" / "morning_flush_study.json"
OUT = ROOT / "data" / "measurement" / "morning_flush_vvix.json"
SLOPE_MIN = 5


def main():
    stored = json.loads(CONT_JSON.read_text())
    samples = stored["minute_samples"]
    assert len(samples) == stored["samples"], "stored sample count mismatch"
    day_dir = {x["date"]: (1 if x["move"]["dir"] == "up" else -1)
               for x in json.loads(STUDY.read_text()) if "move" in x}
    days = sorted({s["date"] for s in samples})

    rows = []
    for dstr in days:
        ints = load_internals(date.fromisoformat(dstr))
        vix, vvix = ints.get("$VIX", {}), ints.get("$VVIX", {})

        def d5(series, m):
            a = series.get(m)
            b = series.get(m - timedelta(minutes=SLOPE_MIN))
            return None if a is None or b is None else a - b

        ratio = {m: vvix[m] / vix[m] for m in vvix if m in vix and vix[m]}
        for s in (x for x in samples if x["date"] == dstr):
            m = datetime.combine(date.fromisoformat(dstr),
                                 time.fromisoformat(s["minute"]), CT)
            rows.append(dict(
                date=dstr, cont=s["cont"], dir=day_dir[dstr],
                dvix=d5(vix, m), dvvix=d5(vvix, m), dratio=d5(ratio, m),
                vvix_level=vvix.get(m)))
    assert len(rows) == len(samples), "join lost minutes"

    both = [(r["dvix"], r["dvvix"]) for r in rows
            if r["dvix"] is not None and r["dvvix"] is not None]
    global_fit = ols(both)
    loo_fit = {}
    for dstr in days:
        pairs = [(r["dvix"], r["dvvix"]) for r in rows if r["date"] != dstr
                 and r["dvix"] is not None and r["dvvix"] is not None]
        loo_fit[dstr] = ols(pairs)

    for r in rows:
        d_ = r["dir"]
        r["vvix_slope5"] = r["dvvix"] * -d_ if r["dvvix"] is not None else None
        r["ratio_slope5"] = r["dratio"] * -d_ if r["dratio"] is not None else None
        f = loo_fit[r["date"]]
        if f and r["dvix"] is not None and r["dvvix"] is not None:
            a, b, _ = f
            r["vvix_resid_vix"] = (r["dvvix"] - (a + b * r["dvix"])) * -d_
        else:
            r["vvix_resid_vix"] = None

    def summarize(key):
        sub = [r for r in rows if r[key] is not None]
        cont = [r[key] for r in sub if r["cont"]]
        term = [r[key] for r in sub if not r["cont"]]
        per_day = []
        for dstr in days:
            c = [r[key] for r in sub if r["date"] == dstr and r["cont"]]
            t = [r[key] for r in sub if r["date"] == dstr and not r["cont"]]
            x = auc(c, t)
            if x is not None:
                per_day.append(x)
        per_day.sort()
        a = auc(cont, term)
        return dict(auc=round(a, 3) if a else None,
                    auc_day_median=(round(per_day[len(per_day) // 2], 3)
                                    if per_day else None), n=len(sub))

    metrics = {k: summarize(k)
               for k in ("vvix_slope5", "vvix_resid_vix", "ratio_slope5")}

    quad = defaultdict(lambda: [0, 0])
    for r in rows:
        if not r["dvix"] or not r["dvvix"]:
            continue
        ctx = "dn_move" if r["dir"] == -1 else "up_move"
        q = ("vix+" if r["dvix"] > 0 else "vix-") + \
            ("vvix+" if r["dvvix"] > 0 else "vvix-")
        c = quad[(ctx, q)]
        c[0] += 1
        c[1] += r["cont"]
    quad_table = {f"{ctx}|{q}": dict(n=n, p_cont=round(k / n, 3))
                  for (ctx, q), (n, k) in sorted(quad.items())}

    levels = [r["vvix_level"] for r in rows if r["vvix_level"] is not None]
    out = dict(
        n_rows=len(rows),
        vvix_level_range=[min(levels), max(levels)] if levels else None,
        coupling_fit=dict(a=round(global_fit[0], 4), b=round(global_fit[1], 4),
                          r2=round(global_fit[2], 3)) if global_fit else None,
        metrics=metrics, quadrants=quad_table)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1), file=sys.stderr)
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
