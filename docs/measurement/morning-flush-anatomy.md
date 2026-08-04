# Morning Flush Anatomy + Convergence Signals

**Bead:** Grade The Flush (st-gzwb) · discovered from Coded Counter Wisdom (st-ug5)
**Date:** 2026-08-03 · **Revised:** 2026-08-04 (§2, §3, §5, §6 — audit remediation, st-kmmg)
**Data:** ES.c.0 trades 08:30–10:30 CT, `data/corpus/*/databento_glbx_es.jsonl`, 22 days (2026-07-02 → 2026-07-31; 07-01 has no morning tape)
**Scripts:** `scripts/measurement/morning_flush_study.py` → `data/measurement/morning_flush_study.json` (census, execution sims) and `scripts/measurement/morning_flush_forward_stats.py` → `data/measurement/morning_flush_forward_stats.json` (forward-looking backtest outcomes and stop economics). Regenerable; `data/` is untracked, so the tables here are the record.

## The contention under test

Steve, 2026-08-03 (refining the 07-31 origin of st-ug5): the recent regime of
large, often V-shaped moves inside the first 2 hours is consistent enough to
justify chasing the flush more vigorously than conventional wisdom accepts —
*"entering and cutting on the slightest backtest, with the intent to re-enter
if the flush resumes."* Explicitly not drawdown tolerance: zero-tolerance
cuts plus liberal re-entry.

Verdict in one paragraph: **the regime claim is confirmed and is stronger
than eyeballed — but the tape prices the proposed execution against you.**
Measured forward from the moment a 2-pt backtest triggers, a new extreme
prints within 15 minutes **91.4%** of the time (435/476 events, median wait
36.6 s) — so the re-entry trigger does fire, and cutting inside that is
expensive: every cut realizes a wiggle the move usually takes back, and the
re-entry refills at a worse price. Every mechanical tight-stop variant tested
lost money at the median *even when the day's direction was known in advance*,
and priced directly against holding through, **no stop distance in {2, 4, 8,
12} pts pays** (§2). What pays in this regime is direction + patience
(oracle-direction hold: **+18.5 pts/day median net, 20/22 days positive**).
The chase instinct survives in one specific form: the breakout re-entry
trigger is reliable enough that *re-entry after a cut is rarely regretted* —
the harness's liberal re-entry design is sound. What does **not** survive is
the idea that the wiggle is refunded seconds later and can therefore be sized
past: **18.7% of 2-pt backtests bleed ≥8 pts against you before resuming**,
p90 12.5 pts, worst 55.0. Roughly four eight-point bleeds a morning.

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

Counter-moves ≥ T from the running extreme, tracked from the primary move's
start to the **window** end (not clipped at the move's extreme — clipping
forces resume = 100 % by construction; the first-pass numbers had that
artifact). Event counts below reproduce the study's stored census exactly at
every threshold; the outcome columns are **forward-looking** —
`morning_flush_forward_stats.py` walks the tick stream from each event and
never consults where the move eventually topped out:

| T (pts) | events/22 days | P(new extreme ≤ 15 min) | median wait | median adverse first | p90 adverse | P(adverse ≥ 8 first) |
|---|---|---|---|---|---|---|
| 1.0 | 945 (≈ 43/day) | 95.6 % (903/945) | 11.6 s | 2.00 | 7.50 | 9.4 % |
| 1.5 | 628 (≈ 29/day) | 93.3 % (586/628) | 23.6 s | 3.00 | 10.50 | 14.2 % |
| **2.0** | **476 (≈ 22/day)** | **91.4 % (435/476)** | **36.6 s** | **3.75** | **12.50** | **18.7 %** |
| 3.0 | 322 (≈ 15/day) | 88.5 % (285/322) | 64.6 s | 5.00 | 15.50 | 27.6 % |
| 5.0 | 164 (≈ 7/day) | 79.9 % (131/164) | 167.1 s | 8.50 | 19.00 | 54.3 % |

"Adverse first" is the worst excursion beyond the standing extreme between
the event and its resolution — a new move-direction extreme, or 10:30 if none
comes. It is what the position endures to collect the resume. At T = 2.0 that
distribution runs median 3.75 / p90 12.50 / p95 17.00 / **max 55.00** pts.

