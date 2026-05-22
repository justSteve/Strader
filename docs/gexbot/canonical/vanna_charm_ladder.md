# -Vanna / Charm Ladder — Canonical

**Source:** <https://www.gexbot.com/documentation>, "state" section
**Captured:** 2026-05-20 from `documentation - gexbot.html` saved by Steve
**Status:** verbatim quotation. Do not paraphrase or edit; if vendor updates, replace the relevant block and note in revision log.

---

## Beta caveat

> **-vanna and charm ex are in beta**
>
> Why? Options profile classifies intraday transactions rather than keeping tabs on total open inventory (eventually gexbot will do both). We care about what customers do and how they respond to price. Vanna and charm effects are dealer heavy, so we are still learning best practices when applied to daily classifications. With that caveat in mind, we can get to the good stuff.

## What -vanna and charm exposures measure

> As our metrics page pointed out, both our -vanna and charm ladders indicate the delta impact, in dollar terms, of the collapse in volatility and the passage of time respectively. While -vanna ex estimates the impact of a total collapse (i.e. all options expiring), charm ex estimates the impact per hour. This is why our charm ex. increases exponentially into expiration: the decay rate of OTM options approaches infinity as time approaches zero. While the -vanna ex is more stable, charm ex highlights the relevance of shorter dated options as an estimate of hedging flows into expiry.

## Reading the bars

> In both cases, a bar to the right indicates that customers will get longer (gain deltas) into expiration whereas a bar to the left indicates they will get shorter (lose deltas) into expiration.
>
> Dealer flows are then straightforward — where customers get longer, dealers get shorter. Bars to the right indicate that dealers will get shorter going into expiration, meaning they will be forced to buy to stay neutral. Bars to the left indicate that dealers will get longer into expiration, meaning they will be forced to sell to stay neutral.
>
> Bluntly: bars to the right will be a source of **supportive flows into expiry**, whereas bars to the left will be a source of **passive selling**.
>
> The relevance of these flows, as mentioned above, grows exponentially into expiry — so watch for the last half hour of the trading day.
>
> - **Positive bars:** bullish passive flows into expiry
> - **Negative bars:** bearish passive flows into expiry

## Reading the Ladder

> Let's get more concrete. In general you'll notice that the -vanna/charm of a customer bought options position (regardless of put/call) flips from positive below spot to negative above spot into expiry. Essentially, it forces spot price away from itself.
>
> The -vanna/charm of a customer sold options position (regardless of put/call) flips from negative below spot to positive above spot into expiry! So **large customer sold options positions actually attract price into expiry**. The -vanna/charm ladders give us a way to visualize this dynamic from the convexity ladder in action.

## -Vanna levels dominate gamma at close

> As the day winds to a close, however, **-vanna levels become more powerful than gamma**. Positive -vanna levels act as support from below, and negative -vanna levels act as resistance from above. That means if we enter into a stack of negative -vanna, we are likely to continue progressing downwards. If we enter into a stack of positive -vanna, we are likely to continue progressing upwards.
>
> Keep in mind that the polarity of a -vanna level will flip as spot crosses it, and zeros out when spot is on it. From a theoretical perspective, when spot is at a -vanna level (local zero -vanna), no hedging is needed for a given change in volatility. But as spot peeks slightly above or below, a substantial change is needed, which is what gives these levels their acuity. **Significant levels represent local zeros for the -vanna complex, making them strong pivots.**

---

## Observations derivable from this passage

These are *implications* of the canonical text. Not canonical — targets
for the measurement framework.

1. **Customer-bought options push price away from themselves** (vanna/charm polarity flips through spot). Customer-bought positions are repulsive levels into expiry.

2. **Customer-sold options attract price toward themselves** (opposite polarity pattern). Customer-sold positions are magnet levels into expiry.

3. **Late-day dominance:** -vanna overrides gamma as a price-direction force as expiry approaches. For 0DTE work, our weighting should shift from `major_long_gamma`/`major_short_gamma` reads (early/mid session) to vanna ladder reads (last hour). Mapping to API: `state/vanna_zero` becomes the primary endpoint after 14:00 CT-ish.

4. **Crossing dynamics — vanna polarity flips at the level itself.** This creates the pivot behavior: levels become support from one side and resistance from the other. Significant ones are "local zeros" of -vanna, where the field changes sign — strong reversal candidates.

5. **Charm acceleration is hourly, vanna is total-collapse — different time scales.** Charm dominates the final 30 minutes (per the doc's "watch for the last half hour" framing). Vanna is stable through the day until expiry.

6. **Beta caveat is real.** The vendor explicitly states they are still learning best practices on the daily-classification application of vanna/charm. Our measurement framework should be especially careful about treating this as canonical truth — it's published canonical but vendor-tagged as in-progress.

## Revision log

- 2026-05-22: Initial canonical capture from `documentation - gexbot.html` saved 2026-05-20.
