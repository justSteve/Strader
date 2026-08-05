# Strader — Current Status

**Role**: SPX Options Trading Intelligence (Consumer tier)
**Bead Prefix**: `st`
**Status**: zgent (in-process toward certification)
**Last refreshed**: 2026-08-05 [st-6qx4, st-btu, st-q5xu, st-e91l, st-g63j]

> Standing operational snapshot — what is wired up, live, or paused right now.
> Session history lives in `DaysActivity.md`; work lives in beads; durable
> knowledge lives in `knowledge/index.md`. This file holds none of those.
> The `/handoff` skill refreshes it.

## Phase

Live trading opened **2026-08-01** on graduated sizing — a hard start, not a
full-size one. Growth is earned (`knowledge/` grow-into-the-system ruling).
The fundamental-units training sequence is mid-flight; drills unlock only on a
summative pass.

## Data and Instruments

| Surface | State |
|---------|-------|
| TradingView MCP | **Removed.** No `.mcp.json`. Chart state comes from screenshots; Pine scripts are pasted by Steve by hand. |
| GEXBot | **ACTIVE — QUANT tier ($350/mo, one-month commitment) since 2026-08-05 PM** (State AM, upgraded same day; pause ran 07-03→08-05). Live 6-endpoint collection in tmux `steves-desk:gexbot-collect` (orderflow leg auto-skips — entitlement missing despite Quant rollup, raise with vendor if it persists). **90-day /hist backfill running** → `data/corpus/gexbot-hist/` (~65-113MB/category-day, manifest.jsonl tracks fetched/denied). Program brief: `docs/a2a/2026-08-05-gexbot-quant-month-program.md`. Month-end sweep + downgrade decision ~Sep 1. |
| Schwab API | `lib/schwab-py` on the `hobbled-readonly` fork — account/order/transaction methods physically removed. Only `broker_schwab/readers/{quote,chain}.py` are auto-allowed. |
| Databento | **CME Standard live GLBX verified 2026-08-03.** ES trades + MBP-1 capture the session window 02:50–15:05 CT via `scripts/live-footprint-up.sh` (tmux `steves-desk:footprint`), now supervised. **GLBX historical is $0.00 on the Futures plan** (measured 2026-08-05, `--estimate-only`; OPRA control $6.07/2h), so an uncaptured GLBX session is **recoverable, not gone** — the old "quotes are NEVER backfilled" premise is false for GLBX and holds only for OPRA. Historical corpus is tape-only — no GEX history. |
| Mancini | Pre-open cron wired; `st-i68` PATH bug open against it. |
| Market internals | `scripts/mi_gauge.py`, captured on the 5-minute session cron. Single-sourced from Schwab — no cross-check exists (`st-jwtn`). |
| Live footprint | v1 running: bridge `127.0.0.1:7788` + JSONL feeder → `/tmp/desk-live-footprint.html`. Same surface as the replay drills (one template, `.live` mode gate hides drill-only controls); bars proven byte-identical to replay. **Rendering confirmed live by Steve 2026-08-04.** Carries the per-bar emissions row + rollover panel. Intra-bar progressive rendering built and tested but **NOT deployed** (`st-e91l`) — needs a feeder+bridge restart, do it after a 15:05 stop. |

## Crons (weekdays, CT)

| Time | Job |
|------|-----|
| 06:30 | Corpus daily (COO-side wrapper) — Mon–Sat since `st-n42a`, so Friday's tape lands Saturday |
| 07:30 | Corpus compaction (`st-itky`) — Mon–Sat, packs the pulled day. Measured 27.4× on 07-31. Refuses to pack a day whose manifest is not healthy |
| 07:00 / 08:30 / 13:00 / 14:45 | Schwab stage-boundary snapshots |
| 08:15 | Mancini pre-open — **`st-i68` open** |
| 08:25 | Pre-open heartbeat + risk-state reset |
| every 5 min, 08:00–15:55 | Market-internals gauge |
| every 2 min, all day | **Capture supervisor** (`st-6qx4`, installed 2026-08-05) — relaunches a dead streamer inside the 02:50–15:05 window; idempotent by process, not tmux window |

First full Monday-morning fire: **2026-08-03**.

## Risk Posture

`config/risk.yaml` snapshots into `data/risk/<day>.json` at the 08:25 reset;
the day trades against the snapshot, so edits take effect tomorrow. State flips
to **HALTED** on a daily-loss breach.

- Daily stop −$300 · max 2 open positions · escalation above $5,000 notional
- Per-strategy: flies 3×$150 · ORB 1×$100 · scalps 3×$100
- **`account_balance_usd` is `null`** — the 2%-per-trade cap is **unarmed**.
  Every number above is Strader's graduated-sizing default, not Steve's ruling.

## Execution Gate

Strader authors trade code. Steve alone executes, via `./scripts/run.sh`.
No autonomous orders, ever.

## Session Lifecycle

`/tap-in` at start, `/handoff` at end. The checkpoint loop was discontinued
2026-07-13 and should not be reintroduced.

## Comms

`gc mail` is dead from Strader in both directions — two COO-side defects (city
resolution walks up from cwd and Strader is out-of-tree; the moocity store is
missing its `leases` table). The working channel is file-convention A2A under
`docs/a2a/`.

## Attention Items

1. **Risk cap unarmed** — `account_balance_usd: null`. Steve's ruling on the
   whole risk table is outstanding.
2. **`st-i68`** — Mancini pre-open cron fails on cron PATH (Azure CLI not
   resolvable). Fires every weekday at 08:15 until fixed.
3. **`st-08p` blocked externally** — training steps 3–5 need Steve's NotebookLM
   upload and COO's deck import.
4. **Recognizer is direction-blind upward** — all four setups are downside
   forms (no failed-breakout), and every Mancini level enters as
   `kind=support`, including parsed **resistances**. A rejection at overhead
   supply emits as a bullish `failed_breakdown`. Treat recognizer reads at
   resistance levels as unreliable in direction. Two calls outstanding from
   Steve: the mirrored setup's name, and whether to apply the interim
   kind-filter-to-supports the acuity path already uses. `st-q5xu`, `st-tme`.
5. **Capture window ruled 2026-08-05** — live capture is session-only
   (02:50–15:05 CT); the uncovered hours backfill free. The backfill leg is
   built-but-not-written (`st-wy6u`) and must never run while a feeder is
   tailing the day, so 24h coverage is not yet actually complete.
