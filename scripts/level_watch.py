#!/root/projects/Strader/.venv/bin/python3
"""Watch for volume EXPANDING below a line, and exit the moment it does. [st-8ywx]

The distinction this exists to catch: sellers thinning out as they approach a
level (the 08:33 sweep at 7741 — three contracts at the low) versus sellers
bringing size through it. Both look like "price is near the level" on a chart.
Only the second one is a breakdown.

Tails the day's ES tape and holds a rolling window of prints strictly BELOW a
price line. Exits 0 and prints a report the first time that window's volume
crosses a threshold, so a caller can simply wait on the process rather than
poll. Exits 2 on timeout with no trigger — a real answer, not a failure.

    scripts/level_watch.py --below 7752 --trigger-vol 900 --minutes 120

Deliberately NOT a signal generator and NOT an order path: it reports that
participation changed, which is the thing a human cannot watch continuously
and a tape can. What that means is the reader's call.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import central_date  # noqa: E402
from market.orderflow.replay import es_day_path, trade_from_row  # noqa: E402

CT = ZoneInfo("America/Chicago")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--below", type=float, required=True,
                    help="the line; only prints strictly below it are counted")
    ap.add_argument("--window", type=float, default=180.0,
                    help="rolling window in seconds (default 180)")
    ap.add_argument("--trigger-vol", type=int, default=900,
                    help="contracts below the line within the window that "
                         "constitutes expansion (default 900)")
    ap.add_argument("--hard", type=float, default=None,
                    help="also trigger immediately if price trades at or "
                         "below this with size >= --hard-size")
    ap.add_argument("--hard-size", type=int, default=50)
    ap.add_argument("--minutes", type=float, default=120.0,
                    help="give up after this long (default 120)")
    ap.add_argument("--status-every", type=float, default=60.0,
                    help="seconds between progress lines (default 60)")
    ap.add_argument("--date")
    args = ap.parse_args()

    day = _date.fromisoformat(args.date) if args.date else central_date()
    path = es_day_path(day)
    if not path.exists():
        print(f"[FAIL] no ES tape at {path}", flush=True)
        return 1

    deadline = time.monotonic() + args.minutes * 60
    win: deque = deque()          # (ts, size, side) strictly below the line
    vol = 0
    last_status = 0.0
    peak = 0

    fh = path.open("r", encoding="utf-8")
    fh.seek(0, 2)                 # only what happens from NOW
    print(f"watching below {args.below:g} — expansion = {args.trigger_vol} "
          f"contracts in {args.window:g}s   (started "
          f"{datetime.now(CT):%H:%M:%S} CT)", flush=True)

    while True:
        if time.monotonic() > deadline:
            print(f"[NO TRIGGER] {args.minutes:g} min elapsed; peak "
                  f"{peak} contracts in a {args.window:g}s window "
                  f"(needed {args.trigger_vol})", flush=True)
            return 2

        line = fh.readline()
        if not line:
            time.sleep(0.25)
            continue
        if not line.endswith("\n"):
            fh.seek(fh.tell() - len(line))
            time.sleep(0.25)
            continue
        try:
            ts, _seq, t = trade_from_row(json.loads(line))
        except Exception:
            continue

        px, size = float(t.price), int(t.size)
        side = getattr(t, "side", "N")

        if args.hard is not None and px <= args.hard and size >= args.hard_size:
            print(f"[TRIGGER-HARD] {ts:%H:%M:%S} CT  {size} contracts at "
                  f"{px:g} (<= {args.hard:g})", flush=True)
            return 0

        if px < args.below:
            win.append((ts, size, side))
            vol += size

        cutoff = ts.timestamp() - args.window
        while win and win[0][0].timestamp() < cutoff:
            vol -= win.popleft()[1]
        peak = max(peak, vol)

        if vol >= args.trigger_vol:
            sell = sum(s for _, s, sd in win if sd == "A")
            buy = sum(s for _, s, sd in win if sd == "B")
            lo = min(float(args.below), px)
            print(f"[TRIGGER] {ts:%H:%M:%S} CT — {vol} contracts below "
                  f"{args.below:g} in {args.window:g}s "
                  f"(threshold {args.trigger_vol})", flush=True)
            print(f"  sell-agg {sell}  buy-agg {buy}  delta {buy - sell:+d}",
                  flush=True)
            print(f"  last print {px:g}  window low {lo:g}", flush=True)
            print("  volume is EXPANDING below the line — this is the thing "
                  "the 7741 sweep never did.", flush=True)
            return 0

        now = time.monotonic()
        if now - last_status >= args.status_every:
            last_status = now
            print(f"  {ts:%H:%M:%S} last={px:g}  below-line {vol}/"
                  f"{args.trigger_vol} in window  (peak {peak})", flush=True)


if __name__ == "__main__":
    sys.exit(main())
