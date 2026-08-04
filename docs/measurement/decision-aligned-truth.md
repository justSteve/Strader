# Decision-Aligned Continuation — What the Tape Answers When You Ask the Right Question

**Bead:** Decision Aligned Truth (st-kqvj) · from the cold-context audit
`docs/audits/2026-08-04-auditor-report.md` §1.1, §1.3, §3.1
**Date:** 2026-08-04 · **Script:** `scripts/measurement/decision_aligned_study.py` →
`data/measurement/decision_aligned_truth.json`
**Data:** the same 22 July morning-move days, the same 1,882 labeled minutes,
the same nine traces as `morning_flush_continuation.py` — rebuilt from the ES
corpus and the Schwab internals candles, then verified minute-for-minute
against the stored study: **1,860 minutes matched, 0 label mismatches, 0 trace
mismatches**. Every number below was computed by that script in this session.

> **Grid note.** This study stays pinned to the audited 10:15 CT grid (1,882
> minutes) so every number here is directly comparable to the auditor's report.
> The baseline script has since adopted the report's §3.5 truncation fix
> (last labeled minute 10:15 → 10:14, one minute per day, 1,882 → 1,860), which
> is why 22 minutes — all of them 10:15 — are in this study and not in the
> current stored output. The parity check confirms the two agree on every
> minute they share. Re-running this script prints that reconciliation as
> `VERIFY [PARITY-ON-OVERLAP]` and records it in the JSON's
> `meta.verify_vs_stored`.

---

## 1. The question the meter was answering, and the question you were asking

The continuation program calls a minute **CONT** if price extends ≥ 2 pts
**beyond the highest (or lowest) price the move has printed so far**, within 15
minutes. Read that again slowly, because the whole framework hangs on it:

> If price has backed off 15 pts from the move's extreme and you are sitting in
> it, that label asks whether price will travel **17 pts** — back to the
> extreme, then 2 more. If price is *sitting on* the extreme, the same label
> asks whether it will travel **2 pts**.

The target moves away from you exactly when you are hurting. So the label is
mostly a restatement of *how far price currently sits inside its own extreme* —
geometry you can read off a chart with no market data at all. Measured: raw
distance-to-extreme grades that label at **AUC 0.790** (day-median 0.811). The
three-trace convergence score — the program's deliverable, the thing on the
pane — grades it at **0.678** (day-median 0.607). The instrument is a worse
proxy for the label than the label's own construction.

What you actually ask, standing in a position at 09:12 with the move 30 pts old:

> **From here, does this pay me N points before it takes M points out of me,
> in the next quarter hour?**

This document relabels the identical minutes with that question and reports
what survives. Short version: **almost nothing survives, and what little does
is the clock.**

---

## 2. The labels — which question each one encodes

Eleven labels, all measured over the same 15-minute forward window from the
**close of the labeled minute** (not from the standing extreme):

| Label key | The question it encodes | Honest use |
|---|---|---|
| `orig_ext2_beyond_standing_extreme` | Will the move print a new extreme 2 pts past its high-water mark? | A **breakout re-entry trigger**. A legitimate question — just not the one a position holder asks. Kept here so every number stays comparable to the published study. |
| `reach2_any_adverse` / `reach5_` / `reach8_` | Does price gain 2 / 5 / 8 pts my way at any point in 15 min? | Target-only. Ignores what you endure to get there — so it flatters every hold. |
| `reach{N}_before_adverse{M}` (N ∈ 2/5/8, M ∈ 4/8) | Does it pay N **before** it takes M out of me? | **The decision.** Resolved in path order on the raw tick stream — which barrier came first is not recoverable from a minute bar's high and low. |
| `fav_exceeds_adverse` | Over 15 min, is the best it offers bigger than the worst it does? | Threshold-free framing. Balanced base rate (.672), so a coin-flip AUC here is not a degenerate-label artifact. |

**One caveat that colours everything below.** The move's *direction and start
time* both come from `primary_move()` in `morning_flush_study.py`, which scans
the whole 08:30–10:30 window and takes the larger of max-drawdown and
max-drawup. That is hindsight, twice over. Every base rate in this document —
like every base rate in the program — is conditioned on already knowing which
way the morning went and where it began. They describe *how a move behaves once
you know it is the move*, not what you can capture live. The audit's §3.4
sharpens the direction half: on 07-30 and 07-10 the assignment was decided by
0.75 and 1.00 points respectively.

