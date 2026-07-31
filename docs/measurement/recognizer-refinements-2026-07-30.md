# Recognizer Refinements — st-98z: Proximity Gate, Re-fire Damping, Developing Day-Type

**Bead:** st-98z · **Date:** 2026-07-30 · **Baseline run:** `20260727T054148Z`
**New runs:** `20260731T043600Z` (stage 2, proximity gate) · `20260731T044440Z` (stage 3, damping) · `20260731T045133Z` (stage 4, developing day-type)
**Data:** `data/measurement/acuity-run2-{days,confirmations}.jsonl` (append-only; filter on the run id)
**Code:** uncommitted working-tree changes in `market/orderflow/recognizer.py`, `market/orderflow/tpo.py`, `market/signals/orderflow.py`, `scripts/acuity_run2.py` + tests. Every number below was recomputed directly from the jsonl run blocks for this doc, not copied from stage notes.

## Question

Run 2 (st-n62) ended with a 47% coin-flip raw stream and a leverage list. This
bead worked four items from it: (1) is the stacked-imbalance 0.9-confidence
branch dead code; (2) stop engaging anchors so far away the engagement is born
dead; (3) does confirm quality decay as the same anchor re-fires, and if so
score it; (4) can the *developing* TPO shape replace the hindsight full-day
day-type cut — the "single highest-leverage follow-up" from the run-2 doc.

## Method

- Same harness, same grading as run 2: `scripts/acuity_run2.py`, full corpus,
  first-touch ±5 ES points verdict at 30 min, all-supports/bullish-only.
- Corpus grew by 3 days since baseline (2026-07-27/28/29): baseline has 262
  day rows / 179 scored, new runs 265 / 182. **Fair before/after is
  common-days-only (262 days)**; all-days shown where noted.
- Time-split discipline: tune on `day < 2026-06-01`, validate on
  `day >= 2026-06-01`, split at analysis time on the row's day field.
- Score-don't-gate: nothing in these changes suppresses a confirmation except
  the proximity gate, which only rejects engagements proven unconfirmable
  (see item 2).
- Verification for this doc: `pytest tests/market/orderflow/` = **91 passed**
  (was 78 pre-bead); `pytest tests/test_tpo.py tests/market/orderflow/` = 109
  per stage 4. Recompute script:
  `data/measurement/tmp-st98z/verify_synthesis.py`.

## Item 1 — Stacked-imbalance confirm branch: reachable but starved (no code change)

Verdict on the suspected-dead 0.9-confidence branch (recognizer.py confirm
path, conf table): **reachable, parametrically starved, not dead.**

- A synthetic flush → flip → reclose sequence with 3 adjacent all-ask cells
  ≥ `IMBALANCE_FLOOR=100` and bar delta +100 < `CONFIRM_DELTA_MIN=200`
  confirms at 0.9 with the "confirmed with stacked imbalance" reason. Now
  locked by regression test
  `test_stacked_imbalance_confirms_at_higher_confidence`; the delta-only 0.8
  path got its first confidence assertion too
  (`test_delta_only_confirm_stays_at_base_confidence`).
- Starvation evidence: **all 353 baseline confirms carry confidence 0.8**
  (recomputed: the baseline run block contains exactly `{0.8: 353}`), and the
  7/22 session produced exactly 1 ImbalanceStack event end-to-end
  (stage-reported from recognizer internals; not recomputable from the jsonl).
- Config forbids lowering `IMBALANCE_FLOOR` (orderflow_config.py:105-110). If
  the branch is ever wanted live, the sanctioned route is aggregating coarser
  bars per the st-2kf note referenced there. No behavior change made.

## Item 2 — Proximity gate on engagement (run `20260731T043600Z`)

**Change:** `_try_engage` previously had only a lower-bound distance test
(penetration ≥ `ENGAGE_PENETRATION_TICKS`), so an anchor 15 points above the
tape could "engage" on a violent bar. That engagement is *provably
unconfirmable*: `_advance` runs the invalidation check first, from an extreme
already ≥ `INVALIDATE_TICKS=60`, so a born-deep engagement dies before the
confirm branch can execute. New gate: `if beyond >= INVALIDATE_TICKS * TICK:
return None`. This is noise-removal, not scoring-avoidance — the rejected
engagement had zero possible outcomes other than invalidation.

Also in this stage: harness `--since`/`--until` flags and a write-only
per-(day,anchor) `fire_index` derivation (feeds item 3).

### Before/after (common 262 days; all recomputed)

| Metric | baseline `20260727T054148Z` | gated `20260731T043600Z` (common) | delta | gated (all 265) |
|---|---|---|---|---|
| Confirmations | 353 | 355 | **+2** | 423 |
| First-touch ±5 @30m | 47% = 149W/169L | 47% = 150W/170L | +1W/+1L | 45% = 175W/212L |
| day_type P | 65% = 36W/19L (60) | 65% = 36W/19L (60) | 0 | 65% = 41W/22L (68) |
| day_type D | 47% = 89W/99L (216) | 47% = 90W/100L (218) | +2 rows | 45% = 106W/127L (261) |
| day_type b | 32% = 24W/51L (77) | 32% = 24W/51L (77) | 0 | 31% = 28W/63L (94) |
| Episodes conf/inval | 353 / 139 (72%) | 355 / 118 (75%) | **inval −21 (−15%)** | 423 / 162 (72%) |
| Tune (< 06-01) | 50% = 94W/93L (217) | 50% = 94W/93L (217) | identical | identical |
| Validate (≥ 06-01) | 42% = 55W/76L (136) | 42% = 56W/77L (138) | +1W/+1L | 40% = 81W/119L (206) |

