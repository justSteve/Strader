#!/usr/bin/env python3
"""Live footprint feeder — corpus tail -> volume bars -> drill bridge. [st-re1o]

The last link in Phase B: turns the drills-only footprint surface into a live
one. It tails the JSONL that ``corpus_stream_databento.py`` is appending during
the session, builds the same volume bars the replay path builds, and POSTs each
closed bar to ``drill_bridge`` for the page to append.

WHY TAIL A FILE INSTEAD OF SHARING THE FEED
    Capture is the irreplaceable half — live trades and MBP-1 are never
    backfilled, so a session lost is lost at any price. Rendering is not: the
    corpus makes the whole day replayable after the close. Tailing keeps those
    failure modes independent. This process can crash, be restarted, or be
    started late without the streamer noticing, and nothing about capture
    depends on the browser being open.

PARITY IS PRESERVED BY CONSTRUCTION
    Rows are parsed with ``replay.trade_from_row`` and deduped with
    ``replay.dedup_key`` — the same helpers ``read_corpus_day`` uses — then fed
    to the same ``build_bars``. A live bar is therefore the bar the replay would
    produce from the same rows, which is the spec §5 guarantee the parity
    harness (st-bw9) pins in CI. Nothing here reimplements the engine.

ORDERING
    ``build_bars`` raises on out-of-order trades, and Databento guarantees order
    only WITHIN a connection — a reconnect can redeliver or interleave. So rows
    pass through a small time-ordered buffer: hold everything newer than
    ``--reorder-lag`` seconds, release the rest in (ts, sequence) order. The lag
    is latency added to every bar, so keep it small; 2s absorbs a reconnect
    without being visible against a bar that takes 30-60s to form.

Usage:
    # Follow today's ES tape, push bars to a bridge on the default port
    .venv/bin/python scripts/live_footprint_feed.py

    # Replay a finished day through the same path at speed (no waiting)
    .venv/bin/python scripts/live_footprint_feed.py --date 2026-07-31 --catch-up-only

    # Sanity check without a bridge running
    .venv/bin/python scripts/live_footprint_feed.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import date as _date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import central_date, resolve_existing  # noqa: E402
from market.orderflow.bars import build_bars                    # noqa: E402
from market.orderflow.fill import bar_fill_steps                # noqa: E402
from market.orderflow.replay import (                           # noqa: E402
    dedup_key, es_day_path, trade_from_row,
)
from market.signals.orderflow_config import TICK, VOLUME_BAR_N  # noqa: E402

logger = logging.getLogger("live_footprint_feed")

DEFAULT_BRIDGE = "http://127.0.0.1:7788"


# --------------------------------------------------------------------------
# Row source
# --------------------------------------------------------------------------

def tail_rows(path: Path, *, follow: bool, poll_s: float = 0.5,
              stop_after_idle_s: float | None = None):
    """Yield parsed JSON rows from ``path``, optionally following appends.

    Waits for the file to appear (the streamer may not have written yet) and
    tolerates partial trailing lines: a row still being written is left in the
    buffer until its newline lands.
    """
    buf = ""
    fh = None
    idle_since = None
    # A compacted day is a finished day: it cannot grow, so following it would
    # spin forever. Catch up over it and stop. (This bites the moment the
    # compaction cron has run over the day you are replaying.)
    if path.suffix == ".gz":
        follow = False
    try:
        while True:
            if fh is None:
                if path.exists():
                    if path.suffix == ".gz":
                        import gzip
                        fh = gzip.open(path, "rt", encoding="utf-8")
                    else:
                        fh = path.open("r", encoding="utf-8")
                    logger.info("reading %s%s", path, "" if follow is False else " (following)")
                elif not follow:
                    return
                else:
                    time.sleep(poll_s)
                    continue

            chunk = fh.read()
            if chunk:
                idle_since = None
                buf += chunk
                *lines, buf = buf.split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.warning("skipping unparseable line: %s", e)
                continue

            if not follow:
                return
            now = time.monotonic()
            idle_since = idle_since or now
            if stop_after_idle_s is not None and now - idle_since >= stop_after_idle_s:
                logger.info("idle %.0fs — stopping", now - idle_since)
                return
            time.sleep(poll_s)
    finally:
        if fh is not None:
            fh.close()


def ordered_trades(rows, *, reorder_lag_s: float, flush_at_end: bool = True):
    """Parse rows and release trades in canonical order. [st-re1o]

    Holds a buffer of parsed trades and releases those whose event time is
    older than ``reorder_lag_s`` behind the newest seen, sorted by (ts,
    sequence). Duplicates — which a reconnect will redeliver — are dropped on
    ``dedup_key``. This is what keeps ``build_bars`` from raising mid-session.
    """
    pending: list[tuple[datetime, int, object]] = []
    seen: set[tuple] = set()
    newest: datetime | None = None
    dupes = bad = 0

    def _drain(cutoff):
        pending.sort(key=lambda t: (t[0], t[1]))
        keep = []
        for item in pending:
            if cutoff is None or item[0] <= cutoff:
                yield item[2]
            else:
                keep.append(item)
        pending[:] = keep

    for row in rows:
        try:
            key = dedup_key(row)
            if key in seen:
                dupes += 1
                continue
            seen.add(key)
            parsed = trade_from_row(row)
        except (KeyError, TypeError, ValueError) as e:
            bad += 1
            logger.warning("unparseable row (%s) — skipped", e)
            continue

        pending.append(parsed)
        ts = parsed[0]
        newest = ts if newest is None or ts > newest else newest
        cutoff = newest - _timedelta_seconds(reorder_lag_s)
        yield from _drain(cutoff)

    if flush_at_end:
        yield from _drain(None)
    if dupes or bad:
        logger.info("feeder: %d duplicate rows dropped, %d bad rows", dupes, bad)


def _timedelta_seconds(s: float):
    from datetime import timedelta
    return timedelta(seconds=s)


# --------------------------------------------------------------------------
# Bar serialisation — the shape the drill page already renders
# --------------------------------------------------------------------------

def take_bar_trades(bar, buf: list) -> list:
    """Pop the trades belonging to ``bar`` off the front of ``buf``.

    build_bars consumes the trade iterator internally, so the feeder tees every
    trade into ``buf`` and reclaims each bar's slice here — same positional walk
    and same straddle convention bar_fill_steps uses, so the slice it gets is
    the slice the drill would have handed it.
    """
    vol = k = 0
    while k < len(buf) and vol < bar.volume:
        vol += buf[k].size
        k += 1
    taken, buf[:] = buf[:k], buf[k:]
    return taken


def bar_payload(bar, trades: list) -> dict:
    """Serialise a FootprintBar into the exact column shape the page renders.

    Key-for-key identical to orderflow_drill.bars_payload's per-bar dict —
    including ``steps``, so a live column animates the same way a drilled one
    does instead of popping in fully formed.
    """
    return {
        "t0": bar.start_ts.isoformat(), "t1": bar.end_ts.isoformat(),
        "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
        "v": bar.volume, "d": bar.delta, "nv": bar.none_vol,
        "dur": round(bar.duration_seconds, 3),
        "poc": bar.poc_price,
        "cells": [[c.price, c.bid_vol, c.ask_vol] for c in bar.cells],
        "steps": bar_fill_steps(trades, [bar])[0] if trades else [],
    }


# --------------------------------------------------------------------------
# Bridge
# --------------------------------------------------------------------------

def post_bars(bridge: str, bars: list[dict], meta: dict | None = None,
              *, timeout: float = 5.0) -> int | None:
    body = json.dumps({"bars": bars, "meta": meta}).encode()
    req = urllib.request.Request(f"{bridge}/bars", data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("total")
    except (urllib.error.URLError, OSError, ValueError) as e:
        # Never fatal: the bridge being down must not stop the feeder, because
        # the feeder stopping is how you notice at 14:55 that you have no chart.
        logger.warning("bridge push failed (%s) — continuing", e)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="corpus day YYYY-MM-DD (default: today CT)")
    ap.add_argument("--bridge", default=DEFAULT_BRIDGE)
    ap.add_argument("--bar-n", type=int, default=VOLUME_BAR_N,
                    help=f"contracts per volume bar (default {VOLUME_BAR_N})")
    ap.add_argument("--reorder-lag", type=float, default=2.0,
                    help="seconds of event-time buffer absorbing reconnect "
                         "disorder (default 2.0)")
    ap.add_argument("--catch-up-only", action="store_true",
                    help="process what is already on disk and exit — the way to "
                         "replay a finished day through the live path")
    ap.add_argument("--idle-stop", type=float, default=None,
                    help="stop after N seconds with no new rows")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and log bars, post nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date) if args.date else central_date()
    path = es_day_path(day)
    resolved = resolve_existing(path)
    if resolved is None and args.catch_up_only:
        print(f"[FAIL] no ES corpus file for {day} at {path}", file=sys.stderr)
        return 1
    if resolved is not None:
        path = resolved

    meta = {"day": day.isoformat(), "bar_n": args.bar_n, "tick": TICK,
            "source": "live", "started": datetime.now().isoformat(timespec="seconds")}

    logger.info("live footprint feed — day=%s bar_n=%d reorder_lag=%.1fs bridge=%s",
                day, args.bar_n, args.reorder_lag, "(dry-run)" if args.dry_run else args.bridge)

    rows = tail_rows(path, follow=not args.catch_up_only,
                     stop_after_idle_s=args.idle_stop)
    trades = ordered_trades(rows, reorder_lag_s=args.reorder_lag)

    # Tee every trade so each closed bar can reclaim its own slice for the
    # intra-bar fill steps; build_bars otherwise swallows them.
    pending_trades: list = []

    def _tee(it):
        for t in it:
            pending_trades.append(t)
            yield t

    sent = 0
    batch: list[dict] = []
    last_push = time.monotonic()
    first = True
    for bar in build_bars(_tee(trades), n=args.bar_n):
        batch.append(bar_payload(bar, take_bar_trades(bar, pending_trades)))
        now = time.monotonic()
        # Push promptly — a bar the page has not seen is a bar Steve is not
        # watching — but coalesce the catch-up burst so a full day does not
        # become hundreds of round trips.
        if len(batch) >= 25 or now - last_push >= 1.0:
            if args.dry_run:
                for j, b in enumerate(batch, sent):
                    logger.info("bar %d: o=%.2f h=%.2f l=%.2f c=%.2f v=%d d=%+d "
                                "%.1fs steps=%d",
                                j, b["o"], b["h"], b["l"], b["c"], b["v"],
                                b["d"], b["dur"], len(b["steps"]))
            else:
                post_bars(args.bridge, batch, meta if first else None)
            sent += len(batch)
            first = False
            batch = []
            last_push = now

    if batch:
        if args.dry_run:
            for j, b in enumerate(batch, sent):
                logger.info("bar %d: o=%.2f h=%.2f l=%.2f c=%.2f v=%d d=%+d "
                            "%.1fs steps=%d",
                            j, b["o"], b["h"], b["l"], b["c"], b["v"],
                            b["d"], b["dur"], len(b["steps"]))
        else:
            post_bars(args.bridge, batch, meta if first else None)
        sent += len(batch)

    logger.info("done — %d bars", sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
