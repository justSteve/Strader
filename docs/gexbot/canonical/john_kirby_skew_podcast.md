# IV Skew, FOMC, CPI — Canonical (John Kirby, Bear Trap podcast)

**Source:** <https://www.youtube.com/watch?v=ZUxKPGV-6b0>
**Captured:** 2026-05-23
**Speakers:** John Kirby (GexBot principal), Vic (Bear Trap Discord host), awk (chart provider, off-mic)
**Length:** 47:08, ~1294 raw transcript snippets bundled into 96 minute-marked lines
**Transcript:** [`transcripts/staff_promoted_bear_trap_skew_podcast.txt`](transcripts/staff_promoted_bear_trap_skew_podcast.txt) (1-min markers)
**Status:** canonical — by attribution. John Kirby is a GexBot principal (see [`principal_discord.md`](principal_discord.md)) speaking on an external community platform. Treat content as vendor first-party doctrine; treat the source platform (Bear Trap Discord) as venue-only. This is the first podcast in a ~2-hour series; the second half lives in a separate "episode 4" that has not been captured yet.

## The intro promised four topics

Per John's opening: **IV skew theory and reading, FOMC dynamics, CPI dynamics, trading psychology.** How they actually landed:

| Topic | Coverage |
|---|---|
| Skew theory | Heavy — the spine of the podcast |
| CPI worked example (Oct 13 2022) | Heavy — section 4 |
| FOMC worked example (Nov 2 2022) | Heavy — section 5 |
| Trading psychology | Threaded throughout (fomo, traps, the smart-money frame); no standalone section. The dedicated psychology material is presumably in the uncaptured episode 4. |

The structure below follows the four-topic outline rather than the podcast's chronology.

---

## 1. What skew is

> Skew is really just a fancy way of saying we're going to take the implied volatility of every option along the chain and graph them all together. *([01:00]–[02:00])*

