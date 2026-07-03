# ES Orderflow Signal Layer — Design Research (Q1–Q3)

> Provenance: produced 2026-07-03 by a COO/Fable research subagent for bead **st-l5o**
> (DataBento orderflow signal layer design). This is the research companion to the
> design-of-record spec at `docs/superpowers/specs/2026-07-03-orderflow-signal-layer-design.md`.
> It is also the **learning document** for the orderflow primitives and setup signatures —
> written plain-English-first for that reason. Claims marked *synthesis* are the model's
> construction where practitioner literature is thin; everything else is sourced.

This report answers three design questions for an ES (S&P 500 E-mini futures) orderflow signal layer fed by DataBento Live: trade prints, top-of-book quotes, and OHLCV bars, feeding a discretionary trader's decision-support system. Throughout, I distinguish **established practice** (what orderflow tooling and practitioner literature actually do) from **proposed synthesis** (my own construction where the literature is thin), and I keep the determinism-and-replay requirement front and center.

A note on terms before we start, since the whole report leans on it: an **aggressor** is the party who "crosses the spread" to make a trade happen immediately — a buyer who lifts the current offer, or a seller who hits the current bid. The resting party (whose limit order was sitting in the book) is passive. Almost every orderflow primitive below is built by classifying each print as buyer-aggressive or seller-aggressive and then doing arithmetic on those two buckets. So the single most important data question is: *how do we know which side was the aggressor?* The good news for this system is that we don't have to guess.

---

## Q1 — v1 orderflow primitive set

### The two raw inputs and how aggressor side is determined

Everything in Q1 is built from two DataBento schemas:

