# fp chart — what changed, 08-24 → 08-26

**Scope of this read:** `git log` since 2026-08-20 over `scripts/orderflow_drill_template.html`,
`scripts/live_footprint_feed.py`, `market/orderflow/`, `market/signals/`. Five commits.
**Three change what renders on the live footprint page; two change the scorer's log only.**
That split was verified by reading the import wiring, not by trusting the commit messages.

---

## Lands on your chart

### 1 · Trapped-seller fuel — a context line on level engagement
`5122fe8` · 08-24 05:52 CT · st-aq1n

New module `market/orderflow/fuel.py` (381 lines), wired into the feeder at
`scripts/live_footprint_feed.py:796-802`. When a bar closes, `fuel.on_bar(bar)` may return
one event, appended to that bar's `ev` list — the same list the page already renders.
Five measured components, from `knowledge/trapped-seller-fuel.md`:

- level-state touch / defense history (lazy retry until the 08:20 tracker runs)
- underwater aggression from bar cells
- lid rejections and absorbed dips on 5-min rolled rows
- node-run / shelf thin scan on 1-pt buckets

It is **payload-only** — it never raises into the feed, so it can annotate a signal but never
change one. 17 tests, including the ES 2026-08-19 7739 worked example pinned from corpus.

> **Measured, right now: this line is dark.** Construction is gated —
> `if not args.no_fuel and mancini:` at `live_footprint_feed.py:497`. The feeder restarted at
> **00:00:12 CT today with `mancini levels=0`**, so `FuelTracker` was never built. That is
> `st-kxnv`, still open. Today's parse published 59 anchors at 03:47 CT; the running feeder
> does not have them.

### 2 · Fuel emission floor
`e6750d9` · 08-24 05:54 CT · st-aq1n

Landed two minutes after the first. Adjacent-level flapping is bounded to **one fuel line per
refresh window** — without it, price sitting between two anchors prints a fuel line for each,
on every refresh. Effect on the chart: fewer duplicate context lines, not different ones.

### 3 · Sweep wording now renders from the lexicon
`30ec6a8` · 08-26 01:25 CT · st-bkvt

**The defect:** one number — how many distinct prices a sweep's aggressor walked — went by
three words at once. The field said `ticks_swept`, the written line said "3 levels", the
spoken line said "three ticks", and the ratified word was a fourth thing, *tick-level*.
Nothing was broken and nobody had lied; three surfaces had each been hand-written, months apart.

**What you see change:** a SweepPrint that read **"3 levels"** now reads **"3 tick-levels"**.
Spoken, "eight ticks" is now "eight tick-levels".

**The mechanism:** a template holds slots and connective tissue and never a field's name; the
word naming a quantity is written once, in `emission.quantities`, and both surfaces pull it
from there. `market/emission/renderer.py` refuses to *load* a lexicon that binds one field to
two quantities — at first import, not at the first emission.

---

## Does **not** land on your chart

Verified: `market/orderflow/tape_events.py` is imported by `scripts/live_effort_effect.py` and
`scripts/replay_emissions.py` only. `live_footprint_feed.py` does not import it. Both changes
below are scorer-side, and surface in `/var/moo/logs/effort-effect/<date>.log`.

### 4 · Four EVENT classes emit from the scorer
`3614fcc` · 08-25 09:59 CT · st-dgwj

SUPERLATIVE, ABSORPTION-CLUSTER, CLIMAX and PLAN-LEVEL each emit their own greppable EVENT
line with a `key=value` payload. Three findings worth keeping:

- **Buy and sell delta are separate series now.** The old `smax` ranked delta on magnitude, so
  whichever side was larger hid the other completely. That is how "biggest buy-delta of the day"
  got answered off a line that only ever showed a *sell* record.
- **The absorption threshold is 80, not 85.** The calibration cluster prints as effort 85/90
  because the graded line formats percentiles with `.0f`; the true values are 84.7 / 90.4. A
  threshold read off the printed line missed the exact case the class exists for — and the unit
  test, written from those same printed numbers, passed.
- **The anchor ladder is dense** — 69 prices across 600 points on 08-24, not a handful of plan
  levels. A naive detector fired 415 times in one session; 7674 alone announced acceptance 58
  times as price chopped across it. Fixed with penetration, distance and cooldown hysteresis
  plus a mechanical scope: the nearest anchor above and below.

### 5 · The regime gate — `rth_min` on every SUPERLATIVE
`3697dbf` · 08-25 10:21 CT · st-eaa8 · st-dgwj

Every SUPERLATIVE now carries `rth_min` — minutes since the 08:30 CT open, negative overnight.
"Sixty minutes in, some bar is always the record" stops being something the reader has to
remember: `rth_min=60` on a day-max is visibly a weaker claim than the same record at
`rth_min=300`. CT constant, not UTC, so it does not repeat the DST landmine already flagged
against the context strip's hardcoded 13:30 UTC.

No regime classifier was built, deliberately — trending-versus-rotation is a method judgement
that belongs in `knowledge/`, not in an event threshold.

---

## Summary

| # | Change | Where it shows | Live now? |
|---|--------|----------------|-----------|
| 1 | Trapped-seller fuel context line | fp chart, bar `ev` strip | **No — 0 anchors, st-kxnv** |
| 2 | Fuel emission floor | fp chart (suppresses duplicates) | No — rides on #1 |
| 3 | Sweep says "tick-levels" | fp chart, SweepPrint text | Yes |
| 4 | Four EVENT classes | scorer log | Yes |
| 5 | `rth_min` on SUPERLATIVE | scorer log | Yes |

---

## Addendum · replay by time

`67b7c91` (runner, 08-25) + `876ede3` (proof, 08-26) · co-b18wf · Desk Ruling 9

`scripts/replay_emissions.py` re-emits archived tape through current code. The time knob:

| Flag | What it does |
|---|---|
| `--from / --to YYYY-MM-DD` | day range; `--to` defaults to `--from` |
| `--between HH:MM-HH:MM` | intra-day window, **CT** |
| `--rth` | shorthand for `--between 08:30-15:00`, the cash session |
| `--price LOW-HIGH` | only bars whose *traded range touched* the band |
| `--kind` / `--subtype` / `--sig` | scope to a subset of the vocabulary |

**The property that makes it trustworthy:** the window narrows what is **reported**, never what
the detector **sees**. Extrema and cooldowns are path-dependent, so the detector always runs the
whole day and the region only scopes output. A `13:30-15:00` replay is the afternoon as the
instrument actually experienced it, with the morning's state intact — not a fresh detector
started at 13:30.

**Determinism:** nothing reads a wall clock. Every decision keys off `Trade.ts`. Two runs over
one region with unchanged code are byte-identical, or the tool is broken and the diff it
produces means nothing.

**Why `--rth` earns its own flag:** a live log watches the cash session, but a replay covers the
whole Globex session and will legitimately report more. Comparing the two without the flag is
how you manufacture a mismatch that is not a defect.

**Proven 2026-08-26 (st-v3wj):** the replay reproduces what the live emitter actually said —
102 EVENT lines against the 102 in `/var/moo/logs/effort-effect/2026-08-25.log`, compared line
by line, all byte-identical, PLAN-LEVEL 37/28/10 either way. The earlier "74 vs 102" was a
mid-session census used as a baseline, not a defect in the tool.

```
scripts/replay_emissions.py run --from 2026-08-25 --to 2026-08-25 \
    --kind PLAN-LEVEL --between 13:30-15:00 -o pm.jsonl
scripts/replay_emissions.py diff before.jsonl after.jsonl
```

**Where it shows:** scorer side. Nothing from this renders on the fp chart.
