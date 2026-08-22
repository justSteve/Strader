# Strader — Current Status

**Role**: SPX Options Trading Intelligence (Consumer tier)
**Bead Prefix**: `st`
**Status**: zgent (in-process toward certification)
**Last refreshed**: 2026-08-21 [st-9bsi, st-dioq, st-nujt; earlier 2026-08-20 st-ksgu, st-cc5k, st-1bv1, st-88ei; earlier 2026-08-19 st-tme, st-q5xu, st-7kmt, st-gno7; earlier same day st-vxbw, st-135m, st-kxnv; prior 2026-08-17 st-slj4, st-n0qm.5; 2026-08-13 st-aski, st-ad6p, st-g0or, st-75z0, st-pfrz, st-4ld0, st-xxo0, st-ylqw]

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
| Schwab API | `lib/schwab-py` on the `hobbled-readonly` fork — account/order/transaction methods physically removed. Only `broker_schwab/readers/{quote,chain}.py` are auto-allowed. **The `schwab-gate.sh` PreToolUse hook was DORMANT from May until 2026-08-13** — it read the bare `.command` key where the payload nests at `.tool_input.command`, so all five gates returned allow without inspecting anything. Fixed and installed with Steve's approval [st-ad6p]: reads the nested key, **fails closed** on any other shape, and gate 3 now blocks by *import reachability* (any `.py` importing `schwab` or `broker_schwab`, readers excepted) rather than by the old blanket ban on `scripts/` — 65 `.py` files live there and only 11 reach the API. Pinned by `tests/test_schwab_gate_hook.py`. **Correction carried into `CLAUDE.md` and the rule file the same day:** the permissions layer never gated interpreters — `python3`, `bash`, `curl`, `echo` are all auto-allowed; only `sh`, `source`, `touch` are absent. Through the dormant period the structural fork was the *only* live protection. |
| Entitlements | **`config/entitlements.yaml` is the single home** for subscription/tier/price state [st-g0or], probed by `scripts/entitlements_probe.py` (local files only, no vendor API). Splits **PROBED** (re-derived each run) from **DATED** (asserted, stamped, aged; `NEVER` renders as NEVER, not as a guess). Bundle docs and COO's conventions point at it — **never restate figures anywhere else**. Read by tap-in step 4d. Open items only Steve can close are listed by the probe every run: Databento's actual billed amount, **Schwab market-data rights (real-time vs delayed — unrecorded, so no agent should call reader quotes real-time)**, TradingView tier, LuxAlgo, and the Mancini newsletter. |
| Databento | **CME Standard live GLBX verified 2026-08-03.** ES trades + MBP-1 capture the session window 02:50–15:05 CT via `scripts/live-footprint-up.sh` (tmux `steves-desk:footprint`), now supervised. **GLBX historical is $0.00 on the Futures plan** (measured 2026-08-05, `--estimate-only`; OPRA control $6.07/2h), so an uncaptured GLBX session is **recoverable, not gone** — the old "quotes are NEVER backfilled" premise is false for GLBX and holds only for OPRA. **The MBP-1 T+1 backfill actually performs that recovery now** (st-xxo0 closed 2026-08-13, `a011873`): authorization derives from the entitlements registry (`databento_plan: active`) instead of the stale five-date July list, a still-missing day raises an `mbp1_gap` alert, and the probe carries an "ES MBP-1 depth landing" line. Collectors run under systemd timers as of 2026-08-13 (COO cutover, st-pgfe; capture 02:50, gexbot+orderflow-1s 08:30 CT). **Daily OPRA import HALTED 2026-08-07** (`st-7av4`, Steve's call): historical OPRA is an ad hoc fetch now via `corpus_backfill_databento.py --opra`. The datastream gate no longer requires the stream; the six measurement scripts that read `databento_opra.jsonl` must each fail loudly on a day without it. Historical corpus is tape-only — no GEX history before 2026-08-05. **Two further units run supervised and were missing from this table until 2026-08-21:** `strader-capture-evening.service` (evening leg of the ES tape) and `strader-orderflow-sentinel.service` (`st-n0qm.9`). **MBP-1 doubling guard closed 2026-08-20** (COO, `013832e`): `corpus_daily.py` tested stream *health* rather than *rows*, so reconnect notes on a healthy stream triggered a batch pull on top of a live tape. **2026-08-19 depth repaired 2026-08-21** (COO, `84e9b55`) — 5,440,418 duplicate batch rows dropped, 6,937,164 live kept, verified independently by Strader; `scripts/corpus_repair_doubled_day.py` is the reusable tool, dry-run by default. |
| Mancini | **08:15 overnight refresh live since 2026-08-18** (`st-vxbw`): the pre-open job's good case (an in-session parse exists) now re-renders the plan doc with the level-interaction section brought from the letter's write-time to now (the parse may have run at 01:00 CT); manual: `PYTHONPATH=. .venv/bin/python -m runbook.mancini.refresh --open`. Human-facing timestamps render CT (Steve 2026-08-18). Pre-open cron wired and working, verified rc=0 end to end on 2026-08-10. The `st-i68` PATH bug and the `st-1qpz` gate bug are both fixed and closed. **Blob ingress depends on Azure subscription `38b503d4…`**: it sat in `Warned` (read-only — key listing refused, no new blobs 08-14→08-17 AM) until Steve fixed billing in the portal 2026-08-17 ~11:00 CT; the Sunday resend then landed and the 08-17 plan parsed clean (78 levels, 10 commentary). Check `az rest …/subscriptions/38b503d4… → state` first if `fetch_latest` ever fails with `ReadOnlyDisabledSubscription`. |
| Market internals | `scripts/mi_gauge.py`, captured on the 5-minute session cron. Single-sourced from Schwab — no cross-check exists (`st-jwtn`). |
| Live footprint | **Coach cursor since 2026-08-18** (`st-135m`): coach verbs `point {bar, price, text, pulse, hold_ms}` / `clear` draw a pointer on a cell through the bridge (`tools/coach.py point --bar I --price P --text …`); confirmed on Steve's page 08-18 13:03 CT. **Known gap (`st-kxnv`, open):** the feeder reads Mancini anchors once at start and the unit restarts at 00:00 CT, before the morning parse — the recognizer runs anchorless until the feed unit is restarted after the parse; the page's level lines re-render on demand (`scripts/live_footprint_page.py`). **Under systemd since 2026-08-16** (`strader-drill-bridge.service` + `strader-footprint-feed.service`, Watcher V2 Phase 2b `a170a5a`); the bridge serves the page itself and it is on the tailnet at `https://mydesk-1.tail89f676.ts.net/footprint/`; producer health dots on the HUD; cell cues (Phase 1) and the anchored aggressor volume profile (Phase 2) live on the page. Inference seam filed as **Emission And Packet Schema** (`st-n0qm.5`) + tape reader (`st-n0qm.6`) + hindsight grading (`st-n0qm.7`) — brief `docs/plans/2026-08-16-inference-layer-brief.md`. Original v1 text follows. v1: bridge `127.0.0.1:7788` + JSONL feeder → `/tmp/desk-live-footprint.html`. Same surface as the replay drills (one template, `.live` mode gate hides drill-only controls); bars proven byte-identical to replay. **Rendering confirmed live by Steve 2026-08-04.** Carries the per-bar emissions row + rollover panel. Intra-bar progressive rendering built and tested but **NOT deployed** (`st-e91l`) — needs a feeder+bridge restart, do it after a 15:05 stop. **Every closed bar now carries a `gex` stamp** (`st-8ywx`, live since 2026-08-07): flip, 0DTE and 1DTE brackets, net-GEX regime sign, distance to flip, which majors the bar's range covered, and the age of the poll. Resolved at-or-BEFORE the bar close — never lookahead — and applied *after* the recogniser judges the bar, so it is recorded alongside recognition and can never become an input to it. Absent feed degrades to no stamp, never to a broken bar. |

## Crons (weekdays, CT)

| Time | Job |
|------|-----|
| 06:30 | Corpus daily (COO-side wrapper) — Mon–Sat since `st-n42a`, so Friday's tape lands Saturday |
| 07:30 | Corpus compaction (`st-itky`) — Mon–Sat, packs the pulled day. Measured 27.4× on 07-31. Refuses to pack a day whose manifest is not healthy |
| 07:00 / 08:30 / 13:00 / 14:45 | Schwab stage-boundary snapshots |
| 08:15 | Mancini pre-open — **green**. The Azure-CLI PATH bug (`st-i68`) was already fixed: `az` resolves via the pinned interop path and the job exited rc=0 on 08-04 through 08-07. Its 08-10 failure was the datastream gate (`st-1qpz`), fixed the same day |
| 08:25 | Pre-open heartbeat + risk-state reset |
| every 5 min, 08:00–15:55 | Market-internals gauge |
| — (retired 2026-08-13) | **`*/2` capture and GexBot cron supervisors removed** in COO's systemd cutover (`st-pgfe`): `strader-capture.timer` 02:50 CT, `strader-gexbot.timer` + `strader-gexbot-orderflow-1s.timer` 08:30 CT, `Restart=on-failure` units. `COO/SCHEDULE.md` is the catalogue. |

> **Erratum, 2026-08-10.** This table used to say the capture supervisor "does
> not survive a tmux server death" and that the 2026-08-05 19:55 incident took it
> down with its collectors — concluding `st-p3lv` needed a systemd unit. Wrong on
> the mechanism. The supervisor is a **cron** job, and its wrapper has an explicit
> `has-session` branch that bootstraps a session when the socket is gone. 19:55 is
> outside the 02:50–15:05 window, so it correctly stood down; the GexBot
> collector, which had no supervisor at all, simply stayed dead. That is why the
> 2026-08-10 build reuses this cron supervisor rather than introducing systemd.

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

`gc mail` is dead from Strader in both directions. As of 2026-08-13 it no longer
fails *quietly*: the `gc-mail-stub.sh` PreToolUse hook **blocks** a `gc`
invocation and points at `docs/a2a/`. The binary still resolves at
`/usr/local/bin/gc`, which is why a stub was needed rather than relying on
command-not-found.

The working channel is A2A under `docs/a2a/`, and it now has a bell and a
receipt [st-75z0]:

- **`docs/a2a/inbox.md`** — append-only ledger, one line per peer event
  (`COMMIT`/`MEMO`/`ACK`/`SERVICED`/`DIGEST`). Every peer commit into this repo
  appends a line **in the same commit** — mandatory for `CLAUDE.md`, `.claude/**`,
  settings, skills, Schwab-adjacent paths, `knowledge/**`, and peer `st-` bead
  actions. A commit without its line is a protocol violation regardless of
  authorization; the next session appends the missing line itself and files a bead.
- **`docs/a2a/receipt-protocol.md`** — every memo gets an ack-or-serviced reply
  within one session of the recipient's next tap-in. OPEN and STALE are computed
  mechanically by `tools/a2a_inbox.py`; skills call the tool rather than eyeball
  the ledger. Tap-in reads it (step 4c), handoff pays it (step 8a).
- **COO's inbox exists since 2026-08-16 04:19 CT** (`/root/projects/COO/docs/a2a/inbox.md`).
  Handoff DIGEST lines land there directly; the parked-in-DaysActivity fallback
  applies only if it is ever missing again.

## Attention Items

0. *(Done 2026-08-12 pre-open: method-notes section removed before the parse
   published — `st-st6h` closed, commit `028341a`.)*
1. **Risk cap unarmed** — `account_balance_usd: null`. Steve's ruling on the
   whole risk table is outstanding.
2. *(RESOLVED 2026-08-12: `bd` writes work again — verified by live
   create/close this morning. The v64→v65 block was repaired COO-side
   estate-wide (co-ir43p): backup, `migrate --force`, push, write-probe.
   Strader learned this only via the 08-12 transcript review — the repair was
   never announced to this repo, which is exactly the notification gap the
   zgent sync plan (st-aski) addresses. `st-p3lv` closed same morning.)*
2b. *(RESOLVED 2026-08-13: the **Zgent Sync Plan** was ratified. Decision 1 —
   COO's standing push authority **ratified with two gates** (read owner's canon
   first; announce in `docs/a2a/inbox.md` in the same commit), written into
   `.claude/rules/zgent-permissions.md`. Decision 3 — contract canonical at
   `/root/projects/COO/conventions/enterprise-contract.md`. Decision 4 — plan
   ratified and delegated to COO. Strader's half shipped the same day:
   st-zc38, st-g0or, st-75z0, st-pfrz, st-4ld0 all closed. Decision 2 —
   Strategy 3 rewrite (`st-mfpm`) was **withdrawn 2026-08-13** and superseded
   by the broader `st-ylqw` scope change: strip ALL strategy mechanics from
   `CLAUDE.md`, refocus on PA learning + chart presentation. Review package on
   Steve's desk (`desk-claudemd-refocus-review.html`); nothing lands until he
   rules.)*
