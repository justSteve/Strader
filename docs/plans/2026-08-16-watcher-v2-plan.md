---
title: Watcher/Sentinel V2 — Implementation Plan
date: 2026-08-16
author: COO (ultracode review, co-mq9o5)
status: draft-for-Steve
---

# Watcher/Sentinel V2 — Implementation Plan

Repo `/root/projects/Strader`. Units throughout: ES points and 0.25-pt ticks
(`market/signals/orderflow_config.py:16`), 2,000-lot volume bars (`:22`), CT clocks. Every code claim carries
`file:line`, verified against the working tree at 07:07 CT 2026-08-16 unless marked *reading* (from the six
structured readings) or *inferred*. Steve's trades are not a subject of this document.

The plan is the feature-first draft's spine (template-only first cue, profile in the same page, ~3 sessions to
both features visible), with the operator-first draft's "nothing dies silently" mechanics and `targets_for`
parity upgrade, and the product-first draft's seam-admission guard, emission schema and explicit not-built
list grafted in. Errors the judges found in the three drafts were re-checked against the code and corrected
here.

---

## 1. Where V1 stands (measured 2026-08-16, 06:04–07:07 CT)

**One thing changed since the readings: the sentinel is supervised now.** Commit `9b90529` (06:22 CT today,
co-03ojd.7) committed `deploy/systemd/strader-orderflow-sentinel.service` and the `DailyLog` change;
`systemctl is-enabled/is-active` → enabled, active since 06:20:05 CDT, `NRestarts=0`, log at
`/var/moo/logs/orderflow-sentinel/2026-08-16.log`. The unit is all-day, `WantedBy=multi-user.target`,
`Restart=on-failure`, no timer (unit lines 6–7, 22, 30–31). **Unsupervised Sentinel Gap** (st-2yuw) still
shows OPEN; its note says "Strader's call whether to close this on that". Everything else below is as the
readings measured it.

**Nothing else in the tier is running and nothing will start it Monday** except the collectors:
`strader-capture.timer` Mon 02:50 CT, `strader-gexbot.timer` and `strader-gexbot-orderflow-1s.timer` 08:30 CT
(`systemctl list-timers`, this session). `pgrep -af 'drill_bridge|live_footprint_feed'` → nothing. The
footprint stack is hand-launched into tmux `moocity/steves-desk:footprint` by `scripts/live-footprint-up.sh`
(`:23-27`) and died in the 08-15 08:5x OOM reset (footprint reading).

**Live footprint stack — the healthiest piece.** `scripts/live_footprint_feed.py` tails today's
`data/corpus/<CT day>/databento_glbx_es.jsonl`, dedups on `(sequence, ts_event)` with a 2 s reorder buffer
(feed:159-204, *reading*), drives the same `StackDriver` as replay (`market/orderflow/parity.py:98-146` — the
parity law), and POSTs `bar_payload` `{t0,t1,o,h,l,c,v,d,nv,dur,poc,cells,steps,ev[,gex]}` (feed:257-270) to
`scripts/drill_bridge.py` :7788, whose `add_bars` holds `_bars` (appended, indexed `i`), `meta`, `final`,
`developing` (replaced, not appended) and serves them on every `GET /bars?since=N` (bridge:98-152). The
template polls every 2 s (`scripts/orderflow_drill_template.html:1560-1603`, `setTimeout(pollBars, 2000)` at
:1603) and renders per-tick cells in `renderColumn` (:628-668); the only emission mark is the per-COLUMN
`.evmark` triangle (:689-703; CSS :163-171). Developing bar every 1 s (feed:456-467; template
`renderDeveloping` :1641-1650). Zero `@keyframes` in the template (measured). 379 tests collected under
`tests/market` (verifier, `--collect-only`); 46 VP tests across `test_anchored_profile.py` 13 /
`test_profile.py` 9 / `test_premarket_volume_profile.py` 24 (verifier); "48 stack tests" is a product-lens
reading not re-derived. Defects V2 inherits: no `try/finally` around the
drive loop, so `final` and the run-log `end` never land on a live day (feed:481-521; run logs 08-12/13/14
`end`=0, *reading*); the feeder raises `DayRolledOver` at midnight and nothing restarts it (feed:143-147);
`BRIDGE` literal in the template (:1517) vs `DRILL_BRIDGE_PORT` in the bridge (:48); `gex` context stamped per
bar and rendered nowhere (feed:487-491).

**Sentinel.** `scripts/orderflow_sentinel.py` tails `gexbot_orderflow_1s.jsonl` from EOF by byte offset (:329,
:335-359), two `LevelWatch` machines on `z_mlgamma`/`z_msgamma` (:38), six alert kinds appended to
`data/corpus/<day>/orderflow_alerts.jsonl` via `_emit` (:116-128; `ts_alert_utc` is wall clock :126). SPX
domain; no path to the page (0 refs in feed/bridge/template). Day rollover resets only `path, offset`
(:337-338), so `LevelWatch` state carries across days. **Measured against replay with fresh watches (Phase 0,
`--replay`):** 08-12's opening alerts (contested 13:30:42Z, relocation 13:31:01Z) are reproduced exactly by
fresh watches — genuine open-of-day ladder contests, not carry-over; 08-13's first alert is at 13:59:38Z; only
08-14's `approach` at 13:30:04Z — four seconds after the open, before the identity window could hold
MIN_ROWS — is the carry-over artifact. Zero `LevelWatch` tests. Also measured this session: the 1 Hz file's first rows per day
are not market rows — 08-14 row 1 has vendor `timestamp` 1786651199 = 08-13T19:59:59Z (prior close snapshot,
pulled 13:30:02Z) and row 2 is a zeroed reset (`z_mlgamma 7535`, `agg_dex 0`); 08-13 row 1 is the zeroed reset
(`z_mlgamma 7495`, `agg_dex 0`).

**Volume profile.** Four artifacts, none live: the 08:16 CT cron page (`crontab` line 47 → `scripts/cron/premarket-vp-wrapper.sh`,
which execs `scripts/premarket_volume_profile.py` at wrapper `:49` with no arguments, so the default
`--source ticks` (premarket `:368`) holds, prior-RTH anchor, aggressor split at 1 tick
via `market/orderflow/anchored_profile.py:122-164`, own row parser bypassing `replay.trade_from_row` and
dedup, *reading*), the single-tone `ProfileAccumulator` in `StackDriver` (`market/orderflow/profile.py:38-60`;
materialised only at `finish`), TPO, and the legacy `es_volume_profile.py`.

