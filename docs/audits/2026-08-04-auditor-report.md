# Auditor's Report — 0DTE Singleton Continuation Program

**Auditor:** cold context, no session history · **Date:** 2026-08-04
**Scope:** the package at `/root/projects/Strader/docs/audits/2026-08-04-0dte-continuation-audit-package.md`, the two measurement docs, the five named scripts, the bead trail, and the underlying corpus.
**Method:** every headline number was recomputed from source. Where the program's own code was the thing under test, I rebuilt the labelling loop independently (1,882 minutes, exact parity with the stored study) rather than reusing it.
**Working files:** `/tmp/claude-0/-root-projects-COO/58f7de97-d7e3-432d-b9de-cbad5f9230ea/scratchpad/` (`build_cache.py`, `analyze.py`, `analyze2.py`, `deltadiv.py`, `label2.py`, `sweep2.py`). Nothing under `/root/projects/Strader` was modified; no beads were touched.

---

## 1. Executive summary

Ranked by what should change the operator's behaviour soonest.

**1. The convergence score does not survive being asked the trader's actual question. (HIGH, verified)**
The whole framework labels a minute CONT if price extends ≥2 pts *beyond the standing high-water mark* within 15 minutes. That target moves away from you as price backs off, so the label is dominated by a fact with no market content: how close price currently sits to its own extreme. Pure price geometry — distance from the standing extreme, computable with no market data beyond ES — grades the label at **AUC 0.790 (day-median 0.811)**. The three-trace convergence score, the program's deliverable, grades it at **0.678 (day-median 0.607)**. The score is a *worse* proxy for the label than the label's own construction is.

When I relabel the identical 1,882 minutes with the question a trader is actually asking — *from where price is right now, does it advance N points in the move's direction in the next 15 minutes* — the score collapses to a coin flip at every threshold: **AUC 0.506 / 0.529 / 0.528** at 2 / 5 / 8 points, and **0.500** for "favourable excursion exceeds adverse." So do all three individual traces. The only thing that keeps working is the clock (below). This is the single most important finding: the meter on Steve's desk is displaying state percentages that carry no information about the decision it is being consulted for.

**2. The resume rates — 96–98% — are a tautology, not a measurement. (HIGH, verified)**
In `morning_flush_study.py:137-178`, an event's `resumed` flag and its `remaining` field are computed from the same quantity: the primary move's terminal extreme, which is hindsight. I checked all 2,535 stored events: `resumed == (remaining > 0)` in **2,535 of 2,535 cases, exactly**. The failure count is capped at one per day at every threshold (22, 22, 21, 18, 16 failures over 22 days). The doc's flagship conditional — "with ≥5 pts of move still ahead, resumption ran 415/415 (100%)" — is true by construction, and is the *same* class of artifact the team believes it fixed when it replaced the span-clipped version. Honest re-measurement on the raw tick stream, forward-looking only: after a 2-pt counter-move, price makes a new extreme within 15 minutes **91.4%** of the time, and **18.7% of the time the position bleeds ≥8 points adverse first** (median worst-case 3.75 pts, p90 12.5 pts, max 55 pts). The re-entry conclusion survives; the "refunded seconds later" characterisation does not.

**3. The clock outperforms every instrument the program measured, and the meter does not show it. (HIGH, verified)**
Minutes elapsed since the move began grades continuation at **AUC 0.728, day-median 0.875** — against the convergence score's 0.678 / 0.607. Base rate runs **91.4% in the move's first 10 minutes and 42.2% after 40 minutes**; by session clock, 85.4% before 09:00 CT and 42.0% after 10:00 CT. A trivial predictor built from ES price and a wall clock alone reaches **AUC 0.815, day-median 0.866**. The meter renders a single pooled percentage per score with no time term, so it reads "33%" during the window where the truth is ~91% and "74%" during the window where the truth is ~42%.

