# DaysActivity - 2026-07-28

## 18:45 - Session Handoff [Taxonomy + Lexicon + Training Package — the Vocabulary Front]

**Summary**: One continuous session spanning Sat 07-25 evening → Mon 07-28 evening. The arc: took over the replay-drill stack from COO's concurrent work, ran the first drills, then — driven by Steve's directives — built the entire vocabulary front end-to-end: corpus-wide recognizer precision measurement (acuity run 2 LEG B), the fundamental-units taxonomy (ultracode, 11 agents, adversarially verified), lexicon.yaml v1 with a CI linter, a measured day-narrative teaching surface, and the generalized five-channel training package (essays/checks/deck/audio). Steve made two standing rulings recorded to memory: he is risk authority, not PA-correctness arbiter (hindsight holds confirmation authority; LEG A retired), and teaching surfaces must embed chart figures (st-flu, parked deliberately). Six of Steve's live catches became lexicon law. Also: DataBento backfill completed after his billing fix (10/10 days + forward cron verified), the 7/22 Mancini pre/tape/post package with a $0.08 pre-market verification proving his "flushed 7506" exact (7504.0 at 07:56:53 CT), a bd-create silent-title-drop defect memo to COO, and a live EOD fly call + rescind graded correct by the close.

**Open Work**:
- **st-ndc (P1)** — Schwab refresh token expires ~Thu 07-30 05:49 CT; re-auth needed before then. **8/1 live date is Saturday**; P1 readiness lane: st-096 (Schwab online), st-958 (risk-state reset), st-66u (heartbeat + unread alerts)
- **st-055** — replay-drill stack complete; closes when Steve sits a full day. 07-15 drill armed (levels 7573/7566/7553/7547/7533); 7/22 reversed-drill partially walked; bridge stopped at session end
- **Evaluation session** (checks-09) — Steve's call after he cycles narrative → audio → essays → cards; passing unlocks drills per his recognition-before-reflex ruling. Deck import needs COO's bridge (`tools/anki/deck-import.sh`) or Steve
- **st-g9y** — lexicon v1 shipped; remaining: extend the bare-word linter to code emissions + drill surfaces; container-word (episode/engagement/instance) and lean-band rulings deferred
- **st-vqa** — x-ray harness design (deterministic watcher 90%, agent at pivotal moments); v1 slice for live week = alerts-to-desk + standing coach session 13:00–15:00
- **st-98z** — recognizer refinement backlog (developing-day-type gate, re-fire damping ≥4th fire 33%, stacked-confirm branch 0/353 dead-path inspection, proximity gate)
- **st-btu** — Phase B capture-window ruling: pre-market extension (the 7/22 7506 trap printed 07:56, invisible to RTH corpus)
- **st-d5g** — bar indexing 1-based everywhere (drill footer is 0-based, progress readout 1-based — internally inconsistent today); **st-mmy** glanceable delta footers; **st-flu** figures infrastructure (palette validated both modes, build parked at Steve's direction)
- **st-i68** — in-repo half shipped 07-25; still awaiting COO on the wrapper patch. **st-kq8** — bd-create defect memo delivered; awaiting COO ack. **st-3c4/st-5rc** — renderer implemented by concurrent session; Steve reports labels still jumping left + wants font +2 (logged on st-5rc, unverified which surface)
- 7/28 annotations file carries Steve's live EOD call (fly 7455/7470/7485 @ .05, rescinded) + settlement grade — feed into the day's hindsight review when 7/28 tape lands (cron 07-29 06:30)

**Tried**:
- Asserted "settlement 7433.99, fly expired worthless" **12 minutes before the close** → Steve caught it ("we are still 7 minutes from close"). Cause: read an index's absent bid/ask as market-closed. Liveness memory now carries corollary 2: no settlement/expiry claims before the bell; market outcomes pre-close are probabilities with "as of <time>"
- Told Steve "screen bars = my table +1" without verifying the drill surface's numbering → wrong; the column footers print 0-based record indices (and disagree with the page's own 1-based progress readout). His "10 ticks" observation exposed it. Never send a bar pointer without checking the payload
- `bd create task "title"` → bd binds "task" as the title and **silently drops the real title** (one positional). Seven corruptions in four days across three callers, all following CLAUDE.md's own stale syntax. CLAUDE.md fixed; memo to COO (docs/a2a/2026-07-27-strader-to-coo-bd-create-silent-title-drop.md); never pre-name bead IDs in prose either — twice guessed wrong before create returned
- DataBento estimate succeeding proves nothing about billing — estimates are free; the 402 fires only on purchase. First backfill retry 402'd after the "fix"; second attempt (Steve found the real portal setting) went clean
- Custom-window corpus pulls **append into the RTH corpus day-file** (`databento_glbx_es_path`) — a pre-market pull via the stock script would contaminate replay. Used a scratchpad-only variant for the 07:56 verification
- Adversarial verification earns its cost: Draft 1's 1.9× enrichment mixed two definitions (real: 1.47×); the "absorption-before-wins 35.6%" claim was irreproducible and likely sign-inverted (withdrawn); the whole grading substrate was unlabeled hindsight until the gates-attack forced the rider. The counterexample verifier reproduced every surviving number exactly
- Python heredoc string replacements silently miss when text wraps across lines — two lexicon/narrative sweeps "succeeded" while leaving bare words; grep-verify after every prose sweep

**Files Changed**:
market/orderflow/moves.py
market/orderflow/anchors.py (review only)
scripts/acuity_run2.py
scripts/moves_sweep.py
scripts/lexicon_render.py
docs/lexicon/lexicon.yaml
tests/docs/test_lexicon.py
tests/market/orderflow/test_moves.py
docs/measurement/recognizer-acuity-run2.md
docs/measurement/orderflow-fundamental-units.md
docs/research/2026-07-28-pa-vocabulary-consistency-review.md
docs/drills/day-in-fundamental-units-2026-07-22.md
docs/foundation/09-fundamental-units.md
docs/training/training-package-pipeline.md
docs/training/checks-09-fundamental-units.md
docs/training/decks/foundation-09-fundamental-units.tsv
docs/training/notebooklm/fundamental-units-source.md
docs/a2a/2026-07-25-strader-to-coo-personal-projects-roster.md
docs/a2a/2026-07-27-strader-to-coo-bd-create-silent-title-drop.md
CLAUDE.md
pyproject.toml
data/measurement/replay/signals_2026-07-{15,22}.jsonl (runs appended)
data/measurement/replay/annotations_2026-07-28.jsonl
data/corpus/2026-07-{23,24}/databento_glbx_es_mbp1.jsonl (backfilled)

**Beads**: Closed — st-e56, st-27y (orphan), st-ve6, st-n62, st-kaf, st-zq0. Created — st-e56, st-btu, st-kq8, st-98z, st-vqa, st-d5g, st-mmy, st-g9y, st-kaf, st-flu, st-zq0, plus retitles (st-3c4/st-ve6/st-gip). Memory — two new: steve-risk-authority-not-pa-arbiter; liveness corollary 2 (no pre-close settlement claims).

---
