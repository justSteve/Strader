# Footprint ICM trial — what three runs showed

2026-08-29 · bead st-h0xx (Footprint ICM Trial) · plan `COO/myDesk/reports/2026-08-28-footprint-icm-audit-lane-plan.md` · Steve's Go 2026-08-28 15:04 CT (Desk rulings memo)

## The verdict, five lines

1. The pattern works as a provenance check. Every one of the twelve model calls across the two days passed the word-for-word check; the planted test — the withdrawn 2026-08-25 sentence and the uncited sentence that replaced it, fed through as a fake reply — was caught on both days, with the sourced half correctly cited to the Target-1 rule.
2. It costs $0.65 to $0.70 a day at list prices and about three and a half minutes of model time; the whole run, replay included, is under five minutes. All four stop conditions hold.
3. What it found on the real days is narrower than "unsourced synthesis in the live path". On 08-25 the analyst's rule-shaped claims rested on the letter ("the recovery threshold his letter names"), which the lane could not check because the day's letter parse is not in its source list. On 08-27 the live side was a COO working session, and its two class-A rows are that session's engineering talk.
4. The lane named no setup on any wake of either day, and said why each time: the six setup names are defined in the recognizer's code in terms of volume-bar beats (flush, stall, flip, confirm) that the EVENT lines do not carry. That is a finding about the inputs, and it is the first entry in the gap map the playbook refactor asked for.
5. Nothing here needs a ruling. The recommendation is to schedule the lane daily after 15:06 CT and admit the day's letter parse as a source; both are follow-on beads.

## What was built

`footprint-icm/` in Strader (commits aaf92d5, 2d17978, and the Day-3 commit carrying this review); outputs under `/var/moo/state/footprint-icm/<day>/`, outside every repo and backed up nightly. One entry point, `bash footprint-icm/run_day.sh <day>`, runs eight stages and stops at the first refusal. Sixty-two tests under `tests/footprint_icm/`, none of which call a model. The README carries the stage table and the measured table.

