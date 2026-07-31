# Internals × Signal Join — does the MI gauge discriminate recognizer confirmations?

**Bead:** st-u05 (Gauge Meets Signal) · **Date:** 2026-07-31
**Signals:** `data/measurement/acuity-run2-confirmations.jsonl`, run `20260731T045133Z`
(423 confirmations, 65 days, 2025-05-29 .. 2026-07-29)
**Internals:** `data/corpus/<day>/internals.jsonl`, `$TICK` minute candles —
37 days, 2026-06-08 .. 2026-07-30, pulled 2026-07-22 .. 2026-07-31
**Gauge:** `market/internals/gauge.py` (`MIGauge`) fed by
`market/internals/feed.py` (`read_tick_day`), replayed in-process — same engine
`scripts/mi_gauge.py --date` drives, no CLI text round-trip
**Join script:** `data/measurement/tmp-st98z/internals_join.py` — every number
below is printed by one run of it; joined rows dumped to `internals_join.jsonl`
**Code:** no changes to `market/` or `scripts/`. Measurement only.

## Question

The recognizer's confirms are a coin flip unfiltered (47% at ±5, run 2). Day
type separates them but is hindsight, and the developing-shape classifier that
was supposed to replace it recalls only 23% of b-days. So: does the MI gauge —
a signal we *can* read live, minute by minute — discriminate confirmation
quality? And does it sharpen the `fire_index>=4` fade?

## Headline

**No. Not on the data that exists.** No gauge cut — band, sign agreement,
driver, or score tercile — moves the ±5 win rate by an amount distinguishable
from day-to-day noise. The fade is not sharpened. The chop-day proxy fails a
permutation test outright. One effect survives, and it is about **trade shape,
not direction**: confirms fired while the gauge reads `climax` reach a
favourable excursion greater than their adverse one only **22%** of the time
versus **54%** elsewhere (day-clustered 95% CI on the difference
**[−55%, −20%]**, the only interval in this study that excludes zero).

Before any of that: the study cannot be validated out-of-sample today, and that
is the finding with the longest shelf life.

## The join is structurally capped — read this first

| | |
|---|---|
| Confirmations in run | **423** |
| Joined to a gauge read | **206** (all exact-minute; zero nearest-prior fallbacks used) |
| Unjoinable — no internals corpus file for the day | **217** |
| Unjoinable — day present but minute absent | **0** |
| Unjoinable — replay failure | **0** |

Joined rows cover **15 days, 2026-07-01 .. 2026-07-29**. The 50 unjoinable days
run 2025-05-29 .. 2026-05-21 and every one of them fails for the same reason:
no `internals.jsonl`. The internals corpus starts 2026-06-08 because Schwab
minute history is a **rolling ~47-day window** (`internals_config.py`), so those
days are not merely un-pulled — they are **unrecoverable**. Backfill is not an
option that exists.

Two consequences, both load-bearing:

1. **The requested tune (<2026-06-01) / validate (>=2026-06-01) split is
   degenerate: tune n=0, validate n=206.** Every joinable row is on the
   validate side. There is no out-of-sample test available, and no amount of
   care in the analysis creates one. Every table below therefore carries a
   substitute **early (<2026-07-16, n=46) / late (>=2026-07-16, n=160)** split.
   That is a within-window consistency check, **not** an out-of-sample
   validation, and nothing in this doc should be read as validated.
2. **n=206 is nowhere near 206 independent observations.** The rows come from
   15 days; 2026-07-29 alone contributes 43 and 2026-07-23 contributes 31 —
   **36% of the sample from two days**. They occupy only 161 distinct minutes
   (30 minutes carry more than one confirmation, up to 5), and in 28 of those
   30 minutes every row shares the same verdict — near-duplicates, not
   evidence. A Fisher test on n=206 badly overstates the evidence here, so
   every contrast below also carries a **day-clustered bootstrap** 95% CI
   (5000 resamples, days drawn with replacement carrying all their rows).
   **Read the CI, not the p.**

Baseline for the joined set: **40%** (81W / 119L, 6 undecided) at ±5 first
touch over 30 minutes — a little below the 47% corpus-wide figure, consistent
with these 15 days being a heavier-tape sample.

