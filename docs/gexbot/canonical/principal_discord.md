# GexBot Principals — Discord Q&A

Canonical-tier archive of Discord posts authored by **GexBot's
principals**: Jasper ("Jass") and John Kirby. When a principal answers
a question directly in Discord, the *content* carries canonical weight
even though the *medium* is community.

## Why a separate file from `community/discord_quotes.md`

- `community/discord_quotes.md` archives posts by community members
  (Freddy Sarmiento, etc.). Authority signal: practitioner experience.
  Subject to Steve's "where canonical and community disagree, canonical
  wins" rule.
- This file archives posts by GexBot staff (Jasper, John). Authority
  signal: vendor. These statements are first-party doctrine; they take
  precedence over community interpretations.

When a community member quotes a principal in a Discord post (e.g.
Freddy paraphrasing Jasper), the verbatim quote goes in
`community/discord_quotes.md`. When a principal posts directly, it
goes here.

## Source rules

- **Channel and date are mandatory.** Discord posts mutate; the
  citation must let a future reader find the original.
- **Speaker role tag preserved.** Discord usually labels principals
  with role icons (`@jass`, `@johnkirby`). Capture verbatim.
- **Quote verbatim.** Don't paraphrase; commentary goes below the
  quote.
- **Q&A format preserved.** When the post is a reply to a community
  question, the question is included for context (with the asker's
  handle), but the canonical content is the principal's answer.

---

## 2025-XX-XX — Jasper, on GEX vs gamma ladder disambiguation