**Data.** Databento prints carry the exchange aggressor side verbatim (`market/ingest/databento.py:42-45`;
08-14: A 120,142 / B 114,678 / N 0, *reading*). Two HIGH defects: (i) the live writer sets `"sequence": None`
on every row (`scripts/corpus_stream_databento.py:393`) **although the `Trade` it is handed carries the venue
sequence** (`market/ingest/databento.py:54`; `client.trades()` :129) and the raw `.dbn` beside it has it —
measured this session and re-counted by the verifier: 234,820 `TradeMsg` in
`data/corpus/2026-08-14/databento_glbx_es.0.dbn` (equal to A 120,142 + B 114,678), 0 null/zero sequences,
first 29785284/29785286/29785290. `dedup_key` (`market/orderflow/replay.py:56-63`) therefore
degrades to `ts_event` alone and drops distinct prints sharing a nanosecond: 08-14 4,141 rows / 26,538
contracts / 3.42 % of volume, 1,818 at a different price (engine reading);
`tests/market/corpus/test_stream_databento.py:147` pins the null. (ii) 08-11 RTH is double-counted because
`corpus_daily.stream_healthy_in_manifest` (`scripts/corpus_daily.py:136-149`) treats any error as unhealthy
and appends a batch pull whose rows carry int sequences (data-sources reading). GexBot 1 Hz rows are 38 SPX
scalars with no price/size/side; the vendor spec has no `/volume` path (*reading*).

**Open beads → V2 disposition.** Bold names are registered ProperNames (`bd propername`) except where
marked ᵍ, which are gists derived from the title.

| Bead | State (bd, 07:07 CT) | Folds into |
|---|---|---|
| **Unsupervised Sentinel Gap** st-2yuw (P1) | open; unit installed+active today | Phase 0 closes it once the day-reset ships and a health file lets the existing checker report a live-but-frozen sentinel (its stall-reporting AC; "liveness by process not window" is met by the unit); its cron-restart-into-`steves-desk:sentinel` AC is superseded by the systemd unit (like-for-like with the collectors, st-pgfe) — say so on close |
| **Sentinel Hardening**ᵍ st-swkk (P2) | open | Phase 0 (day-reset + `LevelWatch` fixture test) and Phase 3 (contract test against `emission.v1.json`) |
| **Live Stack Day Rollover**ᵍ st-h510 (P1) | open; guards shipped 4f68026 | Phase 0 (`try/finally` so `final` lands) + Phase 2b (bridge+feed units as a `PartOf=` pair — the missing restart owner) |
| **Intra-Bar Rendering**ᵍ st-e91l (P2) | open; shipped f0b6c0c, 9 tests | Phase 0: close as done-not-closed |
| **Up.sh Capture Guard**ᵍ st-sgr1 (P2) | open; fix 9da1c5e | Phase 0: one clean start Monday → close |
| **Premarket Anchored VP**ᵍ st-6gs3 (P2, owner Steve; text says Schwab, code says ticks) | open | Phase 2 renders the same accumulator through the shared reader; the 08:16 page stays as the pre-open snapshot; **needs Steve**: keep or retire once the live panel exists |
| **Ladder Node Ranks** st-obdp (P2) | open | not V2-blocking; the Phase 3 `alerts` slot + basis are its landing pad; stays open, needs Steve's spend/priority call |
| **Sentinel Xray Loop** st-igim | in_progress, lease expired | close at Phase 0 as v1-shipped (08-10) with pointers to the V2 beads |
| st-vqa, st-flv4, st-olez, st-88ei | open | adjacent consumers of the schema / accumulator; untouched by V2; note on each |
| st-wy6u nightly GLBX backfill | open | fills the 15:05→02:50 CT hole later; Phase 2 banners the hole, does not depend on it |

---

## 2. Productization stance — seams to establish now

Fork doctrine holds: no rewrite for hygiene. **Seam-admission guard (product-first): a seam is admitted only
if Feature A, Feature B, or an open bead needs it now.** What is NOT changing: `market/orderflow/*` algorithms
and thresholds; `StackDriver`/`live_drive` (parity law); the 1748-line template as the renderer (it gains
code, no framework, no build step); the bridge as a stdlib server with replaced-not-appended slots; the
polling model; the `.evmark` column mark (cue is additive); the premarket 08:16 page; Databento as the sole
trade source; tmux as Steve's viewing surface (process hosting is a Steve question, §5).

