# The Two-Tier Emitter — operating runbook

**Beads:** st-85dv (this structure) · st-dgwj (event emission) · st-6s6x (rules
v2) · st-eaa8 (analyst scope ruling) · st-uqme (grading rubric)
**Ruled by Steve:** 2026-08-25. **Built:** 2026-08-25, mid-session.

---

## Why the shape changed

The 2026-08-24 audit scored two emitter sessions against the scorer log, the
gexbot polls and the internals gauge. The finding that drove everything here:

> **Numerical accuracy in the narration came from the scorer, not the model.**

Both models transcribed tool output near-perfectly. They erred in exactly two
places — when *recalling* instead of reading, and when *characterising*. What
they missed, they missed by not noticing.

That is a structural fact, not a prompt problem, and it has a structural answer:

- **Noticing becomes mechanical.** The scorer detects alert-grade tape events
  itself and emits them as `EVENT` lines. A missed climax is now a bug with a
  test, not an attention lapse.
- **Transcription gets cheap.** It was never the differentiator.
- **Interpretation gets expensive, and rare.** The model spend goes where it
  actually outperformed — playbook binding, event-triggered context, push
  judgement — and is woken by events rather than by a clock.

The clock cost about 276 wakes a day and spent most of them reporting that
nothing had happened. Measured over two real sessions, the event regime wakes
**17 and 10 times inside RTH**.

---

## The wiring

```
  corpus tape
      │
      ▼
  scripts/live_effort_effect.py          ← TIER 0: the instrument
      │   graded line, one per closed minute      (no model, deterministic)
      │   EVENT lines, sig=alert | sig=note
      ▼
  /var/moo/logs/effort-effect/<day>.log
      │
      ├──────────────► TIER 1: TRANSCRIBER — holds the pane, appends the
      │                running record, zero interpretation
      │
      ▼
  tools/effort_event_watch.sh            ← wakes ONLY on sig=alert
      │
      ▼
                       TIER 2: ANALYST — expensive model, woken by events
```

**Tier 0 decides what is worth noticing.** Thresholds live in
`config/tape_events.yaml` and are Steve's. Detection logic and its reasoning are
in `market/orderflow/tape_events.py`.

**Every stdout line the watch prints is a model wake.** That is the budget the
whole design protects. `sig=note` events stay in the log as context for whoever
is already awake; they never wake anyone.

---

## Tier 2 — the analyst's contract

You are woken because the instrument saw something, and the wake carries the
event plus the graded bar that produced it. You are not being asked what
happened — that is already on the line. You are being asked what it *means*.

### The three rules (st-6s6x), each closing an observed failure

**1. Superlatives are grepped, never recalled.**
Any claim of the form "biggest / largest / first of the day" must cite a fresh
read of the log or the scorer's own running maxima. Never answer one from
conversational memory.

> The failure: 2026-08-24 13:14 called +549 the biggest buy-delta of the day,
> contradicting the same session's own 10:47 note of +786.

The instrument now makes this cheap. Buy and sell records are tracked as
**separate series** — the scorer's `smax` field ranks on magnitude alone, so
whichever side is larger hides the other completely, which is precisely how that
question got answered wrong. `EVENT SUPERLATIVE MAX-BUY-DELTA` and
`MAX-SELL-DELTA` each carry their own `prev=` so the standing record is on the
line you are reading.

**2. Digests lead with delta, price second.**
Report what the flow did, then what price did.

> The failure: 2026-08-25 12:13-17 read as "no clean direction" from price
> alone, across four of five negative-delta bars totalling cum -437.

**3. A flagged divergence carries a revisit obligation.**
If you note a non-confirmation — breadth against futures, delta against price,
one instrument against another — you owe it a report at its resolution. Say what
would resolve it when you flag it, and come back when that happens.

> The failure: 2026-08-25's morning breadth divergence was raised at startup and
> never revisited, including through the 10:29 VWAP reclaim that resolved it.

**Push policy:** day-max-volume bars and overnight-low breaks are push-grade
regardless of which model is on duty.

### Naming setups — Steve's ruling, 2026-08-25 (st-eaa8)

Steve ruled **yes** to naming completed setups and **yes** to stating the
playbook implication overtly. His rationale on record: overt labels are helpful
so long as the implications are understood, and the human retains the decision.

