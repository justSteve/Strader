---
type: measurement
title: Orderflow spike thresholds — calibrated from the 1 Hz archive
description: Per-metric absolute-value percentiles for the six GexBot oflow fields, replacing the ad-hoc 100MM line with cited numbers.
timestamp: 2026-08-11T14:49:48Z
bead: st-pz3r
---

# Orderflow Spike Thresholds

## What this replaces

Live reads had been calling an oflow move "meaningful" against an ad-hoc 100MM line that nobody measured. These are the measured distributions. An adjective in a read now cites a percentile or it does not get used.

## Sampling — why only the 1 Hz days calibrate

**Primary (1 Hz):** 2026-08-10 — 13,793 distinct vendor snapshots inside RTH (08:30–15:00 CT) after deduplicating repeated vendor timestamps.

**Cross-check (~60s):** 2026-05-22, 2026-06-08, 2026-06-09, 2026-08-05, 2026-08-06, 2026-08-07, 2026-08-08, 2026-08-09 — same vendor field, but roughly one snapshot in sixty is observed. Used only to ask whether the 1 Hz days were a typical regime, never pooled into the thresholds.

### Feed coverage

The 1 Hz feed has **8 gaps** wider than 5 seconds across the calibration session, 150s missing in total — **99.2% coverage**. The worst is 82s at 2026-08-10T14:32:22+00:00. Small enough not to move the percentiles, but it is the reason the phase sweep below is anchored to the wall clock rather than chained from the previous sample: one gap wider than the offset resynchronises every downstream pick, and a chained sweep would have reported near-zero spread while actually measuring nothing.

### What the old 60s cadence could not have told us

A subsample's percentile is a *noisy* estimate of the full population's, not a systematically low one — so the useful question is not how far 60s undershoots, but how far apart two equally legitimate 60s pollers land. The 1 Hz day was decimated at 20 different phase offsets (~328 snapshots each, against 13,793 at 1 Hz) and the same percentiles recomputed. The range is the answer:

| metric | p95 (1 Hz) | p95 range across 60s phases | p99 (1 Hz) | p99 range across 60s phases |
|---|---|---|---|---|
| dexoflow | 25.16 | 19.63 – 29.84 (22% off) | 49.37 | 33.94 – 78.70 (59% off) |
| gexoflow | 531.15 | 368.02 – 622.09 (31% off) | 1,378 | 771.99 – 1,715 (44% off) |
| cvroflow | 533.01 | 358.12 – 611.44 (33% off) | 1,383 | 767.79 – 1,663 (45% off) |
| one_dexoflow | 4.62 | 3.41 – 6.10 (32% off) | 14.16 | 6.63 – 45.85 (224% off) |
| one_gexoflow | 8.85 | 6.39 – 11.62 (31% off) | 24.32 | 11.84 – 41.71 (71% off) |
| one_cvroflow | 8.39 | 6.38 – 11.34 (35% off) | 24.33 | 12.61 – 37.30 (53% off) |

Read the right-hand columns as error bars on every number the old poller ever produced. A threshold that moves by tens of percent depending on which second of the minute you sampled is not a threshold — which is why only the 1 Hz archive calibrates.

## These are not six independent metrics

Pearson correlation over the calibration day, pairs at |r| ≥ 0.90:

| pair | r |
|---|---|
| gexoflow vs cvroflow | -0.9945 |

**Consequence for reads:** a mirrored pair carries one observation, not two. Citing both as if they corroborate each other inflates confidence in exactly the situation where it should not move. Pick one of each pair as the reported metric and treat the other as a consistency check — if a mirrored pair ever stops mirroring, *that* divergence is the finding.

## Thresholds

Absolute value. Zero-DTE and one-DTE surfaces are kept separate because their scales differ by roughly two orders of magnitude.

| metric | n | median abs | elevated (p90) | notable (p95) | extreme (p99) |
|---|---|---|---|---|---|
| dexoflow | 13,793 | 4.11 | 17.33 | 25.16 | 49.37 |
| gexoflow | 13,793 | 70.50 | 338.75 | 531.15 | 1,378 |
| cvroflow | 13,793 | 67.75 | 338.19 | 533.01 | 1,383 |
| one_dexoflow | 13,793 | 0.31 | 2.89 | 4.62 | 14.16 |
| one_gexoflow | 13,793 | 0.67 | 5.49 | 8.85 | 24.32 |
| one_cvroflow | 13,793 | 0.65 | 5.31 | 8.39 | 24.33 |

Only **extreme** earns the word *spike*. *Elevated* and *notable* are context, not signal.

These whole-day numbers are the fallback. Where an hourly bucket exists, the hourly threshold below is the one to cite — see the next section for why the difference is large enough to matter.

## By session hour (CT) — the operative thresholds

Magnitude is strongly non-stationary: the same number that is unremarkable at 14:00 is far out in the tail at 09:00. A single whole-day threshold therefore under-flags the morning and over-flags the last hour. p95 of the absolute value, by hour:

| metric | 09:00 | 10:00 | 11:00 | 12:00 | 13:00 | 14:00 |
|---|---|---|---|---|---|---|
| dexoflow | 29.70 | 23.93 | 26.97 | 20.22 | 21.78 | 29.29 |
| gexoflow | 106.55 | 143.37 | 216.94 | 284.98 | 395.60 | 1,396 |
| cvroflow | 98.78 | 134.89 | 210.86 | 280.74 | 406.94 | 1,403 |
| one_dexoflow | 4.45 | 4.22 | 4.77 | 3.64 | 4.01 | 7.22 |
| one_gexoflow | 7.43 | 5.97 | 8.06 | 6.27 | 8.00 | 17.30 |
| one_cvroflow | 6.95 | 6.50 | 8.16 | 5.89 | 7.63 | 14.13 |

Snapshots per hour: 09:00 n=1,047, 10:00 n=2,535, 11:00 n=2,523, 12:00 n=2,589, 13:00 n=2,526, 14:00 n=2,573.

## Regime check — was the calibration day typical?

The 1 Hz day decimated to 60s, compared against the genuine 60s days at the same cadence. Like-for-like sampling, so a large gap means the regime differed, not the instrument:

| day | metric | n | p95 | p99 |
|---|---|---|---|---|
| 2026-08-06 | gexoflow | 301 | 308.38 | 626.01 |
| 2026-08-06 | cvroflow | 301 | 211.22 | 1,143 |
| 2026-08-06 | dexoflow | 301 | 34.79 | 62.49 |
| 2026-08-07 | gexoflow | 301 | 296.26 | 654.09 |
| 2026-08-07 | cvroflow | 301 | 318.25 | 746.53 |
| 2026-08-07 | dexoflow | 301 | 39.28 | 76.23 |
| 2026-08-10+ (1Hz→60s) | gexoflow | 328 | 484.76 | 1,360 |
| 2026-08-10+ (1Hz→60s) | cvroflow | 328 | 480.28 | 1,310 |
| 2026-08-10+ (1Hz→60s) | dexoflow | 328 | 24.98 | 49.32 |

## Known limits

- Calibrated on 1 day(s) of 1 Hz data (2026-08-10). One or two sessions is a thin base for a p99 — re-run as the archive grows and expect the extreme tier to move.
- Percentiles are of the absolute value, so a threshold says a move was large, not which direction it favoured.
- The vendor publishes at roughly 1.3s; polling at 1 Hz still misses nothing observable, but repeated timestamps are deduplicated, so n is below the raw row count.
- Session-hour buckets thin out at the edges — treat an hour with a few hundred snapshots as indicative only.
- Today (2026-08-11) was excluded: a partial session would weight the distribution toward whichever hours have elapsed.
