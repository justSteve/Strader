# Flush Watcher — Validation Against Real Flush Days

**Bead:** st-88ei · **Measured:** 2026-08-20 · **Data:** 23 July 2026 ES corpus
days · **Generator:** `scripts/measurement/synth_meter_frames.py` · **Raw:**
`data/measurement/flush_watcher_replay.json`

> Every trigger constant below is **provisional** and awaits st-rtuu. Nothing
> here is a measured threshold. This document exists to *feed* that
> formalization, not to substitute for it.

---

## Why this was needed

Closing st-kos7 established that the flush watcher replays clean against
2026-08-04 and 08-05: zero would-alerts, both up days, and the trigger is
down-only. That proves it does not cry wolf on days it should ignore, and
nothing about whether it catches a genuine flush. The known flush tapes are
2026-07-22 and 2026-07-31, and the live continuation-meter journal only begins
2026-08-03 — so no meter frames exist for either day, and none ever will.

**A detector validated only on days it should ignore is not validated.**

## Method

Meter-shaped frames are rebuilt from the ES corpus, then the **real**
`flush_watcher.evaluate` is run over them with a real `WatchState`. The watcher
is imported, never reimplemented — a replay against a paraphrase of the
decision logic measures the paraphrase.

Three things the acceptance criteria demanded, and how they were met:

**Schema identity.** `move` is built by `continuation_meter.primary_move` — the
live meter's own function, imported from the live module. The bead's text names
`morning_flush_study.primary_move`; that one returns `start_ts`/`end_ts` where
the journal carries `start_t`/`end_t`, and it has no `contested` flag, which
`evaluate` reads. **The deviation from the bead is deliberate**: the study's
function would have produced frames the watcher silently mis-parses, which is
precisely the drift the criteria warn about. Eight tests in
`tests/scripts/test_synth_meter_frames.py` pin the synthetic frame's keys
against a real live journal frame from 2026-08-04.

**Causality.** The move at minute *i* is computed over closes up to and
including *i*, never the whole day. Pinned by test — without it every timing
number is meaningless, because a whole-day move is "known" from the first frame.

**Price source.** The live meter measures SPX from Schwab minute candles; this
measures ES from the Databento corpus. The 25-point line is applied to **ES
points**. ES and SPX travel near 1:1 in points but are not the same series and
the basis moves. Every number here is an ES-point number. Frames carry
`synthetic: true` and `price_source: "ES"` so no downstream reader can mistake
them for live frames.

## Results

`DOWN/win` is the largest down primary move inside the 08:30–11:00 fire window;
`DOWN/day` is the largest across the whole session. Both are reported because a
day can carry a large down move that correctly never fires — it arrived after
the window — and showing only the session figure would read as a miss.

| day | DOWN/win | DOWN/day | fired | detail |
|---|---|---|---|---|
| 07-01 | 0.00 | 22.00 | no | |
| 07-02 | 70.25 | 112.50 | **YES** | 09:41 at 38pt (+49min) |
| 07-03 | 8.75 | 8.75 | no | |
| 07-06 | 14.75 | 14.75 | no | |
| 07-07 | 52.75 | 52.75 | **YES** | 09:10 at 28pt (+39min) |
| 07-08 | 51.75 | 51.75 | **YES** | 09:39 at 26pt (+53min) |
| 07-09 | 6.00 | 6.00 | no | |
| 07-10 | 37.75 | 37.75 | **YES** | 09:32 at 38pt (+30min) |
| 07-13 | 27.25 | 56.00 | **YES** | 09:43 at 25pt (+43min) |
| 07-14 | 25.00 | 25.00 | **YES** | 09:16 at 25pt (+31min) |
| 07-15 | 30.75 | 52.00 | **YES** | 09:42 at 26pt (+66min) |
| 07-16 | 24.75 | 62.50 | no | big move arrived after the window |
| 07-17 | 16.25 | 16.25 | no | |
| 07-20 | 47.75 | 70.00 | **YES** | 08:56 at 25pt (+12min) |
| 07-21 | 14.00 | 14.00 | no | |
| **07-22** | **26.50** | **26.50** | **YES** | 09:44 at 26pt (+39min) — **known flush** |
| 07-23 | 69.75 | 69.75 | **YES** | 09:32 at 34pt (+49min) |
| 07-24 | 23.25 | 63.00 | no | big move arrived after the window |
| 07-27 | 90.50 | 95.75 | **YES** | 08:56 at 28pt (+21min) |
| 07-28 | 30.00 | 30.00 | **YES** | 08:46 at 26pt (+11min) |
| 07-29 | 69.75 | 131.50 | **YES** | 08:52 at 26pt (+19min) |
| 07-30 | 43.00 | 43.00 | **YES** | 10:30 at 43pt (+49min) |
| **07-31** | **80.50** | **80.50** | **YES** | 08:42 at 27pt (+7min) — **known flush** |

- **Flush days caught: 2 / 2.** The gap the bead opened is closed — the watcher
  does fire on both known flush tapes.
- **Other days that fired: 13 / 21.**
- **Lag behind the move: 7–39 minutes** on the two flush days.

## The three findings

### 1. It fires, and it is not early warning

Both flush days caught, but the watcher fires **7 to 39 minutes after the move
began** — the field is named `lag_min` in the output for that reason. On 07-31
the move was already 27 points old at the alert; on 07-22, 26 points and 39
minutes old. Whatever this is worth, it is not a heads-up before the move.

### 2. The 25-point line does not discriminate

It fires on **15 of 23 days**, so it cannot function as a rare-event alarm. The
reason is visible in one comparison:

> **2026-07-22 is a known flush day, and its in-window down move is 26.50
> points — smaller than that of twelve other July days that are not.**

07-02 (70.25), 07-07 (52.75), 07-08 (51.75), 07-10 (37.75), 07-13 (27.25),
07-15 (30.75), 07-20 (47.75), 07-23 (69.75), 07-27 (90.50), 07-28 (30.00),
07-29 (69.75) and 07-30 (43.00) all travelled further down inside the same
window. **Any magnitude threshold low enough to catch 07-22 catches at least
those twelve.** Move size alone cannot separate a flush from an ordinary
down morning; whatever makes 07-22 a flush is not in its magnitude.

That is the input st-rtuu needs — not a better number for `FLUSH_PTS`, but the
finding that no value of `FLUSH_PTS` alone will do the job.

### 3. The window is doing real work

07-16 (62.50 down on the session) and 07-24 (63.00) did **not** fire, correctly:
both had under 25 points of down move inside 08:30–11:00 and did their travelling
later. The 11:00 close is not a rounding decision — it is currently the only
constraint keeping the fire count from being higher still.

## Caveats

- **Ground truth is two days.** "False positive" here means "fired on a day not
  in a two-day label set," which is thin. 07-29 fell 131 points and is called a
  false positive by that labelling. The 13/21 figure is a *discrimination*
  measurement, not an error rate, and should not be quoted as one.
- **ES, not SPX**, throughout — see Method.
- **The live meter's `stale_min` and trace fields are synthesised as clean**
  (0.0 and nulls). A real day has gaps; this replay measures the trigger's
  behaviour on perfect data, which is the optimistic case.

## Reproduce

```bash
.venv/bin/python scripts/measurement/synth_meter_frames.py --report
.venv/bin/python -m pytest tests/scripts/test_synth_meter_frames.py -q
```

## Feeds

**st-rtuu** (Obvious Line Formalization) — per the acceptance criteria, this
result is an input to that work and is not a measured threshold on its own.
