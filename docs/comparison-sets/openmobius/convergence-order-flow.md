# Convergence: OpenMobius "Order Flow" (S2) against the OFB register (S1)

Every one of the 34 cards graded against
`knowledge/sources/orderflow-baseline-v1.md`, using the register's own
annotation vocabulary — **converge / diverge / extend / silent** — and adding new
`OFB-` numbers for claims S2 holds that we do not.

Grading date 2026-09-06. S2 = the OpenMobius `Order Flow` school, 34 cards.

---

## The headline, and it is a measurement

**The school named "Order Flow" contains no order flow.** Counted across the
core fields of all 34 cards, in the source and in the translation:

| term | occurrences |
|---|---:|
| delta | **0** |
| cumulative delta | **0** |
| order flow | **0** |
| absorption | **0** |
| aggressive (order) | **0** |
| tape | **0** |
| bid / ask | 3 / 0 |
| passive | 1 |
| footprint | 3 — all metaphorical ("the long footprint at the LVN", "the historical footprint of trades already done"), never the footprint chart |

Against, in the same fields: liquidity 76, POC 85, VAH 89, LVN 68, EMA 46, HVN
42, order block 41, FVG 30, institution 57, retail 44, market maker 15.

S2 is a **volume-profile and moving-average school**. Its "order flow" is
inferred from where volume accumulated historically, never observed from the
tape. That single fact governs most of the table below: S1 and S2 are answering
the same question — where will price react, and who is trapped — with
instruments that do not overlap at all.

**Consequence for the ICT question §6 was meant to settle:** this tranche gives a
real convergence count for a tenth of the volume, and it says the schools in this
knowledge base are named by *topic vocabulary*, not by *instrument*. A school
label in this corpus is not evidence about what a card actually measures. Any
decision to translate ICT's 1,027 cards should assume the same and budget for
grading against a register that may share none of its instruments.

---

## The register, claim by claim

