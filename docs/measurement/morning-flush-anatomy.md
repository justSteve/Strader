# Morning Flush Anatomy + Convergence Signals

**Bead:** Grade The Flush (st-gzwb) · discovered from Coded Counter Wisdom (st-ug5)
**Date:** 2026-08-03 · **Data:** ES.c.0 trades 08:30–10:30 CT, `data/corpus/*/databento_glbx_es.jsonl`, 22 days (2026-07-02 → 2026-07-31; 07-01 has no morning tape) · **Script:** `scripts/measurement/morning_flush_study.py` → `data/measurement/morning_flush_study.json` (regenerable; data/ is untracked, tables here are the record)

## The contention under test

Steve, 2026-08-03 (refining the 07-31 origin of st-ug5): the recent regime of
large, often V-shaped moves inside the first 2 hours is consistent enough to
justify chasing the flush more vigorously than conventional wisdom accepts —
*"entering and cutting on the slightest backtest, with the intent to re-enter
if the flush resumes."* Explicitly not drawdown tolerance: zero-tolerance
cuts plus liberal re-entry.

Verdict in one paragraph: **the regime claim is confirmed and is stronger
than eyeballed — but the tape prices the proposed execution against you.**
Backtests inside these moves resume 96–98% of the time, which is precisely
why cutting on them is expensive: every cut realizes a wiggle the move was
about to refund, and the re-entry (on breakout to a new extreme) refills at
a worse price. Every mechanical tight-stop variant tested lost money at the
median *even when the day's direction was known in advance*. What pays in
this regime is direction + patience (oracle-direction hold: **+18.5 pts/day
median net, 20/22 days positive**). The chase instinct survives in one
specific form: because resumption is near-certain while ≥5 pts of move
remain, *re-entry after a cut is nearly free of regret* — the harness's
liberal re-entry design is sound — but the cut itself must be structural
(≥8 pts) or event-driven, never "slightest backtest."

## 1. Morning-move census — the regime is real

Primary move = largest peak-to-trough (or trough-to-peak) travel inside
08:30–10:30 CT. All 22 days, ES points:

| Date | Net | Range | Move | Dir | Span | Retrace |
|---|---|---|---|---|---|---|
| 07-02 | −26.00 | 71.25 | 71.25 | dn | 08:52→10:07 | 0.33 |
| 07-03 | +0.50 | 12.50 | 12.50 | up | 08:50→09:42 | 0.52 |
| 07-06 | +22.25 | 34.75 | 34.75 | up | 08:38→10:29 | 0.04 |
| 07-07 | −40.00 | 58.00 | 58.00 | dn | 08:30→09:42 | 0.29 |
| 07-08 | −32.75 | 54.75 | 54.75 | dn | 08:46→10:26 | 0.11 |
| 07-09 | +26.00 | 45.50 | 45.50 | up | 09:21→10:27 | 0.06 |
| 07-10 | +13.00 | 54.00 | 54.00 | up | 09:33→10:27 | 0.06 |
| 07-13 | −0.75 | 37.00 | 37.00 | dn | 09:00→09:16 | 0.82 |
| 07-14 | +17.75 | 47.25 | 47.25 | up | 09:16→09:34 | 0.60 |
| 07-15 | −6.75 | 34.25 | 34.25 | dn | 08:37→10:17 | 0.42 |
| 07-16 | +10.25 | 39.50 | 39.50 | up | 08:48→09:45 | 0.41 |
| 07-17 | +35.00 | 66.00 | 66.00 | up | 08:35→09:17 | 0.52 |
| 07-20 | −12.00 | 51.25 | 51.25 | dn | 08:45→09:59 | 0.46 |
| 07-21 | +17.75 | 39.50 | 39.50 | up | 08:47→10:27 | 0.06 |
| 07-22 | +29.25 | 34.25 | 34.25 | up | 08:30→10:27 | 0.09 |
| 07-23 | −34.25 | 68.25 | 68.25 | dn | 08:43→10:28 | 0.04 |
| 07-24 | +41.25 | 59.50 | 59.50 | up | 09:00→10:28 | 0.11 |
| 07-27 | −66.75 | 91.00 | 91.00 | dn | 08:36→09:43 | 0.43 |
| 07-28 | +19.50 | 60.25 | 60.25 | up | 08:47→10:26 | 0.15 |
| 07-29 | −56.25 | 68.00 | 68.00 | dn | 08:34→09:44 | 0.29 |
| 07-30 | −13.50 | 47.50 | 47.50 | dn | 09:28→10:15 | 0.33 |
| 07-31 | −44.25 | 87.75 | 87.75 | dn | 08:34→09:16 | 0.63 |

