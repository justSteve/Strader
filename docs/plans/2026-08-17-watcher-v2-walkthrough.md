# Watcher V2 — Code Walkthrough

*Prepared 2026-08-17 16:45 CT · repo `Strader` @ `46aaa85` · epic **Watcher V2 Epic** (st-n0qm) · plan `docs/plans/2026-08-16-watcher-v2-plan.md`*

Seven commits by COO on Sunday 08-16 (≈4,000 lines: 3,300 added, 190 removed, 41 files). Every phase is on the LIVE page today; today (Mon 08-17) was the first live session under it. Read this top-down: what it is → what happened today → the walk, file by file → tests → what to look at.

## 1. What V2 is, in one screen

| Phase | Bead | Commit | On screen |
|---|---|---|---|
| 0 Monday Screen | st-n0qm.1 | `817c390` | sentinel survives midnight (day-reset), skips vendor's stale first rows, alerts carry `ts_row`, health file; live tape rows carry venue `sequence` (dedup was eating 3.4 % of 08-14 volume); feeder finalises on kill |
| 1 Cell Cue Client | st-n0qm.2 | `a7779b9` | emission cells flash ~900 ms then keep an edge rule + glyph; `x` toggles; template-only |
| 2b Nothing Dies Silently | st-n0qm.3 | `a170a5a` | bridge + feeder are systemd units; bridge serves the page at `/`; tailnet `/footprint/`; HUD producer dots |
| 2 Live Anchored Profile | st-n0qm.4 | `58d84d4` | `#vp` panel left of the cells, anchored at prior RTH open, sell red / buy blue, prior day faint, today solid, POC/VA/HVN/LVN; `v` toggles |
| 3 (COO half) Basis + Sentinel rows | st-n0qm.8/.9 | `f6a205f` `4a6ae59` | every closed bar carries `bs` (SPX→ES basis); sentinel alerts POST to the bridge and draw as rows at strike+basis; HUD strip; `s` toggles; bridge resets on a new day; alerts seeded from file at start |
| 4 Seams batch one | st-n0qm.10/.11 | `0367fcb` | nothing on screen: corpus_daily never appends batch onto a live tape; aggressor None policy = separate; `STRADER_CORPUS_ROOT`; liveness reads health files |

Still open on the epic (Strader-owned): **Emission And Packet Schema** (st-n0qm.5), **Tier-1 tape reader** (.6), **Hindsight grading** (.7). Phase 4 leftovers named on the epic: LevelSource + providers, FootprintConfig, Null Sequence History, premarket `--out/--register`.

## 2. Today's live proof (Mon 08-17, first session under V2) — measured 16:27 CT

| Piece | Evidence |
|---|---|
| Units | `strader-drill-bridge` up since Sun 14:21 (0 restarts) · `strader-footprint-feed` restarted 00:00:10 CT on `DayRolledOver` (by design, restart counter 1) · `strader-orderflow-sentinel` up since Sun 14:07, `rollovers: 1` · capture ran 02:50→15:05, 1 Hz GEX leg 08:30→15:00 |
| Bars | bridge holds **420** closed bars, `meta.source=live`, `bar_n=2000`, `tick=0.25`; feeder `sent: 420`, state `following` |
| Basis | last bar `bs = {pts: 21.83, n: 10, age_s: 243.8}`; `gex.dflip = −41.83` (spot 7746.21, flip 7787.5, basis-converted) |
| Sentinel | `_sentinel_health.json`: `rows_today 12,676`, `skipped {reset: 1}`, **53 alerts**, last 14:58:57 CT; bridge `/alerts` holds 53 (ids 1..53, `received_utc` stamped) |
| Profile | `/bars` carries a `profile` slot: pre-seeded 00:00:12 CT from **08-14** (`prior_trading_day(Mon)`), 205,789 prints, `session_day`/`anchor_ts` present |
| Page | `GET /` 200 · 131,688 B locally and via `https://mydesk-1.tail89f676.ts.net/footprint/` (0.03 s) |
| Journals | 0 lines matching error/traceback/warn across the three units since 02:00 CT — except the designed midnight `DayRolledOver` exit (full traceback, `status=1/FAILURE`, then the scheduled restart) |

**Two things the live day surfaced** (both filed/known, neither is a page-code bug):

