# Orderflow — the intended read [st-20nw]

**Phase 1 of Orderflow Mastery (epic st-ygy1).** The vendor's intended reading of
the GexBot **Orderflow** view, assembled from the canonical and community tiers,
with every claim cited to its source and its tier. This is the doctrine document:
what the vendor and its principals say the view *means* and how they say to *use*
it. What the claims are *worth* is Phase 2's job (verification against the 62-day
archive) — nothing here is measured truth unless explicitly marked.

**Tier discipline** (per `README.md`): **[CANONICAL]** = vendor-published text or
principal statements (jass, John Kirby, John M as staff). **[COMMUNITY]** =
practitioner interpretation (Freddy Sarmiento, Discord community). **[MEASURED]**
= our own corpus findings. **[STRUCTURAL]** = our observation of naming/shape,
not a claim by anyone.

**Status:** draft v1, 2026-08-06. Freddy series refresh and vendor Orderflow-page
capture in progress (see §8 Gaps).

---

## 1. What the Orderflow view is

The GexBot product ladder: **Classic** (naive OI-based GEX) → **State**
(orderflow-classified positioning: who originated each position) → **Orderflow**
(the flow *deltas* as they happen, on the classified stream). The State charts
show accumulated position state; the Orderflow view shows **flows entering the
system in real time**.

- **[CANONICAL]** The classification engine underneath is the same one that
  powers State: market-maker inventory imbalance tracking — "whenever they can't
  find a buyer, or can't find a seller … we take note, and add it to our tally.
  As the day moves forward, we begin to form a picture of all the **unmatched
  inventory**, which must be hedged with the underlying."
  (`canonical/metrics_math.md`, "Orderflow Classification".)
- **[COMMUNITY]** What the view adds over the State profile: "What if we can
  detect significant flows when they enter the system at different strikes
  through various options structures — iron condors, straddles, strangles? We
  can't see those structures on the GEX profile. But with order flow we could."
  (Freddy, Part 2, `community/freddy_orderflow_series.md`.) Multi-leg structures
  appear as coordinated spike patterns across strikes; the accumulated profile
  can't show them.

## 2. The panes and their intended reads

The view as practitioners screenshot it (aigonewrong 2025-07-25, confirmed
correct by jass — `canonical/principal_discord.md`) is a **three-row time-series
layout per ticker: aggregate DEX, net GEX, net convexity**, plus the spike
charts Freddy tutorializes (Convexity OrderFlow, GEX OrderFlow). Panes and
reads:

### 2.1 Convexity OrderFlow (long/short gamma spikes)

- **[COMMUNITY]** Formula per Freddy (Part 2): `(long orderflow × gamma
  exposure) − (short orderflow × gamma exposure)`. Up spike = someone **buying**
  options (long gamma, taking liquidity) → expectation of **reversion**. Down
  spike = someone **selling** options (short gamma, providing liquidity) →
  expectation of **continuation**. Mnemonic: *long gamma = friction = reversion;
  short gamma = momentum = continuation.*
- **[CANONICAL]** The same operational rule from the principal side, on the
  static ladder: "**Pivot at customer long gamma (cyan). Move through customer
  short gamma (purple).**" (jass, 2025-02-21 closing exchange.) Freddy's spike
  read is the flow-level version of jass's state-level rule; they agree on the
  behavior.
- Everything is **customer-perspective** — jass's standing convention
  (2025-03-05): the charts show the customer's net view; never read MM-side
  from the colors directly.

### 2.2 GEX OrderFlow (call/put imbalance spikes)

- **[COMMUNITY]** Companion chart, signed by call/put rather than long/short:
  up spike = call-gex imbalance growing; down spike = put-gex imbalance growing
  (Freddy, Part 2).
- **[CANONICAL]** Axis discipline from the principals: **call/put GEX measures
  directional convexity (up/down); long/short gamma measures momentum/reversion
  (continue/fade)** — two different axes over the same classified data, never to
  be conflated (jass, `canonical/gex_profile.md` obs. 5,
  `canonical/convexity_ladder.md` obs. 7).

### 2.3 The DEX pane (aggregate delta flow, call and put sides)

- **[CANONICAL — vendor doc, secondhand]** The one verbatim vendor-doc passage
  we hold about the Orderflow view, quoted by aigonewrong on 2025-07-25 and
  implicitly ratified in jass's answer:

  > "Negative call aggdex implies more call deltas sold than bought, and vice
  > versa for puts. So, when call aggdex is negative and put aggdex is positive,
  > participants have been broadly shorting volatility over the course of the
  > day. Different underlyings trade differently. In a lower volatility
  > environment, SPX is primarily a short volatility and hedging instrument, so
  > we often see positive put aggdex, negative call aggdex, and moderately
  > negative net aggdex during uptrends."

  The source page itself is **not yet captured** (§8). This is the passage that
  ties the view directly to the `agg_*_dex` API fields.

