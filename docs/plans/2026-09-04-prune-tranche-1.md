# Prune tranche 1 — sequenced from Desk's 2026-09-04 verdict, staged, not executed

**Source:** Desk VERDICT `20260904T153000__Desk__review-verdict-fable-audit-and-legacy-prune`
on `audit/legacy-2026-09-04.md` (st-2opj, 110 rows: 41 keep / 18 archive / 39 delete /
12 fix, 16 unsure). Desk's ruling principle: *an intended architecture nothing has wired
in four months is a plan, not code; a green test with design intent is cheap to keep; a
correction Steve gave that no longer loads is a defect, not clutter.*

## Gates, in order — nothing below runs until all five hold

1. Desk's UPDATE after Steve answers the five items Desk carries (below).
2. COO's SERVICED row on the three routed questions
   (`COO/docs/a2a/2026-09-04-strader-to-coo-three-prune-questions.md`).
3. `git tag pre-prune-YYYY-MM-DD` on the commit before the first move.
   **CLEARED 2026-09-05** — `pre-prune-2026-09-05`.
4. ~~Report to Desk before any archive or delete executes.~~ **Desk relaxed its
   own ordering in the 09-05 15:01 RULING: "Gate 3 is yours: cut `pre-prune` and
   execute. Report to Desk when done."** The report moves after execution. Noted
   rather than silently followed, because it is the verdict's author loosening a
   gate the verdict set, and the tag is now the only thing standing between the
   plan and an irreversible move.
5. Steve sees category counts plus unsure items only — never individual files.

## Sequence

| # | Verdict item | Action | Why this order |
|---|---|---|---|
| 1 | unsure 2 | Relocate the fixtures `tests/test_schwab_gate_hook.py` reads (`scripts/gex_now.py`, `gex_series.py`, `hello_schwab.py`) into a tests fixture dir; run the hook suite (33 green); **then** delete the three scripts | The hook skips a missing file (`[ -f "$PY_FILE" ] \|\| continue`), so deleting first flips two must-BLOCK cases to allow |
| 2 | unsure 3 | Delete the live-parity wrapper | st-hrwe closed won't-do 2026-09-04; never scheduled in three weeks |
| 3 | unsure 4 | Archive the four `scripts/cron/*supervisor*.sh` with their two tests under `_archive/` | systemd timers are the mechanism since 08-13; a manual fallback nobody needed is a plan |
| 4 | unsure 5 | Archive `strader/feeds/__init__.py`; one paragraph on the seam's intent into the architecture doc that describes it | the empty module is not the intent |
| 5 | unsure 14 | Shrink the 23 indexed memory twins to one-line pointers at their `knowledge/` canon page | two drifted bodies (schwab-auth, databento billing) already prove why full copies are a liability |
| 6 | unsure 15 | Re-index the four behavioural corrections cut on 08-17 (`no_manufactured_precedent`, `no_self_confirming_callbacks`, `steve_risk_authority_not_pa_arbiter`, `corrections_persist_immediately`): graduate to `knowledge/` where canon-shaped, else back into `MEMORY.md`. Never delete | Steve's corrections; that they no longer load is the defect |
| 7 | unsure 16 | Archive `runbook/mancini/commentary/2026-05-19.jsonl`, `2026-07-01.jsonl`, `data/calls/` | unless someone names them golden before the tag; git keeps them |
| 8 | the table | The audit's 39 delete and 18 archive rows that stand as dispositioned, plus st-sl1f's 18 re-confirmed files once Steve releases that bead | each with its evidence row in the audit |
| 9 | unsure 9–11 | **AMENDED 2026-09-05 to COO's measurements (gate 2).** (9) **Delete** `.claude/agents/strader.md` + `intent.yaml` — but not for the reason we gave. No COO registry reads them, *and* the harness itself reads `.claude/agents/*.md` in whatever project it opens, so ours is not unread: it declares six `mcp__tradingview__*` tools for a server removed in `63cac42` (2026-05-14). It defines a subagent that cannot work. (10) **`.beads.gate.lock` — UNTRACK, DO NOT DELETE.** Our "empty stray, zero refs" reading was wrong. The `bd` binary carries a `workspacegate` package writing `<gated-path>.gate.lock`; twelve exist across six repos; our two share an mtime to the nanosecond. Deleting makes `bd` write it back. `36f0a81` was still a wide-`git add` accident, so the fix is `git rm --cached` plus a `.gitignore` line. COO's *absence* of one is COO's bug, not our stray. (11) `.env.template` — **fix-in-place, COO holds the edit**; applied 2026-09-05 10:32 CT (four Twilio field names added to the vault-key comment block). | COO authorizes dispositions; (10) reverses ours |

