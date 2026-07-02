#!/usr/bin/env python3
"""Probe DataBento key access — check what datasets/schemas are available.

Usage:
    ./scripts/run.sh probe_databento_access.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strader.config import ConfigError  # noqa: E402
from strader.settings import load_databento  # noqa: E402


def main() -> int:
    try:
        key = load_databento()["DATABENTO_API_KEY"]
    except ConfigError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    print(f"Key prefix: {key[:8]}...")

    import databento as db
    client = db.Historical()

    print("\n--- Available datasets ---")
    try:
        datasets = client.metadata.list_datasets()
        for ds in datasets:
            print(f"  {ds}")
    except Exception as e:
        print(f"  list_datasets error: {e}")

    print("\n--- OPRA.PILLAR schemas ---")
    try:
        schemas = client.metadata.list_schemas(dataset="OPRA.PILLAR")
        for s in schemas:
            print(f"  {s}")
    except Exception as e:
        print(f"  list_schemas error: {e}")

    print("\n--- GLBX.MDP3 schemas ---")
    try:
        schemas = client.metadata.list_schemas(dataset="GLBX.MDP3")
        for s in schemas:
            print(f"  {s}")
    except Exception as e:
        print(f"  list_schemas error: {e}")

    # Unit prices (USD per GB) keyed by delivery MODE — this is the
    # authoritative answer to "does live cost extra?". Use the SDK method
    # (handles Basic auth correctly) rather than a hand-rolled httpx call.
    import json
    for ds in ("OPRA.PILLAR", "GLBX.MDP3"):
        print(f"\n--- Unit prices (USD/GB) — {ds} ---")
        try:
            prices = client.metadata.list_unit_prices(dataset=ds)
            print(json.dumps(prices, indent=2, default=str))
        except Exception as e:
            print(f"  list_unit_prices error: {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
