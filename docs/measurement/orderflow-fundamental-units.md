# Fundamental Units of Orderflow — Measured Taxonomy, Draft 2

**Bead:** st-kaf · **Date:** 2026-07-28 · **Role:** taxonomy synthesis over five mining reports, revised against three adversarial verdicts (collision, counterexample, gates)
**Corpus:** 263 days · 39,482 one-minute atoms · 1,649 zigzag legs — run `20260728T123632Z` (`data/measurement/moves/atoms.jsonl`, `data/measurement/moves/moves.jsonl`)
**Cross-validation:** 353 recognizer confirmation events, run `20260727T054148Z` (17 stale `054115Z` rows excluded); ground-truth day 2026-07-22 (`data/measurement/replay/signals_2026-07-22.jsonl`)
**Rulings applied:** vocabulary derived from the tape, not legislated · grades not gates · compound-term convention (a boundary-crossing word never appears bare in a definition — always paired: `flush-leg`, `stall-stage`, `delta-flip`, never bare `flush`/`stall`/`flip`) · **new in Draft 2: the hindsight rider (§0.1) — every day-relative measurement is labeled LIVE or HINDSIGHT**
**Feeds:** `lexicon.yaml` v1 backbone · st-79z.1 CLI grammar terminals
**Conflict inventory honored:** `docs/research/2026-07-28-pa-vocabulary-consistency-review.md` — deliberate deviations from miner-proposed names are flagged in §7; the collision recheck's residual findings are resolved there.
**Revision provenance:** Draft 1 claims refuted by the adversarial recheck are withdrawn or replaced below and marked as such; every number the counterexample verifier confirmed exact is retained verbatim.

---

## 0 · Preamble: the grid is imposed, so every label carries a grade

The empirical backbone of grades-not-gates: the effort/effect grade distribution is statistically indistinguishable from a 2×2 grid laid over a smooth continuum. KS distance from the pure-continuum null is **0.027 (atoms)** and **0.072 (legs)**; Sarle bimodality 0.563/0.580 vs 0.555 uniform benchmark — no second mode, no natural valley. **20.4% of atoms and 19.3% of legs sit within grade 0.1 of the 50/50 cell boundary — roughly one classification in five is a literal coin flip** (the independence null predicts 19.0%, i.e. the coin-flip zone exists by construction).

Consequences, binding on all downstream language:

