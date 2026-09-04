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
4. Report to Desk before any archive or delete executes.
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
| 9 | unsure 9–11 | Per COO's answers: delete `.claude/agents/strader.md` + `intent.yaml` if nothing reads them (measured: nothing in COO code does); delete `.beads.gate.lock` if `bd` does not use it (measured: empty stray swept in by `36f0a81`, zero refs); `.env.template` per COO's field comparison against `strader/config.py` | COO authorizes dispositions |

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

## Held for Steve — Desk carries these with recommendations

1. unsure 1 — the 2026-05-17 indicator/entity stratum (Desk recommends archive; "Decision 2", unanswered since 08-12).
2. st-sl1f — one word releases its 18 files into step 8.
3. unsure 13 — `strader/playbooks/options-premium-harvest.md` (strategy content; contradiction flagged).
4. unsure 12 — `knowledge/schwab-auth-pattern.md` (his canon; Desk recommends rewrite to reality).
5. `.claude/settings.json` patch — dead MCP allows and the `gc-mail-stub.sh` hook (a bead for him to land).

## Related beads

st-2opj (the audit, open until the tranche executes) · st-6n7e (Thread 1, closed) ·
st-k75z (checker defect, closed `cb19dfe`) · st-gk8z (sentinel port) · st-hrwe (closed won't-do) ·
st-sl1f (Steve's release) · st-568o (ledger attribution, so these receipts count next time).
