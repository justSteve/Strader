# Orderflow View — Canonical

**Source:** <https://www.gexbot.com/docs>, Orderflow sections (anchors
`#orderflow`, `#dexorderflow`, `#gexorderflow`, `#convexityorderflow`,
`#netgex`, `#netconvexity`, `#aggregatedex`, `#netvannacharm`)
**Captured:** 2026-08-06. The docs page is a client-rendered SPA; the prose was
extracted from the site's JS bundle
(`https://www.gexbot.com/static/js/main.bdc369bb.js`, 6,724,015 bytes, sha256
prefix `5a3dd66b1254e705`) and every passage below was verified verbatim against
the raw bundle bytes [st-20nw]. The bundle is content-hashed and will disappear
from the vendor's CDN on their next deploy; an archived copy lives at
`sources/main.bdc369bb.js.gz` as evidence. Formulas appear only in the Spanish edition of
the docs; they are quoted as published, with translation noted.
**Status:** verbatim quotation. Do not paraphrase or edit; if vendor updates,
replace the relevant block and note in revision log.

---

## Orderflow (section opener)

> Orderflow subplots detect changes in overall positioning: Any time an order
> comes through, we measure and report the delta and gamma of that order, and
> whether it is long or short. Orderflow helps to highlight transition points,
> both in terms of market direction and volatility.
>
> In following our options profile, all plots and equations are in terms of
> paper (customer) positioning.

## Dex Orderflow

Formula (Spanish edition): **`Dex Orderflow = (Volumen alcista × DEX) −
(Volumen bajista × DEX)`** — bullish volume × DEX minus bearish volume × DEX.

> Dex orderflow tells us when big orders are coming into the market in terms of
> their directional share-equivalent. It is as simple to read as: "Someone just
> bought/sold this many shares worth of options here".
>
> Significant dex orderflow highlights levels of interest. Large transactions
> tell us that aggressive positions are being established, or that liquidations
> are taking place. Often, a local bottom will be established as an aggressive
> buyer enters the picture. Just as easily, a local bottom can be marked by
> bearish orderflow, as a long is forced to liquidate.

## Gex Orderflow

Formula (Spanish edition): **`GEX Orderflow = (Desequilibrio GEX de calls) −
(Desequilibrio GEX de puts)`** — call GEX imbalance minus put GEX imbalance.

> Gex orderflow is designed to monitor changes in the gex profile. A bar up
> indicates that call gex imbalance has grown (more green is present on the gex
> profile), whereas a bar down indicates that put gex imbalance has grown (more
> red is present on the gex profile).
>
> Practically speaking, gex orderflow will mark high 𝛄 transactions, which are
> riskier and feature greater payoffs. As such it marks high conviction pivots.
> On an index like SPX, which is dominated by short gamma, positive gex
> orderflow (often call selling) typically marks local tops, whereas negative
> gex orderflow marks local bottoms.

## Convexity Orderflow

Formula (Spanish edition): **`Convexity Orderflow = (Orderflow largo × GEX) −
(Orderflow corto × GEX)`** — long orderflow × GEX minus short orderflow × GEX.

> The intended use of convexity orderflow is to cross reference it against dex
> orderflow. A transaction with positive dex but negative convexity is a short
> put. If the same transaction has positive convexity, it must be a long call.
> In this way, one can monitor the optionsprofile without looking at the ladder
> chart.
>
> More generally, convexity orderflow indicates when participantsi [sic] are
> wagering on more/less near-term volatility: Positive convexity means that
> participants are expecting more volatility (buying options). Negative
> convexity means that participants are expecting less volatility (selling
> options). Sell-offs are often marked by consistent positive convexity
> orderflow (as there is demand for volatility). Whereas grinding days and
> squeezes often feature consistently negative convexity orderflow.

## Net Gex

> Net gex condenses the gex profile into a single measure.
>
> When net gex is high and above 0, there are more holders of call 𝛄 than put
> 𝛄. When net gex is low and below 0, there are more holders of put 𝛄 than
> call 𝛄. 𝛄 is a measure of convexity. If it is high, that means there is more
> upside convexity than downside convexity, and vice versa.
>
> Market Implications: If upside convexity is high and increasing (net gex is
> very positive), and bars are relatively equal, a squeeze is likely. If upside
> convexity is high and rising, and a single bar above price predominates, look
> for reversion there. If downside convexity is low and decreasing (net gex is
> very negative), and bars are relatively equal, a selloff is likely. If
> downside convexity is low and decreasing, and a single bar below price
> predominates, look for reversion there.
>
> Reading net gex in tandem with net convexity can be quite powerful. It can
> tell you at a glance whether there is more gamma exposure bought/sold as
> calls or puts.

## Net Convexity

Formula (Spanish edition): **`Net Convexity = GEX total comprado por clientes −
GEX total vendido por clientes`** — total customer-bought GEX minus total
customer-sold GEX.

> Net convexity is a measure of option buying vs. option selling.
>
> Positive (high) net convexity means that participants are expecting more
> near-term volatility than is currently priced into the market. Negative (low)
> net convexity means that participants are expecting less near-term volatility
> than is currently priced into the market.
>
> Due to the inverse correlation between underlying price and implied
> volatility, low convexity is mildly constructive on underlying price. Very
> high net convexity, which indicates high demand for options, usually only
> occurs during times of panic.

