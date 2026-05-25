#!/usr/bin/env python3
"""IV Pin Study: Does the lowest-IV 0DTE strike predict the close?

Theory: The 0DTE SPXW strike with the LOWEST implied volatility acts as a "pin" —
price gravitates toward it by close.

Method:
  1. At 13:00-13:10 CT, collect all 0DTE SPXW trades within ±3% of spot
  2. For each qualified strike (≥3 trades), compute IV from VWAP
     - Use puts for below-spot, calls for above-spot (OTM = cleaner IV)
     - ATM: average put IV and call IV
  3. Find the strike with minimum IV (the "pin strike")
  4. Compare to actual close price

Output: data/measurement/iv_pin.jsonl

[st-745]
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import date as _date, datetime, time as _time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add project root to path for black_scholes import
sys.path.insert(0, str(Path("/root/projects/Strader")))
from market.pricing.black_scholes import implied_vol

CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")

PROJECT_ROOT = Path("/root/projects/Strader")
CORPUS_DIR = PROJECT_ROOT / "data" / "corpus"
OUTPUT_PATH = PROJECT_ROOT / "data" / "measurement" / "iv_pin.jsonl"
VDAYS_PATH = PROJECT_ROOT / "data" / "measurement" / "v_days.jsonl"
EXPECTED_MOVE_PATH = PROJECT_ROOT / "data" / "measurement" / "expected_move.jsonl"
CONFIRMED_VDAYS_PATH = PROJECT_ROOT / "data" / "measurement" / "confirmed_v_days_v0.txt"

# Parameters
RISK_FREE_RATE = 0.05
DIVIDEND_YIELD = 0.0
STRIKE_RANGE_PCT = 0.03  # ±3% of spot
MIN_TRADES = 3  # minimum trades to qualify a strike
MINUTES_PER_YEAR = 365 * 24 * 60
MIN_T_MINUTES = 5  # floor for T to avoid solver instability
MARKET_CLOSE_CT = _time(15, 0)  # 3:00 PM CT


def get_ts_event_iso(provenance: dict) -> str | None:
    """Extract ts_event as ISO string."""
    if "ts_event" in provenance:
        return provenance["ts_event"]
    if "ts_event_ns" in provenance:
        ns = provenance["ts_event_ns"]
        dt = datetime.fromtimestamp(ns / 1e9, tz=UTC)
        return dt.isoformat()
    return None


def parse_ts_event(ts_str: str) -> datetime:
    """Parse ISO timestamp to datetime."""
    return datetime.fromisoformat(ts_str)


def date_to_utc_window(d: _date) -> tuple[datetime, datetime]:
    """13:00-13:10 CT window in UTC."""
    start_ct = datetime.combine(d, _time(13, 0), tzinfo=CENTRAL)
    end_ct = datetime.combine(d, _time(13, 10), tzinfo=CENTRAL)
    return start_ct.astimezone(UTC), end_ct.astimezone(UTC)


def minutes_to_close(d: _date, ref_ct_time: _time = _time(13, 5)) -> float:
    """Minutes from reference time (midpoint of window) to market close."""
    ref = datetime.combine(d, ref_ct_time, tzinfo=CENTRAL)
    close = datetime.combine(d, MARKET_CLOSE_CT, tzinfo=CENTRAL)
    return (close - ref).total_seconds() / 60.0


def parse_opra_symbol(symbol: str) -> tuple[str, _date, str, float] | None:
    """Parse OCC option symbol: root, expiry, P/C, strike."""
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
    """Get ES spot from first trades at/after reference time (VWAP of first second)."""
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

    total_value = sum(p * s for p, s in prices_sizes)
    total_size = sum(s for _, s in prices_sizes)
    return total_value / total_size if total_size > 0 else prices_sizes[0][0]


def collect_strike_trades(opra_path: Path, d: _date,
                          ref_utc: datetime, window_end_utc: datetime,
                          spot: float) -> dict[float, dict[str, list[tuple[float, int]]]]:
    """Collect all 0DTE trades in window, grouped by strike and type.

    Returns: {strike: {"P": [(price, size), ...], "C": [(price, size), ...]}}
    Only includes strikes within ±3% of spot.
    """
    low_strike = spot * (1 - STRIKE_RANGE_PCT)
    high_strike = spot * (1 + STRIKE_RANGE_PCT)
    ref_iso = ref_utc.isoformat()
    window_end_iso = window_end_utc.isoformat()

    # {strike: {"P": [(price, size)], "C": [(price, size)]}}
    trades: dict[float, dict[str, list[tuple[float, int]]]] = defaultdict(
        lambda: {"P": [], "C": []}
    )

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

            # Must be 0DTE
            if expiry != d:
                continue

            # Must be within range
            if strike < low_strike or strike > high_strike:
                continue

            price = rec["data"]["price"]
            size = rec["data"]["size"]
            trades[strike][pc].append((price, size))

    return dict(trades)


def compute_vwap(trades: list[tuple[float, int]]) -> float | None:
    """Volume-weighted average price."""
    if not trades:
        return None
    total_value = sum(p * s for p, s in trades)
    total_size = sum(s for _, s in trades)
    if total_size == 0:
        return None
    return total_value / total_size


def compute_iv_for_strike(strike: float, spot: float, T: float,
                          put_trades: list[tuple[float, int]],
                          call_trades: list[tuple[float, int]]) -> float | None:
    """Compute IV for a strike using OTM convention.

    - Below spot: use puts (OTM)
    - Above spot: use calls (OTM)
    - ATM (within $2.50): average put and call IV
    """
    atm_threshold = 2.50  # half a $5 strike interval

    try:
        if abs(strike - spot) <= atm_threshold:
            # ATM: try both sides
            ivs = []
            if put_trades:
                put_vwap = compute_vwap(put_trades)
                if put_vwap and put_vwap > 0:
                    try:
                        iv_p = implied_vol(put_vwap, spot, strike, T, RISK_FREE_RATE, "PUT", DIVIDEND_YIELD)
                        ivs.append(iv_p)
                    except (ValueError, RuntimeError):
                        pass
            if call_trades:
                call_vwap = compute_vwap(call_trades)
                if call_vwap and call_vwap > 0:
                    try:
                        iv_c = implied_vol(call_vwap, spot, strike, T, RISK_FREE_RATE, "CALL", DIVIDEND_YIELD)
                        ivs.append(iv_c)
                    except (ValueError, RuntimeError):
                        pass
            if ivs:
                return statistics.mean(ivs)
            return None

        elif strike < spot:
            # Below spot: use puts (OTM)
            if not put_trades:
                return None
            put_vwap = compute_vwap(put_trades)
            if not put_vwap or put_vwap <= 0:
                return None
            return implied_vol(put_vwap, spot, strike, T, RISK_FREE_RATE, "PUT", DIVIDEND_YIELD)

        else:
            # Above spot: use calls (OTM)
            if not call_trades:
                return None
            call_vwap = compute_vwap(call_trades)
            if not call_vwap or call_vwap <= 0:
                return None
            return implied_vol(call_vwap, spot, strike, T, RISK_FREE_RATE, "CALL", DIVIDEND_YIELD)

    except (ValueError, RuntimeError):
        return None


def compute_pin_for_day(d: _date, es_path: Path, opra_path: Path,
                        close_p: float) -> dict | None:
    """Compute the IV pin strike for a single day."""
    ref_utc, window_end_utc = date_to_utc_window(d)

    # Get spot
    spot = get_spot_at_reference(es_path, ref_utc)
    if spot is None:
        return None

    # Time to expiry (from midpoint of window to close)
    mins_to_close = minutes_to_close(d)
    T = max(mins_to_close, MIN_T_MINUTES) / MINUTES_PER_YEAR

    # Collect trades
    strike_trades = collect_strike_trades(opra_path, d, ref_utc, window_end_utc, spot)
    if not strike_trades:
        return None

    # Compute IV for each qualified strike
    strike_ivs: list[tuple[float, float]] = []  # (strike, iv)
    n_failed = 0

    for strike, sides in sorted(strike_trades.items()):
        put_trades = sides["P"]
        call_trades = sides["C"]
        total_trades = len(put_trades) + len(call_trades)

        if total_trades < MIN_TRADES:
            continue

        iv = compute_iv_for_strike(strike, spot, T, put_trades, call_trades)
        if iv is not None and 0.01 < iv < 3.0:  # sanity bounds
            strike_ivs.append((strike, iv))
        else:
            n_failed += 1

    if not strike_ivs:
        return None

    # Find minimum IV strike
    strike_ivs.sort(key=lambda x: x[1])
    pin_strike, pin_iv = strike_ivs[0]

    # If ties, pick nearest to spot
    min_iv = pin_iv
    ties = [(s, iv) for s, iv in strike_ivs if abs(iv - min_iv) < 1e-6]
    if len(ties) > 1:
        ties.sort(key=lambda x: abs(x[0] - spot))
        pin_strike = ties[0][0]

    # Compute distance
    distance_pts = abs(close_p - pin_strike)

    all_ivs = [iv for _, iv in strike_ivs]

    return {
        "date": d.isoformat(),
        "spot_ref": round(spot, 2),
        "pin_strike": pin_strike,
        "pin_iv": round(pin_iv, 4),
        "close_p": close_p,
        "distance_pts": round(distance_pts, 2),
        "n_strikes_qualified": len(strike_ivs),
        "n_failed_iv": n_failed,
        "iv_range": [round(min(all_ivs), 4), round(max(all_ivs), 4)],
        "spot_to_close": round(abs(close_p - spot), 2),
    }


def load_close_prices() -> dict[str, float]:
    """Load close prices from v_days.jsonl."""
    closes = {}
    with VDAYS_PATH.open() as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            closes[rec["date"]] = rec["close_p"]
    return closes


def load_expected_moves() -> dict[str, float]:
    """Load expected move data."""
    moves = {}
    if EXPECTED_MOVE_PATH.exists():
        with EXPECTED_MOVE_PATH.open() as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                moves[rec["date"]] = rec["expected_move_pts"]
    return moves


def load_confirmed_vdays() -> set[str]:
    """Load confirmed V-day dates."""
    vdays = set()
    if CONFIRMED_VDAYS_PATH.exists():
        with CONFIRMED_VDAYS_PATH.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    vdays.add(line)
    return vdays


def load_vdays_data() -> dict[str, dict]:
    """Load full v_days records for trough/peak analysis."""
    data = {}
    with VDAYS_PATH.open() as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            data[rec["date"]] = rec
    return data


def main():
    print("=" * 70, file=sys.stderr)
    print("IV PIN STUDY — Lowest-IV Strike as Close Predictor", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Load reference data
    close_prices = load_close_prices()
    expected_moves = load_expected_moves()
    confirmed_vdays = load_confirmed_vdays()
    vdays_data = load_vdays_data()

    # Process all corpus days
    corpus_dates = sorted(p.name for p in CORPUS_DIR.iterdir() if p.is_dir())
    results: list[dict] = []
    skipped = 0

    print(f"\nProcessing {len(corpus_dates)} corpus days...", file=sys.stderr)

    for date_str in corpus_dates:
        d = _date.fromisoformat(date_str)
        day_dir = CORPUS_DIR / date_str
        es_path = day_dir / "databento_glbx_es.jsonl"
        opra_path = day_dir / "databento_opra.jsonl"

        if not es_path.exists() or not opra_path.exists():
            skipped += 1
            continue

        if date_str not in close_prices:
            skipped += 1
            continue

        close_p = close_prices[date_str]
        result = compute_pin_for_day(d, es_path, opra_path, close_p)

        if result is None:
            skipped += 1
            print(f"  SKIP {date_str}: insufficient data for IV computation", file=sys.stderr)
            continue

        # Add expected move distance if available
        if date_str in expected_moves:
            em = expected_moves[date_str]
            result["distance_pct_em"] = round(result["distance_pts"] / em, 4) if em > 0 else None
            result["expected_move_pts"] = em
        else:
            result["distance_pct_em"] = None

        results.append(result)
        marker = " [V-DAY]" if date_str in confirmed_vdays else ""
        print(f"  {date_str}: pin={result['pin_strike']:.0f} iv={result['pin_iv']:.3f} "
              f"close={close_p:.1f} dist={result['distance_pts']:.1f}pts "
              f"(n_strikes={result['n_strikes_qualified']}){marker}",
              file=sys.stderr)

    print(f"\n  Processed: {len(results)} / {len(corpus_dates)} (skipped: {skipped})", file=sys.stderr)

    if not results:
        print("ERROR: No results computed.", file=sys.stderr)
        sys.exit(1)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\nWrote {len(results)} records to {OUTPUT_PATH}", file=sys.stderr)

    # =========================================================================
    # ANALYSIS
    # =========================================================================
    print(f"\n{'=' * 70}", file=sys.stderr)
    print("ANALYSIS", file=sys.stderr)
    print(f"{'=' * 70}", file=sys.stderr)

    distances = [r["distance_pts"] for r in results]
    spot_to_close = [r["spot_to_close"] for r in results]

    # --- 1. BASELINE: Pin distance vs. null model (spot drift) ---
    print(f"\n--- 1. BASELINE COMPARISON ---", file=sys.stderr)
    print(f"  Pin-to-close (mean):  {statistics.mean(distances):.2f} pts", file=sys.stderr)
    print(f"  Pin-to-close (median): {statistics.median(distances):.2f} pts", file=sys.stderr)
    print(f"  Spot-to-close (mean):  {statistics.mean(spot_to_close):.2f} pts "
          f"(null model: 13:00 spot → close)", file=sys.stderr)
    print(f"  Spot-to-close (median): {statistics.median(spot_to_close):.2f} pts", file=sys.stderr)

    improvement = statistics.mean(spot_to_close) - statistics.mean(distances)
    print(f"  Improvement (mean):    {improvement:.2f} pts "
          f"({'BETTER' if improvement > 0 else 'WORSE'} than null)", file=sys.stderr)

    # --- 2. PIN ACCURACY ---
    print(f"\n--- 2. PIN ACCURACY ---", file=sys.stderr)
    within_5 = sum(1 for d in distances if d <= 5.0)
    within_10 = sum(1 for d in distances if d <= 10.0)
    within_15 = sum(1 for d in distances if d <= 15.0)
    within_20 = sum(1 for d in distances if d <= 20.0)

    n = len(results)
    print(f"  Within 5 pts:   {within_5}/{n} ({100*within_5/n:.1f}%)", file=sys.stderr)
    print(f"  Within 10 pts:  {within_10}/{n} ({100*within_10/n:.1f}%)", file=sys.stderr)
    print(f"  Within 15 pts:  {within_15}/{n} ({100*within_15/n:.1f}%)", file=sys.stderr)
    print(f"  Within 20 pts:  {within_20}/{n} ({100*within_20/n:.1f}%)", file=sys.stderr)

    # Within expected move
    em_results = [r for r in results if r.get("distance_pct_em") is not None]
    if em_results:
        within_em = sum(1 for r in em_results if r["distance_pct_em"] <= 1.0)
        print(f"  Within 1x EM:   {within_em}/{len(em_results)} "
              f"({100*within_em/len(em_results):.1f}%)", file=sys.stderr)
        within_half_em = sum(1 for r in em_results if r["distance_pct_em"] <= 0.5)
        print(f"  Within 0.5x EM: {within_half_em}/{len(em_results)} "
              f"({100*within_half_em/len(em_results):.1f}%)", file=sys.stderr)

    # Compare: how often does spot-at-13:00 end within 5 pts of close? (null model)
    spot_within_5 = sum(1 for s in spot_to_close if s <= 5.0)
    spot_within_10 = sum(1 for s in spot_to_close if s <= 10.0)
    print(f"\n  Null model (spot@13:00 → close):", file=sys.stderr)
    print(f"    Within 5 pts:  {spot_within_5}/{n} ({100*spot_within_5/n:.1f}%)", file=sys.stderr)
    print(f"    Within 10 pts: {spot_within_10}/{n} ({100*spot_within_10/n:.1f}%)", file=sys.stderr)

    # --- 3. V-DAY SPECIFIC ANALYSIS ---
    print(f"\n--- 3. V-DAY ANALYSIS (Confirmed V-days) ---", file=sys.stderr)
    vday_results = [r for r in results if r["date"] in confirmed_vdays]
    non_vday_results = [r for r in results if r["date"] not in confirmed_vdays]

    if vday_results:
        vday_distances = [r["distance_pts"] for r in vday_results]
        print(f"  V-days found in corpus: {len(vday_results)}/{len(confirmed_vdays)}", file=sys.stderr)
        print(f"  V-day pin-to-close (mean):  {statistics.mean(vday_distances):.2f} pts", file=sys.stderr)
        print(f"  V-day pin-to-close (median): {statistics.median(vday_distances):.2f} pts", file=sys.stderr)
        if non_vday_results:
            non_vday_distances = [r["distance_pts"] for r in non_vday_results]
            print(f"  Non-V-day pin-to-close (mean): {statistics.mean(non_vday_distances):.2f} pts",
                  file=sys.stderr)

        print(f"\n  V-day detail:", file=sys.stderr)
        for r in vday_results:
            vd = vdays_data.get(r["date"], {})
            trough_p = vd.get("trough_p", "?")
            peak_p = vd.get("peak_p", "?")
            vwap_p = vd.get("vwap_p", "?")

            pin = r["pin_strike"]
            close = r["close_p"]
            spot = r["spot_ref"]

            # Distance from pin to trough
            dist_to_trough = abs(pin - trough_p) if isinstance(trough_p, (int, float)) else "?"
            # Distance from pin to VWAP (pre-drop consolidation proxy)
            dist_to_vwap = abs(pin - vwap_p) if isinstance(vwap_p, (int, float)) else "?"

            dt_str = f"{dist_to_trough:.1f}" if isinstance(dist_to_trough, (int, float)) else str(dist_to_trough)
            print(f"    {r['date']}: pin={pin:.0f} spot={spot:.1f} close={close:.1f} "
                  f"trough={trough_p} | "
                  f"pin→close={r['distance_pts']:.1f} "
                  f"pin→trough={dt_str}",
                  file=sys.stderr)
    else:
        print("  No confirmed V-days found in results.", file=sys.stderr)

    # --- 4. CONTINUATION DAYS ---
    print(f"\n--- 4. CONTINUATION DAY ANALYSIS ---", file=sys.stderr)
    # Continuation = labeled 'none' in v_days (no V recovery)
    # AND close < spot (drifted lower or stayed lower)
    continuation_results = []
    for r in results:
        vd = vdays_data.get(r["date"], {})
        label = vd.get("label", "")
        # Continuation: price drops but doesn't recover = close significantly below spot
        if label == "none" and r["close_p"] < r["spot_ref"] - 5:
            continuation_results.append(r)

    if continuation_results:
        cont_distances = [r["distance_pts"] for r in continuation_results]
        print(f"  Continuation days (close >5pts below 13:00 spot): {len(continuation_results)}", file=sys.stderr)
        print(f"  Continuation pin-to-close (mean):  {statistics.mean(cont_distances):.2f} pts", file=sys.stderr)
        print(f"  Continuation pin-to-close (median): {statistics.median(cont_distances):.2f} pts", file=sys.stderr)

        # For continuation days, does pin predict where they'd like to go but fail?
        # i.e., is pin above close (they couldn't reach it)?
        pin_above_close = sum(1 for r in continuation_results if r["pin_strike"] > r["close_p"])
        print(f"  Pin above close (failed to reach): {pin_above_close}/{len(continuation_results)} "
              f"({100*pin_above_close/len(continuation_results):.0f}%)", file=sys.stderr)
    else:
        print("  No clear continuation days identified.", file=sys.stderr)

    # --- 5. DISTRIBUTION ---
    print(f"\n--- 5. DISTANCE DISTRIBUTION ---", file=sys.stderr)
    sorted_dist = sorted(distances)
    n = len(sorted_dist)
    print(f"  Min:    {sorted_dist[0]:.2f} pts", file=sys.stderr)
    print(f"  Q25:    {sorted_dist[n//4]:.2f} pts", file=sys.stderr)
    print(f"  Median: {sorted_dist[n//2]:.2f} pts", file=sys.stderr)
    print(f"  Q75:    {sorted_dist[3*n//4]:.2f} pts", file=sys.stderr)
    print(f"  Max:    {sorted_dist[-1]:.2f} pts", file=sys.stderr)
    print(f"  StdDev: {statistics.stdev(distances):.2f} pts", file=sys.stderr)

    # --- 6. PIN IV STATISTICS ---
    print(f"\n--- 6. PIN IV STATISTICS ---", file=sys.stderr)
    pin_ivs = [r["pin_iv"] for r in results]
    print(f"  Mean pin IV:   {statistics.mean(pin_ivs):.4f} ({100*statistics.mean(pin_ivs):.2f}%)",
          file=sys.stderr)
    print(f"  Median pin IV: {statistics.median(pin_ivs):.4f}", file=sys.stderr)
    print(f"  Min pin IV:    {min(pin_ivs):.4f}", file=sys.stderr)
    print(f"  Max pin IV:    {max(pin_ivs):.4f}", file=sys.stderr)

    # --- 7. DIRECTIONAL BIAS ---
    print(f"\n--- 7. DIRECTIONAL ANALYSIS ---", file=sys.stderr)
    pin_above_spot = sum(1 for r in results if r["pin_strike"] > r["spot_ref"])
    pin_below_spot = sum(1 for r in results if r["pin_strike"] < r["spot_ref"])
    pin_at_spot = sum(1 for r in results if abs(r["pin_strike"] - r["spot_ref"]) <= 2.5)
    print(f"  Pin above spot: {pin_above_spot}/{len(results)} ({100*pin_above_spot/len(results):.1f}%)",
          file=sys.stderr)
    print(f"  Pin below spot: {pin_below_spot}/{len(results)} ({100*pin_below_spot/len(results):.1f}%)",
          file=sys.stderr)
    print(f"  Pin ≈ spot (±2.5): {pin_at_spot}/{len(results)} ({100*pin_at_spot/len(results):.1f}%)",
          file=sys.stderr)

    # Does close follow the pin direction?
    correct_direction = 0
    for r in results:
        pin_dir = r["pin_strike"] - r["spot_ref"]  # positive = pin above spot
        close_dir = r["close_p"] - r["spot_ref"]  # positive = close above spot
        if pin_dir * close_dir > 0:  # same sign
            correct_direction += 1
    print(f"  Close moves toward pin direction: {correct_direction}/{len(results)} "
          f"({100*correct_direction/len(results):.1f}%)", file=sys.stderr)

    print(f"\n{'=' * 70}", file=sys.stderr)


if __name__ == "__main__":
    main()
