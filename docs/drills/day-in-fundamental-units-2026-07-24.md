# The Day in Fundamental Units — Friday 2026-07-24

**Bead:** st-4wd · **Form:** measured narrative, sibling of the 2026-07-22 account —
every number below is pulled from `data/measurement/moves/{atoms,moves}.jsonl`
(run `20260728T123632Z`: 390 atoms, 7 legs, day_type `b`, coverage rth), the
recognizer record `data/measurement/replay/signals_2026-07-24.jsonl` (run
`20260731T042819834897Z-7eb5177`, 193 events), the graded confirmations in
`data/measurement/acuity-run2-confirmations.jsonl` (run `20260727T054148Z`, 9 rows),
or — for the prologue and nothing else — the Mancini letters of 07-23 and 07-24,
clearly attributed. Nothing is remembered or embellished. Corpus norms cite the
taxonomy (`docs/measurement/orderflow-fundamental-units.md`, Draft 2), not the
lexicon's stale figures. **Vocabulary:** terms appear **bold** on first use; every
label carries its grade-band, per `docs/lexicon/lexicon.yaml`.

**Coverage note, before anything:** the 2026-07-24 corpus is exactly RTH,
08:30:00–15:00:00 CT. Unlike 7/22 there is no pre-market tape — and none is
needed. The day's marquee Failed Breakdown printed *inside* coverage. The
overnight story below is letter-attested, not measured, and says so.

---

## Prologue — before the tape (letter-attested, not measured)

Everything in this section is Mancini's account, not ours. The 07-23 plan letter
laid the map for Friday: supports "7438 (major), 7429, 7424, 7418, 7412 (major)";
resistances "7447 (major), 7459, 7464, 7474 (major)" up through "7506 (major)."
The 07-24 recap letter tells the overnight: ES chopped through the evening, ran
to 7464 — his first target up — by 3:45AM ET, and set "a clear shelf of lows
set at 7438 between midnight at 3am" [sic]. Then, in his words: "At 945AM
[ET; 08:45 CT], ES sold off down to 7432... ES flushed and recovered a clear
shelf of lows set at 7438... We recovered this shelf around 10:05AM [09:05 CT]
and ripped." Elsewhere in the same letter the elevator drop is "from 7465 down
to 7434" and the recovery "ripped to 7490+." The letter disagrees with itself
by two points on the low; the measured record (below) says the day's low was
7431.5. Keep the shape in mind — shelf lost, low flushed, shelf recovered,
rip — because this time the whole thing happens on film.

## Act I — the Failed Breakdown, on film this time (08:30 → 10:16)

The first **atom** — one clock minute, the smallest unit we grade — opens loud:
12,590 contracts (**effort**, 99.5th percentile of the day) for +2.25 net
(**effect**, 72.8th) — **F1 conviction** in the **solid grade-band** (0.456). The
second minute is a **probe-atom** and a **doji-atom** at once: 7,987 contracts,
**travel-ratio** 0.00 — a full round trip inside the minute — **F2 absorption**
in the **strong grade-band** (0.872). Two minutes in, the tape is already fighting.

The recognizer — one tier below, on 2,000-trade bars — is working the 7447
plan-level. Its first engagement runs the full four stages: **flush-stage** 08:40:06,
**flip-stage** 08:42:34, **stall-stage** 08:48:07, and a **confirmation-event** at
08:49:23 (confidence 0.8). Sixty-six seconds later the market runs it over. At
08:50:28 a **sweep-print** takes nine book levels at once (7450.00 → 7444.25,
206 contracts), and the elevator arrives: the 08:50 atom prints −8.50 on 7,139
contracts (97.9th / 99.2nd, F1 strong-band 0.958), 08:51 adds −6.75 (F1
strong-band 0.934).
Summing atom nets, the tape drops 23.25 points between the 08:49 local high and
the 08:59 trough. The recognizer opens a second 7447 engagement into the hole
(08:50:28) and later kills it — invalidated 09:00:27, no reclaim.