**4. A closed bead claims a data capture that does not exist. (HIGH, verified)**
`st-b3jq` (Roster Completes, commit `42de6dc`) is CLOSED with the reason "Probe run complete and capture landed. Serve+captured: $VIX1D/$COR1M/$COR3M … 1 day each on disk." `grep -rl "VIX1D" data/` returns **nothing anywhere under `data/`** — not in any `internals.jsonl`, not in the `_internals_backup_20260804/` snapshot. The bead's own Acceptance Criterion ("~30 days carry $VIX1D/$COR1M/$COR3M") was not met and the close reason substitutes a different outcome without flagging it. Separately, `data/corpus/2026-08-04/` has **no `internals.jsonl` at all** — today's internals pull has not landed, on the day the meter is nominally live.

**5. The residual test that killed the VIX trace was never run on the other traces — and $TICK fails it too. (HIGH, verified)**
The team residualised VIX and VVIX only. Residualising each trace on the concurrent 5-minute ES move: `vix_slope5` .660→**.520** (reproduces their .522), `tick_aligned` .665→.606 but **day-median .507 — a coin flip**, `vold_slope10` .638→.592 (day-median .530), `delta5_aligned` .548→**.409, inverted**. The one trace with genuine residual signal is `add_slope10` (day-median **.598**) — and $ADD is precisely the channel that publishes a session late and is therefore unavailable live. **The live meter runs on the two traces that fail the residual test and drops the one that passes it.**

**6. The live meter has never graded a live market minute. (HIGH, verified)**
`data/exec/continuation-meter-2026-08-03.jsonl` holds 729 frames spanning **17:22–23:59 CT** — after the 15:00 close. `last_candle` is `14:59` in **all 729**; staleness runs 143 to 541 minutes; every frame carried the STALE banner. Today's file holds **3 frames** (08:30:25–08:31:36), all with `score: None`. Between the first two, the detected move direction **flipped from −1 to +1** on a 1.13-point "primary move," reversing the sign of the $TICK confirmation mark from −170 to +172 in 36 seconds.

**7. The delta-divergence conclusion is stated backwards. (MEDIUM-HIGH, verified)** — see §2.2.

**Negative findings worth stating plainly.** I tried hard to break three things and could not. Every number in the execution table of `morning-flush-anatomy.md` §3 reproduces to the cent from the stored study output (twelve chase cells, one-and-done, endure, and the +18.5 oracle-endure). The chase refutation survives both unswept execution parameters — every cell of an R_END × friction grid is negative, and R_END=8 was if anything *generous* to the chase. And the label parameters (≥2 pts / 15 min) are robust: trace AUCs move by less than 0.05 across a full 4×4 sweep of extension threshold and lookahead.

---

## 2. Findings by charter class

### Class 1 — Candidate-space omissions

**1.1 The enumeration extended the axis the operator had already named. (HIGH, verified)**
`st-b3jq` was the post-correction enumeration, and what it enumerated was *more volatility instruments*: $VIX1D, $COR1M, $COR3M. The probe list in `scripts/corpus_pull_internals.py:14-21` is entirely tickers. The axes that were never enumerated at all are the non-instrument ones — and one of them beats everything in the program:

- **Clock / session structure.** Not a channel anyone thought to name, because it isn't a symbol. It is the strongest single predictor found in this audit (day-median AUC 0.875, §1.3 above) and costs nothing to add.
- **Calendar / event.** Nothing in the program records whether a day carried an 09:00 CT (10:00 ET) data release, an FOMC, an opex, or a month-end. `morning_flush_study.py:332` captures `cov["dow"]` and no analysis ever reads it. 16 of 22 moves originate before 09:00 CT — squarely in the release window.
- **Price location.** Where price sits relative to the overnight range, prior-day high/low/close, opening range, or VWAP is absent as a tested channel. Mancini levels are the acknowledged instance; the free ones are not acknowledged.

**1.2 Instruments already paid for and not pulled. (MEDIUM, verified)**
The DataBento GLBX subscription that supplies `ES.c.0` also carries NQ and RTY. Nothing in `scripts/` pulls them. A one-sided SPX move with or without NQ confirmation is a standard cross-index continuation read and has zero marginal data cost.