- **[CANONICAL]** The two-sided regime read jass confirms
  (`principal_discord.md` 2025-07-25):

  | Call aggdex | Put aggdex | Customer regime |
  |---|---|---|
  | Negative (selling) | Negative (selling) | **Short volatility** — premium writing both sides |
  | Positive (buying) | Positive (buying) | **Long volatility** — premium paying both sides |
  | Negative | Positive | Short call premium + long put premium — bearish hedging stance |
  | Positive | Negative | Long upside + short put premium — bullish positioning |

  The doctrinal payload: **read both sides simultaneously**; one side in
  isolation is a different (directional) statement, not a vol-regime statement.

### 2.4 Net convexity over time (the intraday vol-regime tape)

- **[CANONICAL]** The convexity-dump-then-ramp pattern (jass, 2025-07-25, with
  chart): morning **lift** (customers buying convexity, vol bid) → sharp
  **dump** (holders selling out; net convexity collapses toward zero/negative)
  → directional **ramp** with the flipped dealer hedging as structural support.
  jass: "**those are the best longs tho. there's juice to lean on.**"
- **[CANONICAL]** Post-dump regime: customers net short vol → lighter dealer
  hedging per move → "tape is loosey goosey" — no strong magnets; levels weaken.

## 3. The doctrine hierarchy — what governs what

The material stacks into a small decision structure. From the top:

1. **The regime rule** [CANONICAL, doctrinally stable — stated 2025-04-09,
   restated 2025-10-17]: "if volatility is increasing (the tape is hot) lean on
   long gamma to look for continuation trades. if volatility is decreasing (the
   most common regime for 0dte fyi) then look for reversions/fades off long
   gamma. **yes that is literally all i do**" (jass). The vendor's own
   convexity-ladder doc carries the same polarity table
   (`canonical/convexity_ladder.md`): falling vol → positive convexity stalls
   price, negative convexity is soared through; rising vol → inverted.
2. **The direction rule** [CANONICAL, 2025-09-28]: at a long-gamma pivot
   candidate, direction comes from the directional-GEX spike: long gamma +
   **put**-GEX spiking = bid for reversion up ("someone's stepping in for
   reversion and making downside expensive"); long gamma + **call**-GEX spiking
   = short. Two signals must align.
3. **The read-both-together discipline** [COMMUNITY, consistent with 2]:
   Freddy's "you cannot have a look at this one in isolation … Convexity order
   flow and GEX order flow together — that's the recipe."
4. **Freshness filters** [CANONICAL]: "max change gex" values update every
   second and are lookback aggregates — *which strikes are getting attention
   right now* on top of the static ladder (jass, 2025-04-22). The Orderflow
   spike charts serve the same freshness function at flow level.

Everything else in the corpus — Classic-vs-State, the axis disambiguations, the
vol-surface talk — is infrastructure feeding these two decisions: **which regime
are we in, and which long-gamma levels do we lean on or fade**.

## 4. Where vendor and community diverge

| Claim | Vendor/principal position | Community (Freddy) position | Status |
|---|---|---|---|
| Reversion/continuation read of gamma spikes | Pivot at customer long gamma; move through short gamma (jass) | Same behavior, same trade | **Agree** |
| *Why* long-gamma levels pivot | Customer profit-taking + dealer unwind flow (canonical mechanism, `freddy_orderflow_series.md` Part 2 analysis) | MM hedging story with **directions inverted** (Part 2, 12:00–13:30) | **Freddy's mechanism is wrong; his rule is right.** TommyCirj/John Kirby exchange (2025-03-27) articulates the correct hedging directions. |
| Vocabulary | Convexity, long/short gamma (customer view) | "Reversion / continuation / regime change" instead of bullish/bearish | Compatible framings; Freddy's is deliberately vol-focused |
| Scope of use | Regime + level doctrine, instrument-agnostic | Four scenarios: morning read (open→~12:30), NQ scalps (15–20 pts; "not ES — tick value too small"), event days, EOD speculative positioning (last 5–10 min) | Freddy's scenario scaffold is community-only; no principal ratification found |

**Standing caution:** Freddy is the vendor's most prolific educator but is a
**community** source. Where his mechanism talk contradicts the principals, the
principals govern. His operational reads have so far always matched principal
doctrine; his *explanations* have not.

## 5. Mapping the view to the API fields we archive

The view's panes and the `orderflow_response` scalars (34 orderflow-specific
fields, **zero vendor documentation** — vendor-docs survey 2026-08-06 §8.2)
connect as follows:

| View concept | API fields | Evidence tier |
|---|---|---|
| DEX pane, "aggdex" call/put/net | `agg_call_dex`, `agg_put_dex`, `agg_dex` (+ `one_*`) | **[CANONICAL secondhand]** — the aigonewrong doc quote uses the exact term "aggdex"; identities agg = call+put hold exactly **[MEASURED]** |
| DEX pane, "net" variant | `net_dex`, `net_call_dex`, `net_put_dex` (+ `one_*`) | **[MEASURED, unexplained]** — agg-vs-net distinction is vendor question #1; correlation 0.9989→0.53 across days |
| Net convexity tape (jass's cyan line) | plausibly `zcvr`/`ocvr` | **[STRUCTURAL guess only]** — `cvr` unexplained; the last two undecoded fields. Phase 2 experiment #1: `zcvr` vs summed customer-signed state ladder. |
| Convexity/GEX OrderFlow spikes | plausibly `cvroflow`/`gexoflow`/`dexoflow` (+ `one_*`) | **[MEASURED]** these are exact first differences of `cvr`/`gr`/`agg_dex` per snapshot — i.e. the *flow* of the cumulative series; **[STRUCTURAL]** naming match to the spike charts |
| Ladder levels repeated in view tooltips (major long/short gamma etc.) | `z_mlgamma`, `z_msgamma`, `o_*` — verbatim `state` republications | **[MEASURED]** 16 identities hold exactly |
| Higher-order pane(s) if any | `zvanna`, `ovanna`, `zcharm`, `ocharm` | undecoded semantics beyond name |

## 6. Claims to test in Phase 2 (verification against the 62-day archive)

Ordered by leverage:

1. **`zcvr` = net customer convexity of the day's transactions?** The vendor
   defines convexity ladder = net customer gamma of the day's transactions; sum
   the customer-signed state ladder and compare to `zcvr`. Closes the last
   unknown field and, if it matches, gives us jass's cyan line from data we
   already store.
2. **Convexity-dump-then-ramp** (jass 2025-07-25): detect lift mornings, dump
   events (>50% drop from peak inside 30 min), test forward returns 30/60/120
   min post-dump vs baseline. "Juice to lean on" is a falsifiable
   asymmetric-returns claim.
3. **Vol-regime polarity table** (vendor canonical): falling-vol days, does
   price stall at positive-convexity strikes and traverse negative ones; do the
   polarities invert on rising-vol days? (First operational definition of
   rising/falling vol required — the corpus's open question; candidates: VIX
   trend, RV vs IV, net-convexity trend per §2.4.)
4. **Two-signal fade-entry** (jass 2025-09-28): at long-gamma spikes, does the
   directional-GEX side discriminate forward-return sign?
5. **DEX regime table** (§2.3): do the four agg-dex sign quadrants label days
   whose behavior differs measurably (trendiness, magnet adherence)?
6. **Freddy's spike-scenario claims** (community): morning-window reads,
   EOD "speculative positioning" reads — lower priority, community tier.
7. **Flow-state-at-confirm** (from the measured doc's own recommendation):
   flow does not *lead* price (refuted, decision-grade), but flow state at
   recognizer confirm seconds may still discriminate outcomes — the st-trbn
   join. This is Phase 4's bridge.

## 7. What "mastered" looks like against this doctrine

Steve can articulate, without the vendor's site: which pane answers *regime*,
which answers *level*, which answers *direction*; the two-case regime rule and
its 0DTE default (fade long gamma in falling vol); the dump-then-ramp sequence
and what "juice to lean on" means mechanically; and which of these are measured
truths vs vendor claims on our tape — per the Phase 2 results as they land.

## 8. Gaps — what Phase 1 still owes

1. **The vendor's Orderflow documentation page is uncaptured.** The site is a
   client-rendered SPA (survey §1); the State-section canon came from Steve's
   browser-saved HTML (2026-05-20). **Ask Steve for the same save of the
   Orderflow/documentation section** — the aggdex passage (§2.3) proves the page
   exists and defines view semantics we otherwise hold only secondhand.
2. **Freddy series parts beyond Part 2.** Tracker predates our entitlement;
   enumeration of new parts in progress; each new part gets a transcript pull
   (`scripts/fetch_youtube_transcript.py`) and a synthesis section in
   `community/freddy_orderflow_series.md`.
3. **The stale "we do not subscribe" preamble** in
   `community/freddy_orderflow_series.md` — now false (Quant month, 2026-08-05).
   Fix on the next edit of that file.
4. **Vendor questions** — the 8-item list in the measured doc §3, headlined by
   agg-vs-net DEX; the revised 7-item draft is on Steve's desk awaiting send.

## Revision log

- 2026-08-06: v1 draft — canonical/community synthesis from the existing corpus
  [st-20nw]. Freddy-series refresh and vendor-page capture pending.
