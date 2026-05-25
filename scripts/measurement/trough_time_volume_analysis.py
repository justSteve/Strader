"""
Trough-Time Volume Analysis — Resolving the timing confound for the d=-1.524 finding.

Key question: Is the volume difference between PIVOT and CONTINUATION days real
(reflects hedging exhaustion) or mechanical (later troughs = more volume)?

Approach:
1. Compute per-minute OPRA volume for ALL 243 corpus days in [13:00, 15:00) CT
2. Build time-of-day expected volume curve from the full corpus
3. For each study day, compute volume_ratio = observed / expected at trough time
4. Compare volume_ratio between PIVOT and CONTINUATION classes

If the ratio differs, the signal is real (not just time-of-day).
If the ratio is ~1.0 for both, the signal is purely mechanical.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

STRADER_ROOT = Path("/root/projects/Strader")
DATA_DIR = STRADER_ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
MEASUREMENT_DIR = DATA_DIR / "measurement"

CONFIRMED_V_DAYS = [
    '2025-08-11', '2025-09-17', '2025-09-29', '2025-10-13', '2025-10-29',
    '2025-11-17', '2026-01-30', '2026-02-18', '2026-03-30', '2026-04-01',
    '2026-04-08', '2026-05-08', '2026-05-21',
]


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp, truncating nanoseconds to microseconds."""
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


def parse_trough_min(ts_str: str) -> float:
    """Parse trough timestamp to minutes since 13:00 CT."""
    dt = datetime.fromisoformat(ts_str)
    return (dt.hour - 13) * 60 + dt.minute + dt.second / 60.0


def count_opra_volume_per_minute(opra_path: Path, window_start_utc: datetime,
                                  window_end_utc: datetime) -> dict[int, int]:
    """Count SPXW option contract volume per CT-minute in [start, end).

    Returns dict mapping minute-since-13:00-CT -> total contracts.
    """
    minute_vol = {}
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
            if ts >= window_end_utc:
                break

            data = rec.get("data", {})
            symbol = data.get("symbol", "")
            if not symbol.startswith("SPXW"):
                continue
            size = data.get("size", 0)
            if size <= 0:
                continue

            # Convert to CT (UTC-5 during CDT, UTC-6 during CST)
            # The trough_t field has the offset embedded; we'll use UTC offset -5 for CDT
            # The corpus spans May 2025 - May 2026, all CDT or CST
            # CDT: March-November, CST: November-March
            # For minute binning, we use the event's own timezone info
            ct = ts.astimezone(timezone(timedelta(hours=-5)))
            minute_since_1300 = (ct.hour - 13) * 60 + ct.minute

            if 0 <= minute_since_1300 < 120:  # [13:00, 15:00) CT
                minute_vol[minute_since_1300] = minute_vol.get(minute_since_1300, 0) + size

    return minute_vol


def load_v_days():
    """Load v_days.jsonl and return list of dicts."""
    with open(MEASUREMENT_DIR / "v_days.jsonl") as f:
        return [json.loads(l) for l in f]


def cohen_d(group1, group2):
    """Compute Cohen's d (pooled SD)."""
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return float('nan')
    m1, m2 = statistics.mean(group1), statistics.mean(group2)
    s1, s2 = statistics.stdev(group1), statistics.stdev(group2)
    pooled = ((s1**2 * (n1 - 1) + s2**2 * (n2 - 1)) / (n1 + n2 - 2)) ** 0.5
    if pooled == 0:
        return float('nan')
    return (m1 - m2) / pooled


def bootstrap_ci(group1, group2, n_boot=5000, alpha=0.05):
    """Bootstrap CI for difference of means."""
    diffs = []
    for _ in range(n_boot):
        s1 = random.choices(group1, k=len(group1))
        s2 = random.choices(group2, k=len(group2))
        diffs.append(statistics.mean(s1) - statistics.mean(s2))
    diffs.sort()
    lo = diffs[int(n_boot * alpha / 2)]
    hi = diffs[int(n_boot * (1 - alpha / 2))]
    return lo, hi


def permutation_test(group1, group2, n_perm=10000):
    """Two-sided permutation test for difference of means."""
    observed = abs(statistics.mean(group1) - statistics.mean(group2))
    combined = group1 + group2
    n1 = len(group1)
    count = 0
    for _ in range(n_perm):
        random.shuffle(combined)
        d = abs(statistics.mean(combined[:n1]) - statistics.mean(combined[n1:]))
        if d >= observed:
            count += 1
    return count / n_perm


