# 06 · Bars and the Footprint — Reading the Drill Screen

*Foundation series, document 6 of 8. Rests on: [02 · Volume](02-volume.md) (effort
vs effect) and [05 · Order Flow](05-order-flow.md) (delta, absorption).*

---

## The one idea

A footprint chart is nothing new — it is documents 01–05 drawn as a picture. Each
bar is opened up so you can see, at every price inside it, who was pressing and how
hard. Once the underlying ideas exist, the footprint stops being a wall of colored
numbers and becomes the fastest way to watch the auction argue. This document walks
every element of the drill screen and names the concept behind it.

## First: why the bars aren't clock bars

Your chart habits were built on **clock bars** — every candle is one minute (or
five, or thirty). Clock bars have a hidden flaw for order-flow work: *the amount of
evidence per bar swings wildly*. A 1-minute bar at lunch might hold 300 contracts;
a 1-minute bar during a violent flush might hold 30,000. Same-sized candle, hundred‑
fold difference in how much actually happened. Patterns learned on clock bars are
partly patterns of the clock, not the market.

**Volume bars** fix this by inverting it: every bar closes when the same number of
contracts has traded — in our drills, **2,000 contracts per bar**. Consequences:

- **Every bar carries equal evidence.** A bar is a fixed 2,000-contract sample of
  the auction, always comparable to its neighbors.
- **Time becomes an output.** The one thing that now varies is *how long the bar
  took*. An 11-second bar means 2,000 contracts changed hands in 11 seconds —
  the tape is on fire. A 9-minute bar means the market is asleep. Bar duration is
  a pure **urgency meter**, and the drill's *pace strip* (the little bar-graph
  strip under the chart) displays exactly that: one duration bar per column.

This is a genuine habit change from clock-bar reading, which is why the drill
curriculum's very first unit is nothing but pace: replaying days at various speeds
until "fast bars = urgent tape" is felt rather than computed.

## The footprint: a bar, opened up

