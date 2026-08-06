# Freddy Sarmiento — GexBot OrderFlow video series

Tracker for Freddy's multi-part educational series introducing GexBot's
**OrderFlow** tool (a paid subscription tier within the GexBot product).

## Subscription status

**We subscribe as of 2026-08-05** — the Quant tier (one month, tier
decision ~Sep 1) includes the Orderflow package, and the 62-day
orderflow archive is on Z:. This section previously read "we do not
currently subscribe"; that preamble and its treat-as-background caveat
are superseded [st-20nw]. This series is now primary doctrine input
for the Orderflow Mastery effort (epic st-ygy1) — synthesized against
`../orderflow-intended-read.md`, verified against the archive in
Phase 2.

## Series

| Part | Title (working) | Video | Transcript | Status |
|---|---|---|---|---|
| 1 | Realized vs Implied Volatility (foundation) | <https://youtu.be/RylEg5XEivk> | [`../transcripts/freddy_orderflow_part1_realized_vs_implied_vol.txt`](../transcripts/freddy_orderflow_part1_realized_vs_implied_vol.txt) | ✓ synthesized below |
| 2 | Convexity OrderFlow + GEX OrderFlow (reading the spikes) | <https://youtu.be/75G3sXgZem0> | [`../transcripts/freddy_orderflow_part2_convexity_and_gex_orderflow.txt`](../transcripts/freddy_orderflow_part2_convexity_and_gex_orderflow.txt) | ✓ synthesized below (mechanism issue flagged) |
| 3 | GEX OrderFlow directional read + combining with Convexity OF | <https://youtu.be/6Q2KPv-5KWo> | [`../transcripts/freddy_orderflow_part3_convexity_gex_orderflow_continued.txt`](../transcripts/freddy_orderflow_part3_convexity_gex_orderflow_continued.txt) | ✓ synthesized below |

**The series is complete at three parts** (verified 2026-08-06 [st-20nw]: full
channel enumeration, 34 videos — no Part 4 despite Part 3 promising one "with
real life examples"; the channel pivoted to live-trading recaps from May 2025
and course promos from Jan 2026). Channel: **GexFuturesTrading**
(`@gextrading`, UCH1qiP2SN83pCKRwGlM9oNg), operator Fredy Sarmiento
(one "d" — inferred via LinkedIn/X, not stated on the channel). The de-facto
Part 4 material is the live-trading application videos, chiefly
`ihRxcBJPYnU` (2025-05-06, NQ Orderflow live) and the hour-long pre-series
`5yms1oOGp6k` ("Concepts review — Intro to OrderFlow", 2025-02-17), plus
`AsNlSzOMxnA` (2025-10-27) for post-series product changes. Queued, not yet
transcribed.

---

## Part 1 — Realized vs Implied Volatility

**Video:** <https://youtu.be/RylEg5XEivk> (3:31, 87 transcript snippets)
**Format:** Narrator-style explainer (different from Freddy's
trade-review videos). Speaker says "welcome back to the channel" —
first-person Freddy.
**Steve's note:** "Let's start from the basics!"

### Core distinctions

- **Realized volatility (RV)** = what *actually* happened. How much the underlying moved.
- **Implied volatility (IV)** = what the options market *expects* to happen. Embedded in option prices.

### Analogies stacked

Freddy uses four overlapping analogies for the same RV/IV distinction —
each one targets a different intuition:

1. **Car speed** *([00:00]–[00:30])* — steady 40 mph = low RV; surge to 80 then 10 then 100 = high RV
2. **Weather insurance business** *([00:30]–[01:00])* — RV = what the weather actually did; IV = the forecast the insurer priced on. Premium can be high (priced for hurricane) and the storm never comes (insurer profits) or vice versa.
3. **Casino owner** *([01:00]–[01:30])* — option sellers profit when buyers *overestimate* their chances. If IV was bid up because everyone expected wild swings and the market just drifted, the sellers (who collected the high premiums) win.
4. **Bike downhill** *([02:00]–[02:30])* — steady descent (low RV) → seller is comfortable, profiting from time decay → sudden sharp U-turn → seller must scramble to rehedge → that scramble itself adds volatility, accelerating the move.

