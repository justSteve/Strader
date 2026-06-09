#!/usr/bin/env python3
"""Fly replay — corpus batch. Tests the late-day thesis at scale. [st-745]

For every corpus day with an OPRA tape, centers a fly at that day's OWN
realized pin (put-call parity settle, rounded to the 5-strike), replays the
final hour, and records the thesis metrics. Then aggregates:

  - Anti-drawdown: early-entry drawdown vs late-entry drawdown (does waiting
    to the final 10 min kill the drawdown?).
  - Cheaper-by-waiting: is the late entry cheaper than the early one, and how
    often?
  - Whip: final-10-min peak-to-trough give-back (the exit risk on a tight fly).

n=1 is an anecdote; this is the distribution. Per-day rows are written to
data/measurement/fly_batch.jsonl; a summary prints to stdout.

Usage:
    .venv/bin/python scripts/measurement/fly_replay_batch.py            # all days
    .venv/bin/python scripts/measurement/fly_replay_batch.py --sample 8 # recent 8
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date as _date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from market.corpus.paths import CORPUS_ROOT  # noqa: E402
from market.measurement.fly import (  # noqa: E402
    collect_window, ct_epoch, entry_sweep, fly_intrinsic, fly_series,
    legs_from_window, settle_parity,
)

WIDTH = 5.0
RIGHT = "C"


def _corpus_file(ddir: Path) -> Path | None:
    for name in ("databento_opra.jsonl", "databento_opra.jsonl.gz"):
        if (ddir / name).exists():
            return ddir / name
    return None


def study_day(d: _date, start_ct: str, end_ct: str, bin_s: int) -> dict | None:
    ddir = CORPUS_ROOT / d.isoformat()
    corpus = _corpus_file(ddir)
    if corpus is None:
        return None
    t0, t1 = ct_epoch(d, start_ct), ct_epoch(d, end_ct)
    window = collect_window(corpus, d.strftime("%y%m%d"), t0, t1)
    if not window:
        return None

    settle_spot = settle_parity(window, t1 - 600, t1)
    if settle_spot is None:
        return None
    center = round(settle_spot / 5.0) * 5.0
    k_low, k_mid, k_high = center - WIDTH, center, center + WIDTH

    legs = legs_from_window(window, {k_low, k_mid, k_high}, RIGHT)
    raw = fly_series(legs, k_low, k_mid, k_high, t0, t1, bin_s)
    # economic floor: a long fly is never worth < 0; clamp async-stale noise
    series = [(t, max(0.0, p)) for t, p in raw]
    if len(series) < 5:
        return None

    settle_val = fly_intrinsic(settle_spot, k_low, k_mid, k_high, RIGHT)
    low_t, low_p = min(series, key=lambda x: x[1])

    sweep = entry_sweep(series, settle_val, [t0, t1 - 600])  # -60min, -10min
    early, late = sweep[0], sweep[-1]

    f10 = [(t, p) for t, p in series if t >= t1 - 600]
    peak = max(p for _, p in f10)
    peak_t = next(t for t, p in f10 if p == peak)
    whip = peak - min(p for t, p in f10 if t >= peak_t)

    return {
        "date": d.isoformat(),
        "center": center,
        "settle_spot": round(settle_spot, 2),
        "settle_val": round(settle_val, 2),
        "low": round(low_p, 2),
        "low_min_before_close": round((t1 - low_t) / 60, 1),
        "early_price": early["entry_price"], "early_dd": early["max_drawdown"],
        "late_price": late["entry_price"], "late_dd": late["max_drawdown"],
        "drawdown_saved": round(early["max_drawdown"] - late["max_drawdown"], 2),
        "cheaper_by_waiting": round(early["entry_price"] - late["entry_price"], 2),
        "whip": round(whip, 2),
    }


def _med(xs):
    return round(statistics.median(xs), 2) if xs else None


def _pct(xs, pred):
    return round(100 * sum(1 for x in xs if pred(x)) / len(xs)) if xs else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fly-replay corpus batch")
    ap.add_argument("--sample", type=int, default=None, help="Only the N most-recent days")
    ap.add_argument("--start-ct", default="14:00")
    ap.add_argument("--end-ct", default="15:00")
    ap.add_argument("--bin", type=int, default=30)
    args = ap.parse_args()

    days = sorted(p.name for p in CORPUS_ROOT.iterdir()
                  if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
    if args.sample:
        days = days[-args.sample:]

    out_path = CORPUS_ROOT.parent / "measurement" / "fly_batch.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with out_path.open("w") as fh:
        for i, ds in enumerate(days, 1):
            try:
                rec = study_day(_date.fromisoformat(ds), args.start_ct, args.end_ct, args.bin)
            except Exception as e:
                print(f"  [{i}/{len(days)}] {ds} ERR {type(e).__name__}: {e}", file=sys.stderr)
                continue
            if rec:
                rows.append(rec)
                fh.write(json.dumps(rec) + "\n")
            print(f"  [{i}/{len(days)}] {ds} "
                  f"{'ok' if rec else 'skip'}", file=sys.stderr, flush=True)

    if not rows:
        print("[FAIL] no day produced a fly study", file=sys.stderr)
        return 1

    early_dd = [r["early_dd"] for r in rows]
    late_dd = [r["late_dd"] for r in rows]
    cheaper = [r["cheaper_by_waiting"] for r in rows]
    whip = [r["whip"] for r in rows]
    low_when = [r["low_min_before_close"] for r in rows]
    best_pnl = [round(r["settle_val"] - r["low"], 2) for r in rows]

    print(f"\n# Fly-replay batch — {len(rows)} days "
          f"({rows[0]['date']} … {rows[-1]['date']}), {WIDTH:g}-wide {RIGHT}, "
          f"final hour, centered at each day's parity pin")
    print(f"\n## Anti-drawdown (entry at -60min vs -10min)")
    print(f"  median drawdown  early(-60m): ${_med(early_dd)}   late(-10m): ${_med(late_dd)}")
    print(f"  late entry had LESS drawdown on {_pct(rows, lambda r: r['late_dd'] < r['early_dd'])}% of days")
    print(f"  late entry drawdown ~0 (<=$0.25) on {_pct(late_dd, lambda x: x <= 0.25)}% of days")
    print(f"\n## Cheaper-by-waiting (early price - late price)")
    print(f"  median cheaper_by_waiting: ${_med(cheaper)}  "
          f"(positive = late cheaper)")
    print(f"  late entry was cheaper on {_pct(cheaper, lambda x: x > 0)}% of days")
    print(f"\n## Where the low printed")
    print(f"  median minutes-before-close of the fly LOW: {_med(low_when)}")
    print(f"  low printed in the final 15 min on {_pct(low_when, lambda x: x <= 15)}% of days")
    print(f"\n## Final-10 whip (exit risk)")
    print(f"  median give-back: ${_med(whip)}   p90: "
          f"${round(sorted(whip)[int(0.9*len(whip))-1],2) if whip else 0}")
    print(f"  give-back >= $0.50 on {_pct(whip, lambda x: x >= 0.5)}% of days")
    print(f"\n## Payoff (conditional on the pin)")
    print(f"  median settle value: ${_med([r['settle_val'] for r in rows])}  "
          f"median best-case PnL (settle - low): ${_med(best_pnl)}")
    print(f"\nper-day rows -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
