# DaysActivity - 2026-08-04

## 03:40 - Session Handoff [Phase B Live Capture + Live Footprint v1]

**Summary**: The GLBX/ES live subscription was verified real, Phase B was un-deferred, and the drills-only footprint became a live surface — with ES trades and MBP-1 now capturing continuously for the first time. Long single session spanning 08-02 evening through 08-04 pre-dawn; the 08-02 log was archived and this file opened fresh.

**What shipped**:
- **Mancini API path expunged** (`33b8917`) — `runbook/mancini/llm.py` deleted, every `ANTHROPIC_API_KEY_DIRECT` reference gone. `--extraction-json` (the in-session prompt parse) is now the only interpretive leg; `extraction-contract.md` preserves the SYSTEM_PROMPT/TOOL_SCHEMA knowledge the prompt path needs. Hybrid mode is an explicit branch now, not an exception handler, and a supplied-but-broken extraction halts rc=3 instead of silently demoting.
- **First in-session Mancini parse** (`9a2a8d4`) — 08-03 published with 68 levels and 16 commentary items against the deterministic scrape's 61/0.
- **Daily Payload → clipboard** (`8ed9faa`) — a completed interpretive parse now concludes by loading the clipboard. Closed a hole it exposed: the 08:15 cron's hybrid-skip path returned without touching the clipboard, which is exactly when it is stalest.
- **Phase B steps 1–2** (`151e16a`) — streamer carries per-stream schemas plus a new `es-mbp1` spec; compaction wired to `30 7 * * 1-6`. Readers taught to resolve `.jsonl.gz` first — without that, packing a day would have made it read as *absent* across replay, drills and measurement.
- **Live footprint v1** (`ba9e512`, `027a723`) — feeder, bridge bar channel, template live mode, page, tmux launcher.

**Live right now** (started 02:51 CT, tmux `steves-desk:footprint`):
- pane 1 CAPTURE `corpus_stream_databento.py --streams es,es-mbp1 --now --until-ct 15:05` — writing `data/corpus/2026-08-04/`
- pane 0 bridge `127.0.0.1:7788`, pane 2 feeder — 7 live bars built by 03:37
- page parked at `file://wsl.localhost/Zgent/tmp/desk-live-footprint.html`

**Open Work**:
- **st-6qx4 (P1, subagent running at handoff)** — streamer supervision. Its result had not arrived when this entry was written; check the task notification. Nothing supervises the capture process today, so a death goes unnoticed until someone looks.
- **st-re1o** — live footprint v1 done, four gaps named in the bead: rendering never verified in an actual browser, no supervision, live bars catch up instantly rather than animating (intra-bar fill present in payload, unused live), absorption still needs the MBP-1 wiring.
- **st-d5f** — Phase B un-deferred, gate cleared. Steps 3–5 remain. Three rulings still Steve's: capture window, whether our footprint replaces TradingView's as the watching surface, and whether the held ~$4 pre-build spend is now moot.
- **st-jwtn** — Schwab streaming preclusion, DEFERRED BY STEVE pending his own test of whether TOS conflicts with *any* API use or only streaming. Do not act on it.
- **st-939c** — `listlevels` regex drops `(major)` levels when Mancini leaves the paren unclosed; ate 7374 and 7353 on 08-03.
- **st-4mi4** — entitlement half resolved; Globex capture gap now closed by the running streamer.
- **st-ndc (P1)** — Schwab re-auth. **Per Steve's new rule, do not raise this until the day it expires (Wed 2026-08-05, 10:17 CDT), then raise it early.**

**Tried**:
- `probe_databento_access.py` for entitlement → **cannot answer it**; returns the public catalog and rate card identically whether subscribed or not. Do not reach for it again on that question. A live `db.Live` session is the only real test.
- Estimating overnight MBP-1 volume from one 30s probe → **wrong by ~3×**. Claimed ~4% of RTH intensity; actual capture shows ~18 KB/s, ~66 MB/h, so a full overnight is ~1.2 GB uncompressed — about a third of an RTH day, not a ninth. The scope doc's capture-window arithmetic is understated; do not quote it.
- Removing `bar_fill_steps` from `orderflow_drill.py` by span → **also removed `minute_candles`**. Caught by `test_day_browser` collection, not by review.
- Running the compaction wrapper on 07-31 → 4.0 GB to 148 MB (27.4×), read back to 473,507 trades intact.

**Files Changed**:
runbook/mancini/llm.py (deleted)
runbook/mancini/extraction-contract.md
runbook/mancini/parse.py
runbook/mancini/run.py
runbook/mancini/__init__.py
runbook/README.md
scripts/cron/mancini-preopen-wrapper.sh
scripts/cron/corpus-compact-wrapper.sh
scripts/corpus_stream_databento.py
scripts/live_footprint_feed.py
scripts/live_footprint_page.py
scripts/live-footprint-up.sh
scripts/drill_bridge.py
scripts/orderflow_drill.py
scripts/orderflow_drill_template.html
scripts/acuity_run2.py
scripts/score_recognizer.py
scripts/measurement/mp_day_scan.py
market/corpus/paths.py
market/orderflow/replay.py
market/orderflow/fill.py
docs/superpowers/specs/2026-08-03-phase-b-live-footprint-scope.md
tests/runbook/test_run.py
tests/runbook/test_parse.py
tests/market/corpus/test_stream_databento.py
tests/market/corpus/test_compact_databento.py
tests/scripts/test_live_footprint_feed.py
.github/workflows/ci.yml

---
