---
type: playbook
title: "Buying Movement — Delta-First"
description: "Steve trades flies and singles delta-first not theta-first; singles = short-hold move-capture, flies = V-dump entry with a scaled exit and a runner left for the pin"
timestamp: 2026-06-24T17:05:15-05:00
metadata:
  originSessionId: 68c135db-a2bc-49ae-8b90-5ac270f3fea4
  graduated_from: feedback_buying_movement_short_hold.md
  source_type: feedback
---

Steve's litmus across both vehicles is **delta, not theta** — he selects and manages on price reaching levels, not on decay. Two different vehicles, do NOT impose one time-horizon across both:

- **Singles (short hold):** buy cheap optionality, capture a fast directional move, exit on the repricing. Traded as a futures proxy — see [[singles-as-futures-proxy]].
- **Flies:** he does NOT enter ATM even at a perceived pin. He waits for the **V-shaped dump-and-return** to enter cheap, takes a 3- or 5-lot, scales risk off into the repricing, and **leaves a runner for the pin** — so a fly runner CAN ride toward expiration. Still "buying movement": cheap far from the body, rich near it.

Both model [[carmine-rosato]]'s order-flow + supply/demand-zone style; targets = LuxAlgo confluence.

**Why:** I first assumed flies wanted price to pin at center (positive-GEX mean-revert) — wrong. Then I overstated that flies are also ~15-min holds — also wrong; that short-hold discipline is the *singles* play. Flies = V-dump entry, scale out, runner to pin. Common thread is delta, not theta.

**How to apply:** Frame singles as short-hold futures-proxy move-capture; frame flies as V-dump-and-return entries with a scaled exit plus a pin runner. Favorable conditions for both = order-flow conviction (CumDelta/Footprint) + confluence entry at a LuxAlgo zone + room to travel (neg GEX / distance-to-magnet) + range/pace expansion. Extends [[directional-gex-flies]].
