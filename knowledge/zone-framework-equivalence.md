---
type: reference
title: "Zone Framework Equivalence"
description: "Supply/Demand (Seiden), ICT, SMC, and Carmine's LVN are one event in four dialects — a fast departure leaving unfilled orders + trapped traders"
timestamp: 2026-06-25T07:20:50-05:00
metadata:
  originSessionId: 68c135db-a2bc-49ae-8b90-5ac270f3fea4
  graduated_from: reference_zone_framework_equivalence.md
  source_type: reference
---

**One truth, four dialects.** A fast one-sided move (imbalance) away from a level leaves behind (a) **unfilled institutional orders** ("unfinished business") and (b) **trapped counterparties**; price returns to fix both → high-probability reaction.

| Event | Supply/Demand (Seiden) | ICT | SMC/LuxAlgo | Carmine LVN |
|---|---|---|---|---|
| Origin zone | Base (DBR=demand, RBD=supply; DBD/RBR=continuation) | Order Block (last opposing candle pre-displacement) | Order block / S-D zone | Marked S/D or S-R level |
| Fast move | Strength of departure | Displacement | Impulse / BOS leg | Impulsive move away |
| Gap left | (implied imbalance) | Fair Value Gap (3-candle, wicks 1&3 don't overlap) | Imbalance / FVG | Low-Volume Node |
| Unfilled orders | "unfinished business" | inefficiency / liquidity void | imbalance to fill | thin node to revisit |
| Trapped traders | late buyer, odds against | liquidity / stop-run / mitigation / breaker | inducement / liquidity grab | absorption on return |
| Freshness | odds enhancer | unmitigated OB | untested zone | first revisit |

**Real differences (not synonyms):** ICT order block ⊂ S/D base (single-candle refinement); ICT formalizes the "trapped" half into named tradeable objects (liquidity sweep, mitigation, breaker, inducement) and expects a **sweep of the zone edge before reversal** — so a naive S/D limit gets stopped first; FVG = imbalance marked on price, LVN = same imbalance marked on volume profile. Seiden hard filter: departure leg ≥ 3× entry-to-stop (≥1:3 R/R).

**Strader value-add:** overlay **GEX** — a fresh zone coinciding with a GEX wall/magnet is mechanically reinforced (dealer hedging pushes price into the unfilled orders). Confluence (fresh zone + LVN + GEX) = A+ filter Carmine's pure-price method lacks. Links [[carmine-rosato]], [[pac-order-blocks]].
