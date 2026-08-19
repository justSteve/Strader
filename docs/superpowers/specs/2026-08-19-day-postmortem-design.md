# Day Post-Mortem — design

**Status:** landed 2026-08-19 (Strader 0a161e8…62687a3 + the landing commit; COO 36ce47e SCHEDULE.md); crons installed (15:30 same-day, 08:27 next-morning); backfill 279 tape days, 88 of them with Mancini anchors (see bead co-7kgte). Runs are stitched before measuring — a restart re-walks the tape from the day's start and that overlap is measured once (not in the spec; found on the 08-18 record).

COO for Steve, 2026-08-19. Bead co-7kgte (**Post Mortem Process**). Approved in
conversation: a post-mortem of the **trading day**, run **by itself after every
close**, that **measures** what followed each call and **lists the moves the
machine did not call**, with Mancini's own recap as a second source where his
letter names the setup.

## 1. Purpose

Every session the recognizer makes a few hundred calls. Yesterday's question —
"what did it do at bar 339, and why did nothing say breakout?" — took a hand
trace of the feeder's record to answer. This process does that trace for every
call, every day, and adds the two things a hand trace cannot: the numbers for
what price did afterwards, and the moves that happened with nothing said before
them. Over weeks it becomes the record Steve and Strader use to decide which
refinement earned its keep and which word the vocabulary lacks.

It does not judge. Every line on the page is a number with a stated rule behind
it. Whether a move "was a breakdown" stays Steve's and Strader's.

## 2. What it reads

1. **The feeder's record of the day** — `data/derived/live-parity/<day>.jsonl`.
   Written live by `scripts/live_footprint_feed.py` through
   `market/orderflow/parity.py`: `run` headers (bar size, the Mancini list the
   run used, start time), `bar` rows (`i, t0, t1, o, h, l, c, v, d`), `ev` rows
   (every emission with its `bar_i`), `end` rows. A day may hold several runs
   (restarts); each run numbers its bars from zero. Today the record runs
   02:50 → 23:55 CT. This is the only source that says *what was on Steve's
   screen*.
2. **The day's tape**, for backfill only — `market/orderflow/replay.read_corpus_day`,
   driven through the same `StackDriver` the feeder uses (the way
   `scripts/live_parity_check.py:replay_events` already does, closed bars and
   `LiveAnchors`). Rows from this path are labelled `source: "replay"`;
   rows from the feeder's record are `source: "live"`.
