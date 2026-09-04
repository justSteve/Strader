"""Calibrate the estimated mark path against the OPRA print corpus. [st-9hhc]

WHY
    strader/marks/estimated.py needs a (delta, theta) table per moneyness bin
    and minutes-to-close bucket. This fits it: per-minute premium increments
    from the actual print path regressed on the ES move in the option's
    favour, over every leg-day the corpus can score, 13:00-15:00 CT only —
    the window prints exist in (there is no option print path before 13:00 CT
    on any day; see the plan).

WHAT
    One leg-day row per (day, entry in {13:00, 13:30, 14:00, 14:30},
    put/call x {~10 ITM, ATM, ~10 OTM}), skips included with reasons. The
    fit consumes days <= --fit-through only (default: everything), so a
    2025-fit calibration can be validated out-of-sample on 2026 — the
    split-half DISCARD gate is retired (Steve, 2026-08-30) but the split is
    still computed and reported.

RUN
    .venv/bin/python3 scripts/measurement/estimated_mark_calibrate.py \
        data/measurement/estimated-mark-legdays-<date>.jsonl \
        data/measurement/estimated-mark-calibration-<date>.json \
        [--fit-through YYYY-MM-DD]

DETERMINISM
    Days sorted, Pool.imap (ordered), fixed leg order, fixed rounding, no
    clock reads: two runs over one date range with unchanged code are
    byte-identical. The pool uses the spawn start method with workers in
    strader.marks.jobs — fork under a multi-threaded parent (pytest) can
    deadlock in the child.
"""
import json
import multiprocessing
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from strader.marks import estimated as em
from strader.marks import jobs
from strader.marks import prints as pr


def main(argv: list[str]) -> int:
    out_rows, out_cal = argv[1], argv[2]
    fit_through = "9999-12-31"
    if len(argv) > 4 and argv[3] == "--fit-through":
        fit_through = argv[4]
    days = pr.corpus_days()
    fit_samples = []
    fit_day_span = []
    n_rows = n_scored = 0
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(6) as pool, open(out_rows, "w") as out:
        for day, (rows, samples) in zip(days, pool.imap(jobs.calibrate_day, days)):
            for row in rows:
                row["in_fit"] = day <= fit_through
                out.write(json.dumps(row) + "\n")
                n_rows += 1
                if row["skip"] is None:
                    n_scored += 1
            if day <= fit_through:
                fit_samples.extend(samples)
                fit_day_span.append(day)
    if not fit_day_span:
        print(f"no days at or before {fit_through}; nothing fitted")
        return 1
    cal = em.fit_calibration(
        fit_samples, fit_days=f"{fit_day_span[0]}..{fit_day_span[-1]}")
    with open(out_cal, "w") as f:
        f.write(cal.to_json() + "\n")
    print(f"days {len(days)} · legday rows {n_rows} ({n_scored} scored) · "
          f"fit samples {len(fit_samples)} over {cal.fit_days}")
    for (mi, ti), (delta, theta, n) in sorted(cal.table.items()):
        print(f"  {em.MBIN_NAMES[mi]:>4} ttc{ti} delta {delta:+.4f} "
              f"theta {theta:+.4f} pts/min  n {n}")
    for mi, (delta, theta, n) in sorted(cal.fallback.items()):
        print(f"  {em.MBIN_NAMES[mi]:>4} all  delta {delta:+.4f} "
              f"theta {theta:+.4f} pts/min  n {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
