# Freddy Sarmiento — GexBot Methodology

**This is a community / secondary source.** The canonical statements
about the GexBot model live in `../canonical/`. Where this document and
canonical disagree, canonical wins. Read the canonical docs first;
this is here to capture how a practitioner applies them, not to redefine
them.

This document is a synthesis of two sources, anchored by the video and
extended by ongoing Discord posts:

1. **Trading with Gamma — Jan 24** (2026-01-24, 55:24) — the original
   community video the GexBot team points to as a good introduction.
2. **Discord #theory-questions** — Freddy's follow-up posts that extend
   the video methodology (re-entry rule, R:R discipline, gamma-shift
   signal, zero-gamma regime line, pivots framing). Each section below
   tags its source. Verbatim quotes archived in [`discord_quotes.md`](discord_quotes.md).

Speaker is **Freddy Sarmiento `[PP]` (Moderator)**, an NQ futures trader
and member of the GexBot Discord. He credits **Jasper** ("Jass") and
**John**, GexBot's principals, as the source of the model he's
applying.

This document is a faithful synthesis, **not** an endorsement or
operational instruction. It exists as a reference so future Strader
sessions have a baseline of "what one experienced practitioner says
GexBot looks like in use," to compare against the corpus we build.

### Vocabulary note — MM-talk is being deprecated

Freddy's video and Discord posts frequently use **market-maker
perspective** language ("MMs short gamma," "MMs forced to hedge," etc.).
This is intuitive for futures traders but isn't the canonical
convention.

In a 2025-02-21 Discord exchange, Jasper explicitly stated GexBot's
convention:

> We don't think in terms of MM — everything is in terms of customer.
> That's what you'll find if you read my docs.
> ([`../canonical/principal_discord.md`](../canonical/principal_discord.md))

He added: "I'm going to ask Fredy to change this language."

What this means for reading this document:
- Freddy's mechanical descriptions of MM hedging behavior (§13 squeeze
  loop, etc.) are correct in substance — MMs DO hedge that way
- The *terminology* he uses (MM long gamma, MM short gamma) is the
  inverse of canonical (customer long gamma, customer short gamma)
- When in doubt, flip to customer perspective: "MM long gamma" =
  customer SHORT gamma = purple/violet bars; "MM short gamma" =
  customer LONG gamma = cyan bars
- The operational substance is identical; the labels are inverted

The canonical operational rule for the gamma ladder, in customer
perspective:

> Pivot at customer long gamma (cyan). Move through customer short
> gamma (purple). That's all you really need.
> (Jasper, [`../canonical/principal_discord.md`](../canonical/principal_discord.md))

## Sources

### Video 1 — "Trading with Gamma - Jan 24"

| | |
|---|---|
| **URL** | <https://www.youtube.com/watch?v=vnb92d3lVFs> |
| **Length** | 55:24, 1092 transcript snippets |
| **Date** | 2025-01-24 |
| **Subject** | A full trade-by-trade review of his Friday Jan 24 NQ session |
| **Transcript** | [`../transcripts/2026-01-24_freddy_trading_with_gamma.txt`](../transcripts/2026-01-24_freddy_trading_with_gamma.txt) |

### Video 2 — "What is Convexity"

| | |
|---|---|
| **URL** | <https://www.youtube.com/watch?v=yTCRHW0eLNE> |
| **Length** | 25:50, 520 transcript snippets |
| **Date** | unknown (post-2025-01-24; references back to Video 1) |
| **Subject** | Definition of convexity (Lamborghini analogy) plus a review of another Friday's NQ session showcasing two pattern types |
| **Transcript** | [`../transcripts/freddy_what_is_convexity.txt`](../transcripts/freddy_what_is_convexity.txt) |

### Video 3 — Freddy's "Understanding the Convexity Ladder" paper

Not a video — a 3-page teaching paper Freddy authored on the Convexity
Ladder and its role in market structure. Covers regime-level reads (the
two vol environments, three trading strategies) that sit above the
trade-by-trade tactics in the two videos. Synthesis in
[`freddy_convexity_paper.md`](freddy_convexity_paper.md). Carries the
same MM-vocabulary deprecation note as below.

