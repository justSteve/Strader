---
code: TCP
name: Trend Continuation Pullback
status: worthy
adopted: 2026-07-02
source: InvestiTrade
instruments: [ES, SPX, singles]
favored_conditions: [trend-up, trend-down, vol-low, room-to-travel, level-to-level-room, mancini-carmine-confluence]
avoid_conditions: [range-chop, vol-high, news-scheduled, near-magnet]
indicators: [ema-stack, vwap, rvol, luxalgo-trend]
rationale: "In an established trend, an orderly pullback to dynamic support offers a with-trend entry at improved R/R. Trend alignment does the heavy lifting, so this is a high-win-rate continuation play in clean, directional tape."
updated: 2026-07-02
---
## Thesis

In a clearly established trend, price pulls back to dynamic support (a rising or
falling EMA, VWAP, or a prior breakout level) and then resumes in the trend
direction. Entering on the pullback captures the continuation leg at better R/R
than chasing the impulse.

## Setup

- Clear trend structure: higher highs & higher lows (up) or lower lows & lower
  highs (down) on the 15-min.
- Pullback to the 8 EMA, 20 EMA, or VWAP on the 5-min without breaking structure.
- Orderly pullback — low RVOL, small candles (consolidation, not distribution).
- EMA stack aligned (price > 8 > 20 > 50 for longs); reduce or skip if broken.
- Broader tape in the same trend direction.

## Entry

- The resumption candle: an RVOL uptick that breaks the pullback's high (long) or
  low (short) back in the trend direction.

## Stop

- Below the pullback low (long) / above the pullback high (short) — and it must
  hold the anchoring EMA. If price closes back through the EMA, the trade is void.

## Targets

- T1: the prior swing high/low.
- T2: 2R measured from entry.
- T3: the trend-channel boundary or the next daily level.

## Invalidation

- Pullback deepens into distribution (rising RVOL, large opposing candles).
- Price closes beyond the 50 EMA — the trend may be breaking.
- Broader tape rolls against the trend.

## Sizing

- Risk 0.5% per trade; enter full size on the trigger. Cap concurrent TCP
  exposure at ~3 positions.

## Regime fit (notes)

Best in a clean, directional tape — low volatility trends are ideal because the
pullbacks stay orderly and structure is readable. Skip outright in a range (no
trend to continue). Reduce in high volatility (pullbacks turn into reversals),
avoid entering into a magnet that caps the continuation, and stand down around
scheduled news that can snap the trend.

## Entry checklist

- [ ] Trend structure intact on the 15-min
- [ ] EMA stack aligned in the trade direction
- [ ] Pullback is orderly (low RVOL, small candles)
- [ ] Resumption candle breaks the pullback extreme on an RVOL uptick
- [ ] Broader tape agrees with the trend
- [ ] Clear of scheduled news

## Management checklist

- [ ] Stop below/above the pullback extreme, holding the anchor EMA
- [ ] At T1: trail stop to breakeven
- [ ] At T2: trail stop to T1
- [ ] Let the runner work toward T3 until structure breaks
- [ ] Exit on a close beyond the 50 EMA
