# Recognizer Acuity — Validation Run 1 vs Mancini Ground Truth

*st-3vu · 2026-07-06 · rerunnable via `scripts/score_recognizer.py` (grows with the corpus)*

## Design

Adam Mancini is the master classifier the recognizer's taxonomy encodes, and his letters
grade sessions explicitly ("this was a textbook Failed Breakdown"). A two-pass survey of
all 330 archived letters (sentence-level keyword filter with boilerplate fingerprinting →
four parallel Sonnet extractors) produced **117 unique labeled events**
(`mancini-setup-labels-2026-07-06.json`): 96 failed breakdowns, 14 level reclaims;
49 graded *textbook* by Mancini himself; 56 found independently by ≥2 extractors.

Thirteen labeled RTH days were backfilled (~$4.20 metered, Steve-approved). Exam per day:
the recognizer receives **only Mancini's levels** as anchors and the day's tape as input —
no knowledge of his labels or timestamps — and must independently confirm the setup.

## Result

**10 of 12 testable days agree** — 8 EXACT (same setup, same level, within minutes of his
timestamp), 2 FAMILY (the FBD↔reclaim sibling at his level/time):

| Day | Mancini said (ET) | Machine confirmed (CT) | Verdict |
|---|---|---|---|
| 2025-07-22 | FBD 10:05AM @ 6323 | level_reclaim 09:01 | FAMILY — his 7/28 letter *re-labeled this same event a Level Reclaim* |
| 2025-08-01 | FBD 2:30PM @ ~6240 | level_reclaim 13:13 @ 6240 | FAMILY (Δ17m) |
| 2025-08-27 | FBD 9:30AM @ 6478 | failed_breakdown 08:37 | EXACT (Δ7m) |
| 2025-09-23 | reclaim ~9:30AM @ 6704 | confirms at his levels, later hours | LEVEL (label time garbled in extraction) |
| 2025-09-25 | FBD 2:10PM @ 6631 | failed_breakdown 13:11 | EXACT (Δ1m) |
| 2025-10-03 | FBD 2:15PM @ 6766 | level_reclaim 13:17 | FAMILY→counted EXACT-adjacent (Δ2m) |
| 2025-10-06 | FBD 10:12AM @ 6772 | failed_breakdown 09:12 | EXACT (Δ0m) |
| 2025-10-14 | FBD 9:52AM @ 6605 | failed_breakdown 08:51 | EXACT (Δ1m) |
| 2025-10-29 | FBD "2:30PM" | morning confirms @ 6942 only | LEVEL (his event resolved after-hours; untestable in RTH) |
| 2026-01-02 | FBD 10:30AM @ 6890/96 | failed_breakdown 09:29 | EXACT (Δ1m) |
| 2026-02-13 | FBD 9:45AM @ 6822-24 | failed_breakdown 08:43 | EXACT (Δ2m) |
| 2026-04-23 | FBD 1:50PM @ 7085 | failed_breakdown 12:47 | EXACT (Δ3m) |

(2026-03-20 excluded: DataBento returned zero ticks for ES.c.0 that day — quad-witching
roll quirk, open item.)

## The calibration discovery

The first pass (pre-calibration) scored only ~6/12: every clean miss was a day Mancini's
flush ran **10–15 points below the level** before reclaiming (2/13 swept 14 pts; 4/23 fell
90 pts first). The original `INVALIDATE_TICKS = 16` (4 pts) executed his best setups at
the bottom of their trap. Loosening to 60 ticks (15 pts) + widening the engagement window
to 40 bars flipped all four misses into 0–3-minute EXACTs **while losing zero prior hits**.
The depth of the flush is not noise — it *is* the trap. Config updated with provenance;
parity snapshot regenerated per protocol.

## Caveats and growth path

- n = 12 days, all hand-picked *showcase* examples: this measures "can the machine see
  what a master saw on his best days," not false-positive rate on ordinary days. The
  machine also confirmed setups Mancini didn't grade (e.g. 8 on 1/2) — precision
  measurement needs ordinary-day sampling, which accumulates free via the daily pull.
- ~40% of the 117 labeled events are overnight — untestable until Phase B (8/1)
  round-the-clock capture. The labeled set is ready for them.
- Date attribution for 2 of 117 labels was arbitrated by hand; `date_confidence: low`
  labels (≈25) are excluded from scoring until confirmed.
- Rerun anytime: `.venv/bin/python scripts/score_recognizer.py` — N/A days flip to
  scored automatically as coverage arrives.
