# Orderflow Doctrine Monitor [st-2n69]

Mechanical event detection over the GexBot capture stream. Replaces
minute-by-minute human screenshot reads (Steve's directive 2026-08-07)
with a machine journal reviewed once at end of day. **Interpretation is
deliberately out of scope**: the monitor names patterns, never
directions. The doctrine reads stay human — this is instrumentation for
the mastery effort, not a signal engine.

## Pieces

| Piece | Path |
|---|---|
| Detector | `scripts/orderflow_monitor.py` |
| Thresholds | `scripts/orderflow_monitor.config.json` (all tuning lives here) |
| Launcher | `scripts/orderflow_monitor_up.sh` (window `of-monitor` in the `steves-desk` tmux session, socket `moocity`) |
| Events journal | `data/derived/orderflow-events/<date>.jsonl` |
| Heartbeat | `/var/moo/state/orderflow-monitor.json` |

Input: `data/corpus/<date>/gexbot.jsonl` (the ~60s poll from
`corpus_poll_gexbot.py`). Live mode tails it; `--replay YYYY-MM-DD`
reruns any archived day — replay is also how thresholds get tuned and
how doctrine studies run without burning session tokens.

## Field mapping (the hard-won part)

The GB panes run at **expiry = latest (0DTE)**, so the pane series are
the `z*` fields, *not* the `o*` (all-expiry) fields:

| Pane | API field | Verified |
|---|---|---|
| convexity orderflow | `cvroflow` | +399.91 print matched the 13:25 brake spike, 2026-08-07 |
| gex orderflow | `gexoflow` | −345.07 print matched the off-axis plunge, 2026-08-07 |
| net convexity | **`zcvr`** (NOT `ocvr`) | zcvr −1372 at 9:09 CT matched the chart; ocvr read +177 at the same moment |
| call/put wall lines | `zero_mcall` / `zero_mput` | matched the 13:28 tooltip (7735/7740) |

`ocvr` diverges completely from the rendered pane — a session read that
quotes `ocvr` as "net convexity" is quoting a different series.
`zcvr`'s daily amplitude is huge (−1,812 to +13,438 $MM on
2026-08-07), which is why the dump/ramp thresholds are in the
thousands.

## Event vocabulary → doctrine

| Event | Doctrine meaning (checklist §4) |
|---|---|
| `CVR_SPIKE_UP` | the **brake** — someone buying volatility (pattern 2) |
| `CVR_SPIKE_DOWN` | options sold — fuel for continuation (pattern 4) |
| `GEX_SPIKE_CALL` / `_PUT` | that side of the book just got expensive |
| `TWO_SIGNAL` | brake + gex spike within 2 pulls — the canonical setup (pattern 3); `trend_pts` gives the 30-min price drift for direction context |
| `NETCVX_DUMP_START/_END`, `NETCVX_RAMP_START/_END` | the vol-mood regime shifts (pattern 1) |
| `NETCVX_VTURN` | sharp rise off the low while still in a dump — on 2026-08-07 this fired at 8:59 CT, **11 minutes before the price low** of the 40-pt reversal |
| `WALL_MOVE`, `SPOT_CROSS`, `INVERSION_ON/OFF` | gamma-box structure: walls migrating, spot crossing a wall, call wall below put wall |

Every event records the threshold that fired it, so a tuning pass can
always reconstruct why something did or didn't emit.

## Operating notes

- Start: `bash scripts/orderflow_monitor_up.sh` each trading morning
  (idempotent: detects a dead monitor behind a leftover window and
  recycles it; verifies the process and heartbeat before reporting
  success). View: `tmux -L moocity attach -t steves-desk`, window
  `of-monitor`.
- Follow mode exits cleanly at midnight Central (day rollover) and on
  30 consecutive loop errors; the morning launcher restarts it onto the
  new day. Mid-day restarts are safe: the journal deduplicates, so
  re-deriving state from byte 0 never duplicates events.
- `--replay` REWRITES that day's journal from scratch — it is the
  canonical way to rebuild a day after a threshold change. Don't replay
  the current day while the follower runs.
- EOD review: read `data/derived/orderflow-events/<date>.jsonl`;
  `WALL_MOVE`/`SPOT_CROSS` are the chatty structural layer — filter
  them out to see the flow story.
- Known limits: the ~75s poll undersamples GB's few-second render, so
  spike extremes between pulls are missed (logged on st-fyey);
  pre-market pulls carry session-start artifacts, so processing is
  clipped to RTH (`runtime.rth_utc`).

## Health semantics (read this before declaring it healthy)

The heartbeat (`/var/moo/state/orderflow-monitor.json`) separates the
two failure domains:

| Signal | Meaning |
|---|---|
| `ts` stale (> ~1 min) | the **monitor** died — relaunch |
| `ts` fresh, `last_pull_ts` frozen during RTH | the **collector** died — the monitor is fine but starving |
| `day` ≠ today during RTH | rollover misfire — relaunch |
| `status: error-loop` | the monitor gave up after repeated errors — read the pane |
