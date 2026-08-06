# Retro Gamma Cut — Recognizer Confirms × Dealer Gamma Regime

**Bead:** st-trbn (Retro Gamma Cut) · 2026-08-06
**Inputs:** `data/measurement/acuity-run2-confirmations.jsonl` (run `20260727T054148Z`)
× `Z:\Harvest\gexbot-hist\<date>\classic_gex_zero.json.gz`
**Code:** `scripts/measurement/retro_gamma_cut.py`
**Joined table:** `data/measurement/retro-gamma-cut-joined.jsonl` (141 rows)
**Baseline:** recognizer acuity run 2 (st-n62) — 353 confirms / 62 days,
first-touch ±5 @ 30 min = **47%**; hindsight day-shape spread **65 / 47 / 32** (P / D / b).

## The question and the short answer

Steve's question was "how much better would the recognizer be with GexBot data."
The measurable version: does the dealer-gamma regime at the confirm minute
separate winning confirms from losing ones?

**Answer: directionally yes, and not decision-grade.** Bullish confirms taken in
**positive gamma** won 56% (18W/14L) against 38% (39W/64L) in **negative gamma** —
an 18-point gap. The gap survives stratification by hour, but **it disappears
entirely inside the D-day stratum** (43% vs 44%, the largest and cleanest
stratum), which means a large part of it is the run-2 day-shape finding wearing
a different label. No single regime cell clears a decision-grade bar at the
observed n.

The more durable finding is **not** the win rate. It is the excursion asymmetry:
positive-gamma confirms ran a median MFE/MAE of **15.75 / 5.25** points with
**70%** MFE > MAE, against **7.75 / 8.25** and **46%** in negative gamma. Run 2
warned that ±5 symmetric grading understates fat-MFE confirms; this is that
warning showing up as a measurement. For an asymmetric fly payoff the excursion
gap is worth more than the win-rate gap, and it is the cut most worth
re-measuring with a matched target/stop.

## Method

### Population — which 353, and why only 141 survive

`acuity-run2-confirmations.jsonl` is append-only and holds **1,639 rows across
five runs**. Run 2's published doc reports 353 confirms / 62 days; that is run id
**`20260727T054148Z`**, which contains exactly 353 rows. That run is the study
population. The other four run blocks (17 + 423 × 3) are not part of the
published baseline and are excluded.

| Stage | Confirms | Days |
|---|---|---|
| Run 2 population (`20260727T054148Z`) | 353 | 62 |
| Falls inside the GexBot archive window | **141** | **14** |
| Dropped — day not in the archive | 212 | 48 |
| Dropped — no snapshot inside the confirm minute | 0 | — |
| Dropped — flip level unpopulated at the confirm | 0 | — |
| **Joined** | **141** | **14** |

The 212-confirm drop is the dominant limitation of this study and it is
structural, not fixable: the acuity corpus runs back to **2025-05-29**, while
GexBot `/hist` is a **90-day rolling window** that our archive first captured on
2026-05-07. Only 14 of run 2's 62 confirm-days overlap. Two are in May
(05-19, 05-21) and twelve are in July (07-01 → 07-24); the corpus contributed no
confirm-days in June that also survive in the archive, and none after 07-24.

Nothing was dropped at the join itself. Every one of the 141 in-window confirms
found a snapshot, and every one had a populated flip level.

### Join and tolerance

Confirms carry a CT wall-clock minute (`ct`, `HH:MM`), not a second. The join
takes the **last snapshot at or before the end of that minute**, and requires it
to fall inside the minute — the window is `[mm:00, mm:59]`, 60 seconds, with no
fill from a neighbouring minute.

The tolerance turned out to be nearly free: **the chosen snapshot was 0 seconds
from the end of the confirm minute in 115 of 141 cases and 1 second in the other
26** (max lag 1s). The archive's ~1-per-second cadence removes the timestamp-slop
objection completely; this is effectively a join at the confirm second.

The `regime_t_minus_5` block repeats the same procedure 5 minutes earlier.
**4 of 141** have no t−5 regime because the confirm sits in the first five
minutes of RTH and the feed does not start until 08:30:0x. Those 4 are retained
with a null lookback and appear as `unknown` in the flip-crossing table.

### Regime source — which package, and why

