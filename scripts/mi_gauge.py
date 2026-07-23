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

Replay default prints only non-neutral reads plus every band transition —
the pattern-learning view. --all prints every minute.
"""
from __future__ import annotations

import argparse
import sys
import time as time_mod
from datetime import date as _date, datetime, time as _time
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
    """Live path samples the QUOTE endpoint, not minute history: same-day
    minute candles clamp negatives to zero (see internals-tick-seed doc), but
    quotes return correct signed values. Samples aggregate into synthetic
    minutes fed to the same gauge.

    Honest caveat, printed at startup: a sampled minute's high/low only sees
    the prints we happened to catch, so wick extremes are understated versus
    true minute candles — live climax calls fire slightly late/less often
    than replay. Sample fast (default 5s ≈ 12/min, well inside rate limits)
    to shrink the gap."""
    from broker_schwab.client import create_client
    c = create_client()
    g = MIGauge()
    cur_min: datetime | None = None
    hi = lo = last = None
    print(f"# MI gauge live — sampling $TICK quotes every {poll_s}s; "
          "synthetic minutes (sampled wicks understate true extremes)")
    now_ct = datetime.now(tz=CENTRAL)
    if now_ct.time() > _time(8, 35):
        print("# NOTE: launched mid-session — the cum-TICK spine measures "
              "since LAUNCH, not since the 08:30 open (same-day history is "
              "clamped and cannot backfill it). Start the pane pre-open for "
              "full-session spine semantics; early cum reads run hot.")
    while True:
        try:
            r = c.get_quotes(["$TICK"])
            q = r.json().get("$TICK", {}).get("quote", {}) if r.status_code == 200 else {}
            px = q.get("lastPrice")
        except Exception as e:  # noqa: BLE001 — keep the pane alive
            print(f"  poll error: {e}", file=sys.stderr)
            px = None
        if px is not None:
            now = datetime.now(tz=CENTRAL)
            minute = now.replace(second=0, microsecond=0)
            if cur_min is None:
                cur_min, hi, lo, last = minute, px, px, px
            elif minute > cur_min:
                read = g.process(TickMinute(ts=cur_min, high=int(hi),
                                            low=int(lo), close=int(last)))
                if read is not None:
                    print(render(read), flush=True)
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
    args = ap.parse_args()
    if args.live:
        return live(args.poll)
    if not args.date:
        ap.error("--date required unless --live")
    return replay(_date.fromisoformat(args.date), args.all)


if __name__ == "__main__":
    sys.exit(main())
