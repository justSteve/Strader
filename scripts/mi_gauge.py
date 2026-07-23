#!/usr/bin/env python3
"""MI gauge CLI — replay a corpus day or watch the live tape. [st-3fr]

Replay (deterministic, from the internals corpus):
    .venv/bin/python scripts/mi_gauge.py --date 2026-07-22
    .venv/bin/python scripts/mi_gauge.py --date 2026-07-22 --all   # every minute

Live (polls Schwab $TICK minute history every --poll seconds; designed to sit
in a tmux pane):
    .venv/bin/python scripts/mi_gauge.py --live
    tmux -L moocity new-window -n gauge \\
        '.venv/bin/python scripts/mi_gauge.py --live'

Replay default prints only non-neutral reads plus every band transition —
the pattern-learning view. --all prints every minute.
"""
from __future__ import annotations

import argparse
import sys
import time as time_mod
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.internals.feed import read_tick_day          # noqa: E402
from market.internals.gauge import MIGauge, TickMinute   # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")

BAR = {"climax": "█", "lean": "▒", "neutral": "·"}


def render(r) -> str:
    mag = min(20, abs(r.score) // 5)
    side = ("+" if r.score >= 0 else "-") * 0
    bar = BAR[r.band] * mag
    lane = f"{bar:>20}|" if r.score < 0 else f"{'':>20}|{bar}"
    return (f"{r.timestamp.strftime('%H:%M')}  {r.score:+4d} {lane:<41} "
            f"{r.driver:<18} wick {r.tick_high:+5d}/{r.tick_low:+5d}  "
            f"cum {r.cum_tick:+7d}")


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


def live(poll_s: int) -> int:
    # Live path constructs TickMinute rows from the Schwab minute-history
    # endpoint — same data the corpus stores, same gauge, live==replay.
    from broker_schwab.client import create_client
    c = create_client()
    g = MIGauge()
    seen: set[datetime] = set()
    print("# MI gauge live — polling $TICK minute history "
          f"every {poll_s}s (Ctrl-C to stop)")
    while True:
        end = datetime.now(tz=timezone.utc)
        r = c.get_price_history_every_minute(
            "$TICK", start_datetime=end - timedelta(hours=8),
            end_datetime=end, need_extended_hours_data=False,
        )
        if r.status_code == 200 and not r.json().get("empty"):
            for cd in r.json().get("candles", []):
                ts = datetime.fromtimestamp(
                    cd["datetime"] / 1000, tz=timezone.utc).astimezone(CENTRAL)
                if ts in seen:
                    continue
                seen.add(ts)
                read = g.process(TickMinute(
                    ts=ts, high=int(cd["high"]), low=int(cd["low"]),
                    close=int(cd["close"])))
                if read is not None:
                    print(render(read), flush=True)
        else:
            print(f"  poll error HTTP {r.status_code}", file=sys.stderr)
        time_mod.sleep(poll_s)


def main() -> int:
    ap = argparse.ArgumentParser(description="MI gauge — replay or live")
    ap.add_argument("--date", help="replay this corpus day (YYYY-MM-DD)")
    ap.add_argument("--all", action="store_true",
                    help="replay: print every minute, not just non-neutral")
    ap.add_argument("--live", action="store_true",
                    help="poll Schwab live and stream reads")
    ap.add_argument("--poll", type=int, default=60,
                    help="live poll interval seconds (default 60)")
    args = ap.parse_args()
    if args.live:
        return live(args.poll)
    if not args.date:
        ap.error("--date required unless --live")
    return replay(_date.fromisoformat(args.date), args.all)


if __name__ == "__main__":
    sys.exit(main())
