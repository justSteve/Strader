#!/usr/bin/env python3
"""Residual gate — no trace publishes an AUC alone. [st-4cgo]

The 2026-08-04 audit (docs/audits/2026-08-04-auditor-report.md, §2.3/§5.3)
found that the residual test invented for the VIX trace was run twice — VIX,
then VVIX — and then dropped. The top-ranked trace, $TICK at AUC .665, never
got it, and fails it: its day-median residual is .507, a coin flip. The
auditor's prescription (§4.2) is this module:

    "a study script should refuse to emit a trace's AUC until it has emitted
     that trace's residual against concurrent price and its lift over a
     clock-plus-geometry baseline."

So `grade_trace()` is the only way to get a trace's AUC out of here, and it
returns four numbers or raises:

  (a) auc_raw          rank-sum AUC of the trace as reported
  (b) auc_residual     same, after regressing out the concurrent ES move
  (c) auc_residual_day_median   the day-clustered version of (b) — minutes
                       inside one morning are not independent draws, and this
                       is where $TICK died
  (d) auc_baseline     a trivial clock+geometry competitor fit on the SAME
                       rows: how well "how long has this move been running"
                       plus "how far inside its own extreme is price" grades
                       the label with no market data beyond ES

There is no `raw_auc(trace)` convenience and there will not be one. The
primitive `rank_auc(pos, neg)` is exported because it ranks two lists of
numbers and knows nothing about traces; a *trace grade* without its
companions cannot be constructed through this module's API.

Why these particular companions:

  residual   The VIX slope trace was ~80 % the concurrent ES move wearing a
             VIX costume (st-40fv). Any trace read off a market that is
             mechanically tied to ES can be the same thing. Regressing the
             trace on the concurrent 5-minute ES move and re-grading the
             residual asks: is there anything here that the price move you
             are already staring at does not already tell you?
  day-median A pooled AUC over 22 clustered mornings can be carried by two
             or three days. The median of per-day AUCs cannot.
  baseline   An AUC of .66 sounds like information until you learn that the
             clock alone grades the same label at .73 and price geometry at
             .79. A trace that does not beat the trivial competitor is not
             an instrument, it is a slower way to read a clock.

Row contract (`GateRow`): the caller supplies, per labeled minute, the trace
value, the CONT/TERM label, and three covariates — the concurrent ES move,
minutes elapsed since the move began, and points price sits inside the
standing extreme. All three are free by construction in any study that has
already built the label; the gate raises rather than silently skipping them.

Usage:
    from residual_gate import GateRow, grade_trace, markdown_table

    rows = [GateRow(date=s["date"], cont=s["cont"], value=s["tick_aligned"],
                    es_move=s["es5_aligned"], clock=s["elapsed_min"],
                    geometry=s["dist_ext"]) for s in samples]
    g = grade_trace("$TICK level x dir", rows)
    print(g.auc_raw, g.auc_residual, g.auc_residual_day_median, g.auc_baseline)

Self-test (asserts the gate refuses what it is supposed to refuse):
    .venv/bin/python3 scripts/measurement/residual_gate.py
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from statistics import median

# --- gate constants -------------------------------------------------------
# Deliberately loud rather than lenient: a study that cannot meet these has a
# data problem the operator should see, not a number the operator should read.
MIN_ROWS = 100        # usable (value + covariates) rows below which we refuse
MIN_DAYS = 5          # distinct days below which a day-median is theatre
MIN_COVERAGE = 0.80   # fraction of value-bearing rows that must carry es_move
# Verdict band around 0.5. Calibrated (not swept) so the gate reproduces the
# audit's own verbal verdicts on the five traces it graded by hand: $TICK
# .507 / $VOLD .530 / VIX .498 day-median all read "coin flip", $ADD .598
# reads "survives", ES delta .409 pooled reads "inverted".
EDGE = 0.05


class GateError(RuntimeError):
    """The gate could not grade a trace. Never swallow this — it means the
    study is about to publish an AUC it has not earned."""


@dataclass(frozen=True)
class GateRow:
    """One labeled minute, as the gate needs it.

    date      day key; the unit of clustering for every day-median
    cont      the label (True = continued)
    value     the trace's oriented value at this minute; None = trace blind
              here (an internals gap), row drops out of that trace's grade
    es_move   concurrent ES move over the trace's own horizon, oriented so
              positive = with the move. None where it is not measurable.
    clock     minutes elapsed since the move began
    geometry  points price sits inside the standing extreme (>= 0)
    """
    date: str
    cont: bool
    value: float | None
    es_move: float | None
    clock: float
    geometry: float


@dataclass(frozen=True)
class TraceGrade:
    """A trace's AUC and the three numbers that keep it honest."""
    trace: str
    n: int                      # rows the grade is computed on
    n_days: int
    n_dropped_no_es: int        # value present, concurrent ES move not
    auc_raw: float
    auc_raw_day_median: float
    auc_residual: float
    auc_residual_day_median: float
    auc_baseline: float
    auc_baseline_day_median: float
    es_beta: float              # trace units per ES point
    es_r2: float                # share of trace variance the ES move explains
    verdict: str                # SURVIVES / COIN FLIP / INVERTED
    beats_baseline: bool        # auc_raw > auc_baseline
    per_day_residual: list[float] = field(default_factory=list, repr=False)

    def line(self) -> str:
        """One-line stderr summary — the form a study prints while running."""
        return (f"{self.trace:26s} raw {self.auc_raw:.3f} "
                f"(day {self.auc_raw_day_median:.3f})  "
                f"resid {self.auc_residual:.3f} "
                f"(day {self.auc_residual_day_median:.3f})  "
                f"baseline {self.auc_baseline:.3f}  "
                f"n={self.n}  {self.verdict}"
                f"{'' if self.beats_baseline else '  [below trivial baseline]'}")