**1.3 The overnight session is not captured. (MEDIUM, verified)**
`read_corpus_day(date(2026,7,23))` returns trades in CT hours **8 through 14 only** — the corpus holds no Globex overnight tape. The overnight range, its VWAP, and the 08:30 open's position within it are classic morning-continuation covariates on the same subscription. This also silently degrades the `gap_pts` covariate (`morning_flush_study.py:293-303`), which walks back up to five calendar days to find *any* prior corpus file and differences against its last trade.

**1.4 The cash/futures basis is unmeasured — and the program is internally inconsistent about which instrument it means. (MEDIUM, verified)**
The studies define the primary move on **ES futures ticks** (`morning_flush_study.py:73-99`). The live meter defines it on **$SPX cash minute closes** (`continuation_meter.py:96-115, 149`) and feeds `spx5` into quadrant cells calibrated on `des_pts` from ES (`continuation_meter.py:185-187` vs `morning_flush_vix_depth.py:128-131`). Different instrument, different granularity, different basis. The ES−SPX spread is itself a live-readable channel and is neither measured nor controlled for.

**1.5 Channels present in the repo and never joined. (LOW–MEDIUM, verified)**
`data/measurement/expected_move.jsonl` and `iv_pin.jsonl` exist from May work and are not joined to any continuation study. `data/measurement/moves/moves.jsonl` was last written **2026-07-28** — five trading days stale, not the four the package states.

**1.6 Package inventory inaccuracy. (LOW, verified)**
The package's channel table says MBP-1 is "**Captured but never used in any study**." `scripts/measurement/absorption_calibrate.py:1` reads "Calibrate absorption floors against a purchased MBP-1 corpus day. [st-9vl]" — it has been used, just not in this program. Counts also drift: 269 ES days on disk vs 267 claimed, 272 OPRA vs 250, 17 MBP-1 vs ~13, 1,542 legprofiler rows vs 1,649 claimed.

---

### Class 2 — Mechanical-coupling errors

**2.1 The label itself is mechanically coupled to concurrent price. (HIGH, verified)** — the headline, §1.1 above.
The residual test the team invented was applied to the *traces*. Nobody applied it to the *label*. `morning_flush_continuation.py:152` scores continuation against `ext_series[m]`, the running extreme, so a minute standing 15 pts inside a backtest must travel 17 pts to be labelled CONT while a minute at the extreme must travel 2. Stratified by distance-to-extreme, the score's discriminating power evaporates and in the far strata it **inverts**:

| distance from standing extreme | n | base P(CONT) | score 0/3 | score 3/3 |
|---|---|---|---|---|
| 0–1 pt | 133 | .910 | 1.000 (n=2) | .902 (n=82) |
| 1–3 pts | 296 | .838 | 1.000 (n=5) | .853 (n=170) |
| 3–6 pts | 405 | .768 | .682 (n=22) | .821 (n=140) |
| 6–10 pts | 350 | .574 | .342 (n=38) | .619 (n=84) |
| **10–20 pts** | 386 | .308 | **.282** (n=117) | **.143** (n=49) |
| 20+ pts | 180 | .022 | .022 (n=93) | .000 (n=14) |

Within-stratum score AUCs run .495 / .526 / .593 / .552. The advertised monotone 25→73% ladder is the score tracking proximity, not the score reading the market. The inversion band matters operationally: 10–20 pts inside a backtest is exactly where a trader consults a meter about re-entry, and there all-three-confirming is associated with *lower* continuation (14.3%) than none-confirming (28.2%). Thin (n=49) but wrong-signed.

**2.2 Delta divergence: the reported conclusion is backwards. (MEDIUM-HIGH, verified)**
`morning-flush-continuation.md:44-48` states the exhaustion flag "fired in 22% of continuing minutes vs 10.5% of dying ones — at this granularity it is a *continuation* accompaniment, not a warning. A popular heuristic, refuted on this tape." I reproduce 0.220 vs 0.105 exactly. But the flag is defined as `new_ext_5 AND delta < 0` (`morning_flush_continuation.py:204`), and it can only fire when a new extreme has printed — which happens in **60.3% of CONT minutes vs 25.8% of TERM minutes**. That 2.3× base-rate difference is the entire gap. Conditioning on the only minutes where the heuristic is defined:

| among minutes where a new extreme printed | n | P(CONT) |
|---|---|---|
| delta **against** the move (the divergence) | 307 | **0.723** |
| delta with the move | 548 | **0.774** |

Divergence is associated with *lower* continuation — the classic warning direction, weakly. The doc asserts the opposite of what the correctly-conditioned data shows. Effect size is small and not decision-grade either way; the defect is that a practitioner heuristic was publicly "refuted" on a confounded comparison.

**2.3 The traces that were never residual-tested. (HIGH, verified)** — table in §1.5 above. To be explicit about which reported numbers have *not* had the test: `$TICK level × dir` (.665), `$TICK 10-min sign-share` (.638), `$ADD 10-min slope` (.653), `$VOLD 10-min slope` (.638), `volume pace` (.616), `wiggle-calm` (.578), `ES aggressor delta` (.548), and the **convergence score itself** (.678). Only VIX and VVIX were tested. $TICK's day-median residual is .507.

**2.4 The vol quadrants are mostly the ES sign in costume. (MEDIUM, verified)**
Splitting first on the concurrent 5-minute ES move and then adding VIX:

| context | ES alone | n | + VIX confirming | + VIX against |
|---|---|---|---|---|
| down move, ES with the move | .712 | 538 | .723 (n=483) | .618 (n=55) |
| down move, ES against | .439 | 351 | .629 (n=35) | .418 (n=316) |
| up move, ES with the move | .604 | 462 | .614 (n=427) | .486 (n=35) |
| up move, ES against | .303 | 307 | .429 (n=56) | .275 (n=251) |

VIX adds ~1 percentage point in the well-populated cells and 12–19 points only in cells of n=35–56. Every named quadrant read the meter displays — "bounce NOT believed," "vol bid, tails quiet" — lives in those thin cells. The headline "73% flush running, vol bid" state is statistically indistinguishable from "ES ticked down in the last five minutes" (.723 vs .712).

---

### Class 3 — Label and definition soundness

**3.1 The framework does not measure what the trader needs. (HIGH, verified)**
This is the constructive core of the audit. I relabelled the same 1,882 minutes four ways, anchored on *current price* rather than the standing extreme:

| label | base rate | prox | clock | $TICK | VIX | $ADD | **score3** |
|---|---|---|---|---|---|---|---|
| original: ≥2 pts beyond standing extreme, 15 min | .569 | **.790** | .728 | .665 | .660 | .653 | **.678** |
| ≥2 pts from here, 15 min | .919 | .453 | .629 | .574 | .505 | .499 | **.506** |
| ≥5 pts from here, 15 min | .762 | .470 | .611 | .568 | .532 | .508 | **.529** |
| ≥8 pts from here, 15 min | .604 | .466 | .629 | .541 | .529 | .528 | **.528** |
| favourable excursion > adverse, 15 min | .672 | .493 | .598 | .515 | .487 | .492 | **.500** |

Read the last column. The deliverable is a coin flip under every decision-aligned label, including the two with well-balanced base rates (.604 and .672, so this is not a degenerate-label artifact). `prox` collapses too — confirming it was never an edge, only an explanation of the original label. The clock is the only survivor.

I should be fair about what this does *not* say. "Will the move make a new extreme" is a legitimate question — it is the breakout re-entry trigger. But it is not the question the meter is consulted for, and the meter's own wording says so.

**3.2 The meter's on-screen wording describes a different label than the number it displays. (MEDIUM-HIGH, verified)**
`continuation_meter.py:229-231` renders: *"Score 3/3 → about 73% chance the move extends 2+ pts in the next 15 min."* Read literally by a novice, that is the ≥2-pts-from-here label — whose unconditional base rate is **91.9%**, and which the score does not move (AUC .506). The number 73 is calibrated on the standing-extreme label (base rate 56.9%). The two labels differ by 35 percentage points of base rate. The sentence and the integer describe different quantities.

**3.3 Label parameters are robust — a negative finding. (verified)**
A full 4×4 sweep of extension threshold {1,2,3,5} × lookahead {5,10,15,30} moves trace AUCs by less than 0.05 ($TICK .582–.673, VIX .624–.675, $ADD .594–.665, score3 .634–.689). The "chosen once, unswept" caveat is real but benign. One caveat on the caveat: base rate swings from .180 to .716 across the grid, so the *headline percentages* (25%, 73%) are parameter-specific even though the ranking is not.

