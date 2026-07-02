---
code: ORB
name: Opening Range Breakout
status: worthy
adopted: 2026-07-02
source: InvestiTrade
instruments: [ES, SPX, singles]
favored_conditions: [gap-up, gap-down, vol-high, news-scheduled, room-to-travel, mancini-carmine-confluence]
avoid_conditions: [range-chop, vol-low, near-magnet]
indicators: [opening-range, rvol, vwap, premarket-levels]
rationale: "The first 15-30 minutes set an opening range; a decisive, high-volume break of it signals institutional intent for the session. A pre-market gap or catalyst is the fuel that makes the break follow through."
updated: 2026-07-02
---
## Thesis

The first 15-30 minutes of the session define an opening range. A decisive break
of that range, on strong volume, signals directional intent for the day and
offers a high-probability trade with a clean, mechanical stop and target frame.

## Setup

- ORB-15 preferred (first 15 minutes) — balances speed and reliability over
  ORB-5 (noisy) and ORB-30 (slow).
- A meaningful pre-market gap or catalyst (news, data, event).
- Opening-range height <= ~3% of price — if the range is too wide, skip.
- Breakout candle closes fully outside the opening range.
- RVOL >= 2.0x on the breakout candle.

## Entry

- **Preferred:** first pullback to the broken ORB level after the initial break.
- **Aggressive:** on the breakout candle's close outside the range.
- Long on a break above the range high; short on a break below the range low.

## Stop

- The midpoint of the opening range.

## Targets

- T1: 1x the opening-range height projected from the break.
- T2: 2x the opening-range height.
- T3: the pre-market high (long) / pre-market low (short).

## Invalidation

- Price falls back inside the opening range and closes there (failed break).
- RVOL collapses on the break — no institutional participation.
- A whippy, two-sided open with no clean range definition.

## Sizing

- Risk 0.5% per trade. Gap-with-direction (gap up + long, gap down + short) is
  the full-size combo; a fade of the gap or a flat open is half size. Cap
  concurrent ORB exposure at ~2 positions.

## Regime fit (notes)

Thrives on a gap and volatility — a news-catalyst day is a green light because
the catalyst supplies the follow-through. Wants open room to travel to the target
projection. Reduce in a rangy, low-volatility open (the break fails to extend),
and avoid setups where a magnet/wall sits just beyond the range and caps the move.

## Entry checklist

- [ ] Opening range defined (ORB-15), height <= ~3% of price
- [ ] Pre-market gap or catalyst present
- [ ] Breakout candle closes fully outside the range
- [ ] RVOL >= 2.0x on the break
- [ ] Gap direction aligns with the break (for full size)
- [ ] Clear room to the target projection

## Management checklist

- [ ] Stop at the opening-range midpoint
- [ ] At T1 (1x range): trim, stop to breakeven
- [ ] At T2 (2x range): trim again
- [ ] Runner toward the pre-market extreme
- [ ] Exit on a close back inside the range or an RVOL collapse