The start-time half matters specifically for the one predictor that survives.
**Move age is not live-computable as defined here** — it counts from a peak or
trough you can only identify afterwards. Session clock is. They are the same
predictor inside a day (§4.2), and session clock gives up only 1–2 points of
AUC across the board (.540 vs .548 on "2 before 4", .599 vs .619 on "8 before
8"). So the honest live form of the surviving signal is *time of session*, and
nothing is lost by using it.

---

## 3. The base rates, with intervals

Day-block bootstrap, 4,000 resamples, **whole days resampled** — minutes inside
a day are heavily autocorrelated, and resampling minutes would understate every
interval below by a large factor.

| Label | n | base rate | 95 % CI |
|---|---|---|---|
| original: ≥ 2 pts beyond standing extreme | 1,882 | **.569** | [.494, .651] |
| ≥ 2 pts from here (no stop) | 1,882 | **.919** | [.890, .943] |
| ≥ 5 pts from here (no stop) | 1,882 | **.762** | [.689, .822] |
| ≥ 8 pts from here (no stop) | 1,882 | **.604** | [.516, .684] |
| favourable excursion > adverse | 1,882 | **.672** | [.640, .707] |
| **2 pts before 4 against** | 1,882 | **.735** | [.716, .754] |
| **2 pts before 8 against** | 1,882 | **.866** | [.843, .886] |
| **5 pts before 4 against** | 1,882 | **.522** | [.477, .562] |
| **5 pts before 8 against** | 1,882 | **.693** | [.633, .738] |
| **8 pts before 4 against** | 1,882 | **.394** | [.344, .436] |
| **8 pts before 8 against** | 1,882 | **.545** | [.472, .609] |

The first four rows reproduce the auditor's §3.1 table (.919 / .762 / .604 /
.672) to three decimals. The six bold rows are new — they are the rows with a
stop in them.

**What the barrier costs.** A 5-pt target is reached at *some* point in the next
15 minutes 76.2 % of the time. Require it to arrive before a 4-pt drawdown and
that falls to **52.2 %**. The 24-point gap is the tape going against you first,
and it is the difference between a study number and a trade.

---

## 4. The clock — the only thing that still grades anything

### 4.1 By move age (minutes since the move began)

| Label | 0–10 min | 10–20 | 20–40 | 40+ |
|---|---|---|---|---|
| **original label** | **.914** [.823, .986] | .732 [.586, .868] | .650 [.491, .807] | **.422** [.296, .560] |
| ≥ 2 from here | .982 [.950, 1.000] | .946 [.900, .982] | .941 [.909, .971] | .889 [.848, .927] |
| ≥ 5 from here | .918 [.814, .986] | .791 [.654, .909] | .834 [.746, .911] | .691 [.608, .772] |
| ≥ 8 from here | .795 [.673, .904] | .705 [.550, .846] | .705 [.589, .807] | .496 [.380, .611] |
| 2 before 4 | .809 [.768, .850] | .714 [.645, .782] | .777 [.739, .816] | .706 [.672, .742] |
| 5 before 4 | .654 [.554, .741] | .536 [.423, .645] | .550 [.475, .623] | .478 [.426, .532] |
| 5 before 8 | .836 [.732, .918] | .714 [.582, .832] | .761 [.670, .839] | .628 [.561, .693] |
| 8 before 8 | .723 [.600, .832] | .636 [.486, .777] | .639 [.529, .739] | .445 [.345, .544] |
| fav > adverse | .859 [.773, .932] | .686 [.541, .823] | .759 [.661, .846] | .589 [.512, .668] |
| n minutes | 220 | 220 | 440 | 1,002 |

The original label's 91.4 % → 42.2 % collapse (the audit's §1.3 headline)
reproduces exactly. **But look at what happens to that collapse under the
decision labels**: "2 pts before 4 against" runs .809 → .706, a 10-point spread
where the original label spans 49 points. The clock's apparent power over the
old label was itself partly geometry — early in a move, price is near its
extreme by construction.

