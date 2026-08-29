# Final-Hour Acuity — the plan

**Bead:** st-g0jo · **Date:** 2026-08-28 · **Origin:** the 14:15 CT close read
that called a pinned close in ES 7712–7730 (it closed 7723), and Steve's ask
that evening: apply the same analytics across the collection, because the
final hour strips the problem down to one call — direction.

## What the final hour is worth (measured tonight, 286 days)

- Median net move from the 14:00 CT print to the close: **7.5 ES pts**.
  Four in ten final hours finish 10+ away; seven in ten *travel* 10+ at some
  point.
- Close lands inside the 13:00–14:00 box half the time. Direction is 53/47.
- Full numbers: `docs/measurement/final-hour-base-rates-2026-08-28.md`.

So the prize is there most days, and the base rate gives no direction. The
program below is about turning the three lenses used today into a measured
direction call, and scoring it in premium the way Steve actually exits.

## What today's read was made of

The 14:15 read was three lenses read against one price:

| Lens | What it contributed today | Measurable how |
|---|---|---|
| **Footprint** (our ES tape) | two-hour box 7712–7727, buying absorbed with no price progress, volume dried to a third of late morning, price at the bottom edge of value, heaviest sell node at 7735–7737 | bar delta, absorption (delta sign vs. price change), volume ratio, profile position, sell/buy node location |
| **Mancini** | 7714 major defended 9 of 10 touches with a 2-pt trap below; 7734 lost; 7758/7771 rejected; plan bias "leaning up" | distance to nearest major level, level state at 14:00 (held / broke / reclaimed), plan bias where the in-session parse exists |
| **GEX** (GexBot) | spot bracketed by the two largest long-gamma strikes (7705, 7720); zero gamma 15 above; the long-gamma marker had migrated down to price through the afternoon | strike map at 14:00, spot vs. zero gamma, sign of the strikes just above and below, intraday drift of the major |

The read was a confluence: floor (7712–7717) and lid (7732–7737) agreed
across all three, and the tape inside the box was low-energy. That is a
**pin call**. The other two calls the final hour asks for are **break down**
(the 10-point flush Steve has been staging puts for) and **break up**.

## What the collection supports, per lens

| Lens | Days | Window | Note |
|---|---|---|---|
| ES trade tape | 286 | 13:00–15:00 CT on 247 days; full session on 40 (2026-07-03 →) | the 2025 backfill pulled the late-day window only |
| ES depth (MBP-1) | ~40 | full session, live collection only | absorption at the touch, if wanted later |
| Mancini levels | 292 parsed days | — | backfill = levels + major flags only; bias/commentary only on the 27+ in-session parsed days since 2026-05-19 |
| GexBot snapshots | ~17 days (2026-08-05 →) + 19 history days | full session, ~1/min | forward-only lens; ~20 new days a month |
| OPRA SPXW trades | 269 days | 13:00–15:00 CT | the 0DTE single's mark path into the close — the scoreboard in premium |

The Mancini and footprint lenses can be scored across the whole corpus now.
The GEX lens cannot be rebuilt for 2025 from what we hold (no OI history); it
accrues going forward.

## The program

**Stage 0 — base rates.** Done 2026-08-28 (above).

**Stage 1 — score the outcome in premium, not points.** *Done 2026-08-29 —
`docs/measurement/final-hour-premium-vs-es-2026-08-29.md`: the ITM single
follows the ES move at +0.91; ≥5 ES pts right pays +47% median, ≥10 pays +72%;
a 0.30 stop fires before the first +25% print on 82% of right days.* For every OPRA day,
reconstruct the mark path of a hypothetical 14:00 CT 0DTE single on each side
(the first strike ~10 pts out), from the trade prints. Score it three ways:
result at the close, best mark before the close, and result under Steve's own
cut rule (a ~3% drawdown exit, the 08-26 yardstick). This gives the actual
shape of "right delta call → win huge or marginal; wrong → quick shallow loss"
as a distribution, and it is the denominator every later stage divides by.

**Stage 2 — extract the 14:00 state with no lookahead.** *Done 2026-08-29 —
`scripts/measurement/final_hour_lens.py`, 858 rows at 14:00/14:30/14:45 with
each lens' pre-registered call and the outcome incl. heat;
`docs/measurement/final-hour-lens-calls-2026-08-29.md`.* One row per day per
lens, computed only from data stamped before 14:00 CT (and again at 14:30 and
14:45, since the flush Steve stages for often starts after 14:30):
- footprint: box range, box delta, absorption, last-30 drift, sell/buy node
  location; on full-session days also profile position and volume drying;
- Mancini: nearest major support / resistance and distance, whether it was
  touched and held / broke / reclaimed inside the window, plan bias where the
  parse has it;
- GEX where held: spot vs. zero gamma, the sign and size of the two nearest
  strikes, the afternoon drift of the long-gamma major.
Each lens then emits its own call — *pin / break down / break up* — by a
rule written before the scoring, so the rule is testable rather than fitted.

**Stage 3 — score and split.** *Done 2026-08-29, same write-up: no lens carries a
14:00 direction call (pooled edge 0 / +1 pts, both flip sign across the
2025/2026 split); footprint up at 14:45 is the one rule that held on both
halves (+20 / +27, n=40, ~3-pt median); every down rule failed a half; GEX at
17 days is recorded, not scored. Combinations added the same day —
`docs/measurement/final-hour-combos-2026-08-29.md`: seven pre-registered
agree-or-abstain rules; R2 launch-into-no-lid holds on both halves at every T
(+33 · +45 at 14:45, n=26, ~3-pt median, +43% on a 14:45 ITM call); R1 flush is
inverse at 14:00/14:30 on both halves.* Each lens' call against the realized final
hour (direction of the net move, the 10-pt excursion, and the Stage-1 premium
result), then the confluence call when the lenses agree. Validate by time
split — 2025 half vs. 2026 half — because the last time a cut looked good on
one body of days and flipped sign on the next was the day-type gate
(st-gno7, 2026-08-19). A rule that fails one half is not reported as an edge.
st-9i7a (the sell-burst-then-limp-drift signal) and st-vl3c (the three
footprint constructs) become T-15 features inside this stage rather than
separate studies.

**Stage 4 — the surface, then the drill.** The 14:00 read Strader wrote by
hand today becomes a page generated every session at 14:00, 14:30 and 14:45
CT, carrying each lens' call and its measured hit rate beside it. Then a
drill: replay the 14:00 state from the corpus, Steve makes the delta call,
the page shows the outcome in premium. That is the acuity — his call, scored
against three hundred final hours, on his time.

## Decisions that are Steve's

1. **Re-pull the morning tape for the 247 partial days?** Without it the
   footprint lens is scored on box-and-drift features only; the profile and
   volume-drying reads that were half of today's call stay confined to 40
   days. Recommended: **yes, if the Databento cost is trivial** — Strader
   will quote the cost from the Databento metadata endpoint first and only
   pull on a word from you.
2. **GEX lens: forward-only, or build a proxy from OPRA 0DTE flow for 2025?**
   Recommended: **forward-only.** A flow proxy is not the dealer-position
   picture on his chart, and scoring a different instrument under the same
   name is how a lens gets a reputation it did not earn.
3. **Scoring instrument: the 0DTE single.** Recommended and assumed — it is
   the priority he named on 08-26, and the fly's mark could not be rebuilt
   from Schwab's deep-ITM IVs on 08-12 (st-z96i). The fly comes in at Stage 4
   as a second column once the single scoreboard stands.

Silence takes the recommendations: Stage 1 and the box-and-drift half of
Stage 2 start next session on the tape as it stands.
