# Greek Pattern Discovery Plan — V-Day Trough Identification

**Bead:** TBD (file before execution)
**Date:** 2026-05-24
**Status:** TROUGH-TIME CONFOUND RESOLVED — Iteration 2 hypotheses revised

## Executive Summary

Retrospective pattern-discovery study on 13 confirmed V-days. The question: does the options activity structure at the trough moment carry patterns that distinguish pivots (snap-back) from continuations (continued decline)?

Dataset: 243 trading days, 13 positive (V-day pivot), ~33-53 negatives depending on definition. Per-day: ~291K OPRA trades + ~78K ES trades in the [13:00, 15:00) CT window. Black-Scholes module computes 7 Greeks + implied vol.

**Working Hypothesis (evidence-driven, post-confound resolution):**

~~V-day pivots are characterized by hedging EXHAUSTION — selling pressure has already dissipated, visible as lower volume.~~ **SUPERSEDED.**

V-day pivots are characterized by VOLUME CLIMAX — a surge of activity relative to what's normal for the time of day (1.57x expected, d=0.842, p=0.014). This surge represents the completion of a rapid hedging event (selling climax). After the climax, selling pressure is exhausted and price snaps back. CONTINUATION days show NORMAL OR BELOW-NORMAL volume at their trough (1.08x expected). The signal lives in TIME-NORMALIZED ACTIVITY STRUCTURE and DTE COMPOSITION (0DTE fraction d=1.381), NOT in raw volume or per-contract Greek profiles.

The original d=-1.524 raw volume finding was primarily a mechanical artifact of the trough-time confound (PIVOT troughs at 14:06, CONTINUATION at 14:53). See Part 2A for full decomposition.

---

## Part 1: Iteration 1 Results (COMPLETE)

### Findings — Track 1 Snapshot (Neg-A: n=13 PIVOT vs n=33 CONTINUATION)

**One statistically significant separator (LATER REVISED — see Part 2A):**

| Metric | Cohen's d | PIVOT mean | CONTINUATION mean | Interpretation |
|--------|-----------|-----------|-------------------|---------------|
| Total option volume (10-min pre-trough) | -1.524 | 33,909 contracts | 60,480 contracts | PIVOT has ~HALF the volume |

Decision gate (d >= 0.8) PASSED via volume. The static Greek book does not separate the classes; the activity structure does.

**CRITICAL REVISION (Part 2A):** The d=-1.524 finding was a composite of: (a) 0DTE exclusion by the Greek solver's MIN_T filter, and (b) massive trough-time confound. After proper decomposition: raw total volume d=-0.031, time-normalized d=+0.842 (PIVOT HIGHER than expected). See Part 2A for full resolution.

**Suggestive (medium effects, CI crosses zero):**

| Metric | Cohen's d | Direction |
|--------|-----------|-----------|
| Vega (all trades) | 0.604 | PIVOT higher (longer-dated options) |
| Rho (OTM puts) | -0.538 | PIVOT OTM puts carry more rate sensitivity (longer DTE) |
| Vanna (ATM calls) | -0.498 | CONTINUATION higher call vanna |
| Delta (all trades) | 0.483 | PIVOT trades less net-short |

**No separation (d < 0.3):** ATM put Greeks (all near zero), put/call ratio at ATM, OTM put volume fraction, IV level.

### Interpretation

The per-contract Greek profile at same moneyness does NOT distinguish classes. What distinguishes them is:
1. Total activity level (volume is the primary separator)
2. Composition of that activity (suggestive: longer-DTE, calmer positioning on PIVOT days)

This pivots the study from "which Greek separates?" to "what volume/flow dynamics distinguish exhaustion from active hedging?"

### Decision: Track Priority Reordering

| Original Priority | New Priority | Track | Rationale |
|-------------------|-------------|-------|-----------|
| 4 (conditional) | **1 (primary)** | Volume Microstructure | Volume IS the signal |
| 2 (scheduled) | **2** | Temporal Dynamics | Refocused on volume/premium flow dynamics |
| 5 (late-stage) | **3** | Composites | Volume + DTE composition composite |
| 3 (scheduled) | **4 (Iteration 3)** | IV Surface | Speculative; no IV-level signal in snapshot |
| 1 extensions | **DEPRIORITIZED** | Snapshot extensions | Null result on per-contract Greeks |

---

## Part 2: Negative Class Definitions

The negative class is THE critical design decision. With n=13 positives, statistical power depends entirely on how well-matched the negatives are. We define FOUR negative classes, run all analyses against each, and report where conclusions converge vs. diverge.

### Neg-A: "Strict Drop, No Recovery" (n=33)
```
depth_ok=True AND recovery_ok=False
```
The baseline definition from Strader's initial study. Days with meaningful depth (>= 0.6 x LATR_20) below VWAP but recovery < 50% of the drop. Clean separation by outcome.

**Risk:** Includes days with wildly different depth profiles than the V-days. A 65-pt freefall is categorically different from a 20-pt dip that didn't bounce.

### Neg-B: "Depth-Matched, Closed Below" (n~25-30)
```
depth >= min(V-day depths) AND depth <= max(V-day depths) * 1.2
AND close_p < vwap_p
AND date NOT in confirmed V-days
```
Restricts to days whose drawdown magnitude overlaps the V-day distribution (14-64 pts). "Close below VWAP" is the simplest recovery-failure criterion — the V never completed.

**Rationale:** Matching depth removes a massive confounder. A 60-pt crash on a normal day produces fundamentally different Greek profiles than a 15-pt dip regardless of outcome.

### Neg-C: "Time-and-Depth Matched" (n~20-25)
```
depth >= 15 pts
AND trough_t in [13:30, 14:45) CT
AND recovery < 50% of depth
```
Adds temporal matching. V-day troughs cluster 13:36-14:56 CT. This restricts negatives to the same time window, removing confounders from different theta-decay regimes (options behave differently at 13:35 vs 14:55 with respect to time-decay acceleration).

### Neg-D: "Propensity-Matched" (synthetic, n=13)
For each V-day, find its nearest neighbor on (depth, trough_time, LATR_20) that did NOT recover. 1:1 matching eliminates distributional imbalance entirely.

