#!/usr/bin/env python3
"""One-shot GexBot distillation runner. [st-rks]

Pulls /SPX/state/gamma_zero and emits the 4-tuple to stdout. No JSONL
persistence yet — that lands once the pairing harness is built (Steve's
manual tape-read input + post-EOD print backfill).

Usage:
    .venv/bin/python scripts/gexbot_distill.py [--ticker SPX] [--category gamma_zero]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.ingest.gexbot import distill, fetch_state, load_api_key, make_client


def main() -> int:
    parser = argparse.ArgumentParser(description="GexBot State distillation, one shot.")
    parser.add_argument("--ticker", default="SPX")
    parser.add_argument("--category", default="gamma_zero",
                        help="State category (gamma_zero is the default 0DTE read)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    api_key = load_api_key(root / ".env")

    with make_client(api_key) as client:
        state = fetch_state(client, args.ticker, args.category)

    d = distill(state)
    ts = datetime.fromtimestamp(d.timestamp).strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== GexBot distillation [{args.ticker} {args.category}] ===")
    print(f"  ts        {ts}  (epoch {d.timestamp})")
    print(f"  spot      {d.spot:.2f}")
    print(f"  center    {d.center_strike}")
    print(f"  regime    {d.regime}")
    print(f"  confidence {d.confidence}")
    print(f"  reason    {d.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
