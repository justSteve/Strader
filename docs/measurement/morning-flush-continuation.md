# Morning Flush Continuation Traces — Internals, VIX, Orderflow

**Bead:** Continuation Trace (st-cdwe) · discovered from Grade The Flush (st-gzwb)
**Date:** 2026-08-03 · **Revised 2026-08-04** under Residual Gate Standing (st-4cgo) — see *What the residual gate changed* below
**Script:** `scripts/measurement/morning_flush_continuation.py` + `scripts/measurement/residual_gate.py` → `data/measurement/morning_flush_continuation.json`
**Data:** the 22 July morning-move days (spans from `morning_flush_study.json`); internals $TICK/$TRIN/$ADD/$VOLD 1-min candles; **$VIX backfilled this session** (added to `corpus_pull_internals.py` [st-cdwe] — symbol is `$VIX`, `$VIX.X` is empty; 29 corpus days now carry it, zero rows lost in the force-rewrite, backup at `data/corpus/_internals_backup_20260803/`).

## The question

Steve, after reading the contention review: *"I'm less interested in the
statistical alignment than in finding a metric that bolsters confidence in
continuation. Market Internals or VIX for example. These moves that have been
so one-sided must be leaving some trace apart from 'it's happening more often
in the last couple of months.'"*

Answer, as revised: **the traces are real but most of them are the price move
you are already looking at.** Nine traces separate continuing from dying
minutes at AUC .44–.68 raw. Put every one of them through the residual test
that killed the VIX trace — regress out the concurrent 5-minute ES move — and
the two the live meter runs on ($TICK, VIX) fall to a day-clustered coin flip.
Breadth ($ADD, and the slower $TICK sign-share) is what carries independent
information, and $ADD publishes a session late so it is not live-readable.
**And all ten graded quantities, including the convergence score, sit below a
trivial clock-and-geometry baseline built with no market data beyond ES.**

## Method (one paragraph)

Each minute from a move's start to 10:14 CT is labeled **CONT** if price
extended ≥ 2 pts beyond the extreme-standing-at-that-minute within the next
15 minutes, else **TERM** (last 15 min of window excluded — truncated
lookahead). 1,860 labeled minutes: 1,062 CONT / 798 TERM (base rate 57.1 %).
Every trace is causal (data through minute *t* only) and oriented so higher =
confirms the move. AUC is rank-sum P(CONT sample > TERM sample); "day med" is
the median of per-day AUCs (minutes cluster within days — the honest check).

## Minute-level trace ranking — every column, or none

Produced by `residual_gate.grade_trace()`. The gate returns raw AUC, the
residual after the concurrent 5-minute ES move is regressed out
(leave-one-day-out fit), the day-median of that residual, and a trivial
clock+geometry competitor fit on the same rows — or it raises. There is no
path through this study to a trace's raw AUC alone.

| Trace (oriented) | raw AUC | day med | **residual** | **resid day med** | trivial baseline | verdict |
|---|---|---|---|---|---|---|
| Convergence score 0-3 | 0.690 | 0.652 | **0.607** | **0.572** | 0.822 | SURVIVES |
| $VIX 5-min slope x (-dir) | 0.683 | 0.654 | **0.525** | **0.499** | 0.787 | COIN FLIP |
| $TICK level x dir | 0.677 | 0.632 | **0.609** | **0.510** | 0.821 | COIN FLIP |
| $ADD 10-min slope x dir | 0.673 | 0.690 | **0.611** | **0.603** | 0.822 | SURVIVES |
| $TICK 10-min sign-share | 0.656 | 0.625 | **0.615** | **0.594** | 0.821 | SURVIVES |
| $VOLD 10-min slope x dir | 0.656 | 0.569 | **0.594** | **0.529** | 0.822 | COIN FLIP |
| Volume pace (5-min vs move avg) | 0.655 | 0.594 | **0.599** | **0.524** | 0.787 | COIN FLIP |
| Wiggle-calm (backtest depth trend) | 0.577 | 0.580 | **0.591** | **0.590** | 0.787 | SURVIVES |
| ES 5-min aggressor delta x dir | 0.541 | 0.624 | **0.405** | **0.527** | 0.787 | INVERTED |
| $TRIN oriented | 0.439 | 0.483 | **0.434** | **0.469** | 0.821 | INVERTED |