| Seam | Status | Evidence | Minimum move (which phase) |
|---|---|---|---|
| (a) feed adapter + trade record | **partial** | `Trade(ts CT, symbol, instrument_id, price, size, side B/A/N, sequence)` IS the contract (`market/entities/trade.py:12-25`, *reading*); one shared parse+dedup (`replay.trade_from_row/dedup_key` :56-90) used by replay and feeder; premarket has a second parser (premarket:141-155, *reading*); `market/ingest/databento.py` LiveClient exists (:129) | Phase 2: `market/orderflow/tradesource.py` with `iter_trades(day, *, start_ts=None, follow=False)` wrapping `open_corpus_text`+`trade_from_row`+`dedup_key`+reorder (lift `ordered_trades` from feed:159-204); Feature B's pre-seed and the premarket page use it. **Not built:** Schwab/GexBot `TradeSource` adapters — Schwab supplies bars, GexBot supplies no prints; module docstring says so |
| (b) level source | **partial** | `Anchor(price, kind, label, mancini)` (`recognizer.py:69-74`); `anchors.mancini_levels_for` the only provider (paths hardcoded `anchors.py:21-23`, *reading*); `GexContext.for_bar` stamps SPX majors, no basis (`gex_context.py:191-212`); sentinel `LEVELS` tuple (`sentinel:38`) | Phase 4: `market/orderflow/levels.py` `LevelSource.levels_for(day) -> [Level(price, kind, label, tag, domain∈{ES,SPX})]`, `ManciniLevelSource` wrapping existing code, `GexBotMajorsSource` from `gex_context._parse`; `mancini_confluence` **stays on the wire** (renaming breaks the parity snapshot and template guards); Phase 3: sentinel `LEVELS` → `--levels` (default unchanged) |
| (c) emission schema (versioned JSON) | **missing** | no version key anywhere (only `server_version "DrillBridge/1.0"`, bridge:181); recognizer emissions are `serialize()` dicts `{type, timestamp, source, confidence, reason, <fields>} + {bar_i}` (`parity.py:80-93, 137-145`); sentinel alerts a different flat dict (`sentinel:116-128`) | Phase 2: `meta.schema = 1` (feed:411) and self-describing `profile.v:1`; Phase 3: `market/signals/schema/emission.v1.json` + contract test; every emission gains `sv:1`, `domain`, `targets:[{kind: cell or row or band, price (or lo,hi), role}]` computed in `StackDriver.on_bar` (`parity.py:133-145`) so drill, run log, replay and live carry identical dicts; sentinel `_emit` adds `sv, type:"LevelAlert", domain:"SPX", ts_row` (the row's `ts_pull_utc`) and `seq`. **Not built:** bus, websockets, broker — `GET /bars?since=N` is the subscription |
| (d) config surface | **partial** | thresholds in `orderflow_config.py`; roots hardcoded (`replay.py:34`, `paths.py:24`, `run_log.py:52`, *reading*); bridge address triplicated (feed:70, bridge:48, template:1517); COO desk paths in premarket (`:55-57`) | Phase 2: `SplitAccumulator` is path-free library code; `--vp-anchor` is a feeder flag; `DATA.meta.bridge` injected by `live_footprint_page.py` (`MARKER` :41), template literal becomes fallback. Phase 4: `STRADER_CORPUS_ROOT` env in `paths.py`, `replay.py` imports it; premarket `--out/--register`; `FootprintConfig` dataclass. **Not built:** config framework, YAML thresholds |
| (e) install / run / health | **partial** | collectors on systemd timers with `_<name>_health.json` files (*reading*); sentinel unit installed today (this session), no health file yet; footprint stack hand-run; `GET /health` (bridge:169-174) | Phase 0: sentinel `_sentinel_health.json` every 60 s. Phase 2b: `strader-drill-bridge.service` + `strader-footprint-feed.service` (`PartOf=` the bridge, `Restart=on-failure`; the feeder has no `--until-ct` — it exits on `DayRolledOver` or `--idle-stop`, argparse feed:338-367) + `deploy/install.sh`; feeder writes `_footprint_health.json` per push; page HUD dots. `[project.scripts]` deferred: thin wrapper modules under `strader/` are possible (pyproject packages the root infra, `pyproject.toml:25-38`) but nothing needs them yet |

---

## 3. Feature A — emitter cell cue on the FootPrint chart

**Which emitter.** The footprint stack's recognizers, riding each closed bar as `ev` (feed:266). Sentinel
alerts are SPX-domain rows with no basis to ES; they reach the page in Phase 3 (§5).

### 3.1 Data contract — what an emission carries, what the page can name today

Cell address = `(bar index i, tick tk = round(price / TICK))`; bars arrive with
`cells:[[price,bid_vol,ask_vol]]` and `poc` (feed:261-262), so a price names a cell.

| Type | Carries today | Cells nameable now | Phase 3 `targets` (engine-side) |
|---|---|---|---|
| ImbalanceStack | `prices[]` ascending, `ratios[]`, `direction` (`imbalance.py:64-71`) | **yes, exact** — every price is a traded cell of `bar_i` by construction (`find_imbalances` iterates `bar.cells`, :40) | `cell` × price role `stack`; diagonal opposite (`price−TICK` buy / `+TICK` sell, rule :44-49) role `stack_vs` |
| SweepPrint | `start_price, end_price, ticks_swept, total_size, direction` (`engine.py:184-191`) | range only; the swept set exists in-run as **tick indices** `r["prices"]` (`engine.py:169, 175` — `round(t.price / TICK)`, must be `× TICK` before it names cells); occasionally in `bar_i−1` (2/29, 1/16, 0/50, 0/16, *reading*) | `band` lo..hi role `sweep`, `cell` at `end_price` role `sweep_end`; serialize `prices` as floats; `bar_hint:"prev"` when `start_price ∉ [b.l,b.h]` |
| DeltaDivergence | `price_extreme, prior_extreme, kind` (`engine.py:237-244`) | one tick, pivot often in an EARLIER bar (9/75, 10/52, 34/60, 8/20 outside `bar_i`, *reading*) | `cell` role `pivot` with `bar_hint:"search_back"`; page walks back ≤ `ENGAGEMENT_WINDOW_BARS` for the last bar with `l ≤ price ≤ h`; `extreme_bar_i` engine field only if the search errs >5 % (Risk 3) |
| SetupRecognition | `anchor_price, anchor_kind, bias, state, beats[], fire_index, mancini_confluence` (`recognizer.py:316-327`); beats test whole-bar values (:198, 232-236, 252, 257, 263, *reading*) | anchor ROW only | `row` role `anchor`; derived `flush` band (anchor → `b.l`/`b.h` in break direction) and `confirm` close cell, **labelled derived** in tooltip and schema; optional `cells: tuple = ()` later |
| AbsorptionRead | `price, side, aggressive_vol, displacement_ticks, …` (`market/signals/orderflow.py:54-70`) | one tick — not on the live path (no MBP-1 driver, `parity.py:121-127`; live MBP-1 rows side null, *reading*) | `cell` role `absorb`; schema-ready, no live producer |
| Level (`final`) | `price, level_type` | not per-bar; renders in the emissions panel (template:1586) | `row` role `poc/hvn/lvn` on `final` |
| per-price single imbalances | never emitted (448/day on 08-14 vs 1 stack, *reading*) | — | Phase 3 optional `imb:[[price,dir,ratio]]` on `bar_payload` from `find_imbalances`, off-by-default toggle |

**Phase 1 contract: no engine or feeder change.** The page resolves targets from the fields above
(`resolveTargets(e, i)`); when Phase 3 lands `e.targets` the resolver prefers it and keeps derivation as the
fallback for old run logs and replay records. Same function both ways = one cue definition.

### 3.2 Render behaviour (template hooks, verified)

1. `renderColumn(b, i)` cell loop (:634-668): add `cell.dataset.tk = tk` at creation (:639) — nothing
   addresses a cell by price today except `style.top`.
2. State outside the DOM — `setCol` REPLACES the node (:785-792) and `repaintAll` rebuilds ≤48 columns on
   zoom/resize/cellmode (:706-710): `cueIndex: Map<barIdx, Array<{tk, role, type, srcBar}>>` and `cueSeen:
   Map<"i:type:tk", firstSeenMs>`.
3. `indexCues(i)` called at arrival — in `pollBars` after `bars.push(b)` (:1591) for LIVE and in
   `finishBar`/`step` (:763, :776) for replay — resolves `bars[i].ev` into `cueIndex` (possibly for earlier
   bars: pivot, sweep in `i−1`) and calls `setCol(j, …)` for any visible `j ≠ i` it touched. `renderColumn`
   reads `cueIndex.get(i)` after the loop and applies classes. **Developing column:** `renderDeveloping` calls
   `renderColumn(DEV, bars.length)` then strips `data-i` (:1647-1649); the cue lookup must tolerate `i ==
   bars.length` with `ev: []` and index nothing for it.
4. Flash gate: stamp `cueSeen` only on a fresh arrival — LIVE: `wasAtTip && fresh.length ≤ 3` (a `since=0`
   boot backfill of the day must not flash hundreds of bars; `wasAtTip` at :1590); replay: only while playing.
   Otherwise `seen=0` → persistent marker only.
5. Classes: `.cell.cue.cue-<role>` persistent; `.cue-new` while `now − seen < FLASH_MS` with `animation-delay:
   -(now−seen)ms` so a mid-flash repaint continues rather than restarts; `.churn` when `inChurn(b)`
   (:1017-1020) dims to `.4` like the evmark.
6. **Kill switch:** key `x` (and a HUD chip) toggles all cues off; per-role toggles in the help overlay; the
   single-imbalance hint (Phase 3) is off by default. A misfiring cue in a channel Steve is watching is
   fix-now-or-channel-off, so the off switch ships with the first cue.

CSS (next to `.col .evmark`, :163-171):
- `@keyframes cue-flash` 900 ms, `cubic-bezier(.2,.7,.2,1)`, once: `0% box-shadow: 0 0 0 0 var(--cue), inset 0
  0 0 2px var(--cue); filter: brightness(1.35)` → `100% box-shadow: 0 0 0 7px transparent; filter: none`.
  `.cue-new` removal is JS-timed (`setTimeout`), not `animationend`, so jsdom can observe it.
- `@media (prefers-reduced-motion: reduce) { .cell.cue-new { animation: none } }` — the persistent marker
  appears at once.
- Persistent marker = per-role edge rules composed from four custom properties (`--edge-l/-r/-t/-b`) into ONE
  `box-shadow`, **not `outline`** — `.cell.poc` owns the 2 px outline (:47) and both must show. `stack` left 3
  px, `sweep` right 3 px, `pivot` top 2 px, `anchor/flush/confirm` bottom 2 px. Two roles on one cell → two
  edges. Plus a 4 px top-right corner glyph per recognizer (`▮` stack, `◢` sweep, `◆` pivot) so shape carries
  the type when colour is muted; count badge when >3.
- Colour: cell backgrounds are `color-mix(--buy blue | --sell red)` (:654-656); marks in use are `--good`
  green (setup evmark), `--critical` red, `--ink-2`. New tokens off the blue↔red axis: `--cue: #c99700` light
  / `#f0c040` dark (amber, flash + stack/sweep); `--cue-pivot: #8a5cf6` violet; anchor/flush/confirm reuse
  `--good`. Tokens at :8-18. Contrast ≥ 3:1 against `--surface-1` and against the 75 % heat cell on both
  palettes, checked with the dataviz validator before ship (Risk 6). One-time HUD probe of `matchMedia` for
  `prefers-color-scheme` and `prefers-reduced-motion`, logged to the bridge, before the palette is frozen
  (Risk 7).
- Tooltip: append `"⚑ <emName> <role> (bar N)"` lines to `cell.title` (:667). Click on a cued cell → `emPinned
  = true; emPinnedIdx = i; openEmPanel(i)` (:1101), never `seekTo` in LIVE (the st-ug3f trap, :695-701).
- Latency: bar close + ≤ poll interval. **Poll goes 2000 → 1000 ms** — two literals today, `setTimeout(pollBars, 2000)`
  at `:1578` (day-mismatch retry) and `:1603`; hoist one `POLL_MS` constant and change both — to match the 1 s
  developing/profile push (Risk 8 measures cost).

### 3.3 Parity and tests

One `renderColumn`, one `indexCues`, one CSS block: the drill page (same template, DATA-embedded bars) paints
cues on `step()`, the LIVE page on poll.

- **Contract test** `tests/scripts/test_cell_cue_contract.py` (Phase 1): build one of each Signal from
  existing test builders, `parity.serialize`, assert the resolver's fields exist and lie on the tick grid;
  over the parity fixture run (`tests/market/orderflow/test_parity_harness.py`), every `ImbalanceStack.prices`
  ⊂ `bars[bar_i].cells` prices. Phase 3 replaces it with `tests/market/signals/test_emission_schema.py`
  validating every `serialize()` type and every sentinel kind against `emission.v1.json`, plus
  `targets[].price ∈ owning bar's cells` (or the hinted bar). Note `serialize` rounds only direct float/tuple
  members (`parity.py:88-91`); if `targets` becomes a dataclass field its prices are rounded explicitly in
  `targets_for`.
- **Page check** `tools/cell_cue_check.mjs` on the stubbed-bridge pattern of `tools/live_follow_check.mjs`
  (jsdom@24 out-of-tree per `tools/page_boot_check.mjs` header): boot the LIVE page; push one bar with an
  `ImbalanceStack` (`prices` = 3 ticks) as a fresh arrival → 3 `.cell[data-tk].cue-stack`, `.cue-new` present
  then gone after `FLASH_MS`; `repaintAll()` → `.cue-stack` persists, no `.cue-new`; push a 300-bar `since=0`
  backlog → 0 `.cue-new`; stub reduced-motion → 0 `.cue-new`; toggle `x` → 0 `.cue`; a developing push does
  not index. Run `bash tools/nodecheck.sh tools/cell_cue_check.mjs /tmp/desk-live-footprint.html`.
  `tools/drill_page_check.mjs` gains the same assertions on replay.

---

## 4. Feature B — anchored aggressor Volume Profile

### 4.1 Anchor — Steve already ruled

His words, two places: 2026-07-24 — *"can we use schwab's feed to chart the volume profile of /es anchored at
yesterday's cash open and including overnight action?"* (Strader session f75f8b63, CM
`strader/technical/2026-07-24_f75f8b63__e76172-77540.md`); and 2026-08-11, asked *"'Anchored on the prior
day's open' — which open?"*, he selected **"Prior RTH open, 08:30 CT"** (Strader session 56556178, CM
`strader/technical/2026-08-11_56556178__e98353-99586.md`). The code records the same choice
(`market/orderflow/anchored_profile.py:42-44`, paraphrase) and st-6gs3's description reads "Steve's calls:
prior cash open anchor". Today's ask says "prior day's opening trade" — the same words he used both times, so
the default stands; the flag below keeps the Globex reading one argument away. Two readings, for the record: **prior RTH open 08:30
CT** — modelled (`RTH_OPEN_CT` :45, `anchor_utc(session_day, open_ct)` :167) and covered by the tape (capture
02:50–15:05 CT; measured `ts_event` 07:50Z→20:05Z, *reading*); **prior Globex open 17:00 CT** — one argument
away, but the tick corpus has no prints 15:05→02:50 CT, so it degenerates to the 02:50 first print. **Decision
(bead `--type decision` "Profile Anchor Prior RTH"): feeder flag `--vp-anchor {prior-rth, prior-globex,
<ISO>}`, default `prior-rth`; `prior-globex` accepted and bannered "no prints 17:00→02:50 CT".** "Opening
trade" = first print with `ts ≥ anchor_utc` — the `CVD_RESET_CT` idiom (engine:132-140, *reading*). Prior
session day: **write** `prior_trading_day(d)` in `strader/market_calendar.py` next to `next_trading_day`
(:114) — no prior-session helper exists (`^def ` list: year_is_known, is_holiday, is_early_close,
is_trading_day, session_close_ct, next_trading_day, parse_hm, collect_window, window_state, describe);
`paths.most_recent_session_day` walks weekdays only and says holidays are not modelled (:34-51). The window is
~30.5 h (prior RTH + evening hole + 02:50 pre-market + today); the panel draws a hairline at both 08:30 opens.

