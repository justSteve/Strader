---
type: rule
title: "Channel Family Taxonomy"
description: "The ten channel families every study design must traverse before measuring — one written verdict per family; a family with no entry is a finding, not a silence"
timestamp: 2026-08-04T09:45:48-05:00
metadata:
  authorizing_bead: st-a3yh
  source: docs/audits/2026-08-04-auditor-report.md
  source_type: audit
---

## Why this exists

Every oversight caught in the 0DTE continuation program had one shape: **the
enumeration extended along the axis last named, and stopped at the edge of that
axis.** Steve said "VVIX," so the post-correction enumeration returned three more
volatility tickers ($VIX1D, $COR1M, $COR3M). The standing correction —
*enumerate the candidate space before measuring* — had already fired, and the
same failure recurred inside it one level up: the enumeration ran over **members
of a family**, never over **families** (auditor's report §5.2).

The families nobody ever named include the one that beats everything the program
built. Minutes elapsed since the move began grades continuation at day-median
AUC **.875**, against the convergence score's **.607** on the identical 1,882
minutes. The clock is not a symbol, which is exactly why no enumeration over
symbols could ever reach it.

## The procedure (binding)

1. **A study design opens by traversing this list**, top to bottom, and writing a
   verdict per family into the study doc — before any measurement, not after.
2. **Four verdicts only:** `measured` · `probed-and-unavailable` ·
   `deliberately-excluded` (cite the decision) · `NEVER-TRAVERSED`. A family
   whose sub-channels differ carries more than one verdict — say which is which,
   do not average them into a single word.
3. **A family with no entry is a finding, not a silence.** A missing verdict
   fails review the way a missing acceptance criterion fails a bead. "We didn't
   think of it" is not a state this list permits — the list does the thinking.
4. **Naming is not measuring.** `NEVER-TRAVERSED`, written down and left alone,
   is an honest verdict. The failure mode this rule prevents is silence, not
   deferral.
5. **Re-traverse after every capability unlock** — a new subscription, a symbol
   that starts serving, a widened corpus window, a new pull. The verdicts go
   stale; the families do not.

## The ten families — verdicts as of 2026-08-04

**1. Traded-instrument tape** — the instrument actually being traded: its trades,
prices, sizes, aggressor side.
**`measured` — regular hours only.** DataBento GLBX `ES.c.0`, 269 corpus days on
disk, of which the continuation program's entire labelled sample is **22 July
days**. The corpus holds CT hours 8–14 and nothing else, so the Globex overnight
session — its range, its VWAP, the 08:30 open's position inside it — does not
exist to be tested (report §1.3).

**2. Book microstructure** — the resting book behind the tape: best bid/ask,
size, absorption, depth.
**`NEVER-TRAVERSED` — with the data already on disk.** MBP-1, 17 corpus days
(2026-07-02 onward), never joined to any continuation study. It has been used
elsewhere — `scripts/measurement/absorption_calibrate.py` calibrates absorption
floors against it [st-9vl] — which corrects the audit package's "never used in
any study" (report §1.6). Holding the data is not traversal.

**3. Related-index price and basis** — the other index futures (NQ, RTY) and the
cash-versus-futures spread.
**`NEVER-TRAVERSED`.** NQ and RTY ride the same GLBX subscription at zero marginal
cost and nothing in `scripts/` pulls them (report §1.2). Worse, the program is
internally inconsistent about which instrument it even means: the studies define
the primary move on ES ticks (`morning_flush_study.py`, `primary_move()`), the
live meter defines it on `$SPX` cash minute closes
(`continuation_meter.py:37,144`) and feeds `spx5` into quadrant cells calibrated
on ES points (`continuation_meter.py:171,190`). Different instrument, different
granularity, different basis. The ES−$SPX spread is itself live-readable, and is
neither measured nor controlled for (report §1.4).

**4. Breadth** — how many names participate: `$TICK`, `$TRIN`, `$ADD`, `$VOLD`.
**`measured` — and half of it is unavailable live.** `$TICK`/`$TRIN` carry 40
corpus days, `$ADD`/`$VOLD` 39. Raw grades: `$TICK` on the move's side AUC .665,
`$ADD` 10-min slope .653. `$ADD`/`$VOLD` publish a session late, so the live meter
falls back to two traces — a conclusion adopted on a single evening's observation
(report §3.2). The gap inside the verdict: only `$VIX` and `$VVIX` were ever
residual-tested, so `$TICK` — the top-ranked trace and half of the live meter —
was published untested (report §1.5, §2.3; not recomputed here — see st-4cgo's
residual gate).

**5. Volatility surface** — index vol level and term: `$VIX`, `$VIX9D`, `$VIX3M`,
`$VVIX`, `$VIX1D`, `$COR1M`/`$COR3M`.
**`measured` — and this is the family everyone kept extending.** 31–33 corpus days
each for VIX/9D/3M/VVIX. The 5-min VIX slope trace (.660 raw) turned out ~80%
mechanically coupled to the concurrent ES move, its residual a coin flip
(st-40fv, R² .79 and residual .522; the audit reproduces it at .520, report
§1.5) — the finding that created the residual test. `$VIX1D`/`$COR1M`/`$COR3M`
hold **1 day, 27 rows** on disk (2026-08-04) against st-b3jq's "~30 days"
acceptance criterion; at audit time there were zero rows anywhere (report §1.4).
Schwab's minute history is a rolling ~47-day window, so the vol complex can never
be backfilled further — its sample is capped at what exists plus forward
accumulation (report §4.3).

**6. Options flow and positioning** — what the options market is doing: trades,
expected move, implied vol, dealer positioning.
**Three verdicts.** Options *tape*: `measured` after 13:00 CT, and
`probed-and-unavailable` for a morning study — OPRA SPXW trades, 272 corpus days,
**13:00–15:00 CT only** (2026-07-23 carries CT hours 13 and 14 and nothing else),
so morning options flow does not exist and extending the pull is a paid decision
never made. Dealer *positioning*: `deliberately-excluded` — GexBot paused
2026-07-03 in favour of orderflow-first, with the in-house V-metric (st-r2o.1)
unfinished. Derived vol *state*: `NEVER-TRAVERSED` — `expected_move.jsonl` and
`iv_pin.jsonl` exist from May work and are joined to nothing (report §1.5).

**7. Clock and session structure** — time elapsed in the move, time of session,
distance from the open.
**`NEVER-TRAVERSED` — and it beats everything the program built.** Minutes elapsed
since the move began grades the continuation label at AUC **.728, day-median
.875**, against the convergence score's **.678 / .607** on the identical 1,882
minutes. Base rate runs **85.4%** before 09:00 CT and **42.0%** at/after 10:00 CT;
**91.4%** in the move's first ten minutes and **42.2%** after forty. It is not a
symbol, it costs no data, and no enumeration over instruments could have reached
it (report §1.3).

**8. Calendar and event** — what kind of day this is: data releases, FOMC, opex,
month-end, day of week.
**`NEVER-TRAVERSED`.** `morning_flush_study.py:332` writes `cov["dow"]` and no
analysis reads it — the only other `dow` in the repo is a cron wrapper's log
line. No release, FOMC, opex or month-end field exists anywhere in the program.
**16 of the 22** primary moves start before 09:00 CT, squarely inside the 09:00 CT
(10:00 ET) release window (report §1.1).

**9. Price location versus prior structure** — where price sits relative to
something that already existed: overnight range, prior-day high/low/close,
opening range, VWAP, Mancini levels.
**`NEVER-TRAVERSED` — and the audit's headline confound lives here.** No
`morning_flush_*.py` and no `continuation_meter.py` carries a VWAP, overnight,
prior-close or opening-range term; Mancini levels are parsed daily and joined to
nothing. The one location quantity that leaked in implicitly — distance from the
standing extreme — grades the label at AUC **.790, day-median .811**, beating the
program's own deliverable (.678 / .607). An untraversed family held both the best
predictor of the label and the reason the label was unsound (report §1.1, §2.1).

**10. Cross-asset** — instruments outside the equity index: rates, the dollar,
credit, correlation.
**`deliberately-excluded`, decision on record.** `corpus_pull_internals.py:13`:
"/ZN and TLT serve but are cross-asset with different session semantics —
deliberately not in this stream." Separately `probed-and-unavailable` on Schwab:
`$SKEW`, put/call (`$PCSP`/`$PCALL`/`$PC`) and `$DXY` do not serve — same
docstring, and it says **do not re-probe blind**.

## The next level up

This card is the *enumerate before measuring* correction lifted from members to
families. It will need lifting again, and the place to expect that is inside a
`measured` verdict: a family marked measured has usually been measured in **one
representation** — a level, or a slope — while the others (residual, quadrant,
term, location, duration) go untested. When a verdict reads `measured`, the next
question is *measured how*, not *measured yes*.

## Provenance of the numbers

Every figure above without a `(report §x)` tag was recomputed on 2026-08-04 by
rebuilding the st-cdwe labelling loop against the corpus — 1,882 labelled minutes
over 22 days, exact parity with the stored study — and by counting corpus days
and rows on disk that day. Figures tagged `(report §x)` are the auditor's and
were not recomputed here.

The lookahead-truncation fix landing alongside this card (st-4cgo, audit §3.5)
drops one minute per day from that sample, 1,882 → 1,860 by its own account, so
these AUCs will move in the third decimal once it lands. No family verdict turns
on a third decimal: the ordering that matters — clock .875 and price geometry
.811 over the deliverable's .607 — has margin of a quarter of an AUC point, and
the audit's 4×4 label sweep moved trace AUCs by less than .05 (report §3.3).