1. Say **"graded F1 at 0.62," never "is F1."** Cell membership is a coordinate on a surface, not an identity.
2. Every named unit below carries a **grade band** (§3). A `coin-flip`-band cell label is unreportable as a cell claim — report the straddled **cell pair** instead ("F3/F4 coin-flip"), computable from which axis is nearer 50. (Draft 1 called this band "boundary"; renamed — see §3.1 and §7.)
3. Every threshold in this document is a **slice of a monotone gradient where verified as such** (the V-signature's 77.5% cell sits on a smooth climb from the 46.9% base, not behind a cliff); where a split is *not* monotone, it is presented banded and says so (§2.3 confirmation-quality).

Grade formula (verified, 0/5,000 mismatches): `grade = min(|effort_pct−50|, |effect_pct−50|)/50` — Chebyshev distance to the nearest cell boundary, scaled 0–1.

**Sense discipline used throughout this document** (pending Steve's lexicon ruling round): the four ratified stages are written `flush-stage`, `stall-stage`, `flip-stage`, `confirm-stage`; a recognizer-emitted signal is a **confirmation event**; the unsigned volume axis is **effort**, the signed delta axis is **force** — they are different quantities (conflict item 6) and this taxonomy keeps them as two named axes that are never interchangeable.

### 0.1 · Hindsight rider (binding on every measurement below)

Two structural facts make almost every unit in this document a **hindsight measurement**, and Draft 1 failed to say so:

1. **All percentiles are day-relative and computable only at session close.** `effort_pct`/`effect_pct` are percentile ranks over the *completed* day's atoms (`market/orderflow/moves.py:57` "day-relative percentile, 0-100"; `:132–133` sorted over all atoms of the day; test `test_grades_are_day_relative_percentiles_with_cells`). Every F1–F4 cell, grade, band, archetype cut (effect ≥ 70/≥ 60/< 50), probe-atom count (effort_pct > 80), and confirmation-quality split (atom@0 effect_pct ≥ 80) inherits this. When §2.3 quotes effect_pct 93 at the 09:46 confirmation event, that number was not computable at 09:46.
2. **Leg structure is doubly hindsight.** The zigzag reversal threshold is REVERSAL_FRAC × the day's *final* high–low range (`moves.py:35, 148–150`), and intrinsically a pivot-atom is confirmed only after price retraces `rev` pts from the extreme. So "prior completed leg," "x min into the new up-leg," pivot-atom location, minutes-into-leg, `giveback_frac`, `pace`, and archetype membership are all unavailable at decision time as defined.

Binding consequences: the tier table (§1.0) and the archetype table (§2.1) carry a **LIVE/HINDSIGHT column**; the V-signature is re-expressed as hindsight attribution with the live trigger explicitly future work (§2.3); host-leg context stays a hindsight diagnostic (§2.3); day-type claims are final-shape attributions requiring a graded developing-shape read for live use (§2.5). The live estimator for percentiles — percentile vs a prior-N-day time-of-day distribution with a staleness grade, or a developing-day percentile — is **unratified future work**; nothing in this document defines it.

---

## 1 · Unit hierarchy

Three measured tiers plus one cross-referenced tier. Each unit's definition is operational — computable from the corpus, not descriptive prose.

### 1.0 Tier table with LIVE/HINDSIGHT status

| Tier | Fields | LIVE / HINDSIGHT |
|---|---|---|
| Atom — raw | `net`, `range`, `travel`, effort (`vol`), `force` | **LIVE** at minute close |
| Atom — graded | `effort_pct`, `effect_pct`, cell F1–F4, `grade` | **HINDSIGHT** (day-relative, session close — §0.1) |
| Leg | boundaries, `pace`, `giveback_frac`, archetype, `cells` | **HINDSIGHT** (final-range threshold + pivot-confirmation lag — §0.1) |
| Day-sequence | ordered archetype string | **HINDSIGHT** (end of session) |
| Episode | recognizer four-stage unit | **LIVE** (2,000-contract bars, emitted in real time) |

### 1.1 Atom (measured; n = 39,482)

One clock minute of tape. Fields: OHLC-derived `net`, `range`, unsigned volume (**effort**), signed delta (**force**), day-relative percentiles `effort_pct`/`effect_pct` (hindsight — §0.1), cell F1–F4, `grade`, and **travel** = |net|/range (§5). Atom cell mix: F1 34.7% / F2 16.0% / F3 22.4% / F4 26.9%. 8.0% of atoms have travel exactly 0 (open = close): flagged `doji-atom`, the natural pure-rotation marker.

### 1.2 Leg (measured; n = 1,649)

One element of the zigzag decomposition stored in `moves.jsonl`. **Ruling embedded here to avoid minting a same-phenomenon-two-words conflict: the unit is the *leg*; "move" survives only as the record/file name (`moves.jsonl`), never as a spoken unit.** (For the collision between this *leg* and the option-structure *leg* — OCC legs, multi-leg order strings — see §7: order-structure surfaces must compound to `option-leg`/`spread-leg`.)

Structure check: legs are a strict zigzag — 1,386/1,386 consecutive same-day pairs alternate direction and share exactly one boundary minute, the **pivot-atom** (leg k's last atom = leg k+1's first atom). The representation fully tiles the recognizer's territory: 353/353 confirmation events land on an exact in-leg atom, 0 outside coverage.

**Edge rows, documented:** 4 legs have `extreme_pts = 0` (flagged `zero-extreme`; `giveback_frac` is undefined there — see guard below). 19 legs (1.2%) have sign(`net_pts`) ≠ `dir` (e.g. 2026-03-25 13:55, dir up, net −7.0): direction is assigned at the extreme, so giveback past the origin can leave net against the direction label. These are flagged `sign-edge` and retained; some carry archetypes (probe-fade, absorption-stall) — any claim about such a leg carries the flag.

Median leg: 15 min, 7.25 pts net, 15 atoms, giveback 8%. Distributions (p5/p25/p50/p75/p95): minutes 3/8/15/29/80; |net| 1.5/4.0/7.25/13.5/33.9 pts. Direction balanced: 828 down / 821 up. Leg cell mix: F1 36.6 / F4 36.3 / F2 13.5 / F3 13.6 — effort and effect are strongly coupled at leg scale (r = 0.594; diagonal occupancy 72.9% vs 50% under independence), which is why off-diagonal leg labels need a higher grade bar (§3.2).

First-class leg fields ratified by this draft (all HINDSIGHT per §0.1):

| Field | Definition | Why first-class |
|---|---|---|
| `giveback_frac` | (extreme − \|net\|)/extreme, **defined only for extreme_pts > 0** (the 4 `zero-extreme` rows are excluded from all giveback statistics) | The gb≥0.30 ∧ effect<50 conjunction isolates probe-fades (7.8%); its inverse — big legs hold their extremes (flush-leg median gb 0.05) — supports fly entry at V-dump extremes (hindsight attribution; see §0.1) |
| `pace` | extreme-pts/min; empirical tercile cuts **0.38 / 0.75** | The measured spike/mid/grind-tercile boundary |
| `force-alignment` | sign(force) == direction | 75.9% overall; by effect quintile 67.9 → 71.8 → 79.0 → 81.1 → 80.3 — **rises from ~68% to ~80–81%, flattening in the top two quintiles** (Draft 1's "monotonically 67%→82%" corrected); misalignment defines the counterforce-leg |
| `archetype` + `archetype-grade` | §2.1; grade defined below | Grades not gates at leg scale |

**Archetype-grade, precise definition (Draft 1 left this underspecified):** every defining cut is re-expressed in **corpus-percentile units of its own axis** (pace cuts 0.38/0.75 are the 33.3/66.7 percentiles by construction; effect_pct is native; giveback's 0.30 cut maps to its corpus percentile). `archetype-grade = min over defining axes of |axis-percentile − cut-percentile| / 50`, scaled 0–1 — the same Chebyshev-to-nearest-cut form as the cell grade. A coin-flip-band archetype label (≤ 0.1) is unreportable bare: report the straddled **archetype pair** ("flush-leg/steady-leg"). For counterforce-leg the Draft 1 boolean sign(force) ≠ dir is replaced by the graded quantity `mis = −dir · force` expressed as a corpus percentile; the defining cut is `mis`'s zero crossing and archetype-grade uses distance from that crossing in percentile units.

### 1.3 Day-sequence (measured, derived)

The ordered archetype string of a session (a hindsight object: it requires completed legs). The archetype mix is itself a day-type read (§2.5), and the validated day decomposes correctly under the enforced classifier (§2.1): 2026-07-22 reads **flush-leg** (+28.25; archetype-grade ~0.01, coin-flip band — reportable only as the flush-leg/steady-leg pair: pace 0.792 vs the 0.75 cut, effect 70.4 vs 70) → **steady-leg** (−22.5; pace 0.562, in-window) → **leg-grind** (+31.5) → **steady-leg, off-pace flagged** (−26.0; pure-F1, pace 0.121 below the 0.38 window, effect 65.7 fails leg-grind's ≥ 70). All four force-aligned, all giveback ≤ 0.03 — the sequence narrates the day. (Draft 1's bare "grind" label on leg 4 was not an archetype name and is withdrawn.)

### 1.4 Episode (cross-referenced, NOT measured by this corpus)

The recognizer's unit of work at 2,000-contract bar resolution. **Container-word caveat:** code says `_Engagement`, drills say "instances," records say "recognitions," the coach improvised "episodes" (conflict item 7). This document uses *episode* provisionally and the choice is explicitly deferred to the lexicon ruling round — nothing below depends on which word wins.

**Resolution boundary (taxonomy axiom):** recognizer flush-stages and flip-stages are sub-minute and structurally invisible to atoms. The atom-visible signature of a four-stage episode is **stall-stage(F2) → conviction head** only; never require flush-stage representation in an atom cell string when cross-referencing (7533 validation: the 08:32/08:37/08:41 confirmation events all sit *inside* one 36-min up-leg; their flush-stage excursions to 7531.75/7532.75 appear only as single negative-net atoms).

---

## 2 · Named archetypes and motifs

### 2.1 The leg archetypes (exclusive priority cascade; steady-leg's pace clause now enforced; shares recomputed and republished)

Four axes: pace (terciles 0.38/0.75), effect_pct, giveback_frac, force-alignment. Names obey the compound-term convention; `absorption-stall` and `hollow-glide` deliberately inherit their atom-cell parent words (F2 absorption, F3 hollow) to signal lineage across taxonomy tiers.

**Cascade order (reproduces the corpus counts exactly):** flush-leg → leg-grind → counterforce-leg → probe-fade → steady-leg (pure-F1 residual, pace window **enforced**) → off-pace F1 flag → cell residuals (F2/F3/F4).

**Enforcement decision (counterexample fix):** Draft 1's steady-leg cut "residual pure-F1, pace 0.38–0.75" was not enforced — 112/297 members (38%) sat outside the pace window and the 18.0% share reproduced only with the clause dropped. Draft 2 **enforces** the window: steady-leg core is 185 legs (11.2%); the 112 off-window pure-F1 residuals stay in the steady family but carry a mandatory **off-pace flag** and are never reported as bare "steady-leg" — fast side (pace > 0.75, effect < 70) n = 40 (2.4%), slow side (pace < 0.38, effect < 70) n = 72 (4.4%). All shares below recomputed from `moves.jsonl`; they sum to 99.9% under rounding.

| Archetype | LIVE/HINDSIGHT | Share (n) | Defining cut | Median signature | Read |
|---|---|---|---|---|---|
| **flush-leg** | hindsight | 13.7% (226) | pace ≥ 0.75 ∧ effect ≥ 70 | 16.75 pts / 16 min / gb 0.05 / align 0.84 | The tradeable V-dump leg: fast, big, clean — keeps what it takes. D-day lift **0.95×** (no D enrichment — D is 79.8% of all legs; Draft 1's "76% occur on D days" framing withdrawn as an enrichment claim) |
| **steady-leg** (core) | hindsight | 11.2% (185) | residual pure-F1 ∧ pace 0.38–0.75 (enforced) | 14.5 pts / 30 min / **align 0.97** | Most force-confirmed class in the corpus; the "trust the tape" reference (core medians recomputed post-enforcement) |
| **steady-leg, off-pace** (flagged) | hindsight | 6.8% (112) | residual pure-F1, pace outside window | fast: 8.25 pts / 9 min / pace 1.14 / align 0.93 · slow: 7.6 pts / 36.5 min / pace 0.25 / align 0.92 | Same family, off the pace window; never reported without the flag |
| **leg-grind** | hindsight | 6.0% (99) | pace < 0.38 ∧ effect ≥ 70 | 15.25 pts / 66 min / eff% 89 | The trend-day crawl; 97/99 are F1; over-indexes P days (25% vs 14% base) |
| **counterforce-leg** | hindsight | 4.2% (69) | mis = −dir·force > 0 ∧ effect ≥ 60 (graded per §1.2) | 12.5 pts / 32 min / eff% 81 | The only big-leg class where delta disagrees with price; skews down 41/28 — price falls *through* net buying (trapped-buyer drops). *Renamed from miner's "squeeze-leg" — see §7* |
| **absorption-stall** | hindsight | 9.6% (159) | remaining F2 | 4.75 pts / 22 min / eff% 63 vs efc% 36 | Heavy tape, little travel |
| **hollow-glide** | hindsight | 8.2% (136) | remaining F3 | 7.75 pts / 10 min / pace 0.95 / align 0.87 | LVN-style travel on thin tape — fast and clean |
| **probe-fade** | hindsight | 7.8% (129) | gb ≥ 0.30 ∧ effect < 50 | 2.0 net vs 4.0 extreme / 9 min / gb 0.43 | Overshoot-and-retreat; splits evenly into a quiet-tape half (F4, 65) and a rejected-effort half (F2, 64) |
| **dead-drift** | hindsight | 32.4% (534) | remaining F4 | 4.0 pts / 9 min / eff% 22 | The modal leg; the noise floor. D-day lift 1.06× (≈ base) |

Every row is HINDSIGHT: archetype assignment needs a completed leg plus day-relative percentiles (§0.1). Each leg carries an **archetype-grade** (§1.2) — so a leg at pace 0.76/effect 71 reads "flush-leg, grade 0.02 (coin-flip band — report the flush-leg/steady-leg pair)," never bare "flush-leg."

Load-bearing corpus facts riding on this table:
- **Giveback is a small-leg behavior.** corr(giveback, effect_pct) = −0.11; the gb ≥ 0.30 tail is 9.0% of legs with median effect_pct 12.5; high-gb ∧ high-effect legs are 1.2%. **Once a leg has proven size, its extreme tends to hold** (flush-leg and leg-grind both median gb 0.05) — the fly-entry-at-the-extreme fact. Hindsight caveat: "proven size" is a day-relative, completed-leg measurement; the live translation is open work.
- **rth and late_day are one archetype family with a scale factor, not two taxonomies:** rth legs are ~2.9× larger (18.75 vs 6.5 pts median) and longer (33 vs 14 min) at near-identical pace (0.59 vs 0.53 pt/min). The day-relative percentile normalization already absorbs this; keep it — **noting (§0.1) that this normalization is itself hindsight, and the live estimator for it is unbuilt.**

### 2.2 Leg death modes (graded, from tail composition; now an exhaustive partition with shares)

Legs die hot, not empty. Positional cell shares (legs ≥ 4 atoms, n = 1,564): the pivot-atom is **63.0% F1**, the entry atom 60.2% F1; pre-pivot-atom tail (−3..−2) enrichment vs interior: F1 1.43×, **F2 1.36×**, F3 0.66×, F4 0.60× (Draft 1's 1.50/1.38/0.65/0.58 corrected per the adversarial recheck). Within the same leg (≥ 7 atoms), tail F2 19.7% vs head F2 16.3% (Draft 1's 21.6/17.5 corrected) while F1 is flat. Effort persists into the leg's death; what dies is effect.

Death modes are defined on **tail3** = the three atoms immediately before the pivot-atom. Draft 1 carried absorption-death as a bare set-membership bit; Draft 2 grades it and completes the partition:

| Death mode | Definition (tail3) | Share of legs ≥ 4 atoms | Read |
|---|---|---|---|
| **absorption-death** | contains ≥ 1 F2 atom; **graded**: `absorption-death-grade` = max cell-grade over tail3 F2 atoms (0 if none) | any-F2 slice **49.8%**; solid-band-or-better F2 (grade ≥ 0.3) **25.6%**; strong-band F2 (> 0.6) **7.3%** | The reversal-quality marker (§2.3). The any-F2 slice counts coin-flip-band F2 atoms; the graded slices are the honest form |
| **hot-death** | all three atoms F1 | **15.0%** (234) | Loud ending, no absorption warning |
| **quiet-death** | all three atoms F3/F4 | **15.0%** (234) | Depleted, mid-range noise ending. *Renamed from Draft 1's "fade-death" — see §7* |
| **mixed-tail** | no F2, mixed F1 + F3/F4 | **20.3%** (317) | Residual; unremarkable |

**"Pivot-atoms are loud" — taxonomy axiom:** a reversal that starts on hollow/dead atoms (F3/F4 pivot-atom, 22.4% combined) is the anomaly worth flagging, not the norm.

### 2.3 Leg-boundary motifs: the leg-boundary trap and the V-signature

All motifs in this subsection are **hindsight attributions** (§0.1): they are computed against completed legs whose boundaries require the final-day reversal threshold and the pivot-confirmation retracement.

**Leg-boundary trap** (atom scale, 630 down→up pairs, both legs ≥ 4 atoms): down-leg dies by absorption-death, new up-leg opens with a conviction head.
- Loose form (tail3 has an F2 ∧ head3 has ≥ 2 F1): 27.6% of pairs (1.19× independence). Full four-stage motif: 10.8%. **Grading caveat (gates fix):** these are binary string motifs over cells one-in-five of which are coin-flip-band; the graded overlay is `absorption-death-grade` (§2.2), and the §3.2 solid-band bar for F2/F3 *leg* claims does not apply to single-atom F2 presence here — but any Steve-facing claim about a *specific* trap instance should quote the F2 atom's grade.
- **The real signal is the conditional: P(conviction-led up-leg | absorption-death) = 0.604 vs 0.462 without — 1.31× lift. Final-shape attribution by day type: D 1.35×, b 1.85×, P 0.97× — when the final shape is P the up-leg confirms anyway (~0.71) and the stall-read attenuates to ~1.0×.** Live use requires a developing-shape read with its own confidence grade (§2.5); the taxonomy carries this as a graded attenuation, not a binary "inert on P" ruling.
- Leg-boundary-trap up-legs run better: median net +7.75 vs +7.00; full-motif right tail Q3 net 18.75 vs 12.5.
- **Long-side asymmetry:** down→up trap 27.6% vs up→down mirror 22.0%, with the fatter payoff tail on the long side — empirical support for v-down as the traded direction.

**V-signature** (episode scale, joined to legs; base win rate 46.9% of 318 decided confirmation events): prior completed leg is a down-leg with flush-stage depth ≥ 8 pts, and the confirmation event fires ≤ 3–5 min into the new up-leg.
- ≤ 3 min: **77.5% win (31/40)**; ≤ 5 min: 64.6% (42/65); robust to flush-depth threshold (−5: 66.7%, −15: 61.2%). Non-V confirmation events: 42.4%.
- **This is hindsight attribution, not entry timing.** "≤ 3 min into the new up-leg" references a leg that, at minute 3, generally does not yet exist under the decomposition's own rule (the pivot-atom confirms only after the `rev`-pt retracement, against a threshold set by the day's final range — §0.1). The **live trigger is future work, not ratified here**: sketch — a `provisional-pivot` event emitted the moment the retracement crosses the reversal threshold, carrying its own grade (distance past threshold, staleness, developing-range caveat). The 77.5% is the ceiling such a trigger would chase, not its measured hit rate.
- Anatomy behind it: winning confirmation events' prior leg was down 84.6% of the time with median net **−20.5 pts**, ending 6 min before; losers' prior leg was down only 51.5%, −4.75 pts, 13 min stale. **A real leg-boundary trap has a real flush-leg behind it.** *Join-convention note (recheck finding): the canonical join for pivot-minute confirmation events is the newest-containing leg (used by the host-leg split below); this anatomy paragraph reproduces under the oldest-containing convention — flagged, unification queued for the owned re-derivation.*
- Stored as graded fields: flush-stage depth (pts + corpus percentile), entry lag (min). The 2026-07-22 09:46 confirmation event is the textbook instance: prior down-leg −22.50 ended 1 min before, confirmation 2 min into the +31.50 up-leg, atom F1 grade 0.78, effect_pct 93 (a session-close number — §0.1), force +276.

**Host-leg context — the strongest single hindsight separator, and it stays a hindsight diagnostic:** confirmation event inside an up-leg → 66.0% win (124/188); inside a down-leg → 19.2% (25/130). MFE30/MAE30 medians 10.9/5.0 vs 3.4/11.2 pts. Holds in both cohorts (rth 62.8%, late_day 71.6%). Draft 1 promoted host-leg direction and minutes-since-leg-start to "first-class context features on every confirmation event" — **that promotion is struck**: host-leg direction is not knowable live as defined, and no live proxy is ratified here (a provisional leg direction at threshold-crossing is the obvious candidate — future work). Related state: **confirmations-into-dying-legs** — "neither" verdicts pile up near leg ends (48.6% land within 1 min of a leg end).

**Leg-boundary enrichment around confirmation events — recomputed to consistent definitions (Draft 1's 1.9× mixed two definitions and is withdrawn):** with boundary minutes = leg **start + end** minutes, 42.2% of confirmation events sit within ±3 min vs 28.8% of all atoms (11,366/39,482) — **1.47×**; with boundary minutes = **pivot-atom** minutes only, 28.0% vs 22.2% (8,744/39,482) — **1.27×** (bases recomputed under the same boundary-set convention as the numerators; adversarial recheck 2026-07-28). Enrichment alone is not sufficiency.

**Absorption placement — Draft 1 rule WITHDRAWN.** Draft 1 claimed F2 in the 3 minutes before a bullish confirmation event was a negative marker ("35.6% win, 16/45") and built a Foundation-02 placement clause on it. The adversarial recheck could not reproduce that number under any tested reading. Reproduced numbers, **re-derived by adversarial recheck; the sign of the original claim was likely inverted; Foundation-02 reconciliation deferred pending an owned re-derivation**:

| F2-in-pre-3min condition | Win rate |
|---|---|
| overall | 63/135 = **46.7%** (base-rate; corpus base 46.9%) |
| conditioned host-up | 52/78 = **66.7%** |
| early-in-up-leg (≤ 3 min) ∧ F2-pre | 18/21 = **85.7%** |

Do not encode any placement clause until the owned re-derivation ships; Foundation 02's "absorption = strongest reversal tell" stands unreconciled for now. What *does* reproduce exactly: **F3 hollow in the pre-window is negative — 37.2% vs 50.9% with a clean F1-dominant window.** Caveats carried per the gates recheck: the 3-min lookback is a single untested windowing (sensitivity unchecked), and the presence tests count ungraded atoms — quote atom grades in any instance-level claim.

**Confirmation-quality — presented banded, because it is NOT a monotone gradient (recomputed):** atom@0 effect_pct ≥ 80 → 53.8% win vs < 80 → 40.0% (both verified exact); winners' confirmation atoms are graded higher (0.49 vs 0.39) and more one-way (travel 0.611 vs 0.500). But by band: [0,20) 29.2% (n=24) · [20,40) 51.3% (n=39) · [40,60) 47.7% (n=44) · [60,80) 30.2% (n=53) · [80,100] 53.8% (n=158). The ≥ 80 slice is real; the sub-80 profile is non-monotone with the 60–80 band weakest — carried as a banded observation, not a gradient claim. Feature order matters: the early-entry constraint dominates stacking the atom filter (V-sig ≤ 5 ∧ effect ≥ 80 → 63.0%, below V-sig ≤ 3 alone).

### 2.4 Interior motif and the probe family (cross-scale, deliberate shared word)

- **micro-stall** (`121` trigram): an absorption blink inside a conviction run — 4.3% of **within-leg trigram slots** (1,613/37,570; Draft 1 said "interior," but that denominator includes leg-end trigrams — the true interior figure, excluding leg-end trigrams, is 1,352/34,380 = **3.9%**). A shallow re-test that *reconfirms without ending the leg*; this is what second/third recognizer confirmation events look like at atom scale (7533 08:37: F2 at 08:35, grade 0.84, travel 0.00 on 96th-pct effort, then a confirmation event on the second F1). Distinct from the leg-boundary trap.
- **probe-atom** (atom scale): high effort, low travel, meaningful range. **Ratified probe-grade formula (Draft 1's "e.g." dropped):** `probe-grade = min(effort_pct/100, 1 − travel, range_pct/100)` — monotone in each axis. The published population is the rectangular slice {effort_pct > 80 ∧ travel < 0.3 ∧ range ≥ 2}: **n = 1,754, ~6.7/day — explicitly a slice of the probe-grade surface, not a class.** Composition **75.3% F2 / 24.7% F1** (recomputed) — a sub-structure of the absorption corner, not a new dimension. Time signature is sharply bimodal (recomputed): **21.0%** of 08:30-bucket atoms, **9.4%** of 14:30, 1–3% midday; top ten exact minutes all 14:50–14:59 — the MOC-window effort spike.
- **probe-fade** (leg scale): §2.1 — the excursion-that-retreats at leg resolution.

The shared word **probe** is intentional and names one phenomenon at two taxonomy scales — *an excursion that doesn't hold, graded at the unit's own resolution* — with the partner word (`-atom`, `-fade`) carrying the tier. **Foundation reconciliation (collision fix, §7):** Foundation 01/03 use "probe" for the auction's outcome-*neutral* excursion testing value — a probe there can succeed. The taxonomy's probe-atom/probe-fade are the **graded failure-subset** of that auction-probe sense; where both senses can appear on one surface, the Foundation sense compounds to **auction-probe**.

Probe-atom proximity is an acuity **grade, not a gate** — block recomputed from the stated slice (Draft 1's 18.5%/9.6%/17.9% figures were irreproducible and are withdrawn):
- Confirm-centric: **37.1%** of confirmation events (131/353) have a probe-atom within ±2 min, vs **16.2%** of all atoms as base. Probe-centric: **7.4%** of probe-atoms have a confirmation event within ±2 min, vs **3.3%** of all atoms.
- **The control kills the specialness claim:** a high-effort one-way control (effort_pct > 80 ∧ travel ≥ 0.7 ∧ range ≥ 2; n = 1,845) co-locates confirm-centric at **36.3%** — statistically the same as the probe-atoms' 37.1%. The enrichment is effort-driven.
- The conditional quality edge is real and modest (recomputed): near-probe confirmation events win **51.4%** of decided (n = 109) vs **44.5%** far (n = 209); mfe30 medians **10.25 vs 6.25**, mae30 **9.0 vs 7.75**. Companion read: **the probe-atom round-trips; the confirmation atom wants to travel.**

### 2.5 Day-type priors (final-shape attributions, not live gates)

D/P/b letters are assigned from the *completed* session's profile shape. Live use requires a **developing-shape read with its own confidence grade** — e.g. "developing shape reads b at solid confidence" — and that estimator is unbuilt; until it ships, everything below is attribution for hindsight/review surfaces, and every claim is a graded attenuation, never a binary ruling.

- **b-final (trend-down) days:** biggest legs (median 14.75 pts), fewest F4-cell legs (19% vs 39% on D); strongest stall-read lift (1.85×).
- **P-final days:** leg-grind share doubles (25% vs 14% base); the stall-read attenuates to ~1.0× (0.97) — the up-leg confirms at ~0.71 regardless of the absorption-death signature.
- **D-final days:** D is **79.8% of all legs**, so absolute counts mislead. Lifts vs that base: dead-drift 1.06×, flush-leg **0.95×** — flush-legs slightly *under*-index D. Draft 1's "76% of flush-legs occur on D days" and "84% of dead-drift on D" framings are withdrawn as enrichment claims (the raw counts were true; the enrichment reading was false). The flies-friendly late-day narrative must rest on late-day timing and the leg-boundary-trap conditional, not on D-day flush-leg enrichment.

---

## 3 · Grade bands

### 3.1 The four bands (convention, honestly labeled as such)

The distribution is smeared — no natural valleys exist — so cutpoints must be convention. These are round, defensible, and roughly quartile the corpus. **Rename (collision fix): the ≤ 0.1 band is the `coin-flip` band** — Draft 1's "boundary" collided with leg-boundary trap, cell boundary, and resolution boundary inside one document, and bare `boundary` is **banned as a CLI grammar terminal** (§6.2).

| Band | Grade | Atoms | Legs | Meaning |
|---|---|---|---|---|
| **coin-flip** | ≤ 0.1 | 20.4% | 19.3% | Coin flip; the null predicts 19.0% here by construction. **Unreportable as a cell claim** — report the straddled cell pair ("F3/F4 coin-flip"), computable from which axis is nearer 50 |
| **lean** | 0.1–0.3 | 32.5% | 28.7% | Reportable with the band attached. *Flagged for the ruling round: "lean" is direction-adjacent in trader speech (directional lean/bias) — a Direction Inversion Watch risk* |
| **solid** | 0.3–0.6 | 31.3% | 29.0% | Reliable |
| **strong** | > 0.6 | 15.8% | 23.0% | Survives any reasonable reclassification |

Coin-flip confusion runs along both axes equally (effort-axis cell-pair swaps F1↔F3 + F2↔F4 = 49%; effect-axis cell-pair swaps = 51%) — neither axis is the clean one. Grade profile is invariant across coverage (late_day 0.333 vs rth 0.335 mean) — fuzziness is a property of the measurement, not the session.

### 3.2 Asymmetric bar for off-diagonal cells

All four numbers below are computed at the §3.1 strong cut, **grade > 0.6** (Draft 1's figures were computed at > 0.5 and are superseded). F1 is the only crisp cell: **27.8%** of F1 atoms are strong-band (legs **30.8%**). F3 hollow is the fuzziest: only **5.8% of F3 legs are strong-band — 13 strong-F3 legs exist in the entire corpus.** Because leg-level effort/effect correlation (r = 0.594) makes off-diagonal labels the residual of a degenerate matrix, **an F2/F3 leg claim requires solid-band (grade > 0.3) minimum, strong-band preferred.** Of all strong-band legs, **91.8%** are F1 or F4.

### 3.3 Travel sub-grades inside F1 (graded like cells, not bins)

Travel is r = 0.863 redundant with effect_pct corpus-wide, so it is **not** a free-standing third axis. Its independent information lives inside the high-effect cells: 25.9% of F1 "conviction" atoms round-trip more than half their range. Sub-grades, always written with the cell prefix, and — per the gates recheck, consistent with §5 item 4's "travel is never a binary" — each carries a **travel-cut distance** (distance to the nearer of the 0.5/0.75 cuts); within 0.1 of a cut the sub-grade is unreportable bare and the straddled pair is reported instead ("F1-drive/F1-push cut-adjacent"):

| Sub-grade | Travel | Share of F1 |
|---|---|---|
| **F1-drive** | ≥ 0.75 | 28.5% (one-way conviction) |
| **F1-push** | 0.5–0.75 | — |
| **F1-churn** | < 0.5 | 25.9% (round-trip conviction) |

Plus the corpus-wide `doji-atom` flag (travel = 0 exactly, 8.0%).

---

## 4 · Mapping onto the ratified vocabulary

### 4.1 The four stages (flush-stage → stall-stage → flip-stage → confirm-stage)

| Stage | Empirical status at atom/leg scale |
|---|---|
| **flush-stage** | **Below atom resolution as a stage** (2,000-contract bars); its *leg-scale* correlate is the flush-leg archetype (13.7%), and its depth is now a measured graded field (V-signature flush-stage depth, pts + percentile). Sub-minute flush-stages inside a leg are invisible to cells (7533 08:32–08:41) |
| **stall-stage** | **Atom-scale correlate measured** (mirroring flush-stage's phrasing — the sub-minute stall-stage itself is not measured here): the F2-in-tail3 absorption-death signature with its graded score (§2.2), any-F2 slice 49.8% of legs, carrying the 0.46 → 0.60 conditional (final-shape attribution D 1.35×/b 1.85×; attenuates to ~1.0× on P) |
| **flip-stage** | **Partially measured**: the pivot-atom is its 1-minute shadow (63% F1 — "pivot-atoms are loud"); the delta-flip itself is sub-minute. Note the recognizer ACCEPT-branch `bias` inversion (conflict item 4) remains a code fix, out of taxonomy scope |
| **confirm-stage** | **Measured**: the conviction head (`11`/`111` opens, 37.4%/22.1% of leg starts — binary string motifs, coin-flip-band caveat per §2.3); confirmation-event quality banded by atom@0 effect_pct and travel (§2.3) |

### 4.2 S1–S6 scenarios

The scenario catalog's units are **level-engagement** units; this corpus measured legs **without level context**. That caveat governs *every* row below equally — no scenario is "empirically anchored" in the level-relative sense; the strongest available status is a level-free correlate:

| Scenario | Status | Measured correlate |
|---|---|---|
| S2 failed breakdown | **level-free correlate anchored** | V-signature (77.5% ≤ 3 min, hindsight attribution) + leg-boundary trap + full four-stage motif (10.8% of down→up pairs); 2026-07-22 09:46 is the shared textbook instance |
| S4 clean break | **level-free correlate, by negation** | A flush-leg with hot-death/no absorption-death in tail — the aggression keeps getting paid; also the host-down confirmation-event graveyard (19.2% win) |
| S5 sprung trap fails | **partial level-free correlate** | Confirmations-into-dying-legs (neither-verdicts 48.6% within 1 min of leg end) + host-leg-down context |
| S6 chop straddle | **texture match only** | dead-drift archetype (32.4%) is its leg-scale texture; the level-straddle itself is unmeasured |
| S1 clean rejection | **unmeasured (level-relative)** | probe-fade is the nearest level-free texture, not an identification |
| S3 level reclaim | **unmeasured** (flush-stage-violence discrimination vs S2 requires level + sub-minute data) |

### 4.3 F1–F4 frames

**Now empirically defined** at both atom and leg tiers via day-relative effort_pct/effect_pct — with the imposed-grid caveat (§0), the hindsight rider (§0.1), and the grade-band system (§3) as mandatory riders. The drill-catalog frame table (Part II) gains: population shares, per-cell crispness (§3.2, at the > 0.6 cut), and the rule that F2/F3 leg claims need solid-band grades.

**Effort-vs-force reconciliation (conflict item 6), resolved by structure:** this taxonomy has *two* axes that never substitute — the **effort/effect matrix** (unsigned volume × price displacement → F1–F4) and the **force-alignment axis** (signed delta agreement with direction → steady-leg core's 0.97, counterforce-leg's defining misalignment). "Effort-vs-effect matrix" and "force-and-effect compass" are no longer interchangeable phrases; the lexicon entry bans the swap.

### 4.4 Still unmeasured

Level states (untouched/tested/held/broken/reclaimed), *pin*, *elevator*, GEX-anything (no GEX history in the corpus; GEXBot paused), and every level-relative scenario tell. The taxonomy does not pretend otherwise.

---

## 5 · Known limits of the 1-minute lens, and the travel-ratio mitigation

0. **The hindsight limit (see §0.1, restated here because it belongs in this list):** all percentile fields are day-relative ranks over the completed day (`moves.py` day-relative rank), and leg boundaries depend on REVERSAL_FRAC × the day's final range plus a pivot-confirmation retracement lag — **every cell, grade, band, archetype, and motif statistic in this document is a hindsight measurement.** The live estimator (prior-N-day time-of-day percentile with a staleness grade, or developing-day percentile) is unratified future work.
1. **50.6% of range-travel is invisible to net displacement** (sum|net| 52,158 pts vs sum range 105,652), stable 49.6–51.1% across every hour and day type. By cell: **F2 82.5% missed**, F4 75.4%, F1 38.1%, F3 33.9% — the lens is blindest exactly in absorption cells, the failed-breakdown territory. (Floor, not ceiling: range itself under-measures true tick path.)
2. **Sub-minute stages are invisible** (§1.4 resolution boundary).
3. **rth days decompose into mega-legs** (2026-07-22: 4 legs of 36–221 min) that hide sub-leg trap structure; leg-boundary-trap resolution lives at atom level on rth days, leg level supplies only regime/direction context. Open item: a finer zigzag scale for rth, or the explicit rule as stated.
4. **Gate failure in miniature:** the flagship 2026-07-22 08:30 flush-and-recover atom (net +2.75, range 8.25, effort_pct 99.7, F1 grade 0.892) has travel 0.333 — it *misses* a travel<0.3 gate by 0.033 while being the most extreme open bar in the corpus. Hence: **travel is a graded first-class atom axis (percentile + cut distance, §3.3), never a binary; `range` and `travel` stay on the atom schema permanently.**
5. **Mitigation — residue-expansion pattern:** 1-min atoms are the index; ticks are the drill-down. Atoms whose probe-grade crosses a review threshold get sub-minute expansion from already-collected replay tick data (217,823 trades on file for 2026-07-22). No corpus-wide sub-minute unit: probe-atom density is 9–21% of minutes at open/close but 1–3% midday — a global tier would ~triple atom count to describe structure that is ~50% redundant off-peak.

---

## 6 · What this feeds

### 6.1 lexicon.yaml v1 backbone

Each bold term above becomes an entry with `term / definition / unit-tier / owner-surface / grade-fields / banned-bare-forms / live-or-hindsight`. New terminals contributed: `atom`, `leg` (price-move sense; see §7 for the option-structure scoping), `pivot-atom`, `doji-atom`, the archetypes with the `off-pace` flag, `sign-edge`, `zero-extreme`, `archetype-grade`, `giveback_frac`, `pace`, `force-alignment`, the death modes (`absorption-death` + `absorption-death-grade`, `hot-death`, `quiet-death`, `mixed-tail`), `leg-boundary trap`, `V-signature`, `provisional-pivot` (future work, flagged unratified), `micro-stall`, `probe-atom`, `probe-grade`, `probe-fade`, `auction-probe`, 4 grade bands (`coin-flip`/`lean`/`solid`/`strong`), `F1-drive/push/churn`, `host-leg`, `confirmations-into-dying-legs`, `stall-read`. Entries that *resolve* conflict-inventory items: effort vs force (item 6, two named axes), move→leg (pre-empts a new item), stage suffixing (items on flush/stall/flip/confirm), probe vs auction-probe (Foundation reconciliation), leg vs option-leg/spread-leg (order-context scoping), fade split (quiet-death rename; "fade the move" recorded as a banned bare form in definitional text). Entries *deferred to the ruling round*: container word (episode/engagement/instance/recognition), the FBD name-set, bare-flush winner, the lean-band direction-adjacency flag.

### 6.2 st-79z.1 CLI grammar terminals

The archetype names, grade bands, death modes, and motif names are the grammar's noun terminals; the graded fields (`pace`, `giveback_frac`, `flush-depth`, `entry-lag`, `travel`, `probe-grade`, `minutes-into-leg`) are its measurable arguments — so spoken intent ("flush-leg, coin-flip-band archetype-grade, absorption-death tail") parses to the same tuple the recognizer and replay records emit. **Terminal bans:** bare `boundary` is not a terminal (the band is `coin-flip`; the motif is `leg-boundary trap`); on any surface that can also carry order structures, the option-structure sense must be compounded `option-leg`/`spread-leg` — bare `leg` in the grammar always means the price-move unit. Hindsight-only terminals (everything leg-tier and percentile-derived) carry the HINDSIGHT flag so the grammar cannot silently emit them as live claims.

---

## 7 · Naming decisions vs miner proposals (deviations and collision resolutions logged for the verifiers)

| Miner / Draft-1 name | Taxonomy name | Why |
|---|---|---|
| squeeze-leg | **counterforce-leg** | "squeeze" sits in the ratified direction-synonym cloud as an UP-move word (rip/squeeze/pop, 2026-07-25 entity survey); the archetype skews DOWN (41/28) — the name would have been a direction inversion baked into the vocabulary, the exact failure mode the compound convention exists to prevent |
| HERT | **probe-atom** | acronym → tape word; joins the cross-scale probe family per residue miner's own proposal 2 |
| "trap signature" (bare) | **leg-boundary trap** | "trap" carries 4 senses; the compound pins the atom-scale sense |
| interior "121 micro-stall" | **micro-stall** | partner word `micro-` disambiguates from stall-stage |
| move (unit) | **leg** | one phenomenon, one word; `moves.jsonl` keeps its filename |
| drive/push/churn (bare) | **F1-drive / F1-push / F1-churn** | cell prefix mandatory — travel sub-grades are within-cell only |
| "boundary" band (Draft 1) | **coin-flip band** | collision fix: "boundary" already means leg-boundary trap, cell boundary, and resolution boundary in this document; bare `boundary` banned as a CLI terminal |
| fade-death (Draft 1) | **quiet-death** | collision fix: Draft 1 had probe-fade (extreme retraced) and fade-death (depleted quiet ending) as two different phenomena sharing bare "fade," colliding further with the trader sense "fade the move" (take the other side). probe-fade keeps its compound; the death mode is renamed; "fade the move" is a recorded banned bare form in definitional text |
| probe (unreconciled) | **probe-atom / probe-fade vs auction-probe** | Foundation 01/03's "probe" is the auction's outcome-NEUTRAL excursion testing value — it can succeed. The taxonomy's probe family is the graded failure-subset of that sense. The lexicon entry carries both senses with owner surfaces; where both can appear, the Foundation sense compounds to `auction-probe` |
| leg (unchecked vs option structures) | **leg vs option-leg / spread-leg** | collision fix: `market/entities/spread.py`, OCC legs, schwab-py builders, and TOS multi-leg order strings use leg = option-structure leg, and the st-79z.1 pipeline's terminus is an order string containing option legs. Mandate: on order-structure surfaces and any surface that can contain both, the option sense is always compounded (`option-leg`/`spread-leg`); lexicon records the dual sense with banned-bare-forms scoped to order-context surfaces |
| steady-leg (pace clause unenforced) | **steady-leg (core) + off-pace flag** | counterexample fix: the pace window 0.38–0.75 is now enforced as the defining cut; the 112 off-window pure-F1 residuals (38% of Draft 1's class) stay in the family only under a mandatory `off-pace` flag, with shares and medians republished (§2.1) |
| "lean" band | **lean** (kept, flagged) | direction-adjacent in trader speech (directional lean/bias) — flagged for the ruling round under Direction Inversion Watch; no rename imposed here |

**Post-sweep status:** Draft 1 closed this section by asserting "no bare contested word appears in any definition above"; the collision recheck falsified that claim, and it is not re-asserted. Definitional text has been re-swept in Draft 2 (cell-pair language for grade-band reclassification, confirmation events, flush-stage excursions, leg-boundary trap, pivot-atom, leg-grind, stall-read, dead-drift/F4-cell legs, quiet-death, coin-flip band, MOC-window). Verification of the sweep belongs to the next adversarial pass, not to this document's self-report.