### 4.2 Data — the same trade stream as the footprint

- **Split source:** Databento `side` on every print, written verbatim (`corpus_stream_databento.py:391`;
  `ingest/databento.py:42-45`) → `Trade.side` `B` buy aggressor / `A` sell aggressor / `N`. Cells use the same
  field (`bars.py:60-70`, `bid_vol` = sell-aggr, `ask_vol` = buy-aggr, *reading*).
- **`SplitAccumulator`** (~30 lines) in `anchored_profile.py`: `add(trade)` keyed by tick into
  `buys/sells/nones`, `snapshot() → SplitProfile`; `N` kept **separate** (`NONE_SIDE_POLICY="separate"`,
  `orderflow_config.py:31`) so the invariant *bucket[P] == Σ over closed bars of cells[P].bid + cells[P].ask*
  holds exactly. `build_split_profile` delegates with a `none_policy` argument **defaulting to the existing
  halving** (`:146-149`) so `tests/scripts/test_premarket_volume_profile.py:81` stays green; the latent
  `min(buys or {0:0})` bug (:156-157) is fixed by ranging over the union of keys. Unifying the estate on one N
  policy (and rewriting :81) is a Phase 4 decision bead ("Aggressor None Policy"); N=0 on ES today, so no live
  number changes either way.
