# Morning Flush Continuation Traces — Internals, VIX, Orderflow

**Bead:** Continuation Trace (st-cdwe) · discovered from Grade The Flush (st-gzwb)
**Date:** 2026-08-03 · **Script:** `scripts/measurement/morning_flush_continuation.py` → `data/measurement/morning_flush_continuation.json`
**Data:** the 22 July morning-move days (spans from `morning_flush_study.json`); internals $TICK/$TRIN/$ADD/$VOLD 1-min candles; **$VIX backfilled this session** (added to `corpus_pull_internals.py` [st-cdwe] — symbol is `$VIX`, `$VIX.X` is empty; 29 corpus days now carry it, zero rows lost in the force-rewrite, backup at `data/corpus/_internals_backup_20260803/`).

## The question

Steve, after reading the contention review: *"I'm less interested in the
statistical alignment than in finding a metric that bolsters confidence in
continuation. Market Internals or VIX for example. These moves that have been
so one-sided must be leaving some trace apart from 'it's happening more often
in the last couple of months.'"*

Answer: **they do, and it's a convergence.** Three live-readable traces — $TICK
sitting on the move's side, VIX still traveling with the move, breadth still
expanding — each separate continuing from dying minutes at AUC ≈ 0.65, and
stacked they grade continuation from 25 % to 73 %.

## Method (one paragraph)

Each minute from a move's start to 10:15 CT is labeled **CONT** if price
extended ≥ 2 pts beyond the extreme-standing-at-that-minute within the next
15 minutes, else **TERM** (last 15 min of window excluded — truncated
lookahead). 1,882 labeled minutes: 1,071 CONT / 811 TERM (base rate 56.9 %).
Every trace is causal (data through minute *t* only) and oriented so higher =
confirms the move. AUC is rank-sum P(CONT sample > TERM sample); "day med" is
the median of per-day AUCs (minutes cluster within days — the honest check).

## Minute-level trace ranking

| Trace (oriented) | AUC | day med | CONT median | TERM median | Read |
|---|---|---|---|---|---|
| **$TICK level × dir** | **.665** | .600 | **+116** | **−49** | TICK sits on the move's side while it lives; it has *already flipped sides* when the move is dying. The sign is the signal. |
| **$VIX 5-min slope × (−dir)** | **.660** | **.640** | +0.06 | −0.01 | VIX still traveling with the move = alive; VIX flattening while price stalls = done. Most day-robust trace. |
| **$ADD 10-min slope × dir** | **.653** | .574 | +41 | 0 | Breadth still expanding in the move's direction. |
| $TICK 10-min sign-share | .638 | .565 | 0.70 | 0.50 | Same story as level, slower. |
| $VOLD 10-min slope × dir | .638 | .542 | +3.58 M | +0.49 M | Volume breadth; correlated with $ADD. |
| Volume pace (5-min vs move avg) | .616 | .532 | 0.90 | 0.79 | Tape quieting marks exhaustion, weakly. |
| Wiggle-calm (backtest depth trend) | .578 | .580 | −0.0 | −1.0 | Deepening wiggles precede the end, weakly. |
| ES 5-min aggressor delta × dir | .548 | .634 | +87 | −49 | Aggregate-weak; day-robust median suggests day-mix effects. |
| $TRIN oriented | **.439** | .456 | −0.07 | 0.00 | **Dead — slightly inverted.** Do not use. |

**Delta divergence points the WRONG way.** The classic "price made a new
extreme but delta didn't" exhaustion flag fired in **22 %** of continuing
minutes vs **10.5 %** of dying ones — at this granularity it is a
*continuation* accompaniment, not a warning. A popular heuristic, refuted on
this tape.

## The convergence score — the deliverable

Count how many of {$TICK on move's side, $VIX 5-min slope with the move,
$ADD 10-min slope with the move} currently confirm:

| Score | n minutes | P(extends ≥2 pts in next 15 min) |
|---|---|---|
| 0/3 | 277 | **25.3 %** |
| 1/3 | 417 | 48.9 % |
| 2/3 | 517 | 65.2 % |
| 3/3 | 539 | **72.9 %** |

Monotone, base rate 56.9 %, combined AUC .678. In plain words: **while all
three still make the move's case, stay with it or re-enter into it; when all
three have quit, the move is over regardless of what price just did.**

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

At the 448 matched 2-pt backtest events, only **11–12 failed to resume** —
too few for any trace to filter (all AUCs .35–.59 on n=12). Practical
consequence: **at 2-pt backtests inside a live morning move, no filter is
needed; re-entry is justified by the base rate alone** (96 % resume,
st-gzwb). The one whisper: failed events ran hotter volume (pace 1.11 vs
0.95), consistent with climax-heat (st-u05) — n far too small to act on.

## Caveats

- 22 days, minutes clustered within days; aggregate AUCs flatter than per-day
  medians for some traces. No out-of-sample exists — internals capture begins
  2026-06-18. Every added corpus day extends this for free.
- Internals are 1-min candles read at close: up to 59 s stale vs the tape.
- Label parameters (≥2 pts within 15 min) chosen once, not swept.
- $VIX candles carry v=0 (index); price fields only.

## VIX depth pass (2026-08-03, later the same session — st-40fv)

Steve pushed past rising/falling: de-seasoned slope, beta residual, quadrant
flags, term structure. Script: `scripts/measurement/morning_flush_vix_depth.py`
(joins the same 1,882 labeled minutes; parity asserted). Capture: **$VIX9D and
$VIX3M both serve** via Schwab minute history and are now in
`corpus_pull_internals.py`; 30 days backfilled, zero rows lost.

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
`scripts/measurement/morning_flush_vvix.py` (same 1,882 minutes, parity
asserted).

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

## Follow-on lane

A live **continuation meter** — the three traces + score rendered in a desk
pane during the morning window — is the natural FD0/st-ug5 integration. Not
built here; it belongs with the harness work (st-apzt / st-ug5), where the
score's 25-to-73 gradient becomes the confidence input Steve asked for.
