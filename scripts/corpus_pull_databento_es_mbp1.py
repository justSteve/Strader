#!/usr/bin/env python3
"""Corpus Databento GLBX ES.c.0 MBP-1 batch pull — one trading day. [st-9vl]

Historical batch pull of ES front-month top-of-book quotes (MBP-1: best
bid/ask with size, every book update) for one day. Writes one JSONL row per
book event to `data/corpus/YYYY-MM-DD/databento_glbx_es_mbp1.jsonl`.

This is the ONE approved metered MBP-1 purchase (Steve spend nod 2026-07-22,
~$4 scale) used to build and test AbsorptionRead refill_events logic offline
before the 8/1 Phase B live-capture flip (st-d5f). MBP-1 is otherwise never
backfilled — quotes are captured forward from the live tee once Phase B lands
(orderflow signal layer design §7).

Dataset:   GLBX.MDP3
Schema:    mbp-1
Symbols:   ["ES.c.0"]   (continuous front-month)
Stype_in:  continuous

Unlike the trades pull, each row carries the book state after the event:
bid/ask price, size, and order count at level 0, plus the triggering
action/side. Trade events (action="T") interleave with quote updates, which
is what lets absorption logic pair aggressive volume against passive refill.

Usage:
    .venv/bin/python scripts/corpus_pull_databento_es_mbp1.py \\
        --date 2026-07-02 --estimate-only
    .venv/bin/python scripts/corpus_pull_databento_es_mbp1.py --date 2026-07-02
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date, datetime, time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import databento_glbx_es_mbp1_path  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest, utc_now_iso  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def _load_env() -> None:
    """Validate DATABENTO_API_KEY via the shared fail-fast loader. [st-cir]"""
    from strader.settings import load_databento

    load_databento()


def _ct_to_utc(d: _date, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    local = datetime.combine(d, _time(h, m, 0), tzinfo=CENTRAL)
    return local.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Corpus Databento ES.c.0 MBP-1 pull — one date")
    parser.add_argument("--date", required=True,
                        help="Trading date in YYYY-MM-DD (US/Central)")
    parser.add_argument("--start-ct", default="08:30",
                        help="Window start in CT HH:MM (default 08:30 — RTH open)")
    parser.add_argument("--end-ct", default="15:00",
                        help="Window end in CT HH:MM (default 15:00 — RTH close)")
    parser.add_argument("--symbol", default="ES.c.0",
                        help="Continuous symbol (default ES.c.0 — front-month)")
    parser.add_argument("--dataset", default="GLBX.MDP3")
    parser.add_argument("--schema", default="mbp-1")
    parser.add_argument("--estimate-only", action="store_true",
                        help="Run metadata.get_cost only; do not pull data")
    args = parser.parse_args()

    _load_env()
    import databento as db  # noqa: E402
    client = db.Historical()

    d = _date.fromisoformat(args.date)
    start_utc = _ct_to_utc(d, args.start_ct)
    end_utc = _ct_to_utc(d, args.end_ct)

    print(f"# Databento ES MBP-1 corpus pull")
    print(f"  date           = {args.date}")
    print(f"  CT window      = {args.start_ct} - {args.end_ct}")
    print(f"  UTC window     = {start_utc.isoformat()} - {end_utc.isoformat()}")
    print(f"  dataset/schema = {args.dataset}/{args.schema}")
    print(f"  symbol         = {args.symbol}  (stype=continuous)")

    try:
        cost = client.metadata.get_cost(
            dataset=args.dataset, symbols=[args.symbol], schema=args.schema,
            stype_in="continuous", start=start_utc, end=end_utc,
        )
        print(f"  estimated cost = ${cost:.4f}")
    except Exception as e:
        print(f"  cost estimate ERR: {e}", file=sys.stderr)
        return 2

    if args.estimate_only:
        return 0

    print(f"  pulling...")
    try:
        store = client.timeseries.get_range(
            dataset=args.dataset, symbols=[args.symbol], schema=args.schema,
            stype_in="continuous", start=start_utc, end=end_utc,
        )
    except Exception as e:
        print(f"  pull ERR: {e}", file=sys.stderr)
        update_manifest(d=d, stream="databento_glbx_es_mbp1", errors=[str(e)])
        return 3

    try:
        df = store.to_df()
    except Exception as e:
        print(f"  to_df ERR: {e}", file=sys.stderr)
        update_manifest(d=d, stream="databento_glbx_es_mbp1", errors=[f"to_df: {e}"])
        return 3

    out = databento_glbx_es_mbp1_path(d=d)
    out.parent.mkdir(parents=True, exist_ok=True)
    tick_count = 0
    ts_pull = utc_now_iso()
    cols = set(df.columns)

    def _f(row, name):
        return float(row[name]) if name in cols and row[name] == row[name] else None

    def _i(row, name):
        return int(row[name]) if name in cols and row[name] == row[name] else None

    for _, row in df.iterrows():
        ts_event = row.get("ts_event") if "ts_event" in cols else row.name
        rec = {
            "ts_pull_utc": ts_pull,
            "stream": "databento_glbx_es_mbp1",
            "provenance": {
                "dataset": args.dataset,
                "schema": args.schema,
                "continuous_symbol": args.symbol,
                "ts_event": ts_event.isoformat() if hasattr(ts_event, "isoformat") else str(ts_event),
            },
            "data": {
                "symbol": row.get("symbol") if "symbol" in cols else None,
                "instrument_id": _i(row, "instrument_id"),
                "action": row.get("action") if "action" in cols else None,
                "side": row.get("side") if "side" in cols else None,
                "price": _f(row, "price"),
                "size": _i(row, "size"),
                "bid_px": _f(row, "bid_px_00"),
                "ask_px": _f(row, "ask_px_00"),
                "bid_sz": _i(row, "bid_sz_00"),
                "ask_sz": _i(row, "ask_sz_00"),
                "bid_ct": _i(row, "bid_ct_00"),
                "ask_ct": _i(row, "ask_ct_00"),
                "sequence": _i(row, "sequence"),
                "flags": _i(row, "flags"),
            },
        }
        append_jsonl(out, rec)
        tick_count += 1

    update_manifest(
        d=d, stream="databento_glbx_es_mbp1", increment_cycles=tick_count,
        note=f"one-shot MBP-1 pull {args.start_ct}-{args.end_ct} CT, {args.symbol} [st-9vl]",
    )
    print(f"  wrote {tick_count} book events -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
