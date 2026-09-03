"""Calibrate the estimated mark path against the prints. [st-9hhc]

WHY
    strader/marks/estimated.py ships no numbers. This script measures them:
    per (right, moneyness bin at entry), the premium points per favourable ES
    point and the decay shape, fitted on every minute of every hypothetical
    single the corpus can price from its own prints, 13:00-15:00 CT only.

WHAT
    Per corpus day holding both databento_opra.jsonl(.gz) and
    databento_glbx_es.jsonl(.gz): the fourteen legs at each of four entry
    times (strader/marks/study.py), one calibration row per marked minute, a
    fit per bin (strader.marks.estimated.fit_bin). The output JSON carries the
    fits, the list of days consumed, and the MEASURED print coverage of every
    day — first and last print minute, rows per CT hour — so the coverage
    bound travels with the numbers it bounds.

    Deterministic: days are processed in a pool but collected and sorted by
    day before any sum; sums are math.fsum; the JSON is written with sorted
    keys and no timestamp. Two runs over one corpus with unchanged code are
    byte-identical.

RUN
    .venv/bin/python3 scripts/measurement/estimated_mark_calibrate.py \\
        --out data/measurement/estimated-mark-calibration.json
    .venv/bin/python3 scripts/measurement/estimated_mark_calibrate.py \\
        --days-through 2025-12-31 --out data/measurement/estimated-mark-calibration-2025.json
        # calibrate on 2025 only, so the validate script can score 2026 as holdout

    --corpus defaults to data/corpus under the repo root (STRADER_CORPUS_ROOT
    is honoured through market.corpus.paths when set). Offline; no network.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strader.marks.estimated import (   # noqa: E402
    Calibration, DEFAULT_WINDOW_CT, MIN_LEGS_PER_BIN, MIN_ROWS_PER_BIN, fit_bin,
)
from strader.marks.report import coverage_summary   # noqa: E402
from strader.marks.study import build_day, calibration_rows, corpus_days   # noqa: E402


def default_corpus() -> Path:
    try:
        from market.corpus.paths import CORPUS_ROOT
        return Path(CORPUS_ROOT)
    except Exception:   # pragma: no cover - the fallback is the same path
        return ROOT / "data" / "corpus"


def _worker(args):
    day, day_dir, window = args
    res = build_day(day, day_dir, window)
    rows = []
    for ld in res.legs:
        rows.extend(calibration_rows(ld, res.bars))
    return day, res.coverage, res.skip, dict(res.skips), len(res.legs), rows


def run_days(jobs, workers: int):
    """Map the worker over the jobs, pooled when it pays, sorted by day after."""
    if workers > 1 and len(jobs) > 1:
        with Pool(workers) as pool:
            results = list(pool.imap_unordered(_worker, jobs))
    else:
        results = [_worker(j) for j in jobs]
    results.sort(key=lambda r: r[0])
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=None, help="corpus root (default: data/corpus)")
    ap.add_argument("--out", type=Path, required=True, help="calibration JSON to write")
    ap.add_argument("--days-through", default=None, help="use days <= this YYYY-MM-DD only")
    ap.add_argument("--days-from", default=None, help="use days >= this YYYY-MM-DD only")
    ap.add_argument("--min-rows", type=int, default=MIN_ROWS_PER_BIN)
    ap.add_argument("--min-legs", type=int, default=MIN_LEGS_PER_BIN)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)

    corpus = a.corpus or default_corpus()
    window = DEFAULT_WINDOW_CT
    days = [(d, p) for d, p in corpus_days(corpus)
            if (a.days_through is None or d <= a.days_through)
            and (a.days_from is None or d >= a.days_from)]
    if not days:
        print(f"no corpus days with both OPRA and ES files under {corpus}", file=sys.stderr)
        return 2

    results = run_days([(d, p, window) for d, p in days], a.workers)

    per_bin: dict[tuple[str, int], list] = defaultdict(list)
    coverage: dict[str, dict] = {}
    used_days: list[str] = []
    day_skips: dict[str, int] = defaultdict(int)
    leg_skips: dict[str, int] = defaultdict(int)
    n_legs = 0
    for day, cov, skip, skips, nlegs, rows in results:
        if cov:
            coverage[day] = cov
        if skip:
            day_skips[skip] += 1
            continue
        for k, v in skips.items():
            leg_skips[k] += v
        n_legs += nlegs
        if nlegs:
            used_days.append(day)
        for r in rows:
            per_bin[(r.right, r.bin_lo)].append(r)

    fits = {}
    thin = []
    for key in sorted(per_bin):
        right, lo = key
        fit = fit_bin(right, lo, per_bin[key], min_rows=a.min_rows, min_legs=a.min_legs)
        if fit is None:
            thin.append({"right": right, "bin_lo": lo, "n_rows": len(per_bin[key]),
                         "n_legs": len({r.leg_id for r in per_bin[key]})})
            continue
        fits[key] = fit

    cal = Calibration(
        window_ct=window, fits=fits, days=tuple(used_days),
        coverage={"per_day": coverage, "summary": coverage_summary(coverage, window)},
        source={
            "script": "scripts/measurement/estimated_mark_calibrate.py",
            "corpus": str(corpus),
            "days_from": a.days_from, "days_through": a.days_through,
            "min_rows": a.min_rows, "min_legs": a.min_legs,
            "n_days_seen": len(days), "n_days_used": len(used_days), "n_legs": n_legs,
            "day_skips": dict(sorted(day_skips.items())),
            "leg_skips": dict(sorted(leg_skips.items())),
            "thin_bins": thin,
        })
    a.out.parent.mkdir(parents=True, exist_ok=True)
    cal.dump(a.out)
    s = cal.coverage["summary"]
    print(f"calibrated {len(fits)} bins from {n_legs} legs over {len(used_days)} of {len(days)} days; "
          f"{len(thin)} thin bins; coverage: {s['days_with_prints_before_window']} of {s['n_days']} days "
          f"print before {window[0]} CT -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
