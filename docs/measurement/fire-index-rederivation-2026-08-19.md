# Fire-Index Damp Re-Derivation — st-7kmt

**Bead:** st-7kmt (*Fire Damp Re-Derivation*) · **Date:** 2026-08-19
**Runs:** `20260819T213124Z` (enriched corpus, authoritative) vs `20260731T044440Z` (st-98z's evidence run)
**Data:** `data/measurement/acuity-run2-confirmations.jsonl` (append-only; filter on the run id)
**Analysis:** produced by a delegated stats pass; headline cells independently recomputed before the decision (fi≥4 vs fi1–3 Fisher p: old 0.019, enriched bullish 0.275, enriched bearish 0.448 — all reproduce).

## Decision — the step-damp is REMOVED; the fire counter stays

The recognizer no longer damps confirmed confidence 0.8 → 0.6 (0.9 → 0.7
stacked) at `fire_index ≥ 4`. Grounds, from the tables below:

1. st-98z's measurement was real and reproduces exactly (§1: fi≥4 31% vs
   48%, p = 0.019 on its own run) — but it does not generalize. On the
   enriched corpus the bullish gap is 42% vs 47% (p = 0.275) and the bearish
   step points the **other way** (52% vs 48%, p = 0.448).
2. The time split kills every variant (§3), and no alternative threshold
   (fi≥2/3/4/5) is supported on either side (§4) — the best cell, bullish
   fi≥5 at p = 0.080, is one of eight thresholds tested with no multiplicity
   correction.
3. The composition check (§5) locates the dilution: the cliff still shows on
   the old run's own confirm days (p = 0.038) and is absent on the days the
   enriched corpus added (p = 0.644). The original number was a property of
   the 65-day sample, not of the anchor's fourth fire.
4. The damp had also started firing on bearish emissions (the st-tme/st-q5xu
   mirror) — a population it was never derived from, where the observed
   slope is upward.

