---
code: LDF
name: Late-Day Butterfly (V-Dump)
status: candidate
adopted: 2026-07-18
source: Steve
instruments: [SPX, 0DTE-butterflies]
favored_conditions: [window-late, gex-pos, range-chop, room-to-travel, at-key-level]
avoid_conditions: [trend-up, trend-down, window-open, window-midday, news-adhoc]
indicators: [gex-levels, pac-order-blocks, footprint, cumulative-delta, vwap-bands, mancini-levels]
rationale: "The late-day flush is the trap at session scale: the sharp drop out of afternoon consolidation collapses butterfly prices; the rally-back toward the pin reprices them multiples higher. Buy the fly at the V's bottom, directionally centered on the magnet — collect at the destination."
updated: 2026-07-18
---
## Thesis

This is NOT the textbook ATM theta-harvest butterfly. It is a directional,
convex bet that the late-day flush reverses and travels back toward a
gamma/structure magnet into the close. The flush (v_down) crushes the fly's
price; the rally-back plus the pin does the paying. v_down is the only tradeable
side — v_up output is diagnostic, never an entry.

## Setup

- Afternoon consolidation established by ~13:00 CT; its edges and the day's
  magnet (GEX pin / prior POC / PAC order block shelf) identified.
- The sharp drop out of consolidation — the session-scale flush — occurs
  inside the late window. Single prints / fresh thin ground left overhead is
  the repair path the rally-back travels.
- Day type must allow rotation back: balance/range day, positive-GEX posture.
  A confirmed trend day is the standing veto (until st-r1p measures otherwise,
  trend-day reversion entries get challenged, not sized).

## Pin selection (the 20/10 structure — Steve's doctrine)

- **Expected reversion: one level (~10 SPX points)** off the flush low. That
  expectation is the *profit trigger*, not the pin.
- **Center the fly ~two levels (~20 points) from the flush low**, toward the
  magnet, using PAC order blocks to fine-center the strike. The distant pin is
  what makes the entry cheap; the expected 10-point move is what reprices it
  enough to pay; the full travel to the pin is the bonus, not the requirement.
- Full loss on entry cost is accepted by design — the entry price after the
  dump (cents, not dollars) is the risk budget.

## Entry

- **Cue: v-dump-complete** — the flush has bottomed and the return has started.
  In stage terms: stall and flip printed at the low (absorption eating the
  panic; footers changing color). Do not buy the falling knife; buy the turn.
- Entry price target: the fly at a deep discount to its pre-flush price
  (the $2.60 → $0.25 → $2.50+ arc is the reference shape).
- No entry before 13:00 CT. No new entries in the final ~20 minutes.

## Stop

- The entry premium IS the stop — no premium-based stop-loss management.
- Thesis stop: if price *accepts* below the flush low (business builds there
  rather than rejecting), the reversion story is dead — exit for whatever the
  fly still bids rather than riding a corpse to zero.

## Targets

- 3–5 lot standard. Scale off into the repricing as the reversion pays
  (the ~10-point move), banking the multiple on most of the position.
- **Leave a runner for the pin** — expiration at the center strike is the
  convex tail that turns a good trade into the week's target.

## Invalidation

- Trend-day continuation: no stall/flip forms at the flush low — was never a V.
- Acceptance below the flush low (the audit approves the new price).
- The magnet gives way (GEX flips / wall pulls) — the destination left.

## Sizing

- Position = entry cost, sized so total premium at risk ≤ 2% of account;
  >$5,000 notional escalates to Steve.
- Weekly-target framing: hundreds per week, not thousands per trade. One
  quality V beats three forced ones; zero entries on a trend day is a win.

## Regime fit (notes)

Wants a balance day that spent the afternoon consolidating (D-shape building),
positive GEX (dealers fade the extremes), and a flush that leaves thin repair
ground overhead. Dies on trend days — the rotation back never comes — and on
ad-hoc news that re-prices value rather than trapping sellers. Negative-GEX
movement days belong to the singleton; that is the pair's division of labor.

## Entry checklist

- [ ] Consolidation + magnet named by 13:00 CT; fly strikes pre-planned
- [ ] Flush direction confirmed down (v_down); say it out loud
- [ ] Stall + flip printed at the low (v-dump-complete — the turn, not the knife)
- [ ] Day type allows rotation (no confirmed trend day)
- [ ] Fly price at a deep discount to pre-flush
- [ ] Inside the window: after 13:00, not the final 20 minutes

## Management checklist

- [ ] Scale off 3–5 lot into the ~10-point reversion repricing
- [ ] Runner held for the pin at the center strike
- [ ] Exit the remainder on acceptance below the flush low
- [ ] Log the V's depth, entry price, and reversion size — st-r1p/st-r2o feed