**3.4 The primary move's direction is decided by under a point on some days. (MEDIUM, verified)**
`primary_move()` takes the larger of max-drawdown and max-drawup, and that choice orients every trace on every minute of the day.

| date | assigned dir | drawdown | drawup | margin |
|---|---|---|---|---|
| 2026-07-30 | dn | 47.50 | 46.75 | **0.75 pts** |
| 2026-07-10 | up | 53.00 | 54.00 | **1.00 pt** |
| 2026-07-13 | dn | 37.00 | 30.25 | 6.75 |
| 2026-07-09 | up | 37.00 | 45.50 | 8.50 |

5 of 22 days have a runner-up within 20% of the primary; 12 of 22 within 40%. On 07-30 and 07-10 — roughly 170 minutes, 9% of the sample — a sub-point difference sign-flips every oriented trace for the whole day. There is no contested-direction flag anywhere in the pipeline, and the live meter re-derives direction from scratch every 30 seconds (§5.2).

**3.5 The lookahead truncation is one minute short. (LOW, verified)**
`LAST_LABELED = 10:15` with a 15-minute lookahead, but `minute_bars` is built over `[start, 10:30)`, so the 10:15 minute sees 14 minutes, not 15. Immaterial to conclusions; noted for completeness.

**3.6 A latent logic wart in the new-extreme detector. (LOW, verified)**
`morning_flush_continuation.py:181-185` guards with `i == 0` (the *outer* minute index) inside a comprehension over `look5`, and uses `minutes.index(mm)` where `max(0, -1)` resolves to the element itself, making the inequality trivially false for the first minute. It does not change any headline number but the expression does not mean what it reads as.

---

### Class 4 — Small-n and clustering honesty

**4.1 The displayed percentages need intervals, and the meter shows none. (MEDIUM, verified)**
Day-block bootstrap (4,000 resamples, resampling whole days to respect within-day clustering):