## Method

For each confirmation, replay that day's `$TICK` minutes through a fresh
`MIGauge` and take the read whose minute equals the signal's `ct`. Exact-minute
matching succeeded for all 206 joinable rows, so the declared fallback
(nearest-prior within 5 minutes) was never exercised — every internals day
carries exactly 390 minutes (08:30–14:59 CT) with no gaps. Data quality check:
all 37 days contain genuine negative `$TICK` prints, so none of them hit the
clamped-same-day-history failure mode `read_tick_day` warns about.

Win rate is `wins / (wins + losses)` on `verdict30`; undecided rows are
excluded from the rate and reported as `u`. All signals are bullish, so gauge
`score > 0` = agrees with the signal.

## Win-rate cuts — nothing separates

### By gauge band

| Band | n | All | early (<07-16) | late (>=07-16) |
|---|---|---|---|---|
| climax | 55 | 45% (24W/29L, 2u) | 0% (0W/1L) | 46% (24W/28L, 2u) |
| lean | 51 | 42% (20W/28L, 3u) | 70% (7W/3L) | 34% (13W/25L, 3u) |
| neutral | 100 | 37% (37W/62L, 1u) | 34% (12W/23L) | 39% (25W/39L, 1u) |

An 8-point spread top to bottom, and it does not hold: `lean` goes 70% → 34%
across the in-window split, on 10 then 38 resolved rows. Deduplicating to one
row per minute (n=161) reorders the bands entirely — climax 43%, lean 47%,
neutral 38% — which is what a rank produced by noise looks like.

### By sign agreement

| Cut | n | All | early | late |
|---|---|---|---|---|
| agree (score>0) | 82 | 37% (30W/51L, 1u) | 44% (12W/15L) | 33% (18W/36L, 1u) |
| disagree (score<0) | 124 | 43% (51W/68L, 5u) | 37% (7W/12L) | 44% (44W/56L, 5u) |

The sign of the effect is **backwards from the hypothesis** — bullish confirms
did slightly *better* when the gauge leaned against them — and it flips between
the early and late halves. This is the cut that would have been most useful and
it is the emptiest.

### By driver class

| Driver | n | All | early | late |
|---|---|---|---|---|
| cum spine | 105 | 41% (43W/62L) | 29% (6W/15L) | 44% (37W/47L) |
| flush/capitulation | 34 | 44% (14W/18L, 2u) | — (0 resolved) | 44% (14W/18L, 2u) |
| pressure | 53 | 37% (18W/31L, 4u) | 50% (9W/9L) | 29% (9W/22L, 4u) |
| up-climax | 9 | 44% (4W/5L) | 50% (2W/2L) | 40% (2W/3L) |
| quiet tape | 5 | 40% (2W/3L) | 67% (2W/1L) | 0% (0W/2L) |

Every driver lands within 7 points of the 40% baseline. `flush/capitulation`
has no early-half rows at all.

### By score tercile (cuts at −51 and +14; range −100..+90, median −17)

| Tercile | n | All | early | late |
|---|---|---|---|---|
| T1 low (<=−51) | 70 | 48% (31W/34L, 5u) | 0% (0W/1L) | 48% (31W/33L, 5u) |
| T2 mid | 69 | 36% (25W/44L) | 35% (8W/15L) | 37% (17W/29L) |
| T3 high (>+14) | 67 | 38% (25W/41L, 1u) | 50% (11W/11L) | 32% (14W/30L, 1u) |

Monotonic in the wrong direction (most-negative internals do best), and T1 has
one resolved early-half row.

### Contrasts, with day-clustered intervals

| Contrast | Delta | Fisher p | Day-clustered 95% CI |
|---|---|---|---|
| agree vs disagree | −6% | 0.464 | [−23%, +16%] |
| climax vs rest | +7% | 0.419 | [−35%, +16%] |
| flush/capitulation vs rest | +4% | 0.698 | [−26%, +33%] |
| negative-score climax vs rest | +10% | 0.245 | [−19%, +20%] |

