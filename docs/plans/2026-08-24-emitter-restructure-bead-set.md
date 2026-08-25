# Emitter Restructure — Bead Set (2026-08-24)

Source: chat-side audit of the 08-24 Fable emitter session (st-2nyb, ~07:27–09:24 CT)
and the Sonnet continuation (~10:07–13:25 CT), both scored against
`/var/moo/logs/effort-effect/2026-08-24.log`, `data/corpus/2026-08-24/gexbot.jsonl`,
and `mi_gauge_live.jsonl`.

Core finding driving this set: **numerical accuracy in the narration was produced by
the scorer, not the model** — both models transcribed tool output near-perfectly and
erred only when recalling from conversational memory. The model spend differentiates
on the interpretive layer (playbook binding, event-triggered context, push judgment),
where Fable-xhigh clearly outperformed Sonnet. Restructure accordingly: deterministic
event emission, cheap transcription, expensive event-triggered analysis.

Run the `bd create` lines in order; wire the `--dep` flags after IDs are issued.

---

## Bead 1 — Scorer event emission (deterministic accuracy layer)

```
bd create "Strader: scorer event emission — tagged EVENT lines in live_effort_effect.py" \
  --type task -p 1 \
  -d "Extend live_effort_effect.py to emit tagged EVENT lines so alert-grade tape events are detected mechanically, not by model attention. Event classes: (a) SUPERLATIVE — new day-max vol / max buy delta / max sell delta (smax fields already track these; promote to their own line). (b) ABSORPTION-CLUSTER — N>=2 consecutive bars with effort_pct >= ~85 and effect_pct <= ~10 (2026-08-24 10:41-42, d-122/d-493 net 0.00 each, is the calibration case Sonnet missed). (c) CLIMAX — |delta| above threshold or top-decile vs trailing session (10:20 d-725 is the calibration case). (d) PLAN-LEVEL — touch / acceptance (2 closes beyond) / rejection at loaded anchor levels; the 'near <level>' field already computes proximity. Output: one greppable EVENT line per trigger, machine-parsable, so a monitor filter can wake on EVENT instead of a 5-min clock. Thresholds configurable; defaults tuned against the 08-24 log where the desired hit list is fully known."
```

## Bead 2 — Emitter rules amendments (close today's observed failure modes)

```
bd create "Strader: emitter rules v2 — grep-not-recall, delta-first, divergence-revisit" \
  --type task -p 2 \
  -d "Three rules into the emitter runbook, each closing a failure observed 2026-08-24. (1) SUPERLATIVE CLAIMS ARE GREPPED, NEVER RECALLED: any 'biggest/largest/first of the day' must cite a fresh grep of the effort-effect log or the smax field; Sonnet's 13:14 'biggest buy-delta of the day' (+549) contradicted its own 10:47 note (+786) via conversational recall. (2) DIGESTS LEAD WITH DELTA, PRICE SECOND: promote Sonnet's own post-correction behavior to a standing rule; the 12:13-17 'no clean direction' miss (price-only read over 4-of-5 negative delta bars, cum -437) is the calibration case. (3) FLAGGED DIVERGENCES CARRY A REVISIT OBLIGATION: any noted non-confirm (e.g. breadth ADD/TICK vs futures) must be re-checked and reported at its natural resolution event, not mentioned once at startup; the morning breadth divergence was never revisited through the 10:29 VWAP reclaim that resolved it. Also codify push policy: day-max-volume bars and o/n-low breaks are push-grade regardless of model."
```

## Bead 3 — Two-tier watch: transcriber + event-triggered analyst

```
bd create "Strader: two-tier emitter — cheap transcriber, event-triggered analyst" \
  --type task -p 2 \
  -d "Split emitter duty by model grade, cadence inverted from clock to event. TRANSCRIBER: cheap model (or no model — EVENT lines from Bead 1 may BE the narrative) holds the tmux session, appends events to the running record, zero interpretation. ANALYST: expensive model, woken only on EVENT lines (est. 6-10 wakes/session vs ~40 clock wakes), with the day's letter parse, playbook knowledge files (orb-playbook, selective-range-scalping, trapped-seller fuel), and gex/breadth history in context; owns synthesis, strip re-runs, push judgment, plan-level mapping (e.g. next level AFTER 7680 acceptance is the plan's 7695, not 'day-high area'), and setup naming per the Bead 5 ruling (criteria-cited, implication stated, push-grade). This is the 'mirror' concept from the 08-24 Fable session, inverted. Cost attribution: transcriber wakes and analyst wakes are separate task lineage under the watch bead so per-lane token spend becomes a query (claude-monitor consumer). Ruling resolved 2026-08-24 — analyst tier is justified; xhigh spend belongs here."
```

## Bead 4 — Strip/scorer cum-delta divergence (attach to st-8d3a)