- **Trades** — one record per executed trade: price, size, and a `side` flag. DataBento's convention is that `side` encodes the *aggressor*: `Ask` means a **sell-aggressor** (seller initiated, hit the bid), `Bid` means a **buy-aggressor** (buyer initiated, lifted the offer), and `None` where the source did not tag a side ([DataBento Trades schema](https://databento.com/docs/schemas-and-data-formats/trades)).
- **MBP-1** (Market-by-Price, level 1, a.k.a. "top of book" / L1) — best bid and ask price, size, and order count, updated on every top-of-book change ([DataBento MBP-1 schema](https://databento.com/docs/schemas-and-data-formats/mbp-1)). This is what tells you *how much resting size sat at a level* — essential for absorption.

The critical robustness fact: **for CME futures, aggressor side is provided by the exchange, not inferred.** CME's MDP 3.0 Trade Summary carries Tag 5797 `AggressorSide` with values `NoAggressor = 0, Buy = 1, Sell = 2, NoValue = 255`; "an aggressor is defined as any customer order that triggers a trade immediately upon entering the book" ([CME MDP 3.0 Trade Summary wiki](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457418925/MDP+3.0+-+Trade+Summary)). DataBento's `side` on CME trades is sourced from that field. This matters enormously: most retail equity orderflow tools *infer* aggressor with a "tick rule" (compare trade price to the prevailing bid/ask, or to the previous trade) and get it wrong on ~10–20% of prints. On CME you get the exchange's own classification, which makes delta-based primitives far more trustworthy on ES than they are on, say, unconsolidated equities.

One pitfall to bake in from day one: the exchange emits **aggressor-less trades** ("no value present, then there is no aggressor… at Market Open, after a Pre-Open or after a Pause… also occur when the triggering order is a CME Globex-generated implied bid/offer," [CME wiki](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457418925/MDP+3.0+-+Trade+Summary)). These `None`-side prints have real size but no direction. Every delta calculation must decide explicitly whether to drop them, bucket them separately, or split them — silently treating `None` as zero-or-buy will bias your delta at exactly the moments (the open, post-halt) when you most want it clean.

Now the six candidate primitives.

---

### 1. Cumulative Delta (CVD) — *established, v1*

**Plain English.** Delta is the net aggression in a slice of time: (volume that bought aggressively) − (volume that sold aggressively). Cumulative delta is the running total of that from some reset point, drawn as a line. A rising CVD line means aggressive buyers have been net dominant; falling means aggressive sellers. It "compresses all that information into a single, easy-to-read line" showing "whether buying or selling pressure is building over time" ([Bookmap CVD guide](https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy)).

**Computation.** `delta_of_print = +size if side==Bid else −size if side==Ask else 0`. `CVD = Σ delta_of_print` from the reset point. Formally, `CVD = Σ(Buy Volume − Sell Volume)`, where buy volume is size executed as buy-aggressor and sell volume is size executed as sell-aggressor ([Bookmap](https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy)). Because DataBento hands you the exchange's aggressor flag, this is a direct sum with no inference step.

**Pitfalls.**
- **Reset choice is a modeling decision, not a given.** CVD only has meaning relative to where you zeroed it — session open, RTH open, a swing point. Different resets tell different stories; you must fix a convention (e.g., reset at the CME session boundary) and apply it identically in live and replay.
- **The `None`-side prints** (above) leak in exactly at the open if you don't handle them.
- **CVD is confluence, not a standalone trigger.** Practitioner sources stress it "works best as a confluence of events" combined with price structure, not as a signal by itself ([Bookmap](https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy)).
- **Level vs. slope.** The absolute CVD value is arbitrary (depends on reset); what's tradeable is its *behavior* around price events (see divergence, next).

**v1 verdict: yes, foundational.** It is cheap, fully deterministic from the trade log, and it's the substrate for delta divergence and for most of the Q2 signatures.

---

### 2. Delta Divergence — *established, v1 (as a derived read, not a separate feed)*

**Plain English.** Divergence is when price and delta disagree. Price makes a new high but CVD makes a lower high → the up-move is running on *less* aggressive buying than before → buyers may be exhausting. Symmetrically for lows. "Delta divergence occurs when price and delta tell different stories… price is making new highs, but the delta is making lower highs, buyers are getting weaker" ([Finowings](https://www.finowings.com/Trading/order-flow-analysis-footprint-delta)); Bookmap frames the same as bearish/bullish CVD divergence ([Bookmap](https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy)).

**Computation.** Requires a notion of swing highs/lows in price and the CVD value at each. At a new price extreme, compare CVD-at-this-extreme to CVD-at-the-prior-comparable-extreme. Divergence = price extreme is more extreme, CVD extreme is less extreme. The non-obvious part is **defining the pivots deterministically** (e.g., an N-tick or N-bar swing filter) so the same divergences appear in replay.

**Pitfalls.**
- **Pivot definition is the whole ballgame.** "Divergence" is only as reproducible as your swing detector. A discretionary eyeball divergence is not computable; you must commit to a pivot rule.
- **Divergence is early, not precise** — it flags weakening participation, which can persist for a while before (or without) a reversal. It is evidence, not a timer.

**v1 verdict: yes**, but implement it as a *read over the CVD series plus a deterministic pivot detector*, not as a first-class signal. It's the most load-bearing input to `failed_breakdown` and `range_trap` in Q2.

---

### 3. Footprint / Bid-Ask Imbalance — *established, v1-capable but threshold-sensitive*

**Plain English.** A footprint splits each bar's volume by price level *and* by aggressor, so at every price you see "X traded on the bid, Y traded on the ask." An **imbalance** is where one side massively dominates the other at a price — a fingerprint of aggressive one-sided activity. It shows "whether buyers or sellers were more aggressive — information that a standard candlestick chart does not show" ([NinjaTrader](https://ninjatrader.com/futures/blogs/ninjatrader-order-flow/)).

**Computation — and the diagonal subtlety.** Imbalances are compared **diagonally**, not straight across. "A bid is compared with an ask one level higher… compare ask volume at price P to bid volume at P minus one tick for buy imbalances, or bid at P to ask at P plus one tick for sell imbalances" ([ATAS](https://atas.net/atas-possibilities/cluster-charts-footprint/how-to-find-and-trade-imbalance/); [AlgoStorm](https://algostorm.com/footprint-charts/)). The rationale: a resting seller at price P is hit by aggressive sellers, while aggressive buyers lift the offer one tick up at P+1 — so the meaningful comparison is ask-volume@P vs bid-volume@(P−1). The trigger is a **ratio threshold with a volume floor**: "typically a 3x to 4x difference with minimum absolute volume such as 50–200 contracts on ES" ([AlgoStorm](https://algostorm.com/footprint-charts/)); ATAS ships a 150%-of-opposite default ([ATAS](https://atas.net/atas-possibilities/cluster-charts-footprint/how-to-find-and-trade-imbalance/)). A **stacked imbalance** is "three or more consecutive imbalances in the same direction… a strong institutional signature… often defended on retests" ([AlgoStorm](https://algostorm.com/footprint-charts/)).

**Computation from your inputs.** Per price level within a bar, accumulate `ask_vol[price] += size` when `side==Bid` (buy-aggressor lifts the offer at that price) and `bid_vol[price] += size` when `side==Ask`. Then apply the diagonal ratio test. This needs a *bar* (a bucket to accumulate within) — which is the Q3 question — and a fixed tick size (ES = 0.25).

**Pitfalls.**
- **Threshold arbitrariness.** 3× vs 4×, 50 vs 200 contract floor — these are tunable knobs with no canonical value; different settings produce different imbalances. Pick and freeze them, and expose them as config, not magic numbers.
- **Bar-boundary sensitivity.** Where a bar starts/ends changes which prints land in which cell, which changes imbalances. This couples imbalance directly to the Q3 bar model.
- **Requires per-price accumulation** — more state and more compute than CVD.

**v1 verdict: yes, but it is the first primitive that forces a bar model.** Ship it as a footprint-bar-derived feature (Q3), with thresholds as explicit config. Stacked imbalances are the highest-signal, lowest-false-positive variant and are the natural "confirmation above/below the level" evidence in Q2.

---

### 4. Absorption — *established concept, but the most subjective; v1 as a scored read, not a hard trigger*

**Plain English.** Absorption is when a lot of aggressive volume hits a price but **price refuses to move** — big passive limit orders are soaking up the aggression. "The price remains stable despite a strong flow of market orders… large limit orders are soaking up aggressive market orders, potentially signaling an imminent reversal" ([LiteFinance](https://www.litefinance.org/blog/for-beginners/trading-strategies/order-flow-trading-with-footprint-charts/)); "price keeps hitting a level but doesn't break it" ([Metrotrade](https://www.metrotrade.com/order-flow-analysis-explained/)). It is the mechanical heart of a failed breakdown: sellers throw size, someone absorbs it, price holds.

**Computation.** There is no single canonical formula — this is where you build one. The ingredients are all available: at a price level, you have (a) aggressive volume traded there (from Trades + side), (b) resting size at top-of-book before/after (from MBP-1), and (c) the price displacement over the window. A workable operational definition (my synthesis, grounded in the qualitative literature): *absorption = high aggressive volume in one direction at/through a level, with resting size at the level being repeatedly refilled, and net price displacement near zero (or a rejection wick) over the window.* Concretely: large `sell-aggressor volume` at support, MBP-1 bid size at the level staying non-trivial or refilling across successive quote updates, and price low holding within a few ticks.

**Pitfalls.**
- **Subjectivity is real and acknowledged in the literature** — "absorption being subjective" is a standard caveat. "How much volume" and "how little movement" are judgment calls. Any threshold you set is a synthesis, not a standard.
- **Iceberg/hidden liquidity.** The absorbing size may not be visible in MBP-1 top-of-book at all (it can be refilled iceberg orders); you infer it from the *fact that price didn't move despite volume*, which is indirect.
- **Absorption vs. exhaustion vs. just-thin** look similar in the moment and only resolve on what price does next.

**v1 verdict: include, but as a *scored, probabilistic read*, not a binary event.** This aligns with the system's design intent (discretionary decision-support, evidence not gates). Emit an "absorption score" at a level with its component evidence (aggressive volume, price displacement, resting-size behavior) exposed, and let the human weigh it. Do **not** ship a hard "ABSORPTION=true" flag in v1 — the subjectivity guarantees false positives.

---

### 5. Large-Lot / Sweep Detection — *established idea, simplest to compute; v1*

**Plain English.** Two related things. A **large lot** is a single unusually big print (size ≫ typical), a footprint of a size player. A **sweep** is one aggressor clearing multiple price levels in quick succession — lifting several offers (or hitting several bids) near-instantly — signalling urgency. Practitioner glossaries treat both as aggression/urgency tells.

**Computation.**
- *Large lot:* flag prints where `size ≥ threshold` (absolute, e.g. ≥ some contract count on ES) or `size ≥ k × rolling median print size`. Trivial and fully deterministic.
- *Sweep:* detect a run of same-aggressor-side prints within a very short window that walk *through* multiple distinct price levels — e.g. `side` constant, `price` monotonically advancing across ≥ N ticks, all within T milliseconds. On CME, the exchange's Trade Summary aggregates a sweeping aggressor's fills, which helps; the `AggressorSide` and order-level detail make sweeps identifiable ([CME MDP 3.0 Trade Summary Order Level Detail](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457225774/MDP+3.0+-+Trade+Summary+Order+Level+Detail)).

**Pitfalls.**
- **"Large" is instrument- and regime-relative.** A fixed contract threshold ages badly; a rolling-relative threshold is more robust but needs a warm-up window (a determinism concern — the window must be seeded identically in replay).
- **Sweeps need a time window**, which reintroduces wall-clock/timestamp sensitivity (Q3). Use event timestamps from the stream, never wall-clock.
- **Single large lots can be noise** (spreads, rolls, admin trades) — needs light filtering.

**v1 verdict: yes for large-lot (cheap, deterministic); sweep detection is v1-capable but slightly more involved** because of the time-window. Both are strong *confirmation* inputs to Q2 (the "sellers commit" flush, the "buyers step in" reclaim).

---

### 6. Low-Volume Nodes (LVN) / Volume Profile — *established, but a different time-scale; v1 as context, computed on a schedule not per-tick*

**Plain English.** A volume profile rotates volume onto the *price* axis: for each price, how much total volume traded there over a session/range. High-Volume Nodes (HVN) are prices the market accepted and revisited; **Low-Volume Nodes (LVN)** are prices it rejected and moved through fast. "LVNs are formed when the market moves sharply in one direction without spending much time at specific price levels… price tends to move rapidly through LVNs… key zones where price can either rebound (reverse) or break through rapidly" ([Angel One](https://www.angelone.in/knowledge-center/online-share-trading/low-volume-nodes-lvn); [TradingSim](https://www.tradingsim.com/blog/advanced-day-trading-strategies-using-volume-profile)). This is the Dalton/Market-Profile lineage: value areas, POC (point of control = highest-volume price), and the idea that price reverts toward accepted value and reacts at the edges.

**Computation.** Bucket all trade volume by price over a defined window (prior session, prior swing, current developing session). LVNs are local minima in that histogram below some fraction of the POC volume. Fully deterministic given the window and bucket size (ES tick = 0.25, though profiles often bucket coarser).

**Pitfalls.**
- **It's a slower-moving, structural primitive**, not a per-tick event. It defines *where* to watch, not *when* to act. Recompute on a cadence (per completed session/bar), not per trade.
- **Window choice changes the nodes** (prior day vs. prior week vs. developing session) — must be a fixed, named convention.
- **LVN reaction is bidirectional** — price can reject *or* rip through. The node is a location of expected *reaction*, not a directional signal by itself. That's exactly why Q2's `return_to_lvn` needs the other primitives to say which way.

**v1 verdict: yes, but scoped as context/levels, computed on completed-bar cadence.** It supplies the *levels* that `return_to_lvn` (and, alongside prior-day/overnight levels, `failed_breakdown` and `level_reclaim`) react to.

---

### RECOMMENDATION — Q1

**Ship all six, but in two tiers, because they are not the same kind of object.**

**Tier A — deterministic, per-event primitives (the v1 core; build first):**
1. **Cumulative Delta (CVD)** — the spine. Fix a reset convention (CME session boundary) and an explicit `None`-side policy.
2. **Delta divergence** — derived from CVD + a committed swing-pivot rule.
3. **Footprint bid/ask imbalance** (incl. stacked imbalances) — computed on footprint bars (Q3), thresholds as frozen config (start 3×, ES floor ~100 contracts).
4. **Large-lot / sweep** — cheapest confirmation tells; use event timestamps only.

**Tier B — structural context and scored reads (build alongside, treat differently):**
5. **LVN / volume profile** — levels and value-area context, recomputed on completed-bar cadence with a named window convention.
6. **Absorption** — a *score with exposed evidence*, never a boolean in v1.

**Rationale.** The Tier A four are all direct arithmetic over the exchange-classified trade stream, so they are fully replay-deterministic and low-risk. CVD → divergence → imbalance → sweep is also the exact evidence chain the Q2 setups need. **Absorption is deliberately demoted** despite being conceptually central: the literature itself flags it as subjective, and the system's stated philosophy is real-time pattern recognition and evidence-scoring, not binary classification gates — so absorption belongs as a weighted read, not a trigger. LVN is included but correctly framed as slow-moving context, not a signal. The one primitive I would *not* try to make canonical in v1 is a hard absorption flag; everything else is safe to ship.

---

## Q2 — Orderflow signatures for four intraday ES setups

**Framing.** Each setup below is expressed as a *sequence of observable events* in the Q1 primitives. I ground each in practitioner literature where it exists and mark clearly where the event-sequence is **my synthesis**. Consistent with the system's intent, these are **evidence signatures to score**, not binary gates — a setup that hits 4 of 5 expected events is a weaker instance of the same thing, not a non-event.

A cross-cutting principle from auction market theory ties all four together and is worth stating once, because it's the literature's own reduction: *"is the aggressive side being accepted or absorbed? If aggressive buyers push price higher and it keeps moving, they are in control; if they appear but price does not move higher, they are being absorbed"* ([ChartFanatics AMT](https://www.chartfanatics.com/strategies/auction-market-strategy)). Every signature below is a specific instance of "aggression showed up and then failed to be accepted."

---

### 1. `failed_breakdown` (Mancini-style) — *well-grounded*

**The setup (established).** Mancini's Failed Breakdown: a known support (initial low) is undercut with a new low that triggers stops, then price *reclaims* the level and recovers. The practitioner rules: an initial distinct low (prefers a clean candle/wick over a basing structure), an undercut that triggers stops below, a **bottom wick on at least the 15-min chart**, and entry **at least 5 points above the reclaimed low (Mancini cites 8–10 pts as a guideline for variance)**, with the **stop under the fakeout low** ([TilleyTrader — 100 trades of the FBD](https://www.tilleytrader.com/2023/05/11/100-trades-of-the-failed-breakdown-fbd/)). The framing is a smart-money trap: "the first break is only information… the reclaim is the evidence that the break failed… acceptance back above the level is what gives the long idea real weight" ([Whop/Mancini course summary](https://whop.com/pro-education-access/); [Scribd — Mancini FBDs and Acceptance](https://www.scribd.com/document/885947011/Mancini-FBDs-and-Acceptance)).

**Expected orderflow signature (event sequence — synthesis, grounded in the absorption/delta/AMT literature):**
1. **The flush:** price breaks below support with **strongly negative delta** and a burst of **sell-aggressor volume** / possibly a **downside sweep** through the level. (Sellers commit — established that the break is real selling, not drift.)
2. **Absorption at/below the level:** aggressive selling *continues* but **price stops going down** — big prints hit the bid, MBP-1 bid size holds/refills, net displacement flattens into a wick low. This is the "absorbed, not accepted" moment ([ChartFanatics AMT](https://www.chartfanatics.com/strategies/auction-market-strategy); [LiteFinance absorption](https://www.litefinance.org/blog/for-beginners/trading-strategies/order-flow-trading-with-footprint-charts/)).
3. **Delta flips / diverges on the reclaim:** as price reclaims the level, **CVD turns up** and often **positive delta divergence** is visible (price made the lower low, CVD made a higher low — sellers weaker) ([Bookmap CVD divergence](https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy)).
4. **Buy imbalances above the level:** on the recovery, **stacked buy imbalances** print above the reclaimed level, confirming aggressive buyers are now being *accepted* (price moves on their aggression) ([AlgoStorm stacked imbalance](https://algostorm.com/footprint-charts/)).

**Confidence:** The *setup* is well-established (Mancini is the named source of the taxonomy). The *orderflow event sequence* is my synthesis, but it is a tight, mechanical mapping onto absorption + delta-divergence + imbalance, each of which is independently documented. **High confidence.** This is the flagship signature and the one to build first.

---

### 2. `level_reclaim` — *established structurally; signature is synthesis*

**The setup.** Simpler cousin of failed_breakdown: price loses a level, then reclaims and *holds* it. Where failed_breakdown emphasizes the trap/flush, level_reclaim emphasizes the hold. Mancini's "acceptance" concept is the relevant grounding: acceptance is "price tested the level several times and continues to return to it" — reclaim-and-hold is acceptance *above* the reclaimed level ([Scribd — Mancini FBDs and Acceptance](https://www.scribd.com/document/885947011/Mancini-FBDs-and-Acceptance)).

**Expected orderflow signature (synthesis):**
1. **Loss of level** on modest/mixed delta (not necessarily a violent flush — this distinguishes it from failed_breakdown).
2. **No downside follow-through:** delta fails to extend negative below the level; sell-aggressor volume dries up (thin, not absorbed — subtly different from failed_breakdown's heavy-absorbed flush).
3. **Reclaim with positive delta**, CVD turns up through the level.
4. **Hold = repeated small tests from above that don't break back down**, with **buy imbalances defending** on each retest (stacked imbalances acting as the "defended on retests" signature from [AlgoStorm](https://algostorm.com/footprint-charts/)).

**Confidence:** Structure is established; the event sequence is synthesis. **Medium-high.** The key discriminator from failed_breakdown is *flush intensity and absorption* — failed_breakdown has a violent absorbed flush; level_reclaim has a quieter loss and a "held on retests" character. Worth encoding that distinction so they don't collapse into one signal.

---

### 3. `return_to_lvn` — *LVN behavior established; directional signature is synthesis*

**The setup.** Price returns to a low-volume node from a prior session/move and reacts. LVN behavior is documented: price "tends to move rapidly through LVNs… key zones where price can either rebound (reverse) or break through rapidly" ([Angel One](https://www.angelone.in/knowledge-center/online-share-trading/low-volume-nodes-lvn)); the AMT + LVN playbook treats LVNs as decision points where the market either rejects (reverts to value) or accepts (continues) ([TradeZella AMT+LVN](https://www.tradezella.com/strategies/auction-market-strategy)).

**Expected orderflow signature (synthesis — and the literature is explicitly thin on the *orderflow* read of LVN reactions):** the LVN itself is *directionally neutral* — it tells you *where*, the orderflow tells you *which way*. Two branches:

- **Reject branch (fade back toward value):** price reaches the LVN, aggression in the approach direction **stalls** (delta flattens, an **absorption** read appears at the node), then **delta flips** and price accelerates back toward the adjacent HVN/POC. This is the mean-reversion case ([TradingSim value-area reversion](https://www.tradingsim.com/blog/advanced-day-trading-strategies-using-volume-profile)).
- **Accept branch (rip through):** price reaches the LVN and **delta *extends*** in the approach direction with **sweeps** and **stacked imbalances** in the direction of travel — the node offers no resistance, price moves fast (the documented "move rapidly through" behavior).

**Confidence:** LVN existence/location and the reject-or-accept dichotomy are established; the specific orderflow event sequences that *distinguish* the two branches in real time are my synthesis. **Medium** — flagged as proposed. This is the setup where the orderflow layer earns its keep most, because the LVN alone can't tell you which branch you're in; delta-extension-vs-stall-and-flip is the discriminator proposed here.

---

### 4. `range_trap` — *strongly grounded (failed auction)*

**The setup.** Price breaks out of a range, traps the breakout traders, and reverses back inside. This is the auction-theory **failed auction**, which the literature covers well and even calls the highest-conviction reversal: "a breakout generates zero volume follow-through and violently reverses, representing the highest-conviction reversal signal… breakout traders who entered on the poke above VAH now sit at a loss, and their stop-outs fuel the move back toward POC" ([ChartFanatics AMT](https://www.chartfanatics.com/strategies/auction-market-strategy)). Liquidity-grab framing: "price barely pokes above a previous high, triggers breakout traders and buy stops, then slams back inside… trapped longs — perfect fuel for the down move" ([Grizzly Parrot](https://grizzlyparrottrading.com/market-basics/how-liquidity-grabs-set-up-reversals.html)).

**Expected orderflow signature (synthesis, but closely tracking the AMT literature):**
1. **The poke:** price breaks the range edge (VAH/VAL or range high/low), often on a **sweep** taking stops, with an initial delta spike in the breakout direction.
2. **No acceptance / no follow-through volume:** immediately beyond the edge, **volume and delta fail to extend** — "zero volume follow-through" is the literature's exact tell ([ChartFanatics AMT](https://www.chartfanatics.com/strategies/auction-market-strategy)). Aggressive breakout buyers appear but **price doesn't keep going** = absorbed, not accepted.
3. **Delta divergence at the extreme:** new price high, lower/flat CVD high (breakout is unsupported) ([Bookmap](https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy)).
4. **Reversal back inside with opposite-side imbalances:** price re-enters the range, **delta flips**, **stacked imbalances** in the reversal direction as trapped breakout traders stop out and fuel the move toward POC.

**Confidence:** The setup and the "zero follow-through + trapped traders" mechanic are **established**; the mapping to the specific primitive events is synthesis but very close to what the AMT sources describe. **High confidence.** Note the structural symmetry with `failed_breakdown`: both are "aggression pokes past a level, gets absorbed, delta diverges, reversal with opposite imbalances." The difference is *location and direction* — failed_breakdown is a support undercut that reclaims *up*; range_trap is a range-edge breakout (either side) that reverses *back inside*. They can and should share signature-detection machinery.

---

### RECOMMENDATION — Q2

**Build the signatures as a shared, scored evidence engine, not four bespoke detectors.** All four decompose into the same four-beat rhythm — **(1) aggression pushes past a level → (2) it fails to be accepted (absorbed / no follow-through) → (3) delta flips or diverges → (4) reversal confirmed by opposite-side stacked imbalances.** What differs is *the level type* and *the expected direction*:

| Setup | Level type | Break direction | Reversal direction | Grounding |
|---|---|---|---|---|
| `failed_breakdown` | support (prior low) | down (flush) | up (reclaim) | **Established** (Mancini) + synthesis signature |
| `level_reclaim` | any lost level | down (quiet loss) | up (hold) | Structure established; **synthesis** signature |
| `return_to_lvn` | LVN | either | either (reject *or* accept) | LVN established; **synthesis** directional read |
| `range_trap` | range edge / VAH-VAL | either (breakout) | back inside | **Established** (failed auction) + synthesis signature |

**Sequence to build:** `failed_breakdown` and `range_trap` first — both are literature-grounded and share the most machinery. `level_reclaim` is a lower-intensity variant of failed_breakdown (encode the *flush intensity / absorption* discriminator so they don't merge). `return_to_lvn` last and most cautiously — it's the one where the directional orderflow read is genuinely synthesis and the literature is thin, so its two-branch logic is a proposal to validate against live tape, not settled practice.

**Score, don't gate.** Emit each detected setup with its component evidence (which of the four beats fired, and how strongly) so the discretionary trader sees a graded read. A flush-with-absorption-but-no-imbalance-confirmation is a real, weaker `failed_breakdown`, and hiding it behind a binary gate throws away exactly the early information the trader wants.

---

## Q3 — Unit / bar model

The question is what *unit of aggregation* the primitives and signatures compute over. The tension is between **what each model makes visible** and **whether it replays deterministically from an append-only trade log**. Five candidates, then a layered recommendation.

### The five candidates

**A. Per-trade event streaming (event-driven core).** No aggregation — process each Trades/MBP-1 record as it arrives, updating running state (CVD, last price, book).
- *Makes visible:* everything at full resolution — CVD tick-by-tick, sweeps, large lots, exact sequence of events. Nothing is hidden by bucketing.
- *Determinism:* **best.** An append-only trade log replayed in order reproduces state exactly, *provided* you key off event timestamps and sequence numbers in the stream, never wall-clock. This is the gold standard for replay = live.
- *Complexity:* low for running scalars (CVD, large-lot); the state is small. But it doesn't *by itself* give you footprint/imbalance/profile, which need buckets.

**B. Time bars (1s / 1m).** Aggregate by clock interval.
- *Makes visible:* OHLCV, per-bar delta, and (with per-price accumulation) footprint/imbalance within the bar. Familiar, aligns with the OHLCV feed already ingested.
- *Determinism:* **the classic trap.** Bar boundaries are wall-clock; a trade at the millisecond boundary can fall in either bar depending on clock/timestamp handling. Deterministic *only if* you bucket strictly by the stream's event timestamp with a fixed, documented boundary rule (e.g., `[t, t+1s)` half-open, using `ts_event`). Low-volume seconds produce empty/degenerate bars.
- *Complexity:* low–medium.

**C. Volume bars (every N contracts).** Close a bar every N contracts traded.
- *Makes visible:* normalizes for activity — each bar is "equal effort," which sharpens delta and imbalance comparisons (a 500-contract bar in fast tape and one in slow tape are comparable). Good for footprint.
- *Determinism:* **excellent from a trade log** — the boundary is a cumulative-volume threshold, independent of wall-clock. The only ambiguity is a trade that *straddles* the threshold (a 50-lot when 30 remain): you need a fixed rule (don't split / split / whole-trade-into-next). Document it and it's fully reproducible.
- *Complexity:* medium; needs the straddle rule and a defined N (ES-appropriate).

**D. Range bars (every M ticks of price movement).** Close a bar when price travels M ticks.
- *Makes visible:* structure/trend clarity, strips time; each bar is "equal price distance."
- *Determinism:* **most boundary ambiguity of the deterministic family.** Gaps and the exact tick that trips the range create edge cases; different vendors implement range bars differently (whether a bar can exceed M on a gap, how the new bar opens). Reproducible only with a rigorously specified construction rule, and even then it's the fiddliest to get identical across implementations.
- *Complexity:* medium–high (the construction rules are notoriously vendor-divergent).

**E. Footprint bars (per-price bid/ask volume within a bar).** Not a *boundary* model — a *rendering/aggregation* layered on top of one of A–D. Within whatever bar you chose, accumulate bid-vol and ask-vol per price. NinjaTrader's volumetric bars are "supported on time, tick, volume or range charts" ([NinjaTrader](https://ninjatrader.com/trading-platform/free-trading-charts/order-flow-trading/)) — i.e., footprint is orthogonal to the base-bar choice.
- *Makes visible:* **the only model that exposes bid/ask imbalance, stacked imbalances, and per-price absorption** — Q1 primitives #3 and #4 and half the Q2 signatures *require* this.
- *Determinism:* inherits the determinism of its base bar, plus needs a fixed tick bucket (ES 0.25) and the same per-price accumulation rule live and in replay.
- *Complexity:* medium; it's per-price state within each bar.

### What each model makes visible vs. hides

| Primitive / signature | Event stream (A) | Time bars (B) | Volume bars (C) | Range bars (D) | Footprint (E) |
|---|---|---|---|---|---|
| CVD (running) | full-res | per-bar | per-bar | per-bar | yes |
| Delta divergence | yes (needs pivots) | yes | yes (cleaner) | yes | yes |
| Bid/ask imbalance | no — needs buckets | yes | yes (best) | partial | **required** |
| Absorption (per-price) | partial — needs price buckets | partial | yes | partial | **required** |
| Large-lot / sweep | **best** | blurred | blurred | blurred | partial |
| LVN / volume profile | yes (accumulate) | yes | yes | yes | yes |
| Failed-breakdown / range-trap sequences | timing | partial | yes | partial | yes for confirm |

Event stream wins on sweeps/large-lots and exact sequencing; footprint (over a bucket) is *mandatory* for imbalance/absorption; volume bars give the cleanest normalized footprint; time bars are the most familiar but the weakest on determinism and on activity-normalization.

### RECOMMENDATION — Q3

**Layered model: an event-driven deterministic core, with derived footprint bars, and volume bars as the preferred footprint base.**

1. **Event-driven core (A) is the source of truth.** Process the append-only Trades + MBP-1 stream in sequence order, driving all running state (CVD, large-lot/sweep detection, book state, LVN accumulation). Key *everything* off the stream's own `ts_event`/sequence, never wall-clock. This is what guarantees **live == replay**, which is the system's hard requirement. Sweep and large-lot detection live here, at full resolution, because bucketing blurs them.

2. **Derived footprint bars (E) for the per-price primitives.** Imbalance, stacked imbalance, and per-price absorption *cannot* be computed without a per-price bucket, so materialize footprint bars as a deterministic reduction over the event core. Fix the tick bucket at ES 0.25 and a documented per-print accumulation rule.

3. **Use volume bars (C) as the footprint base, not time bars.** Volume bars replay deterministically from the trade log (cumulative-contract threshold, no wall-clock), and they normalize for activity so imbalance thresholds and delta comparisons mean the same thing in fast and slow tape. Specify the straddle rule (whole-trade-into-the-bar-that-crosses is simplest and fully deterministic) and an ES-appropriate N. **Keep 1-minute time bars too**, but only as a familiar display/alignment layer that mirrors the OHLCV feed and the way levels (prior-day, session) are conventionally drawn — not as the computation substrate for imbalance.

4. **Skip range bars for v1.** They carry the most cross-implementation boundary ambiguity for the least unique benefit here; nothing in Q1/Q2 needs them that volume bars don't cover better and more deterministically.

**Determinism checklist to enforce everywhere (this is the load-bearing part):**
- Bucket and order **only** by stream `ts_event` + sequence number; **never** wall-clock, `ts_recv` for ordering, or arrival order.
- Define **tie-breaking** for equal timestamps explicitly (sequence number), since tick-timestamp ties are common on CME.
- Define **boundary rules** as half-open intervals and **straddle rules** for volume/range thresholds, documented in one place.
- Fix the **`None`-aggressor policy**, the **CVD reset point**, the **swing-pivot rule**, the **tick bucket**, and all **imbalance thresholds** as named config constants — replay divergence almost always traces to one of these being implicit.

**Rationale.** The event-driven core satisfies determinism at full resolution and is where the sequence-sensitive primitives (sweeps, the exact ordering inside a failed-breakdown) are honest. Footprint bars are non-negotiable because imbalance/absorption are per-price by definition. Volume bars beat time bars as the footprint base on both axes that matter here — determinism (no wall-clock) and activity-normalization — while a thin 1-minute time layer keeps the human-facing chart familiar and lines up with how the traded levels are drawn.

---

## Sources

- DataBento — [Trades schema](https://databento.com/docs/schemas-and-data-formats/trades), [MBP-1 schema](https://databento.com/docs/schemas-and-data-formats/mbp-1), [schemas overview](https://databento.com/docs/schemas-and-data-formats)
- CME Group — [MDP 3.0 Trade Summary (Tag 5797 AggressorSide)](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457418925/MDP+3.0+-+Trade+Summary), [Trade Summary Order Level Detail](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457225774/MDP+3.0+-+Trade+Summary+Order+Level+Detail)
- Bookmap — [Cumulative Volume Delta guide](https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy)
- LiteFinance — [Order flow trading with footprint charts](https://www.litefinance.org/blog/for-beginners/trading-strategies/order-flow-trading-with-footprint-charts/)
- NinjaTrader — [Footprint charts / order flow](https://ninjatrader.com/futures/blogs/ninjatrader-order-flow/), [Order flow & volumetric bars](https://ninjatrader.com/trading-platform/free-trading-charts/order-flow-trading/)
- ATAS — [How to find and trade imbalance](https://atas.net/atas-possibilities/cluster-charts-footprint/how-to-find-and-trade-imbalance/)
- AlgoStorm — [Footprint charts (diagonal imbalance, thresholds, stacked imbalances)](https://algostorm.com/footprint-charts/)
- Finowings — [Order flow analysis: footprint, delta divergence, imbalance](https://www.finowings.com/Trading/order-flow-analysis-footprint-delta)
- Metrotrade — [Order flow analysis explained (absorption, trapped traders)](https://www.metrotrade.com/order-flow-analysis-explained/)
- TilleyTrader — [100 trades of the Failed Breakdown (FBD rules)](https://www.tilleytrader.com/2023/05/11/100-trades-of-the-failed-breakdown-fbd/)
- Scribd — [Mancini FBDs and Acceptance](https://www.scribd.com/document/885947011/Mancini-FBDs-and-Acceptance); Whop — [Mancini failed-breakdown course summary](https://whop.com/pro-education-access/); Mancini newsletter — [My Trade Methodology (paywalled)](https://tradecompanion.substack.com/p/my-trade-methodology-fundamentals)
- ChartFanatics / TradeZella — [Auction Market Theory + LVN playbook (failed auction, absorbed-vs-accepted)](https://www.chartfanatics.com/strategies/auction-market-strategy), [AMT + LVN strategy](https://www.tradezella.com/strategies/auction-market-strategy)
- Grizzly Parrot — [How liquidity grabs set up reversals (breakout trap)](https://grizzlyparrottrading.com/market-basics/how-liquidity-grabs-set-up-reversals.html)
- Angel One — [Low Volume Nodes (LVN)](https://www.angelone.in/knowledge-center/online-share-trading/low-volume-nodes-lvn); TradingSim — [Volume profile day-trading strategies](https://www.tradingsim.com/blog/advanced-day-trading-strategies-using-volume-profile)

**Two caveats on sourcing.** (1) The DataBento schema pages and the CME wiki are JavaScript-heavy / rate-limited, so the exact field-name quotes above are drawn from search-result excerpts of those official pages rather than a clean full-page fetch — the *facts* (CME Tag 5797 values; DataBento `side` = Ask/Bid/None as aggressor) are consistent across multiple independent results, but confirm exact field spellings against the live schema docs before coding. (2) Mancini's primary methodology is paywalled; the FBD rules cited come from a detailed third-party practitioner writeup (TilleyTrader) and course summaries, which agree on the substance (initial low → undercut/stop-trigger → reclaim ~5–10 pts → wick confirmation → stop under the fakeout low).
