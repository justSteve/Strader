# Drill Scenario Catalog — the Pro Forma Deck

*st-5ov · 2026-07-09 · The canonical scenario collection all drill content builds on.
Fixed reference instances over fresh-data churn — repetition is a feature at this stage,
not a flaw. Vocabulary note: the four-part sequence is counted in **stages** (never
"beats"): **flush → stall → flip → confirm**.*

Every scenario entry carries: what it is in one sentence · what it looks like on the
footprint · its nearest lookalike and the tell that separates them · the correct call ·
fixed reference instances (day / bars / level). Reference instances marked **[verified]**
come from the recognizer's anatomy output or Steve's own observation; **[to tag]** means
the scenario is defined but its standing example still needs to be pinned to exact bars —
never guess one. Revised 2026-09-10 (st-z1a1): direction is an explicit axis — every
story names and examples both its ↓ (support) and ↑ (resistance) instance — and S1 is
"Clean hold" (was "Clean rejection").

---

## Part I — Level-engagement scenarios (the core six, both sides)

What happens when price meets a level that matters (Mancini number, LVN, range edge).
These are the units of the trading decision. Units 2–5 of the curriculum drill these.

**Direction is an axis, not a seventh story** (st-z1a1, 2026-09-10). Every story below
has two instances, and the instance carries the direction:

| Instance | The level | The break | The reversal, if it comes | Recognizer words |
|---|---|---|---|---|
| **↓ at a support** | a floor | down, on red aggression | back **above** the level — the **bullish** read (Mancini's Failed Breakdown family) | `failed_breakdown` · `level_reclaim` · invalidation "no reclaim" |
| **↑ at a resistance** | a lid | up, on blue aggression | back **beneath** the level — the **bearish** read (the bull trap) | `failed_breakout` · `level_reject` · invalidation "held above, no reject" |

Until this revision the six stories were written from the support side only: S2 and S3
carried downside *names*, S5 was downside-worded, and 47% of the recognizer's emissions
(1,077 bearish confirms of 2,312 on run `20260819T213124Z`) had no home in the canon.
The recognizer itself has read both sides since 2026-08-19 (st-q5xu, st-tme —
`docs/measurement/anchor-kind-mirror-2026-08-19.md`); the stages (flush → stall →
flip → confirm) were always direction-neutral words. Read every ↑ instance as the ↓
story with the colours swapped: the flush is blue through the lid, the stall is
still-bright blue with no new highs, the flip is footers turning red, the confirm is a
close back beneath the level on red pressure.

**The mirror is not symmetric — never pool the sides.** Measured on the enriched
corpus (`docs/measurement/hour-daytype-rederivation-2026-08-19.md`): the midday
depression is a *bullish* effect (↓ hours 10+12 win 31% vs 46% for the rest, p = 0.008)
and does not exist on the ↑ side (↑ hour 12 is that side's best cell at 61%, n = 33,
and hour 14 its only cell that clears p < 0.05). The retired day-type cuts looked stable
partly because they were derived on a bullish-only body and applied to both. Any
measurement that touches these stories names the side, and a pooled number without the
per-side split beside it is not reportable.

**Reference instances.** The ↓ instances are the deck's original references
(2026-07-02, 2026-07-20). The ↑ instances were pinned 2026-09-10 from the replay
recorder's measured records under the kind rule — runs
`20260910T170437943328Z-f60a18d` (07-02), `20260910T170553697346Z-f60a18d` (07-20)
and `20260910T170905249481Z-f60a18d` (08-19), `data/measurement/replay/signals_<day>.jsonl`,
bar_n 2000. 2026-08-19 joins the deck deliberately: it is an up day (D), and the ↑ side
needs instances that lost as well as won — on 07-02 and 07-20 (both down days) the
↑ traps mostly paid. Two drifts the re-record surfaced, both filed rather than fixed
here: the 07-02 ↓ references were pinned at 7511 / 7506, prices the current anchor rule
does not produce for that day (the parse carries 7512 / 7502; the same sequences
reproduce within two bars — 7512: flush 387 → stall 388 → flip 399 → confirm 419), and
the old S5 reference at 7522 on 07-20 was a *resistance* in that day's letter, so the
kind rule now reads it as the ↑ trap it was (moved to S2 ↑ below). [st-r88d]

### S1 · Clean hold

*Renamed from "Clean rejection" 2026-09-10 (st-z1a1). "Reject" was doing two jobs —
this story's name and the recognizer's `level_reject`, which is S3 ↑, a different
story. "Held" is the chart's ratified plan-level word (untouched / held / broken /
reclaimed, `pine/mancini_forecast.pine`), so S1 takes it. The drill's judgment button
still reads "Reject (fade it)" — reconciling the judgment verbs to the chart's words is
st-g9y's, not this pass.*