3. **Mancini's next-morning letter**, when it has arrived — the cleaned text
   under `data/mancini-letters/`. Its "Trade Recap/Daily Summary" section names
   the setups of the last day or two ("The first high quality Failed Breakdown
   was the Failed Breakdown of 7777"), sometimes with a time. This is the
   nearest measurable thing to "the trade he would have taken."

## 3. What it measures

All measuring is done over **bars and events**, one code path for live and
replay. Bars are the feeder's 2,000-lot volume bars; in the cash session that is
roughly a minute each.

### 3a. Calls made, and what followed

For every emission that carries a direction:

| Type | Direction field | Measured |
|---|---|---|
| `SetupRecognition` state `confirmed` | `bias` | yes, in full |
| `SetupRecognition` state `invalidated` | `bias` (the setup's, so the move that beat it reads as adverse) | yes |
| `SetupRecognition` state `forming` | — | counted, not measured |
| `DeltaDivergence` | `kind` | yes |
| `SweepPrint` | `direction` | yes |
| `ImbalanceStack` | `direction` | yes |
| `Level` | — | listed as an anchor, not measured |

For each measured call, from the close of the bar it fired on (`bar_i`):

- **for / against at 5, 15, 30 minutes** — the furthest price went the call's
  way and the furthest against it, in points, from bar highs and lows inside
  each window (the `_excursion` arithmetic in `scripts/acuity_run2.py`, moved
  to the shared module and fed bars instead of trades);
- **first touch at ±5 points** — `win`, `loss`, or `neither` inside 30 minutes;
  when one bar's range covers both sides before either was touched alone, the
  row says `both-in-one-bar` rather than picking;
- **back to the level** — for setups only: whether price closed back on the
  wrong side of the anchor inside 30 minutes, and after how many minutes;
- **nth on this level** — the recognizer's own `fire_index`, shown, so a
  thirteenth confirm on 7724 reads differently from a first;
- **confirm lag** — for confirmed setups: bars from the first close back
  across the anchor after the flush to the confirm bar, and points from the
  anchor at the confirm close. Bar 339's confirm was lag 2, +3.75.

### 3b. Moves that happened with nothing said

A fixed rule, no judgment:

1. Walk the day's bars with a zigzag of threshold **X points**: a new leg
   starts when price has moved X against the prior leg's extreme. Each leg is
   a candidate move: origin bar, end bar, points, minutes.
2. Keep legs of at least X points that reached X inside **Y minutes** of the
   origin.
3. Tag the origin: the nearest anchor (the run's Mancini list, plus the
   profile `Level` events emitted before the origin) and its distance. A move
   is **near a level** when that distance is at most **Z points**.
4. Look back **W minutes** before the origin for calls in the move's direction:
   - `called` — a `confirmed` setup with matching bias;
   - `hinted` — a `forming` beat, a `DeltaDivergence`, a `SweepPrint`, or an
     `ImbalanceStack` in that direction, but no confirm;
   - `silent` — nothing.
5. The page lists every kept leg with its tag. The "misses" a reader will care
   about are the `silent` and `hinted` legs near a level; the others are there
   so the list is complete, not curated.

Defaults: **X = 6, Y = 15, Z = 3, W = 10**. They are knobs in one block
(`config/postmortem.yaml`, Steve-owned numbers in the `risk.yaml` pattern,
falling back to constants in the module), and the backfill reports how many legs a day each default yields
before Steve ever sees a live page. The 11:47 thrust (5.75 points in three
bars) would sit just under X = 6; that is the kind of fact the backfill puts in
front of us to set the knob, not a reason to pre-tune it.

### 3c. Mancini's recap

A small deterministic extractor over the letter's recap section: sentences in
"Trade Recap/Daily Summary" that name a setup word (Failed Breakdown, Level
Reclaim, Range Trap — his "three setup types") with a four-digit level and, when present, a
time. Each becomes a row `{letter_date, session_date, setup, level, time_et,
quote}` in `data/mancini-labels/recaps/<letter-date>.json`. The labelled-corpus
matcher in `scripts/score_recognizer.py` (EXACT ≤ 15 min, FAMILY, LEVEL, MISS)
is reused as-is to match the machine's confirms to those rows.

This section is filled on the **next morning's pass** (the letter arrives in
the evening and is parsed at 08:15). The same-day page carries "Mancini's
recap: not yet received." If the extractor finds no recap section, the page
says so; if his sentence names a level and no time, the match is LEVEL-tier
at best and says so. No model call in this path.

### 3d. Flags for Strader

Threshold-tripped, fixed, listed on the page under "For Strader" and written
to the ledger row:

| Flag | Rule |
|---|---|
| `dense-anchor` | one anchor with ≥ 5 confirmed fires in the day |
| `late-confirm` | confirm lag ≥ 2 bars **or** ≥ 3 points from the anchor |
| `silent-move` | a `silent` leg near a level (§3b) |
| `no-breakout-word` | a leg ≥ 10 points through a level with only `invalidated` said about it |
| `grid-density` | confirmed setups per 10 points of session range ≥ 8 |

On **Fridays** the run also appends one NOTE row to `docs/a2a/inbox.md` with
the week's flag counts and the ledger path. Daily rows would be noise; the
page is the daily surface.

## 4. Outputs

### 4a. Ledger — `data/measurement/postmortem/`

- `<day>.json` — the whole day: header (source, runs, coverage, bar size,
  anchors), every measured call row, every leg row, recap matches, flags,
  running-total inputs. Rewritten on each pass for that day.
- `ledger.jsonl` — one row per measured call, appended; a `pass` field
  (`same-day`, `next-morning`, `backfill`) and `source` (`live`, `replay`).
  Rows for a (day, pass) are replaced, not duplicated, on re-run.
- `legs.jsonl` — one row per kept leg, same discipline.
- `recaps/` as in §3c.

### 4b. The page

Markdown → `tmuxMOO/bin/desk-html.sh` (so it passes the plain-words gate) →
`/var/moo/desk/desk-postmortem-<day>.html`, and the same content at the stable
address `desk-postmortem-latest.html` for a parked tab, registered with
`desk-register.sh`. Sections, in order:

1. **Header** — day, source (`what you saw` / `today's recognizer on that
   day's tape`), record coverage ("02:50 → 15:30 CT; evening session
   unmeasured until the morning pass"), restarts, bar size, anchors in play,
   which pass produced the page.
2. **Census** — calls by type and state; a fires-per-anchor table (anchor,
   forming, confirmed, invalidated, first and last time).
3. **Calls made** — one row per measured call: time CT, bar (run-local,
   with run number if more than one), what it said, nth on level, confidence,
   for/against at 5/15/30, ±5 touch, back-to-level, confirm lag. Cash session
   first; overnight and evening in their own tables below it.
4. **Moves** — one row per kept leg: start, end, points, minutes, nearest
   level and distance, what was said before (`called` / `hinted` / `silent`,
   with the call named).
5. **Mancini's recap** — the rows from §3c and their match tier, or "not yet
   received."
6. **Last 20 days** — from the ledger: confirms per day, ±5 win/loss by setup,
   silent legs per day, with today's number beside the median.
7. **For Strader** — the flags, one line each, with the bar they point at.
8. **What this page does not judge** — the standing footer from the bar-339
   page, verbatim.

### 4c. Logging and alerts

`logs/postmortem.log` through a cron wrapper in the Strader pattern
(`scripts/cron/postmortem-wrapper.sh`). A non-zero exit calls
`corpus_daily.emit_alert("postmortem", …)` so the failure lands in the health
log the morning heartbeat already reads. Exit codes: 0 rendered; 2 no record
for the day (page still written, saying so); 3 renderer missing (the ledger
is still written — the page is a view of it, not the record).

## 5. Schedule

Two crons, Mon–Fri, owner Strader, catalogued in `COO/SCHEDULE.md` and
generated from it:

- `strader-postmortem-close` — **15:30 CT**: same-day pass. The feeder has
  closed the cash session by 15:05; 15:30 gives margin and is before Steve
  looks.
- `strader-postmortem-morning` — **08:27 CT**: next-morning pass for the
  previous session — picks up the evening session's bars and the recap from
  the 08:15 letter parse (after it, never concurrent). `depends_on:
  strader-mancini-preopen`.

Both call `scripts/postmortem_day.py --day <date> --pass <name>`; the script
is idempotent for a (day, pass).

## 6. Backfill

`scripts/postmortem_day.py --backfill` runs the replay path over every corpus
day with ES tape (306 today, 2025-05-27 → 2026-08-19), workers like
`acuity_run2.py`, writing ledger rows `source: replay, pass: backfill` and
**no per-day desk pages** (306 pages would bury the desk). It writes one
summary page, `desk-postmortem-backfill.html`: distributions of calls per day,
±5 outcomes by setup, legs per day at the default X/Y/Z/W and at two
neighbours each, silent-near-level legs per day, and the eight live days set
beside their replay twins (coverage differs — the live record runs to 23:55,
the tape to 15:05 — so the comparison is cash-session only and says so).

The honest label on every backfilled row: today's recognizer on that day's
tape. It is the engine's record, not what was on the screen that day.

## 7. Failure handling

- No record for the day → page says "no feeder record for <day>", alert, exit 2.
- Record ends early → measure what is there; header banner names the unmeasured
  minutes; calls inside the last 30 minutes of the record carry `window
  truncated` on their aftermath cells rather than a number that looks whole.
- Several runs → each measured on its own bars; the page shows run-local bar
  numbers with the run number; the header lists restart times.
- Run header without `bar_n` (older feeder) → skip with a line, never guess.
- Letter absent or without a recap section → the recap section says which.
- Renderer missing → ledger written, exit 3, alert.
- The translator gate never fails a render (its own contract).

## 8. Tests

`tests/market/orderflow/test_postmortem.py`:

- excursion from bars: known fixture → exact for/against, the
  `both-in-one-bar` case, the truncated-window case;
- confirm lag: a flush-reclaim-confirm sequence with the confirm two bars late;
- zigzag legs: a hand-built price path with one 8-point leg in 6 bars, one
  5-point leg (dropped at X = 6), one 9-point leg that took 40 minutes
  (dropped at Y = 15); tagging `called` / `hinted` / `silent`;
- recap extractor: three sentences from a real letter, one with a time;
- record reader: a trimmed two-run fixture cut from the 2026-08-18 record
  (committed under `tests/fixtures/postmortem/`), asserting run splitting and
  bar numbering;
- end to end: fixture record → `<day>.json` with the expected counts, and the
  markdown page containing each section heading.

Plus a smoke inside the morning pass itself: before it runs, the wrapper checks
that the previous session's `<day>.json` exists and parses, and alerts if not
(Strader has no nightly test cron to hang this on).

## 9. Files

Strader:

- `market/orderflow/postmortem.py` — record reader, measuring, legs, flags,
  recap extractor, page writer. No CLI, no cron knowledge.
- `scripts/postmortem_day.py` — CLI: `--day`, `--pass`, `--backfill`,
  `--no-publish`, `--dry-run`.
- `scripts/cron/postmortem-wrapper.sh` — log, alert on failure.
- `scripts/acuity_run2.py` and `scripts/live_parity_check.py` — import the
  excursion function and `replay_events` from the module instead of holding
  their own copies (behaviour unchanged; their tests still pass).
- `config/postmortem.yaml` — X, Y, Z, W, windows, target, flag thresholds.
- `tests/market/orderflow/test_postmortem.py`, `tests/fixtures/postmortem/`.
- `docs/a2a/inbox.md` — WRITE row on the landing commit; NOTE rows Fridays.

COO:

- `SCHEDULE.md` — the two cron entries; crontab regenerated.
- Bead co-7kgte.

## 10. Not in this design

- Grading Steve's trades. No order data is read.
- Any model call on the daily path. The recap extractor is regex; if it proves
  too thin, a labelled pass like the July one is a separate decision.
- Changing the recognizer. Flags go to Strader; the refinements themselves are
  Strader's beads.
- `mancini/post_mortem.py` (his prior-day levels against his recap) — a
  different axis, left as is.
- Per-day desk pages for backfilled history.

## 11. Defaults I chose (say the word to change any)

- Windows 5 / 15 / 30 minutes; ±5-point first touch (acuity's value).
- X 6, Y 15, Z 3, W 10.
- Flag thresholds as in §3d.
- Crons at 15:30 and 08:27 CT (the 08:15 parse, 08:20 tracker and 08:25 risk
  reset each keep their own minute).
- Ledger under `data/measurement/postmortem/`.
- Backfill over all 306 days, no per-day pages.

**Addendum A (2026-08-19, after Strader's st-g1u7 memo):** anchor kind from the parse + `kind-mismatch` flag; anchorless runs said outright; `lid_rejections` / `window_delta` on every leg; `word_match` on recap rows. Details in the plan, `docs/superpowers/plans/2026-08-19-day-postmortem.md` → Addendum A.
