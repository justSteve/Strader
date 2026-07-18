---
code: SGL
name: Singleton Expression (0DTE Single as Futures Proxy)
status: candidate
adopted: 2026-07-18
source: Steve
instruments: [SPX, 0DTE-singles]
favored_conditions: [vol-high, gex-neg, room-to-travel, level-to-level-room]
avoid_conditions: [vol-low]
indicators: [expected-move, footprint, cumulative-delta]
rationale: "A 0DTE single deep enough in the money is a futures contract on its last day. This record is the EXPRESSION layer, not a setup: the house standard for executing any directional setup (FBD first among them) through SPX singles — delta-first strike selection, sizing, escalation, and the vehicle-choice rule versus the butterfly."
updated: 2026-07-18
---
## What this record is (and is not)

**This is not a peer strategy.** The peer set of setups is: the six
InvestiTrade records, FBD (Mancini), and LDF (the V-dump fly). This record is
the **expression layer** those directional setups execute through — the answer
to "a setup has resolved directionally at a level; how does that become an SPX
options position?" It carries no trigger of its own: *entry timing always
belongs to the setup record* (FBD's four criteria, ORB's breakout rules, etc.).

Pending a COO decision on a `kind: setup | expression` field in the Playbook
entity, this distinction lives here in prose: **the evaluator should not rank
SGL against day conditions as if it were a setup.** Its favored/avoid tags
describe when the *vehicle* fits, not when to trade.

## The vehicle thesis

Buy movement, not time. At 0.60+ delta a 0DTE single moves nearly
point-for-point with the underlying — the option is the futures proxy, the
Greeks are a correction factor, not the strategy. Short hold, delta capture,
fast cut: the setup supplies the where and when; this record supplies the what.

## Strike selection (delta-first — the core table)

| Context | Delta band | Why |
|---------|-----------|-----|
| Morning directional (default) | **0.60–0.70** | Majority intrinsic; loss tracks the level stop honestly |
| At-the-level, resolution expected in minutes | 0.50–0.60 | Max gamma per dollar, justified only by short intended hold |
| Midday | 0.70+ or stand aside | Decay accelerating, movement thin |
| Late day (13:00+ CT) | First strike ITM (~0.7–0.9) | Extrinsic gone; option ≈ future |
| Below 0.50 | Declared lottery only, sized as one | Different trade, different distribution — never the singleton |

Measure strike distance in expected-move units, not points — the same 20 points
is far at 09:05 and near at the open. Prefer slightly-ITM where the bid/ask
spread is tighter relative to the intended move.

## Vehicle choice — singles vs the butterfly (the division of labor)

- **Singles collect on the journey** (linear delta capture): movement regimes —
  negative GEX, elevated vol, clear level-to-level room. Distance-to-magnet is
  the shared signal.
- **The fly collects at the destination** (convex, pin): positive-GEX pin
  regimes in the late window — that trade is the LDF record, not an SGL sizing
  decision.
- If neither regime reads clean, no vehicle is a position too.

## Stop and time discipline

- Structure stop comes from the setup record (e.g. FBD: below the lowest low).
  The 0.60+ delta band exists so the option's loss tracks that price stop.
- Time-scratch: a singleton going nowhere in 15–20 minutes is wrong by thesis —
  movement was the product. Scratch before theta makes the decision.

## Sizing and escalation

- Max 2% account risk per trade; anything >$5,000 notional escalates to Steve
  before entry — hard boundary.
- Size modulation by tape (per the setup's house adaptation): confirming order
  flow = full size; neutral = base size; active contradiction = the setup
  stands down (not a sizing decision).
- One singleton at a time.

## Execution checklist

- [ ] A setup record's entry gate is COMPLETE (this record adds no trigger)
- [ ] Delta band chosen from the table for the current window
- [ ] Strike distance sanity-checked in expected-move units
- [ ] Spread acceptable relative to the intended move (slightly-ITM preferred)
- [ ] Size ≤2% risk; escalation check at $5,000 notional
- [ ] Regime check: movement vehicle correct (vs handing the trade to LDF)

## Management checklist

- [ ] Exit on the setup's structure stop — the option never gets extra rope
- [ ] Time-scratch at 15–20 min without progress
- [ ] T1 per the setup record; runner only on exceptional room
- [ ] Log fills, delta at entry, and vehicle-choice reasoning for review
