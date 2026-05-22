# Options Profile (OP) — Canonical

**Source:** <https://www.gexbot.com/documentation>, "state" section
**Captured:** 2026-05-20 from `documentation - gexbot.html` saved by Steve
**Status:** verbatim quotation. Do not paraphrase or edit; if vendor updates, replace the relevant block and note in revision log.

---

## Description

> Our options profile displays the results of our orderflow-classification engine. Options profile is available for the latest expiry and the following one ("next"). Our classification distinguishes between customer long options and customer short options. We do not distinguish between orders to open and orders to close.
>
> Puts default to purple.
> Calls default to orange.
> Long options extend to the right.
> Short options extend to the left.
>
> The applicable features of gexbot classic (lookback dots, history slider) are included here too, with classified volume data as the backbone.
>
> One feature that differs from classic is the addition of 0DTE volatility skew. The red and green dots on the chart represent the implied volatilities of puts and calls respectively. The skew axis is a secondary x axis which can be found at the top of the chart.

## Reading the OP

> The very first thing to keep in mind is that significant strikes represent areas of concentrated liquidity. As such they represent "stops" on our roadmap. But what about direction?
>
> If customers are long, they are incentivized to exit those positions. If customers are short, they are incentivized to maintain their positions, as theta decay and volatility compression will bleed value out of their short contracts.
>
> For the poker fanatics out there: Holding on to long contracts is -EV (expected value), whereas holding on to short contracts is +EV over the long run. This has a very specific effect:
>
> - **Long options act like walls.** When the price gravitates towards them, holders are likely to liquidate, providing liquidity and stifling movement.
> - **Short options do the opposite.** As the price gravitates towards them, holders will likely need to hedge, taking liquidity out of the market and increasing the likelihood of continuation.

## Volatility regime modulation

> One additional variable is worth mentioning here: volatility.
>
> - As volatility rises, contract prices rise too.
> - As volatility compresses, contract prices fall.
>
> The above holds in a declining volatility environment (which is the most common).
>
> - A rising volatility environment, however, decreases the incentive to exit long options positions, **making walls more vulnerable**.
> - A rising volatility environment does not alter (and may even increase) the incentive to hold on to short options positions. Sellers are being paid more to hold on, as volatility premiums rise.
> - Often, sellers will even add to their short inventory as we approach a short strike. **Thus, in a rising volatility environment, short options are more likely to act as walls.**

---

## Observations derivable from this passage

These are *implications* of the canonical text, included here only to
make the operational handles explicit. The implications are not promoted
to canonical status — they're targets for the measurement framework to
validate against corpus data.

1. **Default-regime model (vol declining/stable):**
   - `major_long_gamma` strike acts as a wall (price stalls into it from approach direction)
   - `major_short_gamma` strike acts as an accelerator/magnet (price continues through, or gets pulled in)

2. **Rising-vol regime modulation:**
   - Walls (`major_long_gamma`) become *vulnerable* — break-through probability rises
   - Short-gamma strikes (`major_short_gamma`) can *invert* to act as walls — sellers add inventory as price approaches

3. **Detecting regime from our existing data:**
   - We pull ATM IV via Schwab's chain on every cycle
   - Comparing ATM IV across consecutive cycles within a session tells us whether vol is rising, stable, or compressing
   - The regime label modulates how to read the GexBot major fields

4. **Pending verification (will resolve via Discord Q on `mini_contracts` columns):**
   - Which `mini_contracts` column corresponds to customer-long quantity at each strike
   - Which column corresponds to customer-short quantity
   - The mapping is required to compute the "long acts as wall vs short acts as accelerator" read at any strike beyond the published `major_*` aggregates

## Revision log

- 2026-05-22: Initial capture from `documentation - gexbot.html` saved 2026-05-20. Promoted from a paraphrased section of `community/methodology_freddy_video.md` to canonical primary source per Steve's direction.
