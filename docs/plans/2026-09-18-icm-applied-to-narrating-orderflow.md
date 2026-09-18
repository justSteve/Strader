# ICM applied to `narrating-orderflow` — selection as an artifact, not a memory

2026-09-18 · bead **st-whl4** · skill: `DReader/.claude/skills/narrating-orderflow/` (dr-22w)
· pattern: ICM, *Interpretable Context Methodology* (arXiv 2603.16021; Desk directive 2026-08-28)
· the measured precedent: `docs/reviews/2026-08-29-footprint-icm-trial.md`

## The answer, five lines

1. Yes — and the sharpening is narrower than "restructure the skill into folders". The
   Context move already performs the exclusion Steve describes; what it does not do is
   **leave a trace**. It narrows inside one prompt, produces no artifact, and nothing
   downstream is bound by the narrowing.
2. ICM's load-bearing property is not the numbered folders. It is that **a stage cannot
   cite what is not in its context folder** — the footprint trial measured this: across
   12 model calls, not once did the model hang a cite on words the excerpt did not
   contain; it wrote UNSOURCED or NO-RULE-IN-CANON 46 times instead.
3. Applied here: the Context move writes `selection.md` (level, day type, comparison set,
   scenario row), and the narration stage's `context/` is **generated from that file**, so
   the three unselected scenario rows are physically absent rather than discouraged.
4. Three current rules in the skill are behaviour the model must remember and could become
   properties of the tree: the scenario row is picked silently, the comparison set is
   chosen silently, and the tell has no cite. All three have a checker shape.
5. One part lands today with no runner and no folders: make the selection a **required
   first line of output**. The rest is a grading lane over the nine episodes, not a change
   to the live narrator.

---

## 1. What the Context move actually does, and why it is the right place to cut

The skill's first move asks *"why does this spot matter today?"* and the answer sets three
things at once:

- **which scenario row** the read will come from — the four-row table under *Deriving
  inference, expectation and invalidation* supplies a fixed triple (inference, expectation,
  invalidation) once the row is chosen;
- **which comparison set** every later size word inherits — *"state the character in the
  context move so every later size word inherits it"*;
- **what is excluded** — everything the four rows and the named set do not cover.

That is a routing decision. In the skill as written it is made and immediately dissolved
into prose. The narration stage still has all four rows, every scale rule and the whole of
`carmine-moves.md` in front of it. The instruction *"a read that does not fit a row is
narrated as what it is … never forced into one"* is asking the model to decline material
that is sitting in its context.

This is the same shape the footprint lane was built to attack. The standing provenance
rulings there — regime qualifier required, no regime rule until cited — *"stop being
behavior the analyst must remember and become properties of the directory tree"* (Desk,
2026-08-28). The 2026-08-25 incident is what happens when they stay behaviour.

## 2. Three defects ICM fixes mechanically

### 2a. The scenario row is chosen silently

**Now:** four rows plus the null case are in context at narration time; the model picks one
in its head. A narration that quietly blends row 1's inference with row 4's expectation
reads fine and is not detectable.

**Under ICM:** stage 10 emits a line-shaped `selection.md`:

```
LEVEL     7678.75  session low, first touch 08:30, 1 visit   [fact:at_the_level.level]
DAY-TYPE  inside, 0.9x typical pace at this minute            [fact:day_character.pace_vs_typical]
SET       typical_minute_so_far = 2918                        [fact:day_character.typical_minute_so_far]
ROW       A  (selling into a low; price will not go lower)
```

`ROW NONE` is a valid, checker-passing answer — ICM's `NO-RULE-IN-CANON` under another
name, and the reason Steve's nine-episode set carries one null.

Stage 20's `context/` is then **generated**: the one selected row, the scale rules that
govern the named set, the `carmine-moves.md` lines for the six moves. Wrong-row language
becomes uncitable rather than discouraged.

### 2b. The comparison set is chosen silently

Steve's own objection, this session: at 10:43 *"a normal minute"* means the morning's
median harmlessly; at 14:00 the same words would call an ordinary afternoon quiet. The
skill's answer is prose — *"choose the set to fit the question, and say which one you
used."*

The fact sheet already holds the sets as fields. From `episodes/ep01/facts.json`:
`day_character.typical_minute_so_far`, `day_character.pace_vs_typical`,
`day_character.recent_days_full_range`, `session_so_far.busiest_minute`,
`session_so_far.biggest_buy_delta_minute`, `session_so_far.biggest_sell_delta_minute`,
`at_the_level.minutes_in_contact`. They are a source list that is not yet addressable.

