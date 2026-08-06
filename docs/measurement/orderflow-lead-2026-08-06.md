# Orderflow — decoding the 34 scalars, and does flow lead price? [st-ek8b]

**Bead:** Orderflow Lead Study (st-ek8b) · **Date:** 2026-08-06
**Data:** `Z:\Harvest\gexbot-hist\<date>\orderflow_orderflow.json.gz`, plus
`state_*` / `classic_*` files from the same day-dirs for the cross-package
identity tests. Part A samples 12 days spread over the archive (2026-05-07 →
2026-08-05); Part B uses 2 flush days + 5 control days.
**Script:** `scripts/measurement/orderflow_lead.py` → `data/measurement/orderflow-decode-stats.json`.
Every number below is printed by one run of it. `data/` is untracked, so this
document is the record.

## Headline

**Part A: the package is now decoded, and most of it is not new data.** Sixteen
of twenty-two candidate identities hold *exactly* — to the vendor's own 2-decimal
publication rounding, on all 12 sampled days. Eight of the 34 scalars are price
levels republished verbatim from the `state` package. Six more are literal
first differences of six other fields in the same snapshot, carrying zero
information beyond them. `zgr`/`ogr` are the State-methodology volume-based
total GEX to within 1 part in 10⁴. That leaves **`zcvr`/`ocvr` as the only
fields whose meaning remains genuinely unknown**, and the DEX family as the only
substantial *new* content in the package.

**Part B: flow does not lead price. This is a clean null, and it is
decision-grade.** Across 182 signal-days (7 days × 13 signals × 2 smoothing
windows), the peak cross-correlation with forward spot returns sits at a lead of
0 or ±1 second in 88 of 182 cases, and the best correlation anywhere in the
tradeable 5–300 s band is **0.0945** (R² = 0.9%). Against a properly calibrated
cross-day null, **3.3% of same-day signal-days exceed the null's 95th
percentile — against the 5.0% expected if there is no relationship at all.**
The flow signals predict the *next* day's prices exactly as well as they predict
their own day's. There is real, strong *contemporaneous* coupling (|r| up to
0.497 at lead 0), but it is coincident, not leading.

Neither flush day was distinguishable from the controls on any measure. The
control day 2026-07-16 has the strongest coupling in the whole study.

---

## 0. What the archive actually contains — a schema correction

The vendor-docs survey (`docs/gexbot/vendor-docs-survey-2026-08-06.md` §8.2)
reads the spec's `orderflow_response` as 48 properties: 14 shared with
`basic_response` plus the 34 orderflow scalars, and concludes "an orderflow
snapshot carries a full per-strike GEX ladder *plus* the flow metrics. It is not
a narrow add-on feed."

**Measured: the `/hist` orderflow payload carries 37 keys, not 48.** Every
snapshot on all 12 sampled days holds exactly `timestamp`, `ticker`, `spot` and
the 34 scalars. There is **no `strikes` ladder**, no `sum_gex_vol`, no
`zero_gamma`, no `min_dte`/`sec_min_dte`, no `delta_risk_reversal`. The eleven
other `basic_response` fields are absent.

This is consistent with the survey's own §6 warning that the spec documents only
the `/hist` *envelope* and says nothing about the file behind the signed URL —
the live REST response and the historical file are not the same shape. It is
also why the orderflow files are 12 MB/day against 60–109 MB for the ladder
packages. Practical consequence: orderflow is a **narrow scalar feed** in the
archive, and any study needing per-strike orderflow structure must read the
`state_*` files alongside it (which is exactly what makes the cross-package
identity tests below possible).

### Session coverage and cadence

| Day | Snapshots | First → last (CT) | Median gap | Max gap |
|---|---|---|---|---|
| 2026-05-07 | 21,275 | 09:05:03 → 15:00:00 | 1 s | 2 s |
| 2026-05-20 | 23,373 | 08:30:02 → 15:00:00 | 1 s | 2 s |
| 2026-06-03 | 23,374 | 08:30:02 → 15:00:00 | 1 s | 2 s |
| 2026-06-11 | 23,373 | 08:30:02 → 15:00:00 | 1 s | 2 s |
| 2026-06-24 | 23,373 | 08:30:02 → 15:00:00 | 1 s | 2 s |
| 2026-07-02 | 23,373 | 08:30:02 → 15:00:00 | 1 s | 2 s |
| 2026-07-08 | 23,374 | 08:30:02 → 15:00:00 | 1 s | 2 s |
| 2026-07-15 | 17,844 | 08:30:02 → 15:00:00 | 1 s | 3 s |
| 2026-07-22 | 17,897 | 08:30:03 → 15:00:00 | 1 s | 3 s |
| 2026-07-27 | 18,010 | 08:30:02 → 15:00:00 | 1 s | 3 s |
| 2026-07-31 | 17,836 | 08:30:02 → 15:00:00 | 1 s | 3 s |
| 2026-08-05 | 17,654 | 08:30:02 → 15:00:00 | 1 s | 2 s |