- **What:** Price approaches the level, aggression into it is punished immediately, price
  leaves the way it came. The level holds on first contact — it never trades through.
- **↓ at a support:** sellers into the floor are punished; price leaves upward. Bullish
  reaction.
- **↑ at a resistance:** buyers into the lid are punished; price leaves downward. Bearish
  reaction.
- **Footprint:** Approach columns show fading intensity into the level; at the touch, one
  or two bright cells against the approach direction; footers flip colour at the level.
- **Lookalike:** S2's flush *begins* the same way an approach does. The tell: in S1 the
  level never trades through; in S2 it breaks first.
- **Call:** Held — fade the approach. (In guess-then-reveal terms: price bounces ≥4 points
  away.)
- **Reference:** ↓ [to tag] — pin from 7/2 guess-then-reveal visits on a held touch.
  ↑ [to tag] — pin from a held touch at a 08-19 resistance. The recognizer cannot supply
  either: it engages only on penetration, so S1 has no emission and is tagged by eye.

### S2 · Failed break (the trap)

- **What:** Aggressors break the level with real force, the break stops paying, the other
  side takes over, price retakes the level. The full four-stage sequence with a violent
  flush.
- **↓ Failed breakdown** — at a support, `failed_breakdown`, bullish. Mancini's signature
  setup; the deck's marquee.
- **↑ Failed breakout** — at a resistance, `failed_breakout`, bearish. The bull trap:
  a push above the lid that stalls, flips red and closes back beneath.
- **Footprint (↓):** Stage 1 flush — bright red cells THROUGH the level, red footers, fast
  bars. Stage 2 stall — still-bright red cells but price stops making lows (effort
  without effect). Stage 3 flip — footers turn blue. Stage 4 confirm — price back above
  the level on blue pressure. **(↑):** the same four with the colours swapped — blue
  through the lid, blue with no new highs, footers turn red, close back beneath on red.
- **Lookalike:** S4 (clean break). The tell is stage 2: in S2 the aggressors stop getting
  paid beyond the level; in S4 the break keeps producing new extremes at pace.
- **Call:** After confirm: go with the retake — bullish at a support, bearish at a
  resistance. Before confirm: hands off.
- **Reference ↓ [verified], 2026-07-02:**
  - **Marquee:** @7511, flush bar 389 → stall 390 → flip 399 → confirm 413.
  - @7492, flush 471 → flip 476 → stall 482 → confirm 502.
  - @7506, flush 558 → stall 559 → flip 566 → confirm 594.
- **Reference ↓ [verified], 2026-07-20:**
  - **Marquee:** @7505, flush 159 (09:56 CT) → stall 160 → flip+confirm 168 (10:02) —
    the mapped FBD off the 51-pt morning drop; the letter said *don't bid direct, FBD
    actionable*, and the tape delivered it to spec (shallow flush to 7500.75, delta
    exhaustion on the final push, +23 pts to the 7534-39 shelf after confirm).
  - @7483, flush 398 (14:14) → flip 400 → stall 402 → confirm 408 — late-day range-support defense.
  - @7483, flush 461 → stall 463 → flip 464 → confirm 467 — all four stages in 31 seconds at 14:59.