## Aggregate Dex

> Aggregate dex tells us how much buying/selling the option market has
> contributed over the course of the day.
>
> Negative call aggdex implies more call deltas sold than bought, and vice
> versa for puts. So, when call aggdex is negative and put aggdex is positive,
> participants have been broadly shorting volatility over the course of the
> day.
>
> In a lower volatility environment, SPX is primarily a short volatility and
> hedging instrument, so we often see positive put aggdex, negative call
> aggdex, and moderately negative net aggdex during uptrends. SPY options tend
> to trade more directionally, making divergences between SPY and SPY aggdex
> into particularly powerful signals. In high volatility environments (VIX
> greater than 20) SPX begins trading like SPY (as in the example to the left).

## Net -Vanna / Charm

> Net -vanna and charm approximate the magnitude of the passive hedging
> pressure generated by transactions so far that day as we progress into
> expiration: When positive, they indicate that customers will gain deltas (get
> longer) as we approach expiry. When negative, they indicate that customers
> will lose deltas (get shorter) as we approach expiry.
>
> Example: Assume that the only positions on our ladder are customer sold OTM
> calls (they are short). As we progress into expiry, the value of those calls
> evaporates, making customers *less short*. In this case, both net charm and
> net -vanna would be positive, indicating that customers will get longer as
> expiry approaches. Dealers will be getting shorter, causing them to buy to
> stay neutral. We would accordingly expect bullish passive flows from dealers
> into expiry. These flows will cease if/when price approaches those short
> calls and they become at-the-money contracts.
>
> Timing and Magnitude: While the above is simple and intuitive, the reality is
> that both timing and magnitude matter. On SPX, net -vanna becomes relevant
> when beyond $800MM in magnitude and during the last hour of the day. When
> above $1000MM in magnitude, the effects become relevant sooner–in the last
> couple of hours. Getting a sense for these thresholds is a matter of some
> discretion, but we've noticed a marked difference between extreme and
> moderate values. Extreme days typically feature extreme intraday reversals as
> traders frontrun the effects of positioning unwinding. In these cases, you'll
> see net -vanna, and net charm in particular, accompany and accelerate in the
> direction of the move.

## Vendor self-caveats (from the docs)

> Options profile classifies intraday transactions rather than keeping tabs on
> total open inventory (eventually gexbot will do both). We care about what
> customers do and how they respond to price. Vanna and charm effects are
> dealer heavy, so we are still learning best practices when applied to daily
> classifications.

---

## Observations derivable from this passage

These are *implications* of the canonical text. Not canonical — targets for the
measurement framework.

1. **Net Convexity's formula is the `zcvr` hypothesis, stated by the vendor.**
   "Total customer-bought GEX − total customer-sold GEX" is exactly the
   summed customer-signed ladder the Phase 2 experiment compares `zcvr`
   against (`../orderflow-intended-read.md` §6.1).
2. **The three Orderflow formulas are all `(long/bull side × greek) − (short/
   bear side × greek)`** — signed flow, greek-weighted. Convexity OF weights by
   GEX (long−short axis); Dex OF weights by DEX (bull−bear volume axis); Gex OF
   differences the call−put imbalance axis. Three axes over one classified
   stream — matching the two-axis discipline in `gex_profile.md` obs. 5 plus a
   delta axis.
3. **The SPX-specific read is directional and falsifiable:** "positive gex
   orderflow (often call selling) typically marks local tops, whereas negative
   gex orderflow marks local bottoms." Testable against the archive
   (`gexoflow` sign vs local extrema).
4. **Convexity OF × Dex OF cross-reference is a leg-inference table** (positive
   dex + negative convexity = short put; positive dex + positive convexity =
   long call) — the vendor's own version of "read both together", sharper than
   Freddy's. Full 4-quadrant table: +dex/+cvx = long call, +dex/−cvx = short
   put, −dex/+cvx = long put, −dex/−cvx = short call (last two derived by
   symmetry — verify before use).
5. **Sell-off vs grind signature:** consistent positive convexity OF marks
   sell-offs; consistent negative convexity OF marks grinding days and
   squeezes. A session-character classifier testable on the archive.
6. **The only hard numbers in the doctrine are the -vanna thresholds** ($800MM
   last hour, $1000MM last couple of hours, SPX) — and they sit in the layer
   the vendor itself flags as least settled ("still learning best practices").
   High-value, low-confidence: verify before any operational use.
7. **"All plots and equations are in terms of paper (customer) positioning"**
   confirms jass's customer-perspective convention doc-side, for every
   Orderflow pane.
8. **VIX > 20 regime switch:** SPX "begins trading like SPY" (directional).
   The aggdex regime table (`principal_discord.md` 2025-07-25) carries a
   vendor-stated validity boundary.

## Revision log

- 2026-08-06: Initial canonical capture, extracted from the site JS bundle
  (SPA; no server-rendered docs exist) and byte-verified [st-20nw].
