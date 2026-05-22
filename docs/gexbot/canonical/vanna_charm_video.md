# Vanna and Charm Exposure — Canonical (video)

**Source:** <https://www.youtube.com/watch?v=-RhSCoElB9Y>
**Captured:** 2026-05-22
**Speaker:** unattributed narrator; video hosted on the @gexbot YouTube channel and embedded on GexBot's metrics page
**Length:** 7:38, 233 transcript snippets
**Transcript:** [`transcripts/vanna_and_charm_exposure.txt`](transcripts/vanna_and_charm_exposure.txt) (1-min markers)
**Status:** canonical — vendor-published on `gexbot.com/metrics` as recommended further learning. Treat as immutable until vendor updates.

## Transcript noise

Auto-captioned, same narrator as `gamma_vanna_video.md`. The same mistranscription dictionary applies. Additional artifacts in this video:

| As transcribed | Actual term |
|---|---|
| `vanna`, `vanner`, `banner`, `vena`, `vavana` | vanna |
| `data` | delta (especially common in this video) |
| `doubt to hedge`, `data hedge` | delta hedge |
| `piano of the option` | P/L of the option |
| `shaden`, `shaded blue area` | shaded blue area |
| `looks fire` | expires |
| `carrying buying`, `covering` | covering / buying back |

Direct quotes below use `[bracketed corrections]` where the original wording would mislead.

---

## 1. Recap — delta hedging and gamma

The video opens with a 60-second compressed recap of the previous video. Quoting in full because it sets the framing:

> Buying a call forces a market maker to delta hedge this position by buying stock proportional to a line going perpendicular to the delta of the option. The delta is the slope of the P/L of the option at the current price. The act of delta hedging by the market maker essentially rotates their P/L profile for the option such that the delta is flat at the current price.
>
> As mentioned in a previous video, changes in the price creates gamma exposure for market makers and forces them to dynamically adjust their delta hedge by buying or selling stock proportional to a line going perpendicular to the new delta. *([00:00]–[01:00])*

## 2. The reframing — delta as probability of expiring ITM

This is the conceptual move that makes vanna and charm intuitive:

> However the delta of an option can change independently of [the] price of the underlying. This can be due to changes [in] implied volatility or time, which create vanna and charm exposures for market makers respectively.
>
> To understand vanna and charm it may be easier to **not** think of delta as the current slope of an option's P/L profile, but to instead think of delta as the **probability that an option will go in the money**. Price changes can be modeled to follow certain distributions — most price changes could be small with a few large price changes occurring on the tails, or the distribution could develop in such a way that it widens to include larger price swings on the tails. *([01:00]–[02:00])*

> When thinking of implied volatility and its effect on price changes, one can think of implied volatility as influencing the probability distribution of price changes. **When implied volatility is low, price changes are clustered and typically smaller. As implied volatility increases, the probability distribution widens** and has increased variance or deviation.
>
> Similarly when thinking about the effect of time, **when there is more time until an option expires, there is a higher chance for larger price movements to occur. As an option becomes closer to expiring, the chance of large price swings starts to diminish** and one may expect price changes to start clustering and [the tails] to start narrowing in. *([02:00])*

## 3. Vanna — worked examples

The video walks through four cases. Each is the same mechanism (MM hedges by sizing their stock position proportional to the ITM-probability shaded area), but each combination of long/short × ITM/OTM has a different sign.

### Case A: MM short ITM call

> Market makers with short calls must delta hedge themselves by being long stock. The size of this long stock hedge is proportional to the blue shaded area that is in the money.
>
> - **IV decreases** → chances of the option expiring in the money increases → MM must delta hedge their vanna exposure by being **long more stock** *([02:00]–[03:00])*
> - **IV increases** → chances of the option expiring in the money decreases → MM must delta hedge their vanna exposure by **reducing their long stock exposure** by selling some of it *([03:00])*

Intuition: an ITM option is "expected to be ITM at expiry." Wider distribution (high IV) means the outcome is *less* certain, so the probability mass at "ITM at expiry" decreases. The MM's required hedge shrinks accordingly.

### Case B: MM long OTM call

> Market makers who are long calls must delta hedge themselves by being short stock. The size of the short stock hedge is proportional to the shaded blue area that is in the money.
>
> - **IV increases** → chances of the option expiring in the money increases → MM must delta hedge their vanna exposure by being **short more stock** *([03:00]–[04:00])*
> - **IV decreases** → chances of the option expiring in the money decreases → MM must delta hedge their vanna exposure by **reducing their short stock exposure** by buying or covering some of it back *([04:00])*

Intuition: an OTM option is "not expected to be ITM at expiry." Wider distribution makes the tail outcome more reachable, so ITM probability rises and the MM's short-stock hedge grows.

### The general rule embedded in those cases

For *any* option position, the MM's hedge size is proportional to the option's ITM probability. IV moves the probability mass:

- Towards the middle of the distribution (low IV) → ITM outcome is more certain if the option is ITM, less certain if it's OTM
- Towards the tails (high IV) → opposite

The MM rehedges every time that probability changes. **Vanna exposure = the rate at which delta changes with IV.**

## 4. Charm — the substitution

The video's clean punchline:

