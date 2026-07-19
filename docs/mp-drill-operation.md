# Market Profile Drill — Operation [st-3zh]

The TPO reading drill: the session's Market Profile builds half-hour by
half-hour and you make the reads mid-flight — day type, POC, single prints,
Initial Balance — scored against computed truth. Sibling of the orderflow
footprint drill; same replay-exact tape, same log/export/coach-bridge
plumbing. Content ground: `docs/foundation/03-market-profile.md`.

## Generate + run

```bash
.venv/bin/python scripts/market_profile_drill.py --date 2026-07-02
```

Writes `/tmp/desk-mp-drill-<date>.html` and opens it in the Windows browser.
`--day-type D|P|b|trend` stamps a hand-reviewed deck label over the
heuristic; `--no-open` / `--out` as in the orderflow drill.

## The reps

| Control | What it does |
|---------|--------------|
| Phase `watch` | Profile builds with developing POC/VA/singles shown — see how the read evolves. First pass on a new day. |
| Phase `calls` (default) | Overlays hidden. Playback pauses at checkpoints (after C, F, I, close) and quizzes: day-type call, click-the-POC, flag single prints, IB extension check. |
| Speed | Seconds per bracket: 3 / 6 / 10 / 20. |
| Keys | Space play/pause · → step · R restart · 1–4 answer · Enter submit. |

Day-type calls before the close are logged as **early calls** — judged only
at the final checkpoint, where you also see your own call history (when did
you lock onto the right shape?). That mid-flight trace is the point of the
drill, not the final answer.

Close-of-day reveal includes the **volume twin** toggle: per-row volume bars
behind the letters, time-POC vs volume-POC marked — doc 03's "time is not
volume" caveat, on real tape.

## Scores

Same pattern as the orderflow drill: every answer appends to localStorage
(`mp-drill-<date>`), score readout in the header, **Export JSON** downloads
`{meta, log}`. Exports land in `docs/measurement/` per session when we start
the calibration curve. Coach bridge (`scripts/drill_bridge.py`, port 7788)
receives state snapshots when running; drill works fine without it.

## Deck

`scripts/measurement/mp_day_scan.py` runs the day-type heuristic over the
corpus and prints a shortlist. Deck days (~2 each of D / P / b / trend) get
hand-reviewed labels passed via `--day-type`. Repetition is a feature —
drill the same deck days, don't churn fresh dates.