| id | S1 claim (abbreviated) | S2 verdict | why |
|---|---|---|---|
| **OFB-01** | Price moves only when aggressive orders consume passive liquidity; indicators are downstream | **silent** | S2 never describes the mechanism. It reasons from where volume *accumulated*, not from what consumed what. Its causal agent is "the market maker", asserted, never observed. |
| **OFB-02** | Auction model: balance is agreed value; imbalance drives transition to a new range | **converge — strongly** | S2's HVN is defined as "the balanced value area" and its LVN as "the imbalance / vacuum". Same model, arrived at independently, in the same words. The strongest agreement in the set. |
| **OFB-03** | Retail buys breakouts and dips, institutions counter at wholesale; retail flow is the liquidity | **converge — emphatically, and it is S2's central theme** | Recurs in most cards: "retail contests inside the HVN, institutions act at the LVN"; "market makers deliberately stop just short so retail cannot get out flat"; "the longer the volume bar, the LESS likely an institutional order sits there". |
| **OFB-10** | Absorption / trapped participants: heavy aggressive volume with no follow-through implies a passive counterparty | **extend, on a different detector** | S2 holds the trapped-participant idea hard (trapped longs resting orders to get out flat at the HVN) but locates them by **volume density**, not by aggression without follow-through. Same population, incompatible instrument. It cannot corroborate S1's detector and does not contradict it. |
| **OFB-11** | Volume tail: prints thinning to matched pairs at a bar extreme validates the level | **silent** | Requires a footprint. S2 has none. |
| **OFB-12** | Delta outliers carry signal; no numeric threshold given | **silent** | Zero occurrences of delta. GAP-1 gets no help from this source. |
| **OFB-13** | Level quality is set by orderflow provenance — absorption strong, aggressive-buyers-alone weak | **converge on the principle, diverge on the test** | S2 also holds that levels differ in quality, but its test is **confluence**: a level is strong when several independent methods land on it (moving average + order block + VAH/VAL + FVG). Provenance in S1 is *what happened at the level*; in S2 it is *how many instruments agree about it*. |
| **OFB-20** | Reversal-first: on the FIRST test of a level, default to the reversal | **diverge** | S2's default at a level is explicitly the opposite: wait for a close, then trade the **retest with the trend**. Several cards warn against exactly the countertrend fade, in those words — "do not short against an uptrend on impulse after hearing an analysis". |
| **OFB-21** | Never take the initial break; require a defended retest | **converge — strongly** | S2's core mechanic. "After a close breaks VAH, buy the pullback to VAH"; the support-resistance flip is stated as the same logic as an order block. Independent arrival at S1's continuation protocol. |
| **OFB-22** | Three S/R plays: break→retest; reversal off trapped participants; positioned entry before the break | **partial: converge / extend / silent** | break→retest converges (see OFB-21). Reversal off trapped participants: extend, per OFB-10. Positioned entry before the break: **silent** — S2 always waits for the close. |
| **OFB-23** | CLC: context → location → confirmation from tape, **never from a candle close** | **converge on the first two, diverge flatly on the third** | S2's context and location steps map cleanly. Its confirmation step is the exact thing S1 forbids: 收线破坏 / 收线确认 — "a close that breaks", "wait for a close to confirm" — recurs across the set as the discipline that separates a real signal from an impulse. This is the sharpest disagreement in the register. |
| **OFB-24** | Confirmation timing is the R engine; a candle close widens the stop from ~2pt to ~7pt | **diverge, and S2 answers the objection** | S2 accepts the wider stop from waiting for a close, then recovers the R multiple a different way: **drop a timeframe**. "Validate on the lower timeframe with a tighter stop rather than absorbing pointless wick losses." Where S1 tightens the stop by confirming faster, S2 tightens it by confirming on a smaller chart. Both are answers to the same arithmetic. |
| **OFB-30** | Stops 1.5–3.5 ES points, just beyond the absorption level | **silent on the numbers; converge on the shape** | S2 gives no point values (it trades gold, silver, crude, ETH and A-shares, so ES points would not transfer). It places the stop "just beyond" the structure that justified entry — beyond the confluence zone, beyond the farther of two moving averages, above the previous block's VAH. Same rule, no numbers. |
| **OFB-31** | Target the opposing level, 7.5–13 points, 3–8R planned | **converge on the shape** | S2's range operation is "sell highs and buy lows" between VAH and VAL, targeting the opposing edge. Its worked examples cite 1:2 as the usual reward-to-risk — **materially lower than S1's 3–8R**, which is a real difference in claimed expectancy and is recorded as such. |
| **OFB-32** | Flat size 25–40 contracts, no sizing rule stated | **silent** | S2 states no sizing rule either. GAP-3 stands across both sources. |
| **OFB-40** | Marketing: "$208,000 in September", "236 profitable days" | **silent** | S2 makes no P&L claims. It does make unfalsifiable ones — see the gaps below. |

**Tally: 5 converge, 3 diverge, 1 extend, 5 silent, 2 partial.**

---

## What S2 adds — new claims, numbered per the register's rule

These are claims S2 holds that OFB does not. Evidence classes use the register's
vocabulary: **D** demonstrated with verified data, **A** asserted or illustrated,
**M** marketing.

- **OFB-50** Volume profile is the primary instrument for locating levels, and it
  works without switching timeframes: "the 5-minute and the 1-hour show
  essentially the same support," because the profile divides by price area rather
  than by time. [S2 `session_volume_profile`, `value_area_low`, `vrvp`; A —
  asserted repeatedly, never measured on any chart shown]
- **OFB-51** The gap-fill thesis: an LVN left by a fast move is very likely to be
  filled, and in a decline each wick point maps one-to-one to a gap left above.
  [S2 `liquidity_gap`, `low_volume_node`, cases 003/005; **A with worked
  examples** — the one-to-one wick-to-gap claim is asserted over a chart, not
  counted]
- **OFB-52** Inverted density rule: **the longer the volume bar, the less likely
  an institutional order rests there.** Institutions act at the vacuums; retail
  contests in the peaks. [S2 `hvn_lvn`, case 006; A] — *This is the one claim in
  S2 that is both novel against OFB and directly checkable against our own
  corpus.*