## Keeps — ruled or measured

- **unsure 6** `strader/evaluate/*`, `market/orderflow/regime.py` — Desk: keep.
- **unsure 7** `scripts/fire_server.py` — **keep.** Checked 2026-09-04: execd is loopback-only
  (`BIND_HOST = "127.0.0.1"`, no `/unlock`, no ARM/nonce/FIRE page, no ticket-as-data
  staging); `POST /preview` covers dry-run *pricing*, not the phone-reachable arm-and-fire
  surface. COO's 08-30 CLI v1 roadmap §5 keeps the fire server "until execd stage 3's page
  supersedes it — retiring it is a separate decision with its own review", and st-863b /
  st-bxls (both P1, open) build on it. CI's flask install stays with it.
- **unsure 8** `scripts/orderflow_monitor_up.sh`, `orderflow_alert_fmt.py`,
  `calibrate_oflow_thresholds.py` (rows 27, 30, 43) — **keep, pending st-gk8z.** Measured
  2026-09-04: the sentinel covers **none** of the monitor's five promised event kinds
  (`CVR_SPIKE_UP`, `CVR_SPIKE_DOWN`, `GEX_SPIKE_CALL`, `GEX_SPIKE_PUT`, `TWO_SIGNAL`, off
  the 60 s collector); it emits six level-state kinds on the two major gamma levels off the
  1 Hz leg (`approach`, `zone`, `contested`, `relocation`, `resolved`, `zone_dissolved`).
  Different questions, zero overlap — so the registry's 08-13 blocker resolves to *not
  covered*, and the launcher cannot retire on coverage grounds. `orderflow_hist_sweep.py`
  still imports the monitor's detector unmodified; the runbook says replay is how its
  thresholds get tuned, which is what `calibrate_oflow_thresholds.py` is for. st-gk8z
  carries the real decision: port the five kinds to the 1 Hz sentinel, or drop the promise.

## Gate 2 — CLEARED 2026-09-05 10:25 CT

COO's SERVICED row on the three routed questions landed
(`20260905T102500__COO__github-mcp-answered-and-three-prune-questions-serviced`).
One answer **reverses a disposition of ours** — see step 9 (10) above. Taking a
peer's reversal on its measurement rather than defending our own reading is the
point of routing the questions; recorded here so the change of mind is visible
in the plan and not only in a memo.

## Held for Steve — ANSWERED 2026-09-05 (Desk UPDATE on 20260904T153000; gate 1 cleared)

1. unsure 1 — the 2026-05-17 indicator/entity stratum: **archive** (Decision 2 answered).
2. st-sl1f: **released** — its 18 re-confirmed files fold into step 8; bead closed into this one.
3. unsure 13 — `strader/playbooks/options-premium-harvest.md`: **retain as-is**; one frontmatter `note:` line added so the canon loader's reading of it does not confuse a future session (content untouched).
4. unsure 12 — `knowledge/schwab-auth-pattern.md`: **rewrite to reality** — done 2026-09-05, memory twin collapsed to a pointer in the same step.
5. `.claude/settings.json` patch: **applied 2026-09-05 on Steve's direct word** (st-voc5, commit 9791a83) — TradingView, fetch and checkpoint allows dropped, `gc-mail-stub.sh` deregistered and deleted. Desk's UPDATE asked to hold the `mcp__github__*` line pending COO's answer on the GitHub MCP; it went with the patch on Steve's word and is a no-op either way (no server configured). If COO says adopt, the line returns with the server config in one commit.

Next gate: 2 — COO's SERVICED on the three routed questions.

## Related beads

st-2opj (the audit, open until the tranche executes) · st-6n7e (Thread 1, closed) ·
st-k75z (checker defect, closed `cb19dfe`) · st-gk8z (sentinel port) · st-hrwe (closed won't-do) ·
st-sl1f (Steve's release) · st-568o (ledger attribution, so these receipts count next time).
