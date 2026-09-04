"""Per-day worker jobs for the estimated-mark measurement scripts. [st-9hhc]

These live in an importable module, not in the scripts, because the scripts
run their pools with the **spawn** start method: a fork under a
multi-threaded parent can deadlock in the child, and pytest parents are
multi-threaded by the time a full-suite run reaches these tests — an
order-dependent hang, not a red test (flagged by strader-67, 2026-09-02).
Spawn re-imports workers by module name in the child, so the workers must
resolve on sys.path; ``strader.marks`` does, a loose script file does not.

Spawn children inherit the parent's sys.path and working directory, which is
what the cwd-relative ``data/corpus`` convention and the test fixtures rely
on.
"""
from __future__ import annotations

from strader.marks import estimated as em
from strader.marks import legs as lg
from strader.marks import prints as pr

CAL = None  # per-worker calibration, set by init_cal


def init_cal(cal_path: str) -> None:
    """Pool initializer for validate_day: load the calibration once per
    worker instead of once per task."""
    global CAL
    CAL = em.Calibration.load(cal_path)


def calibrate_day(day: str):
    """(legday_rows, samples) for one day; samples are
    (mi, ti, d_fav, d_mark) per aligned minute, in fixed order."""
    rows, samples = [], []
    es_file = pr.es_path(day)
    es_minutes = pr.load_day_es_minutes(es_file, day) if es_file else []
    for leg in lg.build_day(day):
        row = {
            "day": leg.day, "entry_ct": pr.ct_hms(leg.entry_ct_s)[:5],
            "leg": leg.name, "k": leg.strike, "spx": round(leg.spx_entry, 2),
            "entry": round(leg.entry, 4), "t_entry": pr.ct_hms(leg.t_entry_s),
            "n_prints": len(leg.raw_path), "n_minutes": len(leg.marks),
            "skip": leg.skip, "n_samples": 0,
        }
        if leg.skip is None and es_minutes:
            mark_at = dict(leg.marks)
            cells = em.path_cells(leg.side, leg.strike, leg.spx_entry,
                                  leg.t_entry_s, es_minutes)
            prev_minute = None
            n = 0
            for t, d_fav, mi, ti in cells:
                if prev_minute is None:
                    prev_minute = t - 60
                if prev_minute in mark_at and t in mark_at:
                    samples.append((mi, ti, round(d_fav, 4),
                                    round(mark_at[t] - mark_at[prev_minute], 4)))
                    n += 1
                prev_minute = t
            row["n_samples"] = n
        rows.append(row)
    return rows, samples


def validate_day(day: str):
    """Validation rows for one day: proxy vs prints, close residual plus
    cut/target fire timing. Requires init_cal to have run in this process."""
    rows = []
    es_file = pr.es_path(day)
    es_minutes = pr.load_day_es_minutes(es_file, day) if es_file else []
    for leg in lg.build_day(day):
        if leg.skip is not None:
            rows.append({"day": leg.day, "entry_ct": pr.ct_hms(leg.entry_ct_s)[:5],
                         "leg": leg.name, "skip": leg.skip})
            continue
        if not es_minutes:
            rows.append({"day": leg.day, "entry_ct": pr.ct_hms(leg.entry_ct_s)[:5],
                         "leg": leg.name, "skip": "no-es"})
            continue
        proxy = em.estimated_path(leg.side, leg.strike, leg.entry,
                                  leg.spx_entry, leg.t_entry_s, es_minutes, CAL)
        close_print = leg.marks[-1][1]
        close_proxy = proxy[-1].mark
        row = {
            "day": leg.day, "entry_ct": pr.ct_hms(leg.entry_ct_s)[:5],
            "leg": leg.name, "k": leg.strike, "entry": round(leg.entry, 4),
            "skip": None,
            "close_print": round(close_print, 4),
            "close_proxy": round(close_proxy, 4),
            "res_close_pts": round(close_proxy - close_print, 4),
            "res_close_pct": round((close_proxy - close_print) / leg.entry, 4),
        }
        for tag, level, p_hit, x_hit in (
            ("cut030", leg.entry - 0.30,
             pr.first_print_at_or_below(leg.raw_path, leg.entry - 0.30, leg.t_entry_s),
             em.first_at_or_below(proxy, leg.entry - 0.30)),
            ("tgt25", leg.entry * 1.25,
             pr.first_print_at_or_above(leg.raw_path, leg.entry * 1.25, leg.t_entry_s),
             em.first_at_or_above(proxy, leg.entry * 1.25)),
        ):
            row[tag] = {
                "level": round(level, 4),
                "print_hit": p_hit is not None,
                "print_t": pr.ct_hms(p_hit[0]) if p_hit else None,
                "proxy_hit": x_hit is not None,
                "proxy_t": pr.ct_hms(x_hit.ct_s) if x_hit else None,
                "dt_min": (round((x_hit.ct_s - p_hit[0]) / 60.0, 1)
                           if p_hit and x_hit else None),
            }
        rows.append(row)
    return rows
