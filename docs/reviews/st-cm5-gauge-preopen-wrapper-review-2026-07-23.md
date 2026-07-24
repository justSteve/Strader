# st-cm5 — Gauge Pre-Open Cron Wrapper: Review

**Bead:** st-cm5 · **Date:** 2026-07-23 · **Status:** built + tested, staged, awaiting your approval to commit
**Deadline:** crontab must be installed before tomorrow's first fire at **08:00 CT**

---

## What this delivers

The live MI gauge (cum-TICK spine, window 10 on your desk) currently only exists if someone
launches it by hand. After this change, cron keeps it alive across the whole session:

1. **Launches it pre-open** — first heartbeat fire at 08:00, pane up before the 08:30 open,
   so the cum-TICK spine measures the full session (launched late, it "runs hot").
2. **Respawns it within 5 minutes if it dies mid-session** — and the respawn **continues the
   spine where it left off** instead of resetting to zero.
3. **Bootstraps a minimal `steves-desk` tmux session if the whole desk is down** — which,
   after tonight's reboot, is exactly the state the machine is in right now.

## The three files

| File | What it is |
|---|---|
| `scripts/cron/gauge-preopen-wrapper.sh` | New. The heartbeat wrapper — 173 lines, heavily commented. |
| `scripts/mi_gauge.py` | Modified (+122). `--live` now captures each minute to disk and restores by replay on relaunch. |
| `tests/scripts/test_mi_gauge_capture.py` | New. 6 tests proving the capture→restore contract. |

---

## How the wrapper thinks (`gauge-preopen-wrapper.sh`)

**One idempotent script, on a 5-minute heartbeat:**

```
*/5 8-15 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/gauge-preopen-wrapper.sh
```

Every 5 minutes, 08:00–15:55 CT, weekdays. Each fire asks one question — *is a live gauge
process running?* — and:

- **Yes** → exits immediately (the normal case, a no-op costing nothing)
- **No** → launches one, reaping any stale `gauge` windows

**Alive means process, not window.** On 7/23 the desk had three windows named `gauge` with
only one live — the others had died down to bare shells. So the guard is a `pgrep` filtered
to actual python processes (a bare pattern-match would also match any shell or editor whose
command line mentions the string, and a false "already running" here loses the session).

**Create first, then reap** — the bug the test harness caught. The original order (reap
stale windows, then launch fresh) had a landmine: if the stale gauge windows were the *only*
windows in the session, killing them emptied the session, tmux destroyed it, and the launch
then failed. Production's multi-window desk masks this — it would have surfaced the one
morning it mattered. Fixed: snapshot the stale windows, create the fresh one, then reap the
snapshot. The session is never empty.

**Bootstrap-if-down** (you authorized 7/23): if `steves-desk` doesn't exist, the wrapper
creates a *minimal* session hosting just the gauge — deliberately not a rebuild of COO's
full desk. Header comment flags that COO's rebuild and this bootstrap may need reconciling.
Post-reboot, this is the path tomorrow's 08:00 fire will actually take.

**Crashes stay diagnosable**: `remain-on-exit` freezes a crashed gauge's error in the pane
until the next heartbeat reaps it — nothing dies silently. Every fire appends to
`/var/moo/logs/gauge-preopen/<date>.log`. A missing Schwab gate key logs a warning but still
launches, so an auth failure shows up in the pane rather than vanishing into cron.

## How the spine survives a respawn (`mi_gauge.py`)

The gauge is a deterministic pure function of its tick stream — so we don't checkpoint its
internals. Instead:

- **Capture**: every processed minute is appended as one JSON line to
  `data/corpus/<date>/mi_gauge_live.jsonl`
- **Restore**: on (re)launch, today's capture file is replayed through a fresh gauge —
  reconstructing the *exact* state by construction, then resuming live

Honest-loss principle: minutes elapsed while the process was down are genuinely gone
(same-day $TICK history is clamped to zero and can't backfill). The gauge **names the gap**
in a banner rather than papering over it. A kill mid-write can only truncate the final line,
which restore tolerates; a crash-and-respawn inside the same minute won't double-count
(restored minutes are deduped by timestamp).

Side benefit: the capture file is itself the forward internals sample the regime-weighting
research (st-3fr) wants, co-located with the day's corpus.

New flags: `--capture PATH` (override the default path), `--no-capture` (old behavior).
Default is capture on.

## Test evidence

- **`pytest`: 18 green** (6 new capture/restore tests + existing suite)
- **Scratch-socket smoke: 13 passed, 0 failed** — env-override knobs let a throwaway tmux
  socket + python stub drive every failure path (cold bootstrap, idempotent no-op,
  reap+respawn, anchor placement) with no moocity and no Schwab. This harness is what caught
  the create-first-then-reap bug.

## Your checklist

1. ~~Review this document~~ — you're doing it
2. Skim the wrapper source if you want the full detail: `scripts/cron/gauge-preopen-wrapper.sh`
3. **Install the crontab line** (full copy/paste procedure is in chat)
4. Say the word and I commit all three files under st-cm5

## Post-reboot notes (supersede two caveats from the earlier session)

- The old no-capture gauge (pid 862122) died in the reboot — moot. Tomorrow's launch runs
  the new capture-enabled code from minute one.
- The three stale gauge windows are gone with the socket — moot. And since the desk is down
  entirely, tomorrow's 08:00 fire exercises the bootstrap path for real: expect a minimal
  `steves-desk` with the gauge in it unless COO rebuilds the full desk first.