- **Size:** min 12.5, median **52.6**, max 91.0 pts. 19/22 days ≥ 34 pts.
- **Direction:** 11 down / 11 up — the flush regime is not one-sided.
- **Timing:** 16/22 moves originate before 09:00 CT; median duration 71 min.
  The flush is an *open* phenomenon — by 09:15 you are usually mid-move.
- **V-shape** (≥50 % retrace of the move before 10:30): 5/22 strictly, but
  the retrace distribution is bimodal — 9 days retrace ≤ 0.11 (trend holds
  through 10:30) and 9 days retrace ≥ 0.33. "Often V-shaped" is fair if
  V includes retracement completing after 10:30; within the window it is a
  minority outcome. Trading consequence: the move's *extreme* is not
  reliably followed by a window-time V — exits must not presume the V.

## 2. Backtest anatomy — what "slightest backtest" actually costs

Counter-moves ≥ T from the running extreme, measured from move start to
window end (not clipped at the move's extreme — clipping forces resume=100%
by construction; first-pass numbers had that artifact):

| T (pts) | events/22 days | P(resume) | median resume time | median remaining at event |
|---|---|---|---|---|
| 1.0 | 945 (≈ 43/day) | **98 %** | 12 s | 24.8 pts |
| 1.5 | 628 | 96 % | 26 s | 24.0 |
| 2.0 | 476 (≈ 22/day) | **96 %** | 43 s | 23.5 |
| 3.0 | 322 | 94 % | 74 s | 22.0 |
| 5.0 | 164 (≈ 7/day) | 90 % | 213 s | 20.6 |

Conditioning (T = 2.0): with ≥ 5 pts of move still ahead, resumption ran
**415/415 (100 %)**; the only failures cluster at the move's terminal 0–5 pts
(66 % resume, 61 events). Even 8+-pt counter-moves resumed 85 % (76/89).

Two readings, both true:
1. **Steve's premise holds** — the flush is a freight train; a backtest is
   almost never the end of the move.
2. **That is exactly why cutting on one is a tax, not protection.** At the
   FD0 budget-derived stop (~1.1 pt), the median day serves ~40 cuts inside
   the move. Each cut realizes a loss with ~98 % probability of being
   refunded seconds later, plus ~0.6 pts friction per re-entry (FD0 model:
   $15 spread + $3 fees at 0.30 δ).

## 3. Execution economics — every tight-stop variant loses

Simulation, no hindsight: direction = first ±TRIG excursion off the 08:30
price; stop S adverse; re-enter on new extreme ("flush resumes"); trail-exit
on an 8-pt reversal from the campaign extreme; window-close exit; 0.6 pts
friction per attempt. Median net pts/day (22 days):

| Variant | stop 1 | stop 2 | stop 3 | stop 5 |
|---|---|---|---|---|
| Chase (±5 trigger) | −6.1 | −4.5 | −5.3 | −2.5 |
| Chase, direction known (oracle) | −12.8 | −12.5 | −5.1 | −4.5 |
| Chase, capped 2 attempts (FD0 budget) | −3.2 | −5.2 | −6.5 | −5.3 |
| One-and-done (same entry, 8-pt trail) | — | −2.7 | — | — |
| Endure to 10:30 (same entry) | — | −9.4 | — | — |
| **Endure, direction known (oracle)** | — | **+18.5** (20/22 days +) | — | — |

- Best chase config managed 9/22 positive days; none positive at the median.
- Oracle direction makes tight-stop chasing *worse* (more attempts, same
  churn) — the loss is mechanical, not informational: cut-at-wiggle +
  refill-at-breakout pays the wiggle amplitude every cycle.