- **Feed point:** the feeder's `_tee` sees every released trade before `build_bars` (feed:458-467).
  `vp.add(t)` there — parity by construction with the cells.
- **Pre-seed:** at start, `iter_trades(prior_day, start_ts=anchor)` (§2a; `read_corpus_day` is
  `.jsonl.gz`-aware via `open_corpus_text`, `replay.py:27, 103-111`) → `vp.add`. Today's file is then read
  from its top (`tail_rows`, feed:80-135, opens and reads the whole file; called at :435; day/path resolution
  is :376-383) so today's portion arrives through `_tee`. Snapshot `seeded_n`/`seeded_through`
  at the boundary so the page can draw the prior-day layer separately (§4.4). **Manifest guard:** the pre-seed
  banners "prior day carries a batch pull — profile from live rows only" and filters to `provenance.source ==
  "live"` when the prior day's `manifest.json` records live `cycles > 0` AND a `batch pull` note — the 08-11
  pattern.
- **Cadence:** materialise + push with the developing tick (`_tee`, ≤ 1/s), and on each closed-bar batch so a
  page without a developing bar still gets it. `post_bars` is synchronous with a 5 s timeout (feed:305-322,
  466); a stalled bridge already blocks the trade loop, and a 5–10 KB profile makes each blocked push costlier
  — the profile therefore rides on the **existing** developing push (no extra round trip) and the bridge+feed
  `PartOf=` pair (Phase 2b) is what bounds a stall.
- **Rollover / EOD:** the profile is a pure function of (anchor, tape). Feeder exits on `DayRolledOver`; a
  restart on D+1 anchors on D 08:30 CT automatically and rebuilds from disk — no carried state. EOD: last
  print at capture end, profile freezes. Ties to st-h510 only through the restart owner (Phase 2b).

### 4.3 Transport

Fourth replaced-not-appended slot mirroring `developing` (bridge:112-117, 138-139), returned on every `GET
/bars` (bridge:147-152); `post_bars` gains `profile=`. Payload `{v:1, anchor:"prior-rth", anchor_ts,
session_day, bucket:0.25, lo_tick, buy[], sell[], none[], seeded:{n, through_ts, buy[], sell[]}, n, first_ts,
last_ts, hole:[[from,to]], va:{poc,vah,val}, hvn[], lvn[]}` — arrays from `lo_tick`, ~400 buckets over 30 h at
0.25 (213 rows for one session on 08-14, *reading*) ≈ 5–10 KB, under the 1 MB body cap (bridge:194-197).
`value_area` (`anchored_profile.py:223`) and HVN/LVN thresholds (`orderflow_config.py:59-60`) via
`SplitProfile.as_volume_profile()`. `/health` adds `profile: {n, last_ts}`.

### 4.4 Presentation — same page, left panel, same route

