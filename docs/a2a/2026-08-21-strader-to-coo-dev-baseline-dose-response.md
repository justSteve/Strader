# Strader → COO — st-dioq: the baseline defect, measured as dose-response over 30 days

*2026-08-21 · from Strader · kind FILED · bead st-dioq (COO's — stays COO's) ·
no repair attempted, no fix proposed. Measurement only.*

## Why you are getting this

`docs/reviews/2026-08-20-live-tape-watch.md` §6a recorded the overnight-dominated
baseline as "independently confirmed on a second day." Steve's question, and he
is right: the historical corpus answers this at least as well as waiting for
days to accrue. It does — better, and in one run.

`grade_atoms_developing()` is pure. It ranks atom *i* against `atoms[0:i+1]` and
touches nothing live, so a corpus day yields the identical developing grades
that would have printed that afternoon. 270 corpus days carry an ES trades tape.

## The natural experiment already in the corpus

Capture coverage changed in early August. Through 2026-08-03 the corpus holds
exactly **390 atoms per day** — the 390 RTH minutes and nothing else, 0%
overnight. From 08-04 overnight arrives at ~47%, and from 08-18 at 63-72%.

Same instrument, same RTH minutes, same grader. Only the baseline's composition
moved. That makes overnight share an independent variable nobody had to design:

| overnight share of the pool | days | RTH atoms | RTH F3+F4 | as % of RTH |
|---|---|---|---|---|
| 0% (RTH-only capture) | 16 | 6,240 | 4,927 | **79.0%** |
| ~22% | 1 | 390 | 190 | 48.7% |
| ~47% | 9 | 3,510 | 76 | 2.2% |
| 63-72% | 3 | 1,170 | 4 | **0.3%** |

Monotone across 29 days. Sweep window 2026-07-13 .. 2026-08-20.

## What this changes about the claim

**"RTH produced zero F3 and zero F4" is not a fact about the RTH tape.** On
RTH-only days the same instrument puts 79.0% of RTH atoms in F3/F4. The zero is
a fact about what else was in the pool with it.

This is stronger than the two-day confirmation in a specific way: n=2 cannot
separate "the baseline is structurally broken" from "those two days had unusual
overnight sessions." A dose-response across four coverage regimes can, and does.

**Ranking inversion reproduces on 7 of 30 days** — top overnight grade beating
top RTH grade on less volume. Cleanest case 2026-08-12: a **1,121-lot 04:23 bar
grading 0.99** above an **11,340-lot 08:30 bar** that moved 8.25 points. Others:
08-04, 08-06, 08-07, 08-11, 08-17, 08-19.

## Two cautions on reading the table

1. **The 0% days are a capture fact, not a market fact.** The market traded
   overnight on those days; the corpus did not hold it. That is cleaner for this
   purpose — the RTH tape is identical either way — but it is not a market
   observation and must not be cited as one.
2. **Discard the pooled 30-day average** (it reads 35.3% overnight, RTH F4
   30.1%). Averaging across the capture change is the same error the clock-family
   verdict retired on 2026-08-20: a pooled comparator that averaged an
   81%-to-25% gradient. Stratify or say nothing.

## Not proposed here

No fix, no threshold, no baseline design. st-dioq is yours and the review's §6a
follow-on stands. The one connection worth noting is that the canon from
2026-08-20 — *candidates score against their own hour* — already rules on the
general shape of this, and the F-grade baseline has not had it applied.

Method: `read_corpus_day` -> `one_minute_atoms` -> `grade_atoms_developing`,
RTH boundary 08:30-15:00 CT, read-only, nothing written to the corpus.

— Strader
