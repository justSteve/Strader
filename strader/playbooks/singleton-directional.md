---
code: SGL
name: Singleton Directional
status: candidate
adopted: 2026-07-18
source: Steve
instruments: [SPX, 0DTE-singles]
favored_conditions: [at-key-level, level-to-level-room, room-to-travel, vol-high, gex-neg, window-open, window-late, mancini-carmine-confluence]
avoid_conditions: [range-chop, vol-low, window-midday, near-magnet]
indicators: [mancini-levels, footprint, cumulative-delta, bookmap, expected-move, recognizer-stages]
rationale: "A 0DTE single deep enough in the money is a futures contract on its last day. Trade it like the futures strategies it proxies: a completed reversal at a mapped level, delta capture level-to-level, short hold, fast cut."
updated: 2026-07-18
---
## Thesis

Buy movement, not time. A 0DTE SPX single at 0.60+ delta moves nearly
point-for-point with the underlying — the option is the futures proxy, and the
Greeks are a correction factor, not the strategy. The trade is a short-hold
delta capture from one mapped level toward the next, entered only when a
reversal has *completed* at the level, and cut on the first wrong breath.

## Trigger doctrine (governing) — PROPOSED, needs Steve's ratification

The 2026-07-17 passed setup (7460C, stood down, $11 → $41) proved the record
must name its governing gate — that day the two borrowed systems disagreed live
and the stand-down was undecidable. This record's rule:

- **Primary gate: the completed price-event.** Mancini-style failed breakdown /
  reclaim at a significant level, read as the four stages — flush, stall, flip,
  **confirm**. Stage four at the level IS the entry trigger. This is Steve's
  own drilled read, not a borrowed one.
- **Order flow is a size modifier, not a veto.** Confirmation on the tape
  (delta flip, absorption at the low) = full size. Absent/ambiguous tape =
  base size. Only an *active contradiction* — heavy paid aggression against
  the trade's direction at the entry level — stands the trade down.
- Every stand-down gets logged against these criteria so passed setups score
  as **save or miss** against our own doctrine, not someone else's.

## Setup

- A significant mapped level: Mancini support/resistance, a confluence shelf,
  or a range edge with prior history. No level, no trade.
- The four-stage sequence completes AT that level (flush through, stall, flip,
  price retakes the level on paid aggression).
- Clear room to the next mapped level — the target must exist before entry.

## Strike selection (delta-first, per the 2026-07-17 research brief)

| Context | Delta band | Why |
|---------|-----------|-----|
| Morning directional (default) | **0.60–0.70** | Majority intrinsic; tracks the level stop |
| At-the-level, resolution expected in minutes | 0.50–0.60 | Max gamma per dollar, justified only by short intended hold |
| Midday | 0.70+ or stand aside | Decay accelerating, movement thin |
| Late day (13:00+ CT) | First strike ITM (~0.7–0.9) | Extrinsic gone; option ≈ future |
| Below 0.50 | Declared lottery only, sized as one | Different trade, different distribution — never the singleton |

Measure strike distance in expected-move units, not points — the same 20 points
is far at 09:05 and near at the open.

## Entry

- Long calls on a confirmed reclaim (upward resolution), long puts on a
  confirmed rejection/breakdown (downward resolution). Direction = the
  confirm's direction. Say the flush direction out loud first.

## Stop

- Structure, not dollars: the trade is wrong when price trades back through the
  entry level with paid aggression — the fast cut, first wrong breath. With
  0.60+ delta the option loss tracks the price stop honestly.

## Targets

- T1: the next mapped level. Take it — modest target, grinder's edge.
- Runner only when level-to-level room is exceptional and the tape is paying.

## Invalidation

- Confirm fails to hold (price re-loses the level) — exit immediately.
- Bar deltas fade to nothing after entry — the move is unfueled; scratch it.
- Time: a singleton that goes nowhere in 15–20 minutes is wrong by thesis
  (movement was the product); scratch before theta makes the decision.

## Sizing

- Max 2% account risk per trade; positions >$5,000 notional escalate to Steve.
- Full size only with order-flow confirmation (per trigger doctrine).
- One singleton at a time. Midday: stand aside is a position.

## Regime fit (notes)

Wants movement and mapped structure: negative-GEX tape (moves run), volatility
elevated, clear level-to-level room. The open and the late-day windows are the
edges; midday is the desert. A nearby magnet/wall between entry and target caps
the very move the trade buys — skip. Positive-GEX pin days favor the butterfly
instead; that is the pair's division of labor.

## Entry checklist

- [ ] Mapped level named; next level named (the target exists)
- [ ] Flush direction stated out loud
- [ ] Four stages complete — confirm printed AT the level
- [ ] Delta band chosen from the table for this window
- [ ] Order flow: confirming (full size) / neutral (base) / contradicting (stand down)
- [ ] Room-to-travel: no magnet between entry and target

## Management checklist

- [ ] Cut on a re-loss of the entry level — no averaging, no hoping
- [ ] Scratch if bar deltas die or 15–20 min pass without progress
- [ ] Take T1 at the next level; runner only on exceptional room
- [ ] Log every stand-down and every passed setup: save or miss vs THIS record
