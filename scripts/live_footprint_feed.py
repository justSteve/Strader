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
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import date as _date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import CORPUS_ROOT, central_date, gexbot_path, resolve_existing  # noqa: E402
from market.orderflow.anchors import LiveAnchors, mancini_levels_for  # noqa: E402
from market.orderflow.gex_context import GexContext                # noqa: E402
from market.orderflow.bars import build_bars                    # noqa: E402
from market.orderflow.fill import bar_fill_steps                # noqa: E402
from market.orderflow.parity import StackDriver, live_drive     # noqa: E402
from market.orderflow.replay import (                           # noqa: E402
    dedup_key, es_day_path, trade_from_row,
)
from market.orderflow.run_log import RunLogWriter, run_log_path  # noqa: E402
from market.signals.orderflow_config import TICK, VOLUME_BAR_N  # noqa: E402

logger = logging.getLogger("live_footprint_feed")

DEFAULT_BRIDGE = "http://127.0.0.1:7788"


# --------------------------------------------------------------------------
# Row source
# --------------------------------------------------------------------------

class StopFeed(Exception):
    """Raised from the SIGTERM handler so the drive loop's `finally` runs.

    Before 2026-08-16 the end-of-stream block — `driver.finish`, the run-log
    `end` record, the `final` push that puts the session's profile levels on
    the page — sat AFTER the for-loop, so it ran only when the tape ended by
    itself. On every live day the process was instead killed (reboot, OOM, a
    hand `kill`, tomorrow a `systemctl stop`) and `final` never landed: run
    logs 08-12/13/14 carry no `end` record. A SIGTERM now raises this, the
    loop finalises, and the process exits 0. [st-n0qm.1, plan §1]
    """


class DayRolledOver(RuntimeError):
    """The CT date advanced past the day this feeder was pinned to. [st-h510]"""


