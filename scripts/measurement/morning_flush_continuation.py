#!/usr/bin/env python3
"""Continuation traces — internals/VIX/orderflow state inside morning moves. [st-cdwe]

Steve's question (2026-08-03): standing inside one of the big one-sided
morning moves, what measurable trace says it CONTINUES? Not base rates —
live state. Candidates: market internals ($TICK/$TRIN/$ADD/$VOLD), $VIX
(backfilled this bead), and ES orderflow (aggressor delta, volume pace,
wiggle depth).

Method: for each day in data/measurement/morning_flush_study.json (the
st-gzwb move spans), walk minutes from the primary move's start to 10:14 CT
(the last 15 minutes are excluded — truncated lookahead). A minute is
labeled CONT if price extends >= EXT_PTS beyond the extreme-standing-at-t
within the next LOOKAHEAD minutes, else TERM. Every trace is causal (uses
data through minute t only) and oriented so HIGHER = confirms the move.

Internals are 1-minute candles read at their close — up to 59s stale vs the
tape. Minutes within a day are autocorrelated; day-clustered honesty:
aggregate AUC is reported alongside the median of per-day AUCs.

Every trace AUC goes through `residual_gate.grade_trace()` [st-4cgo]. The
2026-08-04 audit (§2.3/§5.3) found the residual test had been run on VIX and
VVIX and then dropped, so the top-ranked trace — $TICK at .665 — was published
untested and fails it (day-median residual .502). The gate now returns raw
AUC, the residual after the concurrent 5-min ES move is regressed out, the
day-median of that residual, and a trivial clock+geometry baseline on the same
rows, or it raises. No trace in this script can reach the output file with
only the first of those four.

Two label-loop corrections landed with the gate (same audit):
  §3.5  LAST_LABELED is now derived from W_END and LOOKAHEAD_MIN. It was
        10:15, which saw 14 forward minutes, not 15, because bars stop at
        10:29. The last fully-covered minute is 10:14 — 22 minutes (one per
        day) leave the sample, 1,882 -> 1,860.
  §3.6  the new-extreme detector used the OUTER minute index inside a
        comprehension over the 5-minute window and `minutes.index(mm)` with
        max(0, -1) resolving to mm itself, so the day's first minute could
        never register as a new extreme. It is now a precomputed per-minute
        flag that means what it reads as.

Usage:
    .venv/bin/python3 scripts/measurement/morning_flush_continuation.py

Output: data/measurement/morning_flush_continuation.json + a stderr summary.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from market.orderflow.replay import read_corpus_day  # noqa: E402
from residual_gate import (  # noqa: E402
    GateRow, grade_trace, markdown_table, rank_auc as auc)

CT = ZoneInfo("America/Chicago")
CORPUS = ROOT / "data" / "corpus"
STUDY = ROOT / "data" / "measurement" / "morning_flush_study.json"
OUT = ROOT / "data" / "measurement" / "morning_flush_continuation.json"

W_START = time(8, 30)   # study window, from st-gzwb's move spans
W_END = time(10, 30)
LOOKAHEAD_MIN = 15   # minutes ahead a new extreme must print
EXT_PTS = 2.0        # how far beyond the standing extreme counts as continuation
ES_MOVE_MIN = 5      # window of the concurrent ES move the residual gate removes

# The nine traces, keyed as they appear in the sample rows. Single source of
# truth for what gets graded and how it is named in the published table — a
# trace added here is a trace the gate grades.
TRACE_NAMES = {
    "tick_aligned": "$TICK level x dir",
    "tick_share10": "$TICK 10-min sign-share",
    "add_slope10": "$ADD 10-min slope x dir",
    "vold_slope10": "$VOLD 10-min slope x dir",
    "trin_aligned": "$TRIN oriented",
    "vix_slope5": "$VIX 5-min slope x (-dir)",
    "delta5_aligned": "ES 5-min aggressor delta x dir",
    "vol_pace": "Volume pace (5-min vs move avg)",
    "wiggle_calm": "Wiggle-calm (backtest depth trend)",
}
COMBO_KEYS = ("tick_aligned", "vix_slope5", "add_slope10")


def last_fully_labeled(w_end: time, lookahead: int) -> time:
    """Last minute carrying `lookahead` whole forward bars inside the window.

    Bars are minute-stamped and cover [m, m+1), so the final bar of a window
    closing at `w_end` starts at w_end - 1 min. A minute m's label reads bars
    m+1 .. m+lookahead, so m is fully covered only when
    m + lookahead <= w_end - 1 min.

    This was hardcoded to 10:15 (= 10:30 - 15), which is one minute short: the
    10:15 minute saw 14 forward bars, not 15. Auditor's report §3.5.
    """
    anchor = datetime.combine(date(2000, 1, 1), w_end)
    return (anchor - timedelta(minutes=lookahead + 1)).time()


LAST_LABELED = last_fully_labeled(W_END, LOOKAHEAD_MIN)  # 10:14


def load_internals(day: date) -> dict[str, dict[datetime, float]]:
    """symbol -> {minute (CT datetime) -> close}."""
    path = CORPUS / day.isoformat() / "internals.jsonl"
    out: dict[str, dict[datetime, float]] = defaultdict(dict)
    if not path.exists():
        return out
    with path.open() as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            prov = row.get("provenance", {})
            sym = prov.get("symbol")
            ts = prov.get("ts_candle")
            close = row.get("data", {}).get("close")
            if not sym or not ts or close is None:
                continue
            out[sym][datetime.fromisoformat(ts)] = close
    return out


def minute_bars(trades, start: datetime, end: datetime):
    """minute -> dict(close, high, low, delta, vol) for [start, end)."""
    bars: dict[datetime, dict] = {}
    for t in trades:
        if not (start <= t.ts < end):
            continue
        m = t.ts.replace(second=0, microsecond=0)
        b = bars.setdefault(m, dict(close=t.price, high=t.price, low=t.price,
                                    delta=0, vol=0))
        b["close"] = t.price
        b["high"] = max(b["high"], t.price)
        b["low"] = min(b["low"], t.price)
        if t.side == "B":
            b["delta"] += t.size
        elif t.side == "A":
            b["delta"] -= t.size
        b["vol"] += t.size
    return bars


# `auc` is residual_gate.rank_auc, imported above. One implementation of the
# Mann-Whitney statistic in the program, and it lives next to the gate that
# forces its companions. Re-exported under the old name because
# morning_flush_vix_depth / morning_flush_vvix / decision_aligned_study import
# `auc` from this module.


def _gate_dict(g):
    """A TraceGrade as JSON — every field a reader needs to judge the trace."""
    return dict(name=g.trace, n=g.n, n_days=g.n_days,
                n_dropped_no_es=g.n_dropped_no_es,
                auc_raw=g.auc_raw, auc_raw_day_median=g.auc_raw_day_median,
                auc_residual=g.auc_residual,
                auc_residual_day_median=g.auc_residual_day_median,
                auc_baseline=g.auc_baseline,
                auc_baseline_day_median=g.auc_baseline_day_median,
                es_beta=g.es_beta, es_r2=g.es_r2,
                verdict=g.verdict, beats_baseline=g.beats_baseline)


def main():
    study = json.loads(STUDY.read_text())
    samples = []          # one dict per labeled minute
    day_events = []       # backtest-event states (T=2 resume_events)
    day_rows = []         # day-level one-sidedness
    day_dir = {}          # date -> +1 up move / -1 down move

    for row in study:
        d = date.fromisoformat(row["date"])
        move = row.get("move")
        if not move:
            continue
        mdir = 1 if move["dir"] == "up" else -1
        day_dir[row["date"]] = mdir
        m_start = datetime.combine(
            d, time.fromisoformat(move["start"]), CT)
        w_end = datetime.combine(d, W_END, CT)
        try:
            trades = read_corpus_day(d)
        except FileNotFoundError:
            continue
        w_trades = [t for t in trades if W_START <= t.ts.time() < W_END]
        bars = minute_bars(w_trades, m_start.replace(second=0), w_end)
        if not bars:
            continue
        internals = load_internals(d)
        minutes = sorted(bars)

        # running extreme series + forward continuation label, plus the
        # per-minute "this bar set a new extreme" flag.
        #
        # new_ext_at was an inline comprehension that guarded on the OUTER
        # minute index and looked the previous minute up with
        # minutes[max(0, minutes.index(mm) - 1)] — which resolves to mm itself
        # at the start of the series, making the inequality trivially false, so
        # the move's own first bar never counted (auditor's report §3.6). Here
        # it is what it reads as: the bar printed the standing extreme AND the
        # standing extreme moved at that bar; the first bar of the move sets
        # the extreme by definition and counts.
        ext = None
        ext_series = {}
        new_ext_at = {}
        for j, m in enumerate(minutes):
            best = bars[m]["high"] if mdir == 1 else bars[m]["low"]
            ext = best if ext is None else (max(ext, best) if mdir == 1
                                            else min(ext, best))
            ext_series[m] = ext
            new_ext_at[m] = (best == ext and
                             (j == 0 or ext != ext_series[minutes[j - 1]]))

        day_samples = []
        for i, m in enumerate(minutes):
            if m.time() > LAST_LABELED:
                break
            horizon = m + timedelta(minutes=LOOKAHEAD_MIN)
            future = [mm for mm in minutes if m < mm <= horizon]
            if not future:
                continue
            fut_best = (max(bars[mm]["high"] for mm in future) if mdir == 1
                        else min(bars[mm]["low"] for mm in future))
            cont = (fut_best - ext_series[m]) * mdir >= EXT_PTS

            def closes(sym, back):
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

            def depth(win):
                if not win:
                    return None
                worst = (min(bars[mm]["low"] for mm in win) if mdir == 1
                         else max(bars[mm]["high"] for mm in win))
                ref = ext_series[win[-1]]
                return (ref - worst) * mdir

            d5, dprev = depth(look5), depth(prev5)
            new_ext_5 = any(new_ext_at[mm] for mm in look5)

            # residual-gate covariates. es5_aligned is the concurrent ES move
            # every trace is residualised against; it is measured on the move's
            # own bar series, so the first ES_MOVE_MIN minutes of a move carry
            # None and drop out of the gate's grade rather than reaching back
            # into pre-move tape. elapsed_min and dist_ext are the two trivial
            # competitors the gate scores every trace beside — how long the
            # move has been running, and how far inside its own standing
            # extreme price currently sits.
            m_back = m - timedelta(minutes=ES_MOVE_MIN)
            es5 = ((bars[m]["close"] - bars[m_back]["close"]) * mdir
                   if m_back in bars else None)

            s = dict(
                date=row["date"], minute=m.strftime("%H:%M"), cont=cont,
                es5_aligned=round(es5, 2) if es5 is not None else None,
                elapsed_min=round((m - minutes[0]).total_seconds() / 60, 1),
                dist_ext=round((ext_series[m] - bars[m]["close"]) * mdir, 2),
                tick_aligned=(tick_now * mdir) if tick_now is not None else None,
                tick_share10=(sum(1 for v in tick10 if v * mdir > 0) / len(tick10)
                              if tick10 else None),
                add_slope10=((add10[0] - add10[10]) * mdir
                             if add10[0] is not None and add10[10] is not None
                             else None),
                vold_slope10=((vold10[0] - vold10[10]) * mdir
                              if vold10[0] is not None and vold10[10] is not None
                              else None),
                trin_aligned=((trin_now - 1.0) * -mdir
                              if trin_now is not None else None),
                vix_slope5=((vix5[0] - vix5[5]) * -mdir
                            if vix5[0] is not None and vix5[5] is not None
                            else None),
                delta5_aligned=delta5 * mdir,
                new_ext_5=bool(new_ext_5),
                new_ext_now=bool(new_ext_at[m]),
                delta_div=bool(new_ext_5 and delta5 * mdir < 0),
                vol_pace=(vol5 / avg_vol5 if avg_vol5 > 0 else None),
                wiggle_calm=(-(d5 - dprev)
                             if d5 is not None and dprev is not None else None),
            )
            day_samples.append(s)
        samples.extend(day_samples)

        # backtest events (T=2.0) — state at the event minute
        for ev in row.get("resume_events", {}).get("2.0", []):
            em = datetime.combine(d, time.fromisoformat(ev["t"]), CT)
            em = em.replace(second=0)
            match = next((s for s in day_samples if s["minute"] == em.strftime("%H:%M")), None)
            if match:
                day_events.append(dict(match, resumed=ev["resumed"],
                                       depth=ev["depth"]))

        # day-level one-sidedness over the move span
        span = [m for m in minutes if m <= datetime.combine(
            d, time.fromisoformat(move["end"]), CT)]
        ticks = [internals.get("$TICK", {}).get(m) for m in span]
        ticks = [v for v in ticks if v is not None]
        vix_span = [internals.get("$VIX", {}).get(m) for m in span]
        vix_span = [v for v in vix_span if v is not None]
        vold_end = internals.get("$VOLD", {}).get(span[-1]) if span else None
        day_rows.append(dict(
            date=row["date"], dir=move["dir"], size=move["size"],
            tick_sign_share=(sum(1 for v in ticks if v * mdir > 0) / len(ticks)
                             if ticks else None),
            vix_net=((vix_span[-1] - vix_span[0]) * -mdir if len(vix_span) > 1
                     else None),
            vold_end_aligned=(vold_end * mdir if vold_end is not None else None),
        ))

    # ---- aggregate ----
    metrics = list(TRACE_NAMES)

    def gate_rows(value_of):
        """One GateRow per labeled minute for a callable returning its value."""
        return [GateRow(date=s["date"], cont=s["cont"], value=value_of(s),
                        es_move=s["es5_aligned"], clock=s["elapsed_min"],
                        geometry=s["dist_ext"])
                for s in samples]

    # The gate runs FIRST and raises on anything it cannot grade, so no raw
    # AUC below can reach the output file without its residual, its day-median
    # residual, and the trivial baseline computed on the same rows. This is the
    # standing version of the test that was run on VIX, run on VVIX, and then
    # dropped before it reached $TICK (auditor's report §5.3).
    grades = {k: grade_trace(TRACE_NAMES[k], gate_rows(lambda s, k=k: s[k]))
              for k in metrics}

    def score3(s):
        """Convergence score 0-3 at this minute, or None if a leg is blind."""
        if any(s[k] is None for k in COMBO_KEYS):
            return None
        return float(sum(1 for k in COMBO_KEYS if s[k] > 0))

    grades["combo_score3"] = grade_trace("Convergence score 0-3",
                                         gate_rows(score3))

    summary = {}
    for k in metrics:
        cont = [s[k] for s in samples if s["cont"] and s[k] is not None]
        term = [s[k] for s in samples if not s["cont"] and s[k] is not None]
        a = auc(cont, term)
        per_day = []
        for dte in {s["date"] for s in samples}:
            c = [s[k] for s in samples if s["date"] == dte and s["cont"]
                 and s[k] is not None]
            t = [s[k] for s in samples if s["date"] == dte and not s["cont"]
                 and s[k] is not None]
            ad = auc(c, t)
            if ad is not None:
                per_day.append(ad)
        per_day.sort()
        med = lambda v: v[len(v) // 2] if v else None
        g = grades[k]
        summary[k] = dict(
            # auc / auc_day_median stay the all-value-bearing-minutes numbers
            # this study has always published, so the gate's effect is legible
            # rather than silently substituted. The gate's own raw AUC sits in
            # the gate block and is on its (smaller) row set.
            auc=round(a, 3) if a is not None else None,
            auc_day_median=(round(med(per_day), 3) if per_day else None),
            n_cont=len(cont), n_term=len(term),
            cont_median=round(med(sorted(cont)), 3) if cont else None,
            term_median=round(med(sorted(term)), 3) if term else None,
            gate=_gate_dict(g))

    # delta divergence is a flag, not a scalar — and the published version was
    # unconditioned. `delta_div` can only fire when a new extreme has printed,
    # and new extremes print far more often in CONT minutes than TERM ones, so
    # the published CONT-vs-TERM flag-rate gap is that base-rate difference
    # wearing an exhaustion-flag costume (auditor's report §2.2). Conditioning
    # on the minutes where the heuristic is even defined is the honest
    # comparison, and it reverses the sign of the published conclusion.
    dd_cont = [s for s in samples if s["cont"]]
    dd_term = [s for s in samples if not s["cont"]]
    p_cont = lambda rows: (round(sum(1 for s in rows if s["cont"]) / len(rows), 3)
                           if rows else None)

    def conditioned(flag):
        """P(CONT | delta against vs with) among minutes where `flag` fired.

        Reported for both eligibility definitions — a new extreme anywhere in
        the 5-minute window (what `delta_div` uses) and one in this minute
        alone — because the conclusion should not depend on which one a
        reader has in mind, and the audit's own eligible set (855 minutes)
        matches neither exactly.
        """
        elig = [s for s in samples if s[flag]]
        against = [s for s in elig if s["delta5_aligned"] < 0]
        with_ = [s for s in elig if s["delta5_aligned"] >= 0]
        # Naive two-proportion z on the gap. It treats minutes as independent
        # draws, which they are not (they cluster inside 22 mornings), so it is
        # the OPTIMISTIC bound on the gap's significance — if it is not
        # significant here it is certainly not significant day-clustered.
        z = p2 = None
        pa, pw = p_cont(against), p_cont(with_)
        if against and with_:
            pool = ((sum(1 for s in against if s["cont"])
                     + sum(1 for s in with_ if s["cont"])) / len(elig))
            se = math.sqrt(pool * (1 - pool) * (1 / len(against) + 1 / len(with_)))
            if se > 0:
                z = (pa - pw) / se
                p2 = math.erfc(abs(z) / math.sqrt(2))
        return dict(
            n_eligible=len(elig),
            eligible_rate_cont=round(
                sum(1 for s in dd_cont if s[flag]) / len(dd_cont), 3),
            eligible_rate_term=round(
                sum(1 for s in dd_term if s[flag]) / len(dd_term), 3),
            divergence=dict(n=len(against), p_cont=pa),
            with_move=dict(n=len(with_), p_cont=pw),
            gap=round(pa - pw, 3) if pa is not None and pw is not None else None,
            z_naive=round(z, 2) if z is not None else None,
            p_two_sided_naive=round(p2, 3) if p2 is not None else None)

    summary["delta_div_rate"] = dict(
        cont=round(sum(1 for s in dd_cont if s["delta_div"]) / len(dd_cont), 3),
        term=round(sum(1 for s in dd_term if s["delta_div"]) / len(dd_term), 3),
        n_cont=len(dd_cont), n_term=len(dd_term),
        # the confound, and the comparison that removes it
        conditioned_new_ext_5=conditioned("new_ext_5"),
        conditioned_new_ext_now=conditioned("new_ext_now"))

    # ---- what the VIX leg of a quadrant adds over the bare ES sign ----
    # The published quadrant cells (morning_flush_vix_depth.py) split on
    # sign(dES_5m) x sign(dVIX_5m). Splitting on the ES sign ALONE first shows
    # how much of each cell is the price move you can already see: the headline
    # "flush running, vol bid" cell is within a rounding error of it, and the
    # dramatic reads sit in n=35-55 cells (auditor's report §2.4). z is a naive
    # two-proportion test against the ES-only cell — no clustering correction,
    # no multiple-comparison correction, so it is the optimistic bound.
    quad_rows = [dict(mdir=day_dir[s["date"]], es_with=s["es5_aligned"] > 0,
                      vix_conf=s["vix_slope5"] > 0, cont=s["cont"])
                 for s in samples
                 if s["es5_aligned"] not in (None, 0)
                 and s["vix_slope5"] not in (None, 0)]

    def _cell(pred):
        r = [x for x in quad_rows if pred(x)]
        return dict(n=len(r), p_cont=(round(sum(1 for x in r if x["cont"])
                                            / len(r), 3) if r else None))

    def _z(a, b):
        if not a["n"] or not b["n"]:
            return None, None
        ka, kb = a["p_cont"] * a["n"], b["p_cont"] * b["n"]
        pool = (ka + kb) / (a["n"] + b["n"])
        se = math.sqrt(pool * (1 - pool) * (1 / a["n"] + 1 / b["n"]))
        if se == 0:
            return None, None
        z = (a["p_cont"] - b["p_cont"]) / se
        return round(z, 2), round(math.erfc(abs(z) / math.sqrt(2)), 3)

    vix_lift = {}
    for mdir, mname in ((-1, "dn_move"), (1, "up_move")):
        for es_with, ename in ((True, "es_with"), (False, "es_against")):
            def pred(x, mdir=mdir, es_with=es_with):
                return x["mdir"] == mdir and x["es_with"] == es_with
            base = _cell(pred)
            conf = _cell(lambda x, p=pred: p(x) and x["vix_conf"])
            agst = _cell(lambda x, p=pred: p(x) and not x["vix_conf"])
            z, pv = _z(conf, base)
            vix_lift[f"{mname}|{ename}"] = dict(
                es_alone=base, vix_confirming=conf, vix_against=agst,
                z_conf_vs_es_alone=z, p_two_sided_naive=pv)

    ev_summary = {}
    res = [e for e in day_events if e["resumed"]]
    fail = [e for e in day_events if not e["resumed"]]
    for k in metrics:
        rv = [e[k] for e in res if e[k] is not None]
        fv = [e[k] for e in fail if e[k] is not None]
        a = auc(rv, fv)
        med = lambda v: sorted(v)[len(v) // 2] if v else None
        ev_summary[k] = dict(auc=round(a, 3) if a is not None else None,
                             resumed_median=round(med(rv), 3) if rv else None,
                             failed_median=round(med(fv), 3) if fv else None,
                             n_resumed=len(rv), n_failed=len(fv))

    # convergence score: how many of the three interpretable traces confirm
    combo = {}
    for s in samples:
        score = score3(s)
        if score is None:
            continue
        c = combo.setdefault(int(score), [0, 0])
        c[0] += 1
        c[1] += s["cont"]
    combo_table = {
        str(score): dict(n=n, cont=k, p_cont=round(k / n, 3))
        for score, (n, k) in sorted(combo.items())}
    scored = [(s["cont"], v) for s in samples if (v := score3(s)) is not None]
    combo_auc = auc([v for c, v in scored if c], [v for c, v in scored if not c])

    out = dict(samples=len(samples), summary=summary,
               event_summary=ev_summary, events=len(day_events),
               combo=dict(keys=list(COMBO_KEYS), table=combo_table,
                          auc=round(combo_auc, 3) if combo_auc else None,
                          gate=_gate_dict(grades["combo_score3"])),
               gate=dict(
                   note="every trace + the convergence score, graded by "
                        "residual_gate.grade_trace: raw AUC, residual after "
                        "the concurrent 5-min ES move is regressed out "
                        "(leave-one-day-out fit), the day-median of that "
                        "residual, and a leave-one-day-out clock+geometry "
                        "baseline on the same rows [st-4cgo]",
                   es_move_window_min=ES_MOVE_MIN,
                   traces={k: _gate_dict(g) for k, g in grades.items()},
                   markdown=markdown_table(list(grades.values()))),
               vix_lift_over_es_sign=vix_lift,
               day_rows=day_rows, minute_samples=samples)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"labeled minutes: {len(samples)} "
          f"(cont {sum(1 for s in samples if s['cont'])}, "
          f"term {sum(1 for s in samples if not s['cont'])}); "
          f"backtest events matched: {len(day_events)}", file=sys.stderr)
    for k, v in summary.items():
        print(f"  {k:16s} {json.dumps(v)}", file=sys.stderr)
    print("-- backtest-event cut --", file=sys.stderr)
    for k, v in ev_summary.items():
        print(f"  {k:16s} {json.dumps(v)}", file=sys.stderr)
    print("-- residual gate (st-4cgo) --", file=sys.stderr)
    for g in grades.values():
        print(f"  {g.line()}", file=sys.stderr)
    print(markdown_table(list(grades.values())), file=sys.stderr)
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