Three stages are code that the plan's review said had to exist before any model ran: the inputs stage refuses when the live log's EVENT lines, thresholds or level count differ from what the code produces today; the live-lane stage reads the raw session transcript and refuses when the wakes it finds differ from the set the rule derives from the log; the excerpt stage refuses a source outside `knowledge/` (plus the recognizer's docstring, decision 1), either withdrawn-class file, a refused status, or a pin whose lines moved at HEAD.

Two stages call a model, each from a folder that holds nothing but the generated excerpts and the event slice, with no tools, no settings file, no MCP server and no project instructions reachable. The classify stage writes LABEL and IMPLICATION lines; the claims stage transcribes the live replies into CLAIM lines. A checker fails the run when a cite does not resolve or the quoted words are not in the cited excerpt word for word. Every class on the page is assigned by code.

## The stop conditions, measured

| Condition | Result |
|---|---|
| 1. The checker's planted bad examples fail; the planted fixture produces the described rows | Both bad examples fail in the test suite. On both days the planted run produced a class-A row quoting "fade/skip context per the playbook", a class-A row quoting "management and expectancy, not its validity", and a CLAIM cited to `orb-target-1` with "skip the trade or downgrade the expectation" |
| 2. Every LABEL, IMPLICATION and CLAIM passes the checker | 12 of 12 calls; 43 labels, 6 implications, 30 claims; 0 failures |
| 3. At least one row a reader can verify by opening the cite | 08-25 10:56: the analyst's "the divergence was the tell", cited to `orb-gex-sign` with the words "confirms breakout conviction; divergence warns" (`knowledge/orb-playbook.md:51`). Whether those words support the claim is the reader's call — that is the row type the condition asks for |
| 4. Under a dollar and under ten minutes per day | $0.65 (08-27) and $0.70 (08-25) at list; 213 s and 202 s of model time; about 30 s more for replay and the log regeneration |

The dollar figure is the harness's list-price computation from the archived usage blocks, not a statement of which account paid. One correction from the first pass: without `--strict-mcp-config` the first 08-27 call wrote a 39,751-token cache for a 5,000-token input and the day came to $1.18; the user config lists no MCP servers, so the cause is unproven, but with the flag the same prompt and sources measure 4,827 tokens and the day $0.65.

## The two real days

**2026-08-25** — the analyst session (Strader project, the runbook read at cutover, watch armed 10:34:46, stopped by Steve at 14:28:45), three wakes, one push. The live log is two scorer runs joined; the replay reproduces its 102 EVENT lines exactly and the regenerated body matches the second run line for line once the eleven midnight-traceback lines are set aside. Twelve claims transcribed:

- Class A, four rows, all at the 10:35 wake but one: three implications about the letter — "the recovery threshold his letter names for a 7680 reclaim", "a level his own plan names", "first hold above 7685, the reclaim threshold your letter names" — and "Not calling it." at 10:56. The first three are unsourced only because the letter is not a source; they are the analyst citing Mancini, which the runbook asks it to do. The lane cannot tell a correct letter citation from an invented one until the day's parse is admitted.
- Class B, seven rows: five pattern descriptions the vocabulary cannot name ("a 99.5th-percentile buy climax", "the same absorption signature", "the mirror of the 10:56 climax buy") and two regime words — "now at the top of the range instead of the bottom" read as rotation against the lane's unstated. The regime row is the disagreement class the plan wanted: the analyst named a regime; the lane found no source that would let it.
- Class C, two figures: 1,500 and 1,725, both sums the analyst derived over a window. Derived-claim fidelity, in the rubric's words; 28 of 30 figures were found by value in the lines the analyst could read.
- One resolved cite (stop condition 3, above).
- The lane's own labels: none at every wake, each with a NO-RULE-IN-CANON implication saying what the numbers were and that the sources hold no rule for a delta record or a climax bar standing alone.

**2026-08-27** — a COO working session (project COO, watch armed 12:31:07, one wake absorbed mid-turn, no stop), three wakes, no push. The page says so under class A, and the two rows there are about the emitter's own design ("both measure against a session-to-date baseline that can only rise"). Four claims; the lane and the live side agree on the 14:59 wake (none on both sides). The 12:47 wake is the one clean comparison: the analyst quoted the scorer's line, the lane labelled it none per the recognizer's definition ("Confirmed requires flush+flip+confirm") and said why — delta stayed positive, no flip.

## What the pattern caught, and what it cannot

Caught: a cite that does not hold, by code, before anyone reads the page. Across 12 calls the model never once hung a cite on words the excerpt did not contain — it wrote UNSOURCED or NO-RULE-IN-CANON 46 times instead. That is the property Desk's design intent named: the folder makes an unsupported cite fail rather than merely look plausible.

Cannot: decide whether verbatim words support a label. "The divergence was the tell" cited to "divergence warns" is a real cite; whether it is a fair one is a reader's judgement, and the page hands the reader the lines.

Cannot, yet: name a setup from EVENT lines. The recognizer's definitions are in volume-bar beats; the EVENT tier carries plan-level touches, records and climaxes. The classify model said this itself on 08-27 at 09:55: "the penetration and delta thresholds that would establish the flush and name the setup are not stated in the sources, so nothing is classified." Until a setup is defined in terms the EVENT lines carry — or the engine path's SetupRecognition records are added to the inputs — the lane's setup labels will stay none and the comparison rests on rules, implications and regime words.

The transcriber's kind labels are the model's judgement. It filed "a buy climax" as a setup claim; the page now treats an unsourced setup claim as an alarm only when it names one of the six setups, and shows the rest under B as unmapped pattern words.

## The gap map — input to the playbook refactor

Steve sequenced the refactor after this trial so its UNSOURCED map would set the order. From the window runs (every cash-session EVENT line): 08-27 15 labels, 14 UNSOURCED; 08-25 16 labels, 16 UNSOURCED; 0 setups named on either day. What the lane reached for and did not find, in the order it cost the most:

1. **The day's letter parse as a source.** The analyst's most-cited authority on 08-25 and not in the source list. `runbook/mancini/parsed/<day>.json` is written by code, already snapshotted with its fingerprint by the inputs stage, and its rows carry the letter's own words (`source_quote`). Admit its rows with a status of their own ("letter"), generated per day.
2. **Setup definitions in EVENT-line terms**, or the engine path's SetupRecognition records beside the EVENT lines in the inputs. Three of the six names have no method file at all (the refactor's stub entities); the other three are defined in beats the tape tier does not emit.
3. **A regime rule beyond GEX sign.** The only regime rule in the sources keys on GEX sign; the analyst's regime words on 08-25 were about the range. The runbook already records that canon has no rotation-management rule; the lane measured how often that gap is reached: twice in three wakes.
4. **A status field on every method file.** The manifest carries status by hand because only one file declares one; the refactor's typed front matter retires that.

## Follow-on beads

- **Footprint ICM Trigger** — a `SCHEDULE.md` entry at 15:40 CT weekdays, after `strader-capture-evening-timer`, installed by `schedule-generate.sh --install`; the cron wrapper on the postmortem pattern with per-day logging and a non-zero exit alerted; the no-screen `claude -p` hazards on record. Recommend Go; the daily cost is about $0.70.
- **Letter As A Source** — gap 1 above: generate rows for the day's parse into the context folder with status "letter"; the checker already handles any row.
- **Percentile Key Rename** — Strader's: the three colliding keys are renamed in the lane's renderer and should not have to be.

The comparison feature needs a live counterpart; the labelling feature needs only the tape. A day with no live session runs today and yields the window labels and the planted verdict — the labelled corpus Steve's reframing described — for about $0.35.