- **Reference ↑ [verified], 2026-07-02 (the morning top before the cascade):**
  - **Marquee:** @7587, flush 60 (08:50) → flip 63 → stall 70 → confirm 91 (09:08) — the
    top of the opening drive; the day's cascade starts from this confirm.
  - @7587, flush 100 (09:12) → flip 103 → stall 104 → confirm 110 (09:18) — the retest of
    the same lid, failed again.
  - @7551, flush 182 (09:42) → flip 183 → stall 184 → confirm 200 (09:48) — a lower lid on
    the way down.
- **Reference ↑ [verified], 2026-07-20:**
  - **Marquee:** @7522, flush 73 (08:59) → stall 76 → flip 77 → confirm 87 (09:06). These
    are the bars the old catalog carried as a ↓ FBD "confirmed at 09:03" under the
    all-support rule; 7522 was a resistance in the letter, and the kind rule reads the
    same tape as the bull trap — the bearish signal the day then paid (cascade to 7483).
    This is `knowledge/direction-inversion-watch.md` in the tooling, on the reference day.
  - @7546, flush 19 (08:35) → stall 20 → flip 27 → confirm 42 (08:46) — the opening high.
  - @7522, flush 193 (10:23) → flip 194 → stall 195 → confirm 210 (10:40) — the midday
    retest of the same lid.
- **Reference ↑ [verified], 2026-08-19 (an up day — `knowledge/reclaim-under-the-lid.md`):**
  - @7742, flush 179 (08:56) → stall 180 → flip 187 → confirm 187 (09:00).
  - @7742, flush 345 (10:43) → flip 347 → stall 351 → confirm 359 (10:54).
  - @7742, flush 466 (13:02) → flip 467 → stall 469 → confirm 471 (13:06).
  - Three confirmed bull traps at one lid on a day that closed higher. The acuity ledger
    grades them ±5 at 30 min as win / loss / win — the honest ratio the ↑ deck needs.

### S3 · Quiet retake (the gentle sibling)

- **What:** Same destination as S2 — price ends up back on the right side of a lost level
  with opposite evidence — but the flush lacked violence; the level was lost quietly
  rather than trapped.
- **↓ Level reclaim** — at a support, `level_reclaim`, bullish: quietly lost, then retaken
  from below.
- **↑ Level reject** — at a resistance, `level_reject`, bearish: a quiet poke above the lid
  that is retaken from above. *This is the recognizer's only "reject", and it is not S1:
  here the level trades through first.*
- **Footprint:** The give-through is dim (thin, low-effort cells in the break colour), then
  the retake carries the same flip/confirm evidence as S2. Flush violence is the family
  separator the recognizer itself uses (|Δ| ≤ QUIET_DELTA_MAX).
- **Lookalike:** S2. Tell: how the level was LOST — violently (S2) or quietly (S3).
  Mancini himself re-labels between these siblings; family-level agreement is success.
- **Call:** Go with the retake on confirm; slightly lower conviction than a true trap.
- **Reference ↓ [verified], 2026-07-02:** @7511, bars 605→609 (the 14:50 late-recovery
  reclaim); @7506, bars 554→556 (the 13:59 reclaim).
- **Reference ↓ [verified], 2026-07-20:** @7505, bars 173→176 (the 10:06 follow-on reclaim
  right after the marquee FBD confirmed); @7490, bars 426→430 (the 14:36 reclaim in the
  late-day defense).
- **Reference ↑ [verified], 2026-07-02:** @7568, flush 165 (09:37) → stall 169 → flip 174 →
  confirm 176 (09:41); @7560, flush 140 (09:28) → stall 143 → flip+confirm 145 (09:30).
- **Reference ↑ [verified], 2026-07-20:** @7512, flush 170 (10:03) → stall 174 →
  flip+confirm 181 (10:11); @7522, flush 222 (10:53) → stall 225 → flip 227 → confirm 230 (11:02).
- **Reference ↑ [verified], 2026-08-19:** @7742, flush 140 (08:43) → stall 141 → flip 149 →
  confirm 150 (08:48) — the quiet poke over the lid at the open, before the 09:00 trap.

