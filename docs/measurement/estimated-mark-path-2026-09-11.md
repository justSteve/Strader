# Estimated Mark Path — the ES→premium proxy against the prints, 2026-09-11

**Bead:** st-9hhc (*Estimated Mark Path*) · **Measured:** 2026-09-11 · **Calibration:** `data/measurement/estimated-mark-calibration-2025.json` (16 fits over 146 days) · **Rows:** `data/measurement/estimated-mark-validation-2026-09-11.jsonl` · **Scripts:** `scripts/measurement/estimated_mark_calibrate.py`, `estimated_mark_validate.py` · **Model:** `strader/marks/estimated.py`

Every claim below is labelled **measured** (this run, these files) or **reasoned** (a modelling choice, stated so it can be argued with).

## 0. The coverage bound — read this before any number below

**Measured** on every OPRA file this run opened (271 days), counting every row in the file whether or not it is 0DTE:

| | value |
|---|---|
| days with any print before 13:00 CT | **1 of 271** |
| earliest first-print minute across days (CT) | 12:59 |
| latest first-print minute across days (CT) | 13:00 |
| earliest last-print minute across days (CT) | 13:04 |
| latest last-print minute across days (CT) | 14:59 |

Rows per CT hour, summed over days, with the number of days holding any row in that hour:

| hour CT | rows | days |
|---|---|---|
| 12:00 | 1 | 1 |
| 13:00 | 39,819,268 | 270 |
| 14:00 | 53,750,687 | 269 |

**Measured:** 1 day(s) carry prints before 13:00 CT (2025-10-22). They were still calibrated and scored over 13:00–15:00 CT only; the extra minutes were not used.

**So:** the proxy is calibrated and validated over **13:00–15:00 CT only**. `estimate_path` refuses a minute outside that window unless the caller passes `allow_extrapolation=True`, and then every such mark carries `extrapolated=True`. A blotter row marked outside the window is extrapolated and must say so in its own face. Steve's plays are late-day, so the covered window is the one that matters most — but what is covered is the last two hours, not the session.

## 1. What was measured