Two things the dataset survey's "~17,286 snapshots per day" figure does not
capture. **The cadence changed during the archive window**: May and June days
carry ~23,373 snapshots at an effectively unbroken 1 s (23,398 s in the session,
so ≥99.8% coverage), while July days carry ~17,850 at a mean gap of 1.31 s with
a 3 s maximum. The feed thinned by roughly a quarter somewhere between 2026-07-08
and 2026-07-15. **And 2026-05-07 is a partial day** — it begins at 09:05:03 CT,
missing the first 35 minutes. It is the oldest day in the archive and sits at the
edge of the vendor's 90-day window; treat it as incomplete rather than as a
short session.

Part B forward-fills onto a strict 1 s grid and records the carried fraction:
0.1% on 2026-07-06, 23–24% on the July days. Any index-based lag on the raw
snapshot array would be a 1.31 s lag on those days, not 1 s — which is why every
lead/lag number here is computed on the time grid.

---

## 1. Part A — the field guide

### 1.1 Method

Three independent lines of evidence, because none alone is sufficient when the
vendor publishes nothing:

**Identities.** Exact algebraic relations, tested on every snapshot of every
sampled day. Three families: within-snapshot sums (does call + put equal the
total?), between-snapshot differences (is a field literally the first difference
of another?), and **cross-package** (does the field equal a field the vendor
*does* name, in the `state_*`/`classic_*` file at the identical timestamp?).
Values are published to 2 decimals, so a residual ≤ 0.011 is exact up to
publication rounding. An exact match to a vendor-named field is the strongest
evidence obtainable without asking the vendor.

**Behaviour.** The variance ratio VR(k) = Var(x_{t+k} − x_t) / (k · Var(x_{t+1} −
x_t)). For a series with i.i.d. increments VR(k) ≈ 1; for a series that is
*already* a first difference VR(k) ≈ 1/k; below 1 means mean reversion, above 1
means trending increments. This separates cumulative from oscillating
arithmetically rather than by eyeballing a chart. Reported alongside an
efficiency ratio (net displacement ÷ total path length) and the reset test.

**Coupling.** Correlation with spot level, with 1 s spot returns, and with the
field's 0DTE/second-expiry partner — each reported as the cross-day median plus
a sign-consistency score (the fraction of the 12 days agreeing on sign).

### 1.2 The identity results — the strongest evidence in the study

Worst case across all 12 days. "EXACT" means every snapshot of every sampled day
matched to within publication rounding.

| Verdict | Identity | Max residual | Fraction exact |
|---|---|---|---|
| **EXACT** | `agg_dex` = `agg_call_dex` + `agg_put_dex` | 0.01 | 1.0000 |
| **EXACT** | `net_dex` = `net_call_dex` + `net_put_dex` | 0.01 | 1.0000 |
| **EXACT** | `one_agg_dex` = `one_agg_call_dex` + `one_agg_put_dex` | 0.01 | 1.0000 |
| **EXACT** | `one_net_dex` = `one_net_call_dex` + `one_net_put_dex` | 0.01 | 1.0000 |
| **EXACT** | `dexoflow`[t] = `agg_dex`[t] − `agg_dex`[t−1] | 0.01 | 1.0000 |
| **EXACT** | `gexoflow`[t] = `zgr`[t] − `zgr`[t−1] | 0.01 | 1.0000 |
| **EXACT** | `cvroflow`[t] = `zcvr`[t] − `zcvr`[t−1] | 0.01 | 1.0000 |
| **EXACT** | `one_dexoflow`[t] = `one_agg_dex`[t] − `one_agg_dex`[t−1] | 0.01 | 1.0000 |
| **EXACT** | `one_gexoflow`[t] = `ogr`[t] − `ogr`[t−1] | 0.01 | 1.0000 |
| **EXACT** | `one_cvroflow`[t] = `ocvr`[t] − `ocvr`[t−1] | 0.01 | 1.0000 |
| **EXACT** | `z_mlgamma` = `state_gamma_zero.major_long_gamma` | 0.00 | 1.0000 |
| **EXACT** | `z_msgamma` = `state_gamma_zero.major_short_gamma` | 0.00 | 1.0000 |
| **EXACT** | `o_mlgamma` = `state_gamma_one.major_long_gamma` | 0.00 | 1.0000 |
| **EXACT** | `o_msgamma` = `state_gamma_one.major_short_gamma` | 0.00 | 1.0000 |
| **EXACT** | `zero_mcall` = `state_gex_zero.major_pos_vol` | 0.00 | 1.0000 |
| **EXACT** | `zero_mput` = `state_gex_zero.major_neg_vol` | 0.00 | 1.0000 |
| **EXACT** | `one_mcall` = `state_gex_one.major_pos_vol` | 0.00 | 1.0000 |
| **EXACT** | `one_mput` = `state_gex_one.major_neg_vol` | 0.00 | 1.0000 |
| near | `zgr` ≈ `state_gex_zero.sum_gex_vol` | 50.53 | corr ≥ 0.999995 |
| near | `ogr` ≈ `state_gex_one.sum_gex_vol` | 209.37 | corr ≥ 0.997265 |
| **no** | `zgr` = `classic_gex_zero.sum_gex_vol` | 2,144,694 | corr 0.21–0.90 |
| **inconclusive** | `zcvr` = `state_gex_zero.sum_gex_oi` | — | see below |