### S4 · Clean break (continuation — the anti-trap)

- **What:** The level breaks and STAYS broken: force with effect, no stall, no flip.
  What looks like the start of S2 but the trap never springs.
- **↓ Breakdown holds** — at a support: the floor gives way and the lows keep coming.
  The recognizer's word is `invalidated` ("no reclaim").
- **↑ Breakout holds** — at a resistance: the lid gives way and the highs keep coming.
  `invalidated` ("held above, no reject").
- **Footprint (↓):** Bright red through the level and the lows KEEP coming — footers stay
  red, pace stays fast, each bar's POC steps lower. No stage 2. **(↑):** bright blue
  through the lid, highs keep coming, blue footers, POCs stepping higher.
- **Lookalike:** S2, by construction. Tell: does the aggression keep getting paid?
  Paid → continuation; unpaid → trap forming.
- **Call:** Accept the break (or stand aside). Never fade force that is being paid.
- **Reference ↓ [verified], 2026-07-02 (the morning cascade — recognizer engaged, then
  correctly invalidated as support after support gave way):** @7541 bars 239–246;
  @7541 bars 266–276; @7541 bars 321–333.
- **Reference ↓ [verified], 2026-07-20:** @7534 bars 53–72 — engaged at the 7534-39 shelf
  at 08:52, flip fired but support gave way; the 33-pt opening leg of the 51-pt drop.
- **Reference ↑ [verified], 2026-07-02 (the opening drive, 08:30–08:53 — every lid on the
  way up to 7587 gave way):** @7560 bars 6–38 (08:31 → 08:42); @7578 bars 42–65 (08:43 →
  08:53). The buyers were paid through both; the drive ended at 7587 (S2 ↑ marquee).
- **Reference ↑ [verified], 2026-08-19:** @7742 bars 253–287 (09:32 → 09:56) — stall and
  flip fired, then the breakout held and the up-leg went on to engage 7752 and 7758.
- On both sides the recognizer's `invalidated` is the operational S4 signal: it emits one
  word for "the break was real" and for S5's "the retake never came", and the deck's S4
  references (both sides) include stalls and flips that fired before the level gave way.
  What separates S4 from S5 is what the tape did next — paid at pace, or a retake that
  formed and failed.

### S5 · Sprung trap fails (stall without retake)

- **What:** The pattern gets to stage 2 or 3 — the aggressors stall, delta even flips —
  but the retake never comes; price grinds back through the would-be retake level. The
  absorber gave up or was overrun.
- **↓ at a support:** sellers stall, footers turn blue, then blue pressure fails at the
  level from below; footers revert red; the recognizer's lifecycle ends `invalidated`.
- **↑ at a resistance:** buyers stall, footers turn red, then red pressure fails at the
  level from above; footers revert blue; `invalidated`.
- **Lookalike:** S2/S3 in progress. Tell: only the confirm stage separates them —
  which is exactly why the call waits for stage 4. This scenario is why.
- **Call:** No trade. If positioned early (against doctrine), the fast cut.
- **Reference ↓ [verified], 2026-07-02:** @7506 bars 422–434 (flush+flip+stall, no
  reclaim); @7511 bars 535–563 (stall+flip, no retake — resolved only later as the
  separate S3 at bar 605).
