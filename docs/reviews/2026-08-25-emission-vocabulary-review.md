# Emission Vocabulary Review

**Every emission the system can make, and the words it makes them in.**
2026-08-25 · bead st-66ld · supersedes the standalone sweep question (st-jg77)

---

## Corrections, added the same evening

Strader checked this review against the source and found three things wrong with
it. All three were verified before being accepted here.

**The guard test already exists, and that is worse news than none.** This page
says nothing enforces the lexicon. In fact `tests/docs/test_lexicon.py` has been
there since 31 July and is substantially the test proposed at the end of this
page — it reads the banned-word list out of the lexicon and scans the code for
emission strings. It has never caught anything, for two reasons: both of its
banned-word tests are marked to be ignored whatever they find, and the list of
places it looks is hand-maintained at five entries over four files. **None of the
surfaces in this review are on that list.** The marks each name the same four
rulings as their reason for being there. So the enforcement was built, then
parked pending decisions that never came, while five new surfaces shipped past
it. That looks like coverage and is not, which is worse than an honest gap.

**Finding 12 overstated its case.** The plain-words glossary claims nothing about
its own authority. The competing claim is one line in `speech.py`, about
`speech.py`'s own renderings. Two documents did not each claim to be the
authority; one module claimed it on the other's behalf.

**Finding 7 has a better answer than the one below it.** The Pine chart does not
merely use different words — at line 141 it already decides "held" against each
level's own role, close-above for a support and close-below for a resistance,
which is the exact direction this page measured as missing from REJECTION. So
the fix is to adopt that machine, not its vocabulary; taking the words alone
would carry the defect across under a better name. And the sharper finding is
one this page missed entirely: **the emitter has no event for a level being
reclaimed** — the state nearest two of the setups the whole system is built
around. Filed as st-cua1, and it ranks above the rename.

Also: `CarmineSetup` is smaller than this page implies. No emission has ever
carried the name and no fixture moves, so it can land any time. The
recommendation of `SetupTrigger` is withdrawn — the word *trigger* already means
something else in the finding that prompted the rename.

---

## The short version

You asked to stop arguing about the word *sweep* on its own and look at the
whole body of emissions instead. That was the right call, and here is why.

Strader already has a ratified vocabulary. It is
`docs/lexicon/lexicon.yaml` — 44 terms, dated 2026-07-28. Its own opening line
says it settles how every surface names price action. It even carries a list of
words that must never be used bare, because they mean different things in
different corners, and *level* is on that list with the three permitted
replacements spelled out: **plan-level**, **price-level**, **tick-level**.

Nothing enforces it. Every emission surface built or touched since — and
several that predate it — was written without reference to it. The drift is
not a matter of taste; it is measurable, and I measured it.

The single clearest example is the one you caught. The sweep emission has one
number in it: how many distinct prices the aggressive order walked through.
That number goes by **three different words** on three surfaces you can see:

| Where | What it says |
|---|---|
| The code field | `ticks_swept` |
| The chart / log line | `3 levels` |
| The spoken line | `three ticks` |

And the ratified word for it is a fourth thing, **tick-level**, chosen
precisely so it could never be confused with a plan-level from Mancini's
letter — which is the other thing the same log calls `level=7680`.

So *sweep* was never really the question. The question is that we have four
vocabularies running at once and no rule that makes them agree.

---

## Part 1 — The catalog

Thirty distinct emission types, in four tiers. "Emission" here means anything
the instrument says — to the chart, to the log, to the voice, or to a page you
read afterward.

### Tier 1 — The typed emissions (twelve)

These are the signal objects the recognition engine produces. Each one has two
renderings: a written line, and a separate spoken line in `present/speech.py`
written deliberately in plainer words.