At the bottom the record shows the fight in book-level detail. The 08:56:52
**absorption-read**: buyers threw 236 contracts at the 7436.50 ask, got refilled
3× — "absorbed, level broke." Three **delta-divergence** reads stamp the lows —
new swing lows 7434.0 (08:57:07) and 7435.0 (08:59:26, 09:05:03) on weaker
aggression each time, the exhaustion tell. The day's low, 7431.5 (RunMeta), is
touched inside 08:58–09:13: the graded 08:58 entry's 15-minute adverse excursion
is exactly 8.0 points from 7439.5. That is the letter's "sold off down to 7432,"
measured. Note the clock, honestly: the letter says 9:45AM ET (08:45 CT); the
measured elevator minutes are 08:50–08:59 CT.

Then the recovery the letter calls the 10:05AM [ET] Failed Breakdown. The 09:00
atom prints +6.50 (F1 strong-band 0.898), 09:08 +7.25 (95.6th / 99.0th, F1
strong-band 0.912). The recognizer confirms the 7447 failed_breakdown twice more — 09:21:23
and 09:55:25, each through all four stages. The graded record (a different run,
anchored at Mancini's 7438 — more on that below) agrees: its 09:08 entry wins
(+15.5 before −4.25), and its 09:55 entry at 7451.75 is near-perfect — adverse
excursion 0.5 points, favorable 37.75 within thirty minutes. "Ripped to 7490+,"
letter and tape in agreement.

The climb to the top of the leg is thick with structure. Twenty probe-atoms
print today against a corpus norm of ~6.7/day (§2.4 slice: effort_pct > 80,
travel < 0.3, range ≥ 2) — seven of them in 08:31–09:03, six more in 10:02–10:30.
The leg's cell string carries fourteen **micro-stall** motifs (the `121` trigram:
conviction, absorption blink, conviction resuming) in 104 trigram slots — 13.5%
against the corpus interior norm of 3.9%. The tape paused constantly and never
broke. At 10:00:54 an absorption-read catches buyers being absorbed at 7466.25;
at 10:11:21 comes the day's highest-confidence read (0.985): sellers threw 485
contracts at the 7474.25 bid and were refilled 5× — "absorbed, level lifted
away" — inside the 10:11 atom, itself a monster probe-atom: 13,676 contracts
(99.7th percentile), 11.25 points of range, travel 0.20. Two F2 atoms follow
(10:12 grade 0.492, 10:13 grade 0.194) — sellers pressing, absorbed — then the
answer: 10:14 prints +10.50 (98.5th / 100th, F1 0.970) and the leg's last atom,
10:15, +9.25 on 10,334 contracts (99.2nd / 99.5th) — F1 at grade 0.984, the
best-graded atom of the day. The leg dies at maximum volume, going up.

Now the whole run as a **leg** — the zigzag's unit: +43.25 points of 45.5
extreme in 106 minutes. **Pace** 0.429 (extreme-points per minute), **giveback**
0.050 — it kept what it took. Its **force** (+5,082, signed delta — never
conflate with unsigned effort) agrees with its direction. At leg scale it grades
F1 in the strong grade-band (0.822; effort 96.7th / effect 91.1st, corpus-wide).
Apply the archetype cascade by hand: not a **flush-leg** (pace under the 0.75
**cutpoint**), not a **leg-grind** (pace above 0.38), force aligned, giveback
small, pure-F1, pace in the 0.38–0.75 window — a **steady-leg** (core), the
"trust the tape" class (11.2% of corpus legs). Its **archetype-grade** — distance
to the nearest reassigning cutpoint, in corpus-percentile units — is 0.114: the
**lean grade-band**, and honestly only a whisker above the coin-flip line, because
its pace percentile (39.8) sits 5.7 points from the leg-grind edge (34.1). Lean
on the label accordingly.