def main():
    random.seed(42)
    days = load_v_days()
    confirmed_set = set(CONFIRMED_V_DAYS)

    # Build study populations
    pivots = []
    neg_a = []
    for d in days:
        vd = d.get('v_down', {})
        crit = vd.get('criteria', {})
        if d['date'] in confirmed_set:
            pivots.append(d)
        elif crit.get('depth_ok') and not crit.get('recovery_ok'):
            neg_a.append(d)

    print(f"PIVOT: n={len(pivots)}, Neg-A: n={len(neg_a)}")

    # ================================================================
    # STEP 1: Compute per-minute volume for ALL corpus days
    # ================================================================
    print("\nStep 1: Computing per-minute OPRA volume across full corpus...")
    print("  (This will take several minutes — scanning ~71M OPRA records)")

    # We only need per-minute volume in [13:00, 15:00) CT
    # UTC window depends on CDT vs CST:
    #   CDT (Mar-Nov): 13:00 CT = 18:00 UTC, 15:00 CT = 20:00 UTC
    #   CST (Nov-Mar): 13:00 CT = 19:00 UTC, 15:00 CT = 21:00 UTC

    corpus_dates = sorted([d.name for d in CORPUS_DIR.iterdir() if d.is_dir()])
    print(f"  Corpus has {len(corpus_dates)} days")

    # For the baseline, compute per-minute mean volume across ALL days
    # For each study day, compute volume in the 10-min pre-trough window
    all_minute_volumes = {}  # minute -> list of volumes across days

    # Track per-day volumes for study days
    study_day_volumes = {}  # date -> {minute: volume}

    study_dates = set(d['date'] for d in pivots + neg_a)

    processed = 0
    skipped = 0

    for date_str in corpus_dates:
        opra_path = CORPUS_DIR / date_str / "databento_opra.jsonl"
        if not opra_path.exists():
            skipped += 1
            continue

        # Determine CDT vs CST
        month = int(date_str[5:7])
        if 3 <= month <= 10:
            # CDT: UTC-5
            utc_start = datetime(int(date_str[:4]), month, int(date_str[8:10]),
                                18, 0, 0, tzinfo=timezone.utc)
            utc_end = datetime(int(date_str[:4]), month, int(date_str[8:10]),
                              20, 0, 0, tzinfo=timezone.utc)
        else:
            # CST: UTC-6
            utc_start = datetime(int(date_str[:4]), month, int(date_str[8:10]),
                                19, 0, 0, tzinfo=timezone.utc)
            utc_end = datetime(int(date_str[:4]), month, int(date_str[8:10]),
                              21, 0, 0, tzinfo=timezone.utc)

        minute_vol = count_opra_volume_per_minute(opra_path, utc_start, utc_end)

        if not minute_vol:
            skipped += 1
            continue

        # Add to baseline
        for m, v in minute_vol.items():
            if m not in all_minute_volumes:
                all_minute_volumes[m] = []
            all_minute_volumes[m].append(v)

        # Track study days
        if date_str in study_dates:
            study_day_volumes[date_str] = minute_vol

        processed += 1
        if processed % 25 == 0:
            print(f"    Processed {processed} days...")

    print(f"  Done: {processed} processed, {skipped} skipped")

    # ================================================================
    # STEP 2: Build time-of-day expected volume curve
    # ================================================================
    print("\nStep 2: Building time-of-day volume baseline...")

    expected_volume = {}  # minute -> mean volume
    for m in range(120):  # 0-119 = 13:00-14:59
        if m in all_minute_volumes and len(all_minute_volumes[m]) > 10:
            expected_volume[m] = statistics.mean(all_minute_volumes[m])
        else:
            expected_volume[m] = 0

    print("  Time-of-day volume curve (5-min buckets):")
    for bucket_start in range(0, 120, 5):
        bucket_end = min(bucket_start + 5, 120)
        bucket_mean = statistics.mean([expected_volume[m] for m in range(bucket_start, bucket_end)])
        t_hr = 13 + bucket_start // 60
        t_min = bucket_start % 60
        bar = "#" * int(bucket_mean / 100)
        print(f"    {t_hr}:{t_min:02d}-{t_hr + (t_min + 5) // 60}:{(t_min + 5) % 60:02d}  {bucket_mean:>8.0f}  {bar}")

    # ================================================================
    # STEP 3: Compute raw and normalized volume for study days
    # ================================================================
    print("\nStep 3: Computing raw and time-normalized pre-trough volume...")

    results = []
    for d in pivots + neg_a:
        date_str = d['date']
        is_pivot = date_str in confirmed_set
        trough_min = parse_trough_min(d['trough_t'])
        trough_minute_int = int(trough_min)

        if date_str not in study_day_volumes:
            print(f"  WARNING: No OPRA data for {date_str}")
            continue

        day_vol = study_day_volumes[date_str]

        # Raw volume in 10-min pre-trough window
        window_start = max(0, trough_minute_int - 10)
        window_end = trough_minute_int
        raw_vol = sum(day_vol.get(m, 0) for m in range(window_start, window_end))

        # Expected volume in that same window (from baseline)
        expected_vol = sum(expected_volume.get(m, 0) for m in range(window_start, window_end))

        # Normalized ratio
        vol_ratio = raw_vol / expected_vol if expected_vol > 0 else float('nan')

        results.append({
            'date': date_str,
            'is_pivot': is_pivot,
            'trough_min': trough_min,
            'raw_vol': raw_vol,
            'expected_vol': expected_vol,
            'vol_ratio': vol_ratio,
        })

    # ================================================================
    # STEP 4: Compare classes
    # ================================================================
    print("\nStep 4: Comparing PIVOT vs CONTINUATION (Neg-A)...")
    print()

    pivot_raw = [r['raw_vol'] for r in results if r['is_pivot']]
    cont_raw = [r['raw_vol'] for r in results if not r['is_pivot']]
    pivot_ratio = [r['vol_ratio'] for r in results if r['is_pivot'] and r['vol_ratio'] == r['vol_ratio']]
    cont_ratio = [r['vol_ratio'] for r in results if not r['is_pivot'] and r['vol_ratio'] == r['vol_ratio']]
    pivot_expected = [r['expected_vol'] for r in results if r['is_pivot']]
    cont_expected = [r['expected_vol'] for r in results if not r['is_pivot']]

    print("=" * 90)
    print("RAW VOLUME (10-min pre-trough, contracts)")
    print("=" * 90)
    print(f"  PIVOT (n={len(pivot_raw)}):       mean={statistics.mean(pivot_raw):>10,.0f}  sd={statistics.stdev(pivot_raw):>10,.0f}")
    print(f"  CONTINUATION (n={len(cont_raw)}): mean={statistics.mean(cont_raw):>10,.0f}  sd={statistics.stdev(cont_raw):>10,.0f}")
    d_raw = cohen_d(pivot_raw, cont_raw)
    p_raw = permutation_test(pivot_raw, cont_raw)
    ci_raw = bootstrap_ci(pivot_raw, cont_raw)
    print(f"  Cohen's d = {d_raw:.3f}")
    print(f"  Permutation p = {p_raw:.4f}")
    print(f"  95% Bootstrap CI on diff: [{ci_raw[0]:,.0f}, {ci_raw[1]:,.0f}]")

    print()
    print("=" * 90)
    print("EXPECTED VOLUME AT TROUGH TIME (time-of-day baseline)")
    print("=" * 90)
    print(f"  PIVOT expected (avg):       {statistics.mean(pivot_expected):>10,.0f} contracts")
    print(f"  CONTINUATION expected (avg): {statistics.mean(cont_expected):>10,.0f} contracts")
    d_expected = cohen_d(pivot_expected, cont_expected)
    print(f"  Cohen's d (expected) = {d_expected:.3f}")
    print(f"  (This measures how much of the raw difference is explained by timing alone)")

    print()
    print("=" * 90)
    print("TIME-NORMALIZED VOLUME RATIO (observed / expected)")
    print("=" * 90)
    print(f"  PIVOT (n={len(pivot_ratio)}):       mean={statistics.mean(pivot_ratio):>6.3f}  sd={statistics.stdev(pivot_ratio):>6.3f}")
    print(f"  CONTINUATION (n={len(cont_ratio)}): mean={statistics.mean(cont_ratio):>6.3f}  sd={statistics.stdev(cont_ratio):>6.3f}")
    d_norm = cohen_d(pivot_ratio, cont_ratio)
    p_norm = permutation_test(pivot_ratio, cont_ratio)
    ci_norm = bootstrap_ci(pivot_ratio, cont_ratio)
    print(f"  Cohen's d = {d_norm:.3f}")
    print(f"  Permutation p = {p_norm:.4f}")
    print(f"  95% Bootstrap CI on diff: [{ci_norm[0]:.3f}, {ci_norm[1]:.3f}]")

    print()
    print("=" * 90)
    print("INTERPRETATION")
    print("=" * 90)
    if abs(d_norm) >= 0.8:
        print(f"  TIME-NORMALIZED d = {d_norm:.3f} (LARGE EFFECT)")
        print(f"  The volume signal SURVIVES time normalization.")
        print(f"  PIVOT days have genuinely {'lower' if d_norm < 0 else 'higher'} volume relative to expectation.")
        signal = "REAL"
    elif abs(d_norm) >= 0.5:
        print(f"  TIME-NORMALIZED d = {d_norm:.3f} (MEDIUM EFFECT)")
        print(f"  The volume signal is PARTIALLY real — attenuated but present after time normalization.")
        signal = "PARTIALLY_REAL"
    elif abs(d_norm) >= 0.2:
        print(f"  TIME-NORMALIZED d = {d_norm:.3f} (SMALL EFFECT)")
        print(f"  The volume signal is MOSTLY MECHANICAL — small residual after time normalization.")
        signal = "MOSTLY_MECHANICAL"
    else:
        print(f"  TIME-NORMALIZED d = {d_norm:.3f} (NEGLIGIBLE)")
        print(f"  The volume signal is ENTIRELY MECHANICAL — disappears with time normalization.")
        signal = "MECHANICAL"

    print()
    print(f"  Raw d = {d_raw:.3f}, Normalized d = {d_norm:.3f}")
    print(f"  Proportion mechanical: {(1 - abs(d_norm) / abs(d_raw)) * 100:.0f}%")
    print(f"  Signal assessment: {signal}")

    # ================================================================
    # STEP 5: Per-day detail table
    # ================================================================
    print()
    print("=" * 90)
    print("PER-DAY DETAIL")
    print("=" * 90)
    print(f"{'Date':<12} {'Class':<6} {'TrMin':>6} {'Raw Vol':>10} {'Expected':>10} {'Ratio':>7}")
    print("-" * 60)
    for r in sorted(results, key=lambda x: (not x['is_pivot'], x['date'])):
        cls = "PIVOT" if r['is_pivot'] else "CONT"
        t_hr = 13 + int(r['trough_min']) // 60
        t_min = int(r['trough_min']) % 60
        print(f"{r['date']:<12} {cls:<6} {t_hr}:{t_min:02d}  {r['raw_vol']:>10,} {r['expected_vol']:>10,.0f} {r['vol_ratio']:>7.3f}")

    # ================================================================
    # STEP 6: Also test against Neg-D (depth+LATR matched, n=13 vs 13)
    # ================================================================
    neg_d_dates = [
        '2025-08-25', '2026-02-13', '2025-09-12', '2026-01-15', '2025-10-14',
        '2026-03-06', '2025-11-05', '2026-01-07', '2026-02-05', '2026-03-27',
        '2026-03-12', '2025-07-10', '2025-10-30',
    ]
    neg_d_set = set(neg_d_dates)

    neg_d_raw = [r['raw_vol'] for r in results if r['date'] in neg_d_set]
    neg_d_ratio = [r['vol_ratio'] for r in results if r['date'] in neg_d_set and r['vol_ratio'] == r['vol_ratio']]

    print()
    print("=" * 90)
    print("NEG-D (depth+LATR matched, n=13) — RAW VOLUME")
    print("=" * 90)
    if neg_d_raw:
        print(f"  PIVOT mean:  {statistics.mean(pivot_raw):>10,.0f}")
        print(f"  Neg-D mean:  {statistics.mean(neg_d_raw):>10,.0f}")
        d_neg_d_raw = cohen_d(pivot_raw, neg_d_raw)
        p_neg_d_raw = permutation_test(pivot_raw, neg_d_raw)
        print(f"  Cohen's d = {d_neg_d_raw:.3f}, perm p = {p_neg_d_raw:.4f}")

    print()
    print("=" * 90)
    print("NEG-D — TIME-NORMALIZED VOLUME")
    print("=" * 90)
    if neg_d_ratio:
        print(f"  PIVOT ratio mean:  {statistics.mean(pivot_ratio):.3f}")
        print(f"  Neg-D ratio mean:  {statistics.mean(neg_d_ratio):.3f}")
        d_neg_d_norm = cohen_d(pivot_ratio, neg_d_ratio)
        p_neg_d_norm = permutation_test(pivot_ratio, neg_d_ratio)
        ci_neg_d = bootstrap_ci(pivot_ratio, neg_d_ratio)
        print(f"  Cohen's d = {d_neg_d_norm:.3f}, perm p = {p_neg_d_norm:.4f}")
        print(f"  95% Bootstrap CI: [{ci_neg_d[0]:.3f}, {ci_neg_d[1]:.3f}]")

    return signal, d_raw, d_norm


if __name__ == "__main__":
    signal, d_raw, d_norm = main()
