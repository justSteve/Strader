# Fable 5.1 prompt and harness audit — Thread 1 (Strader)

Audited 2026-09-04 for Desk. Report only; nothing in the repo was touched. Paths are relative to `/root/projects/Strader`; `memory/` means `/root/.claude/projects/-root-projects-Strader/memory/`.

## Summary

Instruction hits (things a model actually reads, not logs): family 1 anti-formatting 10 rows, none of them the "never use bullets" chat-style rule 5.1 warns about — they are file-format and line-grammar contracts plus pro-table skill boilerplate; family 2 narration suppression 4 rows, all of them the *content* rule "do not narrate Steve's method back to him" (what not to say), zero instances of "hold findings", "final response only", "no progress updates" or "silent until" as an instruction; family 3 verbosity dampers 17 rows, essentially all house style ("answer at the length it needs", "no preamble", "terse"); family 4 effort/model 7 rows, of which exactly one is a live model pin: `footprint-icm/bin/run_stage.sh:24` defaults to `claude-opus-5` and passes it as `--model` to `claude -p`. (While this audit ran, another session had uncommitted edits open on 22 files including `footprint-icm/bin/classify.py`, `claims.py`, `common.py`, `run_day.sh` and `scripts/cron/footprint-icm-wrapper.sh`; line numbers below are the working tree as of writing, and `run_stage.sh` is unchanged against HEAD.) No effort level, thinking budget or `budget_tokens` is set anywhere in the repo.

There is no direct Anthropic API call site. `import anthropic`/`from anthropic`, `api.anthropic.com`, `messages.create`, `tool_choice`, `budget_tokens`, `max_tokens`, `output_config` all return zero in tracked files and on disk (excluding `.venv`, `lib`, `node_modules`, `.git`, `data`, `__pycache__`, `.pytest_cache`); the SDK is not installed in `.venv`; `pyproject.toml` does not depend on it. The one model reach is the `claude` CLI, single-shot, no tools, no history, from `footprint-icm/bin/run_stage.sh` (cron 15:40 CT weekdays). So forced tool use, non-append-only history, cross-model fallback and cost-tuned compaction do not exist here — nothing to fix in the harness.

The two findings that matter: (1) the only thing that must change to move the audit lane to Fable 5.1 is the `claude-opus-5` literal in `run_stage.sh:24` and its echo in `classify.py:122`; the lane's own failure detection checks only `is_error` and an empty model result passes the checker with zero labels (`checker.py:130`, `ok = not failures`), so a refusal or empty reply on the new model would go unnoticed unless someone verifies that path. (2) The repo's prompt estate contains none of the 5.1-specific workarounds the migration guide says to strip; what it does contain is a deliberate house style (terse, tables, one-line alerts, no engagement filler) written to Steve's stated preference, which should be read as style, not as a stale mitigation.

## Method

Universe: `git ls-files` minus `.venv/ lib/ node_modules/ data/ __pycache__/ .pytest_cache/` (1,099 files), plus `.claude/` on disk (settings.local.json and `state/` are untracked), plus the memory directory, plus on-disk untracked `runbook/mancini/parsed/` (gitignored, 295 files) for the records count. All sweeps used `/usr/bin/grep` (GNU 3.11) via `xargs`. Note for Desk: `xargs … command grep` fails with exit 127 because `command` is a shell builtin; the first pass produced empty results that way and was rerun. Patterns were case-insensitive and included the paraphrases listed in the brief plus `narrat`, `bullet`, `concise`, `terse`, `--model`, `ICM_MODEL`, `\bopus\b|\bsonnet\b|\bhaiku\b|\bfable\b|\bmythos\b`, `claude-[a-z0-9-]+`, `reasoning_effort`, `effort_level`, `--effort`, `budget_tokens`, `thinking[_ ]budget`. Every row below was read in context.

## 1a. Prompt files

