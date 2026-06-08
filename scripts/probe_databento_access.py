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


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s and "DATABENTO" in s:
            k, _, v = s.partition("=")
            os.environ.setdefault(k.strip(), v.split("#", 1)[0].strip())


def main() -> int:
    _load_dotenv()

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("[FAIL] DATABENTO_API_KEY not set", file=sys.stderr)
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
