#!/usr/bin/env python3
"""Corpus Schwab pull — one cycle. [st-1yp]

Thin CLI shim. Real logic in market.corpus.schwab_stream.pull_cycle.
Idempotent; repeated calls append additional rows to the per-day JSONL.

Usage:
    .venv/bin/python scripts/corpus_pull_schwab.py [--symbol $SPX]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import schwab_path  # noqa: E402
from market.corpus.schwab_stream import pull_cycle  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Corpus Schwab pull — one cycle")
    parser.add_argument("--symbol", default="$SPX")
    args = parser.parse_args()

    record = pull_cycle(args.symbol)
    out = schwab_path()
    append_jsonl(out, record)
    update_manifest(d=None, stream="schwab", increment_cycles=1,
                    errors=record["errors"] or None)

    spx = record["data"]["spot_spx"]
    es = record["data"]["spot_es"]
    atm_k = record["data"]["atm"].get("atm_strike")
    straddle = record["data"]["atm"].get("atm_straddle")
    err_n = len(record["errors"])
    print(f"[{record['ts_pull_utc']}] schwab → {out}  "
          f"SPX={spx}  ES={es}  ATM K={atm_k}  straddle={straddle}  "
          f"errors={err_n}")
    return 0 if err_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