**Measured.** Per corpus day holding both an OPRA file and an ES file, and per entry time 13:00 / 13:30 / 14:00 / 14:30 CT, fourteen hypothetical 0DTE singles bought at the first print at or after the entry time: put and call at −15, −10, −5, 0, +5, +10, +15 SPX points ITM (negative = OTM), strikes on the 5-point grid around the parity-inferred SPX. Each leg is marked by its own prints per minute (last print, low, high) and by the proxy per minute from the ES bars (at the bar close, and at the bar's extreme against the leg).

| group | legs | days |
|---|---|---|
| all | 15049 | 270 |
| in_sample | 8159 | 146 |
| holdout | 6890 | 124 |
| 2025 | 8159 | 146 |
| 2026 | 6890 | 124 |

Rows produced: 15049; scored: 15049; skipped: none.
`in_sample` legs are on days the calibration consumed; `holdout` legs are not.

## 2. The model — reasoned

**Reasoned.** One formula, two calibrated numbers per (right, moneyness bin at entry):

```
mark(t) = max( intrinsic(S(t)),
               P_entry + delta_hat * fav_move(t) - TV_entry * (1 - (tau(t)/tau_entry) ** kappa) )
S(t) = S_entry + (ES(t) - ES_entry)        basis held constant over the window
TV_entry = max(0, P_entry - intrinsic(S_entry))   decays to zero at 15:00 CT
```

`delta_hat` is premium points per favourable ES point, least squares through the origin (at zero move and zero decay the mark is the entry). `kappa` is the decay shape, chosen from a fixed grid by smallest squared residual; 0.5 is the square-root-of-time an at-the-money option decays on. The floor at intrinsic is reasoned: an SPX option does not print below its intrinsic value for two hours. The constant basis is reasoned and bounded by `scripts/measurement/basis_pairs.py`.

## 3. Calibration — measured

| right | moneyness bin (ITM +) | delta_hat pts/ES pt | kappa | minute rows | live rows | legs | fit MAE pts | fit median resid pts |
|---|---|---|---|---|---|---|---|---|
| C | [-20, -15) | 0.215 | 0.25 | 23,637 | 16,935 | 316 | 0.63 | +0.16 |
| C | [-15, -10) | 0.281 | 0.25 | 43,544 | 35,690 | 583 | 0.68 | +0.18 |
| C | [-10, -5) | 0.360 | 0.10* | 43,629 | 39,995 | 582 | 0.83 | +0.29 |
| C | [-5, +0) | 0.454 | 0.10* | 43,548 | 41,767 | 583 | 0.82 | +0.22 |
| C | [+0, +5) | 0.551 | 0.10* | 43,714 | 42,745 | 583 | 0.90 | +0.26 |
| C | [+5, +10) | 0.635 | 0.10* | 43,355 | 42,824 | 583 | 1.03 | +0.40 |
| C | [+10, +15) | 0.695 | 0.25 | 43,195 | 42,922 | 584 | 0.99 | +0.35 |
| C | [+15, +20) | 0.753 | 0.25 | 19,400 | 19,320 | 268 | 1.01 | +0.38 |
| P | [-20, -15) | 0.267 | 0.25 | 19,867 | 16,481 | 264 | 0.75 | +0.23 |
| P | [-15, -10) | 0.340 | 0.25 | 43,617 | 38,061 | 582 | 0.81 | +0.21 |
| P | [-10, -5) | 0.420 | 0.25 | 43,439 | 40,320 | 582 | 0.81 | +0.22 |
| P | [-5, +0) | 0.505 | 0.10* | 43,747 | 42,108 | 583 | 0.95 | +0.36 |
| P | [+0, +5) | 0.599 | 0.10* | 43,406 | 42,521 | 582 | 0.97 | +0.39 |
| P | [+5, +10) | 0.683 | 0.10* | 43,462 | 43,012 | 582 | 1.06 | +0.52 |
| P | [+10, +15) | 0.756 | 0.10* | 42,555 | 42,338 | 584 | 1.11 | +0.57 |
| P | [+15, +20) | 0.816 | 0.10* | 22,126 | 22,069 | 318 | 1.06 | +0.54 |

\* 9 fit(s) sit on an edge of the kappa grid (0.1–3.0): the prints wanted a decay shape outside it. Read those bins' residuals with that in mind.

The slope is fitted on the live rows (print above 0.10); a dead option sits on the zero floor whatever ES does and says nothing about the slope. The fit residual is measured on every row with the floors applied, as the proxy predicts. A bin absent from the table had too few rows or legs to fit and the proxy refuses legs in it (`Uncalibrated`) rather than borrowing a neighbour.

## 4. Stop-fire timing — the number the blotter depends on — measured

Does the proxy fire the cut in the minute the prints do? For each leg the first minute the prints touched the level (the minute's low) is compared with the first minute the proxy did. `both`: both fired — `same`, `≤1 min`, `≤5 min` are the share of those whose minutes agree that closely. `proxy only` / `print only`: one fired and the other never did.

### 0.30-pt cut, proxy at the minute's adverse ES extreme

| group | legs | print fires | both | same minute | ≤1 min | ≤5 min | proxy only | print only | neither | proxy − print, median min (p25–p75) |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 15049 | 14147 | 13891 | 67% | 76% | 86% | 279 | 256 | 623 | 0.0 (0.0–0.0) |
| in_sample | 8159 | 7585 | 7440 | 64% | 74% | 85% | 163 | 145 | 411 | 0.0 (-1.0–0.0) |
| holdout | 6890 | 6562 | 6451 | 69% | 78% | 87% | 116 | 111 | 212 | 0.0 (0.0–0.0) |
| 2025 | 8159 | 7585 | 7440 | 64% | 74% | 85% | 163 | 145 | 411 | 0.0 (-1.0–0.0) |
| 2026 | 6890 | 6562 | 6451 | 69% | 78% | 87% | 116 | 111 | 212 | 0.0 (0.0–0.0) |

### 0.30-pt cut, proxy at the minute's closing ES

| group | legs | print fires | both | same minute | ≤1 min | ≤5 min | proxy only | print only | neither | proxy − print, median min (p25–p75) |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 15049 | 14147 | 13188 | 51% | 66% | 81% | 70 | 959 | 832 | 0.0 (0.0–2.0) |
| in_sample | 8159 | 7585 | 7082 | 49% | 64% | 79% | 51 | 503 | 523 | 0.0 (0.0–2.0) |
| holdout | 6890 | 6562 | 6106 | 53% | 68% | 83% | 19 | 456 | 309 | 0.0 (0.0–2.0) |
| 2025 | 8159 | 7585 | 7082 | 49% | 64% | 79% | 51 | 503 | 523 | 0.0 (0.0–2.0) |
| 2026 | 6890 | 6562 | 6106 | 53% | 68% | 83% | 19 | 456 | 309 | 0.0 (0.0–2.0) |

### 10% cut, proxy at the minute's adverse ES extreme

| group | legs | print fires | both | same minute | ≤1 min | ≤5 min | proxy only | print only | neither | proxy − print, median min (p25–p75) |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 15049 | 14213 | 13937 | 67% | 79% | 89% | 167 | 276 | 669 | 0.0 (0.0–0.0) |
| in_sample | 8159 | 7699 | 7550 | 67% | 79% | 89% | 84 | 149 | 376 | 0.0 (0.0–0.0) |
| holdout | 6890 | 6514 | 6387 | 68% | 80% | 89% | 83 | 127 | 293 | 0.0 (0.0–0.0) |
| 2025 | 8159 | 7699 | 7550 | 67% | 79% | 89% | 84 | 149 | 376 | 0.0 (0.0–0.0) |
| 2026 | 6890 | 6514 | 6387 | 68% | 80% | 89% | 83 | 127 | 293 | 0.0 (0.0–0.0) |

### 10% cut, proxy at the minute's closing ES

| group | legs | print fires | both | same minute | ≤1 min | ≤5 min | proxy only | print only | neither | proxy − print, median min (p25–p75) |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 15049 | 14213 | 13169 | 49% | 64% | 80% | 17 | 1044 | 819 | 0.0 (0.0–3.0) |
| in_sample | 8159 | 7699 | 7146 | 47% | 63% | 79% | 9 | 553 | 451 | 0.0 (0.0–4.0) |
| holdout | 6890 | 6514 | 6023 | 50% | 66% | 81% | 8 | 491 | 368 | 0.0 (0.0–3.0) |
| 2025 | 8159 | 7699 | 7146 | 47% | 63% | 79% | 9 | 553 | 451 | 0.0 (0.0–4.0) |
| 2026 | 6890 | 6514 | 6023 | 50% | 66% | 81% | 8 | 491 | 368 | 0.0 (0.0–3.0) |

### Per moneyness bin — 0.30-pt cut, proxy at the adverse extreme, all legs

| right | bin | legs | print fires | both | same minute | ≤1 min | ≤5 min | proxy only | print only |
|---|---|---|---|---|---|---|---|---|---|
| C | [-20, -15) | 557 | 388 | 369 | 36% | 46% | 61% | 15 | 19 |
| C | [-15, -10) | 1078 | 909 | 867 | 39% | 50% | 66% | 40 | 42 |
| C | [-10, -5) | 1071 | 1007 | 979 | 50% | 62% | 77% | 25 | 28 |
| C | [-5, +0) | 1077 | 1036 | 1024 | 64% | 74% | 85% | 27 | 12 |
| C | [+0, +5) | 1073 | 1023 | 1015 | 74% | 82% | 90% | 29 | 8 |
| C | [+5, +10) | 1078 | 1027 | 1020 | 69% | 77% | 88% | 43 | 7 |
| C | [+10, +15) | 1073 | 1015 | 1004 | 65% | 75% | 87% | 40 | 11 |
| C | [+15, +20) | 520 | 491 | 484 | 62% | 74% | 89% | 14 | 7 |
| P | [-20, -15) | 507 | 442 | 428 | 49% | 59% | 72% | 10 | 14 |
| P | [-15, -10) | 1071 | 999 | 969 | 55% | 65% | 77% | 20 | 30 |
| P | [-10, -5) | 1077 | 1051 | 1033 | 67% | 78% | 88% | 6 | 18 |
| P | [-5, +0) | 1073 | 1054 | 1041 | 77% | 85% | 93% | 1 | 13 |
| P | [+0, +5) | 1076 | 1058 | 1047 | 84% | 91% | 95% | 3 | 11 |
| P | [+5, +10) | 1071 | 1051 | 1036 | 86% | 91% | 95% | 1 | 15 |
| P | [+10, +15) | 1079 | 1050 | 1037 | 80% | 88% | 94% | 1 | 13 |
| P | [+15, +20) | 568 | 546 | 538 | 74% | 83% | 91% | 4 | 8 |

### The 82% question — does the cut fire before the first +25%?

On right-direction legs (ES finished ≥ 5 points the leg's way), `final-hour-premium-vs-es-2026-08-29.md:90` measured the 0.30 cut firing before the first +25% print on 82% of ~10 ITM single-days. The same statistic from this run, prints beside proxy:

| group | right-direction legs | prints: cut first | proxy (adverse): cut first | proxy (close): cut first |
|---|---|---|---|---|
| all | 5098 | 63.4% | 64.6% | 47.7% |
| in_sample | 2653 | 61.5% | 62.4% | 46.0% |
| holdout | 2445 | 65.4% | 66.9% | 49.5% |
| 2025 | 2653 | 61.5% | 62.4% | 46.0% |
| 2026 | 2445 | 65.4% | 66.9% | 49.5% |

| right | bin | right-direction legs | prints: cut first | proxy (adverse): cut first | proxy (close): cut first |
|---|---|---|---|---|---|
| C | [-20, -15) | 200 | 30.0% | 32.5% | 24.5% |
| C | [-15, -10) | 388 | 34.8% | 39.2% | 28.4% |
| C | [-10, -5) | 385 | 48.1% | 49.9% | 35.1% |
| C | [-5, +0) | 385 | 55.1% | 64.7% | 42.9% |
| C | [+0, +5) | 384 | 63.0% | 71.6% | 48.4% |
| C | [+5, +10) | 389 | 68.6% | 83.0% | 54.2% |
| C | [+10, +15) | 387 | 73.4% | 85.8% | 57.9% |
| C | [+15, +20) | 189 | 79.4% | 86.2% | 63.5% |
| P | [-20, -15) | 163 | 47.2% | 39.9% | 35.0% |
| P | [-15, -10) | 343 | 55.1% | 47.2% | 39.4% |
| P | [-10, -5) | 340 | 62.9% | 54.7% | 44.1% |
| P | [-5, +0) | 344 | 70.9% | 62.8% | 49.4% |
| P | [+0, +5) | 342 | 76.6% | 71.1% | 55.6% |
| P | [+5, +10) | 343 | 82.5% | 76.7% | 60.1% |
| P | [+10, +15) | 338 | 83.1% | 79.0% | 62.7% |
| P | [+15, +20) | 178 | 82.0% | 78.1% | 61.8% |

## 5. Close-mark residual — measured

proxy − print at the last marked minute, in premium points and as a share of the entry premium.

| group | legs | median pts | MAE pts | p25–p75 pts | median % of entry | MAE % of entry |
|---|---|---|---|---|---|---|
| all | 15049 | -0.03 | 1.42 | -0.05–+1.36 | -1% | 48% |
| in_sample | 8159 | -0.03 | 1.27 | -0.05–+1.36 | -1% | 51% |
| holdout | 6890 | -0.03 | 1.59 | -0.12–+1.38 | -1% | 44% |
| 2025 | 8159 | -0.03 | 1.27 | -0.05–+1.36 | -1% | 51% |
| 2026 | 6890 | -0.03 | 1.59 | -0.12–+1.38 | -1% | 44% |

| right | bin | legs | median pts | MAE pts | p25–p75 pts |
|---|---|---|---|---|---|
| C | [-20, -15) | 557 | -0.02 | 0.89 | -0.04–+1.42 |
| C | [-15, -10) | 1078 | -0.03 | 1.01 | -0.04–+1.64 |
| C | [-10, -5) | 1071 | -0.03 | 1.04 | -0.05–+1.39 |
| C | [-5, +0) | 1077 | -0.03 | 1.10 | -0.05–+1.15 |
| C | [+0, +5) | 1073 | -0.03 | 1.40 | -0.05–+1.70 |
| C | [+5, +10) | 1078 | +0.90 | 1.87 | -0.05–+2.56 |
| C | [+10, +15) | 1073 | +1.48 | 2.30 | -0.05–+3.25 |
| C | [+15, +20) | 520 | +1.66 | 2.45 | -0.05–+3.25 |
| P | [-20, -15) | 507 | -0.03 | 1.00 | -0.05–+1.22 |
| P | [-15, -10) | 1071 | -0.03 | 1.17 | -0.05–+1.14 |
| P | [-10, -5) | 1077 | -0.03 | 1.01 | -0.05–+0.51 |
| P | [-5, +0) | 1073 | -0.05 | 1.16 | -0.52–-0.03 |
| P | [+0, +5) | 1076 | -0.05 | 1.41 | -1.41–-0.03 |
| P | [+5, +10) | 1071 | -0.07 | 1.56 | -1.71–+0.50 |
| P | [+10, +15) | 1079 | -0.22 | 1.79 | -1.70–+0.99 |
| P | [+15, +20) | 568 | -0.23 | 1.81 | -1.70–+1.00 |

## 6. Excursion residuals — measured

proxy − print for the best mark (MFE, proxy at the favourable extreme) and the worst mark (MAE, proxy at the adverse extreme), premium points.

| group | legs | MFE median | MFE MAE | MAE median | MAE MAE |
|---|---|---|---|---|---|
| all | 15049 | +0.35 | 1.18 | -0.02 | 0.49 |
| in_sample | 8159 | +0.35 | 1.15 | -0.02 | 0.48 |
| holdout | 6890 | +0.35 | 1.22 | -0.02 | 0.50 |
| 2025 | 8159 | +0.35 | 1.15 | -0.02 | 0.48 |
| 2026 | 6890 | +0.35 | 1.22 | -0.02 | 0.50 |

## 7. What this settles, and what it does not

**Reasoned, from the tables above.** The standing contract is unchanged by this document: estimated blotter rows carry `exit_reason=time` only and every aggregate splits by mark path. Relaxing it — letting an estimated row carry a stop or a target — is a decision to take on §4, bin by bin, with the same-minute and ≤1-minute shares and the 82% comparison in front of the reader. If a bin's proxy fires the cut in a different minute from the prints more often than not, the honest answer for that bin is that the proxy cannot resolve stops, and the row keeps `time`.

Outside 13:00–15:00 CT nothing here applies: there is no print path to have measured against.