def tail_rows(path: Path, *, follow: bool, poll_s: float = 0.5,
              stop_after_idle_s: float | None = None,
              pinned_day: _date | None = None):
    """Yield parsed JSON rows from ``path``, optionally following appends.

    Waits for the file to appear (the streamer may not have written yet) and
    tolerates partial trailing lines: a row still being written is left in the
    buffer until its newline lands.

    ``pinned_day`` makes the follow loop fail loudly at the date boundary
    instead of quietly following a dead file [st-h510]. On 2026-08-13 this
    process ran 21.5 hours pinned to the previous day: the corpus file it was
    following stopped growing at that day's close, so it produced nothing while
    the bridge kept serving the previous session's bars behind a page that had
    re-rendered itself with today's date. Nothing on screen disagreed. An
    exception here is strictly better than that silence — a dead renderer is
    obvious, a renderer confidently showing the wrong day is not.
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
                    # Waiting for a file that has not appeared is the same idle
                    # state as following one that stopped growing: under a unit
                    # the feeder is started at any hour, and a Sunday start
                    # pinned to Sunday must roll to Monday rather than wait for
                    # a file that will never exist. [st-n0qm.3]
                    if pinned_day is not None and central_date() != pinned_day:
                        raise DayRolledOver(
                            f"CT date is {central_date()} but this feeder is pinned to "
                            f"{pinned_day}; {path} never appeared and now never will. "
                            f"Restart for the new day.")
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
            # Checked only when the tape is IDLE, which is the one state that
            # can persist across midnight. A day still printing is a day still
            # live, whatever the wall clock says. [st-h510]
            if pinned_day is not None and central_date() != pinned_day:
                raise DayRolledOver(
                    f"CT date is {central_date()} but this feeder is pinned to "
                    f"{pinned_day}; {path} cannot grow again. Restart the stack "
                    f"for the new day rather than leaving this one running.")
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


def bar_payload(bar, trades: list, events: list[dict] | None = None,
                *, include_steps: bool = True, gex: dict | None = None) -> dict:
    """Serialise a FootprintBar into the exact column shape the page renders.

    Key-for-key identical to orderflow_drill.bars_payload's per-bar dict —
    including ``steps``, so a live column animates the same way a drilled one
    does instead of popping in fully formed.

    ``ev`` carries the stack's emissions for this bar [st-b0n9]. It rides ON
    the bar rather than a second bridge channel because the page already holds
    bars in an indexed array and pushes them on close, so attaching keeps one
    ordering and one arrival: a bar and what it emitted can never be out of
    step or half-delivered. End-of-stream emissions (engine flush, profile
    levels) belong to no bar and go on the separate ``final`` channel instead.

    ``include_steps`` is off for the DEVELOPING bar [st-e91l]: fill steps exist
    to animate a bar that is already complete, and recomputing them once a
    second for a bar the tape is still writing is work whose output is
    immediately stale.

    ``gex`` is the dealer positioning that was published when this bar closed
    [st-8ywx]. The key is OMITTED rather than sent as null when there is no
    context — the feed is RTH-only and can be down, and an absent key reads as
    "not known" where ``"gex": null`` on every pre-open bar reads as a fault.
    """
    payload = {
        "t0": bar.start_ts.isoformat(), "t1": bar.end_ts.isoformat(),
        "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
        "v": bar.volume, "d": bar.delta, "nv": bar.none_vol,
        "dur": round(bar.duration_seconds, 3),
        "poc": bar.poc_price,
        "cells": [[c.price, c.bid_vol, c.ask_vol] for c in bar.cells],
        "steps": (bar_fill_steps(trades, [bar])[0]
                  if include_steps and trades else []),
        "ev": events or [],
    }
    if gex:
        payload["gex"] = gex
    return payload


def developing_payload(pending: list, bar_n: int) -> dict | None:
    """The bar the tape is CURRENTLY writing, as a display-only column. [st-e91l]

    ``build_bars(..., include_partial=True)`` over the trades accumulated since
    the last close yields exactly one under-``n`` bar — the same accumulator,
    the same cell construction and the same delta the closed bar will be built
    from, so a developing column cannot render differently from the bar it is
    about to become. Nothing here is reimplemented.

    DISPLAY ONLY, and that is the whole safety argument. This bar never enters
    the page's ``bars`` array, never drives ``StackDriver`` and never reaches
    the replay record. Feeding a partial bar to the recognizer would corrupt the
    engagement state it is measuring, and re-processing its trades through the
    engine would double-emit every signal — so it carries no emissions at all.
    The tape is re-read from the same pending list on every tick, which is cheap
    because the list never exceeds one bar of trades.
    """
    if not pending:
        return None
    bars = list(build_bars(iter(pending), n=bar_n, include_partial=True))
    if not bars:
        return None
    # Guard, not decoration: if the pending slice ever reached a full bar the
    # main loop would have closed it, so more than one bar here means the
    # tee/reclaim invariant broke and the newest is the only honest one.
    return bar_payload(bars[-1], [], include_steps=False)


# --------------------------------------------------------------------------
# Bridge
# --------------------------------------------------------------------------

def post_bars(bridge: str, bars: list[dict], meta: dict | None = None,
              final: list[dict] | None = None, developing: dict | None = None,
              *, timeout: float = 5.0) -> int | None:
    body = json.dumps({"bars": bars, "meta": meta, "final": final,
                       "developing": developing}).encode()
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


class _NullRunLog:
    """No-op stand-in so the main loop never branches on whether logging is on.
    A branch per bar is a branch that can be wrong; an object that does nothing
    cannot be."""
    path = None
    live = False

    def on_bar(self, *a, **k) -> None: ...
    def on_final(self, *a, **k) -> None: ...
    def close(self, **k) -> None: ...


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
    ap.add_argument("--mancini-levels",
                    help="comma-separated ES levels the recognizer watches; "
                         "default reads the day's parse (same rule as the page)")
    ap.add_argument("--developing-interval", type=float, default=1.0,
                    help="seconds between pushes of the DEVELOPING (still "
                         "forming) bar; 0 disables and the page shows closed "
                         "bars only, as it did before [st-e91l]")
    ap.add_argument("--no-gex", action="store_true",
                    help="do not stamp bars with GexBot dealer positioning "
                         "[st-8ywx]; the stamp is already a no-op when the "
                         "feed is absent, so this is for isolating it")
    ap.add_argument("--no-run-log", action="store_true",
                    help="do not record this run's bars and emissions to "
                         "data/derived/live-parity/<day>.jsonl [st-x2mp]. The "
                         "log is what scripts/live_parity_check.py diffs a "
                         "replay against, so a session run without it can "
                         "never be checked afterwards")
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

    # The full stack, driven live [st-b0n9]. StackDriver IS the pipeline
    # market/orderflow/parity.py defines — the same object the replay recorder
    # runs — so what the page shows is what a later replay of this tape
    # recomputes. Anchors: today's Mancini levels plus range edges that develop
    # with the session (LiveAnchors owns that rule and why it differs from the
    # replay's lookahead).
    if args.mancini_levels:
        mancini = [float(x) for x in args.mancini_levels.split(",") if x.strip()]
    else:
        try:
            mancini = mancini_levels_for(day)
        except Exception as e:  # noqa: BLE001 — no anchors must not stop the chart
            logger.warning("no Mancini levels for %s (%s) — range edges only", day, e)
            mancini = []
    live_anchors = LiveAnchors(mancini)
    driver = StackDriver(anchors=live_anchors.anchors, mancini_prices=mancini)
    live_anchors.attach(driver.recognizer)

    # meta carries the Mancini set only: the two range edges are placeholders
    # until the first bar seeds them, so publishing them at start would ship
    # 0.0 as a level the recognizer is watching.
    # Dealer positioning for each bar [st-8ywx]. Constructed unconditionally —
    # the reader resolves an absent or dead feed to None per bar, so a session
    # that starts pre-open picks GEX up mid-morning without a restart.
    gex = None if args.no_gex else GexContext(gexbot_path(day))

    meta = {"day": day.isoformat(), "bar_n": args.bar_n, "tick": TICK,
            "source": "live", "started": datetime.now().isoformat(timespec="seconds"),
            "mancini": mancini,
            "gex": bool(gex is not None and gexbot_path(day).exists())}

    # The diffable record of what this run emitted [st-x2mp]. Written for real
    # and catch-up runs alike (the mode is in the header, so the checker can
    # tell them apart); skipped for --dry-run, which posts nothing and is not
    # a session worth certifying.
    runlog = RunLogWriter(
        run_log_path(day), day=day, bar_n=args.bar_n, mancini=mancini,
        reorder_lag=args.reorder_lag, catch_up=bool(args.catch_up_only),
        started=datetime.now(),
    ) if not (args.no_run_log or args.dry_run) else _NullRunLog()

    logger.info("live footprint feed — day=%s bar_n=%d reorder_lag=%.1fs bridge=%s "
                "anchors=%d (%d mancini)",
                day, args.bar_n, args.reorder_lag,
                "(dry-run)" if args.dry_run else args.bridge,
                len(live_anchors.anchors), len(mancini))

    # Pin only when following TODAY. An explicit --date is a deliberate replay
    # of a past day and must not trip the rollover guard. [st-h510]
    rows = tail_rows(path, follow=not args.catch_up_only,
                     stop_after_idle_s=args.idle_stop,
                     pinned_day=None if args.date else day)
    trades = ordered_trades(rows, reorder_lag_s=args.reorder_lag)

    # Tee every trade so each closed bar can reclaim its own slice for the
    # intra-bar fill steps; build_bars otherwise swallows them.
    pending_trades: list = []

    # The developing bar is emitted from HERE, not the main loop [st-e91l].
    # The loop below blocks inside build_bars between closes — it only runs when
    # a bar completes — so the tee is the one place that sees the tape while a
    # bar is still forming. A wall-clock gate keeps it to one push per interval
    # however fast the prints arrive; single-threaded, no new concurrency.
    #
    # Suppressed during catch-up: replaying a finished day would emit a
    # developing bar per interval of WALL time while racing through hours of
    # tape, which is noise, and the last one would be left standing after the
    # run ends.
    dev_on = args.developing_interval > 0 and not args.catch_up_only and not args.dry_run
    last_dev = 0.0
    health_path = CORPUS_ROOT / day.isoformat() / "_footprint_health.json"
    feed_health = {"day": day.isoformat(), "pid": os.getpid(), "sent": 0,
                   "last_bar_t1": None, "developing_t": None, "final": 0}

    def _beat(**kw) -> None:
        if args.dry_run:
            return
        feed_health.update(kw)
        feed_health["written_utc"] = datetime.now().astimezone().isoformat(timespec="seconds")
        write_feed_health(health_path, feed_health)

    # Heartbeat while WAITING too: under the unit the feeder is up all night
    # waiting for the day's file, and a health file that only moves on a push
    # would read "dead" for every quiet hour. A daemon thread beats every 30 s
    # with whatever the counters say; the push path beats immediately.
    if not args.dry_run:
        import threading

        def _pulse() -> None:
            while True:
                time.sleep(30)
                _beat(state="following" if feed_health["sent"] or feed_health["developing_t"] else "waiting")
        threading.Thread(target=_pulse, name="feed-health", daemon=True).start()
        _beat(state="waiting")

    def _tee(it):
        nonlocal last_dev
        for t in it:
            pending_trades.append(t)
            if dev_on:
                now = time.monotonic()
                if now - last_dev >= args.developing_interval:
                    last_dev = now
                    payload = developing_payload(pending_trades, args.bar_n)
                    if payload is not None:
                        post_bars(args.bridge, [], None, None, payload)
                        _beat(developing_t=payload.get("t0"))
            yield t

    # The drive order (observe the bar into the developing range, THEN judge
    # it) lives in parity.live_drive so the parity checker replays through the
    # identical loop rather than a copy of it. [st-x2mp]
    def _closed_bars():
        for bar in build_bars(_tee(trades), n=args.bar_n):
            yield bar, take_bar_trades(bar, pending_trades)

    def _publish(batch: list[dict], meta_: dict | None, final: list | None) -> None:
        if args.dry_run:
            _log_batch(batch, 0)
            for e in final or ():
                logger.info("final: %s", e)
        else:
            post_bars(args.bridge, batch, meta_, final)
            _beat(sent=feed_health["sent"] + len(batch),
                  last_bar_t1=(batch[-1].get("t1") if batch else feed_health["last_bar_t1"]),
                  final=len(final or ()) or feed_health["final"])

    _install_stop_handler()
    drive_and_publish(live_drive(_closed_bars(), driver, live_anchors),
                      driver, pending_trades, runlog, _publish, meta=meta, gex=gex)
    return 0


def write_feed_health(path: Path, payload: dict) -> None:
    """The feeder's own liveness evidence — data/corpus/<day>/_footprint_health.json,
    rewritten atomically on every push (closed-bar batch or developing tick).
    The bridge's /health/producers reads its age; the page draws the dot.
    Never fatal: a chart that stops because its heartbeat could not be written
    would be the wrong trade. [st-n0qm.3]"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("feed health file unavailable (%s)", e)


