# V-Day Definition (v0)

**Status:** v0 — reframed for the 13:00–15:00 CT data we currently have.
**Bead:** [st-r2o](../../.beads/) — V-drop-and-recovery detection.
**Date:** 2026-05-24.

## Purpose

Label each trading day in the corpus as a **V-day** or **non-V-day** so downstream measurement work (greek correlation, base-rate study, pattern validation against jass's three-phase narrative) can run against a clean population.

## Scope and inputs

- Corpus: `data/corpus/YYYY-MM-DD/`
- 250 trading days (approximately 2025-05-23 → 2026-05-22)
- Primary data source: `data/corpus/YYYY-MM-DD/databento_glbx_es.jsonl`
  - ES.c.0 continuous front-month, GLBX.MDP3 trades schema
  - Window covered: **[13:00, 15:00) CT only** — this is the binding constraint that drove the v0 reframe; see *Known limitation* below
- ES is the standard SPX proxy (≈ 0.25 pt tracking error during RTH); all price units in this document are ES points

## Conventions

- All times in US/Central (CT)
- All prices in ES.c.0 points
- A "trading day" is a single RTH session; days with manifest errors on the ES stream are excluded a priori

## Windows

| Symbol | Window | Role |
|---|---|---|
| **P** | [13:00, 13:30) CT | Pre-V baseline — establishes the reference price ("the neck") |
| **A** | [13:30, 15:00) CT | Action window — where the V plays out |
| **t_close** | last trade in [14:55, 15:00) CT | Close measurement — settling tick before bell |

## Reference price (VWAP_p)

Volume-weighted average price over **P**:

```
VWAP_p = Σ(price · size) / Σ(size)     for all ES.c.0 trades in [13:00, 13:30) CT
```

This is the "neck" of the V — the level a centered butterfly placed at 13:30 CT would be priced around. It is the v0 substitute for morning-VWAP; see *Known limitation*.

Also recorded for diagnostics:
- `range_p` = max(price) − min(price) over P (proxy for baseline tightness)

## Late-day extrema (over A)

```
trough_p = min(price) over A
trough_t = timestamp of first trade at trough_p
peak_p   = max(price) over A
peak_t   = timestamp of first trade at peak_p
close_p  = last trade price in [14:55, 15:00) CT
```

## LATR_20 (late-day ATR proxy)

Classical Wilder ATR requires daily OHLC; we only have ES trades for the late-day window, so we use a window-restricted analogue:

```
late_range_d = max(price) − min(price) over [13:00, 15:00) CT for day d
LATR_20      = mean(late_range_d) over the prior 20 trading days
```

For days where fewer than 20 prior days are available (start of corpus), `LATR_20` is undefined and the day is **excluded from labeling** rather than flagged. Expect ~20 unlabeled days at the back of the corpus.

## V-day criteria

A day is **V-down** iff ALL of:

1. `trough_t ≥ 13:30 CT` (in A, not in P)
2. `trough_p < VWAP_p` (price actually drops below the neck)
3. **Depth**: `(VWAP_p − trough_p) ≥ 0.6 × LATR_20`
4. **Recovery**: `(close_p − trough_p) ≥ 0.5 × (VWAP_p − trough_p)`
5. **Landing**: `|close_p − VWAP_p| ≤ 0.3 × LATR_20`

A day is **V-up** (inverted-V, symmetric per 2026-05-24 decision) iff ALL of:

1. `peak_t ≥ 13:30 CT`
2. `peak_p > VWAP_p`
3. **Depth**: `(peak_p − VWAP_p) ≥ 0.6 × LATR_20`
4. **Recovery**: `(peak_p − close_p) ≥ 0.5 × (peak_p − VWAP_p)`
5. **Landing**: `|close_p − VWAP_p| ≤ 0.3 × LATR_20`

A day is a **V-day** if it satisfies V-down OR V-up. Both arms run independently against every day; in the rare case both fire (price both dropped and rallied around the neck), label = `v_both`.

## Parameter starting values (tunable)

| Parameter | Symbol | Start | Rationale |
|---|---|---|---|
| Baseline window | P | [13:00, 13:30) CT | 30 min is short enough to establish a reference before A but long enough to volume-weight meaningfully |
| Action window | A | [13:30, 15:00) CT | 90 min — gives the V room to develop and recover |
| Close measurement | t_close | last trade in [14:55, 15:00) CT | Settling tick |
| Depth threshold | `d_min` | 0.6 × LATR_20 | Higher coefficient than the morning-VWAP version (was 0.4 × full ATR) because LATR is roughly half of full-day ATR — calibrates to a comparable absolute depth |
| Recovery threshold | `r_min` | 0.5 (50% retrace) | Half-recovery is the minimum that re-prices a centered fly meaningfully |
| Landing threshold | `l_max` | 0.3 × LATR_20 | Close must land within ~30% of typical late-day range from the neck — keeps the centered fly winning |

**Calibration target:** ~20–40% of days flagged. Sweep one knob at a time; validate per *Validation protocol*.

## Output schema

One row per trading day → `data/measurement/v_days.jsonl`:

```json
{
  "date": "2026-05-22",
  "label": "v_down" | "v_up" | "v_both" | "none" | "unlabeled",
  "vwap_p": 7505.12,
  "range_p": 2.50,
  "trough_p": 7495.25, "trough_t": "13:42:33-05:00",
  "peak_p":   7510.50, "peak_t":   "14:15:11-05:00",
  "close_p":  7503.00,
  "latr_20":  12.40,
  "v_down":   { "depth": 9.87, "recovery": 7.75, "landing": 2.12,
                "criteria": { "in_A": true, "below_vwap": true,
                              "depth_ok": true, "recovery_ok": true,
                              "landing_ok": true } },
  "v_up":     { "depth": 5.38, "recovery": 7.50, "landing": 2.12,
                "criteria": { "in_A": true, "above_vwap": true,
                              "depth_ok": false, "recovery_ok": true,
                              "landing_ok": true } }
}
```

Per-rule diagnostic flags let us debug parameter sensitivity without re-running the detector. `unlabeled` is reserved for days lacking 20 prior days of LATR data.

## Validation protocol

1. Run detector on the full 250-day corpus → label set
2. Sample 5 V-labeled days and 5 non-V days at random
3. Generate ES chart screenshots for each (`tools/tv_capture/tv_capture.py`, 5-min bars, 13:00–15:00 CT)
4. Eyeball-check: does the detector's verdict agree with what we see?
5. If agreement < 80%, identify which knob is mis-tuned, adjust, re-run
6. Freeze parameters once agreement ≥ 80%; record final values + validation evidence at the bottom of this doc

## Known limitation (v0)

**v0 only catches the post-13:00 subset of the doctrine pattern.** The full doctrine setup (CLAUDE.md, jass three-phase) is *morning consolidation → afternoon V → recovery toward morning consolidation*. v0 substitutes a 30-minute pre-V baseline [13:00, 13:30) for the morning consolidation because we don't have morning ES trades.

Days where the consolidation broke down before 13:00 (e.g., the move started at 12:30 CT) will have their baseline established *inside* the move, and v0 will likely false-negative them. Conservative estimate: v0 misses 20–40% of true doctrine-V days.

False positives in the opposite direction are also possible: a day that genuinely consolidates 10:00–13:00 then drifts (no clean V) might still produce a v0 V-label if the [13:00, 13:30) baseline is tight by coincidence.

**Mitigation:** Use v0 as a coarse filter; manually review the labeled set against TradingView screenshots before trusting it for downstream measurement work.

**Upgrade path (v1):** Reopen st-r2o.1 if calibration plateaus or if base-rate analysis shows the v0 detector is too noisy to support clean greek correlation. v1 = ES backfill extended to 08:30 CT (~$50 spend), reference moves back to morning VWAP_c, full doctrine fidelity.

## Open questions

- Should depth/recovery be measured in $ butterfly P&L instead of price units? Closer to operational signal but requires a centered-fly pricing model (BS calculator + IV surface).
- Should trough/peak be measured at 1-min OHLC bars instead of every tick? Reduces sensitivity to outlier prints.
- Should we add a "tightness gate" on `range_p` to filter days where the pre-V baseline itself was already volatile (signal of a move already underway)?
- Should V-days be sub-classified by *time-of-trough* — early (13:30–14:00), mid (14:00–14:30), late (14:30–15:00)? Probably yes once we have the labeled set in hand.

## Calibration log

| Run | Params | Days labeled | V-down | V-up | V-both | Agreement vs eyeball | Notes |
|---|---|---|---|---|---|---|---|
| _pending_ | _starting values above_ | — | — | — | — | — | — |

(Update after first calibration run; this table tracks the tuning history.)
