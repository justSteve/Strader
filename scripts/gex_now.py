#!/usr/bin/env python3
"""
One-shot GEX read: pull today's SPX chain from Schwab, compute net GEX,
print by-strike contributions ranked by magnitude, and flag the largest
positive-gamma walls around spot.

Bypasses the local schwab/ wrapper package (which shadows the schwab-py
library because of the package-name collision) and talks to schwab-py
directly from site-packages. Replicates the gate-key check inline.

USAGE:
    python scripts/gex_now.py                   # today's expiry, ±50 around spot
    python scripts/gex_now.py --expiry 2026-05-21 --window 75

Requires ~/.schwab_gate_key (Steve creates with `touch`).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Add Strader root for `market.*` and `broker_schwab.*` imports. No sys.path
# gymnastics needed for `schwab` — the upstream hobbled fork resolves cleanly
# from site-packages now that st-8cx renamed the local wrapper.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker_schwab.client import create_client  # noqa: E402
from market.ingest import chain_from_schwab  # noqa: E402
from market.indicators.gex_calc import compute_gex  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="One-shot GEX read on $SPX")
    p.add_argument("--symbol", default="$SPX",
                   help="Underlying symbol (default: $SPX)")
    p.add_argument("--expiry", default=None,
                   help="ISO expiry YYYY-MM-DD (default: today)")
    p.add_argument("--strikes", type=int, default=30,
                   help="Strikes above and below ATM to request (default: 30 → 60 total). "
                        "Bounding this is critical — an unbounded SPX chain query 502s Schwab.")
    p.add_argument("--dte", type=int, default=0,
                   help="Max days-to-expiration for the chain query "
                        "(default: 0 = today only).")
    p.add_argument("--window", type=int, default=50,
                   help="± points around spot to show in by-strike table")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    expiry = (date.fromisoformat(args.expiry)
              if args.expiry else date.today())

    from datetime import timedelta
    to_date = date.today() + timedelta(days=args.dte)

    print(f"[{datetime.now():%H:%M:%S}] Fetching {args.symbol} chain for "
          f"{expiry}  (strike_count={args.strikes}, to_date={to_date})...")
    client = create_client()
    resp = client.get_option_chain(
        symbol=args.symbol,
        strike_count=args.strikes,
        from_date=date.today(),
        to_date=to_date,
        include_underlying_quote=True,
    )
    resp.raise_for_status()
    data = resp.json()

    chain = chain_from_schwab(data, expiry=expiry)
    spot = chain.underlying_price
    n_strikes = len(set(chain.calls) | set(chain.puts))
    print(f"  underlying_price={spot:.2f}  n_strikes={n_strikes}")

    if n_strikes == 0:
        print(f"\n[ALERT] No strikes returned for expiry {expiry}. "
              f"Try an upcoming expiry with --expiry YYYY-MM-DD.")
        return 2

    profile = compute_gex(chain)
    sign = "+" if profile.net_gex >= 0 else "−"
    print(f"\nNET GEX: {sign}{abs(profile.net_gex)/1e9:.2f}B  "
          f"(calls {profile.net_gex_calls/1e9:+.2f}B, "
          f"puts {profile.net_gex_puts/1e9:+.2f}B)")
    regime = ("SUPPRESSIVE (dealers long gamma — magnets, mean-revert)"
              if profile.net_gex > 0
              else "AMPLIFYING (dealers short gamma — accelerate trends)")
    print(f"REGIME: {regime}\n")

    nearby = {k: v for k, v in profile.by_strike.items()
              if abs(k - spot) <= args.window}
    if not nearby:
        print(f"(no strikes within ±{args.window} of spot)")
        return 0

    print(f"Per-strike GEX (sorted by |magnitude|), strikes within ±{args.window} of spot {spot:.0f}:")
    print(f"  {'strike':>8}  {'Δspot':>7}  {'GEX ($B)':>10}  {'role':<12}")
    print(f"  {'─'*8}  {'─'*7}  {'─'*10}  {'─'*12}")
    for k in sorted(nearby.keys(), key=lambda x: abs(nearby[x]), reverse=True):
        gex_b = nearby[k] / 1e9
        delta_spot = k - spot
        role = ("WALL ↑" if nearby[k] > 0 and k > spot else
                "WALL ↓" if nearby[k] > 0 and k <= spot else
                "VAC ↓" if nearby[k] < 0 and k <= spot else "VAC ↑")
        print(f"  {k:>8.0f}  {delta_spot:>+7.1f}  {gex_b:>+10.2f}  {role}")

    print()
    positive = {k: v for k, v in nearby.items() if v > 0}
    if positive:
        wall_strike = max(positive.keys(), key=lambda k: positive[k])
        wall_gex = positive[wall_strike] / 1e9
        print(f"LARGEST POSITIVE-GAMMA WALL: {wall_strike:.0f}  "
              f"(${wall_gex:.2f}B, {wall_strike - spot:+.1f} from spot)")
    negative = {k: v for k, v in nearby.items() if v < 0}
    if negative:
        slide_strike = min(negative.keys(), key=lambda k: negative[k])
        slide_gex = negative[slide_strike] / 1e9
        print(f"LARGEST NEG-GAMMA SLIDE:     {slide_strike:.0f}  "
              f"(${slide_gex:.2f}B, {slide_strike - spot:+.1f} from spot)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
