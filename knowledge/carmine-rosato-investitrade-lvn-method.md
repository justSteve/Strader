---
type: reference
title: "Carmine Rosato — InvestiTrade LVN Method"
description: "Carmine Rosato / InvestiTrade — order-flow + supply/demand \"Low Volume Node\" method Steve models; LVN = zone left by a fast departure"
timestamp: 2026-07-18T02:54:13-05:00
metadata:
  originSessionId: 68c135db-a2bc-49ae-8b90-5ac270f3fea4
  graduated_from: reference_carmine_rosato.md
  source_type: reference
---

Carmine Rosato — trader Steve models; runs **InvestiTrade** (investitrade.net), course "How To Trade Using Orderflow." Full-time options+futures trader; trades ~2 hrs/day, first 2–3 hrs of session, **out by 11:30**; surgical discipline. (The in-repo "InvestiTrade Playbooks — Master R.md" doc is named for his company.)

**Method — Low Volume Node (LVN):** mark a clear supply/demand or S/R level → wait for an **impulsive move away** (signals strong buyers/sellers) → the fast departure leaves a **low-volume node** (thin profile area) → wait for price to **return** to it → **confirm with order flow** (heatmap, footprint, delta, absorption; passive buyers vs aggressive sellers) → long off demand/support, short off supply/resistance. Stop just past the LVN / recent swing; targets = HOD/LOD, next S/D zone, another LVN, or S/R. Define $ risk first, size by stop distance.

This is departure-defined supply/demand (Seiden lineage) read through the **volume profile** — see [[zone-framework-equivalence]]. Maps to LuxAlgo order blocks ([[pac-order-blocks]]). Underpins [[buying-movement-short-hold]] and [[singles-as-futures-proxy]].

**PROVENANCE UNDER REVIEW (st-1s1, 2026-07-16):** Steve's correction via COO: Carmine's LEVELS are derived by conventional means (prior day high/low, range edges, balance-range landmarks) — NOT profile LVNs; his TRIGGERS are Bookmap order-flow reads, concentrated in the first hour. Separately, COO's letter scour (co-tg7w) shows 'failed breakdown' is MANCINI's signature (~90% of his trades, doctrine in 316/330 letters) — code/docs crediting it to Carmine are wrong. The LVN-method framing in this memo's Method paragraph is therefore suspect; hold repo-doc rewrites until Steve's Discord harvest lands (st-1s1 is the anchor). 'Zero print' = Carmine trigger vocabulary, definition pending harvest.

**Instrument correction (Steve, 2026-07-14):** Steve doesn't recall Volume Profile on Carmine's example charts — Carmine's motivating-evidence screen is **Bookmap** (resting-liquidity heatmap: orders stacking / re-loading / pulling). So the LVN *concept* is his, but the VP histogram is OUR instrument for finding such zones; his confirm-on-return instrument is the book side. In our stack that corresponds to depth-of-book (MBP-1) — the st-9vl absorption pre-build — not the trades-derived profile. Carmine's term "re-load" = resting orders getting eaten and reappearing at the same price.