Reading the T = 2.0 row precisely: 435 of 476 events resolve inside 15
minutes; 20 more resolve later (median 24 min); 21 never resolve before 10:30
— and those 21 fall on 21 *distinct* days, one apiece, because a day can only
run out of move once. Ten of the 21 are censored rather than failed: the
10:30 close arrived before their 15-minute clock expired.

**Why the old 96–98 % resume rates are gone.** They came from
`morning_flush_study.resume_events()`, whose `resumed` flag and `remaining`
field are both derived from the primary move's *terminal extreme* — a
quantity nobody standing in the trade can see. Across all 2,535 stored events
(five thresholds × 22 days), `resumed == (remaining > 0)` in **2,535 of
2,535**, and failures are capped at one per day at every threshold
(22/22/21/18/16). So this doc's former conditional — "with ≥ 5 pts of move
still ahead, resumption ran **415/415 (100 %)**" — was true by construction:
an event has `remaining > 0` exactly when a later extreme prints, so
conditioning on `remaining ≥ 5` selects the resumes and then reports that
they resumed. It was the same class of artifact as the span-clipped first
pass this table was written to fix. Surfaced by the cold-context audit,
`docs/audits/2026-08-04-auditor-report.md` §1.2. The forward table above is
the replacement; nothing in it uses the terminal extreme.

**What a stop costs, measured.** Same 476 events, same tape. Both paths start
in position at the standing extreme (where the study's breakout re-entry model
puts you). The endure path holds through the backtest; the stop path exits at
the first tick S pts adverse and re-enters at the new extreme, paying 0.6 pts
friction for the extra attempt (FD0 model: $15 spread + $3 fees at 0.30 δ).
Both paths end holding the same position at the same price, so the whole
difference is the stop's doing, and per-event differences sum coherently
across a day:

| stop S | fires | per day | net vs endure, pts/day | median day | days the stop helped |
|---|---|---|---|---|---|
| 2 pts | 476 | 21.6 | **−52.84** | −50.10 | 0/22 |
| 4 pts | 220 | 10.0 | **−39.61** | −41.50 | 0/22 |
| 8 pts | 89 | 4.1 | **−27.65** | −26.55 | 1/22 |
| 12 pts | 50 | 2.3 | **−21.41** | −12.85 | 2/22 |

The 2-pt row fires on 100 % of 2-pt events by definition — that is the event
set, not a coincidence. The split at S = 8: 7 stop-outs saved a combined
**+75.8** pts on episodes the move never came back from, and 82 cost
**−684.1** pts on episodes it did. The curve is monotone in stop width with no
knee: every distance tested is negative, and the loss shrinks only as the stop
approaches not existing.

Two readings, both true:
1. **Steve's premise mostly holds** — a 2-pt backtest is followed by a new
   extreme inside 15 minutes 91.4 % of the time, half of them inside 36.6
   seconds. A backtest is usually not the end of the move.
2. **That is exactly why cutting on one is a tax, not protection.** At the
   FD0 budget-derived stop (~1.1 pt), the median day serves ~40 cuts inside
   the move. Priced against holding through, a 2-pt stop costs **52.8
   pts/day** and is worse than enduring on 22 of 22 days. But "refunded
   seconds later" was always too generous a gloss: 18.7 % of 2-pt events go
   ≥ 8 pts against you first — about four eight-point bleeds a morning — and
   the worst on this tape was 55 pts.

## 3. Execution economics — every tight-stop variant loses

