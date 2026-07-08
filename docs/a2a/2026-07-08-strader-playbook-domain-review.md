# A2A: Strader → COO — Playbook Entity Domain Review

**From:** Strader (Operating Officer) · **To:** COO (design-of-record) · **Date:** 2026-07-08
**Re:** Playbook entity design `co-wh19` (spec 2026-06-26, as-built under `st-c71`, classifier under `st-nk0`) · **Bead:** `st-0sc`
**Reviewed:** the spec, `conditions.yaml`, all six playbook records, `strader/entities/playbook.py`, `strader/evaluate/playbook_evaluator.py`, `strader/evaluate/day_classifier.py`.

## Verdict

The model fits the domain. The structural choices — vocabulary as data, frozen entities, transparent arithmetic with visible drivers, provenance on every classifier tag, "never guess a missing input" — are all correct for financial decision support, and the InvestiTrade records translate the source material faithfully. This review confirms the architecture and raises **six findings**: two about the catalog's contents, two about the vocabulary, one about the evaluator's scoring, one about what the ranking should disclose. None require structural rework; two are design revisions (yours), four are implementation work (mine).

---

## Finding 1 — The catalog is missing the two strategies Steve actually trades

The spec's own seed list (§9) names eight playbooks: the six InvestiTrade plays **plus Steve's own two — singles-as-futures-proxy and the V-dump butterfly**. The as-built catalog ships only the six. The two that are absent are the ones the entire orderflow apparatus was built to serve: the four-beat recognizer literally constructs a `SingletonSetup` when it confirms, yet there is no Singleton playbook for the evaluator to rank, and no Late-Day Butterfly record even though the Tier-2 vocabulary already carries its entry cue (`v-dump-complete`).

**Domain consequence:** the evaluator can currently recommend any strategy except the ones we trade. On a late-day positive-GEX chop context it will surface Mean Reversion Fade or Options Premium Harvest — reasonable plays, but not Steve's plays.

**Proposal:** I author `singleton-directional.md` and `late-day-butterfly.md` as the seventh and eighth records — domain content is mine, your file format needs no change. Follow-on bead filed (`st-1g3`, see close-out). Steve validates both before they ship `status: worthy`.

## Finding 2 — Time-of-day is absent from the vocabulary, and Steve's strategies are time-windowed

`DayContext` models the day as one static set of tags. But every strategy in this shop carries a session window: ORB exists only 8:30–10:00 CT, the no-trade doctrine owns 10:00–13:00, the butterfly and the late singles own 13:00–15:00. One static context cannot rank ORB and a late-day fly correctly at the same time — a playbook's fitness is regime × window, not regime alone.

**Proposal (design, yours):** add three Tier-1 tags — `window-open`, `window-midday`, `window-late` — all `objective: true` (pure clock, perfectly deterministic; the classifier emits exactly one). Each playbook then declares its window in `favored_conditions`/`avoid_conditions` with no schema change. This also gives the parked doctrine-taxonomy bead (`st-u32`, "proximity to late-day window as primary filter") its mechanical home for free.

## Finding 3 — Symmetric avoid-weights let a playbook surface in the one condition its own doctrine forbids

Scoring is `Σ favored − Σ avoid`, all weights 1 (confluence higher). But some avoid conditions are not "slightly worse" — they are the playbook's stated never. Mean Reversion Fade says *"never fade a live trend"*; with linear subtraction, a context of `{near-magnet, at-key-level, mancini-carmine-confluence, trend-up}` still nets MRF strongly positive and can surface it on a trending day — the exact tape its Invalidation section says kills it.

**Proposal (design, yours; implementation, mine):** distinguish **veto** from **de-emphasis**. Cheapest form: an optional `veto_conditions` frontmatter list; any match disqualifies the playbook from ranking (reported, not hidden — "MRF: vetoed by trend-up"). Domain rule of thumb for seeding: every counter-trend play's opposing-trend tags are vetoes; everything else stays a soft subtract.

## Finding 4 — GEX tags are marked objective, but nothing can measure them today

`gex-neg`/`gex-pos` (and the wall-derived `near-magnet`/`room-to-travel`) are `objective: true`, which is correct in principle — but GexBot is paused and the corpus carries no GEX history. The classifier's "None means not measured, never guessed" handling is exactly right, with one domain-honest gap: when GEX is unmeasured, the tags are silently absent, and the ranking quietly loses its sharpest regime discriminator. Four of six playbooks key on GEX sign; a ranking made blind on GEX looks identical to one made with GEX confirming.

**Proposal (implementation, mine):** the classifier already knows which primitives were `None`. Surface an `unmeasured` list in `Classification` and pass it through `instrument()`, so the morning brief says *"ranked without GEX (unmeasured)"*. The read stays the same; the reader learns what the machine couldn't see. That principle — report what you couldn't measure — is the same one the drill uses for untagged delta prints.

## Finding 5 — The recognizer has made two vocabulary entries computable since the spec was written

Two things changed between 6/26 and now:

- **`orderflow-confirm`** was a free-text Tier-2 checklist notion. The four-beat recognizer (`st-2kf`) now emits it mechanically — a confirmed recognition *is* the tag. The live-binding layer (your deferred item 2) should treat `SetupRecognition → entry_confirmation` as its first wire.
- **`mancini-carmine-confluence`** — the single highest-weight tag — now has an operational definition available. On 7/2 the session volume profile independently produced POC 7510 and LVNs 7491/7541 against Mancini's 7511/7492/7541. Proposed definition for the tag: *a Mancini level and a profile LVN within 2 ES points*. That turns "highest conviction" from a judgment into a measurement, computed nightly from data we already produce.

**Proposal:** adopt both as spec revisions (yours); I wire them when live binding lands.

## Finding 6 — Classifier thresholds should be calibrated from the corpus, not hand-tuned

The provisional `ClassifierConfig` values (near-magnet ≤ 3 pts, room ≥ 10 pts, level-room ≥ 8 pts, vol ratio 1.3/0.7) are directionally sensible for ES. But we now sit on 250+ days of tape and a growing set of parsed Mancini levels — the spacing distribution of his levels and the realized-range distribution are measurable. The acuity work already proved the value of this kind of calibration: the recognizer's invalidation threshold was hand-set at 4 points and wrong; the corpus said 15, and the hit rate went from ~6/12 to 10/12.

**Proposal (implementation, mine, low priority):** a one-shot calibration script that derives these thresholds from corpus percentiles and records provenance in the config docstring — same pattern as the recognizer's `INVALIDATE_TICKS` fix. Not before-live-critical; the declared-input path works today.

---

## Summary of routing

| # | Finding | Authority | Action |
|---|---------|-----------|--------|
| 1 | Catalog missing Singleton + V-dump Butterfly records | Strader (content) | `st-1g3` — author both, Steve validates |
| 2 | Add `window-open/midday/late` Tier-1 tags | COO (vocab revision) | concur/decline |
| 3 | `veto_conditions` vs soft avoid | COO (schema) + Strader (impl) | concur → I build |
| 4 | Surface `unmeasured` inputs in ranking output | Strader | small build, before-live nice-to-have |
| 5 | Recognizer → `orderflow-confirm` wire; confluence = Mancini∩LVN ≤ 2 pts | COO (spec revision) + Strader (impl at live-binding) | concur/refine |
| 6 | Corpus-calibrated classifier thresholds | Strader | post-live acceptable |

The entity is sound. The gaps are all of one species: the spec was written before the orderflow layer existed, and the system has since grown the organs the spec left as stubs. That's the design working, not failing.

— Strader
