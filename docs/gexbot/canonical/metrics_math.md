# GEX, DEX & Options Metrics — Canonical (math)

**Source:** <https://www.gexbot.com/metrics>
**Captured:** 2026-05-20 from `gex, dex & options metrics - gexbot.html` saved by Steve
**Status:** verbatim quotation. Do not paraphrase or edit; if vendor updates, replace the relevant block and note in revision log.

This is the mathematical foundation page — what each exposure metric
*actually computes* and why. The indicator descriptions in the other
canonical files reference these formulas; this is where they live.

---

## Open Interest (OI)

> Options are levered and convex. They can be used to express a view on direction and volatility. Due to their capital efficiency and flexibility, they have made up an increasing proportion of market activity. (cf. Cboe)
>
> An option is a contract between a buyer and a seller. It is a convex liability, which responsible participants must hedge. If options control a substantial portion of the notional value transacted in an asset, the obligations they create will influence underlying price. But underlying price influences options prices too! We specialize in capturing and visualizing these feedback loops (such as the infamous "gamma squeeze").
>
> In order to understand the effect of options, we need to know how many there are. Then we can model how option prices will behave to understand how participants will hedge them. It turns out that "how many" is a difficult question.
>
> The most reliable metric of "how many" is **open interest**. After each trading day, the OCC (Options Clearing Corporation) tallies up option orders "to open" and orders "to close." They report the results of the tally before the next trading day. So from one day to the next we know "how many."
>
> In general, opening and closing order data is not available intraday. Additionally, since options spreads are wide, and most transactions take place at the mid-price, it can be difficult to discern from Time & Sales data whether an option has been bought or sold.

## Volume

> An intermediary solution is to use volume in place of open interest. Wherever volume is greater than open interest, we know that new contracts have been added to the mix. That gives us a rough idea of where and how much hedging has to take place.

## Orderflow Classification

> A more advanced workaround is to think like a market-maker. Almost all orders go through a market-maker, and they don't care if your order is to open or to close, they care how it affects inventory. If you buy, they must find a seller to match you with, and if you sell, they must match you with a buyer. So long as they find good matches, overall inventory is balanced. But whenever they can't find a buyer, or can't find a seller, they must change their price. Otherwise, they get stuck with convex inventory — a very risky proposition.
>
> Although we may not be able to know exactly how many contracts are open at a given strike, if we monitor how market-makers react to orders in real time, we can get an idea of whenever demand outpaces supply, and vice versa. If there is an asymmetry (whether to sell or to buy), we take note, and add it to our tally. As the day moves forward, we begin to form a picture of all the **unmatched inventory**, which must be hedged with the underlying. Now, we don't have to assume that participants will be responsible: we know they will.
>
> More simply, the workaround is to learn blackjack and start counting cards. In quant terms, this is called monitoring the volatility surface. (cf. Hau Volatility)

## Delta Exposure (DEX)

> Once we have "how many," how do we know what effect it will have? The simplest solution is **delta (Δ)**. Delta measures how much an option's price will change for every $1 change in the underlying. By convention, delta is positive for calls and negative for puts.
>
> 100 × Δ tells us how many shares (long or short) someone would need in order hedge their option. **100 × Δ × OI** gives us the shares required to hedge open interest at that strike. Because our preference is to know the capital required for this hedge, we multiply this result by the share price.
>
> Performing this operation for all strikes and summing the result gives us the capital required to hedge the entire complex. Finally, call dex and put dex can be netted out for cleaner visualization. Because we've tranlsated [sic] options positions into a capital requirement, we can more easily understand the impact of movement in the underlying: When the underlying increases by 1% the notional hedge will increase by approximately 1% as well. This value is approximate, because deltas are not constant, so read on.

## Gamma Exposure (GEX)

> When we say that options are convex instruments, we are, in part, referring to their **gamma (𝛄)**. Because it is uncertain whether an option will expire in-the-money, the delta of an option fluctuates with time and with the price of the underlying.
>
> If delta is the speed at which an option will gain or lose value with a $1 change in the underlying, gamma is the acceleration.
>
> 100 × 𝛄 × OI tells us how many additional shares would be required to be delta-hedged given a $1 change in the underlying. As with dex, the capital required for these additional shares is given to us by multiplying by the share price. Since we want a metric which is directly proportional to percentage moves in the underlying, we multiply our default $1 change by the share price × 1% (however many dollars a 1% move is).
>
> **Putting it all together: 100 × 𝛄 × OI × share price × share price × 1%.**
>
> Whether your delta is positive or negative, the acceleration of your delta will be the same. Thus, **gamma is positive for all long (bought) options and negative for all short (sold) options.** We view the result ladder-style, on a strike by strike basis. Call gex and put gex can be netted out for cleaner visualization. As with dex, performing this operation for all strikes and summing the result gives us the capital required to hedge the entire complex given a 1% move in the underlying. (cf. Perfiliev)