def _install_stop_handler() -> None:
    """SIGTERM → StopFeed, so systemd stop / restart finalises the session
    instead of dropping it mid-bar. Only from the main thread (signal's rule);
    a test that calls drive_and_publish directly never needs this."""
    def _on_term(signum, _frame):
        raise StopFeed(f"signal {signum}")
    try:
        signal.signal(signal.SIGTERM, _on_term)
    except ValueError:  # not the main thread
        pass


def drive_and_publish(drive_iter, driver, pending_trades: list, runlog, publish,
                      *, meta: dict | None = None, gex=None,
                      push_every_s: float = 1.0, push_every_n: int = 25) -> dict:
    """Consume (bar_i, bar, bar_trades, events) from `drive_iter`, publish bars
    in coalesced batches, and — WHATEVER ends the stream — flush the engine and
    publish `final`. `publish(batch, meta_or_None, final_or_None)`.

    Ends: the tape finishing (catch-up), `--idle-stop`, StopFeed (SIGTERM) and
    KeyboardInterrupt all finalise and return; DayRolledOver finalises and
    re-raises so the exit is non-zero and the unit's Restart=on-failure brings
    up the new day. Any other exception finalises and re-raises too — a crash
    still leaves `final` and the run-log `end` behind it.

    Returns a summary dict {sent, n_ev, final, stopped_by}.
    """
    sent = 0
    batch: list[dict] = []
    last_push = time.monotonic()
    first = True
    n_ev = 0
    stopped_by = "end-of-stream"
    final: list = []
    try:
        for bar_i, bar, bar_trades, events in drive_iter:
            n_ev += len(events)
            runlog.on_bar(bar_i, bar, events)
            # Stamp AFTER the engine has judged the bar: the context is recorded
            # alongside recognition, never an input to it. Stage 1 changes no
            # recognition behaviour, and this ordering is what enforces that.
            gex_ctx = None
            if gex is not None:
                gex.refresh()
                gex_ctx = gex.for_bar(bar)
            batch.append(bar_payload(bar, bar_trades, events, gex=gex_ctx))
            now = time.monotonic()
            # Push promptly — a bar the page has not seen is a bar Steve is not
            # watching — but coalesce the catch-up burst so a full day does not
            # become hundreds of round trips.
            if len(batch) >= push_every_n or now - last_push >= push_every_s:
                publish(batch, meta if first else None, None)
                sent += len(batch)
                first = False
                batch = []
                last_push = now
    except (StopFeed, KeyboardInterrupt) as e:
        stopped_by = type(e).__name__
        logger.info("stopping (%s) — finalising the session", e or stopped_by)
    except DayRolledOver:
        stopped_by = "DayRolledOver"
        raise
    except Exception:
        stopped_by = "error"
        raise
    finally:
        # End of stream: engine flush + the session's profile levels. These
        # belong to no bar, so they ride the separate `final` channel rather
        # than being smuggled onto the last one. [st-b0n9]
        try:
            final = driver.finish(pending_trades)
        except Exception:  # noqa: BLE001 — a finish error must not eat the run log
            logger.exception("driver.finish failed; publishing without final")
            final = []
        n_ev += len(final)
        try:
            runlog.on_final(final)
        finally:
            runlog.close()
        if batch or final:
            publish(batch, meta if first else None, final or None)
            sent += len(batch)
        logger.info("done (%s) — %d bars, %d emissions (%d end-of-stream)%s",
                    stopped_by, sent, n_ev, len(final),
                    f"; run log {runlog.path}" if getattr(runlog, "live", False) else "")
    return {"sent": sent, "n_ev": n_ev, "final": final, "stopped_by": stopped_by}


def _log_batch(batch: list[dict], sent: int) -> None:
    for j, b in enumerate(batch, sent):
        logger.info("bar %d: o=%.2f h=%.2f l=%.2f c=%.2f v=%d d=%+d %.1fs "
                    "steps=%d ev=%d%s",
                    j, b["o"], b["h"], b["l"], b["c"], b["v"], b["d"], b["dur"],
                    len(b["steps"]), len(b["ev"]),
                    "  " + ", ".join(e["type"] for e in b["ev"]) if b["ev"] else "")


if __name__ == "__main__":
    sys.exit(main())
