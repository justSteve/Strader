# Tranche 0 census — what the estate actually holds, 2026-09-06

Strader's half of tranche 0 of Desk's trading-code-estate architecture order
(2026-09-05 16:00), ratified by Steve 2026-09-06 ("reorg = yes"). **No code
moves in tranche 0.** This is the map the later tranches are argued from.

Measured after the legacy prune executed the same morning (`eea2f6a`), so every
count here is post-prune. The order's own census is superseded: **981 tracked
files in packages, 991 including root files**, against the 1,103 the 08-12
census recorded.

Companion: `OWNERS.md` at the repo root.

---

## 1. `strader.feeds` — the seam, measured

This is the item Desk's F4 and the prune verdict disagree about, so it was
measured rather than reasoned. Three findings, and each of them contradicts one
of the two memos.

**Nothing imports it. Zero files.** Not one module under `strader/`, `market/`,
`scripts/`, `runbook/` or `tests/` does `from strader.feeds import …`. So F4's
premise — that the seam is load-bearing today — is not true of the tree as it
stands.

**It is not empty.** The prune plan's step 4 archives it because "the empty
module is not the intent". The file is **65 lines**: a `CARRIED` catalog of
eleven dotted paths, a lazy `carried()` accessor and an `available()` health
map. Whatever it is, it is not an empty module, and the reason given for
archiving it is false.

**It does not front what `strader/` actually reaches.** `strader/` reaches past
the seam **17 times across 8 files** — 11 module-level, 6 function-local. Of the
11 module-level reach-ins, **9 are `market.entities.*`**, which the catalog does
not cover at all: `CARRIED` lists ingest, corpus, broker and mancini, not
entities. So "route the imports through the seam" is not a mechanical change; it
would first require deciding that entity *types* belong behind a *feed* seam.

| reach-in | count | note |
|---|---:|---|
| `market.entities.*` (module-level) | 9 | not in the catalog; these are types, not feeds |
| `market.resolve`, `runbook.mancini.schema` (module-level) | 2 | live intent path |
| `market.orderflow.*` (function-local) | 4 | two commented "heavy import, on demand" |
| `broker_schwab.client` (function-local) | 1 | `strader/execution/feed.py`, behind the gate |
| `market.entities.chain` (function-local) | 1 | |

**Strader's counter, therefore:** neither memo's stated reason survives. The
seam is *built but never wired*. That is not a prune disposition and not an
architecture premise — it is a tranche-4 decision, taken where
`market/entities` moves to `core/marketdata`, because that move is what settles
whether the catalog should grow an entities section or the seam should go.
Prune step 4 stays held; Desk's F4 needs its premise restated.

**One defect fixed on the way past.** The catalog carried
`ingest_mancini -> market.ingest.mancini`, a module this morning's prune
removed. `available()` reports an unimportable module as `False` by design — a
missing optional dep is information, not an error — so a *deleted* module reads
exactly like an *uninstalled* one and the catalog can rot while its health map
looks fine. Entry removed, and `tests/strader/test_feeds_catalog.py` now asserts
every entry exists on disk, which is the one thing `available()` structurally
cannot tell you. Mutation-checked: restoring the stale entry fails two tests.

## 2. `market/resolve.py` — callers

Two, and one of them is production:

- `strader/intent/session.py:23` — `from market.resolve import ResolutionError, resolve_butterfly`, called at `:324`.
- `tests/market/test_resolve.py:6`.

Desk's disposition row said "folded or deleted per callers" and marked it
*(verify)*. It verifies as **live**. Deleting it breaks the butterfly resolution
path in the intent session; folding it is possible but is tranche-4 work with a
consumer test, not a disposition.

## 3. `present/` — callers

Nine references across seven files, **all of them to `present/speech.py`**:

| caller | kind |
|---|---|
| `strader/intent/readback.py:14` | production |
| `scripts/speak_replay.py:42` | production |
| `market/emission/numbers.py:8`, `strader/intent/numbers.py:9` | doc reference to the phrasebook |
| `strader/tests/test_intent_numbers.py`, `tests/market/emission/test_live_guard.py` (×2), `tests/market/present/test_speech.py` (×2) | tests |

Desk's read was "retire — the drill voice layer moved to `speak_replay.py` and
the coach", marked *(verify)*. It verifies the other way: `speak_replay.py` is
one of `speech.py`'s **callers**, not its replacement. `present/` **splits**. The
dormant half (`regime.py`, `signals.py`) was already pruned on 2026-09-06;
`speech.py` is 11 KB, last edited 2026-08-26, and stays.

## 4. `lib/schwab-py`

