#!/usr/bin/env python3
"""Corpus Schwab pull — one cycle. [st-1yp]

Thin CLI shim. Real logic in market.corpus.schwab_stream.pull_cycle.
Idempotent; repeated calls append additional rows to the per-day JSONL.

The snapshot always lands in TODAY's corpus day-dir (pull-time is the only
honest timestamp a live quote has) — there is deliberately no --date flag,
and schedulers that inject one for T+1 batch scripts must not do so here.

Usage:
    .venv/bin/python scripts/corpus_pull_schwab.py [--symbol $SPX] [--stage open]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import schwab_path  # noqa: E402
from market.corpus.schwab_stream import pull_cycle  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest  # noqa: E402

# Session-stage labels the stage-boundary cron stamps onto each record
# [st-096]. "adhoc" marks a hand-run pull; consumers filter on the label, so
# an unknown stage is a data defect, not a free-text field.
STAGES = ("premarket", "open", "afternoon", "close-watch", "daily-batch", "adhoc")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Corpus Schwab pull — one cycle")
    parser.add_argument("--symbol", default="$SPX")
    parser.add_argument("--stage", default="adhoc", choices=STAGES,
                        help="Session-stage label stamped onto the record (default: adhoc)")
    args = parser.parse_args(argv)

    record = pull_cycle(args.symbol)
    record["stage"] = args.stage
    out = schwab_path()
    append_jsonl(out, record)
    update_manifest(d=None, stream="schwab", increment_cycles=1,
                    errors=record["errors"] or None)

    spx = record["data"]["spot_spx"]
    es = record["data"]["spot_es"]
    atm_k = record["data"]["atm"].get("atm_strike")
    straddle = record["data"]["atm"].get("atm_straddle")
    err_n = len(record["errors"])
    print(f"[{record['ts_pull_utc']}] schwab[{args.stage}] → {out}  "
          f"SPX={spx}  ES={es}  ATM K={atm_k}  straddle={straddle}  "
          f"errors={err_n}")
    return 0 if err_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
