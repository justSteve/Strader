#!/usr/bin/env python3
"""Decision-aligned continuation labels — the question the trader actually asks. [st-kqvj]

The continuation program labels a minute CONT when price extends >= 2 pts
*beyond the standing high-water mark* within 15 minutes
(`morning_flush_continuation.py:152`). That target runs away from you as price
backs off, so the label is dominated by a quantity with no market content in
it: how far price currently sits inside its own extreme. The cold-context audit
(`docs/audits/2026-08-04-auditor-report.md` §1.1, §2.1, §3.1) showed the
deliverable convergence score grades that label at AUC .678 while raw
distance-to-extreme grades it at .790 — the score is a worse proxy for the
label than the label's own construction — and that the score collapses to a
coin flip the moment the label is re-anchored on *current* price.

This script rebuilds the audited universe (the 22 July move days, the same
minute grid, the same traces) and relabels it with the question a trader
holding or considering a position is actually asking:

    From where price is RIGHT NOW, does it advance N points in the move's
    direction BEFORE it takes M points out of me, within the next 15 minutes?

Eleven labels are emitted: the original standing-extreme label (kept so every
result is comparable to the program's published numbers), three unbarriered
"advance >= N from here" labels (the audit's §3.1 rows), six barriered
N-before-M labels (N in {2,5,8} x M in {4,8} — the actual decision, since a
move that pays 5 pts after bleeding 8 is not a win for a 0DTE singleton), and
"favourable excursion exceeds adverse."

Three things this script does that the program did not:

1. **Barrier ordering is resolved on the raw tick stream**, not on minute bars.
   Whether the target or the stop came first is not recoverable from a bar's
   high/low, and it is the whole content of the label.
2. **Every base rate is conditioned on the clock** — minutes since the move
   began and time of session — because the audit found the clock outranks every
   instrument the program measured, and carries day-block bootstrap 95 %
   intervals (whole days resampled; minutes inside a day are not independent).
3. **Every trace is scored against every label alongside the trivial
   baselines** it must beat to be worth a pane: move age, session clock,
   distance-to-extreme, and the concurrent 5-minute ES move. The audit's
   systemic recommendation (§4.2) is that no trace AUC should ever be published
   without its trivial competitor computed on the same rows by the same code.

Causality: every trace and baseline uses data through minute *t* only. Labels
look forward from *t* and nothing else does.

Universe pinning: LOOKAHEAD_MIN / EXT_PTS / LAST_LABELED are declared here
rather than imported from `morning_flush_continuation` on purpose — this study
is a comparison against the audited baseline, so its grid must not drift if
that module's constants are later corrected (e.g. audit §3.5, the 10:15 minute
seeing 14 minutes of lookahead rather than 15 — reproduced here deliberately).

Usage:
    .venv/bin/python3 scripts/measurement/decision_aligned_study.py
    .venv/bin/python3 scripts/measurement/decision_aligned_study.py --cache /tmp/dal.json

Output: data/measurement/decision_aligned_truth.json + a stderr summary.
Doc: docs/measurement/decision-aligned-truth.md
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from bisect import bisect_left
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "measurement"))

from market.orderflow.replay import read_corpus_day  # noqa: E402
from morning_flush_continuation import auc, load_internals, minute_bars  # noqa: E402

CT = ZoneInfo("America/Chicago")
STUDY = ROOT / "data" / "measurement" / "morning_flush_study.json"
STORED = ROOT / "data" / "measurement" / "morning_flush_continuation.json"
OUT = ROOT / "data" / "measurement" / "decision_aligned_truth.json"

# --- universe (pinned to the audited baseline; see module docstring) ---------
LOOKAHEAD_MIN = 15           # minutes of forward window
EXT_PTS = 2.0                # original label's extension beyond the standing extreme
LAST_LABELED = time(10, 15)  # minutes after this lack full lookahead
WIN_OPEN = time(8, 30)       # morning window the study reads
WIN_CLOSE = time(10, 30)

# --- decision-aligned label grid --------------------------------------------
ADVANCE_PTS = (2.0, 5.0, 8.0)   # N — what the position needs to make
ADVERSE_PTS = (4.0, 8.0)        # M — what it may not give up first

# --- clock buckets -----------------------------------------------------------
AGE_BUCKETS = (("0-10", 0.0, 10.0), ("10-20", 10.0, 20.0),
               ("20-40", 20.0, 40.0), ("40+", 40.0, float("inf")))
SESSION_BUCKETS = (("pre-0900", 0, 9 * 60), ("0900-1000", 9 * 60, 10 * 60),
                   ("post-1000", 10 * 60, 24 * 60))

# --- bootstrap ---------------------------------------------------------------
N_BOOT = 4000       # matches the audit's §4.1 day-block bootstrap
BOOT_SEED = 20260804

# traces as the program defines them, oriented so higher = confirms the move
TRACES = ("tick_aligned", "tick_share10", "add_slope10", "vold_slope10",
          "trin_aligned", "vix_slope5", "delta5_aligned", "vol_pace",
          "wiggle_calm")
# the three traces the convergence score stacks, and the two the live meter runs
SCORE3_KEYS = ("tick_aligned", "vix_slope5", "add_slope10")
SCORE2_KEYS = ("tick_aligned", "vix_slope5")
# trivial competitors every trace has to beat to earn a pane
BASELINES = ("prox", "move_age_neg", "clock_neg", "es5_aligned",
             "clock_geom_rank")
PREDICTORS = TRACES + ("score3", "score2") + BASELINES


def label_key(adv: float, adverse: float | None) -> str:
    """Self-describing label key: reach5_before_adverse8 / reach5_any_adverse."""
    if adverse is None:
        return f"reach{adv:g}_any_adverse"
    return f"reach{adv:g}_before_adverse{adverse:g}"


LABELS: dict[str, dict[str, str]] = {
    "orig_ext2_beyond_standing_extreme": dict(
        question="Will the move print a NEW extreme 2 pts past its high-water mark?",
        definition="price extends >= 2.0 pts beyond the extreme standing at t, "
                   "within 15 min (the program's original label, "
                   "morning_flush_continuation.py:152)",
        decision="breakout re-entry trigger; NOT what a position holder asks"),
}
for _n in ADVANCE_PTS:
    LABELS[label_key(_n, None)] = dict(
        question=f"From here, does price gain {_n:g} pts my way within 15 min?",
        definition=f"max favourable excursion from the close of minute t >= {_n:g} pts "
                   "within 15 min; adverse path ignored",
        decision="target-only view; ignores what the position endures first")
    for _m in ADVERSE_PTS:
        LABELS[label_key(_n, _m)] = dict(
            question=f"Does price pay {_n:g} pts before it takes {_m:g} out of me, "
                     "within 15 min?",
            definition=f"first tick reaching +{_n:g} pts from the close of minute t "
                       f"arrives before the first tick reaching -{_m:g} pts; "
                       "resolved on the raw tick stream",
            decision="THE decision: target vs stop, in path order")
LABELS["fav_exceeds_adverse"] = dict(
    question="Over the next 15 min, is the best it offers bigger than the worst it does?",
    definition="max favourable excursion > max adverse excursion, both measured "
               "from the close of minute t over the next 15 min",
    decision="balanced framing with no threshold; audit report §3.1 row 5")
del _n, _m


# ---------------------------------------------------------------------------
# per-minute record construction
# ---------------------------------------------------------------------------

def _first_hits(prices: list[float], lo: int, hi: int, cur: float, mdir: int
                ) -> tuple[dict[float, int | None], dict[float, int | None]]:
    """First tick index (in [lo, hi)) that reaches each target / each stop.

    Returns ({N: idx|None}, {M: idx|None}). A tick cannot satisfy a favourable
    and an adverse threshold at once (they have opposite signs relative to
    ``cur``), so comparing the two indices is a total order — that comparison
    is the barriered label. Scans forward and stops as soon as the widest
    target and the widest stop are both resolved.
    """
    tgt: dict[float, int | None] = {n: None for n in ADVANCE_PTS}
    stp: dict[float, int | None] = {m: None for m in ADVERSE_PTS}
    n_max, m_max = max(ADVANCE_PTS), max(ADVERSE_PTS)
    for j in range(lo, hi):
        exc = (prices[j] - cur) * mdir
        if exc > 0:
            for n in ADVANCE_PTS:
                if tgt[n] is None and exc >= n:
                    tgt[n] = j
        elif exc < 0:
            adverse = -exc
            for m in ADVERSE_PTS:
                if stp[m] is None and adverse >= m:
                    stp[m] = j
        if tgt[n_max] is not None and stp[m_max] is not None:
            break
    return tgt, stp


def build_day(row: dict) -> list[dict]:
    """Per-minute records for one study day: labels, traces, baselines.

    Mirrors `morning_flush_continuation.main()`'s walk exactly for the grid and
    the traces (verified minute-for-minute against the stored study output by
    ``verify_against_stored``), then adds the decision-aligned labels.
    Returns [] for a day with no move span or no corpus file.
    """
    d = date.fromisoformat(row["date"])
    move = row.get("move")
    if not move:
        return []
    mdir = 1 if move["dir"] == "up" else -1
    m_start = datetime.combine(d, time.fromisoformat(move["start"]), CT)
    w_end = datetime.combine(d, WIN_CLOSE, CT)
    try:
        trades = read_corpus_day(d)
    except FileNotFoundError:
        print(f"  {row['date']}: no ES corpus file — day skipped", file=sys.stderr)
        return []

    w_trades = [t for t in trades if WIN_OPEN <= t.ts.time() < WIN_CLOSE]
    del trades  # the full day is ~500 k trades; drop it before the minute loop
    bars = minute_bars(w_trades, m_start.replace(second=0), w_end)
    if not bars:
        print(f"  {row['date']}: no bars inside the move span — day skipped",
              file=sys.stderr)
        return []
    internals = load_internals(d)
    minutes = sorted(bars)

    # tick stream for barrier ordering — parallel arrays, bisect-sliceable
    ts_list = [t.ts for t in w_trades]
    px_list = [t.price for t in w_trades]

    # running extreme series (the original label's moving target)
    ext = None
    ext_series: dict[datetime, float] = {}
    for m in minutes:
        best = bars[m]["high"] if mdir == 1 else bars[m]["low"]
        ext = best if ext is None else (max(ext, best) if mdir == 1 else min(ext, best))
        ext_series[m] = ext

    start_minute = m_start.replace(second=0, microsecond=0)
    out: list[dict] = []
    for i, m in enumerate(minutes):
        if m.time() > LAST_LABELED:
            break
        horizon = m + timedelta(minutes=LOOKAHEAD_MIN)
        future = [mm for mm in minutes if m < mm <= horizon]
        if not future:
            continue

        cur = bars[m]["close"]
        # --- original label: beyond the STANDING EXTREME -------------------
        fut_best = (max(bars[mm]["high"] for mm in future) if mdir == 1
                    else min(bars[mm]["low"] for mm in future))
        orig_cont = bool((fut_best - ext_series[m]) * mdir >= EXT_PTS)

        # --- decision-aligned: excursions from CURRENT price ---------------
        mfe = (fut_best - cur) * mdir
        fut_worst = (min(bars[mm]["low"] for mm in future) if mdir == 1
                     else max(bars[mm]["high"] for mm in future))
        mae = (cur - fut_worst) * mdir

        # --- barrier ordering on the raw tick stream -----------------------
        # the bar window [m+1min, m+16min) covers exactly the `future` minutes
        lo = bisect_left(ts_list, m + timedelta(minutes=1))
        hi = bisect_left(ts_list, m + timedelta(minutes=LOOKAHEAD_MIN + 1))
        tgt, stp = _first_hits(px_list, lo, hi, cur, mdir)

        # mark-out at the end of the forward window — what a position that hit
        # neither barrier is worth when the 15 minutes are up
        ret15 = (bars[future[-1]]["close"] - cur) * mdir

        rec: dict = dict(
            date=row["date"], minute=m.strftime("%H:%M"), dir=mdir,
            close=round(cur, 2), ext=round(ext_series[m], 2),
            mfe=round(mfe, 2), mae=round(mae, 2), ret15=round(ret15, 2),
            elapsed_min=round((m - start_minute).total_seconds() / 60.0, 1),
            minute_of_day=m.hour * 60 + m.minute,
        )
        rec["orig_ext2_beyond_standing_extreme"] = orig_cont
        for n in ADVANCE_PTS:
            rec[label_key(n, None)] = bool(mfe >= n)
            for mm_pts in ADVERSE_PTS:
                ti, si = tgt[n], stp[mm_pts]
                rec[label_key(n, mm_pts)] = bool(ti is not None and
                                                 (si is None or ti < si))
        rec["fav_exceeds_adverse"] = bool(mfe > mae)

        # bar-derived MFE and tick-derived first-hit must agree about whether
        # the target was ever reached; a mismatch means the two windows drifted
        rec["_hit_consistent"] = all(
            (mfe >= n) == (tgt[n] is not None) for n in ADVANCE_PTS)

        # --- traces (causal; definitions mirror morning_flush_continuation) --
        def closes(sym: str, back: int) -> list[float | None]:
            s = internals.get(sym, {})
            return [s.get(m - timedelta(minutes=k)) for k in range(back)]

        tick_now = closes("$TICK", 1)[0]
        tick10 = [v for v in closes("$TICK", 10) if v is not None]
        add10 = closes("$ADD", 11)
        vold10 = closes("$VOLD", 11)
        trin_now = closes("$TRIN", 1)[0]
        vix5 = closes("$VIX", 6)

        look5 = minutes[max(0, i - 4):i + 1]
        prev5 = minutes[max(0, i - 9):max(0, i - 4)]
        delta5 = sum(bars[mm]["delta"] for mm in look5)
        vol5 = sum(bars[mm]["vol"] for mm in look5)
        elapsed = minutes[:i + 1]
        avg_vol5 = 5 * sum(bars[mm]["vol"] for mm in elapsed) / len(elapsed)

        def depth(win: list[datetime]) -> float | None:
            if not win:
                return None
            worst = (min(bars[mm]["low"] for mm in win) if mdir == 1
                     else max(bars[mm]["high"] for mm in win))
            return (ext_series[win[-1]] - worst) * mdir

        d5, dprev = depth(look5), depth(prev5)
        rec.update(
            tick_aligned=(tick_now * mdir) if tick_now is not None else None,
            tick_share10=(sum(1 for v in tick10 if v * mdir > 0) / len(tick10)
                          if tick10 else None),
            add_slope10=((add10[0] - add10[10]) * mdir
                         if add10[0] is not None and add10[10] is not None else None),
            vold_slope10=((vold10[0] - vold10[10]) * mdir
                          if vold10[0] is not None and vold10[10] is not None else None),
            trin_aligned=((trin_now - 1.0) * -mdir if trin_now is not None else None),
            vix_slope5=((vix5[0] - vix5[5]) * -mdir
                        if vix5[0] is not None and vix5[5] is not None else None),
            delta5_aligned=delta5 * mdir,
            vol_pace=(vol5 / avg_vol5 if avg_vol5 > 0 else None),
            wiggle_calm=(-(d5 - dprev) if d5 is not None and dprev is not None else None),
        )

        # --- trivial baselines ---------------------------------------------
        # prox: closeness to the standing extreme, the geometry the original
        # label is built out of. Higher = nearer the extreme.
        rec["prox"] = -round((ext_series[m] - cur) * mdir, 2)
        # move_age_neg / clock_neg: oriented so higher = younger / earlier,
        # the direction the audit found predicts continuation.
        rec["move_age_neg"] = -rec["elapsed_min"]
        rec["clock_neg"] = -rec["minute_of_day"]
        c5 = bars.get(m - timedelta(minutes=5), {}).get("close")
        rec["es5_aligned"] = (round((cur - c5) * mdir, 2) if c5 is not None else None)

        # --- convergence scores ---------------------------------------------
        rec["score3"] = (sum(1 for k in SCORE3_KEYS if rec[k] > 0)
                         if all(rec[k] is not None for k in SCORE3_KEYS) else None)
        rec["score2"] = (sum(1 for k in SCORE2_KEYS if rec[k] > 0)
                         if all(rec[k] is not None for k in SCORE2_KEYS) else None)
        out.append(rec)
    return out


def add_rank_blend(recs: list[dict]) -> None:
    """Attach ``clock_geom_rank`` — an equal-weight rank blend of clock + geometry.

    The audit (§1.3) reports a trivial "ES price and a wall clock alone"
    predictor at AUC .815 without stating its functional form, so this is a
    reconstruction, not a reproduction: average of the within-sample percentile
    ranks of ``move_age_neg`` and ``prox``, no fitting, no weights to tune. It
    is still an in-sample construction and is labelled as such everywhere it
    appears. Records missing either input get None.
    """
    for key in ("move_age_neg", "prox"):
        vals = sorted(r[key] for r in recs if r.get(key) is not None)
        n = len(vals)
        if not n:
            continue
        for r in recs:
            v = r.get(key)
            r[f"_rank_{key}"] = (bisect_left(vals, v) / n) if v is not None else None
    for r in recs:
        a, b = r.get("_rank_move_age_neg"), r.get("_rank_prox")
        r["clock_geom_rank"] = ((a + b) / 2.0) if a is not None and b is not None else None


# ---------------------------------------------------------------------------
# verification against the published study
# ---------------------------------------------------------------------------

def verify_against_stored(recs: list[dict]) -> dict:
    """Check this rebuild reproduces the published study minute-for-minute.

    The traces here are re-derived from the corpus rather than read out of
    `morning_flush_continuation.json`, so this comparison is what licenses
    calling the result "the same 1,882 minutes". Reports counts rather than
    raising: a mismatch is a finding to surface, and a missing/rewritten stored
    file should not stop the study from producing its own numbers.
    """
    res = dict(stored_available=False, stored_minutes=None, rebuilt_minutes=len(recs),
               matched=None, missing_here=None, extra_here=None,
               extra_here_minutes=None, missing_here_minutes=None,
               label_mismatch=None, trace_mismatch=None, verdict=None)
    if not STORED.exists():
        print("VERIFY: stored study output absent — parity check skipped",
              file=sys.stderr)
        return res
    stored = {(s["date"], s["minute"]): s
              for s in json.loads(STORED.read_text())["minute_samples"]}
    here = {(r["date"], r["minute"]): r for r in recs}
    only_stored, only_here = set(stored) - set(here), set(here) - set(stored)
    res.update(stored_available=True, stored_minutes=len(stored),
               missing_here=len(only_stored), extra_here=len(only_here),
               extra_here_minutes=sorted({k[1] for k in only_here}),
               missing_here_minutes=sorted({k[1] for k in only_stored}))
    both = set(stored) & set(here)
    lab_bad = sum(1 for k in both
                  if stored[k]["cont"] != here[k]["orig_ext2_beyond_standing_extreme"])
    tr_bad = 0
    for k in both:
        for t in TRACES:
            a, b = stored[k][t], here[k][t]
            if a is None or b is None:
                if a is not b:
                    tr_bad += 1
            elif abs(a - b) > 1e-9:
                tr_bad += 1
    res.update(matched=len(both), label_mismatch=lab_bad, trace_mismatch=tr_bad)

    # A grid that differs only at the tail is the expected consequence of the
    # audit's §3.5 fix (LAST_LABELED 10:15 -> 10:14 drops one minute per day).
    # This study stays pinned to the audited 10:15 grid so its numbers stay
    # comparable to the report, so that difference is benign — but a mismatch
    # on the OVERLAP is not, and the two must not be reported the same way.
    clean_overlap = lab_bad == 0 and tr_bad == 0
    if clean_overlap and not only_stored and not only_here:
        verdict = "PARITY"
    elif clean_overlap:
        verdict = "PARITY-ON-OVERLAP"
    else:
        verdict = "DRIFT"
    res["verdict"] = verdict
    print(f"VERIFY [{verdict}]: rebuilt {len(recs)} minutes vs stored {len(stored)}; "
          f"matched {len(both)}, label mismatches {lab_bad}, "
          f"trace mismatches {tr_bad}", file=sys.stderr)
    if only_here:
        print(f"  {len(only_here)} minutes here are absent from the stored study "
              f"(minute-of-day {res['extra_here_minutes']}) — expected if the "
              "baseline has since adopted the §3.5 truncation fix; this study "
              f"stays on the audited grid through {LAST_LABELED:%H:%M}",
              file=sys.stderr)
    if only_stored:
        print(f"  {len(only_stored)} stored minutes are absent here "
              f"(minute-of-day {res['missing_here_minutes']}) — investigate: "
              "the baseline covers tape this study does not", file=sys.stderr)
    if not clean_overlap:
        print("  OVERLAP MISMATCH — the rebuild disagrees with the published "
              "study on minutes both cover. Numbers below are not comparable "
              "to the report until this is explained.", file=sys.stderr)
    return res


# ---------------------------------------------------------------------------
# clock conditioning + day-block bootstrap
# ---------------------------------------------------------------------------

def bucket_of(rec: dict, family: str) -> str:
    """Which bucket a minute falls in, for the named bucket family."""
    if family == "all":
        return "all"
    if family == "move_age":
        v = rec["elapsed_min"]
        for name, lo, hi in AGE_BUCKETS:
            if lo <= v < hi:
                return name
        raise ValueError(f"move age {v} outside every bucket")
    if family == "session_clock":
        v = rec["minute_of_day"]
        for name, lo, hi in SESSION_BUCKETS:
            if lo <= v < hi:
                return name
        raise ValueError(f"minute-of-day {v} outside every bucket")
    raise ValueError(f"unknown bucket family {family!r}")


BUCKET_FAMILIES = {
    "all": ("all",),
    "move_age": tuple(b[0] for b in AGE_BUCKETS),
    "session_clock": tuple(b[0] for b in SESSION_BUCKETS),
}


def make_resamples(days: list[str], n_boot: int, seed: int) -> list[list[int]]:
    """n_boot day-index draws, sampled with replacement. Shared by every cell.

    One shared set of draws (rather than fresh randomness per cell) keeps the
    intervals mutually consistent: two cells that move together across days
    show it, instead of the comparison being washed out by independent noise.
    """
    rng = random.Random(seed)
    k = len(days)
    return [[rng.randrange(k) for _ in range(k)] for _ in range(n_boot)]


def bootstrap_cell(n_by_day: list[int], k_by_day: list[int],
                   resamples: list[list[int]]) -> tuple[float | None, float | None]:
    """Percentile 95 % CI for a rate, resampling whole days (day-block bootstrap).

    Minutes inside a day are heavily autocorrelated, so resampling minutes
    would understate the interval by a large factor. Draws in which the cell
    is empty are dropped; if fewer than half the draws populate the cell the
    interval is reported as None rather than as a number nobody should read.
    """
    ps = []
    for draw in resamples:
        n = k = 0
        for idx in draw:
            n += n_by_day[idx]
            k += k_by_day[idx]
        if n:
            ps.append(k / n)
    if len(ps) < len(resamples) // 2:
        return None, None
    ps.sort()
    lo = ps[int(0.025 * (len(ps) - 1))]
    hi = ps[int(0.975 * (len(ps) - 1))]
    return round(lo, 4), round(hi, 4)


def cell_table(recs: list[dict], days: list[str], resamples: list[list[int]]) -> dict:
    """base_rates[label][bucket_family][bucket] -> n / k / p / ci_lo / ci_hi."""
    day_idx = {d: i for i, d in enumerate(days)}
    out: dict = {}
    for label in LABELS:
        out[label] = {}
        for family, buckets in BUCKET_FAMILIES.items():
            out[label][family] = {}
            for bucket in buckets:
                n_by_day = [0] * len(days)
                k_by_day = [0] * len(days)
                for r in recs:
                    if bucket_of(r, family) != bucket:
                        continue
                    i = day_idx[r["date"]]
                    n_by_day[i] += 1
                    k_by_day[i] += bool(r[label])
                n, k = sum(n_by_day), sum(k_by_day)
                lo, hi = bootstrap_cell(n_by_day, k_by_day, resamples) if n else (None, None)
                out[label][family][bucket] = dict(
                    n=n, k=k, p=(round(k / n, 4) if n else None),
                    ci_lo=lo, ci_hi=hi, n_days=sum(1 for x in n_by_day if x))
    return out


def auc_table(recs: list[dict], days: list[str]) -> dict:
    """auc[label][predictor] -> aggregate AUC, day-median AUC, class counts."""
    out: dict = {}
    for label in LABELS:
        out[label] = {}
        pos_all = [r for r in recs if r[label]]
        neg_all = [r for r in recs if not r[label]]
        for p in PREDICTORS:
            pv = [r[p] for r in pos_all if r.get(p) is not None]
            nv = [r[p] for r in neg_all if r.get(p) is not None]
            agg = auc(pv, nv)
            per_day = []
            for d in days:
                c = [r[p] for r in pos_all if r["date"] == d and r.get(p) is not None]
                t = [r[p] for r in neg_all if r["date"] == d and r.get(p) is not None]
                a = auc(c, t)
                if a is not None:
                    per_day.append(a)
            per_day.sort()
            out[label][p] = dict(
                auc=(round(agg, 3) if agg is not None else None),
                auc_day_median=(round(per_day[len(per_day) // 2], 3) if per_day else None),
                n_days_scored=len(per_day), n_pos=len(pv), n_neg=len(nv))
    return out


def outcome_split(recs: list[dict], days: list[str],
                  resamples: list[list[int]]) -> dict:
    """Three-way resolution of each barriered label, plus a crude expectancy.

    A barriered label is False for two very different reasons — the stop came
    first, or neither barrier was touched in 15 minutes — and a trader sizing a
    position needs those separated. Derivable from the stored excursions:
    target-ever iff mfe >= N, stop-ever iff mae >= M, and the label itself says
    which came first.

    ``pts_per_attempt`` is a first-order sanity number, NOT a backtest: it pays
    +N on a target-first minute, −M on a stop-first minute, and marks the
    unresolved minutes to the 15-minute close. It assumes fills exactly at the
    barrier, no slippage and no friction — the audit puts friction at 0.6–1.2
    SPX pts per attempt (§6.4), so subtract that before believing any of it.
    Every minute is an overlapping sample of the same tape, so these are not
    independent trades either.
    """
    day_idx = {d: i for i, d in enumerate(days)}
    out: dict = {}
    for n in ADVANCE_PTS:
        for mpts in ADVERSE_PTS:
            key = label_key(n, mpts)
            out[key] = {}
            for family, buckets in BUCKET_FAMILIES.items():
                out[key][family] = {}
                for bucket in buckets:
                    tot = [0] * len(days)
                    kt = [0] * len(days)
                    ks = [0] * len(days)
                    sret = [0.0] * len(days)
                    for r in recs:
                        if bucket_of(r, family) != bucket:
                            continue
                        i = day_idx[r["date"]]
                        tot[i] += 1
                        if r[key]:
                            kt[i] += 1
                        elif r["mae"] >= mpts:
                            ks[i] += 1
                        else:
                            sret[i] += r["ret15"]
                    N = sum(tot)
                    if not N:
                        continue
                    Kt, Ks, S = sum(kt), sum(ks), sum(sret)
                    exp_pts = (n * Kt - mpts * Ks + S) / N
                    ps = []
                    for draw in resamples:
                        dn = sum(tot[i] for i in draw)
                        if not dn:
                            continue
                        ps.append((n * sum(kt[i] for i in draw)
                                   - mpts * sum(ks[i] for i in draw)
                                   + sum(sret[i] for i in draw)) / dn)
                    ps.sort()
                    out[key][family][bucket] = dict(
                        n=N, p_target_first=round(Kt / N, 4),
                        p_stop_first=round(Ks / N, 4),
                        p_neither=round((N - Kt - Ks) / N, 4),
                        pts_per_attempt=round(exp_pts, 3),
                        pts_ci_lo=(round(ps[int(0.025 * (len(ps) - 1))], 3) if ps else None),
                        pts_ci_hi=(round(ps[int(0.975 * (len(ps) - 1))], 3) if ps else None))
    return out


def excursion_stats(recs: list[dict]) -> dict:
    """What the next 15 minutes actually hand you, in points, from each minute.

    The barriered labels compress this to a bit; the raw distribution is what
    sizes a position. Reported as quantiles because both tails are fat.
    """
    def q(vals: list[float], p: float) -> float:
        s = sorted(vals)
        return round(s[min(len(s) - 1, int(p * len(s)))], 2)

    mfe = [r["mfe"] for r in recs]
    mae = [r["mae"] for r in recs]
    ret = [r["ret15"] for r in recs]
    return dict(
        n=len(recs),
        mfe=dict(p10=q(mfe, .10), median=q(mfe, .50), p90=q(mfe, .90), max=round(max(mfe), 2)),
        mae=dict(p10=q(mae, .10), median=q(mae, .50), p90=q(mae, .90), max=round(max(mae), 2)),
        ret15=dict(p10=q(ret, .10), median=q(ret, .50), p90=q(ret, .90)),
        p_mae_ge_4=round(sum(1 for v in mae if v >= 4) / len(mae), 4),
        p_mae_ge_8=round(sum(1 for v in mae if v >= 8) / len(mae), 4))


def score_conditional(recs: list[dict], days: list[str],
                      resamples: list[list[int]]) -> list[dict]:
    """P(label) by convergence-score value AND clock bucket, with CIs.

    This is the table a meter rework needs: the audit's §4.2 finding is that a
    pooled per-score percentage is wrong at both ends of the morning, so the
    displayed number has to be a function of (score, clock), not of score
    alone. Emitted as a flat list of records so a consumer can filter on any
    field without walking a five-deep dict.
    """
    day_idx = {d: i for i, d in enumerate(days)}
    rows: list[dict] = []
    for score_key, values in (("score3", (0, 1, 2, 3)), ("score2", (0, 1, 2))):
        for val in values:
            subset = [r for r in recs if r.get(score_key) == val]
            for label in LABELS:
                for family, buckets in BUCKET_FAMILIES.items():
                    for bucket in buckets:
                        n_by_day = [0] * len(days)
                        k_by_day = [0] * len(days)
                        for r in subset:
                            if bucket_of(r, family) != bucket:
                                continue
                            i = day_idx[r["date"]]
                            n_by_day[i] += 1
                            k_by_day[i] += bool(r[label])
                        n, k = sum(n_by_day), sum(k_by_day)
                        if not n:
                            continue
                        lo, hi = bootstrap_cell(n_by_day, k_by_day, resamples)
                        rows.append(dict(
                            score=score_key, score_value=val, label=label,
                            bucket_family=family, bucket=bucket,
                            n=n, k=k, p=round(k / n, 4), ci_lo=lo, ci_hi=hi,
                            n_days=sum(1 for x in n_by_day if x)))
    return rows


# ---------------------------------------------------------------------------

def parity_block(recs: list[dict], base: dict, aucs: dict) -> dict:
    """The audit numbers this run is meant to land on, expected vs got.

    Kept in the emitted JSON so a later reader can tell at a glance whether the
    reconstruction still reproduces the report it was built to check.
    """
    orig = "orig_ext2_beyond_standing_extreme"
    def cell(label, fam, b):
        c = base[label][fam][b]
        return c["p"]
    return {
        "base_reach2_any_adverse": dict(
            expected=0.919, got=cell(label_key(2.0, None), "all", "all")),
        "base_reach5_any_adverse": dict(
            expected=0.762, got=cell(label_key(5.0, None), "all", "all")),
        "base_reach8_any_adverse": dict(
            expected=0.604, got=cell(label_key(8.0, None), "all", "all")),
        "base_fav_exceeds_adverse": dict(
            expected=0.672, got=cell("fav_exceeds_adverse", "all", "all")),
        "orig_label_base_rate": dict(expected=0.569, got=cell(orig, "all", "all")),
        "orig_first_10min": dict(expected=0.914, got=cell(orig, "move_age", "0-10")),
        "orig_after_40min": dict(expected=0.422, got=cell(orig, "move_age", "40+")),
        "orig_pre_0900": dict(expected=0.854, got=cell(orig, "session_clock", "pre-0900")),
        "orig_post_1000": dict(expected=0.420, got=cell(orig, "session_clock", "post-1000")),
        "prox_auc_on_orig": dict(expected=0.790, got=aucs[orig]["prox"]["auc"]),
        "prox_auc_day_median_on_orig": dict(
            expected=0.811, got=aucs[orig]["prox"]["auc_day_median"]),
        "clock_auc_on_orig": dict(expected=0.728, got=aucs[orig]["move_age_neg"]["auc"]),
        "score3_auc_on_orig": dict(expected=0.678, got=aucs[orig]["score3"]["auc"]),
        "score3_auc_on_reach2": dict(
            expected=0.506, got=aucs[label_key(2.0, None)]["score3"]["auc"]),
        "score3_auc_on_reach5": dict(
            expected=0.529, got=aucs[label_key(5.0, None)]["score3"]["auc"]),
        "score3_auc_on_reach8": dict(
            expected=0.528, got=aucs[label_key(8.0, None)]["score3"]["auc"]),
        "score3_auc_on_fav_adv": dict(
            expected=0.500, got=aucs["fav_exceeds_adverse"]["score3"]["auc"]),
        "labeled_minutes": dict(expected=1882, got=len(recs)),
    }


SCHEMA_DOC = {
    "meta": "run provenance: dates, universe parameters, bootstrap settings, "
            "and the parity check against morning_flush_continuation.json",
    "labels": "label_key -> {question, definition, decision} — what each label "
              "asks in the trader's terms",
    "base_rates": "base_rates[label][bucket_family][bucket] -> "
                  "{n, k, p, ci_lo, ci_hi, n_days}. bucket_family is one of "
                  "'all' | 'move_age' | 'session_clock'. p is the point base "
                  "rate; ci_* is a 95 % day-block bootstrap percentile interval.",
    "auc": "auc[label][predictor] -> {auc, auc_day_median, n_days_scored, "
           "n_pos, n_neg}. Predictors are the program's nine traces, the two "
           "convergence scores, and four trivial baselines. All oriented so "
           "higher = predicts the positive class; AUC below .50 means the "
           "orientation is backwards on that label.",
    "score_conditional": "flat list of {score, score_value, label, "
                         "bucket_family, bucket, n, k, p, ci_lo, ci_hi, n_days} "
                         "— P(label) jointly conditioned on convergence score "
                         "and clock. This is the meter lookup.",
    "outcome_split": "outcome_split[barriered_label][bucket_family][bucket] -> "
                     "{n, p_target_first, p_stop_first, p_neither, "
                     "pts_per_attempt, pts_ci_lo, pts_ci_hi}. Separates the two "
                     "ways a barriered label can be False. pts_per_attempt is a "
                     "frictionless first-order sanity number, not a backtest.",
    "excursions": "distribution of the 15-minute favourable excursion (mfe), "
                  "adverse excursion (mae) and mark-out (ret15) in SPX points, "
                  "measured from each minute's close.",
    "parity": "audit-report numbers this run reproduces: {expected, got}.",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, default=None,
                    help="read per-minute records from this JSON if it exists, "
                         "else build them and write it (corpus read is ~20 s/day)")
    ap.add_argument("--boot", type=int, default=N_BOOT, help="bootstrap resamples")
    ap.add_argument("--seed", type=int, default=BOOT_SEED, help="bootstrap seed")
    ap.add_argument("--out", type=Path, default=OUT, help="output JSON path")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the parity check against the stored study output")
    args = ap.parse_args()

    if args.boot < 2000:
        print(f"WARNING: {args.boot} resamples is below the 2000 floor these "
              "intervals were specified at", file=sys.stderr)

    study = json.loads(STUDY.read_text())
    recs: list[dict] = []
    if args.cache and args.cache.exists():
        recs = json.loads(args.cache.read_text())
        print(f"loaded {len(recs)} cached minute records from {args.cache}",
              file=sys.stderr)
    else:
        for row in study:
            day_recs = build_day(row)
            recs.extend(day_recs)
            print(f"  {row['date']}: {len(day_recs)} minutes", file=sys.stderr)
        if args.cache:
            args.cache.write_text(json.dumps(recs))

    if not recs:
        print("FATAL: no labeled minutes — corpus unreadable or study file empty",
              file=sys.stderr)
        return 1

    inconsistent = [r for r in recs if not r.get("_hit_consistent", True)]
    if inconsistent:
        print(f"FATAL: {len(inconsistent)} minutes where the tick-resolved target "
              "hit disagrees with the bar-derived MFE — the bar window and the "
              "tick window have drifted apart; every barriered label is suspect. "
              f"First: {inconsistent[0]['date']} {inconsistent[0]['minute']}",
              file=sys.stderr)
        return 1

    add_rank_blend(recs)
    days = sorted({r["date"] for r in recs})
    resamples = make_resamples(days, args.boot, args.seed)

    verify = dict(skipped=True) if args.no_verify else verify_against_stored(recs)
    base = cell_table(recs, days, resamples)
    aucs = auc_table(recs, days)
    scored = score_conditional(recs, days, resamples)
    splits = outcome_split(recs, days, resamples)
    exc = excursion_stats(recs)
    parity = parity_block(recs, base, aucs)

    payload = dict(
        schema=SCHEMA_DOC,
        meta=dict(
            bead="st-kqvj",
            generated=datetime.now(CT).isoformat(timespec="seconds"),
            script="scripts/measurement/decision_aligned_study.py",
            doc="docs/measurement/decision-aligned-truth.md",
            source_study="data/measurement/morning_flush_study.json",
            days=days, n_days=len(days), n_minutes=len(recs),
            lookahead_min=LOOKAHEAD_MIN, ext_pts=EXT_PTS,
            last_labeled=LAST_LABELED.strftime("%H:%M"),
            advance_pts=list(ADVANCE_PTS), adverse_pts=list(ADVERSE_PTS),
            bootstrap=dict(resamples=args.boot, seed=args.seed,
                           method="day-block percentile (whole days resampled)"),
            score3_keys=list(SCORE3_KEYS), score2_keys=list(SCORE2_KEYS),
            verify_vs_stored=verify),
        labels=LABELS, base_rates=base, auc=aucs,
        score_conditional=scored, outcome_split=splits, excursions=exc,
        parity=parity)
    args.out.write_text(json.dumps(payload, indent=1))

    # ---- stderr summary ----
    print(f"\nlabeled minutes: {len(recs)} over {len(days)} days", file=sys.stderr)
    print("\nbase rates (all minutes):", file=sys.stderr)
    for label in LABELS:
        c = base[label]["all"]["all"]
        print(f"  {label:36s} p={c['p']:.3f}  95% CI [{c['ci_lo']:.3f}, {c['ci_hi']:.3f}]"
              f"  n={c['n']}", file=sys.stderr)
    print("\nAUC — traces and trivial baselines, by label:", file=sys.stderr)
    hdr = "  " + " ".join(f"{p[:12]:>13s}" for p in PREDICTORS)
    print(f"  {'label':36s}{hdr}", file=sys.stderr)
    for label in LABELS:
        cells = " ".join(
            f"{(aucs[label][p]['auc'] if aucs[label][p]['auc'] is not None else float('nan')):13.3f}"
            for p in PREDICTORS)
        print(f"  {label:36s}  {cells}", file=sys.stderr)
    print("\nbarrier outcomes, all minutes (target-first / stop-first / neither, "
          "frictionless pts per attempt):", file=sys.stderr)
    for key, fam in splits.items():
        c = fam["all"]["all"]
        print(f"  {key:28s} {c['p_target_first']:.3f} / {c['p_stop_first']:.3f} / "
              f"{c['p_neither']:.3f}   {c['pts_per_attempt']:+.2f} pts "
              f"[{c['pts_ci_lo']:+.2f}, {c['pts_ci_hi']:+.2f}]", file=sys.stderr)
    print(f"\n15-min excursions from each minute's close (pts): "
          f"MFE median {exc['mfe']['median']} p90 {exc['mfe']['p90']}; "
          f"MAE median {exc['mae']['median']} p90 {exc['mae']['p90']} "
          f"max {exc['mae']['max']}; P(MAE>=4)={exc['p_mae_ge_4']:.3f} "
          f"P(MAE>=8)={exc['p_mae_ge_8']:.3f}", file=sys.stderr)

    print("\nparity vs the auditor's report:", file=sys.stderr)
    for k, v in parity.items():
        exp, got = v["expected"], v["got"]
        if got is None:
            flag = "MISSING"
        elif isinstance(exp, int):
            flag = "ok" if exp == got else "DIFF"
        else:
            flag = "ok" if abs(exp - got) <= 0.005 else "DIFF"
        print(f"  {k:32s} expected {exp}  got {got}   [{flag}]", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