Take one 2,000-contract bar. Instead of drawing it as a candle, list every price it
touched (one row per tick — 0.25 points), and at each price show the business done,
split by aggressor side (document 01's tag):

```
one bar, opened up:                        how to read a cell:
price     sell-aggr × buy-aggr
6251.00        12  ×  85          ← buyers pressing here, lightly
6250.75        96  ×  310         ← heavy business, buyers forcing 3:1
6250.50       410  ×  388         ← the bar's biggest fight (its POC)
6250.25       205  ×  71          ← sellers forcing ~3:1
6250.00      (no trades — price jumped straight across this tick)
6249.75        44  ×   9          ← light selling at the low
              ───────────
              bar delta = (sum of buy-aggr) − (sum of sell-aggr)
                        = 863 − 767 = +96 for this bar
```

That table is the raw data. Here is how the SAME bar renders as one column on the
drill screen (default view; the Cells menu can switch the number shown, and
hovering any cell pops the full sell × buy pair):

```
          one column = one 2,000-contract bar
        ┌───────────┐
6251.00 │    73     │  ← pale blue, small number: light business, buyers edged it
6250.75 │    214    │  ← STRONG blue: heavy business, buyers dominated (310 v 96)
6250.50 │ ┏━━━━━━━┓ │
        │ ┃  22   ┃ │  ← the OUTLINED cell = this bar's POC (most volume traded
        │ ┗━━━━━━━┛ │    here: 410+388). Note: brightest cell, tiniest number —
6250.25 │    134    │    a dead-even war. That's the absorption signature.
6250.00 │ ╌╌╌╌╌╌╌╌╌ │  ← dashed VOID: zero trades at this price inside this bar
6249.75 │    35     │    (a micro low-volume node — drawn deliberately)
        ╞═══════════╡
        │ 96 · 13:46│  ← the FOOTER: the bar's total delta (number = magnitude,
        │    389    │    COLOR = winner: blue buyers / red sellers), the bar's
        └───────────┘    closing clock, and the bar's index number
```

Each price row is a **cell**, and the rendering encodes three things at once:

| Visual | Encodes | Concept behind it |
|--------|---------|-------------------|
| **Cell color** (blue vs red) | Which side's aggression won that price — blue = buy-aggressor dominant, red = sell-aggressor | Document 01: the aggressor tag |
| **Cell brightness** | Total contracts at that price — brighter = more business | Document 02: effort |
| **The number** | The net margin (buy-aggr minus sell-aggr at that price) | Document 05: delta, per price |
| **Outlined cell** | The bar's own POC — the price with the most volume inside this bar | Document 03's POC idea, at bar scale |
| **Dashed empty cell** | A price the bar jumped over with zero trades | Document 04's LVN, at micro scale — real, deliberate emptiness |
| **Footer number** | The whole bar's delta, colored by sign | Document 05: the pressure gauge |

Hover any cell in the drill and it spells out its raw sell-aggressor / buy-aggressor
pair — nothing on the screen is more than one hover away from its definition.

## The four single-cell reads

Document 02's effort-vs-effect table becomes, cell by cell, the drill curriculum's
"frame" vocabulary. Same table, now in footprint terms — brightness is effort, the
net number is the score:

| Read | Looks like | Means |
|------|-----------|-------|
| **Conviction** | Bright cell, big net number | Hard fight, clear winner — trust the winner |
| **Absorption** | Bright cell, *small* net number | Huge two-sided strain, no winner — someone strong is hiding at this price; reversal fuel |
| **Hollow** | Dim cell, big net number | A "win" with almost no business behind it — evaporates on contact with a real opponent |
| **Dead** | Dim cell, small number | Nothing happened here |

A real example you found yourself, on the July 2 reference day, first bar of the
session: a cell with net −1 that was *brighter* than a neighboring cell with net
−16. The −16 cell looks scarier by number; the −1 cell is the story — far more
total business, dead-even outcome. That's absorption's signature in the wild.

## From cells to columns to sequences

Reading builds in three steps, and the drill units follow the same three:

1. **One cell** — the four reads above.
2. **One column** (a whole bar) — where inside the bar did the business
   concentrate (the bar's POC)? What's the footer delta? Did the bar's shape climb
   or sag? A column is one 2,000-contract *round* of the fight.
3. **A sequence of columns** — now the compass runs: is the pressing side's effort
   producing effect bar over bar? Run your eye along the **footer row** — the
   strip of bar-delta numbers across the bottom of the columns. Their colors are
   a scoreboard, one entry per round:

```
   footer row across nine consecutive bars   (r) = red number, (b) = blue number
                                              — on screen it's color, not letters

    512(r) 447(r) 610(r) │ 388(r) 402(r) │  55(b) 210(b) 340(b) 415(b)
    ───────────────────────────────────────────────────────────────────
    "staying one color":        still red        "flipping": footers turn
    sellers winning round       but price has    blue — buyers now win the
    after round — the flush     stopped falling  rounds. This color change
                                — the stall      IS the flip, stage three
```

   Footers staying one color = one side in charge, bar after bar. Footers
   changing color = control changed hands. Add the pace strip underneath (are
   bars speeding up — urgency arriving — or slowing?) and this is where the
   level-engagement stories of document 07 play out.

## The whole screen, mapped

Every region of the drill page, top to bottom, with the concept each one carries:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Orderflow Drill   ES.c.0 · 2026-07-02 · N=2000 contracts/bar · 667 bars  │ header: which day,
│                                                                          │ contracts per bar
│ ▶Play ⟨Bar Bar⟩ Speed[20×] ══seek══ Level[____][Arm] chips Ladder▾ ? ... │ controls: playback,
│                                                                          │ arm a level, scenarios
│ Bar 390/667 · Time 13:46 CT · Last 7509.25 · Bar Δ −447 ·               │ readouts: Session Δ =
│ Session Δ −1,882 · Bar took 12.3s · Score 3/4                            │ cumulative delta (slope!)
├───────────────────────────────────────────────────────────────┬─────────┤
│                                                                │  7514   │
│   ▒▒   ▒▒   ░░   ▓▓   ▓▓   ▒▒   ░░   ▒▒   ▓▓   one column     │  7512   │ chart: columns
│   ▒▒   ░░   ▓▓   ▓▓   ▒▒   ▒▒   ▓▓   ▓▓   ▒▒   per bar,       │  7511¼◄─┼─price axis;
│  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ 7511.25 ╌╌╌          │  7510   │ dashed line =
│   ░░   ▒▒   ▒▒   ░░   ▓▓   ▓▓   ▒▒   ░░   ░░   cells stacked  │  7509   │ your ARMED level
│  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐  by price       │  7508   │
│  │512│ │447│ │610│ │388│ │402│ │ 55│ │210│ │340│ ◄── the FOOTER row:     │
│  └──┘ └──┘ └──┘ └──┘ └──┘ └──┘ └──┘ └──┘ └──┘  bar delta + clock + index │
├──────────────────────────────────────────────────────────────────────────┤
│ seconds per bar   ▂▂▁▂▃▂▁▁▂▇█▇▃▁▁▂▁▂▃▂▁▂                                 │ pace strip: one
│                            └── tall = SLOW bar, short = fast/urgent      │ duration bar per column
├──────────────────────────────────────────────────────────────────────────┤
│ Drill log: your calls, outcomes, verdicts (the append-only score record) │
└──────────────────────────────────────────────────────────────────────────┘
```

So every control has a concept attached: the **level chips** arm a price from the
day's map (session open/highs/lows, or levels harvested from Mancini's letter —
document 07 covers why those levels); the **Ladder dropdown** loads the drill
curriculum's scenarios in learning order; **Anatomy** walks recognized four-stage
setups with each stage narrated (the stages themselves are document 07's subject);
and the **Session Δ** readout is cumulative delta from document 05 — watch its
slope, ignore its level.

---

## Known snags — a field guide from your own crossing

This section exists at your request: an honest record of where the comprehension
checks on documents 01–05 went astray, restated in this document's terms, so the
next pass over this ground unwinds the confusion instead of repeating it. Six
snags; each with the trap and the rule that springs it.

**Snag 1 — the flipped anchor.** Your flagged failure mode: once the initial
direction flips, everything downstream stays internally coherent, so the error
can't be felt from inside. The screen gives you a mechanical guard: the flush IS
a color. Bright red cells punching down through a level = flush down; if the trap
springs, it pays UP. Rule: **say the flush direction out loud before analyzing
anything.** Anchor first; the confirm's direction is then automatic.

**Snag 2 — crediting the wrong party.** Twice you assigned the absorber's role to
"the aggressor." The screen guards this one too: **cell colors count aggression
only** — blue is buy-aggressors, red is sell-aggressors; the passive side never
prints a color. A resting wall is invisible in the cells; you see it only as
*effect* — loud one-sided color with price refusing to move. If you catch
yourself saying "the aggressor met all challengers," stop: whoever meets
challengers from a standing position is passive by definition.

**Snag 3 — time versus contracts.** In Market Profile territory you counted
volume where the tool counts half-hours (the POC, single prints). The lenses
usually agree, which is exactly why they blur. On this screen the roles are
explicit: volume is the constant (every bar the same contracts), time is the
*output* (the pace strip). Rule: before saying "transactions," ask which unit the
tool in your hand actually counts.

**Snag 4 — counter versus signed sum.** "Anything that accumulates can only be
higher on revisits" — true for volume, false for delta. Footer numbers are
signed; the Session Δ readout wanders up and down all day, like price. Only
volume is a true counter.

**Snag 5 — earlier-in-time versus old-ground-in-price.** "The move's own earlier
bars" read to you as revisiting old ground. *Earlier* is a time word — look left;
every move has earlier bars. *Old ground* is a price word — it exists only when
price returns to somewhere it traded and left. Exhaustion and absorption read
first-touch, against the move's own earlier bars; divergence is the one read that
needs two visits.

**Snag 6 — attempt-count as classifier.** "Fails on the first attempt = plain
continuation" — no. The classifier at a level is never how many attempts; it is
always **"does the aggression keep getting paid?"** The trap itself is a
first-attempt story — if first attempts defaulted to continuation, there would be
nothing to drill.

None of these are personal defects; they are the standard potholes of this
material — our own recognizer code carries explicit direction constants because
sign errors are exactly that easy. The difference between a snag and a leak is
whether it's written down. It is now.

## Check yourself

*Questions only — bring your answers to the open Strader session.*

1. What's the hidden flaw in clock bars for order-flow work, and what does a
   volume bar hold constant instead?
2. On volume bars, what does a bar's *duration* tell you — and where does the
   drill screen display it?
3. A footprint cell has a color, a brightness, and a number. What does each
   encode, and which foundation concept does each trace back to?
4. Name the four single-cell reads. Which one was your own July 2 first-bar find,
   and what made that cell the story?
5. What is a dashed empty cell on the drill screen, and why is it drawn
   deliberately rather than left blank?

**Next: [07 · Levels and Traps](07-levels-and-traps.md) — where the fights happen,
who gets trapped, and the four-stage reversal the drills are built around.**
