# Blotter Replay — registered rules scored as trades, 2026-09-11

**Bead:** st-uc23 (*Blotter Replay*) · **Range:** 2025-05-27 → 2026-09-10 · **Rows:** `data/measurement/blotter/replay-<day>.jsonl` · **Script:** `scripts/measurement/blotter_replay.py` · **Calibration for estimated rows:** `data/measurement/estimated-mark-calibration-2026-09-11.json`

Every number below is **measured** from the rows named above. Rows marked from the symbol's own prints and rows marked from the ES→premium proxy are **never pooled**: each table splits them. Estimated rows resolve `time` only; what the proxy would have resolved is shown beside, and the residuals it carries are in `docs/measurement/estimated-mark-path-2026-09-11.md`.

## 0. What was scanned

| | count |
|---|---|
| days in range with an ES file | 299 |
| days skipped (thin tape or no file) | 3 |
| rule calls (a rule said up or down) | 68 |
| calls priced (rows) | 64 |
| calls unpriced | 4 |

Unpriced calls by reason (a call the corpus could not price, named so the count is honest):

| reason | calls |
|---|---|
| no-entry-source | 2 |
| no-parity | 2 |

## 1. The rules

| rule | fires at | instrument | declared exit | registered |
|---|---|---|---|---|
| `footprint-up-1445` | 14:45 CT | itm-single-10 | stop 0.30 pts · target +25% · 15:00 CT | `ac02296` |
| `launch-into-no-lid-1445` | 14:45 CT | itm-single-10 | stop 0.30 pts · target +25% · 15:00 CT | `9df6a9c` |

## 2. Rows by rule and mark path — the declared exit

P&L in premium points on one contract (1 pt = $100). `w/l/f` = rows that gained / lost / closed flat. Halves are calendar years of the row's day.

| rule | mark path | rows | w/l/f | sum pts | median pts | sum $ | exits | 2025: n · sum · median | 2026: n · sum · median |
|---|---|---|---|---|---|---|---|---|---|
| `footprint-up-1445` | estimated | 2 | 0/2/0 | -3.38 | -1.69 | -338 | time 2 | — | 2 · -3.38 · -1.69 |
| `footprint-up-1445` | prints | 37 | 8/29/0 | +5.84 | -0.40 | +584 | stop 29, target 8 | 25 · +1.49 · -0.40 | 12 · +4.35 · -0.35 |
| `launch-into-no-lid-1445` | estimated | 2 | 0/2/0 | -3.38 | -1.69 | -338 | time 2 | — | 2 · -3.38 · -1.69 |
| `launch-into-no-lid-1445` | prints | 23 | 4/19/0 | +0.63 | -0.40 | +63 | stop 19, target 4 | 15 · -2.18 · -0.45 | 8 · +2.81 · -0.35 |

Estimated rows: what the proxy would have resolved at the minute's ES extreme (carried on the row as `estimated_exit`, not in the P&L):

| rule | proxy would exit |
|---|---|
| `footprint-up-1445` | stop 2 |
| `launch-into-no-lid-1445` | stop 2 |

## 3. The premium grid beside the declared exit — printed rows only

Stop in premium points below the entry × target as a percent of the entry, first touch wins, the same rows as the `prints` line above. This is the blotter's premium grid on registered rules; it is not st-fpc4's ES-point grid on recognizer confirmations.

**`footprint-up-1445`**

