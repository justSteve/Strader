---
id: footprint-up-1445
type: setup
status: exploratory
owner: Steve
provenance:
  origin: empirical-observation
  ref: "scripts/measurement/final_hour_lens.py:11-19 @ ac02296; docs/measurement/final-hour-lens-calls-2026-08-29.md [st-g0jo]"
lineage:
  supersedes: null
  since: 2026-09-11
  commit: null
cite: ["## Statement"]
triggers: []
rule:
  registered: ac02296
  module: rules/footprint-up-1445
  entry: "at 14:45 CT when the footprint lens reads up: price in the top fifth of the 13:00 to 14:45 box, the last 30 minutes up on positive aggressor delta"
  exit:
    stop_pts: 0.30
    target_pct: 25
    time: "15:00 CT"
  instrument: itm-single-10
title: "Footprint Up at 14:45"
description: "The footprint lens's up call at 14:45 CT, pre-registered 2026-08-29 and the one single-lens call that held on both halves of the corpus — a registered rule the blotter scores as trades. Exploratory: measured as a direction call, not yet as trades."
timestamp: 2026-09-11T10:50:00-05:00
---

# Footprint Up at 14:45

## Statement

At 14:45 CT, with the 13:00 to 14:45 box built from the ES tape, the rule
reads up when price sits in the top fifth of the box (position at or above
0.80 of the box range), the last 30 minutes closed higher than they opened,
and the last 30 minutes' aggressor delta is positive. Otherwise it says
nothing. The instrument scored is the 0DTE SPXW call about 10 points in the
money, bought at the first print at or after 14:45; the declared exit is a
0.30-point stop below the entry, a 25 percent target, or the 15:00 CT close.

## Measured record

The rule was written on 2026-08-29 before the first run
(`scripts/measurement/final_hour_lens.py:11-19`, commit ac02296) and scored
as a direction call on 286 corpus days
(`docs/measurement/final-hour-lens-calls-2026-08-29.md`): at 14:45 it fired
on 40 days; 2025 n=25, hit 36 percent, miss 16 percent; 2026 n=15, hit 40
percent, miss 13 percent; median net the call's way +2.75 ES points. The
write-up's own caveat stands: the base rate at 14:45 is up 30 percent and
down 20 to 25 percent, so about half of the edge is the sample's upward lean
into the close. Nothing on the down side survived the split.

The rule has not yet been scored as trades. The blotter
(`scripts/measurement/blotter_replay.py`, st-uc23) is what does that; its
rows carry this entity's id and the `registered` commit above.

## Sources

- `scripts/measurement/final_hour_lens.py` — the pre-registered rule text and
  the lens code (footprint, Mancini, GEX).
- `docs/measurement/final-hour-lens-calls-2026-08-29.md` — the direction-call
  scoring on 286 days.
- `scripts/measurement/rules/footprint-up-1445.py` — the rule as the blotter
  calls it, carried from the lens unchanged.
