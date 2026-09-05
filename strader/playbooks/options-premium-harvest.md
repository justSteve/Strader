---
code: OPH
name: Options Premium Harvest
status: worthy
adopted: 2026-07-02
source: InvestiTrade
instruments: [SPX]
favored_conditions: [ivr-high, vol-high, range-chop, gex-pos, near-magnet]
avoid_conditions: [ivr-low, vol-low, news-scheduled, gex-neg, room-to-travel]
indicators: [iv-rank, delta, dte, gex]
rationale: "Sell defined-risk premium when implied volatility is rich and likely to revert. The edge is IV overpricing realized volatility most of the time; the enemy is a directional break, so this wants pinning tape, not trend."
updated: 2026-07-02
note: "Catalogue import from InvestiTrade (st-c71), not one of Steve's plays — he trades long premium only; retained as-is by Steve 2026-09-05 (Desk UPDATE on st-2opj), not a live strategy record."
---
## Thesis

Collect theta by selling options premium when implied volatility is high and
likely to revert to the mean. The statistical edge is that IV overprices realized
volatility a majority of the time. This is a neutral, defined-risk position trade
— its risk is a sharp directional move, so it wants dampened, pinning tape.

## Setup

- IV Rank >= 40 (prefer >= 60) — premium is genuinely rich, not just nominal.
- Short strike at 0.20-0.30 delta (roughly 70-80% probability OTM).
- 21-45 DTE at entry.
- For spreads: target credit >= 1/3 of the width.
- Liquid underlying, tight bid/ask (<= ~$0.05 per leg).

## Entry

- Choose the structure to the bias: iron condor (neutral), bull put spread
  (bullish, defined risk), bear call spread (bearish), cash-secured put or
  covered call (directional-neutral). Enter for a credit at the delta/DTE above.

## Stop

- Defined-risk by construction (max loss = width − credit for spreads). Manage,
  don't hard-stop intraday: exit on the loss rule below.

## Targets

- Close at 50% of max credit — do not hold to expiration for the last dollar.

## Invalidation

- IV Rank collapses below the entry threshold before entry — the edge is gone.
- Underlying makes a sharp directional move that pressures the short strike —
  assess delta and roll or close.
- A binary event (earnings, scheduled data) falls inside the holding window.

## Sizing

- Risk up to 2% of account per position (higher than the intraday plays because
  the risk is defined and the hold is longer). Cap concurrent OPH exposure at ~5.

## Regime fit (notes)

Best in high-IV-rank, ranging, positive-GEX tape where dealer hedging pins price
and premium bleeds — a magnet nearby helps the pin. Skip when IV rank is low or
volatility is quiet (nothing to harvest), avoid scheduled-news/binary events, and
treat negative GEX and open room-to-travel as hostile: both let the underlying
run into the short strike.

## Entry checklist

- [ ] IV Rank >= 40 (prefer >= 60)
- [ ] Short strike at 0.20-0.30 delta
- [ ] 21-45 DTE
- [ ] Credit >= 1/3 of width (for spreads)
- [ ] No binary event inside the holding window
- [ ] Liquid chain, tight spreads

## Management checklist

- [ ] Close at 50% of max credit
- [ ] At 21 DTE: evaluate rolling or closing
- [ ] Close for a defined loss at 2x credit received
- [ ] On a sharp directional move: assess delta, roll or close
- [ ] Never let a defined-risk spread ride into expiration unmanaged