Axes (in awk's charts referenced throughout):

- **X axis** = strike price
- **Y axis** = implied volatility at the mid (bid/ask midpoint, back-calculated to IV)
- Horizontal reference lines = historical IV at fixed lookbacks (IV20, IV30, IV60, IV90, HV20, etc.)

One curve per expiry, color-coded across expiries on the same chart. The chart shows shape *across strikes* at one instant — not IV-over-time. It is the same object as Freddy's "skew slide" in [`freddy_methodology.md` §8](../community/freddy_methodology.md), drawn with strike on the vertical and IV on the horizontal; the axes flip but the curves are the same data.

### What lookback to use

> Your understanding of time has to change with the market. If the market's moving really quickly, then your indicator should move a little quicker too. *([03:00])*

In a fast tape (the 2022 bear market, in context), John uses **IV20 / IV30 / HV20**. The longer lookbacks (IV60, IV90) lag too much in a fast regime to be useful as a reference band.

### Why far-dated skew looks "normal"

> Volatility is mean reverting. These really far out skews — they have a tendency to look really similar to each other regardless of the market condition. *([03:00])*

> The further away we are from something, the more it is the case that structural market conditions are going to drive pricing rather than current catalysts. *([04:00])*

Far-dated puts are bought as **portfolio protection**, not as speculative directional bets. That structural-hedge demand is the same in bull and bear regimes, which is why a Dec-30 skew looks much the same when spot is at all-time highs as it does mid-bear-market.

## 2. The default shape: left-leaning normal

> Left-leaning [is the default] because by and large people use options for protection as insurance. When people want to go long, they buy stock — which means there isn't as much demand for options on the upside, because not a lot of people are using options to play the upside. *([05:00])*

The reinforcing flow on the call side:

> When [long shareholders] are doing well, they're selling calls. Which is why even in a bull market you end up with a skew that looks kind of like this, where… when they sell calls out of the money, the skew is going to look even more like [a left-lean]. *([06:00])*

So both directions of "normal" portfolio behavior produce the same shape: long-stock + protective-puts steepens the put side, covered-call selling against winning longs flattens the call side. The result is the canonical left-leaning skew.

### Skew as supply/demand for optionality

> Implied volatility is about how much of a move the options are implying, but really **it's just a measure of option supply versus demand. These are supply-demand curves.** *([08:00])*

> If you look at that 300 strike put right there and it's trading at 37.5 implied vol, what that means is that there's a lot more demand for that put than there is supply, relative to the 325 which is trading at 32.5 implied vol. *([08:00]–[09:00])*

The qualifier — necessary because OTM IV is structurally higher even without flow imbalance:

> It's like a combination of two: we have the market structural conditions which are going to create this type of skew, and then on top of that we have these supply-demand dynamics which are going to modify it by a couple of extra percentage points. *([09:00])*

Two stacked components: a **structural baseline** set by the portfolio-hedging convention, and a **flow modulation** set by current positioning pressure. When John reads "the skew is dislocated," he means the flow component has gotten large relative to the structural baseline.

## 3. The two diagnostic shapes

### 3a. The frown — binary event priced in

> When [a market maker] looks at this, this tells him that market makers know that a move is coming. The vol right here is being priced really high, but the vol on the tails is being priced less, because typically when we have a binary event we get a measured move of some kind. In other words, it's not an unlimited move, and we know when it's going to happen — which actually decreases risk somewhat on the tails. *([16:00]–[17:00])*

A frown (high ATM vol, lower wing vol) is the market's pre-event signature: **move expected, magnitude bounded, timing known.** Bounded magnitude + known timing both compress wing vol relative to ATM.

The decay path after the event is mechanical:

> This frown has to turn into a smile… [or] turn into a smirk. *([17:00]–[18:00])*

Specifically: ATM vol collapses (the event resolves), and one wing rises while the other stays flat — depending on which way price moved. That asymmetric collapse is the canonical "vol crush" pattern around earnings, FOMC, and CPI.

### 3b. The flat skew — no positioning

> If it's flatter [than normal left-lean]… participants are either not really hedged because they're maybe a little unsure, but they're also not really buying a bunch of calls either. So when I see a flat [skew] like that, I'm waiting for something to happen. Nothing's happening here yet. *([20:00])*

A flat skew is **the absence of positioning**, not the presence of any particular thesis. John treats it as a wait state: no participants are paying for protection, no participants are paying for upside, nothing is priced in. Liquidity grabs in either direction become possible because nothing structural pushes back.

### 3c. The bullish-tilt warning — fomo

When the call wing is hot enough that ATM call IV is high relative to ATM put IV at the same expiry — and the same skew shows the wings normalizing while the front-week stays hot — John reads it as **retail fomo at a local top**, not as bullish conviction.

> Look where price is right now on the chart… 386. So folks, in general, this doesn't look like there's funds trying to break us higher to 400 here. It looks like fomo to me — like people are trying to play for that 400. *([24:00]–[25:00])*

The structural tell: if it were institutional accumulation, the further-out expiries would carry the bullish tilt. They don't — only the front-week does. So the bid for calls is short-dated, tactical, and (in John's read) retail.

## 4. Worked example — Oct 7 2022 crash day → Oct 13 CPI reversal

### Oct 7 11:00 AM — mid-drop

Front-week skew is **highly left-leaning**: the ATM-and-below put IV has spiked, the call wing is unchanged. The expiry immediately *after* the front week is comparatively normal — its put IV has come *down* slightly.

> Everybody is currently piling into options for the seventh because we're in the middle of a big drop. So the demand for these guys on the 10th actually goes down, even though for the next day it's going to go up. *([12:00])*

This is the **push-pull** dynamic: when a fast event drives panic demand into the front-week puts, monetization of the next-out expiry's puts can compress that expiry's IV even as the front week explodes.

### The tactical conclusion — don't buy front-week puts on the crash day

> You shouldn't buy puts for the most part on a day like this. If you're going to continue to be bearish, you're overpaying by 15 ball points at least. And you have way less time too… If you're going to play directional puts here, you've got to find the expiry that's cheapest. *([14:00])*

Specifically: buy the *next-week* expiry, or the one after. The IV is materially lower (often below HV20 or IV30 on the reference band), and the time-decay penalty is minimal across one extra week.

**This is the doctrine to remember:** *on a crash day, the cheapest expiry is the play, not the current expiry.* The same logic applies symmetrically to a rip — don't chase front-week calls when call IV is dislocated.

### Oct 13 CPI — frown into the print

Pre-event skew at 6–7 AM on Oct 13: **frown shape on the front-week** (high ATM, lower wings). John reads it correctly as the market pricing a binary, and resists trading the apparent reversal.

> Whenever I see the frowny face like this… [it tells him that] market makers know that a move is coming. *([16:00]–[17:00])*