Simulation, no hindsight: direction = first ±TRIG excursion off the 08:30
price; stop S adverse; re-enter on new extreme ("flush resumes"); trail-exit
on an 8-pt reversal from the campaign extreme; 0.6 pts friction per attempt.
The Chase campaign runs to the 10:30 window close — the 8-pt trail-exit ends
the *attempt*, not the campaign, and a later breakout to a new extreme
re-enters. Only the One-and-done row stops after its first exit. (The
`simulate()` docstring said the trail-exit ended the campaign; corrected
2026-08-04, audit §6.3.) Median net pts/day (22 days):

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
  breakout) was probed and **failed in every configuration measured**. The
  original probe only ever ran nested inside `for cap in (2, 5)`, so the
  liberal re-entry that is the lane's whole point was never actually
  simulated. Re-run with the attempt cap removed (±5 trigger, 2-pt stop,
  2-pt dip, `morning_flush_forward_stats.py` §4):

  | turn threshold | attempt cap | median net pts/day | days positive | median attempts/day |
  |---|---|---|---|---|
  | 1.5 pts | none | **−237.97** | 0/22 | 367 |
  | 1.5 pts | 5 | −6.50 | 2/22 | 5 |
  | 1.5 pts | 2 | −5.58 | 4/22 | 2 |
  | 3.0 pts | none | **−67.07** | 0/22 | 98 |
  | 3.0 pts | 5 | −6.62 | 3/22 | 5 |
  | 3.0 pts | 2 | −3.83 | 4/22 | 2 |

  Raising the turn threshold from 1.5 to 3.0 pts cuts the churn from 367
  attempts/day to 98 and the loss from −238 to −67, and it is still 0/22
  positive: the cooldown does not suppress the tick-churn artifact, **the cap
  does** — and a cap is the opposite of liberal re-entry. So the lane is not
  "promising but unmeasured." At tick granularity it is measured, and it is
  catastrophic. A bar-level version with entry cooldown (Join The Turn,
  st-chat) is still the one shape under which "tight cut + liberal re-entry"
  could work — entry-on-dip inverts the refill geometry, risking turn+stop to
  recapture the wiggle rather than paying it — but it starts from a refuted
  tick-level predecessor, not an encouraging one. Audit
  `docs/audits/2026-08-04-auditor-report.md` §6.2.

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
   ~15×.
   This doc used to conclude from that frequency table alone that *"a stop
   that means anything structural starts near 8 pts."* That was an assertion
   read off event counts, never a cost comparison, and priced properly it
   does not hold. Against the endure baseline (§2), an 8-pt stop fires
   ~4×/morning and costs **−27.65 pts/day** — better than 4 pts (−39.61) and
   2 pts (−52.84), worse than 12 pts (−21.41), negative everywhere, and
   monotone in stop width with no knee at 8 or anywhere else. There is no
   distance at which a stop stops being a tax on a correctly-positioned
   campaign; the cost just shrinks toward the no-stop limit. What 8 pts
   actually marks is a *frequency* boundary, not a structural one: it is
   where stop-outs fall to ~4/day, near the top of the backtest excursion
   distribution (8 pts is exceeded by 18.7 % of events; p90 is 12.5 pts).
   The budget observation survives unchanged — a $100 / 2-attempt budget
   cannot fund an 8-pt stop at 0.30 δ — but it is no longer the reason the
   tenet fails. The tenet fails on its own economics at every width.
   **What this comparison does not price:** it holds direction and entry
   fixed, so it measures the cost of stopping *inside a move you are
   positioned with*. It says nothing about a stop's real job — capping a
   position taken in the wrong direction, which is exactly the exposure the
   §4 fade rule carries. Do not read "no stop pays" as
   "trade without a stop." Read it as: the stop is paid for by the
   direction risk, not by the wiggle.
2. **Liberal re-entry is validated; zero-tolerance cutting is not.** 91.4 %
   of 2-pt backtests print a new extreme within 15 minutes, so the breakout
   re-entry trigger fires nearly every time — that is the license for
   re-entering after *any* exit, and it stands. What does not stand is the
   sizing implication the old "refunded seconds later" phrasing carried: the
   median wait is 36.6 s, but the p90 adverse excursion is 12.5 pts and 18.7 %
   of events bleed ≥ 8 pts first. Re-entry is cheap; enduring to earn it is
   not.
3. **Direction is the whole prize** (+18.5/day median for solving it), and
   the early tape is a trap: the promising graders are early-conviction
   *fade* + $TICK breadth + first-15-min energy for size. These need more
   days before parameterizing — the corpus cron adds one per day.
4. **The V-shape is real but window-incomplete** — 9/22 strong-retrace days.
   Flush-direction campaigns should not assume the V completes by 10:30.

## 6. Out-of-sample addendum (2026-08-03, later the same session)

A scout sweep surfaced 14 pre-July corpus days with 08:30–13:00 CT morning
tape (the rest of the 267-day corpus is afternoon-only). 12 were usable
(2025-07-22 → 2026-04-23; one lacked near-open tape) — an out-of-sample
morning set spanning a year, run through the same script
(`--days … --out data/measurement/morning_flush_oos.json`). This addresses
the coverage confound the Recency Regime Lens bead (st-4ts) worries about:
its 51 %→88 % morning-share claim compares windows with structurally
different pull coverage; restricted to full-RTH days the shift is 78 %→88 %.