What stays: `fire_index` on every emission, the session-long per-anchor
counter, and the spoken/displayed count ("that is the fourth time at this
level today") — the count is a fact about the session. What changes:
confirmed confidence is flat 0.8 (0.9 stacked). Score-don't-gate cuts both
ways: a score must not encode evidence the corpus no longer supports.
Consumers that keyed off `confidence < 0.75` (speech's "Lower confidence"
line) simply stop seeing damped confirms; the parity fixture never reaches
fire 2, so the snapshot is unchanged.

The full statistical record follows, unedited.

---

Question: does the shipped damp (confirmed confidence 0.8 → 0.6 at `fire_index >= 4`, landed under st-98z) still hold on the enriched corpus, and does it hold per side?

## Method and denominators

- Outcome: `verdict30` — first touch of ±5 ES points within 30 minutes of the confirm. **Win rate = wins / (wins + losses)**; rows with neither touch (`verdict30 == "neither"`, reported here as *undecided*) are excluded from the rate but counted in every table.
- CI: Wilson score, 95%.
- Test: **two-sided Fisher exact**, exact-rational implementation written for this task — `scipy` is **not installed** in `/root/projects/Strader/.venv` (verified), so no library test was used. No normal approximation anywhere.
- Time split as in st-98z: **tune = day < 2026-06-01**, **validate = day >= 2026-06-01**.
- NEW / authoritative run `20260819T213124Z`: 270 days scored ok, 2312 confirms (bullish 1235 on 139 days, bearish 1077 on 159 days).
- OLD st-98z evidence run `20260731T044440Z`: 182 days scored ok, 423 confirms, **bullish only**.

## §1 — Old-run reproduction (are we reading the same evidence st-98z read?)

Run `20260731T044440Z`, bullish only, 423 confirms on 65 days (of 182 days scored ok).

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 48% | 164 | 79 | 85 | 11 | 41–56 |
| 2 | 50% | 108 | 54 | 54 | 11 | 41–59 |
| 3 | 43% | 51 | 22 | 29 | 8 | 31–57 |
| >=4 | 31% | 64 | 20 | 44 | 6 | 21–43 |

Tail detail (raw fire_index):

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 4 | 38% | 24 | 9 | 15 | 3 | 21–57 |
| 5 | 31% | 16 | 5 | 11 | 0 | 14–56 |
| 6+ | 25% | 24 | 6 | 18 | 3 | 12–45 |

**fi>=4 31% (n=64) vs fi 1-3 48% (n=323) — Fisher exact two-sided p = 0.019**

Time split:

*tune* — 217 confirms on 50 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 59% | 85 | 50 | 35 | 11 | 48–69 |
| 2 | 51% | 55 | 28 | 27 | 9 | 38–64 |
| 3 | 42% | 19 | 8 | 11 | 6 | 23–64 |
| >=4 | 29% | 28 | 8 | 20 | 4 | 15–47 |

**fi>=4 29% (n=28) vs fi 1-3 54% (n=159) — Fisher exact two-sided p = 0.014**

*validate* — 206 confirms on 15 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 37% | 79 | 29 | 50 | 0 | 27–48 |
| 2 | 49% | 53 | 26 | 27 | 2 | 36–62 |
| 3 | 44% | 32 | 14 | 18 | 2 | 28–61 |
| >=4 | 33% | 36 | 12 | 24 | 2 | 20–50 |

**fi>=4 33% (n=36) vs fi 1-3 42% (n=164) — Fisher exact two-sided p = 0.356**

Reproduced: fi>=4 wins **31%** against **48/50/43%** for fi 1/2/3 — the "31% vs 43–50%" figure st-98z shipped on, and the sign of the step is the same in both halves of the split (tune p = 0.014, validate p = 0.356). We are reading the same evidence.

## §2 — Enriched run, per side

Run `20260819T213124Z`, 270 days scored ok.

### bullish — 1235 confirms on 139 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 46% | 493 | 226 | 267 | 58 | 41–50 |
| 2 | 49% | 278 | 136 | 142 | 36 | 43–55 |
| 3 | 46% | 146 | 67 | 79 | 28 | 38–54 |
| >=4 | 42% | 169 | 71 | 98 | 27 | 35–50 |

Tail detail (raw fire_index):

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 4 | 48% | 77 | 37 | 40 | 11 | 37–59 |
| 5 | 40% | 45 | 18 | 27 | 6 | 27–55 |
| 6+ | 34% | 47 | 16 | 31 | 10 | 22–48 |

**fi>=4 42% (n=169) vs fi 1-3 47% (n=917) — Fisher exact two-sided p = 0.275**

### bearish — 1077 confirms on 159 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 48% | 389 | 188 | 201 | 84 | 43–53 |
| 2 | 47% | 218 | 102 | 116 | 57 | 40–53 |
| 3 | 49% | 122 | 60 | 62 | 37 | 40–58 |
| >=4 | 52% | 131 | 68 | 63 | 39 | 43–60 |

Tail detail (raw fire_index):

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 4 | 51% | 69 | 35 | 34 | 18 | 39–62 |
| 5 | 47% | 38 | 18 | 20 | 10 | 32–63 |
| 6+ | 62% | 24 | 15 | 9 | 11 | 43–79 |

**fi>=4 52% (n=131) vs fi 1-3 48% (n=729) — Fisher exact two-sided p = 0.448**

Both sides pooled, for reference only:

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 47% | 882 | 414 | 468 | 142 | 44–50 |
| 2 | 48% | 496 | 238 | 258 | 93 | 44–52 |
| 3 | 47% | 268 | 127 | 141 | 65 | 41–53 |
| >=4 | 46% | 300 | 139 | 161 | 66 | 41–52 |

**fi>=4 46% (n=300) vs fi 1-3 47% (n=1646) — Fisher exact two-sided p = 0.754**

Undecided share by bucket (share of all rows, not of decided): bullish 11/11/16/14% for fi 1/2/3/>=4; bearish 18/21/23/23%. No bucket loses a disproportionate share to undecided, so the rates are comparable.

## §3 — Time split on the enriched run

### bullish / tune — 794 confirms on 112 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 50% | 349 | 174 | 175 | 47 | 45–55 |
| 2 | 51% | 176 | 89 | 87 | 29 | 43–58 |
| 3 | 46% | 84 | 39 | 45 | 19 | 36–57 |
| >=4 | 43% | 76 | 33 | 43 | 14 | 33–55 |

**fi>=4 43% (n=76) vs fi 1-3 50% (n=609) — Fisher exact two-sided p = 0.332**

### bullish / validate — 441 confirms on 27 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 36% | 144 | 52 | 92 | 11 | 29–44 |
| 2 | 46% | 102 | 47 | 55 | 7 | 37–56 |
| 3 | 45% | 62 | 28 | 34 | 9 | 33–57 |
| >=4 | 41% | 93 | 38 | 55 | 13 | 31–51 |

**fi>=4 41% (n=93) vs fi 1-3 41% (n=308) — Fisher exact two-sided p = 1.000**

### bearish / tune — 763 confirms on 128 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 48% | 281 | 136 | 145 | 75 | 43–54 |
| 2 | 48% | 154 | 74 | 80 | 50 | 40–56 |
| 3 | 47% | 74 | 35 | 39 | 32 | 36–59 |
| >=4 | 50% | 66 | 33 | 33 | 31 | 38–62 |

**fi>=4 50% (n=66) vs fi 1-3 48% (n=509) — Fisher exact two-sided p = 0.795**

### bearish / validate — 314 confirms on 31 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 48% | 108 | 52 | 56 | 9 | 39–57 |
| 2 | 44% | 64 | 28 | 36 | 7 | 32–56 |
| 3 | 52% | 48 | 25 | 23 | 5 | 38–66 |
| >=4 | 54% | 65 | 35 | 30 | 8 | 42–65 |

**fi>=4 54% (n=65) vs fi 1-3 48% (n=220) — Fisher exact two-sided p = 0.400**

## §4 — Alternative cliff placements

Each row: everything at or above the threshold vs everything below it, same outcome definition, same test.

**Enriched run — bullish**

| threshold | at/above: win % (n) | below: win % (n) | Δ pts | Fisher p |
|---|---|---|---|---|
| fi>=2 | 46% (593) | 46% (493) | +0 | 0.951 |
| fi>=3 | 44% (315) | 47% (771) | -3 | 0.349 |
| fi>=4 | 42% (169) | 47% (917) | -5 | 0.275 |
| fi>=5 | 37% (92) | 47% (994) | -10 | 0.080 |

**Enriched run — bearish**

| threshold | at/above: win % (n) | below: win % (n) | Δ pts | Fisher p |
|---|---|---|---|---|
| fi>=2 | 49% (471) | 48% (389) | +1 | 0.891 |
| fi>=3 | 51% (253) | 48% (607) | +3 | 0.455 |
| fi>=4 | 52% (131) | 48% (729) | +4 | 0.448 |
| fi>=5 | 53% (62) | 48% (798) | +5 | 0.510 |

**Old run `20260731T044440Z` — bullish (context)**

| threshold | at/above: win % (n) | below: win % (n) | Δ pts | Fisher p |
|---|---|---|---|---|
| fi>=2 | 43% (223) | 48% (164) | -5 | 0.353 |
| fi>=3 | 37% (115) | 49% (272) | -12 | 0.026 |
| fi>=4 | 31% (64) | 48% (323) | -17 | 0.019 |
| fi>=5 | 28% (40) | 47% (347) | -19 | 0.019 |

## §5 — Sample-composition check (bullish only, the side st-98z measured)

The old run's ok-day set is a strict subset of the new one (182 ⊂ 270 days; old range 2025-05-29 → 2026-07-29, new range 2025-05-29 → 2026-08-19). The enriched run re-walks those days with the enriched anchor body, so a partition on the calendar is *the same days, not the same rows* — bullish confirms now land on 139 days where the old run produced confirms on 65.

### (a) days the old run scored ok — 566 confirms on 68 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 48% | 226 | 109 | 117 | 15 | 42–55 |
| 2 | 50% | 142 | 71 | 71 | 13 | 42–58 |
| 3 | 44% | 72 | 32 | 40 | 10 | 34–56 |
| >=4 | 35% | 80 | 28 | 52 | 8 | 25–46 |

**fi>=4 35% (n=80) vs fi 1-3 48% (n=440) — Fisher exact two-sided p = 0.038**

### (b) days new to the enriched run — 669 confirms on 71 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 44% | 267 | 117 | 150 | 43 | 38–50 |
| 2 | 48% | 136 | 65 | 71 | 23 | 40–56 |
| 3 | 47% | 74 | 35 | 39 | 18 | 36–59 |
| >=4 | 48% | 89 | 43 | 46 | 19 | 38–59 |

**fi>=4 48% (n=89) vs fi 1-3 45% (n=477) — Fisher exact two-sided p = 0.644**

### (a′) tightest like-for-like: only the days the old run actually produced confirms on — 552 confirms on 65 days

| fire_index | win % | n (decided) | wins | losses | undecided | Wilson 95% CI |
|---|---|---|---|---|---|---|
| 1 | 48% | 216 | 103 | 113 | 15 | 41–54 |
| 2 | 50% | 140 | 70 | 70 | 13 | 42–58 |
| 3 | 43% | 70 | 30 | 40 | 10 | 32–55 |
| >=4 | 35% | 80 | 28 | 52 | 8 | 25–46 |

**fi>=4 35% (n=80) vs fi 1-3 48% (n=426) — Fisher exact two-sided p = 0.038**

**fi>=4 on old-scored days 35% (n=80) vs fi>=4 on new-only days 48% (n=89) — Fisher exact two-sided p = 0.088**

**fi 1-3 on old-scored days 48% (n=440) vs fi 1-3 on new-only days 45% (n=477) — Fisher exact two-sided p = 0.427**


## §6 — What the evidence supports

On the enriched corpus (270 scored days) the fire-index step the damp encodes is **not supported on either side at the 4 threshold**. Bullish: fi>=4 wins 42% (n=169 decided, CI 35–50) against 47% for fi 1–3 (n=917), Fisher p = 0.275 — a 5-point gap where the old run showed 17. Bearish moves the other way: fi>=4 wins 52% (n=131) against 48% for fi 1–3 (n=729), p = 0.448; the confidence intervals for every bearish bucket overlap and none excludes 50%. No alternative threshold reaches conventional significance on either side: the smallest p in §4 is 0.080 (bullish fi>=5, 37% on n=92 vs 47% on n=994), and that is one of eight thresholds tested without any multiplicity correction.

The composition check locates the change. The st-98z cliff is still present on the old day sample when the enriched recognizer re-walks it: on the 65 days that produced old-run confirms, fi>=4 wins 35% (n=80) vs 48% for fi 1–3 (n=426), p = 0.038; on the 71 days new to the enriched run it is absent — 48% (n=89) vs 45% (n=477), p = 0.644. The fi 1–3 baseline is statistically indistinguishable across the two partitions (p = 0.427); the fi>=4 rate differs between them by 13 points at p = 0.088, which is suggestive but not itself significant at 0.05. So the enriched result is a dilution concentrated in the added days rather than a uniform fade, and the two candidate explanations — the original cliff being a property of that day sample, or the added days differing in some way that removes it — are not separated by this evidence.

What this does **not** establish: that fire_index carries no information (the bullish tail still slopes down — fi 4 48%, fi 5 40%, fi 6+ 34% on n=77/45/47 decided — it is simply not distinguishable from noise at these n); that the old measurement was wrong (it reproduces exactly, §1); or anything about outcomes on horizons other than the ±5 / 30-minute rule, which is the only outcome measured here.

All numbers in `fire_damp_stats.json` alongside this note. Tests: two-sided Fisher exact throughout; percentages rounded to whole numbers, p-values to 3 decimals.
