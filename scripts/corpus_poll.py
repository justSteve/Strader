#!/usr/bin/env python3
"""Corpus orchestrator — one cycle of Schwab + GexBot, optionally looped. [st-1yp]

Calls `pull_cycle` from each stream's pull script in sequence and writes
their records to the per-day corpus directory. Designed to be wrapped in
a cron job (recommended) or run inline with --interval for a foreground
loop during a market session.

Databento is NOT polled here — it's a T+1 batch run via
`scripts/corpus_pull_databento.py` after the close.

Usage:
    # one-shot (cron-friendly)
    .venv/bin/python scripts/corpus_poll.py

    # foreground loop, 1-min cadence, full RTH session (Ctrl-C or --max-runs)
    .venv/bin/python scripts/corpus_poll.py --interval 60 --max-runs 390

Failures in one stream don't stop the other. Both records always written;
errors propagate into the manifest.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.gexbot_stream import pull_cycle as gexbot_cycle  # noqa: E402
from market.corpus.paths import day_dir, schwab_path, gexbot_path  # noqa: E402
from market.corpus.schwab_stream import pull_cycle as schwab_cycle  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest, utc_now_iso  # noqa: E402


_stop = False


def _handle_sigint(signum, frame):
    global _stop
    _stop = True


def one_cycle() -> tuple[int, int]:
    """Run one Schwab pull + one GexBot pull. Returns (schwab_err_count, gexbot_err_count)."""
    schwab_errs, gexbot_errs = 0, 0

    try:
        rec = schwab_cycle()
        append_jsonl(schwab_path(), rec)
        update_manifest(d=None, stream="schwab", increment_cycles=1,
                        errors=rec["errors"] or None)
        s = rec["data"]
        print(f"  [{rec['ts_pull_utc']}] schwab  SPX={s.get('spot_spx')}  "
              f"ES={s.get('spot_es')}  ATM={s.get('atm', {}).get('atm_strike')}  "
              f"straddle={s.get('atm', {}).get('atm_straddle')}  "
              f"errors={len(rec['errors'])}")
        schwab_errs = len(rec["errors"])
    except Exception as e:
        print(f"  schwab CYCLE FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        update_manifest(d=None, stream="schwab",
                        errors=[f"cycle exception: {type(e).__name__}: {e}"])
        schwab_errs = 1

    try:
        rec = gexbot_cycle()
        append_jsonl(gexbot_path(), rec)
        update_manifest(d=None, stream="gexbot", increment_cycles=1,
                        errors=rec["errors"] or None)
        s = rec["data"]["summary"]
        print(f"  [{rec['ts_pull_utc']}] gexbot  spot={s.get('spot_at_gamma_zero')}  "
              f"mpos={s.get('major_positive')}  mneg={s.get('major_negative')}  "
              f"mLg={s.get('major_long_gamma')}  mSg={s.get('major_short_gamma')}  "
              f"errors={len(rec['errors'])}")
        gexbot_errs = len(rec["errors"])
    except Exception as e:
        print(f"  gexbot CYCLE FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        update_manifest(d=None, stream="gexbot",
                        errors=[f"cycle exception: {type(e).__name__}: {e}"])
        gexbot_errs = 1

    return schwab_errs, gexbot_errs


def main() -> int:
    parser = argparse.ArgumentParser(description="Corpus orchestrator")
    parser.add_argument("--interval", type=int, default=None,
                        help="Seconds between cycles; omit for one-shot")
    parser.add_argument("--max-runs", type=int, default=None,
                        help="Stop after N cycles (default: indefinite with --interval)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_sigint)

    day_dir(create=True)

    if args.interval is None:
        s_e, g_e = one_cycle()
        return 0 if (s_e == 0 and g_e == 0) else 1

    cycles = 0
    print(f"corpus_poll loop: interval={args.interval}s  max_runs={args.max_runs}  "
          f"out={day_dir()}")
    while not _stop:
        one_cycle()
        cycles += 1
        if args.max_runs is not None and cycles >= args.max_runs:
            break
        # Sleep in small chunks so Ctrl-C is responsive.
        end_t = time.time() + args.interval
        while not _stop and time.time() < end_t:
            time.sleep(0.5)
    print(f"\ndone. cycles={cycles}  out={day_dir()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