And here the leg lens must confess. The zigzag's reversal threshold today is
13.0 points (20% of the 65.0-point final range), and the entire morning Failed
Breakdown — down 23.25 summed-net points, back up — lives *inside* leg 1. The excursion
happened in the decomposition's seed phase, before any leg direction existed;
the stored record absorbs the day's marquee event into the interior of one
up-leg. This is the documented mega-leg limitation (taxonomy §5.3): on rth days,
leg-boundary-trap resolution lives at the atom tier; the leg tier supplies only
regime. The
atoms and the recognizer filmed the Failed Breakdown; the leg never saw it.

**The record's far-anchor noise, disclosed.** The recognizer's anchor set this
run was Mancini 7412 / 7447 / 7474 / 7506 — and 7506 sat above the day's entire
range (high 7496.5), 7412 below it (low 7431.5). What did they print? At
08:33:05, with the recognizer's neighboring swing prints at 7442.25 (08:31:23)
and 7448.25 (08:34:02), the record shows level_reclaim engagements
*forming* at 7474 **and at 7506** — the latter some sixty points overhead —
both invalidated 31 seconds later. That is the recognizer's known proximity
blind spot (st-98z item 4), the 7/22 account's 7575 analog: "price below
anchor" counts as a flush-stage no matter how far below. 7412 printed nothing
at all — zero events all day, a silent anchor. And the plan-level the letter's whole
story turns on, 7438, is **not in this run's anchor set** — the graded
confirmations run (20260727T054148Z) anchored 7438 and nothing else. The two
records watch the same tape through different keyholes; neither carries the
other's verdicts.

## Act II — the blink at the top (10:15 → 10:20)

Legs die hot, and the **pivot-atom** — the shared border minute where one leg
ends and the next begins — is the 10:15 monster above (F1, 0.984). What follows
barely exists: five minutes, −3.75 net of 5.5 extreme from its origin, pace
1.100, giveback 0.318, force −502 (aligned). At corpus scale it grades **F4
dead** in the strong grade-band (0.756; effort 12.2nd / effect 6.1st
percentile). The cascade lands on **probe-fade** — out,
nothing there, back (giveback ≥ 0.30, effect < 50) — but its giveback percentile
(92.3) sits 1.0 from the cutpoint's (91.3): archetype-grade 0.020, the
**coin-flip grade-band**, unreportable bare. Report the straddled pair:
*probe-fade / dead-drift*. Either way it is the blink between two stories, and
its second-to-last atom (10:18, F2 solid-band 0.348, 4,326 contracts, travel
0.12) is an **absorption-death** marker — the F2-in-tail signature that lifts
the odds the next up-leg opens on conviction (0.46 → 0.60 corpus-wide; the lift
runs 1.85× on b-final days).

## Act III — borrowed conviction (10:19 → 11:11)

It does open on conviction — head cells `111` — and the recognizer is faster
still: a failed_breakdown at 7474 forms at 10:20:07, flip-stage at 10:20:29, and
the confirmation-event lands the same second, 10:20:29 — the only confirmation
of the day that skips the stall-stage. One minute into the new leg, at the
leg-boundary: textbook **leg-boundary-trap** geometry (F2 in the dying leg's
tail, conviction head on the new leg). Honesty clause: this is *not* a
**V-signature** — the prior down-leg's whole extreme was 5.5 points against the
signature's ≥8-point flush-leg requirement. Small leg-boundary-trap, small spring.

The leg itself: +18.75 of 19.0 extreme in 52 minutes, pace 0.365, giveback
0.013, force +2,512 aligned. And it is the day's designated humility lesson —
the case the vow exists for. At leg scale it grades F1 **at 0.004**: effect
percentile 50.2, two-tenths of a point from the cell-boundary. A coin-flip-band
cell label is unreportable bare, so the leg-scale claim is the pair *F1/F2*.
The archetype call inherits the same razor edge: pure-F1 residual, pace 0.365 —
below the steady window, so *steady-leg, off-pace-slow flag*; nudge effect down
two-tenths of a percentile and it reads *absorption-stall*. Report it as the
coin-flip pair — *steady-leg (off-pace-slow) / absorption-stall*, archetype-grade
0.004 — and note the second thin margin: its pace percentile (32.3) is 1.8 from
the window edge (34.1), so even the off-pace flag versus core is nearly a
coin-flip. The label is not embarrassed; it is telling you exactly how much to lean
on it: almost nothing. What is *not* ambiguous: 52 minutes of aligned buying
that kept 98.7% of its extreme.