## Vanna Exposure

> Rather than measuring how delta changes with respect to the price of the underlying, **vanna** measures the rate of change of delta with respect to increases in implied volatility (IV). IV expresses options prices normalized for time to expiration. Instead of referring to price in dollar terms, IV refers to the move in underlying price implied by the option price, independent of direction. By convention this is expressed in terms of an annualized 1 standard deviation move. For example, an at-the-money IV of 20% on an underlying valued at $100 means that the option price implies a range of $20 above or below current prices over the course of the next 365 days. Just like options prices, implied volatilities change as traders' expectations do.

### IV ≈ time-to-expiration intuition

> It can be especially helpful to think about increases and decreases in implied volatility as increases or decreases in time to expiration. The power of vanna becomes clear with a simple thought experiment that leverages this insight: What happens to the probability of expiring ITM, and hence the delta of an option as we give it more (less) time until expiration? You can test your intuition with the table below.
>
> | Call | Put | IV: Moneyness | Delta | Prob. ITM | Delta Change | Vanna |
> |---|---|---|---|---|---|---|
> | | | OTM | + | + | + | |
> | | | ITM | + | - | - | |
>
> You'll notice that adding more time lowers the probability that ITM options will stay ITM, hence lowering the absolute value of their delta. The opposite is the case for OTM options. Giving an OTM option more time increases the probability that it will expire ITM.

### Vanna sign convention

> Now that we have this intuition, vanna follows. As vanna is defined as the change in delta for a 1% increase in IV, we only care about the case of increasing IV and must factor in the sign of the delta (positive for calls and negative for puts). The end result is that, **irrespective of option type, vanna is positive above spot and negative below!**

### Vanna exposure (vex) — and why GexBot inverts the sign

> So what about vanna exposure? For each strike, 100 × vanna × OI would tell us how many shares we would need to hedge a 1 point move up in IV (e.g. from 20% to 21%). Then, to get the capital required for that hedge, we would further multiply by spot price.
>
> **There is an embedded assumption here.** Who is to say that all strike IVs will increase in lockstep? This is seldom the case. In fact, for a given day, we know that 0DTE option IVs will collapse to 0, while 1DTE option IVs will likely increase slightly.
>
> This is where **gexbot breaks with convention**. Because our focus is on short-dated options, we use vanna to model the capital required to hedge IV going to 0: What would the impact be every contract were to expire? Accordingly, we convert the 1 point increase in IV to a total collapse in IV, by **multiplying by each strike's current IV × -1. Our axis therefore reads "-vanna ex".**
>
> This is an approximation, but a consistent one.

### -Vanna ex sign convention (post-inversion)

> Vanna may be positive above spot and negative below for long options, but the opposite is true for short options. Once these are netted out we get a clean visualization of vanna exposure at each strike. Netting out the whole chain for an expiry approximates the capital require to hedge a total collapse in IV at all strikes (**net vex**).
>
> The upside of this method is that the result is simple and intuitive. We can directly compare its magnitude to the dex and gex of a given day, bringing the impact of volatility/time into perspective. The downside of this method is that **the vanna exposure of each expiry is specific to that expiry**. "-vanna ex" for 0DTE refers to the impact of expiry today, whereas "-vanna ex" for 1DTE refers to the impact of expiry tomorrow. This deficiency, however, is a segue to charm.

## Charm Exposure