Four consequences, in order of how much they change what we can do:

**1. The six `*oflow` fields are pure redundancy.** Each is the arithmetic
first difference of another field in the same feed, exactly, on every snapshot of
every day. `dexoflow` carries nothing `agg_dex` does not; `gexoflow` nothing
`zgr` does not; `cvroflow` nothing `zcvr` does not. The bead's instruction to
"difference any cumulative fields first" turns out to describe a step the vendor
has already performed and shipped as six extra columns. Note also that they are
differences **per snapshot, not per second** — on a 3 s gap the field reports the
3-second change with no normalisation, so a naive read treats a slow-publish tick
as a flow spike.

Independent confirmation from the behaviour side, with no reference to the
identity test: all six have VR(60) ≈ 0.012–0.017 and VR(300) ≈ 0.002–0.003, and
1/60 = 0.0167 and 1/300 = 0.0033 are the exact theoretical values for a
first-differenced series. Two unrelated methods agree.

**2. `ml`/`ms` are settled, and the vendor doc's guess was wrong in a useful
way.** §8.2 offers "`ml`/`ms` plausibly read as *max long*/*max short*". The
exact cross-package match shows they are the `state` package's own
`major_long_gamma` / `major_short_gamma` — **major**, not max. This is not a
quibble: it means the four `*gamma` scalars are not new measurements at all, but
a verbatim republication of a `state` field, and the `state_gamma_*` files are
the authoritative source with the vendor's own name attached.

**3. `gr` is GEX, not "gamma ratio".** `zgr` tracks `state_gex_zero.sum_gex_vol`
at correlation ≥ 0.999995 across all 12 days, with a median absolute residual of
2.0–3.5 on values in the thousands (relative max residual ≤ 1.7 × 10⁻²). The
survey's suggested reading of `cvr`/`gr` as *ratios* is refuted for `gr`: it is a
volume-based total gamma exposure. `ogr` is the same for the second expiry at a
looser but still decisive match (corr ≥ 0.997).

**And it matches the State package, not Classic** — against
`classic_gex_zero.sum_gex_vol` the correlation is 0.21–0.90 and residuals run to
2.1 million. Per the principals' documented methodology (survey §4), State
classifies each trade buy/sell against a vol surface and accumulates *signed*
customer positioning, while Classic increments volume naively. So **the orderflow
package is built on the signed State methodology.** That is a material fact about
what the DEX fields mean, established by measurement rather than assumed.

**4. The `zcvr` test was inconclusive, not negative — and it exposed a wider
schema landmine.** `state_gex_zero.sum_gex_oi` cannot be compared to anything,
because it is **identically zero on every snapshot of every sampled day**. The
same is true of `state_gex_zero.delta_risk_reversal` and `state_gex_zero.zero_gamma`.
Classic populates all three. The dataset survey (§ "Schema landmine") documented
this for `zero_gamma`; **measured here, the dead-in-State set is at least three
fields wide, not one.** Any join reading `sum_gex_oi` or `delta_risk_reversal`
from a `state_*` file is silently reading zeros.

Tested against Classic instead, `zcvr` correlates +0.83 with
`classic_gex_zero.sum_gex_vol` on 2026-06-11 and +0.32 on 2026-07-22; `ocvr`
runs −0.90 then −0.30. Correlations that swing that far across two days are not
an identity. **`zcvr`/`ocvr` remain genuinely unknown** — the one real gap left.

### 1.3 The field guide

Cross-day medians over the 12 sampled days. "Typical |x|" is the median absolute
value. Confidence: **measured** = exact identity or direct measurement;
**supported inference** = near-identity or a measurement consistent across all
12 days, where the *semantic label* is still interpretation; **unknown** = no
evidence either way.

