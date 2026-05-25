"""
Greek Snapshot Study — Track A: Point-in-Time Greek Snapshot at V-Day Trough.

Compares volume-weighted Greeks at the trough moment between:
  PIVOT (13 confirmed V-days with snap-back recovery)
  CONTINUATION (days with meaningful drop but no recovery)

Bead: st-745
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev

# Wire up the BS module
STRADER_ROOT = Path("/root/projects/Strader")
sys.path.insert(0, str(STRADER_ROOT / "market" / "pricing"))
from black_scholes import greeks, implied_vol  # noqa: E402

# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────
RISK_FREE_RATE = 0.05
MIN_T = 0.001  # Skip options expiring within ~8.7 hours
WINDOW_MINUTES = 10  # Look-back window before trough
MIN_DRAWDOWN_PTS = 15  # Minimum depth from VWAP for CONTINUATION class
BOOTSTRAP_N = 1000
GREEK_NAMES = ["delta", "gamma", "theta", "vega", "rho", "vanna", "charm"]

DATA_DIR = STRADER_ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
MEASUREMENT_DIR = DATA_DIR / "measurement"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def parse_occ_symbol(symbol: str) -> dict | None:
    """Parse OCC option symbol like 'SPXW  250811P06370000'.

    Returns dict with: root, expiry (date), opt_type ('CALL'|'PUT'), strike (float).
    Returns None if parsing fails.
    """
    # Strip whitespace normalization — symbol is fixed-width
    # Format: ROOT (6 chars) + YYMMDD (6) + P/C (1) + strike*1000 zero-padded (8)
    # But SPXW has trailing spaces to fill 6 chars
    s = symbol.strip()
    if len(s) < 15:
        return None

    # Find the P or C — it's always at position after the date digits
    # Root is everything up to the first digit sequence of length 6+ that
    # encodes YYMMDD. Easier: work from fixed-width OCC format.
    # OCC standard: 6-char root (space-padded) + 6-char date + 1 P/C + 8-char strike
    raw = symbol  # Keep original with spaces
    if len(raw) < 21:
        return None

    root = raw[:6].strip()
    date_str = raw[6:12]
    pc = raw[12]
    strike_str = raw[13:21]

    try:
        yy = int(date_str[0:2])
        mm = int(date_str[2:4])
        dd = int(date_str[4:6])
        year = 2000 + yy
        expiry = datetime(year, mm, dd)
    except (ValueError, IndexError):
        return None

    if pc not in ("P", "C"):
        return None

    try:
        strike = int(strike_str) / 1000.0
    except ValueError:
        return None

    return {
        "root": root,
        "expiry": expiry,
        "opt_type": "PUT" if pc == "P" else "CALL",
        "strike": strike,
    }


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp with timezone info. Handles nanoseconds by truncating."""
    # Python's fromisoformat can't handle nanosecond precision before 3.11
    # Truncate fractional seconds to 6 digits (microseconds)
    if "." in ts_str:
        base, frac_and_tz = ts_str.split(".", 1)
        # Separate fractional seconds from timezone
        # Timezone starts with + or - after the digits, or Z
        frac = ""
        tz_part = ""
        i = 0
        while i < len(frac_and_tz) and frac_and_tz[i].isdigit():
            frac += frac_and_tz[i]
            i += 1
        tz_part = frac_and_tz[i:]
        # Truncate to 6 digits
        frac = frac[:6].ljust(6, "0")
        ts_str = f"{base}.{frac}{tz_part}"

    # Handle Z suffix
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def get_spot_at_time(es_path: Path, target_utc: datetime) -> float | None:
    """Get ES spot price closest to (but not after) target_utc.

    Reads the ES file and finds the last trade at or before target_utc.
    For efficiency, reads in chunks and stops once past the target.
    """
    best_price = None
    best_ts = None

    with open(es_path, "r") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = rec.get("provenance", {}).get("ts_event")
            if not ts_str:
                continue
            try:
                ts = parse_iso_timestamp(ts_str)
            except (ValueError, IndexError):
                continue
            if ts > target_utc:
                # Past target — stop if we already have something
                if best_price is not None:
                    break
                continue
            price = rec.get("data", {}).get("price")
            if price and price > 0:
                if best_ts is None or ts >= best_ts:
                    best_price = price
                    best_ts = ts

    return best_price