2c. **Two P1 gaps carved out of today's security work.** **`st-fsf3`** — this
   repo has **no bash-guard hook at all** and `Bash(rm *)` / `Bash(mv *)` are
   auto-allowed; the only PreToolUse hooks are the Schwab gate and the `gc`
   stub. COO runs five gates through a shared library. Steve closed the parent
   `st-z3y5` against his in-flight backup-strategy review, which covers the
   backup half but not this enforcement half. **`st-9we4`** — the contract embed
   and tap-in drift check are BLOCKED on COO publishing the canonical file;
   path confirmed, file unwritten, and deliberately no placeholder.
2d. **Code Estate Plan correction** (`st-nujt`): the census claim of a
   "committed virtualenv (1,338 files)" in COO is **retracted** — zero `.venv`
   files are tracked in COO's history and the tree is already gitignored. The
   census counted working-tree rather than tracked files; corrected tracked
   counts are **Strader 781 / COO 1,449**. Every COO file count in that plan is
   unverified pending recount. Decision 3 of that plan is withdrawn.
   Related live state: steves-desk has only the hand-rebuilt Trading window —
   the other seven remain absent until the adopt fix (`st-b9pf`, COO's script).
   Schwab token healthy to **2026-08-24** (wall 2026-08-24T20:19:55Z, from
   `data/corpus/_schwab_token_health.json`; `st-6akd` closed). The date here is
   a snapshot of that probe — read the file, not this line.
3. *(This slot held `st-i68` for four sessions, reading "fires every weekday at
   08:15 until fixed" while that job was exiting rc=0 on 08-04 through 08-07.
   Closed 2026-08-10 with the gate bug `st-1qpz` that was its actual failure,
   both verified green end to end. Kept as a marker: an Attention Item nobody
   re-checks against observable state is worse than an empty list.)*
3. **`st-08p` blocked externally** — training steps 3–5 need Steve's NotebookLM
   upload and COO's deck import.
4. **RESOLVED 2026-08-19 (`st-tme`, `st-q5xu`, `st-2a8v`, `st-7kmt`,
   `st-gno7`)** — anchors carry the parsed Mancini kind; a resistance
   engagement emits the upside mirror `failed_breakout` / `level_reject`
   (bearish); pivots enter both sides; trigger/target are charted, not
   watched. Enriched-corpus re-derivation then removed the fire-index
   confidence damp and retired the day-type cut and the developing-b gate
   (`docs/measurement/{anchor-kind-mirror,fire-index-rederivation,hour-daytype-rederivation}-2026-08-19.md`).
   Standing read: the raw confirm stream has **no mechanical ±5 edge either
   side** (bullish 46%, below coin at p≈.01; bearish 49%) — the recognizer is
   an event detector whose descriptive layer is sound and whose directional
   vocabulary ("Buy signal", confidence 0.8) is unearned. Open with Steve:
   reword the surfaces to narrate events not forecasts, and run the
   matched-random null.
5. **`rcl` is sticky on the Mancini Pine indicator** — `lvState` 3 (RECLAIMED)
   has no outgoing transition, so a level that reclaims and then breaks again
   reads `rcl` for the rest of the session. Observed live on 7741, 2026-08-06.
   Must be fixed together with the asymmetric hysteresis (break needs a 2pt
   buffer, reclaim needs none) or the label oscillates. Not yet beaded.
6. **Capture window ruled 2026-08-05** — live capture is session-only
   (02:50–15:05 CT); the uncovered hours backfill free. The backfill leg is
   built-but-not-written (`st-wy6u`) and must never run while a feeder is
   tailing the day, so 24h coverage is not yet actually complete.