| stop × target | rows | w/l/f | sum pts | median pts | sum $ | exits |
|---|---|---|---|---|---|---|
| 0.20x10 | 37 | 11/26/0 | +1.75 | -0.35 | +175 | stop 26, target 11 |
| 0.20x25 | 37 | 7/30/0 | +4.85 | -0.36 | +485 | stop 30, target 7 |
| 0.20x50 | 37 | 2/35/0 | -5.30 | -0.37 | -530 | stop 35, target 2 |
| 0.20x100 | 37 | 2/35/0 | +3.17 | -0.37 | +317 | stop 35, target 2 |
| 0.30x10 | 37 | 13/24/0 | +2.98 | -0.36 | +298 | stop 24, target 13 |
| 0.30x25 | 37 | 8/29/0 | +5.84 | -0.40 | +584 | stop 29, target 8 |
| 0.30x50 | 37 | 4/33/0 | +3.91 | -0.40 | +391 | stop 33, target 4 |
| 0.30x100 | 37 | 3/34/0 | +10.92 | -0.40 | +1,092 | stop 34, target 3 |
| 0.50x10 | 37 | 17/20/0 | +5.96 | -0.50 | +596 | stop 20, target 17 |
| 0.50x25 | 37 | 11/26/0 | +10.02 | -0.59 | +1,002 | stop 26, target 11 |
| 0.50x50 | 37 | 6/31/0 | +7.92 | -0.60 | +792 | stop 31, target 6 |
| 0.50x100 | 37 | 5/32/0 | +19.44 | -0.60 | +1,944 | stop 32, target 4, time 1 |
| 1.00x10 | 37 | 21/16/0 | +3.87 | +0.90 | +387 | stop 16, target 21 |
| 1.00x25 | 37 | 15/22/0 | +9.39 | -1.08 | +939 | stop 22, target 15 |
| 1.00x50 | 37 | 7/30/0 | -5.19 | -1.20 | -519 | stop 30, target 7 |
| 1.00x100 | 37 | 6/31/0 | +9.87 | -1.20 | +987 | stop 31, target 5, time 1 |

**`launch-into-no-lid-1445`**

| stop × target | rows | w/l/f | sum pts | median pts | sum $ | exits |
|---|---|---|---|---|---|---|
| 0.20x10 | 23 | 6/17/0 | -0.40 | -0.35 | -40 | stop 17, target 6 |
| 0.20x25 | 23 | 3/20/0 | -1.28 | -0.37 | -128 | stop 20, target 3 |
| 0.20x50 | 23 | 2/21/0 | +0.31 | -0.40 | +31 | stop 21, target 2 |
| 0.20x100 | 23 | 2/21/0 | +8.78 | -0.40 | +878 | stop 21, target 2 |
| 0.30x10 | 23 | 7/16/0 | +0.25 | -0.37 | +25 | stop 16, target 7 |
| 0.30x25 | 23 | 4/19/0 | +0.63 | -0.40 | +63 | stop 19, target 4 |
| 0.30x50 | 23 | 3/20/0 | +4.66 | -0.45 | +466 | stop 20, target 3 |
| 0.30x100 | 23 | 3/20/0 | +17.69 | -0.45 | +1,769 | stop 20, target 3 |
| 0.50x10 | 23 | 10/13/0 | +2.95 | -0.50 | +295 | stop 13, target 10 |
| 0.50x25 | 23 | 6/17/0 | +4.20 | -0.58 | +420 | stop 17, target 6 |
| 0.50x50 | 23 | 4/19/0 | +6.30 | -0.60 | +630 | stop 19, target 4 |
| 0.50x100 | 23 | 4/19/0 | +20.15 | -0.60 | +2,015 | stop 19, target 3, time 1 |
| 1.00x10 | 23 | 11/12/0 | -1.90 | -1.00 | -190 | stop 12, target 11 |
| 1.00x25 | 23 | 7/16/0 | -1.82 | -1.12 | -182 | stop 16, target 7 |
| 1.00x50 | 23 | 4/19/0 | -4.42 | -1.17 | -442 | stop 19, target 4 |
| 1.00x100 | 23 | 4/19/0 | +9.43 | -1.17 | +943 | stop 19, target 3, time 1 |

## 4. Determinism

Two runs over one range with unchanged code and files are byte-identical (rows and this document); the test pins it on a synthetic corpus and the run manifest records the range. A rule change ships its blotter diff as the review.
