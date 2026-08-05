# Strader — Current Status

**Role**: SPX Options Trading Intelligence (Consumer tier)
**Bead Prefix**: `st`
**Status**: zgent (in-process toward certification)
**Last refreshed**: 2026-08-04 [st-d5f, st-re1o, st-itky, st-6qx4]

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
| GEXBot | **ACTIVE — State tier ($150/mo), resumed 2026-08-05** (pause ran 2026-07-03 → 08-05). Key verified live; forward collection running (stopgap: tmux `steves-desk:gexbot-collect`, 60s cadence → `data/corpus/<date>/gexbot.jsonl`; real service = st-p3lv). `/hist` Quant historical is NOT included at State (verified: permission denied) — 90-day backfill blocked pending Quant add-on decision (st-trbn deferred on it). Legacy GEX history remains 3 days (May 22, Jun 8–9). |
| Schwab API | `lib/schwab-py` on the `hobbled-readonly` fork — account/order/transaction methods physically removed. Only `broker_schwab/readers/{quote,chain}.py` are auto-allowed. |
| Databento | **CME Standard live GLBX verified 2026-08-03.** ES trades + MBP-1 capture continuously via `scripts/live-footprint-up.sh` (tmux `steves-desk:footprint`). OPRA live sub-covered. Historical corpus is tape-only — no GEX history. Quotes are NEVER backfilled: an uncaptured session is gone. |
| Mancini | Pre-open cron wired; `st-i68` PATH bug open against it. |
| Market internals | `scripts/mi_gauge.py`, captured on the 5-minute session cron. Single-sourced from Schwab — no cross-check exists (`st-jwtn`). |
| Live footprint | v1 running: bridge `127.0.0.1:7788` + JSONL feeder → `/tmp/desk-live-footprint.html`. Same surface as the replay drills; bars proven byte-identical to replay. Browser rendering not yet eyeballed. |

## Crons (weekdays, CT)

| Time | Job |
|------|-----|
| 06:30 | Corpus daily (COO-side wrapper) — Mon–Sat since `st-n42a`, so Friday's tape lands Saturday |
| 07:30 | Corpus compaction (`st-itky`) — Mon–Sat, packs the pulled day. Measured 27.4× on 07-31. Refuses to pack a day whose manifest is not healthy |
| 07:00 / 08:30 / 13:00 / 14:45 | Schwab stage-boundary snapshots |
| 08:15 | Mancini pre-open — **`st-i68` open** |
| 08:25 | Pre-open heartbeat + risk-state reset |
| every 5 min, 08:00–15:55 | Market-internals gauge |

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
4. **Live capture unsupervised** — supervisor is BUILT (`99ea95e`) but NOT
   installed; no crontab entry, so nothing watches the streamer yet. Installing
   it as proposed also extends capture into evening Globex, which is the
   capture-window ruling still outstanding. `st-6qx4`.
