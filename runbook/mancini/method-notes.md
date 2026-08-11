<!-- TEMPORARY — DELETE ON THE NEXT PARSE (Steve, 2026-08-11).
     Left on the 08-11 plan doc for one read only. Steve does not want this
     passage on every letter; the terms go into the Flashcard engine instead
     (COO is handing over the details). See CurrentStatus.md Attention Item 0
     for the exact removal steps. -->

## Method notes — reading Mancini's vocabulary

_One-time section, removed after 2026-08-11. These terms are moving to the
Flashcard engine._

**Elevator down.** A sharp vertical flush that cuts through several supports with
ease. Mancini's framing: ES "rallies slowly (stairs up) and sells in a straight
line (elevator down)." Typically one per session; lasts minutes to hours. This is
the *precondition* for his entry, not the entry itself.

**Significant low.** The level a Failed Breakdown is measured against. Three
accepted definitions: (1) the prior day's low, (2) a multi-hour low or one that
travelled 20+ points, or (3) a cluster or shelf of lows.

**Failed Breakdown.** The whole sequence: price flushes a significant low, traps
the shorts who chased it, then recovers the low. The recovery is what starts the
squeeze — "not a moment before, and if you try knife before this trigger event,
you will lose." This is the only long setup he takes.

**Quick trap.** The *price event* — a shallow, fast poke below a level that
reverses before anyone settles. Shorts chase the breakdown, price reclaims within
minutes, and their stop-buys become the fuel for the move back up. Same mechanism
as a Failed Breakdown, compressed: a few points and a few bars instead of 10–20
points and an hour.

**Acceptance.** Price action required *before* entry, so you don't rush in and get
trapped. It looks like price trying to sell at or above the significant low and
then returning to it — the market showing you it wants to be there.

**Non-acceptance protocol.** The *entry rule*, not a price event. It triggers when
price recovers the significant low by 5 points and holds at or above that for a
couple of minutes. It exists for fast markets "where price does not pause around
the significant low and just rips through" — i.e. where there was no time for
acceptance to form. Mancini uses it whenever acceptance isn't obvious.

> **Quick trap ≠ non-acceptance.** The quick trap is what price did; the
> non-acceptance protocol is how you confirm it. They travel together — a quick
> trap almost always gets confirmed by the protocol, because by definition
> acceptance had no time to build — but they are not the same thing. You can also
> get non-acceptance on a *deep* flush that simply rips back fast: 20 points down,
> straight back up, no loitering. That is non-acceptance without being quick.
>
> **Naming trap:** in this vocabulary "non-acceptance" is **bullish**. It means
> price did not accept *below* the level. Easy to read backwards.

### What these look like on a footprint

Footprint is the cleanest way to separate the two confirmation paths, because they
print near-opposite signatures:

- **Acceptance prints fat.** Price sits at and below the level, volume accumulates
  at each price, a high-volume node forms. That stacking of contracts is the
  literal evidence for "price wants to be here."
- **Quick trap / non-acceptance prints thin.** Price travels fast, so few
  contracts trade at each price — a low-volume node forming in real time. This is
  the same event Carmine calls an LVN; see
  `knowledge/carmine-rosato-investitrade-lvn-method.md`.

Confirming tells on the reversal: aggressive negative delta into the flush
(sellers hitting bids), then either a **delta divergence** — new low in price, no
new low in delta — or outright **absorption**, where delta stays strongly negative
but the range stops extending because passive bids are eating the market sells.
The recovery then runs back through the thin zone fast, precisely because there is
no volume shelf to slow it. That speed on the way back *is* the trap springing.

**Granularity caveat.** At ES scale the 5-point rule is roughly 0.06%. On a
one-tick-per-row footprint the thin/fat distinction is real; aggregated too
coarsely it washes out. Tooling: `scripts/live_footprint_page.py`,
`scripts/live_footprint_feed.py`, and `scripts/replay_day.py` for tape review.

**Status: unmeasured.** The acceptance/non-acceptance split above is Mancini's
description plus the footprint signature it implies — it has not been tested
against our own tape. Treat it as a hypothesis worth checking, not a validated
edge.