## Act IV — the trapped-buyer slide (11:10 → 12:10)

On 7/22 the **counterforce-leg** was a creature of the epilogue — an archetype
seen only in other days' tape. Today it walks on stage. The pivot-atom at 11:10
is quiet-ish (F1 lean-band 0.266), and — the record's own wrinkle — the day's
printed high is *not* at the pivot-atom: RunMeta's range high is 7496.5, and the
recognizer's 11:27:52 delta-divergence reads "bearish: new swing high 7495.25"
seventeen minutes *after* the close-based zigzag turned. The down-leg's interior
contains the day's absolute high; the 1-minute-close lens and the bar-level
extremes disagree, and the leg fields cannot show it (§0.1 — leg structure is
doubly hindsight).

The leg: −29.75 of 30.0 extreme in 60 minutes, pace 0.500, giveback 0.008 — it
closed one tick from its extreme. Effect 72.8th percentile. And its
force is **+2,654 — net BUYING, against a falling leg**. The misalignment
percentile is 97.1 against the 75.9 zero-crossing: price fell thirty points
*through* buyers the whole way down. Cascade: **counterforce-leg**
(mis > 0 ∧ effect ≥ 60), archetype-grade 0.256, lean grade-band — the binding
axis is effect (72.8 vs the 60 cutpoint); the misalignment itself is solid. The
corpus says this class skews down 41/28 — trapped-buyer drops — and the
absorption-read at 11:31:25 shows one cohort of them: buyers threw 418 contracts
at the 7485.50 ask, refilled 2×, "absorbed, level broke." When you see falling
price with blue footers, this is what it looks like at leg scale — Direction
Inversion Watch territory by construction.

Inside this leg the recognizer runs a level_reclaim at 7474 through all four
stages — flush-stage 11:47:52, stall-stage 11:51:46, flip-stage 11:54:22,
**confirmation-event 11:59:14** — a bullish confirmation fired inside a falling
**host-leg**. The
corpus grades that context 19.2% (hindsight attribution; the live proxy is
unbuilt). This run carries no ±5 verdict for it — the graded file watches a
different anchor — so the record honestly cannot say how it resolved. What the
tape shows: the leg kept falling for ten more minutes.

## Act V — the hollow bounce (12:09 → 12:35)

The 12:09 pivot-atom is the quiet kind — graded **F3 hollow** at 0.108
(lean grade-band, 0.008 off the coin-flip line), 1,887 contracts, the
turn nobody paid for (63% of corpus pivot-atoms are F1; today's six split three
loud, three quiet — the morning turned loud, the afternoon turns quiet). The
bounce retakes +16.25 of 16.75 in 26 minutes at pace 0.644, force +1,137
aligned — but at corpus scale it grades F4 (effort 17.8th / effect 40.4th):
**dead-drift**, archetype-grade 0.192, lean grade-band, nearest alternative
**hollow-glide** across the effect axis. Sixteen points on air. Its tail is all
F3/F4 — a **quiet-death**, depleted rather than opposed — and the leg it hands
off to is the day's longest.

## Act VI — the long unwind (12:34 → 14:26)