- **OFB-53** Multi-point timeframe validation: the market's "real" timeframe is
  the lowest one on which a level has earned three or more validation points;
  step up from the 1-minute until you find it, then trade and stop on that
  timeframe's EMA60. [S2 `multi_confluence_validation`, case 014; A]
- **OFB-54** Confluence as the strength test: a level carrying a moving average,
  an order block and an FVG at once, with a divergence, is the highest-certainty
  configuration. [S2 `multi_confluence_validation`; A]
- **OFB-55** Precedence rule: where the volume profile and the moving average
  conflict, **the moving average governs**, because it is "the market's cost
  price". [S2 `vrvp_svp_volume_profile`, `session_volume_profile`; A]
- **OFB-56** Session confluence: where the volume profiles of three consecutive
  trading sessions coincide at one price, that level is materially stronger. [S2
  `session_volume_profile`, case 015; A]
- **OFB-57** Tooling as method: an OB/FVG indicator that does not label the
  timeframe of the block it draws is unusable, because the stop must follow the
  block's timeframe. [S2 `strategy_indicator_flaw`; A] — a process claim, and the
  only card in the set that is about instrumentation discipline rather than the
  market.

---

## Gaps in S2 — what this source never specifies

- **S2-GAP-1** No numeric threshold anywhere, for anything. "Volume is thin",
  "the bar is long", "extension is large" are all eyeballed. S1's GAP-1 (no delta
  threshold) is not closed; it is joined by the same hole in every S2 measure.
- **S2-GAP-2** No losing trade, no win rate, no expectancy. The one self-reported
  result set (case 007: "shorted 4744–4745, took a profitable long below") is
  narrated, not journaled. S1's GAP-4 stands unchanged.
- **S2-GAP-3** Every causal claim about market makers is unfalsifiable as stated.
  "Market makers deliberately stop just short so retail cannot get out flat"
  describes an intent, not an observable. The corresponding *observable* — price
  stalling below a dense volume band — is measurable and is what OFB-52 isolates.
- **S2-GAP-4** No regime conditioning, exactly as in S1's GAP-5. Neither source
  says how its signals differ trending against rotating. **Two independent
  sources, both silent on the same axis** — which is the axis Steve's 2026-08-25
  provenance ruling left open. That is worth recording: the gap is not an
  accident of one source.
- **S2-GAP-5** Instrument transfer is never argued. The set claims the method
  "applies uniformly across gold, forex, crypto and A-shares" and demonstrates it
  on all of them, but never tests whether a volume-profile level behaves the same
  way in a 24-hour spot market and a session-bounded futures market. For SPX and
  /ES the session boundary is load-bearing, so the claim does not transfer for
  free.

---

## Two source defects found while translating

Neither was corrected silently; both are carried through and flagged here.

1. **`vrvp.aliases[7]` is `"VWAP"`.** VWAP is a different indicator from the
   visible-range volume profile. This is an error in the source's alias map, not
   a translation choice. It matters because an alias map is exactly what a later
   automated merge would trust.
2. **Case 004 writes 军线 where 均线 (moving average) is meant** — a homophone
   typo. Translated as moving average, which the surrounding sentence requires.

---

## What is worth our time, and what is not

Stated as a recommendation for the register's curation, not as anything codified.

**One claim here is worth measuring against our own corpus: OFB-52**, the
inverted density rule. It is novel against OFB, it contradicts the intuition that
heavy volume marks institutional interest, and unlike everything else in S2 it is
checkable with what we already collect — we hold the 1-second orderflow archive
and the footprint corpus, so "does price react differently at volume peaks than
at volume vacuums" is a measurement, not an opinion.

**OFB-51's gap-fill thesis is second**, and cheaper than it looks: it needs only
price history and a volume profile, both of which the corpus has.

**The rest is silent where it matters to us.** S2 cannot corroborate absorption,
the volume tail, or delta outliers — the three OFB signals that are actually
scorer-detectable — because it has no instrument that sees them. A source that
shares our vocabulary but not our instruments cannot confirm our detectors, and
treating its agreement on OFB-02 and OFB-03 as validation of the orderflow model
would be exactly the kind of manufactured corroboration the register format
exists to prevent.

[st-ow3p · st-snd8]
