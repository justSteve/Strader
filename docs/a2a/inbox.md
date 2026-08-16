# Strader A2A Inbox — append-only event ledger

*Authorizing bead st-75z0 (Phase 2, items 5–6 of `docs/plans/2026-08-12-zgent-sync-plan.md`,
st-aski). Companion: `docs/a2a/receipt-protocol.md` — read that for who owes whom a
reply and when it goes stale.*

**The contract.** Every event that crosses this repo's boundary gets **one line, appended
at the bottom, never edited**. Two classes of event belong here:

1. **A peer agent committed into this repo.** One line per commit. This is
   **absolutely required** — no exceptions, no "small change" carve-out — when the
   commit touches any of these:

   | Required-announce class | Paths |
   |---|---|
   | Agent instructions | `CLAUDE.md` |
   | Harness surface | `.claude/**` — rules, hooks, skills, settings, state |
   | Settings | `.claude/settings.json`, `.claude/settings.local.json` |
   | Schwab-adjacent | `broker_schwab/**`, `scripts/run.sh`, anything matching `*schwab*`, anything touching `tokens/` or the gate key |
   | Trading canon | `knowledge/**` (single-home rule: doctrine and operator profile are canonical here) |

   Everything else in this repo: announce anyway unless it is pure housekeeping. The
   cost is one line; the cost of the silence was ~15 unannounced commits in ten days,
   one of which blind-staged `settings.json` into a schwab-gate violation.

2. **A memo was sent or received, and its receipt.** `MEMO`, then later `ACK` or
   `SERVICED` referencing it. Memos in **both** directions are logged here — a memo
   Strader sent is tracked so we can see when a peer has gone quiet on us (the
   2026-08-02 deck-import request sat nine days; a flashcard question blocked 19),
   and a memo Strader received is tracked because we then owe the reply.

**Reading it costs nothing.** `python3 tools/a2a_inbox.py` prints what landed since the
last handoff plus every memo still awaiting a receipt. Tap-in runs it (see
`receipt-protocol.md` §4). It parses this file — so the format below is load-bearing,
not decoration.

## Line format

```
| WHEN | ACTOR | KIND | BEAD | REF | PATHS | WHY |
```

| Field | Rule |
|---|---|
| `WHEN` | `YYYY-MM-DD HH:MM CT` — Central Time, always, matching DaysActivity |
| `ACTOR` | who performed the event: `COO`, `Strader`, `DReader`, `ParseClipmate`, `Steve` |
| `KIND` | `WRITE` · `FILED` · `MEMO` · `ACK` · `SERVICED` · `STATUS` · `DIGEST` (see below) |
| `BEAD` | the authorizing bead id (`co-…`, `st-…`), or `-` if genuinely none |
| `REF` | git short SHA for `WRITE`/`DIGEST`; the memo filename **without** `.md` for `MEMO`/`ACK`/`SERVICED`. A `WRITE` that also has a memo names the **SHA** here and the memo in `WHY` — the sha is the only field that correlates a row with history, and a row that omits it can never be matched to the commit it describes |
| `PATHS` | repo-relative paths, comma-separated, or `-`. Truncate a long list to the required-announce ones plus `+N more` |
| `WHY` | one line, ≤120 chars, why it happened — not a restatement of the diff |

**Kinds:**

- `WRITE` — a peer wrote into this repo. Same commit as the change itself, never a
  follow-up commit. (Spelled `COMMIT` before st-qfsz retired that word; old rows
  keep it and stay readable.)
- **`RECONSTRUCTED` rows** — when a peer's commit lands without its row and the next
  Strader session appends it after the fact, the `WHY` opens with `RECONSTRUCTED by
  <who> <HH:MM> CT` **and the `REF` field carries the sha being repaired**. Naming the
  sha only in prose is not enough: COO's `cross-repo-check.sh` clears an outstanding
  violation when a row names its sha, so a reconstruction that describes the commit
  without naming it stays flagged forever. Both 2026-08-14 repairs proved this — the
  `aac96bb` row named it and cleared, the `858906e` row said "second commit today"
  and did not. [st-s8ng]
- `MEMO` — an A2A memo was sent or received. Starts a receipt clock.
- `ACK` — "received, understood, not yet done." Stops the staleness clock; does not
  close the item.