**Algorithm:** For V-day i, compute:
```
distance = w1 * |depth_i - depth_j| / std(depth)
         + w2 * |trough_min_i - trough_min_j| / std(trough_min)
         + w3 * |LATR_i - LATR_j| / std(LATR)
```
Select the nearest non-V-day for each V-day. Weights (w1=0.5, w2=0.3, w3=0.2) reflect importance ordering.

**Risk:** n=13 vs n=13 gives very low power. But this is the cleanest causal comparison.

### Which to Trust

Run analyses against all four. Report:
- **Convergent findings** (signal appears across all definitions) = strongest evidence
- **Neg-A only findings** = potentially confounded by depth mismatch OR trough-time (see below)
- **Neg-D only findings** = may be real but underpowered

### CRITICAL: Trough-Time Confound (discovered during plan refinement)

**The trough-time distribution between classes is massively different (d = -3.405):**

| | PIVOT (n=13) | CONTINUATION Neg-A (n=33) |
|---|---|---|
| Mean trough time | 14:06 CT | 14:53 CT |
| Median | 14:01 | 14:57 |
| Range | 13:36 - 14:56 | 14:21 - 14:59 |

CONTINUATION troughs cluster at the very END of the [13:00, 15:00) window. This is mechanically inevitable: a day that drops and doesn't recover will have its "trough" at or near the close. PIVOT days trough earlier because recovery BY DEFINITION follows.

**Implications for the Iteration 1 volume finding (d=-1.524):**

The volume difference could be partially or entirely mechanical:
- 0DTE option volume increases closer to expiry (gamma scaling drives hedging)
- A trough at 14:53 has ~47 more minutes of cumulative hedging flow than a trough at 14:06
- The d=-1.524 volume signal MUST be re-tested with time-of-day normalization

**Resolution strategy (gates all of Iteration 2):**

1. **Compute expected volume curve:** Average option volume per minute across ALL days (not just study days). This gives the time-of-day baseline.
2. **Time-normalize the volume signal:** For each day, compute volume_observed / volume_expected_at_that_time. Re-run the PIVOT vs CONTINUATION comparison on normalized volume.
3. **If normalized signal persists (d >= 0.8):** Volume exhaustion is real, independent of timing. Proceed with Iteration 2 as planned.
4. **If normalized signal collapses (d < 0.5):** The "signal" was purely mechanical. Reframe: the research question becomes "what distinguishes EARLY troughs from LATE troughs?" which is a different (and arguably more useful) question for the trading system.
5. **Neg-D (propensity-matched) resolves this directly:** By matching on trough time (w2=0.3), Neg-D already controls for the timing confound. If the volume signal survives Neg-D matching, it's real.

**Second-order insight:** The trough timing itself is partially informative for the trading system, even if circular for the pattern study. A real-time analog: "it's 14:20, price has dropped 25pts, and you're seeing volume declining" is a testable condition that doesn't require knowing the future trough. The temporal composition of the signal matters for deployment even if it's confounded for retrospective study.

### Part 2A: Trough-Time Confound RESOLUTION (2026-05-24)

#### Key Finding: Trough Time is DEFINITIONAL, Not Matchable

Trough time is an **outcome variable**, not a covariate:
- A day that drops and recovers MUST trough early (recovery needs time)
- A day that drops and doesn't recover MUST trough late (the trough IS the close)
- You CANNOT match on trough_time while preserving the negative class definition

**Neg-D matching fails:** Even with w2=0.3 weight on trough_time, the matched pairs have d=-2.306 on trough_time (only slightly better than unmatched d=-3.405). The candidate pool simply has no early-trough non-recoveries — because they don't exist by definition.

#### Volume Signal Decomposition (Definitive Analysis)

Analysis script: `scripts/measurement/trough_time_volume_analysis.py`
Corpus: 246 days processed, per-minute OPRA volume in [13:00, 15:00) CT.

**Method:** Compute time-of-day expected volume from the full 246-day corpus. For each study day, measure volume_ratio = observed_10min_pre_trough / expected_at_that_time.

**Results — Total OPRA Volume (all DTE):**

| Metric | PIVOT (n=13) | CONTINUATION (n=33) | Cohen's d | Perm p |
|--------|-------------|--------------------:|----------:|-------:|
| Raw volume (10-min pre-trough) | 127,014 | 128,729 | -0.031 | 0.923 |
| Expected volume (time-of-day) | 82,905 | 120,825 | -2.243 | — |
| **Time-normalized ratio** | **1.567** | **1.084** | **+0.842** | **0.014** |

**Results — Non-0DTE Volume Only:**

| Metric | PIVOT (n=13) | CONTINUATION (n=33) | Cohen's d | Perm p |
|--------|-------------|--------------------:|----------:|-------:|
| Raw volume | 30,949 | 42,770 | -0.532 | 0.109 |
| Expected volume (time-of-day) | 24,092 | 42,078 | -2.426 | — |
| **Time-normalized ratio** | **1.311** | **1.020** | **+0.523** | **0.117** |

**Results — DTE Composition:**

| Metric | PIVOT | CONTINUATION | Cohen's d |
|--------|------:|-------------:|----------:|
| 0DTE fraction | 74.7% | 64.6% | **+1.381** |
| 0DTE raw volume | 105,101 | 113,732 | -0.285 |
| Non-0DTE raw volume | 34,911 | 62,329 | -1.667 |

#### Signal Assessment

| Signal | Status | Evidence |
|--------|--------|----------|
| Raw volume difference (d=-1.524) | **DOES NOT REPLICATE** | Mechanical artifact of trough timing + 0DTE exclusion |
| Time-normalized total volume | **REAL, d=+0.842** | PIVOT volume 57% above expectation; p=0.014 |
| Time-normalized non-0DTE volume | **Suggestive, d=+0.523** | Underpowered (p=0.117) but same direction |
| 0DTE composition fraction | **REAL, d=+1.381** | PIVOT has higher 0DTE proportion |

#### Hypothesis Reversal

| | Old Hypothesis | New Hypothesis (evidence-driven) |
|---|---|---|
| Direction | PIVOT = LOW volume (exhaustion) | PIVOT = HIGH volume relative to expectation (climax) |
| Mechanism | Hedging already finished -> quiet trough | Hedging completes in a SURGE -> activity climax clears the market |
| 0DTE role | Frantic 0DTE on CONTINUATION | Higher 0DTE FRACTION on PIVOT (both layers active simultaneously) |
| Narrative | "Quiet before the turn" | "Crescendo AT the turn" |

