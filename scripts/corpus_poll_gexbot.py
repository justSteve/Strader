"""GexBot corpus poller — session-gated. [st-ox9x / st-p3lv]

Forward collector for the GexBot leg. Same write path as corpus_poll.py —
append to data/corpus/<date>/gexbot.jsonl + manifest — but polls only GexBot,
because Schwab/DataBento collection already runs separately and double-writing
schwab.jsonl would corrupt the corpus.

SESSION GATE [st-p3lv]. Until 2026-08-09 this was a bare `--interval 60` loop
with no notion of a session at all. It ran Friday 2026-08-07 through 23:59 CT,
then all of Saturday 2026-08-08 — 1153 cycles, 58.4 MB of frozen weekend
snapshots — then died unattended at 01:30 Sunday. Two costs, and the second is
worse than the first: QUANT-tier request quota spent on a closed market, and
closed-market rows landing in the corpus wearing the same shape as session rows,
so nothing downstream can tell them apart. CurrentStatus.md claimed "Feed is
RTH-only" throughout. The claim is now true because of this gate.

The gate is HERE, in the process, not in the crontab or the supervisor wrapper.
A hand-run in a tmux pane is how this was started every day of its life, and a
gate that only exists in the scheduler does not protect that path.

    before the window   sleep until it opens (a few hours at most)
    inside the window   poll at --interval
    after the window    exit 0 — the supervisor owns tomorrow's start
    non-trading day     exit 0 immediately, having polled nothing

Backoff: after 5 consecutive failed cycles, sleep 5 min instead of the normal
interval (a lapsed key or API outage must not spin at 60s forever).
SIGINT/SIGTERM exit cleanly so tmux kills don't truncate a mid-write line.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.gexbot_stream import pull_cycle as gexbot_cycle  # noqa: E402
from market.corpus.paths import gexbot_path  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest  # noqa: E402
from strader.market_calendar import (  # noqa: E402
    CENTRAL,
    describe,
    window_state,
    year_is_known,
)

#: Default collect window, US/Central — MEASURED from the feed, not assumed.
#:
#: This constant opened at 07:30 for one day, "to give the pre-open ramp st-p3lv
#: asks for", on the stated belief that GexBot reprices off overnight
#: positioning before the cash open. That belief was wrong and was never
#: checked. The feed is RTH-only, which is what CurrentStatus.md had said all
#: along. Measured on 2026-08-07's own capture:
#:
#:     00:00-08:29 CT   spot_at_gamma_zero frozen at ONE value, 8 hours
#:     08:30:02 CT      first new value — the cash open, to the second
#:     08:30-15:00 CT   304 distinct values, ~76s cadence
#:     15:00:33 CT      last live update
#:     Sat 2026-08-08   1153 polls, ONE distinct value, all day
#:
#: So 07:30 bought nothing but ~60 duplicate rows every morning. 08:30 is the
#: first second the feed carries information.
#:
#: 15:05 is deliberate, not slack: the last live tick lands at 15:00:33, and the
#: five-minute tail costs four frozen rows while guaranteeing a slow cycle never
#: clips it.
#:
#: NOT COLLECTED, on purpose: two further updates land at ~16:08 and ~16:10 CT,
#: a post-close recompute. Two rows a day, meaning unverified. Worth measuring
#: before deciding whether they belong in the corpus — do NOT add a second
#: window on a guess, which is precisely the mistake this comment records.
DEFAULT_START_CT = "08:30"
DEFAULT_UNTIL_CT = "15:05"

_stop = False


def _handle_stop(signum, frame):
    global _stop
    _stop = True
    print(f"\nsignal {signum} — finishing cycle then exiting", file=sys.stderr)


def _sleep(seconds: float) -> None:
    """Sleep in 1-second slices so a signal is honoured within the second."""
    for _ in range(int(seconds)):
        if _stop:
            return
        time.sleep(1)


def _await_window(start_ct: str, until_ct: str) -> bool:
    """Block until the collect window is open. False means "stop, don't poll".

    Called before every cycle, so it also ends the run at the window's close —
    one clock check per minute, which is free next to a network round trip.
    """
    announced = False
    while not _stop:
        now = datetime.now(CENTRAL)
        state, resume_at = window_state(now, start_ct, until_ct)
        if state == "open":
            return True
        if state == "closed":
            print(f"  window closed — {describe(now.date())}; "
                  f"next session opens {resume_at:%Y-%m-%d %H:%M} CT. Exiting.",
                  flush=True)
            return False
        # "early": a trading day, before the window. Wait it out rather than
        # exiting, so a pane opened at 06:00 is collecting by 08:30 unattended.
        wait = (resume_at - now).total_seconds()
        if not announced:
            print(f"  before the window — sleeping {wait / 60:.0f} min until "
                  f"{resume_at:%H:%M} CT ({describe(now.date())})", flush=True)
            announced = True
        _sleep(max(1, min(wait, 60)))
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="GexBot corpus poller (session-gated)")
    ap.add_argument("--interval", type=int, default=60,
                    help="Seconds between cycles (default 60)")
    ap.add_argument("--max-runs", type=int, default=None,
                    help="Stop after N cycles (default: indefinite)")
    ap.add_argument("--start-ct", default=DEFAULT_START_CT,
                    help=f"Collect-window open, US/Central (default {DEFAULT_START_CT})")
    ap.add_argument("--until-ct", default=DEFAULT_UNTIL_CT,
                    help=f"Collect-window close, US/Central (default {DEFAULT_UNTIL_CT}); "
                         "clamped automatically on early-close sessions")
    ap.add_argument("--all-hours", action="store_true",
                    help="Disable the session gate entirely. For backfill and "
                         "debugging only — this is what burned a Saturday of "
                         "QUANT quota on 2026-08-08.")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    if args.all_hours:
        print("  --all-hours: session gate DISABLED, polling around the clock.",
              file=sys.stderr, flush=True)
    elif not year_is_known(datetime.now(CENTRAL).date()):
        print("  WARN: no holiday table for this year in strader/market_calendar.py "
              "— falling back to weekday-only gating. Extend HOLIDAYS/EARLY_CLOSES.",
              file=sys.stderr, flush=True)

    runs = 0
    consecutive_failures = 0
    while not _stop:
        if not args.all_hours and not _await_window(args.start_ct, args.until_ct):
            break
        try:
            rec = gexbot_cycle()
            append_jsonl(gexbot_path(), rec)
            update_manifest(d=None, stream="gexbot", increment_cycles=1,
                            errors=rec["errors"] or None)
            s = rec["data"]["summary"]
            one = (f"  1dte={s.get('one_major_negative')}-{s.get('one_major_positive')}"
                   if s.get("one_major_positive") is not None else "")
            print(f"  [{rec['ts_pull_utc']}] gexbot  spot={s.get('spot_at_gamma_zero')}  "
                  f"bracket={s.get('major_negative')}-{s.get('major_positive')}{one}  "
                  f"errs={len(rec['errors'])}", flush=True)
            consecutive_failures = consecutive_failures + 1 if rec["errors"] else 0
        except Exception as e:
            consecutive_failures += 1
            print(f"  gexbot CYCLE FAILED ({consecutive_failures} consecutive): "
                  f"{type(e).__name__}: {e}", file=sys.stderr, flush=True)
            try:
                update_manifest(d=None, stream="gexbot", increment_cycles=1,
                                errors=[f"{type(e).__name__}: {e}"])
            except Exception as me:
                # Manifest bookkeeping must never kill the collector.
                print(f"  manifest update failed too: {me}", file=sys.stderr, flush=True)

        runs += 1
        if args.max_runs is not None and runs >= args.max_runs:
            break
        sleep_s = 300 if consecutive_failures >= 5 else args.interval
        if consecutive_failures == 5:
            print("  5 consecutive failures — backing off to 5-min cycles",
                  file=sys.stderr, flush=True)
        _sleep(sleep_s)

    print(f"stopped after {runs} cycles", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
