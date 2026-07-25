#!/usr/bin/env python3
"""MI gauge CLI — replay a corpus day or watch the live tape. [st-3fr]

Replay (deterministic, from the internals corpus):
    .venv/bin/python scripts/mi_gauge.py --date 2026-07-22
    .venv/bin/python scripts/mi_gauge.py --date 2026-07-22 --all   # every minute

Live (samples the Schwab $TICK QUOTE endpoint — same-day minute-history
candles clamp negatives to zero, quotes are correct — and aggregates samples
into synthetic minutes; designed to sit in a tmux pane):
    .venv/bin/python scripts/mi_gauge.py --live
    tmux -L moocity new-window -n gauge \\
        '.venv/bin/python scripts/mi_gauge.py --live'

Live exits at 15:15 CT and on a day rollover (--session-end HH:MM | none) —
it is a session daemon, not a service.

Replay default prints only non-neutral reads plus every band transition —
the pattern-learning view. --all prints every minute.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time as time_mod
from datetime import date as _date, datetime, time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.internals.feed import read_tick_day          # noqa: E402
from market.internals.gauge import MIGauge, TickMinute   # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
REPO_ROOT = Path(__file__).resolve().parent.parent

# Live gauge stops here (CT). 15:15 = cash close 15:00 plus a settle-print tail;
# past it the tape is closed and every further "minute" is a flat repeat of the
# last print. Before st-5n8 the loop had NO stop condition at all: the 7/24
# launch ran 26h, wrote 1269 dead rows past the close, and spilled Saturday's
# rows into Friday's capture file. Overridable per-run (--session-end) or by
# environment (STRADER_GAUGE_SESSION_END), which is how the cron wrapper keeps
# its own no-respawn window and the gauge's self-exit on the same number.
SESSION_END_DEFAULT = "15:15"

BAR = {"climax": "█", "lean": "▒", "neutral": "·"}


def render(r) -> str:
    mag = min(20, abs(r.score) // 5)
    side = ("+" if r.score >= 0 else "-") * 0
    bar = BAR[r.band] * mag
    lane = f"{bar:>20}|" if r.score < 0 else f"{'':>20}|{bar}"
    return (f"{r.timestamp.strftime('%H:%M')}  {r.score:+4d} {lane:<41} "
            f"{r.driver:<18} wick {r.tick_high:+5d}/{r.tick_low:+5d}  "
            f"cum {r.cum_tick:+7d}")


# ---------------------------------------------------------------------------
# Live-capture / state-restore.
#
# The gauge is a deterministic pure function of its tick stream, so we do NOT
# checkpoint its internal fields. We capture every synthetic minute we feed it
# to a durable per-day jsonl; on (re)launch we REPLAY that file through a fresh
# gauge to reconstruct the exact spine, then resume live. Replay reproduces
# identical state by construction (the same parity discipline as --date).
#
# This is what makes a mid-session respawn useful instead of a cum=0 reset that
# runs hot. The captured stream is also the forward internals sample st-3fr
# wants, co-located with the batch corpus for the day.
# ---------------------------------------------------------------------------

def default_capture_path(day: _date) -> Path:
    return REPO_ROOT / "data" / "corpus" / day.isoformat() / "mi_gauge_live.jsonl"


def parse_session_end(raw: str | None) -> _time | None:
    """'15:15' → time(15,15); 'none'/'off'/'' → None (run until killed)."""
    if raw is None:
        return None
    s = raw.strip().lower()
    if s in ("", "none", "off", "never"):
        return None
    hh, _, mm = s.partition(":")
    return _time(int(hh), int(mm or 0))


def stop_reason(now: datetime, capture_day: _date,
                session_end: _time | None) -> str | None:
    """Why the live loop must stop, or None to keep running. [st-5n8]

    'rollover' is checked first and is the harder stop: the capture day is
    fixed at launch, so a process that outlives midnight would keep appending
    to the PREVIOUS day's file. A fresh launch owns the new day.
    """
    if now.date() != capture_day:
        return "rollover"
    if session_end is not None and now.time() >= session_end:
        return "session-end"
    return None


def append_capture(path: Path, m: TickMinute, day: _date | None = None) -> bool:
    """Append one processed minute; returns True if written. Flushed +
    fsync-free line write; a kill mid-write can only truncate the FINAL line,
    which restore tolerates.

    When `day` is given the write is REFUSED for a minute from any other day
    [st-5n8] — the last line of defence against a long-lived process folding
    tomorrow's rows into today's capture. restore_state() already filters on
    read; this stops the bad row from being written at all.
    """
    if day is not None and m.ts.date() != day:
        return False
    rec = {"ts": m.ts.isoformat(), "high": m.high, "low": m.low, "close": m.close}
    with path.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return True


def restore_state(path: Path, gauge: MIGauge, day: _date,
                  echo: bool = True) -> datetime | None:
    """Replay a capture file for `day` through `gauge`. Returns the last
    restored minute ts (None if nothing restored). Tolerates a truncated final
    line. Skips records not dated `day` (stale file under a reused path)."""
    if not path.exists():
        return None
    last_ts: datetime | None = None
    restored = 0
    prev_band = "neutral"
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec["ts"])
            m = TickMinute(ts=ts, high=int(rec["high"]),
                           low=int(rec["low"]), close=int(rec["close"]))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue  # truncated/corrupt final line — stop-safe, just skip
        if m.ts.date() != day:
            continue
        r = gauge.process(m)
        last_ts = m.ts
        restored += 1
        if echo and r is not None:
            transition = r.band != prev_band
            prev_band = r.band
            if r.band != "neutral" or transition:
                print(render(r))
    if restored:
        print(f"# restored {restored} captured minute(s) from {path.name} — "
              f"cum {gauge.cum_tick:+d} over {gauge.minutes}m through "
              f"{last_ts.strftime('%H:%M') if last_ts else '??'}; spine continues",
              flush=True)
    return last_ts


def replay(day: _date, show_all: bool) -> int:
    minutes = read_tick_day(day)
    if not minutes:
        print(f"no $TICK minutes for {day}", file=sys.stderr)
        return 1
    g = MIGauge()
    prev_band = "neutral"
    shown = 0
    print(f"# MI gauge replay — {day}  ({len(minutes)} minutes)")
    for m in minutes:
        r = g.process(m)
        if r is None:
            continue
        transition = r.band != prev_band
        prev_band = r.band
        if show_all or r.band != "neutral" or transition:
            print(render(r))
            shown += 1
    print(f"# {shown} reads shown")
    return 0


def live(poll_s: int, capture: Path | None,
         session_end: _time | None = None,
         capture_day: _date | None = None) -> int:
    """Live path samples the QUOTE endpoint, not minute history: same-day
    minute candles clamp negatives to zero (see internals-tick-seed doc), but
    quotes return correct signed values. Samples aggregate into synthetic
    minutes fed to the same gauge.

    Honest caveat, printed at startup: a sampled minute's high/low only sees
    the prints we happened to catch, so wick extremes are understated versus
    true minute candles — live climax calls fire slightly late/less often
    than replay. Sample fast (default 5s ≈ 12/min, well inside rate limits)
    to shrink the gap.

    Durability: unless capture is None, every processed minute is appended to
    the capture file, and on startup any existing capture for today is replayed
    to restore the spine — so a mid-session respawn continues rather than
    resetting to cum=0. Minutes elapsed while the process was DOWN are lost
    (same-day $TICK history is clamped and cannot backfill), so the restore
    banner names the gap when one is detected.

    Lifetime [st-5n8]: the loop stops at `session_end` (CT) and on a day
    rollover. Both are evaluated BEFORE the broker client is built, so a launch
    outside the window costs nothing and touches no API — which is what lets the
    cron wrapper stay a dumb heartbeat."""
    if capture_day is None:
        capture_day = datetime.now(tz=CENTRAL).date()

    reason = stop_reason(datetime.now(tz=CENTRAL), capture_day, session_end)
    if reason == "session-end":
        print(f"# past session end {session_end.strftime('%H:%M')} CT — "
              "not starting a live gauge (nothing to measure on a closed tape).")
        return 0
    if reason == "rollover":
        print(f"# capture day {capture_day} is not today — not starting a live gauge.")
        return 0

    from broker_schwab.client import create_client
    c = create_client()
    g = MIGauge()
    cur_min: datetime | None = None
    hi = lo = last = None
    print(f"# MI gauge live — sampling $TICK quotes every {poll_s}s; "
          "synthetic minutes (sampled wicks understate true extremes)")

    restored_ts: datetime | None = None
    if capture is not None:
        capture.parent.mkdir(parents=True, exist_ok=True)
        restored_ts = restore_state(capture, g, capture_day)
        print(f"# capturing to {capture}", flush=True)

    now_ct = datetime.now(tz=CENTRAL)
    if restored_ts is not None:
        gap_min = int((now_ct - restored_ts).total_seconds() // 60) - 1
        if gap_min >= 1:
            print(f"# [gap] {gap_min} minute(s) of downtime since last capture "
                  f"({restored_ts.strftime('%H:%M')}) — those closes are lost "
                  "(same-day $TICK is clamped); spine has a hole there.",
                  flush=True)
    elif now_ct.time() > _time(8, 35):
        print("# NOTE: launched mid-session with no capture to restore — the "
              "cum-TICK spine measures since LAUNCH, not since the 08:30 open "
              "(same-day history is clamped and cannot backfill it). Start the "
              "pane pre-open for full-session spine semantics; early cum reads "
              "run hot.")

    if session_end is not None:
        print(f"# exits at {session_end.strftime('%H:%M')} CT "
              "(--session-end none to run until killed)", flush=True)

    def commit_minute(ts, h, l, c_):
        """Process one completed synthetic minute, unless it duplicates a
        restored one (fast crash+respawn inside the same minute)."""
        if restored_ts is not None and ts <= restored_ts:
            return
        read = g.process(TickMinute(ts=ts, high=int(h), low=int(l), close=int(c_)))
        if capture is not None:
            m = TickMinute(ts=ts, high=int(h), low=int(l), close=int(c_))
            if not append_capture(capture, m, day=capture_day):
                print(f"  [guard] refused to write a {ts.date()} minute into "
                      f"the {capture_day} capture file", file=sys.stderr,
                      flush=True)
        if read is not None:
            print(render(read), flush=True)

    while True:
        now = datetime.now(tz=CENTRAL)

        # --- stop conditions, checked every tick of the loop ---------------
        reason = stop_reason(now, capture_day, session_end)
        if reason is not None:
            # Flush the minute in progress only if it belongs to the window we
            # are closing out; anything past the boundary is not ours to write.
            if cur_min is not None and cur_min.date() == capture_day and (
                    session_end is None or cur_min.time() < session_end):
                commit_minute(cur_min, hi, lo, last)
            if reason == "rollover":
                print(f"# day rolled over ({capture_day} → {now.date()}) — "
                      "exiting; a fresh launch owns the new day's capture.",
                      flush=True)
            else:
                print(f"# session end {session_end.strftime('%H:%M')} CT — "
                      f"exiting cleanly ({g.minutes}m captured, "
                      f"cum {g.cum_tick:+d}).", flush=True)
            return 0

        try:
            r = c.get_quotes(["$TICK"])
            q = r.json().get("$TICK", {}).get("quote", {}) if r.status_code == 200 else {}
            px = q.get("lastPrice")
        except Exception as e:  # noqa: BLE001 — keep the pane alive
            print(f"  poll error: {e}", file=sys.stderr)
            px = None
        if px is not None:
            minute = now.replace(second=0, microsecond=0)
            if cur_min is None:
                cur_min, hi, lo, last = minute, px, px, px
            elif minute > cur_min:
                commit_minute(cur_min, hi, lo, last)
                cur_min, hi, lo, last = minute, px, px, px
            else:
                hi, lo, last = max(hi, px), min(lo, px), px
        time_mod.sleep(poll_s)


def main() -> int:
    ap = argparse.ArgumentParser(description="MI gauge — replay or live")
    ap.add_argument("--date", help="replay this corpus day (YYYY-MM-DD)")
    ap.add_argument("--all", action="store_true",
                    help="replay: print every minute, not just non-neutral")
    ap.add_argument("--live", action="store_true",
                    help="poll Schwab live and stream reads")
    ap.add_argument("--poll", type=int, default=5,
                    help="live quote-sample interval seconds (default 5)")
    ap.add_argument("--capture", metavar="PATH",
                    help="live: capture/restore file (default: "
                         "data/corpus/<today>/mi_gauge_live.jsonl)")
    ap.add_argument("--no-capture", action="store_true",
                    help="live: disable durable capture + restore")
    ap.add_argument("--session-end", metavar="HH:MM",
                    default=os.environ.get("STRADER_GAUGE_SESSION_END",
                                           SESSION_END_DEFAULT),
                    help="live: exit at this CT time (default "
                         f"{SESSION_END_DEFAULT}; 'none' runs until killed)")
    args = ap.parse_args()
    if args.live:
        today = datetime.now(tz=CENTRAL).date()
        if args.no_capture:
            capture = None
        elif args.capture:
            capture = Path(args.capture)
        else:
            capture = default_capture_path(today)
        try:
            session_end = parse_session_end(args.session_end)
        except ValueError:
            ap.error(f"--session-end: expected HH:MM or 'none', got {args.session_end!r}")
        return live(args.poll, capture, session_end=session_end, capture_day=today)
    if not args.date:
        ap.error("--date required unless --live")
    return replay(_date.fromisoformat(args.date), args.all)


if __name__ == "__main__":
    sys.exit(main())