# --- primitives -----------------------------------------------------------

def rank_auc(pos, neg):
    """Rank-sum P(pos > neg) with tie credit — the Mann-Whitney AUC.

    Returns None when either side is empty. This is a statistic over two
    lists of numbers; it is not a trace grade (see the module docstring).
    """
    if not pos or not neg:
        return None
    sv = sorted(neg)
    wins = ties = 0
    for x in pos:
        lo = bisect.bisect_left(sv, x)
        hi = bisect.bisect_right(sv, x)
        wins += lo
        ties += hi - lo
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def _ols(pairs):
    """Least squares y = a + b*x over (x, y); returns (a, b, r2) or None."""
    n = len(pairs)
    if n < 2:
        return None
    sx = sum(x for x, _ in pairs)
    sy = sum(y for _, y in pairs)
    sxx = sum(x * x for x, _ in pairs)
    sxy = sum(x * y for x, y in pairs)
    den = n * sxx - sx * sx
    if den == 0:
        return None
    b = (n * sxy - sx * sy) / den
    a = (sy - b * sx) / n
    ybar = sy / n
    ss_tot = sum((y - ybar) ** 2 for _, y in pairs)
    ss_res = sum((y - a - b * x) ** 2 for x, y in pairs)
    return a, b, (1 - ss_res / ss_tot if ss_tot > 0 else 0.0)


def _solve(mat, rhs):
    """Gauss-Jordan with partial pivoting; returns the solution or None."""
    n = len(rhs)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(mat)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(aug[r][i]))
        if abs(aug[piv][i]) < 1e-12:
            return None                     # singular: a covariate is constant
        aug[i], aug[piv] = aug[piv], aug[i]
        for r in range(n):
            if r == i:
                continue
            f = aug[r][i] / aug[i][i]
            for c in range(i, n + 1):
                aug[r][c] -= f * aug[i][c]
    return [aug[i][n] / aug[i][i] for i in range(n)]


def _lpm_fit(rows, feats):
    """Linear probability model: OLS of the 0/1 label on `feats`.

    A logistic fit would be tidier but AUC is rank-only, and on two
    monotone covariates the LPM's ranking is the same. Keeping it to normal
    equations keeps the module stdlib-only, like the rest of this program.
    """
    k = len(feats) + 1
    des = [[1.0] + [getattr(r, f) for f in feats] for r in rows]
    y = [1.0 if r.cont else 0.0 for r in rows]
    xtx = [[sum(d[a] * d[b] for d in des) for b in range(k)] for a in range(k)]
    xty = [sum(d[a] * y[i] for i, d in enumerate(des)) for a in range(k)]
    return _solve(xtx, xty)


def _day_median_auc(scored):
    """Median of per-day AUCs over (date, cont, score) triples; also the list.

    Days where one class is absent contribute no AUC — that is a real
    property of the tape (a morning that continued for its whole labeled
    span has no TERM minutes), not something to impute.
    """
    per_day = []
    for d in sorted({t[0] for t in scored}):
        pos = [s for dd, c, s in scored if dd == d and c]
        neg = [s for dd, c, s in scored if dd == d and not c]
        a = rank_auc(pos, neg)
        if a is not None:
            per_day.append(a)
    per_day.sort()
    return (median(per_day) if per_day else None), per_day


# --- the gate -------------------------------------------------------------

