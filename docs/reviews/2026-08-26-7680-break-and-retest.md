# 08-26 — 7,680 Break and Retest, Anatomy

*Strader, written 12:30 CT while the consolidation was still forming. All prices ES unless marked SPX; ES − SPX basis 14.05 at 12:05. Bars are 2,000-lot volume bars; delta is buy-aggressor minus sell-aggressor.* [st-fc0i]

Steve, 12:20 CT: "the tradeable move is past but i think plenty to learn there." This page is the episode laid out in the order the parts moved, with the numbers each surface produced at the time.

**Drill:** `/var/moo/desk/drills/drill-2026-08-26-7680-episode.html` — the day so far, 311 bars. The episode runs 10:59–12:26 CT; scrub to 10:59 and let it play.

## The level

The teal LuxAlgo line at **7,680** on the ES chart. Three things sat on it:

| Source | Level | Note |
|---|---|---|
| Mancini | 7,680 | in today's letter; neighbours 7,673 and 7,691 |
| Prior-session profile | POC **7,682** (24,710 contracts) | stamped by the feeder at 09:37, confidence 0.9 |
| LuxAlgo | 7,680 | the line on the chart |

Not a GEX level. In SPX terms 7,680 ES = 7,666, which sits in the gap between major negative / major short gamma 7,660 (ES ~7,674) and zero gamma 7,671.6 (ES ~7,686). Major positive / major long gamma 7,680 SPX = ES ~7,694 — the 7,694–7,696 box on the chart.

## Timeline

| CT | What the tape did | Numbers |
|---|---|---|
| 10:59–11:35 | **The shelf.** Price sat 7,679.75–7,684 for 35 minutes. | 54,174 contracts, delta −1,230. Thickest ticks 7,681.25–7,682.50 at 3.2–3.6K each. Two-way; nobody won it. |
| 11:28–11:30 | Recognizer: `level_reclaim forming @ 7,680` (flush, then stall). | |
| 11:35–11:46 | **The break.** Thin. | 20,532 contracts through 7,681→7,676, delta −1,354. Only 83–450 contracts per tick passing 7,680.00–7,679.00 — the floor was pulled, sellers didn't pay for it. Sell sweeps 11:37 (212 lots to 7,676.75), 11:43 (104 lots to 7,671.25). |
| 11:37–11:43 | GexBot orderflow into the low: gexoflow −939, −685 (put side). | Canon's local-bottom marker. Net GEX (zgr) collapsed 14,100 (10:00) → 159 (11:39) → **−1,847 at 11:44**. |
| 11:43 | **The low, 7,671.0.** | SPX 7,657.4 — a 2-point poke through the 0DTE major short gamma strike (7,660), then the bounce. Cum delta from the break: −1,284. |
| 11:47 | Recognizer: `level_reclaim confirmed @ 7,673` on opposite delta. | |
| 11:55–12:01 | **The retest.** Buy sweeps 11:56 (289 lots), 11:57 (184, to 7,680.00), 12:00 (113, to 7,680.50). | 17,313 contracts, delta +1,063. Cum delta back to +111 by 12:00 — the break's entire sell aggression was bought back. |
| 11:56:32, 11:57:53, 12:00:55 | GexBot: gexoflow +937, **+1,853 (extreme, > p99 1,378)**, +670 — with positive convexity, i.e. calls being *bought* at the level. | Canon: positive GEX orderflow on SPX "typically marks local tops." The +1,853 print landed at SPX 7,666.06 = ES 7,680 exactly. |
| 11:56, 12:01 | Recognizer: `failed_breakdown confirmed @ 7,673`; `level_reclaim confirmed @ 7,680`. | Both on opposite delta. |
| 12:01–12:04 | First knock-back: 7,681.25 → 7,679.75 on −74, −1. At 7,680.00 the retest traded 1,275 contracts, delta −35 — buyers were met, not overrun. Heaviest retest node 7,678.75 (2,410). | One bar, not a sequence. |
| 12:04:05 | GexBot: **dexoflow +401.8** — eight times the p99 (49), largest directional print of the session, with negative convexity → vendor's leg table says short put. | ~$400MM share-equivalent of puts sold at ES 7,680. One snapshot. |
| 12:06–12:15 | Acceptance above. 7,682.25 → 7,683.25 → 7,685.0 (+370) → 7,686.25 (+300). | Through the shelf's thickest tick (7,682.50) and the prior POC. |
| 12:15 | **Cleared 7,686** (zero gamma in ES terms). | |
| 12:16–12:26 | Consolidation 7,685–7,689 at VWAP **7,687.65**. Bar 12:24: −418 into 7,689. | 7,689–7,690 is a heavy node both days (32K / 55K). |

