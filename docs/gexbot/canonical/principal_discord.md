# GexBot Principals — Discord Q&A

Canonical-tier archive of Discord posts authored by **GexBot's
principals**: Jasper ("Jass") and John Kirby. When a principal answers
a question directly in Discord, the *content* carries canonical weight
even though the *medium* is community.

**Identity note — John M ≠ John Kirby.** "John M" is a separate
identity: a community contributor with no GexBot staff role. His
sustained Q&A is preserved at
[`../community/expert_qa.md`](../community/expert_qa.md) — community
tier, not canonical. Treat any "John M" speaker tag as community
unless the Discord role icon explicitly shows a GexBot staff role.
This file holds only Jasper and John Kirby principal posts.

## Why a separate file from `community/discord_quotes.md`

- `community/discord_quotes.md` archives shorter community posts and
  quotes. Authority signal: practitioner observation.
- `community/expert_qa.md` archives sustained Q&A by John M (community
  contributor). Authority signal: practitioner experience and
  recognized community standing — but NOT vendor authority.
- This file archives posts by GexBot principals (Jasper, John Kirby).
  Authority signal: vendor. These statements are first-party doctrine;
  they take precedence over community interpretations (including over
  John M's community-tier Q&A) per Steve's "where canonical and
  community disagree, canonical wins" rule.

When a community member quotes a principal in a Discord post (e.g.
Freddy paraphrasing Jasper), the verbatim quote goes in
`community/discord_quotes.md`. When John M answers, it goes in
`community/expert_qa.md`. When a principal posts directly, it goes
here.

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
| **Gamma ladder** (purple/cyan) | Long vs short contracts (ignores call/put) | **Cyan = long gamma = positive convexity, Purple = short gamma = negative convexity** (per John Kirby 2025-02-21 8:04 AM, the gamma-ladder colors are an exact relabeling of the canonical "positive/negative convexity" terms in [`convexity_ladder.md`](convexity_ladder.md)) | "Will dealer hedging *amplify* moves or *fade* them?" |

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

### Customer-vs-dealer perspective: RESOLVED

I initially flagged a customer-vs-dealer perspective ambiguity here.
**It's resolved by the three-Q&A exchange that ran on 2025-02-21**:
two community-tier Q&As (Guido + John M, now archived in
[`../community/expert_qa.md`](../community/expert_qa.md)) plus the
Jasper closing entry below. The ladder is **customer perspective**
throughout. Jasper's "long gamma → reversion" is reconciled via
vol-regime modulation (positive convexity stalls in falling vol;
that's what produces the reversion at cyan levels) — not via a
perspective flip.

The operational rule Jasper gave to close the question:

> We pivot at customer long gamma, but move through customer short
> gamma. That's all you really need.

For the full exchange: see the Guido + John M entries in
[`../community/expert_qa.md`](../community/expert_qa.md), then the
Jasper closing entry immediately below.

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
- 2026-05-22: Three more Q&As added (entries 3, 4, 5 — Guido asking +
  GexBot staff answering + John M confirming + Jasper closing) that
  RESOLVE the customer-vs-dealer ambiguity. Convention: always think
  customer-perspective. Operational rule: pivot at cyan (customer long
  gamma), move through purple (customer short gamma). Annotated GexBot
  screenshot added to `images/customer_long_short_gamma_annotated.jpg`.
  Jasper indicated he'll ask Freddy to deprecate MM-perspective
  language; a vocabulary note has been added to community/freddy_methodology.md.
- 2026-05-22: Entry 6 added — John Kirby's 2025-02-21 8:04 AM post
  giving the gamma↔convexity equivalence. Three labels (long gamma /
  cyan / positive convexity) all refer to the same ladder positions.
  Resolves the strike-level "positive gamma" terminology in Freddy's
  paper. Top disambiguation table updated to carry the equivalence.
- 2026-05-22: Entry 7 added — Jasper 2025-03-05 2:59 PM. Two
  confirmations: (a) net convexity is more reliable for MM-reaction
  prediction than call/put alone (with "both views have value"
  caveat); (b) NET GEX IS CUSTOMER PERSPECTIVE, not MM. The
  customer-perspective convention now formally extends to the GEX
  profile, not just the convexity ladder. gex_profile.md updated to
  carry this explicitly.
- 2026-05-22: Entry 8 added — John Kirby 2025-03-27 11:01-11:05 AM
  Q&A with TommyCirj. Two takeaways: (a) Net OI correlates with gamma
  all-else-equal but gamma also depends on price/time/vol — counting
  contracts alone is inadequate; (b) GexBot's orderflow-classification
  approach is fundamentally different from naive Call OI − Put OI
  vendors. Plus TommyCirj's useful pedagogical framing: dealer-long-
  calls and dealer-long-puts differ in initial hedge setup (short vs
  long stock) but produce IDENTICAL dynamic hedging (sell on rises,
  buy on drops = stabilizing) — useful corrective to Freddy's
  mechanism inversion in OrderFlow Part 2.
- 2026-05-22: Entry 9 added — John Kirby 2025-04-04 Q&A with
  stockholm. Documents a FAILURE MODE of the pivot-at-gamma-levels
  rule: sustained directional pressure in a put-dominated regime can
  overwhelm dealer hedging. Three operational points: (a) gamma rules
  presume dealer hedging is dominant flow, not always true; (b)
  put-selling-above-spot at very high IV is often a HEDGE for short
  futures, not bullish positioning; (c) worked example — ES $5237
  puts sold at 9:50 AM, broken through by 10:15. Plus the Freddy
  channel URL is captured: youtube.com/@gextrading.
- 2026-05-22: Entry 10 added — Jasper 2025-04-09 4:30 PM Q&A with
  Andy. Compresses the regime rule into a default+exception form:
  for 0DTE, falling-vol regime is *almost always* the default, so
  the canonical pivot-at-long-gamma rule applies most days. Exception
  is pre-event sessions (CPI/FOMC/NFP) where rising vol flips long
  gamma into a breakout trigger. Plus a live trade narrative showing
  the rule getting updated mid-session ("revving long 216 tho due
  to incoming 50 minute algo"). Two follow-up flags: what is the
  50-minute algo; what is the state-degens channel.
- 2026-05-22: Entry 11 added — John Kirby 2025-04-21 8:19 AM. Large
  increase in ITM call buying = "one of my favorite signals" for
  support. Mechanism: ITM calls have high delta (0.7-1.0) so MM hedge
  size is proportionally larger than OTM, creating stronger structural
  support per contract. Distinct sub-case of the cyan-bar rule —
  ITM long gamma > OTM long gamma for support force.
- 2026-05-22: Entry 12 added — Jasper 2025-04-22 8:07 AM. Mechanics
  of "max change gex" — updates every second; values are lookbacks
  since the ladder has no time axis. Flagged as a UI feature not
  otherwise documented in our canonical files; likely a freshness
  filter analogous to OrderFlow spike concept. First [GOLD]-tagged
  asker seen — subscriber tag note added.
- 2026-05-22: Entry 13 added — Izzy Q&A 2025-05-14/15 with John M
  responses. Substantial exchange with three annotated graphics.
  FOUR new patterns documented: (1) "Double warning" = Calls Sold +
  Puts Bought at same level → bearish resistance; (2) "Bullish-Above/
  Bearish-Below" = Calls Bought + Puts Bought at same level (or its
  inverse) → clean pivot; (3) "Initial Point of Reversion" mechanism
  — positive gamma stalls via profit-taking expectation, not just MM
  hedging (explicit "this is the theory"); (4) Cross-day persistence
  — gamma walls from prior session can carry over (5/13 → 5/14
  worked example). Also captures the operational workflow: 15-20 min
  post-open Options screenshot for markup → identify patterns →
  toggle to Gamma view for confirmation. Implicitly resolves Izzy's
  concern that gamma-filter loses info: use BOTH views, gamma is the
  confirmation layer not the primary read.
- 2026-05-23 (bead st-9w0): New canonical entry appended — Jasper
  2025-10-17 10:45 AM Q&A with T46. **"Literally all i do"** —
  Jasper compresses his entire trading method to a two-case
  decision tree: rising vol → continuation at long gamma; falling
  vol → reversion at long gamma. Restatement and reinforcement of
  the 2025-04-09 regime rule of thumb (this is now doctrinally
  stable across 6+ months of Discord). The meta-claim that "all of
  it" is this rule has structural implications: all other canonical
  infrastructure (Classic vs State, max-change-gex, vol surface,
  GEX axes) exists to inform two decisions — regime and level.
  Reconfirms falling-vol as the 0dte default.
- 2026-05-23 (bead st-dsz): New canonical entry appended combining
  TWO sequential Jasper threads — pensivelion 2025-09-29 9:45 PM
  and Browniver 2025-10-01 1:05 PM. **GEX vs gamma canonical
  definitions** restated and sharpened: GEX = net deltas (call/put
  axis); gamma = net vol (long/short axis). **Repudiation of the
  naive "paper buys puts, sells calls" assumption** — useless for
  0dte/intraday. **Classic vs State product distinction**: Classic
  = naive volume increment per contract; State = trade-classified
  signed volume (e.g. +50 lots bought, −25 lots sold) using a vol
  surface as reference. **Operational corollary**: Classic profile
  shape is structurally biased (calls fill upside, puts fill
  downside) because the naive assumption bakes in; State preserves
  actual positioning. **Regime trading via State** — long-vol regime
  → hotter tape; short-vol → grind. "Even for futures" caveat:
  options regime predicts ES behavior. Two new role tags first seen:
  `[end]` (pensivelion), `[PHUB]` (Browniver).
- 2026-05-23 (bead st-o4i): New canonical entry appended — Jasper
  2025-09-28 2:49 PM Q&A with vqz `[MATH]`. The **two-signal
  fade-entry rule**: long gamma spike + downside (put) GEX spike →
  bid for reversion UP; long gamma + upside (call) GEX → short for
  reversion DOWN. Sharpens the canonical pivot-at-long-gamma rule by
  adding trade direction via the directional-GEX read. Mechanism:
  "making it expensive = stepping in for reversion." First `[MATH]`
  role-tag asker observed; added to the role-tag context-cue set
  alongside `[PP]` and `[GOLD]`. No graphics in source thread.
- 2026-05-23 (bead st-zv6): New canonical entry appended — Jasper
  2025-07-25 11:32 AM–11:58 AM exchange with aigonewrong. Three
  doctrinal payloads: (a) reading net DEX across BOTH call and put
  sides to infer vol regime; (b) the convexity-dump-then-ramp
  pattern (lift → dump → ramp three-phase); (c) the operational rule
  "those are the best longs tho. there's juice to lean on" — when
  customer convexity gets dumped, the resulting position state is a
  structurally supported long setup, with dealer hedging as the cause
  of the directional follow-through. Two graphics archived in
  `images/`: aigonewrong's NDX/SPX orderflow comparison + Jasper's
  SPX convexity dump-ramp chart. First entry to use the "principal's
  emoji reaction is canonical-confirming" attribution convention
  (Steve 2026-05-23) — aigonewrong's 11:58 AM follow-up confirmed
  via Jasper 👍 reaction. Includes operational tests for the
  measurement framework (lift-dump detection thresholds, forward-
  returns vs baseline).
- 2026-05-23 (bead st-62v): Entries 3, 4, 9, 13 re-tiered and moved to
  [`../community/expert_qa.md`](../community/expert_qa.md). Reason:
  speaker is "John M" — a community contributor with no GexBot staff
  role, NOT John Kirby (GexBot principal). Earlier drafts equated the
  two names; Steve confirmed they are distinct identities on
  2026-05-23. Channel attribution corrected to `#theory-questions`
  for the moved entries. Cross-references in remaining entries updated
  to point to the new community-tier file. Identity-note added to file
  header. Note: entries 6 (John Kirby gamma↔convexity), 8 (John Kirby
  Net OI), and 11 (John Kirby ITM call) retain canonical tier — they
  are John Kirby principal posts; the "John M" alias previously
  attached to entry 11's speaker line was removed as inaccurate.

---

## 2025-02-XX — Closing exchange, customer-perspective convention

**Channel:** GexBot Discord (channel not captured)
**Date:** same thread as above (2025-02-21 or shortly after)
**Speakers:** Guido (community) → unattributed GexBot staff (likely
**Jasper** — "my docs" phrasing + referring to John in the third
person + the authority to deprecate Freddy's language)

### Q (Guido)

> To be precise, if "market makers are Long Gamma", means violet bars
> for us?

### A (likely Jasper)

> I'm going to ask Fredy to change this language.
>
> Yes technically violet bars would indicate MM long gamma.
>
> But there's a reason we don't think in terms of MM — everything is
> in terms of customer. That's what you'll find if you read my docs.
>
> John's diagram is correct. We pivot at customer long gamma, but
> move through customer short gamma. That's all you really need.

### What this establishes — the canonical operational rule

This is the most operationally compressed canonical statement we have
about the gamma ladder. Three things land here:

1. **Convention: customer perspective only.** "We don't think in terms
   of MM — everything is in terms of customer." If a community source
   talks about MM-long-gamma or MM-short-gamma, that's their own
   conversion; the *canonical* axis is customer.
2. **Freddy's MM-perspective vocabulary is being deprecated.** Jasper
   explicitly says "I'm going to ask Fredy to change this language."
   Freddy's videos and Discord posts use MM-perspective language
   freely; canonical convention will be customer-perspective going
   forward. A vocabulary note has been added to
   [`../community/freddy_methodology.md`](../community/freddy_methodology.md).
3. **The two-line operational rule:**

   > **Pivot at customer long gamma (cyan).**
   > **Move through customer short gamma (purple/violet).**
   > That's all you really need.

   This is the cleanest canonical statement of the gamma ladder's
   trading meaning we have. It compresses everything in
   [`convexity_ladder.md`](convexity_ladder.md) (vol-regime modulation,
   distribution shape, transition points as pivots) into a two-line
   default heuristic.

### Why this resolves the perspective ambiguity in entry 2

In the second Q&A on this page I flagged a customer-vs-dealer
perspective question as unresolved. This exchange resolves it: the
ladder is **strictly customer perspective**, and any apparent
contradiction with dealer-side intuition is bridged by vol-regime
modulation, not by switching axes.

Jasper's "long gamma (cyan) for poor liq (possible reversion) zones"
in the second Q&A is consistent with this entry's rule: customer long
gamma = pivot = price reverts at the level = poor liquidity (price
doesn't spend volume there because dealers' offsetting positions
absorb the order flow).

Jasper's "short gamma above for long continuation" (also from entry 2)
is consistent with "move through customer short gamma": for a long
trade to continue upward, you want purple bars above so price has
room to move through them.

---

## 2025-02-21 8:04 AM — John Kirby, gamma ↔ convexity equivalence

**Channel:** GexBot Discord, #theory-questions (same thread as the
Guido + John M community-tier exchange now archived in
[`../community/expert_qa.md`](../community/expert_qa.md))
**Date:** 2025-02-21 8:04 AM (9 minutes after John M's prior post in
the community-tier thread — distinct authors, names happen to match)
**Speakers:** community asker (likely Guido — same thread) → John
Kirby (Moderator, GexBot principal — NOT to be confused with John M
who answered the prior posts)

### Q (community asker)

> Thank You! It would help to mention that in the context of this
> paper a "Positive gamma zone" is the same as long gamma (which is
> cyan). Fredy wrote positive gamma, but he ment long gamma. Besides
> that, the paper is great!

### A (John Kirby)

> Call/Put gamma imbalance (green/red on gex profile)
> Long/Short gamma (cyan/purple on convexity ladder). This is the
> same as the Positive/Negative convexity I refer to in the docs.

### Why this matters — the canonical equivalence

John gives us the cleanest dual-axis canonical statement we have. Two
things land:

1. **The two-axis structure restated** (now confirmed by both
   principals — Jasper in the GEX-vs-gamma-ladder disambiguation
   entry and the closing customer-perspective entry, John here):
   - GEX profile axis = call vs put = green/red
   - Gamma ladder axis = long vs short = cyan/purple
2. **The gamma↔convexity equivalence — NEW.** John explicitly equates
   the gamma-ladder colors with the vendor docs' "positive/negative
   convexity" terms:

   | Gamma ladder color | Gamma label | Convexity label |
   |---|---|---|
   | Cyan | Long gamma | Positive convexity |
   | Purple | Short gamma | Negative convexity |

   These three labels refer to the **same thing**. The docs use
   "convexity" with sign; the UI labels use "gamma" with side; both
   resolve to the same ladder, the same colors, the same positions.

### What this resolves for Freddy's paper

The asker proposed an inline correction for Freddy's paper: "positive
gamma zone = long gamma (cyan)." John's reply confirms the
equivalence. So Freddy's "positive gamma" terminology in the paper IS
canonical — it just maps through:

> "positive gamma" (Freddy paper) = long gamma (UI) = cyan (color) = positive convexity (vendor docs)

All four phrases refer to the customer-long zones. This SHOULD have
been spelled out in the paper but wasn't. A reader who keeps the
equivalence in mind can read Freddy's paper without getting confused.

### Lingering nuance — environment vs strike-level positive gamma

Freddy's paper still uses "Positive Gamma" at two different scopes:
1. **Environment level** — "Declining vol environment: MMs are Long Gamma (Positive Gamma)" describes overall market positioning
2. **Strike level** — "positive gamma zones" describes per-strike concentration

John's equivalence resolves the strike-level usage (positive gamma at strike = long gamma at strike = cyan = positive convexity at strike). The environment-level usage is a separate issue — Freddy is using MM-talk for environment classification, which Jasper has already flagged for deprecation in the closing-exchange entry above.

---

## 2025-03-05 2:59 PM — Jasper, net convexity vs call/put + GEX is customer-perspective

**Channel:** GexBot Discord (channel not captured)
**Date:** 2025-03-05 (Jasper's second response is timestamped 2:59 PM)
**Speakers:** unattributed asker → Jasper "jass" (two responses)

### Q (asker)

> It seems like net convexity is a better indicator for the MM
> reaction to gex than call/put?
> The put gamma levels do not need to be always act as pivot points
> or as pinning points. But the net gamma for long and short do that
> more consistently?
>
> Also the net GEX is the market participant's net GEX view right? not MM?

### A1 (Jasper)

> yes well imo at least. there's a case for both

### A2 (Jasper, 2:59 PM — direct reply to the customer-perspective question)

> correct

### What this confirms

1. **Net convexity (long/short axis) > call/put alone for MM-reaction
   prediction.** Jasper agrees with the asker's read: aggregating to
   long/short produces more consistent pivot/pin signals than reading
   call vs put concentrations alone. *But* he caveats "there's a case
   for both" — the GEX profile carries directional convexity
   information the gamma ladder doesn't, so both views remain useful.
   The operational implication: **lead with the gamma ladder
   (cyan/purple) when looking for pivot levels; use the GEX profile
   (green/red) for directional convexity bias.**
2. **Net GEX is customer perspective, NOT MM perspective.** Jasper
   directly confirms with "correct." This extends the
   customer-perspective convention (already established for the
   convexity ladder in the closing-exchange entry above) to the GEX
   profile as well. **Both
   visualizations are customer-perspective.** Any MM-perspective read
   requires inverting the sign.

### Operational implications

- **Read order for finding pivot/pin levels:** start with the gamma
  ladder. Cyan bars are the most reliable pivot signals (per Jasper's
  agreement here + the closing-exchange entry's "pivot at customer
  long gamma"). The GEX
  profile is the *complement*, not the primary lens, for pivot
  identification.
- **Reading the GEX profile:** sign convention is customer side. A
  green spike at a strike = customer net-long call exposure there =
  customer is positioned for upside at that strike. Red spike = the
  symmetric down-side put position.
- **Why "both views have value" matters:** John's earlier statement
  in the gamma↔convexity-equivalence entry above gave the equivalence
  — long gamma = positive convexity at strikes. Jasper is now saying
  that despite the equivalence at the
  per-strike level, the *aggregation* (net long/short vs net call/put)
  produces different signals across the chain. The gamma ladder's
  long/short net is the smoother indicator of where price will *react*
  ; the GEX profile's call/put net is the directional bias indicator.

### Why this matters for our measurement framework

The canonical sign convention for GEX is now nailed down. When we
compare our corpus-derived GEX readings against expected behavior, we
should anchor on:

- A positive call-gex spike → customer-long-calls concentration → bullish positioning at strike
- A negative put-gex spike → customer-long-puts concentration → bearish positioning at strike
- Customer flow drives the sign; dealer behavior is the consequence

The asker's specific claim ("put gamma levels do not always act as
pivots") is now operationally justifiable: pivots come from the
*aggregate* gamma exposure at the strike, not from the put-side
contribution alone. A strike with heavy put gex but offsetting call
gex may not pivot.

---

## 2025-03-27 11:01–11:05 AM — John Kirby, Net OI as gamma proxy + competitor approach

**Channel:** GexBot Discord (channel not captured)
**Date:** 2025-03-27 11:01 AM (first exchange) → 11:05 AM (closing)
**Speakers:** TommyCirj (community) ↔ John Kirby (Moderator)

### Q1 (TommyCirj, 11:01 AM)

> If we were to know the Net OI at a given strike, would the larger
> the volume/OI suggest larger gamma exposure?

### A1 (John Kirby, 11:01 AM)

> All else equal, yes. But gamma depends on price, time, and
> volatility. So its complicated.

### TommyCirj follow-up (11:03 AM)

> yes. I have seen a lot of companies basically look at Call OI -
> Put OI = positive/negative gamma, which then create a gex profile
> of only negative gamma essentially below and positive gamma above
> a particular midpoint
>
> where as yes long gamma means dealers are long, although they
> would be selling the underlying if they were long calls and
> buying the underlying if they were long puts
>
> what I am trying to find is a profile that depicts that flow

### A2 (John Kirby, 11:05 AM)

> yea, well you found it.

### What this establishes

#### 1. Net OI is a partial gamma proxy

John confirms volume/OI does correlate with gamma exposure
*all-else-equal*, but immediately caveats: **gamma is a function of
price, time, and volatility, not just OI**. This echoes the
`metrics_math.md` "how many" ladder:

- Open interest (gold standard, T+1 OCC tallies)
- Volume (intraday proxy, gross)
- Orderflow classification (GexBot's edge — net imbalance, not gross flow)

OI alone tells you "how many contracts." To get to gamma you also need
the Greeks at that strike — which depend on the underlying price,
time-to-expiry, and IV.

#### 2. GexBot vs the naive Call OI − Put OI approach

TommyCirj describes what *other vendors* do: compute `Call OI − Put OI`
at each strike and label the result as positive/negative gamma. This
produces a profile where everything below a midpoint is "negative
gamma" and everything above is "positive gamma." The polarity is
forced by the midpoint, not derived from positioning.

John's "yea, well you found it" implicitly endorses GexBot's approach
as the correct alternative. GexBot's orderflow-classification model
(see [`metrics_math.md`](metrics_math.md) "Orderflow Classification")
identifies *who originated the position* — the customer-long vs
customer-short distinction — instead of imposing a polarity from
strike location. The naive approach can't distinguish "long call at
strike X" from "short call at strike X" since both contribute
identically to call OI.

#### 3. Dealer-long-call vs dealer-long-put — same dynamic hedge, different initial setup

TommyCirj's framing is pedagogically useful: **dealer long gamma**
exists in two flavors that look different but behave the same:

- **Dealer long calls** → calls have positive delta → dealer initially SHORTS stock to offset → as stock rises, call delta grows → dealer sells more stock → as stock falls, dealer covers
- **Dealer long puts** → puts have negative delta → dealer initially LONGS stock to offset → as stock falls, put delta grows more negative → dealer buys more stock → as stock rises, dealer sells

Both end up with the *same* dynamic hedging pattern: **sell on rises,
buy on drops = stabilizing**. The initial hedge direction differs
(short stock vs long stock) but the response to price moves is
identical. This is why canonical
[`gamma_vanna_video.md`](gamma_vanna_video.md) §3 can correctly say
"MM long gamma → stabilizing" without specifying whether the MM is
long calls or long puts — both produce the same behavior.

This framing is also a useful corrective to the mechanism inversion in
Freddy's OrderFlow Part 2 video (see
[`../community/freddy_orderflow_series.md`](../community/freddy_orderflow_series.md)
Part 2 "Mechanism inversion" section). Freddy attributed long-gamma
hedging behavior to MM short gamma; TommyCirj articulates the correct
long-gamma behavior here and John endorses.

---

## 2025-04-09 4:30 PM — Jasper, regime rule of thumb (0DTE-as-default)

**Channel:** GexBot Discord (channel not captured)
**Date:** 2025-04-09, 4:26 → 4:30 PM
**Speakers:** Andy (community, new to GEX) → Jasper "jass" (Moderator)

### Q (Andy)

> ok this might be a dumb question but how can you tell if price is
> going to keep trending or breakout
>
> New to gex

### A (Jasper)

> that's a hard question lol.
>
> my rule of thumb is to look for reversion at long gamma. this is
> usually the case in falling volatility regimes (which for 0dte is
> almost always).
>
> in case of rising volatility (preceding an event) then long gamma
> for pressing a breakout
>
> i faded major long gamma here near EOD ⁠state-degens⁠ (did end up
> bailing and revving long 216 tho due to incoming 50 minute algo)

### Three confirmations land

#### 1. The default rule for 0DTE

> Reversion at long gamma. This is usually the case in falling
> volatility regimes (which for 0dte is almost always).

Jasper's parenthetical is the operationally significant claim: **for
0DTE, falling-vol regime is the default**. The polarity-flip in
[`convexity_ladder.md`](convexity_ladder.md) observation 2 lays out
both regimes; this Q&A says for 0DTE-specifically you can assume
falling-vol unless there's a specific reason not to.

The implication: the default 0DTE rule **is** the canonical pivot-at-
cyan rule from the closing-exchange entry above. Most days, that's
the right read. Don't reach for the rising-vol alternative without a
reason.

#### 2. The exception: pre-event sessions

> In case of rising volatility (preceding an event) then long gamma
> for pressing a breakout.

Pre-event sessions (CPI, FOMC, NFP, etc.) are when vol is being bid
up. In those windows, long-gamma levels flip from **reversion zones**
to **breakout triggers** — exactly the canonical polarity flip but
stated as Jasper's operational rule.

The full default-vs-exception structure for 0DTE:

| Regime | Cyan (long gamma) | Trigger |
|---|---|---|
| Falling vol (default for 0DTE) | Pivot / reversion | Pre-set |
| Rising vol (pre-event) | Breakout press | Specific event on the calendar |

#### 3. Live trade narrative

> I faded major long gamma here near EOD ⁠state-degens⁠ (did end up
> bailing and revving long 216 tho due to incoming 50 minute algo)

Jasper is *applying* his own rule in real time. The reference to
"state-degens" is a Discord channel name where the trade was likely
called. The "50 minute algo" is a specific late-EOD algorithmic
pattern he watches for — worth following up if more context emerges
about what that algorithm does mechanically.

This is also worth noting because it shows the rule is *contingent*:
Jasper faded long gamma (his default rule), then bailed and reversed
when he detected a different signal coming (the 50-minute algo). The
rule of thumb isn't a static prediction — it's a Bayesian prior that
gets updated as new evidence arrives.

### Cross-references

- [`convexity_ladder.md`](convexity_ladder.md) observation 2 — the
  canonical polarity-flip table this Q&A operationalizes
- Jasper closing-exchange entry above — the canonical "pivot at
  customer long gamma" rule. This entry adds the regime modulation
  conditions.
- [`../community/expert_qa.md`](../community/expert_qa.md) — John M's
  2025-04-04 stockholm exchange documents the failure mode when
  sustained directional flow overrides the polarity (community-tier
  pattern recognition, not vendor-confirmed). Together with this entry
  they give the regime-modulation rule + a community-observed limit.

### Follow-up flags

- **What is the "50 minute algo"?** Jasper references it as a known
  pattern. Worth catching context if it comes up again. Could be a
  rebalancing algo, a hedging algo, or a flow pattern documented
  elsewhere in Discord.
- **state-degens channel** — a Discord channel name; could be the
  trading-call channel where Jasper posts setups in real time. Useful
  to know if we ever crawl Discord systematically.

---

## 2025-04-21 8:19 AM — John Kirby on ITM call increase as support

**Channel:** GexBot Discord (channel not captured)
**Date:** 2025-04-21, 8:19 AM
**Speakers:** unattributed asker (new to GEX) → John Kirby (Moderator,
GexBot principal — distinct identity from community contributor "John
M"; this exchange is canonical-tier per the principal role tag)

### Q

> For those of us who are new, does such a large increase in ITM
> calls usually act as support, as it did today? Thanks

### A (John)

> YES
>
> one of my favorite signals

### What this establishes

#### The signal: large increase in ITM call buying → price support

A spike in customer buying of ITM (in-the-money) calls is one of
John's named-favorite signals for identifying price support.

#### Why it works (derived from canonical mechanism)

ITM calls have **high delta** — typically 0.7 to ~1.0, vs OTM call
deltas around 0.1 to 0.4. The delta is what determines the MM's stock
hedge size:

- Customer buys 1 ITM call (delta ~0.85) → MM is short delta -85 → MM buys ~85 shares
- Customer buys 1 OTM call (delta ~0.25) → MM buys ~25 shares

A large *increase* in ITM call buying therefore produces a
proportionally *larger* stock-buying flow from MM hedging than the
same notional in OTM calls. The MM stock buying is the structural
support — and the higher the delta, the stronger the floor.

#### Why this is a distinct subset of the cyan-bar reading

The canonical operational rule from the closing-exchange entry above
("pivot at customer long gamma") doesn't differentiate by moneyness —
long gamma is long gamma
on the convexity ladder. But this Q&A says: **long gamma at ITM
strikes acts more strongly as support than long gamma at OTM
strikes**, because of the mechanical hedge-size difference.

For operational reads:
- Cyan bar at ATM/OTM strike → standard pivot candidate
- Cyan bar at ITM strike with significant size increase → John's
  "favorite signal" — elevated-conviction support

#### How to spot it on the chart

This isn't directly visible from the convexity ladder alone (which
nets long/short gamma by strike, not by moneyness vs spot). You need
either:
- The Options Profile view (which preserves call/put + strike, so ITM-
  vs-OTM is just a comparison to spot)
- The OrderFlow view (Convexity OF spikes that originate at strikes
  inside the current spot range)
- The gamma-switch toggle (gamma view ↔ puts/calls view) John M
  describes in [`../community/expert_qa.md`](../community/expert_qa.md)
  — useful to verify which strikes the long-gamma flow is hitting

### Cross-references

- Jasper closing-exchange entry above — the base pivot-at-long-gamma
  rule. This Q&A is a high-conviction sub-case of that rule.
- [`../community/expert_qa.md`](../community/expert_qa.md) — John M's
  stockholm failure-mode entry describes when pivots *don't* hold
  (community-tier observation). ITM call buying creates strong
  support but isn't immune to overwhelming directional flow.
- [`gex_profile.md`](gex_profile.md) — the Options Profile view that
  preserves moneyness information.

### Operational note

A "large increase" is the qualifier — small ITM call buying happens
all the time and doesn't trigger this signal. The pattern requires a
*notable spike* in ITM call demand to be in John's "favorite signals"
category. We don't have a quantitative threshold from John, so this
is initially a qualitative pattern recognition read.

---

## 2025-04-22 8:07 AM — Jasper on "max change gex" mechanics

**Channel:** GexBot Discord (channel not captured)
**Date:** 2025-04-22, 7:19 → 8:07 AM
**Speakers:** Bass `[GOLD]` (community, GOLD-tier subscriber) → Jasper
"jass" (Moderator)

### Q (Bass)

> this "max change gex" values change (1) once the strike is hit, (2)
> before the strike is hit or (3) when the reaction in price is
> taking place?

### A (Jasper)

> they update every second. theyre lookbacks since the ladder doesnt
> have a time axis

### What this establishes

#### Two structural facts about "max change gex"

1. **Updates every second.** Real-time continuous, not gated on price
   events. Bass's three options ("once strike is hit," "before strike
   is hit," "when reaction is happening") are all wrong — none of them
   describe the actual mechanic.
2. **Values are lookbacks.** Since the convexity ladder is plotted
   strike-by-strike (no time axis), time information is injected via
   lookback aggregation. Each strike's "max change" is the largest
   shift observed in some recent window.

#### Why this matters for measurement framework

If we ever subscribe to or otherwise access this metric in the corpus,
two things matter:

- It's **derived, not raw**. Reproducing it requires the lookback window length and the aggregation method. Neither is documented in this Q&A.
- It's **strike-localized**. Each strike has its own "max change" value, computed over the same lookback. So a single chart timestamp gives a fingerprint of which strikes have had the most recent activity.

#### Why this is a useful pattern

A "max change gex" spike at a strike says: that strike has recently
*shifted* significantly. If the canonical pivot-at-long-gamma rule
from the closing-exchange entry above tells you *where* to act, "max
change" tells you *which strike levels are getting attention right
now* — a freshness filter on top of the static ladder.

This is analogous to the Convexity OrderFlow / GEX OrderFlow signals
Freddy describes in [`../community/freddy_orderflow_series.md`](../community/freddy_orderflow_series.md)
Part 2 (spikes indicating fresh activity at strikes). "Max change gex"
appears to be a similar "where's the recent action?" filter, but
implemented as a lookback aggregate on the existing ladder rather
than as a separate OrderFlow chart.

### Flagged as undocumented UI feature

"max change gex" isn't mentioned in our existing canonical files
(`metrics_math.md`, `gex_profile.md`, `convexity_ladder.md`). It's a
GexBot UI element we haven't surfaced. If we ever get a UI walkthrough
or have access to the chart, this is one of several elements to
identify and document.

### Note on subscriber tags

This is the first **[GOLD]**-tagged asker we've seen in the Q&A series.
GOLD role suggests a paid-tier subscription within GexBot's Discord
hierarchy. Other tags seen so far: `[PP]` (Freddy — possibly "paying
practitioner" or moderator-tier). No canonical statement on what each
tag means; treat as context cues for the asker's familiarity with the
system rather than canonical signal.

---

## 2025-07-25 11:32 AM – 11:58 AM — Jasper, on reading net DEX for vol regime + the convexity-dump-then-ramp pattern

**Channel:** GexBot Discord, #theory-questions
**Date:** 2025-07-25, 11:32 AM → 11:58 AM ET
**Speakers:** aigonewrong (community) ↔ Jasper "jass" (Moderator)

### Q1 (aigonewrong, 11:32 AM)

> today's orderflow screenshot for NDX, SPX (2025-07-25 first 3 hrs).
> still trying & learning to see if this can be incorporated for use
> daily.
> is my below understanding correct?
> NDX: from DEX, looking like customers are net selling both calls
> and puts.
> SPX: from DEX, looking like customers (for now) are net buying both
> calls and puts.

aigonewrong attached the side-by-side NDX/SPX orderflow comparison:
[`images/aigonewrong_2025-07-25_ndx_spx_dex_orderflow.jpg`](images/aigonewrong_2025-07-25_ndx_spx_dex_orderflow.jpg).

![aigonewrong NDX vs SPX orderflow 2025-07-25](images/aigonewrong_2025-07-25_ndx_spx_dex_orderflow.jpg)

Visible in the graphic: three-row orderflow comparison for each
ticker (aggregate dex, net gex, net convexity), all panels covering
9:30am–12:30pm 7/25/25. Bottom annotation summarizes:
- **NDX:** net convexity down. DEX: call selling, put selling
- **SPX:** net convexity neutral. DEX: call buying, put buying

### A1 (Jasper, 11:41 AM)

> yes, those reads are correct

### Q2 (aigonewrong, 11:44 AM, citing the docs)

> thanks @jass
>
> from the doc: "Negative call aggdex implies more call deltas sold
> than bought, and vice versa for puts. So, when call aggdex is
> negative and put aggdex is positive, participants have been broadly
> shorting volatility over the course of the day. Different
> underlyings trade differently. In a lower volatility environment,
> SPX is primarily a short volatility and hedging instrument, so we
> often see positive put aggdex, negative call aggdex, and moderately
> negative net aggdex during uptrends."
>
> so today, VIX is trending lower (at 15 now).
> for NDX, customers are short volatility.. and for whatever reason,
> SPX traders are long volatility...

### A2 (Jasper, 11:46 AM)

> spx was lifting convexity (vol until about midday) where they
> dumped the shit out of it and we finally ramped
>
> right now they're about neutral/short convexity on spx
>
> lmao they dumped convexity as i was bailing trying to short 420s nq
>
> that makes sense
>
> assholes
>
> **those are the best longs tho. there's juice to lean on.**
>
> right now since spx mostly short vol again tape is loosey goosey

Jasper attached the SPX-only convexity chart:
[`images/jasper_2025-07-25_spx_convexity_dump_ramp.jpg`](images/jasper_2025-07-25_spx_convexity_dump_ramp.jpg).

![Jasper SPX convexity dump 2025-07-25](images/jasper_2025-07-25_spx_convexity_dump_ramp.jpg)

Visible in the graphic: SPX 7/25/25 from 9:30am to ~12:45pm. Cyan
line is net convexity ($MM); white line is spot price. The convexity
line climbs through the morning from approximately −1500 to a peak
of approximately +1700 around 11:30, then drops sharply between
12:00 and 12:30 (tooltip at 12:08:22 reads `net convexity: 855.54`,
declining). Spot price (white) breaks out and ramps from 6380 to
approximately 6388 in the post-dump window. Major long gamma 6369.88;
major short gamma 6386.16 per the tooltip.

### Q3 (aigonewrong, 11:58 AM)

> got it thanks.
> long puts are getting out ... as spot goes up.
> with that 6400 short call strike, volatility continues to dampen.
> ??

### A3 (Jasper, confirmed via 👍 reaction — no typed reply)

Jasper acknowledged aigonewrong's read with a thumbs-up emoji
reaction rather than a verbal response. Per Steve's 2026-05-23
convention: an emoji reaction from a principal is canonical-
confirming for the post being reacted to — the principal validated
the read without restating it. The acknowledged content:

1. **Long puts unwinding on upward spot moves.** Customer long-put
   exposure decreases as spot trades higher — consistent with
   delta-hedging mechanics (long puts have negative delta; as spot
   rises, the put position becomes deeper OTM and is closed for
   reduced loss / cash recovery).
2. **6400 short call strike acting as a vol-dampener.** With
   customers SHORT calls at 6400 (above spot at ~6388), any approach
   toward 6400 sees dealers becoming MORE LONG the underlying via
   their own buy-back hedging of those short calls — stabilizing
   flow that dampens realized vol as price nears the strike.

### What this establishes

#### 1. Reading net DEX direction across BOTH call and put sides

The DEX panel exposes net delta exposure (aggregated) signed by
customer-buy-vs-sell, separately tracked for calls and puts. The
canonical method Jasper confirms here:

| Call aggdex | Put aggdex | Customer regime |
|---|---|---|
| Negative (net selling) | Negative (net selling) | **Short volatility** — customers writing premium on both sides |
| Positive (net buying) | Positive (net buying) | **Long volatility** — customers paying premium on both sides |
| Negative call + positive put | | Short call premium + long put premium — bearish hedging stance |
| Positive call + negative put | | Long upside + short put premium — bullish positioning |

The doctrinal payload: **read both sides simultaneously** to infer
vol regime, don't read one side in isolation. NDX showing call
selling AND put selling = customers are NET short vol regardless of
direction; that's a distinct regime from "customers are short calls"
(which would be directional bearish).

#### 2. The convexity-dump-then-ramp pattern

Jasper's SPX narrative for the morning maps to a canonical pattern:

1. **Phase 1 — Lifting convexity (morning).** Customers buy convexity
   (long options on both sides). Net convexity climbs. Vol is being
   bid up.
2. **Phase 2 — Dump (~12:00–12:30).** Holders of the morning's long
   convexity sell out aggressively. Net convexity drops sharply
   toward zero or negative.
3. **Phase 3 — Ramp (post-dump).** Spot moves in a directional way
   (here: upward). The dumping flow is **the structural support** —
   former vol buyers becoming vol sellers means dealer hedging flips
   from short-stock-against-long-customer-options to long-stock-
   against-short-customer-options, which provides buy pressure into
   any pullback.

The 2025-07-25 SPX chart shows this exact sequence in 4 hours.

#### 3. The "juice to lean on" operational rule

Jasper's flagged statement: **"those are the best longs tho. there's
juice to lean on."**

Translation: when customer convexity gets dumped (sold), the
resulting position state is one where a long-spot trade has
asymmetric structural support. The dumping itself doesn't end the
move — it sets up the follow-through. "Juice to lean on" = the
dealer hedging flow provides cushion against pullbacks because
dealers are now structurally long stock against their newly-acquired
short-option positions (from customers selling them).

This is the **dual** of the failure-mode pattern documented in
[`../community/expert_qa.md`](../community/expert_qa.md) (John M /
stockholm 2025-04-04): there, sustained directional pressure
*overwhelmed* dealer hedging; here, dealer hedging is the *cause*
of the directional follow-through.

#### 4. Post-dump regime: "loosey goosey" tape

Jasper's post-dump observation: "right now since spx mostly short
vol again tape is loosey goosey." When customers are net SHORT vol
(having sold off their long-convexity positions), dealer hedging is
LIGHTER per move (smaller gamma exposure) and the tape doesn't have
strong magnets in either direction. "Loosey goosey" = no significant
pin/pivot levels currently dominating because the gamma profile is
flat.

This connects to the canonical convexity-ladder doctrine: high
positive convexity = strong pivot levels (sticky); neutral/short
convexity = weak levels (price moves freely). The intra-day regime
change from "lifting convexity" → "short convexity" is the regime
flip itself, observed in real time.

### Operational reads for the measurement framework

When we have corpus data covering days with this pattern:

1. **Detect "lifting convexity" mornings**: net convexity trending
   monotonically upward in the AM session. Mark as long-vol regime.
2. **Detect the dump**: net convexity dropping >50% from peak within
   a 30-minute window. Time-stamp the dump.
3. **Test "juice to lean on"**: does a long entry within ~30 min
   post-dump have asymmetric upside? Specifically:
   - Compute forward returns 30/60/120 min after dump
   - Compare to baseline forward returns when no dump occurred
   - The Jasper claim predicts dumps mark asymmetric long opportunities
4. **Test "loosey goosey" sequel**: post-dump, measure realized
   vol-of-vol and gamma-magnet stickiness. The claim predicts
   reduced magnet behavior at the standing gamma walls.

This is one of the few canonical entries with a clean intra-day
pattern testable at the corpus level.

### Cross-references

- [`convexity_ladder.md`](convexity_ladder.md) — the static convexity
  ladder this dynamic pattern modulates
- [`gex_profile.md`](gex_profile.md) — the call-vs-put GEX axis
  complementary to the DEX axis discussed here
- [`metrics_math.md`](metrics_math.md) — aggregate DEX formula
- The Jasper closing-exchange entry above (customer-perspective
  convention) — DEX is also customer-perspective; this entry extends
  the convention to the DEX panel
- The Jasper net-convexity-vs-call/put entry above — the
  call-vs-put aggregation argument here is the dual of the
  net-convexity aggregation; both views together give the full picture
- [`../community/expert_qa.md`](../community/expert_qa.md) —
  contrast with stockholm/John M failure mode: directional flow
  overwhelms dealer hedging vs. dealer hedging causes the directional
  flow

### Follow-up flags

- **6400 short call strike pin.** aigonewrong mentions vol dampening
  with the 6400 short call. The strike-as-cap mechanism is worth a
  worked example if we have intraday data — does SPX actually pin
  toward 6400 in the post-dump session?
- **Jasper's NQ 420 short.** Jasper mentions trying to short "420s
  NQ" (probably a 0DTE option strike in NQ — would be a 23420 strike
  given NDX context). Worth catching if more context comes up.
- **"Best longs" frequency.** How often does the lift-dump-ramp
  pattern repeat? Is it a daily occurrence or specific to certain
  regimes (e.g., low VIX, sub-15)?
- **Emoji-reaction canonicality.** This entry is the first to use
  Steve's 2026-05-23 convention that a principal's emoji reaction
  is canonical-confirming. Track how often this attribution form
  appears in subsequent curation; if frequent, formalize in the
  Source rules section at the top of this file.

---

## 2025-09-28 12:53 PM – 2:49 PM — Jasper, the two-signal fade-entry rule (long gamma + directional GEX)

**Channel:** GexBot Discord, #theory-questions
**Date:** 2025-09-28, 12:53 PM → 2:49 PM ET
**Speakers:** vqz `[MATH]` (community) → Jasper "jass" (Moderator)

### Q (vqz, 12:53 PM)

> So from what I've gathered by watching videos and just tryna get
> some sort of understanding to the orderflow side of things, lets
> say im looking to fade ES, what I want to see on the orderflow
> side of things is a spike in Long gamma to the upside indicating
> that liquidity has been taken, and that people are long vol so
> price would like to move away from there and also a spike in gex
> to the upside indicating that higher prices are more expensive
>
> @jass sorry for the @ but would love to hear if Im interpreting
> it correctly

### A (Jasper, 2:49 PM)

> yes. if you're looking to bid for reversion against spot selling
> off, the ideal conditions are long gamma + downside (put) gex
> spiking. this means someone's stepping in for reversion and making
> downside expensive. so spot price goes up
>
> conversely long gamma + upside (call) gex -> short

### What this establishes

#### The two-signal canonical fade-entry rule

Jasper confirms vqz's read AND adds the symmetric inverse. The
canonical rule:

| Signal 1 (long gamma) | Signal 2 (directional GEX) | Action |
|---|---|---|
| Long gamma spike | Downside (put) GEX spiking | **Bid for reversion** — long entry against spot selling off |
| Long gamma spike | Upside (call) GEX spiking | **Short** — sell against spot rallying |

Both conditions must align — long gamma confirms vol-buying is the
underlying flow at the level; directional GEX identifies which side
is being made expensive (= which side has someone stepping in for
reversion).

#### Mechanism: "making it expensive" = stepping in for reversion

Jasper's exact phrasing: "this means someone's stepping in for
reversion and making downside expensive."

Translation: when put GEX spikes on the downside, the put-side flow
is dominated by put-buying (= customers paying premium against
downside). That premium-paying flow is what *makes the downside
expensive*. The flow itself represents reversion bidders — they're
willing to pay to short downside, which means they expect spot to
mean-revert UP from current levels. The dealer hedging of those long
puts (delta-hedged short stock) provides the buy-pressure for the
expected upward reversion.

The symmetric case for call GEX spiking on upside is the same
mechanism inverted: call-buying makes upside expensive, signals
reversion sellers expecting spot to revert down, dealer hedging
provides the sell-pressure.

#### Operational refinement of the pivot-at-long-gamma rule

This entry sharpens the canonical pivot rule from the closing-
exchange entry above:

- **Base rule** (closing exchange, 2025-02): pivot at customer long
  gamma; move through customer short gamma
- **This refinement** (vqz Q&A, 2025-09): the *direction* of the
  pivot is given by the directional GEX spike at the same level

Read order:

1. Find the long-gamma cluster (= pivot candidate, per the base rule)
2. Look at the directional GEX at that same strike/level
3. If downside (put) GEX is spiking → pivot is **bidable** for
   reversion UP
4. If upside (call) GEX is spiking → pivot is **shortable** for
   reversion DOWN
5. If GEX is neutral/mixed → pivot is ambiguous; lower-confidence

This converts the static "pivot at long gamma" into an actionable
trade-direction rule by adding the directional-GEX read.

### Cross-references

- The Jasper closing-exchange entry above — base pivot-at-long-gamma
  rule. This entry adds direction.
- The Jasper net-convexity-vs-call/put entry above — Jasper's prior
  preference for net long/short over call/put alone for pivot
  prediction. This entry doesn't override that — net gamma still
  identifies the LEVEL; directional GEX adds the trade-DIRECTION.
- [`gex_profile.md`](gex_profile.md) — the call-vs-put GEX axis
  carrying the directional component of the rule
- [`convexity_ladder.md`](convexity_ladder.md) — the long/short
  gamma axis (cyan/purple) carrying the level component of the rule
- The Jasper 2025-07-25 entry above (convexity-dump pattern) — covers
  WHAT changes during the day; this entry covers WHERE to act once
  the cluster is stable

### Follow-up flags

- **The `[MATH]` role tag.** First `[MATH]`-tagged asker we've seen.
  Joins the known set of role-tag context cues: `[PP]` (Freddy —
  possibly "paying practitioner"), `[GOLD]` (paid-tier subscriber).
  No canonical statement on what `[MATH]` indicates — speculation:
  a quant-leaning subscriber tier or interest flag. Confirm if more
  context appears.
- **Worked example needed.** This entry gives the rule but no live
  trade narrative. If a future Discord thread shows Jasper applying
  this rule with a chart annotation, that would be a strong
  companion entry.
- **Corpus test design.** The two-signal rule is testable: for each
  long-gamma cluster in the corpus, check whether put-GEX-on-downside
  or call-GEX-on-upside accompanies it, and measure forward returns
  conditional on the alignment. Should produce a clean asymmetry
  between aligned and non-aligned signals if the rule holds.

---

## 2025-09-29 9:41 PM – 2025-10-01 1:08 PM — Jasper, GEX vs gamma definitions + Classic vs State (naive vs trade-classified GEX)

This entry combines two sequential Discord exchanges Jasper used to
develop one continuous doctrine: the foundational distinction
between the GEX-profile and gamma-profile axes (2025-09-29), and the
product-level difference between GexBot's "Classic" (naive) GEX and
"State" (trade-classified) GEX (2025-10-01).

**Channel:** GexBot Discord, #theory-questions
**Dates:**
- 2025-09-29, 9:41 PM → 10:29 PM ET — pensivelion + Jasper
- 2025-10-01, 1:02 PM → 1:08 PM ET — Browniver + Jasper

**Speakers:** pensivelion `[end]` (community) → Jasper "jass"
(Moderator); Browniver `[PHUB]` (community) → Jasper "jass"
(Moderator).

The two threads are treated as one entry because Jasper's
2025-10-01 explanation of Classic vs State directly continues the
2025-09-29 discussion of the naive GEX assumption.

---

### Part 1 — 2025-09-29: GEX vs gamma definitions

#### Q (pensivelion `[end]`, 9:41 PM)

> Hey so. what's the difference between GEX being positive and
> gamma being positive?

#### A1 (Jasper, 9:45 PM)

> with our terminology the original gex profile refers to netting
> out call vs put gamma, irrespective of whether the initiator is
> long or short. then gamma (under options profile) refers to
> long/short gamma, irrespective of whether the transaction is call
> or put.
>
> more practically you can think of gex profile as net long or short
> deltas at some strike (since thats the dimension calls/puts lie
> across) and gamma profile as net long or short vol (easier to
> think of it in terms of straddles, whether customer lifted or
> dumped the volatility at some strike)
>
> the original assumption around gex was that customers are always
> long puts short calls hut that assumption is useless for
> 0dte/intraday timeframe so actual classification (using a
> volatility surface) is necessary

#### A2 (Jasper, 10:29 PM — vol surface normalization aside)

> tldr instead of using options prices there's a method to normalize
> their values so that you can compare them apples to apples. (think
> about when you're trying to determine whether a $0.02 OTM call is
> fairly valued vs a $0.50 ATM call is fairly valued. comparing
> their prices directly doesn't really make sense since their
> moneyness is so different right? so converting prices into
> volatilities normalizes this discrepancy). i recommend reading
> investopedia for more.

(The 10:29 PM content was sent twice — once as a normal message and
once as a quoted re-post of the same text. Both are identical;
captured once here.)

---

### Part 2 — 2025-10-01: Classic vs State product distinction

#### Q (Browniver `[PHUB]`, 1:02 PM)

> You are saying that the difference in GEX profile in classic and
> state is "volatility surface classification" / outnetting naive
> (meaning no classification) gex?
> What does this mean for real life trading?
> What does state show that classic does not and which one to use as
> GEX?

#### A1 (Jasper, 1:05 PM — the product-level distinction)

> classic, like most other gex services, is just naively
> incrementing volume of each option contract as it trades, and then
> incorporates that into the gamma exposure calculation. state
> classifies the trades of the option contract as buy or sell (so
> the volume can be +50 which means 50 lots bot, or -25 which means
> 25 lots sold, all cumulatively over the day) before then
> calculating gex exposure with that
>
> you'll see in a lot of literature the naive assumption of paper
> buys puts and sells calls, therefore dealer is short puts and
> long calls, but that assumption is clearly just wrong

#### A2 (Jasper, 1:08 PM — operational implications)

> on the state ladder for SPX i can see if participants are all
> selling vol or long vol which even for futures has a major impact
> on price action (the regime). e.g. if everybody is long vol
> (meaning buying options, not just puts but across the skew) then
> im expecting hotter tape. if everybody's selling vol then there's
> not much to do other than join some grind
>
> with respect to scalping level to level, state just better
> indicates where shorts or longs are located on the profile.
> classic (naive) gex profile generally fills out calls to the
> upside, puts to the downside.

---

### What this establishes

#### 1. The canonical GEX vs gamma definitions (restated and sharpened)

Two distinct profiles, two distinct axes:

| Profile | Netting axis | Practical translation |
|---|---|---|
| **GEX profile** (green/red) | Call vs put gamma (initiator long/short doesn't matter) | **Net long or short DELTAS at strike** — directional convexity |
| **Gamma profile** (cyan/purple, under options profile) | Long vs short gamma (call vs put doesn't matter) | **Net long or short VOL at strike** — straddle-equivalent, customer lifted or dumped vol |

This is the most operationally compressed canonical statement of
the two-axis structure in this file. It matches and confirms the
earlier canonical statements from the GEX-vs-gamma-ladder
disambiguation entry (first entry) and the John Kirby
gamma↔convexity equivalence entry above, but adds the **deltas vs
vol** translation:

- GEX profile = net deltas direction (call/put axis collapsing onto a directional read)
- Gamma profile = net vol direction (long/short axis collapsing onto a vol-buying-vs-selling read)

**Operational reads:**
- GEX profile tells you **where direction is biased** at a strike
  (call-heavy = upside magnet; put-heavy = downside magnet)
- Gamma profile tells you **where vol is being bought or sold**
  (long-gamma = customers paid for vol; short-gamma = customers
  sold vol)

A trade decision typically needs both: GEX for *level direction*,
gamma for *vol regime at the level*.

#### 2. Repudiation of the naive "paper buys puts, sells calls" assumption

The legacy GEX literature (per Jasper) makes the assumption that
customers are always long puts and short calls. This implies dealers
are short puts and long calls. Jasper's verdict:

> that assumption is clearly just wrong

Specifically, for **0dte / intraday** timeframes, this assumption
breaks down. Modern customer flow is dominated by 0dte trading where
both calls and puts can be bought OR sold by either side; the naive
sign convention produces incorrect inferences. **Actual classification
of each trade as buy or sell — using a volatility surface — is
required to produce a useful GEX read for intraday/0dte purposes.**

This is a canonical statement that the GexBot product was built
specifically because the naive assumption fails. Competitor / legacy
GEX services (per Jasper's 10/01 message) still apply the naive
assumption.

#### 3. The Classic vs State product distinction

| Product | Method | What it measures |
|---|---|---|
| **Classic GEX** | Naively increments volume per contract trade → into GEX calculation | Aggregate per-strike gamma exposure assuming naive sign |
| **State GEX** | Classifies each trade as buy or sell using a vol surface → signed volume cumulative through the day → THEN computes GEX exposure | Customer-classified gamma exposure that preserves initiator side |

Concrete example from Jasper: in State, a strike's volume might be
**+50** (= 50 lots bought by customers) or **−25** (= 25 lots sold
by customers). Classic doesn't preserve this sign — both register
as 75 raw contracts traded with no directional information.

**Operational corollary:** Classic GEX profiles "generally fill out
calls to the upside, puts to the downside" — the naive assumption
is *baked into the chart shape*. That's a structural artifact of
the method, not a real read of positioning.

#### 4. Vol surface classification — the technical machinery

How GexBot State actually classifies a given trade as customer-buy
or customer-sell: by comparing the executed option price to the
volatility surface at that strike/expiry. The surface is the
canonical reference for what the option *should* cost at that
moneyness; trades printing above the surface implication tend to
be customer-buys, below tend to be customer-sells.

Jasper's $0.02-OTM-call-vs-$0.50-ATM-call example makes the point:
comparing option prices directly is misleading because the prices
already bake in moneyness differences. Volatility normalizes the
comparison.

For a deeper read Jasper recommends Investopedia on volatility
surfaces. This entry doesn't reproduce that technical content; the
key takeaway is that **State classification depends on the vol
surface as reference**, which means State data quality depends on
having a calibrated surface for each underlying.

#### 5. Regime trading via State — operationally significant even for futures-only traders

Jasper makes a notable claim that State enables a **regime read**:

| Regime | State signal | Tape expectation |
|---|---|---|
| **Long-vol regime** | Customers buying options across the skew (both puts and calls) | **"Hotter tape"** — bigger moves, active trading environment |
| **Short-vol regime** | Customers selling options across the skew | **"Join the grind"** — small moves, little to do |

> on the state ladder for SPX i can see if participants are all
> selling vol or long vol which even for futures has a major impact
> on price action (the regime)

The **"even for futures"** caveat is significant: the SPX options
positioning regime predicts ES futures behavior. So traders who
*only* trade futures still benefit from reading State (the upstream
options flow drives the dealer hedging that drives the futures
move).

This is doctrinal payload for the measurement framework: classify
each session as long-vol vs short-vol regime, then test whether
forward realized vol (and forward price-move magnitude) is
systematically higher in long-vol regimes.

#### 6. Level-to-level scalping — State preserves the directional information Classic loses

For the scalping use case:

> state just better indicates where shorts or longs are located on
> the profile. classic (naive) gex profile generally fills out
> calls to the upside, puts to the downside.

Classic's shape is misleading because it reflects the *naive
assumption*, not the actual positioning. State's shape reflects
the actual signed volume → genuine read of where customer longs vs
shorts cluster.

If using **State**, the pivot-at-customer-long-gamma rule
(closing-exchange entry above) refers to *measured* long gamma. If
using **Classic**, "long gamma" is whatever the naive sign
convention labels as long — which may not match actual positioning.

**Recommendation implicit in Jasper's framing:** use State for
intraday/0dte work. Classic provides a smoothed structural picture
that is not specifically wrong but lacks the actionable directional
information.

### Cross-references

- The GEX-vs-gamma-ladder disambiguation entry above (Jasper, first
  entry in this file) — the original canonical two-axis statement;
  this entry restates and elaborates with the deltas-vs-vol mapping
- The John Kirby gamma↔convexity equivalence entry above — the
  long-gamma ↔ positive-convexity ↔ cyan equivalence; combined with
  this entry's "gamma = net vol" framing, the operational chain is:
  cyan bar = long gamma = positive convexity = customer net long
  vol at strike
- The Jasper net-convexity-vs-call/put entry above — where Jasper
  first told us net long/short is the smoother indicator for
  pivot/pin prediction; this entry now explains *why* (State
  classification produces a cleaner signal than Classic naive
  netting)
- The Jasper 2025-07-25 convexity-dump entry above — operationalizes
  the regime read introduced here (lifting convexity = long-vol
  regime building; dump = transition to short-vol regime)
- The Jasper 2025-09-28 two-signal fade-entry entry above — applies
  the State classification to the trade-direction rule (long gamma
  + directional GEX); the current entry explains why State's
  signed-volume classification is what makes the directional-GEX
  signal meaningful
- [`gex_profile.md`](gex_profile.md) — the GEX axis (call vs put)
- [`convexity_ladder.md`](convexity_ladder.md) — the gamma axis
  (long vs short) and vol-regime modulation
- [`metrics_math.md`](metrics_math.md) — the underlying GEX/DEX
  formulas; the vol-surface classification step is upstream of
  these

### Follow-up flags

- **The `[end]` role tag** (pensivelion). First seen. Joins `[PP]`,
  `[GOLD]`, `[MATH]`, `[PHUB]` in the role-tag context-cue set.
- **The `[PHUB]` role tag** (Browniver). Also first-time. No
  canonical statement on what either tag indicates.
- **Vol-surface implementation details.** Jasper references the
  surface but doesn't describe the calibration. Worth a future
  entry if more details surface in Discord — what's the calibration
  cadence? What's the surface granularity (strike, expiry)? How
  does it handle low-liquidity strikes?
- **Regime test setup.** The long-vol vs short-vol regime
  classification is corpus-testable: for each session, classify
  using the State ladder (aggregate net-long vs net-short option
  trades across the skew), then measure forward intraday RV and
  range. The Jasper claim predicts long-vol regimes produce hotter
  tape.
- **Classic-vs-State quantitative comparison.** If the corpus has
  both Classic and State data, a direct comparison of the two
  profile shapes (and the trades they identify as long vs short)
  would let us quantify how much information Classic loses. This
  is independent of trading — it's a data-quality study.

---

## 2025-10-17 8:41 AM – 10:45 AM — Jasper, "literally all i do" — the regime-rule compression of his method

A short, high-signal restatement of the regime rule with a closing
meta-claim that compresses Jasper's entire trading method into a
two-case decision tree.

**Channel:** GexBot Discord, #theory-questions
**Date:** 2025-10-17, 8:41 AM → 10:45 AM ET
**Speakers:** T46 (community) → Jasper "jass" (Moderator)

### Q (T46, 8:41 AM)

> ok higher volatility...= stacked long gamma.... then is there a
> method jass uses to trade off particular long gamma levels like
> he has mentions in videos... or is there a different scheme he
> trades???

### A (Jasper, 10:45 AM)

> if volatility is increasing (the tape is hot) lean on long gamma
> to look for continuation trades. if volatiilty is decreasing (this
> is the most common regime for 0dte fyi) then look for
> reversions/fades off long gamma
>
> yes that is literally all i do

### What this establishes

#### 1. Restatement of the regime rule (consistency with 2025-04-09)

The rule is identical in structure to the 2025-04-09 4:30 PM entry
above (Jasper regime rule of thumb with Andy):

| Vol regime | Long-gamma read | Action |
|---|---|---|
| **Rising vol** ("hot tape") | Continuation trigger | **Lean** — press breakout at long gamma |
| **Falling vol** (default for 0dte) | Reversion zone | **Fade** — reversion off long gamma |

The 2025-04-09 entry framed this as default-vs-exception for 0dte;
this entry restates it as a clean two-case rule and confirms the
0dte default ("the most common regime for 0dte fyi").

The agreement across two Discord exchanges six months apart
elevates this from "Jasper's rule of thumb" to **doctrinally stable
canonical method**.

#### 2. The "literally all i do" meta-claim

The high-signal payload:

> yes that is literally all i do

Jasper compresses his entire trading method to this two-case
decision tree. That has substantial implications for how to read
the rest of the canonical material:

- The Classic-vs-State distinction, the call/put GEX axis, the
  long/short gamma axis, the max-change-gex freshness filter, the
  vol-surface classification — **all of that infrastructure exists
  to inform two decisions**: which regime are we in, and which
  long-gamma levels to lean on or fade
- The directional read (call vs put GEX, per the 2025-09-28
  two-signal fade-entry rule) **specifies the direction** of the
  long-gamma trade once the regime is identified
- The 2025-07-25 convexity-dump-then-ramp pattern is a special case
  of "lifting convexity = long-vol regime → press continuation; dump
  = transition to short vol → look for the ramp's tail-end fade"

**Operational implication:** when reading any other canonical entry,
ask: which side of this two-case decision tree is the entry
informing? If it doesn't inform either, it's infrastructure (the
HOW) rather than method (the WHAT).

#### 3. The 0dte default reconfirmed

> if volatiilty is decreasing (this is the most common regime for
> 0dte fyi)

This reconfirms the 2025-04-09 claim that **for 0dte, falling-vol
is the default regime**. Combining with this entry's main rule:
the default 0dte trade is **reversion at long gamma**. Continuation
at long gamma is the exception, reserved for rising-vol sessions
(pre-event, CPI/FOMC/NFP windows).

For a 0dte trader who can identify only "default" days (no event
calendar pressure), the operational default is therefore: find
long-gamma cluster, fade approaches to it. That's the base rate
trade.

### Cross-references

- The Jasper 2025-04-09 regime rule of thumb entry above — the
  original canonical statement of this rule (default-vs-exception
  for 0dte). This entry restates and reinforces.
- The Jasper 2025-09-28 two-signal fade-entry entry above — adds
  the directional-GEX read on top of the regime rule. Together:
  regime gives MODE (continuation vs reversion); directional GEX
  gives SIDE (long vs short).
- The Jasper 2025-07-25 convexity-dump-then-ramp entry above — a
  special case of regime transition (lifting → dumping → tape
  loosens) during a single session.
- The Jasper 2025-09-29 / 2025-10-01 GEX-vs-gamma + Classic-vs-State
  entry above — the infrastructure (which classification method,
  which axis) that feeds into this method's two-case decision.
- The closing-exchange entry above (Jasper customer-perspective
  convention) — establishes the base pivot rule that this entry's
  rule builds on.
- [`convexity_ladder.md`](convexity_ladder.md) observation 2 — the
  canonical polarity-flip table that this rule operationalizes.

### Follow-up flags

- **Method compression for documentation.** Jasper's "literally all
  i do" suggests we should consider a top-level summary in the
  canonical/ directory (e.g. `canonical/jasper_method.md` or
  similar) that compresses the entire canonical doctrine into this
  two-case decision tree, with all other canonical entries cited
  as infrastructure. This would be a useful navigation aid for new
  readers of the doctrine and a sharp test of canonical
  completeness — anything that doesn't trace to one of the two
  decisions is unmotivated detail.
- **Regime classification operationalization.** The rule depends on
  identifying "rising" vs "falling" vol. How is this measured
  intraday? Is it VIX trend? Realized vol vs implied vol? Net
  convexity trend (per the 2025-07-25 entry)? Worth a dedicated
  entry if future Discord material surfaces the specific signal
  Jasper uses.
- **Continuation-side worked example.** This file has multiple
  worked examples of the reversion case (2025-04-09 Andy, 2025-07-25
  SPX dump-ramp tail). Less material on the continuation case. A
  rising-vol pre-event worked example would round out the doctrine.
