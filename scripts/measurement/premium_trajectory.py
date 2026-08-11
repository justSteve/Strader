"""
Premium Trajectory Atlas — Phase 5 of the post-entry tape study.

For each V-day, tracks option premium minute-by-minute from trough to close.
Uses ATM 0DTE calls as the representative directional trade (closest strike
above trough price, 0DTE expiry).

Computes:
- Premium curve from trough to close
- Entry premium (at trough+5min to model confirmation wait)
- Peak premium and when it occurred
- Max drawdown during the hold
- Premium at close vs. entry (the profit multiple)
- The "regret curve": % of final premium captured at each minute

Usage:
    .venv/bin/python scripts/measurement/premium_trajectory.py
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, date as _date
from zoneinfo import ZoneInfo

STRADER_ROOT = Path("/root/projects/Strader")
DATA_DIR = STRADER_ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
MEASUREMENT_DIR = DATA_DIR / "measurement"
PROFILES_DIR = MEASUREMENT_DIR / "tape_profiles"

CENTRAL = ZoneInfo("America/Chicago")

CONFIRMED_V_DAYS = [
    '2025-08-11', '2025-09-17', '2025-09-29', '2025-10-13', '2025-10-29',
    '2025-11-17', '2026-01-30', '2026-02-18', '2026-03-30', '2026-04-01',
    '2026-04-08', '2026-05-08', '2026-05-21',
]


def parse_iso_timestamp(ts_str: str) -> datetime:
    if "." in ts_str:
        base, frac_and_tz = ts_str.split(".", 1)
        frac = ""
        tz_part = ""
        i = 0
        while i < len(frac_and_tz) and frac_and_tz[i].isdigit():
            frac += frac_and_tz[i]
            i += 1
        tz_part = frac_and_tz[i:]
        frac = frac[:6].ljust(6, "0")
        ts_str = f"{base}.{frac}{tz_part}"
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def parse_occ_symbol(symbol: str) -> dict | None:
    symbol = symbol.strip()
    if len(symbol) < 21:
        return None
    try:
        root = symbol[:6].strip()
        exp_str = symbol[6:12]
        pc = symbol[12]
        strike_str = symbol[13:21]
        expiry = datetime.strptime(exp_str, "%y%m%d").date()
        strike = int(strike_str) / 1000.0
        return {"root": root, "expiry": expiry, "pc": pc, "strike": strike}
    except (ValueError, IndexError):
        return None


def build_premium_curve(opra_path: Path, trade_date: _date,
                        target_strikes: list[float],
                        start_minute: int, end_minute: int) -> dict[str, dict[int, dict]]:
    """Build minute-by-minute premium data for specific 0DTE strikes.

    Returns: {strike_key: {minute: {last_price, vwap, volume, trade_count}}}
    """
    curves = defaultdict(lambda: defaultdict(lambda: {"prices": [], "sizes": []}))

    with open(opra_path) as f:
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

            ct = ts.astimezone(CENTRAL)
            m = (ct.hour - 13) * 60 + ct.minute
            if m < start_minute or m > end_minute:
                continue

            data = rec.get("data", {})
            symbol = data.get("symbol", "")
            if not symbol.startswith("SPXW"):
                continue

            size = data.get("size", 0)
            price = data.get("price", 0.0)
            if size <= 0 or price <= 0:
                continue

            parsed = parse_occ_symbol(symbol)
            if parsed is None:
                continue

            dte = (parsed["expiry"] - trade_date).days
            if dte != 0:
                continue

            strike = parsed["strike"]
            pc = parsed["pc"]
            if pc != "C":
                continue
            if strike not in target_strikes:
                continue

            key = f"C{strike:.0f}"
            curves[key][m]["prices"].append(price)
            curves[key][m]["sizes"].append(size)

    result = {}
    for key in curves:
        result[key] = {}
        for m in sorted(curves[key]):
            prices = curves[key][m]["prices"]
            sizes = curves[key][m]["sizes"]
            total_size = sum(sizes)
            vwap = sum(p * s for p, s in zip(prices, sizes)) / total_size if total_size > 0 else 0
            result[key][m] = {
                "last_price": prices[-1],
                "vwap": round(vwap, 4),
                "volume": total_size,
                "trade_count": len(prices),
            }
    return result


def analyze_premium_curve(curve: dict[int, dict], entry_minute: int,
                          close_minute: int = 119) -> dict | None:
    """Analyze a single strike's premium curve from entry to close."""
    sorted_minutes = sorted(curve.keys())
    if not sorted_minutes:
        return None

    # Find entry price: VWAP at entry_minute, or first available after
    entry_price = None
    entry_m = None
    for m in sorted_minutes:
        if m >= entry_minute:
            entry_price = curve[m]["vwap"]
            entry_m = m
            break
    if entry_price is None or entry_price <= 0:
        return None

    # Track premium through time
    trajectory = []
    running_high = entry_price
    running_high_m = entry_m
    max_drawdown_pct = 0.0
    max_drawdown_from_m = entry_m
    max_drawdown_to_m = entry_m

    for m in sorted_minutes:
        if m < entry_m:
            continue
        price = curve[m]["vwap"]
        if price <= 0:
            continue
        pnl_from_entry = (price - entry_price) / entry_price * 100
        multiple = price / entry_price

        if price > running_high:
            running_high = price
            running_high_m = m

        dd_from_high = (running_high - price) / running_high * 100 if running_high > 0 else 0
        if dd_from_high > max_drawdown_pct:
            max_drawdown_pct = dd_from_high
            max_drawdown_from_m = running_high_m
            max_drawdown_to_m = m

        ct_hour = 13 + m // 60
        ct_min = m % 60
        trajectory.append({
            "minute": m,
            "time_ct": f"{ct_hour:02d}:{ct_min:02d}",
            "price": price,
            "multiple": round(multiple, 3),
            "pnl_pct": round(pnl_from_entry, 1),
            "drawdown_from_high_pct": round(dd_from_high, 1),
        })

    if not trajectory:
        return None

    # Find close premium (last available)
    close_price = trajectory[-1]["price"]
    close_multiple = trajectory[-1]["multiple"]

    # Find peak
    peak = max(trajectory, key=lambda t: t["price"])

    # Regret curve: at each minute, what % of final gain have you captured?
    final_gain = close_price - entry_price
    regret_milestones = {}
    if final_gain > 0:
        for t in trajectory:
            gain_so_far = t["price"] - entry_price
            pct_of_final = gain_so_far / final_gain * 100
            mins_since_entry = t["minute"] - entry_m
            for target_pct in [25, 50, 75, 90]:
                if target_pct not in regret_milestones and pct_of_final >= target_pct:
                    regret_milestones[target_pct] = mins_since_entry

    return {
        "entry_minute": entry_m,
        "entry_price": round(entry_price, 2),
        "close_price": round(close_price, 2),
        "close_multiple": round(close_multiple, 3),
        "peak_price": round(peak["price"], 2),
        "peak_minute": peak["minute"],
        "peak_multiple": round(peak["price"] / entry_price, 3),
        "max_drawdown_pct": round(max_drawdown_pct, 1),
        "max_drawdown_from_minute": max_drawdown_from_m,
        "max_drawdown_to_minute": max_drawdown_to_m,
        "minutes_to_25pct_of_final": regret_milestones.get(25),
        "minutes_to_50pct_of_final": regret_milestones.get(50),
        "minutes_to_75pct_of_final": regret_milestones.get(75),
        "minutes_to_90pct_of_final": regret_milestones.get(90),
        "trajectory": trajectory,
    }


