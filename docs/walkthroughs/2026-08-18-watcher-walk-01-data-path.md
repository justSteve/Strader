# Watcher V2 — Walk 1 of 10: the data path, followed live

*Tuesday 2026-08-18, written at 08:31–08:40 CT, ninety seconds after the cash open. Every number on this page was read from the running system while it ran; nothing is hypothetical. This is the first item of the "suggested order" in the walkthrough page (§3): one real trade and one real GexBot row, each followed from the wire to your screen.*

---

## What is running right now

Five processes, all as systemd services on this box.

| Service | What it is, in one sentence |
|---|---|
| `strader-capture` | The Databento collector. It holds an open connection to Databento's live feed for the ES future and appends every trade to a file, `data/corpus/2026-08-18/databento_glbx_es.jsonl`. Its timer started it at 02:50 CT; it stops at 15:05. |
| `strader-gexbot-orderflow-1s` | The "1 Hz leg." Once a second it asks GexBot for its current SPX read (spot, the major gamma levels, dealer-exposure numbers) and appends one row to `gexbot_orderflow_1s.jsonl`. Its timer started it at 08:30:03. |
| `strader-footprint-feed` | The feeder. It reads the trade file as it grows, builds the bars and cells you see, runs the emitters, and pushes the results to the bridge. |
| `strader-orderflow-sentinel` | The sentinel. It reads the 1 Hz file as it grows and watches GexBot's two major gamma levels for price approaching, or the level moving. |
| `strader-drill-bridge` | The bridge — a small web server on port 7788. It holds today's bars, alerts and profile in memory and serves the page. Your browser polls it once a second. It is the only thing the page ever talks to. |

---

## Part A — one trade, wire to screen

### The raw row