The clock survives best where the target is large relative to the stop: "8 pts
before 8 against" still runs **.723 → .445**, a 28-point spread, and "5 before
8" runs .836 → .628.

### 4.2 By session clock (CT)

| Label | pre-09:00 | 09:00–10:00 | post-10:00 |
|---|---|---|---|
| **original label** | **.854** [.725, .956] | .540 [.440, .642] | **.420** [.241, .614] |
| ≥ 2 from here | .968 [.927, .997] | .908 [.878, .937] | .912 [.849, .966] |
| 2 before 4 | .789 [.742, .834] | .723 [.696, .752] | .730 [.668, .793] |
| 5 before 4 | .607 [.500, .699] | .497 [.454, .542] | .534 [.435, .628] |
| 5 before 8 | .795 [.683, .885] | .669 [.611, .719] | .688 [.571, .795] |
| 8 before 8 | .698 [.573, .801] | .515 [.433, .588] | .517 [.389, .642] |
| fav > adverse | .808 [.687, .912] | .622 [.559, .683] | .724 [.614, .824] |
| n minutes | 308 | 1,222 | 352 |

Session clock and move age are **the same predictor inside a single day** —
they differ by a constant, so their per-day AUCs are identical (see the AUC
table: .875 / .875 on the original label, .523 / .523 on "2 before 4"). They
differ only in how they pool across days. Do not treat them as two independent
confirmations.

Note the shape: pre-09:00 is the strong window on every label, but 09:00–10:00
and post-10:00 are indistinguishable from each other on the decision labels.
16 of the 22 moves start before 09:00 CT, and the audit (§1.1) flags that this
is squarely the 09:00 CT data-release window — a calendar channel this program
has never recorded.

---

## 5. What you endure: the excursion distribution

From an arbitrary labeled minute, over the next 15 minutes (SPX points,
move-direction oriented):

| | p10 | median | p90 | max |
|---|---|---|---|---|
| favourable excursion (MFE) | 2.25 | **9.75** | 23.25 | 45.75 |
| adverse excursion (MAE) | 0.75 | **4.75** | 12.75 | **31.25** |
| mark-out at +15 min | −7.25 | +4.75 | +18.00 | — |

**P(adverse ≥ 4 pts) = .569. P(adverse ≥ 8 pts) = .293.** Nearly one minute in
three hands you an 8-point drawdown inside a quarter hour, in a regime whose
median move was 52.6 pts. This is the number that should size a position, and
it is nowhere in the program's outputs.

It also puts a floor under the audit's §6.6 objection to the "8-pt structural
stop." An 8-pt stop is not a rare structural event on this tape; it is a
29-in-100 event from any given minute.

### The three ways a barriered bet ends

Target-first / stop-first / neither-inside-15-min, all minutes:

| Label | target first | stop first | unresolved | frictionless pts per attempt |
|---|---|---|---|---|
| 2 before 4 | .735 | .251 | .014 | +0.45 [+0.33, +0.57] |
| 2 before 8 | .866 | .110 | .024 | +0.81 [+0.68, +0.95] |
| 5 before 4 | .522 | .434 | .044 | +0.88 [+0.63, +1.14] |
| 5 before 8 | .693 | .216 | .091 | +1.70 [+1.43, +1.99] |
| 8 before 4 | .394 | .519 | .087 | +1.24 [+0.91, +1.56] |
| 8 before 8 | **.545** | .271 | .184 | **+2.35** [+1.90, +2.84] |

**Read the last column with both hands on the table.** It pays +N on a
target-first minute, −M on a stop-first minute, marks unresolved minutes to the
15-minute close, and assumes fills exactly at the barrier with **zero friction
and zero slippage**. Real friction is 0.6–1.2 SPX pts per attempt (audit §6.4),
which erases the "2 before 4" row entirely. Every minute is an overlapping
sample of the same 22 mornings, so these are not 1,882 independent trades. And
the direction is hindsight (§2). This column is a sanity check on the shape of
the payoff — wide stops beat tight ones, consistently — not a backtest, and
certainly not a licence.