What actually happened: gap-down on the print, then a violent reversal up. The mechanism, in John's frame:

> They gap it down and then the skew normalizes on that gap down — and that's what pushes us back. Everybody's hedged again or everybody's too far to one side, and then you go higher. Puts need to get way more expensive, calls need to stay around the same, and at-the-money vol needs to come down. That means we get vix suppression, which is exactly what we got. And then that actually enforces call-share buying, which is what pushes us all the way up. *([17:00]–[18:00])*

Three-step cascade: gap-down forces wing vol up → ATM vol collapses → vix suppression → forced call-share buying (the vanna/charm mechanism documented in [`vanna_charm_video.md`](vanna_charm_video.md) §5) → continuation higher. Standard frown-resolution.

## 5. Worked example — Nov 2 2022 FOMC

### Mon Oct 31 → Tue Nov 1 — flat skew

Halloween: skew is flatter than the Oct 5 baseline, similar overall shape but no left-lean. John reads it as positioning vacuum — participants are uncommitted heading into the Wednesday FOMC.

### Mon Oct 31 9:26 AM → 9:47 AM — the bullish-tilt warning fires

In ~20 minutes intraday, the front-week skew shifts dramatically — call IV at the front-week jumps relative to the put IV and relative to the further-out expiries.

> They were hammering [calls] — because even the other skews going way out, just the way the smirk looks compared to what you would normally see in a bear market, it's sort of leaning bullish here. Really a lot. *([22:00]–[23:00])*

John's read at this moment — *before* the FOMC print:

> Your trader mind isn't thinking 'oh they're hammering calls, we got to go up.' That's not what we're thinking. What we're thinking is: what would happen if we were to go down? Puts are getting so cheap right now relative to calls. *([23:00])*

This is the operational use of the skew as a *contrarian* signal at extremes. Cheap puts relative to calls = asymmetric payoff on a downside event. The further-out expiries do not confirm the front-week bullish tilt, so the front-week move is read as fomo, not as positioning.

### Premium-on-premium-on-premium

The cost diagnostic for the front-week call buyer at this moment:

> 45 IV on those calls — and I think at this point we had a VIX that was around 27 or so. So the premium you're paying… IV is generally higher than historical vol. So you're paying a premium upon a premium upon a premium just to buy those calls. *([24:00])*

When VIX is already elevated *and* the front-week IV is elevated *above* VIX, the front-week buyer is paying three stacked premiums. John's frame is that no rational hedge-fund desk pays that stack — only fomo retail does — which is the substrate for the calendar-spread trade he names next.

### The structural calendar trade

> This is an easy calendar trade. You sell this call and you buy this guy [the same strike further out]. It doesn't cost you very much. That's what people do, especially in a liquid index like spy. The smart ones — the ones you don't want to bet against — they're putting the odds in their favor. *([26:00]–[27:00])*

The setup: sell front-week IV at ~45%, buy the same strike in a further expiry at ~25% IV. Net debit is small (because front-week premium offsets most of the back-month cost), the back-month long position retains optionality for weeks, and the entire position profits from vol crush regardless of direction.

### Nov 2 2 PM — into the print

Front-week ATM IV reaches ~120%. The skew across strikes flattens to a near-linear smirk at extreme elevation:

> If you're sitting here with this, you can almost guarantee you're going to make money if you just buy one of the tails… or you could just sell the middle. *([28:00])*

This is the canonical pre-event setup: ATM-vs-wings is so dislocated that **any** of buy-wings / sell-ATM / iron condor variants prints — *if* timing is right around the 2:00 PM / 2:30 PM ET event windows. John's caveat: timing wrong = converse outcome.

### The realization vs implied gap

> The options market was implying a larger move than we actually got — and that's usually what happens. *([29:00])*

> Implied vol is always higher than the historical because everybody's always expecting a bigger move than actually occurs. *([29:00]–[30:00])*

This is the structural reason short-vol strategies have positive expectancy across the long run: realized vol systematically under-delivers vs implied. The IC / sell-the-middle / calendar all monetize this gap. The wing-buy works on individual events but loses the long-run expectancy edge.

### The post-event drift

The Friday after FOMC:

> The liquidation of those puts that they got on FOMC, probably. They just sit there and let the fomo buyers at the FOMC top just get liquidated for the next couple days. Because they were buying calls — not just that day but also high-IV calls on the next couple expiries. *([34:00])*