| Field | Behaviour (VR60) | Typical \|x\| | What was measured | Best-supported reading | Confidence |
|---|---|---|---|---|---|
| `z_mlgamma` | price-level (0.13) | 7464.81 | = `state_gamma_zero.major_long_gamma`, exact | 0DTE major **long**-gamma price level | measured |
| `z_msgamma` | price-level (0.12) | 7459.24 | = `state_gamma_zero.major_short_gamma`, exact | 0DTE major **short**-gamma price level | measured |
| `o_mlgamma` | price-level (0.19) | 7467.73 | = `state_gamma_one.major_long_gamma`, exact | same, second expiry | measured |
| `o_msgamma` | price-level (0.17) | 7532.12 | = `state_gamma_one.major_short_gamma`, exact | same, second expiry | measured |
| `zero_mcall` | price-level (0.02) | 7482.50 | = `state_gex_zero.major_pos_vol`, exact; 79–96% of values are exact 5-point strikes, the rest sit just above one (7505.08, 7505.26 …) | 0DTE major positive-GEX **level**, usually but not always on a strike | measured (identity) / supported inference (the "call wall" gloss) |
| `zero_mput` | price-level (0.02) | 7440.00 | = `state_gex_zero.major_neg_vol`, exact | 0DTE major negative-GEX strike ("put wall") | measured / supported inference |
| `one_mcall` | price-level (0.03) | 7545.00 | = `state_gex_one.major_pos_vol`, exact | same, second expiry | measured / supported inference |
| `one_mput` | price-level (0.03) | 7395.00 | = `state_gex_one.major_neg_vol`, exact | same, second expiry | measured / supported inference |
| `zgr` | cumulative, noisy (0.18) | 2556.80 | ≈ `state_gex_zero.sum_gex_vol`, corr ≥ 0.999995; r(level, spot) +0.83, sign-consistent 12/12 | 0DTE total volume-based GEX, State (signed) methodology | measured (near-identity) |
| `ogr` | cumulative, trending (1.68) | 495.84 | ≈ `state_gex_one.sum_gex_vol`, corr ≥ 0.997; r(level, spot) +0.90 | second-expiry total volume-based GEX | measured (near-identity) |
| `zcvr` | cumulative, noisy (0.21) | 1738.19 | no stable cross-package match; corr with Classic `sum_gex_vol` swings +0.83 → +0.32 across two days | **unknown** — not a ratio (unbounded, ±10⁴), not `sum_gex_oi` | unknown |
| `ocvr` | cumulative, random-walk (1.04) | 807.28 | as above, corr −0.90 → −0.30 | **unknown**, second expiry | unknown |
| `zvanna` | cumulative, mean-reverting (0.47) | 361.02 | r(Δ, 1s return) **+0.244, sign-consistent 12/12** — the strongest contemporaneous coupling of any field | 0DTE vanna exposure accumulator | supported inference |
| `ovanna` | cumulative, mean-reverting (0.64) | 310.10 | r(level, spot) +0.83; r(Δ, return) +0.213, 11/12 | second-expiry vanna exposure | supported inference |
| `zcharm` | cumulative, noisy (0.12) | 58.66 | efficiency 0.589 — by far the most one-directional field; magnitude reaches ±10⁶ late in the day | 0DTE charm accumulator; decays hard into expiry | supported inference |
| `ocharm` | cumulative, mean-reverting (0.63) | 3.88 | r(level, spot) +0.84; ~15× smaller than `zcharm` | second-expiry charm | supported inference |
| `agg_dex` | cumulative, random-walk (0.94) | 1185.25 | = `agg_call_dex` + `agg_put_dex`, exact; opens at 0.00 | aggregate delta exposure, 0DTE | supported inference |
| `agg_call_dex` | cumulative, random-walk (0.95) | 707.10 | component of the above | call-side aggregate DEX | supported inference |
| `agg_put_dex` | cumulative, random-walk (0.99) | 738.57 | component of the above | put-side aggregate DEX | supported inference |
| `net_dex` | cumulative, random-walk (0.76) | 1190.57 | = `net_call_dex` + `net_put_dex`, exact; ≈ Σ column 3 of `state_delta_zero.mini_contracts` (see below) | net delta exposure, 0DTE | supported inference |
| `net_call_dex` | cumulative, mean-reverting (0.70) | 476.54 | component of the above | call-side net DEX | supported inference |
| `net_put_dex` | cumulative, random-walk (0.77) | 791.35 | component of the above | put-side net DEX | supported inference |
| `one_agg_dex` | cumulative, random-walk (1.03) | 593.85 | = call + put, exact | second-expiry aggregate DEX | supported inference |
| `one_agg_call_dex` | cumulative, random-walk (1.08) | 232.33 | component | — | supported inference |
| `one_agg_put_dex` | cumulative, random-walk (1.02) | 675.70 | component | — | supported inference |
| `one_net_dex` | cumulative, random-walk (1.10) | 585.99 | = call + put, exact | second-expiry net DEX | supported inference |
| `one_net_call_dex` | cumulative, random-walk (1.06) | 257.69 | component | — | supported inference |
| `one_net_put_dex` | cumulative, random-walk (1.09) | 668.89 | component | — | supported inference |
| `dexoflow` | first difference (0.017) | 5.50 | ≡ Δ`agg_dex`, exact | per-snapshot change in `agg_dex` — **redundant** | measured |
| `gexoflow` | first difference (0.012) | 31.74 | ≡ Δ`zgr`, exact; r(Δ, return) +0.139, 12/12 | per-snapshot change in 0DTE GEX — **redundant** | measured |
| `cvroflow` | first difference (0.012) | 22.30 | ≡ Δ`zcvr`, exact | per-snapshot change in `zcvr` — **redundant** | measured |
| `one_dexoflow` | first difference (0.017) | 0.41 | ≡ Δ`one_agg_dex`, exact | **redundant** | measured |
| `one_gexoflow` | first difference (0.017) | 0.65 | ≡ Δ`ogr`, exact | **redundant** | measured |
| `one_cvroflow` | first difference (0.016) | 0.64 | ≡ Δ`ocvr`, exact | **redundant** | measured |