The mechanism is actually the same endpoint (hedging demand satisfied) but manifests as a SPIKE not a DROUGHT. The selling climax concentrates activity into a burst that clears the outstanding hedging demand in one event. After the climax, no sellers remain, and price snaps back.

#### Neg-D Matched Comparison (depth + LATR only, n=13 vs 13)

Trough-time matching is impossible (definitional). Neg-D matches on depth and LATR only:

| PIVOT Date | P.Depth | P.LATR | MATCH Date | M.Depth | M.LATR | Dist |
|-----------|--------:|-------:|-----------|--------:|-------:|-----:|
| 2025-08-11 | 19.5 | 23.1 | 2025-08-25 | 19.3 | 23.4 | 0.031 |
| 2025-09-17 | 53.6 | 20.1 | 2025-10-14 | 47.6 | 24.2 | 0.519 |
| 2025-09-29 | 14.1 | 21.9 | 2025-08-05 | 15.0 | 22.1 | 0.057 |
| 2025-10-13 | 19.2 | 24.0 | 2026-05-01 | 17.2 | 27.8 | 0.312 |
| 2025-10-29 | 51.7 | 25.1 | 2026-02-13 | 50.4 | 35.0 | 0.624 |
| 2025-11-17 | 38.2 | 29.3 | 2026-02-05 | 39.4 | 31.3 | 0.170 |
| 2026-01-30 | 27.5 | 28.3 | 2025-11-05 | 28.0 | 30.6 | 0.153 |
| 2026-02-18 | 27.9 | 36.4 | 2026-01-07 | 27.8 | 23.1 | 0.662 |
| 2026-03-30 | 38.6 | 44.0 | 2026-02-05 | 39.4 | 31.3 | 0.734 |
| 2026-04-01 | 17.7 | 45.0 | 2026-03-27 | 27.4 | 43.5 | 0.552 |
| 2026-04-08 | 27.3 | 44.2 | 2026-03-12 | 25.6 | 38.6 | 0.395 |
| 2026-05-08 | 16.0 | 24.6 | 2025-07-10 | 15.2 | 24.4 | 0.047 |
| 2026-05-21 | 32.1 | 27.4 | 2025-10-30 | 33.7 | 27.5 | 0.084 |

Match quality: Depth d=0.064, LATR d=-0.071 (excellent). Trough time cannot be matched (definitional).

Neg-D time-normalized volume: PIVOT ratio=1.567, Neg-D ratio=1.216, d=+0.514, p=0.199.
Consistent direction but underpowered at n=13 vs n=13.

#### Negative Population Viability

| Population | n | Mean Trough (min since 13:00) | Viable? |
|-----------|--:|-----:|---------|
| Neg-A | 33 | 113.2 | YES (primary, with time-normalization) |
| Neg-B | 57 | 103.2 | YES (depth-matched, same time-norm needed) |
| Neg-C | 7 | 86.2 | MARGINAL (too small for reliable inference) |
| Neg-D | 13 | 105.3 | YES for depth+LATR checks; time-norm required |

All negative populations have late troughs (definitionally inevitable). Time-normalization is MANDATORY for all volume comparisons regardless of which negative definition is used.

---

## Part 3: Iteration 2 Analytical Tracks

Iteration 2 focuses exclusively on volume/flow dynamics and their temporal evolution. All tracks operate on 1-minute bins from T-20 to T+10 (30-point time series per day).

---

### TROUGH-TIME CONFOUNDER: RESOLVED (see Part 2A)

**Status:** COMPLETE. The gate check has been run. Key outcomes:
1. Trough-time difference is MASSIVE and DEFINITIONAL (d=-3.405, unmatchable)
2. Raw volume comparison is NIL when counting all trades (d=-0.031)
3. TIME-NORMALIZED volume shows PIVOT 57% above expectation (d=+0.842, p=0.014)
4. 0DTE fraction is a strong standalone signal (d=+1.381)
5. Hypothesis REVERSES: CLIMAX (volume surge) not EXHAUSTION (volume drought)

**Normalization is MANDATORY for all Iteration 2 tracks.** Formula:
```
adjusted_volume[t] = raw_volume[t] / E[volume | minute_of_day = minute(trough_t + t)]
```
Where E[volume] is the per-minute mean from the full 246-day corpus.

---

### Track A: Volume Dynamics (PRIMARY — Iteration 2)

**What:** Decompose the volume signal into temporal dynamics — not just "less volume" but "how does volume BEHAVE" in the minutes surrounding the trough?

**Method:**

1. **Time-normalized volume acceleration/deceleration:**
   - Time-normalized volume ratio per minute in 1-min bins, T-20 to T+10
   - First derivative: normalized volume velocity (is the SURGE building or fading?)
   - Second derivative: acceleration (is the rate of change itself changing?)
   - **REVISED Hypothesis:** PIVOT days show a volume SURGE (ratio >> 1.0) that peaks and then subsides (climax pattern). CONTINUATION days show ratio near 1.0 throughout (no climax event).
   - Note: ALL volume metrics must use time-normalized ratios, not raw counts.

2. **Volume climax timing:**
   - Identify peak-volume minute within [T-20, T+5] using TIME-NORMALIZED ratio
   - Compute: peak_offset = peak_minute - trough_minute
   - **REVISED Hypothesis:** PIVOT peak volume occurs NEAR the trough (the selling climax IS the trough). CONTINUATION has no discernible peak relative to baseline.

3. **Volume surge ratio:**
   - normalized_vol[T-5:T-0] / normalized_vol[T-15:T-10] (late vs. early pre-trough)
   - For PIVOT: expect ratio > 1 (volume surging INTO the trough — climax)
   - For CONTINUATION: expect ratio near 1 (no surge pattern)

4. **0DTE/non-0DTE composition dynamics (NEW — strongest standalone signal):**
   - 0DTE fraction per minute bin from T-20 to T+10
   - Rate of change: d(0DTE_fraction)/dt
   - **Hypothesis:** PIVOT days maintain HIGH 0DTE fraction (~75%) throughout, indicating both 0DTE and non-0DTE participate in the climax. CONTINUATION days have lower 0DTE fraction (~65%), suggesting more institutional (non-0DTE) hedging without the concentrated 0DTE burst.
   - This is the strongest signal from the confound resolution (d=1.381).