## What each surface contributed

**Footprint.** The shelf was inventory, not defence: 54K of two-way business with delta near flat. The break through it was on air (a fifth of the volume, per tick, that the shelf held). That combination — heavy shelf, thin break — is what puts trapped longs above a retest. The retest then answered the question the shelf posed: positive delta into 7,681–7,682.50 *produced price* through 7,682.50, so the trapped-long supply either wasn't there or was absorbed. The tell was effort-with-effect on the 12:06–12:15 bars, not the first push at 12:00.

**GexBot orderflow.** Two panes, two directions, at the same price: the GEX-orderflow pane stamped the retest with its local-top signature (extreme call buying at the level) while the DEX pane showed one outsized put seller stepping in. The retest resolved *up*, i.e. with the DEX print and against the GEX-OF top signature. One episode; not a verdict on either pane.

**GexBot state.** 7,680 ES wasn't a GEX level, and price didn't behave as if it was — the structural events were the low at the short-gamma strike (SPX 7,660) and the clearance of zero gamma (ES ~7,686). The measured cell for a bullish reclaim confirm firing 0–10 SPX points *below* the flip is the worst in the retro-gamma-cut study (33%, n=49, not decision-grade); this one cleared the flip within 14 minutes of confirming.

**Net GEX and net convexity tapes.** Net convexity dumped 5,260 (11:00) → 562 (11:54) into the low, the canon's lift-then-dump shape. Net GEX went negative at the low and rebuilt to 4,100+ on the bounce.

**Day positioning.** Calls flat (+145), puts −1,622 and still growing through the bounce (−1,118 at 11:00, −1,368 at 11:30, −1,622 at 12:00). The bounce did not unwind any of the day's put buying.

## Steve's read vs the volume

Steve, 12:14 CT: no order blocks between 7,686 and 7,694, "no structures usually means the next orderblock is a magnet." Volume-at-price for the span (ES, 1-pt buckets):

| | today RTH | prior RTH (08-25) |
|---|---|---|
| 7,694 | 24.9K | 25.1K |
| 7,693 | 20.7K | 27.2K |
| **7,692** | **16.6K** | 35.3K |
| **7,691** | **12.6K** | 41.9K |
| 7,690 | 27.1K | 55.3K |
| 7,689 | 32.0K | 43.2K |
| 7,688 | 24.9K | 47.6K |
| 7,687 | 24.0K | 48.7K |
| 7,686 | 32.9K | **57.7K** |

Order blocks and volume nodes are different structures. On volume, the span is not empty: 7,686 is yesterday's biggest node, 7,689–7,690 is heavy both days, and the thin patch is 7,691–7,692 (the LVN the feeder stamped at 7,691). At 12:26 price was consolidating at the 7,687–7,689 node — the first thing on the volume list, not the order-block magnet. Whether the OB read or the node read wins this one is open as of writing.

## What to watch in the drill

1. 10:59–11:35 — the shelf's delta hovering near zero while volume piles up. Inventory, not defence.
2. 11:35–11:43 — how little volume it took to go through 7,680. Watch the per-tick counts thin out.
3. 11:55–12:01 — three buy sweeps and cum delta clawing back the whole break. Effort.
4. 12:01–12:04 — the first push at 7,681.25 knocked back. One bar. Then 12:06 onward, the bars that actually cleared 7,682.50 — the effect.
5. 12:15–12:26 — the sell at 7,689 (−418) into the heavy node.

Sources: `data/derived/live-parity/2026-08-26.jsonl` (bars, recognizer events), `data/corpus/2026-08-26/databento_glbx_es.jsonl` (volume-at-price, sweeps, VWAP), `data/corpus/2026-08-26/gexbot_orderflow_1s.jsonl` and `gexbot.jsonl` (options panes, state), `docs/measurement/oflow-spike-thresholds-2026-08-11.md` (spike percentiles), `docs/measurement/retro-gamma-cut-2026-08-06.md` (regime cells).