`zero_gamma` is read from the **classic** package (`classic_gex_zero.json.gz`).
This is the schema landmine documented in
`docs/gexbot/quant-dataset-survey-2026-08-06.md`: the **state** package writes 0
into `zero_gamma` for the entire session, so a state-sourced join would have
silently produced a null regime for every confirm. Classic is also the
methodological control (unsigned volume) rather than the signed-positioning
variant, which is the conservative choice for a first cut.

Verified on the 2026-07-15 file before joining: 17,844 snapshots, `zero_gamma`
and both volume walls populated in all but the single 08:30:02 opening snapshot,
which is the one snapshot per day the survey also found zero.

Files are plain JSON despite the `.json.gz` names (st-kr4a); the reader opens
them as text.

### Instrument note

Confirms are graded on **ES** prices (anchor/entry ~7585); GexBot `spot` is
**SPX** (~7571 at the same moment — the difference is ES basis, not an error).
Every regime feature is computed **entirely within SPX space** (spot vs
zero_gamma, spot vs walls), so no cross-instrument conversion is performed and
none is needed. The ES/SPX basis would only matter if a regime level were
compared against an ES price, which nothing here does.

### Features

- **gamma sign** — `spot − zero_gamma ≥ 0` → positive regime, else negative.
- **distance to flip** — `spot − zero_gamma` in SPX points, binned
  `≤−30 / −30..−10 / −10..0 / 0..+10 / +10..+30 / >+30`. Rationale for the ±10
  inner band: the grading target is ±5 ES points, so within ±10 of the flip the
  entire graded excursion lives on top of the flip level; 10–30 is the working
  band; beyond 30 the flip is not a near-term factor.
- **wall position** — spot against `major_pos_vol` and `major_neg_vol`
  (volume-based majors, per the bead spec): `above_pos_wall` / `between_walls` /
  `below_neg_wall`, plus `inverted_walls` when the negative wall sits above the
  positive one (1 confirm), which is kept separate rather than folded into an
  ordered cell where it would have no directional meaning.
- **distance to nearest wall** — signed distances to both walls, plus which is
  nearer and the absolute distance.
- **t−5 repeat** of all of the above, and `flip_crossed_into_confirm`.

### Grading and intervals

Grading is run 2's, unchanged: first-touch ±5 ES points, win = +5 prints before
−5, measured over 30 minutes (`verdict30`, primary) and 15 minutes (`verdict15`,
secondary). Win rates are computed over **decided** confirms only — undecided
(`neither`) confirms are excluded from the denominator, matching run 2's
149W/169L/35-undecided convention.

- **Intervals: Wilson score, 95%.** Wilson rather than normal-approximation
  because several cells have n < 30 and proportions near the boundary.
- **p-values against the 47% baseline: exact two-sided binomial** (method of
  small probabilities). No scipy in this venv; both the binomial and the Fisher
  test are computed in closed form from `math.comb`.
- **Positive vs negative comparison: Fisher exact two-sided**, plus a
  **day-clustered bootstrap** (see below).
- **n threshold: 30 decided confirms.** At or above it a cell is labelled
  `inference`; below it, `directional-only`. This is a conventional floor, and
  it is deliberately generous — see the decision-grade section for why even the
  cells that clear it are not decision-grade.

## Results — `verdict30` (primary)

Overall on the joined subset: **42%** (57W/78L, 6 undecided), Wilson
[34%, 51%], p vs 47% = 0.301. The joined 14-day slice is a little worse than the
full corpus but not distinguishably so; it is not a representative sample of the
62 days and should not be read as a revision of the 47% baseline.

### Gamma sign

| cell | n | W/L | win% | Wilson 95% CI | p vs 47% | grade |
|---|---|---|---|---|---|---|
| positive | 32 | 18/14 | **56%** | [39%, 72%] | 0.376 | inference |
| negative | 103 | 39/64 | **38%** | [29%, 48%] | 0.075 | inference |

### Distance to flip (SPX points, spot − zero_gamma)

| cell | n | W/L | win% | Wilson 95% CI | p vs 47% | grade |
|---|---|---|---|---|---|---|
| ≤ −30 | 6 | 5/1 | 83% | [44%, 97%] | 0.106 | directional-only |
| −30..−10 | 49 | 19/30 | 39% | [26%, 53%] | 0.257 | inference |
| **−10..0** | 49 | 16/33 | **33%** | [21%, 47%] | **0.046** | inference |
| 0..+10 | 27 | 15/12 | 56% | [37%, 72%] | 0.442 | directional-only |
| +10..+30 | 4 | 2/2 | 50% | [15%, 85%] | 1.000 | directional-only |
| > +30 | 0 | — | — | — | — | no confirms |

