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
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Win the schwab package-name collision: the Strader project root has a
# local `schwab/` directory that shadows the schwab-py library when CWD
# puts the project root on sys.path first. Inserting the lib's parent at
# sys.path[0] forces schwab to resolve to the hobbled fork.
_LIB_SCHWAB_PY = Path(__file__).resolve().parent.parent / "lib" / "schwab-py"
sys.path.insert(0, str(_LIB_SCHWAB_PY))

# Expose project root for `market.*` imports — append so the lib path
# above wins any schwab resolution.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from schwab import auth as schwab_auth  # noqa: E402

from market.ingest import chain_from_schwab  # noqa: E402
from market.indicators.gex_calc import compute_gex  # noqa: E402


GATE_KEY = Path.home() / ".schwab_gate_key"


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.split("#", 1)[0].strip()
        if key and val and key not in os.environ:
            os.environ[key] = val


def _create_client():
    if not GATE_KEY.exists():
        raise RuntimeError(
            "SCHWAB GATE: ~/.schwab_gate_key not found. "
            "Create with `touch ~/.schwab_gate_key` to authorize."
        )
    _load_dotenv()
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    if not api_key or not app_secret:
        raise RuntimeError("Missing SCHWAB_API_KEY or SCHWAB_APP_SECRET in .env")
    if not Path(token_path).exists():
        raise RuntimeError(f"Token not found at {token_path}.")
    return schwab_auth.client_from_token_file(token_path, api_key, app_secret)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="One-shot GEX read on $SPX")
    p.add_argument("--symbol", default="$SPX",
                   help="Underlying symbol (default: $SPX)")
    p.add_argument("--expiry", default=None,
                   help="ISO expiry YYYY-MM-DD (default: today)")
    p.add_argument("--window", type=int, default=50,
                   help="± points around spot to show in by-strike table")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    expiry = (date.fromisoformat(args.expiry)
              if args.expiry else date.today())

    print(f"[{datetime.now():%H:%M:%S}] Fetching {args.symbol} chain for {expiry}...")
    client = _create_client()
    resp = client.get_option_chain(symbol=args.symbol)
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
    print(f"  {'strike':>8}  {'Δspot':>+7}  {'GEX ($B)':>10}  {'role':<12}")
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
