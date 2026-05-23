# Community Expert Q&A — John M

Community-tier archive of Discord Q&A authored by **John M**, a
community contributor in the GexBot Discord. John M's Q&A carries
weight from sustained practitioner experience and recognized authority
in the community — but **John M is NOT John Kirby (GexBot principal)**.
The handles and roles are distinct.

## Why a separate file from `discord_quotes.md`

- `community/discord_quotes.md` archives shorter community quotes and
  paraphrases. Authority signal: practitioner observation.
- This file archives sustained Q&A by John M, where his answers
  function as expert pedagogy — multi-turn exchanges that walk through
  mechanism, failure modes, and worked examples. The structure mirrors
  `canonical/principal_discord.md` (multi-section entries with
  analysis) but the tier is community, not vendor.

When a principal answers, the post goes to
`canonical/principal_discord.md`. When John M answers, it goes here.
When the speaker is ambiguous, default here and flag for Steve to
verify the Discord role tag.

## Why this distinction matters

A previous draft of `principal_discord.md` mis-attributed John M
responses to John Kirby (treating "John M" as a casual abbreviation of
"John Kirby"). Steve corrected this 2026-05-23: John M is a separate
identity, a community contributor with no GexBot staff role. The
re-tiering moved four entries from `canonical/principal_discord.md` to
this file. The content remains operationally valuable — John M's
pattern recognition is sound and worth preserving — but it does NOT
carry vendor-canonical weight. Where John M and a principal disagree,
the principal's statement wins.

## Source rules

- **Channel and date are mandatory.** Discord posts mutate; the
  citation must let a future reader find the original.
- **Speaker role tag preserved.** Discord usually labels community
  contributors with role icons. Capture verbatim.
- **Quote verbatim.** Don't paraphrase; commentary goes below the
  quote.
- **Q&A format preserved.** When the post is a reply to a community
  question, the question is included for context (with the asker's
  handle), but the content here is John M's answer.
- **All entries in this file are from `#theory-questions`** unless
  otherwise noted — confirmed by Steve 2026-05-23.

---

## 2025-02-XX — Guido + GexBot staff/John M, on Convexity Ladder color zones

**Channel:** GexBot Discord, #theory-questions
**Date:** 2025-02 (day not captured; follow-up confirms 2025-02-21)
**Speakers:** Guido (community) → GexBot staff/John M (unattributed in
the paste — likely John M based on the response style and the fact that
the later turn references "John's diagram")

### Q (Guido)

> Please clarify the terms, how would both "ZONES" look like for a
> Gexbot users point of view in terms of colors:
>
> **Point 1.** Convexity Ladder = options profile, gamma, cyan and violet
>
> The positive/right side, cyan color: Market participants classified
> as investors own long call or put, which means on the other hand,
> market makers are on the short side. Now the question is: Positive
> Gamma zones are what? I understand that you mean Cyan color. But
> this would not be the same as positive gamma itself because a long
> put has negative gamma in terms of gex profile (Red color)
>
> This leads to the 2. question, **point 2**, A. Declining volatility
> environment, market makers are Long Gamma
>
> To which part in the Convexity Ladder does this belong when you
> write "market makers are Long Gamma"? I understand you mean the
> bars with the violet color? (but they have both positive and
> negative gamma, so it is not clear for me if you describe this
> situation as Positive Gamma)
>
> For example, **point 4.**, Practical Trading Applications, Strategy 1,
> ... When in negative gamma — means the bars with violet color?

### A (John M)

> Guido, "Buying" Puts or calls creates Positive Gamma, "Selling"
> calls or puts creates negative gamma. Don't confuse the red and
> green from Gex profile with the cyan and purple of the gamma chart.
> As far as Profile Comparison open and read the 3rd attachment to
> envision the process. The negative gamma line in 3rd attachment is
> at the Point of Control, (POC), where a lot of indecisive trade
> occurs. Maybe study this type of theory before adding in the Long/
> Short Volatility part. Hope this helps.

### The attached graphic

The "3rd attachment" referenced is an annotated GexBot screenshot of
NQ_NDX from 2024-11-20, archived at
[`../canonical/images/customer_long_short_gamma_annotated.jpg`](../canonical/images/customer_long_short_gamma_annotated.jpg).

![Customer Long/Short Gamma annotated screenshot](../canonical/images/customer_long_short_gamma_annotated.jpg)

Vendor annotations on the graphic:

> Customer "Long Gamma" vs. "Short Gamma"
> Customer Long contracts vs. Short contracts.
>
> Customer places a position in the Index and hedges through the
> options. The M.M.'s take the opposite side.

And further down:

> Long Gamma position is essentially "Long Volatility". The Customer
> is expecting a move away from the long gamma positions. So if spot
> price moves down to 20600.00, a reversion is assumed or expected.
>
> If price is moving up and a "Long Gamma" position enters the market
> it could very well cap the rise and act as resistance, forcing a
> reversion downward. (Same process in reverse for the downside).

### What John M's response confirms / adds

1. **Two distinct sign rules.** The GEX profile (green/red) signs by
   call-vs-put. The gamma chart (cyan/purple) signs by long-vs-short
   contracts (= positive vs negative gamma, since buying any option
   creates positive gamma).
2. **Buy = positive gamma, sell = negative gamma** — stated cleanly,
   regardless of call/put. This is the textbook truth and resolves
   Guido's confusion about long puts. Note: this matches the canonical
   principal statements in
   [`../canonical/principal_discord.md`](../canonical/principal_discord.md);
   John M is reproducing established doctrine here.
3. **NEW: negative gamma line aligns with the Point of Control (POC).**
   The volume-profile POC is where the most volume traded. John M says
   the negative gamma line falls there because that's where indecisive
   (rangebound) trading concentrates. This claim is **community-tier
   pattern recognition** — not vendor-confirmed. Worth investigating
   operationally; if it holds across sessions, it gives a POC estimate
   purely from gamma data. Treat as hypothesis until measured.

---

## 2025-02-21 7:55 AM — Guido follow-up + John M confirmation

**Channel:** GexBot Discord, #theory-questions
**Date:** 2025-02-21
**Speakers:** Guido (community) → John M (community contributor — NOT
John Kirby)

### Q (Guido, confirming his understanding)

> John, thank you for the examples. I understand in general, that
> calls create positive gamma exposure, means underlying has to be
> bought for a hedge. In the Gex profile Call gamma is green,
> regardless who is supposed to be on the long or short side of this
> call. In the convexity profile it is different because it is
> classified in customers, so if a customer is long, the bars are in
> cyan color, regardless if it is a long put or a long call. Right?
>
> My question above was just to clarify, which point of view is taken
> in the paper. So to understand your answer right: If there is
> written, that market makers are Long gamma, it means for us that we
> are in a low convexity zone an the price is in the area of the
> profile with violet color. Right? My questions were just about the
> terminology which is used in the paper, not about the system itself.

### A (John M)

> Yes, cyan is long gamma, (long puts or calls). Just toggle that
> gamma switch on/ off to switch back to the PUTS/ CALLS bought/ sold
> view to confirm for yourself during the day.

### What John M's response confirms

1. **Cyan = long gamma = long puts OR long calls** (customer
   perspective, customer-bought side). Confirms Guido's reading. This
   matches the canonical Jasper/John Kirby statements; John M is
   reproducing established doctrine.
2. **The customer-long classification is at the CONTRACT level** — if
   a customer is long ANY contract (call OR put), it lands in cyan.
   The call/put distinction is the GEX axis, not the gamma axis.
3. **NEW: UI toggle.** GexBot ships a "gamma switch" that flips the
   chart between (a) cyan/purple gamma view and (b) PUTS/CALLS
   bought/sold view. Toggling between them is John M's recommended way
   to verify the mapping during a live session.

Note Guido's framing of "market makers are Long gamma → violet bars" —
he's correctly reasoning by inversion. If MM is long gamma, customer
is short gamma, customer-short shows as violet. John M doesn't
directly confirm Guido's MM-inversion logic, but Jasper does in the
closing exchange of the thread (see
[`../canonical/principal_discord.md`](../canonical/principal_discord.md),
entry on Jasper closing the customer-perspective convention).

---

## 2025-04-04 — John M on when gamma levels fail to hold

**Channel:** GexBot Discord, #theory-questions
**Date:** 2025-04-04, 11:21 AM → 12:39 PM
**Speakers:** stockholm (community) ↔ John M (community contributor —
NOT John Kirby)

This Q&A documents a **failure mode** of the "pivot at gamma levels"
rule. The asker observes negative gamma levels failing to stop a
downside move; John M explains why.

### Q1 (stockholm, 11:21 AM)

> negative gamma levels don't seem to be stopping the move. Why is that?

### A1 (John M, 12:14 PM)