- A dip-entry variant (re-enter by joining the backtest on its turn, not the
  breakout) was probed and is **unresolved**: at tick granularity a 0.75-pt
  turn sits inside bid-ask bounce and the naive implementation churned
  hundreds of attempts/day (artifact, not finding). A bar-level version with
  entry cooldown is the follow-on lane — it is the one shape under which
  "tight cut + liberal re-entry" could still work, because entry-on-dip
  inverts the refill geometry (each cycle risks turn+stop to recapture the
  wiggle rather than paying it).

## 4. Convergence signals — grading the move at/near the open

The surprise of the study: **the early tape anti-predicts direction.**

| Signal (read by ~08:45–09:00) | Agreement with primary-move direction |
|---|---|
| First-5-min net direction | **8/22 (36 %)** — inverted |
| First ±5-pt trigger direction | 9/22 (41 %) — inverted |
| First-15-min net direction | 10/22 (45 %) |
| First-5/15-min aggressor delta | 9/22 (41 %) |
| Overnight gap direction | 12/21 (57 %) |
| **$TICK 09:00 reading (sign)** | **13/21 (62 %)** — best direct signal |

Down-days vs up-days at the open (medians): down-days *gap up +13.2* and
run *+9.2 in the first 5 min* on *+506 aggressor delta*; up-days open flat
(gap +1.5, f5 −1.0). The big morning flush is a **trap-and-reverse**
structure — the early conviction is the fuel, not the direction. This is
Mancini failed-move / trap doctrine showing up in the measured tape.

Candidate rules (hypothesis-generating; n = 22; none reach conventional
significance — binomial one-sided p ≈ 0.10–0.12; do NOT trade these as
validated):

| Rule | Fires | Correct | False positives |
|---|---|---|---|
| Fade first-5-min net when \|f5\| ≥ 4 pts | 18/22 | 12 (67 %) | 6 |
| Fade-f5 ≥ 4, else $TICK sign | 21/22 | 14 (67 %) | 7 |
| $TICK 09:00 sign alone | 21/22 | 13 (62 %) | 8 |
| Fade gap when \|gap\| ≥ 8 | 18/22 | 9 (50 %) | 9 — dead |

Derived check: entering *opposite* the first ±5 trigger and holding to 10:30
nets **median +8.15/day but mean +2.9 with worst −62.4** (07-24 style
gap-and-go up days destroy an unprotected fade). A fade needs the structural
stop the chase model lacks.

**Size grading** (is today a mover?): first-15-min volume rank-correlates
with primary-move size at ρ ≈ +0.57; first-5/15-min range at ρ ≈ +0.46/0.48;
gap size is useless (ρ +0.08). Early *energy* — not early *direction* —
grades the day.

## 5. Design consequences for st-ug5 / FD0

1. **The noise floor is now measured, and FD0's derived ~1.1-pt stop is ~3×
   inside it.** The FD0 spec's open defect ("needs a sub-minute measure")
   gets its number here: counter-moves ≥ 2 pts arrive ~22×/morning, ≥ 3 pts
   ~15×. A stop that means anything structural starts near 8 pts — which the
   $100/2-attempt budget cannot fund at 0.30 δ. The budget, not the tenet,
   is what forbids "cut on slightest backtest."
2. **Liberal re-entry is validated; zero-tolerance cutting is not.** The
   96–98 % resumption rate is the empirical license for re-entry after *any*
   exit — and simultaneously the indictment of exits taken inside the noise.
3. **Direction is the whole prize** (+18.5/day median for solving it), and
   the early tape is a trap: the promising graders are early-conviction
   *fade* + $TICK breadth + first-15-min energy for size. These need more
   days before parameterizing — the corpus cron adds one per day.
4. **The V-shape is real but window-incomplete** — 9/22 strong-retrace days.
   Flush-direction campaigns should not assume the V completes by 10:30.

## Follow-on lanes (not started)

- Bar-level dip-entry sim with cooldown (the unresolved lane in §3).
- MBP-1 book-imbalance covariate (corpus has it; unused here).
- Mancini letter level/stance join per day (letters parsed daily since
  st-26q5; qualitative join not yet coded).
- Morning OPRA pull (options window is 13:00–15:00 CT only; a morning
  extension is a paid Databento backfill decision).
- Re-run monthly as the corpus grows; every number above regenerates from
  the script.
