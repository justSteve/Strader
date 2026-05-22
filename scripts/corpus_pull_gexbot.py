#!/usr/bin/env python3
"""Corpus GexBot pull — one cycle. [st-1yp]

Thin CLI shim. Real logic in market.corpus.gexbot_stream.pull_cycle.
Hits 5 endpoints (gamma_zero, vanna_zero, charm_zero, delta_zero, and
classic gex_zero/majors), bundles into one JSONL row per cycle.

Usage:
    .venv/bin/python scripts/corpus_pull_gexbot.py [--ticker SPX]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.gexbot_stream import pull_cycle  # noqa: E402
from market.corpus.paths import gexbot_path  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Corpus GexBot pull — one cycle")
    parser.add_argument("--ticker", default="SPX")
    args = parser.parse_args()

    record = pull_cycle(args.ticker)
    out = gexbot_path()
    append_jsonl(out, record)
    update_manifest(d=None, stream="gexbot", increment_cycles=1,
                    errors=record["errors"] or None)

    s = record["data"]["summary"]
    err_n = len(record["errors"])
    print(f"[{record['ts_pull_utc']}] gexbot → {out}  "
          f"spot={s['spot_at_gamma_zero']}  "
          f"mpos={s['major_positive']}  mneg={s['major_negative']}  "
          f"mLg={s['major_long_gamma']}  mSg={s['major_short_gamma']}  "
          f"errors={err_n}")
    return 0 if err_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