> Selling Calls and Selling Puts creates Negative Gamma. It also dumps
> more liquidity into the markets pushing the market lower. We are
> also in a "Put" dominated environment.

### Q2 — stockholm's correct mechanical objection (12:19 PM)

> yes but short puts and long puts are counteracting forces from a
> delta hedging perspective.
>
> Long puts will create selling pressure where as short puts will
> create buying pressure.
>
> Im not following why the DEX from short puts is not acting as a
> stop for the falling markets

### A2 (John M, 12:24 PM)

> Until some sort of positive news flow enters the market to establish
> short covering and call buying, "Dealers" have to keep selling
> futures while they are below specific Gamma levels. Their selling
> is completely outweighing any of the options positions.
>
> Did you happen to take note of the "Put Selling" above spot price
> this morning. There were quite a few attempts where they sold Puts
> pricing 70% volatility. I would gather that these Put Sales were
> just hedges for the pounding they were doing on futures.

### A3 (John M, 12:39 PM — worked example)

> They came in and sold a few thousand of the ES $5237.00 Puts at
> 9:50 am. and by 10:15 they smashed right through them. Those key
> concepts regarding gamma are from Freddie's YouTube class.
> <https://www.youtube.com/@gextrading>

### What John M's response establishes

#### 1. Gamma rules have limits — sustained directional pressure can overrun them

The pivot-at-gamma-levels rule (per Jasper, in
[`../canonical/principal_discord.md`](../canonical/principal_discord.md))
and the short-put-creates-buy-support intuition (per stockholm's
mechanical argument) both presume that **dealer hedging is the
dominant flow at the level**. In a "put dominated environment" with
sustained selling, that presumption fails: directional flow from
real-money sellers can exceed the hedging buy pressure that short-put
dealers would otherwise provide.

**stockholm's mechanical argument is correct** in normal regimes. It
just doesn't apply when the directional pressure dominates. John M
doesn't dispute the mechanics — he explains why they don't bind here.

Note this failure-mode observation is John M's community-tier reading,
not vendor-canonical doctrine. The mechanism is plausible and consistent
with the canonical pivot rule's preconditions; treat as a useful
operational heuristic, but it has not been vendor-validated as
canonical.

#### 2. The "put selling above spot as hedge" pattern

John M identifies a specific tactical structure visible that morning:
institutions **selling puts above spot at 70% IV** as a hedge for
their primary short-futures position. The put sale isn't a bullish
bet — it's premium collection on positions they expect to expire
worthless, used to cushion the short futures.

Operational read: when you see put-selling at very high IV ABOVE spot
in a falling market, do not interpret it as bullish positioning at
the level. It's likely the cover, not the trade.

#### 3. The failed-pivot worked example

ES $5237 puts: "a few thousand" sold at 9:50 AM → "smashed right
through them" by 10:15. About 25 minutes from sale to break. Strong
short-side pressure can take out put-sale supports within minutes,
not hours.

#### 4. Freddy's channel URL captured

> Those key concepts regarding gamma are from Freddie's YouTube class.
> <https://www.youtube.com/@gextrading>

John M confirms Freddy's channel is `@gextrading`. This is the source
for all the Freddy videos in `community/` docs
(`freddy_methodology.md`, `freddy_orderflow_series.md`).

### Cross-references

- [`../canonical/gex_profile.md`](../canonical/gex_profile.md) —
  observation 8, the canonical basis for "lead with the gamma ladder
  for pivots." This Q&A documents *when* that rule fails.
- [`../canonical/convexity_ladder.md`](../canonical/convexity_ladder.md)
  "Risk reading vs direction reading" — canonical vendor text already
  says the convexity ladder is "less about discerning direction, and
  more about measuring risk." This Q&A operationalizes when that risk
  reading should NOT be inverted into a direction call.
- [`freddy_methodology.md`](freddy_methodology.md) §1 max-neg-gamma
  exception — this Q&A adds nuance: even the max-neg-gamma magnet can
  fail when the regime is strongly directional. Worth flagging in §1
  as a regime caveat.

---

## 2025-05-14/15 — Izzy Q&A: gamma filter vs put/call composition (John M worked example)

**Channel:** GexBot Discord, #theory-questions
**Date:** Izzy initial post 2025-05-14 5:43 PM; yungissh 7:31 PM same day;
John M responses 2025-05-15 6:07 AM, 6:20 AM, 6:35 AM
**Speakers:** Izzy (community) + yungissh (community) → John M
(community contributor — NOT John Kirby)