Verdict band: INVERTED = pooled residual below .45; COIN FLIP = day-median
residual below .55; otherwise SURVIVES. The band was calibrated to reproduce
the auditor's own verbal verdicts on the five traces he graded by hand, not
swept. Read the verdicts as labels on the numbers beside them, not as a test.

**Reading the table row by row.**

- **$TICK level × dir** — CONT median +112, TERM median −51. TICK sits on the
  move's side while it lives and has already flipped when it dies. But 15.6 %
  of its variance is the concurrent ES move, and once that is out, the
  day-median residual is **.510**. Pooled it looks alive (.609); day-clustered
  it is a coin flip. **This is half of the live meter.**
- **$VIX 5-min slope × (−dir)** — **78.3 %** of its variance is the concurrent
  ES move (st-40fv found the same thing at R² .79 in percent terms). Residual
  .525, day-median **.499**. Price momentum wearing a VIX costume, confirmed a
  second time by a different route. **This is the other half of the live meter.**
- **$ADD 10-min slope × dir** — the strongest survivor on the day-clustered
  number: residual .611, day-median **.603**, and only 9.7 % ES-coupled
  ($TICK sign-share edges it pooled, .615, but not day-median). Breadth is carrying
  information the price move does not. It also **publishes a session late**, so
  the meter cannot read it live — the program's one genuinely independent
  channel is the one it had to drop.
- **$TICK 10-min sign-share** — residual day-median .594, ES-coupling 4.8 %.
  Never residual-tested before today; it survives. Slower than the level and
  ranked below it raw, which is why it was never promoted.
- **$VOLD 10-min slope**, **volume pace** — residual day-medians .529 / .524.
  Coin flips.
- **Wiggle-calm** — residual (.591) slightly *above* its raw AUC (.577):
  essentially uncoupled from the concurrent ES move (R² 0.6 %). Weak but real,
  and the one trace the residual test flatters.
- **ES 5-min aggressor delta** — pooled residual **.405, inverted**. Its raw
  .541 was already near chance; conditional on the price move it points the
  other way.
- **$TRIN** — dead raw, dead residual. Unchanged verdict.

**The column that should stop the conversation is the last-but-one.** The
trivial baseline is a leave-one-day-out linear fit on two numbers a trader can
read off the chart with no data feed at all: how many minutes the move has been
running, and how far inside its own standing extreme price currently sits. It
grades this label at **.787–.822 pooled, .905–.906 day-median** — against the
convergence score's .690 / .652. **Not one of the ten graded quantities beats
it.** That is finding §1.1/§4.2 of the 2026-08-04 audit, and the gate now
surfaces it automatically on every run instead of waiting for someone to ask.

Because the baseline includes distance-from-the-standing-extreme, this is also
a statement about the *label*: a minute sitting 15 pts inside a backtest must
travel 17 pts to be called CONT while a minute at the extreme must travel 2.
The decision-aligned relabelling is `docs/measurement/decision-aligned-truth.md`.

**Comparability note.** The gate's raw AUC is computed on the rows where the
concurrent 5-minute ES move is defined — measured on the move's own bar series,
so the first five minutes of each move drop out (71–110 rows per trace). On all
value-bearing minutes, the raw AUCs are $TICK .667, $VIX .662, $ADD .654,
$TICK-share .641, $VOLD .638, volume pace .617, wiggle-calm .577, ES delta
.547, $TRIN .436 — within .01 of the figures published on 2026-08-03 (.665 /
.660 / .653 / .638 / .638 / .616 / .578 / .548 / .439). Day-medians moved more
(e.g. $ADD .574 → .675): **2026-07-30** ran 48 labeled minutes of which exactly
one was TERM, and that minute was 10:15, so the §3.5 fix below makes the day
one-class and it drops out of every per-day median. A per-day AUC resting on a
single negative was noise; losing it is a repair, not a regression.

