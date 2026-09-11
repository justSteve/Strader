# Estimated Mark Path — two builds reconciled, 2026-09-11

**Bead:** st-9hhc (*Estimated Mark Path*). Two implementations existed for the
same bead: the on-box build parked on `wip/st-9hhc-onbox-2026-09-04` (written
2026-09-01/02 in a Strader session, calibrated then, preserved at the 09-04
tap-in) and the off-box build on `master` (COO, 2026-09-03, commit `0195113`,
never run against the corpus until today). Both were run on this box today
against the same corpus; the numbers below are **measured** from those runs.

## The two models

| | on-box (`wip/…`) | master (`strader/marks/`) |
|---|---|---|
| form | incremental walk: `mark(t) = max(0, mark(t-1) + delta·d_fav + theta)` | closed form: `mark(t) = max(intrinsic, P_entry + delta·fav_move − TV_entry·(1 − (tau/tau_entry)^kappa))` |
| calibration cell | (moneyness bin *now*, minutes-to-close bucket): 3 × 5 cells + fallbacks | (right, 5-pt moneyness bin *at entry*): 16 cells, no fallback — an unfitted bin is refused |
| marks per minute | one, at the minute's closing ES | three: closing ES, ES extreme against the leg, ES extreme for the leg |
| legs per day | 4 entries × 6 legs (±10, ATM) | 4 entries × 14 legs (−15 … +15 by 5) |
| numbers in code | a default calibration path | none; a leg without a fit raises |
| coverage bound | measured on four days, stated | measured on every file, carried inside the calibration JSON |
| tests | 32 | 26 |

## Reproducibility — measured

The on-box build re-run in a scratch worktree reproduced its 2026-09-01
outputs byte for byte (`cmp` clean on the fit-2025 calibration and the 2,961
out-of-sample rows). The master build run twice today produced byte-identical
calibrations (`cmp` clean). Both satisfy the acceptance.

## The decisive number — stop-fire timing, out of sample (2026 legs)

The bead asks for the residual on stop-fire timing specifically. Same
statistic, both builds, fitted on 2025 and scored on 2026:

| | on-box | master (proxy at the adverse extreme) | master (proxy at the close) |
|---|---|---|---|
| legs scored | 2,946 (6 legs × 4 entries) | 6,890 (14 legs × 4 entries) | 6,890 |
| 0.30 cut: fire / no-fire agreement | 93–95 % by class | **96.7 %** | 93.1 % |
| both fired, same minute | not reported; median \|Δt\| 1–2 min | **69 %** | 53 % |
| both fired, within 1 minute | — | **78 %** | 68 % |
| both fired, within 5 minutes | — | 87 % | 83 % |
| print fired, proxy never | 61 / 47 / 39 of 982 per class (4–6 %) | 111 of 6,890 (**1.6 %**) | 456 (6.6 %) |
| proxy fired, print never | 6 / 3 / 11 of 982 (0.3–1.1 %) | 116 (1.7 %) | 19 (0.3 %) |
| bias of the misses | one direction — the uncounted stop-outs sit on winning days | symmetric | proxy under-fires |

Sources: on-box `docs/measurement/estimated-mark-path-2026-09-01.md` §3 (on
the branch); master `docs/measurement/estimated-mark-path-2026-09-11.md` §4.

## Close-mark residual — measured, both builds

On-box (2026, ~10 ITM class): median |resid| 1.99 pts, signed +4.5 % of
entry. Master (2026 holdout, all bins): median −0.03 pts, MAE 1.59 pts; by
bin the ITM calls carry a positive median residual (+0.9 to +1.7 pts at +5
to +20 ITM) and the ITM puts a small negative one (−0.07 to −0.23). Master's
per-bin table is the one to read for a blotter row: the bias has a sign per
side and it is stated per bin.

## Decision

**Master's build is the Estimated Mark Path.** It wins the number the bead
was written for — the proxy fires the 0.30 cut in the same minute as the
prints 69 % of the time and within a minute 78 % of the time, with misses
under 2 % in either direction — because it marks at the minute's ES extreme,
which is what a resting stop sees; the on-box build marks the close only
and under-counts stop-outs by 4–6 % of leg-days, on the days that then paid.
Master also refuses what it has not fitted and carries the coverage bound
inside its numbers.

The on-box build stays on its branch as reference, unmerged. Its two ideas
that master does not have — a delta that follows the option's *current*
moneyness along the path, and a per-minute drift term — are the first things
to try if the ITM-call close bias in master's §5 turns out to matter to a
row. That is a later bead, filed only if a consumer needs it.

## What lands with this note

- `data/measurement/estimated-mark-calibration-2025.json` — the 2025 fit
  (146 days) the holdout validation used.
- `data/measurement/estimated-mark-calibration-2026-09-11.json` — the
  operative calibration, all 270 scoreable days through 2026-08-14; the
  blotter's estimated rows read this one.
- `data/measurement/estimated-mark-validation-2026-09-11.jsonl` — 15,049
  scored leg-days.
- `docs/measurement/estimated-mark-path-2026-09-11.md` — the generated
  write-up, coverage bound first.

The standing contract is unchanged: estimated blotter rows carry
`exit_reason=time` only and every aggregate splits by mark path. The
write-up's §4 tables are what a relaxation would be ruled on, bin by bin.
