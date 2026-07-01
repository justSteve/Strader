#!/usr/bin/env python3
"""Corpus Databento GLBX ES.c.0 batch pull — one trading day. [st-xc9]

Historical batch pull of ES front-month continuous future trades for the
same late-day window the OPRA pull uses (default 13:00-15:00 CT). Writes
one JSONL row per trade tick to
`data/corpus/YYYY-MM-DD/databento_glbx_es.jsonl`.

Dataset:   GLBX.MDP3
Schema:    trades
Symbols:   ["ES.c.0"]   (continuous front-month, via continuous symbology)
Stype_in:  continuous

ES is the standard SPX proxy for measurement work — tracks SPX index
within ~0.25 pt during RTH. Used here to give the corpus a continuous
spot-price series that complements the OPRA option-trade ticks.

Cost (from earlier probe 2026-05-23): ~\$0.09 per 2-hour window. The
GLBX dataset is metered separately from OPRA (which is flat-fee under
the current subscription). A full 1-year backfill of late-day ES trades
runs ~\$25.

Usage:
    .venv/bin/python scripts/corpus_pull_databento_es.py --date 2026-05-21
    .venv/bin/python scripts/corpus_pull_databento_es.py --date 2026-05-21 \\
        --start-ct 13:00 --end-ct 15:00 --estimate-only
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date, datetime, time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import databento_glbx_es_path  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest, utc_now_iso  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def _load_env() -> None:
    """Validate DATABENTO_API_KEY and publish the clean value to os.environ so
    db.Historical() (which reads the key from the environment) sees the
    authoritative token. Routes through the shared fail-fast loader instead of
    an ad-hoc parse — the .env file wins over any polluted process env, and a
    malformed key fails loudly here rather than as an opaque API error
    (2026-06-30 invalid_client class of bug). [st-cir]"""
    from strader2.settings import load_databento

    load_databento()


def _ct_to_utc(d: _date, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    local = datetime.combine(d, _time(h, m, 0), tzinfo=CENTRAL)
    return local.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Corpus Databento ES.c.0 pull — one date")
    parser.add_argument("--date", required=True,
                        help="Trading date in YYYY-MM-DD (US/Central)")
    parser.add_argument("--start-ct", default="13:00",
                        help="Window start in CT HH:MM (default 13:00)")
    parser.add_argument("--end-ct", default="15:00",
                        help="Window end in CT HH:MM (default 15:00)")
    parser.add_argument("--symbol", default="ES.c.0",
                        help="Continuous symbol (default ES.c.0 — front-month)")
    parser.add_argument("--dataset", default="GLBX.MDP3")
    parser.add_argument("--schema", default="trades")
    parser.add_argument("--estimate-only", action="store_true",
                        help="Run metadata.get_cost only; do not pull data")
    args = parser.parse_args()

    _load_env()
    import databento as db  # noqa: E402
    client = db.Historical()

    d = _date.fromisoformat(args.date)
    start_utc = _ct_to_utc(d, args.start_ct)
    end_utc = _ct_to_utc(d, args.end_ct)

    print(f"# Databento ES corpus pull")
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
        update_manifest(d=d, stream="databento_glbx_es", errors=[str(e)])
        return 3

    try:
        df = store.to_df()
    except Exception as e:
        print(f"  to_df ERR: {e}", file=sys.stderr)
        update_manifest(d=d, stream="databento_glbx_es", errors=[f"to_df: {e}"])
        return 3

    out = databento_glbx_es_path(d=d)
    out.parent.mkdir(parents=True, exist_ok=True)
    tick_count = 0
    ts_pull = utc_now_iso()
    cols = set(df.columns)

    for _, row in df.iterrows():
        ts_event = row.get("ts_event") if "ts_event" in cols else row.name
        rec = {
            "ts_pull_utc": ts_pull,
            "stream": "databento_glbx_es",
            "provenance": {
                "dataset": args.dataset,
                "schema": args.schema,
                "continuous_symbol": args.symbol,
                "ts_event": ts_event.isoformat() if hasattr(ts_event, "isoformat") else str(ts_event),
            },
            "data": {
                "symbol": row.get("symbol") if "symbol" in cols else None,
                "instrument_id": int(row["instrument_id"]) if "instrument_id" in cols else None,
                "price": float(row["price"]) if "price" in cols else None,
                "size": int(row["size"]) if "size" in cols else None,
                "side": row.get("side") if "side" in cols else None,
                "action": row.get("action") if "action" in cols else None,
                "sequence": int(row["sequence"]) if "sequence" in cols else None,
                "flags": int(row["flags"]) if "flags" in cols else None,
            },
        }
        append_jsonl(out, rec)
        tick_count += 1

    update_manifest(
        d=d, stream="databento_glbx_es", increment_cycles=tick_count,
        note=f"batch pull {args.start_ct}-{args.end_ct} CT, {args.symbol}",
    )
    print(f"  wrote {tick_count} ticks -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
