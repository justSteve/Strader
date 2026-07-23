#!/usr/bin/env python3
"""Read-only: fetch price-history candles for given symbols. [st-3fr]

Probe/reader for the MI gauge data question: does Schwab serve intraday
candle history for internals symbols ($TICK, $ADD, $TRIN)? If yes, internals
calibration can be backfilled; if not, forward capture is the only source.

Usage:
    .venv/bin/python3 broker_schwab/readers/history.py '$TICK' --days 1
    .venv/bin/python3 broker_schwab/readers/history.py '$TICK' '$ADD' --days 30
    .venv/bin/python3 broker_schwab/readers/history.py '$TICK' --days 1 --json

Prints candle count, span, and head/tail samples per symbol — enough to judge
depth and granularity without dumping thousands of rows.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from broker_schwab.client import create_client

CENTRAL = ZoneInfo("America/Chicago")


def fmt(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(
        CENTRAL).strftime("%Y-%m-%d %H:%M CT")


def main():
    ap = argparse.ArgumentParser(description="Schwab price-history probe (read-only)")
    ap.add_argument("symbols", nargs="*", default=["$TICK"])
    ap.add_argument("--days", type=int, default=1,
                    help="how far back to request (default 1)")
    ap.add_argument("--json", action="store_true", help="dump raw response")
    args = ap.parse_args()

    c = create_client()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=args.days)

    for sym in args.symbols or ["$TICK"]:
        print(f"\n=== {sym}  (minute candles, {args.days}d back) ===")
        r = c.get_price_history_every_minute(
            sym, start_datetime=start, end_datetime=end,
            need_extended_hours_data=False,
        )
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}: {r.text[:300]}")
            continue
        data = r.json()
        candles = data.get("candles", [])
        if data.get("empty") or not candles:
            print(f"  EMPTY response (symbol={data.get('symbol')!r})")
            continue
        print(f"  candles: {len(candles)}")
        print(f"  span:    {fmt(candles[0]['datetime'])} -> {fmt(candles[-1]['datetime'])}")
        for c_ in candles[:3]:
            print(f"  head: {fmt(c_['datetime'])}  o={c_['open']} h={c_['high']} "
                  f"l={c_['low']} c={c_['close']} v={c_['volume']}")
        for c_ in candles[-3:]:
            print(f"  tail: {fmt(c_['datetime'])}  o={c_['open']} h={c_['high']} "
                  f"l={c_['low']} c={c_['close']} v={c_['volume']}")
        if args.json:
            print(json.dumps(data, indent=2)[:2000])


if __name__ == "__main__":
    main()
