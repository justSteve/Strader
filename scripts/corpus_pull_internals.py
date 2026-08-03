#!/usr/bin/env python3
"""Corpus pull: NYSE market internals minute candles via Schwab. [st-3fr]

Fetches $TICK / $TRIN / $ADD / $VOLD / $VIX minute candles from Schwab price
history and writes them into the per-day corpus
(`data/corpus/YYYY-MM-DD/internals.jsonl`, one row per symbol-minute).
Schwab's minute history is a ROLLING ~47-day window — running this weekly
makes the history permanent before it rolls off.

$VIX added 2026-08-03 [st-cdwe]; $VIX9D/$VIX3M [st-40fv] and $VVIX
[st-lru8] added same day for term-structure and vol-of-vol reads. Index symbols are bare (`$VIX` —
`$VIX.X` returns EMPTY), serve ~389 RTH minute candles/day with v=0 (indices
— volume is meaningless). Rows before the add dates carry fewer symbols.

Idempotent by day: a day whose file already exists is skipped, EXCEPT the
current session day, which is always rewritten (it may have been partial on
the previous run). One API call per symbol covers the whole range.

Usage:
    .venv/bin/python scripts/corpus_pull_internals.py              # last 45 days
    .venv/bin/python scripts/corpus_pull_internals.py --days 10
    .venv/bin/python scripts/corpus_pull_internals.py --force      # rewrite all
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker_schwab.client import create_client  # noqa: E402
from market.corpus.paths import central_date, internals_path  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest, utc_now_iso  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
SYMBOLS = ("$TICK", "$TRIN", "$ADD", "$VOLD", "$VIX", "$VIX9D", "$VIX3M", "$VVIX")


def fetch_symbol(client, symbol: str, days: int) -> list[dict]:
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
    r = client.get_price_history_every_minute(
        symbol, start_datetime=start, end_datetime=end,
        need_extended_hours_data=False,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{symbol}: HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    if data.get("empty"):
        return []
    return data.get("candles", [])


def main() -> int:
    ap = argparse.ArgumentParser(description="Corpus internals pull (Schwab minute candles)")
    ap.add_argument("--days", type=int, default=45,
                    help="how far back to request (default 45; Schwab wall ~47)")
    ap.add_argument("--force", action="store_true",
                    help="rewrite existing day files instead of skipping them")
    args = ap.parse_args()

    client = create_client()
    ts_pull = utc_now_iso()
    today = central_date()

    # day -> list of (symbol, candle) in fetch order
    by_day: dict = defaultdict(list)
    counts: dict[str, int] = {}
    for sym in SYMBOLS:
        try:
            candles = fetch_symbol(client, sym, args.days)
        except RuntimeError as e:
            print(f"  {e}", file=sys.stderr)
            counts[sym] = -1
            continue
        counts[sym] = len(candles)
        # Schwab serves the just-settled day TWICE in one response: the healed
        # (negative-capable) segment first, then the stale same-day clamped
        # segment (lows/closes floored at 0). First-wins dedup keeps the
        # healed series (observed 2026-07-23, st-3fr).
        seen: set = set()
        for c in candles:
            ts = datetime.fromtimestamp(c["datetime"] / 1000,
                                        tz=timezone.utc).astimezone(CENTRAL)
            if (sym, ts) in seen:
                continue
            seen.add((sym, ts))
            by_day[ts.date()].append((sym, ts, c))

    print("# internals corpus pull")
    for sym in SYMBOLS:
        n = counts.get(sym)
        print(f"  {sym:6s} candles={'ERR' if n == -1 else n}")

    written = skipped = 0
    for day in sorted(by_day):
        out = internals_path(day)
        if out.exists() and not args.force and day != today:
            skipped += 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()  # rewrite atomically-enough: full day always re-emitted
        rows = 0
        for sym, ts, c in by_day[day]:
            append_jsonl(out, {
                "ts_pull_utc": ts_pull,
                "stream": "schwab_internals",
                "provenance": {"symbol": sym, "ts_candle": ts.isoformat()},
                "data": {
                    "symbol": sym,
                    "open": c.get("open"), "high": c.get("high"),
                    "low": c.get("low"), "close": c.get("close"),
                },
            })
            rows += 1
        update_manifest(d=day, stream="schwab_internals", increment_cycles=rows,
                        note=f"internals minute candles ({rows} rows)")
        written += 1
    print(f"  days written={written} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