Prompt files found: one `CLAUDE.md` (root; no nested ones); `AGENTS.md` (beads boilerplate); `.beads/PRIME.md` (injected every session by the `bd prime --hook-json` SessionStart hook in `.claude/settings.json:31`); `.claude/agents/strader.md`; six `.claude/rules/*.md`; ten `SKILL.md` files under `.claude/skills/`; three hook scripts; `intent.yaml` (domain-factory profile whose `additionalRules` text is the source of `.claude/agents/strader.md`); two embedded system prompts, `footprint-icm/20-classify/prompt.md` and `footprint-icm/40-compare/prompt.md` (handed to `claude -p --system-prompt`); `runbook/mancini/extraction-contract.md` (read in-session by `/mancini-parse`); `MEMORY.md` and 51 memory files plus one archived index.

### Family 1 — anti-formatting rules

| file | line | pattern | surrounding instruction | proposed action | note |
|---|---|---|---|---|---|
| .claude/skills/handoff/SKILL.md | 178 | no bullet | "**Summary**: Standalone sentence, no bullet" | keep-with-note | Entry-format contract for DaysActivity.md (a parsed file), not chat style. Not a 5.1 workaround. |
| .claude/skills/handoff/SKILL.md | 179 | no bullets | "**Files Changed**: One file per line, no bullets, relative paths" | keep-with-note | Same contract. |
| footprint-icm/20-classify/prompt.md | 30 | no prose / no headings | "Nothing else in the output: no prose, no headings, no explanation." | keep | Line-grammar contract for `checker.py`; the output is machine-parsed. Load-bearing regardless of model. This prompt is the one that will actually run on Fable 5.1 if `run_stage.sh` is repointed. |
| footprint-icm/40-compare/prompt.md | 18 | no prose / no headings | "Nothing else in the output: no prose, no headings, no explanation." | keep | Same, for CLAIM lines. |
| .claude/agents/strader.md | 41 | tables over prose | "Terse. Tables over prose. Numbers speak. No preamble." | keep-with-note | Pro-table, not anti-formatting; does not fight 5.1's under-formatting. Frontmatter (`roleDescription`, `skillRefs`, `ruleRefs`, no `name:`) is domain-factory shape, not Claude Code's subagent schema; no `model:` key. |
| .claude/skills/strader/daily-pnl-summary/SKILL.md | 39, 40, 43 | tables not paragraphs | "Use tables, not paragraphs." / "Prefer structured tables over narrative text." (line appears twice) | keep-with-note | Generated scaffold (body still says "(Define structure and format here)"). Pro-table. Duplicate line at 40 and 43. |
| .claude/skills/strader/entry-signal-evaluation/SKILL.md | 60, 61, 64 | same | same boilerplate, duplicate at 61/64 | keep-with-note | Same scaffold. |
| .claude/skills/strader/greeks-analysis/SKILL.md | 62, 63, 66 | same | same boilerplate, duplicate at 63/66 | keep-with-note | Same scaffold. |
| .claude/skills/strader/position-sizing/SKILL.md | 68, 69, 72 | same | same boilerplate, duplicate at 69/72 | keep-with-note | Same scaffold. |
| .claude/skills/strader/risk-limit-enforcement/SKILL.md | 53, 54, 57 | same | same boilerplate, duplicate at 54/57 | keep-with-note | Same scaffold. |
| CLAUDE.md | 131-133 | don't restructure | "When Steve asks what something means, explain it in a few sentences — don't restructure it into a document." | keep-with-note | House style (tone_preference block). Closest thing in the repo to an anti-structure rule; it is Steve's stated preference, not a model mitigation. |
| CLAUDE.md | 117 | length-to-surface | "Anything longer than a paragraph goes to a desk page." | keep-with-note | Delivery rule (terminal vs desk page), house style. |
| memory/feedback_review_docs_via_steves_desk.md | 19 | no markdown link syntax | "End the reply with the raw address, one per line, no markdown link syntax." | keep-with-note | Terminal-rendering constraint (raw address is what works in his terminal). |
| memory/feedback_review_docs_via_steves_desk.md | 22 | too much text | Steve, 2026-08-18: "this is too much text sent to the terminal window." | keep-with-note | Record of the ruling behind the desk-page rule; house style. |