This exchange is one of the most operationally rich Q&As in the
series. Izzy raises the legitimate concern that the gamma filter (net
long/short) loses put/call composition information; John M responds by
demonstrating how to read both views together rather than choosing
one. Because this is community-tier rather than canonical, treat the
patterns John M articulates as **practitioner pattern recognition**,
not vendor-confirmed doctrine.

### Q (Izzy, 5/14 5:43 PM)

> I watched a tutorial video with Jas where he turns the gamma filter
> on the state view to look for reversion trades. Basically that long
> gamma acts as resistance and spot will pin to those levels.
> Furthermore, that short gamma 'repels' spot and pushes spot towards
> the next node of long gamma.
>
> However, isn't the whole point of gexbot is to have the order
> classification of puts and calls, as not all short gamma is treated
> the same? For example, if the long call near spot is acting as
> resistance, doesn't it make a world of a difference whether the
> short gamma is puts or calls? In order to act as an accelerant for
> spot price, don't you want to enter where there are a large number
> of trapped short gamma sellers? (short puts if price is trending
> down, and short calls if price is trending up). Thus doesn't turning
> on the gamma filter cause you to miss that information?
>
> what am I missing? Do most people prefer the above view without the
> gamma filter on?
>
> Maybe a different way to ask the question — what is the perfect
> trade setup that you could witness on gexbot? Wouldn't it be large
> long gamma node, but also with short gamma pushing price toward the
> long gamma? ie multi strike short calls below a large long call.
> Wouldn't that be much different that multistrike short puts below a
> large long call?

Izzy attached a baseline SPX state screenshot showing the un-gamma-
filtered view:
[`../canonical/images/john_izzy1_spx_state_baseline.jpg`](../canonical/images/john_izzy1_spx_state_baseline.jpg).

### Q (yungissh, 5/14 7:31 PM)

> Let me know what you find out on this I'm trying to understand the
> gamma filter better, from what I've seen and I could be wrong here
> so please grain of salt as of late we've been attracted to the
> largest gamma clusters whether above or below. Once we reach the
> first wall we either attempt to break and fail fall back below or
> break and mellow out between the two largest gamma nodes.

### A1 (John M, 5/15 6:07 AM — workflow and "double warning")

> Izzy, take a look at this options view from yesterday, (05/14/2025).
> Once the market opens and then settles in after 15-20 minutes
> capture a screen shot for yourself to mark up. Note how I
> immediately marked up "Calls Sold" and "Puts Bought" at the ES
> $5919.00, both of these orders express a bearish morning outlook
> for the market. We essentially have a "double" warning that for at
> least the morning session keeping price above or getting above will
> be difficult. That "Calls Sold" position grew to over 2000 contracts
> into lunch hour. Now, once you have your "Options" view laid out,
> toggle the button to show the "Gamma" view. The second diagram was
> the "Gamma" view coming in to lunch just after European close where
> you can see I labelled the possibilities for the afternoon.

Attached graphic:
[`../canonical/images/john_izzy2_es_5919_double_warning.jpg`](../canonical/images/john_izzy2_es_5919_double_warning.jpg).

The graphic shows the Options view (no gamma filter) with John M's
markups. Visible patterns:
- $5919 strike has BOTH "Calls Sold" (left orange) AND "Puts Bought" (right purple) — labeled with red arrows + text "CALLS SOLD AT $5919.00 RESISTANCE" and "PUTS BOUGHT AT $5919.00 BEARISH BET: RESISTANCE"
- $5894, $5879: "PUTS BOUGHT" — additional bearish bets below
- $5850: green-arrow-labeled "$5850.00 SUPPORT ZONE"
- $5809: large purple bar far-left, labeled "PUTS SOLD LARGEST SUPPORT"
- Cyan line shows price testing $5919 from below and getting rejected

### A2 (John M, 5/15 6:20 AM — hypothetical mechanism)