`#cols` is `inset:0 56px 0 0` (template:40) with `#colstrip` right-aligned (:41); add `#vp` absolutely
positioned at the left, `VP_W` px (default 120; key `v` toggles; width in localStorage next to
`oflow-help-seen` :1454 — `LS_KEY` :537 holds the drill log, not settings), and set `#cols` left inset to
`VP_W` when shown. Rows `<div class="vprow" data-tk>` at `top = yFor(price) − cellH/2` (`yFor` :581), height
`cellH−1`, clipped by the same `updateView` window (:559) — a VP row and the cell at that price share a pixel
row, which is the "watch the parts move" payoff: the developing cell fills and the VP row grows on the next
poll. Two-tone widths: sell (`--sell`) from the left, buy (`--buy`) stacked right, scaled to the visible max;
**prior-day layer at reduced alpha with today's overlaid** (from `seeded.buy/sell` vs totals); POC row
outlined like `.cell.poc`; VA rows tinted `--mid`; HVN/LVN ticks; hairlines at both 08:30 opens; header
`anchor Thu 08:30 CT · n prints · hole 15:05→02:50` driven by the payload `hole`, not a string. Rebuild rows
when `profile.n` changes or `updateView()` returned true; diff-render if Risk 8 says so. Second page / second
route rejected: two windows break "one surface"; a second route duplicates since-count and day-guard logic.
The 08:16 premarket page becomes a static render of the same `SplitProfile` via `iter_trades` — **one
histogram, two renderers**.

### 4.5 GexBot — measured verdict: overlay, not source; no "two versions by source"

`gexbot_orderflow_1s.jsonl` rows are 38 flat SPX scalars (measured keys) with no price/size/side;
`gexbot.jsonl` per-strike arrays are gamma/greek ladders (`gex_context.py:113-129`, *reading*); the vendor
spec has one `/orderflow` path and zero `/volume` paths (*reading*). There is no per-price aggressor quantity
to profile. What GexBot can add is **level rows** on the ES axis (zero_gamma, majors, `z_mlgamma`/
`z_msgamma`, `zero_mcall/mput`) at `strike + basis` — the `row` target kind Feature A already uses, behind
seam (b) and a live basis (Phase 3); st-obdp's ladder feeds the same overlay. `ES_SPX` ticker variant is one
probe (Risk 5). **Any join to the 1 Hz file filters on the vendor `timestamp`, not `ts_pull_utc`** — row 1 of
a day can be the prior close snapshot and row 2 a zeroed reset (§1).

**Basis** (shared by sentinel rows and the overlay): nothing maintains SPX↔ES live; `gex_context.py:191-199`
compares SPX levels to ES bar `lo..hi` unconverted (`touch`) and `dflip` = `close − flip` in mixed units — a
latent error. Phase 3 adds `basis = median(bar.c − gex.spot over the last 10 bars with age_s < MAX_AGE_S)` to
`meta.gex` and per-bar `gex`, and fixes `touch`/`dflip`; product-first's synchronous-pairs measurement (Risk
4) validates it first.

### 4.6 Tests

- `tests/market/orderflow/test_split_accumulator.py`: over
  `tests/market/fixtures/es_ticks_golden_20260702.jsonl` feed the same trades to `build_bars` and to
  `SplitAccumulator`; ∀ price, Σ cells bid+ask over closed bars + partial-bar remainder == buy+sell; `none` ==
  Σ `nv`; `build_split_profile` == accumulator with `none_policy="halve"`; a `.gz` fixture pre-seeds.
- `tests/scripts/test_drill_bridge.py`: `profile` replaced-not-appended, served when `since ≥ total`, never
  retired by bars.
- `tools/vp_panel_check.mjs`: push `profile` + a bar; assert `#vp .vprow` count, POC class once, and
  `style.top` of `.vprow[data-tk=T]` == `.cell[data-tk=T]` in the newest column at three zoom levels; `v`
  toggles; hole banner text comes from the payload.

---

## 5. Sequencing — every phase visible on Steve's screen

Effort in sessions. New beads are Strader beads (`st-`), ProperNames given.

**Phase 0 — Monday Screen (½ session, before 08:30 CT Mon 08-17).** Cut line first. (1) `LevelWatch` day-reset
that also skips vendor-stale and zeroed rows: at the rollover branch (sentinel:337-338) rebuild `watches`; in
the row loop skip rows whose vendor `timestamp` is > N s older than `ts_pull_utc` or that carry the reset
signature (`agg_dex == 0` with `z_mlgamma == z_msgamma` on a 5-pt grid — thresholds measured from 08-13/14
rows 1–2). Two-day fixture test under `tests/scripts/test_orderflow_sentinel.py` (first `LevelWatch` tests).
(2) Sentinel `_sentinel_health.json` every 60 s (heartbeat 600 s → 60 s) — st-2yuw's AC. (3) Writer fix:
`corpus_stream_databento.py:393` `"sequence": trade.sequence`; update `test_stream_databento.py:147`;
`dedup_key` unchanged and exact from Monday. (4) Feeder `try/finally` so `final` + run-log `end` land
(feed:481-521). (5) `live-footprint-up.sh` clean start Monday → st-sgr1 closes. (6) Close st-e91l, st-igim (v1
shipped), st-2yuw. Double-launch: the sentinel is unit-only now (document: never hand-launch it — two writers
interleave into one `orderflow_alerts.jsonl`, `writer.py:33-37`); `up.sh` keeps its pgrep guard for capture.
*Visible:* footprint window back; sentinel's first-minute alerts clean; `final` levels appear at the close for
the first time on a live day. *Beads:* **Sentinel Day Reset** (AC: no alert in the first `MIN_ROWS` rows of a
new day references prior-day state; stale/zero rows skipped; fixture test) · **Sequence On Wire** (AC: live
rows carry int `sequence` equal to the `.dbn` record's; test updated; `read_corpus_day` drops only true
redeliveries) — closes st-2yuw, st-e91l, st-sgr1, st-igim.

**Phase 1 — Cell Cue Client (1 session).** §3.2–3.3, template + two test files, zero Python runtime change;
poll → 1000 ms; kill switch; HUD `matchMedia` probe. *Visible on the next live day:* a stack's three cells
flash amber and keep a left rule; a sweep's range a right rule; a pivot a violet top rule; hover names it;
click opens the panel; after 14:50 CT they dim; `x` clears them. *Bead:* **Cell Cue Client** (AC: on the LIVE
page an `ImbalanceStack` paints its `prices[]` cells with a ≤ 1 s flash then a persistent marker that survives
`repaintAll`; `since=0` backfill does not flash; reduced-motion suppresses motion; toggle works;
`cell_cue_check.mjs` + `test_cell_cue_contract.py` green; drill replay paints the same).

