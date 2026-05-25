# Post-Entry Tape Study — Late-Day Drop Position Management

**Bead:** st-745 (reframed from Greek discovery plan)
**Date:** 2026-05-25
**Status:** PHASES 1-5,7 COMPLETE — Phase 6 (CONTINUATION contrast) pending

### Completed Phases

- [x] **Phase 1:** May 21 reconstruction (tape_reconstruction.py, tape_2026-05-21.json)
- [x] **Phase 2:** All 13 V-day tape profiles (tape_profiles/*.json)
- [x] **Phase 3:** Scare dip catalog — 149 dips, 0 reversals (scare_dip_catalog.jsonl)
- [x] **Phase 4:** Consolidation patterns — 3 events, all resolved upward
- [x] **Phase 5:** Premium trajectory atlas (premium_trajectories.json)
- [ ] **Phase 6:** CONTINUATION day contrast (pending)
- [x] **Phase 7:** Recognition library v1 (recognition-library.md)

## The Question

You enter every late-day drop with a tight stop-loss. Loss avoidance is almost secondary.
The real question: **how do you read the tape after entry to maximize profit instead of bailing early?**

This is not a classification study ("should I enter?"). Entry is assumed.
This is a recognition study: what patterns exist in the post-entry tape, how do they
vary, and what does each pattern mean for hold/scale/exit decisions?

## The Anchor: May 21, 2026

The case that defines the problem:

| Event | Time (CT) | ES Price | Premium | Action |
|-------|-----------|----------|---------|--------|
| Trough | 13:55 | 7438.0 | — | Drop bottoms |
| Entry | ~14:00 | ~7440-7445 | $1.10 | Bought 3 contracts after bounce confirmation |
| Sharp rise | 13:55→14:20 | 7438→~7455 | $1.10→$2.20+ | Price recovers ~17pts in 25min |
| Scare dip | ~14:20 | ~7450 | ~$2.20 | Sold 1 contract (dip spooked) |
| Extended consolidation | 14:20→14:50 | ~7445-7455 | $2.00-2.50 | Price oscillates near 7450 strike |
| Exit | ~14:50 | ~7450 | ~$2.30 | Sold remaining 2 (uncertainty) |
| Close | 15:00 | 7465.25 | ~$5+ | Contracts worth 2x what Steve sold for |

**Money left on the table:** ~$2.70/contract x 200 contracts = ~$540 on 2 contracts.
The 14:20 sell was ~$2.80/contract early. Total: ~$820 in unrealized profit.

The stop-loss handled the downside. The problem was exiting during noise.

## What This Study Builds

A **recognition library** — not a model, not a classifier. A field guide for reading
live conditions while you're in the trade. The output is: "I've seen this pattern
before, here's what it looked like across 13 historical V-days, and here's what the
tape typically did next."

### Deliverables

1. **Per-V-day tape profiles** — minute-by-minute reconstruction from trough to close
2. **Scare dip catalog** — every intra-recovery pullback, its character, and what followed
3. **Consolidation pattern taxonomy** — what consolidation looks like before continuation vs. before fade
4. **Profit trajectory atlas** — premium available at each minute post-entry across all V-days
5. **Recognition reference cards** — synthesized patterns with live-readable signatures

---

## Phase 1: May 21 Reconstruction (ANCHOR CASE)

Reconstruct the complete post-trough tape for May 21 at 1-minute resolution.
This becomes the reference that every other V-day is compared against.

### 1A: ES Price Trajectory

From the corpus (`data/corpus/2026-05-21/databento_glbx_es.jsonl`):

- 1-second price grid from 13:50 to 15:00 CT (10 min pre-trough through close)
- Per-minute: OHLC, VWAP, range, trade count
- Identify every pullback > 2pts during the recovery
- Compute bounce velocity: pts/min in first 5 minutes post-trough
- Mark Steve's decision points on the timeline

### 1B: OPRA Volume Dynamics

From the corpus (`data/corpus/2026-05-21/databento_opra.jsonl`, 435K records):

- Per-minute SPXW volume (contracts) from 13:50 to 15:00 CT
- Time-normalize using the 246-day baseline (from `trough_time_volume_analysis.py`)
- Split by: 0DTE vs non-0DTE, puts vs calls, ATM (±10pts) vs OTM
- Track the volume climax resolution: does volume fall off a cliff after trough, or taper?
- Premium flow (sum of size * price * 100) per minute — total dollars moving through options

### 1C: Premium Trajectory

For contracts representative of Steve's trade (calls or bull spreads near 7450 strike):

- Track actual traded prices of the specific strike/expiry throughout 13:55-15:00
- Map: at each minute, what was the last-traded premium?
- Identify the "regret curve": premium vs time, with Steve's actual sells marked
- Compute: how much profit was available at each minute post-entry?

### 1D: Scare Dip Decomposition

For the ~14:20 dip that triggered Steve's first sell:

- Depth (pts from local high)
- Duration (minutes)
- Volume character during the dip: surging (real selling) or declining (noise)?
- Premium behavior during the dip: sharp drop or gentle?
- What happened immediately after: continuation higher or more selling?

**Output:** A single comprehensive 1-page timeline of May 21, annotated with volume/premium overlays and Steve's decision points. This is the reference document.

---

## Phase 2: All-V-Day Tape Profiles (13 days)

Apply Phase 1's methodology to all 13 confirmed V-days. The window expands from
the old plan's T-20 to T+10 (30 minutes) to **trough minus 10 through close**
(~60-75 minutes depending on trough time).

### V-Day Corpus (with trough times)

| Date | Trough CT | Depth (pts) | Recovery (pts) | Minutes to Close |
|------|-----------|-------------|----------------|-----------------|
| 2025-08-11 | 14:56 | 19.5 | 12.5 | 4 |
| 2025-09-17 | 13:54 | 53.6 | 48.8 | 66 |
| 2025-09-29 | 14:15 | 14.1 | 18.0 | 45 |
| 2025-10-13 | 14:01 | 19.2 | 13.0 | 59 |
| 2025-10-29 | 13:41 | 51.7 | 45.8 | 79 |
| 2025-11-17 | 14:03 | 38.2 | 35.2 | 57 |
| 2026-01-30 | 14:22 | 27.5 | 27.2 | 38 |
| 2026-02-18 | 14:16 | 27.9 | 23.0 | 44 |
| 2026-03-30 | 14:29 | 38.6 | 28.2 | 31 |
| 2026-04-01 | 13:36 | 17.7 | 15.5 | 84 |
| 2026-04-08 | 14:01 | 27.3 | 31.0 | 59 |
| 2026-05-08 | 13:55 | 16.0 | 13.5 | 65 |
| 2026-05-21 | 13:55 | 32.1 | 27.2 | 65 |

**Note:** 2025-08-11 troughs at 14:56 — only 4 minutes to close. This day has almost
no post-entry window and should be treated as an outlier for position management.

### Per-Day Extraction (automated script)

For each V-day, produce a standardized feature set:

**ES Price:**
- 1-minute OHLC from T-10 to close
- Bounce velocity: pts recovered in first 5, 10, 15 minutes
- Number of pullbacks > 2pts during recovery
- Maximum pullback depth during recovery (deepest scare dip)
- Final recovery as % of depth
- Time to recover 50% of depth, 75%, 100%

**OPRA Volume (time-normalized):**
- Per-minute volume ratio (observed/expected) from T-10 to close
- Volume climax timing: minute of peak volume relative to trough
- Post-climax decay rate: how fast does volume fall after the peak?
- Put/call volume ratio evolution post-trough
- 0DTE fraction evolution post-trough

**Premium Flow:**
- Per-minute total put premium, total call premium
- Premium climax timing (separate from volume climax — same minute or different?)
- Call premium awakening: when does call premium first exceed put premium?
- Total premium in window as multiple of daily average

### Output

13 tape profiles in a standardized format. Side-by-side comparison possible.

---

## Phase 3: Scare Dip Catalog

The critical question for hold/scale decisions: **when price pulls back during a
recovery, is this noise or a real reversal?**

### Definition

A "scare dip" is any pullback > 2 points from a local high during the post-trough
recovery phase. This threshold is approximately the minimum move that would affect
premium enough to create exit pressure.

### For Each Scare Dip, Record:

| Feature | Description |
|---------|-------------|
| Depth | Points from local high |
| Depth % | As % of recovery-so-far |
| Duration | Minutes from local high to local low |
| Volume character | Time-normalized volume during the dip vs. during the preceding rise |
| Premium impact | % change in representative contract premium during the dip |
| Recovery time | Minutes from dip low back to prior high |
| Context | Minutes since trough, % of total recovery already captured |
| Outcome | Price 5 and 15 minutes after dip low |

### Analysis

- **Total scare dip count** across 13 V-days (expected: 30-60 events)
- **Depth distribution**: how deep are typical scare dips? (expect: 2-8 pts)
- **Volume signature**: do scare dips have lower, similar, or higher time-normalized volume than the preceding rise?
- **Duration distribution**: how long do they last? (expect: 1-5 minutes)
- **Sequential pattern**: do scare dips cluster early in recovery, late, or uniformly?
- **Worst-case dip**: across all V-days, what's the deepest intra-recovery pullback?

### The Key Comparison

For each dip, what happened after?
- **Continuation** (price exceeded prior high within 10 minutes)
- **Consolidation** (price stayed within the dip range for 10+ minutes before continuing)
- **Reversal** (price never recovered the prior high — this should be rare on V-days)

What tape features at the dip distinguish these outcomes? This is the actionable core:
"I'm seeing a 4-point pullback at 14:20 — should I hold or cut?"

---

## Phase 4: Consolidation Patterns

When price stalls after the initial bounce, what does the tape tell you about whether
it will continue higher or fade?

### Definition

A consolidation zone is a period of 5+ minutes where ES price stays within a 5-point range
after having risen 10+ points from the trough.

### For Each Consolidation Zone:

| Feature | Description |
|---------|-------------|
| Entry price | ES price when consolidation began |
| Recovery so far | Points recovered from trough |
| Range | High-low during consolidation |
| Duration | Minutes |
| Volume trend | Time-normalized volume: rising, flat, or declining during consolidation |
| Premium behavior | Is contract premium holding, leaking, or building? |
| Put/call shift | Does the P/C ratio change during consolidation? |
| Outcome | Did price break up, down, or fade to close? |
| Post-consolidation move | Points gained/lost in 10 minutes after breakout |

### Taxonomy

Expect to find 2-4 distinct consolidation patterns:

1. **Compression before continuation** — range narrows, volume declines, then breaks higher
2. **Absorption** — repeated tests of the range top with buying volume, eventual breakout
3. **Distribution** — range holds but volume picks up on the downside tests
4. **Drift to close** — range narrows, volume dies, price settles near consolidation midpoint

Patterns 1 and 2 favor holding. Pattern 3 favors scaling out. Pattern 4 is the theta-bleed
scenario where holding costs money (premium decays while price goes nowhere).

### Premium Decay During Consolidation

This is specific to the position management problem. During consolidation, theta is eating
the premium even if delta is neutral. Measure:

- Premium at consolidation start vs. end
- Premium decay rate per minute during consolidation
- Does premium recovery after breakout exceed the theta lost during consolidation?

---

## Phase 5: Profit Trajectory Atlas

For each V-day, model the premium trajectory that a representative directional trade
would have experienced from entry to close.

### Trade Model

Since we have full OPRA trade data, we can reconstruct actual traded premiums for
representative contracts. For each V-day:

1. Select contracts near the trough price (ATM calls or bull put spreads)
2. Track last-traded premium at 1-minute intervals from trough to close
3. Compute: profit at each minute post-entry assuming entry at first-traded premium post-trough

### Premium Curve Classification

Across 13 V-days, the premium curves should cluster into recognizable shapes:

- **Rocket**: premium rises sharply and continuously (deep V, strong momentum)
- **Staircase**: premium rises in steps with flat periods (consolidation between moves)
- **Front-loaded**: most premium gain in first 15 minutes, then flattens (shallow V)
- **Slow grind**: gradual premium increase all the way to close (wide V, late trough)

### The "Regret Window" Analysis

For each V-day: at what point in the recovery was premium at 50% of its eventual maximum?
At 75%? At 90%? This tells Steve: "historically, at minute T+15, you've captured about
X% of the available profit — here's how much more was typically available."

### Maximum Drawdown During Hold

For each V-day premium curve: what was the worst peak-to-trough drawdown in premium
between entry and close? This is the "scare" intensity — how bad does it get before
it gets better?

---

## Phase 6: CONTINUATION Days as Contrast

The old plan's negative classes remain useful — not for classification, but for
contrast. What does the tape look like on days where the bounce FAILS?

### Subset

Use Neg-A (n=33) as the primary contrast. These are days with similar depth but no
recovery. The tape after the trough looks fundamentally different:

- No sustained bounce (or bounce that fails within minutes)
- Volume doesn't resolve — selling continues at baseline or above
- Premium never recovers — directional trades bleed to zero
- Scare dips lead to more selling rather than stabilization

### Differential Features

For each Phase 2-5 feature, compute the same metric for CONTINUATION days.
The contrast sharpens recognition: "on V-days the tape looks like THIS;
on continuation days the tape looks like THAT."

### Stop-Loss Calibration

Since Steve uses a tight stop-loss, measure: on CONTINUATION days, how quickly does
the trade go underwater? This validates the stop-loss approach:

- Time from trough to first new low (invalidating the bounce)
- How many minutes of "false hope" before the bounce fails?
- Premium behavior: how fast does premium decay on a failed bounce?

This isn't the study's primary focus but anchors the "loss avoidance is secondary"
stance with data: if the stop handles CONTINUATION days efficiently, the entire
focus correctly shifts to profit maximization on V-days.

---

## Phase 7: Recognition Library Construction

Synthesize Phases 1-6 into reference cards.

### Card Format (per pattern)

```
PATTERN: [Name]
FREQUENCY: Appeared in X/13 V-days
SIGNATURE: [What you see on the tape at the moment of recognition]
  - ES: [price behavior description]
  - Volume: [time-normalized volume behavior]
  - Premium: [how your contracts are behaving]

HISTORICAL PREMIUM TRAJECTORY:
  T+5:  [median premium multiple from entry]
  T+15: [median premium multiple]
  T+30: [median premium multiple]
  T+60: [median premium multiple]
  Close: [median premium multiple]

SCARE DIPS IN THIS PATTERN:
  Count: [typical number]
  Max depth: [typical worst pullback]
  Character: [what they look like]

MANAGEMENT APPROACH:
  [Hold/scale/trail-stop guidance based on the historical data]

ANCHOR EXAMPLES: [dates that exemplify this pattern]
```

### Expected Patterns (hypothesized, to be confirmed)

**1. Volume Climax V** (expected: 4-6 of 13 days)
- Massive volume surge at trough (ratio >> 1.5), sharp dropoff
- Price bounces hard and fast — most recovery in first 15 minutes
- Scare dips are shallow (2-4 pts) and short (1-2 min)
- Premium doubles in first 10-15 minutes, then grinds higher
- Historical hold to close captures 3-5x entry premium
- Anchor: probably Sep 17 (53pt depth), Oct 29 (51pt depth)

**2. Grinding Recovery** (expected: 3-5 of 13 days)
- Volume elevated but not climactic
- Price recovers steadily — 1-2 pts per 5 minutes, extended over 30-60 minutes
- Scare dips moderate (3-6 pts) and more frequent
- Premium builds slowly — patience required
- Anchor: probably Jan 30, Feb 18

**3. Consolidation-Then-Pop** (expected: 2-4 of 13 days)
- Price bounces to a level and stalls (consolidation zone)
- Volume drops during consolidation (sellers exhausted, buyers waiting)
- Eventually breaks higher with a fresh volume impulse
- Premium gains mostly in the post-consolidation leg
- May 21 looks like this pattern
- Anchor: May 21

**4. Shallow V / Quick Exhaustion** (expected: 2-3 of 13 days)
- Smaller drops (14-20 pts), less dramatic recovery
- Volume barely above baseline
- Premium gain limited (1.5-2x entry)
- Stop-loss risk is LOW but upside is also limited
- Anchor: probably Sep 29 (14pt depth), May 8 (16pt depth)

---

## Execution Plan

### Infrastructure Reuse

From the old plan, carry forward:
- `trough_time_volume_analysis.py` → time-of-day baseline (246-day per-minute volume curve)
- `detect_v_days.py` → V-day corpus with trough timestamps
- `v_days.jsonl` → per-day metadata
- OPRA record parser (timestamp handling, symbol parsing, DTE computation)
- Statistical utilities (Cohen's d, permutation test, bootstrap CI)

### New Scripts

| Script | Phase | Description |
|--------|-------|-------------|
| `tape_reconstruction.py` | 1-2 | Build per-day 1-minute tape from trough-10 to close (ES + OPRA) |
| `scare_dip_catalog.py` | 3 | Detect and characterize all intra-recovery pullbacks |
| `consolidation_detector.py` | 4 | Identify and classify consolidation zones |
| `premium_trajectory.py` | 5 | Track contract premium curves trough-to-close |
| `recognition_cards.py` | 7 | Generate pattern reference cards from clustered tape profiles |

### Execution Order

```
Phase 1: May 21 reconstruction (standalone, immediate)
   |
   v
Phase 2: All-V-day tape profiles (reuses Phase 1 script, parallel across days)
   |
   +---> Phase 3: Scare dip catalog (reads Phase 2 output)
   |
   +---> Phase 4: Consolidation patterns (reads Phase 2 output)
   |
   +---> Phase 5: Premium trajectories (reads Phase 2 output)
   |
   v
Phase 6: CONTINUATION contrast (same pipeline on Neg-A days)
   |
   v
Phase 7: Recognition library (synthesis of all phases)
```

Phases 3, 4, 5 can run in parallel once Phase 2 completes.

### Statistical Framework

**Carried forward from old plan:**
- Permutation testing (10,000 permutations)
- Cohen's d with bootstrap CI
- Benjamini-Hochberg FDR correction
- All volume metrics time-normalized

**New for this plan:**
- Within-pattern variance: how consistent is each pattern across its member days?
- Temporal correlation: are Phase 3 scare dip features predictive of Phase 5 premium outcomes?
- No classification model needed — the output is descriptive, not predictive

### Decision Gates

Unlike the old plan's d >= 1.0 composite gates, this study's gates are:

1. **Phase 1 gate:** Does the May 21 reconstruction match Steve's described experience?
   If the tape doesn't show the scare dip at ~14:20 and consolidation he described,
   the data pipeline has a problem.

2. **Phase 2 gate:** Do the 13 V-days show enough variety to support a taxonomy?
   If all 13 look identical, there's one pattern, not a library. If all 13 are unique,
   there's no generalizable pattern.

3. **Phase 3 gate:** Are scare dips distinguishable from real reversals using tape features?
   If volume/premium during dips is indistinguishable from the surrounding recovery,
   the recognition library can't help with hold/exit decisions.

4. **Phase 7 gate:** Can the recognition cards pass the "Steve test" — would Steve,
   sitting in a live trade, be able to identify which pattern he's seeing and act on it?

---

## What Changed From the Greek Discovery Plan

| Old Plan | New Plan |
|----------|----------|
| Question: should I enter? | Question: how do I manage after entry? |
| Window: T-20 to T+10 (30 min around trough) | Window: T-10 to close (60-80 min post-trough) |
| Output: classifier (PIVOT vs CONTINUATION) | Output: recognition library (pattern field guide) |
| Focus: volume/Greek signals at the trough | Focus: tape behavior during recovery |
| V-days vs CONTINUATION as classes | V-days as primary; CONTINUATION as contrast only |
| Composite score with d >= 1.0 gate | Pattern taxonomy with live-readability gate |
| Iteration 2-3 track system | Phase 1-7 sequential with parallel inner phases |
| Tracks A-D: volume, premium, DTE, composite | Phases: reconstruction, scare dips, consolidation, premium, recognition |

### What Carries Forward

- The volume climax finding (d=+0.842) — relevant because it describes what happens AT entry
- Time-normalization methodology — mandatory for all volume comparisons
- 0DTE composition finding (d=+1.381) — useful for understanding post-trough flow shifts
- The trough-time confound resolution — prevents naive comparison errors
- The Neg-A/B/D populations — used in Phase 6 contrast
- The per-minute OPRA parser and statistical utilities

### What's Dropped

- Greek snapshot analysis (per-contract Greeks don't separate — confirmed)
- IV pin theory (doesn't beat null model — confirmed)
- Day type classifier (PIVOT vs CONTINUATION classification — no longer the question)
- Elastic net / LDA model building (no classifier needed)
- Leave-one-out cross-validation (no model to validate)
- IV surface exploration (speculative, no signal in snapshots)

---

## Appendix: Known Limitations

1. **n=13 V-days.** The recognition library is built on 13 examples. Patterns with
   3-5 members have very wide confidence intervals. Every new V-day that occurs
   in live trading is an opportunity to update the library.

2. **Trough identified ex-post.** In real-time, Steve doesn't know the trough is in.
   He waits for bounce confirmation (as on May 21). Phase 1C should quantify: how
   much of the premium move happens between the actual trough and the point where
   the bounce is "confirmed"? This is the cost of waiting for confirmation.

3. **No bid/ask quotes.** Cannot determine urgency (hitting bid vs lifting offer).
   Volume is total volume, not net directional flow.

4. **Premium reconstruction is approximate.** We have last-traded prices, not a
   continuous mark-to-market. Illiquid strikes may have stale quotes.

5. **Scare dip sample size.** If there are 30-60 scare dips across 13 days, subsetting
   by outcome (continuation vs reversal) may leave subgroups too small for statistical
   confidence. The catalog is still useful as a reference even without statistical power.

6. **No position-specific modeling.** The premium trajectory assumes a generic
   directional trade. Steve's actual trade structure (butterfly, vertical spread,
   naked call) affects the exact premium curve. The ES price trajectory and volume
   patterns are trade-structure-agnostic.