> Now that vanna exposure is accounted for, the good news is that we can finally take it easy. The analogy between IV and time until expiration is quite strict, meaning that we can understand charm exposure by means of some substitutions and convention changes.
>
> **Charm** is sometimes called **delta decay**, because it describes how delta changes as expiry approaches (in units of deltas per year). As you may recall, this is the opposite of vanna, which describes changes in delta as volatility rises. We can perform the same thought experiment as above to gain an intuitive sense for charm:
>
> | Call | Put | Moneyness | Delta | Time | Prob. ITM | Delta Change | Charm |
> |---|---|---|---|---|---|---|---|
> | | | OTM | + | | - | - | |
> | | | ITM | + | | + | + | |
>
> While the delta of ITM options increases in absolute value as time runs out, the delta of OTM options decreases in absolute value (they expire worthless).
>
> So what about charm exposure? For each strike, 100 × charm × OI tells us how many shares we would need to hedge the delta decay of those contracts for an entire year. In order to get a more intuitive result, we divide by 365 days × 24 hours to get the shares needed **per hour**. Finally, we multiply by spot price to get the capital required for this hedge.
>
> Thus, our charm exposure charts approximate the capital required to hedge current inventory per hour, assuming all other variables are held constant. Once again, short options are netted out against long options for cleaner visualization.
>
> Unlike vanna exposure, **charm can be aggregated**. We can directly compare the impact of 0DTE with 1DTE, and so on, as all are in units of dollars per hour.

## Further Learning (vendor-recommended videos)

> In order to further your understanding of delta, gamma, vanna, and charm exposures, we recommend reviewing the following videos:

The metrics page embeds two YouTube videos. The HTML extraction
mangled their titles to placeholder strings ("Sample output of
devtools-to-video cli tool", "YouTube video player 2") — those are
not the actual video titles, just embed defaults. The real titles,
resolved via WebFetch:

| ID | Title | URL | Synthesis |
|---|---|---|---|
| `zfkOCc2evEk` | Gamma and Vanna exposures | <https://www.youtube.com/watch?v=zfkOCc2evEk> | [`gamma_vanna_video.md`](gamma_vanna_video.md) |
| `-RhSCoElB9Y` | Vanna and Charm Exposure | <https://www.youtube.com/watch?v=-RhSCoElB9Y> | [`vanna_charm_video.md`](vanna_charm_video.md) |

GexBot channel: <https://www.youtube.com/@gexbot>

Both videos were transcribed and synthesized 2026-05-22 (bead `st-9e3`).
Transcripts live in `transcripts/`; the synthesis docs above quote
heavily from the cleaned transcript with documented mistranscription
fixes. Vendor-published video content is part of the canonical surface.

---

## Observations derivable from this passage

These are *implications* of the canonical text. Not canonical — targets
for the measurement framework.

1. **The three escalating "how many" methods are a ladder of confidence:**
   - OI is the gold standard (T+1, OCC tallies)
   - Volume is the intraday proxy when volume > OI
   - Orderflow classification is GexBot's edge — they monitor market-maker reaction to infer unmatched inventory
   Our subscription reaches level 3 (orderflow classification). *Which* tier that is —
   and whether it still carries the orderflow endpoint — is in `config/entitlements.yaml`;
   probe it (`.venv/bin/python3 scripts/entitlements_probe.py`) rather than recalling it.
   This line said "the State tier we subscribe to" for a week after the Quant upgrade [st-g0or].

2. **GEX formula:** `100 × 𝛄 × OI × share_price² × 1%` per strike. Sign is positive for customer-long, negative for customer-short.

3. **Vanna sign convention** (canonical): standard vanna is positive above spot, negative below — *irrespective of put/call*. GexBot inverts this by multiplying by current IV × -1 to model IV-collapse-to-zero rather than +1 IV. The result reads as `-vanna ex`. Cross-referenced from `vanna_charm_ladder.md` "Reading the bars" section.

4. **Charm has a useful aggregation property vanna doesn't:** charm is per-hour, so 0DTE charm + 1DTE charm + N-DTE charm can be summed for total charm impact. Vanna is expiry-specific because it models that-expiry's IV collapse. For our SPX 0DTE late-day work this means: vanna_zero is the right pull; charm can be cross-checked against charm_zero + charm_one if we want aggregate dealer hedging pressure.

5. **The threshold-passing from `community/freddy_methodology.md`** ("net -vanna becomes relevant beyond $800MM in magnitude on SPX in the last hour") is consistent with this math — net vex is the capital required to hedge total IV collapse across the chain, and $800MM × the chain's hedge multiplier translates to a force that exceeds typical dealer-positioning noise.

## Revision log

- 2026-05-22: Initial canonical capture from `gex, dex & options metrics - gexbot.html` saved 2026-05-20. Two embedded YouTube video URLs preserved verbatim; their titles will need to be resolved separately (HTML embed titles are placeholders, not the real titles).
- Source typo "tranlsated" (in DEX section) preserved verbatim with [sic] annotation.