### Discord posts

Verbatim archive in [`discord_quotes.md`](discord_quotes.md). Sections
below cite individual posts by date where they extend video material.

### Transcription noise

Auto-captioned, speaker has a noticeable accent. Conceptual content
captures cleanly; jargon is noisy. Common mistranscriptions across
both videos:

| As transcribed | Actual term |
|---|---|
| `GubO`, `Guest boots`, `GP`, `gets boot`, `guas`, `gubo`, `getb` | GexBot |
| `GMA`, `GAMA`, `gama`, `camera` (rare) | gamma |
| `complexity` | convexity |
| `Cella` | seller |
| `tie stops` | tight stops |
| `CES` | customer |
| `Trace`, `tray` | trades / traded |
| `Mason money` | making money |
| `John` (when preceding "24") | Jan (Jan 24) |
| `Delta H`, `Delta new Neal` | delta neutral / delta hedged |
| `Lo` (mid-phrase) | low / little |
| `enq`, `inq`, `in Q`, `D andq` | NQ |
| `Vold surface`, `vol surface` | vol surface |

Every claim below cites a transcript timestamp range and which video.
To verify, search the relevant timestamped txt for the cited minute
marker.

## Confidence flags

Each claim is tagged:

- **HIGH** — transcript captures the assertion clearly and Freddy repeats or demonstrates it
- **MED** — claim is present but transcript noise leaves room for nuance
- **LOW** — terminology is garbled; verify against the GexBot docs or by re-watching before treating as operational truth

## 1. Central rule — trade only on excess gamma, never on negative gamma [HIGH]

*[10:30–14:00]*

The "blue bars" in GexBot's gamma profile = high net convexity / excess
gamma. These mark levels where institutional flow has concentrated. They
are the *only* places to enter.

The areas between those bars — "negative gamma" — are where stops get hit
on noise. Freddy is explicit and repeats it. **Do not enter on negative
gamma.**

One exception: the **maximum negative gamma** strike itself is treated as
a magnet/target, not a no-trade zone — price tends to be pulled toward
it.

### Max negative gamma operates in two modes

Freddy clarified in a later Discord post that the max-negative-gamma
strike isn't only a magnet. It can resolve two ways:

1. **Magnet / mean reversion** (default mode): price gets pulled toward
   the strike, then mean-reverts away. This is the use Freddy puts it
   to most often.
2. **Breakout trigger** (when price crosses through with strength):
   if price actually breaks above (or below) max neg gamma rather than
   reverting, the level flips from magnet to *accelerator*.

Freddy's mechanism for mode 2:

> If the price is strong enough to break through (for example, moving
> from below to above), it can act as a trigger. If there's a positive
> excess of gamma above, my thinking is that whoever placed that
> maximum negative gamma position is now underwater, and market makers
> would need to hedge in the futures market, adding fuel to the move.
> (Discord, see [`discord_quotes.md`](discord_quotes.md))

