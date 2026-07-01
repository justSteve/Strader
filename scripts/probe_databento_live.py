#!/usr/bin/env python3
"""Probe DataBento Live access — connect, grab 3 SPXW trades, disconnect.

Usage:
    ./scripts/run.sh probe_databento_live.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strader2.config import ConfigError  # noqa: E402
from strader2.settings import load_databento  # noqa: E402


def main() -> int:
    try:
        key = load_databento()["DATABENTO_API_KEY"]
    except ConfigError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    print(f"Key prefix: {key[:8]}...")

    try:
        import databento as db

        print("Connecting via db.Live(key=...) to OPRA.PILLAR...")
        client = db.Live(key=key)
        client.subscribe(
            dataset="OPRA.PILLAR",
            schema="trades",
            symbols=["SPXW.OPT"],
            stype_in="parent",
        )

        count = 0
        for record in client:
            from databento_dbn import TradeMsg, SymbolMappingMsg
            if isinstance(record, SymbolMappingMsg):
                continue
            if isinstance(record, TradeMsg):
                count += 1
                print(f"  [{count}] instrument_id={record.instrument_id}  "
                      f"price={record.pretty_price:.2f}  size={record.size}")
                if count >= 3:
                    break

        client.stop()
        print(f"\n[OK] Live access confirmed — received {count} trades")
        return 0

    except Exception as e:
        print(f"\n[FAIL] {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