5. **Put-call volume ratio dynamics:**
   - P/C volume ratio in 1-minute bins from T-20 to T+10
   - Rate of change of P/C ratio: d(P/C)/dt
   - Hypothesis: P/C ratio peaks AT or NEAR the trough for pivots (concentrated put-buying climax), distributed more evenly for continuations.

6. **Size distribution evolution:**
   - Average trade size per minute bin
   - Large-trade fraction (size >= 50 contracts) per bin
   - **REVISED Hypothesis:** Large trades CONCENTRATE near trough on PIVOT days (institutional selling climax). Large trades are spread more evenly on CONTINUATION days (ongoing rather than climactic).

7. **Trade arrival rate:**
   - Inter-trade time statistics per 5-min window (mean, variance, coefficient of variation)
   - Burstiness metric: CV > 1 = clustered; CV < 1 = regular
   - Hypothesis: PIVOT days show peak burstiness AT the trough (climax concentration). CONTINUATION days show moderate, sustained burstiness (no peak event).

**Output:** 30-point time-series plots (mean +/- SE band per class) for each metric. Feature-level comparison table with effect sizes. Volume-climax timing histogram.

**Execution estimate:** ~3 hours (I/O dominated; volume metrics are cheap once trades are loaded).

---

### Track B: Premium Surge (PRIMARY — Iteration 2, hypothesis revised)

**What:** Total put premium flow as a time series leading into the trough. Premium flow = the actual dollars changing hands for downside protection. **REVISED:** If premium flow SURGES into the trough while price drops, that's the selling climax — all remaining hedging demand being satisfied in a concentrated burst.

**Method:**

1. **Premium flow time series:**
   - For each minute bin: sum(trade_size * trade_price * 100) for all put trades
   - This gives total dollar premium exchanged per minute
   - Separate into: ATM puts, OTM puts, all puts

2. **Premium flow velocity:**
   - First derivative of TIME-NORMALIZED premium flow: d(premium_ratio)/dt
   - Positive = premium flow increasing relative to baseline (climax building)
   - Negative = premium flow declining relative to baseline (fading)
   - **REVISED Key metric:** sign and magnitude of premium_velocity at T-5 to T-0; expect POSITIVE for PIVOT (climax surge) and near-zero for CONTINUATION

3. **Premium-to-intrinsic ratio evolution:**
   - For ATM puts: ratio = traded_price / intrinsic_value
   - This ratio = 1 + (time_value / intrinsic) — captures IV component
   - Track this ratio over T-20 to T+10
   - **REVISED Hypothesis:** PIVOT days may show ratio SPIKING before trough (IV elevating as panic peaks in the climax) then collapsing (IV deflating as the climax resolves). CONTINUATION days show stable ratio (no climactic event, no resolution).

4. **Cumulative premium climax curve:**
   - Cumulative sum of put premium from T-20 to T+10
   - Normalize by total premium in the window
   - Plot as S-curve; measure "elbow" location
   - **REVISED Hypothesis:** PIVOT S-curve elbows STEEPLY near trough (premium concentrates into the climax moment). CONTINUATION S-curve is linear (premium distributed evenly, no concentration event).

5. **Premium concentration ratio:**
   - Premium in [T-5, T-0] / Premium in [T-10, T-5]
   - > 1 = later concentration (climax at trough)
   - < 1 = earlier concentration or flat
   - **REVISED:** Directly tests "does premium concentrate INTO the trough moment?"

6. **Call premium awakening:**
   - Track call premium flow alongside put premium flow
   - Compute put_premium / call_premium ratio per minute
   - Hypothesis: PIVOT days show call premium appearing POST-TROUGH (recovery bets emerging as the climax resolves). CONTINUATION days show put-only flow throughout (no resolution event triggers call interest).

**Output:** Premium flow time-series plots. Exhaustion curve comparisons. Premium velocity at key windows. Call/put premium ratio dynamics.

**Execution estimate:** ~2 hours (requires price * size computation, straightforward).

---

### Track C: DTE Composition Dynamics (SECONDARY — Iteration 2)

**What:** The suggestive signals (vega d=0.604, rho d=-0.538) point toward PIVOT days having longer-dated options in the flow. Track the DTE composition as a time series.

**Method:**

1. **Volume-weighted DTE per minute bin:**
   - For each minute: weighted_DTE = sum(trade_size * DTE) / sum(trade_size)
   - Track from T-20 to T+10
   - **REVISED Hypothesis:** PIVOT days show LOW weighted_DTE at trough (0DTE-dominated climax, d=1.381 on 0DTE fraction), potentially INCREASING post-trough as the climax resolves and longer-dated positioning begins. CONTINUATION shows moderate but steady DTE throughout (no climactic concentration).

2. **0DTE fraction dynamics:**
   - Fraction of volume that is 0DTE, per minute bin
   - First derivative: d(0DTE_fraction)/dt
   - **REVISED Hypothesis:** PIVOT 0DTE fraction is HIGH throughout (75% average) and peaks AT the climax. CONTINUATION has lower 0DTE fraction (65%) without a peak event. The PIVOT fraction may drop sharply post-trough (climax over, recovery positioning shifts to longer dates).

3. **DTE bucket migration:**
   - Three buckets: 0DTE, 1-2 DTE, 3+ DTE
   - Track volume share of each bucket per minute
   - Visualize as stacked area chart
   - **REVISED Hypothesis:** PIVOT shows 0DTE dominance AT trough then rapid shift toward 1-2 DTE POST-trough (regime change from panic to recovery). CONTINUATION shows steady composition throughout.

4. **DTE x moneyness interaction:**
   - Cross-tabulate: is the longer-DTE flow in PIVOT days coming from ATM or OTM?
   - If longer-DTE + ATM: portfolio hedging (calm, systematic)
   - If longer-DTE + OTM: tail hedging (also calm, different motivation)
   - Both contrast with 0DTE + ATM: panicked spot hedging

