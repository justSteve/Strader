"""Footprint read at named price levels, from the live ES tape. [st-flv4]

Reads the tail of today's databento_glbx_es.jsonl (live trades, aggressor on
every print: side 'B' = lifted the ask, 'A' = hit the bid — convention pinned
in market/orderflow/anchored_profile.py [st-6gs3]) and reports, for each level
of interest, the last-N-minutes interaction: prints, buy/sell aggressor volume,
delta, and whether price is currently engaging the level.

Read-only over local corpus files; no network, no Schwab.

Usage:
    .venv/bin/python scripts/level_interaction_read.py \
        --levels 7820,7799,7794,7767,7751,7744,7734,7726,7721 \
        --minutes 15 --band 2.0
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "data" / "corpus"
# Generous tail: ES rarely exceeds ~3k prints/min; 300 bytes/line, 10x margin.
TAIL_BYTES_PER_MIN = 3_000 * 300


def read_tail_records(path: Path, minutes: float) -> list[dict]:
    """Parse the last `minutes` of records from the live JSONL tail."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    size = path.stat().st_size
    want = min(size, int(TAIL_BYTES_PER_MIN * minutes))
    out: list[dict] = []
    with path.open("rb") as f:
        f.seek(size - want)
        if want < size:
            f.readline()  # discard partial first line
        for raw in f:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts = rec.get("ts_pull_utc") or ""
            try:
                when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if when < cutoff:
                continue
            d = rec.get("data") or {}
            if d.get("action") == "T" and d.get("price") is not None:
                out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", required=True,
                    help="comma-separated ES prices, e.g. 7799,7794,7744")
    ap.add_argument("--band", type=float, default=2.0,
                    help="half-width in points counted as 'at the level'")
    ap.add_argument("--minutes", type=float, default=15.0)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default today)")
    args = ap.parse_args()

    day = args.date or datetime.now().strftime("%Y-%m-%d")
    path = CORPUS / day / "databento_glbx_es.jsonl"
    if not path.exists():
        print(f"no live tape at {path}", file=sys.stderr)
        return 1

    trades = read_tail_records(path, args.minutes)
    if not trades:
        print(f"no trades parsed in the last {args.minutes:g} min "
              f"({path.stat().st_size} bytes on disk)", file=sys.stderr)
        return 2

    last = trades[-1]["price"]
    lo = min(t["price"] for t in trades)
    hi = max(t["price"] for t in trades)
    total_buy = sum(t["size"] for t in trades if t.get("side") == "B")
    total_sell = sum(t["size"] for t in trades if t.get("side") == "A")
    print(f"window last {args.minutes:g}m: {len(trades)} prints  "
          f"range {lo}-{hi}  last {last}  "
          f"delta {total_buy - total_sell:+d} (B {total_buy} / A {total_sell})")

    levels = sorted((float(x) for x in args.levels.split(",")), reverse=True)
    print(f"{'level':>8} {'dist':>7} {'prints':>7} {'buyV':>8} {'sellV':>8} "
          f"{'delta':>7}  note")
    for lv in levels:
        at = [t for t in trades if abs(t["price"] - lv) <= args.band]
        buy = sum(t["size"] for t in at if t.get("side") == "B")
        sell = sum(t["size"] for t in at if t.get("side") == "A")
        dist = last - lv
        if at:
            share = sum(t["size"] for t in at) / max(total_buy + total_sell, 1)
            note = "ENGAGED" if abs(dist) <= args.band else "touched"
            if share >= 0.35:
                note += " heavy"
        else:
            note = ""
        print(f"{lv:>8g} {dist:>+7.2f} {len(at):>7} {buy:>8} {sell:>8} "
              f"{buy - sell:>+7}  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