One tracked file — the submodule pointer. It tracks the `hobbled-readonly` fork
with account, order and transaction methods physically removed
(DEFENSE NOTE in `schwab/client/base.py`). Unchanged by this order; the
structural backstop under the gate hook.

---

## 5. `scripts/` by class — tranche 3's bead set

125 tracked files. **Class is assigned from what schedules or invokes the file,
never from its name** — a name is a claim, a scheduler entry is a measurement.
Evidence column says which.

### Two amendments to Desk's taxonomy

Desk's six classes are daemon / chore / probe / repair / study / template. Two
more are needed, and both are load-bearing rather than cosmetic:

- **`tool`** — 12 files whose *design* is hand invocation. The 09-04 audit
  already ruled one of them this way (`lexicon_render.py`: "invocation-by-hand
  is its design; not clutter"). Without this class they read as unreferenced and
  get proposed for deletion every time someone counts references. They are not
  chores: nothing schedules them and nothing should.
- **`asset`** — 1 file, `scripts/orderflow_monitor.config.json`. Config beside
  its script is not a script.

### One orphan found

`scripts/cron/corpus-daily-wrapper.sh` lives in `scripts/cron/` and **nothing
schedules it** — it is in no crontab line and no unit `ExecStart`. The 09-04
audit checked schedule → file ("every catalogued job resolves to a file in
HEAD") and that direction was clean; this is the other direction, file →
schedule, and it is not. Its disposition belongs to tranche 3.

### Counts

```
daemon         13
chore          41
probe          5
repair         6
study          42
tool           12
template       4
asset          1
ORPHAN         1
TOTAL          125
```

### The table

| # | path | class | evidence |
|---|---|---|---|
| 1 | `scripts/corpus_poll_gexbot.py` | daemon | systemd: strader-gexbot |
| 2 | `scripts/corpus_poll_gexbot_orderflow_1s.py` | daemon | systemd: strader-gexbot-orderflow-1s |
| 3 | `scripts/cron/capture-evening.sh` | daemon | systemd: strader-capture-evening |
| 4 | `scripts/drill_bridge.py` | daemon | systemd: strader-drill-bridge |
| 5 | `scripts/fire_server.py` | daemon | launcher / long-running, not scheduled here |
| 6 | `scripts/flush_watcher.py` | daemon | launcher / long-running, not scheduled here |
| 7 | `scripts/health_assessors.sh` | daemon | systemd: strader-health-assessors |
| 8 | `scripts/level_watch.py` | daemon | launcher / long-running, not scheduled here |
| 9 | `scripts/live-footprint-up.sh` | daemon | launcher / long-running, not scheduled here |
| 10 | `scripts/live_footprint_feed.py` | daemon | systemd: strader-footprint-feed |
| 11 | `scripts/live_footprint_page.py` | daemon | systemd: strader-footprint-feed |
| 12 | `scripts/orderflow_monitor_up.sh` | daemon | launcher / long-running, not scheduled here |
| 13 | `scripts/orderflow_sentinel.py` | daemon | systemd: strader-orderflow-sentinel |
| 14 | `scripts/acuity_run2.py` | chore | called by scripts/speak_replay.py |
| 15 | `scripts/corpus_compact_databento.py` | chore | called by scripts/cron/corpus-compact-wrapper.sh |
| 16 | `scripts/corpus_daily.py` | chore | called by scripts/capture_health.py, scripts/corpus_pull_internals.py … |
| 17 | `scripts/corpus_poll_schwab_late_chain.py` | chore | corpus pull, hand-run or wrapper-run |
| 18 | `scripts/corpus_pull_databento.py` | chore | called by scripts/corpus_backfill_databento.py |
| 19 | `scripts/corpus_pull_databento_es.py` | chore | called by scripts/corpus_daily.py |
| 20 | `scripts/corpus_pull_databento_es_mbp1.py` | chore | corpus pull, hand-run or wrapper-run |
| 21 | `scripts/corpus_pull_internals.py` | chore | corpus pull, hand-run or wrapper-run |
| 22 | `scripts/corpus_pull_opra_quotes.py` | chore | corpus pull, hand-run or wrapper-run |
| 23 | `scripts/corpus_pull_schwab.py` | chore | called by scripts/cron/schwab-stages-wrapper.sh |
| 24 | `scripts/corpus_stream_databento.py` | chore | called by scripts/cron/capture-evening.sh, scripts/live-footprint-up.sh … |
| 25 | `scripts/cron/corpus-compact-wrapper.sh` | chore | cron: 1 entry |
| 26 | `scripts/cron/footprint-icm-wrapper.sh` | chore | cron: 1 entry |
| 27 | `scripts/cron/gauge-preopen-wrapper.sh` | chore | cron: 1 entry |
| 28 | `scripts/cron/heartbeat-lib.sh` | chore | called by scripts/gexbot_hist_nightly.sh |
| 29 | `scripts/cron/level-tracker-wrapper.sh` | chore | cron: 1 entry |
| 30 | `scripts/cron/mancini-preopen-wrapper.sh` | chore | cron: 1 entry |
| 31 | `scripts/cron/postmortem-wrapper.sh` | chore | cron: 2 entries |
| 32 | `scripts/cron/premarket-vp-wrapper.sh` | chore | cron: 1 entry |
| 33 | `scripts/cron/preopen-heartbeat-wrapper.sh` | chore | cron: 1 entry |
| 34 | `scripts/cron/schwab-stages-wrapper.sh` | chore | cron: 4 entries |
| 35 | `scripts/desk/continuation_meter.py` | chore | called by scripts/flush_watcher.py |
| 36 | `scripts/drill_coach.sh` | chore | skill: drill-coach |
| 37 | `scripts/entitlements_probe.py` | chore | skill: tap-in |
| 38 | `scripts/execd_market_credential.py` | chore | called by scripts/execd_vault_init.py |
| 39 | `scripts/execd_vault_init.py` | chore | called by scripts/execd_market_credential.py |
| 40 | `scripts/gexbot_hist_nightly.sh` | chore | cron: 1 entry |
| 41 | `scripts/mi_gauge.py` | chore | called by scripts/cron/gauge-preopen-wrapper.sh |
| 42 | `scripts/orderflow_alert_fmt.py` | chore | called by scripts/orderflow_drill_template.html |
| 43 | `scripts/orderflow_drill.py` | chore | skill: drill-coach |
| 44 | `scripts/orderflow_monitor.py` | chore | called by scripts/orderflow_monitor_up.sh |
| 45 | `scripts/postmortem_day.py` | chore | called by scripts/cron/postmortem-wrapper.sh |
| 46 | `scripts/premarket_volume_profile.py` | chore | called by scripts/cron/premarket-vp-wrapper.sh |
| 47 | `scripts/record_schwab_shapes.py` | chore | called by scripts/measurement/spx_option_tick.py |
| 48 | `scripts/refresh_schwab_token.py` | chore | called by scripts/corpus_daily.py, scripts/cron/schwab-stages-wrapper.sh … |
| 49 | `scripts/replay_annotate.py` | chore | called by scripts/replay_day.py, scripts/replay_review.py |
| 50 | `scripts/replay_day.py` | chore | called by scripts/day_browser_template.html, scripts/live_effort_effect.py … |
| 51 | `scripts/replay_emissions.py` | chore | called by scripts/drill_bridge.py, scripts/orderflow_drill_template.html |
| 52 | `scripts/replay_review.py` | chore | called by scripts/replay_day.py |
| 53 | `scripts/run.sh` | chore | skill: tap-in |
| 54 | `scripts/surface_liveness.sh` | chore | skill: tap-in |
| 55 | `scripts/capture_health.py` | probe | read-only report |
| 56 | `scripts/gexbot_tier_boundary_probe.py` | probe | read-only report |
| 57 | `scripts/gexbot_ws_probe.py` | probe | read-only report |
| 58 | `scripts/live_parity_check.py` | probe | read-only report |
| 59 | `scripts/schwab_token_health.py` | probe | read-only report |
| 60 | `scripts/corpus_backfill_databento.py` | repair | one-off repair |
| 61 | `scripts/corpus_repair_doubled_day.py` | repair | one-off repair |
| 62 | `scripts/fix_gexbot_hist_gzip.py` | repair | one-off repair |
| 63 | `scripts/gexbot_hist_backfill.py` | repair | one-off repair |
| 64 | `scripts/gexbot_hist_migrate.py` | repair | one-off repair |
| 65 | `scripts/mancini_backfill_levels.py` | repair | one-off repair |
| 66 | `scripts/calibrate_oflow_thresholds.py` | study | measurement lane |
| 67 | `scripts/measurement/absorption_calibrate.py` | study | measurement lane |
| 68 | `scripts/measurement/basis_pairs.py` | study | measurement lane |
| 69 | `scripts/measurement/clock_family_traversal.py` | study | measurement lane |
| 70 | `scripts/measurement/corpus_duplicate_sweep.py` | study | measurement lane |
| 71 | `scripts/measurement/decision_aligned_study.py` | study | measurement lane |
| 72 | `scripts/measurement/detect_v_days.py` | study | measurement lane |
| 73 | `scripts/measurement/estimated_mark_calibrate.py` | study | measurement lane |
| 74 | `scripts/measurement/estimated_mark_validate.py` | study | measurement lane |
| 75 | `scripts/measurement/final_fifteen_base.py` | study | measurement lane |
| 76 | `scripts/measurement/final_fifteen_by_rule.py` | study | measurement lane |
| 77 | `scripts/measurement/final_fifteen_premium.py` | study | measurement lane |
| 78 | `scripts/measurement/final_fifteen_premium_summary.py` | study | measurement lane |
| 79 | `scripts/measurement/final_fifteen_spread.py` | study | measurement lane |
| 80 | `scripts/measurement/final_fifteen_summary.py` | study | measurement lane |
| 81 | `scripts/measurement/final_hour_base.py` | study | measurement lane |
| 82 | `scripts/measurement/final_hour_combo.py` | study | measurement lane |
| 83 | `scripts/measurement/final_hour_lens.py` | study | measurement lane |
| 84 | `scripts/measurement/final_hour_lens_summary.py` | study | measurement lane |
| 85 | `scripts/measurement/final_hour_premium.py` | study | measurement lane |
| 86 | `scripts/measurement/final_hour_premium_summary.py` | study | measurement lane |
| 87 | `scripts/measurement/fly_replay.py` | study | measurement lane |
| 88 | `scripts/measurement/fly_replay_batch.py` | study | measurement lane |
| 89 | `scripts/measurement/internals_calibrate.py` | study | measurement lane |
| 90 | `scripts/measurement/legprofiler_study.py` | study | measurement lane |
| 91 | `scripts/measurement/morning_flush_continuation.py` | study | measurement lane |
| 92 | `scripts/measurement/morning_flush_forward_stats.py` | study | measurement lane |
| 93 | `scripts/measurement/morning_flush_study.py` | study | measurement lane |
| 94 | `scripts/measurement/morning_flush_vix_depth.py` | study | measurement lane |
| 95 | `scripts/measurement/morning_flush_vvix.py` | study | measurement lane |
| 96 | `scripts/measurement/mp_day_scan.py` | study | measurement lane |
| 97 | `scripts/measurement/orderflow_lead.py` | study | measurement lane |
| 98 | `scripts/measurement/premium_trajectory.py` | study | measurement lane |
| 99 | `scripts/measurement/residual_gate.py` | study | measurement lane |
| 100 | `scripts/measurement/retro_gamma_cut.py` | study | measurement lane |
| 101 | `scripts/measurement/scare_dip_catalog.py` | study | measurement lane |
| 102 | `scripts/measurement/score_meter_journal.py` | study | measurement lane |
| 103 | `scripts/measurement/spx_option_tick.py` | study | measurement lane |
| 104 | `scripts/measurement/synth_meter_frames.py` | study | measurement lane |
| 105 | `scripts/measurement/tape_reconstruction.py` | study | measurement lane |
| 106 | `scripts/measurement/trough_time_volume_analysis.py` | study | measurement lane |
| 107 | `scripts/orderflow_hist_sweep.py` | study | measurement lane |
| 108 | `scripts/acuity_run2_summary.py` | tool | on-demand; hand-invoked by design |
| 109 | `scripts/day_browser.py` | tool | on-demand; hand-invoked by design |
| 110 | `scripts/fetch_youtube_transcript.py` | tool | on-demand; hand-invoked by design |
| 111 | `scripts/level_interaction_read.py` | tool | on-demand; hand-invoked by design |
| 112 | `scripts/level_strength.py` | tool | on-demand; hand-invoked by design |
| 113 | `scripts/lexicon_render.py` | tool | on-demand; hand-invoked by design |
| 114 | `scripts/live_effort_effect.py` | tool | on-demand; hand-invoked by design |
| 115 | `scripts/market_profile_drill.py` | tool | on-demand; hand-invoked by design |
| 116 | `scripts/regen_parity_snapshot.py` | tool | on-demand; hand-invoked by design |
| 117 | `scripts/score_recognizer.py` | tool | on-demand; hand-invoked by design |
| 118 | `scripts/session_review.py` | tool | on-demand; hand-invoked by design |
| 119 | `scripts/speak_replay.py` | tool | on-demand; hand-invoked by design |
| 120 | `scripts/candles_template.html` | template | rendered asset |
| 121 | `scripts/day_browser_template.html` | template | rendered asset |
| 122 | `scripts/market_profile_drill_template.html` | template | rendered asset |
| 123 | `scripts/orderflow_drill_template.html` | template | rendered asset |
| 124 | `scripts/orderflow_monitor.config.json` | asset | config beside its script |
| 125 | `scripts/cron/corpus-daily-wrapper.sh` | ORPHAN | in scripts/cron/ but NOTHING schedules it |

[st-c6ii]
