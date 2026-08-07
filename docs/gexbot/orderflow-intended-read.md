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

**Status:** v2, 2026-08-06. The vendor's Orderflow documentation is now captured
verbatim (`canonical/orderflow_view.md`, extracted from the site's JS bundle and
byte-verified) and the Freddy series is complete — three parts, all synthesized
(`community/freddy_orderflow_series.md`; no Part 4 exists, verified by full
channel enumeration). Remaining inputs are queued videos and Phase 2 itself
(§8).

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

The view is a time-based subplot with selectable metrics — **Dex Orderflow, Gex
Orderflow, Convexity Orderflow, Net Gex, Net Convexity, Aggregate Dex, Net
-Vanna/Charm** — metric values on the left axis, price ladder and the "white
jagged line" of spot on the right (vendor guided-tour text,
`canonical/orderflow_view.md`). Practitioners screenshot it as a three-row
layout (aggregate DEX / net GEX / net convexity — aigonewrong 2025-07-25,
confirmed correct by jass). The vendor's frame for the whole family: "Orderflow
helps to highlight transition points, both in terms of market direction and
volatility," and **"all plots and equations are in terms of paper (customer)
positioning"** — the customer-perspective convention, now confirmed doc-side.

All formulas share one shape [CANONICAL]: `(long/bull side × greek) − (short/
bear side × greek)`. Dex OF weights by DEX, Convexity OF by GEX on the
long/short axis, Gex OF differences the call/put imbalance. Panes and reads:

### 2.1 Convexity OrderFlow (long/short gamma spikes)

- **[CANONICAL]** Formula: `Convexity Orderflow = (long orderflow × GEX) −
  (short orderflow × GEX)`. "Positive convexity means that participants are
  expecting more volatility (buying options). Negative convexity means that
  participants are expecting less volatility (selling options). Sell-offs are
  often marked by consistent positive convexity orderflow … grinding days and
  squeezes often feature consistently negative convexity orderflow."
  (`canonical/orderflow_view.md`.)
- **[CANONICAL]** The vendor's stated *intended use* is cross-reference against
  Dex OF as a **leg-inference table**: "A transaction with positive dex but
  negative convexity is a short put. If the same transaction has positive
  convexity, it must be a long call. In this way, one can monitor the
  optionsprofile without looking at the ladder chart."
- **[COMMUNITY]** Freddy's reading rules (Part 2, matching): up spike = options
  bought, liquidity taken → **reversion**; down spike = options sold, liquidity
  provided → **continuation**. Mnemonic: *long gamma = friction = reversion;
  short gamma = momentum = continuation.* Part 3's compression: markets are
  **drawn to liquidity providers** (option sellers) and **move away from
  liquidity takers** (option buyers).
- **[CANONICAL]** The same operational rule from the principal side, on the
  static ladder: "**Pivot at customer long gamma (cyan). Move through customer
  short gamma (purple).**" (jass, 2025-02-21 closing exchange.) Freddy's spike
  read is the flow-level version of jass's state-level rule; they agree on the
  behavior.
- Everything is **customer-perspective** — jass's standing convention
  (2025-03-05): the charts show the customer's net view; never read MM-side
  from the colors directly.

### 2.2 GEX OrderFlow (call/put imbalance spikes)

- **[CANONICAL]** Formula: `GEX Orderflow = (call GEX imbalance) − (put GEX
  imbalance)`. "A bar up indicates that call gex imbalance has grown … a bar
  down indicates that put gex imbalance has grown." It "marks high 𝛄
  transactions, which are riskier and feature greater payoffs. As such it marks
  high conviction pivots. **On an index like SPX, which is dominated by short
  gamma, positive gex orderflow (often call selling) typically marks local
  tops, whereas negative gex orderflow marks local bottoms.**"
  (`canonical/orderflow_view.md`.)
- **[COMMUNITY]** Freddy Part 3's directional read agrees at the operational
  level — positive spike in an uptrend = "cost of upside lifted" = reversal
  warning — but attributes the spike to call *buying* where the vendor says
  "often call selling". Flow attribution differs; the top/bottom read is the
  same (divergence flag in `community/freddy_orderflow_series.md` Part 3).
