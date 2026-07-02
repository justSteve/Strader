---
code: GF
name: Gap Fill
status: worthy
adopted: 2026-07-02
source: InvestiTrade
instruments: [ES, SPX, singles]
favored_conditions: [gap-up, gap-down, range-chop, vol-low, gex-pos]
avoid_conditions: [trend-up, trend-down, vol-high, gex-neg]
indicators: [gap-size, rvol, vwap, prior-close]
rationale: "Un-catalyzed gaps leave a price void the market tends to revisit. The trade fades the gap back toward the prior close, and only qualifies on common or exhaustion gaps in calm, reverting tape."
updated: 2026-07-02
---
## Thesis

Price gaps create unfilled voids on the chart, and the market frequently revisits
and fills them — especially when the gap is not driven by a fundamental catalyst.
The trade fades the gap back toward the prior close. It is a mean-reversion play
and lives or dies on gap classification.

## Setup

- Gap >= 0.5% but <= 5% of the prior close — very large gaps are breakaway
  candidates and are skipped.
- Gap is a common or exhaustion type (no major catalyst).
- Price has begun reverting toward the gap — at least one candle body toward fill.
- RVOL declining from the gap open (fading interest in the gap direction).
- Broader tape not trending hard in the gap direction.

## Entry

- On the first 5-min candle that shows a reversal toward the gap.

## Stop

- Beyond the gap-open extreme (the furthest point from the fill).

## Targets

- T1: 50% of the gap filled.
- T2: full gap fill (the prior close).
- T3: prior close plus a small extension if momentum carries through.

## Invalidation

- A catalyst surfaces — reclassify as a breakaway gap and stand down.
- RVOL re-accelerates in the gap direction (the gap is extending, not filling).
- Broader tape trends hard with the gap.

## Sizing

- Risk 0.5% per trade. Cap concurrent GF exposure at ~2 positions.

## Regime fit (notes)

Needs a gap to work at all, then wants calm, ranging, positive-GEX tape where
price reverts — low volatility gives the cleanest fills. Avoid on trend days
(gaps fill far less often), in high volatility (erratic, unreliable fills), and
under negative GEX where the move runs away from the fill instead of toward it.

## Entry checklist

- [ ] Gap between 0.5% and 5% of prior close
- [ ] Gap is common or exhaustion type (no catalyst)
- [ ] At least one candle body reverting toward the gap
- [ ] RVOL declining from the gap open
- [ ] Broader tape not trending with the gap

## Management checklist

- [ ] Stop beyond the gap-open extreme
- [ ] At T1 (50% fill): trim, stop to breakeven
- [ ] At T2 (full fill / prior close): trim again
- [ ] Optional runner to a small extension past the prior close
- [ ] Exit immediately if a catalyst reclassifies the gap as breakaway
