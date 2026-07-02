---
code: MRF
name: Mean Reversion Fade
status: worthy
adopted: 2026-07-02
source: InvestiTrade
instruments: [ES, SPX, singles]
favored_conditions: [range-chop, gex-pos, near-magnet, at-key-level, mancini-carmine-confluence]
avoid_conditions: [trend-up, trend-down, vol-high, gex-neg, room-to-travel]
indicators: [vwap, bollinger-bands, rsi, cumulative-delta]
rationale: "After an extended, exhausting push, price becomes statistically overextended from its anchors and snaps back to the mean. The fade takes defined risk at the extreme; it only works in ranging, dealer-dampened tape — never against a live trend."
updated: 2026-07-02
---
## Thesis

After a parabolic, exhausting move, price sits well outside its anchors (VWAP,
20 EMA, Bollinger band). A fade captures the snap-back to the mean, entered at
the extreme with tightly defined risk. This is a counter-trend trade — its whole
edge depends on the tape being range-bound, not trending.

## Setup

- Price >= 2.5 standard deviations from VWAP, or outside the Bollinger band.
- RSI(14) >= 80 (fade the highs) or <= 20 (fade the lows) on the 5-min.
- RVOL declining — the move is exhausting, not accelerating.
- At least one reversal candle (doji, hammer, shooting star, engulfing) printed.
- Broader tape not making fresh extremes in the move's direction.

## Entry

- **Standard:** break of the reversal candle's opposite extreme (e.g. break of
  the doji low for a short fade).
- **Aggressive:** enter into the reversal-candle body on the momentum shift with
  a tight stop.

## Stop

- Just beyond the reversal candle's wick extreme.
- Absolute cap 1.0 ATR from entry — if it needs to be wider, skip the fade.

## Targets

- T1: return to VWAP.
- T2: the 20 EMA on the 5-min.
- T3: the prior consolidation area.

## Invalidation

- A new candle prints a fresh extreme beyond the reversal candle.
- A catalyst (news, headline) drops mid-move — exit immediately.
- RVOL spikes again on the continuation candle — the reversal is failing.

## Sizing

- Risk 0.5% of account per trade. Cap concurrent MRF exposure at ~2 positions —
  fades are lower conviction and correlate on a risk-off flush.

## Regime fit (notes)

Best condition is a ranging, choppy tape with positive GEX (dealer hedging pins
and reverts price) and price parked at a magnet/wall. Never fade a live trend:
in a strong up- or down-trend the "overextension" just keeps extending. High
volatility makes fades very risky (the squeeze runs), and open room-to-travel is
the wrong backdrop — a fade wants a wall to lean on, not clear air.

## Entry checklist

- [ ] Price >= 2.5 SD from VWAP (or outside the Bollinger band)
- [ ] RSI(14) >= 80 or <= 20 on the 5-min
- [ ] RVOL declining into the extreme
- [ ] A reversal candle has printed
- [ ] Broader tape not making a fresh extreme with the move
- [ ] No live catalyst driving the push

## Management checklist

- [ ] Stop just beyond the reversal-candle wick, within 1.0 ATR
- [ ] At T1 (VWAP): trim and de-risk
- [ ] At T2 (20 EMA): trim again
- [ ] Exit the remainder into the prior consolidation
- [ ] Bail immediately on a fresh extreme or a mid-move catalyst
