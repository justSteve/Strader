# PA Vocabulary Consistency Review

**Bead:** st-g9y · **Date:** 2026-07-28 · **Feeds:** st-79z.1 (trade-language normalization / CLI grammar)
**Method:** two-track sweep — code phrase surfaces (`market/orderflow`, `market/signals`, drill template, bridge) reviewed directly; prose surfaces (foundation docs, drills, knowledge bundle, specs/plans, Pine renderer, CLAUDE.md, coach skill) via subagent inventory. Trigger: three live ambiguity failures in one drill session (2026-07-27: stages/beats, invented "silhouette", 0-vs-1 bar numbering).

## Verdict

**The spine is solid; everything around it is improvised.** The four-stage
sequence (flush → stall → flip → confirm) is defined in `docs/foundation/07`
and restated consistently across six surfaces. Almost nothing else is:

| Failure class | Count found |
|---|---|
| Same word, multiple phenomena | **12** (worst: confirm ×5 senses, flip ×4, stall ×4, trap ×4) |
| Same phenomenon, multiple words | **7** (worst: the failed breakdown itself has 5 names) |
| Load-bearing terms never defined | **~15** (incl. *pin* — central to the butterfly thesis — and *elevator*, Mancini's own trigger word) |
| Ruled-out terms still live | **beats** — in the record's JSON field, reason strings, drill template (~6 sites), and the coach skill's own text |
| Machine verdicts trapped in prose | absorption outcome, recognizer branch semantics — analysis requires regexing English |

## The worst offenders (merged, ranked)

1. **"Failed breakdown" has five names** — trap / failed breakdown / FBD /
   Pine's `RECLAIMED` state / Mancini's "elevator-down into FBD". No document
   states they're the same object. The renderer treats reclaim as a *level
   state*, the drill deck as a *scenario*; nothing bridges them.
2. **"flush" self-contradicts at the top of the authority chain.** Foundation
   07 defines it as stage 1 — *the* load-bearing event. The renderer spec and
   Pine source use "wicks are flush noise" — flush as the excursion to
   *ignore*. The vocabulary's most important word means opposite things on
   the two most authoritative surfaces.
3. **"beats" is in the data model.** The stages ruling (knowledge/
   stages-not-beats, 2026-07-09) was applied one surface deep: the review
   page's column header says "stages" while the JSON field, the reason
   strings ("beats so far: flush+flip"), the drill template, and the
   drill-coach skill text all still say beats. The coach skill is a live
   violation in *user-facing* text.
4. **The recognizer's ACCEPT branch silently inverts `bias`.** Everywhere
   else `bias` = direction of the reversal being confirmed; on the accept
   branch it follows the break (continuation). Same field, opposite trade
   meaning, distinguishable only by parsing the reason prose. Undocumented
   stage word `extend` and undocumented setup `return_to_lvn` ride the same
   branch.
5. **"confirm" carries ≥5 senses** (stage 4 / orderflow-confirm tag / delta
   confirming an extreme / Pine bar-closed / post-entry confirmation) —
   directly relevant to Steve's role ruling that "confirmation" authority
   belongs to hindsight: the word itself doesn't currently name one thing.
6. **effort/effect vs force/effect are different quantities** (unsigned
   volume vs signed delta) but the drill surfaces use the two compasses
   interchangeably ("effort-vs-effect matrix" / "force-and-effect compass").
7. **Four container words for one unit of work** — code `_Engagement`, drill
   "instances", records "recognitions", coach ad-hoc "episodes" (the last
   exists in no repo surface at all).
8. **Absorption's outcome is prose-only.** "absorbed, level broke" — a
   verdict ("defense failed") readable only by someone who already knows the
   model, stored only inside the reason sentence; no outcome field exists.
9. **"level" is a price, a 10-pt distance unit, sweep tick-rows,
   imbalance-stack rows, and a CVD y-value** across surfaces.
10. **Bar indexing** — the drill surface disagrees with *itself* (footer
    0-based, progress readout 1-based); fix in flight (st-d5g).

## What's worth keeping (the anchors for normalization)

1. **Renderer level-states** (`untouched → tested/held → broken → reclaimed`,
   close-based, tolerance-explicit) — the best-specified vocabulary in the
   repo.
2. **`conditions.yaml`** in the playbook entity design — the only controlled
   vocabulary with `def:` fields anywhere.
3. **Foundation 02 + 05 effort/force definitions** — rigorous individually;
   they need one reconciliation decision (unsigned vs signed), then they
   anchor the compass language.
4. The four-stage spine itself, and the scenario catalog S1–S6 names.
5. Prior art: `docs/research/2026-07-25-trade-language-entity-survey.md`
   already maps the direction-synonym cloud (rip/squeeze/pop vs
   flush/knife/elevator); build on it.

## Direction: the lexicon is metadata → make it executable

This is the same move as metadata→CLI, applied to language. One tracked
artifact — `lexicon.yaml` (term, definition, owner-surface, allowed senses,
banned synonyms, emitting surfaces) — becomes the source of truth that
*compiles outward*:

- **code**: stage/state/setup enums and JSONL field names generated or
  lint-checked against it (a `beats` field fails CI)
- **records**: verdict words become enum fields (absorption outcome,
  branch marker), prose reasons keep the narrative but stop being the only
  carrier of meaning
- **docs**: the glossary section of foundation docs generated from it
- **coach/drill**: the phrasebook I speak from — no more invented words
  ("silhouette") reaching Steve's screen uncited
- **CLI grammar** (st-79z.1): the same lexicon supplies the grammar's
  terminals, so spoken intent, TOS syntax, and recognizer output converge on
  one vocabulary

Sequencing proposal (each its own bead when authorized):
1. **Ruling round** (Steve, ~30 min with the conflict table): pick winners
   for flush, confirm, the FBD name-set, effort-vs-force, the container word.
   Nothing downstream is buildable until these are ruled.
2. **lexicon.yaml v1** encoding the rulings + the already-good vocabularies.
3. **Code migration**: `beats`→staged field rename with `bar_base`-style
   run-marker (same pattern as st-d5g), absorption outcome enum, ACCEPT
   branch made explicit (`branch: reversal|acceptance` field).
4. **Surface sweep**: drill template, coach skill, Pine comments, review page
   regenerated/checked from the lexicon.
