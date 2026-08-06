#!/usr/bin/env python3
"""Retro gamma cut — recognizer acuity confirms × GexBot gamma regime. [st-trbn]

Joins acuity run 2's confirmations (docs/measurement/recognizer-acuity-run2.md,
st-n62) to the dealer-positioning regime that was live at the confirm minute,
using the backfilled GexBot /hist archive (st-ox9x). Reports win rate by regime
cell against run 2's 47% overall baseline.

Regime source is the **classic** package (`classic_gex_zero.json.gz`): the state
package writes 0 into `zero_gamma` all day, so classic is the only place the
flip level is populated (measured, quant-dataset-survey-2026-08-06.md).

Two phases, so the expensive part runs once:

  join     read the archive, attach regime features at the confirm minute and
           5 minutes earlier, write the per-confirm joined table
  analyze  read the joined table, emit the regime-cell tables

Outputs:
  data/measurement/retro-gamma-cut-joined.jsonl   one row per joined confirm
  stdout                                          the results tables

Usage:  .venv/bin/python scripts/measurement/retro_gamma_cut.py
        .venv/bin/python scripts/measurement/retro_gamma_cut.py --skip-join
"""
from __future__ import annotations

import argparse
import bisect
import json
import logging
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "measurement"
CONFIRMS_PATH = DATA_DIR / "acuity-run2-confirmations.jsonl"
JOINED_PATH = DATA_DIR / "retro-gamma-cut-joined.jsonl"
ARCHIVE_ROOT = Path("/mnt/z/Harvest/gexbot-hist")
HIST_FILE = "classic_gex_zero.json.gz"  # plain JSON despite the name (st-kr4a)

# Run 2's study population. The confirmations file is append-only across several
# runs; this is the run the published doc reports (353 confirms / 62 days).
RUN_ID = "20260727T054148Z"

CT = ZoneInfo("America/Chicago")

# Join tolerance: the snapshot must fall inside the confirm's own CT minute,
# i.e. within [mm:00, mm:59]. The feed is ~1 snapshot/second, so this is a
# 60-second window that should essentially always contain a snapshot; confirms
# where it does not are counted and dropped rather than filled from a neighbour.
JOIN_WINDOW_S = 60
LOOKBACK_MIN = 5  # second observation, for regime-shift-into-confirm

# Distance-to-flip bins, in SPX points. Rationale in the results doc: the grading
# target is +/-5 ES points, so a +/-10 band is "close enough to the flip that the
# whole graded excursion lives near it"; 10-30 is the working band; >30 is far.
FLIP_BINS = [
    ("<= -30", -math.inf, -30.0),
    ("-30..-10", -30.0, -10.0),
    ("-10..0", -10.0, 0.0),
    ("0..+10", 0.0, 10.0),
    ("+10..+30", 10.0, 30.0),
    ("> +30", 30.0, math.inf),
]

# Cells at or above this n are reported as inference-grade; below it they are
# labelled directional-only. 30 is the conventional floor for a proportion whose
# Wilson interval is narrow enough to exclude either the 47% baseline or a coin
# flip at a plausible effect size; see the doc's decision-grade section.
MIN_N_INFERENCE = 30

logger = logging.getLogger("retro_gamma_cut")


# ──────────────────────────────────────────────────────────────────────
# Statistics (no scipy in this venv — closed forms)
# ──────────────────────────────────────────────────────────────────────
def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. Returns (lo, hi) as %."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (100 * max(0.0, centre - half), 100 * min(1.0, centre + half))