- **Reference ↓ [verified], 2026-07-20:** @7505 bars 354–369 (13:31 — 7505 lost for good
  on the afternoon leg); @7490 bars 369–409 (13:44 — cascade continues to 7483).
  *Superseded 2026-09-10:* the former third reference, @7522 bars 85–114 ("reclaim
  overrun mid-cascade at 09:05 — its own FBD at bars 71–81 HAD confirmed"), was a
  support-side read of a level the letter had as resistance; under the kind rule those
  bars are the S2 ↑ marquee above. The fast-cut lesson it carried moves to S5 ↑ 07-02.
- **Reference ↑ [verified], 2026-07-02:** @7568 bars 34–43 (08:40 → 08:43) — flush, stall
  36, flip 40, invalidated 43 as the opening drive ran on to 7587. Its own ↑ confirms
  at bars 21 (08:35) and 27 (08:38) HAD fired: confirm is not immunity, this is the
  fast-cut case on the bearish side.
- **Reference ↑ [verified], 2026-07-20:** @7534 bars 0–24 (08:30 → 08:37) — the opening
  push over 7534 stalled and flipped, then held above; 7534 gave way fifteen minutes
  later from the other side (S4 ↓, bars 53–72).
- **Reference ↑ [verified], 2026-08-19:** @7752 bars 283–323 (09:53 → 10:24) — stall 286,
  flip 288, then the up-leg pushed on through 7752 to 7758.

### S6 · Chop straddle

- **What:** Price oscillates across the level with conviction in neither direction.
  The level is noise today, or the tape is resting on it. Direction-neutral by
  construction — there is no ↓ / ↑ instance, which is the story's content.
- **Footprint:** Alternating footer colours, dim cells both sides of the level, slow
  bars, POCs clustered ON the level rather than stepping away from it.
- **Lookalike:** S1 early on. Tell: S1 leaves the level after holding; S6 keeps
  coming back with no force either way.
- **Call:** No call. The drill already scores this correctly: neither 4-point move
  within 10 bars = chop, no credit for guessing.
- **Reference:** [to tag] — pin a mid-morning 7/2 stretch or a 10:00–13:00 CT window
  from any accumulating RTH day (the no-trade window is built from this scenario).

---

## Part II — Frame scenarios (single-bar cell reading)

Unit 1 material: one paused bar, "what is happening in this cell/column?"
The effort-vs-effect matrix, four cases. Effort = cell brightness (total contracts).
Score = the number (net winner margin, color = winner).

| Code | Name | Signature | Meaning |
|------|------|-----------|---------|
| F1 | Conviction | Bright cell, big number | Hard fight, clear winner — trust the winner |
| F2 | Absorption | Bright cell, small number | Huge strain, arm didn't move — someone strong is hiding; reversal fuel |
| F3 | Hollow | Dim cell, big number | Big score, empty table — evaporates on contact with a real opponent |
| F4 | Dead | Dim cell, small number | Nothing happened |

- **Reference [verified]:** F2 — 2026-07-02 bar 0 (Steve's own first-bar find: a net −1
  cell brighter than a −16 cell → heavier two-sided volume at the −1 price).
- Column-level variants (footer + column shape) and micro-LVNs (dashed void cells —
  price jumped a level without one trade) belong to this part. [to tag] one standing
  example of each remaining frame type from 7/2.

## Part III — Tempo scenarios (pace reading)

Unit 0 material. The pace strip is the instrument; the skill is feeling it before
looking at it.

- **T1 Heating** — bar durations shortening sequence-over-sequence (urgency arriving).
- **T2 Dead tape** — long bars, dim columns (the market resting; 10:00–13:00 CT default).
- **T3 Burst** — a cluster of seconds-long bars (an event on the tape; often stage 1
  of an S2 somewhere).
- **Reference [verified]:** T3 — 2026-07-02 early-afternoon flush sequence into bar 389+;
  T3 — 2026-07-20 bars 461–467, six bars in 31 seconds at 14:59 (the final 7483 defense).

---

## How lessons consume this catalog

Concentration order lives in [skill-ladder.md](skill-ladder.md); the machine-readable
deck (ladder order + fixed instances, consumed by the drill's Ladder dropdown) is
[scenario-deck.json](scenario-deck.json). A lesson spec names: **scenarios drawn** (e.g. S2 vs S4 discrimination) · **scaffold
level** (narrated / prompted / cold) · **deck** (which fixed instances, in what mix and
order — losing hands at honest ratios: 7/2's truth is 9 invalidations to 4 confirms) ·
**pass bar**. The generator builds the drill from the spec; the same deck repeats until
the pass bar is met. Fresh days are added to the deck deliberately, not automatically.
