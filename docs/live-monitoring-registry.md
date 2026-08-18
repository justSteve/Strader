# Live-Monitoring Surfaces — Authority Registry

**Bead:** st-pfrz (live-monitoring surfaces registry) · **Observed:** 2026-08-13
**Design law it serves:** *observation beats claim* (Zgent Sync Plan law 3,
`docs/plans/2026-08-12-zgent-sync-plan.md`, st-aski).

Twenty-plus scripts in this repo watch some aspect of the live session. Several
answer the same question in different words, and until now nothing said which
answer wins. This page is that ruling.

**How to use it.** Two steps, in this order:

1. `bash scripts/surface_liveness.sh` — what is *actually* running, observed
   from `ps`, not claimed by any file. That script is the entry point; this page
   explains what each row means and which row to believe when two disagree.
2. Find your question in the authority table below and read only the surface
   named authoritative for it. Every other surface that touches the question is
   listed as secondary with the reason it loses.

**This page is a claim.** It was true when written. `surface_liveness.sh` is an
observation. Where they disagree, the script wins and this page is stale — fix
it rather than trusting it.

---

## 1. The authority table — one question, one owner

| Question | AUTHORITATIVE surface | Why it wins | Also answers it (and why it loses) |
|---|---|---|---|
| What is running right now? | `scripts/surface_liveness.sh` | Dependency-free (`ps`/`ls`/`date` only), read-only, cannot itself be the broken thing. Run at every `/tap-in`. | `CurrentStatus.md`, auto-memory, any handoff note — all are claims written in the past tense. |
| Is the ES tick tape being captured and advancing? | `scripts/capture_health.py` (pure assessor `strader/capture_health.py`), run every 2 min by `strader-health-assessors.timer` → `scripts/health_assessors.sh` | Only surface that separates *process alive* from *process receiving*; feeds the 08:25 pre-open heartbeat. Writes `data/corpus/_capture_health.json`. (Until 2026-08-13 the `*/2` cron supervisor ran it; the units that replaced the supervisors did not, and the file froze for four days — co-03ojd.7 J-F1.) | `surface_liveness.sh` "ES capture" row — tells you a process matched, not that bytes are landing. Use it for presence, not for health. |
| Is the GexBot 10-endpoint feed alive? | `data/corpus/_gexbot_health.json` (written every 2 min by `strader-health-assessors.timer` → `scripts/health_assessors.sh`; the collector itself is `strader-gexbot.service`) | Same assessor, its own state file; knows the RTH gate and the NYSE holiday table, so it can say `idle` instead of crying `dead` all weekend. | `surface_liveness.sh` "GEX collector" row — presence only, no staleness verdict. |
| Is the 1 Hz orderflow leg alive? | `data/corpus/_gexbot_of1s_health.json` (same writer, `strader-health-assessors.timer`; the collector is `strader-gexbot-orderflow-1s.service`) | Separate process, separate state file by design — a shared file would cross the two collectors' cycle counts and cry stale every two minutes. | `surface_liveness.sh` "GEX 1Hz orderflow" row (added under this bead) — presence only. |
| Has price come to a level worth a deep read? | `scripts/orderflow_sentinel.py` | The *live* watcher: reads the 1 Hz feed, fires `approach` / `relocation` with hysteresis, writes `orderflow_alerts.jsonl`. This is the watching tier of the trader loop Steve directed 2026-08-10. | `scripts/orderflow_monitor.py` — journals doctrine events but **alerts nothing** and has not run since 2026-08-07. See ruling §3.1. |
| What orderflow events happened today, for later measurement? | `scripts/orderflow_monitor.py` (`--replay <date>`) | Its event taxonomy (CVR/GEX spikes, NETCVX dump/ramp, wall moves, inversions) is the measurement vocabulary, and `orderflow_hist_sweep.py` imports its detector. | The sentinel's alert log is a *decision* log, not an event census — it deliberately suppresses repeats. |
| Is the market internals tape leaning? | `scripts/mi_gauge.py --live` | Cron-respawned every 5 min in-session (`gauge-preopen-wrapper.sh`), replays `mi_gauge_live.jsonl` on relaunch so the cum-TICK spine survives a restart. | Nothing else reads $TICK live. |
| Where is the day's volume trading, live? | `scripts/live_footprint_feed.py` → `drill_bridge.py` → the page | Parity-guaranteed: same `build_bars` the replay uses, so a live bar equals the replay bar. | Reading the raw JSONL by hand. Don't — ordering and dedup are handled in the feeder. |
| Did the live surface actually equal the replay? | `scripts/live_parity_check.py` | The formal acceptance check (st-d5f AC#4). | **NOTHING ELSE — and it never runs.** Its wrapper was deliberately left uninstalled in cron. See §4. |
| Is a Mancini level touched / held / broken / reclaimed? | `data/level_state/current.json` (written by `runbook.mancini.tracker`, cron 08:20–15:15) | Single atomically-rewritten file; the same state machine the overnight brief and the Pine markers use. | Eyeballing the chart; re-deriving from the letter. Both re-litigate a settled computation. |
| Did the pre-open chain (pull → parse → gate) run? | `runbook/heartbeat.py` via `cron/preopen-heartbeat-wrapper.sh` (08:25 CT) | Asserts the outcome five minutes before the bell, alerts on failure. | Reading the individual cron logs after the fact. |
| Is the Schwab token about to die? | `scripts/schwab_token_health.py` | Alarms *before* the 7-day wall; invoked by `corpus_daily.py` and by `capture_health.py`. | Waiting for a 401. Note its cadence is the 06:30 cron — an intra-day token failure is not caught until the next morning. |
| Is the /hist archive current? | `/var/moo/logs/gexbot-hist-nightly.log` + `data/corpus/gexbot-hist/<date>/` | The nightly job (`gexbot_hist_nightly.sh`, cron 21:00 CT weekdays, st-mx42) is idempotent and self-heals 3 days back. | `surface_liveness.sh` "GEX hist backfill" row — it is DOWN ~23h55m of every day by design. |
| Will this move continue? | `scripts/desk/continuation_meter.py` | Only surface reading measured probabilities out of `decision_aligned_truth.json` with intervals. | **Currently dead** — last journal 2026-08-05. See §4. |
| How hard did it trade *at* that level? | `scripts/level_strength.py` (on demand) | Aggressor split + did-they-get-paid out of the footprint. Not a monitor — a measurement you ask for. | `level_watch.py` answers a different question: is volume *expanding* below a line, right now. |

---

## 2. Surface inventory — observed 2026-08-13 05:22 CT

State column is what was **observed**, not what any doc claims. `ps`, file
mtimes, `crontab -l`, and `tmux -L moocity` were the instruments.

### 2.1 Supervised live tier (systemd restarts the three collectors since 2026-08-13 [st-pgfe]; DOWN inside the window is a fault)

| Surface | Question | Reads | Writes | Started by | State |
|---|---|---|---|---|---|
| `corpus_stream_databento.py` | live ES trades + MBP-1 | Databento live | `data/corpus/<day>/databento_glbx_es*.jsonl` | `strader-capture-early.timer` 00:00, `strader-capture.timer` 02:50, `strader-capture-evening.timer` 15:06 CT weekdays (+ Sun 17:00) [st-9olq] → `strader-capture.service` (Restart=on-failure), window 02:50–15:05 CT; health verdict by `strader-health-assessors.timer` | **LIVE** (pid 775145, relaunched 02:50 today — `restarts:1`) |
| `corpus_poll_gexbot.py` | 10 GexBot endpoints @60s | GexBot API | `gexbot.jsonl` | `strader-gexbot.timer` 08:30 CT weekdays → `strader-gexbot.service`, 08:30–15:05 CT; health verdict by `strader-health-assessors.timer` (holiday-aware) | DOWN — **normal**, pre-window |
| `corpus_poll_gexbot_orderflow_1s.py` | orderflow spike train @~1 Hz | GexBot `/SPX/orderflow/orderflow` | `gexbot_orderflow_1s.jsonl` | `strader-gexbot-orderflow-1s.timer` 08:30 CT weekdays → `strader-gexbot-orderflow-1s.service`, same gate | DOWN — **normal**, pre-window (13 MB written 08-12) |
| `mi_gauge.py --live` | $TICK internals lean | Schwab quote endpoint | `mi_gauge_live.jsonl` | `cron/gauge-preopen-wrapper.sh` `*/5 8-15` | DOWN — normal between ticks |
| `runbook.mancini.tracker` | level touched/held/broken | /ES candles + parse | `data/level_state/current.json` | `cron/level-tracker-wrapper.sh` 08:20, self-exits 15:15 | last wrote 08-12 15:14 — normal |
| `gexbot_hist_backfill.py` | /hist archive currency | GexBot `/hist` | `data/corpus/gexbot-hist/<date>/` | `gexbot_hist_nightly.sh`, cron 21:00 weekdays | last fire 08-12 21:00, exit 0, 30 files |
| `premarket_volume_profile.py` | premarket anchored VP page | Schwab /ES ETH bars | desk page | cron 08:16 weekdays | last log 08-12 08:16 |
| `schwab-stages-wrapper.sh` | 4 chain/quote snapshots | Schwab | `schwab.jsonl` | cron 07:00 / 08:30 / 13:00 / 14:45 | last wrote 08-12 14:45 |

### 2.2 Live but UNSUPERVISED (nothing restarts these)

> **Superseded 2026-08-16 [st-n0qm.1, st-n0qm.3 — Watcher V2 Phases 0/2b].** Every row
> in this table now runs under systemd, same container as the collectors:
> `strader-orderflow-sentinel.service` (06:20 CT, co-03ojd.7; day-boundary reset +
> `_sentinel_health.json` every 60 s since Phase 0), `strader-drill-bridge.service`
> and `strader-footprint-feed.service` (`PartOf=` the bridge; the feeder renders
> the day's page at start and heartbeats `_footprint_health.json`). Install/refresh
> with `bash deploy/install.sh`; watch with `journalctl -fu <unit>`. The bridge
> serves the page at `http://127.0.0.1:7788/` and on the tailnet at
> `https://mydesk-1.tail89f676.ts.net/footprint/` (`tailscale serve --set-path`);
> `GET /health/producers` reports every producer's health-file age and the page
> draws them as dots. `live-footprint-up.sh` is unit-aware and becomes a viewer
> when the units are active. The table below is kept as the record of what this
> registry found on 08-13.
>
> **Phase 3, 2026-08-16 [st-n0qm.8, st-n0qm.9].** The sentinel now also POSTs
> each alert to the bridge (`--bridge`, default `http://127.0.0.1:7788`, best-
> effort, off under `--replay`); the bridge keeps them as an append-only
> `alerts` channel (`POST /alerts`, `GET /alerts?since=N`) and resets every
> day-owned slot when a `/bars` push carries a new `meta.day`. The page polls
> `/alerts` each tick and draws each SPX level on the ES axis at
> `strike + basis`, the basis being the `bs` every closed bar now carries
> (`market/orderflow/basis.py`: 1 Hz vendor spot vs the bar close, median of
> ten; measured 08-14 within 0.7 pt of Schwab's in-session basis). `s` toggles
> the rows; the HUD strip carries the newest sentence and the basis. Row 4's
> "orderflow_alert_fmt.py never in the pipe" is half-resolved: the page has a
> JS twin of `fmt()`; the tmux pipe stays unwired by Steve's page-over-tmux
> ruling (08:26 CT).

| Surface | Question | Writes | Started by | State |
|---|---|---|---|---|
| `orderflow_sentinel.py` | level-proximity alerts | `orderflow_alerts.jsonl`, `/var/moo/logs/orderflow-sentinel/<CT date>.log` (rolls daily since 2026-08-16) | **systemd** `strader-orderflow-sentinel.service` (enabled + started 2026-08-16, st-2yuw / COO co-03ojd.7); before that by hand into `steves-desk:sentinel` | **LIVE** — pid 148773, up 23h10m, `tee`-ing to a log still named `2026-08-12` |
| `drill_bridge.py` | browser ↔ agent channel :7788 | HTTP only | `live-footprint-up.sh` / drill-coach skill | **LIVE** — pid 327027, up 16h47m |
| `live_footprint_feed.py` | live volume bars | POSTs to the bridge | `live-footprint-up.sh` | **LIVE** — pid 327054 |
| `live_footprint_page.py` | the page itself | `/tmp/desk-live-footprint.html` | `live-footprint-up.sh` (regenerated each bring-up) | output path is cleared by every reboot — a bookmark contract that must be re-rendered |

**This is the registry's sharpest finding.** The sentinel is the only
session-critical *watcher* with no restart path. Three cron supervisors cover the
three collectors; nothing covers the thing they feed. It died with the 08-11
reboot and stayed down until `/tap-in` noticed the missing alert file (st-2yuw).
Its log filename is pinned to its hand-launch date, so log rollover is also
manual.

### 2.3 Dormant / dead — nothing runs them

| Surface | Last live | Why it stopped | Disposition |
|---|---|---|---|
| `orderflow_monitor.py` + `orderflow_monitor_up.sh` | events file 2026-08-07; heartbeat `/var/moo/state/orderflow-monitor.json` frozen 08-08 00:00 | Superseded for the *live watch* by the sentinel (st-igim, 08-10) | **KEEP the replay path, retire the live path** — see §3.1 |
| `desk/continuation_meter.py` | journal 2026-08-05 19:56 (the tmux-server death) | Hand-launched pane, no supervisor, never relaunched | Keep — but it is the *only* source for the continuation question, so a dead meter means that question is currently unanswerable |
| `flush_watcher.py` | journal 2026-08-05 | Shadow-mode by design, awaiting measured thresholds (st-rtuu). Nothing schedules it | Keep — but note its shadow journal, the evidence st-rtuu needs, is **not accumulating** |
| `live_parity_check.py` + `cron/live-parity-wrapper.sh` | never scheduled | Wrapper deliberately awaits a human cron install (`10 16 * * 1-5`) | **Install the line** — cheapest risk reduction in the estate |
| `orderflow_alert_fmt.py` | never in the pipe | Built 08-10; the running sentinel `tee`s raw JSONL and skips it | Wire it or let it rot — confirmed by `ps`: only `tee` is downstream |
| `fire_server.py` | never | Dry-run execution surface, no launch path by design | Leave alone. Promotion is st-bxls and needs explicit review |
| `gex_now.py`, `gex_series.py` | May 2026 | Schwab-chain GEX superseded by the GexBot feed | Retirement candidates (§5) |
| `corpus_poll.py` | superseded | Split into `corpus_poll_gexbot*` | Retirement candidate (§5) |

### 2.4 On-demand analyst tools (not monitors — no liveness question applies)

`level_strength.py`, `level_watch.py`, `gexbot_distill.py`, `gex_now.py`,
`replay_*`, `market_profile_drill.py`, `orderflow_drill.py`,
`scripts/measurement/*`. These answer questions when asked and exit. They belong
in this registry only so nobody mistakes their absence from `ps` for a fault.

---

## 3. Overlap rulings

### 3.1 `orderflow_monitor.py` vs `orderflow_sentinel.py` — split the roles

Both read GexBot orderflow. Both detect "something happened near a level." The
code-estate audit called the missing ruling out by name
(`docs/audits/2026-08-12-code-estate/`, duplication lens: *"orderflow_monitor vs
orderflow_sentinel overlap with no canonical-watcher ruling"*). The ruling:

- **The sentinel is authoritative for the LIVE watch.** It alerts; the monitor
  explicitly does not ("Interpretation is out of scope: no direction calls, no
  alerts"). A watcher that cannot summon anyone is not a watcher. It also reads
  the 1 Hz leg, where the monitor reads the 60s collector — a 70s sample cannot
  see a spike train, which is the whole content of the question.
- **The monitor is authoritative for the EVENT CENSUS, offline.** Its taxonomy is
  the measurement vocabulary and `orderflow_hist_sweep.py` imports its detector.
  Run it as `--replay <date>`, not `--follow`.
- **Retire the monitor's live path**, i.e. `orderflow_monitor_up.sh` and the
  `--follow` runbook in `docs/gexbot/orderflow-monitor.md`. Nothing is deleted
  under this bead; this is the recommendation, and it is cheap to reverse.

### 3.2 `surface_liveness.sh` vs the three `_*_health.json` files

Not redundant — different questions, and the distinction matters at 08:31.

- `surface_liveness.sh` answers **"is a process there?"** by pattern-matching
  `ps`. It is deliberately dumb so it cannot break.
- The `_capture_health.json` / `_gexbot_health.json` / `_gexbot_of1s_health.json`
  verdicts answer **"is it receiving?"** by reading manifest cycle counts, and
  can return `alive-but-not-advancing` — the failure that looks healthy.

Rule: liveness first (it is never wrong about presence), health second (it is the
only one that catches a live-but-deaf process).

### 3.3 `level_watch.py` vs `level_strength.py` vs the sentinel

Three tools at one level, three genuinely different questions — no overlap to
resolve:

- sentinel: *price is arriving* at a gamma level (forward-looking, alerting)
- `level_watch.py`: *volume is expanding* below a line right now (blocking, exits
  on trigger)
- `level_strength.py`: *how did it trade* there (backward-looking measurement)

### 3.4 `flush_watcher.py` vs `market/orderflow/regime.py`

Both claim the "is this a meltdown / does the flush continue" question, from
different inputs — the watcher off the continuation meter's journal, `regime.py`
off the recognizer's confirmed/invalidated balance. **Neither is authoritative,
because neither runs**: the meter that feeds the watcher has been dead since
08-05, and `regime.py` is imported by nothing but its own test. Both thresholds
are self-declared provisional pending st-rtuu. Treat any output from either as
shadow-mode until that lands.

---

## 4. Genuine redundancy — retirement candidates (nothing deleted here)

| Candidate | Reason | Blocked on |
|---|---|---|
| `orderflow_monitor_up.sh` | Launches the superseded live path (§3.1) | Confirming the sentinel covers every alerting case the monitor's runbook promised |
| `gex_now.py`, `gex_series.py` | Schwab-chain GEX superseded by the GexBot feed; `data/gex_series/` holds one file from May 20 | Worth keeping as an independent cross-check *if* the GexBot subscription lapses again — that is their only residual value |
| `corpus_poll.py` | Split into `corpus_poll_gexbot*`; referenced only by a provenance docstring | Nothing |
| `orderflow_alert_fmt.py` | Presentation layer the live pipe skips | Decide: wire into the sentinel pipe, or drop |

Everything above is a *recommendation*. Per st-pfrz, nothing was deleted.

---

## 5. Observation gaps found while writing this

1. **`surface_liveness.sh` "ES capture" uptime is wrong.** The probe takes the
   first `ps` line containing `corpus_stream_databento.py`, and the `tmux
   new-session` command line for the capture window contains that string. It
   therefore reports pid 133436 / 1d01h (the tmux session's age) instead of pid
   775145 / 53m (the streamer, relaunched by the supervisor at 02:50 today). The
   UP/DOWN verdict is right; the pid and uptime are the wrapper's. Left unfixed —
   outside this bead's two named defects, and the fix (filter on `comm` being a
   python, the guard `capture_health.py` already applies) deserves its own bead.
2. **No meta-test ties collectors to liveness rows.** The 1 Hz leg ran live for
   three days with no row. The audit's proposed fix stands: glob `scripts/corpus_*`
   and assert each name appears in `surface_liveness.sh`, so the next collector
   cannot be forgotten.
3. **`live_parity_check.py` has never run.** Live-vs-replay drift would currently
   be invisible. One cron line.
4. **The sentinel's log filename does not roll.** It is pinned to the hand-launch
   date (`orderflow-sentinel-2026-08-12.log`, still being appended on 08-13), so
   log-by-date lookups silently miss. Folds naturally into st-2yuw's supervisor
   shim.

---

## 6. Changes made to `scripts/surface_liveness.sh` under this bead

- **Added** the `GEX 1Hz orderflow` probe row for
  `corpus_poll_gexbot_orderflow_1s.py`, carrying the sibling collector's measured
  RTH-window caveat. It had been live since 2026-08-10 (st-ipn0) with no row —
  the script could not have said either way, which is exactly the 2026-08-05
  blindness it exists to end.
- **Added** the `OF sentinel` probe row, marked UNSUPERVISED, because the
  registry names it authoritative for the live level watch and an authority the
  observation tool cannot see is not an authority.
- **Corrected** the `GEX hist backfill` row: it cited st-ox9x (CANCELLED
  2026-08-10) and told the reader to delete the row when the paid window
  completed. The probe is now anchored to the *nightly* harvest (st-mx42, cron
  21:00 CT weekdays, verified firing 08-12), so the row is permanent, DOWN is
  normal nearly all day, and the surviving loose end is named as st-kr4a.
- **Added** `GEX 1Hz rows` and `OF alerts` file-size rows, with the note that an
  absent alert file is a quiet market rather than a fault — *provided* the
  sentinel process row above reads UP.

Verified by running `bash scripts/surface_liveness.sh` end to end: exit 0, all
rows render, no shell errors.
