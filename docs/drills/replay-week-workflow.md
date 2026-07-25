# FootPrint Replay Week — Drill Workflow (st-055)

Re-run a full week of DataBento RTH history through the production
classifier/recognizer stack, one day at a time, from the chair — same
FootPrint surface, same pipeline, every emission recorded for 20/20
hindsight review.

**Why this is faithful:** the computation path (reader → volume bars →
engine → stacks → recognizer) contains zero wall-clock reads — all time is
event time from the tape. The measured record is computed in one
deterministic batch pass; the drill surface renders the identical pipeline
with the identical anchor rule. Watching at speed 1× IS the live pacing
(bar duration ÷ speed, progressive intra-bar fill from real tape slices).

## The week

Target week **2026-07-13 → 2026-07-17** (most recent complete Mon–Fri
full-RTH week). The 07-06 → 07-10 week is equally replayable.

| Day | Date | ES trades on disk |
|-----|------------|---------|
| Mon | 2026-07-13 | 342,928 |
| Tue | 2026-07-14 | 278,031 |
| Wed | 2026-07-15 | 354,464 |
| Thu | 2026-07-16 | 339,526 |
| Fri | 2026-07-17 | 417,804 |

## One drill day, start to finish

1. **Launch** (COO runs it; Steve says "run Monday"):

       .venv/bin/python scripts/replay_day.py --date 2026-07-13

   This records the day (append-only, `data/measurement/replay/`), then
   opens the footprint drill in the browser. Optional: pin the day's levels
   with `--mancini-levels 6212,6230` — the SAME levels anchor both the
   record and the drill.

2. **Sit the session.** Set speed **1×**. Watch as-if-live. The optional
   coach channel works exactly as in normal drills
   (`scripts/drill_coach.sh start` before, `stop` after).

3. **Annotate in hindsight.** During or after the replay, Steve dictates;
   COO appends (never edits):

       .venv/bin/python scripts/replay_annotate.py --date 2026-07-13 \
           --time 09:14 --text "flush into 6212 was the real one"

   Use `--bar N` instead of `--time` when the note is about a specific bar.

4. **Review.** Merge the record with the notes into the review page:

       .venv/bin/python scripts/replay_review.py --date 2026-07-13

   Day type, every recognition with its stages, emission counts, and the
   hindsight notes — this page (plus the raw JSONL) is the audit record
   for the recognizer review.

5. **Teardown.** Close the browser tab; `scripts/drill_coach.sh stop` if
   the bridge was up. The record and annotations persist under
   `data/measurement/replay/`; the HTML in `/tmp` is disposable.

## Invariants

- **No live-path contamination.** Corpus files are read-only inputs; the
  replay writes only under `data/measurement/replay/` and `/tmp`. No
  Schwab, no DataBento pulls.
- **Append-only record.** Re-running a day appends a new run block under a
  fresh `run_id`; nothing is rewritten. Review tools read the latest run;
  history stays.

## Troubleshooting

- `FileNotFoundError: no ES corpus file` — that date has no tape. Pick
  another day.
- No absorption rows in the record — the day has no MBP-1 file (07-23/24
  pending billing; the 07-06 week is trades-only). RunMeta says `mbp1: false`;
  everything else records normally. The target week 07-13..17 has full MBP-1.
- Empty recognitions — an unlabeled day anchors on range edges only;
  supply `--mancini-levels` to anchor the levels you traded.
- Out-of-order/duplicated tape (e.g. 2026-07-02) is safe: the reader
  dedups and canonically sorts before anything downstream sees it.
