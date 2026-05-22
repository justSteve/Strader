# GexBot Methodology — Freddy (community video, ~2026-01-24)

Synthesis of a 55-min community explainer video the GexBot team points to
as a good introduction. Speaker is **Freddy**, an NQ futures trader and
member of the GexBot Discord. He credits **Jasper** and **John**
(GexBot's principals) as the source of the model he's applying.

This document is a faithful synthesis, **not** an endorsement or
operational instruction. It exists as a reference so future Strader
sessions have a baseline of "what one experienced practitioner says
GexBot looks like in use," to compare against the corpus we build.

## Source

| | |
|---|---|
| **Video URL** | <https://www.youtube.com/watch?v=vnb92d3lVFs> |
| **Title** | "Trading with Gamma - Jan 24" |
| **Speaker** | Freddy (GexBot Discord community member, NQ futures trader) |
| **Length** | 55:24, 1092 transcript snippets |
| **Transcript** | Auto-captioned via `youtube-transcript-api`. Audio quality: speaker has an accent; conceptual content captured cleanly, jargon is noisy. Common mistranscriptions: "GubO" / "Guest boots" / "GP" / "gets boot" → GexBot. "Cella" → seller. "tie stops" → tight stops. "CES" → customer. "Trace" / "tray" → traded. "Mason money" → making money. |
| **Primary source** | [`docs/gexbot/transcripts/2026-01-24_freddy_trading_with_gamma.txt`](transcripts/2026-01-24_freddy_trading_with_gamma.txt) (with timestamps every 60s) |

Every claim below cites a transcript timestamp range. To verify, search
the timestamped txt for the cited minute marker.

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

## 2. Level-to-level mean reversion [HIGH]

*[12:00–14:30]*

Freddy maps GexBot's gamma model to classical volume-profile language:

- Excess gamma levels = "high value nodes" in volume-profile terms
- Spaces between = "low value nodes"
- Trade *the low value nodes toward the high value nodes*, expecting price to magnetize toward concentration
- High value nodes pull price in once approached, then either mean-revert away or continue to the next high value node

His framing: "price trades level to level." The trade is the move from
one excess-gamma level to the next.

## 3. Entry mechanics — gamma cross confirmation [HIGH]

*[28:00–31:00]* and *[38:30–40:00]* (failure-case demo)

Concrete entry rule:

1. Identify the excess gamma level you want to act on
2. **Wait for price to actually trade through it** — a clean cross, not a touch
3. Enter in the direction of the cross
4. Stop loss = the OTHER side of the crossed level (very tight; example: 10–12 NQ points)
5. Target = the *next* excess gamma level in the trade direction

Result: tight stops + larger targets, opposite of conventional "futures
need wide stops" advice. Discipline produces the asymmetry.

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

## 6. Directional bias from orderflow classification [HIGH]

*[31:00–34:30]*

This is the most direct use of GexBot's State-tier classification. Freddy
reads the *kind* of activity at each strike (per GexBot's per-strike
classification of customer-buy vs customer-sell across calls and puts):

| Pattern at a strike | Bias |
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

## 7. Why NDX, not QQQ (institutional vs retail) [HIGH]

*[15:00–17:00]*

Freddy notes GexBot tracks NDX rather than QQQ deliberately. Reasoning:

- QQQ contracts: $50–$400 within first standard deviation → retail-scale → flow is muddied by small participants
- NDX contracts: $1,600–$116,000 within first standard deviation → institutional-scale → flow reflects sophisticated positioning

The implication for our work: same principle says **SPX is the
institutional read; SPY is muddied by retail**. Our corpus correctly
focuses on SPX state endpoints, not SPY.

## 8. Volatility skew/smile shape read [LOW — verify against GexBot docs]

*[17:30–19:30]*

Freddy references reading the IV curve shape, but this section is the
murkiest in the transcript. The general claim, as I can read it:

- **Vertical/flat skew** (his Friday example) → "ball can go either way easily" → expect motion in either direction
- **Downward slope** → easier to go down (puts richer)
- **Bowl/curve shape** → options expensive on both sides → price tends to get trapped in a range

Confidence on the specific mappings is LOW because the audio garbled the
slope direction descriptions. The general intuition (skew shape implies
regime) is consistent with standard options trading literature but the
specific operational rules need re-verification.

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

*[01:18–01:35]* and throughout

Freddy frames GexBot as making futures trading "algorithmic in fashion."
He emphasizes:

- Tight stops + bigger targets (opposite of conventional futures advice)
- Rules-based entries (the cross trigger)
- No discretionary entries inside negative gamma
- The model is what makes the trade, not the trader's instinct

Not "automate the execution" — but "follow the rules without
discretion."

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

1. Section 8 (skew/smile mappings) — re-watch the video or check GexBot's
   metrics page for the canonical interpretation. The transcript was
   noisiest here.
2. Whether Freddy's "selling of calls = bearish in nature" lines up with
   the *direction* GexBot's `mini_contracts` columns label customer
   activity. Pending Discord answer.
3. The specific NQ-point thresholds Freddy uses for stops (he cites
   10–12 pts on NQ) don't translate 1:1 to SPX without rescaling — NQ at
   22000 vs SPX at 7400 means SPX equivalents are roughly 1/3 the
   numeric magnitude. We should derive scaling empirically from the
   corpus, not borrow Freddy's numbers directly.

## Source provenance

Bead [st-rks](.) introduces the GexBot integration; this methodology
file is intended as research input to that work, not a separate task.
Cited timestamps refer to the primary source transcript at
`docs/gexbot/transcripts/2026-01-24_freddy_trading_with_gamma.txt`.
