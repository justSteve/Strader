# DaysActivity - 2026-10-01

## 03:40 - Session Handoff [harness, gap audit, dedup + sweep definition, execd defects]

**Summary**: Built the execd scenario harness (st-ug1h) and ran two gap audits on Steve's ask. Fixed the corpus/live dedup that dropped 3-5% of ES volume (st-exmw; 575 was right, not 538) and redefined a sweep as one match event ≥ 200 lots (6.5/day). Made Session Δ equal the engine's CVD, stamped code revisions into the parity check, added a real-tape production fixture, merged 8 small reader/health fixes, and fixed 18 execd defects (restart after a replaced stop, fly SELL_TO_OPEN read as a close, trail locking a loss, lost triggered sends, split closes, partial entries, fees on closed P&L, and more). Everything is local (58 commits ahead); nothing is installed.

**Open Work**:
- Steve's calls: st-yeph (stop at/above the bid — refuse on the ticket?), st-a54y (H5: close-at-SPX level already crossed at the fill — fire?); st-91yu waits on st-yeph.
- Install: the execd changes need `bash deploy/install.sh --execd` while flat (pulls websockets); the parity timer needs a deploy/install.sh run; the footprint feeder picks up market/ changes at its midnight restart.
- Research, not started: st-peqp (large-lot definition vs match events); divergence calibration (PIVOT_FILTER_TICKS is an uncalibrated seed).
- Push held behind the st-5n3s review group.

**Tried**:
- Piping pytest through tail inside an `&&` chain hid a red suite, and a commit landed with an unbound `day` in the feeder; fixed in 50e43e2. Check `${PIPESTATUS[0]}` before committing.
- Naming .py files in a Bash command that also runs python trips the schwab gate (it glob-expands the tokens and found broker_schwab importers). Put such edits in a scratch script, or use Edit.
- Two attempted fixes were reverted as Steve's rulings, not gaps: shorts on contracts execd never traded stay loud (st-7ah8); a stop at/above the bid is not refused (09-17 "no hand holding"), parked as st-yeph.

**Files Changed**:
market/orderflow/ (replay, engine, fill, run_log, quotes, parity)
market/signals/orderflow_config
scripts/ (live_footprint_feed, live_parity_check, drill_bridge, orderflow_drill, orderflow_drill_template.html, mi_gauge, premarket_volume_profile, surface_liveness.sh)
tools/ (local_chart, context_strip)
execd/ (service, stops, schwab, watch, panel, bounds)
deploy/systemd/strader-parity-check.service
deploy/systemd/strader-parity-check.timer
docs/lexicon/lexicon.yaml
docs/measurement/2026-09-30-sweep-level-size.md
tests/execd/scenario/
tests/market/orderflow/test_realtape_production
tests/market/fixtures/es_ticks_realtape_20260930.jsonl.gz

---

## 00:35 - Session Handoff [execd stream, dollar stop, bracket fix, trail, iPad pass 4, sweep floor]

**Summary**: The 09-30 session (ran past midnight) shipped eleven local commits on top of the six held st-5n3s commits. The commits cover the ACCT_ACTIVITY doorbell (Steve's probe measured coexistence with TOS), dollar stops re-struck at the send, the fired-bracket bug and stop-follows-fill, Steve's trailing stop, iPad pass 4, and the sweep level floor; schwab-gate gate 8 was landed by Steve (27e78a0). Nothing is pushed and nothing is installed — the live service still runs 6734ac9 in paper.

**Open Work**:
- Scenario harness (st-ug1h) — next, per Steve: real service over the paper book on recorded tape, invariants every step, drives the page form. Then a sweep for other gaps of the same kind ("tests should have caught these").
- 17 commits held local (080914b..4d08b0b); do not push until Steve has stepped through the st-5n3s group. Steve installs via `bash deploy/install.sh --execd` while flat (needs network: websockets==16.0).
- Paper book carries a phantom short 1 SPXW 260930P07700000 from the 13:24 double bracket. Steve was given the stop/mv/start command; whether he ran it is unconfirmed.
- Schwab re-auth st-2exz: token expires 2026-10-05.

**Tried**:
- `bd update --notes` on st-8bls → replaced its existing notes. Restored from the session's earlier `bd show`. Use `--append-notes`.
- The first fired-bracket fix set the filled leg's id on the position → the close "cancelled" it, found it filled, and booked it twice (oversold). Only the sibling leg is held now.
- The sweep floor golden hash did not reproduce the old pin when the new field was stripped → two fixture sweeps had dust prices and genuinely changed (named in the repin comment).

**Files Changed**:
execd/schwab.py
execd/watch.py
execd/__main__.py
execd/service.py
execd/stops.py
execd/orderform.py
execd/bounds.py
execd/page.py
execd/orderpage.py
execd/panel.py
execd/README.md
deploy/execd-requirements.txt
docs/execution-engine-operations-manual.md
docs/patches/2026-09-30-gate-credential-reads.diff
docs/measurement/2026-09-30-sweep-level-size.md
docs/lexicon/lexicon.yaml
.claude/rules/shell-shim-hazards.md
market/orderflow/engine.py
market/orderflow/parity.py
market/signals/orderflow.py
market/signals/orderflow_config.py
market/emission/renderer.py
present/speech.py
scripts/schwab_stream_probe.py
scripts/measurement/sweep_level_size.py
scripts/orderflow_drill_template.html
tests/execd/test_stream.py
tests/execd/test_triggered.py
tests/execd/test_order_screen.py
tests/execd/test_wall.py
tests/test_stream_probe.py
tests/market/orderflow/test_engine.py
tests/market/orderflow/test_replay_golden.py
tests/market/orderflow/test_region_replay.py

---
