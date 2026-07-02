# DaysActivity - 2026-06-09

## 11:23 - Session Handoff [Day-type whippiness study + infra recovery]

**Summary**: Explored the dependability of early day-type judgements (V-days deliberately excluded) across the 243-day ES corpus and a causal 2:30-anchored fly study, then recovered the beads tracker after COO's embedded-Dolt repave and flagged a permission-gate drift.

**Findings** (research bead st-ydm, CLOSED with full detail):
- "Whippy" splits into magnitude vs shape, with opposite behavior. MAGNITUDE (range/path) persists strongly intraday — prior afternoon forecasts the final-30-min at path corr +0.74; calm vs hot prior afternoon → final-30 range median 10.75pt vs 22.25pt (~2.1x). SHAPE (chop/reversals) does NOT persist (corr ~0).
- Causal 2:30-anchored fly (center on 2:30 put-call-parity spot, 241 days): the forecastable magnitude is a **NO-GO tilt, not a buy signal**. Calm 2:30 → fly pins 35% / dead 42% / ends ~4pt from center; HOT 2:30 → pins 14% / DEAD 69% / ends ~8pt away. An earlier hindsight cut (fly centered on realized settle) falsely showed hot=deep-discount=buy; corrected by the causal run.
- Whip (exit give-back ~$1.40) is unforecastable (corr +0.07) → supports the fast-cuts discipline. Doctrine-consistent: calm=rotate/pin (flies OK), whippy=trend-away (flies at risk).

**Open Work**:
- st-nd5 (P2) — Scope long single-option directional 0DTE strategy (post-PDT pivot). **Next session's focus per Steve.**
- Deferred whippiness follow-ups (in st-ydm close): anchor-time sweep (2:00/2:30/2:45 "how early" curve); model actual dip-buy/rally-sell P&L.
- **DECISION PENDING (Steve)**: permission-gate drift — commit f2bdd87 also auto-allowed Bash(curl *) and Bash(echo *), contradicting the documented Schwab hard gate. Effective gate mostly holds (deny-list on schwab token paths + schwab-gate.sh hook + hobbled schwab-py), but config now disagrees with the written rule. Decide: remove curl/echo from allow, or update gate docs.
- For COO: beads has no Dolt remote configured (cross-machine sync off; durability via git JSONL export only).

**Tried**:
- `bd bootstrap` to recover beads → FAILED: pulled an empty Dolt remote and corrupted the local DB (wisps migration 0047). COO then repaved onto embedded Dolt (`bd init` + `export.auto`) → 55 issues restored, tracker functional.
- Hindsight-centered fly_batch dollar cut suggested hot afternoon = deep entry discount = buy signal → identified as a hindsight artifact; the 2:30-anchored causal study reversed it.

**Files Changed**:
None in the repo — this was a read-only analysis session; nothing persisted to tracked files. (Memory updated outside repo; .claude/state/checkpoint.json is gitignored. 6 pre-existing WIP files — mancini/parser.py, market/pricing/black_scholes.py, scripts/corpus_backfill_databento.py, tests/market/pricing/test_black_scholes.py, tests/market/test_ingest_databento.py, tools/tv_capture/tv_capture.py — predate this session and were NOT touched here.)

---
