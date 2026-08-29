# footprint-icm — the post-session audit lane

Bead: st-h0xx (Footprint ICM Trial). Plan: `COO/myDesk/reports/2026-08-28-footprint-icm-audit-lane-plan.md`.
Directive: Desk, relayed from Steve, 2026-08-28; ruled Go the same day.

## What it is

After the close, this lane re-reads a day's archived EVENT stream — the lines
the scorer (`scripts/live_effort_effect.py`) wrote — and produces a second
reading of it that is bounded by folders: the model that labels setups can see
only the files in its own stage folder, every label must quote the exact words
of the rule it stands on, and a code check fails the run when those words are
not there. The result is compared with what the live analyst said in real time.
Divergence is the alarm that unsourced synthesis crept into the live path. The
live lane is never touched.

Steve's reframing (2026-08-28): this is a permanent harness for any day in the
recorded corpus. Days with a live session get a comparison; days without one
still get provenance-checked labels.

## Run it

```bash
bash footprint-icm/run_day.sh 2026-08-27            # everything that exists, stop at the first refusal
.venv/bin/python footprint-icm/bin/inputs.py 2026-08-27       # one stage at a time
.venv/bin/python footprint-icm/bin/live_lane.py 2026-08-27
.venv/bin/python footprint-icm/bin/compare.py 2026-08-27 --no-publish
bash footprint-icm/bin/run_stage.sh /var/moo/state/footprint-icm/2026-08-27/smoke --smoke
.venv/bin/python -m pytest tests/footprint_icm -q
```

Outputs live under `/var/moo/state/footprint-icm/<day>/` — outside every repo,
backed up nightly, no `CLAUDE.md` in any parent:

```
run.json            every stage's record: commits, thresholds, counts, checks, refusals
run.log             the stages' stderr and one-line reports
00-inputs/          events.jsonl, events.rth.jsonl, log.txt, levels.json, live_log.json
live-lane/          session.json, wakes.jsonl (each wake: alert lines, bar, reply, pushes, tokens)
10-transcribe/      events.md, window.txt, wake-HHMM.txt (one per delivered wake)
20-classify/context/  <row-id>.md (generated excerpts) + index.json; never hand-edited
40-compare/         numbers.json (the number check per wake), tripwire.json (derived words)
page.md             the page, rendered to /var/moo/desk/desk-footprint-icm-<day>.html
```

## The stages

| Stage | File | Model? | Does |
|---|---|---|---|
| 00 | `bin/inputs.py` | no | replay the day through the engine; refuse if the live log's EVENT lines, thresholds or level count differ; snapshot the anchor file with its fingerprint; regenerate the full log body |
| 00 | `bin/live_lane.py` | no | find the session that held the watch, its arm and stop, every wake it was sent, the reply, pushes and tokens; refuse if the transcript's wake set differs from the one the rule derives from the log |
| 10 | `bin/render_events.py` | no | the plain-words event table, the whole-window slice, and one alert-only slice per delivered wake; renames the three colliding percentile keys (`effort_pct_dev`, `effect_pct_dev`, `pctl_dev`) |
| 20 | `bin/excerpts.py` | no | builds `context/` in the run folder from `20-classify/context/manifest.yaml` (the source list — Strader's, status words trusted / exploratory / code); refuses a path outside `knowledge/` (plus the recognizer docstring, decision 1), a refused file or status, a pin whose lines moved at HEAD, a quote not in its own lines; `--verify` fails on any hand-added or edited file; derives the compare stage's tripwire words from the rows' quotes plus the two planted sentences |
| 20 | `bin/checker.py` | no | the line shapes (LABEL / IMPLICATION / CLAIM); a cite must resolve to a row and its `because` words must be in that row's excerpt word for word; UNSOURCED and NO-RULE-IN-CANON stand alone; a CLAIM's quote must be in the live reply word for word. The two planted bad examples fail; the good one passes (`tests/footprint_icm/test_checker.py`) |
| 20 | `20-classify/prompt.md` | yes | *(Day 3)* LABEL and IMPLICATION lines over a slice, run once per delivered wake and once over the window |
| 40 | `bin/compare.py` | code half now; the CLAIM transcriber on Day 3 | the page: per wake, what was shown, what was said, the number check; coverage; provenance |

## The rule for "what the analyst was shown"

Every `HH:MM` on a scorer line is tape time, not print time. The scorer prints a
minute's lines when the next minute's first trade arrives, and a restart prints
the whole morning in one burst; the watch starts at the end of the file. So an
alert was delivered only if its tape minute is at or after the scorer's start
minute, at or after the arm minute, and before the stop minute. Alerts in one
tape minute are one wake. `common.derive_wakes` is that rule; `live_lane.py`
asserts it against the transcript on every day that has one.

## Stop conditions for the trial

1. The checker's planted bad examples fail and the planted fixture produces the
   described rows — else the pattern does not catch the incident class.
2. Every LABEL, IMPLICATION and CLAIM passes the checker — else the folder is
   not bounding the model.
3. On 08-27 or 08-25, at least one comparison row a reader can verify by opening
   the cited lines.
4. Under a dollar and under ten minutes per day, by the archived usage blocks.

## Deliberately left out

A model in stage 10; a separate stage 30; any schedule entry (a passing trial
files the trigger bead); any change to the live lane; a scan of outputs against
the lexicon's banned words (Desk Ruling 13: derived lists, not hand lists).
