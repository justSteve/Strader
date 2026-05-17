# Strader → COO: ORB Backtester — Approach for Code Planning

**From:** Strader
**To:** COO
**Date:** 2026-05-17
**Re:** Code planning and implementation support for ORB backtesting

---

## Context

We're expanding Strader's 0DTE SPX strategy from late-day butterflies only to include Opening Range Breakouts as a secondary strategy. We've selected LuxAlgo's Ultimate ORB indicator as the charting tool. Now we need to validate the approach with historical data before trading it.

## What Exists

- Schwab API auth is working (token-file pattern, confirmed)
- schwab-py v1.5.1 installed in Strader's .venv
- Read-only readers exist: `schwab/readers/quote.py`, `schwab/readers/chain.py`
- schwab-py has convenience methods for historical data:
  - `get_price_history_every_minute()` — up to 48 days
  - `get_price_history_every_five_minutes()` — up to 9 months
  - All return OHLCV candles

## What We Need Built

### 1. Historical Price Reader (`schwab/readers/history.py`)

New reader script following the same pattern as `quote.py` and `chain.py`. Pulls intraday bars for `$SPX` (and optionally `/ES`) via schwab-py's `get_price_history` methods. Auto-allowed like the other readers.

### 2. ORB Backtester

Simulates the ORB strategy against historical data:

- For each trading day in the dataset:
  - Define the opening range (high/low of first 15 or 30 min)
  - Detect breakouts (price exceeds range high or low)
  - Classify breakout volume as HV or LV (relative to 20-period avg)
  - Simulate entry at breakout, stop at opposite side of range
  - Track targets at 1x and 2x range width
  - Score: win/loss, P&L, max drawdown
- Output: summary stats, per-day results, HV vs LV win rate comparison

### 3. Approach Options

**Option A: Custom Python** — build the sim loop ourselves with pandas. Full control, lightweight, no new deps.

**Option B: vectorbt** — mature backtesting library, handles vectorized simulation, built-in stats/reporting. Heavier dependency but less code to write and maintain.

Strader leans toward Option A given that the strategy logic is simple (breakout detection + fixed stop/target) and we'd avoid a large dependency. But COO should weigh in on what fits enterprise conventions.

### Constraints

- All code lives in Strader repo (`schwab/` and `tools/`)
- Schwab API hard gate applies — readers are auto-allowed, but Steve runs anything beyond readers via `scripts/run.sh`
- Reader scripts follow the existing pattern in `schwab/readers/`

## Ask

COO: please review and advise on:

1. Directory/module structure for the backtester
2. Option A vs B (custom pandas vs vectorbt)
3. Any enterprise conventions that apply (testing, output format, etc.)
4. Implementation plan / task breakdown