**Under ICM:** each field gets an id; `selection.md` names the set by id; the checker fails
a size word whose comparison set is not one the sheet carries. The narrator can no longer
invent a baseline, which is exactly the failure the running-median discussion was circling.

### 2c. The tell has no cite

The skill's strongest rule — *"every adjective carries its tell"* — is verified by a human
reading for it (*"find each strong word and its tell in the same breath"*). The banned list
(`absorbed, trapped, not getting paid, failing, giving up, stepping in, defending, leaning
on`) is exactly the vocabulary that reads plausible when unsupported.

**Under ICM:** a strong word carries `[fact:<id>=<value>]` in the same sentence, and a code
checker resolves the id and matches the value **verbatim** against `facts.json`. This is
the trial's one durable result imported wholesale: the quoted-words check is *"the one
place an unsupported cite fails by code."* "Clear absorption" with no tell then fails the
run rather than reading well.

## 3. What to import from the trial, and what to leave

**Import — measured, not theorised:**

- **Code writes the facts, never a model.** Already true (`episodes/factsheet.py`). ICM
  makes it a *refusal*: the builder refuses to emit percentiles, so the skill's *"percentiles
  do not belong in the fact sheet the narrator reads from"* stops being prose the builder
  might ignore.
- **A generated context folder with a manifest and a drift refusal.** `carmine-moves.md` is
  a hand-copied excerpt file — precisely the artifact ICM's `excerpts.py` refuses. Its
  quotes already carry card + timestamp, so the manifest is half-written: pin each to
  `yt-analyst/videos/<card>/transcript.txt` and generate the file, refusing on drift.
- **Isolation of the run.** The RED/GREEN record already depends on "fresh agent, same
  prompt". The measured runner is `claude -p --setting-sources "" --tools ""
  --strict-mcp-config` from a folder outside every repo. Not a detail: without
  `--strict-mcp-config` the trial measured a 39,751-token cache write against a 5,000-token
  input, and the day's cost nearly doubled.
- **The null as a first-class line shape**, so refusing to force a row is a pass, not a
  silence.

**Leave:**

- **The live narration stays unstaged.** ICM is a post-hoc shape; Steve's own scope ruling
  on the footprint lane was that the live path takes no added latency. A narrator at a
  decision point has seconds.
- **Do not split into four model calls.** The trial folded stage 30 into 20 because a
  second call over identical excerpts bought nothing. Here: context/effort/result are one
  read, and inference/expectation/invalidation are a lookup from the selected row. Two
  calls at most.
- **ICM's workspace-level folder-map and routing files.** They steer an interactive
  session; a graded run has no session to steer. The trial omitted them for the same reason.

## 4. The shape

Grading lane, beside the skill it grades, over the nine episodes:

```
narrating-orderflow/grade/
  00-facts/     code — factsheet.py → facts.json + the field-id table; refuses percentiles
  10-select/    prompt.md + context/  (scenario table + level taxonomy only)
                → selection.md: LEVEL / DAY-TYPE / SET / ROW (A|B|C|D|NONE), each [fact:<id>]
  20-narrate/   prompt.md + context/  GENERATED from selection.md: the one row, the named
                comparison-set fields, the carmine-moves lines for the six moves
                → narration.md; every strong word carries [fact:<id>=<value>]
  30-check/     code — each [fact:] resolves and matches verbatim; <=1 number per sentence;
                no percentile; last two sentences are expectation and invalidation
  40-compare/   code — narration vs aftermath.json (held back) and vs the no-skill baseline;
                every class assigned by code, never by model prose
  _archive/     one folder per episode per run
```

Home: **DReader**, beside the skill and the episodes. Strader keeps the tape reader and is
read-only from the lane, as `episodes/scan.py` already does it.

## 5. What lands today, without any of the above

One change to `SKILL.md`: the narration's **first line is its selection** —

> `Low of day 7678.75, first touch at the open, 59 minutes ago · inside day, 0.9x pace ·
> set: typical minute so far (2,918) · row A, selling into a low.`

Then the prose. No runner, no folders, no checker. It costs one line and it gives the
existing self-check something external to check against — and it is the artifact the staged
lane would later consume unchanged.

## 6. Cost and sequence

The footprint lane was ~3.5 working days and $0.65–$0.70/day at list (no marginal charge on
the Pro plan; the calls go through `claude -p` on plan quota). This is smaller: the facts
stage, the nine episodes and the scenario table all exist. Sequence: §5 first (one edit),
then 00/10/30 as code and one model call, then 20 and 40.

## Open

Nothing blocking. The one judgement made here rather than asked: the lane lives in DReader,
because the skill and the episodes are there and cross-repo writes need delegation.
