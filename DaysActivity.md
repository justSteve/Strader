# DaysActivity - 2026-06-08

## 02:53 - Session Handoff [Datastream collection + late-day fly research]

**Summary**: Stood up forward datastream collection (Databento OPRA live, Schwab+GexBot 1-min poll) and built a fly-replay analysis tool + 246-day corpus batch that established the late-day butterfly edge is a **day-selection** problem, not blanket patience. (Session ran 06-08 evening past midnight; logged under 06-08.)

**Datastreams collected today** (all 3): Databento OPRA streamed live ~11:20–15:15 CT (816,941 ticks, clean auto-stop, compacted 320MB→10.3MB, 31×); Schwab + GexBot ran via corpus_poll (Steve launched). OPRA live is covered by the $199/mo OPRA sub (no per-GB charge); ES has no live sub → stays T+1 batch.

**Late-day fly batch verdict (246 days, 5-wide call, parity-centered at each day's pin):** wait→cheaper only **26%** of days (fly richens into pin on calm days); wait→less-drawdown mild ($0.35→$0.25, near-zero late on 51%); exit-whip ≥$0.50 on **17%** of days (validates "bank the near-max winner"); oracle payoff median +$3.63. Edge = identifying dislocation/whippy vs calm days.

**Open Work**:
- **[NEXT SESSION] Interpret the 13:00–15:00 re-run** — running now in tmux moocity steves-desk:fly-batch → `data/measurement/fly_batch_1300.log` (per-day rows overwrote `data/measurement/fly_batch.jsonl`). Wider window better tests "wait longer than reasonable."
- **[NEXT SESSION] "How well can we judge day-type (whippy), and how early?"** — Steve's key question. Day-type is non-stationary intraday (today: whippy early, settled final 1/2hr; a close-judgment wouldn't have held earlier). Full context in memory `project_pin_projection_research`.
- **Daily-collection schedule** deferred — gate 2/3 (tomorrow's fresh launch must produce a real raw `.dbn` archive) before wiring the 12:55 CT cron + `--yesterday` compaction. Gate 1/3 (clean stop) + 3/3 (compaction 31×) passed.
- **Pin-card logger** (log ~1pm GEX levels + settle daily) — offered, not built.
- **Gate-posture decision** — whether to relax the behavioral Schwab gate for read-only collection (Tier 1/2/3 lean given; no config changed).
- **[ALERT] Beads tracker still down** ("database st not found"); COO owns recovery. All session work committed bead-pending (referenced st-745 / st-1yp lineage), attach IDs retroactively.

**Tried**:
- Databento live billing — wrongly asserted live is metered ($336/GB from `list_unit_prices`); Steve corrected: OPRA Standard sub covers live. `list_unit_prices` = pay-as-you-go, not subscription billing. → corrected.
- LiveClient symbol map used `stype_in_symbol` (collapsed every contract to parent "SPXW.OPT") → fixed to `stype_out_symbol`; live probe caught it before any bad row landed.
- fly_replay first run gave −$233 flies → parent symbology blends ALL expiries; added expiry filter (0DTE only). Then −$0.50 residual = async last-trade noise, floored at 0 in the batch.
- Schwab refresh token was expired (invalid_grant); pre-flight reader caught it; Steve re-authed.

**Files Changed** (committed 847e4be, 34e1c53, a31b5c6 — all pushed):
scripts/corpus_stream_databento.py
scripts/corpus_compact_databento.py
scripts/probe_databento_access.py
scripts/corpus_poll.py
market/ingest/databento.py
market/entities/trade.py
market/corpus/paths.py
market/measurement/__init__.py
market/measurement/fly.py
scripts/measurement/fly_replay.py
scripts/measurement/fly_replay_batch.py
tests/market/corpus/test_stream_databento.py
tests/market/corpus/test_compact_databento.py
tests/market/corpus/test_schwab_stream.py
tests/market/test_ingest_databento.py
tests/market/measurement/test_fly_replay.py

---

## 10:06 - Tap In

Session start. Daily housekeeping: archived stale 2026-06-01 DaysActivity (empty header), created fresh file for today.

**[ALERT] Beads tracker down.** Dolt server running (PID 87409, :31611) but pointed at empty `.beads/dolt` (created today by my `bd dolt start`); local `embeddeddolt/st` clone has empty issues table; `issues.jsonl` deleted. Authoritative 55-issue dataset is on the GitHub remote (`refs/dolt/data`, reachable). Recovery: `bd bootstrap` (clone `st` from remote) — flagged for Steve, not run autonomously.

**Carried-forward beads** (from 2026-06-01 briefing, unconfirmed): st-r2o (P1, blocked on COO greek framing), st-745 (P2, V-day measurement — active), st-u32/st-lks (P2, unblocked), st-cgb (P2, possibly unblocked now corpus is backfilled), st-u29 (P3).

Full briefing in session-briefing.md.