**Channel:** GexBot Discord (channel not captured in source paste; likely #theory-questions based on subject matter)
**Date:** not captured in source paste (Steve to confirm)
**Speakers:** Freddy Sarmiento `[PP]` (question) → Jasper "Jass" + John Kirby tagged (Jasper answered)

### Q (Freddy Sarmiento)

> Good mng. @jass , @johnkirby — I've been reviewing the GexBot docs and looking back at previous trading sessions, and I came across something that I'm having trouble fully understanding.
>
> I noticed the 21,835 long call in the options profile, which is graphically displayed in the GEX profile with an excess of green gamma (which makes sense to me). However, right above it, there are two short calls — which should have negative gamma — but in the GEX profile, they're still showing up as green. ??
>
> I was expecting to see some excess of red gamma instead.

### A (Jasper)

> the "gex" profile is netted out calls vs puts, ignoring long/short.
> the purple/cyan ladder "gamma" is long/short contracts, ignoring call/put
>
> call/put gex → measure of directional (up/down) convexity
> long/short gamma → measure of momentum/reversion (continuation or fade)

### Disambiguation summary

This Q&A resolves a confusion latent in the vendor docs: GexBot ships
**two ladders that both visualize gamma but on orthogonal axes**.

| Ladder | Netting axis | Visualization | Operational question |
|---|---|---|---|
| **GEX profile** (green/red) | Calls vs puts (ignores long/short) | Green = call gex imbalance, Red = put gex imbalance | "What direction does the *convexity* point — up or down?" |
| **Gamma ladder** (purple/cyan) | Long vs short contracts (ignores call/put) | **Cyan = long gamma, Purple = short gamma** (confirmed by Jasper in the second Q&A below) | "Will dealer hedging *amplify* moves or *fade* them?" |

The two readings answer two different questions and should not be
substituted for each other. Freddy's confusion came from reading
long/short into the GEX profile (which doesn't carry that information).
The short calls he noticed *are* visible in the GEX profile, but as
*call gex* (green) — because the GEX axis is call-vs-put, not
long-vs-short. To see the short-ness of those calls, switch to the
gamma ladder.

### Why this matters operationally

- **GEX profile reads** ([`gex_profile.md`](gex_profile.md)) → use for: identifying targets (high call gex = upside magnet, high put gex = downside magnet), defining intraday regime (call-heavy vs put-heavy day)
- **Gamma ladder reads** ([`convexity_ladder.md`](convexity_ladder.md)) → use for: predicting whether a move at a given strike will be amplified (negative customer gamma = dealer short gamma = forced-buy-into-rises = momentum/squeeze) or faded (positive customer gamma = dealer long gamma = forced-buy-into-drops = mean reversion)

A trade decision typically wants both: GEX profile to pick the *level*
(where to act), gamma ladder to predict the *behavior at that level*
(continuation vs reversion).

### Cross-references

- [`gex_profile.md`](gex_profile.md) — the call-vs-put netting axis
- [`convexity_ladder.md`](convexity_ladder.md) — the long-vs-short netting axis (and the vol-regime modulation that further conditions the behavior)
- [`metrics_math.md`](metrics_math.md) — the formulas behind both: GEX = `100 × γ × OI × spot² × 1%` per strike (sign by call/put), gamma ladder uses the same number but signed by customer-long vs customer-short

### Date follow-up

The date of this Q&A was not captured in the source paste. Steve to
confirm; once nailed down, the heading date should be updated.

---

## 2025-XX-XX — Jasper, on reading distributed negative convexity

**Channel:** GexBot Discord (channel not captured)
**Date:** not captured in source paste (Steve to confirm)
**Speakers:** unattributed asker (referencing the convexity-ladder
metrics-card text) → Jasper "Jass"

### Q

> So I read thru' metrics card for Convexity Ladder.. It says
>
> *Significant and well-distributed negative convexity: We are trading
> in liquid markets as traders are happy to sell options. (Concentrated
> negative convexity is a clear exception.)*
> *Significant and well-distributed positive convexity: Indicates an
> elevated and well-informed expectation of volatility. We typically
> see this prior to days with event-driven volatility.*
>
> Is there a visual that explains how a Significant and
> well-distributed negative convexity looks? Trying to understand when
> to worry about the purple lines and when to ignore them.

### A (Jasper)

> i think we're juts always eyeballing long gamma (cyan) for poor liq
> (possible reversion) zones, and purple is more a… after thought-ish?
>
> like for SPX, rather see it all short gamma above (liquidity
> providing) for long continuation

### What this confirms / corrects

**Color mapping (correction of the prior table).** The first Jasper Q&A
in this file just said "the purple/cyan ladder" without specifying
which color was which. I (the synthesizer) initially guessed
purple=long, cyan=short. This Q&A overrides that guess:

| Color | Side |
|---|---|
| **Cyan** | Long gamma |
| **Purple** | Short gamma |

That correction has been propagated to the disambiguation table above
and to the cross-references in `gex_profile.md` and `convexity_ladder.md`.

### Operational guidance from Jasper (his own practice)

- He leads with the **cyan (long gamma)** lane when scanning — that's where he expects "poor liquidity (possible reversion)."
- He treats the **purple (short gamma)** lane as "more an afterthought." Operationally secondary.
- For a long SPX continuation trade, his preferred setup is **short gamma above** (purple stack above spot) — described as "liquidity providing."

These are practitioner reads from a principal, not a vendor-spec rule.
Treat as how Jasper-the-trader uses the ladder, not as a definition of
what the ladder means.

### Customer-vs-dealer perspective: flagged ambiguity

Jasper's reversion/continuation mapping reads naturally from a *dealer*
perspective:
- *Dealer long gamma* (stabilizing limit-buys below + limit-sells above) → reversion ✓
- *Dealer short gamma* (forced to chase moves) → amplification/continuation ✓

But the canonical [`convexity_ladder.md`](convexity_ladder.md) text
defines the ladder from a *customer* perspective: "Long calls and long
puts represent long customer gex." Customer-long is the inverse of
dealer-long.

Two interpretations remain:
1. The gamma ladder plots **dealer perspective**, and "long customer
   gex" in the convexity_ladder.md text is describing *which side
   originated the position*, not how the ladder colors it. Under this
   reading Jasper's terminology is internally consistent and the
   ladder color = dealer side.
2. The gamma ladder plots **customer perspective** (literally), and
   Jasper's casual "long gamma → reversion" is using dealer-side
   trading vocabulary applied to customer-side ladder colors — same
   words, opposite signs.

We don't have a clean canonical statement disambiguating these.
Operationally it doesn't matter much because the *behavior* (cyan zones
are reversion-y, purple zones are continuation-y) is captured by
Jasper. But the perspective question is worth posing to Jasper directly
if a future opportunity arises.

### Cross-references

- The disambiguation table at the top of this file (corrected)
- [`gex_profile.md`](gex_profile.md) observation 5 (color mapping corrected)
- [`convexity_ladder.md`](convexity_ladder.md) observation 7 (color mapping corrected)

## Revision log

- 2026-05-22: File created with Jasper's GEX-vs-gamma-ladder
  disambiguation Q&A as the first entry. Pattern: canonical-tier
  Discord archive paralleling `community/discord_quotes.md` for
  community-tier voices.
- 2026-05-22: Second Jasper Q&A added (distributed neg convexity visual
  question). Corrected the gamma-ladder color mapping (long=cyan,
  short=purple) — my earlier guess was inverted. Surfaced the
  customer-vs-dealer perspective ambiguity as unresolved.