- **[CANONICAL]** Axis discipline from the principals: **call/put GEX measures
  directional convexity (up/down); long/short gamma measures momentum/reversion
  (continue/fade)** — two different axes over the same classified data, never to
  be conflated (jass, `canonical/gex_profile.md` obs. 5,
  `canonical/convexity_ladder.md` obs. 7).

### 2.2b Dex OrderFlow (directional share-equivalent)

- **[CANONICAL]** Formula: `Dex Orderflow = (bullish volume × DEX) − (bearish
  volume × DEX)`. "It is as simple to read as: 'Someone just bought/sold this
  many shares worth of options here' … Often, a local bottom will be
  established as an aggressive buyer enters the picture. Just as easily, a
  local bottom can be marked by bearish orderflow, as a long is forced to
  liquidate." Level-of-interest marker; pairs with Convexity OF for the
  leg-inference table (§2.1).

### 2.3 Aggregate Dex (the day's cumulative delta contribution)

- **[CANONICAL]** "Aggregate dex tells us how much buying/selling the option
  market has contributed over the course of the day. Negative call aggdex
  implies more call deltas sold than bought, and vice versa for puts. So, when
  call aggdex is negative and put aggdex is positive, participants have been
  broadly shorting volatility over the course of the day. In a lower volatility
  environment, SPX is primarily a short volatility and hedging instrument, so
  we often see positive put aggdex, negative call aggdex, and moderately
  negative net aggdex during uptrends." (`canonical/orderflow_view.md` — now
  captured firsthand; this is the passage aigonewrong quoted in the 2025-07-25
  Discord exchange, which jass's answers ratified.) It ties the view directly
  to the `agg_*_dex` API fields.
- **[CANONICAL]** Two boundary conditions in the same passage: "SPY options
  tend to trade more directionally, making divergences between SPY and SPY
  aggdex into particularly powerful signals," and **"In high volatility
  environments (VIX greater than 20) SPX begins trading like SPY"** — a
  vendor-stated validity boundary on the whole SPX-as-vol-instrument read.

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

### 2.4 Net Convexity and Net Gex (the intraday vol-regime tape)