**Phase 2 — Live Anchored Profile (1½ sessions).** §4.1–4.6: `prior_trading_day`, `SplitAccumulator`,
`iter_trades`, feeder pre-seed + `--vp-anchor` + `_tee` add + `profile` push + manifest guard, bridge slot,
`#vp` panel, `meta.schema=1`, `DATA.meta.bridge`, three tests; premarket page through the shared reader (fixes
`.gz` skip and dedup bypass). *Visible:* two-tone profile left of the footprint anchored at yesterday's 08:30
CT, prior day faint and today accreting onto it each second; POC/VAH/VAL rows move; hole banner. *Beads:*
**Live Anchored Profile** (AC: anchored at prior RTH open from the same trade iterator as the cells; invariant
test green; slot on every `/bars`; rows aligned to `yFor`; page check green; hole and manifest banners;
`prior-globex` accepted and bannered) · **Trade Source Seam** (AC: feeder pre-seed and premarket VP both
iterate `iter_trades`; premarket parser deleted; a `.gz` prior day reads) · **Profile Anchor Prior RTH**
(`--type decision`, quoting anchored_profile.py:42-44). Annotate st-6gs3 with the live link; Steve decides its
fate.

**Phase 2b — Nothing Dies Silently (1 session; may run before Phase 2 if Monday shows a stall).**
`strader-drill-bridge.service` + `strader-footprint-feed.service` (`PartOf=`, `After=strader-capture.service`,
`Restart=on-failure`; DayRolledOver exit → restart) + `deploy/install.sh`; feeder `_footprint_health.json`;
bridge `GET /health/producers` reading the health files; page HUD dots tape/profile/sentinel with ages (amber
on gap, red with age when stalled); page reload-from-0 when bridge `total` < own `bars.length` (today
`pollBars` asks `since=bars.length` and gets nothing after a bridge restart until the feeder re-posts past N);
`up.sh` becomes viewer/launcher-of-last-resort with a unit-aware guard (`systemctl is-active` before
spawning). **Needs Steve:** the desk `footprint` window becomes a `journalctl -fu` viewer instead of the
process host — taste. *Visible:* three green dots at 08:20 with no hand launch; `kill -9` the feeder → amber →
green with the tape whole. *Beads:* **Live Stack Supervision** (AC: kill/restart test passes within 10 s; page
never shows a stale total; units come back after a Steve-run `wsl --shutdown`) · **Producer Health Dots** (AC:
dot red within 90 s of a killed producer) — closes st-h510.

**Phase 3 — Emission Schema + Sentinel Reaches the Page (2 sessions).** `emission.v1.json` + contract test;
`targets_for(sig, bar)` in `StackDriver.on_bar` (parity snapshot regenerated deliberately via
`scripts/regen_parity_snapshot.py`); resolver prefers `targets`; `SweepPrint.prices` (× TICK); optional `imb`
hint behind the toggle; **Live Basis** in `meta.gex` + `touch/dflip` fix; sentinel `_emit` adds
`sv/type/domain/ts_row/seq`, `--levels`; bridge `POST /alerts` + `GET /alerts?since=N`; sentinel posts
best-effort; page draws SPX row cues at `strike + basis` (UTC alert time → CT bar via `t0 ≤ ts < t1` with the
tz conversion — bars carry `-05:00` offsets, feed:258); desk `sentinel` window = `journalctl -o cat -fu
strader-orderflow-sentinel | orderflow_alert_fmt.py` (`-o cat` required: `alert_fmt.py:44-49` echoes non-JSON
lines raw). **Needs Steve:** phone push per kind is opt-in, off by default. *Visible:* an approach shows as a
labelled row on the footprint within one poll; sweep cells exact; pivots on the right bar. *Beads:* **Emission
Schema V1** (AC: every `serialize()` type and sentinel kind validates; `targets[].price ∈` owning bar) ·
**Live Basis Estimate** (AC: per-bar basis in payload; `touch` diff on 08-14 counted) · **Sentinel Page
Alerts** (AC: replayed 08-14 alerts paint rows within 1 ES pt of the Schwab-snapshot basis at
13:30Z/18:00Z/19:45Z; sentinel window shows sentences) — closes st-swkk.

**Phase 4 — Seams closed out (1 session; nothing new on screen, said honestly).** `LevelSource` + two
providers; `STRADER_CORPUS_ROOT`; premarket `--out/--register`; `FootprintConfig`; **Aggressor None Policy**
decision bead (unify on `separate`, rewrite test :81); `surface_liveness.sh` rows read health files;
historical null-sequence days (08-10..08-14): rehydrate from `.dbn` or content key, decided by Risk 1;
`corpus_daily` guard (skip batch append when live `cycles > 0`). *Beads:* **Level Source Seam**, **Footprint
Config Object**, **Null Sequence History** (AC: 08-14 rebuild keeps the 4,141 distinct rows; 08-11 RTH volume
≈ live figure; snapshot regen recorded).

Total: Phases 0–2 ≈ 3 sessions to both features on the live surface; +1 (2b) +2 (3) +1 (4) ≈ 7 sessions for
the whole of V2.

---

## 6. Risks and measured unknowns

