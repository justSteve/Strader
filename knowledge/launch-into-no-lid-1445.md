---
id: launch-into-no-lid-1445
type: setup
status: exploratory
owner: Steve
provenance:
  origin: empirical-observation
  ref: "scripts/measurement/final_hour_combo.py:11-45 @ 9df6a9c; docs/measurement/final-hour-combos-2026-08-29.md [st-g0jo]"
lineage:
  supersedes: null
  since: 2026-09-11
  commit: null
cite: ["## Statement"]
triggers: []
rule:
  registered: 9df6a9c
  module: rules/launch-into-no-lid-1445
  entry: "at 14:45 CT when price is in the top quarter of the 13:00 to 14:45 box, the last 30 minutes up on positive aggressor delta, and no Mancini resistance held within 10 points above"
  exit:
    stop_pts: 0.30
    target_pct: 25
    time: "15:00 CT"
  instrument: itm-single-10
title: "Launch Into No Lid at 14:45"
description: "R2 of the final-hour combination calls at 14:45 CT: the footprint launch shape with no Mancini lid held within 10 points above — pre-registered 2026-08-29, the one combination that held on both halves. A registered rule the blotter scores as trades. Exploratory: measured as a direction call, not yet as trades."
timestamp: 2026-09-11T10:50:00-05:00
---

# Launch Into No Lid at 14:45

## Statement

At 14:45 CT the rule reads up when price sits in the top quarter of the
13:00 to 14:45 box (position at or above 0.75 of the box range), the last 30
minutes closed higher than they opened on positive aggressor delta, and no
Mancini resistance within 10 points above price has held or been reclaimed
over 13:00 to 14:45. A day without a parsed letter has no lid, so the rule
can fire on it. Otherwise it says nothing. The instrument scored is the 0DTE
SPXW call about 10 points in the money, bought at the first print at or
after 14:45; the declared exit is a 0.30-point stop below the entry, a 25
percent target, or the 15:00 CT close.

## Measured record

The rule was written on 2026-08-29 before the first run as R2 of seven
agree-or-abstain combinations
(`scripts/measurement/final_hour_combo.py:11-45`, commit 9df6a9c) and scored
as a direction call on 286 corpus days
(`docs/measurement/final-hour-combos-2026-08-29.md`): at 14:45 it fired on
26 days (9 percent), hit 46 percent, miss 8 percent, median net the call's
way +3.25 ES points, positive on both halves (+33 on n=15 in 2025, +45 on
n=11 in 2026). The Mancini clause is load-bearing: the same footprint shape
without it (ablation A2) fires on 44 days and halves the edge. The write-up
calls it a lean of about 3 points into the bell that fires one day in eleven.

The rule has not yet been scored as trades. The blotter
(`scripts/measurement/blotter_replay.py`, st-uc23) is what does that; its
rows carry this entity's id and the `registered` commit above.

## Sources

- `scripts/measurement/final_hour_combo.py` — the pre-registered rule table.
- `scripts/measurement/final_hour_lens.py` — the lens state the rule reads,
  including the Mancini level replay that defines a lid.
- `docs/measurement/final-hour-combos-2026-08-29.md` — the direction-call
  scoring on 286 days.
- `scripts/measurement/rules/launch-into-no-lid-1445.py` — the rule as the
  blotter calls it, carried from the combo script unchanged.
