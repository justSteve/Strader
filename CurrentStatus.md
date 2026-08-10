# Strader — Current Status

**Role**: SPX Options Trading Intelligence (Consumer tier)
**Bead Prefix**: `st`
**Status**: zgent (in-process toward certification)
**Last refreshed**: 2026-08-10 [st-a6zm, st-p3lv, co-hvxye]

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
| GEXBot | **ACTIVE — QUANT tier ($350/mo, one-month commitment) since 2026-08-05 PM** (State AM, upgraded same day; pause ran 07-03→08-05). Live **10-endpoint** collection in tmux `steves-desk:gex`: the full State package — {gamma,delta,vanna,charm} × {`_zero`,`_one`}, 87 strikes each — plus `classic/gex_zero/majors` and the **orderflow leg, which went live 2026-08-06 with 37 fields** (it was auto-skipping on entitlement before the upgrade; no code change was needed). 0DTE legs are requested first so a truncated cycle keeps what the fly window trades. Feed is **RTH-only** — collector DOWN outside 08:30–15:00 CT is normal. Now measured rather than asserted: on 2026-08-07 `spot_at_gamma_zero` sat frozen at one value from midnight, took its first new value at **08:30:02 CT**, updated on a ~76s cadence to **15:00:33 CT**, then went flat; Saturday 2026-08-08 never moved once across 1153 polls. The collector is gated to that window (`corpus_poll_gexbot.py`, restored 2026-08-10) and cron `*/2` restarts it inside the window via `scripts/cron/gexbot-supervisor-session.sh` [st-a6zm, st-p3lv]. **Consumer warning — `gexbot.jsonl` files dated 2026-08-09 or earlier are ~70% duplicate rows**: the collector polled around the clock, and a frozen feed returns the last RTH value unchanged, so an overnight row is not stale-but-plausible data, it is a verbatim repeat. 2026-08-07 holds 352 in-session rows against 783 repeats. Filter by timestamp — and never count, average, or weight these rows without deduplicating first. [co-hvxye] **A dedicated live 1 Hz orderflow leg runs beside the 60s collector since 2026-08-10** [st-ipn0]: `corpus_poll_gexbot_orderflow_1s.py` polls `/SPX/orderflow/orderflow` alone at ≥1.1s spacing (the vendor's stated per-metric ceiling), same 08:30–15:05 CT gate, writes flat rows to `data/corpus/<date>/gexbot_orderflow_1s.jsonl` (~1.3s native feed cadence, consecutive duplicates skipped), supervised by cron `*/2` via `scripts/cron/gexbot-orderflow-1s-supervisor.sh` in tmux window `gexbot-of1s`. This is the real-time spike-train read the 60s cycle cannot see; nightly `/hist` remains the archival 1s source. Program brief: `docs/a2a/2026-08-05-gexbot-quant-month-program.md`. Month-end sweep + downgrade decision ~Sep 1. |
| Schwab API | `lib/schwab-py` on the `hobbled-readonly` fork — account/order/transaction methods physically removed. Only `broker_schwab/readers/{quote,chain}.py` are auto-allowed. |
| Databento | **CME Standard live GLBX verified 2026-08-03.** ES trades + MBP-1 capture the session window 02:50–15:05 CT via `scripts/live-footprint-up.sh` (tmux `steves-desk:footprint`), now supervised. **GLBX historical is $0.00 on the Futures plan** (measured 2026-08-05, `--estimate-only`; OPRA control $6.07/2h), so an uncaptured GLBX session is **recoverable, not gone** — the old "quotes are NEVER backfilled" premise is false for GLBX and holds only for OPRA. **Daily OPRA import HALTED 2026-08-07** (`st-7av4`, Steve's call): historical OPRA is an ad hoc fetch now via `corpus_backfill_databento.py --opra`. The datastream gate no longer requires the stream; the six measurement scripts that read `databento_opra.jsonl` must each fail loudly on a day without it. Historical corpus is tape-only — no GEX history before 2026-08-05. |
| Mancini | Pre-open cron wired; `st-i68` PATH bug open against it. |
| Market internals | `scripts/mi_gauge.py`, captured on the 5-minute session cron. Single-sourced from Schwab — no cross-check exists (`st-jwtn`). |
| Live footprint | v1 running: bridge `127.0.0.1:7788` + JSONL feeder → `/tmp/desk-live-footprint.html`. Same surface as the replay drills (one template, `.live` mode gate hides drill-only controls); bars proven byte-identical to replay. **Rendering confirmed live by Steve 2026-08-04.** Carries the per-bar emissions row + rollover panel. Intra-bar progressive rendering built and tested but **NOT deployed** (`st-e91l`) — needs a feeder+bridge restart, do it after a 15:05 stop. **Every closed bar now carries a `gex` stamp** (`st-8ywx`, live since 2026-08-07): flip, 0DTE and 1DTE brackets, net-GEX regime sign, distance to flip, which majors the bar's range covered, and the age of the poll. Resolved at-or-BEFORE the bar close — never lookahead — and applied *after* the recogniser judges the bar, so it is recorded alongside recognition and can never become an input to it. Absent feed degrades to no stamp, never to a broken bar. |

## Crons (weekdays, CT)

| Time | Job |
|------|-----|
| 06:30 | Corpus daily (COO-side wrapper) — Mon–Sat since `st-n42a`, so Friday's tape lands Saturday |
| 07:30 | Corpus compaction (`st-itky`) — Mon–Sat, packs the pulled day. Measured 27.4× on 07-31. Refuses to pack a day whose manifest is not healthy |
| 07:00 / 08:30 / 13:00 / 14:45 | Schwab stage-boundary snapshots |
| 08:15 | Mancini pre-open — **`st-i68` open** |
| 08:25 | Pre-open heartbeat + risk-state reset |
| every 5 min, 08:00–15:55 | Market-internals gauge |
| every 2 min, all day | **Capture supervisor** (`st-6qx4`, installed 2026-08-05) — relaunches a dead streamer inside the 02:50–15:05 window; idempotent by process, not tmux window. **Does not survive a tmux server death**: the `moocity` server died ~19:55 on 2026-08-05 and took the supervisor down with the collectors it was supervising. A supervisor hosted inside the thing it supervises is not one. Settles `st-p3lv` toward a systemd unit |

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
5. **`rcl` is sticky on the Mancini Pine indicator** — `lvState` 3 (RECLAIMED)
   has no outgoing transition, so a level that reclaims and then breaks again
   reads `rcl` for the rest of the session. Observed live on 7741, 2026-08-06.
   Must be fixed together with the asymmetric hysteresis (break needs a 2pt
   buffer, reclaim needs none) or the label oscillates. Not yet beaded.
6. **Capture window ruled 2026-08-05** — live capture is session-only
   (02:50–15:05 CT); the uncovered hours backfill free. The backfill leg is
   built-but-not-written (`st-wy6u`) and must never run while a feeder is
   tailing the day, so 24h coverage is not yet actually complete.
