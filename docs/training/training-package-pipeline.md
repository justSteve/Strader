# The Training-Package Pipeline

**Bead:** st-zq0 · **Date:** 2026-07-28 · **Role:** instructional-designer review
of the pipeline that taught effort/effect, refined and generalized so any future
topic can run it.

## What the prior pipeline actually was (review)

The effort/effect understanding did not come from one artifact. It came from
**five channels carrying one vocabulary**, consumed in different modes:

| Channel | Artifact | Consumption mode | What it uniquely does |
|---|---|---|---|
| **Essays** | `docs/foundation/01–08` | Slow reading, re-readable | Builds the *model* — one idea per doc, explicit lineage ("rests on: 01") |
| **Questions** | comprehension checks (protocol retired 07-18 after 01–08 passed) | Hosted LLM session, answers articulated aloud | Proves the model is *possessed*, not recognized — grading rewards mechanism, punishes pattern-matching |
| **Cards** | COO Anki bridge (`co-65gj`), `Front/Back/Category` TSV | Daily minutes, spaced | Keeps possession from decaying — snag-focused, judgment-rich Q/A |
| **Audio** | NotebookLM over the source docs | Passive, away-from-desk | Re-exposure without screen time; the same vocabulary in dialogue form |
| **Narrative** *(new, 07-28)* | measured day-story (`day-in-fundamental-units`) | Immersive first contact | *Acquisition* — terms arrive when the tape needs them, before the reference forms are usable |

**The design insight worth generalizing:** these are not five copies of the same
content. They are five *modes* — acquire (narrative), model (essays), prove
(questions), retain (cards), re-expose (audio) — and the pipeline works because
every mode draws from **one controlled vocabulary** (now enforced: `lexicon.yaml`
+ its linter). The failure mode the lexicon prevents is the modes drifting into
dialects.

## Refinements over the prior run

1. **Narrative-first ordering.** The foundation series began with essays; this
   package begins with the measured day-story. Ruling of record (Steve,
   07-28): at the introductory phase, recognition precedes reflex — the
   narrative supplies recognition, the deck supplies reflex, and drills come
   *after* both.
2. **The lexicon is the answer key.** Prior checks graded against the essays.
   Now every channel cites `lexicon.yaml` as ground truth, and the evaluator
   grades vocabulary use against it (compound-term convention included).
3. **Learner catches feed back as cards.** Four of Steve's own catches
   (band, terminal, zigzag, cutpoint) and his fencing frame became lexicon
   amendments same-day. The pipeline now has an explicit return path:
   *puzzlement → lexicon amendment → snag card*. A confusion that cost real
   time is the highest-value card content that exists.
4. **Figures rule** (st-flu, build pending): teaching surfaces embed chart
   images at points of reference. Channels ship text-only only until that
   infrastructure lands, and retrofit after.
5. **LIVE/HINDSIGHT badging** carries into every channel — the learner's
   *seat* (risk authority, not PA arbiter) is part of the curriculum, not
   context around it.

## The generalized recipe (run this for any topic)

**Inputs:** a measured/verified source of truth (a taxonomy doc, a spec, a
corpus finding) + the lexicon entries it introduces.

1. **Lexicon first.** New terms enter `lexicon.yaml` with definitions,
   `on_the_chart` lines, LIVE/HINDSIGHT flags. The linter must pass. No
   channel is written before its words are ratified.
2. **Narrative** — one real, dated, measured instance told start-to-finish in
   the new vocabulary; terms bold on first use; every number pulled from data;
   honest-exception moments included on purpose.
3. **Essays** — `docs/foundation/NN-*.md`, one idea per essay, ≤700 words
   each, explicit rests-on lineage, corpus numbers cited. The essay teaches
   the *mechanism*; the narrative already supplied the *experience*.
4. **Questions** — `docs/training/checks-NN-*.md`: 10–15 questions targeting
   mechanism and discrimination (the "which of two stories are you in?"
   class), plus the evaluation protocol for a hosted LLM session (grading
   rubric, mastery bar, lexicon as answer key).
5. **Cards** — `docs/training/decks/foundation-NN-*.tsv` in the COO bridge
   format (`Front	Back	Category`, category `Foundation::NN::Sub`).
   Card sources, in priority order: learner catches → discrimination pairs →
   honest exceptions → definitions. Import via COO's
   `tools/anki/deck-import.sh` (COO owns the bridge; Steve or COO runs it).
6. **Audio bundle** — `docs/training/notebooklm/<topic>-source.md`: the
   narrative + essays + a prose rendering of the topic's lexicon entries,
   concatenated with a header telling NotebookLM what the material is.
   Steve uploads; the audio overview is generated there.
7. **Evaluation session** — after Steve has cycled the channels on his own
   time, a hosted LLM session runs the checks doc. Passing retires the
   check (precedent: docs 01–08); failures route back as lexicon
   clarifications or new cards.

**Sequencing for the learner:** narrative → audio (passive, repeated) →
essays → cards begin → evaluation session → drills. Drills remain the
*reflex* layer and start only after the evaluation passes — the 07-28 ruling.

## Ownership

Strader authors content (domain). COO owns the Anki bridge and import
tooling (structure). Steve owns pace, evaluation scheduling, and the
NotebookLM channel. The lexicon linter owns consistency, mechanically.