The `−10..0` cell — spot sitting just **below** the flip — is the only cell in
the study whose p-value against the 47% baseline clears 0.05 (p = 0.046,
p = 0.030 at 15 min). Read it with the multiplicity caveat below: this is one
cell out of roughly two dozen tested, and one cell at p ≈ 0.05 out of two dozen
is what chance produces.

### Position vs volume walls

| cell | n | W/L | win% | Wilson 95% CI | p vs 47% | grade |
|---|---|---|---|---|---|---|
| above_pos_wall | 0 | — | — | — | — | no confirms |
| between_walls | 116 | 49/67 | 42% | [34%, 51%] | 0.308 | inference |
| below_neg_wall | 18 | 7/11 | 39% | [20%, 61%] | 0.638 | directional-only |
| inverted_walls | 1 | 1/0 | 100% | [21%, 100%] | 0.470 | directional-only |

**Wall position carries no signal here, and the cell structure explains why.**
Every run-2 recognition is bullish-biased off a support anchor, so spot is
essentially never above the positive wall — that cell is empty, and 116 of 141
confirms land in the single `between_walls` bucket. Wall position as defined
does not partition this corpus. A useful wall cut needs a different feature
(distance to the wall the trade is heading *into*, or wall-strength), not this
three-way position label.

### Distance to nearest volume wall (absolute SPX points)

| cell | n | W/L | win% | Wilson 95% CI | p vs 47% | grade |
|---|---|---|---|---|---|---|
| ≤10 | 78 | 36/42 | 46% | [36%, 57%] | 0.910 | inference |
| 10–30 | 56 | 21/35 | 38% | [26%, 51%] | 0.181 | inference |
| >30 | 1 | 0/1 | 0% | [0%, 79%] | 1.000 | directional-only |

### Setup type × gamma sign

| cell | n | W/L | win% | Wilson 95% CI | p vs 47% | grade |
|---|---|---|---|---|---|---|
| failed_breakdown / negative | 79 | 32/47 | 41% | [30%, 52%] | 0.261 | inference |
| failed_breakdown / positive | 29 | 15/14 | 52% | [34%, 69%] | 0.711 | directional-only |
| level_reclaim / negative | 24 | 7/17 | 29% | [15%, 49%] | 0.101 | directional-only |
| level_reclaim / positive | 3 | 3/0 | 100% | [44%, 100%] | 0.104 | directional-only |

`failed_breakdown` is the only setup with usable n on both sides of the gamma
split, and there the gap narrows to 11 points (52% vs 41%) from the 18-point
aggregate. `level_reclaim` in positive gamma is 3 confirms; the 100% is noise and
is shown only so the cell is not silently dropped.

### Regime shift into the confirm (the cheap second cut)

| cell | n | W/L | win% | Wilson 95% CI | p vs 47% | grade |
|---|---|---|---|---|---|---|
| crossed | 25 | 10/15 | 40% | [23%, 59%] | 0.551 | directional-only |
| no cross | 106 | 45/61 | 42% | [33%, 52%] | 0.382 | inference |
| unknown | 4 | 2/2 | 50% | [15%, 85%] | 1.000 | directional-only |

**Nothing here.** Whether price crossed the flip in the five minutes into the
confirm makes no difference (40% vs 42%). Reported per the brief's instruction to
show it only if it showed something — it did not, and that is worth recording so
the cut is not re-run.

### Excursion @ 30 min — the finding that does not depend on ±5

| cell | n | med MFE | med MAE | MFE > MAE |
|---|---|---|---|---|
| all hours · positive | 33 | **15.75** | **5.25** | **70%** |
| all hours · negative | 108 | 7.75 | 8.25 | 46% |
| 08–09 · positive | 25 | 19.25 | 6.25 | 72% |
| 08–09 · negative | 32 | 8.75 | 10.62 | 41% |
| 10–14 · positive | 8 | 5.50 | 2.12 | 62% |
| 10–14 · negative | 76 | 6.25 | 6.62 | 49% |