```
bd comment st-8d3a \
  "Audit 2026-08-24: tools/context_strip.py cum RTH delta diverges from the scorer's minute-sum, systematically and growing — strip -5,600 vs scorer -4,176 at 08:50 (gap -1,424); strip -5,810 vs scorer -3,706 at 10:10 (gap -2,104). Same sign both times: strip counts more sell delta. Narrations quoted their instrument faithfully both sessions; the instruments disagree. Product fix must (a) settle which classification matches the raw databento tape (needs local recompute; 98MB file), (b) unify delta definition across strip and scorer, (c) still fix the hardcoded 13:30 UTC RTH open (DST landmine, fires Nov 1) and the GexContext._polls private-attr reach flagged in the earlier code review."
```

## Bead 5 — Codify ruling: analyst names setups, criteria-cited, implications stated

RULED by Steve 2026-08-24 (chat session): YES to naming, YES to stating playbook
implications. Rationale on record: overt labels are helpful so long as implications
are understood; the human retains the decision.

```
bd create "Strader: codify analyst-scope ruling under st-tme/st-gno7 lineage" \
  --type task -p 1 \
  -d "Ruling (Steve, 2026-08-24): the analyst MAY name completed setups AND state the playbook implication overtly. Amends the st-tme/st-gno7 narrate-events discipline with four conditions. (1) CRITERIA-CITED, NEVER VIBES-CITED: a pattern name is a graded claim — state the setup's defining conditions and show each met from the effort-effect log (e.g. 'prior low 7664.5 broken 08:42, flush held plan support 7654 within tolerance, reclaimed within 4 bars at 08:46 — FB structure complete'). Auditable by the Bead 6 rubric like any point claim. (2) IMPLICATION STATED, DECISION RETAINED: the analyst states what the playbook says the setup implies (entry zone, trigger, level sequence) as classification-plus-implication, never as directive; 'the playbook's entry is the reclaim, trigger above 7666' is in scope, 'enter now' is not. (3) NAMED SETUPS ARE PUSH-GRADE: a completed-setup call is only worth its cost if heard in time (2026-08-24 calibration: the two unnamed FB entries were worth ~20 and ~29 pts). (4) MECHANICAL-FIRST: setup preconditions that are mechanically detectable belong in Bead 1's event classes; the analyst names on top of detected structure, minimizing the judgment surface. Lands in the emitter runbook + fly-doctrine under st-tme/st-gno7 lineage."
```

## Bead 6 — Setup ledger rubric (session grading, optional but recommended)

```
bd create "Strader: setup-ledger rubric for grading emitter sessions" \
  --type task -p 3 \
  -d "Formalize the audit method into a repeatable rubric: after each emitter session, enumerate every playbook-defined setup that fired in the window (from letter levels + knowledge files + scorer log) and score the narration on four tiers — point-claim accuracy, derived-claim fidelity, omissions (did the record catch the thesis events), fabrications. The two 2026-08-24 transcripts + the audited effort-effect log are the calibration pair (Fable: 2 slips, 1 omission, 0 fabrications; Sonnet: 4 errors incl. one self-contradiction, 2 omissions incl. both effort-no-effect thesis events, 0 fabrications). Candidate packaging: a skill the reviewing session invokes against the day's log + transcript."
```

---

### Suggested dependency wiring (after IDs issue)

- Bead 3 `--dep` Bead 1 (needs EVENT lines) and Bead 5 (needs the codified scope rules in the runbook)
- Bead 5 is unblocked — the ruling is made; this bead is now pure codification
- Bead 6 independent; feeds claude-monitor once Bead 3's lineage split exists. Note the
  ruling upgrades the rubric: named setups with stated implications have testable
  outcomes, so the ledger can score analyst calls against results — the first
  measurable step toward Strader's trading loop.

---

## IDs as issued — filed by COO 2026-08-24

| Plan | Bead | Proper name | P | Status |
|---|---|---|---|---|
| Bead 1 | `st-dgwj` | Scorer Event Emission | P1 | open, ready |
| Bead 2 | `st-6s6x` | Emitter Rules V2 | P2 | open, ready |
| Bead 3 | `st-85dv` | Two Tier Emitter | P2 | open, **blocked** by st-dgwj + st-eaa8 |
| Bead 4 | — | comment on `st-8d3a` | — | filed, no new bead |
| Bead 5 | `st-eaa8` | Analyst Scope Ruling | P1 | open, ready |
| Bead 6 | `st-uqme` | Setup Ledger Rubric | P3 | open, ready |

All five assigned to COO, per Steve's ask that COO lead the coding. Dependencies
wired as suggested: `st-85dv` blocks on both `st-dgwj` (needs the EVENT lines to
wake on) and `st-eaa8` (needs the analyst's scope codified before an analyst
tier is stood up).

Cross-references inside the bead descriptions use the issued IDs rather than
"Bead N", so a bead read on its own still points at the right neighbour.