5. **Premium-per-DTE-day:**
   - Average premium / DTE days for trades in each bucket
   - Captures "how much are they paying per day of coverage?"
   - **REVISED Hypothesis:** PIVOT days pay MORE per day (0DTE-heavy climax = expensive per day = urgent panic buying that clears the market). CONTINUATION days pay less per day (more distributed across longer DTE, less panicked). The high premium-per-day IS the climax signature — paying any price to get hedged NOW.

**Output:** DTE time-series plots. 0DTE fraction dynamics. Stacked area visualizations. Premium-per-day comparisons.

**Execution estimate:** ~2 hours (DTE from OCC symbol parse, already available in pipeline).

---

### Track D: Composite Signal Construction (Iteration 2 synthesis)

**What:** Combine the volume, premium exhaustion, and DTE composition features into a unified score.

**Method:**

1. **Feature extraction from Tracks A-C:**
   - From Track A: volume_velocity_T5, volume_peak_offset, volume_decay_ratio, pc_ratio_peak_offset, large_trade_fraction_T5
   - From Track B: premium_velocity_T5, premium_concentration_ratio, put_call_premium_ratio_at_trough, cumulative_elbow_offset
   - From Track C: weighted_DTE_at_trough, zero_DTE_fraction_T5, DTE_velocity

2. **Univariate screening:**
   - Compute Cohen's d for each feature against all four negative class definitions
   - Retain features with d >= 0.5 in at least 2/4 definitions

3. **Correlation structure:**
   - Compute pairwise correlations among retained features
   - Drop redundant features (r > 0.8) keeping the higher-d member

4. **Principal Component Analysis:**
   - On the retained, non-redundant feature set
   - Question: do PIVOT and CONTINUATION separate in PC1-PC2 space?
   - If yes: what linear combination defines the separating axis?

5. **Simple composite score (pre-model):**
   - Z-score each retained feature (using full-sample mean/SD)
   - Composite = mean of Z-scores (sign-aligned so positive = PIVOT-like)
   - Compare composite distributions between classes
   - This is the "does a simple average of signals work?" check before building a model

**Output:** Feature screening table. Correlation matrix. PCA biplot. Simple composite score distributions.

**Decision gate for Iteration 3:** Composite score separates classes with d >= 1.0 AND at least 3 component features individually show d >= 0.5.

---

## Part 4: Iteration 3 — Model Validation (Conditional on Iteration 2)

### Scope

If Iteration 2 produces a composite with d >= 1.0, build a predictive model and validate it.

**Steps:**

1. **Elastic net logistic regression:**
   - Features: all retained features from Track D screening
   - L1+L2 penalty to handle p relative to n
   - 5-fold cross-validation for penalty parameter
   - Report which features survive penalization (non-zero coefficients)

2. **Leave-one-out cross-validation:**
   - For each V-day, train on the other 12 + all negatives, predict the held-out day
   - Compute LOO accuracy, sensitivity, specificity
   - Build calibration plot (predicted probability vs. actual outcome)

3. **Score all 243 days:**
   - Apply the model to every day in the corpus
   - Examine the distribution of scores
   - Identify clusters of high-scoring non-V-days (potential undetected pivots?)

4. **Soft validation — borderline days:**
   - 5 detector-positive-but-Steve-unconfirmed days (2025-09-10, 2025-11-13, 2025-12-18, 2026-03-02, 2026-05-07): do they score high?
   - MISS-BY-1 days (drop+recovery present but landing criteria missed): do they score intermediate?
   - Neither validates nor invalidates, but increases confidence if scores are monotone with outcome quality.

5. **LDA comparison:**
   - Regularized LDA (shrinkage estimator for covariance)
   - Compare LOO accuracy with elastic net
   - If LDA performs comparably with fewer features, prefer the simpler model

### IV Surface Exploration (Speculative — Iteration 3)

Demoted from primary status. Run only if Iteration 2 leaves time/budget:

1. **Implied volatility smile at trough:**
   - For 0DTE options, compute IV at each strike with sufficient volume (>= 5 trades in window)
   - Fit quadratic (a + b*moneyness + c*moneyness^2)
   - Compare level/skew/convexity between PIVOT and CONTINUATION
   - Expectation based on Iteration 1: likely no separation (IV level showed d~0 in snapshot)

2. **Gamma concentration profile:**
   - Total gamma (volume * gamma) at each strike
   - Gamma-weighted average moneyness
   - May show structure that per-contract gamma missed

3. **Strike clustering:**
   - Number of unique strikes traded in the window
   - "Activity breadth" = fraction of available strikes with any volume
   - Exploratory only — no prior signal suggests this will separate

### Decision Gate — Iteration 3 Complete

LOO accuracy > 70% (chance = 28% with 13/46 positives) AND false-positive rate on "clearly not V" days < 20%.

---

## Part 5: ES Spot Microstructure (Baseline — Run Alongside Iteration 2)

Even without options data, the ES price action itself may contain structure. This provides a floor for "how much information is in price alone vs. how much the volume/flow features add."

**Method:**

1. **Velocity at trough:**
   - Price change per minute in the 5 minutes approaching trough
   - Deceleration: is the rate of decline slowing?
   - Hypothesis: pivots decelerate before turning; continuations maintain velocity

2. **Bounce signature:**
   - Price action in [T+0, T+2] minutes (first 2 minutes after trough)
   - Size of first uptick relative to the decline

3. **Tick imbalance:**
   - ES has side information ("A" for ask, "B" for bid)
   - Compute buy/sell imbalance in the trough window
   - Hypothesis: pivots show buying pressure AT the trough

4. **Price relative to round numbers:**
   - Distance of trough_p from nearest 25-pt, 50-pt, 100-pt level
   - Hypothesis: V-days bottom near round numbers more often

5. **LATR context:**
   - Depth / LATR_20 ratio (how unusual is this drop relative to recent volatility?)

**Output:** Feature comparison table. Establishes the information baseline that volume/flow features should beat.

---

## Part 6: Statistical Framework

### Power Analysis

With n=13 PIVOT and n=33 CONTINUATION (Neg-A):
- Two-sample t-test at alpha=0.05, power=0.80:
  - Detectable effect size: Cohen's d >= 0.95 (LARGE effect only)
- At alpha=0.10 (exploratory study):
  - Detectable d >= 0.82

With n=13 vs n=13 (Neg-D):
- Detectable d >= 1.12 at alpha=0.05, power=0.80