**`net_dex` and the per-strike ladder.** Summing column 3 of
`state_delta_zero.mini_contracts` across strikes reproduces `net_dex` closely at
sampled timestamps on 2026-07-22 (263.56 vs 263.73; −929.02 vs −935.05; −2827.77
vs −2819.68; −5578.75 vs −5555.13; −7370.6 vs −7286.57). The residual grows
through the day, so this is a near-match rather than an identity — but it
supports reading `net_dex` as the strike-summed net 0DTE delta exposure, and
identifies **column 3 of `mini_contracts` as per-strike net DEX**, which the
dataset survey lists as unknown. The nested 3-element array in that row trails
the current value (−7160 / −6959 / −5784 against a current −7370), consistent
with the lookback reading the survey calls plausible-but-unconfirmed.

### 1.4 The `agg` vs `net` distinction — measured but not explained

Both families exist for 0DTE and second expiry, both satisfy the call+put sum
identity exactly, and both are cumulative random walks opening at zero. They are
*not* redundant with each other, and their relationship is not stable: on
2026-07-22 they correlate +0.9989 with a maximum divergence of 1,128; on
2026-07-31, +0.53 with a maximum divergence of 3,494. Neither is monotone (the
share of upward moves among non-zero moves is 0.49–0.51 for both, i.e.
symmetric).

So `agg` is not "the absolute-value accumulator" and `net` is not "the signed
one" — both are signed. What actually distinguishes them is not recoverable from
the archive. **This is the sharpest vendor question in the study**, because the
DEX family is the only substantial new content the package carries and half of it
is a duplicate of unknown character.

### 1.5 Operational traps

1. **Daily reset is real and total.** All 26 flow scalars and the four `*_mcall`/
   `*_mput` levels open at exactly `0.00` on the day's first snapshot, on 10 of
   12 sampled days. The two exceptions are explained, not counterexamples:
   2026-05-07 is a partial day starting 09:05, and 2026-07-22's first snapshot is
   at 08:30:03, three seconds after the open, by which time small values have
   accrued. Everything in this package is a since-the-open accumulator.
2. **The four `*gamma` level fields open on a stale placeholder.** They never
   open at zero — they open at a value 3–4% *below* spot (7205.00 against a spot
   of 7462.13 on 2026-07-31; 7045.00 against 7299.56 on 2026-06-11). The stale
   value clears within **0–6 seconds**, so the practical rule is to discard the
   first ~10 seconds of each session rather than to distrust the field.
3. **`*oflow` are per-snapshot, not per-second.** On July days with 3 s gaps, the
   field reports a 3-second change unnormalised. Divide by the actual timestamp
   gap before treating any of them as a rate.
4. **Three `state_gex_*` fields are identically zero** — `sum_gex_oi`,
   `delta_risk_reversal`, `zero_gamma`. Read them from `classic_*`.
5. **The `o_`/`one_` fields have no partner column in the table** because the
   partner map runs 0DTE → second-expiry; their `r_partner` is n/a by
   construction, not a failed measurement.

---

## 2. Part B — does flow lead price into flushes?

### 2.1 The flush windows, and the structural problem they create

Quoted from `docs/measurement/morning-flush-anatomy.md` §1 (primary-move census,
ES.c.0 tape, 08:30–10:30 CT). Not re-derived here.

| Day | Net | Range | Primary move | Dir | Span | Retrace |
|---|---|---|---|---|---|---|
| 2026-07-22 | +29.25 | 34.25 | 34.25 | **up** | 08:30 → 10:27 | 0.09 |
| 2026-07-31 | −44.25 | 87.75 | 87.75 | **dn** | 08:34 → 09:16 | 0.63 |

Two things must be said plainly before any result is read.

**First, "the two flush days" is not what the census says these are.** By the
same table, 2026-07-22's primary morning move is 34.25 points **upward** — the
joint-smallest of the 22 July days — while 2026-07-31's is 87.75 points down, the
second-largest. They are not a matched pair of flush days. 2026-07-22 earns the
flush label from a different document and a different scale:
`docs/measurement/orderflow-fundamental-units.md` §2.1 reads it as a **flush-leg
→ steady-leg → leg-grind → steady-leg** sequence and calls its 08:30 bar "the
flagship 2026-07-22 08:30 flush-and-recover atom (net +2.75, range 8.25,
effort_pct 99.7)". So on 07-22 the flush is a **single opening bar**, not the
day's primary move. Any comparison that treats these two days as one category is
comparing an opening-bar spike with a 42-minute 88-point collapse.

**Second, and more consequentially: this feed cannot see the run-up to either
flush.** The orderflow feed is RTH-only, first snapshot 08:30:02–08:30:03 CT.
2026-07-22's window opens at 08:30 — *before* the first snapshot, so the
requested "15 minutes before flush start" contains **zero seconds of data** and
the event-anchored z-score returns `outside session`. 2026-07-31's opens at
08:34, leaving **238 seconds** of the requested 900. Neither documented flush has
a complete pre-window, and no amount of care in the analysis creates one.