No hit anywhere for "avoid bold", "no headers" (as a style rule), "minimal formatting", "plain prose only", "no markdown", "avoid lists". `runbook/mancini/extraction-contract.md` has no formatting rules beyond its JSON shape.

### Family 2 — narration suppression

| file | line | pattern | surrounding instruction | proposed action | note |
|---|---|---|---|---|---|
| CLAUDE.md | 24 | do not narrate | "Answer the question asked, at the length it needs; do not narrate his method back to him or volunteer trade opinions." | keep-with-note | A content rule (don't recite his trading method), not progress-narration suppression. House doctrine (Steve 2026-08-13/14, quoted on lines 19-23). |
| .beads/PRIME.md | 74 | Do NOT narrate | "Do NOT narrate Steve's method back to him. Trading mechanics are a `knowledge/` read at question time, not context you recite" | keep-with-note | Same rule, injected every session via `bd prime --hook-json`. Duplicate of CLAUDE.md:24. |
| .claude/rules/fly-doctrine.md | 45 | narrate back | "Method questions beyond this are a bundle read at question time, not context to carry or narrate back to him." | keep-with-note | Same content rule, loaded every session. |
| memory/feedback_orderflow_leads_structure_breaks_ties.md | 26 | do not narrate | "do not narrate the letter's regime frame unasked." | keep-with-note | Content rule for live tape reads (Steve 2026-08-21). |

Zero instructions matching "hold (all) findings", "final response only", "no commentary between", "no progress updates", "silent until", "no interim", "say nothing until". The nearest phrase, "silent until the day of expiry", is in the archived memory index (records section) and was superseded on 2026-08-17 by the live MEMORY.md line 21. The opposite direction exists: `.claude/skills/drill-coach/SKILL.md:59` tells the coach to "narrate the beat that just fired" — pro-narration, no action.

### Family 3 — verbosity dampers (flag only)

| file | line | pattern | surrounding instruction | proposed action | note |
|---|---|---|---|---|---|
| CLAUDE.md | 23-24 | length it needs | "Answer the question asked, at the length it needs" | keep | House style, quoted from Steve. |
| CLAUDE.md | 26 | one line | "`[ALERT]`, one line." | keep | Alert format contract. |
| CLAUDE.md | 27-28 | a few lines / one sentence | "Decide, build, report in a few lines. When something truly needs him: one sentence with a recommended answer he can accept in a word" | keep | House operating rule. |
| CLAUDE.md | 131-134 | length it needs / no engagement filler | tone_preference: "Answer the question asked, at the length it needs. … Numbers with just enough context to read them; no engagement filler." | keep | House style. Matches the migration guide's own recommended phrasing ("length the question needs") rather than a numeric cap. |
| .claude/rules/hard-boundaries.md | 8-9, 11 | length it needs / one line | "Answer the question asked, at the length it needs. … flagged `[ALERT]`, one line." | keep | Duplicate of CLAUDE.md, loaded every session. |
| .claude/agents/strader.md | 41 | Terse / No preamble | "**Output style:** Terse. Tables over prose. Numbers speak. No preamble." | keep-with-note | 5.1 is already low-preamble and terser in summaries; "Terse" compounds that. Flag only; whether this file even loads as a subagent is doubtful (see family 1 note). |
| .claude/skills/strader/daily-pnl-summary/SKILL.md | 39 | Minimize words / No preamble | "Minimize words. Use tables, not paragraphs. Numbers speak. No preamble." | keep-with-note | Scaffold boilerplate, identical in five skills. |
| .claude/skills/strader/entry-signal-evaluation/SKILL.md | 60 | same | same | keep-with-note | |
| .claude/skills/strader/greeks-analysis/SKILL.md | 62 | same | same | keep-with-note | |
| .claude/skills/strader/position-sizing/SKILL.md | 68 | same | same | keep-with-note | |
| .claude/skills/strader/risk-limit-enforcement/SKILL.md | 53 | same | same | keep-with-note | |
| .claude/skills/handoff/SKILL.md | 215 | concise | "Keep summaries concise and actionable" | keep | |
| .claude/skills/tap-in/SKILL.md | 101 | one line | "The reply costs one line — see `docs/a2a/receipt-protocol.md` §2" | keep | A2A receipt contract. |
| memory/feedback_establish_before_abbreviate.md | 13 | terse | "Terse ≠ compressed-jargon; terse means no filler, not no context." | keep-with-note | This is a counterweight to over-terseness; useful against 5.1's denser prose. Same text in `knowledge/establish-before-abbreviate.md:14`. |
| knowledge/spell-out-bead-references.md | 14 | terse | "Terse-with-jargon reads as noise; terse-with-plain-language reads as signal." | keep | Bundle, read at question time. |
| memory/feedback_verify_level_role_before_naming_setup.md | 29 | one line | "state in one line what the level is on the timeframe of the setup" | keep | Read-format contract. |
| memory/feedback_regime_read_commentary_style.md | 11 | one-line / one sentence | "compact tape table (SPX / ES / VIX with a one-line read each), Mancini bias in one sentence" | keep | Records a format Steve liked; prescriptive by example. |

Not counted: `.claude/skills/mancini-parse/SKILL.md:46` ("The reason is not brevity") is an explanation, not a damper.

### Family 4 — effort assumptions and model IDs

| file | line | pattern | surrounding instruction | proposed action | note |
|---|---|---|---|---|---|
| footprint-icm/bin/run_stage.sh | 24 | model ID | `MODEL="${ICM_MODEL:-claude-opus-5}"` | replace | The one live pin. Overridable per call via `ICM_MODEL` (set by `classify.py --model` / `claims.py --model`). No effort, thinking or tool_choice settings exist to migrate. |
| footprint-icm/bin/run_stage.sh | 72 | --model | `--setting-sources "" --tools "" --strict-mcp-config --model "$MODEL"` | harness-change | Goes with line 24; the flag itself is fine on 5.1. See 1b for what else in the call would want a measured check. |
| footprint-icm/bin/classify.py | 122 | model ID | `--model` help: "override the model (default run_stage.sh's, claude-opus-5)" | replace | Doc string mirrors the pin; change together or it lies. |
| footprint-icm/bin/claims.py | 112 | --model | `ap.add_argument("--model")` | keep | Pass-through, no default. |
| .claude/skills/drill-coach/SKILL.md | 16-17 | --model / /model | "Run this session on a capable model — coaching is judgment-heavy … Set it with `claude --model` / `/model`." | keep-with-note | Operator instruction, no ID, no effort level. |
| knowledge/orderflow-mastery-ownership.md | 36-37 | Fable (tier name) | Steve, 2026-08-06, quoted: "I'm going to leave your model level at Fable… I'm going to declare an exception" | keep-with-note | A quoted directive in the bundle, time-bound to the Quant month (tier decision ~Sep 1 per line 40). Names a tier, not an ID. |
| .claude/settings.local.json | 61 | opus-5 | allow rule for `… runbook.mancini.run … --model opus-5 --extraction-json …` | keep-with-note | A permission literal; `--model` there is a label recorded in the parse (`run.py:505-508`), not a model setting. Harmless but a stale one-off allow rule. |

Zero hits for `reasoning_effort`, `effort_level`, `--effort`, `budget_tokens`, `thinking_budget`, `max_thinking`, `ANTHROPIC_MODEL`, `CLAUDE_MODEL`, `subagent_type`, or `model:` frontmatter in any `.claude/agents/*.md` or `SKILL.md`. The word "effort" appears ~40 times as the desk's own Wyckoff term (effort vs effect: `market/orderflow/moves.py:5,74,265`, `tools/effort_event_watch.sh`, `scripts/live_effort_effect.py`, `docs/drills/scenario-catalog.md:124`) — all domain, none a model setting. The mancini runbook's `--model` (`run.py:505`), `parse.py:27 DEFAULT_MODEL = "in-session"`, and `schema.py:117-118` (`deterministic-lists`, `listlevels-backfill`) are provenance labels; `run.py:18` "This CLI calls no model."

### Records, not instructions

Counted so Desk can see they were looked at; none of these steer a model.

| file | family | count | what it is |
|---|---|---|---|
| runbook/mancini/parsed/*.json (untracked, gitignored, 295 files) | 4 | 13 files carry a model ID: 5 `in-session:claude-fable-5`, 2 `in-session:opus-5`, 2 `in-session:claude-opus-5`, 2 `claude-opus-4-8`, 3 `in-session-manual (… ANTHROPIC_API_KEY_DIRECT credit-blocked)`; the rest are `listlevels-backfill` (257), `in-session` (20), `deterministic-lists` (2) | Provenance labels stamped by `run.py`; who read the letter. |
| docs/audits/2026-08-12-code-estate/census.json | 2, 4, 1b | 16 narration-word hits (all "narrative pane"/"narration" purposes), 6 model hits, 3 "anthropic" | Estate audit. Line 7583 and `wiring.json:6` record COO's `pulse-zepos-wrapper.sh` pinned to `claude-sonnet-4-6` — outside this repo. Line 10972 records a COO bun CLI that calls the API via Haiku — outside this repo. |
| docs/audits/2026-08-12-code-estate/{wiring,dead-verdicts,lens-analyses}.json | 2, 4 | 1 + 3 + 3 | Same audit. |
| archive/DaysActivity-*.md (12 files) | 2, 4, 1b | 17 narration-word, 8 model-name, 3 `ANTHROPIC_API_KEY_DIRECT` | Session logs. 08-04 line 73 records the deletion of `runbook/mancini/llm.py` and the API path. |
| docs/plans/2026-08-16-inference-layer-brief.md | 4 | 14 | A plan proposing tiers (Haiku 4.5 / "Sonnet 5 at low effort" / Opus 5 / Fable) and prices; no code implements it. Its effort-level and price assumptions are dated to 2026-08-16. |
| docs/plans/2026-08-24-emitter-restructure-bead-set.md | 2, 4 | 5 + 7 | Bead descriptions; line 12 "Fable-xhigh clearly outperformed Sonnet" — a measurement record naming a Fable 5 effort level. |
| docs/a2a/inbox.md, docs/a2a/*.md | 2, 4, 1b | 5 + 3 + 1 | Ledger rows and memos, incl. the Desk audit ACK at inbox.md:345. |
| docs/reviews/2026-08-29-footprint-icm-trial.md | 4, 1b | 2 | Trial record: "twelve Opus calls", "$0.65-0.70 a day list", `claude -p` on the Pro plan. Cost/rate-limit assumptions are Opus-priced. |
| docs/plans/estimated-mark-path-plan.md:3, docs/research/2026-07-03-orderflow-primitives-research.md:3, docs/measurement/recognizer-acuity-2026-07-06.md:10, docs/plans/youtube-ingestion-plan.md:274 | 4 | 4 | "Fable-grade model", "COO/Fable research subagent", "four parallel Sonnet extractors", "An Opus subagent as second reader" — history or plan. |
| tests/runbook/test_run.py:228,421,435; tests/scripts/test_mancini_backfill_levels.py:126-133; tests/footprint_icm/test_live_lane.py:40,114,131; tests/footprint_icm/test_compare.py:66 | 4 | 10 | Fixture labels (`in-session:claude-fable-5`, `in-session:opus-5`, `claude-opus-4-8`, `claude-opus-5`). `live_lane.py` records the model it finds in the claude-monitor transcript and asserts nothing about its value. |
| docs/retired-rules/trading-intermediary.md:9,23-25; docs/retired-rules/beads-first.md:3 | 1, 3 | 4 | Retired rules ("Terse, Not Passive", "no preamble", "You are …"). Not loaded; `.claude/agents/strader.md` `ruleRefs` still names `trading-intermediary`. |
| intent.yaml:78-84 | 1a source | 2 | Domain-factory profile text that generated `.claude/agents/strader.md` ("You are an opinionated intermediary …"). |
| memory/archive/MEMORY-index-2026-08-17.md:38 | 2 | 1 | "silent until the day of expiry" — superseded 2026-08-17 (live MEMORY.md:21). |
| memory/feedback_answer_asked_no_strategy_advice.md:15 | 2 | 1 | Quotes the former CLAUDE.md "Do not narrate his method back" as history. |
| runbook/README.md:86; runbook/mancini/schema.py:6 | 1b | 2 | Stale doc lines: "The live Anthropic call is injected" and "see llm.TOOL_SCHEMA" — `llm.py` was deleted 2026-08-04 (33b8917). Nothing executes them. |
| tui/POLECAT-BRIEF.md | 4 | 3 | "layout model", "navigation model" — UI, not LLM. |
| ~60 other docs/, knowledge/, scripts/, market/, present/ lines | 2 | — | "narrative", "narrated", "narrator" as prose about drills, videos, panes, or the tape-events work; none an instruction to a model. |

## 1b. Harness compatibility

**Direct API call sites: none.** Evidence, each run over the tracked universe above and repeated on disk with `--exclude-dir` for the seven excluded directories:

- `^\s*(import anthropic|from anthropic)|@anthropic-ai|import Anthropic|new Anthropic|Anthropic\(` — 0 lines (tracked), 0 lines (on disk).
- `anthropic` in dependency files — the only one tracked is `pyproject.toml`; 0 matches. No `requirements*.txt`, `package.json` or lockfile is tracked. `.venv/lib/python*/site-packages` contains no `anthropic*` package.
- `api\.anthropic\.com|anthropic\.com/v1|x-api-key|anthropic-version|anthropic-beta|ANTHROPIC_API_KEY` — 4 lines, all history: `archive/DaysActivity-2026-07-21.md:11`, `-07-30.md:17`, `-08-04.md:73`, `docs/audits/2026-08-12-code-estate/census.json:10987` (the `ANTHROPIC_API_KEY_DIRECT` path of the deleted `runbook/mancini/llm.py`).
- `messages\.create|messages\.stream|tool_choice|budget_tokens|max_tokens|output_config|tool_runner|\.beta\.messages|"thinking"|thinking=` — 1 line, `market/ingest/databento.py:146` ("interleaved" substring). 0 real hits.
- The bare word `anthropic` (case-insensitive) outside `parsed/` — 7 files, all records (listed above).

**CLI invocations.** One in the repo, and it is the whole model reach:

`footprint-icm/bin/run_stage.sh:71-73`:
```
printf '%s' "$INPUT" | claude -p \
    --setting-sources "" --tools "" --strict-mcp-config --model "$MODEL" \
    --no-session-persistence --system-prompt "$PROMPT" --output-format json > usage.json
```
with `MODEL="${ICM_MODEL:-claude-opus-5}"` (line 24). Callers: `footprint-icm/bin/classify.py:67-78` (once per delivered wake plus once for the window; each call runs in its own process group under `common.STAGE_TIMEOUT_S`, env `ICM_STAGE_TIMEOUT`, default 2400 s, `common.py:72`, and a timeout kills the group and exits 3) and `footprint-icm/bin/claims.py` (`claims` and `planted` runs), both via `footprint-icm/run_day.sh:63-65`, from cron `scripts/cron/footprint-icm-wrapper.sh` at 15:40 CT Mon-Fri (`timeout 3600` on the whole run, heartbeat to `/var/moo/state/strader-footprint-icm.json`, alert on non-zero rc). The trial record says about 12 calls a day. Determination for both files Desk asked about: `classify.py` is not an API call — it shells out to `run_stage.sh`; `run_stage.sh` is a `claude -p` invocation. Settings passed: model only. No effort, no thinking config, no `tool_choice`; tools are disabled outright (`--tools ""`), MCP is disabled (`--strict-mcp-config` with no config), settings files are not loaded, there is no session, so each call is one system prompt plus one user turn and nothing carries between calls. `run_stage.sh:74-86` reads `is_error`, `result`, `usage.{input_tokens,output_tokens,cache_read_input_tokens,cache_creation_input_tokens}`, `total_cost_usd`, `duration_ms` from the CLI's JSON; `classify.py:83-89` also reads `modelUsage` keys. Those are harness JSON fields, not API fields. The lane reads model calls as costless (Pro plan quota, `footprint-icm-wrapper.sh:40-42`); `usage.json`'s dollar figure is list price.

Second reach, outside the repo but on Strader's delivery path: every desk page Strader renders goes through COO's `tmuxMOO/bin/desk-html.sh`, whose plain-words gate `desk-translate.py:1011` runs `claude -p --model MODEL --tools "" --setting-sources ""` with `MODEL = os.environ.get("DESK_TRANSLATE_MODEL", "sonnet")` (line 74) — an alias, not a versioned ID. `scripts/cron/postmortem-wrapper.sh:22-34` and `footprint-icm-wrapper.sh:44-57` append `~/.local/bin` to PATH specifically so that gate can find `claude`. Not a Strader file; noted so Desk knows the model choice there is COO's.

No other invocation: `tools/`, `deploy/`, `daemon/strader-session.sh` (tmux panes only), and every `/etc/systemd/system/strader-*.service` `ExecStart` (all `.venv/bin/python` or bash scripts) contain no `claude` call. `scripts/cron/corpus-daily-wrapper.sh:26` says "NO CLAUDE SESSION" and is right. The mancini parse path calls no model: `runbook/mancini/run.py:18` and `runbook/README.md:50`; the interpretive leg is whatever interactive session runs `/mancini-parse`, which hands the CLI a JSON via `--extraction-json`, and `--model` is a label.

Per the four items:

1. **Forced tool use** — none. No `tool_choice` anywhere; the one CLI call disables tools. No routing logic depends on a forced tool.
2. **Non-append-only history** — none. `--no-session-persistence`, single turn per call; no code rewrites, trims, summarizes or injects into earlier turns. `runbook/mancini/refresh.py` and `run.py:160-167,641-647` compare stored parse *records* (JSON files), not conversation history.
3. **Cross-model fallback** — none. `ICM_MODEL` is a per-run override, not a retry path; a failed call raises `LaneError` (`classify.py:79-81`) and stops the run.
4. **Client-side compaction trigger tuned for cost** — none. The only cost logic is bookkeeping (`classify.py:143` sums list-price cost into `run.json`).

What would want a measured check before repointing `run_stage.sh` to `claude-fable-5-1`, stated as facts not proposals: (a) failure detection in the lane is `is_error` only (`run_stage.sh:78`); `checker.check_lines` returns `ok = not failures` (`checker.py:130`), so an empty `result` passes with zero LABEL/CLAIM lines and `classify.py:112-114` only logs failures — a refusal or blank reply would read as a clean run. (b) `tests/footprint_icm/test_run_stage.py` and `test_model_stages.py` use a stub `ICM_RUN_STAGE` and assert on the folder-bounding refusals, not on the model; nothing pins `claude-opus-5` in tests. (c) Cost and rate-limit statements in `docs/reviews/2026-08-29-footprint-icm-trial.md:8,65` and `footprint-icm-wrapper.sh:40-42` are Opus-priced; whether Fable 5.1 is drawn from the same Pro-plan quota is not something this repo records and was not verified here. (d) each model call is capped at 2,400 s (`ICM_STAGE_TIMEOUT`, `common.py:72`, set today after `claude -p` outlived its shell by 13 minutes on 09-02/09-03 per `footprint-icm-wrapper.sh:36-38`) and the wrapper caps the whole run at 3,600 s (`footprint-icm-wrapper.sh:65`); with about 12 calls a run, the whole-run bound is the binding one, so 5.1's longer turns fit only if the calls average under ~5 minutes. (e) Steve's 2026-08-06 directive ("leave your model level at Fable", `knowledge/orderflow-mastery-ownership.md:36-37`) was scoped to the Quant month ending ~Sep 1 — the interactive-session model is his to set and is not pinned in any file.

## Observations

Observations only; no per-agent model or effort defaults and no doctrine changes are proposed.

- The repo has none of the 5.1-relevant workarounds the migration guide names ("hold all findings", "don't narrate", "never use bullets", "no bold", numeric word caps, "think step by step", prefill). The "do not narrate his method" rule is about *what* to say, not *when*; it should survive a 5.1 switch unchanged. The length rules are phrased qualitatively ("at the length it needs"), which is the form the guide recommends over numeric caps.
- Two things in the estate push the same direction 5.1 already leans: `.claude/agents/strader.md:41` "Terse" plus five scaffold skills' "Minimize words … No preamble", and the CLAUDE.md desk-page rule. On 5.1 the observable risk is not over-formatting but final messages that are shorter than Steve's "he learns by watching the parts move" needs, and denser prose (guide: "longer sentences, fewer paragraph breaks"). `memory/feedback_establish_before_abbreviate.md:13` ("terse means no filler, not no context") and `knowledge/spell-out-bead-references.md` already say the right thing in the right direction; they are the lines to keep visible.
- Emphatic imperative style (`MUST`, `NEVER`, `Do NOT`) is common in loaded text: `.claude/hooks/scripts/session-start.sh:42-46` ("You MUST run /tap-in … Do not skip this."), `.beads/PRIME.md:66-75`, `AGENTS.md:17`, `.claude/agents/strader.md:37-38`, `.claude/rules/hard-boundaries.md`. The guide's caution is that current models take emphasis literally and it is a dated over-triggering fix on prompts that were written for older models; here most of it guards real gates (orders, Schwab, commit hygiene) and reads as intentional. Flagged, not proposed.
- `AGENTS.md:65,90` (beads boilerplate: "Do not run git commits, git pushes … unless explicitly asked") contradicts `CLAUDE.md:120-124` (commit and push without asking). CLAUDE.md and PRIME.md win by their own precedence text; the conflict is a standing reconcile-on-read for every session regardless of model.
- `.claude/agents/strader.md` is domain-factory output from April: its frontmatter is not Claude Code's subagent schema (`name:`/`model:` absent), its `tools:` list names an `mcp__tradingview__*` server the memory says does not exist, and its `ruleRefs` point at a retired rule. Whether it is loaded at all was not measured. Any Fable 5.1 model pin per agent would have to be added here, and there is currently none.
- The five `.claude/skills/strader/*/SKILL.md` files are unfilled scaffolds ("(Define structure and format here)") carrying the only repeated output-style boilerplate in the estate, each with a duplicated line. They are the least load-bearing prompts in the repo.
- Duplication of the same rule in three loaded places (CLAUDE.md:24, PRIME.md:74, fly-doctrine.md:45 for "don't narrate his method"; CLAUDE.md:23-24 and hard-boundaries.md:8-9 for "length it needs") is deliberate per `fly-doctrine.md:11-15` ("a constraint that only binds when retrieved does not bind"). The guide counts duplicated rules as reconciliation cost on the model; the repo's own reasoning for it is on record and was not re-litigated here.
- The two footprint-icm system prompts (`20-classify/prompt.md`, `40-compare/prompt.md`) are the only prompts that will run under a switched `--model`. They are line-grammar contracts enforced by code, cite-or-UNSOURCED, no chat-style rules, no examples. They are the kind of prompt the guide calls "fragile operations keep exact scripts" and look portable as written; the checker is what needs the measured empty-result check above.
- Stale but harmless: `runbook/README.md:86` and `runbook/mancini/schema.py:6` still describe the deleted `llm.py` API path; `.claude/settings.local.json:61` still allows a one-off `--model opus-5` command from 2026-08-03.
