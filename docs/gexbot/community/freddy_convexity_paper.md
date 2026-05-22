# Freddy Sarmiento — "Understanding the Convexity Ladder" paper

**Source PDF:** [`papers/freddy_convexity_ladder.pdf`](papers/freddy_convexity_ladder.pdf)
**Title:** "Understanding the Convexity Ladder and Its Role in Market Structure"
**Author:** Freddy Sarmiento (community)
**Date:** undated; predates 2025-02-21 (referenced in the Guido/Jasper
Q&A thread on that date)
**Length:** 3 pages

This is **the paper** Guido was citing in the `canonical/principal_discord.md`
2025-02 Q&A thread ("read the 3rd attachment", "Point 4 Practical
Trading Applications Strategy 1, ... When in negative gamma"). All of
Guido's section/point numbers map directly to the structure below.

## Vocabulary warning — MM-talk per Jasper's deprecation note

The paper uses **market-maker perspective** language throughout
("Market Makers are Long Gamma," "MMs Short Gamma"). In a 2025-02-21
Discord exchange ([`../canonical/principal_discord.md`](../canonical/principal_discord.md))
Jasper explicitly stated GexBot's canonical convention is
**customer perspective** and added: "I'm going to ask Fredy to change
this language." As of the latest version of this PDF that change has
**not** been applied.

Translation table (paper → canonical):

| Paper language | Canonical equivalent | Ladder color |
|---|---|---|
| "MMs are Long Gamma" / "Positive Gamma" environment | Customers net short gamma (purple); MM is on the long side of the matched book | Purple-heavy chain |
| "MMs are Short Gamma" / "Negative Gamma" environment | Customers net long gamma (cyan); MM is on the short side | Cyan-heavy chain |
| "Positive gamma zones" (at the strike level) | Customer long gamma at the strike = cyan bars | Cyan |
| "Negative gamma zones" (at the strike level) | Customer short gamma at the strike = purple bars | Purple |

When Freddy says "MMs are Long Gamma → buy on drops, sell on rises →
stabilizing," that's textbook for the MM side. In customer-perspective
language: customer-short-gamma zones (purple) get stabilized by MM
long-gamma hedging — but only in the *declining-vol* regime per the
canonical convexity_ladder.md vol-regime modulation table.

Read the substance through the canonical lens. Don't carry forward
MM-talk into new writing — Jasper's request to standardize on
customer-perspective makes the paper's vocabulary the deprecated
version.

## Per-section summary

### 1. What is the Convexity Ladder?

Vendor-aligned definition. The ladder visualizes distribution of
options gamma by strike. Two trading rules-of-thumb stated:

- Positive gamma zones → price slows down
- Negative gamma zones → price speeds up

This is consistent with canonical [`../canonical/convexity_ladder.md`](../canonical/convexity_ladder.md)
under the *declining-vol* regime (the common case). The paper doesn't
make the regime-dependence explicit at this point but addresses it in §2.

### 2. The two market environments

#### A. Declining vol (more common)

Paper: "Market Makers are Long Gamma (Positive Gamma)." They buy on
drops, sell on rises, acting as a stabilizing force.

Translated: in a declining-vol environment, the bulk of MM gamma
positioning is on the long side (= customers net short gamma overall).
The MM hedging behavior produces the "braking effect" on price at
gamma-heavy strikes.

Speed-bump analogy:
> Imagine driving on a highway with strong speed bumps (positive gamma).
> Your car will slow down as you pass each one, making it harder to
> accelerate. But once you pass into a smooth road (negative gamma
> zone), your car speeds up.

Operational takeaways from the paper:
- Positive gamma zones → mean-reverting behavior
- Negative gamma zones → momentum-driven moves

#### B. Rising vol

Paper: "Market Makers are Short Gamma (Negative Gamma)." They sell on
drops, buy on rises, amplifying market moves.

Translated: in a rising-vol environment, MM gamma is net short (=
customers net long). MM hedging amplifies rather than dampens, leading
to violent swings.

Downhill-with-no-brakes analogy:
> A steep downhill road (negative gamma) with no brakes on your car…
> When you reach a flat road (positive gamma), your speed stabilizes.

Operational takeaways:
- Negative gamma zones → violent price swings
- Positive gamma zones → price consolidates

This matches the canonical polarity-flip in
[`../canonical/convexity_ladder.md`](../canonical/convexity_ladder.md)
observation 2 exactly: the wall-vs-passage role flips when vol regime
flips.

### 3. Transition points

Where gamma flips from positive to negative across strikes = pivot
points where market structure shifts.

- Transitioning **positive → negative gamma** (going from a slowing
  zone to an accelerating zone) → volatility expansion, trending move
  starts
- Transitioning **negative → positive gamma** (entering a stalling
  zone) → mean reversion, volatility compression

This is the canonical "transition points = pivots" observation from
`convexity_ladder.md` observation 6, with operational guidance about
which direction of transition produces which behavior.

### 4. Practical trading applications

Three strategies:

**Strategy 1 — Trend trading in negative gamma environments**
- Negative gamma → explosive price moves → trend-following works
- Breakouts more reliable; momentum trading favored

**Strategy 2 — Mean reversion in positive gamma environments**
- Positive gamma → controlled price movement
- Fading breakouts is high-probability; price snaps back to mean

**Strategy 3 — Trading the transition zones**
- Positive→negative transition → prepare for trend acceleration
- Negative→positive transition → prepare for volatility compression

## How this slots vs other Strader docs

- **Canonical baseline**: [`../canonical/convexity_ladder.md`](../canonical/convexity_ladder.md) (vendor-authored). The vol-regime modulation table is the rigorous version of Freddy's §2.
- **Operational two-line rule** (Jasper, 2025-02-21): "Pivot at customer long gamma (cyan), move through customer short gamma (purple). That's all you really need." Lives in [`../canonical/principal_discord.md`](../canonical/principal_discord.md). Freddy's three strategies are the elaborated version of this rule.
- **Mechanism docs**: [`../canonical/gamma_vanna_video.md`](../canonical/gamma_vanna_video.md) covers WHY MM hedging stabilizes (when long gamma) or amplifies (when short gamma). The mechanism Freddy invokes in his §2 is documented canonically there.
- **Freddy's other methodology**: [`freddy_methodology.md`](freddy_methodology.md) covers his entry mechanics, time-compression read, and the two trade-pattern archetypes. This paper covers the regime-level read that sits above those tactics.

## What this paper adds that isn't elsewhere

1. **The speed-bump / highway analogy** — a complement to the Lamborghini analogy in `freddy_methodology.md §1`. Two analogies for the same convexity concept; pick whichever fits the audience.
2. **The three trading strategies (§4)** — explicit operational packaging of the regime read into actionable rules. Useful as a teaching scaffold.
3. **Explicit transition-direction asymmetry (§3)** — positive→negative produces volatility expansion; negative→positive produces compression. Canonical observation 6 only says transition points are pivots; this paper adds the directional asymmetry.

## What this paper gets wrong (or muddies)

1. **MM-perspective vocabulary** — Jasper has flagged this for deprecation. Read through the translation table above.
2. **Section 1 statement** "Positive Gamma zones = Price movement slows down" / "Negative Gamma zones = Price movement speeds up" is presented as universal. It's only true in the *declining-vol* regime. §2 addresses this but readers who stop at §1 will carry a false universal rule.
3. **Conflation of environment-level positioning with strike-level positioning.** "MMs are Long Gamma (Positive Gamma)" describes the OVERALL regime; "positive gamma zones" describes per-strike concentration. Freddy uses the same word "positive gamma" for both. Causes the Guido-style confusion documented in `../canonical/principal_discord.md`.