### The trading dynamic

> If the market trends steadily option sellers win because realized
> volatility stays lower than implied volatility. But if a sudden
> reversal happens realized volatility jumps breaking the stable
> relationship with implied volatility. This leads to unexpected
> market movement forcing option sellers to adjust often at a loss.

The asymmetric payoff for sellers (steady win, sudden lose) is the
core of the dynamic. It connects directly to the canonical mechanism
described in [`../canonical/gamma_vanna_video.md`](../canonical/gamma_vanna_video.md):
when IV decreases (option selling pressure), market makers and
sophisticated participants hedge in ways that reinforce the trend.
When IV suddenly increases (the reversal), forced hedging amplifies
the move further.

### Slow-down-trend example walked through

> Imagine ndx [NQ] is in a slow downtrend. Sellers wrote contracts
> expecting big swings (high IV). The market moves down slowly at a
> constant pace (low realized vol). Sellers profit — options were
> priced as if the market would swing wildly, but it didn't, so as
> long as the market continues steadily, the seller keeps pocketing
> premiums.

This is the **"vanna/charm rally"** mechanism in reverse — sustained
trending in either direction with low realized vol is what the
canonical [`../canonical/vanna_charm_video.md`](../canonical/vanna_charm_video.md)
§5 describes as "market makers effectively supporting [or pushing] the
markets constantly until the options expire."

### What Part 1 doesn't yet cover

Part 1 is foundational and doesn't yet:
- Introduce the OrderFlow tool itself
- Connect RV/IV to the convexity ladder or GEX profile we already have
- Address the practitioner question "how do I trade this?"

Presumably Parts 2+ will bridge to the OrderFlow tooling and the
operational reads.

### Cross-references to canonical material

The RV/IV mechanism Freddy describes is canonically documented:

- [`../canonical/gamma_vanna_video.md`](../canonical/gamma_vanna_video.md) §5 — "in order for market makers to be short gamma, investors need to bid for options. The bidding of options has a tendency to increase implied volatility." That's the IV-rise mechanism.
- [`../canonical/vanna_charm_video.md`](../canonical/vanna_charm_video.md) §5 — the combined vanna + charm + gamma support that produces sustained trending in low-RV regimes.
- [`../canonical/metrics_math.md`](../canonical/metrics_math.md) "Vanna Exposure" — the math behind IV → MM hedging.
- [`discord_quotes.md`](discord_quotes.md) "lifted vs depressed vols" entry — the related practitioner vocabulary (lifted = rising IV; depressed = falling IV).

### Confidence

HIGH on substance — the transcript is clean (different audio profile
from Freddy's trade-review videos; this video is narrated, not live
trade-analysis). The four analogies map cleanly to canonical theory.

---

## Part 2 — Convexity OrderFlow + GEX OrderFlow

**Video:** <https://youtu.be/75G3sXgZem0> (27:32, 615 transcript snippets, video ID `75G3sXgZem0`)
**Format:** Tutorial — Freddy walks the OrderFlow chart visually while
narrating; some chart elements assumed visible to viewer

### Pitch (from the opening)

> What if I told you there is a way to trade that 99% of traders
> don't even know exist? […] What if you have a tool — well, you
> guys know — sort of flow that could tell you where the market is
> most likely to move next.
>
> The most amazing thing is that with this tool, you can take trend
> trades as well as counter trend trades with confidence. Why? Because
> you can see exactly at the same time when the big guys are buying
> options, selling options, taking profits from these options, and
> actually they're moving the market.
>
> So we all know about the world of market makers, how when they
> hedge their positions they influence the market. But now with this
> tool you forget about the market makers and the customer side. You
> don't have to think "oh this is the customer side, this is the
> market maker." Just forget about it — it's all filtered for you.
> *([00:30]–[01:30])*

### Linear → nonlinear thinking

> As futures traders we always think in linear terms. So we buy, we
> expect the price to go up, we make money. Or we sell and we expect
> the price to go down. […] But if you want to trade with order flow,
> we need to change that mentality and move into thinking how the
> options guys think — which is nonlinear.
>
> Trading with order flow you have to think of reversions as well as
> continuations and regime change. *([02:00]–[03:00])*