Every interval straddles zero, most of them by 30+ points. With 15 days the
study cannot resolve anything smaller than roughly a 25-point win-rate swing,
and no cut here is close.

## The one thing that survives: climax reads wreck the trade's shape

Win rate is the wrong lens. Excursion is where the difference lives:

| Band | n | median MFE30 | median MAE30 | MFE>MAE |
|---|---|---|---|---|
| climax | 55 | 7.75 | **17.00** | **22%** |
| lean | 51 | 8.00 | 9.00 | 57% |
| neutral | 100 | 7.88 | 8.00 | 53% |

A confirm taken while the gauge reads climax reaches the same favourable
excursion as any other (median MFE ~7.8 points, flat across bands) but takes
**roughly twice the heat**, and only 22% of them end the 30-minute window with
MFE exceeding MAE, against 54% everywhere else.

- MFE>MAE share, climax vs rest: **−32 points**, day-clustered 95% CI
  **[−55%, −20%]** — the only interval in this study that excludes zero.
- Median MAE difference: +8.25 points, but CI **[−3.50, +17.00]** — the median
  itself is *not* separable once days are resampled. The proportion is the
  robust statement; the median is not.

Honest limit on this one: climax rows come from **6 of 15 days**, with
2026-07-29 (26 rows) and 2026-07-23 (21 rows) supplying 47 of 55. Both were
heavy down-tape D days (morning cum TICK −25,566 and −54,763). Leave-one-day-out
on the climax median MAE ranges 14.00 to 18.88 — dropping 07-29 pulls it to
14.00, still well above the 8.75 of everything else. The day-clustered bootstrap
already prices this concentration in and the proportion still holds, but "6
days" is the sample, and it should be re-tested before it is trusted.

Read plainly: **the gauge is not telling you whether the trade wins. It is
telling you the trade will be ugly.** That is consistent with the gauge's own
design doctrine — a climax print is an exit-into-it marker, not a
counter-entry — and it is the only place the internals earned their keep here.

## The fade cut — fire_index >= 4

38 of the run's 70 `fire_index>=4` confirmations joined, spread over 9 days
(2026-07-23 alone supplies 12).

Joined long win rate **33%** (12W/24L, 2u) → **short-side win rate 67%**
(24W/12L). The fade replicates on this sub-sample.

| Gauge state at fire time | n | long win | SHORT win |
|---|---|---|---|
| climax | 6 | 50% (3W/3L) | 50% (3W/3L) |
| lean | 12 | 36% (4W/7L, 1u) | 64% (7W/4L) |
| neutral | 20 | 26% (5W/14L, 1u) | **74% (14W/5L)** |
| agree (score>0) | 10 | 22% (2W/7L, 1u) | 78% (7W/2L) |
| disagree (score<0) | 28 | 37% (10W/17L, 1u) | 63% (17W/10L) |

The ordering is *tidy* — the fade is best on a quiet tape and vanishes into a
climax — and it is also **not evidence**:

- neutral vs non-neutral: delta −15%, Fisher p=0.483, day-clustered CI
  **[−71%, +22%]**
- agree vs disagree: delta −15%, Fisher p=0.685, day-clustered CI
  **[−61%, +42%]**

The climax cell is 6 rows. Leave-one-day-out on the best-looking cut
(fire>=4 & neutral gauge) holds the short win rate between 67% and 78% across
all 9 days, so the *fade* is stable — but its 74% versus the 67% unconditional
fade is a 7-point gain on 19 resolved rows, which is nothing.

**Verdict on the fade: internals neither sharpen nor kill it.** Trade the fade
on its own merits; do not gate it on the gauge on this evidence.

## The chop-day proxy — a clean negative

Morning internals summary per day (08:30–10:30 CT: mean score, mean |score|,
fraction of negative minutes, non-neutral fraction, cum TICK at 10:30, climax
counts each side), against the final TPO day type. Universe widened past the 15
signal days to **all 22 classifiable days** in the internals window (2026-06-30
.. 2026-07-30) by classifying the 5 days the acuity run skipped for want of
anchors — day type needs the tape, not the anchors. Types: 10 P, 8 D, **4 b**.

Best in-sample single thresholds for "final type is b":