def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a,b],[c,d]] by summing tables no more
    likely than the observed one. Exact — the cells here are small."""
    def hyp(w: int, x: int, y: int, z: int) -> float:
        return (math.comb(w + x, w) * math.comb(y + z, y)
                / math.comb(w + x + y + z, w + y))

    n1, n2, k = a + b, c + d, a + c
    obs = hyp(a, b, c, d)
    tol = obs * (1 + 1e-9)
    total = 0.0
    for i in range(max(0, k - n2), min(n1, k) + 1):
        p = hyp(i, n1 - i, k - i, n2 - (k - i))
        if p <= tol:
            total += p
    return min(1.0, total)


def cluster_bootstrap_diff(rows: list[dict], verdict_key: str, reps: int = 20000,
                           seed: int = 20260806) -> dict:
    """Bootstrap the positive-minus-negative win-rate gap, resampling *days*.

    Confirms cluster hard inside days (141 confirms over 14 days), so a
    confirm-level interval overstates precision. The resampling unit is the day.
    """
    import random
    rng = random.Random(seed)
    decided = [r for r in rows if r.get(verdict_key) in ("win", "loss")]
    days = sorted({r["day"] for r in decided})
    by_day = {d: [r for r in decided if r["day"] == d] for d in days}

    def gap(sample: list[dict]) -> float | None:
        pos = [r for r in sample if r["regime"]["gamma_sign"] == "positive"]
        neg = [r for r in sample if r["regime"]["gamma_sign"] == "negative"]
        if len(pos) < 5 or len(neg) < 5:
            return None
        pw = sum(1 for r in pos if r[verdict_key] == "win")
        nw = sum(1 for r in neg if r[verdict_key] == "win")
        return 100 * pw / len(pos) - 100 * nw / len(neg)

    diffs = []
    for _ in range(reps):
        sample = [r for d in rng.choices(days, k=len(days)) for r in by_day[d]]
        g = gap(sample)
        if g is not None:
            diffs.append(g)
    diffs.sort()
    if not diffs:
        return {"reps": 0}
    return {
        "reps": len(diffs),
        "point": gap(decided),
        "median": diffs[len(diffs) // 2],
        "lo": diffs[int(0.025 * len(diffs))],
        "hi": diffs[int(0.975 * len(diffs))],
        "frac_le_zero": sum(1 for x in diffs if x <= 0) / len(diffs),
    }


def binom_two_sided_p(wins: int, n: int, p0: float) -> float:
    """Exact two-sided binomial p-value (method of small probabilities)."""
    if n == 0:
        return float("nan")

    def pmf(k: int) -> float:
        return math.comb(n, k) * p0**k * (1 - p0) ** (n - k)

    obs = pmf(wins)
    # Floating-point slack so that equally-likely outcomes are not dropped.
    tol = obs * (1 + 1e-9)
    return min(1.0, sum(pmf(k) for k in range(n + 1) if pmf(k) <= tol))


# ──────────────────────────────────────────────────────────────────────
# Inputs
# ──────────────────────────────────────────────────────────────────────
def load_confirms(run_id: str) -> list[dict]:
    """Read the study population out of the append-only confirmations file."""
    if not CONFIRMS_PATH.exists():
        raise SystemExit(f"confirmations file not found: {CONFIRMS_PATH}")
    rows, runs = [], Counter()
    with CONFIRMS_PATH.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{CONFIRMS_PATH}:{lineno}: bad JSON: {exc}")
            runs[rec.get("run")] += 1
            if rec.get("run") == run_id:
                rows.append(rec)
    logger.info("confirmations file holds %d rows across runs: %s",
                sum(runs.values()), dict(runs))
    if not rows:
        raise SystemExit(f"no rows for run {run_id}; runs present: {dict(runs)}")
    return rows


def archive_days() -> set[str]:
    """Trading days present in the GexBot /hist archive."""
    if not ARCHIVE_ROOT.is_dir():
        raise SystemExit(
            f"GexBot archive not readable at {ARCHIVE_ROOT} — is Z: mounted?")
    days = set()
    for child in ARCHIVE_ROOT.iterdir():
        if child.is_dir() and (child / HIST_FILE).is_file():
            days.add(child.name)
    if not days:
        raise SystemExit(f"no day-dirs with {HIST_FILE} under {ARCHIVE_ROOT}")
    return days


def read_day_snapshots(day: str) -> list[tuple]:
    """Load one archive day, keeping only the scalars this study needs.

    The files are 60-110 MB of plain JSON on a slow mount, so each day is read
    exactly once and reduced to compact tuples before the next day is opened.
    """
    path = ARCHIVE_ROOT / day / HIST_FILE
    with path.open() as fh:
        raw = json.load(fh)
    snaps = []
    for snap in raw:
        ts = snap.get("timestamp")
        spot = snap.get("spot")
        if not ts or not spot:
            continue
        snaps.append((
            int(ts),
            float(spot),
            float(snap.get("zero_gamma") or 0.0),
            float(snap.get("major_pos_vol") or 0.0),
            float(snap.get("major_neg_vol") or 0.0),
            float(snap.get("major_pos_oi") or 0.0),
            float(snap.get("major_neg_oi") or 0.0),
        ))
    snaps.sort(key=lambda s: s[0])
    del raw
    return snaps


# ──────────────────────────────────────────────────────────────────────
# Regime features
# ──────────────────────────────────────────────────────────────────────
def bin_flip_distance(dist: float) -> str:
    for label, lo, hi in FLIP_BINS:
        if lo < dist <= hi:
            return label
    return FLIP_BINS[0][0] if dist <= -30.0 else FLIP_BINS[-1][0]


def snapshot_features(snap: tuple) -> dict | None:
    """Derive the regime features from one snapshot tuple.

    Returns None when the flip level is unpopulated (measured: one snapshot per
    day, always the 08:30:0x opener, carries zero_gamma == 0).
    """
    ts, spot, zero_gamma, pos_vol, neg_vol, pos_oi, neg_oi = snap
    if zero_gamma <= 0:
        return None

    dist_flip = spot - zero_gamma
    feat = {
        "ts": ts,
        "spot": round(spot, 2),
        "zero_gamma": round(zero_gamma, 2),
        "gamma_sign": "positive" if dist_flip >= 0 else "negative",
        "dist_flip": round(dist_flip, 2),
        "dist_flip_bin": bin_flip_distance(dist_flip),
        "major_pos_vol": pos_vol,
        "major_neg_vol": neg_vol,
        "major_pos_oi": pos_oi,
        "major_neg_oi": neg_oi,
    }

    # Wall position uses the volume-based majors, per the bead spec.
    if pos_vol > 0 and neg_vol > 0:
        if neg_vol > pos_vol:
            # Negative wall sitting above the positive wall — the bracket is
            # inverted, so "between" has no directional meaning. Kept as its own
            # label rather than silently folded into one of the ordered cells.
            feat["wall_pos"] = "inverted_walls"
        elif spot > pos_vol:
            feat["wall_pos"] = "above_pos_wall"
        elif spot < neg_vol:
            feat["wall_pos"] = "below_neg_wall"
        else:
            feat["wall_pos"] = "between_walls"
        d_pos, d_neg = spot - pos_vol, spot - neg_vol
        feat["dist_pos_wall"] = round(d_pos, 2)
        feat["dist_neg_wall"] = round(d_neg, 2)
        nearest = "pos" if abs(d_pos) <= abs(d_neg) else "neg"
        feat["nearest_wall"] = nearest
        feat["dist_nearest_wall"] = round(min(abs(d_pos), abs(d_neg)), 2)
    else:
        feat["wall_pos"] = "unavailable"
    return feat


def pick_snapshot(snaps: list[tuple], stamps: list[int],
                  minute_start: int) -> tuple | None:
    """Last snapshot at or before the end of the CT minute starting at ts.

    `stamps` is the day's timestamp column, built once per day so the binary
    search does not rebuild it per confirm. Returns None when no snapshot falls
    inside [minute_start, minute_start + JOIN_WINDOW_S - 1].
    """
    lo, hi = minute_start, minute_start + JOIN_WINDOW_S - 1
    idx = bisect.bisect_right(stamps, hi) - 1
    if idx < 0:
        return None
    snap = snaps[idx]
    return snap if snap[0] >= lo else None


def ct_minute_epoch(day: str, hhmm: str) -> int:
    """Epoch seconds of the start of a CT wall-clock minute on a given day."""
    dt = datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=CT)
    return int(dt.timestamp())


# ──────────────────────────────────────────────────────────────────────
# Join
# ──────────────────────────────────────────────────────────────────────
def run_join() -> dict:
    confirms = load_confirms(RUN_ID)
    days_available = archive_days()

    pop_days = sorted({c["day"] for c in confirms})
    in_window = [c for c in confirms if c["day"] in days_available]
    dropped_out_of_window = len(confirms) - len(in_window)
    days_joined = sorted({c["day"] for c in in_window})

    logger.info("population: %d confirms / %d days (run %s)",
                len(confirms), len(pop_days), RUN_ID)
    logger.info("in archive window: %d confirms / %d days (dropped %d on %d days)",
                len(in_window), len(days_joined), dropped_out_of_window,
                len(pop_days) - len(days_joined))

    by_day: dict[str, list[dict]] = defaultdict(list)
    for c in in_window:
        by_day[c["day"]].append(c)

    joined, no_snap, no_flip, no_lookback = [], [], 0, 0
    for day in days_joined:
        logger.info("loading %s (%d confirms)", day, len(by_day[day]))
        try:
            snaps = read_day_snapshots(day)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("skipping %s — unreadable archive file: %s", day, exc)
            no_snap.extend(by_day[day])
            continue
        stamps = [s[0] for s in snaps]
        logger.info("  %s: %d snapshots %s..%s CT", day, len(snaps),
                    datetime.fromtimestamp(snaps[0][0], CT).strftime("%H:%M:%S"),
                    datetime.fromtimestamp(snaps[-1][0], CT).strftime("%H:%M:%S"))

        for c in by_day[day]:
            t0 = ct_minute_epoch(day, c["ct"])
            snap = pick_snapshot(snaps, stamps, t0)
            if snap is None:
                no_snap.append(c)
                continue
            feat = snapshot_features(snap)
            if feat is None:
                no_flip += 1
                continue

            row = {k: c[k] for k in (
                "day", "ct", "hour", "setup", "bias", "anchor", "anchor_src",
                "entry", "confidence", "day_type", "coverage",
                "mfe15", "mae15", "verdict15", "mfe30", "mae30", "verdict30")
                if k in c}
            row["run"] = RUN_ID
            row["regime"] = feat
            row["join_lag_s"] = t0 + JOIN_WINDOW_S - 1 - feat["ts"]

            prior_snap = pick_snapshot(
                snaps, stamps, t0 - LOOKBACK_MIN * 60)
            prior = snapshot_features(prior_snap) if prior_snap else None
            if prior is None:
                no_lookback += 1
            row["regime_t_minus_5"] = prior
            row["flip_crossed_into_confirm"] = (
                None if prior is None
                else prior["gamma_sign"] != feat["gamma_sign"])
            joined.append(row)
        del snaps, stamps

    JOINED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JOINED_PATH.open("w") as fh:
        for row in joined:
            fh.write(json.dumps(row) + "\n")
    logger.info("wrote %d joined rows to %s", len(joined), JOINED_PATH)

    return {
        "population": len(confirms),
        "population_days": len(pop_days),
        "in_window": len(in_window),
        "in_window_days": len(days_joined),
        "dropped_out_of_window": dropped_out_of_window,
        "dropped_no_snapshot": len(no_snap),
        "dropped_no_flip_level": no_flip,
        "missing_lookback": no_lookback,
        "joined": len(joined),
        "days_joined": days_joined,
    }


# ──────────────────────────────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────────────────────────────
BASELINE = 0.47  # run 2 overall first-touch +/-5 @ 30 min


def grade(rows: list[dict], verdict_key: str) -> dict:
    """Win rate over decided confirms only, matching run 2's grading."""
    wins = sum(1 for r in rows if r.get(verdict_key) == "win")
    losses = sum(1 for r in rows if r.get(verdict_key) == "loss")
    undecided = len(rows) - wins - losses
    n = wins + losses
    lo, hi = wilson_ci(wins, n)
    return {
        "n": n, "wins": wins, "losses": losses, "undecided": undecided,
        "win_pct": (100.0 * wins / n) if n else float("nan"),
        "ci_lo": lo, "ci_hi": hi,
        "p_vs_baseline": binom_two_sided_p(wins, n, BASELINE) if n else float("nan"),
    }