The vocabulary shift is explicit: **reversion / continuation /
regime change** instead of bullish / bearish. This aligns with
Freddy's earlier Discord defense of his vol-focused framing (see
[`discord_quotes.md`](discord_quotes.md) "Freddy on his vocabulary
choice").

### Four use scenarios

Freddy lays out where OrderFlow is most useful:

| Scenario | Timing | Reading style |
|---|---|---|
| Morning, non-event day | Open → ~12:30/1:00 PM | "Cost of upside / downside lifted"; "liquidity taken / provided" — the main reading style this video covers |
| NQ local scalping | Anytime intraday | Spikes good for 15–20 NQ points (~80 ticks). Recommended NQ only — ES tick value too small to be worth it. |
| Event days (FOMC, etc.) | Around the event | Detect positioning structure; see hedges as they're put on |
| End of day | Last 5–10 min | "Speculative positioning" — read late-day option buys as direction bets |

The morning + NQ scalping is the focus of this video. Event-days and
EOD readings get full treatment in later parts presumably.

### What OrderFlow shows that GEX profile alone doesn't

> What if we can detect significant flows when they enter the system
> at different strikes through various options structures — iron
> condors, straddles, strangles? We can't see those structures on
> the GEX profile. But with order flow we could.

OrderFlow visualizes **flows entering the system in real time** —
single-strike trades show up as one spike, but a multi-leg structure
(iron condor, straddle, etc.) shows up as a coordinated pattern of
spikes across strikes. The GEX profile only shows the accumulated
state; OrderFlow shows the deltas as they happen.

### Convexity OrderFlow

**Formula** (per Freddy *[~10:00]*): `(long order flow × gamma exposure) - (short order flow × gamma exposure)`

The chart shows two-sided bars at each strike (or time bucket):
- **Up spike (positive) = long gamma** — someone is BUYING options
- **Down spike (negative) = short gamma** — someone is SELLING options

#### Reading rules (operational core of this video)

| Spike direction | Meaning | Trade implication |
|---|---|---|
| **Up spike (long gamma)** | Someone buying options at the level → taking liquidity → expressing expectation of regime change via buying volatility | **REVERSION** — current trend likely about to reverse |
| **Down spike (short gamma)** | Someone selling options at the level → providing liquidity → expressing expectation that current regime will continue | **CONTINUATION** — current trend likely to continue |