The one thing it says cleanly, and it agrees with the chase refutation in
`morning-flush-anatomy.md`: **the tight stop is the expensive part.** Moving the
stop from 4 to 8 pts roughly doubles the frictionless edge at every target.

---

## 6. AUC — every trace against every label, next to the trivial competitors

Aggregate AUC (day-median in parentheses). Every predictor is oriented so
higher = predicts the label; a value below .500 means the orientation is
backwards on that label.

| Predictor | original | 2 before 4 | 5 before 4 | 8 before 8 | fav > adv |
|---|---|---|---|---|---|
| **distance-to-extreme** (geometry) | **.790** (.811) | .497 (.456) | .490 (.451) | .460 (.372) | .493 (.421) |
| **move age** (clock) | **.728** (.875) | **.548** (.523) | **.549** (.546) | **.619** (.696) | **.598** (.602) |
| session clock | .693 (.875) | .540 (.523) | .540 (.546) | .599 (.696) | .569 (.602) |
| clock + geometry blend | **.813** (.927) | .529 (.511) | .526 (.497) | .547 (.473) | .556 (.488) |
| concurrent 5-min ES move | .695 (.676) | .502 (.521) | .500 (.487) | .493 (.432) | .485 (.430) |
| $TICK level × dir | .665 (.600) | .501 (.498) | .487 (.509) | .500 (.448) | .515 (.481) |
| $VIX 5-min slope | .660 (.640) | .486 (.503) | .494 (.475) | .497 (.429) | .487 (.422) |
| $ADD 10-min slope | .653 (.574) | .516 (.501) | .486 (.476) | .503 (.414) | .492 (.437) |
| $VOLD 10-min slope | .638 (.542) | .496 (—) | .469 (—) | .461 (—) | .445 (—) |
| $TICK 10-min sign-share | .638 (.565) | .503 (—) | .488 (—) | .509 (—) | .505 (—) |
| volume pace | .616 (.532) | .509 (—) | .464 (—) | .506 (—) | .491 (—) |
| wiggle-calm | .578 (.580) | .480 (—) | .503 (—) | .510 (—) | .525 (—) |
| ES 5-min aggressor delta | .548 (.634) | .492 (—) | .501 (—) | .463 (—) | .459 (—) |
| $TRIN oriented | .439 (.456) | .497 (—) | .495 (—) | .465 (—) | .467 (—) |
| **convergence score 3/3** | **.678** (.607) | **.501** (.493) | **.486** (.490) | **.491** (.429) | **.500** (.447) |
| **convergence score 2/2** (live meter) | .672 (.650) | .493 (.496) | .493 (.495) | .492 (.428) | .511 (.487) |

(Full 16 × 11 grid, including the unbarriered labels, is in
`decision_aligned_truth.json` under `auc`.)

**What this table says, in order of how much it should change your behaviour:**

1. **Every internals trace is a coin flip on every decision-aligned label.** The
   best any trace manages on any barriered label is $ADD at .516. The
   convergence score — the deliverable, the pane — runs .482 to .501 across the
   six barriered labels. It is not weak; it is *absent*.
2. **The geometry that explained the old label explains nothing here.**
   Distance-to-extreme goes from .790 to .460–.497. That confirms it was never
   an edge; it was the label's own construction reflected back.
3. **The clock is the only survivor, and it is much smaller than it looked.**
   Move age holds .548–.619 on the barriered labels against .728 on the
   original; session clock, which unlike move age is live-computable (§2),
   holds .540–.599. Real, worth conditioning on, nowhere near a trade on its
   own.
4. **The clock+geometry blend is *worse* than the clock alone** on the decision
   labels (.529 vs .548, .547 vs .619). Adding geometry actively dilutes. On the
   original label the blend hit .813 — a near-match to the audit's .815 trivial
   predictor, whose functional form the report does not state, so treat the
   agreement as coincidental rather than as a reproduction.
5. The best single result anywhere in the decision-aligned half of the table is
   **$TICK at .574 on "≥ 2 pts from here, no stop"** — the one decision label
   with no stop in it and a .919 base rate, scored on only 19 of 22 days
   (2 days had no negative minutes at all; a third has no $TICK data),
   day-median .530. That is not a
   finding; it is what a coin flip looks like when you squint.

