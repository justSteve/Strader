# Anchor Kind Fidelity and the Upside Mirror — st-tme · st-q5xu

**Beads:** st-tme (*Anchor Kind Fidelity*), st-q5xu (recognizer has no upside mirror) · **Date:** 2026-08-19
**Run:** `20260819T205533Z` (full corpus, 280 tape days) · **Baseline:** `20260731T045133Z` (st-98z stage 4, the shipped recognizer)
**Data:** `data/measurement/acuity-run2-{days,confirmations}.jsonl` (append-only; filter on the run id; `20260819T205505Z` is a one-day smoke of 08-05 that precedes it)
**Code:** `market/orderflow/anchors.py`, `market/orderflow/recognizer.py`, `scripts/acuity_run2.py`, `scripts/acuity_run2_summary.py` (the tables below are its output, unedited)

## What was wrong

Two layers, both live on 2026-08-05 when Steve asked whether we tell a
breakdown from a breakout:

1. **The anchor loader dropped the letter's kind.** `anchors.py` admitted every
   Mancini level as `support`. Verified that day: all 51 anchors `support`,
   including the 12 the parse recorded as resistance. The acuity sweep had its
   own private loader that kind-filtered to supports, so the measured path and
   the live path did not even watch the same set — the same-anchor rule the
   module's own docstring claims.
2. **No name for the upside form.** The recognizer's state machine was already
   direction-parameterized (`resistance` engages on a push above), but the
   *name* at a resistance stayed `failed_breakdown` — so a push above 7815
   that failed read as `failed_breakdown forming @ 7815 (support ∩ mancini)`:
   the bear signal, labelled as the long. Same silhouette, opposite meaning.
   The operator error mode in `knowledge/direction-inversion-watch.md`, in
   the tooling.