That is not a reason to skip the test — it is a reason to be explicit that the
event-anchored part of Part B is under-powered by construction, and to supply
events that *do* have a pre-window. A supplementary detector (clearly not ground
truth) flags trailing-15-minute declines of ≥ 20 SPX points in the feed's own
spot series, de-duplicated to one per 30 minutes. It finds 6 events across the 7
days, 3 of which have a complete 900 s pre-window.

**Control days:** 2026-07-06, 07-15, 07-16, 07-21, 07-30 — July days from the
same census, mid-pack move sizes, no documented flush anatomy. 2026-07-03 would
have been the quietest control (12.50 pts) but is absent from the archive.

### 2.2 Method

Signals are the differenced cumulative fields, since Part A shows nearly
everything in the package is an accumulator. **Differenced:** `agg_dex`,
`net_dex`, `net_call_dex`, `net_put_dex`, `zgr`, `zcvr`, `zvanna`, `zcharm`,
`one_agg_dex`, `ogr`. **Used raw** (already first differences, per §1.2):
`dexoflow`, `gexoflow`, `cvroflow`. Each at two smoothing windows — the raw 1 s
change and a 60 s rolling sum. 13 signals × 2 windows × 7 days = 182 signal-days.

Everything is computed on a strict 1 s RTH grid with forward fill. The
cross-correlation against 1 s spot returns is evaluated at **every** lead from
−300 s to +300 s by FFT, so no lead is sampled or interpolated. **Positive lead
means flow leads price**; negative means price leads flow. Both halves are always
reported, because "which one leads" is the entire question.

Two further quantities: the correlation of each signal against the *cumulative*
forward return over 5/15/30/60/120/300 s (the practically meaningful form), and a
price-versus-price baseline (spot returns against their own future) so the flow
numbers can be read against what price predicts about itself.

### 2.3 The null had to be rebuilt — and that is a finding

Taking the maximum |correlation| over 601 leads inflates the statistic, so it
needs a null. The first attempt shifted the signal circularly against price
within the day and re-took the maximum. **It was beaten by 37.9% of signal-days
against a nominal 5%** — the null was mis-calibrated, not the signals strong.
Narrowing the shifts to ±10–60 minutes improved it only to 30.2%.

The cause is structural: both the flow signals and spot returns carry the same
strong intraday volatility profile (heavy at the open and the close, quiet
midday). Any shift large enough to break the lead relationship also misaligns
those profiles, so the null covariance is deflated and everything looks
significant.

The fix is to keep both series intact and break only the pairing: **correlate
each day's flow signal against a *different* day's spot returns, aligned on clock
second.** Each series retains its own autocorrelation and time-of-day profile
exactly, and no true relationship can exist. 7 days give 42 mismatched pairs per
signal, 1,092 null values in total.

Recording this because the first two nulls would each have supported a positive
claim. The result below survives only because the null was fixed, and a study
that reported the shift-null numbers would have announced a lead that is not
there.

### 2.4 Results — the null

**The calibrated test:**

| | Peak \|corr\| over leads 5–300 s |
|---|---|
| **Null** (1,092 mismatched day-pairs) | median 0.0251 · **p95 0.0668** · max 0.1059 |
| **Observed** (182 same-day signal-days) | median **0.0249** · max **0.0945** |
| Observed above the null's p95 | **3.3%** |
| Expected if flow does not lead price | 5.0% |

The observed distribution is not merely indistinguishable from the null — it sits
very slightly *below* it. A flow signal predicts a randomly chosen different
day's prices as well as it predicts its own day's.

**Where the peaks actually are.** Of 182 signal-days, **88 peak at a lead of 0 or
±1 second**. The global peak correlations are substantial — up to +0.4965
(`d_zvanna@1s`, 2026-07-16) — but they are *contemporaneous*: flow and price move
within the same second, which is what one expects of fields derived from the same
option tape that price itself drives. Restricted to leads of ≥ 5 s, where a
signal could actually be acted on, the same 182 signal-days give a median |r| of
0.0249 and a maximum of 0.0945 (R² = 0.9%), and that maximum is peak-picked over
296 leads.

**Per day**, best contemporaneous coupling against best strictly-leading:

| Day | | Price-vs-price baseline | Best at lead 0 | Best at lead ≥ 5 s |
|---|---|---|---|---|
| 2026-07-22 | FLUSH | 0.0269 @ +2 s | `d_zvanna` **+0.1860** | `gexoflow` −0.0671 @ +55 s |
| 2026-07-31 | FLUSH | 0.0520 @ +1 s | `d_zvanna` **+0.2521** | `d_ogr` +0.0860 @ +133 s |
| 2026-07-06 | ctrl | 0.0322 @ −3 s | `d_zgr` +0.1438 | `d_zcharm` +0.0759 @ +7 s |
| 2026-07-15 | ctrl | 0.0449 @ −1 s | `d_zgr` +0.3249 | `d_zcharm` −0.0671 @ +27 s |
| 2026-07-16 | ctrl | 0.0318 @ −1 s | `d_zvanna` **+0.4965** | `d_zcharm` −0.0545 @ +63 s |
| 2026-07-21 | ctrl | 0.0299 @ +3 s | `d_zvanna` +0.2249 | `d_zcharm` −0.0945 @ +60 s |
| 2026-07-30 | ctrl | 0.0453 @ −1 s | `d_zvanna` +0.3970 | `d_zcharm` −0.0559 @ +99 s |