**Implication:** Subtle signals (d < 0.5) are undetectable at this sample size. The time-normalized volume finding (d=+0.842) and 0DTE fraction (d=+1.381) both exceed the detection threshold. The non-0DTE normalized signal (d=+0.523) is suggestive but underpowered at the full-window level — may reach significance in specific time windows via temporal decomposition.

### Multiple Comparison Correction

Use Benjamini-Hochberg FDR at q=0.10. With Iteration 2's time-series focus, the comparison count is lower than Iteration 1's combinatorial explosion (targeted features, not exhaustive search).

**Pre-specified primary hypotheses (Iteration 2, REVISED post-confound resolution):**
- H1: Time-normalized volume ratio is HIGHER for PIVOT than CONTINUATION at T-5 to T-0 (climax)
- H2: 0DTE FRACTION is higher for PIVOT than CONTINUATION (composition signal, d=1.381 established)
- H3: Volume surge ratio (late/early) is higher for PIVOT (climax builds toward trough)
- H4: Premium flow velocity is positive (surging) into trough for PIVOT, flat for CONTINUATION

**Exploratory hypotheses:** All other Track A-C features. FDR-corrected.

### Permutation Testing

For every comparison:
1. Pool all days (PIVOT + CONTINUATION)
2. Randomly assign labels 10,000 times
3. Compute test statistic under each permutation
4. p-value = fraction of permutation statistics >= observed

### Effect Size Reporting

Report ALL of:
- Cohen's d (for comparability and decision gates)
- Rank-biserial correlation (non-parametric, robust to outliers)
- 95% bootstrap CI on difference of means (BCa method, 10,000 resamples)
- Bayes factor (BF10) against null: BF > 3 = "moderate evidence", BF > 10 = "strong"

### Threshold for "Signal"

A finding is "signal" (progresses to composite) if ALL of:
1. |d| >= 0.8 (large effect)
2. Permutation p < 0.05
3. Bootstrap CI excludes zero
4. Appears in at least 2/4 negative class definitions

A finding is "suggestive" (included in composite with lower weight) if:
1. |d| >= 0.5 (medium effect)
2. Permutation p < 0.10
3. Appears in at least 1 negative class definition

---

## Part 7: Confounders to Control

| Confounder | Why It Matters | Control Method |
|-----------|---------------|----------------|
| **Time-of-trough (RESOLVED)** | Trough time is DEFINITIONAL (outcome variable, not covariate); volume at different times is incomparable without normalization | RESOLVED: time-normalize ALL volume metrics using 246-day per-minute baseline (Part 2A) |
| Drop depth | Deeper drops may mechanically produce more volume regardless of outcome | Neg-B/C/D match on depth; include depth as covariate |
| LATR regime (vol context) | High-vol days may have fundamentally different volume patterns | Stratify by LATR quartile; normalize volumes by LATR |
| Day of week | Friday afternoon has different volume than Monday afternoon | Tabulate; include as categorical covariate |
| Expiry cycle | Monthly expiry week has different OI structure and volume | Flag monthly-expiry-week days |
| Market trend | Trending vs mean-reverting regimes change hedging demand | 5-day prior return as covariate |
| SPX level (non-stationarity) | SPX went from ~5900 to ~7500 over the corpus | Normalize all volume metrics by trailing average daily volume |
| Seasonality | Summer vs winter vol regimes differ | Month fixed effects in regression |

---

## Part 8: Honest Priors and Expectations (Updated Post-Iteration 1)

### What We Now Know Does NOT Work

- **Per-contract Greek profiles at same moneyness:** d < 0.3 across ATM puts, OTM puts. The options at equivalent strikes look the same on PIVOT and CONTINUATION days.
- **Static IV level:** No separation. The volatility surface at the trough moment is not informative.
- **ATM put/call ratio:** No separation. The composition at a single snapshot does not distinguish.
- **Raw volume comparison (any DTE):** d=-0.031. When all trades are counted, raw volumes are IDENTICAL between classes. The original d=-1.524 was an artifact of 0DTE exclusion + timing.
- **Trough-time matching:** Impossible. Trough time is an outcome variable, not a covariate.

### Where Signal Lives (Confirmed and Hypothesized)

**Confirmed (d > 0.8, established):**
1. **Time-normalized volume ratio (d=+0.842, p=0.014)** — PIVOT days have 57% ABOVE expected volume at trough time. Volume SURGES, not droughts, precede pivots.
2. **0DTE composition fraction (d=+1.381)** — PIVOT days have 75% 0DTE vs 65% for CONTINUATION. The climax is concentrated in short-dated flow.

**Hypothesized (to be tested in Iteration 2):**
3. **Volume climax dynamics** — the surge builds toward the trough (volume accelerating into a peak, then rapid decline post-trough as the event completes).
4. **Premium surge** — total dollar premium flow INCREASING into trough for PIVOT (the climax moves premium), flat/normal for CONTINUATION.
5. **DTE composition timing** — the 0DTE fraction may PEAK at the trough for PIVOT (all the panic concentrates into the climax moment) then shift toward longer-dated as recovery begins.
6. **Non-0DTE volume (d=+0.523, suggestive)** — institutional flow also elevated, but less pronounced than total. May reach significance in temporal decomposition.

### Mechanistic Narrative (REVISED post-confound resolution)

~~The narrative tying these together: On PIVOT days, the hedging event has already COMPLETED by the time the price trough occurs.~~ **SUPERSEDED.**

On PIVOT days, the hedging event COMPLETES IN A CONCENTRATED BURST at the trough — a selling climax. Volume surges to 57% above normal-for-that-time, with a high proportion of 0DTE activity (75% vs 65%). This burst represents the final, panicked wave of selling/hedging that clears all outstanding demand in one event. After the climax, no sellers remain, and price snaps back.

On CONTINUATION days, no climactic event occurs. Volume at the trough is near normal for that time of day (1.08x baseline). Selling pressure continues at a background rate — there is no burst that clears the market. The drop continues because it was never concentrated into a single resolution event.

The key insight: **the same endpoint** (hedging demand satisfied) manifests differently. PIVOT = fast, concentrated, climactic. CONTINUATION = diffuse, ongoing, unresolved.

### What Would Strengthen the Hypothesis