## Delta divergence — the "refutation" was a conditioning artifact

**Superseded 2026-08-04 (auditor's report §2.2).** The 2026-08-03 version of
this section read: *"the classic 'price made a new extreme but delta didn't'
exhaustion flag fired in 22 % of continuing minutes vs 10.5 % of dying ones —
at this granularity it is a continuation accompaniment, not a warning. A
popular heuristic, refuted on this tape."* That comparison was unconditioned
and the claim does not survive fixing it.

The flag is `new_ext_5 AND delta5 × dir < 0` — it **cannot fire unless a new
extreme has printed in the last five minutes**. New extremes print in **63.5 %
of CONT minutes and 25.9 % of TERM minutes**. That 2.5× eligibility gap is the
entire published effect: the flag fires more often during continuation because
continuation is when the flag is *allowed* to fire. Reproduced unconditioned
rates on the corrected sample: 22.4 % CONT vs 10.5 % TERM.

Conditioning on the 881 minutes where the heuristic is even defined:

| among minutes where a new extreme printed in the last 5 min | n | P(CONT) |
|---|---|---|
| delta **against** the move (the divergence) | 322 | **0.739** |
| delta with the move | 559 | **0.780** |

Divergence is associated with **lower** continuation — the classic warning
direction — by 4.1 points. Naive two-proportion z = −1.38, p = 0.167, and that
test treats 1,860 minutes inside 22 mornings as independent draws, so it is the
*optimistic* bound. Day-clustered it is weaker still.

**How weak: the sign is not even stable to the eligibility definition.**
Requiring the new extreme in *this* minute rather than anywhere in the last
five leaves 410 minutes, and the gap reverses: divergence 0.908 (n = 98) vs
0.853 (n = 312), z = +1.39, p = 0.163. Both cuts are individually
insignificant and they point opposite ways, which is what an effect of no
practical size looks like when you slice it two defensible ways.

Honest conclusion: **the classic exhaustion read is weakly in the direction
practitioners claim, on the definition this study's flag actually uses, and it
is nowhere near decision-grade. The published "refuted on this tape" claim was
an artifact of comparing unconditioned base rates and is withdrawn.**

Reproduction note: the auditor's §2.2 conditioned table reports 307 diverging /
548 with-move minutes (0.723 / 0.774) against my 322 / 559 (0.739 / 0.780). The
direction, the magnitude of the gap and the conclusion all reproduce; the
eligible-minute count does not (855 vs 881). His labelling loop was rebuilt
independently and his new-extreme detector is not identical to this one: the
§3.6 fix below moved this study's eligible set by 9 minutes (872 → 881) and
its diverging subset by 2 (320 → 322), so it accounts for a small part of the
26-minute gap and the rest sits in his rebuild, not in this script. Noted
rather than reconciled — the conclusion is the same either way.

## The convergence score — the deliverable, re-graded

Count how many of {$TICK on move's side, $VIX 5-min slope with the move,
$ADD 10-min slope with the move} currently confirm:

| Score | n minutes | P(extends ≥2 pts in next 15 min) |
|---|---|---|
| 0/3 | 273 | **25.3 %** |
| 1/3 | 417 | 48.9 % |
| 2/3 | 510 | 65.5 % |
| 3/3 | 529 | **73.3 %** |

Monotone, base rate 57.1 %, combined AUC .680. Through the gate: raw .690,
**residual .607, residual day-median .572**, trivial baseline **.822**. So the
score itself does keep a little independent signal — its day-median residual
clears the coin-flip band by .022, which is the thinnest "survives" in the
table — while grading the label materially *worse* than the clock-plus-geometry
competitor. Two of its three legs are the two that fail the residual test.

In plain words, revised: **the ladder is real but it is mostly a proximity
ladder.** All-three-confirming is strongly associated with price sitting near
its own extreme early in a move, which is where continuation is common for
reasons that have nothing to do with internals. Do not read 73 % as "the
internals say 73 %."

## Day-level: the one-sidedness trace Steve intuited

| Day metric over the move's span | vs move size | Note |
|---|---|---|
| **VIX net travel × (−dir)** | **ρ +0.85, and positive 22/22 days** | VIX rose during *every* down move and fell during *every* up move in July — no exceptions — and how far it traveled ranks the move's size almost perfectly. |
| $TICK sign-share | ρ +0.35 | Weaker than expected; two decent moves ran with TICK mostly on the wrong side (07-15, 07-22 — grinders). |
| $VOLD end level × dir | ρ +0.19 | Not a size grader. |

Honesty note: VIX moving inverse to SPX is mechanically expected; the
non-obvious, usable parts are (a) the *graded magnitude* (ρ +0.85 with move
size), and (b) the minute-level *flattening at exhaustion* (TERM median
slope ≈ 0 while CONT stays positive).

## Backtest-event cut (the re-entry decision point)

At the 443 matched 2-pt backtest events, only **10–11 failed to resume** —
too few for any trace to filter (all AUCs .35–.63 on n≈10). Practical
consequence: **at 2-pt backtests inside a live morning move, no filter is
needed; re-entry is justified by the base rate alone** (96 % resume,
st-gzwb). The one whisper: failed events ran hotter volume (pace 1.11 vs
0.95), consistent with climax-heat (st-u05) — n far too small to act on.

The 96 % resume rate this leans on is st-gzwb's, and the 2026-08-04 audit
(§1.2) disputes how it was computed. Read "no filter needed" as "no *trace*
filters it", not "re-entry is free", until
`docs/measurement/morning-flush-anatomy.md` settles it.

## What the residual gate changed (2026-08-04, st-4cgo)

The 2026-08-04 cold-context audit found that the residual test invented for
the VIX trace had been run on VIX (st-40fv), run again on VVIX (st-lru8), and
then dropped — so **$TICK, the top-ranked trace and half the live meter, was
published untested and fails it** (§2.3/§5.3). Three changes landed:

1. **`scripts/measurement/residual_gate.py`** — one function returns raw AUC,
   residual AUC, day-median residual AUC and the trivial clock+geometry
   baseline, or raises. There is no way through it to a raw AUC alone. Its
   `__main__` runs a self-test that asserts the gate refuses empty input, thin
   samples, too few days, missing covariates, a constant ES move and one-class
   labels, and that a synthetic pure-costume trace grades .70 raw / .51
   residual while a synthetic independent one keeps its residual.
2. **§3.5 truncation fix.** `LAST_LABELED` was 10:15, computed as 10:30 − 15
   min. Bars stop at 10:29, so the 10:15 minute saw 14 forward minutes, not 15.
   It is now derived (`last_fully_labeled(W_END, LOOKAHEAD_MIN)` → 10:14).
   **1,882 → 1,860 labeled minutes**, 22 dropped (one per day), base rate
   56.9 % → 57.1 %. No shared minute changed label.
3. **§3.6 new-extreme detector fix.** The flag guarded on the *outer* minute
   index inside a comprehension over the 5-minute window and looked the
   previous minute up with `minutes[max(0, minutes.index(mm) - 1)]`, which
   resolves to `mm` itself at the start of the series — so the move's own first
   bar could never register as a new extreme. It is now a precomputed per-minute
   flag. Effect, measured on identical rows: eligible minutes 872 → 881,
   conditioned divergence 320 → 322 minutes (0.738 → 0.739), with-move 552 →
   559 (0.777 → 0.780). The unconditioned flag rate moved 22.2 % → 22.4 % CONT,
   10.5 % → 10.5 % TERM. **No published conclusion moves.**

**Parity with the auditor's §2.3.** Run against the pre-fix 1,882-minute
sample, the gate reproduces every residual figure he reported: $VIX .520 →
.522, $TICK .606 pooled / .507 day-median → .606 / .502, $VOLD .592 / .530 →
.593 / .530, ES delta .409 → .407, $ADD day-median .598 → .597 — maximum
deviation .005, all of it the leave-one-day-out fit this gate uses (the
program's st-40fv convention) against his pooled one; a pooled fit here returns
.520 / .606 / .507 / .592 / .409 / .598, exact on all six. On the corrected
1,860-minute sample the published numbers are $VIX **.525**, $TICK **.609 /
.510**, $VOLD **.594 / .529**, ES delta **.405**, $ADD **.603** — the drift is
the 22 dropped minutes, not a difference in method.

## Caveats

- 22 days, minutes clustered within days; aggregate AUCs flatter than per-day
  medians for some traces. No out-of-sample exists — internals capture begins
  2026-06-18. Every added corpus day extends this for free.
- Internals are 1-min candles read at close: up to 59 s stale vs the tape.
- Label parameters (≥2 pts within 15 min) chosen once, not swept.
- $VIX candles carry v=0 (index); price fields only.
- **Every trace and the score sit below the trivial clock+geometry baseline**
  (.79–.82 pooled, .91 day-median). Nothing in this document is established as
  better than "how long has this been running, and how close is price to its
  own extreme."
- The residual is taken against the concurrent 5-min ES move only. A trace
  could still be a costume for something else the trader can already see
  (session clock, prior-day levels, overnight range) — those are not in the
  gate's baseline.
- The gate's rows exclude the first five minutes of each move, where the
  concurrent ES move is not measurable on the move's own bar series.

## VIX depth pass (2026-08-03, later the same session — st-40fv)

Steve pushed past rising/falling: de-seasoned slope, beta residual, quadrant
flags, term structure. Script: `scripts/measurement/morning_flush_vix_depth.py`
(joins the labeled minutes from `morning_flush_continuation.json`; parity
asserted). Capture: **$VIX9D and $VIX3M both serve** via Schwab minute history
and are now in `corpus_pull_internals.py`; 30 days backfilled, zero rows lost.

> **Stale as of 2026-08-04.** Every number in this section and the VVIX section
> below was computed on the pre-correction **1,882**-minute sample. The §3.5
> truncation fix moved the sample to 1,860, and `morning_flush_vix_depth.py` /
> `morning_flush_vvix.py` have not been re-run against it. Expect third-decimal
> drift in the AUCs and single-digit drift in the quadrant `n`s; the
> reproduction below of the ES-vs-ES+VIX comparison *was* run on the corrected
> sample and is the number to trust where the two disagree.

**The honest headline is a negative result.** The 5-min coupling fit is
ΔVIX = −0.005 − 1.55·ΔES% with **R² = 0.79** — four-fifths of VIX slope
variance is the concurrent ES move, mechanically. Subtract it and the
**beta residual grades continuation at AUC 0.522 (day-median 0.463) — a coin
flip.** So yesterday's "VIX still traveling with the move" trace (AUC .660)
was substantially *price momentum wearing a VIX costume*, not independent
protection-demand information. The continuation meter still works — but its
VIX leg should be understood as a smoothed momentum proxy, not vol
intelligence. De-seasoning, likewise, changes nothing at this granularity
(AUC .667 vs .660 raw; the intraday decay is real at day scale but too slow
to matter inside a 5-minute slope).

**The quadrants are the keeper.** sign(ΔES_5m) × sign(ΔVIX_5m), split by
move direction, P(extends ≥2 pts in next 15 min):

| Context | Quadrant | n | P(CONT) | Read |
|---|---|---|---|---|
| Down move | ES− / VIX+ (flush, vol bid) | 501 | **73.1 %** | The freight train. |
| Down move | **ES+ / VIX+ (bounce, vol STILL bid)** | 38 | **65.8 %** | **The bounce isn't believed** — protection still being paid for while price lifts; flush tends to resume. The spot-up-vol-up read, working exactly as doctrine says. |
| Down move | ES− / VIX− (monetization?) | 58 | 63.8 % | **The monetization/exhaustion read FAILS** — predicted fuel-gone, measured mildly *elevated* continuation. |
| Down move | ES+ / VIX− (bounce, vol crush) | 335 | 45.1 % | The only sub-base state in a down move. |
| Up move | ES+ / VIX− (rally, vol crush) | 446 | 62.6 % | Healthy up. |
| Up move | **ES− / VIX+ (dip, vol bid)** | 274 | **33.6 %** | Dip with protection bid — the up-move's death rattle. |
| Up move | ES+ / VIX+ (spot-up-vol-up) | 38 | 52.6 % | Classic suspicion read: directionally right (down from 62.6 %), mild, thin n. |
| Up move | ES− / VIX− | 58 | 44.8 % | — |

The asymmetry is the finding: **within down moves, VIX+ keeps continuation
elevated no matter what price is doing this minute (73 %, 66 %); within up
moves, VIX+ anywhere is the warning state (34 %, 53 %).** Both anomalous
quadrants run n = 38 — flagged, not validated.

### What the VIX leg of a quadrant actually adds (2026-08-04, §2.4)

Split first on the ES sign alone, then add VIX. Regenerated on the corrected
1,860-minute sample (`morning_flush_continuation.json` →
`vix_lift_over_es_sign`; 1,639 minutes carry a non-zero 5-min move in both):

| context | ES sign alone | n | + VIX confirming | + VIX against | z (confirming vs ES alone) |
|---|---|---|---|---|---|
| down move, ES with the move | **.718** | 531 | **.729** (n=476) | .618 (n=55) | 0.39, p .70 |
| down move, ES against | .443 | 348 | .629 (n=35) | .422 (n=313) | 2.10, p .035 |
| up move, ES with the move | .602 | 457 | .611 (n=422) | .486 (n=35) | 0.27, p .79 |
| up move, ES against | .304 | 303 | .418 (n=55) | .278 (n=248) | 1.67, p .096 |

**The headline state is the ES sign in costume.** "Flush running, vol bid" at
72.9 % is statistically indistinguishable from "ES ticked down in the last five
minutes" at 71.8 % — a 1.1-point difference on n = 476, z = 0.39. The same
holds for the healthy-up cell (61.1 % vs 60.2 %). VIX adds 12–19 points **only**
in the cells of n = 35–55 — and those are exactly the named reads the live meter
displays: "bounce NOT believed", "dip with protection bid". The z-values there
(2.10 and 1.67) are naive: no clustering correction, no correction for the eight
cells inspected, and the cells were chosen after seeing them. Treat them as
hypotheses with 35–55 supporting minutes, not as measured edges.

This does not retract the *asymmetry* finding — VIX+ behaving oppositely inside
down and up moves is visible in the well-populated cells too. It retracts the
implied precision of the headline percentages.

**Term structure:** as a 5-min slope, no upgrade (AUC .631). At day scale it
tells a July story: the 9D−30D spread sat at −3.4 to −1.9 (deep contango)
early July, compressed toward flat through the late-July flush cluster, and
**inverted intraday on 07-23 (+0.13) and 07-27 (+0.37) — the 68-pt and 91-pt
days** — with 07-28 touching 0.00. But 07-31 (87.75 pts) ran at −2.4, so
front-end stress is descriptive of the late-July regime, not a per-day size
grader. Now captured daily; worth rechecking at n ≥ 60 days.

**Re-scored convergence** (de-seasoned slope swapped in): 24.9 / 48.2 / 64.9
/ **73.6 %**, AUC .683 — marginal over the original .678. The trio's value
survives; its members are correlated with each other, and honesty requires
saying the meter is closer to "three views of one underlying state" than
three independent confirmations.

## VVIX pass (2026-08-03, third pass same session — st-lru8)

VVIX = implied vol of ~30-day VIX options — the quoted price of crash-tail
convexity, one derivative beyond VIX. **$VVIX serves and is now captured**
(30 days backfilled, zero rows lost; symbol roster is 8). July morning range:
86.3–107.7 — no stress episode in-window. Script:
`scripts/measurement/morning_flush_vvix.py` (joins the same labeled minutes,
parity asserted; the numbers below are the pre-correction 1,882-minute run —
see the staleness note in the VIX depth section).

**Coupling:** ΔVVIX_5m = 0.02 + 2.15·ΔVIX_5m, **R² = 0.53** — only half of
VVIX's minute movement is the VIX print (vs 0.79 for VIX-on-ES). The other
half is its own animal — but that half carries no continuation signal:
**residual AUC 0.532 (day-median 0.479), the same coin-flip verdict** the
VIX residual earned. At 5-minute granularity inside a morning move,
vol-of-vol adds nothing beyond the VIX print as a continuous signal.

**VVIX/VIX ratio slope comes out INVERTED** (AUC 0.375 as naively oriented
⇒ 0.625 flipped): the ratio *compressing* accompanies continuation. Largely
mechanical — in percentage terms VIX moves far more than VVIX during a
flush, so sustained moves compress the ratio. Do not trade the naive
"ratio rising = tails bid = bearish" read intraday.

**The VIX × VVIX quadrants are where VVIX earns its seat:**

| Context | State of the vol complex | n | P(CONT) |
|---|---|---|---|
| Down move | VIX+ / VVIX+ (complex bid) | 466 | **73.8 %** |
| Down move | VIX+ / VVIX− | 74 | 63.5 % |
| Down move | VIX− / VVIX+ | 112 | 54.5 % |
| Down move | **VIX− / VVIX− (complex releasing)** | 293 | **46.8 %** |
| Up move | **VIX+ / VVIX+ (complex bid AGAINST the rally)** | 220 | **30.9 %** |
| Up move | VIX+ / VVIX− | 72 | 48.6 % |
| Up move | VIX− / VVIX+ | 78 | 48.7 % |
| Up move | VIX− / VVIX− (complex releasing) | 388 | 65.7 % |

The §2.4 caveat above applies here too, with one difference in this table's
favour: these cells are better populated (220–466 in the load-bearing ones,
72–112 in the thin ones), so the vol-complex reads are less exposed to the
n = 35–55 problem than the ES × VIX quadrants. They have not been compared
against the bare ES sign, though — that comparison exists only for the VIX
quadrants, and the honest expectation is that some of this is the same
mechanism.

Plain words: **when the whole vol complex agrees with the move, it
continues (74 % / 66 %); when the whole complex leans against it, it dies.**
The up-move death rattle sharpens to **30.9 % on n = 220** — the strongest
single warning state measured today, and better-sampled than the ES-quadrant
version (33.6 %, n = 274). And unlike the failed ES-side monetization read,
the *both-releasing* state during a down move genuinely weakens continuation
(46.8 % vs 57 % base) — the vol complex letting go IS the fuel-gone signal,
you just have to read it in vol space, not price space.

**What this does NOT test:** the practitioner (DonK-style) early-warning use
of VVIX is day-to-regime scale — VVIX firming for days while VIX sleeps,
absolute levels pushing 110–120+. July's window never left calm territory
and 22 days can't span regimes. That read stays open, and the capture now
feeds it a day per session.

## Follow-on lane — BUILT 2026-08-03 (Meter Goes Live, st-byrg)

The live **continuation meter** runs in the `meter` window of steves-desk
(`tmux -L moocity attach -t steves-desk`, window: meter), refreshing every
30 s from Schwab minute history: primary-move-so-far, the trace marks, the
score with its measured mapping, and the named quadrant states (death
rattle, fuel gone, bounce-not-believed, dip-with-protection-bid). Display
only — no orders, no FD0 coupling; the human stays the trigger.

    .venv/bin/python3 scripts/desk/continuation_meter.py [--once] [--interval N]

Operational notes, learned on first live run: **$ADD/$VOLD publish a session
late** on the minute-history endpoint, so live mornings run the two-trace
score (TICK+VIX: 33/57/74 %, measured on the same minutes — barely worse
than the three-trace 25/…/73 %); a >3-min-stale feed puts a loud STALE
banner on every number; each frame journals to
`data/exec/continuation-meter-<day>.jsonl` so the meter's own calls can be
scored later. Schwab token wall (st-ndc) takes the feed down when it hits —
the meter degrades to feed-error lines, not silence.

> **Read this section against the gate table above.** The live two-trace score
> runs on $TICK (residual day-median .510) and $VIX (.499) — the two traces
> that fail the residual test — and drops $ADD (.603), the one that passes.
> The trace the meter cannot read is the trace carrying the information. That
> is the auditor's §2.3 headline and it is a statement about what the meter's
> percentages mean, not about whether the code works.