def main():
    results = []
    # Skips are tracked by reason and reported. Since st-7av4 stopped the daily
    # OPRA import (2026-08-07), the tape is pulled on demand for selected
    # sessions, so a partially-populated date range is the normal case. Dropping
    # days silently would let every statistic below be computed over an unnamed
    # subset while reading as the full study.
    missing_profile: list[str] = []
    missing_opra: list[str] = []

    for date_str in CONFIRMED_V_DAYS:
        profile_path = PROFILES_DIR / f"tape_{date_str}.json"
        if not profile_path.exists():
            missing_profile.append(date_str)
            continue
        with open(profile_path) as f:
            profile = json.load(f)

        corpus_path = CORPUS_DIR / date_str
        opra_path = corpus_path / "databento_opra.jsonl"
        if not opra_path.exists():
            missing_opra.append(date_str)
            continue

        trough_minute = profile["trough_minute"]
        trough_price = profile["trough_price"]
        trade_date = _date.fromisoformat(date_str)

        # Select strikes: ATM call and ±5, ±10 around trough price
        atm_strike = round(trough_price / 5) * 5
        strikes_to_track = []
        for offset in [-10, -5, 0, 5, 10, 15, 20]:
            strikes_to_track.append(atm_strike + offset)

        # Entry at trough + 5min (confirmation wait)
        entry_minute = trough_minute + 5

        print(f"\n{'='*72}", file=sys.stderr)
        print(f"  {date_str} — trough {trough_price:.0f} @ min {trough_minute}, "
              f"ATM strike {atm_strike}", file=sys.stderr)

        curves = build_premium_curve(opra_path, trade_date, strikes_to_track,
                                     trough_minute - 2, 120)

        day_result = {
            "date": date_str,
            "trough_minute": trough_minute,
            "trough_price": trough_price,
            "close_price": profile["close_price"],
            "depth_pts": profile["depth_pts"],
            "recovery_pts": profile["recovery_pts"],
            "atm_strike": atm_strike,
            "entry_minute": entry_minute,
            "strikes": {},
        }

        best_strike = None
        best_multiple = 0

        for key in sorted(curves.keys()):
            analysis = analyze_premium_curve(curves[key], entry_minute)
            if analysis is None:
                continue

            strike_val = float(key.replace("C", ""))
            otm_distance = strike_val - trough_price

            day_result["strikes"][key] = {
                "strike": strike_val,
                "otm_distance_at_trough": round(otm_distance, 1),
                **{k: v for k, v in analysis.items() if k != "trajectory"},
                "trajectory_points": len(analysis["trajectory"]),
            }

            if analysis["close_multiple"] > best_multiple:
                best_multiple = analysis["close_multiple"]
                best_strike = key

            print(f"  {key}: entry ${analysis['entry_price']:.2f} → close ${analysis['close_price']:.2f} "
                  f"({analysis['close_multiple']:.1f}x) | peak ${analysis['peak_price']:.2f} "
                  f"({analysis['peak_multiple']:.1f}x) | maxDD {analysis['max_drawdown_pct']:.0f}%",
                  file=sys.stderr)

        if best_strike:
            day_result["best_strike"] = best_strike
            day_result["best_close_multiple"] = best_multiple

        results.append(day_result)

    # Coverage first, and on stderr, so a partial run cannot be mistaken for a
    # full one no matter how the stdout table is piped or pasted.
    total = len(CONFIRMED_V_DAYS)
    if missing_profile or missing_opra:
        print(f"\n[coverage] {len(results)}/{total} V-days processed", file=sys.stderr)
        if missing_opra:
            print(f"  {len(missing_opra)} skipped — no OPRA tape "
                  f"(on-demand since st-7av4): {', '.join(missing_opra)}",
                  file=sys.stderr)
        if missing_profile:
            print(f"  {len(missing_profile)} skipped — no tape profile: "
                  f"{', '.join(missing_profile)}", file=sys.stderr)

    if not results:
        print(f"[FAIL] no V-day had both a tape profile and an OPRA tape; "
              f"{total} candidates, none usable. Pull the tape with "
              f"corpus_backfill_databento.py --opra before rerunning.",
              file=sys.stderr)
        return 1

    # Cross-day summary
    print(f"\n{'='*72}")
    print(f"  PREMIUM TRAJECTORY ATLAS — {len(results)} of {total} V-days")
    print(f"{'='*72}\n")

    # For each day, show the best-performing strike (the one a trader would have picked)
    print(f"  BEST-STRIKE SUMMARY (ATM 0DTE call with highest close multiple)")
    print(f"  {'Date':>10}  {'Trgh':>6}  {'Strike':>7}  {'OTM':>5}  {'Entry':>6}  {'Close':>6}  "
          f"{'Mult':>5}  {'Peak':>6}  {'PkMult':>6}  {'MaxDD':>5}  {'T→50%':>5}  {'T→75%':>5}")

    multiples = []
    max_dds = []
    t50s = []
    t75s = []

    for r in results:
        if "best_strike" not in r:
            continue
        s = r["strikes"][r["best_strike"]]
        multiples.append(s["close_multiple"])
        max_dds.append(s["max_drawdown_pct"])
        t50 = s.get("minutes_to_50pct_of_final")
        t75 = s.get("minutes_to_75pct_of_final")
        if t50 is not None:
            t50s.append(t50)
        if t75 is not None:
            t75s.append(t75)

        t50_str = f"{t50:>4}m" if t50 is not None else "  n/a"
        t75_str = f"{t75:>4}m" if t75 is not None else "  n/a"
        print(f"  {r['date']:>10}  {r['trough_price']:>6.0f}  {r['best_strike']:>7}  "
              f"{s['otm_distance_at_trough']:>4.0f}p  ${s['entry_price']:>5.2f}  ${s['close_price']:>5.2f}  "
              f"{s['close_multiple']:>5.1f}x  ${s['peak_price']:>5.2f}  {s['peak_multiple']:>5.1f}x  "
              f"{s['max_drawdown_pct']:>4.0f}%  {t50_str}  {t75_str}")

    if multiples:
        print(f"\n  STATISTICS")
        print(f"    Close multiple: mean={statistics.mean(multiples):.1f}x, "
              f"median={statistics.median(multiples):.1f}x, "
              f"range={min(multiples):.1f}-{max(multiples):.1f}x")
        print(f"    Max drawdown: mean={statistics.mean(max_dds):.0f}%, "
              f"median={statistics.median(max_dds):.0f}%, "
              f"max={max(max_dds):.0f}%")
        if t50s:
            print(f"    Time to 50% of final gain: mean={statistics.mean(t50s):.0f}min, "
                  f"median={statistics.median(t50s):.0f}min")
        if t75s:
            print(f"    Time to 75% of final gain: mean={statistics.mean(t75s):.0f}min, "
                  f"median={statistics.median(t75s):.0f}min")

    # OTM strike analysis: how do slightly OTM calls perform?
    print(f"\n  OTM DISTANCE ANALYSIS (which strike offset performs best?)")
    by_offset = defaultdict(list)
    for r in results:
        for key, s in r["strikes"].items():
            otm = s["otm_distance_at_trough"]
            if s["entry_price"] > 0 and s["close_multiple"] > 0:
                bucket = round(otm / 5) * 5
                by_offset[bucket].append(s["close_multiple"])

    print(f"  {'OTM':>6}  {'Count':>5}  {'Mean Mult':>9}  {'Median':>7}  {'Range':>12}")
    for offset in sorted(by_offset.keys()):
        vals = by_offset[offset]
        if len(vals) < 3:
            continue
        print(f"  {offset:>+5}p  {len(vals):>5}  {statistics.mean(vals):>9.1f}x  "
              f"{statistics.median(vals):>6.1f}x  {min(vals):.1f}-{max(vals):.1f}x")

    # Save results
    output_path = MEASUREMENT_DIR / "premium_trajectories.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Wrote {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