**Flush days are not distinguishable from controls.** Median |r| at lead 0 is
0.0429 on flush days against 0.0442 on controls; the maxima run 0.2521 (flush)
against 0.4965 (control). In the leading band the maxima are 0.0860 against
0.0945. If anything the controls couple *more* strongly. The hypothesis that
flush days show a flow lead that ordinary days do not is refuted on this sample.

**The surviving leading correlations are noise, and they look like noise.** The
same signal flips sign at similar leads across days: `d_zgr` gives +0.0411 at
+298 s on 07-21 and −0.0472 at +241 s on 07-30; `d_zcharm` gives +0.0759 at +7 s
on 07-06 and −0.0945 at +60 s on 07-21. Peak leads scatter across the entire grid
(+7, +27, +55, +60, +63, +99, +133 s) with no clustering. A real mechanism would
put the same sign at a similar lead on most days.

**Forward-return correlations agree.** Across the five headline 60 s signals × six
horizons × seven days (210 values), correlations span −0.1082 to +0.1224. Two
signals do show a consistent sign — `d_zgr@60s` is negative at the 60 s horizon on
7 of 7 days, `d_agg_dex@60s` positive on 6 of 7 — but the magnitudes never exceed
0.102 in absolute value, so the largest implies R² ≈ 1%. `d_zcvr@60s` changes sign
between days. Nothing there is tradeable, and nothing contradicts the
cross-correlation result. The two sign-consistent signals are the only thing in
Part B worth a second look, and they are noted as directional-only below.

### 2.5 Event-anchored view

For each event, the 60 s rolling signal at the anchor second, standardised
against that day's own distribution with the event window excluded so the event
does not set the scale it is judged against.

| Day | Event | Anchor | Pre-window available | Largest \|z\| |
|---|---|---|---|---|
| 2026-07-22 | documented flush | 08:30 | **0 s of 900** | *no data — anchor precedes first snapshot* |
| 2026-07-31 | documented flush | 08:34 | 238 s of 900 | `d_agg_dex` −0.46 |
| 2026-07-31 | down-leg (suppl.) | 08:30 | 12 s | `d_net_call_dex` −1.67 |
| 2026-07-31 | down-leg (suppl.) | 09:00 | **900 s (complete)** | `d_ogr` +1.89 |
| 2026-07-31 | down-leg (suppl.) | 10:14 | **900 s (complete)** | `d_agg_dex` +1.04 |
| 2026-07-15 | down-leg (suppl.) | 08:36 | 370 s | `d_one_agg_dex` +0.90 |
| 2026-07-16 | down-leg (suppl.) | 08:30 | 0 s | `d_net_put_dex` +2.03 |
| 2026-07-30 | down-leg (suppl.) | 09:36 | **900 s (complete)** | `d_zvanna` +0.99 |

Across all 91 (event × signal) cells the median |z| is **0.30**, the 90th
percentile 1.10, and the maximum 2.03. **Only 1.1% of cells exceed |z| = 2**,
against roughly 4.6% expected if the values were standard normal. Flow at flush
onset is *less* extreme relative to the day's own distribution than chance would
produce, not more. There is no deterioration or divergence to quantify.

The two largest readings (+2.03 and −1.67) both sit on 08:30 anchors with zero
pre-window, i.e. on the opening seconds where the accumulators have just reset —
the least trustworthy moment in the day for a z-score against a full-day
distribution.

### 2.6 Verdict

**Decision-grade: flow does not lead price at any horizon between 5 and 300
seconds, on these 7 days.** The claim rests on a properly calibrated null
(observed 3.3% exceedance against 5.0% expected), a maximum leading correlation
of 0.0945 that is peak-picked over 296 leads and below the null's own maximum of
0.1059, sign inconsistency across days, and no flush/control separation. This is
strong enough to close the hypothesis rather than park it. The st-g3yh / st-863b
/ st-88ei idea that orderflow gives the flush watcher a *leading* input is
refuted; a *confirming* one is untested here and remains open.

**Directional-only:**

- **The contemporaneous coupling is real but its size is not established.**
  |r| at lead 0 reaches 0.4965 and the strongest couplings (`zvanna`, `zgr`) are
  sign-consistent on 12 of 12 Part A days. But it varies by a factor of ~2.7
  across seven days with no explanation, and coincident correlation is not
  evidence of anything causal in either direction.
- **The 07-22 vs 07-31 comparison should not be repeated as posed.** They are
  not the same kind of event at the same scale, and neither has a usable
  pre-window in this feed.
- **The supplementary down-leg events are a detector output, not ground truth.**
  Six events on seven days, three with complete pre-windows, is a pilot.