def get_opra_trades_in_window(
    opra_path: Path, window_start_utc: datetime, window_end_utc: datetime
) -> list[dict]:
    """Get all OPRA trades within [window_start, window_end] UTC."""
    trades = []
    past_window = False

    with open(opra_path, "r") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = rec.get("provenance", {}).get("ts_event")
            if not ts_str:
                continue
            try:
                ts = parse_iso_timestamp(ts_str)
            except (ValueError, IndexError):
                continue

            if ts < window_start_utc:
                continue
            if ts > window_end_utc:
                past_window = True
                break

            data = rec.get("data", {})
            symbol = data.get("symbol", "")
            if not symbol.startswith("SPXW"):
                continue
            price = data.get("price", 0)
            size = data.get("size", 0)
            if price <= 0 or size <= 0:
                continue

            trades.append({
                "ts": ts,
                "symbol": symbol,
                "price": price,
                "size": size,
            })

    return trades


def compute_day_greeks(date_str: str, trough_t_str: str) -> dict | None:
    """Compute volume-weighted average Greeks for a given day at its trough.

    Returns dict of {greek_name: value} or None if insufficient data.
    """
    # Parse trough time (CT with offset) and convert to UTC
    trough_utc = parse_iso_timestamp(trough_t_str).astimezone(timezone.utc)

    # Window: 10 minutes before trough
    window_start = trough_utc - timedelta(minutes=WINDOW_MINUTES)
    window_end = trough_utc

    # File paths
    opra_path = CORPUS_DIR / date_str / "databento_opra.jsonl"
    es_path = CORPUS_DIR / date_str / "databento_glbx_es.jsonl"

    if not opra_path.exists() or not es_path.exists():
        return None

    # Get spot at trough
    spot = get_spot_at_time(es_path, trough_utc)
    if spot is None or spot <= 0:
        return None

    # Get option trades in window
    trades = get_opra_trades_in_window(opra_path, window_start, window_end)
    if not trades:
        return None

    # Compute Greeks for each trade
    weighted_greeks = {g: 0.0 for g in GREEK_NAMES}
    total_volume = 0
    errors = 0
    skipped_expiry = 0

    for trade in trades:
        parsed = parse_occ_symbol(trade["symbol"])
        if parsed is None:
            errors += 1
            continue

        # Time to expiry
        # Expiry is end of day on expiry date (use 16:00 CT = market close)
        expiry_dt = parsed["expiry"].replace(
            hour=21, minute=0, second=0,  # 16:00 CT = 21:00 UTC (CDT)
            tzinfo=timezone.utc
        )
        T = (expiry_dt - trade["ts"].astimezone(timezone.utc)).total_seconds() / (
            365.25 * 24 * 3600
        )

        if T < MIN_T:
            skipped_expiry += 1
            continue

        # Compute implied vol
        try:
            iv = implied_vol(
                market_price=trade["price"],
                spot=spot,
                strike=parsed["strike"],
                T=T,
                r=RISK_FREE_RATE,
                opt_type=parsed["opt_type"],
            )
        except (ValueError, RuntimeError):
            errors += 1
            continue

        # Compute Greeks
        try:
            g = greeks(
                spot=spot,
                strike=parsed["strike"],
                T=T,
                r=RISK_FREE_RATE,
                sigma=iv,
                opt_type=parsed["opt_type"],
            )
        except (ValueError, ZeroDivisionError):
            errors += 1
            continue

        # Accumulate volume-weighted
        vol = trade["size"]
        for name in GREEK_NAMES:
            weighted_greeks[name] += g[name] * vol
        total_volume += vol

    if total_volume == 0:
        return None

    # Normalize
    result = {name: weighted_greeks[name] / total_volume for name in GREEK_NAMES}
    result["_meta"] = {
        "date": date_str,
        "spot": spot,
        "trades_used": len(trades) - errors - skipped_expiry,
        "errors": errors,
        "skipped_expiry": skipped_expiry,
        "total_volume": total_volume,
    }
    return result


# ──────────────────────────────────────────────────────────────────────
# Class definition
# ──────────────────────────────────────────────────────────────────────
def load_v_days() -> dict:
    """Load v_days.jsonl into a dict keyed by date."""
    days = {}
    with open(MEASUREMENT_DIR / "v_days.jsonl") as f:
        for line in f:
            d = json.loads(line)
            days[d["date"]] = d
    return days


def get_pivot_dates() -> list[str]:
    """Load confirmed V-day dates."""
    dates = []
    with open(MEASUREMENT_DIR / "confirmed_v_days_v0.txt") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                dates.append(line)
    return dates


