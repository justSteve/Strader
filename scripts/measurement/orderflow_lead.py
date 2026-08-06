#!/usr/bin/env python3
"""Orderflow lead study — decode the 34 scalars, test flow-leads-price. [st-ek8b]

The GexBot `orderflow` package ships 34 scalars with **zero** vendor
documentation: not one carries a description in the OpenAPI spec, the README,
websocket.md, the reference downloader, or the principals' Discord archive
(docs/gexbot/vendor-docs-survey-2026-08-06.md §8.2, §10.1). This script is the
empirical substitute.

PART A — decode. Three independent lines of evidence per field:

  identities     exact algebraic relations inside a snapshot (call+put sums)
                 and between snapshots (are the `*oflow` fields simply first
                 differences of a level field?), plus cross-package identity
                 against state_*/classic_* files at the same timestamps. An
                 exact match to a field the vendor *does* name is the strongest
                 evidence available without asking the vendor.
  behaviour      variance-ratio classification. For a series whose increments
                 are i.i.d., Var(x_{t+k}-x_t) grows linearly in k, so
                 VR(k) = Var(Δ_k x) / (k · Var(Δ_1 x)) ≈ 1. A series that is
                 *already* a first difference has VR(k) ≈ 1/k. A mean-reverting
                 level sits between. This separates cumulative from oscillating
                 without eyeballing a chart.
  coupling       correlation with spot level, with 1s spot returns, and with
                 the field's own 0DTE/1DTE partner.

PART B — does flow lead price? Cross-covariance between each candidate flow
signal and 1s spot returns over a lead grid of −300..+300 s at 1s resolution,
computed by FFT so every lead is exact rather than sampled. Negative leads mean
*price* leads *flow*; the sign of the peak is the whole question, so both halves
are always reported.

Two honesty mechanics that decide whether the result is decision-grade:

  peak-picking null   taking the max |corr| over 601 leads inflates the
                      statistic. The null here is a circular shift of the
                      signal against price: because a circular cross-covariance
                      over all n lags is one FFT, the null distribution of
                      "max over a 601-wide lead window" is obtained by sliding
                      that window to random far-away offsets — exact, and
                      essentially free. p = P(null peak ≥ observed peak).
  block bootstrap     a stationary block bootstrap (block ≈ 300 s) on the peak
                      correlation, because 23,400 one-second samples are
                      nowhere near 23,400 independent observations.

Flush windows are NOT re-derived here. They are quoted from
docs/measurement/morning-flush-anatomy.md §1 (primary-move census, ES 08:30 -
10:30 CT), and the structural problem they create — both flush windows open at
or within four minutes of the 08:30 bell, while this feed is RTH-only — is
reported rather than papered over. A supplementary same-feed down-leg detector
(clearly labelled, not ground truth) supplies events that *do* have a pre-window.

Usage:
    .venv/bin/python3 scripts/measurement/orderflow_lead.py            # all
    .venv/bin/python3 scripts/measurement/orderflow_lead.py --part a
    .venv/bin/python3 scripts/measurement/orderflow_lead.py --no-cross-package

Output: data/measurement/orderflow-decode-stats.json + stderr progress.
The results doc is docs/measurement/orderflow-lead-2026-08-06.md.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = Path("/mnt/z/Harvest/gexbot-hist")
OUT = REPO / "data/measurement/orderflow-decode-stats.json"

# CDT. Every day in the 62-day archive (2026-05-07 .. 2026-08-05) is inside US
# daylight time, so a fixed -5 offset is correct here and avoids a tz dependency.
# It would be wrong for a November day; assert the archive range before reusing.
CT = timezone(timedelta(hours=-5))

RTH_OPEN_S = 8 * 3600 + 30 * 60          # 08:30:00 CT, seconds from midnight
RTH_CLOSE_S = 15 * 3600                  # 15:00:00 CT

# ---------------------------------------------------------------- day sets

# Part A sample: 12 days spread across all three months of the archive, chosen
# to span the primary-move size range in morning-flush-anatomy.md §1 — quiet
# (07-15, 34.25 pts) through the two largest (07-27, 91.0; 07-31, 87.75).
DECODE_DAYS = [
    "2026-05-07", "2026-05-20", "2026-06-03", "2026-06-11",
    "2026-06-24", "2026-07-02", "2026-07-08", "2026-07-15",
    "2026-07-22", "2026-07-27", "2026-07-31", "2026-08-05",
]

# Part B. Flush days are the two named in the bead; controls are July days from
# the same census with mid-pack move sizes and no documented flush anatomy.
# 2026-07-03 would have been the quietest control (12.50 pts) but is absent from
# the archive.
FLUSH_DAYS = ["2026-07-22", "2026-07-31"]
CONTROL_DAYS = ["2026-07-06", "2026-07-15", "2026-07-16", "2026-07-21", "2026-07-30"]

# Quoted verbatim from docs/measurement/morning-flush-anatomy.md §1 (primary
# move = largest peak-to-trough or trough-to-peak travel inside 08:30-10:30 CT,
# measured on ES.c.0 tape, not on this feed's SPX spot). `size` is the move in
# ES points, `direction` its sign.
FLUSH_WINDOWS = {
    "2026-07-22": dict(start="08:30", end="10:27", size=34.25, direction="up",
                       source="morning-flush-anatomy.md §1"),
    "2026-07-31": dict(start="08:34", end="09:16", size=87.75, direction="dn",
                       source="morning-flush-anatomy.md §1"),
}

# ---------------------------------------------------------------- field groups

LEVEL_FIELDS = ["z_mlgamma", "z_msgamma", "o_mlgamma", "o_msgamma",
                "zero_mcall", "zero_mput", "one_mcall", "one_mput"]

FLOW_FIELDS = [
    "zcvr", "ocvr", "zgr", "ogr", "zvanna", "ovanna", "zcharm", "ocharm",
    "agg_dex", "one_agg_dex", "agg_call_dex", "one_agg_call_dex",
    "agg_put_dex", "one_agg_put_dex",
    "net_dex", "one_net_dex", "net_call_dex", "one_net_call_dex",
    "net_put_dex", "one_net_put_dex",
    "dexoflow", "gexoflow", "cvroflow",
    "one_dexoflow", "one_gexoflow", "one_cvroflow",
]

ALL_FIELDS = LEVEL_FIELDS + FLOW_FIELDS

# 0DTE field -> second-expiry field. The z_/zero_ vs o_/one_ split is the
# vendor doc's structural observation (§8.2); these pairings test it.
PARTNERS = {
    "z_mlgamma": "o_mlgamma", "z_msgamma": "o_msgamma",
    "zero_mcall": "one_mcall", "zero_mput": "one_mput",
    "zcvr": "ocvr", "zgr": "ogr", "zvanna": "ovanna", "zcharm": "ocharm",
    "agg_dex": "one_agg_dex", "agg_call_dex": "one_agg_call_dex",
    "agg_put_dex": "one_agg_put_dex",
    "net_dex": "one_net_dex", "net_call_dex": "one_net_call_dex",
    "net_put_dex": "one_net_put_dex",
    "dexoflow": "one_dexoflow", "gexoflow": "one_gexoflow",
    "cvroflow": "one_cvroflow",
}

# Within-snapshot sum identities to test: lhs == rhs[0] + rhs[1].
SUM_IDENTITIES = [
    ("agg_dex", "agg_call_dex", "agg_put_dex"),
    ("net_dex", "net_call_dex", "net_put_dex"),
    ("one_agg_dex", "one_agg_call_dex", "one_agg_put_dex"),
    ("one_net_dex", "one_net_call_dex", "one_net_put_dex"),
]

# Between-snapshot identities to test: oflow[t] == level[t] - level[t-1].
DIFF_IDENTITIES = [
    ("dexoflow", "agg_dex"),
    ("gexoflow", "zgr"),
    ("cvroflow", "zcvr"),
    ("one_dexoflow", "one_agg_dex"),
    ("one_gexoflow", "ogr"),
    ("one_cvroflow", "ocvr"),
]

# Cross-package identities: orderflow field -> (file stem, field). Every state
# category file carries the same scalar header, so the gamma file is used as the
# representative for the shared scalars.
CROSS_IDENTITIES = [
    ("z_mlgamma", "state_gamma_zero", "major_long_gamma"),
    ("z_msgamma", "state_gamma_zero", "major_short_gamma"),
    ("o_mlgamma", "state_gamma_one", "major_long_gamma"),
    ("o_msgamma", "state_gamma_one", "major_short_gamma"),
    ("zero_mcall", "state_gex_zero", "major_pos_vol"),
    ("zero_mput", "state_gex_zero", "major_neg_vol"),
    ("one_mcall", "state_gex_one", "major_pos_vol"),
    ("one_mput", "state_gex_one", "major_neg_vol"),
    ("zgr", "state_gex_zero", "sum_gex_vol"),
    ("ogr", "state_gex_one", "sum_gex_vol"),
    ("zcvr", "state_gex_zero", "sum_gex_oi"),
    ("zgr", "classic_gex_zero", "sum_gex_vol"),
]

# Values are published to 2 decimal places, so an identity that holds to 0.011
# is exact up to the publication rounding.
ROUND_TOL = 0.011

# ---------------------------------------------------------------- Part B knobs

LEAD_MAX = 300               # seconds each side of zero
LEAD_MIN_TRADEABLE = 5       # a 0-1s "lead" is contemporaneous, not actionable
FWD_HORIZONS = [5, 15, 30, 60, 120, 300]
SMOOTH_WINDOWS = [1, 60]     # rolling-sum windows applied to the flow signal
NULL_DRAWS = 2000            # circular-shift offsets for the peak-picking null
BOOT_DRAWS = 500
BOOT_BLOCK = 300             # seconds

# Candidate signals for Part B, as (name, source field, needs_differencing).
# Fields that Part A shows are already first differences are used raw; the
# cumulative levels are differenced first, which is the differencing step the
# bead asks to be stated explicitly.
PART_B_SIGNALS = [
    ("d_agg_dex", "agg_dex", True),
    ("d_net_dex", "net_dex", True),
    ("d_net_call_dex", "net_call_dex", True),
    ("d_net_put_dex", "net_put_dex", True),
    ("d_zgr", "zgr", True),
    ("d_zcvr", "zcvr", True),
    ("d_zvanna", "zvanna", True),
    ("d_zcharm", "zcharm", True),
    ("d_one_agg_dex", "one_agg_dex", True),
    ("d_ogr", "ogr", True),
    ("dexoflow", "dexoflow", False),
    ("gexoflow", "gexoflow", False),
    ("cvroflow", "cvroflow", False),
]

# Supplementary down-leg detector (NOT ground truth — see module docstring).
DOWNLEG_WINDOW_S = 900       # 15 minutes
DOWNLEG_DROP_PTS = 20.0      # SPX points over that window
DOWNLEG_SEPARATION_S = 1800  # de-duplicate to one event per 30 minutes


# ---------------------------------------------------------------- io helpers

def load_raw(day: str, stem: str, archive: Path) -> list[dict]:
    """Read one archive file. Names end .json.gz but most are plain JSON — the
    vendor's own downloader sniffs the gzip magic bytes rather than trusting the
    header (vendor-docs-survey §6), so do the same."""
    path = archive / day / f"{stem}.json.gz"
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def to_arrays(recs: list[dict], fields: list[str]) -> dict[str, np.ndarray]:
    out = {"timestamp": np.array([r["timestamp"] for r in recs], dtype=np.int64),
           "spot": np.array([r["spot"] for r in recs], dtype=float)}
    for f in fields:
        out[f] = np.array([r.get(f, np.nan) for r in recs], dtype=float)
    return out


def ct_seconds(ts: np.ndarray) -> np.ndarray:
    """Epoch seconds -> seconds since midnight CT."""
    return (ts + CT.utcoffset(None).total_seconds()) % 86400


def hhmm_to_s(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 3600 + int(m) * 60


# ---------------------------------------------------------------- Part A stats

def variance_ratio(x: np.ndarray, k: int) -> float:
    """VR(k) = Var(x_{t+k} - x_t) / (k · Var(x_{t+1} - x_t)).

    ≈1 for a random walk, ≈1/k for a series that is already a first difference,
    <1 for mean reversion, >1 for trending increments."""
    d1 = np.diff(x)
    v1 = d1.var()
    if not np.isfinite(v1) or v1 == 0 or len(x) <= k:
        return float("nan")
    dk = x[k:] - x[:-k]
    return float(dk.var() / (k * v1))


def safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) != len(b) or len(a) < 3:
        return float("nan")
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return float("nan")
    a, b = a[m], b[m]
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def field_stats(v: np.ndarray, spot: np.ndarray) -> dict:
    """Everything Part A measures about one field on one day."""
    finite = v[np.isfinite(v)]
    if len(finite) < 100:
        return {"n": int(len(finite))}
    d1 = np.diff(v)
    tot_travel = float(np.nansum(np.abs(d1)))
    st = {
        "n": int(len(v)),
        "first": float(v[0]),
        "last": float(v[-1]),
        "min": float(np.nanmin(v)),
        "p01": float(np.nanpercentile(v, 1)),
        "p50": float(np.nanpercentile(v, 50)),
        "p99": float(np.nanpercentile(v, 99)),
        "max": float(np.nanmax(v)),
        "mean": float(np.nanmean(v)),
        "std": float(np.nanstd(v)),
        "abs_median": float(np.nanmedian(np.abs(v))),
        # share of consecutive snapshots where the value moved at all
        "frac_changed": float(np.mean(d1 != 0)),
        # of the moves that happened, share that were upward: 0.5 = symmetric,
        # ->1 or ->0 = one-way accumulation
        "frac_up_of_moves": (float(np.mean(d1[d1 != 0] > 0))
                             if np.any(d1 != 0) else float("nan")),
        # net displacement as a share of total path length
        "efficiency": (abs(float(v[-1] - v[0])) / tot_travel
                       if tot_travel > 0 else float("nan")),
        "vr_10": variance_ratio(v, 10),
        "vr_60": variance_ratio(v, 60),
        "vr_300": variance_ratio(v, 300),
        "ar1_diff": safe_corr(d1[:-1], d1[1:]),
        "r_spot_level": safe_corr(v, spot),
        "r_diff_ret": safe_corr(d1, np.diff(spot)),
        # is this a price level rather than a flow quantity?
        "rel_dist_to_spot": float(np.nanmedian(np.abs(v - spot)) / np.nanmedian(spot)),
        "opens_at_zero": bool(abs(float(v[0])) < 1e-9),
    }
    return st


def classify(agg: dict) -> str:
    """Behaviour class from the cross-day medians. Thresholds are stated here
    rather than in prose so the label is reproducible from the numbers."""
    vr60, vr300 = agg.get("vr_60"), agg.get("vr_300")
    rel = agg.get("rel_dist_to_spot")
    if rel is not None and np.isfinite(rel) and rel < 0.02:
        return "price-level"
    if vr60 is None or not np.isfinite(vr60):
        return "unclassified"
    # a first difference of a random walk has VR(k) = 1/k exactly
    if vr60 < 0.05 and (vr300 is None or not np.isfinite(vr300) or vr300 < 0.01):
        return "first-difference (already differenced)"
    if vr60 >= 0.75:
        return "cumulative, random-walk-like"
    if vr60 >= 0.25:
        return "cumulative, mildly mean-reverting"
    return "cumulative, noisy (1s jitter reverts)"


def part_a(days: list[str], archive: Path, cross_package: bool) -> dict:
    per_day: dict[str, dict] = {}
    for day in days:
        recs = load_raw(day, "orderflow_orderflow", archive)
        A = to_arrays(recs, ALL_FIELDS)
        secs = ct_seconds(A["timestamp"])
        gaps = np.diff(A["timestamp"])
        row = {
            "n_snapshots": len(recs),
            "n_keys": len(recs[0]),
            "keys": sorted(recs[0].keys()),
            "first_ct": f"{int(secs[0])//3600:02d}:{int(secs[0])%3600//60:02d}:{int(secs[0])%60:02d}",
            "last_ct": f"{int(secs[-1])//3600:02d}:{int(secs[-1])%3600//60:02d}:{int(secs[-1])%60:02d}",
            "gap_median_s": float(np.median(gaps)),
            "gap_max_s": int(gaps.max()),
            "duplicate_timestamps": int((gaps == 0).sum()),
            "fields": {},
            "identities": {"sum": {}, "diff": {}, "cross_package": {}},
        }
        for f in ALL_FIELDS:
            row["fields"][f] = field_stats(A[f], A["spot"])
        for a, b in PARTNERS.items():
            row["fields"][a]["r_partner_level"] = safe_corr(A[a], A[b])
            row["fields"][a]["r_partner_diff"] = safe_corr(np.diff(A[a]), np.diff(A[b]))

        for lhs, r1, r2 in SUM_IDENTITIES:
            err = np.abs(A[lhs] - (A[r1] + A[r2]))
            row["identities"]["sum"][f"{lhs} == {r1} + {r2}"] = {
                "max_abs_resid": float(np.nanmax(err)),
                "frac_within_rounding": float(np.mean(err <= ROUND_TOL)),
            }
        for of, lvl in DIFF_IDENTITIES:
            err = np.abs(A[of][1:] - np.diff(A[lvl]))
            row["identities"]["diff"][f"{of}[t] == {lvl}[t] - {lvl}[t-1]"] = {
                "max_abs_resid": float(np.nanmax(err)),
                "frac_within_rounding": float(np.mean(err <= ROUND_TOL)),
            }

        if cross_package:
            cache: dict[str, list[dict]] = {}
            for ofield, stem, sfield in CROSS_IDENTITIES:
                try:
                    if stem not in cache:
                        cache[stem] = load_raw(day, stem, archive)
                    other = cache[stem]
                except FileNotFoundError:
                    continue
                if len(other) != len(recs):
                    row["identities"]["cross_package"][f"{ofield} == {stem}.{sfield}"] = {
                        "status": "length mismatch",
                        "n_orderflow": len(recs), "n_other": len(other)}
                    continue
                ts_match = np.array_equal(
                    A["timestamp"],
                    np.array([r["timestamp"] for r in other], dtype=np.int64))
                y = np.array([r.get(sfield, np.nan) for r in other], dtype=float)
                err = np.abs(A[ofield] - y)
                denom = np.nanmedian(np.abs(y))
                row["identities"]["cross_package"][f"{ofield} == {stem}.{sfield}"] = {
                    "timestamps_identical": bool(ts_match),
                    "max_abs_resid": float(np.nanmax(err)),
                    "median_abs_resid": float(np.nanmedian(err)),
                    "rel_max_resid": (float(np.nanmax(err) / denom)
                                      if denom and np.isfinite(denom) and denom != 0
                                      else float("nan")),
                    "frac_within_rounding": float(np.mean(err <= ROUND_TOL)),
                    "corr": safe_corr(A[ofield], y),
                }
            del cache
        per_day[day] = row
        print(f"[A] {day} n={len(recs)} {row['first_ct']}->{row['last_ct']}",
              file=sys.stderr)

    # cross-day aggregation: median of each statistic, plus sign consistency
    agg: dict[str, dict] = {}
    stat_keys = ["abs_median", "vr_10", "vr_60", "vr_300", "efficiency",
                 "frac_changed", "frac_up_of_moves", "ar1_diff",
                 "r_spot_level", "r_diff_ret", "rel_dist_to_spot",
                 "r_partner_level", "r_partner_diff"]
    for f in ALL_FIELDS:
        row = {}
        for k in stat_keys:
            vals = [per_day[d]["fields"][f].get(k) for d in days]
            vals = [v for v in vals if v is not None and np.isfinite(v)]
            if vals:
                row[k] = float(np.median(vals))
                row[k + "_n"] = len(vals)
                if k.startswith("r_"):
                    row[k + "_sign_consistency"] = float(
                        max(np.mean(np.array(vals) > 0), np.mean(np.array(vals) < 0)))
        opens = [per_day[d]["fields"][f].get("opens_at_zero") for d in days]
        row["frac_days_open_at_zero"] = float(np.mean([bool(o) for o in opens]))
        row["class"] = classify(row)
        agg[f] = row
    return {"per_day": per_day, "aggregate": agg, "days": days}


# ---------------------------------------------------------------- Part B core

def regular_grid(A: dict[str, np.ndarray]) -> dict:
    """Forward-fill snapshots onto a strict 1s RTH grid.

    Snapshot gaps run 1-3 s, so a raw index-based lag is not a time lag. Every
    lead/lag number in Part B is computed on this grid, and fill_fraction
    records how much of it is carried rather than observed."""
    secs = ct_seconds(A["timestamp"]).astype(np.int64)
    keep = (secs >= RTH_OPEN_S) & (secs < RTH_CLOSE_S)
    secs, order = secs[keep], np.argsort(secs[keep], kind="stable")
    secs = secs[order]
    grid = np.arange(secs[0], secs[-1] + 1, dtype=np.int64)
    # index of the most recent snapshot at or before each grid second
    idx = np.searchsorted(secs, grid, side="right") - 1
    out = {"grid_s": grid, "n": len(grid),
           "fill_fraction": float(1.0 - len(secs) / len(grid)),
           "observed": len(secs), "start_s": int(grid[0]), "end_s": int(grid[-1])}
    for k, v in A.items():
        if k == "timestamp":
            continue
        out[k] = v[keep][order][idx]
    return out


def circular_crosscov(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """c[l] = (1/n) Σ_t x_t · y_{(t+l) mod n}, for l = 0..n-1, via FFT.

    Circular (rather than zero-padded) because the wraparound is exactly what
    makes the shift null below both valid and free: every circular shift of the
    signal against price is already one entry of this array."""
    n = len(x)
    xs = x - x.mean()
    ys = y - y.mean()
    F = np.fft.rfft(xs, n)
    G = np.fft.rfft(ys, n)
    return np.fft.irfft(np.conj(F) * G, n) / n


def lead_profile(sig: np.ndarray, ret: np.ndarray, lead_max: int,
                 exclude_zero: bool = False) -> dict:
    """Cross-correlation of signal against 1s spot returns at every lead in
    [-lead_max, +lead_max], with a circular-shift null on the peak.

    Positive lead L: signal at t vs return at t+L, i.e. FLOW LEADS PRICE.
    Negative lead: price leads flow.

    `exclude_zero` drops lead 0, which is only needed for the price-vs-price
    baseline where lead 0 is the trivial r=1."""
    n = len(sig)
    sd = sig.std() * ret.std()
    if n < 4 * lead_max or sd == 0 or not np.isfinite(sd):
        return {"status": "insufficient data"}
    c = circular_crosscov(sig, ret) / sd          # index l == lead +l (mod n)
    leads = np.arange(-lead_max, lead_max + 1)
    prof = c[leads % n]
    search = np.abs(prof).copy()
    if exclude_zero:
        search[lead_max] = -np.inf

    j = int(np.argmax(search))
    peak_lead, peak_corr = int(leads[j]), float(prof[j])

    # Peak-picking null: slide the same 601-wide window to offsets that break the
    # lead relationship but keep the two series' shared intraday volatility
    # profile roughly aligned. Offsets are drawn from ±(10 min .. 60 min), NOT
    # uniformly across the session: a uniform draw lands most windows where the
    # open of one series sits against midday of the other, which suppresses the
    # null covariance and makes everything look significant. Measured on the
    # first pass: a uniform null was beaten by 37.9% of signal-days against a
    # nominal 5%, i.e. it was calibrated wrong, not the signals being strong.
    win = 2 * lead_max + 1
    rng = np.random.default_rng(20260806)
    near_lo, near_hi = 2 * lead_max, min(3600, n // 3)

    def shift_null(width: int) -> tuple[float, float, float]:
        if near_hi <= near_lo:
            return float("nan"), float("nan"), float("nan")
        mag = rng.integers(near_lo, near_hi, size=NULL_DRAWS)
        sign = rng.choice([-1, 1], size=NULL_DRAWS)
        starts = (mag * sign - lead_max) % n
        vals = np.array([np.max(np.abs(np.take(c, np.arange(s, s + width),
                                               mode="wrap")))
                         for s in starts])
        return vals, float(np.percentile(vals, 95)), float(np.median(vals))

    null, null_p95, null_med = shift_null(win)
    p_peak = (float(np.mean(null >= abs(peak_corr)))
              if isinstance(null, np.ndarray) else float("nan"))

    # The tradeable question is narrower than "is there any structure": a lead
    # of 0 or 1s is contemporaneous co-movement and cannot be acted on. Restrict
    # to leads of at least LEAD_MIN_TRADEABLE seconds and re-run the same null
    # at that band's width, so the comparison is like-for-like.
    band = (leads >= LEAD_MIN_TRADEABLE)
    bwin = int(band.sum())
    bj = int(np.argmax(np.abs(prof[band])))
    b_lead = int(leads[band][bj])
    b_corr = float(prof[band][bj])
    null2, b_null_p95, _ = shift_null(bwin)
    b_p = (float(np.mean(null2 >= abs(b_corr)))
           if isinstance(null2, np.ndarray) else float("nan"))

    # stationary block bootstrap on the correlation at the observed peak lead
    if peak_lead >= 0:
        a, b = sig[:n - peak_lead], ret[peak_lead:]
    else:
        a, b = sig[-peak_lead:], ret[:n + peak_lead]
    m = len(a)
    nb = max(1, m // BOOT_BLOCK)
    starts_pool = m - BOOT_BLOCK
    boots = []
    if starts_pool > 1:
        am, bm = a - a.mean(), b - b.mean()
        for _ in range(BOOT_DRAWS):
            s = rng.integers(0, starts_pool, size=nb)
            sel = (s[:, None] + np.arange(BOOT_BLOCK)[None, :]).ravel()
            aa, bb = am[sel], bm[sel]
            den = aa.std() * bb.std()
            boots.append(float((aa * bb).mean() / den) if den > 0 else np.nan)
        boots = np.array([v for v in boots if np.isfinite(v)])
    ci = ([float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
          if len(boots) > 50 else None)

    return {
        "peak_lead_s": peak_lead,
        "peak_corr": peak_corr,
        "peak_abs_corr": abs(peak_corr),
        "peak_p_shift_null": p_peak,
        "null_p95_abs_corr": null_p95,
        "null_median_abs_corr": null_med,
        "boot_ci95": ci,
        "corr_at_lead_0": float(prof[lead_max]),
        # strictly-leading band: the only part of the profile that could be traded
        "tradeable_peak_lead_s": b_lead,
        "tradeable_peak_corr": b_corr,
        "tradeable_p_shift_null": b_p,
        "tradeable_null_p95": b_null_p95,
        "tradeable_beats_null": bool(abs(b_corr) > b_null_p95) if np.isfinite(b_null_p95) else None,
        "corr_at_selected_leads": {str(L): float(prof[lead_max + L])
                                   for L in (-300, -60, -30, -5, -1, 0, 1, 5,
                                             30, 60, 300)},
        "best_negative_lead": int(leads[:lead_max][int(np.argmax(np.abs(prof[:lead_max])))]),
        "best_negative_corr": float(prof[:lead_max][int(np.argmax(np.abs(prof[:lead_max])))]),
        "mean_abs_corr_positive_leads": float(np.mean(np.abs(prof[lead_max + 1:]))),
        "mean_abs_corr_negative_leads": float(np.mean(np.abs(prof[:lead_max]))),
    }


def forward_return_corr(sig: np.ndarray, spot: np.ndarray,
                        horizons: list[int]) -> dict:
    """corr(signal_t, spot_{t+H} - spot_t) — the practical form of the question:
    does what flow just did predict where price goes over the next H seconds?"""
    out = {}
    for H in horizons:
        if len(spot) <= H + 10:
            continue
        fwd = spot[H:] - spot[:-H]
        out[str(H)] = safe_corr(sig[:len(fwd)], fwd)
    return out


def rolling_sum(x: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return x
    c = np.concatenate([[0.0], np.cumsum(x)])
    out = np.full_like(x, np.nan, dtype=float)
    out[w - 1:] = c[w:] - c[:-w]
    out[:w - 1] = out[w - 1]
    return out


def detect_downlegs(grid: dict) -> list[dict]:
    """SUPPLEMENTARY, not ground truth. Fast declines in this feed's own spot:
    a trailing DOWNLEG_WINDOW_S drop of at least DOWNLEG_DROP_PTS, de-duplicated
    to one event per DOWNLEG_SEPARATION_S. Exists because both documented flush
    windows start at/near the 08:30 bell and therefore have no pre-window inside
    an RTH-only feed."""
    spot, gs = grid["spot"], grid["grid_s"]
    w = DOWNLEG_WINDOW_S
    if len(spot) <= w:
        return []
    drop = spot[w:] - spot[:-w]
    cand = np.where(drop <= -DOWNLEG_DROP_PTS)[0]
    events, last = [], -10 ** 9
    for i in cand:
        start_i = int(i)                       # window opens here, decline follows
        if gs[start_i] - last < DOWNLEG_SEPARATION_S:
            continue
        last = gs[start_i]
        events.append({
            "start_s": int(gs[start_i]),
            "start_ct": f"{gs[start_i]//3600:02d}:{gs[start_i]%3600//60:02d}",
            "drop_pts": float(drop[i]),
        })
    return events


def zscore_at(sig: np.ndarray, grid_s: np.ndarray, at_s: int,
              exclude: tuple[int, int] | None) -> dict:
    """Standard score of the signal at one second against the same day's own
    distribution, with the event window optionally excluded so the event does
    not set the scale it is being judged against."""
    if at_s < grid_s[0] or at_s > grid_s[-1]:
        return {"status": "outside session"}
    i = int(np.searchsorted(grid_s, at_s))
    ref = np.ones(len(sig), dtype=bool)
    if exclude is not None:
        ref &= ~((grid_s >= exclude[0]) & (grid_s <= exclude[1]))
    ref &= np.isfinite(sig)
    if ref.sum() < 300 or not np.isfinite(sig[i]):
        return {"status": "insufficient reference"}
    mu, sd = sig[ref].mean(), sig[ref].std()
    return {
        "value": float(sig[i]),
        "z": float((sig[i] - mu) / sd) if sd > 0 else float("nan"),
        "ref_n": int(ref.sum()),
        "pct_rank": float((sig[ref] < sig[i]).mean()),
    }


def band_peak(sig: np.ndarray, ret: np.ndarray, lead_max: int,
              lead_min: int) -> tuple[int, float]:
    """Cheap version of lead_profile: peak |corr| over leads [lead_min, lead_max]."""
    n = len(sig)
    sd = sig.std() * ret.std()
    if n < 4 * lead_max or sd == 0 or not np.isfinite(sd):
        return 0, float("nan")
    c = circular_crosscov(sig, ret) / sd
    leads = np.arange(lead_min, lead_max + 1)
    prof = c[leads % n]
    j = int(np.argmax(np.abs(prof)))
    return int(leads[j]), float(prof[j])


def cross_day_null(store: dict, lead_max: int, lead_min: int) -> dict:
    """The properly calibrated null: pair each day's flow signal against *other*
    days' spot returns, aligned on clock second.

    A circular shift within a day cannot produce a valid null here — both series
    carry the same strong intraday volatility profile, so any shift that breaks
    the lead relationship also breaks the diurnal alignment and deflates the null
    covariance. Measured: a within-day shift null was beaten by ~30% of
    signal-days against a nominal 5%. Pairing across days preserves each series'
    own autocorrelation and time-of-day profile exactly while guaranteeing no
    true relationship exists."""
    days = list(store)
    sig_names = list(store[days[0]]["signals"])
    observed: dict[str, dict[str, float]] = {}
    null_pool: list[float] = []
    per_signal_null: dict[str, list[float]] = {s: [] for s in sig_names}

    for d in days:
        observed[d] = {}
        for s in sig_names:
            for e in days:
                a_s, b_s = store[d]["grid_s"], store[e]["grid_s"]
                lo = max(a_s[0], b_s[0])
                hi = min(a_s[-1], b_s[-1])
                if hi - lo < 4 * lead_max:
                    continue
                ia = slice(int(lo - a_s[0]), int(hi - a_s[0]) + 1)
                ib = slice(int(lo - b_s[0]), int(hi - b_s[0]) + 1)
                _, r = band_peak(store[d]["signals"][s][ia],
                                 store[e]["ret"][ib], lead_max, lead_min)
                if not np.isfinite(r):
                    continue
                if e == d:
                    observed[d][s] = abs(r)
                else:
                    null_pool.append(abs(r))
                    per_signal_null[s].append(abs(r))

    obs_all = [v for d in observed for v in observed[d].values()]
    p95 = float(np.percentile(null_pool, 95)) if null_pool else float("nan")
    exceed = float(np.mean([v > p95 for v in obs_all])) if obs_all else float("nan")
    return {
        "method": "same-signal, other-day returns, aligned on clock second; "
                  f"peak |corr| over leads {lead_min}..{lead_max}s",
        "n_null_pairs": len(null_pool),
        "n_observed": len(obs_all),
        "null_median": float(np.median(null_pool)) if null_pool else None,
        "null_p95": p95,
        "null_max": float(np.max(null_pool)) if null_pool else None,
        "observed_median": float(np.median(obs_all)) if obs_all else None,
        "observed_max": float(np.max(obs_all)) if obs_all else None,
        "frac_observed_above_null_p95": exceed,
        "expected_frac_if_no_signal": 0.05,
        "per_day_observed": observed,
    }


def part_b(flush_days: list[str], control_days: list[str], archive: Path) -> dict:
    days = list(dict.fromkeys(flush_days + control_days))
    src_fields = sorted({f for _, f, _ in PART_B_SIGNALS})
    results: dict[str, dict] = {}
    store: dict[str, dict] = {}

    for day in days:
        recs = load_raw(day, "orderflow_orderflow", archive)
        A = to_arrays(recs, src_fields)
        g = regular_grid(A)
        spot = g["spot"]
        ret = np.diff(spot, prepend=spot[0])
        row = {
            "is_flush_day": day in flush_days,
            "grid": {k: g[k] for k in ("n", "fill_fraction", "observed",
                                       "start_s", "end_s")},
            "flush_window": FLUSH_WINDOWS.get(day),
            "signals": {},
            "downlegs": detect_downlegs(g),
        }

        # price's own predictability, as the yardstick every flow number is read
        # against: if flow's peak is no better than price predicting itself,
        # flow adds nothing.
        row["price_autocorr_baseline"] = lead_profile(ret, ret, LEAD_MAX,
                                                      exclude_zero=True)

        store[day] = {"grid_s": g["grid_s"], "ret": ret, "signals": {}}
        for name, field, needs_diff in PART_B_SIGNALS:
            base = np.diff(g[field], prepend=g[field][0]) if needs_diff else g[field]
            base = np.nan_to_num(base, nan=0.0, posinf=0.0, neginf=0.0)
            for w in SMOOTH_WINDOWS:
                sig = rolling_sum(base, w)
                sig = np.nan_to_num(sig, nan=0.0)
                key = f"{name}@{w}s"
                prof = lead_profile(sig, ret, LEAD_MAX)
                prof["fwd_return_corr"] = forward_return_corr(sig, spot, FWD_HORIZONS)
                row["signals"][key] = prof
                store[day]["signals"][key] = sig

        # event-anchored view
        row["events"] = {}
        fw = FLUSH_WINDOWS.get(day)
        anchors = []
        if fw:
            anchors.append(("documented_flush", hhmm_to_s(fw["start"]),
                            (hhmm_to_s(fw["start"]), hhmm_to_s(fw["end"]))))
        for k, ev in enumerate(row["downlegs"]):
            anchors.append((f"downleg_{k}_{ev['start_ct']}", ev["start_s"],
                            (ev["start_s"], ev["start_s"] + DOWNLEG_WINDOW_S)))

        for label, at_s, excl in anchors:
            pre_avail = int(min(900, max(0, at_s - g["start_s"])))
            ev = {"anchor_s": at_s,
                  "anchor_ct": f"{at_s//3600:02d}:{at_s%3600//60:02d}",
                  "pre_window_seconds_available": pre_avail,
                  "pre_window_complete": bool(pre_avail >= 900),
                  "signals": {}}
            for name, field, needs_diff in PART_B_SIGNALS:
                base = np.diff(g[field], prepend=g[field][0]) if needs_diff else g[field]
                base = np.nan_to_num(base, nan=0.0, posinf=0.0, neginf=0.0)
                sig60 = np.nan_to_num(rolling_sum(base, 60), nan=0.0)
                ev["signals"][f"{name}@60s"] = zscore_at(sig60, g["grid_s"],
                                                        at_s, excl)
            row["events"][label] = ev

        results[day] = row
        print(f"[B] {day} flush={row['is_flush_day']} grid_n={g['n']} "
              f"fill={g['fill_fraction']:.3f} downlegs={len(row['downlegs'])}",
              file=sys.stderr)

    print("[B] cross-day null ...", file=sys.stderr)
    xnull = cross_day_null(store, LEAD_MAX, LEAD_MIN_TRADEABLE)

    return {"per_day": results, "flush_days": flush_days,
            "control_days": control_days,
            "cross_day_null": xnull,
            "lead_grid": {"min": -LEAD_MAX, "max": LEAD_MAX, "step": 1},
            "null": {"draws": NULL_DRAWS, "method": "circular shift, max |corr| over lead window"},
            "bootstrap": {"draws": BOOT_DRAWS, "block_s": BOOT_BLOCK}}


# ---------------------------------------------------------------- reporting

def summarise_a(res: dict) -> None:
    agg, days = res["aggregate"], res["days"]
    print("\n=== PART A: field guide (cross-day medians, "
          f"{len(days)} days) ===", file=sys.stderr)
    hdr = (f"{'field':18s} {'class':34s} {'|med|':>12s} {'VR60':>6s} "
           f"{'VR300':>6s} {'eff':>5s} {'r_spot':>7s} {'r_d/ret':>7s} {'r_ptnr':>7s}")
    print(hdr, file=sys.stderr)
    for f in ALL_FIELDS:
        a = agg[f]
        print(f"{f:18s} {a['class']:34s} {a.get('abs_median', float('nan')):>12.2f} "
              f"{a.get('vr_60', float('nan')):>6.3f} {a.get('vr_300', float('nan')):>6.3f} "
              f"{a.get('efficiency', float('nan')):>5.3f} "
              f"{a.get('r_spot_level', float('nan')):>+7.3f} "
              f"{a.get('r_diff_ret', float('nan')):>+7.3f} "
              f"{a.get('r_partner_level', float('nan')):>+7.3f}", file=sys.stderr)

    print("\n--- identities (worst case across days) ---", file=sys.stderr)
    for group in ("sum", "diff", "cross_package"):
        keys = set()
        for d in days:
            keys |= set(res["per_day"][d]["identities"][group])
        for k in sorted(keys):
            worst, frac, corr = 0.0, 1.0, []
            for d in days:
                e = res["per_day"][d]["identities"][group].get(k)
                if not e or "max_abs_resid" not in e:
                    continue
                worst = max(worst, e["max_abs_resid"])
                frac = min(frac, e["frac_within_rounding"])
                if e.get("corr") is not None and np.isfinite(e.get("corr", np.nan)):
                    corr.append(e["corr"])
            cs = f" corr_min={min(corr):+.6f}" if corr else ""
            verdict = "EXACT" if frac >= 0.9999 else ("near" if worst and corr and min(corr) > 0.999 else "no")
            print(f"  [{verdict:5s}] {k:52s} maxresid={worst:>12.2f} "
                  f"frac_exact={frac:.4f}{cs}", file=sys.stderr)


def summarise_b(res: dict) -> None:
    x = res.get("cross_day_null", {})
    if x:
        print("\n=== PART B: cross-day null (the calibrated test) ===", file=sys.stderr)
        print(f"  {x['method']}", file=sys.stderr)
        print(f"  null   ({x['n_null_pairs']} mismatched day pairs): "
              f"median {x['null_median']:.4f}  p95 {x['null_p95']:.4f}  max {x['null_max']:.4f}",
              file=sys.stderr)
        print(f"  observed ({x['n_observed']} same-day):            "
              f"median {x['observed_median']:.4f}  max {x['observed_max']:.4f}",
              file=sys.stderr)
        print(f"  observed above null p95: {x['frac_observed_above_null_p95']:.1%}  "
              f"(5.0% expected if flow does not lead price)", file=sys.stderr)
    print("\n=== PART B: lead/lag, flow vs 1s spot returns ===", file=sys.stderr)
    print("positive lead = flow leads price; p = circular-shift null on the peak",
          file=sys.stderr)
    for day, row in res["per_day"].items():
        tag = "FLUSH" if row["is_flush_day"] else "ctrl "
        base = row["price_autocorr_baseline"]
        print(f"\n{tag} {day}   (price-vs-price baseline peak "
              f"|r|={base.get('peak_abs_corr', float('nan')):.4f} @ "
              f"{base.get('peak_lead_s')}s)", file=sys.stderr)
        rows = sorted(row["signals"].items(),
                      key=lambda kv: -(kv[1].get("peak_abs_corr") or 0))
        print(f"   {'signal':22s} {'peak r':>8s} {'@lead':>6s}   "
              f"{'lead>=5s r':>10s} {'@lead':>6s} {'null_p95':>9s} beats?",
              file=sys.stderr)
        for k, v in rows[:6]:
            print(f"   {k:22s} {v.get('peak_corr', float('nan')):>+8.4f} "
                  f"{v.get('peak_lead_s'):>+5}s   "
                  f"{v.get('tradeable_peak_corr', float('nan')):>+10.4f} "
                  f"{v.get('tradeable_peak_lead_s'):>+5}s "
                  f"{v.get('tradeable_null_p95', float('nan')):>9.4f} "
                  f"{'YES' if v.get('tradeable_beats_null') else 'no'}",
                  file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=["a", "b", "all"], default="all")
    ap.add_argument("--archive", type=Path, default=ARCHIVE)
    ap.add_argument("--decode-days", default=",".join(DECODE_DAYS))
    ap.add_argument("--flush-days", default=",".join(FLUSH_DAYS))
    ap.add_argument("--control-days", default=",".join(CONTROL_DAYS))
    ap.add_argument("--no-cross-package", action="store_true",
                    help="skip state_*/classic_* identity tests (much less IO)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    if not args.archive.exists():
        sys.exit(f"archive not found: {args.archive}")

    out: dict = {"bead": "st-ek8b", "archive": str(args.archive)}
    if args.part in ("a", "all"):
        out["part_a"] = part_a([d for d in args.decode_days.split(",") if d],
                               args.archive, not args.no_cross_package)
        summarise_a(out["part_a"])
    if args.part in ("b", "all"):
        out["part_b"] = part_b([d for d in args.flush_days.split(",") if d],
                               [d for d in args.control_days.split(",") if d],
                               args.archive)
        summarise_b(out["part_b"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=float))
    print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
