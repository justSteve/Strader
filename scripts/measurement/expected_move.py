#!/usr/bin/env python3
"""Compute the options-implied expected move (ATM straddle VWAP) for each corpus day.

Method:
  1. Find ES spot price at 13:00 CT (first trade at/after 18:00 UTC CDT, 19:00 UTC CST)
  2. Find nearest $5 SPXW strike to spot
  3. Collect 0DTE put and call trades at that strike in [13:00, 13:10) CT
  4. Volume-weighted average price for each leg
  5. Straddle = put VWAP + call VWAP = expected move in index points

Output: data/measurement/expected_move.jsonl — one JSON line per day.

Usage:
    .venv/bin/python scripts/measurement/expected_move.py
    .venv/bin/python scripts/measurement/expected_move.py --dry-run --limit 5
    .venv/bin/python scripts/measurement/expected_move.py --start-date 2025-08-01

[st-745]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date as _date, datetime, time as _time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")

PROJECT_ROOT = Path("/root/projects/Strader")
CORPUS_DIR = PROJECT_ROOT / "data" / "corpus"
OUTPUT_PATH = PROJECT_ROOT / "data" / "measurement" / "expected_move.jsonl"

# Window: [13:00, 13:10) CT
WINDOW_MINUTES = 10

# SPXW strikes are at $5 intervals for liquid 0DTE
STRIKE_INTERVAL = 5


def get_ts_event_iso(provenance: dict) -> str | None:
    """Extract ts_event as ISO string, handling both string and nanosecond formats."""
    if "ts_event" in provenance:
        return provenance["ts_event"]
    if "ts_event_ns" in provenance:
        ns = provenance["ts_event_ns"]
        dt = datetime.fromtimestamp(ns / 1e9, tz=UTC)
        return dt.isoformat()
    return None


def date_to_utc_window(d: _date) -> tuple[datetime, datetime]:
    """Convert 13:00 CT and 13:10 CT on the given date to UTC datetimes."""
    start_ct = datetime.combine(d, _time(13, 0), tzinfo=CENTRAL)
    end_ct = datetime.combine(d, _time(13, 10), tzinfo=CENTRAL)
    return start_ct.astimezone(UTC), end_ct.astimezone(UTC)


def nearest_strike_5(spot: float) -> int:
    """Round spot to nearest $5 strike."""
    return int(round(spot / STRIKE_INTERVAL) * STRIKE_INTERVAL)


def parse_opra_symbol(symbol: str) -> tuple[str, _date, str, float] | None:
    """Parse OCC option symbol into (root, expiry_date, put_or_call, strike).

    Format: 'SPXW  YYMMDD{P|C}SSSSSSS0'
    Root is 6 chars (padded), date is 6 chars, type is 1 char, strike is 8 chars.
    Total = 21 chars.
    """
    if not symbol or len(symbol) != 21:
        return None
    root = symbol[:6].strip()
    if root != "SPXW":
        return None
    try:
        yy = int(symbol[6:8])
        mm = int(symbol[8:10])
        dd = int(symbol[10:12])
        expiry = _date(2000 + yy, mm, dd)
    except (ValueError, IndexError):
        return None
    pc = symbol[12]
    if pc not in ("P", "C"):
        return None
    try:
        strike_raw = int(symbol[13:21])
        strike = strike_raw / 1000.0
    except (ValueError, IndexError):
        return None
    return (root, expiry, pc, strike)


def get_spot_at_reference(es_path: Path, ref_utc: datetime) -> float | None:
    """Get ES spot price from first trade at or after reference time (VWAP of first second)."""
    ref_iso = ref_utc.isoformat()
    one_sec_later = (ref_utc + timedelta(seconds=1)).isoformat()

    prices_sizes: list[tuple[float, int]] = []
    with es_path.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_event = get_ts_event_iso(rec["provenance"])
            if ts_event is None:
                continue
            if ts_event < ref_iso:
                continue
            if ts_event >= one_sec_later:
                break
            prices_sizes.append((rec["data"]["price"], rec["data"]["size"]))

    if not prices_sizes:
        # Fallback: just first trade at or after ref
        with es_path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_event = get_ts_event_iso(rec["provenance"])
                if ts_event and ts_event >= ref_iso:
                    return rec["data"]["price"]
        return None

    # Volume-weighted price over that first second
    total_value = sum(p * s for p, s in prices_sizes)
    total_size = sum(s for _, s in prices_sizes)
    return total_value / total_size if total_size > 0 else prices_sizes[0][0]


def compute_expected_move(d: _date, es_path: Path, opra_path: Path) -> dict | None:
    """Compute expected move for a single day using VWAP of ATM straddle."""
    ref_utc, window_end_utc = date_to_utc_window(d)

    # Step 1: Get spot at reference time
    spot = get_spot_at_reference(es_path, ref_utc)
    if spot is None:
        return None

    # Step 2: Determine ATM strike (nearest $5 interval)
    atm_strike = nearest_strike_5(spot)

    # Step 3: Collect 0DTE put and call trades at ATM strike in [13:00, 13:10) CT
    ref_iso = ref_utc.isoformat()
    window_end_iso = window_end_utc.isoformat()

    # Accumulate volume-weighted data: list of (price, size)
    put_trades: list[tuple[float, int]] = []
    call_trades: list[tuple[float, int]] = []

    with opra_path.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_event = get_ts_event_iso(rec["provenance"])
            if ts_event is None:
                continue
            if ts_event < ref_iso:
                continue
            if ts_event >= window_end_iso:
                break  # OPRA data is time-ordered

            parsed = parse_opra_symbol(rec["data"]["symbol"])
            if parsed is None:
                continue

            root, expiry, pc, strike = parsed

            # Must be 0DTE (expiry matches trade date)
            if expiry != d:
                continue

            # Must be at ATM strike
            if strike != atm_strike:
                continue

            price = rec["data"]["price"]
            size = rec["data"]["size"]

            if pc == "P":
                put_trades.append((price, size))
            else:
                call_trades.append((price, size))

    # If no trades at exact ATM, try adjacent strikes (+/- $5)
    if not put_trades or not call_trades:
        adj_put_trades: list[tuple[float, int]] = []
        adj_call_trades: list[tuple[float, int]] = []

        with opra_path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_event = get_ts_event_iso(rec["provenance"])
                if ts_event is None:
                    continue
                if ts_event < ref_iso:
                    continue
                if ts_event >= window_end_iso:
                    break
                parsed = parse_opra_symbol(rec["data"]["symbol"])
                if parsed is None:
                    continue
                root, expiry, pc, strike = parsed
                if expiry != d:
                    continue
                if abs(strike - atm_strike) > STRIKE_INTERVAL:
                    continue
                price = rec["data"]["price"]
                size = rec["data"]["size"]
                if pc == "P":
                    adj_put_trades.append((price, size))
                else:
                    adj_call_trades.append((price, size))

        if not put_trades:
            put_trades = adj_put_trades
        if not call_trades:
            call_trades = adj_call_trades

    if not put_trades or not call_trades:
        return None

    # Compute VWAP for each leg
    put_value = sum(p * s for p, s in put_trades)
    put_volume = sum(s for _, s in put_trades)
    put_vwap = put_value / put_volume

    call_value = sum(p * s for p, s in call_trades)
    call_volume = sum(s for _, s in call_trades)
    call_vwap = call_value / call_volume

    straddle = put_vwap + call_vwap

    return {
        "date": d.isoformat(),
        "spot_ref": round(spot, 2),
        "atm_strike": atm_strike,
        "put_vwap": round(put_vwap, 2),
        "call_vwap": round(call_vwap, 2),
        "straddle_price": round(straddle, 2),
        "expected_move_pts": round(straddle, 2),
        "n_put_trades": len(put_trades),
        "n_call_trades": len(call_trades),
    }


def main():
    parser = argparse.ArgumentParser(description="Compute expected move from OPRA straddle VWAP")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing file")
    parser.add_argument("--limit", type=int, default=0, help="Process only N days (0=all)")
    parser.add_argument("--start-date", type=str, default=None, help="Start from this date (YYYY-MM-DD)")
    args = parser.parse_args()

    corpus_dates = sorted(p.name for p in CORPUS_DIR.iterdir() if p.is_dir())
    if args.start_date:
        corpus_dates = [d for d in corpus_dates if d >= args.start_date]
    if args.limit:
        corpus_dates = corpus_dates[:args.limit]

    results: list[dict] = []
    skipped = 0

    print(f"Processing {len(corpus_dates)} corpus days...", file=sys.stderr)

    for date_str in corpus_dates:
        d = _date.fromisoformat(date_str)
        day_dir = CORPUS_DIR / date_str
        es_path = day_dir / "databento_glbx_es.jsonl"
        opra_path = day_dir / "databento_opra.jsonl"

        if not es_path.exists() or not opra_path.exists():
            skipped += 1
            continue

        result = compute_expected_move(d, es_path, opra_path)
        if result is None:
            skipped += 1
            print(f"  SKIP {date_str}: insufficient ATM straddle data", file=sys.stderr)
            continue

        results.append(result)
        print(f"  {date_str}: EM={result['expected_move_pts']:.2f} pts "
              f"(put={result['put_vwap']:.2f} call={result['call_vwap']:.2f} "
              f"n_put={result['n_put_trades']} n_call={result['n_call_trades']} "
              f"spot={result['spot_ref']:.1f} K={result['atm_strike']})",
              file=sys.stderr)

    # Summary statistics
    if results:
        moves = [r["expected_move_pts"] for r in results]
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"EXPECTED MOVE SUMMARY", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"  Days computed: {len(results)} / {len(corpus_dates)} (skipped: {skipped})", file=sys.stderr)
        print(f"  Mean:   {statistics.mean(moves):.2f} pts", file=sys.stderr)
        print(f"  Median: {statistics.median(moves):.2f} pts", file=sys.stderr)
        print(f"  StdDev: {statistics.stdev(moves):.2f} pts", file=sys.stderr)
        print(f"  Min:    {min(moves):.2f} pts", file=sys.stderr)
        print(f"  Max:    {max(moves):.2f} pts", file=sys.stderr)

        # Quartiles
        sorted_moves = sorted(moves)
        n = len(sorted_moves)
        q25 = sorted_moves[n // 4]
        q75 = sorted_moves[3 * n // 4]
        print(f"  Q25:    {q25:.2f} pts", file=sys.stderr)
        print(f"  Q75:    {q75:.2f} pts", file=sys.stderr)

        # Temporal variation: first half vs second half
        mid = len(results) // 2
        first_half = [r["expected_move_pts"] for r in results[:mid]]
        second_half = [r["expected_move_pts"] for r in results[mid:]]
        if first_half and second_half:
            print(f"\n  Temporal split (first half vs second half):", file=sys.stderr)
            print(f"    First half mean:  {statistics.mean(first_half):.2f} pts "
                  f"({results[0]['date']} to {results[mid-1]['date']})", file=sys.stderr)
            print(f"    Second half mean: {statistics.mean(second_half):.2f} pts "
                  f"({results[mid]['date']} to {results[-1]['date']})", file=sys.stderr)

    # Write output
    if not args.dry_run and results:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_PATH.open("w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"\nWrote {len(results)} records to {OUTPUT_PATH}", file=sys.stderr)
    elif args.dry_run:
        for r in results[:5]:
            print(json.dumps(r))
        if len(results) > 5:
            print(f"... ({len(results)} total)")


if __name__ == "__main__":
    main()