def get_continuation_dates(v_days: dict, pivot_dates: set[str]) -> list[str]:
    """Get CONTINUATION class: depth_ok=True, recovery_ok=False, depth>=15pt, not a PIVOT day."""
    dates = []
    for date_str, d in v_days.items():
        if date_str in pivot_dates:
            continue
        vd = d.get("v_down")
        if not vd:
            continue
        criteria = vd.get("criteria", {})
        if criteria.get("depth_ok") and not criteria.get("recovery_ok"):
            if vd.get("depth", 0) >= MIN_DRAWDOWN_PTS:
                dates.append(date_str)
    return sorted(dates)


# ──────────────────────────────────────────────────────────────────────
# Statistics
# ──────────────────────────────────────────────────────────────────────
def cohens_d(group1: list[float], group2: list[float]) -> float:
    """Cohen's d effect size (pooled std)."""
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return float("nan")
    m1, m2 = mean(group1), mean(group2)
    s1, s2 = stdev(group1), stdev(group2)
    pooled = ((((n1 - 1) * s1**2) + ((n2 - 1) * s2**2)) / (n1 + n2 - 2)) ** 0.5
    if pooled == 0:
        return float("nan")
    return (m1 - m2) / pooled


def bootstrap_ci(
    group1: list[float], group2: list[float], n_resamples: int = BOOTSTRAP_N
) -> tuple[float, float]:
    """Bootstrap 95% CI on the difference of means (group1 - group2)."""
    diffs = []
    random.seed(42)  # Reproducible
    for _ in range(n_resamples):
        s1 = random.choices(group1, k=len(group1))
        s2 = random.choices(group2, k=len(group2))
        diffs.append(mean(s1) - mean(s2))
    diffs.sort()
    lo = diffs[int(0.025 * n_resamples)]
    hi = diffs[int(0.975 * n_resamples)]
    return lo, hi


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def compute_day_greeks_segmented(date_str: str, trough_t_str: str) -> dict | None:
    """Like compute_day_greeks but returns separate aggregations:
    - all: volume-weighted across all trades
    - puts_atm: puts within 1% of spot
    - puts_otm: puts 1-3% OTM (below spot)
    - calls_atm: calls within 1% of spot

    Returns dict of {segment: {greek: value}} or None.
    """
    trough_utc = parse_iso_timestamp(trough_t_str).astimezone(timezone.utc)
    window_start = trough_utc - timedelta(minutes=WINDOW_MINUTES)
    window_end = trough_utc

    opra_path = CORPUS_DIR / date_str / "databento_opra.jsonl"
    es_path = CORPUS_DIR / date_str / "databento_glbx_es.jsonl"

    if not opra_path.exists() or not es_path.exists():
        return None

    spot = get_spot_at_time(es_path, trough_utc)
    if spot is None or spot <= 0:
        return None

    trades = get_opra_trades_in_window(opra_path, window_start, window_end)
    if not trades:
        return None

    # Segments: track weighted greeks and volume separately
    segments = {
        "all": {"greeks": {g: 0.0 for g in GREEK_NAMES}, "vol": 0},
        "puts_atm": {"greeks": {g: 0.0 for g in GREEK_NAMES}, "vol": 0},
        "puts_otm": {"greeks": {g: 0.0 for g in GREEK_NAMES}, "vol": 0},
        "calls_atm": {"greeks": {g: 0.0 for g in GREEK_NAMES}, "vol": 0},
    }
    errors = 0

    for trade in trades:
        parsed = parse_occ_symbol(trade["symbol"])
        if parsed is None:
            errors += 1
            continue

        expiry_dt = parsed["expiry"].replace(
            hour=21, minute=0, second=0, tzinfo=timezone.utc
        )
        T = (expiry_dt - trade["ts"].astimezone(timezone.utc)).total_seconds() / (
            365.25 * 24 * 3600
        )
        if T < MIN_T:
            continue

        try:
            iv = implied_vol(
                market_price=trade["price"],
                spot=spot,
                strike=parsed["strike"],
                T=T,
                r=RISK_FREE_RATE,
                opt_type=parsed["opt_type"],
            )
        except (ValueError, RuntimeError):
            errors += 1
            continue

        try:
            g = greeks(
                spot=spot,
                strike=parsed["strike"],
                T=T,
                r=RISK_FREE_RATE,
                sigma=iv,
                opt_type=parsed["opt_type"],
            )
        except (ValueError, ZeroDivisionError):
            errors += 1
            continue

        vol = trade["size"]
        moneyness = (parsed["strike"] - spot) / spot  # negative = OTM put, positive = OTM call

        # Determine segments
        target_segments = ["all"]
        if parsed["opt_type"] == "PUT":
            if abs(moneyness) <= 0.01:
                target_segments.append("puts_atm")
            elif -0.03 <= moneyness < -0.01:
                target_segments.append("puts_otm")
        elif parsed["opt_type"] == "CALL":
            if abs(moneyness) <= 0.01:
                target_segments.append("calls_atm")

        for seg in target_segments:
            for name in GREEK_NAMES:
                segments[seg]["greeks"][name] += g[name] * vol
            segments[seg]["vol"] += vol

    # Normalize
    result = {}
    for seg_name, seg_data in segments.items():
        if seg_data["vol"] > 0:
            result[seg_name] = {
                name: seg_data["greeks"][name] / seg_data["vol"]
                for name in GREEK_NAMES
            }
            result[seg_name]["_vol"] = seg_data["vol"]
        else:
            result[seg_name] = None

    result["_meta"] = {"date": date_str, "spot": spot, "errors": errors}
    return result


