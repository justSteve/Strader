# Strader — Current Status

**Role**: SPX Options Trading Intelligence (Consumer tier)
**Bead Prefix**: `st`
**Status**: zgent (in-process toward certification)
**Last refreshed**: 2026-09-05 [st-voc5, st-maav, st-rfjg, st-e12g, st-lrqq, st-2opj, st-6n7e; earlier 2026-08-30 [st-qcj3, st-ro04, st-byif, st-gnv5, st-ts3o; earlier 2026-08-29 st-wnuk (fix), st-g0jo; earlier 2026-08-28 st-9r51, st-kxnv (closed), st-psoj, st-5ndx; earlier 2026-08-26 st-kxnv, st-v3wj; earlier same day st-92m7, st-w87l, st-9cp0, st-zt9b, st-hd51, st-pc9q; earlier same day st-66ld, st-hmbr, st-bkvt, st-cua1; earlier 2026-08-25 st-mieu, st-2nyb, st-1eaw; earlier 2026-08-24 st-aq1n, st-wnuk, token re-auth; earlier 2026-08-21 st-9bsi, st-dioq, st-nujt; earlier 2026-08-20 st-ksgu, st-cc5k, st-1bv1, st-88ei; earlier 2026-08-19 st-tme, st-q5xu, st-7kmt, st-gno7; earlier same day st-vxbw, st-135m, st-kxnv; prior 2026-08-17 st-slj4, st-n0qm.5; 2026-08-13 st-aski, st-ad6p, st-g0or, st-75z0, st-pfrz, st-4ld0, st-xxo0, st-ylqw]

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
| GEXBot | **CANCELLED 2026-08-30 by Steve — QUANT access runs THROUGH 2026-09-06, State tier after** (`st-qcj3`; cancellation executed in the portal and easily reversed). What State keeps and loses is measured from the vendor's own tier tags: it keeps every classic and state endpoint including `majors`, and loses `/orderflow/orderflow`, `/hist`, the WebSocket and the two Quant discovery endpoints. **`/hist` is the real loss — it is Quant-only, so from 2026-09-07 no GEX day can ever be backfilled and a collector outage becomes a permanent hole.** The archive is complete to the window (79 days, 2026-05-07 → 2026-08-28) but the nightly harvest is plain cron Mon–Fri and CANNOT reach the last session of the entitlement, so a hand sweep on 09-05 or 09-06 is mandatory. Brief: `docs/reports/2026-08-30-gexbot-websocket-and-the-state-move.md`. Original QUANT text follows. **QUANT tier ($350/mo, one-month commitment) since 2026-08-05 PM** (State AM, upgraded same day; pause ran 07-03→08-05). Live **10-endpoint** collection in tmux `steves-desk:gex`: the full State package — {gamma,delta,vanna,charm} × {`_zero`,`_one`}, 87 strikes each — plus `classic/gex_zero/majors` and the **orderflow leg, which went live 2026-08-06 with 37 fields** (it was auto-skipping on entitlement before the upgrade; no code change was needed). 0DTE legs are requested first so a truncated cycle keeps what the fly window trades. Feed is **RTH-only** — collector DOWN outside 08:30–15:00 CT is normal. Now measured rather than asserted: on 2026-08-07 `spot_at_gamma_zero` sat frozen at one value from midnight, took its first new value at **08:30:02 CT**, updated on a ~76s cadence to **15:00:33 CT**, then went flat; Saturday 2026-08-08 never moved once across 1153 polls. The collector is gated to that window (`corpus_poll_gexbot.py`, restored 2026-08-10) and cron `*/2` restarts it inside the window via `scripts/cron/gexbot-supervisor-session.sh` [st-a6zm, st-p3lv]. **Consumer warning — `gexbot.jsonl` files dated 2026-08-09 or earlier are ~70% duplicate rows**: the collector polled around the clock, and a frozen feed returns the last RTH value unchanged, so an overnight row is not stale-but-plausible data, it is a verbatim repeat. 2026-08-07 holds 352 in-session rows against 783 repeats. Filter by timestamp — and never count, average, or weight these rows without deduplicating first. [co-hvxye] **A dedicated live 1 Hz orderflow leg runs beside the 60s collector since 2026-08-10** [st-ipn0]: `corpus_poll_gexbot_orderflow_1s.py` polls `/SPX/orderflow/orderflow` alone at ≥1.1s spacing (the vendor's stated per-metric ceiling), same 08:30–15:05 CT gate, writes flat rows to `data/corpus/<date>/gexbot_orderflow_1s.jsonl` (~1.3s native feed cadence, consecutive duplicates skipped), supervised by cron `*/2` via `scripts/cron/gexbot-orderflow-1s-supervisor.sh` in tmux window `gexbot-of1s`. This is the real-time spike-train read the 60s cycle cannot see; nightly `/hist` remains the archival 1s source. Program brief: `docs/a2a/2026-08-05-gexbot-quant-month-program.md`. Month-end sweep + downgrade decision ~Sep 1 — *ruled 2026-08-30, see above.* |
| Schwab API | `lib/schwab-py` on the `hobbled-readonly` fork — account/order/transaction methods physically removed. Only `broker_schwab/readers/{quote,chain}.py` are auto-allowed. **The `schwab-gate.sh` PreToolUse hook was DORMANT from May until 2026-08-13** — it read the bare `.command` key where the payload nests at `.tool_input.command`, so all five gates returned allow without inspecting anything. Fixed and installed with Steve's approval [st-ad6p]: reads the nested key, **fails closed** on any other shape, and gate 3 now blocks by *import reachability* (any `.py` importing `schwab` or `broker_schwab`, readers excepted) rather than by the old blanket ban on `scripts/` — 65 `.py` files live there and only 11 reach the API. Pinned by `tests/test_schwab_gate_hook.py`. **Correction carried into `CLAUDE.md` and the rule file the same day:** the permissions layer never gated interpreters — `python3`, `bash`, `curl`, `echo` are all auto-allowed; only `sh`, `source`, `touch` are absent. Through the dormant period the structural fork was the *only* live protection. |
| Entitlements | **`config/entitlements.yaml` is the single home** for subscription/tier/price state [st-g0or], probed by `scripts/entitlements_probe.py` (local files only, no vendor API). Splits **PROBED** (re-derived each run) from **DATED** (asserted, stamped, aged; `NEVER` renders as NEVER, not as a guess). Bundle docs and COO's conventions point at it — **never restate figures anywhere else**. Read by tap-in step 4d. Open items only Steve can close are listed by the probe every run: Databento's actual billed amount, **Schwab market-data rights (real-time vs delayed — unrecorded, so no agent should call reader quotes real-time)**, TradingView tier, LuxAlgo, and the Mancini newsletter. |
| Databento | **CME Standard live GLBX verified 2026-08-03.** ES trades + MBP-1 capture the session window 02:50–15:05 CT via `scripts/live-footprint-up.sh` (tmux `steves-desk:footprint`), now supervised. **GLBX historical is $0.00 on the Futures plan** (measured 2026-08-05, `--estimate-only`; OPRA control $6.07/2h), so an uncaptured GLBX session is **recoverable, not gone** — the old "quotes are NEVER backfilled" premise is false for GLBX and holds only for OPRA. **The MBP-1 T+1 backfill actually performs that recovery now** (st-xxo0 closed 2026-08-13, `a011873`): authorization derives from the entitlements registry (`databento_plan: active`) instead of the stale five-date July list, a still-missing day raises an `mbp1_gap` alert, and the probe carries an "ES MBP-1 depth landing" line. Collectors run under systemd timers as of 2026-08-13 (COO cutover, st-pgfe; capture 02:50, gexbot+orderflow-1s 08:30 CT). **Daily OPRA import HALTED 2026-08-07** (`st-7av4`, Steve's call): historical OPRA is an ad hoc fetch now via `corpus_backfill_databento.py --opra`. **Two hard facts measured 2026-08-30** (`st-byif`): historical OPRA has a **date wall at 2026-08-14T13:30Z** — the vendor refuses anything after it without a live licence, so ten of the fifteen uncovered August days are unreachable at any price; and everything *before* it is reachable with no plan at all, verified by a real `get_range` (200 OK, 420,720 records) because `metadata.get_cost` keeps answering after a billing lapse and can never settle it. Steve ruled the $199/mo plan out the same day. **A new corpus stream landed 2026-08-30**: `databento_opra_quotes.jsonl.gz` — cbbo-1s NBBO over 14:45–15:00 CT on the 34 strikes within ±40 pts, 274 days for $1.40 via `scripts/corpus_pull_opra_quotes.py`. It is a **separate stream on purpose** — `corpus_backfill_databento.py` appends unsorted to a day that already holds an OPRA file, so writing quotes into the trades stream would have corrupted 274 days of prints. It carries `window_ct` and `schema` in its manifest record. The datastream gate no longer requires the stream; the six measurement scripts that read `databento_opra.jsonl` must each fail loudly on a day without it. Historical corpus is tape-only — no GEX history before 2026-08-05. **Two further units run supervised and were missing from this table until 2026-08-21:** `strader-capture-evening.service` (evening leg of the ES tape) and `strader-orderflow-sentinel.service` (`st-n0qm.9`). **MBP-1 doubling guard closed 2026-08-20** (COO, `013832e`): `corpus_daily.py` tested stream *health* rather than *rows*, so reconnect notes on a healthy stream triggered a batch pull on top of a live tape. **2026-08-19 depth repaired 2026-08-21** (COO, `84e9b55`) — 5,440,418 duplicate batch rows dropped, 6,937,164 live kept, verified independently by Strader; `scripts/corpus_repair_doubled_day.py` is the reusable tool, dry-run by default.  **09-04/05 (co-8b60y, st-e12g):** the streamer now reconnects with backoff (0…300 s) for the whole window instead of giving up after six tries — the 09-03 outage produced 176 restarts and 6,466 notes per stream and zero bytes; the revised unit files (RestartSec 30 s stretching to 5 min) were installed 09-05 08:28 CT. 09-03 RTH tape backfilled by batch; its overnight/evening windows are not. |
| Mancini | **08:15 overnight refresh live since 2026-08-18** (`st-vxbw`): the pre-open job's good case (an in-session parse exists) now re-renders the plan doc with the level-interaction section brought from the letter's write-time to now (the parse may have run at 01:00 CT); manual: `PYTHONPATH=. .venv/bin/python -m runbook.mancini.refresh --open`. Human-facing timestamps render CT (Steve 2026-08-18). Pre-open cron wired and working, verified rc=0 end to end on 2026-08-10. The `st-i68` PATH bug and the `st-1qpz` gate bug are both fixed and closed. **Blob ingress depends on Azure subscription `38b503d4…`**: it sat in `Warned` (read-only — key listing refused, no new blobs 08-14→08-17 AM) until Steve fixed billing in the portal 2026-08-17 ~11:00 CT; the Sunday resend then landed and the 08-17 plan parsed clean (78 levels, 10 commentary). Check `az rest …/subscriptions/38b503d4… → state` first if `fetch_latest` ever fails with `ReadOnlyDisabledSubscription`. **All four stages of the richer extraction are built as of 2026-08-28** (`st-9r51`): the extractor now reads `/tmp/mancini-plan.txt`, the letter segmented to the forward plan (median 16% of it) — **not the raw letter**, because Mancini reprints his previous edition inside the recap and the first `Bull case` in the file is yesterday's on 201 of 353 letters. `data/level_state/current.json` carries `callout`, `callout_quotes`, `callout_attribution` (`quoted`/`mixed`/`gloss` — whether the words may be attributed to him), and typed `intent`/`conviction`/`setup` closed enums. A completeness floor grades richness and **warns without ever blocking**; commentary `tags` are a closed vocabulary (the open one had reached 83 values). Contract: `runbook/mancini/extraction-contract.md`. |
| Market internals | `scripts/mi_gauge.py`, captured on the 5-minute session cron. Single-sourced from Schwab — no cross-check exists (`st-jwtn`). |
| Live footprint | **Coach cursor since 2026-08-18** (`st-135m`): coach verbs `point {bar, price, text, pulse, hold_ms}` / `clear` draw a pointer on a cell through the bridge (`tools/coach.py point --bar I --price P --text …`); confirmed on Steve's page 08-18 13:03 CT. **Anchor reconciliation CLOSED and verified in production 2026-08-28** (`st-kxnv`): the feeder read Mancini anchors once at start and the unit restarts before the morning parse, so the recognizer ran anchorless — 0 anchors at process start on 08-21 through 08-26 except the hand-restarted 08-24, and on 08-26 the live page served 0 levels for 65 minutes of the open session. The fix is COO's restart branch in the 08:15 pre-open wrapper (`f2e6b73`). **First real production exercise was 2026-08-28** — the 03:30 reboot brought the feeder up with `anchors=0` and the parse landed 07:37, so the branch had a genuine reconciliation to do for the first time (08-27's apparent pass was a build-time restart leaving anchors already in place). Measured: run row `03:30:58 anchors=0` → `08:15:12 anchors=63`, feeder pid 118456 restarted 08:15:21, all 63 of the day's levels loaded. **Under systemd since 2026-08-16** (`strader-drill-bridge.service` + `strader-footprint-feed.service`, Watcher V2 Phase 2b `a170a5a`); the bridge serves the page itself and it is on the tailnet at `https://mydesk-1.tail89f676.ts.net/footprint/`; producer health dots on the HUD; cell cues (Phase 1) and the anchored aggressor volume profile (Phase 2) live on the page. Inference seam filed as **Emission And Packet Schema** (`st-n0qm.5`) + tape reader (`st-n0qm.6`) + hindsight grading (`st-n0qm.7`) — brief `docs/plans/2026-08-16-inference-layer-brief.md`. Original v1 text follows. v1: bridge `127.0.0.1:7788` + JSONL feeder → `/tmp/desk-live-footprint.html`. Same surface as the replay drills (one template, `.live` mode gate hides drill-only controls); bars proven byte-identical to replay. **Rendering confirmed live by Steve 2026-08-04.** Carries the per-bar emissions row + rollover panel. Intra-bar progressive rendering built and tested but **NOT deployed** (`st-e91l`) — needs a feeder+bridge restart, do it after a 15:05 stop. **Every closed bar now carries a `gex` stamp** (`st-8ywx`, live since 2026-08-07): flip, 0DTE and 1DTE brackets, net-GEX regime sign, distance to flip, which majors the bar's range covered, and the age of the poll. Resolved at-or-BEFORE the bar close — never lookahead — and applied *after* the recogniser judges the bar, so it is recorded alongside recognition and can never become an input to it. Absent feed degrades to no stamp, never to a broken bar. **Trapped-seller fuel line live since 2026-08-24** (`st-aq1n`): when price engages a Mancini level, the payload's emissions row carries a `Fuel` context event — level-state history (lazy retry until the 08:20 tracker runs), underwater aggression, lid rejections and absorbed dips on 5-min rolls, thin-above shelf scan — rate-limited to one per 10 bars, appended after the run log so parity is untouched; a measured display, not a graded signal (`knowledge/trapped-seller-fuel.md`). **Sunday-reopen crash fixed 2026-08-29** (`st-wnuk`, `106998e`): the developing bar with volume and no cells (all side-N reopen prints) now yields no column instead of raising `bar has no cells` — the 08-23 crash looped 11 times into systemd's start limit and left the surface dead ~11h. Live from the CT-midnight restart of 08-29/30, i.e. before the 08-30 17:00 reopen. The unit's restart backoff (`RestartSteps=5`, `RestartMaxDelaySec=5min`, burst 30) is in `deploy/systemd/` only until `bash deploy/install.sh` is run. |

## Crons (weekdays, CT)

| Time | Job |
|------|-----|
| 06:30 | Corpus daily — **ownership accepted by Strader 2026-08-30** (`st-gnv5`): the wrapper now lives at `scripts/cron/corpus-daily-wrapper.sh` (smoked rc=0), while the catalog entry stays in COO's `SCHEDULE.md` because that is where the dependency graph lives and two Strader jobs gate on this node. Awaiting COO's one-commit rename to `strader-corpus-daily`. Mon–Sat since `st-n42a`, so Friday's tape lands Saturday  **Gate revised 09-04 (COO a3a4956):** a day whose tape is present and covers the session passes at any reconnect count, warning above three — stale reconnect history no longer halts the 08:15 parse. |
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

`gc mail` is dead from Strader in both directions. The `gc-mail-stub.sh`
PreToolUse hook that used to block `gc` was **deregistered and deleted
2026-09-05** on Steve's word (st-voc5): the binary has been gone from
`/usr/local/bin/gc` since 08-21, so command-not-found now does the job. The
only PreToolUse hook on Bash is `schwab-gate.sh`.

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

0c. **Schwab refresh token expires 2026-09-05 12:32 CT** (`st-6z7d`; health probe critical + actionable at 08:25). Steve's re-auth via `scripts/refresh_schwab_token.py`; next session is Tue 09-08 (Labor Day Monday). A lapsed token is a live failure — report at once.

0d. **Prune tranche 1 (`st-rfjg`) is staged, not executed.** Gate 1 cleared 09-05 (Steve's five answers via Desk); gate 2 is COO's SERVICED on the three routed questions; then a `pre-prune` tag and a report to Desk. `st-2opj` stays open until it executes. The 09-03 outage aftermath (`st-e12g`): overnight/evening ES windows unfilled, DNS/network root cause unknown (also hit the 21:00 /hist harvest on 09-02 and 09-03).

0a. **Emitter watch is STOPPED and should stay stopped until its shape is
   decided.** *Attribution corrected 2026-08-26 (Steve: "i don't recall saying"
   it): the line "the monitor is not effective here in last 30 minutes… we need
   a restart" was Steve's `/handoff` argument at 14:28 CT on 08-25 — a session
   handoff note, not a ruling to stop the watch. Recording it as "Steve's
   call" was Strader's inference. The stop holds on Desk's ruling below, not
   on that note. Steve, 14:55 CT same day: the note explained why he was
   willing to reboot services THAT afternoon, "not a decision that stood from
   that point forward … i remain interested in learning more about late day
   singletons … currently that's a priority for my account." Late-day work is
   live, not stood down.* The two-tier cutover itself landed
   and verified (COO st-dgwj/st-85dv; scorer emits `EVENT` lines, watch tier is
   `tools/effort_event_watch.sh`, contract `docs/playbooks/emitter-two-tier.md`).
   The defect is **`st-mieu`**: SUPERLATIVE is a one-way ratchet and CLIMAX is
   the 99.5th percentile of the session so far, so both alert bars rise all day
   — measured silence 11:30-14:27 CT through a 13.50-pt range that touched both
   framing anchors. **Its shape is now RULED** (Desk, 2026-08-25/26): heartbeat
   first as the emission schema's first citizen, rolling-window percentile
   second and evidence-gated, thresholds retuned last from the counts. COO holds
   the bead. Spec correction that binds both agents — sensitivity must be
   **time-invariant across full RTH**; clock-time-weighted wake thresholds are
   off the table and "loudest when Steve trades" is retracted as spec. The watch
   stays stopped until the heartbeat lands. The scorer keeps running regardless;
   it is the data source.

0b. **Bridge memos now surface in-session** — `st-92m7`, P1, still open
   pending end-to-end proof over the new transport. The 2026-08-25 incident
   (five Desk memos unread up to 9h35m) was RE-DIAGNOSED 2026-08-26 and the
   original account here was wrong: nothing was mis-routed — the memos landed
   in `Strader/inbox`, the folder `bridge-check.sh` reads, and it counted them.
   They were invisible because Strader's only surfacing ran at tap-in, ONCE per
   session, so a memo arriving after start-up waited for the next session by
   construction. Built: `tools/bridge_inbox.py` — `--watch` (a Monitor command,
   silent until a memo lands), `--ledger` (writes the MEMO row), and a
   first-seen ledger at `/var/moo/state/bridge-inbox-seen.jsonl`, deliberately
   OUTSIDE the bridge so a re-clone cannot reset it. It distinguishes drained
   from broken from unreachable — an absent inbox is `[ALERT]` and exit 2, not
   "empty". **Transport is git as of 2026-08-26** (Ruling 12a, COO `6f23520`,
   `github.com/justSteve/bridge` private): Drive retired, inbound latency
   5 minutes instead of 4 hours, no model session in the loop. `BRIDGE_DIR` is
   unchanged. Arm the watch at tap-in; do not hand-check the folder.

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
   auto-allowed; the only PreToolUse hook is the Schwab gate (the `gc` stub was removed 09-05)
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
   Schwab token healthy to **2026-08-31** (re-authed by Steve 2026-08-24 AM;
   wall 2026-08-31T09:23:33Z, from `data/corpus/_schwab_token_health.json`;
   `st-6akd` closed). The date here is a snapshot of that probe — read the
   file, not this line.
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