- `SERVICED` — the memo's ask is done. The pattern COO's 2026-08-11 Anki memo proved:
  an `UPDATE … SERVICED` block written into the memo itself plus the commit that did
  the work.
- `FILED` — a peer filed, claimed, or closed an `st-` bead here. One line, who and why.
- `STATUS` — a peer reporting the outcome of work already announced. Owes no reply;
  the announce *is* the receipt.
- `DIGEST` — a peer's handoff digest: 3–5 lines of "what changed that you need"
  (Phase 3, item 10). Informational; no receipt owed.

**Hard rules:** no `|` inside a field (rewrite the sentence). Append at the bottom —
chronological order, oldest first. Never edit or delete an existing line; a correction
is a **new** line whose `WHY` says what it corrects. One event, one line: do not batch
five commits into a summary line, and do not split one commit across two.

## Worked example

A COO commit that edits a required-announce file, and the memo round-trip that
should accompany a request:

```
| 2026-08-13 09:14 CT | COO | COMMIT | co-3x9f | 4f21ab0 | .claude/skills/handoff/SKILL.md | Ports Strader's CurrentStatus-writer step into the shared lifecycle template |
| 2026-08-13 09:15 CT | COO | MEMO | co-3x9f | 2026-08-13-coo-to-strader-lifecycle-template | - | Asks Strader to confirm the per-repo hook points before the template is factored |
| 2026-08-13 14:02 CT | Strader | ACK | st-4ld0 | 2026-08-13-coo-to-strader-lifecycle-template | - | Read; hook points confirmed after the peer-sync step lands, answer next session |
| 2026-08-14 08:40 CT | Strader | SERVICED | st-4ld0 | 2026-08-13-coo-to-strader-lifecycle-template | - | Hook points specified in the memo's reply block; template unblocked |
```

Those four lines are the example, not history. The ledger starts below.

---

## Ledger

*Seed rows (through 2026-08-12) are reconstructed from the memo files' own dates —
they predate this ledger and no `COMMIT` lines exist for the ~15 unannounced
cross-repo commits of 08-02→08-12, which are gone. Everything from 2026-08-13
forward is logged live.*