> Hypothetical situation: Let's assume the ES is trading around
> $5890.00 and we see a "Calls Bought" position come in up at ES
> $5910.00, (Calls Bought would show up as "positive gamma".
> Furthermore, as long as there isn't a larger negative gamma position
> at the same price level to overtake the positive gamma you will see
> the cyan blue line extend to the right of axis. In yesterday's
> example the Calls Sold outweighed the Puts Bought hence the large
> negative gamma line extending left of axis. Now, as price rises to
> meet the "Calls Bought" at the $5910 price point we have to expect
> some initial profit taking to occur. This is the theory behind the
> "positive gamma" level being an initial "Point of Reversion". The
> profit taking initially prevents price from going higher unless of
> course the order flow is extremely bullish. If you read both
> diagrams and put the context together we really needed stronger
> order flow to move higher and the buyers weren't able to do the job.

### A3 (John M, 5/15 6:35 AM — Bullish Above / Bearish Below pattern)

> Here is a view from last week. Take note of the yellow rectangle.
> We had "Calls Bought" and "Puts Bought" on/at the same price level.
> This now acts as your "Bullish Above/ Bearish Below". Practice
> laying out the possibilities then match up your gamma view. The
> second diagram is from 05/13/2025. This view shows how that ES
> $5920.00 line became the "Resistance Problem" one day prior to the
> $5920.00/ $5919.00 into 05/14/2025 in the first example, (from
> above). Calls bought and Puts Bought on the same price level. (Also
> works when Calls Sold/ Puts Sold at same level). I hope this helps.

Attached graphic:
[`../canonical/images/john_izzy3_es_5920_battle_line_precursor.jpg`](../canonical/images/john_izzy3_es_5920_battle_line_precursor.jpg).

Visible: 5/13 view with price testing $5920 (annotated "$5920.00 IS
THE NEW BATTLE LINE FOR NOW") with both Calls Bought and Puts Bought
visible at that level. Large $5950 calls-bought bar above (green
arrow) and large $5889 puts-bought bar below (red arrow).

---

### Four patterns documented in this exchange

These are John M's pattern recognitions — community-tier observations,
not vendor doctrine. They are operationally useful and worth tracking
in the measurement framework, but should be treated as hypotheses to
verify, not as canonical rules.

#### Pattern 1: Double-warning (Calls Sold + Puts Bought at same level)

Both orders express a *bearish* outlook at the level. John M's
"double warning" — keeping price above or getting above will be
difficult. Operationally: a level with this pattern is a high-
confidence resistance candidate.

Visible at ES $5919 on 5/14 — both red-arrow-tagged in graphic
[`../canonical/images/john_izzy2_es_5919_double_warning.jpg`](../canonical/images/john_izzy2_es_5919_double_warning.jpg).
The symmetric inverse (Puts Sold + Calls Bought at same level) would
be the "double warning" upward.

#### Pattern 2: Bullish-Above / Bearish-Below (Calls Bought + Puts Bought at same level)

Both orders are LONG options at the same level, but the call is a
bullish bet (profits above) and the put is a bearish bet (profits
below). The level becomes a clean pivot candidate: above = bullish
dominant, below = bearish dominant. Whoever holds the level wins.

John M also notes this works for the inverse: **Calls Sold + Puts Sold
at the same level** also creates a Bullish-Above/Bearish-Below pivot
(sellers profit if price stays AT the level, lose either direction).

Visible at ES $5920 on 5/13 in graphic
[`../canonical/images/john_izzy3_es_5920_battle_line_precursor.jpg`](../canonical/images/john_izzy3_es_5920_battle_line_precursor.jpg)
— described as the "battle line."

#### Pattern 3: Initial Point of Reversion (mechanism)

Positive gamma levels stall price via **profit-taking expectation**,
not just MM hedging. From John M's 6:20 AM hypothetical:

> Price rises to meet the Calls Bought at the $5910 price point. We
> have to expect some initial profit taking to occur. This is the
> theory behind the "positive gamma" level being an initial "Point of
> Reversion". The profit taking initially prevents price from going
> higher unless of course the order flow is extremely bullish.

This is the **customer-flow** version of the pivot mechanism — the
same mechanism noted in [`freddy_orderflow_series.md`](freddy_orderflow_series.md)
Part 2 "Mechanism inversion" section. Customers take profit at their
long-gamma strikes; that selling provides the wall, not pure MM gamma
hedging. John M makes this explicit: "this is the theory."

The "unless of course the order flow is extremely bullish" caveat
recovers the failure mode documented in the prior entry — sustained
directional pressure can overwhelm the profit-taking wall.

Note: this is John M's framing. The canonical mechanism story remains
the dealer-hedging account documented in
[`../canonical/principal_discord.md`](../canonical/principal_discord.md)
and [`../canonical/convexity_ladder.md`](../canonical/convexity_ladder.md).
John M's "profit-taking → reversion" is a community-tier extension of
the canonical mechanism, not a replacement.

#### Pattern 4: Cross-day persistence

The $5920 line was the "battle line" on 5/13. It became the resistance
problem at $5919/$5920 on 5/14. **Gamma walls from one session can
persist into the next session**, especially when the underlying
positioning carries over.

Worth tracking: if a major level held (or failed) yesterday, expect
it to be in play today. Don't reset gamma map at each session open.

---

### Workflow discipline (operational, per John M)

From John M's response, the explicit operational sequence:

1. **Wait 15-20 minutes** after market open for initial volatility to settle
2. **Screenshot the Options view** (no gamma filter) and mark it up — identify Calls Bought / Calls Sold / Puts Bought / Puts Sold concentrations
3. **Look for the patterns**: double-warning, Bullish-Above/Bearish-Below, ITM call buying
4. **Toggle to Gamma view** to confirm net polarity (cyan/purple extent at marked levels)
5. **Layout possibilities for the session** based on what holds
6. **Re-check the gamma view** at major sessions (European close = lunch hour in US)

This is the workflow that *uses* the gamma filter as a confirmation
layer rather than treating it as the primary view. It directly answers
Izzy's concern.

### How this resolves Izzy's three sub-questions

**Q1: Doesn't the gamma filter cause you to miss put/call info?**
A: Yes if you only look at the gamma view. But the operational
workflow uses Options view FIRST for composition, then Gamma view
for confirmation. The gamma filter is a complement, not a
replacement, for the Options view.

**Q2: Don't you want trapped short put sellers / short call sellers
for acceleration?**
A: Yes, and this is visible in the Options view (the COMPOSITION of
short gamma at each strike), not directly in the gamma-filtered view.
The gamma filter tells you the NET — for composition you go back to
the Options view.

**Q3: What's the perfect trade setup?**
A: Implicitly, John M shows it: a strike with the right pattern
(double-warning, Bullish-Above/Bearish-Below, or just ITM call buying)
+ confirmation from the gamma view. The put-vs-call composition of
the surrounding short gamma DOES matter and DOES change the read,
exactly as Izzy intuited.

### What John M doesn't directly address

Izzy explicitly asked: "what is the perfect trade setup that you
could witness on gexbot? Wouldn't it be large long gamma node, but
also with short gamma pushing price toward the long gamma? ie multi
strike short calls below a large long call. Wouldn't that be much
different than multistrike short puts below a large long call?"

John M demonstrates patterns but doesn't give a one-line "perfect
setup" formula. The implicit answer from the patterns: the perfect
setup is the convergence of a strong directional pattern (double-
warning, Bullish-Above/Bearish-Below, or ITM call buying) WITH
supportive gamma extension AND a clear orderflow narrative in the
surrounding strikes. There isn't a single template — it's pattern
recognition over multiple charts.

### Cross-references

- [`../canonical/principal_discord.md`](../canonical/principal_discord.md)
  entry on John Kirby ITM-call-buying-as-support — pattern that
  combines well with the Bullish-Above/Bearish-Below pivot
- [`../canonical/principal_discord.md`](../canonical/principal_discord.md)
  entry on Jasper's pivot-at-customer-long-gamma rule — the canonical
  base rule these patterns refine
- [`../canonical/principal_discord.md`](../canonical/principal_discord.md)
  entry on John Kirby gamma↔convexity equivalence — the structural
  equivalence Izzy is reasoning across
- [`../canonical/gex_profile.md`](../canonical/gex_profile.md) — the
  green/red GEX axis Izzy references
- [`../canonical/convexity_ladder.md`](../canonical/convexity_ladder.md)
  — the cyan/purple gamma axis Izzy references
- [`freddy_orderflow_series.md`](freddy_orderflow_series.md) Part 2
  mechanism note — the customer-flow mechanism John M makes explicit
  ("profit taking → initial Point of Reversion") matches the corrected
  mechanism documented there

---

## Revision log

- 2026-05-23: File created from re-tier of four entries previously in
  `canonical/principal_discord.md` (bead st-62v). Entries 3 (Guido
  color-zone Q&A), 4 (Guido follow-up + John M confirmation), 9
  (stockholm gamma-levels failure mode), 13 (Izzy gamma-filter Q&A)
  moved here. Reason: speaker is John M (community contributor), NOT
  John Kirby (GexBot principal); content tier is community, not
  vendor-canonical. Channel attribution corrected to `#theory-questions`
  per Steve's 2026-05-23 confirmation.