The 08-19 session showed the other face of the same bug: 7738 was a `trigger`
in the parse ("reclaims are a possible long trigger"), yesterday's ceiling —
admitted as support, it produced ten `failed_breakdown` / `level_reclaim`
confirms through the morning on what was a breakout retest and continuation
(`knowledge/reclaim-under-the-lid.md`; Steve: "to my eye it's continuation
upward from below").

## What changed

- **Anchors carry the parsed kind.** `mancini_kinds_for(day)` → {price: kinds},
  same sources and precedence as `mancini_levels_for` (labeled corpus → all
  supports by construction; else the day's parse). `support` → support anchor;
  `resistance` → resistance anchor; `pivot` → both, at one price (each with
  its own engagement state and fire history); `trigger` / `target` → **not an
  anchor** — commentary about a direction or a destination, not a ladder
  level; the price still reaches the chart and the confluence set. A level
  whose role we cannot read is not watched. (`ANCHOR_KINDS_BY_PARSE_KIND`.)
- **One rule, every path.** Drill (`day_anchors`), live feed (`LiveAnchors`),
  replay recorder, parity replay, post-mortem backfill and the acuity sweep
  all take kinds from that one function; acuity's private `letter_levels_for`
  is gone. `tests/market/orderflow/test_anchor_parity.py` pins that the three
  derive the identical (price, kind) set from one parse. The live run log
  header and the feeder's page meta carry `mancini_kinds` so a parity replay
  watches what the live run watched. `--mancini-levels` on the feed, page and
  `replay_day` takes `PRICE[:KIND]`; a bare price is still a support.
- **The mirror is named.** At a resistance the violent form is
  **`failed_breakout`** (push above, stall, delta flips down, close back
  beneath — Mancini's Failed Breakdown is the long; this is the bull trap, the
  short) and the quiet form is **`level_reject`** (a quiet poke above that is
  retaken — to `failed_breakout` what `level_reclaim` is to
  `failed_breakdown`). Bias is bearish. Stage names are unchanged; they were
  already direction-neutral words. The invalidation word at a resistance is
  "held above, no reject" (the breakout held), mirroring "no reclaim".
  `CarmineSetup` carries both; the drill's labels are "Failed Breakout" /
  "Level Reject"; the post-mortem's recap matcher treats the pair as a family
  and looks for "failed breakout" in his recap words.
- Parity snapshot regenerated for the rename (`tests/market/fixtures/parity/CHANGES.md`).
- `regime.py` (the meltdown read) stays downside-only by design and says so;
  a melt-up read from the mirror is a separate question.

On the 08-05 tape, 7815 now emits `level_reject` / `failed_breakout`
confirmed (bearish) from 08:31 on; on 08-19, 7738 emits nothing and 7742 (major
R) emits `failed_breakout` at 09:00, 10:54, 13:06.

## The re-sweep — bullish and bearish graded separately, never pooled

Same harness and grading as run 2 / st-98z: first-touch ±5 ES points at 30 min
from the confirm bar's first trade; time split tune < 2026-06-01 / validate ≥.
280 tape days (the sweep's glob now includes compacted `.jsonl.gz` days), 197
scored, 83 with no anchors. Resistance anchors exist only where a parse exists
— 26 letter days, 2026-07-15 onward plus one 05-19 — so the bearish
population is **validate-half only** (241 of 244).

### Regression check — the support side did not move

| bullish, common days (197) vs baseline `20260731T045133Z` | n | Win | W / L / und | Med MFE / MAE |
|---|---|---|---|---|
| baseline | 423 | 45% | 175 / 212 / 36 | 6.75 / 7.75 |
| this run | 423 | 45% | 175 / 212 / 36 | 6.75 / 7.75 |

Bullish confirms added 0, removed 0 (keyed on day, anchor, setup, minute).
Carrying kind changed nothing on the support side; the only support-side
addition by rule (a pivot now also a support) produced no new confirm.

### Population

| Cut | n | Win (±5 @30) | W / L / und | Med MFE / MAE | MFE>MAE |
|---|---|---|---|---|---|
| bullish (support anchors) | 569 | 43% | 218 / 284 / 67 | 6.50 / 7.25 | 47% |
| **bearish (resistance anchors) — new** | **244** | **51%** | 113 / 109 / 22 | **7.25 / 6.12** | 51% |

The bearish stream is a coin flip at ±5 symmetric (113/222, two-sided
binomial p = 0.84) — as the bullish stream was at its baseline (47%). Its
excursion profile is the better of the two over the same period: median MFE
above MAE (7.25 / 6.12) where the bullish validate half runs 7.25 / 8.38.
Read every bearish number as "accuracy of bearish reversal confirms at
Mancini resistances, 07-15 → 08-19, out of sample by construction"; nothing
here was tuned.

### Bearish, by cut

| Cut | n | Win | W / L / und | Med MFE / MAE | note |
|---|---|---|---|---|---|
| failed_breakout | 161 | 50% | 72 / 73 / 16 | 6.75 / 6.00 | |
| level_reject | 83 | 53% | 41 / 36 / 6 | 7.75 / 6.25 | p = 0.65 vs coin |
| fire 1 | 93 | 53% | 46 / 41 / 6 | 8.50 / 7.00 | |
| fire 2 / 3 / 4+ | 55 / 40 / 56 | 46% / 50% / 53% | | | no fi≥4 cliff on this side (n small) |
| hour 08 | 41 | 49% | 20 / 21 / 0 | 14.50 / 9.25 | open hour moves both ways, as on the bull side |
| hour 09 / 10 | 58 / 45 | 50% / 49% | | 9.75 / 8.12 · 5.00 / 7.00 | |
| hour 11 | 25 | 58% | 14 / 10 / 1 | 6.25 / 4.50 | |
| hour 12 / 13 | 15 / 18 | 46% / 38% | | | midday, same dead zone as bullish |
| hour 14 | 32 | 65% | 17 / 9 / 6 | 7.50 / 3.38 | **p = 0.17 — not an edge, a small cell**; quote it with the p or not at all |
| full-day D / P / b / trend | 107 / 71 / 36 / 30 | 49% / 52% / 53% / 50% | | b: 13.25 / 8.25 | no day-type dependence — unlike bullish (P 54% / b 33%) |
| developing D / P / unknown | 121 / 25 / 85 | 51% / 61% / 49% | | | |
| rth / late_day | 237 / 7 | 50% / 86% | | | late-day n=7, unreportable |

### Bullish, the same period, for contrast (validate half)

| Cut | n | Win | Med MFE / MAE |
|---|---|---|---|
| bullish, tune (< 06-01) | 217 | 50% | 5.50 / 5.50 |
| bullish, validate (≥ 06-01) | 352 | 39% | 7.25 / 8.38 |

The bullish validate half is below a coin (124/315, p = 0.0002): support-side
reversal confirms have been getting run over in the summer tape. That is not
new to this run — it is the st-98z stream on more days — but it is the
honest backdrop for the bearish 50%: in the same weeks, the same machine's
long-side read was 39%.

## What this does and does not say

- It says the tooling now names the move after verifying the anchor's role,
  and both paths measure the same thing. It says the new bearish stream is,
  unfiltered, as much a detector-not-a-filter as the bullish one was.
- It does not say anything about an edge in either direction at ±5 symmetric,
  which is not the trade. Nothing here is a recommendation; Steve directs the
  trading.
- The post-mortem backfill (COO, co-7kgte) measured its 88 anchored days under
  the all-support rule; its ledger rows for resistance levels carry the old
  `failed_breakdown`-as-support reads. Re-running `--backfill` under the new
  rule is COO's to schedule (memo sent).
- The developing-day-type gate (st-98z item 4) and the hour cuts were derived
  on the bullish stream; whether they transfer to the bearish one is an open
  measurement, not an assumption.

## Verification

`pytest tests/ strader/tests` = all green (the one failure is the pre-existing
peer-ledger NOTE-row test, not this change). New: 5 recognizer mirror tests,
7 anchor-kind tests, 1 three-path parity test; parity snapshot regenerated
deliberately.

---

## Addendum — the enriched corpus (run `20260819T213124Z`, same day, st-2a8v)

Hours after the sweep above, COO's levels backfill (co-vp45h) gave every letter
in the blob cache a parse artifact: `runbook/mancini/parsed/` went 27 → 284
days, covering 255 of 280 tape days. Two changes and a re-sweep on top:

1. **Labeled days gain the parse's resistance side.** `mancini_levels_for` /
   `mancini_kinds_for` on a labeled day now merge in the parse's resistance
   prices; the support set stays exactly the labels'. Resistance anchors
   cannot emit a bullish setup, so the bullish stream on labeled days is
   unchanged **by construction and by measurement**: on the 49 tape days with
   actual label levels, 124 bullish confirms before, 124 after, 0 added, 0
   removed. (Pinned by `test_labeled_day_gains_the_parses_resistance_side_only`.)
2. **Coverage.** Scored days 197 → **270** (no-anchors 83 → 10); days with
   resistance anchors 26 → **253**. Anchor source: 63 labels / 192 letter.

### Population, enriched

| Cut | n | Win (±5 @30) | W / L / und | Med MFE / MAE |
|---|---|---|---|---|
| bullish (support anchors) | 1235 | 46% | 500 / 586 / 149 | 6.25 / 6.75 |
| bearish (resistance anchors) | 1077 | 49% | 418 / 442 / 217 | 4.75 / 5.00 |

Bearish at 49% (418/860, two-sided p = 0.43): a coin flip, now on 4.4× the
sample — the 51% above was the same coin on fewer days. `level_reject` 51%
(n=286) vs `failed_breakout` 48% (n=791). Bearish time split: tune 48% /
validate 49% — stable across the halves, unlike bullish (49% / 41%).

### Cuts derived on the old anchor body FLATTEN on the fuller one

These were measured before trusting the old numbers forward; both moved:

| Cut (bullish) | old body | enriched | note |
|---|---|---|---|
| fire_index ≥ 4 | 33% vs ~50% fi 1–3 (st-98z: the damp's evidence) | **42%** vs 46–49% | direction survives, the cliff is now a slope; the 0.8→0.6 confidence damp in the recognizer rests on the old measurement |
| full-day b (trend down) | 32–33% | **46%** | the "bullish confirms get run over on b days" pattern largely dissolves |
| full-day P (trend up) | 54–65% | **50%** | likewise the P-day pocket |

On the bearish side there is **no fi≥4 cliff at all** (fi4 = 52%, n=170).
The recognizer's step-damp fires on both sides today; its evidence base is
now the weakest number in the stack — re-deriving it (time-split, per side)
before anything consumes the damped confidence is the follow-up this
addendum leaves open. Same for the developing-day-type gate idea: the
day-type dependence it was meant to exploit is much flatter here.

### Sample-shape caveat

The enriched tune half is dominated by 2025 late-day pulls (13:00–15:00 CT
tape), which is why bearish median MFE/MAE compressed to 4.75/5.00 — shorter
windows to the close truncate excursions (217 of 1077 undecided). Hour rows
13–14 CT carry 731 of the 1077 bearish confirms. Nothing here is a
recommendation; Steve directs the trading.

Verification: strict-reproduction diff script in the run notes; full pytest
suite green post-merge. Runs `20260819T205533Z` (kind rule, 26 letter days)
and `20260819T213124Z` (enriched) both stand in the append-only store.