def grade_trace(name: str, rows) -> TraceGrade:
    """Grade one trace, or raise. Returns raw AUC, residual AUC, day-median
    residual AUC and the trivial clock+geometry baseline on the same rows.

    Residual: the trace is regressed on the concurrent ES move with a
    leave-one-day-out fit (the convention st-40fv established for the VIX
    beta residual), so no day's residual is defined by a line that day helped
    draw. The reported `es_beta`/`es_r2` come from the pooled fit, which is
    what "how mechanical is this trace" means.

    Baseline: a leave-one-day-out linear probability model on
    (clock, geometry), scored out-of-fold. It is fit, so it must be
    out-of-fold or it flatters itself.

    Raises GateError on: no rows, one-class labels, thin samples
    (< MIN_ROWS usable / < MIN_DAYS days), missing covariates, or an
    ES-move series with no variance to regress against.
    """
    if not rows:
        raise GateError(f"{name}: no rows handed to the gate")
    for i, r in enumerate(rows):
        if r.clock is None or r.geometry is None:
            raise GateError(
                f"{name}: row {i} ({r.date}) is missing the clock/geometry "
                f"covariates. Both are free once the label exists — compute "
                f"them rather than grading without a baseline.")

    valued = [r for r in rows if r.value is not None]
    usable = [r for r in valued if r.es_move is not None]
    dropped = len(valued) - len(usable)
    if valued and len(usable) / len(valued) < MIN_COVERAGE:
        raise GateError(
            f"{name}: only {len(usable)}/{len(valued)} value-bearing rows "
            f"carry a concurrent ES move ({len(usable) / len(valued):.0%} < "
            f"{MIN_COVERAGE:.0%}). The residual is not gradeable on this "
            f"sample; fix the ES covariate before publishing an AUC.")
    if len(usable) < MIN_ROWS:
        raise GateError(f"{name}: {len(usable)} usable rows < MIN_ROWS="
                        f"{MIN_ROWS}")
    days = sorted({r.date for r in usable})
    if len(days) < MIN_DAYS:
        raise GateError(f"{name}: {len(days)} days < MIN_DAYS={MIN_DAYS}; a "
                        f"day-median over this many days is theatre")
    n_cont = sum(1 for r in usable if r.cont)
    if n_cont == 0 or n_cont == len(usable):
        raise GateError(f"{name}: labels are one-class on the usable rows "
                        f"({n_cont} CONT / {len(usable) - n_cont} TERM)")

    # --- (a) raw
    scored_raw = [(r.date, r.cont, r.value) for r in usable]
    auc_raw = rank_auc([s for _, c, s in scored_raw if c],
                       [s for _, c, s in scored_raw if not c])
    raw_dm, _ = _day_median_auc(scored_raw)

    # --- coupling + (b)/(c) residual
    pooled = _ols([(r.es_move, r.value) for r in usable])
    if pooled is None:
        raise GateError(f"{name}: the concurrent ES move has no variance on "
                        f"these rows — nothing to residualise against")
    loo = {}
    for d in days:
        f = _ols([(r.es_move, r.value) for r in usable if r.date != d])
        if f is None:
            raise GateError(f"{name}: leave-one-out fit failed with {d} held "
                            f"out — too few rows or a constant ES move")
        loo[d] = f
    scored_res = []
    for r in usable:
        a, b, _ = loo[r.date]
        scored_res.append((r.date, r.cont, r.value - (a + b * r.es_move)))
    auc_res = rank_auc([s for _, c, s in scored_res if c],
                       [s for _, c, s in scored_res if not c])
    res_dm, per_day_res = _day_median_auc(scored_res)

    # --- (d) trivial clock+geometry baseline, out-of-fold, same rows
    feats = ["clock", "geometry"]
    scored_base = []
    for d in days:
        coef = _lpm_fit([r for r in usable if r.date != d], feats)
        if coef is None:
            raise GateError(f"{name}: baseline fit is singular with {d} held "
                            f"out — clock or geometry is constant")
        for r in usable:
            if r.date == d:
                s = coef[0] + sum(coef[i + 1] * getattr(r, f)
                                  for i, f in enumerate(feats))
                scored_base.append((r.date, r.cont, s))
    auc_base = rank_auc([s for _, c, s in scored_base if c],
                        [s for _, c, s in scored_base if not c])
    base_dm, _ = _day_median_auc(scored_base)
    if auc_raw is None or auc_res is None or auc_base is None:
        raise GateError(f"{name}: one of the four AUCs came back None; the "
                        f"gate does not publish a partial grade")

    if auc_res < 0.5 - EDGE:
        verdict = "INVERTED"
    elif res_dm < 0.5 + EDGE:
        verdict = "COIN FLIP"
    else:
        verdict = "SURVIVES"

    return TraceGrade(
        trace=name, n=len(usable), n_days=len(days), n_dropped_no_es=dropped,
        auc_raw=round(auc_raw, 3), auc_raw_day_median=round(raw_dm, 3),
        auc_residual=round(auc_res, 3),
        auc_residual_day_median=round(res_dm, 3),
        auc_baseline=round(auc_base, 3),
        auc_baseline_day_median=round(base_dm, 3),
        es_beta=round(pooled[1], 4), es_r2=round(pooled[2], 3),
        verdict=verdict, beats_baseline=bool(auc_raw > auc_base),
        per_day_residual=[round(x, 3) for x in per_day_res])


