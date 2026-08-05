"""GexBot-only corpus poller. [st-ox9x / st-p3lv]

Stopgap forward collector started at reactivation (2026-08-05) so GexBot
capture doesn't wait on the supervised service (st-p3lv). Same write path
as corpus_poll.py — append to data/corpus/<date>/gexbot.jsonl + manifest —
but polls only the GexBot leg, because Schwab/DataBento collection already
runs separately and double-writing schwab.jsonl would corrupt the corpus.

Backoff: after 5 consecutive failed cycles, sleep 5 min instead of the
normal interval (a lapsed key or API outage must not spin at 60s forever).
SIGINT/SIGTERM exit cleanly so tmux kills don't truncate a mid-write line.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.gexbot_stream import pull_cycle as gexbot_cycle  # noqa: E402
from market.corpus.paths import gexbot_path  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest  # noqa: E402

_stop = False


def _handle_stop(signum, frame):
    global _stop
    _stop = True
    print(f"\nsignal {signum} — finishing cycle then exiting", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="GexBot-only corpus poller")
    ap.add_argument("--interval", type=int, default=60,
                    help="Seconds between cycles (default 60)")
    ap.add_argument("--max-runs", type=int, default=None,
                    help="Stop after N cycles (default: indefinite)")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    runs = 0
    consecutive_failures = 0
    while not _stop:
        try:
            rec = gexbot_cycle()
            append_jsonl(gexbot_path(), rec)
            update_manifest(d=None, stream="gexbot", increment_cycles=1,
                            errors=len(rec["errors"]))
            s = rec["data"]["summary"]
            print(f"  [{rec['ts_pull_utc']}] gexbot  spot={s.get('spot_at_gamma_zero')}  "
                  f"bracket={s.get('major_negative')}-{s.get('major_positive')}  "
                  f"errs={len(rec['errors'])}", flush=True)
            consecutive_failures = consecutive_failures + 1 if rec["errors"] else 0
        except Exception as e:
            consecutive_failures += 1
            print(f"  gexbot CYCLE FAILED ({consecutive_failures} consecutive): "
                  f"{type(e).__name__}: {e}", file=sys.stderr, flush=True)
            update_manifest(d=None, stream="gexbot", increment_cycles=1, errors=1)

        runs += 1
        if args.max_runs is not None and runs >= args.max_runs:
            break
        sleep_s = 300 if consecutive_failures >= 5 else args.interval
        if consecutive_failures == 5:
            print("  5 consecutive failures — backing off to 5-min cycles",
                  file=sys.stderr, flush=True)
        for _ in range(sleep_s):
            if _stop:
                break
            time.sleep(1)

    print(f"stopped after {runs} cycles", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
