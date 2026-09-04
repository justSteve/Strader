# Estimated Mark Path — what the ES→premium proxy earns, and where it stops

**Bead:** st-9hhc (*Estimated Mark Path*) · **Measured:** 2026-09-01/02 ·
**Module:** `strader/marks/` (`estimated.py`, `prints.py`, `legs.py`) ·
**Scripts:** `scripts/measurement/estimated_mark_calibrate.py`,
`estimated_mark_validate.py` · **Rows:**
`data/measurement/estimated-mark-{legdays,validation-oos2026,validation-insample}-2026-09-01.jsonl` ·
**Calibrations:** `estimated-mark-calibration{,-fit2025}-2026-09-01.json`

## 0. The coverage bound, before any other number

**Measured.** OPRA prints exist **13:00–15:00 CT only, on every day** — not
"on OPRA-less days", on every day. Checked on four days spanning both DST
offsets (2025-05-27, 2025-11-14, 2026-04-15, 2026-08-14): every print falls
in CT hours 13–14; the NBBO quotes stream covers **hour 14 only** (the
14:45–15:00 final fifteen) on all four. The corpus holds 276 print days and
274 quote days, 2025-05-27 → 2026-08-14; **271 days carry both prints and ES
tape** and are what everything below is measured on.

So the proxy is calibrated and validated over **13:00–15:00 CT only**. Any
use outside that window is extrapolation: `estimated_path()` **refuses** it
unless the caller passes `allow_extrapolation=True`, and then every point
outside the window carries `extrapolated=True`. A morning fire cannot
acquire a validated estimated path from this work — there are no prints
anywhere in the corpus to validate one against.

## 1. What was built

`strader/marks/estimated.py` walks minute by minute:

```
mark(t) = max(0, mark(t-1) + delta · d_fav + theta · dt_minutes)
```