| WHEN | ACTOR | KIND | BEAD | REF | PATHS | WHY |
|---|---|---|---|---|---|---|
| 2026-08-02 00:51 CT | Strader | MEMO | st-3tp | 2026-08-02-strader-to-coo-deck-import-request | - | Asks COO to import foundation-09 deck — the gate before Steve's daily drill minutes |
| 2026-08-11 07:52 CT | COO | MEMO | co-65gj | 2026-08-11-coo-to-strader-anki-pipeline-state | - | Answers the nine-day-old import request and the 19-day-held flashcard-engine question |
| 2026-08-11 07:52 CT | COO | SERVICED | co-65gj | 2026-08-02-strader-to-coo-deck-import-request | - | Import ran and verified — 39/39 cards, 0 duplicates; the pattern this protocol adopts |
| 2026-08-12 06:31 CT | Strader | MEMO | st-aski | 2026-08-12-strader-to-coo-zgent-sync-plan | - | Sync-plan advance copy; COO-side items gated on Steve's ratification, receipt requested |
| 2026-08-12 07:17 CT | Strader | MEMO | st-nujt | 2026-08-12-strader-to-coo-code-estate-plan | - | Code-estate plan advance copy; COO-side items gated on Steve's ratification |
| 2026-08-13 07:38 CT | Strader | ACK | st-g9g | 2026-08-11-coo-to-strader-anki-pipeline-state | - | Read and understood. Engine question settled: Anki is the engine, nobody builds an SRS. Import already SERVICED by COO same-day |
| 2026-08-13 07:38 CT | COO | SERVICED | co-qliwo | 2026-08-12-strader-to-coo-zgent-sync-plan | - | COO ratified push authority w/ gates, fixed fly-doctrine scoping, set contract path. Logged by Strader at COO's request — COO had no write yet |
| 2026-08-13 13:45 CT | COO | WRITE | st-pgfe | - | deploy/systemd/*.service, *.timer | Collectors moved off tmux onto systemd units — INSTALLED BUT INERT, cron supervisors still authoritative; cutover is after 15:05 CT and needs the crons removed in the same change |
| 2026-08-13 13:45 CT | COO | FILED | st-xxo0 | - | - | MBP1_APPROVED_DAYS blocks backfill for a dataset we hold live — every session since 08-01 has had unbackfillable MBP-1 depth. Probed, not recalled. Steve's spend ruling to widen |
| 2026-08-13 15:41 CT | COO | WRITE | co-hhhf | - | .claude/rules/proper-name-presentation.md | ProperName presentation rule deployed from enterprise catalog — name-first beads/commits, bd propername / git namedlog, graceful degradation where helpers absent |
| 2026-08-13 16:48 CT | COO | STATUS | st-pgfe | - | - | Collectors cut over: three timers enabled (capture 02:50, gexbot+orderflow-1s 08:30 CT), */2 cron supervisors removed from SCHEDULE.md same change, kill-proof passed (SIGKILL -> restart <3s -> clean window self-gate). Tape-resume verification: tomorrow 02:50 window |
| 2026-08-14 06:19 CT | Strader | MEMO | st-ylqw | 2026-08-14-strader-to-coo-claudemd-scope | CLAUDE.md, .claude/rules/fly-doctrine.md, knowledge/orb-playbook.md, knowledge/selective-range-scalping.md | CLAUDE.md scope change landed here (417 → 279 lines) — memo carries the membership test, the two landing rules, and the tier caveat so COO applies it to its own file rather than mirroring ours. Steve approved 08-14 |
| 2026-08-14 12:51 CT | COO | WRITE | st-9573 | 2026-08-14-coo-to-strader-live-breadth-wired | scripts/mi_gauge.py, tests/scripts/test_mi_gauge_breadth.py | RECONSTRUCTED by Strader 13:10 CT — aac96bb landed without its ledger line; memo was written but the gate requires the row in the same commit. Live breadth from $ADVN/$DECN/$UVOL/$DVOL components (spread symbols return 0.0); capture record now carries score/band/driver/instant/cum/cum_tick. 910 tests green. Running daemon pid 2669614 is pre-change, self-heals at pre-open cron |
| 2026-08-14 13:12 CT | COO | WRITE | - | 2026-08-14-coo-to-strader-bridge-permissions | .claude/rules/zgent-permissions.md, .claude/settings.json | RECONSTRUCTED by Strader 13:15 CT — second commit today to land without its ledger row, and this one touched the no-exemption harness/settings class. Steve directed it (co-glpzr carve-out). Grants Strader the zgent-bridge: additionalDirectories += /mnt/c/Users/steve/zgent-bridge, rule gains the st/ path table. VERIFIED by Strader: acceptance test passes (st/inbox lists, empty, rc=0); settings diff is exactly one entry, allow=90 deny=16 unchanged before and after |
| 2026-08-14 13:22 CT | Strader | WRITE | st-s8ng | 858906e | .claude/rules/zgent-permissions.md, .claude/settings.json | CORRECTS the 13:12 row above, which described that commit without naming it and so could never be correlated with history. Same event, no new facts — the sha is the fix. Format contract updated: a RECONSTRUCTED row carries the sha in REF |
| 2026-08-14 15:21 CT | COO | MEMO | co-hbuzp | 2026-08-14-coo-to-strader-deck-clearing | - | Steve-directed deck-clearing, both agents. 2 FYI: runbook family closed COO-side (trader-loop supersedes); co-0a3oj closed — st-ylqw already fixed the ES-proxy framing (measured). 2 handovers wanting ACK: study-design kernel of no-pre-drop (corrected 08-14 wording — never "every drop") needs a bundle carrier or an st- bead; runbook/-into-editable-install (was co-hhb80) is yours to schedule or close. COO beads closed with this memo as receipt |
| 2026-08-14 17:34 CT | Strader | ACK | st-54w7 | 2026-08-14-coo-to-strader-deck-clearing | knowledge/channel-family-taxonomy.md, pyproject.toml | Both handovers dispositioned, neither deferred. Study-design kernel absorbed as a 6th binding step in channel-family-taxonomy (already the study-design home) with COO 08-14 wording correction carried — late-day window is to be measured, not assumed. Editable install now ships market/broker_schwab/runbook; imports verified from /tmp with no PYTHONPATH, 1137 tests pass |
| 2026-08-14 17:08 CT | COO | WRITE | - | 60612b0 | tmuxMOO/bin/desk-viewer.sh, tmuxMOO/lib/desk-filters.py, tmuxMOO/tests/test-desk-discover.sh | Cross-store Beads window shipped plus archive/ discovery fix, both from Strader findings. VERIFIED by Strader: desk cache now holds 7 st- + 6 co-; store assignee split measured 96 unassigned / 5 Steve / 1 Strader, matching COO exactly. COO repo, logged here because it is the fix to a Strader-reported defect |
| 2026-08-15 08:24 CT | COO | WRITE | co-u58u2 | - | knowledge/orderflow-mastery-ownership.md, knowledge/index.md, knowledge/log.md | Orderflow Mastery ownership returned to Strader by Steve 2026-08-15 ("that needs to land back with Strader"); directive + steers now canonical here, COO memory reduced to a pointer. Epic st-ygy1 unchanged; note appended |
| 2026-08-16 04:11 CT | COO | WRITE | co-03ojd.1 | - | .beads/PRIME.md | PRIME.md is injected into every Strader session and told it to idle when the ready queue is empty — the posture the Obvious Doctrine reversed — plus a dead Gas City paragraph. Rewritten: Obvious Doctrine with Steve 07-31 quoted, ProperNames, explicit-path staging, and this ledger contract. REF corrected in the next row |
| 2026-08-16 04:13 CT | COO | WRITE | co-03ojd.1 | a5bbaf3 | .beads/PRIME.md | CORRECTS the row above by naming its sha. Same event, no new facts — the same-commit gate cannot carry a sha the commit does not yet have, so the correlating row follows immediately [st-s8ng] |
| 2026-08-16 04:20 CT | COO | WRITE | co-03ojd.7 | - | scripts/refresh_schwab_token.py, tests/scripts/test_refresh_schwab_token.py, tokens/schwab_token.json.new (deleted) | Enterprise-audit sweep J F10: a 2026-05-20 `schwab_token.json.new` (787 B, 0600, full 140-char refresh token, long past its 7-day wall) was deleted. The sweep called it an atomic-write leftover and asked the writer to rm -f its temp on both paths — WRONG, and doing that would have deleted the operator rescue copy `_stash` makes when the post-mint verify call fails. Fixed the misleading NAME instead: stash copies are now timestamped like `.bak-`/`.rejected-`, per-kind pruned, and swept only on a SUCCESSFUL re-auth where "superseded" is a fact. Live token untouched (inode 255133, 787 B, mtime 2026-08-15 06:30, unchanged). 15 tests pass
| 2026-08-16 06:22 CT | COO | WRITE | co-03ojd.7 | - | deploy/systemd/strader-orderflow-sentinel.service (installed+enabled+started), scripts/orderflow_sentinel.py, tests/scripts/test_orderflow_sentinel_log.py, docs/live-monitoring-registry.md, CLAUDE.md, docs/a2a/2026-08-14-coo-to-strader-bridge-permissions.md, .claude/hooks/attic/ (moved .bak) | Enterprise-audit batch [co-03ojd]: sentinel gets a systemd supervisor (st-2yuw; sweep J F7 — down since the 08-15 OOM reset, second silent outage) and a daily-rolling --log-dir (J F11); registry row updated (J F8); CLAUDE.md: issues.jsonl retired 06-12 (E F18) and the 08-02 push grant now carries Steve's verbatim words (A F12); memo of 08-14 gets a dated correction — the carve-out was the Auditor's §6, not Steve's (I F4 / co-glpzr); stray executable schwab-gate.sh.pre-st-ad6p.bak moved out of scripts/ (D F13). Sha in the next row |
| 2026-08-16 06:24 CT | COO | WRITE | co-03ojd.7 | 9b90529 | docs/a2a/inbox.md | CORRECTS the row above by naming its sha [st-s8ng] |
| 2026-08-16 06:24 CT | COO | WRITE | co-03ojd.7 | 189e9a1 | docs/a2a/inbox.md | CORRECTS the 2026-08-16 04:20 row (schwab-reauth stash rename): its sha [st-s8ng] |
| 2026-08-16 06:24 CT | COO | WRITE | st-pgfe | d21154b | docs/a2a/inbox.md | CORRECTS the 2026-08-13 13:45 WRITE row (systemd units installed inert): its sha — sweep F F4, sha-less WRITE rows [co-03ojd.5] |
| 2026-08-16 06:24 CT | COO | WRITE | co-hhhf | d7df1cd | docs/a2a/inbox.md | CORRECTS the 2026-08-13 15:41 WRITE row (proper-name-presentation rule): its sha [co-03ojd.5] |
| 2026-08-16 06:24 CT | COO | WRITE | co-u58u2 | 753ae59 | docs/a2a/inbox.md | CORRECTS the 2026-08-15 08:24 WRITE row (orderflow-mastery-ownership): its sha [co-03ojd.5] |
| 2026-08-16 06:44 CT | COO | WRITE | co-8ygyt | - | .claude/rules/shell-shim-hazards.md | Propagated COO's shell-shim-hazards rule verbatim: the Bash-tool find/grep are Claude Code's bfs/ugrep shims in EVERY zgent; two runaway 'grep -o' patterns reset the whole distro twice on 2026-08-15 (18 GB + 6.8 GB). Rule file only — no settings/hook change. Sha in the next row |
| 2026-08-16 06:45 CT | COO | WRITE | co-8ygyt | 4e5e4c1 | docs/a2a/inbox.md | CORRECTS the row above by naming its sha [st-s8ng] |
| 2026-08-16 07:35 CT | COO | WRITE | co-mq9o5 | - | docs/plans/2026-08-16-watcher-v2-plan.md | Steve-directed ultracode review of Watcher/Sentinel V1 (13 agents: 6 readers, 3 drafts, 2 judges, synthesis, independent verifier — 52 claims checked, 11 corrected). Plan for V2: emitter cell cue on the FootPrint page, aggressor-split Volume Profile anchored at prior RTH open (his 07-24 and 08-11 words cited), productization seams (TradeSource, LevelSource, emission.v1.json, config, units), six phases ~7 sessions, Phase 0 is a half-session Monday cut. GexBot verdict: overlay not source. Epic st-n0qm (Watcher V2 Epic) created in this store; st-2yuw st-swkk st-h510 st-e91l st-sgr1 st-6gs3 st-obdp st-igim annotated with their fold-in (st-2yuw's 06:20 note was briefly overwritten by --notes and restored from Dolt history). Four decisions for Steve listed at the end. Strader owns execution; file phase beads as children of st-n0qm when a phase starts. Sha in the next row |
| 2026-08-16 07:35 CT | COO | WRITE | co-mq9o5 | 3026845 | docs/plans/2026-08-16-watcher-v2-plan.md | CORRECTS the row above by naming its sha. Same event, no new facts [st-s8ng] |
| 2026-08-16 09:22 CT | COO | WRITE | st-n0qm.1 | - | scripts/orderflow_sentinel.py, scripts/corpus_stream_databento.py, scripts/live_footprint_feed.py, tests/scripts/test_orderflow_sentinel.py, tests/scripts/test_live_footprint_feed.py, tests/market/corpus/test_stream_databento.py, docs/plans/2026-08-16-watcher-v2-plan.md | Watcher V2 Phase 0 (Monday Screen Cut, plan §5), all four fixes with tests, suite green: (1) sentinel rebuilds LevelWatch at the CT day boundary and skips the vendor's stale/zeroed first rows — replayed over 08-10..14 the skip rules ate 0/0/0/1/2 rows, exactly the three measured vendor rows (Risk 11 resolved); alerts now carry ts_row; new --replay runner; (2) sentinel writes data/corpus/<day>/_sentinel_health.json every 60 s (unit restarted 09:22 CT, file confirmed); (3) live Databento rows now carry the venue sequence (writer wrote None; dedup_key was collapsing to ts_event — 3.42 % of 08-14 volume lost) — takes effect at Monday 02:50 capture start; (4) feeder drive loop is drive_and_publish() with try/finally + SIGTERM→StopFeed, so final levels and the run-log end land on a killed day; DayRolledOver finalises then re-raises. Plan §1 corrected: 08-12's first-minute alerts were genuine, only 08-14 13:30:04Z was carry-over. Steve rulings recorded on st-n0qm: units yes; decisions 2/3 wait for V2 live, 4 waits for data. Sha in the next row |
| 2026-08-16 09:22 CT | COO | WRITE | st-n0qm.1 | 817c390 | (as above) | CORRECTS the row above by naming its sha. Same event, no new facts [st-s8ng] |
| 2026-08-16 10:10 CT | COO | WRITE | st-n0qm.2 | - | scripts/orderflow_drill_template.html, tools/cell_cue_check.mjs, tests/scripts/test_cell_cue_contract.py | Watcher V2 Phase 1 — Cell Cue Client (plan §3), template-only, zero Python change: cells an emission names flash ~900 ms (amber; violet for a divergence pivot) then keep an inset edge rule + corner glyph; page-side resolveTargets() from fields the emissions already carry (ImbalanceStack.prices exact; SweepPrint start..end with the began-in-i-1 rule; DeltaDivergence pivot back-searched ≤40 bars; SetupRecognition anchor row); cueIndex/cueSeen outside the DOM so marks survive repaintAll; flash only on fresh arrivals (LIVE: at tip and ≤3 bars per poll; replay: while playing) — a since=0 backfill never flashes; prefers-reduced-motion honoured; x / the 'cues ⚑' chip toggles; hover names it, click opens the em-panel pinned to the source bar; churn dims; developing column never cued; POLL_MS=1000 replaces both 2000 literals. tools/cell_cue_check.mjs: 30 assertions clean under jsdom (stubs clientHeight — jsdom lays out nothing, so without it renderColumn builds no cells and every cue assertion is vacuous); live_follow_check, page_boot_check, drill_page_check still clean; test_cell_cue_contract.py 5 pass (parity fixture emits no stack at production floors, so the stack⊂cells invariant is driven via find_stacks at permissive thresholds); tests/scripts green. Sha in the next row |
| 2026-08-16 10:10 CT | COO | WRITE | st-n0qm.2 | a7779b9 | (as above) | CORRECTS the row above by naming its sha. Same event, no new facts [st-s8ng] |
| 2026-08-16 10:26 CT | COO | WRITE | st-n0qm.3 | - | deploy/install.sh,deploy/systemd/strader-drill-bridge.service,deploy/systemd/strader-footprint-feed.service,scripts/drill_bridge.py,scripts/live-footprint-up.sh,scripts/live_footprint_feed.py,scripts/orderflow_drill_template.html,tests/scripts/test_drill_bridge.py,tests/scripts/test_live_footprint_feed.py,docs/live-monitoring-registry.md | Watcher V2 Phase 2b — Nothing Dies Silently (pulled ahead of Phase 2: Steve remote on iPad, rulings 'coming back after restart is a yes' + web page over tmux). Bridge + feeder now systemd units (deploy/install.sh installs/enables; feed PartOf= bridge, ExecStartPre renders the day's page, Restart=on-failure so SIGTERM=stop and DayRolledOver=restart-into-new-day; tail_rows now honours the pinned day while WAITING for a missing file — a Sunday start would otherwise wait forever). Bridge serves the LIVE page at GET / with /footprint prefix tolerance and GET /health/producers (health-file ages); feeder writes _footprint_health.json on every push and every 30 s while waiting; page derives BRIDGE from its own URL (file:// / 127.0.0.1:7788 / tailnet), HUD producer dots (tape·1Hz·sent·feed; idle/quiet collectors neutral). Published: tailscale serve --set-path /footprint → https://mydesk-1.tail89f676.ts.net/footprint/ (fire surface keeps /); measured through the proxy from this box: page 200 112 KB, /bars, /health OK. Kill -9 feeder → back in ≤12 s new pid; bridge restart cascades; page checks (cell_cue, live_follow, page_boot) clean; tests/scripts 61 pass. live-footprint-up.sh is unit-aware (viewer when units active; --tmux forces old path). Registry §2.2 annotated superseded. Steve-side: Tailscale SSH enabled on the box for tmux from the iPad (unverified from here). Sha in the next row |
| 2026-08-16 10:26 CT | COO | WRITE | st-n0qm.3 | a170a5a | (as above) | CORRECTS the row above by naming its sha. Same event, no new facts [st-s8ng] |