def main():
    print("=" * 72)
    print("GREEK SNAPSHOT STUDY — Track A: Point-in-Time at Trough")
    print("=" * 72)
    print()

    # Load data
    v_days = load_v_days()
    pivot_dates = get_pivot_dates()
    continuation_dates = get_continuation_dates(v_days, set(pivot_dates))

    print(f"PIVOT class:        {len(pivot_dates)} days (confirmed V-days)")
    print(f"CONTINUATION class: {len(continuation_dates)} days (drop without recovery)")
    print()

    # Process PIVOT days (segmented)
    print("Processing PIVOT days (segmented)...")
    pivot_segmented = []
    for date_str in pivot_dates:
        day_data = v_days.get(date_str)
        if not day_data:
            print(f"  SKIP {date_str}: not in v_days.jsonl")
            continue
        trough_t = day_data.get("trough_t")
        if not trough_t:
            print(f"  SKIP {date_str}: no trough_t")
            continue
        print(f"  {date_str}...", end=" ", flush=True)
        result = compute_day_greeks_segmented(date_str, trough_t)
        if result and result.get("all"):
            meta = result.pop("_meta")
            pivot_segmented.append(result)
            print(f"OK (spot={meta['spot']:.1f}, err={meta['errors']})")
        else:
            print("FAILED")

    print()

    # Process CONTINUATION days (segmented)
    print("Processing CONTINUATION days (segmented)...")
    cont_segmented = []
    for date_str in continuation_dates:
        day_data = v_days.get(date_str)
        if not day_data:
            print(f"  SKIP {date_str}: not in v_days.jsonl")
            continue
        trough_t = day_data.get("trough_t")
        if not trough_t:
            print(f"  SKIP {date_str}: no trough_t")
            continue
        print(f"  {date_str}...", end=" ", flush=True)
        result = compute_day_greeks_segmented(date_str, trough_t)
        if result and result.get("all"):
            meta = result.pop("_meta")
            cont_segmented.append(result)
            print(f"OK (spot={meta['spot']:.1f}, err={meta['errors']})")
        else:
            print("FAILED")

    print()
    print("-" * 72)
    print(f"Successfully processed: PIVOT={len(pivot_segmented)}, "
          f"CONTINUATION={len(cont_segmented)}")
    print("-" * 72)
    print()

    if len(pivot_segmented) < 3 or len(cont_segmented) < 3:
        print("ERROR: Insufficient data for statistical comparison.")
        return

    # Report for each segment
    SEGMENTS = ["all", "puts_atm", "puts_otm", "calls_atm"]
    SEGMENT_LABELS = {
        "all": "ALL TRADES (volume-weighted)",
        "puts_atm": "PUTS ATM (strike within 1% of spot)",
        "puts_otm": "PUTS OTM (strike 1-3% below spot)",
        "calls_atm": "CALLS ATM (strike within 1% of spot)",
    }

    for seg in SEGMENTS:
        # Filter to days that have data for this segment
        p_data = [d[seg] for d in pivot_segmented if d.get(seg) is not None]
        c_data = [d[seg] for d in cont_segmented if d.get(seg) is not None]

        print()
        print(f"SEGMENT: {SEGMENT_LABELS[seg]}")
        print(f"  PIVOT days with data: {len(p_data)}, CONTINUATION: {len(c_data)}")

        if len(p_data) < 3 or len(c_data) < 3:
            print("  SKIP: insufficient data for this segment")
            continue

        # Volume info
        p_vols = [d.get("_vol", 0) for d in p_data]
        c_vols = [d.get("_vol", 0) for d in c_data]
        print(f"  Avg volume — PIVOT: {mean(p_vols):.0f}, CONT: {mean(c_vols):.0f}")
        print()

        print(f"  {'Greek':<8} {'P mean':>11} {'P std':>11} "
              f"{'C mean':>11} {'C std':>11} "
              f"{'Cohen d':>8} {'CI lo':>10} {'CI hi':>10} {'Sig?':>5}")
        print(f"  {'-'*93}")

        for greek_name in GREEK_NAMES:
            pvals = [d[greek_name] for d in p_data]
            cvals = [d[greek_name] for d in c_data]

            p_mean = mean(pvals)
            p_std = stdev(pvals) if len(pvals) > 1 else 0.0
            c_mean = mean(cvals)
            c_std = stdev(cvals) if len(cvals) > 1 else 0.0

            d = cohens_d(pvals, cvals)
            ci_lo, ci_hi = bootstrap_ci(pvals, cvals)
            signal = "YES" if (ci_lo > 0 or ci_hi < 0) else "no"

            print(f"  {greek_name:<8} {p_mean:>11.6f} {p_std:>11.6f} "
                  f"{c_mean:>11.6f} {c_std:>11.6f} "
                  f"{d:>8.3f} {ci_lo:>10.6f} {ci_hi:>10.6f} {signal:>5}")

    # ──────────────────────────────────────────────────────────────────
    # SUPPLEMENTAL: IV level and put/call volume ratio
    # ──────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("SUPPLEMENTAL METRICS (not per-Greek, but structural)")
    print("=" * 72)
    print()

    # Extract IV and volume ratios from the segmented data
    # IV proxy: use vega / (spot * sqrt(T)) relationship is complex,
    # better: compute mean IV directly. Let's use theta/vega ratio as IV proxy
    # Actually, for puts_atm, vega is roughly spot*sqrt(T)*N'(d1), and theta
    # contains a sigma term. Simpler: just report the volume ratio.

    # Put/Call volume ratio at ATM
    pivot_pc_ratio = []
    for d in pivot_segmented:
        put_vol = d.get("puts_atm", {}).get("_vol", 0) if d.get("puts_atm") else 0
        call_vol = d.get("calls_atm", {}).get("_vol", 0) if d.get("calls_atm") else 0
        if call_vol > 0:
            pivot_pc_ratio.append(put_vol / call_vol)

    cont_pc_ratio = []
    for d in cont_segmented:
        put_vol = d.get("puts_atm", {}).get("_vol", 0) if d.get("puts_atm") else 0
        call_vol = d.get("calls_atm", {}).get("_vol", 0) if d.get("calls_atm") else 0
        if call_vol > 0:
            cont_pc_ratio.append(put_vol / call_vol)

    if len(pivot_pc_ratio) >= 3 and len(cont_pc_ratio) >= 3:
        d_val = cohens_d(pivot_pc_ratio, cont_pc_ratio)
        ci_lo, ci_hi = bootstrap_ci(pivot_pc_ratio, cont_pc_ratio)
        signal = "YES" if (ci_lo > 0 or ci_hi < 0) else "no"
        print(f"  ATM Put/Call Volume Ratio:")
        print(f"    PIVOT:  mean={mean(pivot_pc_ratio):.3f}  std={stdev(pivot_pc_ratio):.3f}")
        print(f"    CONT:   mean={mean(cont_pc_ratio):.3f}  std={stdev(cont_pc_ratio):.3f}")
        print(f"    Cohen's d={d_val:.3f}  CI=[{ci_lo:.3f}, {ci_hi:.3f}]  Signal={signal}")
        print()

    # Total volume comparison (all trades in window)
    pivot_total_vol = [d["all"]["_vol"] for d in pivot_segmented if d.get("all")]
    cont_total_vol = [d["all"]["_vol"] for d in cont_segmented if d.get("all")]
    if len(pivot_total_vol) >= 3 and len(cont_total_vol) >= 3:
        d_val = cohens_d(pivot_total_vol, cont_total_vol)
        ci_lo, ci_hi = bootstrap_ci(pivot_total_vol, cont_total_vol)
        signal = "YES" if (ci_lo > 0 or ci_hi < 0) else "no"
        print(f"  Total Option Volume in 10min Window:")
        print(f"    PIVOT:  mean={mean(pivot_total_vol):.0f}  std={stdev(pivot_total_vol):.0f}")
        print(f"    CONT:   mean={mean(cont_total_vol):.0f}  std={stdev(cont_total_vol):.0f}")
        print(f"    Cohen's d={d_val:.3f}  CI=[{ci_lo:.3f}, {ci_hi:.3f}]  Signal={signal}")
        print()

    # OTM put volume as fraction of total
    pivot_otm_frac = []
    for d in pivot_segmented:
        otm_vol = d.get("puts_otm", {}).get("_vol", 0) if d.get("puts_otm") else 0
        total = d["all"]["_vol"] if d.get("all") else 0
        if total > 0:
            pivot_otm_frac.append(otm_vol / total)

    cont_otm_frac = []
    for d in cont_segmented:
        otm_vol = d.get("puts_otm", {}).get("_vol", 0) if d.get("puts_otm") else 0
        total = d["all"]["_vol"] if d.get("all") else 0
        if total > 0:
            cont_otm_frac.append(otm_vol / total)

    if len(pivot_otm_frac) >= 3 and len(cont_otm_frac) >= 3:
        d_val = cohens_d(pivot_otm_frac, cont_otm_frac)
        ci_lo, ci_hi = bootstrap_ci(pivot_otm_frac, cont_otm_frac)
        signal = "YES" if (ci_lo > 0 or ci_hi < 0) else "no"
        print(f"  OTM Put Volume Fraction (of total):")
        print(f"    PIVOT:  mean={mean(pivot_otm_frac):.3f}  std={stdev(pivot_otm_frac):.3f}")
        print(f"    CONT:   mean={mean(cont_otm_frac):.3f}  std={stdev(cont_otm_frac):.3f}")
        print(f"    Cohen's d={d_val:.3f}  CI=[{ci_lo:.3f}, {ci_hi:.3f}]  Signal={signal}")
        print()

    # Theta/Vega ratio for ATM puts (proxy for IV level — higher ratio = higher IV)
    pivot_tv_ratio = []
    for d in pivot_segmented:
        pa = d.get("puts_atm")
        if pa and pa.get("vega", 0) != 0:
            pivot_tv_ratio.append(abs(pa["theta"]) / pa["vega"])

    cont_tv_ratio = []
    for d in cont_segmented:
        pa = d.get("puts_atm")
        if pa and pa.get("vega", 0) != 0:
            cont_tv_ratio.append(abs(pa["theta"]) / pa["vega"])

    if len(pivot_tv_ratio) >= 3 and len(cont_tv_ratio) >= 3:
        d_val = cohens_d(pivot_tv_ratio, cont_tv_ratio)
        ci_lo, ci_hi = bootstrap_ci(pivot_tv_ratio, cont_tv_ratio)
        signal = "YES" if (ci_lo > 0 or ci_hi < 0) else "no"
        print(f"  ATM Put |Theta|/Vega Ratio (IV proxy):")
        print(f"    PIVOT:  mean={mean(pivot_tv_ratio):.5f}  std={stdev(pivot_tv_ratio):.5f}")
        print(f"    CONT:   mean={mean(cont_tv_ratio):.5f}  std={stdev(cont_tv_ratio):.5f}")
        print(f"    Cohen's d={d_val:.3f}  CI=[{ci_lo:.5f}, {ci_hi:.5f}]  Signal={signal}")
        print()

    print("=" * 72)
    print("LEGEND:")
    print("  Cohen's d: |d| > 0.2 small, > 0.5 medium, > 0.8 large effect")
    print("  Sig = YES means 95% bootstrap CI on (PIVOT - CONT) excludes zero")
    print("  Positive d = PIVOT > CONTINUATION for that Greek")
    print()
    print("SUMMARY:")
    print("  Look for |d| > 0.5 with Sig=YES — these are actionable separators.")
    print("  With N=13 PIVOT days, power is limited; |d| > 0.5 without significance")
    print("  still suggests a real effect worth validating with more data.")
    print()


if __name__ == "__main__":
    main()
