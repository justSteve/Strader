"""
Scare Dip Catalog — Phase 3 of the post-entry tape study.

Aggregates all intra-recovery pullbacks from the 13 V-day tape profiles.
For each dip, determines what happened after (continuation, consolidation, reversal)
and measures the volume/premium character during the dip vs. the preceding rise.

Usage:
    .venv/bin/python scripts/measurement/scare_dip_catalog.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from collections import defaultdict

STRADER_ROOT = Path("/root/projects/Strader")
PROFILES_DIR = STRADER_ROOT / "data" / "measurement" / "tape_profiles"

CONFIRMED_V_DAYS = [
    '2025-08-11', '2025-09-17', '2025-09-29', '2025-10-13', '2025-10-29',
    '2025-11-17', '2026-01-30', '2026-02-18', '2026-03-30', '2026-04-01',
    '2026-04-08', '2026-05-08', '2026-05-21',
]


def classify_dip_outcome(dip: dict, es_bars: list, trough_minute: int) -> str:
    """Classify what happened after the dip.

    - 'continuation': price exceeded prior high within 10 minutes of dip low
    - 'consolidation': price stayed in range for 10+ min before continuing up
    - 'reversal': price never recovered the prior high before close
    - 'close': dip happened in last 5 minutes, no time to judge
    """
    low_minute = dip["low_minute"]
    start_price = dip["start_price"]
    end_minute = dip.get("end_minute", low_minute)

    if low_minute >= 115:  # 14:55 CT or later
        return "close"

    bar_by_minute = {b["minute"]: b for b in es_bars}

    exceeded_by = None
    for m in range(low_minute + 1, 120):
        bar = bar_by_minute.get(m)
        if bar is None or bar.get("trades", 0) == 0:
            continue
        if bar["high"] > start_price:
            exceeded_by = m - low_minute
            break

    if exceeded_by is None:
        return "reversal"
    elif exceeded_by <= 10:
        return "continuation"
    else:
        return "consolidation"


def compute_dip_volume_context(dip: dict, opra_bars: list, baseline_vol: float = 1.0) -> dict:
    """Measure volume character during and before the dip."""
    bar_by_minute = {b["minute"]: b for b in opra_bars}
    start_m = dip["start_minute"]
    low_m = dip["low_minute"]
    duration = dip["duration_minutes"]

    # Volume during the dip
    dip_vols = []
    dip_premiums = []
    for m in range(start_m, max(low_m + 1, start_m + 1)):
        bar = bar_by_minute.get(m)
        if bar and bar.get("total_volume", 0) > 0:
            dip_vols.append(bar["total_volume"])
            dip_premiums.append(bar.get("total_premium_usd", 0))

    # Volume in the 5 minutes before the dip
    pre_vols = []
    pre_premiums = []
    for m in range(max(0, start_m - 5), start_m):
        bar = bar_by_minute.get(m)
        if bar and bar.get("total_volume", 0) > 0:
            pre_vols.append(bar["total_volume"])
            pre_premiums.append(bar.get("total_premium_usd", 0))

    # Volume ratio during dip vs before
    dip_avg = statistics.mean(dip_vols) if dip_vols else 0
    pre_avg = statistics.mean(pre_vols) if pre_vols else 0
    vol_ratio = dip_avg / pre_avg if pre_avg > 0 else 0

    # Time-normalized volume during dip
    dip_ratios = []
    for m in range(start_m, max(low_m + 1, start_m + 1)):
        bar = bar_by_minute.get(m)
        if bar and bar.get("volume_ratio", 0) > 0:
            dip_ratios.append(bar["volume_ratio"])

    # P/C ratio during dip
    dip_pc = []
    for m in range(start_m, max(low_m + 1, start_m + 1)):
        bar = bar_by_minute.get(m)
        if bar and bar.get("pc_ratio", 0) > 0 and bar["pc_ratio"] < 50:
            dip_pc.append(bar["pc_ratio"])

    return {
        "dip_avg_volume": round(dip_avg, 0),
        "pre_avg_volume": round(pre_avg, 0),
        "volume_ratio_dip_vs_pre": round(vol_ratio, 3),
        "dip_avg_time_normalized_ratio": round(statistics.mean(dip_ratios), 3) if dip_ratios else 0,
        "dip_avg_pc_ratio": round(statistics.mean(dip_pc), 3) if dip_pc else 0,
        "dip_total_premium_usd": round(sum(dip_premiums), 0),
    }


def main():
    all_dips = []
    day_summaries = []

    for date_str in CONFIRMED_V_DAYS:
        profile_path = PROFILES_DIR / f"tape_{date_str}.json"
        if not profile_path.exists():
            continue
        with open(profile_path) as f:
            profile = json.load(f)

        trough_minute = profile["trough_minute"]
        es_bars = profile["es_1min"]
        opra_bars = profile["opra_1min"]
        depth = profile["depth_pts"]
        recovery = profile["recovery_pts"]

        for i, dip in enumerate(profile["scare_dips"]):
            outcome = classify_dip_outcome(dip, es_bars, trough_minute)
            vol_context = compute_dip_volume_context(dip, opra_bars)

            # Context within the recovery
            minutes_since_trough = dip["start_minute"] - trough_minute
            pct_of_time_to_close = minutes_since_trough / (120 - trough_minute) * 100

            record = {
                "date": date_str,
                "dip_index": i + 1,
                "depth_pts": dip["depth_pts"],
                "depth_pct_of_recovery": dip["depth_pct_of_recovery"],
                "duration_minutes": dip["duration_minutes"],
                "start_minute": dip["start_minute"],
                "low_minute": dip["low_minute"],
                "minutes_since_trough": minutes_since_trough,
                "pct_of_time_to_close": round(pct_of_time_to_close, 1),
                "recovery_so_far_pts": dip["recovery_so_far_pts"],
                "day_depth_pts": depth,
                "day_recovery_pts": recovery,
                "outcome": outcome,
                **vol_context,
            }
            all_dips.append(record)

        day_summaries.append({
            "date": date_str,
            "depth_pts": depth,
            "recovery_pts": recovery,
            "dip_count": len(profile["scare_dips"]),
            "trough_minute": trough_minute,
        })

    # Classify dips into severity tiers
    minor_dips = [d for d in all_dips if d["depth_pts"] < 5]
    moderate_dips = [d for d in all_dips if 5 <= d["depth_pts"] < 10]
    major_dips = [d for d in all_dips if d["depth_pts"] >= 10]

    print(f"{'='*80}")
    print(f"  SCARE DIP CATALOG — {len(all_dips)} dips across {len(day_summaries)} V-days")
    print(f"{'='*80}")
    print()

    # Overall statistics
    depths = [d["depth_pts"] for d in all_dips]
    durations = [d["duration_minutes"] for d in all_dips]
    print(f"  OVERALL STATISTICS")
    print(f"    Total dips (>2pt threshold): {len(all_dips)}")
    print(f"    Per day: mean={len(all_dips)/len(day_summaries):.1f}, range={min(d['dip_count'] for d in day_summaries)}-{max(d['dip_count'] for d in day_summaries)}")
    print(f"    Depth: mean={statistics.mean(depths):.1f}pts, median={statistics.median(depths):.1f}pts, max={max(depths):.1f}pts")
    print(f"    Duration: mean={statistics.mean(durations):.1f}min, median={statistics.median(durations):.0f}min, max={max(durations)}min")
    print()

    # Severity tiers
    print(f"  SEVERITY TIERS")
    for label, group in [("Minor (<5pts)", minor_dips), ("Moderate (5-10pts)", moderate_dips), ("Major (≥10pts)", major_dips)]:
        if not group:
            print(f"    {label}: 0 dips")
            continue
        outcomes = defaultdict(int)
        for d in group:
            outcomes[d["outcome"]] += 1
        total = len(group)
        print(f"    {label}: {total} dips")
        print(f"      Depth: mean={statistics.mean([d['depth_pts'] for d in group]):.1f}pts, max={max(d['depth_pts'] for d in group):.1f}pts")
        print(f"      Duration: mean={statistics.mean([d['duration_minutes'] for d in group]):.1f}min")
        print(f"      Outcomes: {', '.join(f'{k}={v} ({v/total*100:.0f}%)' for k, v in sorted(outcomes.items()))}")
        vol_ratios = [d["volume_ratio_dip_vs_pre"] for d in group if d["volume_ratio_dip_vs_pre"] > 0]
        if vol_ratios:
            print(f"      Vol during dip vs. pre-dip: mean={statistics.mean(vol_ratios):.2f}x, median={statistics.median(vol_ratios):.2f}x")
    print()

    # Outcome analysis
    print(f"  OUTCOME ANALYSIS")
    outcome_groups = defaultdict(list)
    for d in all_dips:
        outcome_groups[d["outcome"]].append(d)
    for outcome in ["continuation", "consolidation", "reversal", "close"]:
        group = outcome_groups.get(outcome, [])
        if not group:
            print(f"    {outcome.upper()}: 0 dips")
            continue
        depths_g = [d["depth_pts"] for d in group]
        durs_g = [d["duration_minutes"] for d in group]
        vol_ratios_g = [d["volume_ratio_dip_vs_pre"] for d in group if d["volume_ratio_dip_vs_pre"] > 0]
        pct_recovery_g = [d["depth_pct_of_recovery"] for d in group]
        mins_since_g = [d["minutes_since_trough"] for d in group]
        print(f"    {outcome.upper()}: {len(group)} dips ({len(group)/len(all_dips)*100:.0f}%)")
        print(f"      Depth: mean={statistics.mean(depths_g):.1f}pts, median={statistics.median(depths_g):.1f}pts")
        print(f"      Duration: mean={statistics.mean(durs_g):.1f}min, median={statistics.median(durs_g):.0f}min")
        print(f"      % of recovery-so-far: mean={statistics.mean(pct_recovery_g):.0f}%, median={statistics.median(pct_recovery_g):.0f}%")
        if vol_ratios_g:
            print(f"      Vol during vs. pre: mean={statistics.mean(vol_ratios_g):.2f}x, median={statistics.median(vol_ratios_g):.2f}x")
        print(f"      Minutes since trough: mean={statistics.mean(mins_since_g):.0f}, median={statistics.median(mins_since_g):.0f}")
    print()

    # Temporal distribution
    print(f"  TEMPORAL DISTRIBUTION (minutes since trough)")
    time_buckets = {"0-5min": [], "5-15min": [], "15-30min": [], "30-60min": [], "60+min": []}
    for d in all_dips:
        m = d["minutes_since_trough"]
        if m <= 5:
            time_buckets["0-5min"].append(d)
        elif m <= 15:
            time_buckets["5-15min"].append(d)
        elif m <= 30:
            time_buckets["15-30min"].append(d)
        elif m <= 60:
            time_buckets["30-60min"].append(d)
        else:
            time_buckets["60+min"].append(d)

    for label, group in time_buckets.items():
        if not group:
            print(f"    {label}: 0 dips")
            continue
        outcomes = defaultdict(int)
        for d in group:
            outcomes[d["outcome"]] += 1
        total = len(group)
        avg_depth = statistics.mean([d["depth_pts"] for d in group])
        print(f"    {label}: {total} dips, avg depth {avg_depth:.1f}pts — "
              f"{', '.join(f'{k}:{v}' for k, v in sorted(outcomes.items()))}")
    print()

    # Volume signature comparison: continuation vs reversal
    cont_dips = outcome_groups.get("continuation", [])
    rev_dips = outcome_groups.get("reversal", [])
    if cont_dips and rev_dips:
        print(f"  CONTINUATION vs REVERSAL — Volume Signature")
        cont_vr = [d["volume_ratio_dip_vs_pre"] for d in cont_dips if d["volume_ratio_dip_vs_pre"] > 0]
        rev_vr = [d["volume_ratio_dip_vs_pre"] for d in rev_dips if d["volume_ratio_dip_vs_pre"] > 0]
        if cont_vr and rev_vr:
            cont_mean = statistics.mean(cont_vr)
            rev_mean = statistics.mean(rev_vr)
            # Cohen's d
            n1, n2 = len(cont_vr), len(rev_vr)
            if n1 >= 2 and n2 >= 2:
                s1, s2 = statistics.stdev(cont_vr), statistics.stdev(rev_vr)
                pooled = ((s1**2 * (n1-1) + s2**2 * (n2-1)) / (n1+n2-2)) ** 0.5
                d_val = (cont_mean - rev_mean) / pooled if pooled > 0 else 0
                print(f"    Continuation dip vol ratio: mean={cont_mean:.2f}x (n={n1})")
                print(f"    Reversal dip vol ratio: mean={rev_mean:.2f}x (n={n2})")
                print(f"    Cohen's d: {d_val:.3f}")
            else:
                print(f"    Continuation: mean={cont_mean:.2f}x (n={n1})")
                print(f"    Reversal: mean={rev_mean:.2f}x (n={n2})")
                print(f"    (insufficient n for effect size)")

        cont_depth = [d["depth_pts"] for d in cont_dips]
        rev_depth = [d["depth_pts"] for d in rev_dips]
        n1, n2 = len(cont_depth), len(rev_depth)
        if n1 >= 2 and n2 >= 2:
            s1, s2 = statistics.stdev(cont_depth), statistics.stdev(rev_depth)
            pooled = ((s1**2 * (n1-1) + s2**2 * (n2-1)) / (n1+n2-2)) ** 0.5
            d_val = (statistics.mean(cont_depth) - statistics.mean(rev_depth)) / pooled if pooled > 0 else 0
            print(f"    Continuation depth: mean={statistics.mean(cont_depth):.1f}pts")
            print(f"    Reversal depth: mean={statistics.mean(rev_depth):.1f}pts")
            print(f"    Cohen's d (depth): {d_val:.3f}")

        cont_dur = [d["duration_minutes"] for d in cont_dips]
        rev_dur = [d["duration_minutes"] for d in rev_dips]
        if len(cont_dur) >= 2 and len(rev_dur) >= 2:
            s1, s2 = statistics.stdev(cont_dur), statistics.stdev(rev_dur)
            pooled = ((s1**2 * (len(cont_dur)-1) + s2**2 * (len(rev_dur)-1)) / (len(cont_dur)+len(rev_dur)-2)) ** 0.5
            d_val = (statistics.mean(cont_dur) - statistics.mean(rev_dur)) / pooled if pooled > 0 else 0
            print(f"    Continuation duration: mean={statistics.mean(cont_dur):.1f}min")
            print(f"    Reversal duration: mean={statistics.mean(rev_dur):.1f}min")
            print(f"    Cohen's d (duration): {d_val:.3f}")
    print()

    # Top 10 most significant dips
    print(f"  TOP 10 DEEPEST DIPS")
    sorted_dips = sorted(all_dips, key=lambda d: d["depth_pts"], reverse=True)
    print(f"    {'Date':>10}  {'Depth':>6}  {'Dur':>4}  {'%Rec':>5}  {'T+':>4}  {'VolR':>5}  {'Outcome':>14}")
    for d in sorted_dips[:10]:
        vr = f"{d['volume_ratio_dip_vs_pre']:.2f}" if d['volume_ratio_dip_vs_pre'] > 0 else "n/a"
        print(f"    {d['date']:>10}  {d['depth_pts']:>5.1f}p  {d['duration_minutes']:>3}m  "
              f"{d['depth_pct_of_recovery']:>4.0f}%  {d['minutes_since_trough']:>3}m  {vr:>5}  {d['outcome']:>14}")

    # Save full catalog
    output_path = STRADER_ROOT / "data" / "measurement" / "scare_dip_catalog.jsonl"
    with open(output_path, "w") as f:
        for d in all_dips:
            f.write(json.dumps(d) + "\n")
    print(f"\n  Wrote {len(all_dips)} dips to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