Positive-gamma confirms carried roughly **three points of MFE for every point of
MAE**; negative-gamma confirms carried less MFE than MAE. Run 2's corpus-wide
edge-dominance figure was 50%; positive gamma is 70% and negative is 46%. Note
that most of the positive-gamma sample sits in the 08–09 band, where run 2
already documented outsized excursion in both directions — but the *asymmetry*
(72% vs 41% within that same band) is not an hour effect, because both sides of
that comparison are drawn from the same hours.

## Confound controls

The aggregate gamma-sign gap only means something if it survives the two things
run 2 already showed drive outcomes: hour of day and day shape.

**Unstratified 2×2:** positive 18W/14L vs negative 39W/64L — Fisher exact
two-sided **p = 0.100**. That test assumes the 141 confirms are independent draws,
which they are not.

**Day-clustered bootstrap** (20,000 resamples of the 14 days, resampling whole
days because confirms cluster hard inside them): point estimate **+18.4 points**,
median +18.9, 95% CI **[+1.2, +48.0]**, with **1.7%** of resamples at or below
zero. The interval excludes zero, barely, and it is very wide — a plausible
world in this data has positive gamma worth 1 point or 48.

The two disagree in the conventional direction of "borderline", and neither is
strong. Treat the honest reading as: the gap is more likely real than not, and
the data cannot size it.

| stratum | positive W/n | positive win% | negative W/n | negative win% |
|---|---|---|---|---|
| hour 08–09 | 13/25 | 52% | 8/32 | **25%** |
| hour 10–14 | 5/7 | 71% | 31/71 | 44% |
| day_type P | 6/8 | 75% | 4/8 | 50% |
| **day_type D** | 9/21 | **43%** | 29/66 | **44%** |
| day_type b | 3/3 | 100% | 6/29 | 21% |

**This table is the most important one in the study, and it cuts against the
headline.** The gamma gap holds inside both hour bands, so it is not the open
hour in disguise. But inside the **D-day stratum — 87 decided confirms, the
largest and most balanced — the gap is exactly zero (43% vs 44%).** The
aggregate 18-point gap is produced by the P and b strata, where the positive-gamma
cells hold 8 and 3 confirms respectively.

The mechanism is visible in the composition: b-days are almost entirely negative
gamma (29 of 32 confirms), and b-days won 21%. So a meaningful share of "negative
gamma loses" is "b-days lose," which run 2 already reported at 32% without
needing GexBot at all.

**The counter-argument, which is the actual reason to keep going:** day shape is
*hindsight* — run 2 says so explicitly, and building a developing-shape
classifier is its top recommendation. Gamma sign is **knowable in real time, at
the confirm second**. If gamma sign is even a partial live proxy for the
hindsight-only day-shape signal, that is worth more than an independent signal of
the same size. This study cannot establish that it is; it can only say the
overlap is real and the residual is unmeasured at this n.

### Per-day composition — where the precision actually goes

| day | day_type | confirms | positive-gamma frac | W/decided |
|---|---|---|---|---|
| 2026-05-19 | D | 3 | 0.33 | 0/2 |
| 2026-05-21 | P | 2 | 1.00 | 2/2 |
| 2026-07-01 | P | 2 | 0.50 | 2/2 |
| 2026-07-02 | b | 5 | 0.00 | 1/5 |
| 2026-07-07 | P | 3 | 0.67 | 1/3 |
| 2026-07-10 | P | 6 | 0.00 | 3/6 |
| 2026-07-13 | b | 18 | 0.06 | 5/18 |
| 2026-07-14 | P | 3 | 1.00 | 2/3 |
| 2026-07-15 | D | 9 | 0.00 | 5/9 |
| 2026-07-16 | D | 23 | 0.35 | 6/23 |
| 2026-07-20 | D | 21 | 0.00 | 6/16 |
| 2026-07-22 | D | 8 | 0.75 | 5/8 |
| 2026-07-23 | D | 29 | 0.24 | 16/29 |
| 2026-07-24 | b | 9 | 0.22 | 3/9 |

