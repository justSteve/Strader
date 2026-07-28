#!/usr/bin/env python3
"""Corpus-wide fundamental-units sweep — atoms + moves for every ES day. [st-kaf]

Writes (append-only, run-stamped, one row per unit):
  data/measurement/moves/atoms.jsonl — every 1-minute atom, day-relative grades
  data/measurement/moves/moves.jsonl — every zigzag leg; effort/effect grades
                                       recomputed CORPUS-wide (a day has too
                                       few legs to grade against itself)

Usage:  .venv/bin/python scripts/moves_sweep.py [--workers 6] [--days ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date as _date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.orderflow.moves import (grade_atoms, one_minute_atoms,  # noqa: E402
                                    segment_moves, _grade, _pctl_rank)
from market.orderflow.replay import read_corpus_day                  # noqa: E402
from market.orderflow.tpo import build_tpo, classify_day_type        # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "measurement" / "moves"


def run_day(day_s: str) -> dict:
    try:
        day = _date.fromisoformat(day_s)
        trades = read_corpus_day(day)
        if not trades:
            return {"day": day_s, "status": "empty"}
        atoms = grade_atoms(one_minute_atoms(trades))
        moves = segment_moves(atoms)
        try:
            day_type, _ = classify_day_type(build_tpo(trades))
        except Exception:
            day_type = "unknown"
        coverage = "rth" if trades[0].ts.hour < 9 else "late_day"
        a_rows = [{"day": day_s, "ct": a.ts.strftime("%H:%M"),
                   "net": a.net, "range": a.range_pts, "travel": a.travel_ratio,
                   "vol": a.volume, "force": a.delta,
                   "effort_pct": a.effort_pct, "effect_pct": a.effect_pct,
                   "cell": a.cell, "grade": a.cell_grade,
                   "day_type": day_type, "coverage": coverage}
                  for a in atoms]
        m_rows = [{"day": day_s, "start_ct": m.start_ts.strftime("%H:%M"),
                   "end_ct": m.end_ts.strftime("%H:%M"), "dir": m.direction,
                   "net_pts": m.net_pts, "extreme_pts": m.extreme_pts,
                   "minutes": m.minutes, "effort": m.effort, "force": m.force,
                   "cells": "".join(m.atoms).replace("F", ""),
                   "day_type": day_type, "coverage": coverage}
                  for m in moves]
        return {"day": day_s, "status": "ok", "atoms": a_rows, "moves": m_rows}
    except Exception as exc:
        return {"day": day_s, "status": "error", "detail": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Fundamental-units corpus sweep [st-kaf]")
    ap.add_argument("--days", nargs="*")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    days = sorted(args.days) if args.days else sorted(
        p.parent.name for p in
        (REPO_ROOT / "data" / "corpus").glob("*/databento_glbx_es.jsonl"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"moves sweep {run_id}: {len(days)} days, {args.workers} workers")

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_day, d): d for d in days}
        for n, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if n % 50 == 0 or n == len(days):
                print(f"  {n}/{len(days)}")
    results.sort(key=lambda r: r["day"])

    all_moves = [m for r in results if r["status"] == "ok" for m in r["moves"]]
    # corpus-wide grades for legs — normalized within coverage cohort so a
    # 2-hour tape's legs aren't graded against full-RTH legs
    for cohort in ("rth", "late_day"):
        legs = [m for m in all_moves if m["coverage"] == cohort]
        eff = sorted(m["effort"] for m in legs)
        net = sorted(abs(m["net_pts"]) for m in legs)
        for m in legs:
            m["effort_pct"] = _pctl_rank(eff, m["effort"])
            m["effect_pct"] = _pctl_rank(net, abs(m["net_pts"]))
            m["cell"], m["grade"] = _grade(m["effort_pct"], m["effect_pct"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_atoms = 0
    with (OUT_DIR / "atoms.jsonl").open("a", encoding="utf-8") as fa, \
            (OUT_DIR / "moves.jsonl").open("a", encoding="utf-8") as fm:
        for r in results:
            if r["status"] != "ok":
                continue
            for a in r["atoms"]:
                n_atoms += 1
                fa.write(json.dumps({"run": run_id} | a, separators=(",", ":")) + "\n")
            for m in r["moves"]:
                fm.write(json.dumps({"run": run_id} | m, separators=(",", ":")) + "\n")

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"run {run_id}: {ok} days -> {n_atoms:,} atoms, {len(all_moves):,} moves")
    for st in ("empty", "error"):
        bad = [r["day"] for r in results if r["status"] == st]
        if bad:
            print(f"  {st}: {len(bad)} ({', '.join(bad[:5])}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