1. **Anchorless Midnight Feeder** (st-kxnv, new, child of the epic). The feeder reads Mancini levels **once** at start (`scripts/live_footprint_feed.py:439-448` → `mancini_levels_for(day)`); under the unit it starts at 00:00:10 CT on rollover; the day's parse lands 04:22–08:04 CT (today 12:11 after the Azure outage). Result: `anchors=2 (0 mancini)`, `meta.mancini == []` all day, every day. Old hand-launched path started after the parse, so this is a Phase 2b regression. Smallest fix: `/mancini-parse` publish ends with `systemctl restart strader-footprint-feed` (feed alone; bridge state stays). Product fix: feeder re-polls the parse until first RTH bar.
2. **Health assessors frozen since 08-13** (COO's co-03ojd.7, in progress). `_capture_health.json` / `_gexbot_of1s_health.json` last written 08-13 18:10 / 16:44 — the `*/2` cron supervisors that wrote them went with the systemd cutover. Effect on V2: the `tape` and `gex_1s` HUD dots and `/health/producers` read a 4-day-old verdict (`age_s 339,411`, status `idle`); the `sentinel` and `feed` dots are live (V2 writes those itself). Feeds themselves ran fine today.

## 3. The walk — suggested order (≈ 60–90 min)

1. **Data path end to end** (§4) — five minutes on the diagram, then follow one trade and one 1 Hz row through the code.
2. **Feeder** `scripts/live_footprint_feed.py` — Phase 0 `drive_and_publish` / try-finally / SIGTERM, Phase 2 `--vp-anchor` pre-seed + tee, Phase 2b health file, Phase 3 `bs` stamp.
3. **Sentinel** `scripts/orderflow_sentinel.py` — day boundary, skip rules, `ts_row`, health file, `--replay`, `--bridge` POST.
4. **Basis** `market/orderflow/basis.py` + `gex_context.for_bar(basis=)` — the unit conversion that fixes the ~20-pt mixed-unit compare.
5. **Bridge** `scripts/drill_bridge.py` — endpoints, slots, day reset, alerts seed, `/health/producers`.
6. **Page** `scripts/orderflow_drill_template.html` — boot/poll, cell cues (`resolveTargets`), `#vp` panel, sentinel rows + HUD strip, producer dots.
7. **Profile library** `market/orderflow/anchored_profile.py` + `tradesource.py` + `prior_trading_day`.
8. **Deploy** `deploy/systemd/*.service`, `deploy/install.sh`, `scripts/live-footprint-up.sh`.
9. **Seams** `corpus_daily.py` guard, `paths.py`, `surface_liveness.sh`.
10. **Tests** — inventory + one run.

## 4. How the pieces connect

- **ES tape:** Databento live → `scripts/corpus_stream_databento.py` `StreamWorker._row` (:374) → `data/corpus/<day>/databento_glbx_es.jsonl`. Unit `strader-capture.service` (`--streams es,es-mbp1 --until-ct 15:05 --now`, timer 02:50 CT).
- **1 Hz vendor spot:** `scripts/corpus_poll_gexbot_orderflow_1s.py` (unit `strader-gexbot-orderflow-1s.service`, 08:30–15:05 CT) → `gexbot_orderflow_1s.jsonl` (`paths.gexbot_orderflow_1s_path` :78). Read by BOTH the sentinel (`_iter_complete_lines`) and the feeder's `BasisEstimator.refresh`.
- **60 s GEX poll:** `corpus_poll_gexbot.py` → `gexbot.jsonl` → `GexContext.refresh/poll_at`.
- **Feeder path:** `main` → `tail_rows` → `ordered_trades` (dedup_key/trade_from_row) → `_tee` (also `SplitAccumulator.add`, developing tick) → `build_bars` → `take_bar_trades` → `parity.live_drive` → `drive_and_publish` → `BasisEstimator.sample` → `GexContext.for_bar(basis=)` → `bar_payload` → `_publish` → `post_bars` → **POST 127.0.0.1:7788/bars** (`{bars, meta, final, developing, profile}`; bridge `do_POST` drill_bridge.py:443). Health: `write_feed_health` → `<day>/_footprint_health.json` → bridge **GET /health/producers** (`producers_health` :311, PRODUCERS "feed" :82, fresh_s 90).
- **Sentinel path:** main loop → `_iter_complete_lines` → `SentinelState.feed_row` → `row_verdict` → `LevelWatch.update` → `_emit` → `append_jsonl(<day>/orderflow_alerts.jsonl)` → `_post_alert` → **POST /alerts** (bridge `STATE.add_alert` :220, adds `id`,`received_utc`; page polls GET /alerts?since). Health: `write_health` → `<day>/_sentinel_health.json` → GET /health/producers ("sentinel" :81).
- **Page** draws a sentinel row at `strike + bs.pts` from the firing bar (§6).

```
Databento live ──► corpus_stream_databento ──► <day>/databento_glbx_es.jsonl ─┐
                                                                             ▼
GexBot 60 s ──► corpus_poll_gexbot ──► gexbot.jsonl ──► GexContext ──► live_footprint_feed ──POST /bars──┐
GexBot 1 Hz ──► corpus_poll_gexbot_orderflow_1s ──► gexbot_orderflow_1s.jsonl ─┬─► BasisEstimator ─┘     │
                                                                             └─► orderflow_sentinel ──POST /alerts──┤
                                                                                                                    ▼
                                                                    drill_bridge :7788  ◄──GET / /bars /alerts /health/producers── page (browser / tailnet)
```

## 5. Python pipeline — feeder, sentinel, basis, gex_context

Tests over these five files: **71 passed in 0.99 s** (feeder 20, sentinel 17, basis 10, gex_context 12, stream_databento 12).

### 5.1 `scripts/live_footprint_feed.py` — feeder

Purpose: tail today's ES corpus, build volume bars through the same engine as replay, stamp `gex`/`bs`, POST to the bridge. Invoked by `strader-footprint-feed.service` (`ExecStart … live_footprint_feed.py`, no flags; `PartOf=strader-drill-bridge.service`, `Restart=on-failure`, `KillSignal=SIGTERM`, ExecStartPre renders the page). Flags (:378-417): `--date --bridge --bar-n --reorder-lag --catch-up-only --idle-stop --mancini-levels --developing-interval --vp-anchor {prior-rth|prior-globex|ISO|off} --no-gex --no-run-log --dry-run -v`.

| Symbol | Line | What / invariant |
|---|---|---|
| `StopFeed` | :86 | Raised by SIGTERM handler so `drive_and_publish`'s finally runs; process exits 0. |
| `DayRolledOver` | :99 | CT date passed the pinned day; finalise then re-raise → non-zero → unit restart. |
| `tail_rows` | :103 | Follow JSONL; `.gz` ⇒ follow=False; partial trailing line held; raises `DayRolledOver` while *waiting for a missing file* (:147) and while *idle* (:175) when `pinned_day != central_date()`. |
| `ordered_trades` | :191 | Dedup on `dedup_key` (sequence, ts_event), release trades older than `reorder_lag_s` behind newest, sorted (ts, seq). |
| `take_bar_trades` | :248 | Reclaims a bar's slice off the tee by cumulative volume. |
| `bar_payload` | :264 | Wire dict `t0,t1,o,h,l,c,v,d,nv,dur,poc,cells,steps,ev` + optional `gex`, + `bs` **only when `bs.pts is not None`** (:308). |
| `developing_payload` | :313 | Partial bar, display-only, no steps/ev. |
| `post_bars` | :345 | POST `/bars`; swallows URLError/OSError/ValueError → warn + None (:356). |
| `main` | :375 | Builds StackDriver, `GexContext(gexbot_path)` and `BasisEstimator(gexbot_orderflow_1s_path)` (both off under `--no-gex`, :457-460); Mancini anchors read once (:439-448); vp pre-seed from prior day (:490-508); health dict + `_beat` (:539-548) with keys `day,pid,sent,last_bar_t1,developing_t,final,written_utc,state`; 30 s daemon `_pulse` thread (:557); `_tee` (:564); `_publish` (:587); installs SIGTERM handler then calls `drive_and_publish` (:598-601). |
| `resolve_vp_anchor` | :605 | `prior-rth` → prior trading day RTH_OPEN_CT; `prior-globex` → 17:00 CT; else ISO (naive = CT). |
| `write_feed_health` | :623 | tmp + `os.replace`; OSError → warn only. |
| `_install_stop_handler` | :638 | SIGTERM → `StopFeed`; ValueError (non-main thread) ignored. |
| `drive_and_publish` | :650 | Core loop; per bar: `runlog.on_bar` → `basis.refresh(); bs = basis.sample(bar)` → `gex.refresh(); gex.for_bar(bar, basis=bs["pts"])` (:682-689) → batch; push when `len ≥ push_every_n (25)` or `≥ push_every_s (1.0)`. `except (StopFeed, KeyboardInterrupt)` swallow; `DayRolledOver`/other re-raise; **finally**: `driver.finish` (guarded), `runlog.on_final` + `close`, publish leftover batch + `final`. Returns `{sent,n_ev,final,stopped_by}`. |

Control flow: `main` → build stack/contexts/health → `drive_and_publish(live_drive(_closed_bars()))` → per bar stamp bs→gex→payload → coalesced `_publish`→`post_bars` (+`_beat`) → finally finish/runlog/final push → exit 0 (or re-raise on rollover/error).

Tests (`tests/scripts/test_live_footprint_feed.py`): `test_drive_and_publish_finalises_on_a_clean_end` :377 (meta on first push, final on last); `..._finalises_when_the_stream_is_killed_mid_day` :391 (StopFeed after 3 bars still yields Level in final, `bar_i is None`); `..._finalises_then_reraises_day_rollover` :414; `..._survives_a_finish_error` :434; `test_waiting_for_a_missing_file_also_raises_when_the_day_rolls` :447; `test_closed_bars_carry_the_basis_and_gex_converts_through_it` :462 (bs.pts == median of last-10 close−spot; `gex.basis == bs.pts`, `dflip` converted, `flip` stays SPX); `test_bar_payload_omits_bs_when_unknown` :516; older pins: `test_idle_tail_raises_when_the_ct_date_rolls_past_the_pinned_day` :173, `test_reorder_buffer_absorbs_out_of_order_delivery` :110, `test_redelivered_rows_are_deduped` :142.

Reviewer's eye:
- `_beat` is called from the main thread (:577, :594) **and** the 30 s daemon thread (:560); both mutate `feed_health` and write the same `.json.tmp` (:631) — no lock. Unverified whether a torn/`FileNotFoundError` race has been seen; `write_feed_health` catches OSError so worst case is a dropped beat.
- Health only reflects pushes; `_pulse` sets `state` from `sent`/`developing_t` (:560) — under `--catch-up-only` there is no developing tick, so `state` is "waiting" until the first closed batch.
- `runlog.on_final` raising (:721) propagates after `close()` and **skips** the final `publish` (:724-725) — the guarded path covers `driver.finish` only.
- `bs.age_s` is wall-clock relative (basis.py:181) — on `--catch-up-only` replays it reads as hours; `gex.age_s` is bar-relative. Two "age" semantics on one payload.
- `post_bars` failures are warn-only (:356-360); vp pre-seed POST at :506 fires before any tape row and before the SIGTERM handler is installed (:598).
- `meta["gex"]` (:465) is `gexbot_path(day).exists()` at start-up only. Same one-shot pattern as the Mancini anchors (st-kxnv, §2).
- SIGINT is not mapped to StopFeed but `KeyboardInterrupt` is caught in `drive_and_publish` (:701) — same outcome.

### 5.2 `scripts/orderflow_sentinel.py` — sentinel

Purpose: deterministic level-proximity watcher on the 1 Hz GexBot file; alerts to JSONL + stdout + bridge. Invoked by `strader-orderflow-sentinel.service` (`… orderflow_sentinel.py --log-dir /var/moo/logs/orderflow-sentinel`, `Restart=on-failure`, **`KillSignal=SIGINT`**). Flags (:516-549): `--band 2.5 --rearm 5.0 --move 5.0 --poll 2.0 --heartbeat 600 --feed --alerts --health --log-dir --bridge ($STRADER_BRIDGE|http://127.0.0.1:7788|off) --replay FEED_FILE`.

Constants: `LEVELS` z_mlgamma/z_msgamma :58; `REARM_ROWS=15` :60; `APPROACH_COOLDOWN_S=120` :61; `STALE_ROW_S=120` :62; `HEALTH_INTERVAL_S=60` :64; `LevelWatch.WINDOW=90, MIN_ROWS=20, DOMINANT=0.85, CONTENDER=0.25, ZONE_REOPEN_S=1800, ZONE_EXIT_ROWS=450` :250-255; `_BRIDGE_TIMEOUT_S=1.5` :173.

| Symbol | Line | What / invariant |
|---|---|---|
| `_feed_path/_alerts_path/_health_path` | :67/:71/:75 | `CORPUS_ROOT/<central_date()>/…` recomputed per call (that is the rollover trigger). |
| `_pull_epoch` | :79 | ISO Z → epoch; None if unparseable. |
| `row_verdict` | :89 | Skip rules in order: `"anomaly"` key → `anomaly`; `z_mlgamma == z_msgamma and agg_dex == 0` → `reset`; numeric `timestamp` with `pull − ts > 120` → `stale`; else None. |
| `DailyLog` | :112 | stdout always + `<dir>/<CT date>.log`, rolls daily; open failure → stdout only. |
| `_post_alert` | :177 | POST `/alerts` with 1.5 s timeout; never raises; logs failure #1 and every 50th; module globals `_BRIDGE`, `_bridge_failures`. |
| `_strike` | :203 | round to 5-pt grid. |
| `_emit` | :209 | Adds `strike` (from value/new/settled), `strike_low/high`, contender strikes, `ts_alert_utc`, `ts_row = _STATE.last_row_pull_utc` (:220-224); `append_jsonl` (:225) **before** log and POST (:229). Alert record fields: `kind` ∈ approach/relocation/contested/resolved/zone/zone_dissolved, `level, name, spot`, plus per-kind (`value,distance_pts,side` / `old,new` / `contenders` / `low,high,note` / `zone,settled`). |
| `LevelWatch` | :232 | Rolling-window cluster identity (`_clusters` :274, `_update_identity` :287); `update` :360 — approach fires when armed ∧ `dist ≤ band` ∧ approaching ∧ cooldown elapsed; re-arm after `REARM_ROWS` rows at `≥ rearm`. |
| `SentinelState` | :396 | `rollover(day)` :419 rebuilds watches, resets `rows_today/skipped/alerts_today`, bumps `rollovers`; `feed_row` :431 counts skips, updates `rows`, `last_row_pull_utc`, drives each watch; `health` :452 dict keys `written_utc,pid,day,feed,feed_offset,rows,rows_today,skipped,last_row_pull_utc,alerts_today,last_alert_utc,rollovers,watches{value,armed,contested,zone}`. |
| `write_health` | :473 | tmp + `os.replace`; OSError logged. |
| `_iter_complete_lines` | :485 | Byte-offset tail; stops at a line without `\n`; bad JSON consumed. |
| `replay_file` | :502 | From byte 0 through fresh state; returns health dict. |
| `main` | :514 | replay branch (:564-572, alerts default `orderflow_alerts.replay.jsonl`, bridge off); live: start at EOF (:578), loop (:584): path change → `rollover` (:586-589); truncation → offset 0 (:592); feed rows, log reset/stale skips (:597); heartbeat (:604); health every 60 s (:610); `sleep(poll)`. |

Control flow: tail loop → day-boundary rebuild → `row_verdict` skip → `LevelWatch.update` → `_emit` → append JSONL → log → `_post_alert` → heartbeat/health → sleep.

Tests (`tests/scripts/test_orderflow_sentinel.py`): `row_verdict` :65-95 (`test_reset_row_is_skipped_as_reset`, `_stale_…`, `_market_row_is_not_skipped`, `_stale_and_zeroed_reads_as_reset_and_anomaly_wins`, `_equal_levels_alone_are_not_a_reset`, `_slightly_late_vendor_timestamp_is_fine` — exactly 120 s is still a market row); `test_feed_row_counts_and_skips` :109; `test_rollover_rebuilds_watches_and_resets_day_counters` :122; `test_day_two_first_rows_never_judged_by_day_one_window` :138 and its control `test_without_rollover_the_carried_window_does_fire` :155; `test_health_payload_shape` :169; `test_write_health_is_atomic_and_readable` :185; `test_replay_file_counts_skips_and_alerts_from_byte_zero` :196 (torn tail not consumed); `test_replay_alerts_carry_the_row_time` :216; `test_emit_posts_the_alert_to_the_bridge_best_effort` :239 (file written once, POST carries `strike`); `test_emit_survives_a_dead_bridge_and_logs_sparsely` :273; `test_bridge_is_off_when_unset` :287.

Reviewer's eye:
- `LevelWatch` gates use `time.monotonic()` (:318, :322, :379-380): under `--replay` the 120 s approach cooldown and 1800 s zone-reopen are **wall-clock**, so a replay compresses them (one approach per level per ~replay). Health/skip counts in replay are exact; alert counts are not live-equivalent.
- `ts_row` is the firing row's `ts_pull_utc` (:440-442, :224), not the vendor `timestamp`.
- With `--feed` overridden, `_feed_path` is constant (:558) so the rollover branch never fires — testing flag only.
- The reset rule `agg_dex == 0` (:103) is exact-zero; the stale rule requires numeric `timestamp` (:107) — a string timestamp bypasses it (basis.py coerces, see below).
- Unit sends SIGINT; there is no handler — `KeyboardInterrupt` propagates out of `main`. Nothing needs finalising (alerts are appended per event), so this is by design; unverified whether the last health write is missed on stop.
- `_iter_complete_lines` seeks a text-mode handle with a byte offset (:489-494) — valid for UTF-8 with no decoder state; relies on that.
- Module-level mutable state (`_LOG`, `_STATE`, `_BRIDGE`, `_bridge_failures`) is how `_emit` reaches context; tests monkeypatch it.

### 5.3 `market/orderflow/basis.py` — BasisEstimator

Purpose: live SPX→ES basis (`es ≈ spx + pts`) from the 1 Hz vendor spot; used by the feeder per closed bar. No CLI. Constants: `WINDOW=10` :36, `MAX_PAIR_AGE_S=5.0` :37, `STALE_ROW_S=120.0` :38, `TRIM_BEHIND_S=600.0` :40; trim threshold `> 2000` rows :163.

| Symbol | Line | What / invariant |
|---|---|---|
| `row_spot` | :50 | (epoch ts, spot) or None; refuses anomaly, non-positive/missing spot, reset shape, stale (>120 s behind `ts_pull_utc`). Independent copy of the sentinel rule (coerces via `float`, checks spot>0). |
| `BasisEstimator.__init__` | :81 | offset, ascending `_rows`, `deque(maxlen=window)` samples. |
| `refresh` | :94 | Byte-offset tail; torn line re-read; out-of-order vendor second dropped (:119); OSError → 0. |
| `spot_at` | :130 | Newest row at-or-before `when` within `max_pair_age_s`; no lookahead (same rule as `GexContext.poll_at`). |
| `sample(bar)` | :146 | Appends `round(close − spot, 2)`; trims `_rows` behind `end − 600 s` only when >2000 rows (:163-169) — trimming at sample, never at refresh, so whole-file-refresh-then-replay works; never raises. |
| `estimate` | :174 | `{pts: median(samples,2dp) | None, n, age_s}`; `age_s` = now − last sampled bar end (wall clock, :181). |

Tests (`tests/market/orderflow/test_basis.py`): `test_absent_file_yields_unknown_not_error` :38; `test_sample_pairs_the_bar_close_with_the_vendor_second` :44; `test_never_pairs_with_a_row_from_after_the_bar_close` :53; `test_a_row_older_than_the_pair_window_is_refused` :60 (5.0 s inclusive); `test_median_over_the_window_and_the_window_slides` :68; `test_sentinel_skip_shapes_are_refused` :80; `test_torn_final_line_is_re_read_whole` :92; `test_estimate_reports_sample_age` :102; `test_a_broken_bar_object_cannot_raise` :111; `test_whole_file_refresh_then_replay_pairs_every_bar` :119 (memory bound).

Reviewer's eye: skip rules exist twice (`row_spot` here, `row_verdict` in the sentinel) with small divergences (spot>0, string coercion). `spot_at` is a linear reverse scan; bounded by trim. `sample` catches bare `Exception` (:170).

### 5.4 `market/orderflow/gex_context.py` — `GexContext.for_bar(bar, basis=)`

Purpose: stamp each closed bar with the 60 s GexBot poll; Phase 3 change is the `basis` parameter. `MAX_AGE_S=300` :39.

| Symbol | Line | What / invariant |
|---|---|---|
| `refresh` | :66 | Byte-offset tail of `gexbot.jsonl`. |
| `_parse` | :97 | Extracts summary + `/classic/gex_zero/majors` leg → `ts,spot,flip,net_gex_oi,net_gex_vol,pos,neg,long_gamma,short_gamma,one_pos,one_neg`. |
| `poll_at` | :143 | Newest poll at-or-before, within `max_age_s`. |
| `for_bar` | :166 | Returns `{ts,age_s,spot,flip,pos,neg,one_pos,one_neg,regime,net_gex_oi,basis,dflip,touch}`. Levels stay SPX on the wire; only `touch` (`lo ≤ lvl + b ≤ hi` over pos/neg/flip/long_gamma/short_gamma, :203-206) and `dflip = close − (flip + b)` (:208) convert. `basis None` ⇒ `touch=[]`, `dflip=None` (never mixed units). Bare `except Exception` → None (:225). |

Tests (`tests/test_gex_context.py`): `test_touch_reports_majors_inside_the_bar_range` :98 (basis 0.0); `test_touch_and_dflip_convert_spx_levels_through_the_basis` :109 (+20 basis flips the touch verdict); `test_no_basis_means_unknown_not_mixed_units` :122; plus pre-existing :56-95, :131-165 (no lookahead, stale refused, torn line, malformed lines).

### 5.5 `scripts/corpus_stream_databento.py` — sequence on live rows

`StreamWorker._row` :374 — `"sequence": getattr(trade, "sequence", None)` (:398, was literal `None`). Consequence: `replay.dedup_key` (replay.py:56, `(sequence, ts_event)`) no longer collapses to `ts_event` alone; commit message cites 3.42 % of 08-14 volume previously dropped. Test: `test_writes_corpus_rows_matching_batch_schema` tests/market/corpus/test_stream_databento.py:123 — asserts `sequence == 29785284` on row 1 and `None` on a source without one (:150-152). Reviewer's eye: `getattr` default keeps a sequence-less Trade writing None, so batch/live parity depends on `ingest/databento.py` populating it (unverified here). Today's feeder log: `228,340 trades (6,480 duplicates dropped, 0 bad rows)` on the pre-seed read of 08-14 — the dedup now runs on the real key.

### 5.6 `scripts/measurement/basis_pairs.py` — Risk 4 measurement

Purpose: offline check that the 1 Hz spot is a usable basis source. CLI: `.venv/bin/python scripts/measurement/basis_pairs.py 2026-08-14 [more days]` (:14, `main` :121). `load_prints` :37 (ES `action=="T"` prints, `ts_event` trimmed to µs :29); `measure` :57 — for each 1 Hz row in RTH by vendor `timestamp` (13:30–20:00Z, :64-65), pairs `es_at(t) − spot` (bisect at-or-before), reports `median, p95_dev, lo, hi, hourly{n,median,p95_dev}`, and Schwab `spot_es − spot_spx` snapshots from `schwab.jsonl` (:100-117). Reviewer's eye: hard-coded `CORPUS` path (:26) and RTH bounds; **no reset/stale filtering** here (only `spot > 0`, :75), unlike `basis.row_spot`; no tests; result recorded in basis.py docstring (:10-14: median +20.75, p95 dev 0.70).

## 6. Bridge — `scripts/drill_bridge.py` (478 lines)

**Server / threading.** `ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)` at `:466` — one thread per request. All state is one module-level `STATE = BridgeState()` created at **import time** `:346` (side effect: makes `data/drill-bridge/` and appends a `bridge_start` line, `:111-113`). `BridgeState` has a single `threading.Lock` `:92`; every slot read/write is under it (`add_state :125`, `add_coach :132`, `add_bars :173`, `bars_since :213`, `add_alert :226`, `alerts_since :273`, `commands_since :279`, `tail :283`, `stats :294`). `producers_health` `:311` and `_send_page` `:378` are lock-free disk reads. Port from `DRILL_BRIDGE_PORT` `:62`; log file name fixed at construction to the **UTC** date the bridge started `:112` — a bridge that outlives the day keeps writing to the start-day file (day reset does not rotate it).

**Endpoints** (routing `do_GET :400`, `do_POST :436`; prefix strip `_route :391-397`, `PATH_PREFIXES=("/footprint",) :74`; bare `/footprint` → 302 to `/footprint/` `:404-410`; JSON via `_send :353` with `Access-Control-Allow-Origin: *` `:358`; POST body ≤ 1,000,000 bytes `:362-366`; `ValueError`/`JSONDecodeError` → 400 `:433, :459`):

| Method+path | Handler | Backing method |
|---|---|---|
| GET `/`, `/index.html` | `:411-412` → `_send_page :378-389` | serves `PAGE_PATH` bytes, `text/html`, `Cache-Control: no-store`; 503 if file absent `:379-382` |
| GET `/health/producers` | `:413-414` | `producers_health :311-343` |
| GET `/health` | `:415-416` | `stats :293-299` (`ok, started, events, queued, bars, alerts, log, page, page_present`) |
| GET `/commands?since=` | `:417-421` | `commands_since :278` |
| GET `/alerts?since=` | `:422-424` | `alerts_since :272-276` |
| GET `/bars?since=` | `:425-427` | `bars_since :212-218` |
| GET `/state/tail?n=` | `:428-430` | `tail :282-291` (cap 500) |
| POST `/state` | `:441-443` | `add_state :124` |
| POST `/bars` | `:444-450` | `add_bars(bars, meta, final, developing, profile) :138-210` |
| POST `/alerts` | `:451-453` | `add_alert :220-231` |
| POST `/coach` | `:454-456` | `add_coach :129-136` (types `:85`) |
| OPTIONS * | `:371-376` | 204 preflight |

**In-memory slots** (`__init__ :91-113`): `_commands` (append, 1-based id `:133`); `_bars` (append-only, `i` = position stamped at `:196`); `_bar_meta` (replaced wholesale when a truthy `meta` arrives `:174,190`); `_final` (replaced when truthy `:191-192` — an empty list never clears it); `_developing` (single slot: cleared when a push carries closed bars `:199-200`, then set if supplied `:201-202` — order matters); `_profile` (single slot, replaced when supplied, never retired by bars `:203-204`); `_alerts` (append-only, `id` = index+1 `:227`, plus `received_utc`); `_events` counter.

**Day-reset rule** `:181-189`: only when the incoming `meta.day` is truthy, the held `meta.day` is truthy, and they differ → log `day_reset` (from/to/dropped_bars/dropped_alerts) and clear `_bars, _final, _alerts, _developing, _profile`. Same-day meta re-post resets nothing. `_commands` and `_events` are **not** reset. Validation: `profile` dict `:165`, `bars` list `:167`, `final` list `:169`, `developing` dict `:171`; per-bar dict check is inside the append loop `:193-196` — a bad element mid-batch raises after earlier bars in that batch (and `meta`) were already applied.

**Alerts seed rule** `seed_alerts :233-270`: called once at start `:467` with `CORPUS_ROOT/<CT day>/orderflow_alerts.jsonl` (`_central_day :302-308`, falls back to zoneinfo when `market/` unimportable). Missing file → 0; **non-empty channel → 0 (no-op)** `:244-246`; blank/invalid lines skipped `:249-255`; each dict gets `id = len+1` (monotonic, under lock) `:257-262`, `received_utc = ts_alert_utc or now`, `seeded: True`; one `alerts_seeded` log line; `OSError` swallowed → 0 `:268-270`. The server socket is bound `:466` before seeding `:467` (tiny window where `/alerts` is empty). Live `add_alert` never re-checks the file.

**PRODUCERS spec** `:78-83` → `producers_health :311-343`:

| key | file | per_day | fresh_s |
|---|---|---|---|
| tape | `_capture_health.json` | False (corpus root) | 180 |
| gex_1s | `_gexbot_of1s_health.json` | False | 180 |
| sentinel | `_sentinel_health.json` | True (`<root>/<CT day>/`) | 90 |
| feed | `_footprint_health.json` | True | 90 |

Row per producer `:322-323`: `path, present, age_s (mtime age, 1 dp), fresh (age ≤ fresh_s), fresh_s, status` (from the JSON body when readable, else `"unreadable"` `:338-339`); sentinel adds `rows_today, last_row_pull_utc` `:332-334`; feed adds `sent, last_bar_t1` `:335-337`. Envelope `{day, checked_utc, producers}` `:319`. No verdict — the page decides.

**Page serving.** `PAGE_PATH` env `DRILL_BRIDGE_PAGE`, default `/tmp/desk-live-footprint.html` `:70` (systemd unit sets the same, `deploy/systemd/strader-drill-bridge.service:31`). File re-read on every GET `:383` — no caching. `CORPUS_ROOT` honours `STRADER_CORPUS_ROOT` `:67`.

## 7. Page JS — `scripts/orderflow_drill_template.html` (2,370 lines)

**Boot.** `DATA` injected at `:466`; `TICK = DATA.meta.tick :470`; `POLL_MS = 1000 :478`; `KEEP_COLS = 48 :475`; `bars = DATA.bars :495`; `LIVE = DATA.meta.source === "live" :496`; `PAGE_DAY = DATA.meta.date :500`. LIVE branch `:508-512` adds `body.live`, retitles, `buildLiveHud :519-548` (moves header/readouts/controls into `#livehud`, then moves `#bridge-dot`, `#prod-dots`, `#cue-chip`, `#sen-strip` beside `#meta` `:533-546`). Replay indexes all cues once `:835`. Bottom of script: `connectBridge() :2333`, wrappers reassign `step`/`armLevel`/… `:2336-2347`, `seekTo(0) :2369`.

`BRIDGE` derivation `:1913-1922`: `_pageDir` = pathname minus trailing `/`, or its dirname when it ends in an extension, else the pathname; `BRIDGE = origin + _pageDir` on http(s), else the literal `http://127.0.0.1:7788` (file://). `connectBridge :2320-2332`: GET `/health` → `bridgeUp`, `setDot("live")`, `pollBars()` if LIVE, `sendState("session_open")`, `pollCoach()`; on failure retry every 3 s. Independently `pollProducers` first fires at 800 ms `:2063`.

**Poll loop** `pollBars :1965-2024` (self-reschedules every `POLL_MS` `:2023`, even after errors; 3 consecutive errors → dot "feed stalled" `:2021`): fetch `/bars?since=bars.length` `:1968` → **day guard** `d.meta.day !== PAGE_DAY` → banner, keep polling, return `:1982-1985` (`showDayMismatch :2231`, `clearDayMismatch :2242`) → adopt `d.meta.bar_n` only `:1987` (`meta.tick` ignored) → `FINAL` replaced when length differs `:1991` → `DEV = d.developing || null :1992` → `PROFILE` replaced, `profileMoved = n changed :1994-1997` → append `d.bars`; `flash = wasAtTip && fresh.length ≤ 3 :1996`; `indexCues` **before** columns render `:1997`; `refreshMeta :1998`; catch-up `while (idx < bars.length-1) step()` only if `liveFollow && wasAtTip :2003` → `setDot("live · N bars") :2004` → `renderDeveloping :2013` → `renderProfile` if moved `:2014` → `await pollAlerts()` **after bars**, `drawSentinelRows()` if new alerts or fresh bars `:2017-2019`. Page never reads `d.total`; there is no "total < bars.length" resync for bars (contrast `pollAlerts`).

**Bars → columns.** `step :1165-1172` → `updateView :943-965` (window over the last `KEEP_COLS` bars, expand fast/contract 4 ticks per step, clamps to `maxRows`) → `repaintAll :1093-1098` or `drawAxis :967` → `finishBar :1151-1163` → `setCol(i, renderColumn(b,i)) :1156` (`setCol :1174-1181` replaces by `data-i` or appends and trims to `KEEP_COLS`). `renderColumn :1013-1091`: cells keyed by tick `:1017-1018`, whole-cell clipping `:1023`, `cell.dataset.tk :1025`, void cells `:1027-1035`, POC `:1039,1045`, footer + duration fill `:1054-1069`, evmark (click seeks only in replay `:1087`), `applyCues :1090`. `yFor :966`. `repaintAll` also re-renders the developing column `:1096` and the VP panel `:1097`.

**Cell cues** `:648-835`. Consts: `CUE_FLASH_MS = 900 :668` (must match `@keyframes cue-flash … 900ms` CSS `:194-198`), `CUE_FLASH_MAX_FRESH = 3 :669`, `CUE_BACK_BARS = 40 :670`, `CUE_ROLE :673-681` (edge/width/tone/glyph/label per role). State outside the DOM: `cueIndex: Map<barIdx,[{tk,role,type,src,bar}]> :682`, `cueSeen: Map<"src:type:tk:role", ms> :683`, `cuesOn :684` (not persisted), `reducedMotion :688` (read once). `cueBarFor(price,i,back) :694-701`: walk back ≤ `back` bars for the last bar whose `[l−½t, h+½t]` holds the price, else `i`.
`resolveTargets(e,i) :703-743`: if `e.targets` array present, it wins `:712-720` (`bar_i`, `bar_hint==="search_back"`, `kind==="band"` lo..hi, `role` default sweep/stack). Fallback by type:
- `ImbalanceStack` → each of `e.prices` → role `stack`, bar `i` `:723-724`.
- `SweepPrint` → needs finite `start_price`,`end_price` `:726`; ticks `lo..hi`; bar = `i` unless the range lies outside bar `i`'s `[l−½t,h+½t]`, then `cueBarFor(start_price, i, 2)` (i.e. i or i−1) `:729-730`; end tick role `sweep_end`, others `sweep` `:731`.
- `DeltaDivergence` → `e.price_extreme`, role `pivot`, bar `cueBarFor(…, i, 40)` `:734-735`.
- `SetupRecognition` → `e.anchor_price`, role `anchor`, bar `i` `:737-738`.
- `AbsorptionRead` → `e.price`, role `absorb` `:740`. Others → no cell `:742`.
`indexCues(i, fresh) :747-768`: resolver wrapped in try/catch `:754`; dedupe on (tk,role,src,type) `:757`; stamps `cueSeen` only if `fresh && !reducedMotion` `:760`; earlier bars touched are repainted in place only if their column node exists `:765-767`. `markCuesFresh(i) :771-774` (replay: stamps everything with `src===i`); called from `finishBar` only when `!LIVE && playing :1155`. `applyCues(col,b,i) :776-822`: bails on `!cuesOn || b !== bars[i]` (developing column never cued) `:777`; groups by tick, one inset box-shadow per edge `:790-795`, glyph + count>3 `:805`, tooltip lines `:800,807`, click pins the emissions panel to `src` `:810`; flash iff `now − newest cueSeen < CUE_FLASH_MS` `:815-820` with negative `animationDelay` and JS-timed class removal. `toggleCues :824-829` (`x` key `:1894`; chip click `:830`).

**#vp panel** `:837-926`. `VP_W = 132 :843`; `PROFILE :844`; `vpOn = LIVE && localStorage["oflow-vp-on"] !== "0" :845`. `applyVpLayout :849-854` (on iff `LIVE && vpOn && PROFILE.n > 0`; sets `#vp` width and `#cols` left). `renderProfile :856-919`: fields consumed `bucket (||TICK), lo_tick, buy[], sell[], seeded{buy[],sell[]}, va{poc,vah,val}, hvn[], lvn[], n, anchor, anchor_ts, first_ts, last_ts, hole[[a,b]]`. Rows only for visible, non-zero buckets `:868-874`; `vmax` scaled to visible rows `:873`; POC = `|price−poc| < bucket/2` `:885` else VA = `val−½b ≤ price ≤ vah+½b` `:886` (POC row is not also VA); HVN/LVN by rounded tick `:879-880,887-888`; segments in order `ss` (prior sell, faint), `st` (today sell), `bs` (prior buy, faint), `bt` (today buy) `:889-896` — CSS `:219-222` (sell red left, buy blue); title arithmetic `:897-902`; header label hard-codes `prior-rth → "Dow 08:30 CT"`, `prior-globex → "17:00 CT"` `:904-908`; hole banner from payload `:911-914` with hard-coded "02:50–15:05 CT" note in its title `:915`. `toggleVp :920-925` (`v` key `:1895`, persists localStorage).

**Sentinel rows** `:2064-2226`. `SENT_KEEP_MARKS = 30, SENT_BASIS_BACK = 40 :2079`; `sentAlerts[], sentSeen, sentOn (localStorage "oflow-sent-on") :2080`; `SEN_NAMES :2081` (JS copy of level short-names). `senSpx(a) :2086-2093`: `value → new → settled → (low+high)/2 → contenders[0].value`. `senSentence :2095-2103` (twin of `orderflow_alert_fmt.py`; reads `kind,name,level,strike,side,spot,distance_pts,strike_low,strike_high,contenders[].strike/share,old`). `basisNow :2105-2110`: newest bar within 40 with `bs.pts` finite → that `bs`. `senBarFor :2116-2129`: bar whose `[t0,t1)` holds `ts_row || ts_alert_utc`, else last bar with `t1 ≤ t`, else tip; cached on the alert as `_bar`. `senColX :2131-2137`: `x = colsWidth − (idx−i+1)·COL_W`, off-screen left → `{x:0,on:false}`. `drawSentinelRows :2152-2202` (called from `drawLevelLine :980` on every axis draw, and after polls): strip states `empty` / `nobasis` / `ok` `:2156-2164`; **ES = senSpx(a) + bs.pts** `:2172`; one row per `a.level` (newest wins) `:2170-2171`; line at `top = yFor(es)`, `left = cols.offsetLeft + x` `:2176-2180`; tag text `⚑ <short> <strike ?? round(spx)> · <kind>[ (earlier)] · ES <tick-rounded>` `:2184`; tooltip carries the arithmetic `:2185`; marks for the last 30 untagged alerts on-screen `:2189-2201`. `pollAlerts :2205-2226`: GET `/alerts?since=sentSeen`; if `d.total < sentSeen` → clear and refetch `since=0` `:2211-2217`; else append `d.alerts`, `sentSeen = d.total`; any error → `false`. `toggleSentinel :2144-2149` (`s` key `:1896`; strip click `:2150`). HUD strip: `#sen-strip` markup `:403`, `senStripText :2138-2142`, CSS `:245-257`.

**Producer dots** `:2026-2063`. `PROD_ORDER :2030` (tape/1Hz/sent/feed), `PROD_POLL_MS = 15000 :2031`. `renderProducerDots(h) :2032-2054` reads `h.producers[key].{present, path, status, fresh, age_s, fresh_s}`: no entry → grey "no data"; `!present` → `bad` (red); `status idle|quiet` → neutral grey; `fresh` → `ok` (green); `age_s ≤ 3·fresh_s` → `warn` (amber `--cue`); else `bad`. Colours CSS `:234-237`. `pollProducers :2055-2061`: fetch failure → `renderProducerDots(null)` greys all.

### 7.1 Contracts as the page reads them

- **GET /bars** → `{bars:[…], total, meta:{day, bar_n, tick, source, …}, final:[…], developing:{…}|null, profile:{…}|null}` (`bars_since :215-218`). Page reads `meta.day`, `meta.bar_n`, `final`, `developing`, `profile`, `bars`; ignores `total`, `meta.tick`. Bar fields the page reads: `t0,t1,o,h,l,c,v,d,nv,dur,poc,cells[[price,bid,ask]],steps,ev[],bs{pts,n},i` (feeder `bar_payload` `scripts/live_footprint_feed.py:300-310`; feeder meta `:462-465`; feeder pushes ≤25 bars or every 1 s `:652,695`).
- **GET /alerts** → `{alerts:[…], total, day}` (`:275-276`); page reads `alerts`, `total`; each alert: sentinel schema + `id`, `received_utc`, optional `seeded`.
- **GET /health/producers** → `{day, checked_utc, producers:{tape,gex_1s,sentinel,feed → {path,present,age_s,fresh,fresh_s,status[,rows_today,last_row_pull_utc|sent,last_bar_t1]}}}` (`:319-342`).
- **GET /health** → `{ok, started, events, queued, bars, alerts, log, page, page_present}` (`:295-299`); page only needs it to parse.

### 7.2 Bridge + page tests and checks

`tests/scripts/test_drill_bridge.py` (19): log start `:16`; state events `:21`; coach ids monotonic `:30`; invalid coach `:39`; coach logged `:45`; JSONL valid `:51`; tail bounds `:57`; `final` served on every response `:66`; `final` replaced `:82`; `final` must be list `:88`; bars carry `ev` + `i` `:93`; `/` serves page + `no-store` `:134`; 503 until rendered `:145`; `/footprint` prefix + 302 `:154`; producers_health age/fresh/status/rows_today `:175`; profile slot replaced/served at tip/never retired `:200`; alerts ids + incremental + log `:217`; day reset (same-day no-op, new day drops all, `day_reset` log) `:238`; seed from file (skips bad lines, `seeded`, `received_utc=ts_alert_utc`, no-op onto non-empty, live id continues, missing → 0) `:264`.
`tests/scripts/test_cell_cue_contract.py` (5): fixture emits Sweep+Setup `:73`; resolver fields present/finite/on-grid `:83`; every stack price is a traded cell `:103`; sweep range in bar or i−1 `:129`; `prices` serializes as list `:146`.
`tools/cell_cue_check.mjs` (8 groups, `:15-26`; assertions `:138-209`): backfill paints/no flash, fresh flash then mark, survives `repaintAll`, sweep range/end, pivot on earlier bar, i−1 sweep, burst no flash, `x` toggle, developing never cued, click pins panel. `tools/vp_panel_check.mjs` `:115-152`: panel on/cols pushed, row/cell alignment at cellH 13/18/24, POC once, seg order `ss,st,bs,bt`, VA/HVN/LVN, hole from payload, header, `v` toggle, grown profile redraw. `tools/sentinel_rows_check.mjs` `:110-164`: no basis → no rows + strip says so, `top == yFor(spx+basis)`, left at firing column, tag/tooltip text, two levels, relocation replaces row + mark on earlier bar, `s` toggle, zoom re-place, reset refetch, no uncaught errors. `tools/live_follow_check.mjs` `:116-164`: follow on/off/resume. `tools/page_boot_check.mjs`: boot without uncaught errors.

Run today (2026-08-17):
```
.venv/bin/python3 -m pytest -q tests/scripts/test_drill_bridge.py tests/scripts/test_cell_cue_contract.py   → 24 passed (19 + 5)
.venv/bin/python scripts/live_footprint_page.py --date 2026-08-07 --out <scratch>/live-cue.html            (LIVE page, empty tape)
bash tools/nodecheck.sh tools/<check>.mjs <scratch>/live-cue.html   (node v20.20.2; jsdom 24.1.3 — jsdom is not in-tree, it was symlinked from an existing scratch install; nodecheck.sh derives NODE_PATH from the target's dir)
  cell_cue_check      27 PASS / 0 FAIL, "all checks clean", exit 0
  vp_panel_check      15 PASS / 0 FAIL, exit 0
  sentinel_rows_check 21 PASS / 0 FAIL, "ALL PASS", exit 0
  live_follow_check   16 PASS / 0 FAIL, exit 0
  page_boot_check     booted, 0 bars, status clean, exit 0
```

### 7.3 Reviewer's eye — bridge + page

- **Hard-coded literals:** bridge port fallback `7788` in the page `:1922` and `PORT` default `:62` (must agree; docstring `:46`); `PATH_PREFIXES` `:74`; `PAGE_PATH` default `:70`; producer budgets `:78-83`; body cap 1 MB `:364`; `POLL_MS` `:478`, `PROD_POLL_MS` `:2031`, first producer poll 800 ms `:2063`, coach poll 2 s `:1957`, health retry 3 s `:2331`, coach reconnect 10 s `:1955`; `CUE_FLASH_MS=900` `:668` duplicated in CSS `:198`; `CUE_FLASH_MAX_FRESH=3`, `CUE_BACK_BARS=40`, sweep back-search 2 `:730`; `SENT_KEEP_MARKS=30`, `SENT_BASIS_BACK=40` `:2079`; `SEN_NAMES` `:2081` and `senSentence` `:2095` are hand-kept twins of Python (`LEVEL_NAMES`, `orderflow_alert_fmt.py`); VP header labels "08:30 CT"/"17:00 CT" `:904` and hole note "02:50–15:05 CT" `:915`; `.sen-line right:56px` CSS `:245`; `VP_W=132` `:843`.
- **Best-effort catches:** `seed_alerts` swallows `OSError` `:268` and bad lines `:254`; `producers_health` swallows `OSError` `:340`, unreadable JSON → `"unreadable"` `:338`; `_central_day` bare `except Exception` `:306`; page: resolver try/catch `:754`, `pollAlerts` → `false` on any error `:2225` (its failures never count toward `liveErrs`), `pollProducers` → grey `:2060`, `sendState` `.catch(()=>{})` `:1940`, `pollBars` swallows and counts `:2020-2022`.
- **Ordering assumptions:** alerts polled after bars so `basisNow()` sees the newest `bs` `:2017-2019`; `indexCues` before `step()` `:1996-2003`; bridge `add_bars` applies `meta` (and the day reset) before `final`/bars `:174-192`, clears `developing` before setting a new one `:199-202`; `_body()` is parsed before routing `:439-440` (a POST to an unknown route with a bad body returns 400 not 404); socket bound before alerts seed `:466-467`.
- **Unbounded within a day:** bridge `_bars`, `_alerts` (reset only on day change), `_commands`/`_events` never reset `:188`; page `bars`, `cueIndex`, `cueSeen` (never pruned; `markCuesFresh` scans all of it per replay bar `:773`), `sentAlerts` (marks capped at 30 but the array is not), `#bartable` rows via `appendBarRow`. `/bars` returns `final` + full `profile` (buy/sell/none/seeded arrays) on every 1 s poll `:215-218` — no ETag/If-None-Match.
- **Partial-apply on bad input:** `add_bars` validates each bar inside the append loop `:193-196` — a non-dict at position k raises after k bars (and `meta`, `final`) were applied; `_final` cannot be cleared by posting `[]` `:191`; `add_alert` accepts any non-empty dict, no schema `:224`.
- **Bars channel has no resync; alerts channel does.** `pollAlerts` handles `total < sentSeen` `:2211`; `pollBars` ignores `d.total` and keeps asking `since=bars.length` — after a same-day bridge restart the page shows nothing new until reload (day-change is caught by the banner `:1982`; same-day restart under systemd `Restart=always` is unverified as to feeder behaviour). Also `PAGE_DAY` is baked at render `:500`; page must be re-rendered daily (bridge serves the file with `no-store` `:387`).
- **Long-lived bridge log:** log filename fixed at construction to the UTC start date `:112`; under systemd (`Restart=always`) the file only rotates on process restart. `producers_health` and `seed_alerts` use CT day `:318, :467`.
- **Flash vs mark:** `@keyframes cue-flash` animates `box-shadow` `:194-197` with fill-mode `both` `:198`, so the inline inset edge mark (`:808`) is not visible during the 900 ms flash and reappears only when the JS timer removes `.cue-new` `:819`; `reducedMotion` is sampled once at boot `:688`. CSS names roles `cue-flush`/`cue-confirm` `:192-193` that no resolver path emits (unknown roles fall back to `CUE_ROLE.stack` `:786`).
- **LIVE vs replay divergence:** flash gate LIVE = `wasAtTip && ≤3 fresh` `:1996` vs replay = `playing` `:1155`; cues indexed at boot in replay `:835`, incrementally in LIVE; evmark click seeks only in replay `:1087`; `step()` at end-of-tape pauses only in replay `:1167`; VP panel `:845,850`, sentinel rows `:2154`, producer dots `:2056` + CSS `:232-233`, Mancini lines `:996`, `pollBars` `:1966`, `pollAlerts` `:2206` are all LIVE-only; `BRIDGE` derivation applies to both (a file:// replay drill still targets 127.0.0.1:7788 for coach). `renderColumn` indexes `b.cells[0]` `:1018` — a bar with empty `cells` would throw (feeder never sends one: closed bars have 2000 contracts; developing is `None` when no pending trades, `live_footprint_feed.py:331`).
- **Keyboard:** handler ignores only `INPUT` targets `:1884`; `x`/`v`/`s` fire when focus is on a `<select>`/button (unverified whether that matters).
- **Import side effect:** `STATE = BridgeState()` at `:346` writes `data/drill-bridge/state-<UTC date>.jsonl` on any import (tests import the module `tests/scripts/test_drill_bridge.py:8` and then build their own instance with `tmp_path`).

## 8. Profile library — `market/orderflow/anchored_profile.py` (361 lines), `tradesource.py`, calendar, corpus root

| Symbol | Line | Note |
|---|---|---|
| module docstring — why bars vs ticks (02:50–15:05 CT capture hole) | 1–27 | pre-V2 rationale, still accurate |
| `RTH_OPEN_CT = time(8, 30)` | 45 | hard-coded anchor clock, CT |
| `VALUE_AREA_COVERAGE = 0.70` | 49 | |
| `class ValueArea` (val/poc/vah/volume/total/coverage) | 52–69 | |
| `class SplitProfile` (symbol,start_ts,end_ts,bucket_pts,prices,buy_volumes,sell_volumes) | 72–119 | `.volumes`=b+s, `.deltas`, `.total`, `.delta`, `.as_volume_profile()`; **N volume is not in it** |
| `HOLE_MIN_S = 30 * 60` | 125 | gap ≥ 30 min between consecutive prints = hole |
| `class SplitAccumulator` | 128–207 | `__slots__` 145; `__init__(bucket_ticks=1)` 148 → `self.bucket = bucket_ticks * TICK` (TICK=0.25, `orderflow_config.py:16`) |
| `.add(t)` | 160–173 | `k = int(t.price // bucket)` (floor, 161); side `"B"`→buys, `"A"`→sells, else→nones (162–167); first trade sets symbol/first_ts (168–169); hole recorded when `t.ts - last_ts >= HOLE_MIN_S` (170–171) |
| `.mark_seeded()` | 175–178 | snapshot `{n, through_ts, buys, sells}` — nones NOT snapshotted |
| `.keys()` | 180–184 | contiguous `range(min_k, max_k+1)` over all three dicts |
| `.snapshot(none_policy="separate")` | 186–207 | `halve`: `half=int(nn/2)` to buys, remainder to sells (196–199) → odd N leans sell (test :79: 3 → 1 buy/2 sell); raises on n==0 (190) |
| `build_split_profile(trades, bucket_ticks=1, none_policy="separate")` | 210–232 | thin wrapper over the accumulator; docstring records the None-Policy decision (220–227) |
| `profile_payload(acc, *, anchor, anchor_ts, session_day, hvn_min=0.70, lvn_max=0.30)` | 235–273 | wire form |
| `anchor_utc(session_day, open_ct=RTH_OPEN_CT)` | 276–283 | CT → UTC |
| `_bar_trades`, `build_profile_from_bars` (bar path, `PROFILE_BUCKET_TICKS=4`) | 286–329 | pre-V2, unchanged |
| `value_area(profile, coverage=0.70)` | 332–361 | single-row expansion from POC, ties take upper (347, 354) |

**Invariant** (docstring 136–138; pinned by `tests/market/orderflow/test_split_accumulator.py:37–56`): for every price P, `buys[P] + sells[P] == Σ over closed bars of cells[P].bid + cells[P].ask` (cells `bid_vol`=A-side, `ask_vol`=B-side), and `Σ nones == Σ bar.none_vol` — holds because `build_bars` also keeps N out of cells (`NONE_SIDE_POLICY="separate"`, `orderflow_config.py:31`).

**none_policy**: `separate` (default everywhere since 0367fcb) — N prints stay in `nones`, excluded from `SplitProfile.total` and from POC/VA. `halve` — opt-in on `snapshot`/`build_split_profile` for total==traded. On ES it is a no-op (0 N of 258k on 08-11, per docstring 227). `profile_payload` always emits `none` as its own array (256) and computes VA from `acc.snapshot()` = separate (262).

**Payload shape** (244–273): `v:1, anchor:str, anchor_ts:iso, session_day:"YYYY-MM-DD", bucket:0.25, n:int, first_ts, last_ts, hole:[[iso,iso],…]`; if `n>0`: `lo_tick:int` (= keys.start), `buy[]`, `sell[]`, `none[]` (parallel, one entry per tick from lo_tick), `seeded:{n, through_ts, buy[], sell[]}` (only if `mark_seeded` was called; same key range as the live arrays), and if `vp.total>0`: `va:{poc,vah,val}` (bucket floors), `hvn:[prices]` (local maxima ≠ POC, ≥ 0.70·POC vol), `lvn:[prices]` (local minima, 0 < vol ≤ 0.30·POC vol) via `profile._local_extrema` (266–272). Empty accumulator → `n:0`, no arrays (249–250).

**Prior day vs today**: distinguished by `seeded` (the pre-seed boundary snapshot) — the page draws `seeded.buy/sell` faint and `buy/sell` (cumulative, includes the seed) on top; the 15:05→02:50 CT gap lands in `hole`. Bucket size is 1 tick = 0.25 (feeder constructs `SplitAccumulator(1)`, `live_footprint_feed.py:492`).

**Live evidence** (bridge `/bars` at ~16:37 CT today): `n=451,606, seeded.n=205,789 through 2026-08-14 15:05 CT, anchor_ts 2026-08-14T13:30:00Z, hole ×1, 260 buckets from lo_tick 31064 (7766.0), poc 7803.0 vah 7823.5 val 7786.0, hvn ×4, lvn ×45`.

Feeder wiring (`scripts/live_footprint_feed.py`): `--vp-anchor` 397–404 (default `prior-rth`; `prior-globex`; ISO; `off`); `resolve_vp_anchor` 606–620; pre-seed 490–508 (`iter_trades(prior_trading_day(day), start_ts=vp_anchor_ts)` — no `end_ts`, so the seed runs to the prior file's last print; `FileNotFoundError` → warning + empty seed layer 500–505); tee `vp.add(t)` 569 before `build_bars`; pushed on every developing tick and closed batch (576, 593) into the bridge's replaced `profile` slot (`drill_bridge.py:103,160–166,203–204`).

**`market/orderflow/tradesource.py` (38 lines).** `iter_trades(day: date | Path, *, start_ts=None, end_ts=None) -> Iterator[Trade]` — :26–38. Yields `Trade`s from `replay.read_corpus_day(day)` (deduped by `dedup_key`, sorted (ts, seq)), filtered `start_ts <= ts < end_ts` (`break` on end_ts, 36). Source today: `data/corpus/<day>/databento_glbx_es.jsonl` (or `.jsonl.gz` via `open_corpus_text`) — `replay.py:34–35,105`. Raises `FileNotFoundError` when the day has no ES file (docstring 30–32). Seam comment :11–14: Schwab (bars) and GexBot (no prints) adapters deliberately NOT built — "a stub interface for a source that cannot exist is over-building".

**Calendar and corpus root.** `strader/market_calendar.py:122–129` — `prior_trading_day(d: date) -> date`: `d -= 1 day` while `not is_trading_day(d)`; `is_trading_day` (:100–106) = weekday and not in the hand-maintained `HOLIDAYS` table (2026, 2027 only, :43–68); unknown years degrade to weekday-only. `market/corpus/paths.py:32` — `CORPUS_ROOT = Path(os.environ.get("STRADER_CORPUS_ROOT") or (PROJECT_ROOT / "data" / "corpus"))`, read once at import; every helper in that module derives from it (`day_dir` :64). `scripts/drill_bridge.py:67` reads the same env var itself.

## 9. Seams — corpus_daily guard, surface_liveness

**`scripts/corpus_daily.py` — Risk 15 guard.** `stream_healthy_in_manifest(day, stream)` :142–146 — cycles>0 AND no errors (the pre-existing idempotency skip). `stream_has_rows_in_manifest(day, stream) -> (bool, list[str])` :149–165 — cycles>0 regardless of errors, plus the error list. `_stream_state` :168–178 (missing/unparseable manifest → None). Rule, in the Databento loop :283–300: if not `--force` and healthy → skip (287–289); else if not `--force` and has rows → **skip with warning** (290–300): `"skip %s: %s already holds rows for %s (errors: %s) — a batch append would double the tape; use --force with --start-ct/--end-ct to fill a specific gap"`. Escape: `--force` (:255) plus `--start-ct/--end-ct` (:259–261) for a windowed pull. The loop covers only `DATABENTO_PULLS = {"databento_glbx_es": …}` (:77–79). The MBP-1 branch (:311–332) still uses only `stream_healthy_in_manifest` — no Risk-15 guard there.

**`scripts/surface_liveness.sh` — hstat rows (:87–112).** `hstat <label> <path> <fresh_s>` :92–108: age = now − mtime; `status` = JSON `status` or `state` field; `IDLE` if status ∈ {idle, quiet} (checked BEFORE age, :103); else `FRESH` age ≤ fresh; `AGING` age ≤ 3×fresh; `STALE` beyond. Rows :109–112:

| Row | File | fresh_s | AGING/STALE bounds |
|---|---|---|---|
| tape health | `data/corpus/_capture_health.json` | 180 | ≤540 / >540 |
| 1Hz gex health | `data/corpus/_gexbot_of1s_health.json` | 180 | ≤540 / >540 |
| sentinel health | `data/corpus/<today>/_sentinel_health.json` | 90 | ≤270 / >270 |
| feed health | `data/corpus/<today>/_footprint_health.json` | 90 | ≤270 / >270 |

Budgets equal the bridge's `PRODUCERS` table (`drill_bridge.py:78–82`: 180/180/90/90). Process rows :70–85 also updated (bridge/feeder → systemd since 08-16; sentinel unit; GEX rows → timers).

## 10. Deploy / systemd

**strader-drill-bridge.service** (`deploy/systemd/…`, 42 lines): `After=network-online.target`, `Wants=network-online.target` (21–22); `StartLimitIntervalSec=300 / Burst=10`; `Type=exec`; `WorkingDirectory=/root/projects/Strader`; `Environment=PYTHONPATH=/root/projects/Strader`, `Environment=DRILL_BRIDGE_PAGE=/tmp/desk-live-footprint.html` (30–31); `ExecStart=/root/projects/Strader/.venv/bin/python /root/projects/Strader/scripts/drill_bridge.py` (32, no flags → port 7788 `drill_bridge.py:62`); `Restart=always`, `RestartSec=3s`; `KillSignal=SIGINT`, `TimeoutStopSec=15`; journal, `SyslogIdentifier=strader-drill-bridge`; `WantedBy=multi-user.target`.

**strader-footprint-feed.service** (46 lines): `PartOf=strader-drill-bridge.service`, `After=strader-drill-bridge.service network-online.target`, `Wants=strader-drill-bridge.service` (24–26); `StartLimitIntervalSec=600 / Burst=10`; `WorkingDirectory` + `PYTHONPATH` as above; `ExecStartPre=-…/.venv/bin/python …/scripts/live_footprint_page.py` (35, `-` = failure tolerated); `ExecStart=…/.venv/bin/python …/scripts/live_footprint_feed.py` (36, no flags → defaults: today CT, bridge 127.0.0.1:7788, bar_n 2000, `--vp-anchor prior-rth`, developing 1 s); `Restart=on-failure` (SIGTERM→exit 0 is a stop; DayRolledOver exits non-zero → restart → new day's page), `RestartSec=10s`; `KillSignal=SIGTERM`, `TimeoutStopSec=30`; `WantedBy=multi-user.target`.

**strader-orderflow-sentinel.service** (installed, pre-V2 st-2yuw): `ExecStart=… scripts/orderflow_sentinel.py --log-dir /var/moo/logs/orderflow-sentinel`, `Restart=on-failure`, `RestartSec=5s`, `KillSignal=SIGINT`, `TimeoutStopSec=30`.

**deploy/install.sh** (59 lines): copies (not symlinks) every `deploy/systemd/*.service|*.timer` into `/etc/systemd/system` only when `cmp` differs (28–42) — idempotent; `--diff` shows unified diffs and touches nothing (35–37, 43–45); `systemctl daemon-reload` (46); enables every unit with an `[Install]` section (47–52); `--start` restarts only bridge/feed/sentinel (53–58), never a timer's service. `set -euo pipefail`.

**scripts/live-footprint-up.sh** (:49–70): if `strader-drill-bridge.service` is active and `--tmux`/`STRADER_FP_FORCE_TMUX=1` not set → prints the viewer block (page URLs incl. tailnet `https://mydesk-1.tail89f676.ts.net/footprint/`, `journalctl -fu` lines, the bridge restart command) and exits 0. Otherwise the old path: render page (76), reuse/detect stale tmux window via bridge `meta.day` (80–105), guard on a running `corpus_stream_databento.py` (120–127), three panes (136–154).

**Installed == repo**: `diff -u /etc/systemd/system/<u> deploy/systemd/<u>` IDENTICAL for all three; `bash deploy/install.sh --diff` → `0 unit(s) differ`. All three `enabled`.

**State (systemctl status, ~16:37 CT 08-17)**: bridge active since Sun 14:21:35 CDT, PID 877159, 16.2 MB; last log `drill bridge on http://127.0.0.1:7788 — log data/drill-bridge/state-2026-08-16.jsonl — page /tmp/desk-live-footprint.html — 0 alert(s) seeded from today's file`. Feeder active since Mon 00:00:10 CDT (restart counter 1 = the CT-midnight DayRolledOver restart, as designed), PID 946785, ExecStartPre exit 0 (`day=2026-08-17 N=2000 mancini levels=0`); logs: `read_corpus_day databento_glbx_es.jsonl: 228340 trades (6480 duplicates dropped)` → `profile pre-seeded from 2026-08-14: 205789 prints since 2026-08-14T13:30:00+00:00 (prior-rth)` → 02:50:05 `reading …/2026-08-17/databento_glbx_es.jsonl (following)`. Sentinel active since Sun 14:07:42 CDT, PID 858777; heartbeats every ~10 min, `rows=12676`, last alert 14:58:57 CT (`approach z_msgamma 7750.3`); alerts present in the bridge `/alerts` channel (ids from 1, first 13:30:10Z) — the f6a205f bridge-POST path is running.

## 11. Test inventory — the whole V2 change set

| File | tests | Pins |
|---|---|---|
| tests/market/corpus/test_paths.py | 5 | most_recent_session_day; `STRADER_CORPUS_ROOT` re-import (:41–56) |
| tests/market/corpus/test_stream_databento.py | 12 | live capture rows match batch schema (incl. `sequence`); reconnect keeps both segments; MBP-1 stream |
| tests/market/orderflow/test_basis.py | 10 | SPX→ES basis: pairing rule, window, median, torn-line re-read, unknown-not-error |
| tests/market/orderflow/test_split_accumulator.py | 8 | profile==Σcells invariant on golden fixture; separate default; halve opt-in; seeded/holes/payload keys; empty payload; prior_trading_day (Mon/Sun/Labor Day); iter_trades windowing |
| tests/scripts/test_cell_cue_contract.py | 5 | emission-cell cue resolver contract (Phase 1) |
| tests/scripts/test_corpus_daily_batch_guard.py | 3 | Risk 15: rows-with-errors ≠ healthy; absent/empty; main skips + names errors |
| tests/scripts/test_drill_bridge.py | 19 | log/coach channel; serves page (200/503); `/health/producers`; profile slot replaced; alerts append+poll; day reset; alert seeding |
| tests/scripts/test_live_footprint_feed.py | 20 | feeder bars == replay bars; reorder/dedup/tail; day-roll guard; payload shape; drive_and_publish finalise on kill/rollover; basis on closed bars |
| tests/scripts/test_orderflow_sentinel.py | 17 | reset/stale row skip; day rollover; health file; replay; bridge POST best-effort |
| tests/scripts/test_premarket_volume_profile.py | 24 | premarket page + `build_split_profile` contract (N not invented into a side, :81–92) |
| tests/test_gex_context.py | 12 | GEX bar context; SPX levels converted through basis |

Aggregate, run today: `.venv/bin/python3 -m pytest -q <these 11 files>` → **135 passed, 0 failed, 0 skipped in 2.82 s**. Golden fixture `tests/market/fixtures/es_ticks_golden_20260702.jsonl` present (580 KB), so the invariant test ran, not skipped. Page checks (jsdom): `cell_cue 27/27 · vp_panel 15/15 · sentinel_rows 21/21 · live_follow 16/16 · page_boot clean` — jsdom is not in the tree; `tools/nodecheck.sh` needs a `node_modules` beside the target page.

One command to re-run the Python set during the walk:

```
.venv/bin/python3 -m pytest -q tests/market/corpus/test_paths.py tests/market/corpus/test_stream_databento.py \
  tests/market/orderflow/test_basis.py tests/market/orderflow/test_split_accumulator.py \
  tests/scripts/test_cell_cue_contract.py tests/scripts/test_corpus_daily_batch_guard.py \
  tests/scripts/test_drill_bridge.py tests/scripts/test_live_footprint_feed.py \
  tests/scripts/test_orderflow_sentinel.py tests/scripts/test_premarket_volume_profile.py tests/test_gex_context.py
```

### 11.1 Reviewer's eye — profile, seams, deploy

- Hard-coded: `RTH_OPEN_CT = 08:30 CT` (anchored_profile.py:45), `HOLE_MIN_S = 1800` (:125), VA 0.70 (:49), HVN/LVN thresholds 0.70/0.30 (:236), bucket 1 tick from the feeder (`live_footprint_feed.py:492`), `prior-globex` = 17:00 CT (:616). Feeder unit passes no flags — every default is in code, not the unit.
- `prior_trading_day`: weekend + table holidays for 2026/2027 only; 2028+ = weekday-only (market_calendar.py:100–106, 43–68). Test covers Mon→Fri, Sun→Fri, Labor Day (test_split_accumulator.py:128–133).
- Empty-but-present prior-day file: `read_corpus_day` returns `[]` → seed n=0, `mark_seeded()` still called, only an INFO "0 prints" line (feed :498–500); the `FileNotFoundError` warning path (:500–505) does not fire. Compacted `.gz` prior day is handled (replay.py:102–105).
- `mark_seeded` snapshots buys/sells only, not nones (:177–178) — fine on ES (N=0), inconsistent by design otherwise. `snapshot("halve")` on odd N: extra contract goes to the sell side (:198–199).
- Out-of-order print (ts < last_ts) in `add`: negative delta → no hole, `last_ts` regresses (:170–172); the live tee is fed by `ordered_trades` so this should not occur; the batch path is pre-sorted.
- **STRADER_CORPUS_ROOT is a partial seam**: honoured by `market/corpus/paths.py` and `drill_bridge.py`; NOT by `replay.py:34` (`_CORPUS_ROOT` hard-coded — this is what `iter_trades(date)` and the feeder's `es_day_path` (feed :425) resolve through), `quotes.py:32`, `surface_liveness.sh:26,109–110`, `schwab_token_health.py:42`. Under the override the feeder would read the tape from `data/corpus` but write `_footprint_health.json` under the override root (feed :539). The commit message scopes the claim to paths+bridge, so this is a known edge, not a regression.
- Risk-15 guard covers the ES trade pull only; MBP-1 backfill (:311–332) still keys on `stream_healthy_in_manifest`.
- `test_main_skips_the_batch_when_live_rows_exist` runs `--dry-run` (:55), so `"corpus_pull_databento_es.py" not in calls` (:56) is vacuous (dry-run never calls `run_pull`); the load-bearing assertion is the caplog "would double the tape" + error text (:57–58). The docstring's "--force still pulls" is not asserted anywhere.
- surface_liveness `hstat`: `status idle/quiet` short-circuits age (:103) — a producer that wrote `idle` and then died reads IDLE forever, never STALE. Observed now: `_capture_health.json` last written 2026-08-13T23:10Z (`status: idle`, ~94 h old) while today's ES file grew ~246k prints; the file is written by `scripts/capture_health.py` (a checker), not by the capture stream, so the note at :109 ("capture writes it while streaming") is inaccurate. Same file feeds the bridge's `tape` dot. This is the co-03ojd.7 gap in §2.
- Sentinel PID 858777 started 14:07:42 CDT, 1m43s before commit f6a205f (14:09:25) touched `orderflow_sentinel.py`; the running process does POST to the bridge (alerts ids 1.. present), so it was started from a working tree that already had the change — byte-identity to HEAD not provable from here. Bridge PID started 9 s before 4a6ae59 landed; its start log line shows the seeding code running. Cheap to remove the doubt after close: restart the bridge unit (feed cascades) and the sentinel unit.
- Best-effort catches: `write_feed_health` swallows `OSError` (feed :623–636); feeder profile push rides `post_bars` (best-effort HTTP); `install.sh` enable errors are silenced (`>/dev/null 2>&1`, :50) — a failed enable prints nothing.

## 12. Standing decisions and what is left

Plan "Decisions that need Steve": (1) hosting → **ruled, units** (08-16 08:26: "coming back after restart is a yes"); (2) premarket 08:16 page (st-6gs3) and (3) sentinel phone push → **wait for V2 live** (08-16 08:29) — V2 has now been live one session; (4) st-obdp / GexBot Quant spend past ~Sep 1 → waits for data.

Open on the epic: **Emission And Packet Schema** (st-n0qm.5, Strader, next build), **Tier-1 tape reader** (.6), **Hindsight grading** (.7), **Anchorless Midnight Feeder** (st-kxnv, new today), plus the Phase 4 leftovers named on the epic (LevelSource + providers, FootprintConfig, Null Sequence History, premarket `--out/--register`). COO-owned: health assessors (co-03ojd.7).