Four days supply 91 of the 141 confirms. **21 of the 33 positive-gamma confirms
come from just three days** (07-16 × 8, 07-23 × 7, 07-22 × 6). Gamma regime is
strongly day-level: four of the fourteen days (07-02, 07-10, 07-15, 07-20)
produced **zero** positive-gamma confirms.
The Wilson intervals in the tables above treat confirms as independent and are
therefore **optimistic**; the day-clustered bootstrap is the interval to trust,
and its effective sample size is closer to 14 than to 141.

## Are any cells decision-grade?

**No. Not one cell in this study is decision-grade, including the cells labelled
`inference`.** The `inference` / `directional-only` label marks whether a cell
cleared the n ≥ 30 floor; clearing that floor is necessary, not sufficient, and
four things independently block the stronger claim:

1. **Effective sample size is days, not confirms.** 141 confirms over 14 days,
   with regime strongly day-level and three days supplying most of the
   positive-gamma cell. The honest denominator for a day-level regime feature is
   ~14.
2. **The day-clustered interval is uninformative for sizing.** [+1.2, +48.0]
   points cannot support a position-sizing or gating rule; it can only support
   "look again."
3. **Day-shape confounding is unresolved.** The gap vanishes in the D stratum.
   Until the effect is measured inside a shape stratum with real n on both sides,
   we cannot say whether gamma sign adds anything to what run 2 already knew.
4. **Multiplicity.** Twenty cells were tested against the 47% baseline at
   `verdict30`. Exactly one landed at p < 0.05 (`−10..0`, p = 0.046). One hit in
   twenty at the 5% level is precisely the yield chance produces, and no
   correction would leave it standing.

**What would make a cell decision-grade.** In rough order of leverage:

- **More overlapping days, which requires forward collection, not more archive.**
  The 212 dropped confirms are gone permanently — /hist is a 90-day rolling
  window and those days aged out before we archived. The overlap only grows
  forward. A re-cut after the recognizer runs live alongside the archive for
  ~40 more sessions would roughly triple the day count, which is the binding
  constraint.
- **Re-grade against the actual trade.** ±5 symmetric is not the fly. Run 2's
  own recommendation 5 (+8/−4 or a target/stop matched to the entry) would let
  the excursion asymmetry — the strongest signal here — express itself as a win
  rate instead of being averaged away.
- **Stratify inside developing day shape, not full-day shape.** The developing
  classifier is run 2's top recommendation for its own reasons; it is also the
  only way to ask whether gamma sign adds signal *beyond* shape without using
  lookahead on both sides.
- **Pre-register the cells.** This was an exploratory sweep. One confirmatory
  cell, named before the data is cut, is worth more than twenty-four exploratory
  ones.

## What to measure next

1. **Orderflow lead into the confirm** (st-g3yh / st-863b). The orderflow package
   is per-second DEX/GEX flow we have never consumed, and it covers all 14 of
   these days. Unlike gamma sign, it is not a slow day-level state, so it will
   not collapse to an effective n of 14 — the same 141 confirms give it far more
   independent information. This is the highest-value next cut on this corpus.
2. **Re-grade the joined table with an asymmetric target/stop.** The joined file
   already holds every regime feature; only the grading changes, and the ES tape
   is on disk. Cheap, and it targets the study's strongest signal directly.
3. **Wall features that actually partition.** Position-vs-walls failed because
   bullish-only confirms never sit above the positive wall. Try distance to the
   wall *ahead of* the trade, and wall strength (`sum_gex_vol` share at the wall
   strike) rather than wall location.
4. **State-package gamma majors as a second regime source.** This cut used
   classic's `zero_gamma`. State's `major_long_gamma` / `major_short_gamma` is the
   signed-positioning view of the same question and is a genuine methodological
   alternative, not a redundancy.
5. **Extend the archive daily through the Quant month.** Every day not archived
   before the tier decision (~Sep 1) is lost to the 90-day window, and the
   overlap problem above is the single biggest limitation of this study.

## Reproduce

```bash
cd /root/projects/Strader
.venv/bin/python scripts/measurement/retro_gamma_cut.py              # join + analyse
.venv/bin/python scripts/measurement/retro_gamma_cut.py --skip-join  # analyse only
```

The join reads 14 archive days (1.78 GB off `/mnt/z`) and takes a few minutes;
`--skip-join` reruns the tables from `retro-gamma-cut-joined.jsonl` in under a
second. The bootstrap is seeded (`seed=20260806`), so every number in this
document reproduces exactly.
