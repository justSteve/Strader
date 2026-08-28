# DaysActivity - 2026-08-28

## 13:52 - Session Handoff [Mancini Richer Extraction — all four stages]

**Summary**: Parsed the Friday 2026-08-28 plan (63 levels, 12 commentary, clipboard loaded), then built all four stages of the st-9r51 richer-extraction plan; three of the four corrected a premise in the plan that did not survive measurement against the full 380-letter corpus, since the plan was written against 12.

**Open Work**:
- st-9r51 stays in progress only for `precondition` as a nested field — measured at 6.1% of rich callouts and explicitly NOT built, because the information is already addressable as trigger-kind levels (today's parse carries 7632 and 7663 that way). Reopen if the sentinel wants the structure.
- st-rgm8 (P2, new) Mancini Level Alerts — the sentinel's watch set is `("z_mlgamma","z_msgamma")` only; nothing fires on the plan levels even though `data/level_state/current.json` now carries callout/attribution/intent/conviction/setup. Scoping is the bead; note `intent=offered` is a short Mancini publishes but does not take, and Steve is long-premium-only.
- st-g8mq (P2, new) Bridge Log Provenance — any process can write `data/drill-bridge/state-<day>.jsonl`; 24 phantom `bridge_start` rows today read as the live bridge flapping during RTH.
- Steve reported seeing no alerts today. Backend verified healthy at every hop (35 alerts, sentinel → jsonl → bridge → page, 0 post failures, basis fresh 40/40 bars). Unresolved on the browser side: the alert layer is a persisted `s` toggle in localStorage (`oflow-sent-on`), unreadable from here. Next session should ask whether pressing `s` fixed it.

**Tried**:
- st-kxnv 08:15 restart branch → first real production exercise fired clean: run row `03:30:58 anchors=0` → `08:15:12 anchors=63`, feeder pid 118456 at 08:15:21. Bead closed. (08-27's apparent pass was a build-time restart, not the branch.)
- `callout_verbatim` as the plan's bool → dead field. The whole callout is a contiguous quote in 4 of 269 (1%), median longest quoted run 33%. Shipped as spans + `quoted|mixed|gloss` instead.
- Plan's segmentation markers (`Bull case tomorrow`, unanchored) → lands on Mancini's QUOTED PRIOR LETTER in 201/353 letters (57%), because he reprints his previous edition in the recap and the header is usually weekday-named. Fixed by anchoring on the `Supports are:` ladder — the one marker he never quotes — plus weekday-aware headers.
- Letting the bid-direct paragraph also open the forward region → my own bug, same class as the one the module exists to prevent. It leads in 1 of 355 letters and that one is the quoted prior letter 19,242 chars early. Caught on the corpus sweep, not in review. Anchor is the ladder alone; the shape is a pinned regression test.
- Plan's "every (major) level carries a callout" floor → fires on 100% of days including the best ones (11–22 of 22–30 majors are bare even now). Dropped for the three signals that actually discriminate.
- Reporting prose levels absent from the ladder → false-positived on Mancini's dated anecdotes (7325, five parses in a fortnight). Separator is a calendar date in the same sentence: 11/11 correct on the suppressed side, 26/26 on the warned side.
- Suspected the bridge was flapping every 2 min during RTH (25 `bridge_start` rows) → NOT the live bridge; `/health` still reports the *first* `started`, so the server state object was never replaced. Then guessed my own test suite wrote them; wrong, tests use `tmp_path`. Likely the peer's in-flight replay work.
- Suspected the browser never polled (0 GET lines in the bridge journal) → also wrong; `log_message` routes to `logger.debug`, so my own curl calls did not log either.
- Two store defects found by causing them: blind append doubled the day (3 days already doubled, 1 tripled — st-psoj, fixed and all four repaired), then skip-if-present left stale tags behind a re-tag (fixed with upsert-on-identity, original `ingested_at` preserved).

**Note for the next session**: the `schwab-gate.sh` hook blocks a Bash heredoc whose *text* merely names `runbook/mancini/overnight.py` (it imports `broker_schwab`). Correct fail-closed behaviour, but it means editing that file or listing it in a script must go through the Edit/Write tools, not a shell heredoc. Cost two blocked calls today.

**Files Changed**:
runbook/mancini/attribution.py
runbook/mancini/segment.py
runbook/mancini/completeness.py
runbook/mancini/schema.py
runbook/mancini/validate.py
runbook/mancini/store.py
runbook/mancini/tracker.py
runbook/mancini/overnight.py
runbook/mancini/run.py
runbook/mancini/extraction-contract.md
.claude/skills/mancini-parse/SKILL.md
tests/runbook/test_mancini_attribution.py
tests/runbook/test_mancini_segment.py
tests/runbook/test_mancini_completeness.py
tests/runbook/test_mancini_typed_levels.py
tests/runbook/test_store.py
runbook/mancini/commentary/2026-08-28.jsonl
CurrentStatus.md

---