- Time-normalized volume ACCELERATION toward the trough for PIVOT (climax building)
- Premium flow surging into trough for PIVOT but flat for CONTINUATION
- 0DTE fraction peaking AT the trough for PIVOT (concentration of panic activity)
- Volume climax timing consistently within [-3, 0] minutes of trough for PIVOT
- All the above appearing across Neg-A, Neg-B, and Neg-D (with time-normalization)

### What Would Weaken the Hypothesis

- Time-normalized ratio is driven by 2-3 outlier days (remove them and d < 0.5)
- The surge pattern is not consistent (some PIVOTs have quiet troughs, some CONTs have surges)
- 0DTE fraction signal collapses when examined in temporal dynamics
- The climax interpretation fails the real-time test: "elevated volume at this time" is too common to be actionable (high false-positive rate on the full corpus)

---

## Part 9: Parallel Execution Plan (for GC Teams)

Iteration 2 tracks can execute in parallel once the trough-time confounder check completes.

### Dependencies (UPDATED — trough-time check COMPLETE)

```
[Trough-Time Confounder Check] ──── COMPLETE (Part 2A)
                                  
[Time-of-day baseline] ──── COMPLETE (246-day per-minute volume curve available)
                                  
──> [Track A: Volume CLIMAX Dynamics]    (can start immediately)
──> [Track B: Premium SURGE]             (can start immediately)
──> [Track C: DTE Composition]           (can start immediately)
──> [ES Baseline (Part 5)]               (can start immediately)
                                  
[All Track A-C complete] ──> [Track D: Composite Construction]
[Track D complete] ──> [Iteration 3: Model Validation]
```

### Team Assignment Template (UPDATED)

| Team | Track | Estimated Duration | Dependencies |
|------|-------|-------------------|--------------|
| Team 1 | Track A (Volume Climax Dynamics) | 3 hours | Time-normalization baseline (provided) |
| Team 2 | Track B (Premium Surge) | 3 hours | Time-normalization baseline (provided) |
| Team 3 | Track C (DTE Composition + 0DTE fraction temporal) | 3 hours | None (0DTE fraction already established) |
| Team 4 | ES Baseline | 2 hours | None |
| Synthesis | Track D (Composite) | 3 hours | Tracks A-C complete |

### Shared Infrastructure Requirements

All teams need:
- Access to the per-day trade files (OPRA + ES)
- Trough timestamps per day (from existing V-day corpus)
- Negative class membership lists (Neg-A through Neg-D, from confound resolution)
- **Time-of-day volume baseline** (246-day per-minute expected volume — output of `trough_time_volume_analysis.py`)
- Common statistical utility: permutation test, bootstrap CI, Cohen's d with CI
- **ALL volume comparisons MUST use time-normalized ratios** (raw volume comparisons are invalid)

### Output Coordination

Each team produces:
1. A per-day feature matrix (rows = days, columns = features) as TSV
2. A statistical comparison table (feature x neg-class-definition) as TSV
3. Time-series visualization (30-point mean +/- SE band per class) as PNG
4. Brief findings narrative (1 page max)

Track D synthesizes all feature matrices into a single combined matrix for composite construction.

---

## Part 10: Implementation Notes

### Data Processing Pipeline

```
For each day in (PIVOT_SET + NEGATIVE_SET):
    1. Load ES trades -> build 1-second price grid
    2. Identify trough timestamp (pre-computed, from corpus)
    3. Define analysis window [T-20, T+10] minutes
    4. Load OPRA trades in window
    5. For each OPRA trade:
       a. Parse OCC symbol (expiry, strike, P/C)
       b. Compute DTE from expiry vs. trade date
       c. Compute moneyness from strike vs. spot
       d. Look up spot from ES grid at trade timestamp
       e. Compute trade_premium = size * price * 100
       f. Assign to minute bin, DTE bucket, moneyness bucket
    6. Aggregate per minute bin:
       - Volume (trade count, contract count)
       - Premium flow (sum of trade_premium)
       - Weighted DTE (volume-weighted mean DTE)
       - P/C ratio (put volume / call volume)
       - Size statistics (mean, large-trade fraction)
    7. Compute time-series features (velocity, acceleration, peak timing)
    8. Store per-day feature vector
```

**Note:** Iteration 2 does NOT require IV solving or Greek computation for most metrics. Volume, premium flow, and DTE are all directly observable from trade records. Only Track B item 3 (premium-to-intrinsic ratio) requires spot price lookup. This makes Iteration 2 substantially cheaper than Iteration 1.

**CRITICAL:** All volume and premium metrics MUST be time-normalized using the 246-day per-minute baseline. The baseline is computed by `scripts/measurement/trough_time_volume_analysis.py` and can be cached as a 120-element array (minutes 0-119 = 13:00-14:59 CT). For premium flow, compute a separate premium baseline using the same per-minute aggregation approach.

### Performance Considerations

- Each day has ~90K trades in the [T-20, T+10] window
- No IV solver needed for Tracks A, B (except item 3), C
- Pipeline is I/O bound (loading + parsing), not compute bound
- Estimated wall-clock per team: 2-4 hours including analysis
- Parallelization across teams cuts critical path to ~5 hours total

### Known Limitations

1. **Side information is "N" (unknown)** for all OPRA trades. We cannot determine buyer vs. seller. All volume analysis is total volume, not net directional flow.

2. **No open interest data.** We have trades (flow) but not positions (stock). Cannot determine if volume is opening or closing.

3. **No bid/ask quotes.** Cannot determine if trades hit the bid vs. lifted the offer (urgency proxy).

4. **Sample size is n=13.** Despite the d=-1.524 finding, this remains a discovery study. Iteration 2 features must be treated as hypothesis-generating. Replication on new V-days is mandatory before trading on any signal.

5. **Trough identified ex-post.** In real-time deployment, the trough is unknown. Any feature that requires "minutes before trough" needs a streaming analog (e.g., "volume declining over last 10 minutes" rather than "volume relative to future trough").

---

## Appendix A: V-Day Characteristics Summary