Four conditions:

**1. Criteria-cited, never vibes-cited.**
A pattern name is a graded claim. State the setup's defining conditions and show
each one met, from the log.

> "Prior low 7664.5 broken 08:42, flush held plan support 7654 within tolerance,
> reclaimed within 4 bars at 08:46 — failed-breakdown structure complete."

not

> "Looks like a failed breakdown here."

**2. Implication stated, decision retained.**
Say what the playbook says the setup implies — entry zone, trigger, level
sequence — as classification-plus-implication. Never as a directive.

> In scope: "the playbook's entry is the reclaim, trigger above 7666."
> Out of scope: "enter now."

**3. Named setups are push-grade.**
A completed-setup call is only worth its cost if it is heard in time. On
2026-08-24 the two unnamed failed-breakdown entries were worth roughly 20 and 29
points.

**4. Mechanical-first.**
Any precondition that can be detected mechanically belongs in Tier 0, not in
your judgement. Name setups *on top of* detected structure so the judgement
surface stays as small as it can be.

### The regime gate — amendment 2026-08-25 ~09:55, REVISED ~10:35

**The first version of this section said a completed setup at a range edge in
rotation is "fade/skip context rather than pushed as an entry." That phrasing is
WITHDRAWN.** Steve challenged its provenance; Desk traced it and retracted it as
unsourced synthesis — training-data reading of a trading-modes framework blended
with generic auction lore, not anything in Strader's canon. The best-sourced
version says regime changes a setup's **management and expectancy**, not its
**validity**.

The revised criterion, and the discipline it imposes on itself:

**5. Criteria-cited naming must carry a regime qualifier — trending, or
established rotation — and state the playbook's regime-specific MANAGEMENT
implication, citing the exact rule from Strader's own knowledge files. No regime
rule enters this runbook until the codifying session has read
`orb-playbook`, `selective-range-scalping` and `trapped-seller-fuel` and cites
them.** The criteria-cited discipline applies to the doctrine as much as to the
call.

#### What those three files actually say — read 2026-08-25 during codification

**There is exactly one regime rule in canon, and it governs expectation, not
validity.** `knowledge/orb-playbook.md`:

> "**GEX sign** — positive (mean-revert regime) is hostile to continuation;
> negative (trending regime) favors it."

and, on management:

> "Take Target 1 and walk away. Cross-check against GEX first: a GEX wall sitting
> between price and the target means the target probably does not get hit — skip
> the trade or **downgrade the expectation**."

Note what that rule is keyed to: a **GEX wall between price and the target**. It
is not keyed to rotation as such. "Skip" appears in canon only under that
specific condition — which is why the withdrawn phrasing could not be sourced.

**Range trading exists in canon but is not settled method.**
`knowledge/selective-range-scalping.md` opens by saying so:

> "Strategy 3, and it is **exploratory** — that is the status it carried in
> CLAUDE.md and it was never promoted past it. Nothing here is settled method;
> treat it as a candidate, not a playbook Steve runs."

Its binding parts are a cadence cap (2-3 trades per session) and a friction rule,
with 3-5 SPX point targets. Any rotation-management claim leaning on this file
must carry its exploratory status out loud.

**And the ceiling on what may be claimed at all.**
`knowledge/trapped-seller-fuel.md`:

> "trades tell us where aggression happened, not who is still holding or where
> anyone's stop sits"

> "High fuel is not a signal to enter; it is one input Steve weighs. The feature
> never fires advice."

#### The honest state of this criterion

Canon supports the **qualifier** requirement and the **GEX-sign** management rule.
It does **not** currently contain a regime-specific management rule for the
rotation case beyond that. So criterion 5 is satisfiable today only where the GEX
rule applies; anywhere else, the analyst states the regime and says plainly that
the playbook has no management rule for it rather than inventing one. Writing
that rule is Steve's and Strader's, not the emitter's and not COO's.

That gap is the whole reason the fade/skip phrasing had to be withdrawn: the
runbook reached for a rule that did not exist, and reaching felt like knowing.