The gate touched exactly **12 days** (recomputed from days.jsonl), cutting
invalidations 139 → 118 with confirms +2 and precision statistically unchanged
in both time-split halves. The surprise is the **+2 confirms**: a born-dead
engagement didn't just pollute the record, it left the anchor in `_blocked` —
for an anchor beyond the whole session, blocked permanently, since clearance
needs a full bar back across the level. Rejecting the engagement leaves the
anchor free for later genuine engagements. 2026-07-23 shows it cleanly:
invalidations 19 → 11, confirms 29 → 31.

### Finding (recorded, not fixed): anchors.py violates its own same-anchor rule

`market/orderflow/anchors.py` `mancini_anchors()` types **every** Mancini
level as a support anchor regardless of the parsed letter's kind (the
`for lv in mancini_levels: add(lv, "support", ...)` loop, lines 58-59). That
is what made 7575 — a resistance/pivot in the 7/22 letter — a "support"
sitting 11.5 points above the entire session. The acuity path is shielded
because `acuity_run2.py` (`letter_levels_for`) kind-filters to
`kind == "support"` before anchoring; the replay/drill path goes through
`mancini_anchors()` unfiltered. Correct fix (future stage): carry the parsed
kind into the Anchor — `resistance` engages *downward-approach/upward-break*
semantics — rather than filtering. A resistance level is signal, not noise.

## Item 3 — Re-fire damping (run `20260731T044440Z`)

**Change:** per-anchor confirmed-fire counter (`self._fires`, keyed like
`_active`/`_blocked` on `id(anchor)`, deliberately never cleared so it
survives block/re-engage cycles). Every `SetupRecognition` now carries
`fire_index` (1-based; on forming/invalidated emissions, the fire this
engagement *would be*). Confirmed confidence is step-damped at
`fire_index >= 4`: 0.8 → 0.6, stacked 0.9 → 0.7. Emission still happens
unconditionally — score-don't-gate.

**Precision unchanged, confirmed:** vs the stage-2 run, the confirm stream is
identical — recomputed as the same (day, anchor, ct, setup, bias) multiset of
423 rows, 0 verdict30 diffs, 0 fire_index diffs (the recognizer's recorded
field matched stage-2's independent harness derivation on every row; zero
mismatch warnings). Damping altered confidence only: all 70 fi≥4 confirms
carry 0.6, all 353 fi 1-3 carry 0.8. No stacked confirms in corpus,
consistent with item 1.

### Per-fire_index table (recorded field, verdict30 ±5; recomputed)

| fire | ALL (265d) | TUNE < 06-01 | VALIDATE ≥ 06-01 |
|---|---|---|---|
| 1 | 48% = 79W/85L (175) | 59% = 50W/35L (96) | 37% = 29W/50L (79) |
| 2 | 50% = 54W/54L (119) | 51% = 28W/27L (64) | 49% = 26W/27L (55) |
| 3 | 43% = 22W/29L (59) | 42% = 8W/11L (25) | 44% = 14W/18L (34) |
| **4+** | **31% = 20W/44L (70)** | **29% = 8W/20L (32)** | **33% = 12W/24L (38)** |

The cliff at fire 4 holds in *both* halves — 29%/33% vs 42-59% for fires 1-3
— so the step damp at fi≥4 is placed on out-of-sample-stable evidence, not a
tune-half artifact. (Fire-1's tune/validate spread, 59% vs 37%, is the usual
regime warning about the corpus halves; the fi≥4 floor is the robust part.)

**Parity note:** `parity.serialize()` iterates dataclass fields, so
`fire_index` flowed into the snapshot automatically and broke the committed
field-by-field diff. Snapshot regenerated deliberately via
`scripts/regen_parity_snapshot.py` (CHANGES.md entry appended); the diff is
purely additive — `"fire_index": 1` on the 6 recognizer events, counts and
everything else unchanged.

## Item 4 — Developing day-type (run `20260731T045133Z`)

**Change (measurement-only):** `classify_day_type(profile, upto=k)` classifies
from `brackets[:k]` only (upto=None is byte-identical to old behavior),
returning `("unknown", "IB incomplete")` while upto < IB_BRACKETS;
`initial_balance` gained the same `upto`; new `developing_upto(profile, ts)`
maps confirm wall-clock to a bracket position **excluding the in-progress
bracket** (the profile is built from the full-day tape; including it leaks up
to 30 min of future). Harness rows gain `developing_day_type` + `dev_upto`.
No recognizer behavior change.

### Cross-tab, developing (rows) × final (cols), all 423 confirms (recomputed)