The post-event drift is fomo-call decay, not directional flow. The fomc-day call buyers paid the triple-premium stack and bleed it back to the calendar-spread sellers over the following sessions.

## 6. Reading the pocket — where price gravitates

This is the integration of skew shape into a trade location:

> The reason I play for [the pocket] is because these zones where you see that implied [vol] is low — this is where price is probably going to go. *([35:00])*

> Price is going to try to go where the IV is lowest. *([35:00])*

Same mechanism as Freddy's "path of least resistance (as vols go to zero)" — the slide-axis-flipped version in [`freddy_methodology.md` §8](../community/freddy_methodology.md). Where IV is *low* across strikes, the protective-bid is absent, dealer hedging carries less weight, and spot drifts there by expiry as IV mechanically decays to zero.

### Constraint: only valid when skew is left-leaning

> Not if the skew is not left-tailed. *([35:00])*

The pocket-as-magnet read applies when the structural baseline is intact (left-leaning normal). On a frown, flat, or call-side-tilted skew, the pocket read is unreliable — the IV minimum doesn't reflect dealer hedging gravity, it reflects the absence of positioning or an event-priced binary.

### Misread John caught himself making

The podcast captures a real-time correction. Pre-FOMC, John had set up an iron condor for "this pocket" based on an expected post-event skew shape:

> I was thinking about how the skew was going to move as the event progressed. *([36:00])*

Vic pushes back; John concedes:

> You can't trade for what you think is going to happen — you can only trade the probability. *([37:00])*

> The only thing you can bet on is that the skew is going to essentially turn into a smirk. *([37:00])*

The lesson: **trade the current skew shape, not the predicted future skew shape.** The mechanical post-event resolution (frown → smirk via ATM vol collapse) is reliable; predicting *where* the post-event spot lands inside the resolved smirk is not.

## 7. The smart-money frame and trading psychology

The psychology material in this first podcast is not delivered as a standalone section. It surfaces as embedded framing while John walks through the worked examples. Themes:

### The hedge-fund frame as a thinking tool

> What I always wanted… is where the fomo is happening. *([24:00])*

> I'm always thinking about: what would a hedge fund manager do? If I had a billion dollars, I'd take half in long shares, a bunch in cash, and then take ten percent of it and just sell calls, buy puts, sell calls, buy puts — because it's essentially free. *([38:00]–[39:00])*

The exercise is to **separate flow you can monetize from flow you can be monetized by**. Front-week premium buyers on event days are providing the bid; calendar-spread sellers and tail-buyers on cheap days are the natural other side. The flow you want to *be* is structural; the flow you want to *fade* is fomo.

### Traps are not adversarial — they are liquidity grabs

> I'm always thinking trap. They're always trying to trap somebody. And it's not really a trap, it's just a liquidity grab. *([32:00])*

Reframing: the move into fomo retail's stops isn't directional intent, it's mechanical liquidity sourcing. This decouples the price location read from the directional intent read — useful for not getting faded by reading flat-skew pre-event moves as conviction.

### The expectancy frame

> If you played for the distribution for the last 40 years, you're killing the market — even if you got blown up once or twice. *([43:00])*

Operational form: wait for 1.5–2 standard-deviation events on a weekly chart (10/20-period lows), then sell puts there, accepting the occasional blow-up because the expectancy across many trades dominates the variance.

### Combining edges across dimensions

> You've got the time and the distribution. You have all these data points that are edges for yourself if you combine them. So this is what I've been doing: combining where open interest is, where the distributions are in the skew, where the distributions are in the volume profile, where the distributions are on the GEX. You start with the edges and work your way in. *([44:00])*

This is John's explicit composition rule for the GexBot stack: skew distribution + GEX profile + volume profile + open interest all describe distributions of positioning across the same strike axis. Where their distributions overlap is the high-conviction zone.

### The closing analogy

> If you're not looking at skew, it's almost like you're going shopping online and you're only looking at the product on the brand-name website — you're not checking Amazon to see if it's cheaper. You're not looking for deals. *([45:00])*

Skew is the deal-finder — it identifies which strikes/expiries are cheap or expensive relative to the structural baseline. Not consulting it leaves the trader paying retail for instruments available wholesale a strike or expiry away.

### The closing mechanical statement

> As price moves lower, it has steeper and steeper [skew] to go down… as you're climbing up, it's going to be harder and harder for participants to pay money for protection. *([46:00]–[47:00])*