| Emission | What it says happened | Its own vocabulary |
|---|---|---|
| **SweepPrint** | one aggressor walked several prices at once | buy / sell |
| **DeltaDivergence** | new price extreme on weaker pressure | bullish / bearish |
| **ImbalanceStack** | one side owned three or more rungs of the ladder | buy / sell |
| **AbsorptionRead** | someone kept refilling and price would not move | bid / ask; held, broke, lifted-away |
| **SetupRecognition** | a setup formed at an anchor | six setup names; forming / confirmed / invalidated; four stage names |
| **Level** | a volume shelf from yesterday | POC / HVN / LVN; support / resistance / target / stop |
| **Regime** | what kind of day the options positioning implies | trending / ranging / volatile / compressed |
| **InternalsRead** | the TICK gauge's minute reading | climax / lean / neutral; four driver phrases |
| **Bias** | direction | bullish / bearish / neutral |
| **Alert** | something needs attention | info / warn / critical |
| **Action** | a suggestion, never an execution | free text |
| **InferenceRequest** | the escape hatch for what isn't codeable yet | free text |

The six setup names are `failed_breakdown`, `level_reclaim`,
`failed_breakout`, `level_reject`, `return_to_lvn`, `range_trap`. The four
stage names are flush, stall, flip, confirm — with a fifth, `extend`, on the
volume-node branch.

### Tier 2 — The EVENT lines (ten)

This is the tier that went in yesterday: the scorer notices things mechanically
so that noticing stops depending on a model paying attention. Four classes, ten
kinds of line, each marked either **alert** (wake the analyst now) or **note**
(true, logged, read it if you are already awake).

| Class | Kinds | What fired today |
|---|---|---|
| **SUPERLATIVE** | MAX-VOL, MAX-BUY-DELTA, MAX-SELL-DELTA | 6 / 6 / 5 |
| **CLIMAX** | BUY, SELL | 2 / 1 |
| **ABSORPTION-CLUSTER** | START, END | 1 / 1 |
| **PLAN-LEVEL** | TOUCH, ACCEPTANCE, REJECTION | 25 / 19 / 8 |

Seventy-four lines on 2026-08-25, of which the level lines are seven in ten.

### Tier 3 — The scorer's own lines (three)

The **graded** line, once a minute: the cell (F1 conviction, F2 absorption, F3
hollow, F4 dead), the developing percentiles, the bar's raw numbers, the running
session maximums, and a `** NEW-MAX-VOL **` flag when a record falls. The
**partial** line, every ten seconds while price sits near a plan-level, carrying
no cell and no percentile on purpose. And the **regime-change marker**, which
records that the emitter's behaviour changed — see finding 9.

### Tier 4 — The surfaces downstream (five)

The **Pine level-state HUD** on your chart, which names each plan-level
untouched / held / BROKEN / RECLAIMED. The **postmortem's leg tags**, which mark
each swing called / hinted / silent. The **meltdown read**, still in shadow mode.
The **trapped-seller fuel** panel. And the **gamma context stamp** on every bar.

---

## Part 2 — What is wrong with the words

Thirteen findings. Each one is measured against the source file or today's log,
not asserted. The first four are the ones that matter.

### 1. One number, three words — this is the sweep question

Covered above. `ticks_swept` is written as "levels," spoken as "ticks," and
ratified as "tick-level." Your screen capture said "reference to 3 prices but
only decimals difference," and you were right twice over: the span really is a
half point by construction, *and* the word announcing it was never the agreed
word. `market/orderflow/engine.py:188`, `present/speech.py:220`,
`docs/lexicon/lexicon.yaml:44` and `:363`.

### 2. Bare "level" means three unrelated things, in front of you

- **tick-levels** — the prices a sweep walked through
- **ladder rungs** — the spoken imbalance line says "Buy stack, three levels"
- **plan-levels** — `level=7680` on all 52 of today's PLAN-LEVEL lines

The lexicon banned the bare word on 2026-07-28 and named those exact three
replacements. All three surfaces still use it bare. Two of the six setup labels
on the drill — **Level Reclaim** and **Level Reject** — make it a fourth
appearance, in the names of the setups themselves.

### 3. Live percentiles are being emitted under the after-the-fact names

This one is subtle and it is the one I would fix first.

A percentile ranks a bar against the rest of the day. There are two versions:
the honest live one, which can only rank against the day *so far*, and the
hindsight one, which ranks against the finished day. They are different numbers
and the scorer is careful about it — its own header says the live one lives in
"separately named fields (`effort_pct_dev`, not `effort_pct`) so the two can
never collide."