- **[CANONICAL]** `Net Convexity = total customer-bought GEX − total
  customer-sold GEX` (formula published in the docs' Spanish edition). "Net
  convexity is a measure of option buying vs. option selling … Due to the
  inverse correlation between underlying price and implied volatility, low
  convexity is mildly constructive on underlying price. Very high net
  convexity, which indicates high demand for options, usually only occurs
  during times of panic." (`canonical/orderflow_view.md`.)
- **[CANONICAL]** Net Gex "condenses the gex profile into a single measure",
  and the two combine into a four-case squeeze/selloff/reversion read: net gex
  very positive + bars relatively equal → squeeze likely; very positive + a
  single bar above price predominating → look for reversion there; mirrored on
  the negative side for selloffs and downside reversion.
- **[CANONICAL]** The convexity-dump-then-ramp pattern (jass, 2025-07-25, with
  chart): morning **lift** (customers buying convexity, vol bid) → sharp
  **dump** (holders selling out; net convexity collapses toward zero/negative)
  → directional **ramp** with the flipped dealer hedging as structural support.
  jass: "**those are the best longs tho. there's juice to lean on.**" Note this
  is the principals' dynamic version of the docs' static "low convexity is
  mildly constructive" claim.
- **[CANONICAL]** Post-dump regime: customers net short vol → lighter dealer
  hedging per move → "tape is loosey goosey" — no strong magnets; levels weaken.

### 2.5 Net -Vanna / Charm (late-day passive-flow pressure)

- **[CANONICAL]** "Net -vanna and charm approximate the magnitude of the
  passive hedging pressure generated by transactions so far that day as we
  progress into expiration": positive → customers gain deltas into expiry,
  dealers get shorter, **bullish passive dealer flows into expiry** — which
  "cease if/when price approaches those short calls and they become
  at-the-money". The doctrine's only hard numbers live here: **on SPX, net
  -vanna matters beyond $800MM magnitude in the last hour; beyond $1000MM it
  matters in the last couple of hours.** Extreme days feature extreme intraday
  reversals as traders front-run the unwind.
- **[CANONICAL — vendor self-caveat]** "Vanna and charm effects are dealer
  heavy, so **we are still learning best practices** when applied to daily
  classifications." The layer with the only numeric thresholds is also the one
  the vendor flags as least settled. Verify before any operational use.
- This pane connects directly to the late-day pinning doctrine
  (`canonical/convexity_ladder.md`: 0DTE negative convexity as close magnets
  via -vanna/charm) and to Steve's late-day fly lane.
- **[STRUCTURAL — UI observation 2026-08-06]** The live UI splits this into
  two separate metrics, **net vanna** and **net charm**, both beta-flagged
  (`screenshots/capture-protocol.md`) — a one-to-one match to the archived
  `zvanna`/`zcharm` field pair, and cleaner for the mapping than the docs'
  combined section suggested.

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
| What a positive GEX OF spike *is* | "Often call selling" (SPX short-gamma dominated), still marks local tops | "Cost of upside lifted" — call *buying* making upside expensive (Part 3) | **Same operational read (tops/bottoms), contradictory flow attribution.** Measurable: `gexoflow` sign vs classified flow. |
| Two-signal reversal entry | jass 2025-09-28: long gamma + directional GEX spike gives side | Part 3 teaches the identical pair, five months earlier, adding two qualifiers: spike must be *meaningful vs prior spikes*, and there must be *a trend to reverse* | **Agree** — independent convergence; Freddy's qualifiers are the operational sharpening |
| Post-entry management | — (no principal statement found) | Part 3: after reversal entry, watch Convexity OF for short-gamma momentum spikes in the new direction (liquidity provided = fuel) | Community-only, coherent, unverified — Phase 2 test |

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
| Aggregate Dex pane, "aggdex" call/put/net | `agg_call_dex`, `agg_put_dex`, `agg_dex` (+ `one_*`) | **[MEASURED — VERIFIED 2026-08-07]** tooltip anchor at 2026-08-06 19:59:59 UTC matches all three fields + spot exactly (`screenshots/capture-protocol.md` ledger) |
| DEX pane, "net" variant | `net_dex`, `net_call_dex`, `net_put_dex` (+ `one_*`) | **[MEASURED, unexplained]** — agg-vs-net distinction is vendor question #1; correlation 0.9989→0.53 across days. The docs define only "aggdex"; no "net dex" pane text found — the distinction remains undocumented. |
| Net Convexity tape (jass's cyan line) | `zcvr`/`ocvr` | **[MEASURED — VERIFIED 2026-08-07]** tooltip anchor: net convexity (next) −1854.82 = `ocvr` exact at the 20:00:00 UTC snapshot. **`cvr` = Net Convexity — the last unknown field, identified.** Experiment #1 remains as the *formula* cross-check: does the value equal the summed customer-signed state ladder, as the docs' formula claims. |
| Net Gex pane | `zgr`/`ogr` | **[MEASURED — VERIFIED 2026-08-07]** net gex (next) = `ogr` 346.95 at the same snapshot — consistent with the earlier `zgr` ≈ volume-based total GEX identity (docs: "condenses the gex profile into a single measure") |
| Convexity/GEX/DEX OrderFlow spike panes | `cvroflow`/`gexoflow`/`dexoflow` (+ `one_*`) | **[MEASURED — VERIFIED 2026-08-07]** tooltip anchors match all three `one_*oflow` fields exactly (36.15 / −6.30 / −0.49 at the close snapshot). Combined with the first-difference identities, the spike panes are literally the per-snapshot deltas of the cumulative panes. |
| Ladder levels repeated in view tooltips (major long/short gamma etc.) | `z_mlgamma`, `z_msgamma`, `o_*` — verbatim `state` republications | **[MEASURED]** 16 identities hold exactly |
| Net vanna / net charm panes | `zvanna`, `ovanna`, `zcharm`, `ocharm` | **[MEASURED — VERIFIED 2026-08-07]** net vanna @ "latest" = `zvanna` exactly (tooltip anchor 13:55:41 UTC; `ovanna` differs, ruling out second expiry) — confirming the `z*` ↔ latest / `o*` ↔ next mapping family-wide. `zcharm` presumed symmetric, one tour capture to confirm. |

## 6. Claims to test in Phase 2 (verification against the 62-day archive)

Ordered by leverage:

1. **Does Net Convexity equal its published formula?** The pane↔field identity
   is settled (2026-08-07: `cvr` *is* the Net Convexity pane, verified by
   tooltip anchor), so the experiment sharpens to internal consistency: sum
   the customer-signed state ladder and compare against `zcvr` — does the
   vendor's number actually equal "customer-bought GEX − customer-sold GEX"
   computed from their own ladder? A match makes jass's cyan line fully
   reconstructable and auditable from data we already store.
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
6. **SPX GEX-OF extrema claim** (vendor canonical): "positive gex orderflow …
   typically marks local tops, negative … local bottoms." Direct test:
   `gexoflow` sign/magnitude spikes vs local price extrema on the archive. Also
   adjudicates the call-selling-vs-call-buying attribution split (§4).
7. **Session-character signature** (vendor canonical): sell-offs marked by
   consistent positive convexity OF; grinds/squeezes by consistent negative.
   Day-level classifier from `cvroflow` sign persistence.
8. **Net -vanna thresholds** (vendor canonical, self-caveated): do SPX days
   with |net -vanna| > $800MM show distinct last-hour behavior (reversals,
   directional persistence) vs moderate days? Requires the vanna field
   semantics (`zvanna`/`ovanna`) to be pinned first.
9. **Post-entry momentum rule** (community, Part 3): after a two-signal
   reversal entry, does short-gamma flow in the new direction discriminate
   follow-through from failure? Joins naturally onto experiment 4.
10. **Freddy's spike-scenario claims** (community): morning-window reads,
    EOD "speculative positioning" reads — lower priority, community tier.
11. **Flow-state-at-confirm** (from the measured doc's own recommendation):
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

Resolved 2026-08-06: the vendor Orderflow page is captured and byte-verified
(`canonical/orderflow_view.md`); the Freddy series is complete at three parts,
all synthesized; the tracker's stale subscription preamble is fixed.

Remaining:

1. **Queued video material** (community tier, transcripts not yet pulled):
   the hour-long "Concepts review — Intro to OrderFlow" (`5yms1oOGp6k`,
   2025-02-17, pre-series source material), the
   live-application sessions (`ihRxcBJPYnU` 2025-05-06 NQ Orderflow;
   `AnZx2_Xt-xE` 2025-06-17), and the post-series product update
   (`AsNlSzOMxnA` 2025-10-27, "new tools" — may cover Orderflow changes newer
   than everything above).
2. **The vendor's Discord "Introduction to Orderflow" livestream** (announced
   on X, 2023): recording, if any, is behind the Discord. Worth a look from
   Steve's account if convenient — vendor-run, would be canonical.
3. **Vendor questions** — the 8-item list in the measured doc §3, headlined by
   agg-vs-net DEX (the docs define "aggdex" but never "net dex", so the
   question stands); the revised 7-item draft is on Steve's desk awaiting send.
4. **Two research-agent caveats to keep visible:** the operator identification
   (Fredy Sarmiento ↔ GexFuturesTrading channel) is inferred via LinkedIn/X,
   not vendor-confirmed; and an unverified lead credits "Freddy & Fabio — GEX
   live trading sessions (May 2026): the convexity-node methodology" — if
   real, that content is somewhere private, not on the channel.

## Revision log

- 2026-08-06 v2: vendor Orderflow docs captured firsthand → §§2.x rewritten
  with verbatim formulas and reads; Net Gex / Net Convexity / Net -Vanna-Charm
  panes added; Part 3 synthesized (two-signal rule convergence with jass,
  post-entry momentum rule, attribution divergence flagged); Phase 2 test list
  grown 7 → 11 [st-20nw].

- 2026-08-06 v1: initial draft — canonical/community synthesis from the
  existing corpus [st-20nw].
