# DaysActivity - 2026-07-25

## 17:28 - Session Handoff [Runaway Gauge + Cron PATH + Desk Autostart]

**Summary**: Saturday maintenance session. Tap-in surfaced two P1 defects that had gone unread since Friday; both were fixed, tested, committed and pushed, and the cross-repo half was handed to COO as an A2A memo. The MI gauge daemon (PID 177811) had run 27 hours from Friday 09:12 CT into Saturday afternoon with no stop condition, writing dead-market rows into Friday's capture file at one row per minute; the morning Mancini cron had died Friday on `FileNotFoundError: 'az'` because the Azure CLI resolves only through WSL interop and cron's PATH omits it. Two subagents ran the fixes in parallel. Steve killed the daemon and authorized the `remain-on-exit` change, the commits, the push, and the memo.

**Open Work**:
- st-i68 ("Morning Mancini cron fails on cron PATH — Azure CLI not resolvable", P1, in_progress) — the in-repo half is shipped and Monday 07-27 06:30 CT is safe on it alone; closes when COO applies or explicitly skips the wrapper patch proposed in the memo
- st-66u ("Runbook #11 implementation — heartbeat: did pull/parse/gate run before the open", P1, open) — to be widened from "did it run" to also cover *unread alerts*; the 7/24 health alert fired correctly and sat ~19h until the next tap-in read it
- st-3fr ("Strader: MI composite gauge — internals-driven entry/exit scale", P2) — forward-capture sample is now trimmed and trustworthy; calibration work itself untouched this session
- COO owes three answers (memo section "Requested from COO"): apply/adapt the wrapper patch; rule on hoisting PATH composition into `factory/factory.env`; state whether the corpus-cron handover to Strader is near enough (live date 08-01) that the structural fix should land with the migration instead

**Tried**:
- Asserted the tap-in `ps` snapshot was "~50 minutes stale" → wrong; derived the interval from an `11:45Z` log timestamp without reading the clock, on a box running Central. It was seven minutes. Steve called it out. Read the clock, never subtract timestamps by eye — recorded as a corollary in the liveness auto-memory
- First-draft COO wrapper patch used a wholesale `export PATH="…"` replacement → wrong idiom; COO's own `pulse-zepos-wrapper.sh` (lines 23–32) solves the identical cron-PATH problem additively with `export PATH="${GO_BIN}:${PATH}"`. Rewritten append-style (`"${PATH}:${AZ_WBIN}"`), re-verified under `env -i HOME=/root PATH=/usr/bin:/bin` → resolves az 2.83.0. Caught only because the wrapper was read directly rather than trusting the subagent's report
- Subagent reported "mirrored copies" of COO's wrapper at `/mnt/wslg/distro/root/projects/COO/…` that might drift → false. `stat` shows inode 56293 on device 2096 for both paths: one file through a bind mount. Retracted explicitly in the memo before COO could spend time on it. No second copy exists in the distro tree
- Trim of the 7/24 capture had to be run twice → the first trim (435 rows) was re-polluted to 470 because the runaway daemon was still appending during the fix. Kill first, then trim. Re-trim needed no date arithmetic: every polluted row carries a `2026-07-25` timestamp, so a `grep '"ts": "2026-07-24'` filter is sufficient and exact
- tap-in filed st-i68 with the literal title `task` → uncitable in a memo and invisible in `bd propername`. Retitled before writing. Worth watching whether bead-filing from tap-in drops titles generally
- `pytest -q` from `pyproject.toml` addopts plus an explicit `-q` becomes `-qq` and suppresses the pass/fail summary line entirely → use the exit code, or drop the extra `-q`. Cost several confused runs before the count appeared

**Decisions**:
- `remain-on-exit` switched `on` → `failed` (Steve). Before st-5n8 the gauge never exited cleanly so the two settings behaved identically; now that 15:15 CT is a clean exit, `on` would park a dead pane on the desk nightly. The final read is already durable in the capture file
- The caller-side "verify steves-desk is up before presenting" step is **retired** (Steve). The gauge start path now brings the desk up on demand, so callers stop checking. The adjacent rule — never *assert* something is running from a stale check — stands, scoped in memory to assertions only: check before you claim, not before you act
- A gauge found alive outside the session window is logged as a WARN and never killed from cron; that stays a human call
- The COO wrapper patch was written as a proposal, not applied — cross-repo writes need separate authorization, and PATH composition is COO's structural call, not Strader's

**Files Changed**:
scripts/mi_gauge.py
scripts/cron/gauge-preopen-wrapper.sh
runbook/mancini/fetch.py
scripts/session_review.py
tests/scripts/test_mi_gauge_session_stop.py
tests/scripts/test_gauge_preopen_wrapper.py
tests/runbook/test_fetch.py
docs/a2a/2026-07-25-strader-to-coo-cron-path-az.md
archive/DaysActivity-2026-07-23.md
data/corpus/2026-07-24/mi_gauge_live.jsonl
data/corpus/2026-07-24/mi_gauge_live.raw.jsonl

**Commits**: 5cee846 (gauge, st-5n8 + st-r3f) · 5e1f267 (mancini az, st-i68) · 1e6cf81 (log housekeeping) · a2bf571 (A2A memo, st-i68) — pushed, tree clean. Suite green at this session's HEAD (461) and re-verified at repo HEAD after the concurrent work below: **464 passed / 0 failed** across `tests/`, `strader/tests`, `runbook/mancini/tests`.

**Concurrent session**: this was not the only session in the repo today. Between 15:18 and 17:28 CT another session committed under the same git identity — 20ee4e2 (Mancini stable renderer design spec, st-3c4), dceed36 (replay-drill plan update, st-ve6 + st-055), and three st-055 refactors extracting the shared day-anchor rule into `anchors.py` and the `full_stack_events` drive loop out of `parity_run`. None of that is described by this entry and it should get its own handoff. Flagged because the two sessions' work interleaves in the same history and the orderflow/parity refactors were not reviewed here.

**Beads Closed**: st-5n8 (MI gauge daemon never stops) · st-r3f (gauge start path auto-starts the real steves-desk)

---
