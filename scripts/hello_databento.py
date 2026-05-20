#!/usr/bin/env python3
"""
Hello World for Databento Live integration.

Connects to the Databento Live gateway with DATABENTO_API_KEY from env (or .env),
subscribes to a narrow stream (default: ES futures trades), prints the first
N typed Trade entities, and exits.

USAGE:
    python scripts/hello_databento.py                 # default: 5 ES trades
    python scripts/hello_databento.py --count 20      # 20 records
    python scripts/hello_databento.py --symbol AAPL --dataset XNAS.ITCH

COST WARNING: subscribing to a Databento Live stream incurs metered cost.
This script disconnects after the requested record count to bound the bill.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_dotenv_if_present() -> None:
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Databento Live smoke test")
    p.add_argument("--dataset", default="GLBX.MDP3",
                   help="Databento dataset (default: GLBX.MDP3 = CME futures)")
    p.add_argument("--schema", default="trades",
                   help="Databento schema (default: trades)")
    p.add_argument("--symbol", default="ES.c.0",
                   help="Symbol to subscribe (default: ES.c.0 = front-month E-mini S&P)")
    p.add_argument("--stype", default="continuous",
                   help="Symbol type (continuous|raw_symbol|...). Default: continuous")
    p.add_argument("--count", type=int, default=5,
                   help="How many Trade entities to print before disconnecting")
    return p.parse_args()


def main() -> int:
    _load_dotenv_if_present()

    if not os.environ.get("DATABENTO_API_KEY"):
        print("[ALERT] DATABENTO_API_KEY not set in env or .env", file=sys.stderr)
        return 1

    args = parse_args()
    print(f"Connecting to Databento Live gateway...")
    print(f"  dataset={args.dataset}  schema={args.schema}  symbol={args.symbol}  stype_in={args.stype}")

    from market.ingest.databento import LiveClient

    client = LiveClient()
    client.subscribe(
        dataset=args.dataset,
        schema=args.schema,
        symbols=[args.symbol],
        stype_in=args.stype,
    )

    is_quote_schema = args.schema in ("mbp-1", "tbbo")
    record_label = "quote(s)" if is_quote_schema else "trade(s)"
    print(f"Subscribed. Waiting for first {args.count} {record_label}...\n")

    received = 0
    try:
        if is_quote_schema:
            for quote in client.quotes():
                received += 1
                print(f"  [{received}] {quote.ts.isoformat()}  {quote.symbol:<10}  "
                      f"bid {quote.bid_price:>10.4f}x{quote.bid_size:<5}  "
                      f"ask {quote.ask_price:>10.4f}x{quote.ask_size:<5}  "
                      f"spread={quote.spread:.4f}")
                if received >= args.count:
                    break
        else:
            for trade in client.trades():
                received += 1
                print(f"  [{received}] {trade.ts.isoformat()}  {trade.symbol:<10}  "
                      f"{trade.price:>12.4f}  size={trade.size:<6}  side={trade.side}")
                if received >= args.count:
                    break
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        client.close()
        print(f"\nDisconnected. Received {received} {record_label}.")

    return 0 if received > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