| cell | n minutes | point | 95% CI |
|---|---|---|---|
| score 0/3 | 277 | .253 | **[.147, .397]** |
| score 1/3 | 417 | .489 | [.391, .596] |
| score 2/3 | 517 | .652 | [.561, .744] |
| score 3/3 | 539 | .729 | **[.628, .815]** |
| score 0/2 (meter's live mode) | 419 | .329 | **[.221, .461]** |
| score 1/2 | 680 | .572 | [.494, .654] |
| score 2/2 (meter's live mode) | 680 | .741 | **[.656, .810]** |

The meter's "74%" is 66–81%; its "33%" is 22–46%. And these are *in-sample* intervals — they capture day-sampling variance only, not the fact that the traces, orientations and cell boundaries were all chosen on these same 22 days. There is no out-of-sample set for anything internals-based, and none was held out.

**4.2 "73% state" to a novice reader overstates — for a reason beyond width. (HIGH, verified)**
The interval is the smaller problem. The larger one is §1.3: the cell percentage is a pooled average over a window where the honest base rate runs from 91% to 42% on the clock alone. A reader looking at "74%" at 10:10 CT is being handed a number that is materially too high, and at "33%" at 08:40 one that is materially too low. Combined with §3.2 (the sentence describes a 91.9%-base-rate event), the meter's numeric display is wrong in three independent ways at once.

**4.3 The n=38 quadrants are correctly flagged but structurally unfixable. (MEDIUM, verified)**
`data/measurement/morning_flush_vix_depth.json` confirms both anomalous cells at n=38 (dn ES+/VIX+ at .658; up ES+/VIX+ at .526). The docs flag them. What the docs do not say is that these cells cannot grow: Schwab's minute-history endpoint is a rolling ~47-day window, $VIX has 32 corpus days and $VIX9D/$VIX3M/$VVIX have 30 each, so **no backfill beyond what exists is possible, ever**. The vol-complex study's sample is permanently capped at what was captured on 2026-08-03 plus forward accumulation.

**4.4 The direction rules are correctly caveated. (verified, negative finding)**
`morning-flush-anatomy.md:146-147` says "none reach conventional significance — binomial one-sided p ≈ 0.10–0.12; do NOT trade these as validated." My computation: fade-f5≥4 12/18 p=.119, $TICK 09:00 13/21 p=.192, f5 inversion 14/22 p=.143. The doc slightly understates the $TICK p-value; the honesty is otherwise intact.

**4.5 The "first-hour edge" is not an edge, and the package flags the wrong problem. (MEDIUM, verified)**
The package's oversight #7 notes that `st-ug5` cites "first-hour edge 54% wins" while `docs/measurement/recognizer-acuity-run2.md:68` says 52% for hour 08. Confirmed. But the more important fact goes unremarked: that row is **22/42, p = 0.44** — indistinguishable from a coin flip. Correcting 54 to 52 preserves the impression that a measured edge exists.

**4.6 Day-level claims verified. (negative finding)**
VIX net travel positive on **22/22** days and Spearman ρ vs move size **+0.853** (doc: +0.85). OOS median move 31.5 (doc: 31.0), ≥45 pts on 4/12 (doc: 4/12). All reproduce. Worth noting the 12 OOS days span 2025-07 to 2026-04 but cluster (four in October 2025), and carry **no internals at all** — so the continuation program proper (st-cdwe → st-byrg) has zero out-of-sample days of any kind.

---

### Class 5 — Prompting-dependency residue

**5.1 Decisions that exist only because Steve asked.** VVIX (st-lru8), $VIX1D/$COR (st-b3jq), the de-seasoned/residual/quadrant depth pass (st-40fv, "Steve pushed past rising/falling"), the OOS addendum, and this audit. Every doc header attributes its scope to a Steve prompt: `morning-flush-continuation.md:10-15`, `morning_flush_vix_depth.py:4`, `morning_flush_vvix.py` header.

**5.2 The correction itself was prompting-shaped. (HIGH, verified)**
This is the finding the class exists to surface. The standing correction is *enumerate the candidate space before measuring*. What st-b3jq enumerated was three more volatility tickers — an extension along the axis Steve had already named when he said "VVIX." The enumeration was over *members of a family*, not over *families*. The families never enumerated — clock, calendar, price location, cross-index — include the one that beats everything the program built (§1.3). The correction fired and the same failure recurred inside it, one level up.

**5.3 The residual test did not generalise either. (HIGH, verified)**
Same shape. Steve's push produced a residual test; it was applied to the instrument under discussion (VIX), then to the next instrument he named (VVIX), and stopped. It was never lifted to a standing requirement, so $TICK — the top-ranked trace and half the live meter — still carries an untested .665 (§2.3).

**5.4 Verification is prompting-shaped too. (HIGH, verified)**
`st-b3jq` closed asserting capture that does not exist (§1.4). The stated verification was "zero rows lost," which checks the *old* symbols. `fetch_symbol` (`corpus_pull_internals.py:47-59`) returns `[]` on an empty response and writes nothing, so a non-serving symbol is indistinguishable from a serving one that no one counted. The AC explicitly required "~30 days carry $VIX1D/$COR1M/$COR3M" and was not run.

**5.5 The package under-reports its own weakest artifact. (MEDIUM, verified)**
`st-byrg`'s bead is honest — it says the stale guard fired on a "closed session" with 147-minute-old candles. The doc (`morning-flush-continuation.md:200-218`) and the audit package both describe the meter as live with operational notes "learned on first live run," and neither says that run was 729 after-hours frames on a frozen 14:59 candle. Fidelity degraded as the claim moved bead → doc → package.

---

### Class 6 — Execution-side blind spots

**6.1 The chase refutation is artifact-free. (verified, negative finding — the strongest good news here)**
I swept both parameters the study fixed. Every cell is negative for the chase:

| R_END trail | friction 0.6 | friction 1.2 |
|---|---|---|
| 4 | −6.75 | −10.53 |
| 8 (study's choice) | **−4.53** | −7.53 |
| 12 | −8.40 | −11.28 |
| 20 | −7.80 | −9.60 |
| 40 | −7.80 | −9.60 |

(median net pts/day, ±5 trigger, 2-pt stop). R_END=8 is the *best* cell — the study's unswept choice was generous to the hypothesis it refuted. Wider stops do not rescue it blind (stop 8 → −5.08; stop 20 → −5.08). Only oracle direction plus a 20-pt stop and 20-pt trail turns positive (+4.55, 12/22) — and that configuration is no longer a chase, it is endure. Friction at 2× leaves every conclusion intact. **The refutation of cut-on-slightest-backtest holds.**

**6.2 The dip-entry lane is worse than "unresolved." (MEDIUM, verified)**
The study only ever ran dip variants capped at 2 or 5 attempts (`morning_flush_study.py:428-437` nests the dip loop inside `for cap in (2, 5)`), so the lane never got to demonstrate the liberal re-entry that is its whole point. Uncapped, with the cooldown already in the code, it is catastrophic: median **−238 pts/day** at DIP_TURN 1.5 and **−65** at DIP_TURN 3.0, 0/22 positive in every configuration. Capped at 5 it recovers only to −4.5/−6.6. So the tick-churn artifact is not suppressed by the cooldown, only by the cap. The package's characterisation ("abandoned at tick granularity as artifact-prone") is accurate, and the bar-level lane (st-chat) remains genuinely open — but nobody should carry forward an impression that the dip shape looked promising. It did not, in any configuration I could construct.

**6.3 The simulation's docstring does not describe the simulation. (LOW-MEDIUM, verified)**
`morning_flush_study.py:23-27` says "campaign ends when price retraces R_END pts from the campaign extreme without a new extreme (move over) or at window close." The code does not end the campaign there — `simulate()` at lines 231-236 records a trail exit, sets `in_pos = False`, and continues looping, re-entering on the next breakout. Only the `one_done` baseline actually breaks. Anyone reading the docstring to interpret the "Chase" row misreads what was simulated.

**6.4 The friction model is directionally conservative. (LOW, verified)**
`FRICTION_PTS = 0.6` derives from $15 spread + $3 fees at 0.30 delta: $18 / ($0.30 × 100) = 0.6 SPX points. Arithmetically sound. Whether $15 covers one crossing or a round trip is unstated; if it is per side, true friction is nearer 1.2. That direction makes the chase worse and leaves the +18.5 endure number essentially unchanged, so the conclusions are safe — but the "$100 / 2-attempt budget cannot fund an 8-pt stop" reasoning in §5 of the anatomy doc inherits the ambiguity.

**6.5 Entry is a single unswept model. (MEDIUM, verified)**
Direction comes from the first ±TRIG excursion off the 08:30 price, swept only over {5, 8}. No alternative entry logic — opening-range break, first-15-minute close, retest — was tested. Given that the study's own §4 finds the early tape *anti*-predicts direction, an entry model keyed to the first excursion is entangled with the finding it is used to evaluate.

**6.6 The 8-pt "structural stop" recommendation is asserted, not measured. (MEDIUM, verified)**
`morning-flush-anatomy.md:169-173` concludes "a stop that means anything structural starts near 8 pts." My honest re-measurement (§1.2) says a 2-pt counter-move goes ≥8 pts adverse **18.7% of the time** before resuming — roughly 4 stop-outs per morning at 22 events/day, not the rare structural event the number implies. And in the sim, stop=8 blind returns −5.08 median, no better than stop=2. The 8-pt figure is derived from the counter-move frequency table, not from any test that it pays.

---

## 3. What I could not verify

1. **That $VIX1D/$COR1M/$COR3M ever served.** The st-b3jq bead reports a successful probe ("389 RTH candles/day"). I cannot re-probe — that needs a live Schwab call with a valid token, and the token wall (st-ndc) is a known failure mode. What I *can* say is that no such data exists on disk. Whether the probe was wrong, the backfill silently wrote nothing, or the data was written and lost, I cannot distinguish.
2. **Whether $ADD/$VOLD genuinely publish a session late.** The evidence is one after-hours run: $ADD was absent in 617 frames and appeared in 110, all timestamped 23:00–23:59 CT. That is consistent with the claim and I lean toward believing it, but it is a single evening's observation from a closed session, and the operational consequence (dropping to the two-trace live score) was adopted on that basis.
3. **The st-4ts recency confound numbers** (51%→88% vs full-RTH 78%→88%). The bead is open with the confound flagged; I did not attempt to reconstruct the windowed comparison, which would require re-deriving corpus coverage per window.
4. **Whether the meter's $SPX-based move detection agrees with the study's ES-based one.** This needs concurrent SPX and ES minute series over the 22 study days; the corpus carries ES but not $SPX. I flag the inconsistency as a design defect (§1.4) without being able to quantify how often it changes the answer.
5. **The 1,649 legs / 263 days figure.** `data/measurement/legprofiler_study.jsonl` holds 1,542 rows. The discrepancy runs the wrong way for corpus growth and I did not chase it.
6. **Live meter behaviour under load.** Three frames on one morning is not a sample. The direction flip I observed is real but n=1.
7. **Anything about market reality.** I audited whether the program measures what it claims. Whether the July regime persists, whether SPX behaves like ES, and whether any of this generalises past 22 clustered days are questions no amount of re-analysis of this corpus can answer.

---

## 4. Charter class 5's systemic question

**What would this program look like if its coverage did not depend on the operator's prompting?**

The pattern across every caught oversight — VVIX, VIX1D, the VIX residual, and now the clock, the calendar, and the untested $TICK residual — is the same. The agent extends along the axis the operator last named, and stops at the edge of that axis. Prompting-dependence is not a motivation problem; it is a **scope-definition** problem. Four changes would remove it:

**1. Enumerate channel *types*, not channel *instances*.** The failure mode is that "what else is like VVIX?" returns more volatility tickers. The fix is a standing taxonomy that the study design must traverse before any measurement, with an explicit written verdict per family — *measured / probed and unavailable / deliberately excluded, and why*. The families: traded-instrument tape; book microstructure; related-index price and basis; breadth; volatility surface; options flow and positioning; **clock and session structure**; **calendar and event**; **price location relative to prior structure**; cross-asset. The three in bold have never been traversed, and the first of them beats the entire program. A family with no entry is a finding, not a silence.

**2. Make the null model mandatory and adversarial.** Every reported AUC should ship next to the best *trivial* competitor — clock, price geometry, concurrent price change — computed on the same rows by the same code. The VIX residual test was invented, applied twice, and abandoned; it should have become a gate that no trace passes without. Concretely: a study script should refuse to emit a trace's AUC until it has emitted that trace's residual against concurrent price and its lift over a clock-plus-geometry baseline. Had this existed, the $TICK residual (.507) and the proximity baseline (.790 vs the score's .678) would have surfaced on day one without anyone asking.

**3. Derive the label from the decision, and state the decision in the artifact.** The deepest defect here is not any single number; it is that the label answers "will price exceed its high-water mark" while the trader asks "will this position pay before it hurts." A study should open by writing the decision in the operator's terms, then derive the label from it, then check that the label is not mechanically determined by something the trader already knows. That check — *what trivially available quantity most strongly predicts my label?* — is one line of code and would have caught the proximity confound before any trace was computed.

**4. Verify the artifact, not the process.** `st-b3jq` closed on "zero rows lost" — a process check — while the thing it claimed (three new symbols captured) was false and its own AC (row counts for the new symbols) went unrun. Closure criteria should assert the *artifact's* properties: rows present for the named symbols, frames journaled inside market hours, the meter's own calls scored against outcomes. The meter journal exists precisely so its calls can be scored, and the fact that scoring has not happened is the same gap in a different costume: the loop only closes when someone asks for it to.

Two of these are worth doing before the meter is consulted for another trade. The score display should carry a time term and an interval, or be turned off — as it stands it is confidently wrong in the direction that encourages holding a fading move. And the resume-rate paragraph in `morning-flush-anatomy.md` should be replaced with the forward-looking numbers, because "96–98%, refunded seconds later" and "91% within 15 minutes, 19% of the time after an 8-point bleed" recommend different position sizing.

---

*Prepared read-only. No file under `/root/projects/Strader` was created or modified; no bead was created, updated, or closed; nothing was committed.*