---

## 7. Where the old framework came apart

### 7.1 The convergence ladder does not survive relabelling

| Convergence score | n | P(original label) | P(5 before 4) | P(8 before 8) |
|---|---|---|---|---|
| 0/3 | 277 | **.253** [.146, .411] | .480 [.396, .567] | .495 [.410, .623] |
| 1/3 | 417 | .489 [.390, .597] | **.602** [.527, .673] | **.633** [.554, .718] |
| 2/3 | 517 | .652 [.558, .745] | .532 [.489, .575] | .592 [.516, .668] |
| 3/3 | 539 | **.729** [.629, .818] | .501 [.452, .550] | .531 [.445, .614] |

The published 25 → 73 % monotone ladder is real *for the label it was built on*.
Under the decision labels it is not monotone and not ordered: it **peaks at 1/3
and declines**, and every cell's interval overlaps every other cell's. All
three traces confirming is associated with a marginally *lower* chance of
making 5 before losing 4 than one trace confirming.

### 7.2 Conditioning on the clock does not rescue it

Within the 40+ minute move-age bucket — a mature move, exactly where a trader
consults a meter about staying in or re-entering:

| score 3 | n | P(original label) | P(5 before 4) |
|---|---|---|---|
| 0/3 | 198 | .157 [.056, .318] | .485 [.393, .573] |
| 1/3 | 218 | .284 [.151, .461] | .537 [.409, .662] |
| 2/3 | 262 | .530 [.375, .689] | .511 [.444, .583] |
| 3/3 | 278 | .644 [.496, .762] | .439 [.340, .527] |

The ladder is intact on the original label inside the bucket (.157 → .644), so
this is not a slicing artifact — the score really does track the standing-extreme
label. On the decision label in the same rows it is flat and slightly inverted.
The same holds in the 09:00–10:00 session bucket: .457 / .572 / .484 / .516
across 199 / 271 / 349 / 343 minutes.

### 7.3 The sentence on the pane is the sharpest failure

`continuation_meter.py` renders: *"Score 3/3 → about 73 % chance the move
extends 2+ pts in the next 15 min."* Read literally by a novice — which is who
it is for — that sentence names the "≥ 2 pts from here, 15 min" label. Measured:

| score 3 | n | P(≥ 2 pts from here in 15 min) |
|---|---|---|
| 0/3 | 277 | **.935** [.890, .978] |
| 1/3 | 417 | .916 [.878, .956] |
| 2/3 | 517 | .932 [.904, .957] |
| 3/3 | 539 | **.929** [.898, .959] |

For the sentence it displays, the meter's 3/3 state is **92.9 %**, not 73 %, and
its 0/3 state — the one the pane reports as **25 %** — is **93.5 %**. The score
carries no information about the sentence written next to it (AUC .506), and
the integer is 20 points low at one end and 68 points low at the other. Same
story for the live two-trace mode: .931 / .919 / .938 against a displayed
33 / 57 / 74 %.

### 7.4 Interval width is the smaller problem, but it is still a problem

The published 25 % state is **[.146, .411]** and the 73 % state is
**[.629, .818]** on their own label. Those are in-sample intervals capturing
day-sampling variance only — the traces, orientations and cell boundaries were
all chosen on these same 22 days, and there is no held-out set.

---

## 8. What a meter should say instead

The lookup is `data/measurement/decision_aligned_truth.json`. Three rules fall
straight out of the numbers above:

1. **Display a label a trader can act on.** "2 pts before 4 against" or "5
   before 4" — with the stop named. A number whose label has no stop in it
   flatters every hold, by 24 points at the 5-pt target.
2. **Condition on the clock, not on the traces.** The clock is the only
   predictor left standing, and it is worth 5–12 points of AUC, not 25. Read the
   cell from `base_rates[label][bucket_family][bucket]`, not a pooled average.
   Use `session_clock` for anything live: move age needs a start time that is
   only knowable in hindsight (§2), and costs 1–2 points of AUC to give up.
3. **Show the interval, or show nothing.** Every cell in the JSON ships
   `ci_lo`/`ci_hi`. The median decision-label cell is **15 points wide** and the
   widest is **30** (`reach8_any_adverse`, post-10:00); a bare integer hides
   that.

