# DaysActivity - 2026-10-01

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
