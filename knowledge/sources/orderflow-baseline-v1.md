---
type: register
status: source
title: "Orderflow Baseline v1 — the Carmine claim register"
description: "S1: Carmine Rosato's orderflow series as a numbered claim register with evidence classes; hypotheses with attribution, never doctrine"
source_id: OFB
timestamp: 2026-08-28T21:42:01-05:00
metadata:
  filed_from: 20260828T214201__Desk__orderflow-baseline-v1-carmine
  filed_on: 2026-09-06
  filed_by: st-snd8
  claims: 16
  gaps: 5
---

# Orderflow Baseline v1 (OFB) — S1, Carmine Rosato

**STATUS `source`. This file is not canon and the emitter lane refuses it by
status.** Every entry below is a **claim with attribution**, not a rule we hold.
The demonstrated sample behind the series is seven winning trades, curated — no
losers shown, no win rate, no track record. Read every line as "S1 asserts X,"
never as "X is true."

Filed 2026-09-06 from Desk's bridge memo with its provenance block intact
(st-snd8). Corrections amend in place, per Ruling 12a.

**Count, measured from this file: 16 `OFB-` claims and 5 `GAP-` entries.** Other
beads have said 24; that figure is the ID range (01–40), not the claim count.

## Register format

`OFB-##` | claim | source | evidence class:

| class | meaning |
|---|---|
| **D** | demonstrated with verified on-screen data |
| **A** | asserted or illustrated, no supporting data |
| **M** | marketing — excluded from interpretation |

A later source (S2, S3, …) annotates each ID **converge / diverge / extend /
silent**, and adds new OFB numbers for claims we do not yet hold. S1 is this
series; episode cites are S1 episode numbers.

## Premise

- **OFB-01** Price moves only when aggressive (market) orders consume passive
  (limit) liquidity; indicators and "concepts" are downstream of order flow.
  [S1 ep1; A]
- **OFB-02** Auction model: balance is a range where both sides agree on value;
  an imbalance event drives the transition to a new range. [S1 ep1; A]
- **OFB-03** Retail systematically buys breakouts and dips and sells panics;
  institutions counter — accumulating at wholesale (demand zones, stop hunts)
  and distributing into strength. Retail flow is the liquidity being traded
  against. [S1 ep1, ep4; A]

## Signals

- **OFB-10** Absorption / trapped participants: heavy aggressive volume at a
  price with NO follow-through implies an active passive counterparty, so a
  reversal is a candidate. Heavy selling that does not drop price means a
  passive buyer; heavy buying that does not lift price means a passive seller.
  [S1 ep2, ep5; D — footprint examples frame-verified]
- **OFB-11** Volume tail: prints thinning to matched pairs at a bar extreme
  (verified examples 29×29, 136×136, 51×51) mean the last buyer bought and the
  last seller sold; it validates the level. [S1 ep5; D]
- **OFB-12** Delta outliers carry signal, but S1 defines NO numeric threshold —
  "just an outlier in the data." Verified examples: −735 and −1171 at the Oct 3
  low; +1633 at the Sep 27 break; +4000 at the Oct 9 level. [S1 ep3, ep6; D for
  the examples; see GAP-1]
- **OFB-13** S/R quality is defined by orderflow provenance: a level is strong
  when its prior defense came from seller exhaustion or absorption, and weak
  when the bounce came from aggressive buyers alone. [S1 ep5; A with worked
  examples]

## Frameworks

- **OFB-20** Reversal-first at levels: on the FIRST test of a level, default to
  looking for the reversal (his "~99%" is rhetoric, not measured); aggressive
  volume into the level without continuation is a fade. [S1 ep6; A]
- **OFB-21** Continuation protocol: never take the initial break. (1) Confirm
  strong volume in the break direction. (2) Require pullbacks to HOLD without
  rejection, and enter the retest. A defended retest proves stronger hands.
  [S1 ep3, ep6; A]
- **OFB-22** Three S/R plays: break-then-retest; reversal off trapped
  participants; positioned entry BEFORE the break, with confirmation, using the
  level as target. [S1 ep5; A]
- **OFB-23** CLC rule: CONTEXT (trend; today's volume against average; higher
  timeframes for location and context only) → LOCATION (a level of interest) →
  CONFIRMATION read live from tape and footprint — "The Now" — never from a
  candle close. [S1 ep7; A]
- **OFB-24** Confirmation timing is the R engine: waiting for a candle close
  widens the stop from ~2 points to ~7 and destroys the R multiple; tape-level
  confirmation is what makes 1.5–3.5 point stops possible. [S1 ep7; D — the
  trade-log arithmetic backs it]

## Execution — from the seven verified journaled trades

- **OFB-30** Stops of 1.5–3.5 ES points, placed just beyond the absorption level
  that justified entry. [S1 eps 2, 3, 5, 7; D]
- **OFB-31** Target at the opposing level, 7.5–13 points out; planned 3–8R,
  realized 4–10R across the sample. [D]
- **OFB-32** Size shown flat at 25–40 contracts, with no stated sizing rule.
  [D as observation only]

## Marketing tier — excluded from interpretation

- **OFB-40** "$208,000 in September"; "236 profitable days" (Goldman overlay).
  The histogram sums internally, but provenance is his slide, not a broker
  record. [M]

## Gaps — what the series never specifies

- **GAP-1** No numeric delta or volume outlier threshold. Our scorer needs one;
  whatever we adopt (a session-relative z-score would honour his "outlier in the
  data" phrasing) is OUR synthesis — never attribute it to S1.
- **GAP-2** No loss management beyond initial stop placement. No losing trade is
  shown, and nothing covers exiting when confirmation fails after entry.
- **GAP-3** No position-sizing model.
- **GAP-4** No win rate and no expectancy; the sample is curated winners.
- **GAP-5** No regime conditioning — nothing on how the signals differ trending
  against established rotation. That is exactly the axis Steve's 2026-08-25
  provenance ruling left open in our own canon, and S1 is silent on it, so the
  regime question stays open with no source.

## Annotations from later sources

| source | filed | what it annotates |
|---|---|---|
| S2 — OpenMobius `Order Flow` school, 34 cards | 2026-09-06 | `docs/comparison-sets/openmobius/` — see the convergence table there [st-ow3p] |

Related: [[carmine-rosato-investitrade-lvn-method]],
[[zone-framework-equivalence]].
