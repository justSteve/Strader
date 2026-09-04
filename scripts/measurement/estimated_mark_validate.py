"""Validate the estimated mark path against the actual print path. [st-9hhc]

WHY
    A proxy with a good close mark and bad stop timing is useless for a
    blotter, and reporting only the close residual would hide exactly that.
    This reports both, per leg-day: the close-mark residual AND whether the
    proxy fires a 0.30 cut (and a +25% target) in the same minute the prints
    do.

WHAT
    Per scoreable leg-day: walk the proxy (calibration + ES minutes) and the
    prints side by side from the same entry, then compare
      * close: proxy final mark vs last print mark at 15:00 CT;
      * cut030: first raw print at/below entry-0.30 (print resolution — what
        a resting stop sees) vs first proxy minute at/below it;
      * tgt25: first raw print at/above entry*1.25 vs first proxy minute.
    Prints are the truth here; the proxy is the thing on trial.

RUN
    .venv/bin/python3 scripts/measurement/estimated_mark_validate.py \
        data/measurement/estimated-mark-calibration-<date>.json \
        data/measurement/estimated-mark-validation-<date>.jsonl \
        [--from YYYY-MM-DD] [--to YYYY-MM-DD]

    --from/--to bound the validated days: fit on 2025 (calibrate
    --fit-through 2025-12-31), validate --from 2026-01-01 for the
    out-of-sample answer.

DETERMINISM
    Days sorted, Pool.imap (ordered), fixed rounding, no clock reads: two
    runs over one date range with unchanged code are byte-identical. The
    pool uses the spawn start method with workers in strader.marks.jobs —
    fork under a multi-threaded parent (pytest) can deadlock in the child.
"""
import json
import multiprocessing
import sys
from pathlib import Path
from statistics import median, quantiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from strader.marks import estimated as em
from strader.marks import jobs
from strader.marks import prints as pr


def summarize(rows: list[dict]) -> None:
    scored = [r for r in rows if r.get("skip") is None]
    skips = len(rows) - len(scored)
    print(f"leg-days {len(rows)} · scored {len(scored)} · skipped {skips}")

    def cls(r):
        return r["leg"].split("_")[1].rstrip("0123456789")

    for c in ("itm", "atm", "otm"):
        sub = [r for r in scored if cls(r) == c]
        if not sub:
            continue
        abs_pts = sorted(abs(r["res_close_pts"]) for r in sub)
        res_pct = sorted(r["res_close_pct"] for r in sub)
        print(f"\n{c} (n={len(sub)})")
        print(f"  close residual |pts|: median {median(abs_pts):.2f} "
              f"p75 {quantiles(abs_pts, n=4)[2]:.2f} "
              f"p95 {quantiles(abs_pts, n=20)[18]:.2f}; "
              f"signed pct median {median(res_pct):+.3f}")
        for tag in ("cut030", "tgt25"):
            both = [r for r in sub if r[tag]["print_hit"] and r[tag]["proxy_hit"]]
            p_only = sum(1 for r in sub if r[tag]["print_hit"] and not r[tag]["proxy_hit"])
            x_only = sum(1 for r in sub if r[tag]["proxy_hit"] and not r[tag]["print_hit"])
            neither = sum(1 for r in sub if not r[tag]["print_hit"] and not r[tag]["proxy_hit"])
            agree = (len(both) + neither) / len(sub)
            line = (f"  {tag}: agree {agree:.0%} "
                    f"(both {len(both)}, neither {neither}, "
                    f"print-only {p_only}, proxy-only {x_only})")
            if both:
                dts = sorted(abs(r[tag]["dt_min"]) for r in both)
                signed = sorted(r[tag]["dt_min"] for r in both)
                line += (f"; both-fire |dt| median {median(dts):.0f} min "
                         f"p75 {quantiles(dts, n=4)[2]:.0f}; "
                         f"signed median {median(signed):+.0f}")
            print(line)


def main(argv: list[str]) -> int:
    cal_path, out_path = argv[1], argv[2]
    day_from, day_to = "0000-00-00", "9999-12-31"
    rest = argv[3:]
    while rest:
        if rest[0] == "--from":
            day_from = rest[1]
        elif rest[0] == "--to":
            day_to = rest[1]
        rest = rest[2:]
    days = [d for d in pr.corpus_days() if day_from <= d <= day_to]
    all_rows = []
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(6, initializer=jobs.init_cal, initargs=(cal_path,)) as pool, \
            open(out_path, "w") as out:
        for rows in pool.imap(jobs.validate_day, days):
            for row in rows:
                out.write(json.dumps(row) + "\n")
            all_rows.extend(rows)
    cal = em.Calibration.load(cal_path)
    print(f"calibration fit_days {cal.fit_days} · validated days "
          f"{days[0] if days else '-'}..{days[-1] if days else '-'}")
    summarize(all_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