| | July 2026 (n=22) | Out-of-sample (n=12) |
|---|---|---|
| Primary move, median | **52.6 pts** | 31.0 pts |
| Days ≥ 45 pts | 15/22 (68 %) | 4/12 (33 %) |
| V-shape (≥50 % retrace by 10:30) | 5/22 | 5/12 |
| P(new extreme ≤ 15 min), T=1 / 2 / 5 | 95.6 / 91.4 / 79.9 % | 94.3 / 88.0 / **66.1 %** |
| Median adverse before resume, T=2 | 3.75 pts | 3.50 pts |
| P(adverse ≥ 8 first), T=2 | 18.7 % | 13.5 % |
| 8-pt stop vs endure, pts/day | −27.65 (1/22 days helped) | −9.48 (3/12) |
| f5 direction agreement | 8/22 (inverted) | 7/12 (not inverted) |
| Fade-f5 ≥ 4 rule | 12/18 | **3/9 — fails** |
| Energy→size, ρ (f5rng / f15rng / f15vol) | +.46 / +.48 / +.57 | **+.82 / +.87 / +.90** |

The resume row replaces the earlier `98 / 96 / 90 %` vs `97 / 94 / 84 %`
comparison, which used the hindsight `resumed` flag retired in §2. Both
samples were re-run through `morning_flush_forward_stats.py`.

Sampling caveat: the OOS days were pulled for earlier studies, i.e. selected
*because* they were interesting — which biases them toward big days and makes
the size gap, if anything, understated.

**Scope of this OOS set — read before treating any of it as validation.**
These 12 days carry ES tape and nothing else. All 12 lack
`data/corpus/<day>/internals.jsonl` (verified 0/12), so **no internals-based
finding in this program has a single out-of-sample day**: not the $TICK,
$ADD, $VOLD, $VIX, $VVIX or $TRIN traces, not the convergence score, not the
volatility quadrants, and not the live meter's displayed percentages — those
all rest on the same 22 clustered July days that trained them, with nothing
held out. What *is* out-of-sample here is the price-only anatomy: move size,
V-shape, backtest resume rates, stop economics and the direction/energy
covariates. The 12 days are also clustered (four of them in October 2025),
so even the price-side replication is 12 draws, not 12 independent months.

What this changes:

1. **"Recently consistent regime" upgrades from eyeball to measured.** July's
   median morning move is ~1.7× the year-spanning baseline, against a
   selection bias running the other way.
2. **The anatomy is mostly structural, with a caveat the hindsight numbers
   hid.** Shallow backtests resume at nearly the same forward rate in both
   samples (T=1: 95.6 % vs 94.3 %; T=2: 91.4 % vs 88.0 %) — backtests-resume
   is how ES mornings work, not a July novelty. **Deep ones do not**: at
   T=5 the forward rate falls from 79.9 % in-sample to **66.1 %** out of
   sample, a gap the retired hindsight measure showed as 90 % vs 84 %. So a
   5-pt backtest is a materially weaker resume signal outside July than the
   old table implied. The indictment of noise-level cuts stands everywhere
   (every stop distance in {2, 4, 8, 12} costs more than enduring on average
   in both samples); the license for liberal re-entry stands for shallow
   backtests everywhere and should not be extended to deep ones on July
   evidence.
3. **The fade-the-open direction rule is demoted** from candidate to
   July-local artifact (3/9 out-of-sample). Direction remains unsolved.
   $TICK could not be tested — the earliest internals capture on disk is
   2026-06-08 and every OOS day predates it.
4. **Early energy for size is the one grader that replicates**, strongly, in
   both samples. The first 15 minutes tell you *how big* today is — still
   not *which way*.

## Follow-on lanes (not started)

- Bar-level dip-entry sim with cooldown (§3) — now the *only* surviving form
  of that lane; the tick-level version is measured and refuted, not open.
- MBP-1 book-imbalance covariate (corpus has it; unused here).
- Mancini letter level/stance join per day (letters parsed daily since
  st-26q5; qualitative join not yet coded).
- Morning OPRA pull (options window is 13:00–15:00 CT only; a morning
  extension is a paid Databento backfill decision).
- Re-run monthly as the corpus grows; every number above regenerates from
  the script.