> The way market makers delta hedge their charm exposure is essentially identical in principle to the way they delta hedge their vanna exposure. In the same way that implied volatility changes the probability that an option will expire in the money and thus changes the delta of the option, **time until the option expires also changes the probability that an option expires in the money** and can change the delta of an option independent of price movements.
>
> Thus charm exposure is analogous to vanna exposure in that **less time until expiration has the same effect as decreasing implied volatility** by narrowing the probability distribution of price changes, whereas **more time until expiration has the same effect as increasing implied volatility** by widening the probability of price changes. *([04:00]–[05:00])*

So all four cases from section 3 generalize to charm by substituting "time passes" for "IV decreases" and "more time" for "IV increases."

This matches `metrics_math.md`'s charm formula derivation: charm is per-hour delta decay, mechanically the same as a slow IV decrease.

## 5. The combined-mechanism example — supportive markets pre-expiry

> To see the effect that market makers delta hedging vanna and charm exposures can have when combined, take an example of a market where many investors have bought out of the money puts, thus leaving market makers short out of the money puts. Since market makers are short puts they are exposed to potential infinite losses if the price of the underlying goes down, and thus must sell or short the underlying stock to hedge themselves. *([05:00])*

Now the three forces stack:

> - **As time goes by**, provided that there are no large changes in the current price, the passing of time reduces the amount of days until expiry, thus slightly reducing the probability that these puts go in the money. Thus delta hedging charm exposure forces the market maker to **buy back a small amount of stock**.
> - Many reasons could lead to **implied volatility decreasing** — which could be due to structural reasons in the VIX curve, or simply because investors have over-bid for put options in anticipation of a market event. Whatever the reason, when implied volatility decreases this again reduces the probability that these puts go in the money. Thus market makers hedging their vanna exposure forces the market makers to **buy back more stock**.
> - The effect of market makers delta hedging both their vanna and charm exposures by buying stock can push up the price of the underlying. *([05:00]–[06:00])*

The video then notes the third reinforcement:

> This increase in price itself also reduces the probability that these puts will go in the money — which is thus **another way to think of gamma exposure** [: gamma is the change in probability that an option expires in the money according to changes in the underlying price]. Thus market makers must delta hedge their gamma exposure by buying more stock in this situation. These increases in price can help further reduce implied volatility which, when coupled with the simple passing of time and the slow pushing up of prices that all this delta hedging can cause, means that **market makers are effectively supporting the markets constantly until the options expire**. *([06:00]–[07:00])*

**This is the canonical "vanna/charm rally" mechanism.** It does not require new buying or bullish sentiment — it is a forced consequence of MMs being short OTM puts and time/IV/price each independently reducing the ITM probability.

## 6. The expiration cliff

> Once the options expire, however, this constant bidding for stock by market makers is taken out of the market, leaving it potentially vulnerable to large changes in price. *([07:00])*

The same support that lifted prices is mechanical, not directional — when it ends, the market loses a structural bid. This is the canonical justification for "expiry is the reset event" referenced throughout GexBot's docs.

## 7. The operational thesis

> In markets that are dominated by the use of options, knowledge of how market makers must delta hedge their vanna and charm exposures can be taken advantage of by investors to identify the likely effect the market makers will have on prices at particular times and in particular volatility. *([07:00])*

---

## Cross-references

- **`gamma_vanna_video.md`** — companion video. Covers gamma in detail; introduces vanna at the end. This video reframes delta as ITM-probability and develops vanna + charm with worked examples.
- **`metrics_math.md`** — quantitative implementation. The "Vanna Exposure" and "Charm Exposure" sections derive the formulas (`100 × vanna × OI × spot`, charm per-hour) that turn this qualitative model into the ladders.
- **`vanna_charm_ladder.md`** — the visualized exposure ladder that lets traders read where vanna and charm hedging pressure concentrates by strike.
- **`gex_profile.md`** — gamma exposure visualization. Section 1's recap on gamma feeds directly into GEX Profile interpretation.

## Operational notes (derived, not canonical)

These are *implications* of the video, useful for the measurement framework. They are not vendor statements.

1. **The "constant support" effect described in section 5 is the mechanism behind late-day SPX 0DTE pinning.** All three forces (charm, vanna, gamma) reinforce each other and intensify into the close as IV decays toward zero and time-to-expiry shrinks.
2. **The cliff in section 6 is why the 3:55 → 4:00 ET window matters.** Support vanishes the moment options expire; whatever direction the underlying was being pinned away from becomes the path of least resistance for the after-hours session and the next morning's gap.
3. **The video's "MM short OTM put" example is asymmetric to the bullish case** (MM long OTM put, e.g., from sold calls or skewed flow). The same three-force stacking happens in reverse, producing constant *downward* pressure into expiry. The polarity comes from the customer-long-vs-short classification documented in `options_profile.md`.

## Revision log

- 2026-05-22: Initial canonical capture. Auto-captioned transcript pulled via `scripts/fetch_youtube_transcript.py` from video ID `-RhSCoElB9Y`. Transcription-noise dictionary documented above. Bracketed corrections are mechanical fixes, not editorial paraphrasing — original transcript preserved in `transcripts/`.
