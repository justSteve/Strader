# 09 · Fundamental Units — Naming What the Tape Does

*Foundation series, document 9. Rests on: [02 · Volume](02-volume.md) (effort vs
effect), [05 · Order Flow](05-order-flow.md) (aggression, delta, absorption),
[06 · Bars and the Footprint](06-bars-and-the-footprint.md) (cells, footers),
[07 · Levels and Traps](07-levels-and-traps.md) (the four stages).*

*This document is five short essays, read in order. Ground truth for every term
is `docs/lexicon/lexicon.yaml`; every number is a measurement from 263 trading
days (39,482 minutes, 1,649 price swings), adversarially verified. First
contact with this vocabulary should be the companion narratives,*
The Day in Fundamental Units *(2026-07-22 and 2026-07-24)*; these essays
explain the machinery the narratives showed in motion. For the measurement
vocabulary the accuracy numbers are spoken in — anchor, fire, the scoring
rule — read `docs/training/plain-words-glossary.md` first; no essay assumes
it.*

---

## Essay I — The atom and the four cells

**The one idea:** one minute of tape, scored on two axes, lands in one of four
cells — and the cells already have names you know.

The **atom** is one clock minute. It gets two scores. **Effort** — how many
contracts changed hands (document 02's participation, unsigned). **Effect** —
how far price moved. Score each against the rest of the day (a percentile:
busier or quieter than the day's other minutes?) and cross them:

| | High effect | Low effect |
|---|---|---|
| **High effort** | **F1 conviction** — the movement is being paid for (34.7% of minutes) | **F2 absorption** — someone is standing there (16.0%) |
| **Low effort** | **F3 hollow** — price drifting on air (22.4%) | **F4 dead** — nothing happening (26.9%) |

Two refinements make the atom honest. First, effect has two faces:
**displacement** (where the minute closed vs opened) and **travel** (its full
high-low span). A minute can travel five points and close where it opened — a
round trip. The **travel-ratio** (displacement ÷ travel) catches this: near 1
is one-way traffic, near 0 is a fight. This matters because the measured
corpus shows **half of all travel hides inside minutes whose displacement is
small** — and 82.5% of that hidden violence lives in F2 absorption cells.
Absorption minutes are not quiet; they are wars that ended where they started.

Second, **force** — signed delta, document 05's aggression balance — is
recorded on every atom but is *not* one of the matrix axes. Effort answers
"how much business"; force answers "which side pressed." Keeping them separate
is not pedantry: one of the eight swing types exists precisely because force
and direction *disagree*.

## Essay II — Grades, not gates

**The one idea:** the four cells are lines we drew on a smooth surface, so
every label must say how far it sits from the line.

We tested whether the tape naturally clusters into the four cells. It does
not: the distribution of minutes over the effort/effect surface is smooth —
no valleys, no gaps. The 2×2 grid is *imposed*. The honest consequence:
**one classification in five is a literal coin flip** — 20.4% of atoms sit
within a whisker of a cell-boundary.

So every label carries a **grade**: distance from the nearest cell-boundary,
0 to 1. And grades are spoken in **grade-bands**: **coin-flip** (≤0.1 — never
report the cell alone; say the straddled pair, "F3/F4 coin-flip"), **lean**,
**solid**, and **strong** (>0.6 — survives any reasonable redrawing of the
lines). Speak them like this: *"graded F1 at 0.62"* — never *"is F1."*

This is not hedging; it is calibration. When the 7/22 opening swing scored
pace 0.792 against a 0.75 cutpoint, the vocabulary reported
"flush-leg/steady-leg, coin-flip" — telling you *exactly* how much weight the
label can bear. A vocabulary that admits its coin flips earns trust for its
strong calls. (A **cutpoint**, while we are here, is a dividing line that
*sorts*; a **threshold** is a value that *triggers*. The 0.75 pace cutpoint
above sorts flush-leg from steady-leg, and the 50/50 percentile boundary
sorts atoms into cells — nothing happens at either, a label just changes.
The reversal threshold ends a swing, the 150-contract delta threshold fires
the flip-stage — something *happens*. Bare "cut" stays reserved for what you
do to a losing position.)

## Essay III — The zigzag and the eight archetypes

**The one idea:** redraw the day with the fewest pen strokes, and the strokes
themselves sort into eight recurring characters.

The **zigzag decomposition** is the drawing rule: trace the day with
alternating strokes, ending a stroke only when price retraces more than a
threshold (20% of the day's range) from the stroke's furthest point. Each
stroke is a **leg** — median 15 minutes, 7.25 points. A backtrack smaller than
the threshold does not turn the pen: its minutes stay on the tape, fully
graded, inside the leg — the leg's *texture*, the reason travel exceeds
displacement and giveback exists. (Not "absorbed" — that word stays reserved
for the F2 cell.)

Across 1,649 legs, four measured axes — pace, effect, giveback, force
alignment — sort the population into eight **archetypes**: **flush-leg**
(fast and big; the tradeable V-dump cliff, 13.7%), **steady-leg** (mid-pace,
force agreeing 95% — the trust-the-tape reference), **leg-grind** (slow and
big; the trend-day escalator), **counterforce-leg** (price moving *through*
opposing force — falling prices on net buying; direction-inversion territory),
**absorption-stall** (the wall: 70,825 contracts for 3.5 points, once),
**hollow-glide** (distance on air), **probe-fade** (out, nothing there,
back), and **dead-drift** (the honest majority: 32.4% of legs are nothing
happening).

Two corpus facts to carry: **big legs keep what they take** (flush-legs give
back a median 5% of their extreme — the reason a fly entered at a V-dump
extreme isn't fighting the leg that made it), and **legs die hot** — the
**pivot-atom** where one leg ends and the next begins grades F1 conviction
63% of the time. Swings end by opposition, not exhaustion. The exceptions —
quiet pivots like 7/22's 11:19 top — are real, at 37%, and worth knowing by
that number.

## Essay IV — The tiers, and where your words live

**The one idea:** every vocabulary you already have keeps working; each word
now has an address.

Start at the smallest unit and build upward. An **atom** is one minute of
tape. A **leg** contains atoms — one stroke of the zigzag, median fifteen
minutes of them. The trading day contains the legs: write down each leg's
archetype in the order they happened — 7/22 reads roughly "steady-leg,
flush-leg, absorption-stall, leg-grind…" — and that ordered list is the
**day-sequence**, the whole day's character in one line. (A Market Profile
rotation day, the D-shape, shows itself here as short legs alternating
direction — the rotation is readable from the inside.) So the nesting is:
minutes, inside swings, inside the day. Three tiers, each built from the one
below it.

The **axes** — effort, effect, force — are not a fourth tier in that stack.
They are the rulers, and the same rulers measure more than one tier: a single
minute gets an effort score, and so does an entire leg.

One more tier exists, and it deliberately does *not* sit inside the nesting —
it sits beside it. An **episode** is one whole fight at one price level, from
first contact to resolution. The nested tiers slice the day by *time* — the
clock, then the zigzag. An episode slices it by *place*: one level's fight
can stretch across pieces of several legs. This is the recognizer's home
ground. It watches episodes on **2,000-contract bars**, calls the four
**stages** (flush-stage → stall-stage → flip-stage → confirm-stage) as they
happen, and every **primitive** from your footprint reading — **sweep-print**,
**absorption-read**, **delta-divergence**, **imbalance-stack** — lives here.
It is also the tier with a different clock: episodes and stages are **LIVE**,
called in the moment, while legs and the day-sequence are **HINDSIGHT** maps
drawn after the close (Essay V). Nothing you learned in documents 01–08 was
replaced; it was given a floor in the building.

The tiers also resolve an apparent paradox worth meeting head-on: 7/22's
afternoon leg is wall-to-wall F4-dead *atoms*, yet grades F1 at *leg* scale —
because 221 minutes of small efforts sum to a large one. Atom grades are the
day's texture; leg grades are corpus-scale mass. Both true. When you speak a
grade, say which tier you mean.

<!-- fig:722-paradox START -->
<svg viewBox="0 0 860 380" width="100%" role="img" aria-label="Price path and atom string of the 7/22 afternoon leg" xmlns="http://www.w3.org/2000/svg" style="background:#fafafa">
<text x="56" y="24" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="15" font-weight="600" fill="#222222">The afternoon leg, atom by atom — 11:19 → 15:00 CT, −26.00 pts</text>
<text x="56" y="42" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" fill="#898781">ES 1-minute closes (top) and the leg&#8217;s atom string (below) — one tick per minute, colored by cell</text>
<line x1="56" y1="235.5" x2="844" y2="235.5" stroke="#e1e0d9" stroke-width="1"/>
<text x="48" y="239.5" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">7535</text>
<line x1="56" y1="204.2" x2="844" y2="204.2" stroke="#e1e0d9" stroke-width="1"/>
<text x="48" y="208.2" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">7540</text>
<line x1="56" y1="172.9" x2="844" y2="172.9" stroke="#e1e0d9" stroke-width="1"/>
<text x="48" y="176.9" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">7545</text>
<line x1="56" y1="141.7" x2="844" y2="141.7" stroke="#e1e0d9" stroke-width="1"/>
<text x="48" y="145.7" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">7550</text>
<line x1="56" y1="110.4" x2="844" y2="110.4" stroke="#e1e0d9" stroke-width="1"/>
<text x="48" y="114.4" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">7555</text>
<line x1="56" y1="79.1" x2="844" y2="79.1" stroke="#e1e0d9" stroke-width="1"/>
<text x="48" y="83.1" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">7560</text>
<polyline points="56.0,61.9 59.6,69.7 63.2,68.1 66.7,69.7 70.3,72.8 73.9,69.7 77.5,71.2 81.1,72.8 84.7,75.9 88.2,72.8 91.8,69.7 95.4,72.8 99.0,72.8 102.6,71.2 106.1,61.9 109.7,66.6 113.3,71.2 116.9,72.8 120.5,72.8 124.1,66.6 127.6,69.7 131.2,75.9 134.8,75.9 138.4,80.6 142.0,80.6 145.5,75.9 149.1,80.6 152.7,86.9 156.3,90.0 159.9,83.8 163.5,86.9 167.0,85.3 170.6,93.1 174.2,86.9 177.8,90.0 181.4,91.6 184.9,72.8 188.5,72.8 192.1,68.1 195.7,71.2 199.3,72.8 202.9,68.1 206.4,74.4 210.0,83.8 213.6,91.6 217.2,94.7 220.8,91.6 224.3,90.0 227.9,79.1 231.5,85.3 235.1,86.9 238.7,93.1 242.3,93.1 245.8,96.3 249.4,101.0 253.0,107.2 256.6,108.8 260.2,108.8 263.7,104.1 267.3,105.7 270.9,110.4 274.5,115.1 278.1,119.7 281.7,122.9 285.2,119.7 288.8,116.6 292.4,124.4 296.0,121.3 299.6,119.7 303.1,115.1 306.7,122.9 310.3,116.6 313.9,113.5 317.5,121.3 321.1,124.4 324.6,135.4 328.2,129.1 331.8,122.9 335.4,113.5 339.0,118.2 342.5,104.1 346.1,116.6 349.7,116.6 353.3,116.6 356.9,121.3 360.5,119.7 364.0,118.2 367.6,116.6 371.2,122.9 374.8,122.9 378.4,124.4 381.9,122.9 385.5,119.7 389.1,126.0 392.7,135.4 396.3,144.8 399.9,146.3 403.4,152.6 407.0,154.2 410.6,155.7 414.2,157.3 417.8,149.5 421.3,158.9 424.9,166.7 428.5,171.4 432.1,165.1 435.7,165.1 439.3,160.4 442.8,147.9 446.4,158.9 450.0,169.8 453.6,168.3 457.2,176.1 460.7,183.9 464.3,183.9 467.9,187.0 471.5,183.9 475.1,176.1 478.7,179.2 482.2,168.3 485.8,174.5 489.4,162.0 493.0,168.3 496.6,169.8 500.1,176.1 503.7,174.5 507.3,171.4 510.9,171.4 514.5,169.8 518.1,158.9 521.6,160.4 525.2,169.8 528.8,179.2 532.4,183.9 536.0,176.1 539.5,176.1 543.1,162.0 546.7,163.6 550.3,166.7 553.9,165.1 557.5,163.6 561.0,171.4 564.6,163.6 568.2,171.4 571.8,169.8 575.4,171.4 578.9,155.7 582.5,158.9 586.1,165.1 589.7,163.6 593.3,174.5 596.9,179.2 600.4,172.9 604.0,174.5 607.6,165.1 611.2,157.3 614.8,152.6 618.3,158.9 621.9,157.3 625.5,157.3 629.1,162.0 632.7,165.1 636.3,174.5 639.8,177.6 643.4,168.3 647.0,171.4 650.6,176.1 654.2,168.3 657.7,172.9 661.3,172.9 664.9,174.5 668.5,177.6 672.1,183.9 675.7,191.7 679.2,191.7 682.8,193.3 686.4,191.7 690.0,180.8 693.6,180.8 697.1,179.2 700.7,180.8 704.3,185.5 707.9,194.9 711.5,188.6 715.1,190.2 718.6,194.9 722.2,201.1 725.8,205.8 729.4,196.4 733.0,185.5 736.5,188.6 740.1,202.7 743.7,202.7 747.3,201.1 750.9,205.8 754.5,207.4 758.0,210.5 761.6,210.5 765.2,213.6 768.8,221.4 772.4,224.6 775.9,218.3 779.5,208.9 783.1,199.5 786.7,196.4 790.3,199.5 793.9,199.5 797.4,199.5 801.0,194.9 804.6,191.7 808.2,187.0 811.8,194.9 815.3,198.0 818.9,187.0 822.5,188.6 826.1,196.4 829.7,204.2 833.3,199.5 836.8,183.9 840.4,188.6 844.0,226.1" fill="none" stroke="#52514e" stroke-width="2" stroke-linejoin="round"/>
<circle cx="56.0" cy="61.9" r="4" fill="#52514e"/>
<text x="64.0" y="81.9" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781">11:19 — quiet pivot, F4 dead 0.276</text>
<circle cx="844.0" cy="226.1" r="4" fill="#2a78d6"/>
<text x="836.0" y="216.1" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">14:59 — loudest atom of the day, F1 1.000</text>
<rect x="56.00" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:19 · F4 dead 0.276 · 1,040 contracts · net +0.25</title></rect>
<rect x="59.57" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:20 · F3 hollow 0.298 · 955 contracts · net -1.00</title></rect>
<rect x="63.13" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:21 · F4 dead 0.206 · 725 contracts · net +0.50</title></rect>
<rect x="66.70" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:22 · F4 dead 0.466 · 851 contracts · net -0.25</title></rect>
<rect x="70.26" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:23 · F4 dead 0.466 · 653 contracts · net -0.25</title></rect>
<rect x="73.83" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:24 · F3 hollow 0.092 · 790 contracts · net +0.75</title></rect>
<rect x="77.39" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:25 · F4 dead 0.718 · 692 contracts · net +0.00</title></rect>
<rect x="80.96" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:26 · F4 dead 0.210 · 1,105 contracts · net -0.25</title></rect>
<rect x="84.52" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:27 · F4 dead 0.206 · 875 contracts · net -0.50</title></rect>
<rect x="88.09" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:28 · F4 dead 0.206 · 736 contracts · net +0.50</title></rect>
<rect x="91.66" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:29 · F4 dead 0.206 · 454 contracts · net +0.50</title></rect>
<rect x="95.22" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:30 · F4 dead 0.206 · 695 contracts · net -0.50</title></rect>
<rect x="98.79" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:31 · F4 dead 0.698 · 710 contracts · net +0.00</title></rect>
<rect x="102.35" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:32 · F4 dead 0.466 · 690 contracts · net +0.25</title></rect>
<rect x="105.92" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:33 · F3 hollow 0.210 · 1,105 contracts · net +1.75</title></rect>
<rect x="109.48" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:34 · F4 dead 0.206 · 548 contracts · net -0.50</title></rect>
<rect x="113.05" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:35 · F4 dead 0.206 · 538 contracts · net -0.50</title></rect>
<rect x="116.62" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:36 · F4 dead 0.764 · 666 contracts · net +0.00</title></rect>
<rect x="120.18" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:37 · F4 dead 0.466 · 591 contracts · net +0.25</title></rect>
<rect x="123.75" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:38 · F3 hollow 0.298 · 442 contracts · net +1.00</title></rect>
<rect x="127.31" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:39 · F4 dead 0.206 · 450 contracts · net -0.50</title></rect>
<rect x="130.88" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:40 · F3 hollow 0.298 · 955 contracts · net -1.00</title></rect>
<rect x="134.44" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:41 · F4 dead 0.630 · 769 contracts · net +0.00</title></rect>
<rect x="138.01" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:42 · F4 dead 0.206 · 857 contracts · net -0.50</title></rect>
<rect x="141.57" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:43 · F4 dead 0.524 · 839 contracts · net +0.00</title></rect>
<rect x="145.14" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:44 · F3 hollow 0.092 · 643 contracts · net +0.75</title></rect>
<rect x="148.71" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:45 · F3 hollow 0.092 · 1,038 contracts · net -0.75</title></rect>
<rect x="152.27" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:46 · F3 hollow 0.246 · 1,069 contracts · net -1.25</title></rect>
<rect x="155.84" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:47 · F4 dead 0.154 · 1,181 contracts · net -0.50</title></rect>
<rect x="159.40" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:48 · F3 hollow 0.092 · 966 contracts · net +0.75</title></rect>
<rect x="162.97" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:49 · F4 dead 0.466 · 680 contracts · net -0.25</title></rect>
<rect x="166.53" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:50 · F4 dead 0.364 · 980 contracts · net +0.25</title></rect>
<rect x="170.10" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:51 · F3 hollow 0.236 · 1,080 contracts · net -1.25</title></rect>
<rect x="173.67" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:52 · F3 hollow 0.298 · 827 contracts · net +1.00</title></rect>
<rect x="177.23" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:53 · F3 hollow 0.092 · 637 contracts · net -0.75</title></rect>
<rect x="180.80" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:54 · F4 dead 0.466 · 688 contracts · net -0.25</title></rect>
<rect x="184.36" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:55 · F3 hollow 0.302 · 1,003 contracts · net +3.00</title></rect>
<rect x="187.93" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:56 · F4 dead 0.544 · 823 contracts · net +0.00</title></rect>
<rect x="191.49" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>11:57 · F3 hollow 0.092 · 784 contracts · net +0.75</title></rect>
<rect x="195.06" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:58 · F4 dead 0.466 · 680 contracts · net -0.25</title></rect>
<rect x="198.62" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>11:59 · F4 dead 0.466 · 588 contracts · net -0.25</title></rect>
<rect x="202.19" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:00 · F3 hollow 0.092 · 1,199 contracts · net +0.75</title></rect>
<rect x="205.76" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:01 · F3 hollow 0.462 · 617 contracts · net -1.25</title></rect>
<rect x="209.32" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:02 · F3 hollow 0.308 · 1,001 contracts · net -1.50</title></rect>
<rect x="212.89" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>12:03 · F1 conviction 0.216 · 1,710 contracts · net -1.25</title></rect>
<rect x="216.45" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:04 · F3 hollow 0.092 · 1,058 contracts · net -0.75</title></rect>
<rect x="220.02" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:05 · F4 dead 0.098 · 1,238 contracts · net +0.50</title></rect>
<rect x="223.58" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:06 · F4 dead 0.016 · 1,379 contracts · net +0.00</title></rect>
<rect x="227.15" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:07 · F3 hollow 0.262 · 1,044 contracts · net +1.75</title></rect>
<rect x="230.71" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:08 · F3 hollow 0.298 · 563 contracts · net -1.00</title></rect>
<rect x="234.28" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:09 · F4 dead 0.466 · 527 contracts · net -0.25</title></rect>
<rect x="237.85" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:10 · F3 hollow 0.298 · 591 contracts · net -1.00</title></rect>
<rect x="241.41" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:11 · F4 dead 0.466 · 872 contracts · net -0.25</title></rect>
<rect x="244.98" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:12 · F3 hollow 0.092 · 493 contracts · net -0.75</title></rect>
<rect x="248.54" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:13 · F3 hollow 0.092 · 769 contracts · net -0.75</title></rect>
<rect x="252.11" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>12:14 · F1 conviction 0.056 · 1,455 contracts · net -1.25</title></rect>
<rect x="255.67" y="252.0" width="2.97" height="36" fill="#eb6834"><title>12:15 · F2 absorption 0.292 · 1,822 contracts · net -0.25</title></rect>
<rect x="259.24" y="252.0" width="2.97" height="36" fill="#eb6834"><title>12:16 · F2 absorption 0.016 · 1,422 contracts · net +0.25</title></rect>
<rect x="262.81" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:17 · F3 hollow 0.092 · 991 contracts · net +0.75</title></rect>
<rect x="266.37" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:18 · F4 dead 0.206 · 903 contracts · net -0.50</title></rect>
<rect x="269.94" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:19 · F4 dead 0.206 · 1,072 contracts · net -0.50</title></rect>
<rect x="273.50" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:20 · F3 hollow 0.200 · 1,129 contracts · net -1.00</title></rect>
<rect x="277.07" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>12:21 · F1 conviction 0.158 · 1,596 contracts · net -1.00</title></rect>
<rect x="280.63" y="252.0" width="2.97" height="36" fill="#eb6834"><title>12:22 · F2 absorption 0.206 · 2,313 contracts · net -0.50</title></rect>
<rect x="284.20" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>12:23 · F1 conviction 0.092 · 1,492 contracts · net +0.75</title></rect>
<rect x="287.76" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:24 · F4 dead 0.124 · 1,216 contracts · net +0.25</title></rect>
<rect x="291.33" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:25 · F3 hollow 0.184 · 1,138 contracts · net -1.50</title></rect>
<rect x="294.90" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:26 · F3 hollow 0.092 · 667 contracts · net +0.75</title></rect>
<rect x="298.46" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:27 · F4 dead 0.206 · 545 contracts · net +0.50</title></rect>
<rect x="302.03" y="252.0" width="2.97" height="36" fill="#eb6834"><title>12:28 · F2 absorption 0.026 · 1,425 contracts · net +0.50</title></rect>
<rect x="305.59" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:29 · F3 hollow 0.066 · 1,284 contracts · net -1.25</title></rect>
<rect x="309.16" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:30 · F3 hollow 0.462 · 796 contracts · net +1.25</title></rect>
<rect x="312.72" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:31 · F4 dead 0.206 · 952 contracts · net +0.50</title></rect>
<rect x="316.29" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:32 · F3 hollow 0.462 · 883 contracts · net -1.25</title></rect>
<rect x="319.86" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:33 · F3 hollow 0.092 · 918 contracts · net -0.75</title></rect>
<rect x="323.42" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:34 · F3 hollow 0.344 · 989 contracts · net -1.75</title></rect>
<rect x="326.99" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:35 · F3 hollow 0.092 · 1,218 contracts · net +0.75</title></rect>
<rect x="330.55" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:36 · F3 hollow 0.462 · 896 contracts · net +1.25</title></rect>
<rect x="334.12" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:37 · F3 hollow 0.380 · 971 contracts · net +1.50</title></rect>
<rect x="337.68" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:38 · F3 hollow 0.092 · 789 contracts · net -0.75</title></rect>
<rect x="341.25" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:39 · F3 hollow 0.390 · 964 contracts · net +2.25</title></rect>
<rect x="344.81" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:40 · F3 hollow 0.610 · 779 contracts · net -1.75</title></rect>
<rect x="348.38" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:41 · F4 dead 0.770 · 665 contracts · net +0.00</title></rect>
<rect x="351.95" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:42 · F4 dead 0.836 · 530 contracts · net +0.00</title></rect>
<rect x="355.51" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:43 · F3 hollow 0.298 · 625 contracts · net -1.00</title></rect>
<rect x="359.08" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:44 · F4 dead 0.466 · 374 contracts · net +0.25</title></rect>
<rect x="362.64" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:45 · F4 dead 0.466 · 409 contracts · net +0.25</title></rect>
<rect x="366.21" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:46 · F4 dead 0.206 · 524 contracts · net +0.50</title></rect>
<rect x="369.77" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:47 · F3 hollow 0.298 · 654 contracts · net -1.00</title></rect>
<rect x="373.34" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:48 · F4 dead 0.836 · 497 contracts · net +0.00</title></rect>
<rect x="376.90" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:49 · F4 dead 0.836 · 482 contracts · net +0.00</title></rect>
<rect x="380.47" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:50 · F4 dead 0.794 · 649 contracts · net +0.00</title></rect>
<rect x="384.04" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:51 · F4 dead 0.466 · 583 contracts · net +0.25</title></rect>
<rect x="387.60" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:52 · F3 hollow 0.462 · 570 contracts · net -1.25</title></rect>
<rect x="391.17" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:53 · F3 hollow 0.462 · 867 contracts · net -1.25</title></rect>
<rect x="394.73" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>12:54 · F1 conviction 0.324 · 1,904 contracts · net -1.75</title></rect>
<rect x="398.30" y="252.0" width="2.97" height="36" fill="#eb6834"><title>12:55 · F2 absorption 0.466 · 3,413 contracts · net -0.25</title></rect>
<rect x="401.86" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>12:56 · F3 hollow 0.170 · 1,155 contracts · net -1.00</title></rect>
<rect x="405.43" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:57 · F4 dead 0.426 · 939 contracts · net -0.25</title></rect>
<rect x="409.00" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:58 · F4 dead 0.344 · 989 contracts · net -0.25</title></rect>
<rect x="412.56" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>12:59 · F4 dead 0.698 · 710 contracts · net +0.00</title></rect>
<rect x="416.13" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:00 · F1 conviction 0.088 · 1,475 contracts · net +1.00</title></rect>
<rect x="419.69" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:01 · F1 conviction 0.354 · 1,927 contracts · net -1.50</title></rect>
<rect x="423.26" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:02 · F1 conviction 0.462 · 4,134 contracts · net -1.25</title></rect>
<rect x="426.82" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:03 · F4 dead 0.112 · 1,218 contracts · net -0.50</title></rect>
<rect x="430.39" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:04 · F1 conviction 0.006 · 1,402 contracts · net +1.00</title></rect>
<rect x="433.95" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:05 · F4 dead 0.030 · 1,370 contracts · net +0.00</title></rect>
<rect x="437.52" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:06 · F3 hollow 0.092 · 1,183 contracts · net +0.75</title></rect>
<rect x="441.09" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:07 · F3 hollow 0.052 · 1,300 contracts · net +2.00</title></rect>
<rect x="444.65" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:08 · F3 hollow 0.652 · 741 contracts · net -1.75</title></rect>
<rect x="448.22" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:09 · F3 hollow 0.134 · 1,194 contracts · net -1.75</title></rect>
<rect x="451.78" y="252.0" width="2.97" height="36" fill="#eb6834"><title>13:10 · F2 absorption 0.056 · 1,455 contracts · net +0.50</title></rect>
<rect x="455.35" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:11 · F3 hollow 0.498 · 868 contracts · net -1.50</title></rect>
<rect x="458.91" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:12 · F1 conviction 0.000 · 1,394 contracts · net -1.50</title></rect>
<rect x="462.48" y="252.0" width="2.97" height="36" fill="#eb6834"><title>13:13 · F2 absorption 0.180 · 1,615 contracts · net +0.00</title></rect>
<rect x="466.05" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:14 · F4 dead 0.206 · 974 contracts · net -0.50</title></rect>
<rect x="469.61" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:15 · F3 hollow 0.092 · 1,066 contracts · net +0.75</title></rect>
<rect x="473.18" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:16 · F1 conviction 0.184 · 1,628 contracts · net +1.50</title></rect>
<rect x="476.74" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:17 · F4 dead 0.466 · 757 contracts · net -0.25</title></rect>
<rect x="480.31" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:18 · F3 hollow 0.292 · 1,015 contracts · net +1.50</title></rect>
<rect x="483.87" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:19 · F3 hollow 0.370 · 976 contracts · net -1.25</title></rect>
<rect x="487.44" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:20 · F3 hollow 0.288 · 1,031 contracts · net +1.75</title></rect>
<rect x="491.00" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:21 · F1 conviction 0.020 · 1,424 contracts · net -0.75</title></rect>
<rect x="494.57" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:22 · F4 dead 0.466 · 684 contracts · net -0.25</title></rect>
<rect x="498.14" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:23 · F3 hollow 0.298 · 854 contracts · net -1.00</title></rect>
<rect x="501.70" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:24 · F4 dead 0.206 · 993 contracts · net +0.50</title></rect>
<rect x="505.27" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:25 · F4 dead 0.466 · 329 contracts · net +0.25</title></rect>
<rect x="508.83" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:26 · F4 dead 0.836 · 584 contracts · net +0.00</title></rect>
<rect x="512.40" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:27 · F4 dead 0.836 · 562 contracts · net +0.00</title></rect>
<rect x="515.96" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:28 · F1 conviction 0.272 · 1,800 contracts · net +2.00</title></rect>
<rect x="519.53" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:29 · F4 dead 0.206 · 828 contracts · net -0.50</title></rect>
<rect x="523.10" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:30 · F1 conviction 0.524 · 2,258 contracts · net -1.50</title></rect>
<rect x="526.66" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:31 · F1 conviction 0.276 · 1,802 contracts · net -1.75</title></rect>
<rect x="530.23" y="252.0" width="2.97" height="36" fill="#eb6834"><title>13:32 · F2 absorption 0.206 · 1,922 contracts · net -0.50</title></rect>
<rect x="533.79" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:33 · F3 hollow 0.298 · 949 contracts · net +1.00</title></rect>
<rect x="537.36" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:34 · F4 dead 0.676 · 726 contracts · net +0.00</title></rect>
<rect x="540.92" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:35 · F3 hollow 0.088 · 1,248 contracts · net +2.50</title></rect>
<rect x="544.49" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:36 · F4 dead 0.194 · 1,130 contracts · net -0.50</title></rect>
<rect x="548.05" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:37 · F3 hollow 0.092 · 606 contracts · net -0.75</title></rect>
<rect x="551.62" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:38 · F4 dead 0.466 · 485 contracts · net +0.25</title></rect>
<rect x="555.19" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:39 · F4 dead 0.466 · 778 contracts · net +0.25</title></rect>
<rect x="558.75" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:40 · F3 hollow 0.600 · 786 contracts · net -1.50</title></rect>
<rect x="562.32" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:41 · F3 hollow 0.298 · 774 contracts · net +1.00</title></rect>
<rect x="565.88" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:42 · F3 hollow 0.036 · 1,352 contracts · net -1.50</title></rect>
<rect x="569.45" y="252.0" width="2.97" height="36" fill="#eb6834"><title>13:43 · F2 absorption 0.042 · 1,444 contracts · net +0.25</title></rect>
<rect x="573.01" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:44 · F4 dead 0.046 · 1,311 contracts · net -0.50</title></rect>
<rect x="576.58" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:45 · F1 conviction 0.626 · 2,522 contracts · net +2.25</title></rect>
<rect x="580.14" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:46 · F3 hollow 0.092 · 1,086 contracts · net -0.75</title></rect>
<rect x="583.71" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:47 · F3 hollow 0.298 · 543 contracts · net -1.00</title></rect>
<rect x="587.28" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:48 · F4 dead 0.206 · 814 contracts · net +0.50</title></rect>
<rect x="590.84" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:49 · F3 hollow 0.272 · 1,041 contracts · net -1.75</title></rect>
<rect x="594.41" y="252.0" width="2.97" height="36" fill="#eb6834"><title>13:50 · F2 absorption 0.076 · 1,471 contracts · net -0.50</title></rect>
<rect x="597.97" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:51 · F3 hollow 0.092 · 1,001 contracts · net +0.75</title></rect>
<rect x="601.54" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:52 · F4 dead 0.466 · 790 contracts · net -0.25</title></rect>
<rect x="605.10" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:53 · F3 hollow 0.610 · 634 contracts · net +1.50</title></rect>
<rect x="608.67" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>13:54 · F1 conviction 0.430 · 2,082 contracts · net +1.25</title></rect>
<rect x="612.24" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:55 · F3 hollow 0.092 · 1,115 contracts · net +0.75</title></rect>
<rect x="615.80" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:56 · F3 hollow 0.056 · 1,298 contracts · net -0.75</title></rect>
<rect x="619.37" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:57 · F4 dead 0.466 · 522 contracts · net +0.25</title></rect>
<rect x="622.93" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>13:58 · F4 dead 0.466 · 719 contracts · net -0.25</title></rect>
<rect x="626.50" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>13:59 · F3 hollow 0.092 · 955 contracts · net -0.75</title></rect>
<rect x="630.06" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:00 · F3 hollow 0.072 · 1,278 contracts · net -0.75</title></rect>
<rect x="633.63" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:01 · F1 conviction 0.610 · 2,475 contracts · net -1.50</title></rect>
<rect x="637.19" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:02 · F4 dead 0.206 · 989 contracts · net -0.50</title></rect>
<rect x="640.76" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:03 · F3 hollow 0.230 · 1,083 contracts · net +1.50</title></rect>
<rect x="644.33" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:04 · F3 hollow 0.092 · 912 contracts · net -0.75</title></rect>
<rect x="647.89" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:05 · F4 dead 0.206 · 745 contracts · net -0.50</title></rect>
<rect x="651.46" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:06 · F3 hollow 0.076 · 1,277 contracts · net +1.00</title></rect>
<rect x="655.02" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:07 · F3 hollow 0.092 · 1,147 contracts · net -0.75</title></rect>
<rect x="658.59" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:08 · F4 dead 0.466 · 687 contracts · net +0.25</title></rect>
<rect x="662.15" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:09 · F4 dead 0.206 · 405 contracts · net -0.50</title></rect>
<rect x="665.72" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:10 · F4 dead 0.206 · 997 contracts · net -0.50</title></rect>
<rect x="669.29" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:11 · F3 hollow 0.164 · 1,156 contracts · net -1.00</title></rect>
<rect x="672.85" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:12 · F3 hollow 0.016 · 1,379 contracts · net -1.25</title></rect>
<rect x="676.42" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:13 · F4 dead 0.010 · 1,382 contracts · net +0.25</title></rect>
<rect x="679.98" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:14 · F2 absorption 0.206 · 2,001 contracts · net -0.50</title></rect>
<rect x="683.55" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:15 · F2 absorption 0.206 · 1,926 contracts · net +0.50</title></rect>
<rect x="687.11" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:16 · F1 conviction 0.046 · 1,448 contracts · net +1.50</title></rect>
<rect x="690.68" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:17 · F4 dead 0.662 · 734 contracts · net +0.00</title></rect>
<rect x="694.24" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:18 · F4 dead 0.466 · 581 contracts · net +0.25</title></rect>
<rect x="697.81" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:19 · F4 dead 0.466 · 734 contracts · net -0.25</title></rect>
<rect x="701.38" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:20 · F3 hollow 0.092 · 900 contracts · net -0.75</title></rect>
<rect x="704.94" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:21 · F1 conviction 0.112 · 1,520 contracts · net -1.25</title></rect>
<rect x="708.51" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:22 · F3 hollow 0.298 · 819 contracts · net +1.00</title></rect>
<rect x="712.07" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:23 · F4 dead 0.466 · 661 contracts · net -0.25</title></rect>
<rect x="715.64" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:24 · F3 hollow 0.092 · 687 contracts · net -0.75</title></rect>
<rect x="719.20" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:25 · F1 conviction 0.092 · 1,759 contracts · net -0.75</title></rect>
<rect x="722.77" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:26 · F2 absorption 0.190 · 1,632 contracts · net -0.50</title></rect>
<rect x="726.33" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:27 · F1 conviction 0.144 · 1,562 contracts · net +1.50</title></rect>
<rect x="729.90" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:28 · F1 conviction 0.584 · 2,412 contracts · net +1.50</title></rect>
<rect x="733.47" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:29 · F4 dead 0.206 · 774 contracts · net -0.50</title></rect>
<rect x="737.03" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:30 · F1 conviction 0.384 · 1,997 contracts · net -2.25</title></rect>
<rect x="740.60" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:31 · F2 absorption 0.206 · 1,672 contracts · net +0.00</title></rect>
<rect x="744.16" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:32 · F4 dead 0.026 · 1,377 contracts · net +0.00</title></rect>
<rect x="747.73" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:33 · F1 conviction 0.102 · 1,504 contracts · net -1.00</title></rect>
<rect x="751.29" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:34 · F2 absorption 0.072 · 1,470 contracts · net -0.25</title></rect>
<rect x="754.86" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:35 · F4 dead 0.206 · 1,042 contracts · net -0.50</title></rect>
<rect x="758.43" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:36 · F2 absorption 0.420 · 2,060 contracts · net -0.25</title></rect>
<rect x="761.99" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:37 · F3 hollow 0.092 · 1,193 contracts · net -0.75</title></rect>
<rect x="765.56" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:38 · F1 conviction 0.462 · 2,254 contracts · net -1.25</title></rect>
<rect x="769.12" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:39 · F2 absorption 0.200 · 1,667 contracts · net -0.25</title></rect>
<rect x="772.69" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:40 · F1 conviction 0.256 · 1,776 contracts · net +1.00</title></rect>
<rect x="776.25" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:41 · F1 conviction 0.252 · 1,774 contracts · net +1.25</title></rect>
<rect x="779.82" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:42 · F1 conviction 0.416 · 2,054 contracts · net +1.75</title></rect>
<rect x="783.38" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:43 · F2 absorption 0.128 · 1,544 contracts · net +0.50</title></rect>
<rect x="786.95" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:44 · F2 absorption 0.318 · 1,903 contracts · net -0.25</title></rect>
<rect x="790.52" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:45 · F2 absorption 0.488 · 2,192 contracts · net +0.00</title></rect>
<rect x="794.08" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:46 · F2 absorption 0.124 · 1,530 contracts · net +0.25</title></rect>
<rect x="797.65" y="252.0" width="2.97" height="36" fill="#1baf7a"><title>14:47 · F3 hollow 0.092 · 951 contracts · net +0.75</title></rect>
<rect x="801.21" y="266.0" width="2.97" height="8" fill="#c9c8c1"><title>14:48 · F4 dead 0.006 · 1,385 contracts · net +0.50</title></rect>
<rect x="804.78" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:49 · F1 conviction 0.092 · 2,097 contracts · net +0.75</title></rect>
<rect x="808.34" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:50 · F1 conviction 0.610 · 5,394 contracts · net -1.50</title></rect>
<rect x="811.91" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:51 · F2 absorption 0.206 · 2,096 contracts · net -0.50</title></rect>
<rect x="815.48" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:52 · F1 conviction 0.606 · 2,441 contracts · net +1.75</title></rect>
<rect x="819.04" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:53 · F2 absorption 0.466 · 2,144 contracts · net -0.25</title></rect>
<rect x="822.61" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:54 · F1 conviction 0.298 · 3,376 contracts · net -1.00</title></rect>
<rect x="826.17" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:55 · F1 conviction 0.462 · 3,601 contracts · net -1.25</title></rect>
<rect x="829.74" y="252.0" width="2.97" height="36" fill="#eb6834"><title>14:56 · F2 absorption 0.206 · 2,877 contracts · net +0.50</title></rect>
<rect x="833.30" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:57 · F1 conviction 0.866 · 5,246 contracts · net +2.50</title></rect>
<rect x="836.87" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:58 · F1 conviction 0.092 · 7,538 contracts · net -0.75</title></rect>
<rect x="840.43" y="252.0" width="2.97" height="36" fill="#2a78d6"><title>14:59 · F1 conviction 1.000 · 39,694 contracts · net -6.25</title></rect>
<text x="95.4" y="304" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">11:30</text>
<text x="202.9" y="304" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">12:00</text>
<text x="310.3" y="304" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">12:30</text>
<text x="417.8" y="304" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">13:00</text>
<text x="525.2" y="304" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">13:30</text>
<text x="632.7" y="304" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">14:00</text>
<text x="740.1" y="304" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">14:30</text>
<text x="844.0" y="304" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">15:00</text>
<rect x="56" y="322" width="12" height="12" fill="#2a78d6"/>
<text x="74" y="332" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" fill="#52514e">F1 conviction ×37</text>
<rect x="251" y="322" width="12" height="12" fill="#eb6834"/>
<text x="269" y="332" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" fill="#52514e">F2 absorption ×24</text>
<rect x="446" y="322" width="12" height="12" fill="#1baf7a"/>
<text x="464" y="332" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" fill="#52514e">F3 hollow ×79</text>
<rect x="605" y="325" width="12" height="6" fill="#c9c8c1"/>
<text x="623" y="332" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" fill="#52514e">F4 dead ×81</text>
</svg>

*Figure 1 — every minute of the fade, graded. Full-height ticks are atoms with something happening; the short gray ticks are F4 dead — the leg is mostly absence. (run `20260728T123632Z`, hover any tick for its atom.)*

<svg viewBox="0 0 860 320" width="100%" role="img" aria-label="Cumulative effort of the afternoon leg vs corpus landmarks" xmlns="http://www.w3.org/2000/svg" style="background:#fafafa">
<text x="72" y="24" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="15" font-weight="600" fill="#222222">The same 221 minutes as a running sum of effort</text>
<text x="72" y="42" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" fill="#898781">small efforts, summed minute over minute — atom texture below, corpus-scale mass at the right edge</text>
<line x1="72" y1="252.0" x2="844" y2="252.0" stroke="#e1e0d9" stroke-width="1"/>
<text x="64" y="256.0" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">0k</text>
<line x1="72" y1="198.7" x2="844" y2="198.7" stroke="#e1e0d9" stroke-width="1"/>
<text x="64" y="202.7" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">100k</text>
<line x1="72" y1="145.4" x2="844" y2="145.4" stroke="#e1e0d9" stroke-width="1"/>
<text x="64" y="149.4" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">200k</text>
<line x1="72" y1="92.1" x2="844" y2="92.1" stroke="#e1e0d9" stroke-width="1"/>
<text x="64" y="96.1" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">300k</text>
<path d="M 72.0,252 L 72.0,251.4 L 75.5,250.9 L 79.0,250.5 L 82.5,250.1 L 86.0,249.7 L 89.5,249.3 L 93.1,249.0 L 96.6,248.4 L 100.1,247.9 L 103.6,247.5 L 107.1,247.3 L 110.6,246.9 L 114.1,246.5 L 117.6,246.2 L 121.1,245.6 L 124.6,245.3 L 128.1,245.0 L 131.7,244.6 L 135.2,244.3 L 138.7,244.1 L 142.2,243.8 L 145.7,243.3 L 149.2,242.9 L 152.7,242.5 L 156.2,242.0 L 159.7,241.7 L 163.2,241.1 L 166.7,240.5 L 170.3,239.9 L 173.8,239.4 L 177.3,239.0 L 180.8,238.5 L 184.3,237.9 L 187.8,237.5 L 191.3,237.2 L 194.8,236.8 L 198.3,236.3 L 201.8,235.8 L 205.3,235.4 L 208.9,235.0 L 212.4,234.7 L 215.9,234.1 L 219.4,233.8 L 222.9,233.2 L 226.4,232.3 L 229.9,231.7 L 233.4,231.1 L 236.9,230.4 L 240.4,229.8 L 243.9,229.5 L 247.5,229.2 L 251.0,228.9 L 254.5,228.4 L 258.0,228.2 L 261.5,227.8 L 265.0,227.0 L 268.5,226.0 L 272.0,225.3 L 275.5,224.7 L 279.0,224.2 L 282.5,223.7 L 286.1,223.1 L 289.6,222.2 L 293.1,221.0 L 296.6,220.2 L 300.1,219.5 L 303.6,218.9 L 307.1,218.6 L 310.6,218.3 L 314.1,217.5 L 317.6,216.8 L 321.1,216.4 L 324.7,215.9 L 328.2,215.4 L 331.7,215.0 L 335.2,214.4 L 338.7,213.8 L 342.2,213.3 L 345.7,212.8 L 349.2,212.4 L 352.7,211.9 L 356.2,211.4 L 359.7,211.1 L 363.3,210.8 L 366.8,210.5 L 370.3,210.3 L 373.8,210.0 L 377.3,209.8 L 380.8,209.4 L 384.3,209.2 L 387.8,208.9 L 391.3,208.6 L 394.8,208.2 L 398.3,207.9 L 401.9,207.5 L 405.4,206.5 L 408.9,204.6 L 412.4,204.0 L 415.9,203.5 L 419.4,203.0 L 422.9,202.6 L 426.4,201.8 L 429.9,200.8 L 433.4,198.6 L 436.9,198.0 L 440.5,197.2 L 444.0,196.5 L 447.5,195.8 L 451.0,195.1 L 454.5,194.8 L 458.0,194.1 L 461.5,193.3 L 465.0,192.9 L 468.5,192.1 L 472.0,191.3 L 475.5,190.8 L 479.1,190.2 L 482.6,189.3 L 486.1,188.9 L 489.6,188.4 L 493.1,187.9 L 496.6,187.3 L 500.1,186.5 L 503.6,186.2 L 507.1,185.7 L 510.6,185.2 L 514.1,185.0 L 517.7,184.7 L 521.2,184.4 L 524.7,183.4 L 528.2,183.0 L 531.7,181.8 L 535.2,180.8 L 538.7,179.8 L 542.2,179.3 L 545.7,178.9 L 549.2,178.3 L 552.7,177.7 L 556.3,177.3 L 559.8,177.1 L 563.3,176.7 L 566.8,176.2 L 570.3,175.8 L 573.8,175.1 L 577.3,174.3 L 580.8,173.6 L 584.3,172.3 L 587.8,171.7 L 591.3,171.4 L 594.9,171.0 L 598.4,170.4 L 601.9,169.7 L 605.4,169.1 L 608.9,168.7 L 612.4,168.4 L 615.9,167.2 L 619.4,166.7 L 622.9,166.0 L 626.4,165.7 L 629.9,165.3 L 633.5,164.8 L 637.0,164.1 L 640.5,162.8 L 644.0,162.3 L 647.5,161.7 L 651.0,161.2 L 654.5,160.8 L 658.0,160.1 L 661.5,159.5 L 665.0,159.1 L 668.5,158.9 L 672.1,158.4 L 675.6,157.8 L 679.1,157.0 L 682.6,156.3 L 686.1,155.2 L 689.6,154.2 L 693.1,153.4 L 696.6,153.1 L 700.1,152.7 L 703.6,152.4 L 707.1,151.9 L 710.7,151.1 L 714.2,150.6 L 717.7,150.3 L 721.2,149.9 L 724.7,149.0 L 728.2,148.1 L 731.7,147.3 L 735.2,146.0 L 738.7,145.6 L 742.2,144.5 L 745.7,143.6 L 749.3,142.9 L 752.8,142.1 L 756.3,141.3 L 759.8,140.7 L 763.3,139.6 L 766.8,139.0 L 770.3,137.8 L 773.8,136.9 L 777.3,136.0 L 780.8,135.0 L 784.3,133.9 L 787.9,133.1 L 791.4,132.1 L 794.9,130.9 L 798.4,130.1 L 801.9,129.6 L 805.4,128.9 L 808.9,127.7 L 812.4,124.9 L 815.9,123.7 L 819.4,122.4 L 822.9,121.3 L 826.5,119.5 L 830.0,117.6 L 833.5,116.0 L 837.0,113.2 L 840.5,109.2 L 844.0,88.1 L 844.0,252 Z" fill="#cde2fb" fill-opacity="0.55"/>
<polyline points="72.0,251.4 75.5,250.9 79.0,250.5 82.5,250.1 86.0,249.7 89.5,249.3 93.1,249.0 96.6,248.4 100.1,247.9 103.6,247.5 107.1,247.3 110.6,246.9 114.1,246.5 117.6,246.2 121.1,245.6 124.6,245.3 128.1,245.0 131.7,244.6 135.2,244.3 138.7,244.1 142.2,243.8 145.7,243.3 149.2,242.9 152.7,242.5 156.2,242.0 159.7,241.7 163.2,241.1 166.7,240.5 170.3,239.9 173.8,239.4 177.3,239.0 180.8,238.5 184.3,237.9 187.8,237.5 191.3,237.2 194.8,236.8 198.3,236.3 201.8,235.8 205.3,235.4 208.9,235.0 212.4,234.7 215.9,234.1 219.4,233.8 222.9,233.2 226.4,232.3 229.9,231.7 233.4,231.1 236.9,230.4 240.4,229.8 243.9,229.5 247.5,229.2 251.0,228.9 254.5,228.4 258.0,228.2 261.5,227.8 265.0,227.0 268.5,226.0 272.0,225.3 275.5,224.7 279.0,224.2 282.5,223.7 286.1,223.1 289.6,222.2 293.1,221.0 296.6,220.2 300.1,219.5 303.6,218.9 307.1,218.6 310.6,218.3 314.1,217.5 317.6,216.8 321.1,216.4 324.7,215.9 328.2,215.4 331.7,215.0 335.2,214.4 338.7,213.8 342.2,213.3 345.7,212.8 349.2,212.4 352.7,211.9 356.2,211.4 359.7,211.1 363.3,210.8 366.8,210.5 370.3,210.3 373.8,210.0 377.3,209.8 380.8,209.4 384.3,209.2 387.8,208.9 391.3,208.6 394.8,208.2 398.3,207.9 401.9,207.5 405.4,206.5 408.9,204.6 412.4,204.0 415.9,203.5 419.4,203.0 422.9,202.6 426.4,201.8 429.9,200.8 433.4,198.6 436.9,198.0 440.5,197.2 444.0,196.5 447.5,195.8 451.0,195.1 454.5,194.8 458.0,194.1 461.5,193.3 465.0,192.9 468.5,192.1 472.0,191.3 475.5,190.8 479.1,190.2 482.6,189.3 486.1,188.9 489.6,188.4 493.1,187.9 496.6,187.3 500.1,186.5 503.6,186.2 507.1,185.7 510.6,185.2 514.1,185.0 517.7,184.7 521.2,184.4 524.7,183.4 528.2,183.0 531.7,181.8 535.2,180.8 538.7,179.8 542.2,179.3 545.7,178.9 549.2,178.3 552.7,177.7 556.3,177.3 559.8,177.1 563.3,176.7 566.8,176.2 570.3,175.8 573.8,175.1 577.3,174.3 580.8,173.6 584.3,172.3 587.8,171.7 591.3,171.4 594.9,171.0 598.4,170.4 601.9,169.7 605.4,169.1 608.9,168.7 612.4,168.4 615.9,167.2 619.4,166.7 622.9,166.0 626.4,165.7 629.9,165.3 633.5,164.8 637.0,164.1 640.5,162.8 644.0,162.3 647.5,161.7 651.0,161.2 654.5,160.8 658.0,160.1 661.5,159.5 665.0,159.1 668.5,158.9 672.1,158.4 675.6,157.8 679.1,157.0 682.6,156.3 686.1,155.2 689.6,154.2 693.1,153.4 696.6,153.1 700.1,152.7 703.6,152.4 707.1,151.9 710.7,151.1 714.2,150.6 717.7,150.3 721.2,149.9 724.7,149.0 728.2,148.1 731.7,147.3 735.2,146.0 738.7,145.6 742.2,144.5 745.7,143.6 749.3,142.9 752.8,142.1 756.3,141.3 759.8,140.7 763.3,139.6 766.8,139.0 770.3,137.8 773.8,136.9 777.3,136.0 780.8,135.0 784.3,133.9 787.9,133.1 791.4,132.1 794.9,130.9 798.4,130.1 801.9,129.6 805.4,128.9 808.9,127.7 812.4,124.9 815.9,123.7 819.4,122.4 822.9,121.3 826.5,119.5 830.0,117.6 833.5,116.0 837.0,113.2 840.5,109.2 844.0,88.1" fill="none" stroke="#2a78d6" stroke-width="2"/>
<rect x="72.00" y="52" width="3.49" height="200" fill="transparent"><title>11:19 · +1,040 → cum 1,040</title></rect>
<rect x="75.49" y="52" width="3.49" height="200" fill="transparent"><title>11:20 · +955 → cum 1,995</title></rect>
<rect x="78.99" y="52" width="3.49" height="200" fill="transparent"><title>11:21 · +725 → cum 2,720</title></rect>
<rect x="82.48" y="52" width="3.49" height="200" fill="transparent"><title>11:22 · +851 → cum 3,571</title></rect>
<rect x="85.97" y="52" width="3.49" height="200" fill="transparent"><title>11:23 · +653 → cum 4,224</title></rect>
<rect x="89.47" y="52" width="3.49" height="200" fill="transparent"><title>11:24 · +790 → cum 5,014</title></rect>
<rect x="92.96" y="52" width="3.49" height="200" fill="transparent"><title>11:25 · +692 → cum 5,706</title></rect>
<rect x="96.45" y="52" width="3.49" height="200" fill="transparent"><title>11:26 · +1,105 → cum 6,811</title></rect>
<rect x="99.95" y="52" width="3.49" height="200" fill="transparent"><title>11:27 · +875 → cum 7,686</title></rect>
<rect x="103.44" y="52" width="3.49" height="200" fill="transparent"><title>11:28 · +736 → cum 8,422</title></rect>
<rect x="106.93" y="52" width="3.49" height="200" fill="transparent"><title>11:29 · +454 → cum 8,876</title></rect>
<rect x="110.43" y="52" width="3.49" height="200" fill="transparent"><title>11:30 · +695 → cum 9,571</title></rect>
<rect x="113.92" y="52" width="3.49" height="200" fill="transparent"><title>11:31 · +710 → cum 10,281</title></rect>
<rect x="117.41" y="52" width="3.49" height="200" fill="transparent"><title>11:32 · +690 → cum 10,971</title></rect>
<rect x="120.90" y="52" width="3.49" height="200" fill="transparent"><title>11:33 · +1,105 → cum 12,076</title></rect>
<rect x="124.40" y="52" width="3.49" height="200" fill="transparent"><title>11:34 · +548 → cum 12,624</title></rect>
<rect x="127.89" y="52" width="3.49" height="200" fill="transparent"><title>11:35 · +538 → cum 13,162</title></rect>
<rect x="131.38" y="52" width="3.49" height="200" fill="transparent"><title>11:36 · +666 → cum 13,828</title></rect>
<rect x="134.88" y="52" width="3.49" height="200" fill="transparent"><title>11:37 · +591 → cum 14,419</title></rect>
<rect x="138.37" y="52" width="3.49" height="200" fill="transparent"><title>11:38 · +442 → cum 14,861</title></rect>
<rect x="141.86" y="52" width="3.49" height="200" fill="transparent"><title>11:39 · +450 → cum 15,311</title></rect>
<rect x="145.36" y="52" width="3.49" height="200" fill="transparent"><title>11:40 · +955 → cum 16,266</title></rect>
<rect x="148.85" y="52" width="3.49" height="200" fill="transparent"><title>11:41 · +769 → cum 17,035</title></rect>
<rect x="152.34" y="52" width="3.49" height="200" fill="transparent"><title>11:42 · +857 → cum 17,892</title></rect>
<rect x="155.84" y="52" width="3.49" height="200" fill="transparent"><title>11:43 · +839 → cum 18,731</title></rect>
<rect x="159.33" y="52" width="3.49" height="200" fill="transparent"><title>11:44 · +643 → cum 19,374</title></rect>
<rect x="162.82" y="52" width="3.49" height="200" fill="transparent"><title>11:45 · +1,038 → cum 20,412</title></rect>
<rect x="166.32" y="52" width="3.49" height="200" fill="transparent"><title>11:46 · +1,069 → cum 21,481</title></rect>
<rect x="169.81" y="52" width="3.49" height="200" fill="transparent"><title>11:47 · +1,181 → cum 22,662</title></rect>
<rect x="173.30" y="52" width="3.49" height="200" fill="transparent"><title>11:48 · +966 → cum 23,628</title></rect>
<rect x="176.80" y="52" width="3.49" height="200" fill="transparent"><title>11:49 · +680 → cum 24,308</title></rect>
<rect x="180.29" y="52" width="3.49" height="200" fill="transparent"><title>11:50 · +980 → cum 25,288</title></rect>
<rect x="183.78" y="52" width="3.49" height="200" fill="transparent"><title>11:51 · +1,080 → cum 26,368</title></rect>
<rect x="187.28" y="52" width="3.49" height="200" fill="transparent"><title>11:52 · +827 → cum 27,195</title></rect>
<rect x="190.77" y="52" width="3.49" height="200" fill="transparent"><title>11:53 · +637 → cum 27,832</title></rect>
<rect x="194.26" y="52" width="3.49" height="200" fill="transparent"><title>11:54 · +688 → cum 28,520</title></rect>
<rect x="197.76" y="52" width="3.49" height="200" fill="transparent"><title>11:55 · +1,003 → cum 29,523</title></rect>
<rect x="201.25" y="52" width="3.49" height="200" fill="transparent"><title>11:56 · +823 → cum 30,346</title></rect>
<rect x="204.74" y="52" width="3.49" height="200" fill="transparent"><title>11:57 · +784 → cum 31,130</title></rect>
<rect x="208.24" y="52" width="3.49" height="200" fill="transparent"><title>11:58 · +680 → cum 31,810</title></rect>
<rect x="211.73" y="52" width="3.49" height="200" fill="transparent"><title>11:59 · +588 → cum 32,398</title></rect>
<rect x="215.22" y="52" width="3.49" height="200" fill="transparent"><title>12:00 · +1,199 → cum 33,597</title></rect>
<rect x="218.71" y="52" width="3.49" height="200" fill="transparent"><title>12:01 · +617 → cum 34,214</title></rect>
<rect x="222.21" y="52" width="3.49" height="200" fill="transparent"><title>12:02 · +1,001 → cum 35,215</title></rect>
<rect x="225.70" y="52" width="3.49" height="200" fill="transparent"><title>12:03 · +1,710 → cum 36,925</title></rect>
<rect x="229.19" y="52" width="3.49" height="200" fill="transparent"><title>12:04 · +1,058 → cum 37,983</title></rect>
<rect x="232.69" y="52" width="3.49" height="200" fill="transparent"><title>12:05 · +1,238 → cum 39,221</title></rect>
<rect x="236.18" y="52" width="3.49" height="200" fill="transparent"><title>12:06 · +1,379 → cum 40,600</title></rect>
<rect x="239.67" y="52" width="3.49" height="200" fill="transparent"><title>12:07 · +1,044 → cum 41,644</title></rect>
<rect x="243.17" y="52" width="3.49" height="200" fill="transparent"><title>12:08 · +563 → cum 42,207</title></rect>
<rect x="246.66" y="52" width="3.49" height="200" fill="transparent"><title>12:09 · +527 → cum 42,734</title></rect>
<rect x="250.15" y="52" width="3.49" height="200" fill="transparent"><title>12:10 · +591 → cum 43,325</title></rect>
<rect x="253.65" y="52" width="3.49" height="200" fill="transparent"><title>12:11 · +872 → cum 44,197</title></rect>
<rect x="257.14" y="52" width="3.49" height="200" fill="transparent"><title>12:12 · +493 → cum 44,690</title></rect>
<rect x="260.63" y="52" width="3.49" height="200" fill="transparent"><title>12:13 · +769 → cum 45,459</title></rect>
<rect x="264.13" y="52" width="3.49" height="200" fill="transparent"><title>12:14 · +1,455 → cum 46,914</title></rect>
<rect x="267.62" y="52" width="3.49" height="200" fill="transparent"><title>12:15 · +1,822 → cum 48,736</title></rect>
<rect x="271.11" y="52" width="3.49" height="200" fill="transparent"><title>12:16 · +1,422 → cum 50,158</title></rect>
<rect x="274.61" y="52" width="3.49" height="200" fill="transparent"><title>12:17 · +991 → cum 51,149</title></rect>
<rect x="278.10" y="52" width="3.49" height="200" fill="transparent"><title>12:18 · +903 → cum 52,052</title></rect>
<rect x="281.59" y="52" width="3.49" height="200" fill="transparent"><title>12:19 · +1,072 → cum 53,124</title></rect>
<rect x="285.09" y="52" width="3.49" height="200" fill="transparent"><title>12:20 · +1,129 → cum 54,253</title></rect>
<rect x="288.58" y="52" width="3.49" height="200" fill="transparent"><title>12:21 · +1,596 → cum 55,849</title></rect>
<rect x="292.07" y="52" width="3.49" height="200" fill="transparent"><title>12:22 · +2,313 → cum 58,162</title></rect>
<rect x="295.57" y="52" width="3.49" height="200" fill="transparent"><title>12:23 · +1,492 → cum 59,654</title></rect>
<rect x="299.06" y="52" width="3.49" height="200" fill="transparent"><title>12:24 · +1,216 → cum 60,870</title></rect>
<rect x="302.55" y="52" width="3.49" height="200" fill="transparent"><title>12:25 · +1,138 → cum 62,008</title></rect>
<rect x="306.05" y="52" width="3.49" height="200" fill="transparent"><title>12:26 · +667 → cum 62,675</title></rect>
<rect x="309.54" y="52" width="3.49" height="200" fill="transparent"><title>12:27 · +545 → cum 63,220</title></rect>
<rect x="313.03" y="52" width="3.49" height="200" fill="transparent"><title>12:28 · +1,425 → cum 64,645</title></rect>
<rect x="316.52" y="52" width="3.49" height="200" fill="transparent"><title>12:29 · +1,284 → cum 65,929</title></rect>
<rect x="320.02" y="52" width="3.49" height="200" fill="transparent"><title>12:30 · +796 → cum 66,725</title></rect>
<rect x="323.51" y="52" width="3.49" height="200" fill="transparent"><title>12:31 · +952 → cum 67,677</title></rect>
<rect x="327.00" y="52" width="3.49" height="200" fill="transparent"><title>12:32 · +883 → cum 68,560</title></rect>
<rect x="330.50" y="52" width="3.49" height="200" fill="transparent"><title>12:33 · +918 → cum 69,478</title></rect>
<rect x="333.99" y="52" width="3.49" height="200" fill="transparent"><title>12:34 · +989 → cum 70,467</title></rect>
<rect x="337.48" y="52" width="3.49" height="200" fill="transparent"><title>12:35 · +1,218 → cum 71,685</title></rect>
<rect x="340.98" y="52" width="3.49" height="200" fill="transparent"><title>12:36 · +896 → cum 72,581</title></rect>
<rect x="344.47" y="52" width="3.49" height="200" fill="transparent"><title>12:37 · +971 → cum 73,552</title></rect>
<rect x="347.96" y="52" width="3.49" height="200" fill="transparent"><title>12:38 · +789 → cum 74,341</title></rect>
<rect x="351.46" y="52" width="3.49" height="200" fill="transparent"><title>12:39 · +964 → cum 75,305</title></rect>
<rect x="354.95" y="52" width="3.49" height="200" fill="transparent"><title>12:40 · +779 → cum 76,084</title></rect>
<rect x="358.44" y="52" width="3.49" height="200" fill="transparent"><title>12:41 · +665 → cum 76,749</title></rect>
<rect x="361.94" y="52" width="3.49" height="200" fill="transparent"><title>12:42 · +530 → cum 77,279</title></rect>
<rect x="365.43" y="52" width="3.49" height="200" fill="transparent"><title>12:43 · +625 → cum 77,904</title></rect>
<rect x="368.92" y="52" width="3.49" height="200" fill="transparent"><title>12:44 · +374 → cum 78,278</title></rect>
<rect x="372.42" y="52" width="3.49" height="200" fill="transparent"><title>12:45 · +409 → cum 78,687</title></rect>
<rect x="375.91" y="52" width="3.49" height="200" fill="transparent"><title>12:46 · +524 → cum 79,211</title></rect>
<rect x="379.40" y="52" width="3.49" height="200" fill="transparent"><title>12:47 · +654 → cum 79,865</title></rect>
<rect x="382.90" y="52" width="3.49" height="200" fill="transparent"><title>12:48 · +497 → cum 80,362</title></rect>
<rect x="386.39" y="52" width="3.49" height="200" fill="transparent"><title>12:49 · +482 → cum 80,844</title></rect>
<rect x="389.88" y="52" width="3.49" height="200" fill="transparent"><title>12:50 · +649 → cum 81,493</title></rect>
<rect x="393.38" y="52" width="3.49" height="200" fill="transparent"><title>12:51 · +583 → cum 82,076</title></rect>
<rect x="396.87" y="52" width="3.49" height="200" fill="transparent"><title>12:52 · +570 → cum 82,646</title></rect>
<rect x="400.36" y="52" width="3.49" height="200" fill="transparent"><title>12:53 · +867 → cum 83,513</title></rect>
<rect x="403.86" y="52" width="3.49" height="200" fill="transparent"><title>12:54 · +1,904 → cum 85,417</title></rect>
<rect x="407.35" y="52" width="3.49" height="200" fill="transparent"><title>12:55 · +3,413 → cum 88,830</title></rect>
<rect x="410.84" y="52" width="3.49" height="200" fill="transparent"><title>12:56 · +1,155 → cum 89,985</title></rect>
<rect x="414.33" y="52" width="3.49" height="200" fill="transparent"><title>12:57 · +939 → cum 90,924</title></rect>
<rect x="417.83" y="52" width="3.49" height="200" fill="transparent"><title>12:58 · +989 → cum 91,913</title></rect>
<rect x="421.32" y="52" width="3.49" height="200" fill="transparent"><title>12:59 · +710 → cum 92,623</title></rect>
<rect x="424.81" y="52" width="3.49" height="200" fill="transparent"><title>13:00 · +1,475 → cum 94,098</title></rect>
<rect x="428.31" y="52" width="3.49" height="200" fill="transparent"><title>13:01 · +1,927 → cum 96,025</title></rect>
<rect x="431.80" y="52" width="3.49" height="200" fill="transparent"><title>13:02 · +4,134 → cum 100,159</title></rect>
<rect x="435.29" y="52" width="3.49" height="200" fill="transparent"><title>13:03 · +1,218 → cum 101,377</title></rect>
<rect x="438.79" y="52" width="3.49" height="200" fill="transparent"><title>13:04 · +1,402 → cum 102,779</title></rect>
<rect x="442.28" y="52" width="3.49" height="200" fill="transparent"><title>13:05 · +1,370 → cum 104,149</title></rect>
<rect x="445.77" y="52" width="3.49" height="200" fill="transparent"><title>13:06 · +1,183 → cum 105,332</title></rect>
<rect x="449.27" y="52" width="3.49" height="200" fill="transparent"><title>13:07 · +1,300 → cum 106,632</title></rect>
<rect x="452.76" y="52" width="3.49" height="200" fill="transparent"><title>13:08 · +741 → cum 107,373</title></rect>
<rect x="456.25" y="52" width="3.49" height="200" fill="transparent"><title>13:09 · +1,194 → cum 108,567</title></rect>
<rect x="459.75" y="52" width="3.49" height="200" fill="transparent"><title>13:10 · +1,455 → cum 110,022</title></rect>
<rect x="463.24" y="52" width="3.49" height="200" fill="transparent"><title>13:11 · +868 → cum 110,890</title></rect>
<rect x="466.73" y="52" width="3.49" height="200" fill="transparent"><title>13:12 · +1,394 → cum 112,284</title></rect>
<rect x="470.23" y="52" width="3.49" height="200" fill="transparent"><title>13:13 · +1,615 → cum 113,899</title></rect>
<rect x="473.72" y="52" width="3.49" height="200" fill="transparent"><title>13:14 · +974 → cum 114,873</title></rect>
<rect x="477.21" y="52" width="3.49" height="200" fill="transparent"><title>13:15 · +1,066 → cum 115,939</title></rect>
<rect x="480.71" y="52" width="3.49" height="200" fill="transparent"><title>13:16 · +1,628 → cum 117,567</title></rect>
<rect x="484.20" y="52" width="3.49" height="200" fill="transparent"><title>13:17 · +757 → cum 118,324</title></rect>
<rect x="487.69" y="52" width="3.49" height="200" fill="transparent"><title>13:18 · +1,015 → cum 119,339</title></rect>
<rect x="491.19" y="52" width="3.49" height="200" fill="transparent"><title>13:19 · +976 → cum 120,315</title></rect>
<rect x="494.68" y="52" width="3.49" height="200" fill="transparent"><title>13:20 · +1,031 → cum 121,346</title></rect>
<rect x="498.17" y="52" width="3.49" height="200" fill="transparent"><title>13:21 · +1,424 → cum 122,770</title></rect>
<rect x="501.67" y="52" width="3.49" height="200" fill="transparent"><title>13:22 · +684 → cum 123,454</title></rect>
<rect x="505.16" y="52" width="3.49" height="200" fill="transparent"><title>13:23 · +854 → cum 124,308</title></rect>
<rect x="508.65" y="52" width="3.49" height="200" fill="transparent"><title>13:24 · +993 → cum 125,301</title></rect>
<rect x="512.14" y="52" width="3.49" height="200" fill="transparent"><title>13:25 · +329 → cum 125,630</title></rect>
<rect x="515.64" y="52" width="3.49" height="200" fill="transparent"><title>13:26 · +584 → cum 126,214</title></rect>
<rect x="519.13" y="52" width="3.49" height="200" fill="transparent"><title>13:27 · +562 → cum 126,776</title></rect>
<rect x="522.62" y="52" width="3.49" height="200" fill="transparent"><title>13:28 · +1,800 → cum 128,576</title></rect>
<rect x="526.12" y="52" width="3.49" height="200" fill="transparent"><title>13:29 · +828 → cum 129,404</title></rect>
<rect x="529.61" y="52" width="3.49" height="200" fill="transparent"><title>13:30 · +2,258 → cum 131,662</title></rect>
<rect x="533.10" y="52" width="3.49" height="200" fill="transparent"><title>13:31 · +1,802 → cum 133,464</title></rect>
<rect x="536.60" y="52" width="3.49" height="200" fill="transparent"><title>13:32 · +1,922 → cum 135,386</title></rect>
<rect x="540.09" y="52" width="3.49" height="200" fill="transparent"><title>13:33 · +949 → cum 136,335</title></rect>
<rect x="543.58" y="52" width="3.49" height="200" fill="transparent"><title>13:34 · +726 → cum 137,061</title></rect>
<rect x="547.08" y="52" width="3.49" height="200" fill="transparent"><title>13:35 · +1,248 → cum 138,309</title></rect>
<rect x="550.57" y="52" width="3.49" height="200" fill="transparent"><title>13:36 · +1,130 → cum 139,439</title></rect>
<rect x="554.06" y="52" width="3.49" height="200" fill="transparent"><title>13:37 · +606 → cum 140,045</title></rect>
<rect x="557.56" y="52" width="3.49" height="200" fill="transparent"><title>13:38 · +485 → cum 140,530</title></rect>
<rect x="561.05" y="52" width="3.49" height="200" fill="transparent"><title>13:39 · +778 → cum 141,308</title></rect>
<rect x="564.54" y="52" width="3.49" height="200" fill="transparent"><title>13:40 · +786 → cum 142,094</title></rect>
<rect x="568.04" y="52" width="3.49" height="200" fill="transparent"><title>13:41 · +774 → cum 142,868</title></rect>
<rect x="571.53" y="52" width="3.49" height="200" fill="transparent"><title>13:42 · +1,352 → cum 144,220</title></rect>
<rect x="575.02" y="52" width="3.49" height="200" fill="transparent"><title>13:43 · +1,444 → cum 145,664</title></rect>
<rect x="578.52" y="52" width="3.49" height="200" fill="transparent"><title>13:44 · +1,311 → cum 146,975</title></rect>
<rect x="582.01" y="52" width="3.49" height="200" fill="transparent"><title>13:45 · +2,522 → cum 149,497</title></rect>
<rect x="585.50" y="52" width="3.49" height="200" fill="transparent"><title>13:46 · +1,086 → cum 150,583</title></rect>
<rect x="589.00" y="52" width="3.49" height="200" fill="transparent"><title>13:47 · +543 → cum 151,126</title></rect>
<rect x="592.49" y="52" width="3.49" height="200" fill="transparent"><title>13:48 · +814 → cum 151,940</title></rect>
<rect x="595.98" y="52" width="3.49" height="200" fill="transparent"><title>13:49 · +1,041 → cum 152,981</title></rect>
<rect x="599.48" y="52" width="3.49" height="200" fill="transparent"><title>13:50 · +1,471 → cum 154,452</title></rect>
<rect x="602.97" y="52" width="3.49" height="200" fill="transparent"><title>13:51 · +1,001 → cum 155,453</title></rect>
<rect x="606.46" y="52" width="3.49" height="200" fill="transparent"><title>13:52 · +790 → cum 156,243</title></rect>
<rect x="609.95" y="52" width="3.49" height="200" fill="transparent"><title>13:53 · +634 → cum 156,877</title></rect>
<rect x="613.45" y="52" width="3.49" height="200" fill="transparent"><title>13:54 · +2,082 → cum 158,959</title></rect>
<rect x="616.94" y="52" width="3.49" height="200" fill="transparent"><title>13:55 · +1,115 → cum 160,074</title></rect>
<rect x="620.43" y="52" width="3.49" height="200" fill="transparent"><title>13:56 · +1,298 → cum 161,372</title></rect>
<rect x="623.93" y="52" width="3.49" height="200" fill="transparent"><title>13:57 · +522 → cum 161,894</title></rect>
<rect x="627.42" y="52" width="3.49" height="200" fill="transparent"><title>13:58 · +719 → cum 162,613</title></rect>
<rect x="630.91" y="52" width="3.49" height="200" fill="transparent"><title>13:59 · +955 → cum 163,568</title></rect>
<rect x="634.41" y="52" width="3.49" height="200" fill="transparent"><title>14:00 · +1,278 → cum 164,846</title></rect>
<rect x="637.90" y="52" width="3.49" height="200" fill="transparent"><title>14:01 · +2,475 → cum 167,321</title></rect>
<rect x="641.39" y="52" width="3.49" height="200" fill="transparent"><title>14:02 · +989 → cum 168,310</title></rect>
<rect x="644.89" y="52" width="3.49" height="200" fill="transparent"><title>14:03 · +1,083 → cum 169,393</title></rect>
<rect x="648.38" y="52" width="3.49" height="200" fill="transparent"><title>14:04 · +912 → cum 170,305</title></rect>
<rect x="651.87" y="52" width="3.49" height="200" fill="transparent"><title>14:05 · +745 → cum 171,050</title></rect>
<rect x="655.37" y="52" width="3.49" height="200" fill="transparent"><title>14:06 · +1,277 → cum 172,327</title></rect>
<rect x="658.86" y="52" width="3.49" height="200" fill="transparent"><title>14:07 · +1,147 → cum 173,474</title></rect>
<rect x="662.35" y="52" width="3.49" height="200" fill="transparent"><title>14:08 · +687 → cum 174,161</title></rect>
<rect x="665.85" y="52" width="3.49" height="200" fill="transparent"><title>14:09 · +405 → cum 174,566</title></rect>
<rect x="669.34" y="52" width="3.49" height="200" fill="transparent"><title>14:10 · +997 → cum 175,563</title></rect>
<rect x="672.83" y="52" width="3.49" height="200" fill="transparent"><title>14:11 · +1,156 → cum 176,719</title></rect>
<rect x="676.33" y="52" width="3.49" height="200" fill="transparent"><title>14:12 · +1,379 → cum 178,098</title></rect>
<rect x="679.82" y="52" width="3.49" height="200" fill="transparent"><title>14:13 · +1,382 → cum 179,480</title></rect>
<rect x="683.31" y="52" width="3.49" height="200" fill="transparent"><title>14:14 · +2,001 → cum 181,481</title></rect>
<rect x="686.81" y="52" width="3.49" height="200" fill="transparent"><title>14:15 · +1,926 → cum 183,407</title></rect>
<rect x="690.30" y="52" width="3.49" height="200" fill="transparent"><title>14:16 · +1,448 → cum 184,855</title></rect>
<rect x="693.79" y="52" width="3.49" height="200" fill="transparent"><title>14:17 · +734 → cum 185,589</title></rect>
<rect x="697.29" y="52" width="3.49" height="200" fill="transparent"><title>14:18 · +581 → cum 186,170</title></rect>
<rect x="700.78" y="52" width="3.49" height="200" fill="transparent"><title>14:19 · +734 → cum 186,904</title></rect>
<rect x="704.27" y="52" width="3.49" height="200" fill="transparent"><title>14:20 · +900 → cum 187,804</title></rect>
<rect x="707.76" y="52" width="3.49" height="200" fill="transparent"><title>14:21 · +1,520 → cum 189,324</title></rect>
<rect x="711.26" y="52" width="3.49" height="200" fill="transparent"><title>14:22 · +819 → cum 190,143</title></rect>
<rect x="714.75" y="52" width="3.49" height="200" fill="transparent"><title>14:23 · +661 → cum 190,804</title></rect>
<rect x="718.24" y="52" width="3.49" height="200" fill="transparent"><title>14:24 · +687 → cum 191,491</title></rect>
<rect x="721.74" y="52" width="3.49" height="200" fill="transparent"><title>14:25 · +1,759 → cum 193,250</title></rect>
<rect x="725.23" y="52" width="3.49" height="200" fill="transparent"><title>14:26 · +1,632 → cum 194,882</title></rect>
<rect x="728.72" y="52" width="3.49" height="200" fill="transparent"><title>14:27 · +1,562 → cum 196,444</title></rect>
<rect x="732.22" y="52" width="3.49" height="200" fill="transparent"><title>14:28 · +2,412 → cum 198,856</title></rect>
<rect x="735.71" y="52" width="3.49" height="200" fill="transparent"><title>14:29 · +774 → cum 199,630</title></rect>
<rect x="739.20" y="52" width="3.49" height="200" fill="transparent"><title>14:30 · +1,997 → cum 201,627</title></rect>
<rect x="742.70" y="52" width="3.49" height="200" fill="transparent"><title>14:31 · +1,672 → cum 203,299</title></rect>
<rect x="746.19" y="52" width="3.49" height="200" fill="transparent"><title>14:32 · +1,377 → cum 204,676</title></rect>
<rect x="749.68" y="52" width="3.49" height="200" fill="transparent"><title>14:33 · +1,504 → cum 206,180</title></rect>
<rect x="753.18" y="52" width="3.49" height="200" fill="transparent"><title>14:34 · +1,470 → cum 207,650</title></rect>
<rect x="756.67" y="52" width="3.49" height="200" fill="transparent"><title>14:35 · +1,042 → cum 208,692</title></rect>
<rect x="760.16" y="52" width="3.49" height="200" fill="transparent"><title>14:36 · +2,060 → cum 210,752</title></rect>
<rect x="763.66" y="52" width="3.49" height="200" fill="transparent"><title>14:37 · +1,193 → cum 211,945</title></rect>
<rect x="767.15" y="52" width="3.49" height="200" fill="transparent"><title>14:38 · +2,254 → cum 214,199</title></rect>
<rect x="770.64" y="52" width="3.49" height="200" fill="transparent"><title>14:39 · +1,667 → cum 215,866</title></rect>
<rect x="774.14" y="52" width="3.49" height="200" fill="transparent"><title>14:40 · +1,776 → cum 217,642</title></rect>
<rect x="777.63" y="52" width="3.49" height="200" fill="transparent"><title>14:41 · +1,774 → cum 219,416</title></rect>
<rect x="781.12" y="52" width="3.49" height="200" fill="transparent"><title>14:42 · +2,054 → cum 221,470</title></rect>
<rect x="784.62" y="52" width="3.49" height="200" fill="transparent"><title>14:43 · +1,544 → cum 223,014</title></rect>
<rect x="788.11" y="52" width="3.49" height="200" fill="transparent"><title>14:44 · +1,903 → cum 224,917</title></rect>
<rect x="791.60" y="52" width="3.49" height="200" fill="transparent"><title>14:45 · +2,192 → cum 227,109</title></rect>
<rect x="795.10" y="52" width="3.49" height="200" fill="transparent"><title>14:46 · +1,530 → cum 228,639</title></rect>
<rect x="798.59" y="52" width="3.49" height="200" fill="transparent"><title>14:47 · +951 → cum 229,590</title></rect>
<rect x="802.08" y="52" width="3.49" height="200" fill="transparent"><title>14:48 · +1,385 → cum 230,975</title></rect>
<rect x="805.57" y="52" width="3.49" height="200" fill="transparent"><title>14:49 · +2,097 → cum 233,072</title></rect>
<rect x="809.07" y="52" width="3.49" height="200" fill="transparent"><title>14:50 · +5,394 → cum 238,466</title></rect>
<rect x="812.56" y="52" width="3.49" height="200" fill="transparent"><title>14:51 · +2,096 → cum 240,562</title></rect>
<rect x="816.05" y="52" width="3.49" height="200" fill="transparent"><title>14:52 · +2,441 → cum 243,003</title></rect>
<rect x="819.55" y="52" width="3.49" height="200" fill="transparent"><title>14:53 · +2,144 → cum 245,147</title></rect>
<rect x="823.04" y="52" width="3.49" height="200" fill="transparent"><title>14:54 · +3,376 → cum 248,523</title></rect>
<rect x="826.53" y="52" width="3.49" height="200" fill="transparent"><title>14:55 · +3,601 → cum 252,124</title></rect>
<rect x="830.03" y="52" width="3.49" height="200" fill="transparent"><title>14:56 · +2,877 → cum 255,001</title></rect>
<rect x="833.52" y="52" width="3.49" height="200" fill="transparent"><title>14:57 · +5,246 → cum 260,247</title></rect>
<rect x="837.01" y="52" width="3.49" height="200" fill="transparent"><title>14:58 · +7,538 → cum 267,785</title></rect>
<rect x="840.51" y="52" width="3.49" height="200" fill="transparent"><title>14:59 · +39,694 → cum 307,479</title></rect>
<line x1="72" y1="197.3" x2="844" y2="197.3" stroke="#898781" stroke-width="1.5" stroke-dasharray="6 4"/>
<text x="78" y="191.3" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781">median full-RTH leg — 103k</text>
<line x1="72" y1="165.0" x2="844" y2="165.0" stroke="#898781" stroke-width="1.5" stroke-dasharray="6 4"/>
<text x="78" y="159.0" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781">7/22&#8217;s own morning leg-grind, whole — 163k</text>
<circle cx="844.0" cy="88.1" r="5" fill="#2a78d6"/>
<text x="840" y="64.1" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" font-weight="600" fill="#222222" text-anchor="end">307,479 contracts</text>
<text x="840" y="80.1" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="end">89.7th percentile of the 213 full-RTH legs → F1 at leg scale</text>
<text x="110.6" y="270" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">11:30</text>
<text x="321.1" y="270" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">12:30</text>
<text x="531.7" y="270" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">13:30</text>
<text x="742.2" y="270" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">14:30</text>
<text x="844.0" y="270" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#898781" text-anchor="middle">15:00</text>
</svg>

*Figure 2 — the paradox resolved: no single minute is loud, but the sum passes the whole morning leg-grind and lands in the corpus&#8217;s top decile of full-RTH legs. Leg percentiles rank against coverage-matched legs only (window truncation biases leg statistics).*
<!-- fig:722-paradox END -->

One discrimination from this stack matters more than any other, and it has a
fencing name: at a contested price, a thrust meets a parry. If the **parry
fails** — conviction resumes through it — you watched a **micro-stall**, a
pause inside a living leg. If the **parry holds** and force turns, you
watched a **stall-stage**, and the leg is dying into a possible trap. *In the
moment the two are indistinguishable.* The next atoms decide. Sitting with
that ambiguity — rather than resolving it prematurely — is the discipline the
whole grade-band system exists to train.

## Essay V — LIVE and HINDSIGHT: your seat

**The one idea:** every measurement in this document is stamped LIVE or
HINDSIGHT, and the stamp defines your job.

**LIVE** — knowable in the minute: raw atom fields, the four stages, every
primitive, every confirmation-event. **HINDSIGHT** — computable only after:
all percentiles (they rank against the *completed* day), all cells and
grade-bands, all leg boundaries (a pivot exists only after the retracement
proves it), all archetypes, the day-sequence.

The system's two strongest discoveries are both hindsight, and honestly
labeled. First: every confirmation lands inside some stroke of the zigzag —
its **host-leg**. A buy call fired inside a rising host-leg wins its scoring
race (±5 first-touch, 30 minutes) 66% of the time; fired inside a falling
one — a bottom-call made mid-drop — it wins 19%. Second, the
**V-signature** — a deep flush-leg answered by a confirmation-event
within minutes — wins 77.5% versus a 46.9% base. Neither is a live entry
rule yet; turning them live (developing percentiles, provisional pivots) is
open engineering, and until it ships, they are how the tape gets *graded*,
not how it gets *traded*.

Which is the seat, stated one last time: deterministic code watches every
minute; an agent switches on where it counts; **hindsight is the authority on
what was correct; you are the authority on risk** — the final call on every
trade and every size. This vocabulary's whole purpose is to make what the
watchers tell you *unambiguous* at the moment that call is yours.