| # | Unknown / risk | Resolves with |
|---|---|---|
| 1 | Historical null-sequence days: content key `(ts_event, price, size, side)` may merge genuinely identical simultaneous prints (2,339 content-identical drops on 08-14, *reading*). | Rehydrate 08-14 from `databento_glbx_es.0.dbn` (sequences present, measured) and diff against both keys; the count that survives sequence-dedup but not content-dedup is the content key's error. Forward days need neither (Phase 0 writer fix). |
| 2 | Live vs batch sequence identity — do the writer's sequences equal batch rows' for the same print? | On 08-11 (both present) join live `.dbn` `sequence` to batch rows by `(ts_event, price, size)`; report match rate before relying on it for the 08-11 de-double. |
| 3 | DeltaDivergence page-side back-search picks the wrong bar when `price_extreme` traded in several recent bars. | Over 08-07/12/13/14 run logs + rebuilt bars, fraction of pivots in >1 of the previous 40 bars' `[l,h]`; if >5 %, add `extreme_bar_i` (`engine.py:237-244`) in Phase 3 and regen. |
| 4 | Basis discrepancy: +16.5 (1 Hz `spot` vs ES print, 08-14 20:00Z) vs +20.2–20.9 (Schwab in-session, *reading*). | Join `gexbot_orderflow_1s` by vendor `timestamp` (not `ts_pull_utc`) to the last ES print at that second over 13:30–20:00Z; median/p95 and drift; if p95 > 1.5 pt, rows get a ± band; if the 1 Hz `spot` lags, take spot from `gexbot.jsonl` majors instead. |
| 5 | `ES_SPX` ticker variant might expose futures-scale positioning. | One `GET /tickers` (`docs/gexbot/gexbot.spec3-2.3.0.yaml:210`; the `ES_SPX` `ticker_variant` enum is `:798-807`) with the Quant key; keys only; if SPX levels rescaled, still an overlay. Quant month ends ~Sep 1 — probe before then. |
| 6 | Cue colour collides with heat at high alpha or in dark mode. | dataviz palette validator: `--cue`/`--cue-pivot` over `color-mix(--buy or --sell 75 %)` on both `--surface-1` values (:9, :15); ≥ 3:1. |
| 7 | Steve's browser theme and reduced-motion are unknown. | HUD `matchMedia('(prefers-color-scheme: dark)')` + `('(prefers-reduced-motion: reduce)')` logged once to the bridge (Phase 1); read it before freezing the palette. |
| 8 | Repaint cost: 48 columns + ~400 VP rows at a 1 s poll. | jsdom: 300 polls of a 08-14 fixture, `performance.now()` per `pollBars`; budget 16 ms; diff-render VP rows if over; revert poll to 2000 ms if still over. |
| 9 | Pre-seed time at feeder start (~228k trades), and a `.jsonl.gz` prior day once compaction resumes (08-10..14 are plain today, `ls`). | `time .venv/bin/python -c "from market.orderflow.replay import read_corpus_day; from datetime import date; read_corpus_day(date(2026,8,14))"`; if > 30 s, seed in a thread and banner "seeding"; `.gz` fixture in the accumulator test (`open_corpus_text`, `replay.py:27`). |
| 10 | Holiday: `prior_trading_day` correctness. | `python -c` around Labor Day 2026-09-07 for 09-08 → 09-04. |
| 11 | ~~Sentinel stale/zero-row skip thresholds may drop real rows.~~ **Resolved 2026-08-16 (Phase 0):** `--replay` over 08-10..14 skipped 0 / 0 / 0 / 1 (reset) / 2 (stale + reset) rows — exactly the three measured vendor rows, nothing else. | Was: the sentinel has no replay mode (argparse `:297-316` defines only `--band --rearm --move --poll --heartbeat --feed --alerts --log-dir`, and `--feed` starts at EOF, `:329`). Phase 0 builds a fixture runner (`tests/scripts/test_orderflow_sentinel.py`, or `--feed` against a copied file with the offset forced to 0) and counts skipped rows per day over 08-10..14; expect ≤ 2/day; alert counts unchanged after row 2. |
| 12 | jsdom availability for the three page checks. | `bash tools/nodecheck.sh tools/page_boot_check.mjs /tmp/desk-live-footprint.html --expect-empty`; if absent, the checks are a documented manual step until a JS runtime convention lands. |
| 13 | Feeder unit vs `up.sh` both launching a feeder. | `pgrep -fc live_footprint_feed` == 1 after running both; `up.sh` `systemctl is-active` guard. |
| 14 | systemd units on WSL after a Windows reboot. | Measured yes for `strader-capture.timer` (fired Fri 02:50); confirm `journalctl -u strader-footprint-feed --since today` on the first weekday after Phase 2b. |
| 15 | `corpus_daily` batch append recurring on any live reconnect error distorts the prior-day seed. | Manifest scan for `batch pull` notes weekly; Phase 2 manifest guard test with a synthetic manifest; Phase 4 `corpus_daily` guard. |

---

## Decisions that need Steve

1. **Footprint stack hosting** (Phase 2b): systemd units with the desk `footprint` window as a `journalctl`
   viewer, or keep the tmux hand-launch and accept no auto-restart. COO recommendation, unratified: units.
2. **Premarket 08:16 page** (st-6gs3): keep as the pre-open snapshot once the live panel exists, or retire it.
3. **Sentinel phone push** (Phase 3): stays off; opt-in per kind if he wants it.
4. **st-obdp priority / GexBot Quant spend past ~Sep 1** gates the overlay work.

Everything else — anchor default (his 08-11 ruling), GexBot overlay-not-source, N-side policy, poll interval,
colours, sequencing — is decided above and marked as decision beads where it outlives the work.

---

## Appendix — Provenance

**Six structured readings (2026-08-16, 06:04–06:19 CT):** sentinel (`scripts/orderflow_sentinel.py`, alerts,
unit), footprint stack (feeder, bridge, template, page, up.sh, tools), engine (`market/orderflow/*` emission
field sets, per-day attribution counts), volume profile (`anchored_profile.py`, `premarket_volume_profile.py`,
`profile.py`, tests), data sources (Databento live/batch rows, dedup, GexBot 1 Hz/60 s files, spec, Schwab),
product lens (tests, config, packaging, install).

**Three angle drafts:** product-first (seams, schema, not-built list), feature-first (template-only cue,
`none_policy`, ½-session Monday cut), operator-first (seven-moment chair narrative, `targets_for` in
`StackDriver`, health dots, basis seam). Two judges' scores, error lists and "missing everywhere" items were
re-checked against the working tree in this session; where the tree had moved since the readings (sentinel
unit committed and active, `9b90529`), the plan follows the tree.

**Independent verification (no prior context):** 52 code/data claims extracted and checked against the tree;
40+ held, 11 were refuted or mis-cited and are corrected in this text (the `.dbn` record count, a second
poll-interval literal, a non-existent sentinel `--replay` flag, st-2yuw's actual AC, the 08-13 first-minute
alert, the premarket cron wrapper, `/tickers` line, five unregistered ProperNames, an incomplete
`AbsorptionRead` field list, and minor line drift). Left as *reading* and not re-derived: the 3.42 % dedup-loss
figures, per-recognizer attribution counts, the basis figures, and the MBP-1 side-null claim — each has a
resolving command in §6. COO reviewed the whole document before commit (co-mq9o5).