The structural baseline self-reinforces in trend: declines steepen the left-tail (more puts bid, more left-lean, more protective demand), advances flatten it (less protective demand, less left-lean). The skew shape *is* a regime indicator.

---

## Cross-references

- **[`convexity_ladder.md`](convexity_ladder.md)** §2 — vol-regime modulation. The convexity ladder reads *positioning* across strikes; skew reads *priced-in vol* across strikes. Both compress to the same operational question (where will dealer hedging pull spot?) via different inputs. John's "price goes to where IV is lowest" rule is the skew-side statement of the convexity ladder's "negative convexity = pinning magnet" rule.
- **[`vanna_charm_video.md`](vanna_charm_video.md)** §5 — the vix-suppression → forced-call-share-buying mechanism that John invokes to explain the Oct 13 CPI reversal is the same constructive-case cascade walked through in that video.
- **[`gamma_vanna_video.md`](gamma_vanna_video.md)** §6 — the constructive case (selling OTM puts → MMs long OTM puts → vanna+gamma hedging supports prices) is the structural mechanism behind John's "structural baseline" component of skew. The portfolio-hedging convention that makes left-lean the default is the *flow* that creates the dealer position the vanna/charm rally needs.
- **[`gex_profile.md`](gex_profile.md)** — the implied order book. John names GEX as one of the four distributions (OI, skew, volume profile, GEX) he composes when locating a trade.
- **[`options_profile.md`](options_profile.md)** — customer-vs-dealer classification. John's "smart money sells calls and buys puts" framing maps onto the customer-side classification; the dealer position is the structural inverse.
- **[`principal_discord.md`](principal_discord.md)** — John Kirby's other vendor-attributed statements, sourced from the GexBot Discord.
- **[`../community/freddy_methodology.md`](../community/freddy_methodology.md) §8** — Freddy's "path of least resistance (as vols go to zero)" slide. This canonical podcast clarifies what Freddy is paraphrasing: the slide's four shapes are the four diagnostic skew shapes John walks through here, with axes flipped. Read Freddy's slide as the static four-state taxonomy; read this podcast as the dynamic walk-through of how the shapes form, resolve, and decay.

## Operational notes (derived, not canonical)

These are *implications* of the podcast, useful for the measurement framework. They are not John's statements.

1. **Skew shape is a regime tag.** Left-lean normal = baseline; frown = pre-binary; flat = positioning vacuum; bullish-tilt front-week-only = fomo. Each of these is a discrete state for session classification in the corpus and should be tagged at the same timestamp as the convexity ladder state and the GEX-profile state.
2. **The cheapest-expiry rule on crash/rip days is a testable doctrine.** Pull historical IV by expiry on session crash/rip days, measure realized return at +1/+2/+5 days for front-week-strike vs next-out-strike puts at matched delta. Hypothesis: next-out-strike beats front-week-strike on a risk-adjusted basis on crash days.
3. **The calendar-spread trade on event days is the dollar-and-cents form of the "smart money frame."** Front-week IV vs back-month IV at the same strike, on event days, is a measurable dislocation that compresses through the event. Worth tracking as a session-level metric in the corpus.
4. **The realized-vs-implied gap is structural alpha for short-vol strategies in this corpus.** John states it explicitly; the magnitude of the gap (implied – realized) over a rolling window is a regime indicator worth maintaining in the metrics layer.
5. **The "trade current skew, not predicted future skew" lesson is generalizable.** The pre-event skew tells you the shape priced in *now*; predicting where spot lands inside the post-event resolved smirk is a separate, harder problem. Don't conflate. This applies to convexity-ladder reads as well.

## Follow-up flags

- **Episode 4 (second half of this series) is not captured.** John signals it contains the remainder of the FOMC/CPI material and the dedicated trading-psychology section. Worth a separate bead to fetch and synthesize when it surfaces.
- **No transcript-noise dictionary needed.** Unlike `gamma_vanna_video.md` and `vanna_charm_video.md`, this transcript is conversational native-English with minimal auto-caption errors. Direct quotes above are verbatim; bracketed insertions are punctuation/grammar repairs only, not term corrections.

## Revision log

- 2026-05-23: Initial canonical capture. Synthesizes the 47-minute first podcast of John Kirby's Bear Trap "skew special" series. Bead `st-lks`.