The newest line in the trade file when I looked (08:30:47 CT, row 51,941 of today's file):

```json
{"ts_pull_utc": "2026-08-18T13:30:47Z", "stream": "databento_glbx_es",
 "provenance": {"dataset": "GLBX.MDP3", "schema": "trades", "continuous_symbol": "ES.c.0",
                "ts_event": "2026-08-18T13:30:47.254303013+00:00", "source": "live"},
 "data": {"symbol": "ESU6", "instrument_id": 42140870, "price": 7727.25, "size": 1,
          "side": "B", "action": "T", "sequence": 8096931, "flags": null}}
```

Read it as: **one contract of the September ES future (`ESU6`) traded at 7727.25, and the buyer was the aggressor.** `side: "B"` means the trade lifted the offer; `"A"` would mean a seller hit the bid; `"N"` means the exchange could not say. `ts_event` is the exchange's own timestamp to the nanosecond — 08:30:47.254 CT. `sequence` is the exchange's running counter for this instrument, and it is the field Phase 0 of V2 fixed: until Sunday the collector wrote `null` here, so two genuine trades in the same nanosecond looked like duplicates and one was thrown away — about 3.4 % of Friday's volume. Now every row carries its sequence number and de-duplication is exact.

### What the feeder does with it — four things, in this order

**1. De-duplicate and order.** Databento can redeliver a row after a reconnect, and rows can arrive slightly out of order. The feeder keys each trade on `(sequence, ts_event)`, drops repeats, and holds trades back for two seconds (the `reorder_lag`) so late arrivals slot into their proper place before anything downstream sees them.

**2. Feed the volume profile.** Every trade is also added to the anchored profile — the panel on the left of the page — bucketed by price and by which side was the aggressor. This trade adds 1 contract to the *buy* side of the 7727.25 bucket. The profile started this morning at 00:00 with the whole of Friday's cash session pre-loaded (264,402 prints) and has been accreting since; it stood at 271,350 when I looked.

**3. Build the bar.** A bar on this page is **not a time bar**. It closes when 2,000 contracts have traded — so at the open bars close every few seconds and at lunch one can take ten minutes. That is why the columns are the width they are and why the footer of each column shows a duration. This trade landed inside bar 66, which had opened at 08:31:03.6.

**4. When the bar closes, run the emitters and stamp it.** Bar 66 closed at 08:31:11.7 — 2,008 contracts in 8.08 seconds. Here is what the feeder built from it:

```
bar 66      t0 08:31:03.6 CT      t1 08:31:11.7 CT
o/h/l/c     7729.00 / 7731.50 / 7727.25 / 7730.50
volume 2008        delta +274        poc 7730.75        duration 8.08 s

cells (price, sell-side volume, buy-side volume) — top of the bar:
   7731.50      0      7
   7731.25     42     64
   7731.00     12     40
   7730.75    150    133     <- POC: the price where the most volume traded
   7730.50     84     90
```

Each **cell** is one price tick within the bar; the two numbers are how many contracts were *sold into the bid* and how many were *bought at the offer* at that price. Add them all up on both sides and you get the bar's volume. Subtract sells from buys and you get **delta** — +274 here, net aggressive buying in this bar. Those two numbers per cell *are* the footprint chart; everything else on the page is derived from them.

### The emitters that fired on bar 66

Two of them:

- **`DeltaDivergence`** — the bar's price and its delta disagreed in a way the detector flags: price pushing one direction while aggression did not confirm it.
- **`SetupRecognition`** — the recognizer saw price engage one of its anchor levels and logged a "beat" toward a setup. It emits every beat, forming or not, and lets the reader judge.

On the page those are the amber flash on the cells involved and the small marker that stays after the flash. (I will take each emitter apart in the walk item on the feeder; for today, know that they are functions of exactly the cell numbers above and nothing else.)

### The two stamps

The feeder then stamps two pieces of context onto the closed bar.

- **`gex`** — GexBot's most recent 60-second poll before the bar closed: spot 7703.26 SPX, flip 7730.08, regime `neg`, the positive and negative brackets, and which of those levels the bar's range covered.
- **`bs`** — the basis: 21.77 points, meaning ES was trading 21.77 above SPX across the last ten bars. You ruled this morning that the basis is plumbing, not information for you — it exists so GexBot's SPX numbers can be placed on the ES chart, and that is all it does here.

### The push, and the page

The feeder batches closed bars (at most 25, or one second's worth, whichever comes first) and sends `POST /bars` to the bridge, along with the profile and the still-open **developing** bar — at that moment bar 67, opened 08:31:11.7, at 465 contracts and counting. The bridge appends the closed bars to its in-memory list, replaces the profile and developing slots, and answers your browser's next `GET /bars?since=66` with bar 66. The page renders it as a new column at the right edge and — because it arrived fresh while you were watching the tip — flashes the cells the emitters named.

That is the whole path:

```
exchange → Databento → capture file → feeder → bridge → page
```

and no step is more than a few hundred milliseconds behind the one before it.

---

## Part B — one GexBot row, wire to screen

### The raw row

The 1 Hz leg's first row this morning, 08:30:07 CT (trimmed — it carries about forty fields):

```json
{"ts_pull_utc": "2026-08-18T13:30:07Z", "timestamp": 1787059806, "ticker": "SPX",
 "spot": 7703.26, "z_mlgamma": 7654.89, "z_msgamma": 7724.97,
 "zero_mcall": 7760, "zero_mput": 7725, "one_mcall": 7740, "one_mput": 7665,
 "agg_dex": 107.48, "net_dex": 122.68, ... }
```

Three fields matter for what follows: `spot` (SPX cash, 7703.26), `z_mlgamma` (GexBot's **major long gamma** level for the 0DTE chain, 7654.89) and `z_msgamma` (**major short gamma**, 7724.97). These are SPX prices — about 22 points under ES.

### Two readers

- The **feeder's basis estimator** pairs this row with the ES bar closing in the same second — that is where the 21.77 above came from.
- The **sentinel**, whose whole job is: for each of those two levels, keep a rolling ninety-row view of where GexBot has been putting it, and say something when price gets within 2.5 points of it, or the level jumps, or GexBot cannot decide between two candidates.

### What the sentinel said in its first ninety seconds today

This is the actual alerts file, `orderflow_alerts.jsonl`, rewritten as sentences:

| Time (CT) | Kind | What it means |
|---|---|---|
| 08:30:33 | approach | GexBot's major long gamma level was sitting at 7700.36 and SPX (7700.52) had come down to within 0.16 points of it, from above. Rounded to the strike grid: **7700**. |
| 08:30:35 | contested | Two seconds later GexBot's own reads scattered — 45 % of the recent rows put the level near 7790 and 25 % near 7670 — so the sentinel marks the level *contested* rather than pretending it knows where it is. Its health file shows `contested: true` for that level right now. |
| 08:31:35 | approach | Major short gamma at 7710.36, SPX 7711.11, 0.75 points away from above. Strike **7710**. |

The `strike` field is the level rounded to the 5-point grid — the number that means something on an SPX chain.

### The alert's path to the page

Each alert takes the same three steps:

1. It is **appended to `orderflow_alerts.jsonl`** — the durable record; the table above is that file.
2. It is **posted to the bridge's `/alerts` channel**, best-effort (if the bridge is down the file still has it, and the bridge re-reads the file when it restarts).
3. The **page picks it up on its next poll** and draws a horizontal row on the footprint at *strike plus basis* — 7700 + 21.77 ≈ **7721.75 on the ES scale** — from the bar that was open when it fired out to the right edge, with the sentence in the HUD strip. If there were no basis yet the page would say so and draw nothing, rather than draw it 22 points wrong.

Yesterday this loop produced 53 alerts; today it produced three in the first two minutes.

---

## Where to see it

- The live page: `https://mydesk-1.tail89f676.ts.net/footprint/` — or locally `file://wsl.localhost/Zgent/tmp/desk-live-footprint.html`.
- Two things happened in the minute this was written that show the path working end to end: bar 66 closed with two emissions and reached the page, and the sentinel's first approach of the day (7700, major long gamma) is on the page as a row.

**Next in the order — walk 2, the feeder file itself.** Same method: open `scripts/live_footprint_feed.py` and, instead of listing functions, follow bar 66 through the actual lines with the numbers above in hand.
