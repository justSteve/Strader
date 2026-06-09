#!/usr/bin/env python3
"""Fly replay — reconstruct a butterfly's price path over the final hour. [st-745]

Conditional on the pin (realized settle), answers:
  1. Patience / anti-drawdown — for each candidate entry time, the fly mid you'd
     pay, the worst drawdown you'd sit through after, and the settle payoff.
  2. Exit / whip lens — the value path through the final 10 minutes, peak-to-
     trough give-back (the late swing a tight fly can't survive).

Prices from the OPRA SPXW trade tape (`databento_opra.jsonl[.gz]`), actual leg
prints (last-trade-forward). Settle: --settle, else last `schwab.jsonl` print,
else put-call parity off the tape. Core logic in market.measurement.fly.

Usage:
    .venv/bin/python scripts/measurement/fly_replay.py --date 2026-06-08 \\
        --center 7405 --width 5 --right C
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from market.corpus.paths import day_dir  # noqa: E402
from market.measurement.fly import (  # noqa: E402
    CENTRAL, collect_window, ct_epoch, entry_sweep, fly_intrinsic,
    fly_series, legs_from_window, settle_parity,
)


def settle_from_schwab(d) -> float | None:
    p = day_dir(d) / "schwab.jsonl"
    if not p.exists():
        return None
    last = None
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                v = json.loads(line)["data"].get("spot_spx")
                if v is not None:
                    last = float(v)
            except Exception:
                continue
    return last


def find_corpus(ddir: Path) -> Path | None:
    for name in ("databento_opra.jsonl", "databento_opra.jsonl.gz"):
        if (ddir / name).exists():
            return ddir / name
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay a butterfly's final-hour path")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (US/Central)")
    ap.add_argument("--center", type=float, required=True, help="Body strike")
    ap.add_argument("--width", type=float, default=5, help="Wing width (default 5)")
    ap.add_argument("--right", default="C", choices=["C", "P"])
    ap.add_argument("--start-ct", default="14:00")
    ap.add_argument("--end-ct", default="15:00", help="Window end / settle (default 15:00)")
    ap.add_argument("--bin", type=int, default=30)
    ap.add_argument("--settle", type=float, default=None,
                    help="SPX settle spot (default: schwab last, else parity)")
    args = ap.parse_args()

    d = datetime.fromisoformat(args.date).date()
    k_low, k_mid, k_high = args.center - args.width, args.center, args.center + args.width
    t0, t1 = ct_epoch(d, args.start_ct), ct_epoch(d, args.end_ct)

    ddir = day_dir(d)
    corpus = find_corpus(ddir)
    if corpus is None:
        print(f"[FAIL] no OPRA tape for {args.date} in {ddir}", file=sys.stderr)
        return 1

    expiry = d.strftime("%y%m%d")
    window = collect_window(corpus, expiry, t0, t1)
    legs = legs_from_window(window, {k_low, k_mid, k_high}, args.right)
    series = fly_series(legs, k_low, k_mid, k_high, t0, t1, args.bin)
    if not series:
        print(f"[FAIL] no fly prices — leg prints: "
              f"{ {k: len(v) for k, v in legs.items()} }", file=sys.stderr)
        return 2

    settle_spot = (args.settle if args.settle is not None
                   else settle_from_schwab(d)
                   or settle_parity(window, t1 - 600, t1))
    settle_val = (fly_intrinsic(settle_spot, k_low, k_mid, k_high, args.right)
                  if settle_spot is not None else None)

    lows = min(series, key=lambda x: x[1])
    highs = max(series, key=lambda x: x[1])
    fmt = lambda ep: datetime.fromtimestamp(ep, CENTRAL).strftime("%H:%M")

    print(f"# Fly replay — {args.date}  {args.right} "
          f"{k_low:g}/{k_mid:g}/{k_high:g} ({args.width:g}-wide)")
    print(f"  window      = {args.start_ct}-{args.end_ct} CT,  {len(series)} bins")
    print(f"  leg prints  = {k_low:g}:{len(legs[k_low])}  "
          f"{k_mid:g}:{len(legs[k_mid])}  {k_high:g}:{len(legs[k_high])}")
    if settle_spot is not None:
        print(f"  settle spot = {settle_spot:.2f}  ->  fly value = ${settle_val:.2f}")
    print(f"  fly LOW     = ${lows[1]:.2f} @ {fmt(lows[0])} CT")
    print(f"  fly HIGH    = ${highs[1]:.2f} @ {fmt(highs[0])} CT")

    print("\n## Entry-time sweep (the patience test)")
    print(f"  {'entry':>6}  {'pay':>6}  {'max_dd':>7}  {'settle':>7}  {'pnl':>7}")
    entry_eps = [t1 - m * 60 for m in (60, 45, 30, 20, 10, 5) if t1 - m * 60 >= t0]
    for r in entry_sweep(series, settle_val or 0.0, entry_eps):
        sv = f"{r['settle_value']:>7.2f}" if settle_val is not None else f"{'n/a':>7}"
        pnl = f"{r['pnl_to_settle']:>+7.2f}" if settle_val is not None else f"{'n/a':>7}"
        print(f"  {r['entry_ct']:>6}  {r['entry_price']:>6.2f}  "
              f"{r['max_drawdown']:>7.2f}  {sv}  {pnl}")

    f10 = [(t, p) for t, p in series if t >= t1 - 600]
    if f10:
        peak = max(p for _, p in f10)
        peak_t = next(t for t, p in f10 if p == peak)
        trough = min(p for t, p in f10 if t >= peak_t)
        print(f"\n## Final 10 min (exit/whip lens)")
        print(f"  peak ${peak:.2f} @ {fmt(peak_t)} -> trough ${trough:.2f}  "
              f"=  give-back ${peak - trough:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