```
dev\fin     P     D     b   tot   agree
     P      9    11     0    20    45%
     D     21   123    42   186    66%
     b      1    31    22    54    41%
 trend      0     0     6     6     0%
unknown    37    96    24   157     –
```

Agreement among known developing calls: 154/266 = **58%**. 157 rows (37% of
all confirms) are structurally `unknown` — the IB isn't complete, so the first
hour is silent. On full-RTH coverage, agreement is 19% at upto=2, ~41-50%
mid-day (upto 3-8), 64-67% at upto 9/12 with a 20-30% dip at upto 10-11
(small n). The late-day-tape agreement (80% at upto=2, 92% at upto=3) is
near-tautological — there the "final" label is computed from the same
13:00-15:00 sliver the developing call sees — and is excluded as evidence.

### Precision (verdict30) by developing type (recomputed)

| dev type | ALL | TUNE < 06-01 | VALIDATE ≥ 06-01 |
|---|---|---|---|
| P | 65% = 11W/6L (20) | 73% = 8W/3L (14) | 50% = 3W/3L (6) |
| D | 39% = 64W/99L (186) | 37% = 29W/49L (96) | 41% = 35W/50L (90) |
| b | 42% = 22W/31L (54) | 44% = 4W/5L (9) | 41% = 18W/26L (45) |
| unknown | 50% = 75W/74L (157) | 60% = 50W/34L (92) | 38% = 25W/40L (65) |
| *ref: final* | *P 65 / D 45 / b 31* | *P 68 / D 50 / b 35* | *P 59 / D 42 / b 27* |

### Recommendation: do NOT ship a developing-b suppression gate

The bead's question — does the developing b-call preserve the final-day 65/32
P/b separation — answers **no**, on three independent failures:

1. **Recall collapses.** Only 22 of 94 final-b confirms (23%) are called b at
   confirm time; the toxic population hides as dev-D (42), dev-unknown (24),
   dev-trend (6). The final-b rows *not* caught by dev-b run 29% = 20W/50L —
   invisible live.
2. **Dev-b precision isn't toxic.** Rows called b live run 42% (41% in
   validate) — near the D baseline, nowhere near the final-b 31% that
   motivated the gate. Suppressing on dev-b would cut near-average trades.
3. **The good pocket shrinks too.** Dev-P is only n=20 (final-P is 68), 50%
   in validate (n=6) — too thin to promote either.

The honest conclusion: at confirm time, mid-session TPO shape is mostly
indistinguishable rotation, and the run-2 day-type edge is predominantly
hindsight. Keep `developing_day_type`/`dev_upto` as recorded annotations
(they cost nothing and future cuts may combine them with hour or fire_index),
but the "developing-shape gate" from the run-2 recommendation list is
**measured and rejected** in its naive form. Any revival needs a different
live regime signal (e.g. cumulative delta, IB range extension direction), not
TPO letters.

## Summary

| Item | Change | Precision effect | Verdict |
|---|---|---|---|
| 1. Stacked branch | tests only | none (no behavior change) | reachable but starved; 353/353 baseline confirms at 0.8; leave alone pending st-2kf coarser-bar route |
| 2. Proximity gate | `_try_engage` rejects `beyond >= INVALIDATE_TICKS` | invalidations −21 (139→118), confirms +2, win% unchanged both halves | **ship** — pure noise removal, plus unblocking side benefit |
| 3. Re-fire damping | `fire_index` on SetupRecognition; conf 0.8→0.6 (0.9→0.7) at fi≥4 | stream identical; fi≥4 = 31% (29% tune / 33% validate) vs 43-50% fi 1-3 | **ship** — cliff is stable out-of-sample; score-don't-gate respected |
| 4. Developing day-type | `classify_day_type(upto)` + row annotations | measurement only | **gate rejected** — 23% recall on final-b, dev-b runs 42% not 31%; keep annotations |
| — anchors.py finding | none (recorded) | n/a | `mancini_anchors()` types all levels "support"; fix by carrying parsed kind into Anchor, future stage |

## Caveats

- Bullish-only, ±5 symmetric, corpus-vintage caveats from the run-2 doc all
  still apply.
- The 423-confirm totals in the three new runs reflect the **stacked
  working-tree changes** (each run includes all prior stages' uncommitted
  edits) plus 3 new corpus days; only the common-262-day columns are
  before/after comparisons against baseline.
- All changes are uncommitted in the working tree. The working tree also
  carries unrelated uncommitted edits (`runbook/mancini/run.py`,
  `scripts/corpus_daily.py`, `scripts/cron/mancini-preopen-wrapper.sh`,
  `tests/runbook/test_run.py`, `tests/conftest.py`) from another workflow —
  a commit of the st-98z work must be file-scoped.
- Stage-1's "exactly 1 ImbalanceStack on 7/22" is from recognizer internals
  and is not recomputable from the jsonl; every other number in this doc was
  independently recomputed and matched the stage reports
  (`data/measurement/tmp-st98z/verify_synthesis.py`).
- Run ids are UTC-stamped `20260731T…` for work done late 2026-07-30 local.