And one negative instruction: **do not display the convergence score against a
decision-aligned label at all.** Not scaled, not de-rated, not with a caveat.
At AUC .482–.501 it is noise, and a novice reading a number that moves will
believe the movement means something.

If the score stays on the pane, it must be labelled as what it measures — *the
chance this move prints a new extreme 2 pts past its high-water mark* — which
is a breakout re-entry trigger and a fair thing to want. It is just not an
answer about the position you are holding.

---

## 9. JSON schema — `data/measurement/decision_aligned_truth.json`

Top-level keys (the file also carries a `schema` block describing itself):

| Key | Shape | Use |
|---|---|---|
| `meta` | run provenance: days, universe parameters, bootstrap settings, and `verify_vs_stored` (the parity check against `morning_flush_continuation.json`) | confirm the file is current before consuming it |
| `labels` | `label_key → {question, definition, decision}` | what each label asks, in the trader's words |
| `base_rates` | `[label][bucket_family][bucket] → {n, k, p, ci_lo, ci_hi, n_days}` | **the meter lookup.** `bucket_family` ∈ `all` / `move_age` / `session_clock` |
| `auc` | `[label][predictor] → {auc, auc_day_median, n_days_scored, n_pos, n_neg}` | 16 predictors × 11 labels; below .500 means the orientation is backwards |
| `score_conditional` | flat list of `{score, score_value, label, bucket_family, bucket, n, k, p, ci_lo, ci_hi, n_days}` | P(label) jointly conditioned on convergence score **and** clock |
| `outcome_split` | `[barriered_label][bucket_family][bucket] → {n, p_target_first, p_stop_first, p_neither, pts_per_attempt, pts_ci_lo, pts_ci_hi}` | separates the two ways a barriered label is False |
| `excursions` | MFE / MAE / 15-min mark-out quantiles, `p_mae_ge_4`, `p_mae_ge_8` | position sizing |
| `parity` | `{metric: {expected, got}}` | the 18 audit-report numbers this run reproduces |

Buckets: `move_age` ∈ `0-10` / `10-20` / `20-40` / `40+` (minutes since move
start); `session_clock` ∈ `pre-0900` / `0900-1000` / `post-1000` (CT).
Label keys: `orig_ext2_beyond_standing_extreme`, `reach{N}_any_adverse`,
`reach{N}_before_adverse{M}`, `fav_exceeds_adverse`.

---

## 10. What this does not say

- **It does not say the tape is unreadable.** It says these nine channels, on
  these 22 days, at 1-minute resolution, do not read it. The audit's §1.1 names
  three families never enumerated at all — calendar/event, price location
  relative to prior structure, cross-index (NQ/RTY, already paid for) — and one
  of those may well carry what these do not.
- **It does not resolve direction.** Every number here is conditioned on
  hindsight direction (§2). The program's open question is unchanged.
- **It is 22 clustered July days with no out-of-sample set.** No internals data
  exists before 2026-06-18 (audit package channel table), and Schwab's minute
  history is a rolling ~47-day window (audit §4.3), so the sample cannot be
  backfilled — only grown forward.
- **The 15-minute horizon is inherited, not justified.** It is the program's
  choice, carried over so the comparison is like-for-like. The audit's §3.3
  sweep found trace *rankings* stable across lookaheads but base rates swinging
  from .180 to .716, so the headline percentages here are horizon-specific.
- **Barrier resolution assumes you get filled at the barrier.** No slippage, no
  spread, and SPX options are not ES futures — this is ES tick geometry standing
  in for an options position, the same instrument mismatch the audit flags at
  §1.4.

---

## Reproduce

```bash
cd /root/projects/Strader
.venv/bin/python3 scripts/measurement/decision_aligned_study.py
```

~80 seconds (22 corpus days). Prints the base rates, the full AUC grid, the
barrier outcomes, the excursion quantiles, and an 18-row parity check against
the auditor's report; writes `data/measurement/decision_aligned_truth.json`.
Add `--cache <path>` to keep the per-minute records for a fast re-run,
`--boot N` / `--seed N` to change the bootstrap.
