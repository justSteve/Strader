"""Aggregate the validation rows and render the measurement write-up. [st-9hhc]

The write-up's order is the acceptance's order: the coverage bound first,
measured on every day the run touched, before any premium-shaped number.
Every table row says whether it is measured or reasoned. Nothing here reads a
clock — ``as_of`` is an argument — so two runs over one date range with
unchanged code render byte-identical text.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Iterable, Mapping

from strader.marks.estimated import KAPPA_GRID, Calibration, minute_index
from strader.marks.study import STOP_ABS_PTS, STOP_PCT, TARGET_PCT, RIGHT_DIRECTION_PTS

__all__ = ["aggregate", "render_markdown", "coverage_summary"]

_STOPS = (("abs30", f"{STOP_ABS_PTS:.2f}-pt cut"), ("pct10", f"{int(STOP_PCT * 100)}% cut"))
_VARIANTS = (("proxy_adverse", "proxy at the minute's adverse ES extreme"),
             ("proxy_close", "proxy at the minute's closing ES"))


def _q(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    i = (len(s) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def _resid_stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "median": round(statistics.median(xs), 4),
            "mae": round(sum(abs(x) for x in xs) / len(xs), 4),
            "p25": round(_q(xs, 0.25), 4), "p75": round(_q(xs, 0.75), 4)}


def _stop_stats(rows: list[Mapping], stop: str, variant: str) -> dict:
    pk, vk = f"stop_{stop}_print", f"stop_{stop}_{variant}"
    both = same = within1 = within5 = proxy_only = print_only = neither = 0
    diffs: list[int] = []
    for r in rows:
        p, v = r.get(pk), r.get(vk)
        if p and v:
            both += 1
            d = minute_index(v) - minute_index(p)
            diffs.append(d)
            same += d == 0
            within1 += abs(d) <= 1
            within5 += abs(d) <= 5
        elif v:
            proxy_only += 1
        elif p:
            print_only += 1
        else:
            neither += 1
    n = len(rows)
    return {"n": n, "print_fires": both + print_only, "both": both, "same_minute": same,
            "within_1": within1, "within_5": within5, "proxy_only": proxy_only,
            "print_only": print_only, "neither": neither,
            "diff_median_min": (statistics.median(diffs) if diffs else None),
            "diff_p25_min": _q(diffs, 0.25) if diffs else None,
            "diff_p75_min": _q(diffs, 0.75) if diffs else None}


def _stop_before_target(rows: list[Mapping], stop: str, variant: str | None) -> dict:
    """On right-direction legs: how often the stop fires before the first
    +25% mark. ``variant`` None scores the prints themselves."""
    sk = f"stop_{stop}_print" if variant is None else f"stop_{stop}_{variant}"
    tk = "target25_print" if variant is None else "target25_proxy"
    n = fires_first = 0
    for r in rows:
        if not r.get("right_direction"):
            continue
        n += 1
        s, t = r.get(sk), r.get(tk)
        if s and (t is None or minute_index(s) < minute_index(t)):
            fires_first += 1
    return {"n_right": n, "stop_first": fires_first,
            "pct": round(100.0 * fires_first / n, 1) if n else None}


def coverage_summary(per_day: Mapping[str, Mapping], window_ct: tuple[str, str]) -> dict:
    """The coverage bound, measured: how many days print before the window
    opens, the earliest and latest print minute across days, rows per hour."""
    lo = window_ct[0]
    firsts = sorted(c["first_minute_ct"] for c in per_day.values() if c.get("first_minute_ct"))
    lasts = sorted(c["last_minute_ct"] for c in per_day.values() if c.get("last_minute_ct"))
    before = [d for d, c in per_day.items() if c.get("first_minute_ct") and c["first_minute_ct"] < lo]
    hours: Counter = Counter()
    days_with_hour: Counter = Counter()
    for c in per_day.values():
        for h, n in c.get("rows_per_hour_ct", {}).items():
            hours[h] += n
            days_with_hour[h] += 1
    return {
        "n_days": len(per_day),
        "days_with_prints_before_window": len(before),
        "days_before_window_list": sorted(before)[:20],
        "earliest_first_minute_ct": firsts[0] if firsts else None,
        "latest_first_minute_ct": firsts[-1] if firsts else None,
        "earliest_last_minute_ct": lasts[0] if lasts else None,
        "latest_last_minute_ct": lasts[-1] if lasts else None,
        "rows_per_hour_ct": dict(sorted(hours.items())),
        "days_with_rows_per_hour_ct": dict(sorted(days_with_hour.items())),
    }


def aggregate(rows: Iterable[Mapping], cal: Calibration, per_day_coverage: Mapping[str, Mapping]) -> dict:
    rows = list(rows)
    scored = [r for r in rows if "skip" not in r]
    skipped = Counter(r["skip"] for r in rows if "skip" in r)
    groups = {
        "all": scored,
        "in_sample": [r for r in scored if r["in_sample"]],
        "holdout": [r for r in scored if not r["in_sample"]],
        "2025": [r for r in scored if r["day"] < "2026-01-01"],
        "2026": [r for r in scored if r["day"] >= "2026-01-01"],
    }
    by_bin: dict[str, list] = defaultdict(list)
    for r in scored:
        by_bin[f"{r['right']}|{r['bin_lo']:+d}"].append(r)

    def block(rs: list[Mapping]) -> dict:
        out = {
            "n": len(rs), "n_days": len({r["day"] for r in rs}),
            "close_resid_pts": _resid_stats([r["close_resid_pts"] for r in rs]),
            "close_resid_pct": _resid_stats([r["close_resid_pct"] for r in rs if r["close_resid_pct"] is not None]),
            "mfe_resid_pts": _resid_stats([r["mfe_resid_pts"] for r in rs]),
            "mae_resid_pts": _resid_stats([r["mae_resid_pts"] for r in rs]),
            "stops": {}, "stop_before_target": {},
        }
        for stop, _ in _STOPS:
            for variant, _ in _VARIANTS:
                out["stops"][f"{stop}|{variant}"] = _stop_stats(rs, stop, variant)
            out["stop_before_target"][f"{stop}|print"] = _stop_before_target(rs, stop, None)
            for variant, _ in _VARIANTS:
                out["stop_before_target"][f"{stop}|{variant}"] = _stop_before_target(rs, stop, variant)
        return out

    return {
        "n_rows": len(rows), "n_scored": len(scored), "skipped": dict(sorted(skipped.items())),
        "coverage": coverage_summary(per_day_coverage, cal.window_ct),
        "groups": {k: block(v) for k, v in groups.items()},
        "bins": {k: block(v) for k, v in sorted(by_bin.items())},
        "calibration": {"n_fits": len(cal.fits), "n_days": len(cal.days), "window_ct": list(cal.window_ct)},
    }


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.0f}%" if d else "—"


def _bin_items(agg: dict) -> list[tuple[str, int, dict]]:
    """(right, bin_lo, block) in numeric bin order, puts then calls last."""
    items = []
    for key, block in agg["bins"].items():
        right, lo = key.split("|")
        items.append((right, int(lo), block))
    return sorted(items, key=lambda t: (t[0], t[1]))


def _f(x, nd=2) -> str:
    return "—" if x is None else f"{x:.{nd}f}"


def render_markdown(cal: Calibration, agg: dict, *, as_of: str, rows_path: str, cal_path: str) -> str:
    """The write-up. Coverage first; every claim labelled."""
    w0, w1 = cal.window_ct
    cov = agg["coverage"]
    L: list[str] = []
    A = L.append
    A(f"# Estimated Mark Path — the ES→premium proxy against the prints, {as_of}")
    A("")
    A(f"**Bead:** st-9hhc (*Estimated Mark Path*) · **Measured:** {as_of} · "
      f"**Calibration:** `{cal_path}` ({agg['calibration']['n_fits']} fits over "
      f"{agg['calibration']['n_days']} days) · **Rows:** `{rows_path}` · "
      f"**Scripts:** `scripts/measurement/estimated_mark_calibrate.py`, "
      f"`estimated_mark_validate.py` · **Model:** `strader/marks/estimated.py`")
    A("")
    A("Every claim below is labelled **measured** (this run, these files) or "
      "**reasoned** (a modelling choice, stated so it can be argued with).")
    A("")
    A("## 0. The coverage bound — read this before any number below")
    A("")
    A(f"**Measured** on every OPRA file this run opened ({cov['n_days']} days), counting every row "
      f"in the file whether or not it is 0DTE:")
    A("")
    A("| | value |")
    A("|---|---|")
    A(f"| days with any print before {w0} CT | **{cov['days_with_prints_before_window']} of {cov['n_days']}** |")
    A(f"| earliest first-print minute across days (CT) | {cov['earliest_first_minute_ct']} |")
    A(f"| latest first-print minute across days (CT) | {cov['latest_first_minute_ct']} |")
    A(f"| earliest last-print minute across days (CT) | {cov['earliest_last_minute_ct']} |")
    A(f"| latest last-print minute across days (CT) | {cov['latest_last_minute_ct']} |")
    A("")
    A("Rows per CT hour, summed over days, with the number of days holding any row in that hour:")
    A("")
    A("| hour CT | rows | days |")
    A("|---|---|---|")
    for h, n in cov["rows_per_hour_ct"].items():
        A(f"| {h}:00 | {n:,} | {cov['days_with_rows_per_hour_ct'].get(h, 0)} |")
    A("")
    if cov["days_with_prints_before_window"]:
        A(f"**Measured:** {cov['days_with_prints_before_window']} day(s) carry prints before {w0} CT "
          f"({', '.join(cov['days_before_window_list'])}{'…' if cov['days_with_prints_before_window'] > 20 else ''}). "
          f"They were still calibrated and scored over {w0}–{w1} CT only; the extra minutes were not used.")
    else:
        A(f"**Measured:** no day in this run holds an option print before {w0} CT. "
          f"There is no print path to calibrate or validate against outside {w0}–{w1} CT.")
    A("")
    A(f"**So:** the proxy is calibrated and validated over **{w0}–{w1} CT only**. "
      f"`estimate_path` refuses a minute outside that window unless the caller passes "
      f"`allow_extrapolation=True`, and then every such mark carries `extrapolated=True`. "
      f"A blotter row marked outside the window is extrapolated and must say so in its own face. "
      f"Steve's plays are late-day, so the covered window is the one that matters most — "
      f"but what is covered is the last two hours, not the session.")
    A("")
    A("## 1. What was measured")
    A("")
    A("**Measured.** Per corpus day holding both an OPRA file and an ES file, and per entry time "
      "13:00 / 13:30 / 14:00 / 14:30 CT, fourteen hypothetical 0DTE singles bought at the first "
      "print at or after the entry time: put and call at −15, −10, −5, 0, +5, +10, +15 SPX points "
      "ITM (negative = OTM), strikes on the 5-point grid around the parity-inferred SPX. Each "
      "leg is marked by its own prints per minute (last print, low, high) and by the proxy per "
      "minute from the ES bars (at the bar close, and at the bar's extreme against the leg).")
    A("")
    g = agg["groups"]
    A("| group | legs | days |")
    A("|---|---|---|")
    for k in ("all", "in_sample", "holdout", "2025", "2026"):
        A(f"| {k} | {g[k]['n']} | {g[k]['n_days']} |")
    A("")
    A(f"Rows produced: {agg['n_rows']}; scored: {agg['n_scored']}; skipped: "
      + (", ".join(f"{k} {v}" for k, v in agg["skipped"].items()) if agg["skipped"] else "none") + ".")
    A("`in_sample` legs are on days the calibration consumed; `holdout` legs are not.")
    A("")
    A("## 2. The model — reasoned")
    A("")
    A("**Reasoned.** One formula, two calibrated numbers per (right, moneyness bin at entry):")
    A("")
    A("```")
    A("mark(t) = max( intrinsic(S(t)),")
    A("               P_entry + delta_hat * fav_move(t) - TV_entry * (1 - (tau(t)/tau_entry) ** kappa) )")
    A("S(t) = S_entry + (ES(t) - ES_entry)        basis held constant over the window")
    A("TV_entry = max(0, P_entry - intrinsic(S_entry))   decays to zero at 15:00 CT")
    A("```")
    A("")
    A("`delta_hat` is premium points per favourable ES point, least squares through the origin "
      "(at zero move and zero decay the mark is the entry). `kappa` is the decay shape, chosen "
      "from a fixed grid by smallest squared residual; 0.5 is the square-root-of-time an "
      "at-the-money option decays on. The floor at intrinsic is reasoned: an SPX option does not "
      "print below its intrinsic value for two hours. The constant basis is reasoned and bounded "
      "by `scripts/measurement/basis_pairs.py`.")
    A("")
    A("## 3. Calibration — measured")
    A("")
    A("| right | moneyness bin (ITM +) | delta_hat pts/ES pt | kappa | minute rows | live rows | legs | fit MAE pts | fit median resid pts |")
    A("|---|---|---|---|---|---|---|---|---|")
    edge = 0
    for key in sorted(cal.fits):
        f = cal.fits[key]
        at_edge = f.kappa <= min(KAPPA_GRID) or f.kappa >= max(KAPPA_GRID)
        edge += at_edge
        A(f"| {f.right} | [{f.bin_lo:+d}, {f.bin_lo + cal.bin_width:+d}) | {f.delta_pts_per_es:.3f} | "
          f"{f.kappa:.2f}{'*' if at_edge else ''} | {f.n_rows:,} | {f.n_live:,} | {f.n_legs} | "
          f"{f.resid_mae_pts:.2f} | {f.resid_p50_pts:+.2f} |")
    A("")
    if edge:
        A(f"\\* {edge} fit(s) sit on an edge of the kappa grid ({min(KAPPA_GRID)}–{max(KAPPA_GRID)}): the "
          "prints wanted a decay shape outside it. Read those bins' residuals with that in mind.")
        A("")
    A("The slope is fitted on the live rows (print above 0.10); a dead option sits on the zero "
      "floor whatever ES does and says nothing about the slope. The fit residual is measured on "
      "every row with the floors applied, as the proxy predicts. A bin absent from the table had "
      "too few rows or legs to fit and the proxy refuses legs in it (`Uncalibrated`) rather than "
      "borrowing a neighbour.")
    A("")
    A("## 4. Stop-fire timing — the number the blotter depends on — measured")
    A("")
    A("Does the proxy fire the cut in the minute the prints do? For each leg the first minute "
      "the prints touched the level (the minute's low) is compared with the first minute the "
      "proxy did. `both`: both fired — `same`, `≤1 min`, `≤5 min` are the share of those whose "
      "minutes agree that closely. `proxy only` / `print only`: one fired and the other never did.")
    A("")
    for stop, stop_name in _STOPS:
        for variant, variant_name in _VARIANTS:
            A(f"### {stop_name}, {variant_name}")
            A("")
            A("| group | legs | print fires | both | same minute | ≤1 min | ≤5 min | proxy only | print only | neither | proxy − print, median min (p25–p75) |")
            A("|---|---|---|---|---|---|---|---|---|---|---|")
            for k in ("all", "in_sample", "holdout", "2025", "2026"):
                s = g[k]["stops"][f"{stop}|{variant}"]
                A(f"| {k} | {s['n']} | {s['print_fires']} | {s['both']} | {_pct(s['same_minute'], s['both'])} | "
                  f"{_pct(s['within_1'], s['both'])} | {_pct(s['within_5'], s['both'])} | {s['proxy_only']} | "
                  f"{s['print_only']} | {s['neither']} | {_f(s['diff_median_min'], 1)} ({_f(s['diff_p25_min'], 1)}–{_f(s['diff_p75_min'], 1)}) |")
            A("")
    A("### Per moneyness bin — 0.30-pt cut, proxy at the adverse extreme, all legs")
    A("")
    A("| right | bin | legs | print fires | both | same minute | ≤1 min | ≤5 min | proxy only | print only |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for right, lo, b in _bin_items(agg):
        s = b["stops"]["abs30|proxy_adverse"]
        A(f"| {right} | [{lo:+d}, {lo + cal.bin_width:+d}) | {s['n']} | {s['print_fires']} | {s['both']} | "
          f"{_pct(s['same_minute'], s['both'])} | {_pct(s['within_1'], s['both'])} | {_pct(s['within_5'], s['both'])} | "
          f"{s['proxy_only']} | {s['print_only']} |")
    A("")
    A(f"### The 82% question — does the cut fire before the first +{int(TARGET_PCT * 100)}%?")
    A("")
    A(f"On right-direction legs (ES finished ≥ {RIGHT_DIRECTION_PTS:.0f} points the leg's way), "
      "`final-hour-premium-vs-es-2026-08-29.md:90` measured the 0.30 cut firing before the first "
      "+25% print on 82% of ~10 ITM single-days. The same statistic from this run, prints beside proxy:")
    A("")
    A("| group | right-direction legs | prints: cut first | proxy (adverse): cut first | proxy (close): cut first |")
    A("|---|---|---|---|---|")
    for k in ("all", "in_sample", "holdout", "2025", "2026"):
        sb = g[k]["stop_before_target"]
        p, a, c = sb["abs30|print"], sb["abs30|proxy_adverse"], sb["abs30|proxy_close"]
        A(f"| {k} | {p['n_right']} | {_f(p['pct'], 1)}% | {_f(a['pct'], 1)}% | {_f(c['pct'], 1)}% |")
    A("")
    A("| right | bin | right-direction legs | prints: cut first | proxy (adverse): cut first | proxy (close): cut first |")
    A("|---|---|---|---|---|---|")
    for right, lo, b in _bin_items(agg):
        sb = b["stop_before_target"]
        p, a, c = sb["abs30|print"], sb["abs30|proxy_adverse"], sb["abs30|proxy_close"]
        A(f"| {right} | [{lo:+d}, {lo + cal.bin_width:+d}) | {p['n_right']} | {_f(p['pct'], 1)}% | "
          f"{_f(a['pct'], 1)}% | {_f(c['pct'], 1)}% |")
    A("")
    A("## 5. Close-mark residual — measured")
    A("")
    A("proxy − print at the last marked minute, in premium points and as a share of the entry premium.")
    A("")
    A("| group | legs | median pts | MAE pts | p25–p75 pts | median % of entry | MAE % of entry |")
    A("|---|---|---|---|---|---|---|")
    for k in ("all", "in_sample", "holdout", "2025", "2026"):
        c, p = g[k]["close_resid_pts"], g[k]["close_resid_pct"]
        if not c["n"]:
            A(f"| {k} | 0 | — | — | — | — | — |")
            continue
        A(f"| {k} | {c['n']} | {c['median']:+.2f} | {c['mae']:.2f} | {c['p25']:+.2f}–{c['p75']:+.2f} | "
          f"{100 * p['median']:+.0f}% | {100 * p['mae']:.0f}% |")
    A("")
    A("| right | bin | legs | median pts | MAE pts | p25–p75 pts |")
    A("|---|---|---|---|---|---|")
    for right, lo, b in _bin_items(agg):
        c = b["close_resid_pts"]
        A(f"| {right} | [{lo:+d}, {lo + cal.bin_width:+d}) | {c['n']} | {c['median']:+.2f} | "
          f"{c['mae']:.2f} | {c['p25']:+.2f}–{c['p75']:+.2f} |")
    A("")
    A("## 6. Excursion residuals — measured")
    A("")
    A("proxy − print for the best mark (MFE, proxy at the favourable extreme) and the worst mark "
      "(MAE, proxy at the adverse extreme), premium points.")
    A("")
    A("| group | legs | MFE median | MFE MAE | MAE median | MAE MAE |")
    A("|---|---|---|---|---|---|")
    for k in ("all", "in_sample", "holdout", "2025", "2026"):
        f_, a_ = g[k]["mfe_resid_pts"], g[k]["mae_resid_pts"]
        if not f_["n"]:
            A(f"| {k} | 0 | — | — | — | — |")
            continue
        A(f"| {k} | {f_['n']} | {f_['median']:+.2f} | {f_['mae']:.2f} | {a_['median']:+.2f} | {a_['mae']:.2f} |")
    A("")
    A("## 7. What this settles, and what it does not")
    A("")
    A("**Reasoned, from the tables above.** The standing contract is unchanged by this document: "
      "estimated blotter rows carry `exit_reason=time` only and every aggregate splits by mark "
      "path. Relaxing it — letting an estimated row carry a stop or a target — is a decision to "
      "take on §4, bin by bin, with the same-minute and ≤1-minute shares and the 82% comparison "
      "in front of the reader. If a bin's proxy fires the cut in a different minute from the "
      "prints more often than not, the honest answer for that bin is that the proxy cannot "
      "resolve stops, and the row keeps `time`.")
    A("")
    A(f"Outside {w0}–{w1} CT nothing here applies: there is no print path to have measured against.")
    A("")
    return "\n".join(L)
