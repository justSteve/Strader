---
type: playbook
title: "Directional GEX Butterflies"
description: "Steve trades late-day flies DIRECTIONALLY centered on the GEX target, not neutral/ATM theta-harvest"
timestamp: 2026-07-13T20:57:23-05:00
metadata:
  originSessionId: 41eb1962-b77b-41fd-aa6c-9869ceaa4f97
  graduated_from: feedback_directional_gex_flies.md
  source_type: feedback
---

Steve does NOT trade late-day butterflies the textbook way (ATM, price-neutral, living off theta decay). He centers the fly on the **GEX-based target** and buys when price is far enough from that target that the fly is cheap AND there's room to travel toward it + an EOD multiplier. It is a directional delta bet with a convex payoff, not a theta harvest.

The v-drop/return setup is still his priority (he takes it every time, cuts on the first wrong breath), but those instances have become much rarer — he needs a second engine, which is why we are scoping long singles ([[st-nd5]]).

**Why:** CLAUDE.md describes flies in textbook price-neutral terms; Steve's actual method is directional. Advising him as if he is theta-harvesting ATM flies would be wrong.

**How to apply:** Read every fly setup through "how far is price from the GEX magnet, and is there room + time to travel there." Distance-to-GEX-magnet is the shared signal across flies (collect at the destination, convex) and singles (collect on the journey, linear). Related: [[project_pin_projection_research]], [[feedback_v_day_target_is_down_only]].

**2026-08-05 — banned framing, and why this kept recurring [st-frco]:**

Never write that a fly "wants" a consolidation range, that it needs price to stay
range-bound, or that it is price-neutral / harvests theta. **The precondition is a
departure and a return, not range occupancy.** A market extended far from its
supports is not hostile to this play — distance from the target is what makes the
fly cheap and gives it room to travel. The body goes at the DESTINATION (the V-return
level, or the GEX magnet); the consolidation range is the landmark that identifies
that destination, never a requirement.

Root cause of the repetition: CLAUDE.md — always loaded and declared authoritative —
said "centering butterflies relative to the consolidation range." The `Why` note
above spotted that in July but the source was never fixed, so instructions outranked
this concept every session and the correction had to be re-issued by hand. CLAUDE.md
was corrected on 2026-08-05.

Steve's corrections, verbatim (claude-monitor record):
- 2026-06-09 — "Textbook approaches to flies read them as price neutral. I don't.
  I'm not taking atm and trying to live off theta decay. i'm diretionally oriented
  guided by GEX."
- 2026-06-24 — "I'm not looking to center and hold. I'm buying late to buy the
  movement... so you say: Fly wants: isn't the fly i want."
- 2026-06-24 — "i rarely take a fly atm even if i think that's the pin. I'll hold out
  for the v-shaped dump and return. i guess my litmus is less theta than it is delta."

**2026-07-13 additions (foundation-check conversation):**
- Steve's SPX parlance: "one level" ≈ 10 SPX points.
- Bet-structure doctrine: he EXPECTS a ~10-pt (one-level) EOD reversion off a late flush but won't pay up to bet exactly that — he prefers the cheaper fly pinned ~20 pts away (2 levels), accepting full-loss risk, and takes early profit if only the expected 10-pt move materializes. The expected move is his profit-taking trigger, not his pin.
- He claims this reversion expectation holds "even on a trend day" — UNVERIFIED and contradicts classic profile teaching (trend days tend to close at the extreme). Measurement bead st-r1p filed to test it against the corpus; until measured, challenge trend-day reversion entries.