| Feature | Rule | Recall | Precision | F1 |
|---|---|---|---|---|
| mean_score | >= +40 | 75% (3/4) | 43% (3/7) | 0.55 |
| cum_at_1030 | >= +3500 | 75% (3/4) | 38% (3/8) | 0.50 |
| frac_neg | <= 0.10 | 75% (3/4) | 38% (3/8) | 0.50 |
| mean_abs | >= 34 | 100% (4/4) | 24% (4/17) | 0.38 |

Taken at face value this beats the developing classifier's 23% recall / 41%
precision. **It should not be taken at face value.** Two reasons:

1. **The permutation null kills it.** The sweep tries 432 candidate rules
   against 4 positive days. Shuffling the day-type labels 1000 times and
   re-running the identical sweep: median best F1 on *random* labels **0.50**,
   p90 **0.67**, max 0.89, versus the observed **0.55**. **p = 0.434** — random
   labelings match or beat the real one 43% of the time. The rule is the search,
   not the signal.
2. **The direction is backwards from mechanism.** The winning rule says a
   *strongly positive* morning tape predicts a b-day — and b is defined
   (`market/orderflow/tpo.py`) as POC in the lower range under a thin upper
   stem, a one-sided push *down*. Three of the four b-days (07-02, 07-24,
   07-27) did print strong up mornings before rolling over, which is a
   recognisable bull-trap shape — but "three days" is an anecdote, and the
   sweep found it by looking 432 times.

**The chop-day question is unanswered, not answered negatively.** Four b-days
cannot support a classifier. This needs to be re-run when the internals corpus
holds enough b-days to matter — call it 20, which at the observed 18% base rate
means about 111 days in total, so roughly **90 more trading days** of
accumulation beyond the 22 we have.

## What this does and does not say

- **Nothing here is validated.** The tune/validate split is degenerate (tune
  n=0). The early/late split is a within-July consistency check on 46 vs 160
  rows and several cuts flip across it.
- **The sample is 15 days, not 206 signals.** Two days are 36% of it. Every
  interval quoted is day-clustered for exactly this reason; the Fisher p's are
  shown only to demonstrate how much they mislead here (climax MFE>MAE reads
  p=0.0000 row-level and [−55%, −20%] day-clustered — same direction, honest
  width).
- **Bullish-only, still.** All anchors are supports, so "gauge disagrees" means
  a down-leaning tape under a long signal. Nothing here says anything about
  short entries; the fade numbers are the *inverse* of long confirms, not
  independently graded shorts.
- **±5 symmetric is not the trade** — the same caveat as run 2, and it is why
  the excursion table matters more than the win-rate tables here.
- **The gauge itself is not on trial.** This tests one narrow use: gauge state
  at a single minute as a filter on one recognizer's bullish confirms. The
  climax/exit doctrine it was built for is untouched by these results, and the
  one surviving effect supports it.

## Recommendations

1. **Do not wire the gauge into the signal stream as a win-rate filter.** There
   is no measured basis for it, and the two cuts most likely to be adopted on
   intuition (sign agreement; suppress on climax) point the wrong way or nowhere.
2. **Do consider it as a heat/size input, not a direction input.** The one
   surviving effect — climax reads → MFE>MAE collapses from 54% to 22% at the
   same median MFE — argues for reducing size or tightening the stop on a
   confirm that fires into a climax print, not for skipping it. Re-test before
   trusting: 6 days.
3. **Re-run this join on a forward window.** The blocker is data, not method.
   The script is deterministic and re-runnable; the honest re-test date is when
   the internals corpus holds a genuinely out-of-sample stretch after
   2026-07-30. Nothing else in this study changes until then.
4. **Protect the internals corpus.** Schwab's rolling ~47-day window means any
   day not pulled is lost forever, and that is precisely why 217 of 423
   confirmations are unjoinable. The daily pull is now load-bearing measurement
   infrastructure; a gap in it destroys future studies retroactively.
5. **Leave the chop-day question open.** Re-ask it at ~20 b-days. Until then the
   developing-shape classifier's 23% recall stands as the incumbent, unbeaten
   but not yet honestly challenged.