def grade_all(traces: dict) -> dict:
    """Grade every trace in {name: [GateRow, ...]}; raises on the first
    trace that cannot be graded, by design — a table with one ungated row
    is exactly the artifact this module exists to prevent."""
    return {name: grade_trace(name, rows) for name, rows in traces.items()}


def markdown_table(grades) -> str:
    """The gate's table, ready to paste into a measurement doc.

    Ordered by raw AUC descending, i.e. the ranking a reader would have
    trusted before the gate existed — so the collapse is legible row by row.
    """
    gs = sorted(grades, key=lambda g: g.auc_raw, reverse=True)
    out = ["| Trace (oriented) | raw AUC | day med | **residual** | **resid day med** | trivial baseline | verdict |",
           "|---|---|---|---|---|---|---|"]
    for g in gs:
        out.append(f"| {g.trace} | {g.auc_raw:.3f} | {g.auc_raw_day_median:.3f} "
                   f"| **{g.auc_residual:.3f}** | **{g.auc_residual_day_median:.3f}** "
                   f"| {g.auc_baseline:.3f} | {g.verdict} |")
    return "\n".join(out)


def _self_test():
    """Prove the gate refuses what it must refuse, on synthetic rows."""
    import random
    rng = random.Random(7)
    days = [f"d{i}" for i in range(20)]

    def rows(value_fn, es_fn=None, n=150):
        out = []
        for d in days:
            for i in range(n):
                cont = rng.random() < 0.55
                es = rng.gauss(1.0 if cont else -0.5, 2.0)
                out.append(GateRow(date=d, cont=cont,
                                   value=value_fn(cont, es, rng),
                                   es_move=es if es_fn is None else es_fn(es),
                                   clock=float(i),
                                   geometry=abs(rng.gauss(0, 3))))
        return out

    # a pure costume: the trace IS the ES move plus noise -> residual ~ .5
    costume = grade_trace("costume", rows(lambda c, es, r: 3 * es + r.gauss(0, 0.3)))
    assert costume.auc_raw > 0.6, costume
    assert abs(costume.auc_residual - 0.5) < 0.05, costume
    assert abs(costume.auc_residual_day_median - 0.5) < 0.06, costume
    assert costume.verdict == "COIN FLIP", costume
    # genuine independent signal -> residual survives
    real = grade_trace("real", rows(lambda c, es, r: (1.5 if c else -1.5) + r.gauss(0, 1)))
    assert real.auc_residual > 0.7, real
    assert real.verdict == "SURVIVES", real

    def refuses(what, **kw):
        try:
            grade_trace("x", **kw)
        except GateError as e:
            print(f"  refuses {what}: {e}")
            return True
        return False

    assert refuses("empty input", rows=[])
    assert refuses("thin sample", rows=rows(lambda c, e, r: e, n=2))
    thin_days = [r for r in rows(lambda c, e, r: e) if r.date in days[:3]]
    assert refuses("too few days", rows=thin_days)
    blind = [GateRow(r.date, r.cont, r.value, None, r.clock, r.geometry)
             for r in rows(lambda c, e, r: e)]
    assert refuses("no ES covariate", rows=blind)
    noclock = [GateRow(r.date, r.cont, r.value, r.es_move, None, r.geometry)
               for r in rows(lambda c, e, r: e)]
    assert refuses("no clock covariate", rows=noclock)
    flat = [GateRow(r.date, r.cont, r.value, 1.0, r.clock, r.geometry)
            for r in rows(lambda c, e, r: e)]
    assert refuses("constant ES move", rows=flat)
    one_class = [GateRow(r.date, True, r.value, r.es_move, r.clock, r.geometry)
                 for r in rows(lambda c, e, r: e)]
    assert refuses("one-class labels", rows=one_class)

    # grade_all + markdown_table are the API sibling studies will reach for
    both = grade_all({"costume": rows(lambda c, es, r: 3 * es + r.gauss(0, 0.3)),
                      "real": rows(lambda c, es, r: (1.5 if c else -1.5)
                                   + r.gauss(0, 1))})
    assert set(both) == {"costume", "real"}, both
    table = markdown_table(list(both.values()))
    assert table.count("\n") == 3, table          # header + rule + two rows
    try:
        grade_all({"ok": rows(lambda c, e, r: e), "bad": []})
    except GateError as e:
        print(f"  refuses a batch containing one ungradeable trace: {e}")
    else:
        raise AssertionError("grade_all graded a batch it should have refused")

    print("  costume:", costume.line())
    print("  real   :", real.line())
    print("residual_gate self-test OK")


if __name__ == "__main__":
    _self_test()
