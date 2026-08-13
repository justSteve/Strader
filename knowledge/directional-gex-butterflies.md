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

---

**2026-08-12 — the error recurred live; specifics backported from COO [st-zc38, co-y3fdk]:**

The 08-05 block above did not hold, because it was in the wrong repo. On
2026-08-11 the live trading session ran in COO, whose `CLAUDE.md` contained the
words "butterfly", "fly", and "flies" exactly zero times — and Steve had to issue
the correction three more times in one afternoon. Post-mortem:
`/root/projects/COO/myDesk/reports/2026-08-12-fly-strategy-memory-failure.md`.
COO now carries its own gate plus `/root/projects/COO/.claude/rules/fly-doctrine.md`.
**This concept stays canonical; the two must read identically, so a change on
either side updates both.**

Why the form is *prohibitions* and not a description: standard option theory is
dense, default, and internally self-consistent — a long butterfly *is* a neutral,
positive-theta, pinning structure. Steve's method is a narrow, deliberate
exception that uses the same instrument for the opposite purpose, so a merely
descriptive note ("he trades them directionally, far OTM") does not block the
default reasoning path; under time pressure the textbook reasserts and the note
reads as compatible colour commentary. That is observed, not theorised — on
2026-08-11 COO wrote the correct mechanism in its own notes at 13:08 and argued
the opposite at 14:02, in the same session. Only an explicit ban survives.

**1. Centering standard — never at or near spot.** If price is X, his candidate
centers are roughly **X±12 or further**, in the direction of the move he expects.
**Five points from spot is still ATM** and still worthless to him — his standard,
stated twice on 08-11 after the "correction" was to halve the distance. His live
order that day: `7760/7745/7730 PUT @1.70` — body 7745, 15-point wings, body
roughly **19 points** from spot (~7726). Body above spot, expected move up, and
it paid as SPX ticked up. Every structure proposed to him in the preceding
forty-five minutes was 0–5 points from spot.

**2. Never reason from expiry.** Banned: breakevens · "you need +N just to break
even" · "dead zone" · settlement-value tables · payoff-at-stall-point. He
evaluates on the **mark**, not at settlement: marked continuously, a far-OTM fly
carries positive delta and pays from the first favourable tick.

> *Scope note — reconciling with the pin runner.* COO's rule originally stated
> flatly that he "does not hold to expiry." Canon here is narrower and canon won:
> he leaves a **runner for the pin**, and a fly runner CAN ride toward expiration
> — see [Buying Movement — Delta-First](buying-movement-delta-first.md) and
> CLAUDE.md's "The Play." What is banned is *reasoning about the trade through
> its expiry payoff* — pricing it or judging how it is doing by what it would
> settle at — not a claim that no contract ever survives to the close. Risk comes
> off into the repricing; the runner is a residual, never the thesis.
>
> Both misreadings are live, so both are banned. **Do not "correct" him out of
> the runner**, and **do not treat the runner's existence as permission to
> reintroduce settlement math.** If he asks what a runner is worth, answer in
> **$ per SPX point and when to take profit** — the same frame as everything
> else here.
>
> *Resolved on both sides 2026-08-13.* COO verified the conflict independently
> (against `buying-movement-delta-first.md`, committed 2026-07-19 `f1ca968`, and
> CLAUDE.md's "held to expiration can easily triple", committed 2026-04-26
> `56c674c`), took it to Steve, and changed its own two copies in one commit —
> `co-qliwo` / `b7c18fb`. **The newer document was the wrong one**: COO's 08-12
> rule was written from a live incident with high confidence and over-broadened
> against canon four months older. Recency lost to canon, correctly.

**3. Correct frame — dollars per SPX point, and when to take profit.** On
2026-08-11 he was up **$150 on $340 risked while SPX moved 1.6 points**
(7722.91 → 7724.48) — roughly **$95 per SPX point** — across the exact range COO
was simultaneously describing as a dead zone in which he had been paid nothing.

**4. Never claim orderflow can't help a fly.** Delta bursts, absorption, and
stall detection are the **exit-timing** signal this strategy runs on — knowing
when to take profit is the whole skill. The 2026-08-08 scalp-proxy redirect
scopes what the *measurement program* targets; it says nothing about what the
instruments are good for, and reading it the other way is what produced the wrong
claim to Steve at 14:02 on 08-11.

**5. Price what he named.** If he gives a structure, price that structure. Do not
substitute one you think is better, and do not "improve" the strikes.

**Additional banned phrases** (extending the 08-05 list): "fits the gamma box" ·
"fully contains the zone / settlement anywhere in the band pays" · "centered on
spot rather than needing a move" · "get centered and time becomes your ally."

Steve's corrections, verbatim (2026-08-11 session `8d15a359`):
- 13:21 — "but i don't take atm flys. I'm in them to reap delta or not in them.
  the point is late day fly where large price moves in my favor."
- 13:26 — "omg - you are still looking at atm flies. worthless - just stop"
- 14:08 — "they start paying from the first positive tick. you just have to know
  to take profit. you are displaying a distinct lack of understanding of my strat.
  distinct and persistant."