Mnemonic (Freddy's): **long gamma = friction = reversion; short gamma = momentum = continuation.**

### GEX OrderFlow

The companion chart. Same up/down spike pattern, but signed by
call/put rather than long/short:

- **Up spike (yellow) = call gex imbalance growing** — more green being added to the GEX profile
- **Down spike = put gex imbalance growing** — more red being added

Freddy proposes naming convention: "call gamma" for positive GEX OF
spikes, "put gamma" for negative ones. *(Note: this naming overlaps
confusingly with the "long/short gamma" labels on the convexity
ladder. The labels are scoped to the OrderFlow context per Freddy's
usage in this video.)*

### The "secret": read both together

> You cannot have a look at this one in isolation. You have to look
> it all together. […] Convexity order flow and GEX order flow
> together — that's the recipe.
> *([08:30])*

A reversion signal needs to show up in BOTH a long-gamma Convexity OF
spike AND a corroborating GEX OF read (which side the gamma growth
favors). Reading either chart in isolation produces false signals.

### Worked example — FOMC March 2025

> Around 11:00, we saw a big call buy at the top of the day, right
> before the FOMC interest rate decision. You'd think — why are they
> buying a call when the market is already trending up?
>
> Then we realize: the actual position was selling the futures, and
> the call was just a hedge for that position. I took that trade and
> made good returns.
> *([05:30]–[06:30])*

The point: a single bullish-looking flow (call buy) doesn't tell you
intent. The trader was net SHORT — the call was the hedge against
adverse moves on the short futures. OrderFlow lets you see the
structure of multi-leg positioning that the GEX profile alone would
miss.

### ⚠️ Mechanism inversion — Freddy gets MM hedging direction backwards

In *[12:00]–[13:30]* Freddy describes WHY long-gamma spikes produce
reversion, with a story about MM delta hedging:

> Customers long gamma → market makers are short gamma → that is
> volatility suppressing. […] When market makers need to be delta
> hedged: as price moves up, they need to sell futures; as price
> moves down, they need to buy futures. So they're selling on rallies
> and buying on dips. That's the volatility suppressing behavior.

**This is mechanically inverted from canonical theory.** Per
[`../canonical/gamma_vanna_video.md`](../canonical/gamma_vanna_video.md) §3:

- MM **long gamma** (= MM owns options) → MM sells on rises, buys on drops → **stabilizing**
- MM **short gamma** (= MM sold options) → MM buys on rises, sells on drops → **amplifying**

Freddy attributes the long-gamma stabilizing behavior ("sell on rises,
buy on drops") to MM **short** gamma. The directions are swapped.

He repeats the inversion symmetrically *[~13:00]* for the other side
(customer short gamma → MM long gamma → he calls this "amplifying"
when canonical says MM long gamma is stabilizing).

#### The operational conclusion is still correct

Despite the mechanism error, Freddy's OPERATIONAL claim is the same
as jass's canonical rule from
[`../canonical/principal_discord.md`](../canonical/principal_discord.md):

> Pivot at customer long gamma (cyan). Move through customer short
> gamma (purple).

Both Freddy and jass agree on **what** happens. They disagree on
**why**.

#### The correct mechanism (per canonical + customer-flow nuance)

The reason customer-long-gamma strikes act as pivots **isn't** direct
MM hedging — it's a flow dynamic mediated by customer behavior:

1. Customer is long options at strike K. Price approaches K.
2. Customer's option becomes near-ATM, gamma peaks, position gains
   value quickly.
3. **Customer takes profit by selling the options.**
4. MM (who was short the matched position) closes by buying the
   options back from the customer.
5. MM unwinds their stock hedge — sells the shares they were holding.
6. Net effect: customer + MM flow combine to produce SELL pressure at
   the strike, stalling/reverting the underlying.

The pure-mechanical MM gamma hedging story (textbook) DOES predict
amplification at customer-long strikes — but in practice, customer
profit-taking dominates and inverts the net effect. This is why the
rule "pivot at customer long gamma" works empirically even though the
pure-gamma textbook would predict otherwise.

Freddy's video skips the customer-flow leg of this story and instead
re-labels MM hedging directions to make the operational story work.
The result is the right rule with the wrong mechanism.

### What to carry forward operationally

- The Convexity OF / GEX OF reading rules (long-gamma spike = reversion; short-gamma spike = continuation) are sound — they match jass's canonical rule
- The four-scenario framework (morning, scalping, event days, EOD) is the operational scaffold for using OrderFlow
- The "read both charts together" requirement is the discipline that prevents false signals
- The mechanism explanation in *[12:00]–[13:30]* should be read through canonical theory + the customer-flow nuance above, not taken at face value
- ~~We don't currently subscribe to OrderFlow, so all of this remains background~~ — superseded 2026-08-06 [st-20nw]: we subscribe (Quant month); these reads are now Phase 2 verification targets, see `../orderflow-intended-read.md` §6

### Confidence

- Operational rules (reversion/continuation reading): HIGH (consistent with canonical jass rule)
- Vocabulary (reversion/continuation/regime change): HIGH (consistent with Freddy's own vol-focused framing in Discord)
- Mechanism explanation: LOW (gets MM hedging directions inverted; see warning above)
- Worked examples (FOMC trade): MED (specific to one session, hard to validate without recording the chart)

---

## Part 3 — GEX OrderFlow directional read + the combination

**Video:** <https://youtu.be/6Q2KPv-5KWo> (26:29, 556 transcript snippets,
published 2025-04-01, 4.5K views)
**Transcript quality note:** heavier auto-caption noise than Parts 1–2 —
"GexBot" renders as "gets bit", "GEX" as "gets/guess/gigs", "scalp" as
"sculp". Readings below are reconstructed through that noise.
**Synthesized:** 2026-08-06 [st-20nw]

### The GEX OrderFlow directional read ("cost of upside/downside lifted")

- **Positive (yellow) GEX OF spike** = "call gex" = **cost of upside lifted** —
  options above the level got more expensive *([01:00]–[02:00])*.
- **Negative GEX OF spike** = "put gex" = **cost of downside lifted** —
  downside options got more expensive *([03:00])*.
- "So we can say that gets [GEX] order flow is actually directional" *([04:00])*
  — GEX OF carries the direction; Convexity OF carries the regime (take/provide
  liquidity). Matches the canonical axis split (`../canonical/gex_profile.md`
  obs. 5).

### The reversal setup — two conditions plus two qualifiers

The trade Part 3 teaches *([23:00]–[25:00])*:

| Trend | Signal pair | Read |
|---|---|---|
| Trending **down** | Long-gamma spike (Convexity OF) + **put**-side GEX OF spike | Downside made expensive while liquidity is taken → **reversal up**, "perfect environment" |
| Trending **up** | Long-gamma spike (Convexity OF) + **call**-side GEX OF spike | Upside made expensive while liquidity is taken → **reversal down** |

Qualifiers Freddy repeats throughout:

1. **Meaningfulness** — the spike must be large "compared to the previous
   ones" *([04:00], [05:00])*. No numeric threshold given.
2. **Market structure** — there must be a trend to reverse; the same spike in a
   trendless tape means nothing *([02:00])*. "Be careful of the time of the day
   and the market structure" *([01:00])*.

This is **exactly jass's two-signal fade-entry rule**
(`../canonical/principal_discord.md` 2025-09-28: long gamma + put GEX spiking →
bid; long gamma + call GEX spiking → short) — published by jass five months
after this video. Freddy adds the meaningfulness and market-structure
qualifiers, which jass's statement leaves implicit.

### NEW — post-entry monitoring rule *([24:00]–[25:30])*

Not in Part 2, not in the principals' archive: **after entering the reversal,
watch Convexity OF for short-gamma (momentum) spikes in your new direction** —
liquidity being provided is the fuel that carries the reversal. Entry reads
long gamma (friction); follow-through reads short gamma (momentum). A
falsifiable two-stage claim worth its own Phase 2 test.

### The liquidity compression *([15:00]–[16:30])*

Freddy's Part 3 mnemonic, replacing Part 2's shaky MM-hedging story:

> markets are drawn to liquidity providers … the market likes to move away
> from liquidity takers

Long gamma = options bought = liquidity **removed** → price moves away /
reverses. Short gamma = options sold = liquidity **provided** → price is drawn
along / momentum. Note this sidesteps the Part 2 mechanism inversion entirely —
no MM hedging directions are asserted this time.

### Trade guidance *([17:00]–[18:30])*

- **Don't scalp ES**; NQ 15–30 ticks if scalping at all (restates Part 2).
- Preferred use: **wait for price to reach a key level** (Classic / GEX profile
  / options profile), *then* read OF to judge whether flow supports the trend
  or opposes it — level first, flow as the confirm. His nightly practice:
  screenshot the day's OF charts every evening for pattern study *([18:00])*.
- Windows restated: morning, event days (FOMC/CPI), last 5–10 minutes.

### Divergence flag — "cost lifted" vs vendor's "often call selling"

Freddy reads a positive GEX OF spike as upside options **bought** (cost
lifted, liquidity taken). The vendor's own docs
(`../canonical/orderflow_view.md`) say on SPX a positive GEX OF spike is
"**often call selling**" yet still "typically marks local tops". Same
operational read (positive spike near highs → top), different asserted flow
behind it. The vendor text wins tier-wise; the discrepancy is measurable
(gexoflow sign vs classified call volume) and is on the Phase 2 list.

### Confidence

- Reversal setup (two-signal + qualifiers): HIGH — independently confirmed by
  jass 2025-09-28 canonical rule
- Post-entry momentum-monitoring rule: MED — coherent with doctrine but
  single-source, unverified
- Liquidity provider/taker mnemonic: HIGH as vocabulary; mechanism-neutral
- "Cost lifted" flow attribution: LOW — conflicts with vendor's "often call
  selling"; measure before trusting either