`d_fav` is the ES move in the option's favour over the step; `(delta,
theta)` come from a fitted table keyed by the option's **current** moneyness
bin (OTM beyond 5 / within 5 / ITM beyond 5) and minutes-to-close bucket
(0–15 / 15–30 / 30–60 / 60–90 / 90+), so a single that goes ITM picks up
delta along the path. One function, `path_cells()`, owns the state
convention; the calibration fit and the walk both consume it, so they cannot
disagree. Pure functions, stdlib only, no network, no clock reads.

This replaces "the ITM single tracks ES at +0.91", which is a Pearson
correlation, not a conversion
(`docs/measurement/final-hour-premium-vs-es-2026-08-29.md:31`).

## 2. Calibration — measured over 271 days

6,465 leg-day rows (4 entries × 6 legs × 271 days, minus 15 skips: 12
no-entry-print, 3 no-parity), 6,450 scored, **482,357 per-minute samples**.
Legs are the st-g0jo construction — put and call at ~10 ITM, ATM, ~10 OTM,
entry = first print at/after T — at four entries (13:00, 13:30, 14:00,
14:30) so the fit sees the whole covered window. Fitted (delta = pts premium
per ES pt in favour; theta = pts/min drift at zero ES move):

| bin | 90+ min | 60–90 | 30–60 | 15–30 | 0–15 |
|---|---|---|---|---|---|
| ITM delta | +0.66 | +0.70 | +0.73 | +0.77 | **+0.78** |
| near delta | +0.48 | +0.48 | +0.48 | +0.48 | +0.46 |
| OTM delta | +0.27 | +0.23 | +0.17 | +0.12 | **+0.06** |
| ITM theta | −0.005 | +0.001 | +0.001 | −0.003 | +0.029 |
| near theta | −0.007 | +0.000 | −0.007 | −0.006 | −0.014 |
| OTM theta | −0.007 | −0.002 | −0.008 | −0.010 | −0.016 |

The shape is what expiry should do — ITM delta climbs toward 1 into the
close, OTM delta dies, decay steepens near the bell for near/OTM. The
positive ITM theta in the last 15 minutes is measured, not smoothed away;
the plausible reading (reasoned, not measured) is convergence to intrinsic
showing up as drift. The 2025-only fit (`fit2025` file) lands within a few
hundredths everywhere — the table is stable across halves.

## 3. Validation — the residuals that decide it

Headline numbers are **out-of-sample**: fitted on 2025 (2025-05-27 →
2025-12-31), validated on 2026 (2026-01-02 → 2026-08-14, 2,946 leg-days).
In-sample over all 271 days is the check in parentheses where it differs
materially. The split-half discard gate is retired (Steve, 2026-08-30); the
split is computed and reported, nothing is discarded on it.

**Close-mark residual** (proxy close vs last print mark at 15:00):

| class | n | median \|pts\| | p75 | p95 | signed, % of entry (median) |
|---|---|---|---|---|---|
| ITM (~12.0 entry) | 982 | 1.99 | 3.78 | 8.16 | +4.5% |
| ATM | 982 | 1.42 | 2.98 | 6.92 | +7.5% |
| OTM | 982 | 0.71 | 1.80 | 5.45 | **+18.4%** |

**Stop-fire timing — the number the bead asks for.** 0.30-pt cut below
entry, print fire = first raw print at/below the level (what a resting stop
sees), proxy fire = first minute at/below it:

| class | fire/no-fire agree | both fire | neither | print-only | proxy-only | both-fire \|Δt\| median / p75 | signed |
|---|---|---|---|---|---|---|---|
| ITM | **93%** | 882 | 33 | **61** | 6 | 2 / 4 min | +2 (late) |
| ATM | 95% | 907 | 25 | 47 | 3 | 1 / 4 min | +1 |
| OTM | 95% | 897 | 35 | 39 | 11 | 2 / 6 min | +1 |

**+25% target timing**, same construction: agree 84–90%, both-fire |Δt|
median 1 min, proxy late by a median 1 minute, print-only 78/85/120 per
class.

**The bias has one direction and it flatters.** Where the proxy and prints
disagree on the cut, it is almost always the prints that fired (61 vs 6 on
ITM). Those 61 misses are wick-outs: on their days the proxy's close ended a
**median 10.6 pts above the cut level** — mostly days that shook through the
stop on print-level noise and then paid. A minute-resolution ES proxy
cannot see a within-minute premium wick (ITM print noise is ~0.10 pts,
st-g0jo), so an estimated row scoring a 0.30 cut **under-counts stop-outs
by ~6% of leg-days, and the uncounted stop-outs are concentrated on days
that finished as winners**. Estimated-path P&L under a tight stop is
therefore biased high against printed reality, and the close residual's
signed bias (+4.5% ITM, +18% OTM) points the same way. Any consumer of
estimated rows inherits both numbers.

## 4. What this earns the blotter, and what it does not

**Earned (measured):** a per-minute path good enough to resolve a stop and
a target at minute resolution inside 13:00–15:00 CT, with the residuals
above attached — 93–95% fire/no-fire agreement, fires a median 1–2 minutes
late, misses the wick-outs, flatters by the stated margins.

**Not earned:** anything before 13:00 CT (no prints exist to validate
against — the module refuses or labels); print-resolution stop fidelity (a
0.30 stop's within-minute wick behaviour is invisible at this resolution
and the misses are not symmetric); pooled aggregates. **Estimated rows
still split from printed rows in every aggregate** — that contract
(`docs/plans/estimated-mark-path-plan.md`) is unchanged by this work.
Whether `exit_reason=time` on estimated rows is relaxed to stop/target
resolution with these residuals attached is the blotter beads' call
(st-uc23, st-uaxf, st-08ru), made against this document, not assumed by it.

## 5. Determinism and how to run

Two runs over one date range with unchanged code are **byte-identical** —
proven on the real corpus for all three outputs (legdays, calibration JSON,
validation rows; `cmp` clean), and pinned in
`tests/scripts/test_estimated_mark_scripts.py` on a synthetic two-day
corpus (one summer, one winter day). Unit tests
(`strader/tests/test_marks_{prints,estimated}.py`, 32 tests) pin the decay
term, the conversion at known bins, the state-at-step-start convention, the
coverage guard's refusal, DST handling, and the record-shape hazard
(`provenance.ts_event`, not top-level — a naive read parses to nothing).

```
.venv/bin/python3 scripts/measurement/estimated_mark_calibrate.py \
    data/measurement/estimated-mark-legdays-<date>.jsonl \
    data/measurement/estimated-mark-calibration-<date>.json \
    [--fit-through YYYY-MM-DD]
.venv/bin/python3 scripts/measurement/estimated_mark_validate.py \
    <calibration.json> <out.jsonl> [--from YYYY-MM-DD] [--to YYYY-MM-DD]
```

The operative calibration for consumers is
`data/measurement/estimated-mark-calibration-2026-09-01.json`
(`estimated.DEFAULT_CALIBRATION_PATH`), fitted on all 271 days. Timestamps
CT throughout; the corpus was touched read-only; no network anywhere in
this work.
