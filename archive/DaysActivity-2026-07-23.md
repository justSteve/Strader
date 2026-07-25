# DaysActivity - 2026-07-23

## 09:52 - Session Handoff [Absorption + MI Gauge + Mancini v2 + Token]

**Summary**: One session spanning Wed 7/22 → Thu 7/23. Bought the approved MBP-1 day ($1.21 for 7/2 full RTH, 9.06M book events) and built AbsorptionTracker end-to-end — band-tolerant level episodes, refill counting, floors calibrated on the real day, parity harness extended (st-9vl closed). Designed and built the MI composite gauge (st-3fr): $TICK percentile scale calibrated from a 31-session backfill (folklore ±1000 is a 1-in-10-session event; real climax ±450–600 by bucket), MIGauge engine with named drivers, replay + live CLI; replay of 7/22 showed breadth diverging at the 9:05 high and pegged −92 during the 9:30 flush — the sell-into-climax bell for Steve's +118% 7520 put. Found and fixed the Schwab same-day clamp (negatives floored to 0 in intraday minute history; just-settled day arrives duplicated; T+1 heals; live gauge rebuilt on quote sampling). Mancini pipeline v2 completed and st-ze6 closed: --from-blob fetch, plan-day from title, deterministic list extractor (69/69 on the real 7/23 letter, parity gate), hybrid mode with no-clobber guard, morning chain riding corpus_daily's cron. July 22 + 23 plans processed via in-session extraction (68 + 71 levels, validated). Token re-minted by Steve (one code-expiry retry; next wall ~7/30; st-z6p closed). Deck freeze committed (st-sfb closed), stray st-aeg closed, GEXBot pause memorized. Two subs drove the 7/23 Mancini import and Databento fill in parallel. All work committed and pushed (85ad2e5..cb0c5c9, 9 commits, 345 tests green).

**Open Work**:
- st-3fr (in progress) — MI gauge remaining: drill-deck TICK overlay, live breadth unavailable (ADD/VOLD quotes dead intraday, T+1 only), regime-weight calibration as forward capture accumulates
- Steve to post the schwab-py Discord draft (same-day clamp forensics) — drafted in-session, his call
- co-8gp (COO) — API credits still block interpretive commentary; hybrid mode publishes deterministic levels meanwhile; auto-restores when funded
- st-096 — remaining AC: daily Schwab pull cron wiring, stage-boundary quote poll, May snapshot-stop root cause
- Tomorrow pre-open: `tmux -L moocity new-window -n gauge '.venv/bin/python scripts/mi_gauge.py --live'` before 8:30 for full-session spine semantics
- Next token wall ~2026-07-30 (heartbeat warns Tue/Wed AM); consider the warm-up-login trick before the real paste

**Tried**:
- Strict single-price absorption episodes → only ever completed refill cycles in closing-auction churn (all 14 hits 14:58–15:00); 2-tick band tolerance is what surfaced mid-session defenses
- Schwab minute history for live $TICK → same-day candles clamp negatives to 0 (quote endpoint correct at the same moment); live gauge must sample quotes, not candles
- `--days 3` internals re-pull of the just-settled day → every minute duplicated (healed segment first, stale clamped second); first-wins dedup + implausibility guard added
- Mancini LLM leg 400 with bare status → error body revealed credit exhaustion; llm.py now surfaces the API's own message
- Web survey of the same-day clamp → undocumented anywhere public (schwab-py docs/issues, TDA-era trackers, useThinkScript); our forensics are the first account
- OAuth paste attempt #1 → dead code (~30s expiry); warm login made attempt #2 trivial

**Files Changed**:
market/entities/book.py
market/orderflow/absorption.py
market/orderflow/quotes.py
market/orderflow/parity.py
market/signals/orderflow.py
market/signals/orderflow_config.py
market/signals/internals.py
market/signals/internals_config.py
market/internals/gauge.py
market/internals/feed.py
market/corpus/paths.py
broker_schwab/readers/history.py
runbook/mancini/run.py
runbook/mancini/llm.py
runbook/mancini/fetch.py
runbook/mancini/listlevels.py
runbook/mancini/tests/test_listlevels.py
runbook/mancini/commentary/2026-07-22.jsonl
runbook/mancini/commentary/2026-07-23.jsonl
scripts/corpus_pull_databento_es_mbp1.py
scripts/corpus_pull_internals.py
scripts/corpus_daily.py
scripts/mi_gauge.py
scripts/regen_parity_snapshot.py
scripts/measurement/absorption_calibrate.py
scripts/measurement/internals_calibrate.py
docs/drills/scenario-catalog.md
docs/drills/scenario-deck.json
docs/measurement/internals-tick-seed-2026-07-22.md
tests/market/orderflow/test_absorption.py
tests/market/orderflow/test_parity_harness.py
tests/market/internals/test_gauge.py
tests/market/fixtures/es_mbp1_golden_20260702.jsonl.gz
tests/market/fixtures/parity/expected_absorption_20260702.json
tests/runbook/test_run.py
tests/scripts/test_scenario_deck.py

---
