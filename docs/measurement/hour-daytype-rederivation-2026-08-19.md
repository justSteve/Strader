# Hour Cuts and Day-Type Gate Re-Derivation — st-gno7

**Bead:** st-gno7 (*Hour Daytype Re-Derivation*) · **Date:** 2026-08-19
**Runs:** `20260819T213124Z` (enriched corpus, authoritative) vs `20260727T054148Z` (run-2) and `20260731T045133Z` (st-98z stage 4)
**Data:** `data/measurement/acuity-run2-confirmations.jsonl` (append-only; filter on the run id)
**Analysis:** delegated stats pass; the five deciding cells independently recomputed before the verdicts (midday-combined p = 0.008; P-vs-b p = 0.424; composition 0.003 / 0.097; stage-4 developing-b p = 0.656; developing-D p = 9.2e-05 — all reproduce).

## Verdicts

1. **Midday hours (run-2's "measured, not just doctrine" cell): weakened,
   direction survives.** On enriched bullish rth confirms, hours 10+12
   combined win 31% (29/95) vs 46% for the rest, p = 0.008 — but neither
   hour clears individually (h12 26%, p = 0.060; h10 33%, p = 0.103), nor
   the multiplicity line for an 8-cell table. The playbook's 10:00–13:00
   no-trade window stands on Steve's own grounds; what this run withdraws is
   run-2's claim that hour 12 alone was independently significant. The
   combined midday depression is still the most consistent hour effect in
   the data.
2. **The full-day day-type dependence is RETIRED.** Bullish P 50% / D 45% /
   b 46% (P-vs-b p = 0.424); bearish flat too (p = 0.901). The composition
   check is the story: run-2's pattern reproduces on its own 62 days
   (P 60% vs b 38%, p = 0.003) and **inverts** on the 77 added days
   (P 39% vs b 52%, p = 0.097). A sign reversal across samples is not
   dilution; it is a cut that was never structural.
3. **The developing-day-type gate ("run-2's single highest-leverage
   follow-up") is RETIRED UNBUILT.** The proposed gate — downgrade bullish
   confirms when the developing shape is b — never held even on the body it
   was proposed from (stage 4: developing-b 42% vs 46%, p = 0.656, while the
   *hindsight* b cut on the same body was p = 0.002). The recommendation was
   a transfer of a hindsight result onto the non-lookahead field, and the
   enriched corpus agrees (rth p = 0.609; both time-split halves fail). The
   bearish mirror (developing-P) pools at p = 0.031 and fails both halves.
   No gate gets built; `developing_day_type` stays a recorded field.
4. **One incidental cell is left as a hypothesis, not a finding:** bullish
   rth developing-**D** 31% vs 50%, p = 9.2e-05 (1 of 58 developing cells;
   clears even Bonferroni, repeats in the validate half at p = 0.017). It
   was not a hypothesis under test and inverts the intuition the gate was
   built on (rotation, not trend-down, is where bullish reversal confirms
   drown). It earns a pre-registered test on future data — runs from
   2026-08-20 onward, which share no rows with this derivation — before
   anything consumes it. Recorded here so the pre-registration has a date.
5. **Structural caveat on every hour/coverage cut:** coverage is
   near-collinear with the time split (rth: 12 tune / 34 validate days;
   late_day: 192 / 2), and 713 of 1235 bullish confirms sit in late-day
   hours 13–14. Hour cells outside 13–14 are rth-only by construction.

Nothing here is a trading recommendation; Steve directs the trading. The
run-2 doc (`recognizer-acuity-run2.md`) now carries a banner pointing here.

The full statistical record follows, unedited.

---

Source: `data/measurement/acuity-run2-confirmations.jsonl` / `acuity-run2-days.jsonl`.

**Conventions.** Win rate = wins/(wins+losses) on `verdict30`; undecided (stored as `"neither"`) is
excluded from the rate and reported in its own column. 95% CI is Wilson score. Every "p vs rest" is a
two-sided Fisher exact against the pooled rest of that side (own exact-rational implementation — scipy
is not installed in the venv); "vs coin" is a two-sided exact binomial against p = 0.5. Time split:
tune = day < 2026-06-01, validate = day >= 2026-06-01. Percentages rounded to whole numbers, p to 3 dp.
MFE30/MAE30 medians are over all rows in the cell (undecided included).

**Runs.**

| run | role | confirms | bullish | bearish | days scored | day span (distinct days with confirms) |
|---|---|---:|---:|---:|---:|---|
| `20260819T213124Z` | NEW / authoritative | 2312 | 1235 | 1077 | 270 | 2025-05-29 → 2026-08-19 (240) |
| `20260727T054148Z` | OLD run-2 baseline | 353 | 353 | 0 | 179 | 2025-05-29 → 2026-07-24 (62) |
| `20260731T045133Z` | OLD stage-4 | 423 | 423 | 0 | 182 | 2025-05-29 → 2026-07-29 (65) |

## §0 — Structure of the enriched corpus (read before any table below)

Coverage and the tune/validate time split are near-collinear. Days carrying confirms, by coverage and period:

| | tune (< 2026-06-01) | validate (>= 2026-06-01) |
|---|---:|---:|
| rth days | 12 | 34 |
| late_day days | 192 | 2 |

Confirm rows, by side / coverage / period:

| side | coverage | tune rows | validate rows |
|---|---|---:|---:|
| bullish | rth | 83 | 439 |
| bullish | late_day | 711 | 2 |
| bearish | rth | 133 | 307 |
| bearish | late_day | 630 | 7 |

Consequence, and it constrains everything after: **an "rth-only" table is almost entirely the validate
half**, and **a pooled table is almost entirely the 2025 late_day backfill**. A tune/validate split *inside*
the rth-only subset is nearly degenerate on the tune side (83 bullish rth rows before 2026-06-01, 133 bearish).
So "does it hold out of sample" and "does it hold on full-session tape" are not independent questions here.

## §1 — Reproduction of the old run-2 claims (run `20260727T054148Z`, 353 confirms, bullish only)

### Hours (its own rows, its own `day_type`)

| hour | rows | W | L | undec | decided | win% | 95% CI | binom p vs coin | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|---:|
| 08 | 42 | 22 | 20 | 0 | 42 | 52% | [38–67] | 0.878 | 0.508 | 17.25 | 9.12 |
| 09 | 59 | 28 | 30 | 1 | 58 | 48% | [36–61] | 0.896 | 0.885 | 8.75 | 10.25 |
| 10 | 20 | 5 | 14 | 1 | 19 | 26% | [12–49] | 0.064 | 0.095 | 4.75 | 7.75 |
| 11 | 26 | 12 | 13 | 1 | 25 | 48% | [30–67] | 1.000 | 1.000 | 6.5 | 6.38 |
| 12 | 20 | 4 | 16 | 0 | 20 | 20% | [8–42] | 0.012 | 0.019 | 2.5 | 9.5 |
| 13 | 80 | 34 | 37 | 9 | 71 | 48% | [37–59] | 0.813 | 0.893 | 5.5 | 6.5 |
| 14 | 106 | 44 | 39 | 23 | 83 | 53% | [42–63] | 0.661 | 0.203 | 5.12 | 4.0 |

### Full-day day_type

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 216 | 89 | 99 | 28 | 188 | 47% | [40–54] | 0.909 | 6.5 | 6.12 |
| P | 60 | 36 | 19 | 5 | 55 | 65% | [52–77] | 0.003 | 9.38 | 4.5 |
| b | 77 | 24 | 51 | 2 | 75 | 32% | [23–43] | 0.004 | 6.0 | 8.5 |

P vs b directly: Fisher p = 1.872e-04 (0.0002).

### Claim-by-claim verdict

| claim as stated | observed | reproduces? |
|---|---|---|
| hour 12 = 4/20 decided, p = 0.012 vs coin | wins=4, n_decided=20, n_rows=20, win_pct=20, binom_p=0.012 | **YES** |
| hour 10 = 5/19, p = 0.064 | wins=5, n_decided=19, n_rows=20, win_pct=26, binom_p=0.064 | **YES** |
| hour 08 = 22W/20L, p = 0.44 | wins=22, losses=20, n_rows=42, win_pct=52, binom_p=0.878, fisher_vs_rest_p=0.508 | **YES** |
| hour 14 = n 106 / 53% / med MAE 4.0 | n_rows=106, n_decided=83, win_pct=53, med_mae30_all=4.0, med_mae30_decided=5.25, med_mfe30_all=5.12 | **YES** |
| P = 65% (n 60), D = 47% (216), b = 32% (77) | P=win_pct=65, n_rows=60, n_decided=55, D=win_pct=47, n_rows=216, n_decided=188, b=win_pct=32, n_rows=77, n_decided=75 | **YES** |

Every stated cell reproduces exactly. Two clarifications the old doc left implicit:

- The day-type `n` (60 / 216 / 77) are **row** counts including undecided; the percentages are on decided
  rows only (55 / 188 / 75). Same convention, but the denominators printed next to the percentages are not
  the denominators of the percentages.
- "hour 14 med MAE 4.0" is the median over **all 106 rows**. Over the 83 decided rows it is 5.25 — hour 14
  carries 23 undecided (22% of the cell), and those are the small-excursion rows that pull the median down.

One caveat the old doc does not carry: 7 hour cells were tested and hour 12 (p = 0.012) is the smallest of
them; at 7 tests a Bonferroni threshold for 0.05 is 0.007, so hour 12 was already marginal *on its own body*.

## §2 — Enriched hour cuts (run `20260819T213124Z`), per side

Hours with n(decided) >= 10 shown; everything else lumped as "other".

### bullish — all coverage (pooled 1235 rows, 1086 decided, 46% CI [43–49])

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| 08 | 98 | 54 | 44 | 0 | 98 | 55% | [45–65] | 0.071 | 12.0 | 9.25 |
| 09 | 124 | 49 | 73 | 2 | 122 | 40% | [32–49] | 0.178 | 8.25 | 10.25 |
| 10 | 67 | 21 | 43 | 3 | 64 | 33% | [23–45] | 0.038 | 8.25 | 8.5 |
| 11 | 67 | 25 | 36 | 6 | 61 | 41% | [30–54] | 0.431 | 7.0 | 5.75 |
| 12 | 37 | 8 | 23 | 6 | 31 | 26% | [14–43] | 0.027 | 2.75 | 8.25 |
| 13 | 358 | 150 | 174 | 34 | 324 | 46% | [41–52] | 0.947 | 5.88 | 6.75 |
| 14 | 468 | 190 | 189 | 89 | 379 | 50% | [45–55] | 0.048 | 5.25 | 5.25 |
| other (h 2,3,5,6,7,15,21) | 16 | 3 | 4 | 9 | 7 | 43% | [16–75] | 1.000 | 2.0 | 3.88 |

### bearish — all coverage (pooled 1077 rows, 860 decided, 49% CI [45–52])

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| 08 | 77 | 33 | 44 | 0 | 77 | 43% | [32–54] | 0.339 | 9.25 | 10.25 |
| 09 | 110 | 46 | 55 | 9 | 101 | 46% | [36–55] | 0.527 | 9.75 | 7.62 |
| 10 | 67 | 32 | 27 | 8 | 59 | 54% | [42–66] | 0.419 | 5.25 | 5.25 |
| 11 | 43 | 20 | 18 | 5 | 38 | 53% | [37–68] | 0.623 | 6.25 | 7.0 |
| 12 | 39 | 20 | 13 | 6 | 33 | 61% | [44–75] | 0.213 | 7.75 | 4.25 |
| 13 | 286 | 114 | 116 | 56 | 230 | 50% | [43–56] | 0.758 | 4.75 | 4.75 |
| 14 | 445 | 150 | 164 | 131 | 314 | 48% | [42–53] | 0.724 | 3.5 | 4.0 |
| other (h 5,6,7) | 10 | 3 | 5 | 2 | 8 | 38% | [14–69] | 0.726 | 2.5 | 6.0 |

### bullish — coverage == rth only (pooled 522 rows, 476 decided, 43% CI [38–47])

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| 08 | 98 | 54 | 44 | 0 | 98 | 55% | [45–65] | 0.006 | 12.0 | 9.25 |
| 09 | 124 | 49 | 73 | 2 | 122 | 40% | [32–49] | 0.596 | 8.25 | 10.25 |
| 10 | 67 | 21 | 43 | 3 | 64 | 33% | [23–45] | 0.103 | 8.25 | 8.5 |
| 11 | 67 | 25 | 36 | 6 | 61 | 41% | [30–54] | 0.890 | 7.0 | 5.75 |
| 12 | 37 | 8 | 23 | 6 | 31 | 26% | [14–43] | 0.060 | 2.75 | 8.25 |
| 13 | 49 | 19 | 23 | 7 | 42 | 45% | [31–60] | 0.746 | 5.5 | 5.75 |
| 14 | 64 | 24 | 27 | 13 | 51 | 47% | [34–60] | 0.550 | 5.38 | 5.0 |
| other (h 2,3,5,6,7,15,21) | 16 | 3 | 4 | 9 | 7 | 43% | [16–75] | 1.000 | 2.0 | 3.88 |

### bearish — coverage == rth only (pooled 440 rows, 388 decided, 50% CI [45–55])

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| 08 | 77 | 33 | 44 | 0 | 77 | 43% | [32–54] | 0.203 | 9.25 | 10.25 |
| 09 | 110 | 46 | 55 | 9 | 101 | 46% | [36–55] | 0.356 | 9.75 | 7.62 |
| 10 | 67 | 32 | 27 | 8 | 59 | 54% | [42–66] | 0.482 | 5.25 | 5.25 |
| 11 | 43 | 20 | 18 | 5 | 38 | 53% | [37–68] | 0.735 | 6.25 | 7.0 |
| 12 | 39 | 20 | 13 | 6 | 33 | 61% | [44–75] | 0.207 | 7.75 | 4.25 |
| 13 | 41 | 11 | 18 | 12 | 29 | 38% | [23–56] | 0.247 | 4.25 | 4.25 |
| 14 | 53 | 28 | 15 | 10 | 43 | 65% | [50–78] | 0.036 | 5.75 | 3.5 |
| other (h 5,6,7) | 10 | 3 | 5 | 2 | 8 | 38% | [14–69] | 0.724 | 2.5 | 6.0 |

### The coverage confound, measured

Hours 13–14 exist under both coverages; hours 08–12 exist **only** under rth (the late_day pull is a
13:00–15:00 CT window, so it can emit nothing before 13:00). Row counts:

| side | late_day hours | rth hours |
|---|---|---|
| bullish | 13:309, 14:404 | 2:1, 3:1, 5:2, 6:6, 7:3, 8:98, 9:124, 10:67, 11:67, 12:37, 13:49, 14:64, 15:2, 21:1 |
| bearish | 13:245, 14:392 | 5:1, 6:1, 7:8, 8:77, 9:110, 10:67, 11:43, 12:39, 13:41, 14:53 |

And the two coverages do not score alike:

| side | rth win% (decided) | late_day win% (decided) | Fisher p |
|---|---|---|---:|
| bullish | 43% (476) | 49% (610) | 0.050 |
| bearish | 50% (388) | 48% (472) | 0.583 |

So on the bullish side the pooled hour table is 713 of 1235 rows sitting in hours 13–14 of the late_day
backfill, at a win rate 6 points above the rth rows (p = 0.050). Any hour comparison that mixes coverages is
partly a coverage comparison.

### Does the old midday finding survive?

Bullish, **rth only** (the like-for-like body — 522 rows, 476 decided, pooled 43%):

- hours 10+12 combined — bullish rth hours 10+12: 29/95 = 31% CI [22–40] (undec 9) vs bullish rth other hours: 174/381 = 46% — Fisher p = 0.008
- hour 10 alone — bullish rth hour 10: 21/64 = 33% CI [23–45] (undec 3) vs rest: 182/412 = 44% — Fisher p = 0.103
- hour 12 alone — bullish rth hour 12: 8/31 = 26% CI [14–43] (undec 6) vs rest: 195/445 = 44% — Fisher p = 0.060

All coverage, for reference: bullish hours 10+12: 29/95 = 31% CI [22–40] (undec 9) vs bullish other hours: 471/991 = 48% — Fisher p = 0.002

**Verdict: the midday depression survives as a direction and as a combined effect, but neither hour clears
on its own.** On rth-only bullish rows, hours 10+12 pooled are 29/95 = 31% against 46% for the rest of the
rth day, p = 0.008. Split apart, hour 10 is 33% (p = 0.103) and hour 12 is 26% (p = 0.060) — both still the
same sign as run-2, both now non-significant individually, and hour 12 in particular went from p = 0.012 on
353 rows to p = 0.060 on a body 1.5x its size. The cells grew (20 → 31 decided at hour 12, 19 →
64 at hour 10) and the effect shrank rather than sharpened: hour 12 moved 20% → 26%, hour 10 moved 26% → 33%.

**Multiplicity.** 16 hour cells are tested in the rth tables and 16 in the pooled tables, across the two sides. No
correction is applied to any printed p. At ~8 cells per side, a Bonferroni threshold for 0.05 is ~0.006. On
that footing the only rth hour cell that clears is bullish hour 08 (55%, p = 0.006), and it is a *high*
outlier, not the midday one. Bearish hour 14 rth (65%, p = 0.036) and bearish hour 12 (61%, p = 0.207) do not.

## §3 — Enriched full-day (hindsight) day_type (run `20260819T213124Z`), per side

### bullish — all rows (pooled 1235, 1086 decided, 46%)

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 779 | 306 | 371 | 102 | 677 | 45% | [41–49] | 0.490 | 5.75 | 6.5 |
| P | 218 | 92 | 93 | 33 | 185 | 50% | [43–57] | 0.293 | 7.38 | 6.12 |
| b | 230 | 99 | 118 | 13 | 217 | 46% | [39–52] | 0.939 | 7.75 | 8.0 |
| trend | 8 | 3 | 4 | 1 | 7 | 43% | [16–75] | 1.000 | 4.12 | 5.12 |

- P vs b — bullish day_type P: 92/185 = 50% CI [43–57] (undec 33) vs bullish day_type b: 99/217 = 46% — Fisher p = 0.424

**tune** (794 rows):

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 578 | 228 | 263 | 87 | 491 | 46% | [42–51] | 0.042 | 5.25 | 6.25 |
| P | 116 | 54 | 46 | 16 | 100 | 54% | [44–63] | 0.281 | 6.25 | 5.75 |
| b | 100 | 53 | 41 | 6 | 94 | 56% | [46–66] | 0.122 | 9.88 | 6.25 |

- P vs b (tune) — tune P: 54/100 = 54% CI [44–63] (undec 16) vs tune b: 53/94 = 56% — Fisher p = 0.774

**validate** (441 rows):

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 201 | 78 | 108 | 15 | 186 | 42% | [35–49] | 0.839 | 8.25 | 8.75 |
| P | 102 | 38 | 47 | 17 | 85 | 45% | [35–55] | 0.459 | 8.5 | 7.0 |
| b | 130 | 46 | 77 | 7 | 123 | 37% | [29–46] | 0.324 | 7.25 | 9.0 |
| trend | 8 | 3 | 4 | 1 | 7 | 43% | [16–75] | 1.000 | 4.12 | 5.12 |

- P vs b (validate) — validate P: 38/85 = 45% CI [35–55] (undec 17) vs validate b: 46/123 = 37% — Fisher p = 0.316

### bearish — all rows (pooled 1077, 860 decided, 49%)

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 675 | 262 | 265 | 148 | 527 | 50% | [45–54] | 0.441 | 4.5 | 4.25 |
| P | 269 | 100 | 113 | 56 | 213 | 47% | [40–54] | 0.581 | 4.5 | 5.0 |
| b | 103 | 43 | 51 | 9 | 94 | 46% | [36–56] | 0.586 | 9.0 | 8.75 |
| trend | 30 | 13 | 13 | 4 | 26 | 50% | [32–68] | 1.000 | 3.88 | 5.25 |

- P vs b — bearish day_type P: 100/213 = 47% CI [40–54] (undec 56) vs bearish day_type b: 43/94 = 46% — Fisher p = 0.901

**tune** (763 rows):

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 560 | 209 | 214 | 137 | 423 | 49% | [45–54] | 0.449 | 4.25 | 4.25 |
| P | 149 | 52 | 55 | 42 | 107 | 49% | [39–58] | 1.000 | 3.75 | 4.5 |
| b | 54 | 17 | 28 | 9 | 45 | 38% | [25–52] | 0.163 | 3.88 | 9.25 |

- P vs b (tune) — tune P: 52/107 = 49% CI [39–58] (undec 42) vs tune b: 17/45 = 38% — Fisher p = 0.285

**validate** (314 rows):

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 115 | 53 | 51 | 11 | 104 | 51% | [41–60] | 0.712 | 6.75 | 5.0 |
| P | 120 | 48 | 58 | 14 | 106 | 45% | [36–55] | 0.329 | 5.38 | 6.75 |
| b | 49 | 26 | 23 | 0 | 49 | 53% | [39–66] | 0.638 | 17.75 | 8.0 |
| trend | 30 | 13 | 13 | 4 | 26 | 50% | [32–68] | 1.000 | 3.88 | 5.25 |

- P vs b (validate) — validate P: 48/106 = 45% CI [36–55] (undec 14) vs validate b: 26/49 = 53% — Fisher p = 0.392

**The day-type dependence is gone on the enriched corpus.** Bullish: P 50% (185 decided), D 45% (677), b 46%
(217); P vs b p = 0.424. Bearish: P 47% (213), D 50% (527), b 46% (94); P vs b p = 0.901. No cell on either
side clears 0.05 against its own pooled rest in the all-rows table. The one cell under 0.05 anywhere in the
split is bullish D in the tune half (46%, p = 0.042) — 1 of 22 day-type cells tested across the two sides and
three scopes, i.e. what multiplicity alone predicts.

### Composition check — did run-2's P/b spread hold on its own days, or vanish everywhere?

Bullish confirms partitioned by whether the day produced confirms in run `20260727T054148Z` (62 such days) or is new to the enriched run (77 days).

**Partition A — days that were in run-2** — 484 rows over 62 days; coverage {'late_day': 197, 'rth': 287}

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 284 | 114 | 137 | 33 | 251 | 45% | [39–52] | 0.499 | 6.62 | 6.5 |
| P | 101 | 55 | 36 | 10 | 91 | 60% | [50–70] | 0.005 | 9.5 | 4.75 |
| b | 99 | 37 | 60 | 2 | 97 | 38% | [29–48] | 0.051 | 7.0 | 8.75 |

- P vs b — P: 55/91 = 60% CI [50–70] (undec 10) vs b: 37/97 = 38% — Fisher p = 0.003

**Partition B — days new to the enriched run** — 751 rows over 77 days; coverage {'late_day': 516, 'rth': 235}

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 495 | 192 | 234 | 69 | 426 | 45% | [40–50] | 0.803 | 5.5 | 6.5 |
| P | 117 | 37 | 57 | 23 | 94 | 39% | [30–49] | 0.219 | 5.5 | 7.25 |
| b | 131 | 62 | 58 | 11 | 120 | 52% | [43–60] | 0.155 | 8.25 | 6.75 |
| trend | 8 | 3 | 4 | 1 | 7 | 43% | [16–75] | 1.000 | 4.12 | 5.12 |

- P vs b — P: 37/94 = 39% CI [30–49] (undec 23) vs b: 62/120 = 52% — Fisher p = 0.097

Answer: **it held on its own days and reversed on the added ones — it did not merely dilute.**

- On the 62 run-2 days, re-scored by the enriched recognizer (484 bullish rows, up from 353): P 60%
  (91 decided) vs b 38% (97), p = 0.003. Same sign, same shape, a little softer than the 65/32 of run-2 —
  the 131 extra rows the enriched recognizer emits on those same days move it, but not its sign.
- On the 77 new days (751 rows): P 39% (94) vs b 52% (120), p = 0.097. The sign is **inverted**.

Two partitions of opposite sign, each with ~90–120 decided rows per cell, average to the flat pooled table in
§3. A dilution story would show the effect shrinking toward zero on the new days; an inversion of this size is
more consistent with the run-2 spread having been a property of that particular 62-day sample.

(The partitions are also matched on setup by construction: bullish confirms only ever carry
['failed_breakdown', 'level_reclaim'], the same two setups run-2 could emit, so the same-setups-only restriction is a no-op
and is not shown separately. The new-days partition is 69% late_day vs 41% for the run-2 days, which is a real
difference between them.)

## §4 — Developing day_type, the non-lookahead gate (run `20260819T213124Z`), per side

### bullish — all coverage

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 585 | 211 | 276 | 98 | 487 | 43% | [39–48] | 0.112 | 5.0 | 6.25 |
| P | 68 | 35 | 27 | 6 | 62 | 56% | [44–68] | 0.115 | 7.12 | 6.75 |
| b | 85 | 30 | 46 | 9 | 76 | 39% | [29–51] | 0.283 | 6.25 | 6.25 |
| trend | 12 | 8 | 2 | 2 | 10 | 80% | [49–94] | 0.051 | 5.62 | 1.75 |
| unknown | 485 | 216 | 235 | 34 | 451 | 48% | [43–53] | 0.323 | 7.75 | 7.75 |

### bullish — coverage == rth only

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 211 | 58 | 127 | 26 | 185 | 31% | [25–38] | 0.000 | 4.75 | 8.25 |
| P | 43 | 23 | 16 | 4 | 39 | 59% | [43–73] | 0.042 | 9.0 | 6.25 |
| b | 80 | 29 | 44 | 7 | 73 | 40% | [29–51] | 0.609 | 6.38 | 6.0 |
| trend | 12 | 8 | 2 | 2 | 10 | 80% | [49–94] | 0.022 | 5.62 | 1.75 |
| unknown | 176 | 85 | 84 | 7 | 169 | 50% | [43–58] | 0.015 | 10.88 | 9.5 |

**bullish tune (all coverage)**

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 399 | 155 | 169 | 75 | 324 | 48% | [42–53] | 0.646 | 4.5 | 5.25 |
| P | 33 | 16 | 13 | 4 | 29 | 55% | [38–72] | 0.571 | 5.75 | 6.5 |
| b | 14 | 5 | 7 | 2 | 12 | 42% | [19–68] | 0.773 | 6.0 | 6.62 |
| trend | 6 | 3 | 2 | 1 | 5 | 60% | [23–88] | 0.680 | 5.0 | 2.88 |
| unknown | 342 | 156 | 159 | 27 | 315 | 50% | [44–55] | 0.818 | 7.0 | 6.75 |

**bullish validate (all coverage)**

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 186 | 56 | 107 | 23 | 163 | 34% | [28–42] | 0.023 | 6.0 | 8.12 |
| P | 35 | 19 | 14 | 2 | 33 | 58% | [41–73] | 0.063 | 9.0 | 7.0 |
| b | 71 | 25 | 39 | 7 | 64 | 39% | [28–51] | 0.782 | 6.5 | 6.25 |
| trend | 6 | 5 | 0 | 1 | 5 | 100% | [57–100] | 0.011 | 7.5 | 1.25 |
| unknown | 143 | 60 | 76 | 7 | 136 | 44% | [36–53] | 0.393 | 9.75 | 9.5 |

**bullish tune (rth only)** — small, see §0

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 27 | 4 | 20 | 3 | 24 | 17% | [7–36] | 0.000 | 1.75 | 8.25 |
| P | 8 | 4 | 2 | 2 | 6 | 67% | [30–90] | 0.676 | 8.5 | 2.38 |
| b | 9 | 4 | 5 | 0 | 9 | 44% | [19–73] | 0.731 | 6.25 | 5.5 |
| trend | 6 | 3 | 2 | 1 | 5 | 60% | [23–88] | 1.000 | 5.0 | 2.88 |
| unknown | 33 | 25 | 8 | 0 | 33 | 76% | [59–87] | 0.000 | 17.75 | 5.25 |

**bullish validate (rth only)**

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 184 | 54 | 107 | 23 | 161 | 34% | [27–41] | 0.017 | 6.0 | 8.38 |
| P | 35 | 19 | 14 | 2 | 33 | 58% | [41–73] | 0.063 | 9.0 | 7.0 |
| b | 71 | 25 | 39 | 7 | 64 | 39% | [28–51] | 0.783 | 6.5 | 6.25 |
| trend | 6 | 5 | 0 | 1 | 5 | 100% | [57–100] | 0.011 | 7.5 | 1.25 |
| unknown | 143 | 60 | 76 | 7 | 136 | 44% | [36–53] | 0.390 | 9.75 | 9.5 |

Coverage mix of each developing value: `{'D': {'late_day': 374, 'rth': 211}, 'P': {'late_day': 25, 'rth': 43}, 'b': {'rth': 80, 'late_day': 5}, 'trend': {'rth': 12}, 'unknown': {'late_day': 309, 'rth': 176}}`

### bearish — all coverage

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 558 | 205 | 220 | 133 | 425 | 48% | [44–53] | 0.838 | 4.0 | 4.38 |
| P | 103 | 38 | 34 | 31 | 72 | 53% | [41–64] | 0.463 | 4.25 | 4.0 |
| b | 21 | 9 | 9 | 3 | 18 | 50% | [29–71] | 1.000 | 7.25 | 7.0 |
| trend | 4 | 2 | 2 | 0 | 4 | 50% | [15–85] | 1.000 | 12.75 | 5.88 |
| unknown | 391 | 164 | 177 | 50 | 341 | 48% | [43–53] | 0.834 | 6.0 | 6.0 |

### bearish — coverage == rth only

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 212 | 92 | 92 | 28 | 184 | 50% | [43–57] | 1.000 | 5.88 | 5.75 |
| P | 65 | 31 | 17 | 17 | 48 | 65% | [50–77] | 0.031 | 5.5 | 4.0 |
| b | 13 | 7 | 5 | 1 | 12 | 58% | [32–81] | 0.573 | 7.25 | 4.5 |
| trend | 4 | 2 | 2 | 0 | 4 | 50% | [15–85] | 1.000 | 12.75 | 5.88 |
| unknown | 146 | 61 | 79 | 6 | 140 | 44% | [36–52] | 0.073 | 9.25 | 9.25 |

**bearish tune (all coverage)**

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 412 | 138 | 157 | 117 | 295 | 47% | [41–52] | 0.453 | 3.5 | 4.25 |
| P | 64 | 19 | 23 | 22 | 42 | 45% | [31–60] | 0.749 | 3.75 | 3.75 |
| b | 12 | 5 | 5 | 2 | 10 | 50% | [24–76] | 1.000 | 6.5 | 7.0 |
| unknown | 275 | 116 | 112 | 47 | 228 | 51% | [44–57] | 0.348 | 5.0 | 5.25 |

**bearish validate (all coverage)**

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 146 | 67 | 63 | 16 | 130 | 52% | [43–60] | 0.477 | 6.0 | 5.88 |
| P | 39 | 19 | 11 | 9 | 30 | 63% | [46–78] | 0.123 | 5.0 | 4.25 |
| b | 9 | 4 | 4 | 1 | 8 | 50% | [22–78] | 1.000 | 8.0 | 5.0 |
| trend | 4 | 2 | 2 | 0 | 4 | 50% | [15–85] | 1.000 | 12.75 | 5.88 |
| unknown | 116 | 48 | 65 | 3 | 113 | 42% | [34–52] | 0.071 | 9.75 | 8.5 |

**bearish tune (rth only)** — small, see §0

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 72 | 31 | 29 | 12 | 60 | 52% | [39–64] | 0.703 | 6.12 | 4.88 |
| P | 26 | 12 | 6 | 8 | 18 | 67% | [44–84] | 0.303 | 5.62 | 2.25 |
| b | 4 | 3 | 1 | 0 | 4 | 75% | [30–95] | 0.622 | 6.5 | 3.5 |
| unknown | 31 | 13 | 15 | 3 | 28 | 46% | [30–64] | 0.390 | 4.5 | 9.5 |

**bearish validate (rth only)**

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 140 | 61 | 63 | 16 | 124 | 49% | [41–58] | 0.810 | 5.62 | 6.62 |
| P | 39 | 19 | 11 | 9 | 30 | 63% | [46–78] | 0.085 | 5.0 | 4.25 |
| b | 9 | 4 | 4 | 1 | 8 | 50% | [22–78] | 1.000 | 8.0 | 5.0 |
| trend | 4 | 2 | 2 | 0 | 4 | 50% | [15–85] | 1.000 | 12.75 | 5.88 |
| unknown | 115 | 48 | 64 | 3 | 112 | 43% | [34–52] | 0.178 | 9.75 | 8.5 |

Coverage mix of each developing value: `{'D': {'late_day': 346, 'rth': 212}, 'P': {'late_day': 38, 'rth': 65}, 'b': {'rth': 13, 'late_day': 8}, 'trend': {'rth': 4}, 'unknown': {'late_day': 245, 'rth': 146}}`

### The st-98z gate: suppress/downgrade bullish confirms when the developing shape is b

Bullish, rth only:

- all — bullish rth developing=b: 29/73 = 40% CI [29–51] (undec 7) vs bullish rth developing!=b: 174/403 = 43% — Fisher p = 0.609
- tune — tune developing=b: 4/9 = 44% CI [19–73] (undec 0) vs tune rest: 36/68 = 53% — Fisher p = 0.731
- validate — validate developing=b: 25/64 = 39% CI [28–51] (undec 7) vs validate rest: 138/335 = 41% — Fisher p = 0.783

Bullish, all coverage:

- all — bullish developing=b: 30/76 = 39% CI [29–51] (undec 9) vs bullish developing!=b: 470/1010 = 47% — Fisher p = 0.283
- tune — tune: 5/12 = 42% CI [19–68] (undec 2) vs tune rest: 330/673 = 49% — Fisher p = 0.773
- validate — validate: 25/64 = 39% CI [28–51] (undec 7) vs validate rest: 140/337 = 42% — Fisher p = 0.782

**Not supported, in or out of sample.** Bullish rth developing-b is 29/73 = 40% against 43% for everything
else on the rth tape, p = 0.609 — a 3-point gap on 73 decided rows. The tune half has 9 decided rows in the
cell (44%, p = 0.731); the validate half has 64 (39% vs 41%, p = 0.783). Pooling coverages widens the gap to
8 points (39% vs 47%) but only because developing-b is 80/85 rth while the comparison set is mostly late_day —
that is the §2 coverage effect re-entering, not a shape effect, and it still does not reach p = 0.05 (0.283).

### Mirror: bearish, developing == P vs rest

Bearish, rth only:

- all — bearish rth developing=P: 31/48 = 65% CI [50–77] (undec 17) vs bearish rth developing!=P: 162/340 = 48% — Fisher p = 0.031
- tune — tune: 12/18 = 67% CI [44–84] (undec 8) vs tune rest: 47/92 = 51% — Fisher p = 0.303
- validate — validate: 19/30 = 63% CI [46–78] (undec 9) vs validate rest: 115/248 = 46% — Fisher p = 0.085

Bearish, all coverage:

- all — bearish developing=P: 38/72 = 53% CI [41–64] (undec 31) vs rest: 380/788 = 48% — Fisher p = 0.463
- tune — tune: 19/42 = 45% CI [31–60] (undec 22) vs rest: 259/533 = 49% — Fisher p = 0.749
- validate — validate: 19/30 = 63% CI [46–78] (undec 9) vs rest: 121/255 = 47% — Fisher p = 0.123

**The mirror is the stronger of the two and still does not clear out of sample.** Bearish rth developing-P is
31/48 = 65% vs 48%, p = 0.031 pooled — but that pooled p is the whole rth body, which §0 says is ~80%
validate. Split honestly: tune 12/18 = 67% (p = 0.303), validate 19/30 = 63% (p = 0.085). Same sign in both
halves, which is more than the bullish gate manages, but 30 decided validate rows and p = 0.085 is not a
separation you can act on, and 58 developing-day-type cells were tested to find it.

One cell in these tables is larger than either gate and worth naming because it is the same statistic pointed
the other way: **bullish rth developing-D is 58/185 = 31%** against 145/291 = 50% for the rest of the
bullish rth rows, p = 9.2e-05, and it
repeats in the validate half (54/161 = 34%, p = 0.017) as well as the thin tune half (4/24 = 17%, p = 4.9e-05).
It clears a Bonferroni line drawn over all 58 developing cells (0.05/58 = 8.6e-04), let alone the 10-cell
pooled-rth family (0.005). It is reported here as
measured, not proposed as a gate — it was not the hypothesis under test, and it is one cell out of 58.

## §5 — The stage-4 body where the gate was proposed (run `20260731T045133Z`, 423 confirms, bullish only)

Coverage {'late_day': 136, 'rth': 287}; tune 217 rows / validate 206 rows.

Developing day_type:

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 186 | 64 | 99 | 23 | 163 | 39% | [32–47] | 0.050 | 4.5 | 6.5 |
| P | 20 | 11 | 6 | 3 | 17 | 65% | [41–83] | 0.134 | 6.5 | 4.88 |
| b | 54 | 22 | 31 | 1 | 53 | 42% | [29–55] | 0.656 | 6.5 | 8.0 |
| trend | 6 | 3 | 2 | 1 | 5 | 60% | [23–88] | 0.662 | 5.0 | 2.88 |
| unknown | 157 | 75 | 74 | 8 | 149 | 50% | [42–58] | 0.116 | 10.0 | 9.25 |

Full-day day_type on the same body (for contrast):

| cell | rows | W | L | undec | decided | win% | 95% CI | Fisher p vs rest | med MFE30 | med MAE30 |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| D | 261 | 106 | 127 | 28 | 233 | 45% | [39–52] | 0.917 | 6.5 | 7.0 |
| P | 68 | 41 | 22 | 5 | 63 | 65% | [53–76] | 0.001 | 10.5 | 5.75 |
| b | 94 | 28 | 63 | 3 | 91 | 31% | [22–41] | 0.002 | 5.75 | 9.0 |

developing b vs rest, on the body where the gate was proposed:

- all rows — stage4 developing=b: 22/53 = 42% CI [29–55] (undec 1) vs stage4 developing!=b: 153/334 = 46% — Fisher p = 0.656
- rth only — stage4 rth developing=b: 22/53 = 42% CI [29–55] (undec 1) vs stage4 rth rest: 97/222 = 44% — Fisher p = 0.878
- tune — tune: 4/9 = 44% CI [19–73] (undec 0) vs rest: 90/178 = 51% — Fisher p = 0.747
- validate — validate: 18/44 = 41% CI [28–56] (undec 1) vs rest: 63/156 = 40% — Fisher p = 1.000

**The developing-b gate was never supported, including on its own body.** On stage-4, developing-b is
22/53 = 42% against 46% for the rest, p = 0.656. What was strong on that body was the *hindsight* day_type —
P 65% (p = 0.001), b 31% (p = 0.002) — and the developing (non-lookahead) version of the same label does not
carry it: developing-b is 42%, eleven points above hindsight-b's 31%, and indistinguishable from the rest.
The gate appears to have been proposed by transferring the hindsight day_type result onto the developing
field, and the transfer does not hold even where the hindsight result was significant.

## §6 — Factual summary

| old claim | reproduced on its own body? | on the enriched corpus |
|---|---|---|
| midday hours depressed, bullish (h12 4/20, p = 0.012; h10 5/19, p = 0.064) | **yes**, exactly | **weakened, direction survives.** rth-only bullish: h10+h12 combined 29/95 = 31% vs 46%, p = 0.008; h12 alone 8/31 = 26%, p = 0.060; h10 alone 21/64 = 33%, p = 0.103. Neither hour clears alone, and neither clears the ~0.006 Bonferroni line for 8 cells. |
| hour 14 profile (n 106, 53%, med MAE 4.0) | **yes**, exactly (median over all 106 rows; over the 83 decided it is 5.25) | **holds, and 4.4x the rows.** Bullish all-coverage h14: 468 rows, 379 decided, 50%, med MAE 5.25; rth-only h14: 64 rows, 51 decided, 47%, med MAE 5.0. The undecided share stays the signature of the cell (89/468 = 19%). |
| full-day day_type dependence (P 65% / D 47% / b 32%) | **yes**, exactly; P vs b p = 1.9e-04 | **fails.** Bullish P 50% (185) / D 45% (677) / b 46% (217), P vs b p = 0.424. Bearish P 47% (213) / D 50% (527) / b 46% (94), p = 0.901. No cell clears 0.05 vs its own rest. |
| — composition of that failure | — | **held on run-2's own 62 days (P 60% vs b 38%, p = 0.003), inverted on the 77 added days (P 39% vs b 52%, p = 0.097).** Not dilution — sign reversal. |
| developing-b gate for bullish confirms (st-98z) | **no — it did not hold on the stage-4 body it was proposed from**: 22/53 = 42% vs 46%, p = 0.656 | **not supported.** rth-only 29/73 = 40% vs 43%, p = 0.609; tune 4/9, p = 0.731; validate 25/64 = 39% vs 41%, p = 0.783. |
| mirror: developing-P gate for bearish confirms | n/a (bearish did not exist before the enriched run) | **not supported out of sample.** rth pooled 31/48 = 65% vs 48%, p = 0.031, but tune 12/18 = 67% (p = 0.303) and validate 19/30 = 63% (p = 0.085). Same sign in both halves; neither half clears. |

**Multiplicity across the whole note.** 16 hour cells (pooled) + 16 hour cells (rth) + 22 full-day day_type
cells + 58 developing day_type cells + the named gate tests were computed. No p in this note is corrected. At
that count, cells at p ~ 0.03–0.05 are the expected yield of noise; the two results that survive a per-family
Bonferroni are bullish rth hour 08 (55%, p = 0.006) and bullish rth developing-D (31%, p = 9.2e-05), neither
of which was a hypothesis anyone brought to the data.

**Structural caveat, restated.** Per §0, coverage is nearly collinear with the time split (rth = 12 tune days
/ 34 validate days; late_day = 192 / 2). "Restricted to rth" and "held out of sample" therefore test
overlapping things, and no result in this note has been shown to hold on full-session tape in an earlier
period, because the corpus contains almost none.

---

Generated for st-gno7. Machine-readable companion: `hour_daytype_stats.json`.
