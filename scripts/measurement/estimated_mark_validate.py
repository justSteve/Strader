"""Validate the estimated mark path against the prints, and write it up. [st-9hhc]

WHY
    A proxy with a good close mark and bad stop timing is useless to a
    blotter, and a write-up reporting only the close residual would hide
    exactly that. This script scores both, per leg-day, and renders the
    measurement document with the coverage bound stated before any
    premium-shaped number.

WHAT
    Loads a calibration (estimated_mark_calibrate.py), rebuilds the same legs
    on every corpus day (or a date range), marks each leg with the proxy and
    scores it against its own prints:
      * close residual (proxy - print, pts and % of entry)
      * MFE / MAE residuals
      * STOP-FIRE TIMING: the first minute the prints touched entry-0.30 and
        entry-10%, against the first minute the proxy did — at the bar's
        closing ES and at the bar's ES extreme against the leg
      * the 82% comparison: on right-direction legs, how often the cut fires
        before the first +25%, prints beside proxy
    Legs on days the calibration consumed are labelled in_sample; the rest
    holdout. Rows go to a JSONL sorted by leg_id; the aggregate renders to
    Markdown (strader/marks/report.py).

    Deterministic: no clock is read. --as-of names the run in the document
    and defaults to the last day scored, so an unchanged corpus renders the
    same bytes twice.

RUN
    .venv/bin/python3 scripts/measurement/estimated_mark_validate.py \\
        --calibration data/measurement/estimated-mark-calibration-2025.json \\
        --rows data/measurement/estimated-mark-validation.jsonl \\
        --doc docs/measurement/estimated-mark-path-2026-09-03.md --as-of 2026-09-03
"""
from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strader.marks.estimated import Calibration   # noqa: E402
from strader.marks.report import aggregate, render_markdown   # noqa: E402
from strader.marks.study import build_day, corpus_days, validate_leg   # noqa: E402

_CAL: Calibration | None = None
_CAL_PATH: Path | None = None


def default_corpus() -> Path:
    try:
        from market.corpus.paths import CORPUS_ROOT
        return Path(CORPUS_ROOT)
    except Exception:   # pragma: no cover - the fallback is the same path
        return ROOT / "data" / "corpus"


def _load_cal() -> Calibration:
    global _CAL
    if _CAL is None:
        assert _CAL_PATH is not None
        _CAL = Calibration.load(_CAL_PATH)
    return _CAL


def _worker(args):
    day, day_dir, cal_path = args
    global _CAL_PATH
    _CAL_PATH = cal_path
    cal = _load_cal()
    res = build_day(day, day_dir, cal.window_ct)
    rows = [validate_leg(ld, res.bars, cal) for ld in res.legs]
    return day, res.coverage, res.skip, dict(res.skips), rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=None, help="corpus root (default: data/corpus)")
    ap.add_argument("--calibration", type=Path, required=True)
    ap.add_argument("--rows", type=Path, required=True, help="per-leg JSONL to write")
    ap.add_argument("--doc", type=Path, required=True, help="Markdown write-up to write")
    ap.add_argument("--as-of", default=None, help="date named in the write-up (default: last day scored)")
    ap.add_argument("--days-through", default=None)
    ap.add_argument("--days-from", default=None)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)

    corpus = a.corpus or default_corpus()
    cal = Calibration.load(a.calibration)
    days = [(d, p) for d, p in corpus_days(corpus)
            if (a.days_through is None or d <= a.days_through)
            and (a.days_from is None or d >= a.days_from)]
    if not days:
        print(f"no corpus days with both OPRA and ES files under {corpus}", file=sys.stderr)
        return 2

    jobs = [(d, p, a.calibration) for d, p in days]
    if a.workers > 1 and len(jobs) > 1:
        with Pool(a.workers) as pool:
            results = list(pool.imap_unordered(_worker, jobs))
    else:
        results = [_worker(j) for j in jobs]
    results.sort(key=lambda r: r[0])

    rows: list[dict] = []
    coverage: dict[str, dict] = {}
    for day, cov, skip, skips, day_rows in results:
        if cov:
            coverage[day] = cov
        rows.extend(day_rows)
    rows.sort(key=lambda r: r["leg_id"])

    a.rows.parent.mkdir(parents=True, exist_ok=True)
    with open(a.rows, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    agg = aggregate(rows, cal, coverage)
    as_of = a.as_of or (days[-1][0] if days else "unknown")
    doc = render_markdown(cal, agg, as_of=as_of, rows_path=str(a.rows), cal_path=str(a.calibration))
    a.doc.parent.mkdir(parents=True, exist_ok=True)
    a.doc.write_text(doc)

    cov = agg["coverage"]
    s = agg["groups"]["all"]["stops"]["abs30|proxy_adverse"]
    print(f"scored {agg['n_scored']} of {agg['n_rows']} legs over {len(days)} days; "
          f"coverage: {cov['days_with_prints_before_window']} of {cov['n_days']} days print before "
          f"{cal.window_ct[0]} CT; 0.30 cut (adverse): both {s['both']}, same minute {s['same_minute']}, "
          f"proxy only {s['proxy_only']}, print only {s['print_only']} -> {a.doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