−45.25 points of 46.5 extreme across 112 minutes, pace 0.415, giveback 0.027,
force −2,089 aligned. Read its atom string and it is wall-to-wall F4 dead and
F3 hollow — 55 F4 and 32 F3 of 112 atoms, 78% of the leg drifting down on air —
yet at leg scale it grades F1 in the solid grade-band (0.558; effort 77.9th /
effect 91.5th). Both are true: atom grades are day-relative texture, leg grades
are corpus-wide mass; 112 small efforts sum to a large one. Say which tier you
mean. The cascade: pure-F1, pace inside the window — steady-leg — but its pace
percentile (38.0) sits 3.9 from the leg-grind edge: archetype-grade 0.078,
**coin-flip grade-band**. Report the pair: *steady-leg / leg-grind*. Whichever
word wins, it is the b-day's signature stroke: the letter's morning rip, taken
back a point deeper at nearly the same pace (0.415 against the rip's 0.429).

The recognizer spends the leg trying to catch the falling knife at its two
anchors and failing honestly. The second 7474 level_reclaim (formed 12:39:45)
never confirms — invalidated 13:20:40. A 7447 failed_breakdown forms 13:31:27,
reaches "flush+flip+stall" (the record's own stage string) by 13:36:49, and dies
unconfirmed at 14:04:31. The
graded record at 7438 is blunter: its three mid-leg entries — 13:36, 13:57,
14:12, all bullish, all inside a falling host-leg — all lose at the ±5 bracket
(the 13:57 entry takes 14.0 points of adverse excursion for 2.5 favorable).
Confirmations against the host-leg are the corpus's graveyard, and today they
died on schedule. The absorption-reads frame the bottom: 14:03:31, sellers threw
112 contracts at the 7441.50 bid, refilled 3×, "level lifted away"; 14:04:26,
buyers threw 188 at 7443.00, "level broke" — both sides absorbed within a
minute, six ticks apart. The 13:42:47 delta-divergence stamps the afternoon
low zone: new swing low 7435.5 on weaker aggression — the tape revisiting the
morning's basement (7431.5) and declining to break it. The leg's last atom,
the 14:25 pivot-atom, grades F4 at 0.348 (solid grade-band): 1,850 contracts,
travel 0.10. The day's
biggest leg ends in a whisper.

## Act VII — the last fight (14:25 → 15:00)

The close leg opens dead — head cells `444` — then wakes up. +14.25 of 17.5
extreme in 35 minutes, pace 0.500, giveback 0.186, and an aligned force of
+4,918 net buying on 132,514 contracts — second in size only to leg 1's +5,082,
in a third of the minutes. At corpus scale it grades
F2 (effort 60.1st / effect 35.2nd) → **absorption-stall**, archetype-grade
0.202, lean grade-band — and the honesty clause cuts twice here. First, the
taxonomy's off-diagonal bar (§3.2): an F2 leg claim wants solid-band grade
(> 0.3) minimum, and this one is below it — so report the pair
*absorption-stall / dead-drift* (the nearest alternative, across the effort
axis), with *probe-fade* only 0.224 away across the giveback
axis. A crowded neighborhood; hold the label loosely. Second, the graded record:
its 14:44 and 14:49 bullish entries both lose at ±5 before the 14:53 entry
finally wins (+12.0 against 0.5 adverse) — even the winning side of a rising leg
paid twice for position first.

Then the MOC window, which the corpus says owns the day's densest effort — and
today obliges. The 14:58 atom is a probe-atom *and* doji-atom: 4,597 contracts,
travel 0.00, F2 strong-band (0.820). Twenty-three of the day's 34 absorption-reads
stamp 14:58–15:00, both directions at once: buyers absorbed at the 7443.50–7450.00
asks, sellers absorbed at the 7442.00–7449.25 bids, refill ratios to 6×. And
14:59 is the loudest atom of the day: **38,868 contracts — 100th percentile —
for a force of minus six.** Thirty-nine thousand contracts of effort and the
signed aggression netted to −6, while price ranged 10.75 points and closed +3.75.
F1 at 0.790, and the purest exhibit in the file of why effort and force are
different axes. The final absorption-read, 14:59:59: "absorbed, level held (end
of stream)."

## The day in one line

**Day-sequence:** steady-leg *(lean, 0.114 — a whisker off the leg-grind edge)* →
probe-fade *(coin-flip, pair with dead-drift)* → steady-leg, off-pace-slow
*(coin-flip, pair with absorption-stall — the F1 cell itself grades 0.004)* →
counterforce-leg *(lean)* → dead-drift *(lean)* → steady-leg *(coin-flip, pair
with leg-grind)* → absorption-stall / dead-drift *(lean, below the off-diagonal
solid bar — reported as a pair per §3.2)*.

Three of seven archetype calls land in the coin-flip grade-band; the closest
published baseline is the ~19% coin-flip share for leg *cell* grades (the
taxonomy publishes no grade-band distribution for archetype-grades) — by any
reading,
this day was drawn mostly on the cutlines. The
stored day-type is **b**, and the recognizer's profile read says why: "bulge
sits in the lower range (POC at 26% of range) under a thin upper stem —
one-sided push down, then acceptance below." The b-day median leg is the
corpus's biggest, and today's median leg is 18.75 points against the corpus's
7.25. Summed over 390 atoms: 1,077,442 contracts, day force +12,978, and a
close-to-close sum of nets of **−0.75** — a round trip. The morning rip
(+43.25) and the afternoon unwind (−45.25) are the same stroke drawn twice
with the sign flipped, which is what this b-day looks like from the inside.

## Epilogue — creatures not seen today

Three archetypes never got a bare label today (one lurks as a coin-flip
pair-partner, one as a lean-band nearest alternative; none was assigned). Their best sightings from other days in the
263-day corpus — real dates, real numbers, nothing staged:

- **flush-leg** — fast AND big, the tradeable V-dump leg; today's tape never
  paired its speed with its size (leg 2 had the pace, 1.100, and a 6th-percentile
  effect). The corpus specimen: 2026-03-09, 13:00 — **+109.75 points of 112.5
  extreme in 100 minutes**, pace 1.12, giveback 0.024, effort 99.6th / effect
  100th. Kept essentially all of it.
- **leg-grind** — the trend-day crawl; it haunted today as leg 6's coin-flip
  pair-partner (and leg 1's nearest edge) but never won an assignment. Specimen: 2025-10-29, 08:57 —
  **−62.75 points over 288 minutes**, pace 0.234, effort 99.1st / effect 97.7th.
  Nearly five hours downhill and never a clean entry.
- **hollow-glide** — distance on air, leg-scale F3. Specimen: 2026-03-18,
  13:00 — **−35.0 points in 60 minutes on 23,407 contracts** (effort 40.3rd
  percentile). Nobody paid for that trip, and it traveled anyway.

And one homecoming, with a correction attached: the **counterforce-leg**
printed live today as Act IV. The 7/22 epilogue could only point at a
specimen — 2026-07-27's −81.75 on net buying — but the enforced cascade files
that leg **flush-leg** (pace 1.130, effect 98.6th; flush-leg is checked first
in the priority order), so its genuine misalignment (+3,033 of net buying
against an 81.75-point fall) never gets to name it. No 2026-07-27 leg
classifies counterforce — today's Act IV is the class's first true appearance
in this drill series, not its second. The bestiary rotates.

## Coda — what was LIVE in this story

Everything narrated from atoms' raw fields (volumes, nets, ranges, travel,
force), every stage transition, every confirmation-event, every absorption-read,
sweep-print, and delta-divergence: **LIVE** — knowable in the minute or the
bar. Every percentile, cell, grade-band, leg-boundary, pace, giveback,
archetype, host-leg attribution, the ±5 verdicts (computed after the fact from
excursion records), the day-type letter, and the day-sequence itself:
**HINDSIGHT** — the grading of the tape after the fact, which is exactly the
authority hindsight holds in this system. Two further things this record
structurally cannot see, said plainly: the atoms carry no absolute prices, so
every price in this narrative comes from the recognizer record or the letters;
and the two recognizer runs watched different anchor sets (7412/7447/7474/7506
vs 7438 alone), so the five signals-run confirmations and the nine graded
verdicts describe overlapping but non-identical setups — neither is the other's
scorecard. The narrative you just read is the hindsight layer teaching the live
layer's vocabulary; your seat only ever gets asked about the live half.