The EVENT tier collides them. It reads the live field and prints it under the
hindsight name: `effort_pct=82+  effect_pct=7-` on every absorption-cluster
line, and a bare `pctl=99.6` on every climax line. Meanwhile the plain-words
glossary rules percentiles hindsight-only, and the speech layer refuses to say
a hindsight number out loud in real time because doing so "asserts something
unknowable."

So the log now says, in the minute, something the voice is forbidden to say —
under the name of the quantity it isn't. `tape_events.py:408`, `:447`;
`scripts/live_effort_effect.py:17`.

### 4. "Confidence" is one word over seven unrelated quantities

Every emission carries a `confidence` between 0 and 1, and it is shown on the
chart. Here is what it actually is, per emitter:

| Emission | What its confidence is |
|---|---|
| Sweep | number of prices walked ÷ 6, capped at 1 |
| Divergence | the constant 0.50, always |
| Absorption read | a real composite score of volume and refills |
| Volume shelf | 0.9 for the POC, 0.6 for everything else |
| Gamma regime | one of five hand-set constants, 0.4 to 0.8 |
| TICK gauge | the absolute score ÷ 100 |
| Setup | 0.8, or 0.9 with a stacked imbalance |

Three of those are measured, four are decoration, and they all print in the same
column in the same format. The lexicon already has the honest alternative and
nothing uses it: a **grade** (distance from the dividing line) reported with its
**band** — coin-flip, lean, solid, strong — where coin-flip is unreportable
alone and must be spoken as the straddled pair.

**A correction to st-jg77.** That bead said the confidence number decides which
emissions surface first, citing `anatomy.py:140`. I re-checked: that sort runs
only over setup instances in the drill's walkthrough list, and confidence is its
third key, behind state and stage count. Sweeps never reach it. Nothing anywhere
orders sweeps by confidence. The number is *displayed* beside every emission,
which is enough to make it worth fixing, but the ordering claim does not hold and
I have corrected the bead.

### 5. "Climax" names two calibrated, unrelated things — both live, both yours

The TICK gauge has meant "climax" since July: a minute whose wick clears the
95th percentile of its time-of-day bucket, with an action zone at score 75 and
a driver phrase, "TICK climax," that prints in plain words by design.

Yesterday's EVENT tier minted a second one: a minute whose delta sits at the
99.5th percentile of the session so far. Different instrument, different input,
different threshold, same word, no cross-reference. Three fired today.

### 6. "Absorption" names four things

The F2 cell (a minute, hindsight). The absorption-stall (a leg, hindsight). The
absorption-read (the order book, live). And now ABSORPTION-CLUSTER (two or more
minutes in the effort/effect band, live). The lexicon compounds the first three
for exactly this reason; the fourth was minted after it and did not.

### 7. The plan-level state machine is named twice, differently, on the same day

Your Pine chart says a level is **untouched / held / BROKEN / RECLAIMED**. That
is the ratified set. The EVENT lines say **TOUCH / ACCEPTANCE / REJECTION**.
Same anchors, same session, no mapping between them.

And REJECTION carries no direction. Across 2026-08-24 and 25 there were eight of
them: four at a support approached from above, two at a resistance approached
from below, one at a resistance approached from *above*, and one at a support
approached from below. So in two of the eight, the `anchor=` word named the
opposite of the role the level was actually playing — the line read
`REJECTION ... anchor=resistance` about a level that had just held as support.
The information is recoverable from the `from=` field, but the headline word
misleads before you get there.

### 8. "Band" names five things, and one collision was predicted a month ago

Grade-band (coin-flip / lean / solid / strong). The TICK gauge's action band
(climax / lean / neutral). The price envelope around a defended price. The
distance-to-a-plan-level knob. And the effort/effect box an absorption cluster
lives inside — the code literally says "Band broken."

The lexicon bans bare "band" and, more pointedly, its own entry for **lean band**
is marked *provisional — collides with directional "lean."* That collision was
flagged on 2026-07-28 and then shipped anyway, in the gauge.

### 9. "Regime" names three things, and the third is in today's log

Market regime (trending / ranging / volatile / compressed). The meltdown read.
And this line, which is in the log you read:

```
# ==== REGIME CHANGE 2026-08-25T15:28:35Z — EVENT-EMISSION ENABLED ====
```

That one means *the emitter changed its own behaviour* — nothing to do with the
market. It is a good marker and it needs a different word.

### 10. The setup names credit the wrong practitioner

The type is called `CarmineSetup` and holds six setups, two of which you
established on 2026-07-18 are **Mancini's** signature — he trades them in
roughly nine cases out of ten and they appear in 316 of 330 letters. The code
says so in a comment and points at st-1s1, which has been open since 16 July.
The wrong attribution is still the name of the taxonomy every setup emission
carries.

### 11. Two banned bare words survive in the setup labels on the drill

The drill shows six setup names, and two carry a banned bare word: **Range
Trap** uses bare *trap*, and the volume-node branch's teaching gloss uses
*acceptance* for something that is not the plan-level ACCEPTANCE. A third,
**Return to LVN**, ships an abbreviation the speech layer already knows how to
avoid — it says "a thin shelf" instead.

Worth recording what is *not* broken here, since it is the model for the rest:
your "stages, not beats" ruling from 2026-07-09 was applied properly. The drill
displays "stages," the spoken line renders each stage as a plain phrase
("pushed through," "failed to hold"), and the word *beat* survives only in
variable names and CSS classes, which that ruling explicitly exempted. That is
what conformance looks like when someone checks.

### 12. Two documents each claim to be the authority

`docs/lexicon/lexicon.yaml` says it settles how every surface names price
action. `docs/training/plain-words-glossary.md` says it is "the authority for
every word chosen here," and the speech layer cites it. They happen to agree
today. Nothing keeps them agreeing, and every surface built since August cites
neither.

### 13. "Sweep" also means a parameter sweep

In about eight scripts — `acuity-sweep`, `orderflow_hist_sweep`, the edge tests.
Engineering-internal, never in front of you. Noted only so a rename does not walk
into it.

---

## Part 3 — What I propose

Two piles. The first I will just do, because the lexicon already ruled and this
is conformance, not judgment. The second needs a word from you, and each has a
recommendation you can accept by saying nothing.

### I will do these

- Emit the live percentiles under their live names — `effort_pct_dev`,
  `effect_pct_dev`, `pctl_dev` — so a developing number never wears the
  finished-day name. **(Finding 3.)**
- Replace bare *level* with **tick-level**, **ladder-rung**, and **plan-level**
  across the sweep line, the spoken stack line, and the EVENT lines.
  **(Findings 1, 2.)**
- Make the sweep emission lead with span and size rather than the count, which
  is what st-jg77 asked for and now has a vocabulary to land in.
- Take the retired word *beats* out of the drill's display text, leaving the
  code identifiers alone. **(Finding 11.)**
- Add a test that fails when an emission string contains a banned bare word.
  Without it this review is a snapshot and the drift resumes tomorrow.

### These are yours — my recommendation is first, silence takes it

1. **"Climax" — who keeps it?** *Recommend: the TICK gauge keeps it; the delta
   event becomes `DELTA-EXTREME`.* The gauge has had the word since July,
   speaks it aloud, and its meaning is nearer the trading sense.
2. **Plan-level words — one set or two?** *Recommend: the EVENT lines adopt the
   chart's words* — touched / held / broken / reclaimed — so the log and the
   chart agree, and REJECTION becomes *held*, which carries its own direction.
3. **"Confidence" — keep the word or retire it?** *Recommend: retire it from
   display.* Show a measured grade with its band where one exists, and show
   nothing where the number is decoration. This is the method question the sweep
   bead deliberately left open.
4. **`CarmineSetup` — rename now?** *Recommend: yes, to `SetupTrigger`* — it is
   a neutral name, it stops crediting the wrong trader, and st-1s1 closes with it.

### What this does not touch

Renaming a live emission changes the fixtures the parity harness and the
postmortem check against, so none of it lands mid-session. The order is: your
four answers, then one change with the fixtures regenerated in the same commit,
then the guard test. Today's deploy stays additive, as promised.

Nothing here proposes changing what any emission *detects*. Every threshold
stays where it was measured. This is about what the instrument calls things.
