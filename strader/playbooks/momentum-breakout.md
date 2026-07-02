---
code: MB
name: Momentum Breakout
status: worthy
adopted: 2026-07-02
source: InvestiTrade
instruments: [ES, SPX, singles]
favored_conditions: [trend-up, trend-down, vol-high, gex-neg, room-to-travel, level-to-level-room, mancini-carmine-confluence]
avoid_conditions: [range-chop, vol-low, near-magnet, gex-pos]
indicators: [rvol, vwap, cumulative-delta, luxalgo-trend]
rationale: "A clean break of a level tested at least twice, on elevated relative volume, signals institutional intent; the edge is one large winner funded by many small, quickly-invalidated losers. Curated worthy from Steve's InvestiTrade reference; strongest when the broken level is a Mancini<->Carmine confluence."
updated: 2026-07-02
---
## Thesis

Price consolidates against a significant level (prior-day high/low, VWAP, a key
round number, or a Mancini level) then breaks out with elevated volume, signaling
institutional participation and directional conviction. The trade rides the
initial impulse and scales out into strength.

## Setup

- A clearly defined level, tested at least twice from the same side.
- Relative volume (RVOL) >= 1.5x the 20-day average on the breakout candle.
- Breakout candle body fills >= 60% of its range (no long-wick rejection).
- Broader tape (ES/SPX) trending in the same direction, or not fighting it.
- Not within 30 minutes of a scheduled economic release or Fed announcement.

## Entry

- **Conservative (preferred):** first pullback that holds the broken level, then
  a resumption candle in the breakout direction. Better R/R, lower fill rate.
- **Aggressive:** the breakout candle's close beyond the level. Higher slippage,
  best only in fast tape with clear order-flow confirmation.

## Stop

- Hard stop just inside the consolidation (below the low for longs, above the
  high for shorts).
- Floor the stop at 0.5 ATR to avoid noise stop-outs; cap it at 1.5 ATR — if the
  level needs a wider stop than that, skip the trade.

## Targets

- T1 at 1R: trim ~40% and move the stop to breakeven.
- T2 at 2R: trim another ~35%.
- T3 at 3R or the measured move (consolidation height projected from the break):
  exit the runner, or trail it under structure.

## Invalidation

- Breakout immediately reverses back inside the consolidation (bull/bear trap).
- RVOL falls below 1.0x within two candles of the break — no participation.
- The broader tape reverses hard against the setup.
- Repeated failed breakout attempts on the same level in one session.

## Sizing

- Risk 0.5% of account per trade; size = risk / (entry − stop) in underlying
  points. Cap concurrent MB exposure at ~3 positions.

## Regime fit (notes)

Best in a trending, volatile tape with room to the next level, and stronger when
GEX is negative (dealer hedging lets moves run). Reduce size in chop and near a
magnet/wall; skip in quiet, low-volatility tape where breakouts fail to follow
through, and treat positive-GEX days (price pins/reverts) as hostile. On a
news-catalyst day an MB is acceptable if the catalyst is the driver.

## Entry checklist

- [ ] Level identified and tested >= 2x from the same side
- [ ] RVOL >= 1.5x on the breakout candle
- [ ] Breakout body >= 60% of candle range
- [ ] Order flow confirms (cumulative delta / footprint agree)
- [ ] Broader tape not fighting the direction
- [ ] Clear of scheduled news by 30+ minutes

## Management checklist

- [ ] Stop set inside the consolidation, within 0.5–1.5 ATR
- [ ] At T1: trimmed ~40%, stop to breakeven
- [ ] At T2: trimmed ~35%, stop trailed to T1
- [ ] Runner trailed under structure toward T3
- [ ] Exit immediately on a back-inside reversal or RVOL collapse
