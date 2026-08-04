# DaysActivity - 2026-08-04

## 09:32 - Session Handoff [Live Footprint Painting — Boot Path Fixed]

**Summary**: The live footprint renders — Steve confirmed it painting mid-session, the first time anyone has watched it. Getting there took fixing three live-only boot crashes that the headless data-path proof could never have caught.

**Live at handoff** (tmux `steves-desk:footprint`):
- CAPTURE pid 496170, **6h10m up** — 63 MB ES trades, **1.2 GB** MBP-1
- **215 live bars**; page confirmed rendering at `file://wsl.localhost/Zgent/tmp/desk-live-footprint.html`
- ES ran to ~7695 — through Mancini's 7683 major and out the top of his 08-04 ladder

**Fixed** (`ea77d7a`) — three defects, all live-only, firing in sequence at page init:
1. **The killer.** The level-chip loop called `addChip(label, DATA.levels[k])` and `fmtPrice` does `p.toFixed()`. A live page has no session-derived levels at boot, so the first undefined price threw at the TOP of the boot script — nothing below ran, no bridge, no poller, no bars. Chrome rendered and the page sat empty, which reads as a network fault and is not one.
2. `seekTo(0)` on an empty tape: the clamp yields `t=0`, the loop runs once, `bars[0].d` throws.
3. `connectBridge` was one-shot — the launcher starts bridge and page together, so losing that race left a live page dead with nothing retrying.

Every other `DATA.*` access was already guarded with `|| []`; `DATA.levels[k]` was the lone unguarded one, because a replay always has session levels.

**Open Work**:
- `st-b0n9` (NEW) — live emissions panel: show what the stack emitted at a given bar, via a rollover panel over the control strip. **Scope warning in the bead**: the live feeder does not run the engine at all, so this is putting `parity.full_stack_events` into the live path, not a UI tweak. Deferred deliberately; `replay_day.py` gives the full emission record for today after the close.
- `st-7av4` (P1) — stop the daily OPRA pull. **After the close**, four code sites move together.
- `st-6qx4` — supervisor built (`99ea95e`), NOT installed. Its default extends capture into evening Globex, which is the capture-window ruling.
- `st-re1o` — v1 now visually confirmed. Remaining: bridge/feeder unsupervised, live bars catch up instantly rather than animating.
- `st-ndc` — **due tomorrow (Wed 08-05, 10:17 CDT). Raise early that morning per the standing rule.**

**Tried**:
- Guessed twice at the blank-page cause (empty-tape `seekTo`, then `connectBridge` retry) → **both were real bugs but neither was the one**. What actually found it was enumerating every `DATA.*` access and checking each against the stub payload. Guessing cost two rounds; the enumeration took one command.
- Reasoning that the headless proof covered the page → **it covered the DATA path, not the BOOT path**. Bars in, bars out, byte-identical — and three crashes upstream of any of that.

**Files Changed**:
scripts/orderflow_drill_template.html

---

## 08:50 - Session Handoff [First Full Mancini Procedure + OPRA Cost Ruling]

**Summary**: Ran the Mancini Parse end to end for the first time under the new procedure — clipboard loaded automatically — and settled that the OPRA subscription's replacement by the Futures plan means the daily OPRA pull is now metered and should stop. Live capture has been up since 02:51 and is healthy.

**Live at handoff** (tmux `steves-desk:footprint`):
- CAPTURE pid 496170, **5h31m up** — 39 MB ES trades, 757 MB MBP-1 into `data/corpus/2026-08-04/`
- bridge + feeder alive, **124 live bars** built
- `capture_health.py --porcelain` reports `status=ok actionable=0`

**Decisions taken**:
- **`st-7av4` (P1) — stop the daily OPRA pull.** Steve confirmed on the Databento portal that the $199 OPRA subscription is gone and the Futures plan replaced it, so `corpus_daily`'s daily OPRA pull has been running as usage-billed historical (~$280/GB, est. ~$6.40/day, ~$134/mo — estimate only, record size inferred). **Schwab cannot replace it**: no historical options tape, quotes/chains are now-only. Seven measurement tools read that tape, including `fly_replay.py`, which reconstructs a butterfly's price path over the final hour — the instrument that measures the actual edge. What makes stopping safe is the asymmetry: MBP-1 live quotes are captured forward or lost forever, but historical OPRA is purchasable any time, so the daily pull buys only convenience. **Apply after the close, not mid-session** — the gate change risks the pre-open path.
- **Supervisor built but NOT installed** (`st-6qx4`, commit `99ea95e`). Its default is round-the-clock, so installing as proposed extends capture past 15:05 into evening Globex. That is the capture-window ruling Steve has been reserving — needs his consent, both crontab variants are in the bead.

**Open Work**:
- `st-7av4` — four code sites must move together: `gate.py DEFAULT_REQUIRED_STREAMS`, the compaction wrapper's `REQUIRED`, `corpus_daily`'s stream/window maps plus its now-false "OPRA flat-fee" comment, and the streamer's stale `--streams opra` default (wrong regardless).
- `st-6qx4` — install decision pending. Supervisor gaps it names: holidays unmodeled, a legitimate second capture reads as `duplicate`, **bridge and feeder are unsupervised** so a dead feeder freezes the live page looking like a quiet tape, no night push.
- `st-re1o` — **the live footprint has still never been eyeballed in a browser.** Data path proven, rendering unverified. 124 bars are sitting there waiting.
- `st-d5f` — capture-window ruling, whether our footprint replaces TradingView's, and the held pre-build spend.
- `st-jwtn` — Schwab streaming preclusion, still parked on Steve's own TOS-vs-API test.
- `st-ndc` — **due tomorrow (Wed 08-05, 10:17 CDT). Raise it early that morning, per the standing rule; not before.**

**Tried**:
- Suspecting the supervision sub was hung after 2.5h of no file writes → **it was not**; it ran 5.5h and completed with 67 tests. File mtimes are a poor liveness signal for an agent that spends its time testing.
- Expecting the OPRA switch to have broken the gate and compaction → **it had not**. This morning's 06:30 pull got 475,073 OPRA cycles cleanly, because historical is usage-billed rather than subscription-gated. The breakage was economic, not functional — checking beat assuming.

**Files Changed**:
runbook/mancini/parsed/2026-08-04.json
runbook/mancini/commentary/2026-08-04.jsonl
runbook/mancini/charts/2026-08-04.pine
runbook/mancini/charts/2026-08-04.payload.txt

---

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