def cell_table(title: str, groups: dict[str, list[dict]], verdict_key: str,
               order: list[str] | None = None) -> list[str]:
    keys = order if order else sorted(groups)
    out = [f"\n### {title}  (verdict: {verdict_key})",
           "| cell | n | W/L | win% | Wilson 95% CI | p vs 47% | grade |",
           "|---|---|---|---|---|---|---|"]
    for key in keys:
        rows = groups.get(key)
        if not rows:
            continue
        g = grade(rows, verdict_key)
        if g["n"] == 0:
            out.append(f"| {key} | 0 | — | — | — | — | no decided confirms |")
            continue
        mark = "inference" if g["n"] >= MIN_N_INFERENCE else "directional-only"
        out.append(
            f"| {key} | {g['n']} | {g['wins']}/{g['losses']} | {g['win_pct']:.0f}% "
            f"| [{g['ci_lo']:.0f}%, {g['ci_hi']:.0f}%] | {g['p_vs_baseline']:.3f} "
            f"| {mark} |")
    return out


def median(vals: list[float]) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def run_analyze(verdict_key: str = "verdict30") -> list[str]:
    if not JOINED_PATH.exists():
        raise SystemExit(f"{JOINED_PATH} missing — run without --skip-join first")
    rows = [json.loads(l) for l in JOINED_PATH.open() if l.strip()]
    if not rows:
        raise SystemExit(f"{JOINED_PATH} is empty")

    lines = [f"\n## Joined corpus: {len(rows)} confirms / "
             f"{len({r['day'] for r in rows})} days"]
    overall = grade(rows, verdict_key)
    lines.append(
        f"Overall on the joined subset: {overall['win_pct']:.0f}% "
        f"({overall['wins']}W/{overall['losses']}L, {overall['undecided']} undecided) "
        f"Wilson [{overall['ci_lo']:.0f}%, {overall['ci_hi']:.0f}%], "
        f"p vs 47% = {overall['p_vs_baseline']:.3f}")

    def group(fn) -> dict[str, list[dict]]:
        g = defaultdict(list)
        for r in rows:
            g[fn(r)].append(r)
        return g

    lines += cell_table("Gamma sign (spot vs zero_gamma)",
                        group(lambda r: r["regime"]["gamma_sign"]),
                        verdict_key, ["positive", "negative"])
    lines += cell_table("Distance to flip (SPX points, spot - zero_gamma)",
                        group(lambda r: r["regime"]["dist_flip_bin"]),
                        verdict_key, [b[0] for b in FLIP_BINS])
    lines += cell_table("Position vs volume walls",
                        group(lambda r: r["regime"]["wall_pos"]), verdict_key,
                        ["above_pos_wall", "between_walls", "below_neg_wall",
                         "inverted_walls", "unavailable"])

    # Distance to nearest wall — bins fixed at the same 10/30-point scale.
    def wall_bin(r):
        d = r["regime"].get("dist_nearest_wall")
        if d is None:
            return "unavailable"
        return "<=10" if d <= 10 else ("10-30" if d <= 30 else ">30")

    lines += cell_table("Distance to nearest volume wall (abs SPX points)",
                        group(wall_bin), verdict_key,
                        ["<=10", "10-30", ">30", "unavailable"])

    lines += cell_table("Gamma sign x setup",
                        group(lambda r: f"{r['setup']} / {r['regime']['gamma_sign']}"),
                        verdict_key)

    # Second cut: regime shift into the confirm.
    lines += cell_table(
        f"Flip crossed in the {LOOKBACK_MIN} min into confirm",
        group(lambda r: {True: "crossed", False: "no cross", None: "unknown"}[
            r.get("flip_crossed_into_confirm")]),
        verdict_key, ["crossed", "no cross", "unknown"])

    # ── Excursion. Run 2 warns that +/-5 symmetric understates fat-MFE confirms,
    # so the excursion asymmetry is reported next to the win rate, not under it.
    lines.append("\n### Excursion @ 30 min by gamma sign (and by hour band)")
    lines.append("| cell | n | med MFE | med MAE | MFE > MAE |")
    lines.append("|---|---|---|---|---|")
    bands = [("all hours", None), ("08-09", {8, 9}), ("10-14", {10, 11, 12, 13, 14})]
    for band_label, hrs in bands:
        for sign in ("positive", "negative"):
            sub = [r for r in rows if r["regime"]["gamma_sign"] == sign
                   and (hrs is None or r.get("hour") in hrs)]
            sub = [r for r in sub
                   if r.get("mfe30") is not None and r.get("mae30") is not None]
            if not sub:
                continue
            dom = 100 * sum(1 for r in sub if r["mfe30"] > r["mae30"]) / len(sub)
            lines.append(
                f"| {band_label} · {sign} | {len(sub)} | "
                f"{median([r['mfe30'] for r in sub]):.2f} | "
                f"{median([r['mae30'] for r in sub]):.2f} | {dom:.0f}% |")

    # ── Confound controls. The aggregate gamma-sign gap is only meaningful if it
    # survives the two things run 2 already showed drive outcomes: hour of day
    # and full-day TPO shape.
    lines.append("\n### Confound controls — gamma sign held against hour and day shape")
    decided = [r for r in rows if r.get(verdict_key) in ("win", "loss")]

    def wl(sub: list[dict]) -> tuple[int, int]:
        w = sum(1 for r in sub if r[verdict_key] == "win")
        return w, len(sub) - w

    pos_w, pos_l = wl([r for r in decided
                       if r["regime"]["gamma_sign"] == "positive"])
    neg_w, neg_l = wl([r for r in decided
                       if r["regime"]["gamma_sign"] == "negative"])
    fisher_p = fisher_exact_2x2(pos_w, pos_l, neg_w, neg_l)
    lines.append(
        f"\nUnstratified 2x2: positive {pos_w}W/{pos_l}L vs negative "
        f"{neg_w}W/{neg_l}L — Fisher exact two-sided p = **{fisher_p:.4f}** "
        f"(this test assumes confirms are independent, which they are not).")

    boot = cluster_bootstrap_diff(rows, verdict_key)
    if boot.get("reps"):
        lines.append(
            f"Day-clustered bootstrap of the gap ({boot['reps']} resamples of the "
            f"{len({r['day'] for r in decided})} days): point estimate "
            f"**{boot['point']:+.1f} pts**, median {boot['median']:+.1f}, "
            f"95% CI **[{boot['lo']:+.1f}, {boot['hi']:+.1f}]**, "
            f"{boot['frac_le_zero']:.1%} of resamples <= 0.")

    lines.append("\n| stratum | positive W/n | positive win% | negative W/n | negative win% |")
    lines.append("|---|---|---|---|---|")
    strata: list[tuple[str, list[dict]]] = [
        ("hour 08-09", [r for r in decided if r.get("hour") in (8, 9)]),
        ("hour 10-14", [r for r in decided if r.get("hour") not in (8, 9)]),
    ]
    for dt in ("P", "D", "b"):
        strata.append((f"day_type {dt}",
                       [r for r in decided if r.get("day_type") == dt]))
    for label, sub in strata:
        p = [r for r in sub if r["regime"]["gamma_sign"] == "positive"]
        n = [r for r in sub if r["regime"]["gamma_sign"] == "negative"]
        pw, pl = wl(p)
        nw, nl = wl(n)
        pp = f"{100 * pw / (pw + pl):.0f}%" if pw + pl else "—"
        np_ = f"{100 * nw / (nw + nl):.0f}%" if nw + nl else "—"
        lines.append(f"| {label} | {pw}/{pw + pl} | {pp} | {nw}/{nw + nl} | {np_} |")

    # Day-level composition, so the clustering is visible rather than asserted.
    lines.append("\n### Per-day composition (clustering is the main precision limit)")
    lines.append("| day | day_type | confirms | positive-gamma frac | W/decided |")
    lines.append("|---|---|---|---|---|")
    for day in sorted({r["day"] for r in rows}):
        sub = [r for r in rows if r["day"] == day]
        w, l = wl([r for r in sub if r.get(verdict_key) in ("win", "loss")])
        frac = sum(1 for r in sub
                   if r["regime"]["gamma_sign"] == "positive") / len(sub)
        lines.append(f"| {day} | {sub[0].get('day_type')} | {len(sub)} | "
                     f"{frac:.2f} | {w}/{w + l} |")

    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-join", action="store_true",
                    help="reuse the existing joined table")
    ap.add_argument("--verdict", default="verdict30",
                    choices=["verdict30", "verdict15"])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not args.skip_join:
        stats = run_join()
        print("\n## Population accounting")
        for k, v in stats.items():
            if k != "days_joined":
                print(f"  {k}: {v}")
        print(f"  days_joined: {', '.join(stats['days_joined'])}")

    for verdict in ("verdict30", "verdict15"):
        print("\n" + "=" * 70)
        print(f"VERDICT KEY: {verdict}")
        print("=" * 70)
        print("\n".join(run_analyze(verdict)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