| Date | Depth (pts) | Recovery (pts) | Trough Time CT | LATR_20 |
|------|------------|----------------|----------------|---------|
| 2025-08-11 | 19.5 | 12.5 | 14:56 | 22.8 |
| 2025-09-17 | 53.6 | 48.8 | 13:54 | 20.1 |
| 2025-09-29 | 14.1 | 18.0 | 14:15 | 22.0 |
| 2025-10-13 | 19.2 | 13.0 | 14:01 | 24.1 |
| 2025-10-29 | 51.7 | 45.8 | 13:41 | 25.1 |
| 2025-11-17 | 38.2 | 35.2 | 14:03 | 29.4 |
| 2026-01-30 | 27.5 | 27.2 | 14:22 | 28.4 |
| 2026-02-18 | 27.9 | 23.0 | 14:16 | 36.3 |
| 2026-03-30 | 38.6 | 28.2 | 14:29 | 43.8 |
| 2026-04-01 | 17.7 | 15.5 | 13:36 | 45.0 |
| 2026-04-08 | 27.3 | 31.0 | 14:01 | 44.2 |
| 2026-05-08 | 16.0 | 13.5 | 13:55 | 24.4 |
| 2026-05-21 | 32.1 | 27.2 | 13:55 | 27.4 |

**Mean depth:** 29.5 pts | **Median:** 27.5 pts | **Range:** 14.1 - 53.6

---

## Appendix B: Execution Checklist

### Iteration 1 (COMPLETE)
- [x] Build Neg-A population (n=33)
- [x] Run Track 1 (point-in-time snapshot) — all segments, all neg definitions
- [x] ITERATION 1 GATE: d >= 0.8 found? **YES — volume, d=-1.524** (later revised, see below)
- [x] Decision: pivot from Greek profiles to volume/flow dynamics

### Confound Resolution (COMPLETE — 2026-05-24)
- [x] **GATE CHECK:** Trough-time distribution (d=-3.405, definitional)
- [x] Determine trough-time is OUTCOME VARIABLE, not matchable covariate
- [x] Build time-of-day baseline (246 days, per-minute OPRA volume)
- [x] Time-normalize volume comparison: d=+0.842 (REVERSED direction), p=0.014
- [x] Discover 0DTE fraction signal: d=+1.381 (strongest signal)
- [x] Build Neg-B (n=57), Neg-C (n=7, marginal), Neg-D (n=13, depth+LATR matched)
- [x] Revise hypothesis: EXHAUSTION -> CLIMAX
- [x] **REVISED GATE:** Original d=-1.524 was mechanical artifact; true signal is time-normalized d=+0.842

### Iteration 2 (READY — hypotheses revised)
- [x] Build Neg-B, Neg-C, Neg-D populations
- [ ] Track A: Volume CLIMAX dynamics (time-normalized surge, peak timing, 0DTE composition)
- [ ] Track B: Premium SURGE (premium flow velocity INTO trough, not away)
- [ ] Track C: DTE composition dynamics (0DTE fraction temporal, bucket migration)
- [ ] ES Baseline: Price microstructure features
- [ ] Track D: Composite construction (feature screening, PCA, simple composite)
- [ ] ITERATION 2 GATE: Composite d >= 1.0 with 3+ component features at d >= 0.5?

### Iteration 3 (CONDITIONAL)
- [ ] Elastic net logistic regression on composite features
- [ ] Leave-one-out cross-validation
- [ ] Score all 243 days
- [ ] Soft validation against borderline days
- [ ] IV surface exploration (speculative, if time permits)
- [ ] ITERATION 3 GATE: LOO accuracy > 70%, FPR < 20%?
- [ ] Final report with honest power assessment

---

## Appendix C: Confound Resolution Artifacts (2026-05-24)

### Analysis Script

`scripts/measurement/trough_time_volume_analysis.py` — computes the time-of-day volume baseline from the full 246-day corpus and performs the time-normalized comparison.

### Time-of-Day Volume Baseline (per-minute, all OPRA SPXW trades)

| Time Window (CT) | Mean Volume (contracts/min) |
|-----------------|---------------------------:|
| 13:00-13:10 | 7,754 |
| 13:10-13:20 | 7,818 |
| 13:20-13:30 | 7,109 |
| 13:30-13:40 | 7,625 |
| 13:40-13:50 | 7,381 |
| 13:50-14:00 | 8,135 |
| 14:00-14:10 | 8,330 |
| 14:10-14:20 | 8,339 |
| 14:20-14:30 | 8,103 |
| 14:30-14:40 | 9,566 |
| 14:40-14:50 | 10,224 |
| 14:50-15:00 | 14,530 |

Note: Volume rises ~90% from 13:00 to 14:55 (gamma-driven 0DTE hedging). This gradient is the mechanical confound — later troughs mechanically face higher baseline volume.

### Non-0DTE Volume Baseline (per-minute)

| Time Window (CT) | Mean Volume (contracts/min) |
|-----------------|---------------------------:|
| 13:00-13:10 | 1,784 |
| 13:10-13:20 | 1,966 |
| 13:20-13:30 | 1,765 |
| 13:30-13:40 | 2,038 |
| 13:40-13:50 | 2,044 |
| 13:50-14:00 | 2,392 |
| 14:00-14:10 | 2,275 |
| 14:10-14:20 | 2,441 |
| 14:20-14:30 | 2,368 |
| 14:30-14:40 | 3,030 |
| 14:40-14:50 | 3,668 |
| 14:50-15:00 | 5,546 |

Non-0DTE volume has an even STEEPER late-day gradient (3.1x from 13:00 to 14:55), explaining why non-0DTE raw comparison was most distorted.

### Neg-B Population (n=57)

Days with depth in [14.1, 64.3] pts (V-day range x 1.2) that closed below VWAP. Mean trough: 103.2 min since 13:00 (14:43 CT).

### Neg-C Population (n=7)

Days with depth >= 15 pts, trough in [13:30, 14:45) CT, recovery < 50%. **MARGINAL** — too small for reliable inference. Exists primarily as a sanity check.

### Neg-D Population (n=13, depth+LATR matched)

Propensity-matched on depth (w=0.6) and LATR (w=0.4). Trough time NOT matched (impossible — definitional outcome). Match quality: depth d=0.064, LATR d=-0.071.

Matched dates: 2025-08-25, 2025-10-14, 2025-08-05, 2026-05-01, 2026-02-13, 2026-02-05, 2025-11-05, 2026-01-07, 2026-02-05, 2026-03-27, 2026-03-12, 2025-07-10, 2025-10-30.
