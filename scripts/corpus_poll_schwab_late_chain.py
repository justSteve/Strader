#!/usr/bin/env python3
"""Schwab LAST-HOUR chain leg — the 0DTE window every 30s, 14:00-15:01 CT. [st-9dyz]

WHY THIS EXISTS. Steve, 2026-08-26: late-day singletons are a priority for
his account — "the lack of loss in the last 30 minutes makes the way out of
delta worth watching." The corpus cannot show him that. The Schwab stream is
four stage snapshots a day (premarket / open / afternoon / close-watch), so a
late-day single's mark path exists only in his eye: today's 7685P was 10.10
at 13:44, ~2.10 at 14:30 with SPX ~7,687, 2.45 at 14:45 with SPX 7,684.6 and
~6.5 at 14:56 with SPX 7,678.5 — three of those four numbers are from memory.
This leg turns that into rows.

WHAT IT DOES. Every ``--interval`` seconds inside the window it runs the same
``pull_cycle`` the stage cron runs — quotes for $SPX and /ES plus the ±10-strike
0DTE chain window with bid/ask/mark/iv/delta per row — stamps the record
``stage="late-chain"`` and appends it to ``data/corpus/<today>/schwab_late_chain.jsonl``.
Separate file from ``schwab.jsonl`` on purpose: consumers of the four-snapshot
stream must not suddenly see 120 rows a day.

REST, NOT STREAMER. Same reasoning as scripts/cron/schwab-stages-wrapper.sh:
each cycle is two REST GETs (quotes, chain) — no streamer session, so it can
never collide with Steve's ToS login. 120 cycles an hour is 240 requests,
against Schwab's documented 120 requests/minute.

SESSION GATE IN-PROCESS, weekdays only, window ``--start-ct``..``--until-ct``.
Started early it waits; started late it exits 0 with a line saying so. The
gate lives here rather than in the scheduler because hand-run panes are how
collectors actually get started (corpus_poll_gexbot.py doctrine).

FAILURE SURFACE. ``pull_cycle`` never raises; it returns ``errors``. Five
consecutive error cycles back off ``--failure-backoff`` seconds. An
auth-shaped error (401/403/token) is loud and exits non-zero at once — a lapsed
token is a live failure, not something to retry through.

THE SCHWAB GATE. This file imports ``market.corpus.schwab_stream``, which
reaches the Schwab client, so ``schwab-gate.sh`` blocks the agent from running
it. Steve runs it (``./scripts/run.sh scripts/corpus_poll_schwab_late_chain.py``)
or installs the cron line below. The import is deferred into ``run()`` so the
window and loop logic are unit-testable with a fake ``pull_cycle`` and no
client.

Cron (America/Chicago, alongside the four stage lines in schwab-stages-wrapper.sh):
    58 13 * * 1-5 cd /root/projects/Strader && .venv/bin/python scripts/corpus_poll_schwab_late_chain.py >> /var/moo/logs/schwab-stages/late-chain-$(date +\\%F).log 2>&1

Usage:
    .venv/bin/python scripts/corpus_poll_schwab_late_chain.py            # wait for 14:00, poll to 15:01
    .venv/bin/python scripts/corpus_poll_schwab_late_chain.py --once     # one cycle now, any time (smoke)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, time as _time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import CENTRAL, schwab_late_chain_path  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest  # noqa: E402

logger = logging.getLogger("schwab_late_chain")

STAGE = "late-chain"
STREAM = "schwab_late_chain"
DEFAULT_START_CT = "14:00"
DEFAULT_UNTIL_CT = "15:01"      # one cycle past the 15:00 settle catches the last mark
DEFAULT_INTERVAL_S = 30.0
FAILURE_BACKOFF_S = 300
FAILURE_BACKOFF_AFTER = 5
MANIFEST_BATCH = 10
AUTH_MARKERS = ("401", "403", "token", "unauthor", "forbidden")


def parse_hhmm(s: str) -> _time:
    h, m = s.split(":")
    return _time(int(h), int(m))


def window_state(now: datetime, start: _time, until: _time) -> str:
    """'before' | 'open' | 'after' | 'weekend' for a Central-aware ``now``."""
    now = now.astimezone(CENTRAL)
    if now.weekday() >= 5:
        return "weekend"
    t = now.time()
    if t < start:
        return "before"
    if t >= until:
        return "after"
    return "open"


def seconds_until(now: datetime, start: _time) -> float:
    now = now.astimezone(CENTRAL)
    target = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    return max(0.0, (target - now).total_seconds())


def is_auth_error(errors: list[str]) -> bool:
    joined = " ".join(errors).lower()
    return any(m in joined for m in AUTH_MARKERS)


def run(
    *,
    pull: Callable[[str], dict],
    symbol: str = "$SPX",
    start: _time,
    until: _time,
    interval: float = DEFAULT_INTERVAL_S,
    once: bool = False,
    now_fn: Callable[[], datetime] = lambda: datetime.now(CENTRAL),
    sleep_fn: Callable[[float], None] = time.sleep,
    out_path: Callable[[], Path] = schwab_late_chain_path,
) -> int:
    """The loop. Returns a process exit code. Every dependency is injectable so
    the window/backoff logic is testable without a Schwab client."""
    if once:
        rec = pull(symbol)
        rec["stage"] = STAGE
        append_jsonl(out_path(), rec)
        update_manifest(d=None, stream=STREAM, increment_cycles=1, errors=rec["errors"] or None)
        logger.info("once: spx=%s es=%s errors=%d -> %s", rec["data"].get("spot_spx"),
                    rec["data"].get("spot_es"), len(rec["errors"]), out_path())
        return 2 if is_auth_error(rec["errors"]) else 0

    state = window_state(now_fn(), start, until)
    if state == "weekend":
        logger.info("weekend — nothing to poll; exit 0")
        return 0
    if state == "after":
        logger.info("started after %s CT — window closed; exit 0", until.strftime("%H:%M"))
        return 0
    if state == "before":
        wait = seconds_until(now_fn(), start)
        logger.info("waiting %.0fs for the %s CT window", wait, start.strftime("%H:%M"))
        sleep_fn(wait)

    cycles = 0
    consecutive_failures = 0
    pending_manifest = 0
    logger.info("late-chain leg open: %s..%s CT every %.0fs -> %s",
                start.strftime("%H:%M"), until.strftime("%H:%M"), interval, out_path())
    while window_state(now_fn(), start, until) == "open":
        t0 = now_fn()
        rec = pull(symbol)
        rec["stage"] = STAGE
        append_jsonl(out_path(), rec)
        cycles += 1
        pending_manifest += 1
        if rec["errors"]:
            consecutive_failures += 1
            logger.warning("cycle %d errors: %s", cycles, "; ".join(rec["errors"])[:300])
            if is_auth_error(rec["errors"]):
                update_manifest(d=None, stream=STREAM, increment_cycles=pending_manifest,
                                errors=rec["errors"], note="late-chain: auth failure, exited")
                logger.error("[ALERT] Schwab auth error on the late-chain leg — exiting; "
                             "token needs Steve")
                return 2
        else:
            consecutive_failures = 0
        if pending_manifest >= MANIFEST_BATCH:
            update_manifest(d=None, stream=STREAM, increment_cycles=pending_manifest,
                            errors=rec["errors"] or None)
            pending_manifest = 0
        if consecutive_failures >= FAILURE_BACKOFF_AFTER:
            logger.warning("%d consecutive failures — backing off %ds",
                           consecutive_failures, FAILURE_BACKOFF_S)
            sleep_fn(FAILURE_BACKOFF_S)
            consecutive_failures = 0
            continue
        elapsed = (now_fn() - t0).total_seconds()
        sleep_fn(max(0.0, interval - elapsed))

    if pending_manifest:
        update_manifest(d=None, stream=STREAM, increment_cycles=pending_manifest,
                        note=f"late-chain: {cycles} cycles")
    logger.info("window closed after %d cycles -> %s", cycles, out_path())
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Schwab last-hour 0DTE chain leg (30s, 14:00-15:01 CT)")
    ap.add_argument("--symbol", default="$SPX")
    ap.add_argument("--start-ct", default=DEFAULT_START_CT)
    ap.add_argument("--until-ct", default=DEFAULT_UNTIL_CT)
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S,
                    help="seconds from cycle start to cycle start (default 30)")
    ap.add_argument("--once", action="store_true", help="one cycle now, ignore the window (smoke)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # Deferred: this is the Schwab reach. Tests inject a fake and never import it.
    from market.corpus.schwab_stream import pull_cycle  # noqa: E402

    return run(pull=pull_cycle, symbol=args.symbol, start=parse_hhmm(args.start_ct),
               until=parse_hhmm(args.until_ct), interval=args.interval, once=args.once)


if __name__ == "__main__":
    sys.exit(main())