- **Two forward-return signs are consistent across all seven days** —
  `d_zgr@60s` negative at the 60 s horizon (7/7) and `d_agg_dex@60s` positive
  (6/7). Seven days is far too few to call this, and the magnitudes (|r| ≤ 0.102,
  R² ≈ 1%) are not tradeable on their own. It is the one thread in Part B worth
  re-testing on the full 62 days, and it is a *sign* claim, not a lead claim —
  it does not resurrect the leading hypothesis.

**What would change the verdict:** a genuine lead confined to the first minutes
of the session — which is precisely where this feed cannot look, since the
accumulators reset at 08:30 and the documented flushes begin at 08:30 and 08:34.
Nothing here rules out a pre-open or opening-seconds effect. It rules out a lead
during the session, which is what was asked.

---

## 3. Vendor questions

Ordered by how much the answer would change what we do. The first is worth asking
on its own; the rest can ride along.

1. **What distinguishes `agg_*_dex` from `net_*_dex`?** Both are signed, both are
   cumulative, both satisfy call+put exactly, and their correlation ranges from
   +0.9989 to +0.53 across two days. This is the only substantial new content in
   the package and half of it is uninterpretable.
2. **What are `zcvr` and `ocvr`?** The only fields with no measured reading at
   all. Is `cvr` a convexity measure, a call/put volume ratio, something else?
   Note they are unbounded (±10⁴) and cumulative, so "ratio" is already doubtful.
3. **Are the six `*oflow` fields intended to be exact first differences?** They
   are, on every snapshot of 12 days. Confirming it is deliberate — rather than
   an artefact we should not depend on — would let us drop six columns.
4. **Are `*oflow` per-snapshot or per-second?** Measured as per-snapshot,
   unnormalised, so a 3 s publication gap reports a 3 s change. Confirm.
5. **Why do `state` responses carry `sum_gex_oi`, `delta_risk_reversal` and
   `zero_gamma` as identically zero?** Not orderflow-specific, but it is a live
   defect in a paid feed and we have measured its extent.
6. **What are the units** of the DEX and GEX fields — shares, contracts, notional
   dollars? Unstated everywhere, and it blocks any absolute-size interpretation.
7. **Is the orderflow `/hist` payload intended to omit the `strikes` ladder** and
   the other ten `basic_response` fields the spec's `orderflow_response`
   declares? (§0.)
8. **Did the publication cadence change around 2026-07-08 → 07-15?** Snapshot
   counts drop from ~23,373/day to ~17,850/day and the maximum gap goes 2 s → 3 s.

## 4. What to measure next

1. **Re-point consumers at the authoritative source.** Eight orderflow fields are
   verbatim copies of `state_*` fields that carry the vendor's own names, and six
   more are redundant differences. Anything reading `z_mlgamma` should read
   `state_gamma_zero.major_long_gamma`. This also shrinks what a future
   orderflow reader has to support to: `agg_*`/`net_*` DEX, `zcvr`/`ocvr`,
   `zvanna`/`ovanna`, `zcharm`/`ocharm`, `zgr`/`ogr`.
2. **Widen the schema-landmine audit.** Three `state_gex_*` fields are dead, not
   one. Sweep every field of every package for identically-zero columns across
   the 62 days — it is one pass over data we already hold, and it protects every
   join in the program. Feeds directly into st-roj9.
3. **Test orderflow as a *confirming* input, not a leading one.** The refuted
   claim is that flow leads price. Whether flow *state* at a signal moment
   discriminates outcome is a different question and the natural join is the one
   st-trbn is already set up for: 353 recognizer confirms against flow at the
   confirm second.
4. **Re-test the two sign-consistent forward-return signals on all 62 days.**
   `d_zgr@60s` negative at 60 s (7/7) and `d_agg_dex@60s` positive (6/7) is the
   only pattern in Part B that did not dissolve. The script already takes a
   `--control-days` list, so this is one longer run, not new code. Expect it to
   evaporate; it is cheap to find out.
5. **If the lead question is revisited, it needs the pre-open.** Both documented
   flushes begin at or within four minutes of the bell, and this feed starts at
   08:30. That is a live-capture decision during the Quant month, not something
   the archive can answer.
6. **Ask the vendor.** Question 1 above is worth an email on its own.

---

## Method caveats

- **Seven days is seven days.** The null is calibrated and the effect size is
  small enough that the conclusion is unlikely to reverse, but the cross-day null
  draws its 1,092 pairs from 7 days, so those pairs are not independent.
- **Correlation only.** No non-linear or threshold relationship was tested. A
  flow signal that matters only in its extreme tail would not appear here.
- **SPX spot from the orderflow feed**, not ES tape. The flush windows are
  defined on ES; the lead/lag is measured on SPX spot as published in this feed.
  The two are not the same instrument and the mapping was not verified.
- **Forward-fill on the 1 s grid** carries 23–24% of July grid seconds. A carried
  second contributes a zero change to a differenced signal, which biases
  correlations toward zero — a conservative direction for a null result, but not
  a neutral one.
- **The 2026-07-22 event-anchored row is empty**, not zero. Its flush window
  opens before the feed does.