This is the same gamma-squeeze mechanism as [§13](#13-the-gamma-squeeze-loop-and-who-hedges)
but applied specifically to the max-neg-gamma level: cross it →
positions are underwater → forced hedging accelerates the move →
especially powerful if a positive-excess-gamma magnet sits in the
direction of the break.

### Only the maximum matters

Freddy is explicit that this exception applies *only* to the maximum
negative gamma strike, not to large negative gamma levels in general:

> I only pay attention to maximum negative gamma levels, keeping my
> trading as simple as possible.

Other negative-gamma levels — even visually large ones — remain
no-trade transition zones. The asymmetric treatment of max neg gamma is
operational simplification, not a universal rule about negative gamma.

### Convexity defined

Freddy uses "high net convexity" and "excess gamma" interchangeably. He
gives the definition twice — once in Discord, once in Video 2 — and
makes the equation explicit:

> Convexity is the non-linear relationship between the underlying price
> and the options, measured by gamma.
> (Discord #theory-questions, 2025-01-28)

> If you guys are new trading with gamma and new to the GexBot channel,
> you can think of convexity as another term for gamma exposure. So
> basically convexity is the same as gamma exposure. So when the gamma
> is high… the option's delta changes rapidly for small moves in the
> underlying, leading to a curve, nonlinear relationship between the
> option price and the underlying price.
> (Video 2 "What is Convexity" *[04:30–05:30]*)

**Convexity is the shape; gamma is the measurement.** Same phenomenon,
two words. GexBot uses "convexity" rather than "gex" in their UI to
keep the visceral, non-linear quality of the relationship front-of-mind
(see canonical [`convexity_ladder.md`](../canonical/convexity_ladder.md)).

#### The Lamborghini analogy (Video 2 *[01:30–03:00]*)

Freddy's explanation for newcomers — the cleanest concrete framing in
the methodology:

> Imagine you're driving your nice Lamborghini and you turn 15° to the
> left. In a low convexity environment, you turn your steering wheel a
> little to the left, the car also turns a little — proportionally.
> That's low convexity: you move 15° to the left and the car moves a
> little, proportionally to the left as well.
>
> But when you have high convexity and you move the steering wheel the
> same 15°, this small turn of the wheel suddenly makes the car turn
> sharply. That curve in the response is analogous to high convexity.

The mapping:
- **Steering wheel input** = underlying price change
- **Car response** = option delta change
- **Low convexity** = option's delta moves proportionally to underlying
- **High convexity** = option's delta moves *more than* proportionally

This is why high-convexity strikes are where dealer hedging cascades:
a small move in the underlying forces a *disproportionately large*
rebalance, which itself moves the underlying further — the gamma
squeeze loop ([§13](#13-the-gamma-squeeze-loop-and-who-hedges)).

Quoting Jasper through Freddy: "Convexity is a key concept option
traders understand well... and that convexity is key for us Futures
traders too."

### The binary choice (Discord restatement)

The same Discord post sharpens the video's framing into a binary:

> Two options: trade in between excess of gamma levels, where the
> probability to get into a range, consolidation etc... and hit stop
> losses more often... or wait for the excess of gamma levels, where
> there is an "imbalance" of gamma and convexity.

There is no third option. Trading the between-zone produces stops;
trading the imbalance produces edge. This is the operational form of
the "no-trade zone" derivation in the actionable section below.

## 2. Level-to-level mean reversion [MED — vocabulary unstable]

*[12:00–14:30]*

Freddy maps GexBot's gamma model to classical volume-profile language.
The *operational substance* is consistent across his statements but the
*HVN/LVN labels* he applies are inconsistent. The mechanics are:

- Excess gamma levels = where institutional positioning concentrates → magnets, pivots, targets
- Spaces between = transition zones with no concentration → where price traverses but doesn't settle
- Trade direction: enter near one excess-gamma level, target the next
- "Price trades level to level"

### Vocabulary inconsistency, flagged

In the Jan 24 video *[~14:00]* Freddy explicitly equates max negative
gamma with "the high value node" (HVN). In a later Discord post (see
[`discord_quotes.md`](discord_quotes.md)) he calls positive excess gamma
levels "pivots (LVNs)" because price tends to move away from them.

Both can't be right under classical volume-profile semantics (HVN =
where price spends time, LVN = where it doesn't). Freddy's vocabulary
appears to have shifted across sessions, or the transcript noise on the
Jan 24 passage flipped what he actually said.

**The mapping that's coherent with the canonical model:**
- *In a falling-vol regime* (most common, per canonical
  [`convexity_ladder.md`](../canonical/convexity_ladder.md)): positive
  convexity stalls price → price spends time near the level → behaves
  like an HVN. Negative convexity is transit → behaves like an LVN.
- *In a rising-vol regime*: polarity flips — positive convexity passes
  through (LVN-like), negative convexity stalls (HVN-like).

So the HVN/LVN mapping is **vol-regime-dependent**, not a fixed
property of positive vs negative gamma. Freddy's vocabulary inconsistency
likely reflects whichever regime he was looking at in each session.
Don't carry the labels as universal; carry the operational substance
(trade between levels, target the next level).

### Operational substance (stable across statements)

His framing — "price trades level to level" — is the durable claim. The
trade is the move from one excess-gamma level to the next. What changes
session to session is whether the next level acts as a wall (stall and
revert) or a magnet that gets passed through, and that's governed by
the vol regime, not the volume-profile vocabulary.

## 3. Entry mechanics — gamma cross confirmation [HIGH]

*[28:00–31:00]* and *[38:30–40:00]* (failure-case demo)

Concrete entry rule:

1. Identify the excess gamma level you want to act on
2. **Wait for price to actually trade through it** — a clean cross, not a touch
3. Enter in the direction of the cross
4. Stop loss = the OTHER side of the crossed level (very tight; example: 10–12 NQ points)
5. Target = the *next* excess gamma level in the trade direction
6. **If stopped out, re-enter when price re-crosses the level in your bias direction** — getting stopped does not invalidate the read, only the timing

Result: tight stops + larger targets, opposite of conventional "futures
need wide stops" advice. Discipline produces the asymmetry.

### Exit discipline (Discord 2025-01-27)

> Moves that could give me more than 1-3 ratios, take profits in 50% or
> more and leave a runner.

(Freddy Sarmiento, Discord #theory-questions, 2025-01-27 10:43 AM)

Three concrete numbers: target R:R ≥ 1:3 (minimum). Scale 50% off at
the first major level reached. Leave the remainder as a runner to the
next level. Freddy frames this as "not home runs, but moves that could
give me more than 1-3 ratios" — explicitly anti-greedy.

**Re-entry rule source:** Step 6 is not in the video itself — it comes
from Freddy's follow-up Discord post the day after, quoting Jasper:

> Jass emphasis on entering on the high net convexity, tight SL if price
> breaks that level against you but entering again of price moves on
> your bias.

(Freddy Sarmiento [PP], Discord #theory-questions, 2025-01-25 12:23 PM —
see [`discord_quotes.md`](discord_quotes.md))

The rule changes the win/loss math materially: without it, "tight SL"
means most setups end as small losses. With re-entry, the structure
becomes "many small losses + occasional larger wins on the trade that
ran" — which is what makes the algorithmic profile work and is why
Freddy frames discipline as the source of the asymmetry.

## 4. The discipline failure he documents [HIGH]

*[38:00–41:30]*

On his Friday second trade, Freddy entered SHORT *before* price actually
crossed the gamma level — he got excited about confirming his bearish
bias, front-ran his own rule. The market made one more higher-high and
stopped him out, then went where he expected. He calls this out as the
lesson of the video.

**Discipline: don't front-run your own cross trigger.** The cross is the
trigger, not the bias.

## 5. Confluence requirement — gamma alone is not enough [HIGH]

*[20:00–25:00]*

Freddy independently marks levels from price action *before* looking at
gamma:

- Multiple prior days' support/resistance (looking for recurring levels that flip role across days)
- Previous-day high and low (daily chart)
- **Overnight session high and low** — repeatedly emphasized
- Levels that have served as resistance → support → resistance across sessions

Then he overlays GexBot's excess gamma levels. **Confluence between the
two sets of levels = high-probability trade.** Gamma without technical
confluence is a skip.

## 6. Directional bias from orderflow classification — Freddy's application

*[31:00–34:30]*

**Canonical source: `../canonical/options_profile.md`.** The bias logic
itself is GexBot's published model (customer-long = wall, customer-short
= accelerator, driven by EV asymmetry between long and short option
positions). Freddy is *applying* the canonical rule, not stating it.
Where this section's table and the canonical text disagree, canonical
wins.

Freddy's practical table for reading the Options Profile at each strike:

| Pattern at a strike | Bias (per Freddy's narration) |
|---|---|
| Selling of calls (customer SELL-CALL excess) | Bearish — expect downside follow-through |
| Buying of calls (customer BUY-CALL excess) | Bullish |
| Selling of puts (customer SELL-PUT excess) | Bullish |
| Buying of puts (customer BUY-PUT excess) | Bearish |
| **Buying calls + selling puts at same strike** | Double-bullish support |
| **Selling calls + buying puts at same strike** | Double-bearish resistance |

His Friday short setup used exactly this: max gamma resistance above
spot + the negative gamma above came from sold calls (bearish) + GexBot
docs explicitly call high gamma nodes "targets" → cross below = short.

**Important nuance not covered by Freddy:** the canonical docs (see
`../canonical/options_profile.md`) state that this bias logic is the
*default-vol-regime* behavior. In a **rising volatility regime**, walls
become vulnerable and short-side strikes can actually *invert* to act as
walls (sellers add to inventory rather than hedging out). Freddy does
not address this regime modulation in the video. The canonical text
governs in rising-vol sessions; this table only applies cleanly under
declining or stable vol.

## 7. Instrument selection — SPX big-picture, SPY directional, never QQQ [HIGH]

*[15:00–17:00]* + Discord 2025-01-27

In the video Freddy explains the QQQ avoidance:

- QQQ contracts: $50–$400 within first standard deviation → retail-scale → flow is muddied by small participants
- NDX contracts: $1,600–$116,000 within first standard deviation → institutional-scale → flow reflects sophisticated positioning

His Discord follow-up nuances the SPX/SPY mapping in a way the video
doesn't:

> I don't look QQQ at all, instead I look at SPX for a bigger picture
> and SPY to confirm directional moves. I used to trade ES by looking at
> SPY, simply because SPX is mainly used for institutions to hedge,
> while SPY is directional… I believe both, retails and institutions
> use SPY; if you have a look the documentation in gexbot, they mention
> something similar for gamma in SPY.

(Discord #theory-questions, 2025-01-27 10:43 AM)

**Operational pattern:** SPX is the *positioning* read (where
institutions have placed hedges). SPY is the *direction confirmation*
read (where actual buying/selling pressure resolves). Use SPX gamma
levels to define where to act; use SPY behavior at those levels to
confirm direction. QQQ is excluded entirely.

This is a meaningful correction to the simple "SPX = institutional, SPY
= retail" framing. Both audiences trade SPY actively; what makes SPX
distinctively institutional is the *hedging* use case, not the
participant mix. The GexBot docs reference Freddy mentions for this is
worth a follow-up search.

## 8. Volatility skew/smile shape read [HIGH — slide recovered]

*[17:30–19:30]*

Freddy is reading off a four-panel slide titled **"path of least
resistance (as vols go to zero, i.e. expire)"**. Slide image:
[`images/freddy_skew_slide.jpg`](images/freddy_skew_slide.jpg).

### Axes (critical — easy to misread)

The chart is **not** a price-over-time chart. Both axes are state at one
moment:

- **Vertical axis = strike price** (high strikes at top, low strikes at bottom)
- **Horizontal axis = implied volatility level** (high IV to the right, low IV to the left)
- **Spot price** = the horizontal dashed line crossing the middle
- **Green dashed curve** = call vols (the IV of every call strike, connected)
- **Red dashed curve** = put vols
- **Yellow** = the implied direction of the "ball" (where price gets pulled)

A naive left-to-right text-reading of slope direction will invert the
interpretation. The slope is telling you *where the wall is*, not which
way price has been going.

### The four shapes

| Panel | Curve shape | Above-spot IV | Below-spot IV | Path of least resistance |
|---|---|---|---|---|
| Top-left | Slopes top-left → bottom-right | Low (cheap calls, no wall) | High (expensive puts, wall) | **Up easy** |
| Top-middle | Bowl / smile (curves bow outward) | High (wall) | High (wall) | **Stuck in middle** (range) |
| Top-right | Slopes top-right → bottom-left | High (expensive calls, wall) | Low (cheap puts, no wall) | **Down easy** |
| Bottom | Vertical (both curves parallel to spot) | Equal | Equal | **No imbalance** — can move either way |

The bottom panel is Freddy's Friday case ("no hills, no valleys, no
imbalance present"), which is why he kept emphasizing that price could
"easily go up or easily go down" that session.

### The mechanism

The slide's subtitle — "as vols go to zero, i.e. expire" — is the key.
The shape predicts where spot will be drawn *by expiry*, not the next
tick. As time decays, IV mechanically goes to zero. Strikes with the
*most* IV today carry the most positioning weight; as that premium burns
off, dealer hedging pulls price *away from* the high-IV walls and
*toward* the low-IV side. So a wall isn't a hard barrier — it's a
gravity well to be pushed away from.

### Relationship to the canonical regime modulation

The canonical docs (`../canonical/options_profile.md` "Volatility regime
modulation") cover a distinct concept: how *rising vs falling* IV (vol
*trajectory*) modulates wall-vs-accelerator behavior. The slide here
covers skew *shape* at one instant. The two are independent inputs to
the same trading decision and should not be conflated.

## 9. Time-compression at retested levels (non-gamma input) [HIGH]

*[42:00–47:00]*

Freddy credits this to "a very good Futures Trader" he learned market
structure from — not GexBot itself. The pattern:

When price retests a level multiple times:

1. Track the *time* between successive tests
2. If the time is *compressing* (each retest is faster than the last) AND making lower highs into resistance (or higher lows into support), the defenders are getting weaker
3. Combine with gamma read at the level for stronger entry conviction

His Friday short setup used this: three tests of the overnight high, each
faster than the last, with declining highs each time → high-probability
breakdown coming → he just waited for the gamma cross to enter.

## 10. Bias toward algorithmic / rule-based execution [HIGH]

*[01:18–01:35]* and throughout, + Discord 2025-01-29

Freddy frames GexBot as making futures trading "algorithmic in fashion."
He emphasizes:

- Tight stops + bigger targets (opposite of conventional futures advice)
- Rules-based entries (the cross trigger)
- No discretionary entries inside negative gamma
- The model is what makes the trade, not the trader's instinct

Not "automate the execution" — but "follow the rules without
discretion."

### Mental model — "gamma levels are pivots"

Freddy's Discord one-liner that compresses the methodology:

> Think of this gamma levels as pivots, where you put a tight SL and
> look for a good move in your favour. The difference with other
> methodologies / technical analysis, etc, is that here, we see what
> really moves the market, institutions interacting with the market, in
> specific levels with volumes that create an impact.

(Discord #theory-questions, 2025-01-29 7:05 AM)

Two takeaways: (1) *pivots* is the right word — levels around which
risk is defined and sentiment turns. (2) The differentiator from
classical TA is causal, not statistical: TA shows pattern recurrence,
gamma shows the *institutional footprint that produces the pattern*.
Gamma isn't "another indicator" — it's the upstream cause.

## 11. Gamma-profile shift as the sentiment signal [Discord-sourced]

*Discord #theory-questions, 2025-01-27 10:43 AM*

The video framing is "trade between gamma levels in the direction the
profile suggests." The Discord clarification adds the regime-change
signal: when GexBot's computation of the *max* gamma level itself
relocates, that is the sentiment change — not the price action that
follows it.

Freddy's worked example from Jan 27:

> NQ rallies, I was long when the market opened, gamma confirmed my
> view, then I had a gamma target (max gamma excess at 21,606 when NQ
> was at 21,332). Then what happened? we hit Max negative gamma at
> 21,417 (I took profits 50%, left a runner) and the large top side
> target — Max gamma at 21,606 — shifted to 21,051. Is that a shift in
> sentiment? 100% yes… so took small profits on my last 50% and gamma
> level at 21,203 confirmed the downtrend.

**Mechanics:** GexBot recomputes the max gamma strike continuously from
the underlying flow. When the strike relocates from above-spot (21,606)
to below-spot (21,051), it's because positioning has flipped — dealer
obligations have moved from "defend the upside" to "defend the
downside." Treating this recomputation as a directional signal (rather
than as noise in the indicator) is the operational rule.

**Decision protocol from the example:**

1. Initial setup: max gamma above, trade long toward it
2. Take 50% profit at the next gamma level reached (here: max negative gamma as magnet/target — see §1 exception)
3. Watch for max gamma to *relocate*
4. If max gamma flips polarity (above-spot → below-spot, or vice versa) → close remainder, reverse bias
5. Confirm new direction with the next gamma cross trigger

The runner that survives the partial exit gets stopped by the regime
flip, not by an arbitrary trailing stop.

## 12. Zero gamma line as regime delimiter [Discord-sourced]

*Discord #theory-questions, 2025-01-27 10:43 AM*

> I look classic to see if we are above zero gamma or below.

("classic" is presumably a chart view name in the GexBot UI — not yet
documented in our canonical files; worth resolving from the GexBot docs
or interface.)

**Zero gamma** is the underlying price level at which aggregate dealer
gamma flips sign. Above it, dealers are net long gamma (mean-reverting
behavior — they sell into strength, buy into weakness). Below it,
dealers are net short gamma (amplifying behavior — they sell into
weakness, buy into strength).

This is the regime delimiter the canonical [`gamma_vanna_video.md`](../canonical/gamma_vanna_video.md)
section 3 describes mechanistically. Freddy treats it as a first-look
filter:

- **Spot above zero gamma:** expect mean-reversion behavior at gamma levels; favor scalp setups
- **Spot below zero gamma:** expect amplification; entries are higher-conviction trend trades but with materially wider drawdowns possible between levels

Combine with the §1 binary (at-level vs between-level) and §11
(gamma-shift = sentiment): the full read-order is **zero-gamma regime →
nearest excess gamma level → cross trigger → gamma-shift watch**.

## 13. The gamma squeeze loop, and who hedges [HIGH]

*Video 2 [03:00–05:00] and [11:00–13:00]*

In Video 1 the discussion of dealer hedging is implicit. Video 2 makes
the mechanism explicit and adds a meaningful nuance: **it is not only
market makers who hedge dynamically.**

> It's not only the market makers who actually have to hedge. Most of
> the options traders in the NDX, they are sophisticated options
> traders, so they don't put an option and leave it like that — they
> actually dynamically hedge that option in the NQ market too.
> *[Video 2, ~11:30]*

This is operationally significant. The "flow" visible at excess-gamma
levels is the *aggregate* of MM hedging + sophisticated participant
hedging, not just MM hedging. The institutional positioning Freddy
trades around is built by parties on both sides of the dealer book.

### The squeeze loop

Freddy walks through the bullish gamma-squeeze loop on Friday's trade
(Video 2):

1. Spot starts moving up toward an excess-gamma level (big OTM call,
   157 contracts — likely a single institution)
2. High-convexity environment: small move in NQ causes
   *disproportionately large* delta changes on those options
3. Dealers + sophisticated participants are forced to buy NQ to re-hedge
4. That buying pushes NQ further up
5. Higher NQ → more delta change at those strikes → more forced buying
6. Loop continues until the gamma magnet is reached or until volatility
   regime flips

> If NQ moves a little bit up, then all these market makers and options
> participants as well, they say "now my gamma is telling me that I
> have to buy more"… and as they buy more NQ, NQ goes up… and then if
> NQ goes up very quick as we saw on Friday, the gamma says "now you
> are no [longer] delta neutral, you need to buy more in NQ"… it's a
> loop and the futures send higher and higher. *[Video 2, ~04:30]*

He calls this **the gamma squeeze**. The mirror-image loop runs on the
downside when the dominant excess-gamma strike is below spot and
negative-convexity. Same mechanism, opposite sign.

### Vol-regime modulation (passing reference)

In Video 2 *[~10:00]* Freddy mentions briefly:

> Usually these massive levels tend to work as a support or resistance,
> [but it] depends of if we're in a high volatility or low volatility
> environment… that's something we'll talk about in future videos.

He doesn't develop it. The canonical version of this — positive
convexity stalls in falling vol but is passed through in rising vol;
negative convexity flips the opposite way — lives in
[`../canonical/convexity_ladder.md`](../canonical/convexity_ladder.md)
"Convexity Ladder and the Volatility Environment." Cross-reference
when the regime is in doubt.

## 14. Two trade patterns — magnet vs resistance/exhaustion [HIGH]

*Video 2 [06:00–25:00], full session walkthrough*

In Video 2 Freddy retroactively reviews a Friday's session and
categorizes the day into two distinct trade types. This sharpens the
entry-mechanics framing from §3 by making the trade-context explicit:
*what kind of gamma situation is this?*

### Pattern A: Magnet trade

A single excess-gamma strike dominates — large enough that its
positioning weight overwhelms everything else on the chain. Spot is
some distance from it, and the strike pulls price toward itself via the
dealer-hedging mechanism in §13.

Worked example from Video 2 *[07:00–13:00]*:
- 09:35 ET: a 157-contract bought-call (NDX) lands as a massive excess
  gamma strike above spot at 21,833
- Spot at 21,800 has no significant gamma below to support, the lone
  big magnet above
- Bias: long, target = the magnet
- Confirmation: market structure (higher highs and higher lows) — the
  confluence requirement from §5 still applies
- Trade: long, taking partial profit at intermediate excess-gamma
  levels per §3 R:R rule

Freddy notes: "That's a tricky trade to be honest because I like to
enter only on levels of gamma, but when you have this big gamma
which… is bigger than anything… 157 contracts in the NDX market is
quite a lot." The size of the imbalance overrides the usual entry
discipline.

### Pattern B: Resistance + exhaustion trade

The dominant excess gamma is on the *opposite* side of spot from the
trade direction — it acts as a wall the underlying repeatedly fails to
break. Time-compression at retests (§9) confirms the wall is holding
and the defenders behind it are getting weaker, and the short trade
sets up on the eventual failure.

Worked example from Video 2 *[14:00–22:00]*:
- 12:30 ET: spot near max negative gamma, attempts to break it
- Three retests, each with shorter time between them and lower highs
  on the rally attempts
- Pattern is exactly §9's time-compression read
- Break of structural support → short trade
- First target: next excess-gamma level down (acts as magnet)
- Final target: max negative gamma below — price went there "to the
  tick and bounced" in his words *[Video 2, ~22:00]*

### When to expect each pattern

The two patterns map naturally to the zero-gamma regime read (§12):
- **Pattern A (magnet)** dominates when the chain has one or two
  oversized strikes that overwhelm everything else — usually means a
  single institution has taken a directional bet that day
- **Pattern B (resistance/exhaustion)** dominates when the chain has
  well-distributed positioning with clear max-positive/max-negative
  poles — the normal day

Reading the convexity ladder shape at the open (concentrated vs
distributed — see canonical [`convexity_ladder.md`](../canonical/convexity_ladder.md))
gives you the session-character bias before the first trade.

---

## What's directly actionable from this *with the corpus we already
have*

Without any new code, four rules from Freddy's framework can be applied
to the State-tier responses we're already capturing:

1. **No-trade zone derivation.** If spot is between `major_long_gamma`
   and `major_short_gamma`, we're in the chop zone — Freddy's negative-gamma
   territory. Don't take a directional read here. Pure derivation from
   existing State fields.

2. **Cross-confirmation gating.** When spot crosses `major_positive` /
   `major_negative` / `major_long_gamma` / `major_short_gamma`, log it as
   a CROSS EVENT in the corpus. These are Freddy's entry triggers. Schwab's
   5-min spot cadence detects them.

3. **Confluence check with overnight levels.** Schwab's price-history
   endpoint gives us prior-session OHLC and overnight bars. A derivation
   pass over the corpus can flag gamma levels that fall within ~5 pts of
   the overnight high/low — Freddy's confluence requirement made explicit.

4. **Directional bias from orderflow classification** (#6 above) requires
   the `mini_contracts` column meanings (pending GexBot Discord answer
   per `st-rks`). Once that's resolved, Freddy's call-sell vs put-buy
   read becomes a direct per-strike derivation from the State response.

## What needs verification before operational use

1. Whether Freddy's "selling of calls = bearish in nature" lines up with
   the *direction* GexBot's `mini_contracts` columns label customer
   activity. Pending Discord answer.
2. The specific NQ-point thresholds Freddy uses for stops (he cites
   10–12 pts on NQ) don't translate 1:1 to SPX without rescaling — NQ at
   22000 vs SPX at 7400 means SPX equivalents are roughly 1/3 the
   numeric magnitude. We should derive scaling empirically from the
   corpus, not borrow Freddy's numbers directly.
3. Section 8 slide is captured from the community video, not GexBot's
   own documentation. If Jasper has posted a canonical version of this
   four-shape framework in Discord, that supersedes this synthesis.

## Source provenance

Bead [st-rks](.) introduces the GexBot integration; this methodology
file is intended as research input to that work, not a separate task.
Cited timestamps refer to the primary source transcript at
`docs/gexbot/transcripts/2026-01-24_freddy_trading_with_gamma.txt`.
