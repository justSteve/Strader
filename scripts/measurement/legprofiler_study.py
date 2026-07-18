#!/usr/bin/env python3
"""Structural Leg Profiler study — corpus batch. [st-bg4]

Replays every corpus day with an ES tape through the deterministic Leg
Profiler reimplementation (market/measurement/legprofiler.py) at each swing
multiplier in the sensitivity sweep, scores hypotheses H1 (naked-POC touch
reaction vs matched random control), H2 (delta divergence at leg extensions
precedes termination), H3 (volume anomalies in the leg's final range fraction
mark reversals), and appends one row per (day, multiplier) to the append-only
measurement store. Collections (late-day vs full-RTH vs morning-only) are
classified from the tape's own time span and always reported separately —
window truncation biases leg statistics.

Usage:
    .venv/bin/python3 scripts/measurement/legprofiler_study.py               # all days
    .venv/bin/python3 scripts/measurement/legprofiler_study.py --sample 5    # recent 5
    .venv/bin/python3 scripts/measurement/legprofiler_study.py --summarize   # aggregate
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import date as _date, time as _time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from market.measurement import legprofiler as lp  # noqa: E402
from market.orderflow.replay import read_corpus_day  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "data" / "corpus"
STORE = ROOT / "data" / "measurement" / "legprofiler_study.jsonl"
ES_FILE = "databento_glbx_es.jsonl"


def classify(first: _time, last: _time) -> str:
    if first <= _time(9, 0) and last >= _time(14, 30):
        return "full_rth"
    if first >= _time(12, 30):
        return "late_day"
    if first <= _time(9, 0):
        return "morning_only"
    return "other"


def study_day(day: str) -> list[dict]:
    trades = read_corpus_day(CORPUS / day / ES_FILE)
    if len(trades) < 1000:
        return []
    collection = classify(trades[0].ts.time(), trades[-1].ts.time())
    ts_index = [t.ts for t in trades]
    bars = lp.build_time_bars(trades)
    atrs = lp.wilder_atr(bars, lp.ATR_PERIOD)
    flags = lp.anomaly_flags(bars)
    rows = []
    for mult in lp.SWING_MULTS:
        legs = lp.segment_legs(bars, atrs, mult)
        profs = [lp.build_leg_profile(lp.leg_trades(trades, ts_index, leg))
                 for leg in legs]
        touch = lp.score_naked_pocs(legs, profs, trades, ts_index,
                                    f"{day}:{mult}")
        audit = lp.audit_no_repaint(touch, legs)
        h1 = {"poc": defaultdict(int), "control": defaultdict(int)}
        for e in touch:
            h1[e.kind][e.outcome] += 1
        ext = lp.score_delta_divergence(legs, bars)
        anom = lp.score_volume_anomalies(legs, bars, flags)
        extanom = lp.score_extension_anomalies(legs, bars, flags)
        rows.append({
            "day": day, "collection": collection,
            "atr_period": lp.ATR_PERIOD, "mult": mult,
            "n_trades": len(trades), "n_bars": len(bars), "n_legs": len(legs),
            "median_leg_range_pts": round(statistics.median(
                [l.range_pts for l in legs]), 2) if legs else None,
            "median_leg_bars": statistics.median(
                [l.end_idx - l.start_idx for l in legs]) if legs else None,
            "h1": {k: dict(v) for k, v in h1.items()},
            "h2": {
                "div_n": sum(1 for e in ext if e.divergent),
                "div_term": sum(1 for e in ext if e.divergent and e.terminal),
                "conf_n": sum(1 for e in ext if not e.divergent),
                "conf_term": sum(1 for e in ext if not e.divergent and e.terminal),
            },
            "h3": {
                "extreme_n": sum(1 for e in anom if e.zone == "extreme"),
                "extreme_term": sum(1 for e in anom if e.zone == "extreme" and e.terminal),
                "body_n": sum(1 for e in anom if e.zone == "body"),
                "body_term": sum(1 for e in anom if e.zone == "body" and e.terminal),
            },
            "h3b": {
                "anom_n": sum(1 for e in extanom if e.anomalous),
                "anom_term": sum(1 for e in extanom if e.anomalous and e.terminal),
                "plain_n": sum(1 for e in extanom if not e.anomalous),
                "plain_term": sum(1 for e in extanom if not e.anomalous and e.terminal),
            },
            "audit_violations": len(audit),
            "bead": "st-bg4",
        })
    return rows


def run(sample: int | None, force: bool) -> None:
    done: set[tuple[str, float]] = set()
    if STORE.exists() and not force:
        for line in STORE.open():
            if line.strip():
                r = json.loads(line)
                done.add((r["day"], r["mult"]))
    days = sorted(d.name for d in CORPUS.iterdir()
                  if (d / ES_FILE).exists())
    if sample:
        days = days[-sample:]
    todo = [d for d in days if any((d, m) not in done for m in lp.SWING_MULTS)]
    print(f"{len(days)} tape days, {len(todo)} to run", flush=True)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    for i, day in enumerate(todo, 1):
        try:
            rows = [r for r in study_day(day) if (r["day"], r["mult"]) not in done]
        except Exception as e:  # noqa: BLE001 — one bad day must not kill the batch
            print(f"[{i}/{len(todo)}] {day} FAILED: {e}", flush=True)
            continue
        with STORE.open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        if rows:
            r = rows[0]
            print(f"[{i}/{len(todo)}] {day} {r['collection']}: "
                  f"{r['n_bars']} bars, legs {[x['n_legs'] for x in rows]}, "
                  f"audit={sum(x['audit_violations'] for x in rows)}", flush=True)


def _rate(k: int, n: int) -> str:
    return f"{k / n:.1%} ({k}/{n})" if n else "—"


def summarize() -> None:
    # append-only store: a --force re-run supersedes — keep the LAST row per (day, mult)
    latest: dict[tuple[str, float], dict] = {}
    for l in STORE.open():
        if l.strip():
            r = json.loads(l)
            latest[(r["day"], r["mult"])] = r
    groups: dict[tuple[str, float], list[dict]] = defaultdict(list)
    for r in latest.values():
        groups[(r["collection"], r["mult"])].append(r)
    for (coll, mult) in sorted(groups):
        g = groups[(coll, mult)]
        if coll not in ("late_day", "full_rth", "morning_only"):
            continue
        legs = sum(r["n_legs"] for r in g)
        viol = sum(r["audit_violations"] for r in g)
        print(f"\n=== {coll} · mult {mult} · {len(g)} days · {legs} legs "
              f"· audit violations {viol} ===")
        # H1
        def _h1(kind: str) -> tuple[int, int, int]:
            b = sum(r["h1"][kind].get("bounce", 0) for r in g)
            p = sum(r["h1"][kind].get("penetrate", 0) for r in g)
            t = sum(r["h1"][kind].get("timeout", 0) for r in g)
            return b, p, t
        pb, pp, pt = _h1("poc")
        cb, cp, ct = _h1("control")
        pn, cn = pb + pp + pt, cb + cp + ct
        _, _, z = lp.two_prop_z(pb, pn, cb, cn)
        print(f"H1 bounce-at-touch: poc {_rate(pb, pn)}  vs  control {_rate(cb, cn)}"
              f"   z={z:+.2f}")
        print(f"   poc outcomes: bounce {pb} / penetrate {pp} / timeout {pt} / "
              f"never {sum(r['h1']['poc'].get('never_touched', 0) for r in g)}")
        # H2
        dn = sum(r["h2"]["div_n"] for r in g)
        dt = sum(r["h2"]["div_term"] for r in g)
        cn2 = sum(r["h2"]["conf_n"] for r in g)
        ct2 = sum(r["h2"]["conf_term"] for r in g)
        _, _, z2 = lp.two_prop_z(dt, dn, ct2, cn2)
        print(f"H2 terminal-within-{lp.TERM_WINDOW_BARS}-bars: divergent "
              f"{_rate(dt, dn)}  vs  confirmed {_rate(ct2, cn2)}   z={z2:+.2f}")
        # H3
        en = sum(r["h3"]["extreme_n"] for r in g)
        et = sum(r["h3"]["extreme_term"] for r in g)
        bn = sum(r["h3"]["body_n"] for r in g)
        bt = sum(r["h3"]["body_term"] for r in g)
        _, _, z3 = lp.two_prop_z(et, en, bt, bn)
        print(f"H3 anomaly->reversal: extreme-zone {_rate(et, en)}  vs  body "
              f"{_rate(bt, bn)}   z={z3:+.2f}")
        # H3b (real-time variant; older rows may predate it)
        gb = [r for r in g if "h3b" in r]
        if gb:
            an = sum(r["h3b"]["anom_n"] for r in gb)
            at = sum(r["h3b"]["anom_term"] for r in gb)
            qn = sum(r["h3b"]["plain_n"] for r in gb)
            qt = sum(r["h3b"]["plain_term"] for r in gb)
            _, _, z4 = lp.two_prop_z(at, an, qt, qn)
            print(f"H3b extension+anomaly->terminal: anomalous {_rate(at, an)}  vs  "
                  f"normal-vol {_rate(qt, qn)}   z={z4:+.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, help="only the most recent N tape days")
    ap.add_argument("--force", action="store_true",
                    help="re-run days already in the store (rows still append)")
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()
    if args.summarize:
        summarize()
    else:
        run(args.sample, args.force)


if __name__ == "__main__":
    main()