> The calibration case is today, 09:30-09:32. The flush of 7680 to 7663.25 and
> the reclaim came on the day's max volume (14,778) **and** the day's max sell
> delta (-1240), on one 17-point bar. It met every mechanical failed-breakdown
> criterion. It then produced about 3.75 points of favourable excursion inside a
> roughly 12-point rotation, and gave it all back.
>
> Steve's read — "just chop" — was correct. Desk's "completed on record bars"
> framing was **the emitter failure class inverted: accurate numbers, inflated
> narrative.** Every figure in it was right. The story built on them was not.

That inversion is the one this whole runbook is least protected against, because
the instrument cannot catch it. The numbers will be correct. The discipline has
to come from the analyst.

**Within-day superlatives early in RTH are additionally discounted.** Sixty
minutes in, some bar is always the record. The instrument now says how far into
the session a record landed rather than leaving you to remember: every
`SUPERLATIVE` event carries `rth_min=`, minutes since the 08:30 CT open, negative
overnight. `rth_min=60` on a day-max is a much weaker claim than the same record
at `rth_min=300`, and the line tells you which one you have.

**What is deliberately NOT mechanical here.** There is no regime classifier. The
detector does not decide trending-versus-rotation, and it should not — that is a
method judgement belonging to `knowledge/`, not to an event threshold. If a
mechanical regime read is wanted later, it needs Strader's definition first, not
COO's guess. Until then the qualifier is the analyst's to state, and stating it
is mandatory.

### What is still out of scope

Sizing, order placement, and anything that transmits. The fire key is Steve's
and the st-5ey wall is untouched.

---

## Reading an EVENT line

```
08:43 CT  EVENT SUPERLATIVE MAX-SELL-DELTA  sig=alert  delta=-676  prev=-551@06:51  vol=4004  net=-2.00  close=7693.75
```

`EVENT <KIND> <SUBTYPE>  sig=<alert|note>  key=value ...` — greppable by eye,
parsable by scanning for `key=value` tokens. The four kinds:

| Kind | Means | Watch for |
|---|---|---|
| `SUPERLATIVE` | new session max volume / buy delta / sell delta | `prev=` carries the record it displaced |
| `ABSORPTION-CLUSTER` | consecutive bars of effort with no displacement | `START` is the alarm, `END` reports how it resolved |
| `CLIMAX` | `delta` at the top percentile of the session so far | `pctl=` is against the session, causally |
| `PLAN-LEVEL` | touch / acceptance / rejection at a Mancini anchor | `through=` is how far price actually went |

A `SUPERLATIVE` delta record deliberately suppresses the `CLIMAX` that would
otherwise fire on the same bar — a record is a climax by any reading, and the
record is the stronger claim.

---

## Running it

```bash
# Tier 0 — the instrument (in the emitter pane, piped to the day's log)
.venv/bin/python scripts/live_effort_effect.py | tee -a /var/moo/logs/effort-effect/$(TZ=America/Chicago date +%F).log

# Tier 2 — the wake channel (as a Monitor, from the analyst session)
bash tools/effort_event_watch.sh /var/moo/logs/effort-effect/$(TZ=America/Chicago date +%F).log
```

`--no-events` on the scorer disables EVENT emission. It is the escape hatch, not
the norm; emission is additive and leaves every pre-existing line byte-identical.

### Cutting over mid-session

The scorer replays the day from the corpus on restart, deterministically, so a
restart costs nothing but duplicated morning lines in the log — and those are
useful, because they let the morning be diffed across the change.

1. Stop the scorer. Leave the capture stack alone; it is a separate process and
   must never be restarted for this.
2. Restart it. It prints a `REGIME CHANGE` marker, then replays the day.
3. **Wait for the replay to finish before arming the watch.** Arming first would
   wake the analyst once for every event the morning already produced.
4. Arm `effort_event_watch.sh`. It starts at the end of the file for the same
   reason.
5. Diff the pre-restart morning against the replayed copy — they must be
   identical. That is the acceptance condition, and it is what makes the day
   comparable across its own regime change.

---

## Grading a session afterwards

`st-uqme` formalises the audit method into a repeatable rubric: enumerate every
playbook-defined setup that fired in the window, then score the narration on
point-claim accuracy, derived-claim fidelity, omissions and fabrications. The
2026-08-25 log is the first calibration set that contains **both regimes on the
same tape**, which is why the cutover marker exists.

Because the ruling above makes named setups carry stated implications, those
calls now have testable outcomes — so the ledger can score analyst judgement
against results, not just its arithmetic.
