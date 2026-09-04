"""The estimated mark path — a per-minute ES->premium proxy for 0DTE SPXW
singles. [st-9hhc]

WHY
    The blotter needs a minute path on days with no OPRA prints, and "the ITM
    single tracks ES at +0.91" is a correlation, not a conversion
    (docs/measurement/final-hour-premium-vs-es-2026-08-29.md:31). This module
    is the conversion: premium change per minute = delta x the ES move in the
    option's favour, plus a decay term, both CALIBRATED against the actual
    print path over the window where prints exist.

THE MODEL
    Walking minute t-1 -> t:

        mark(t) = max(0, mark(t-1) + delta * d_fav + theta * dt_minutes)

    where d_fav is the ES move in the option's favour over the step (signed:
    up for a call, down for a put), and (delta, theta) come from a calibration
    table keyed by the option's CURRENT moneyness bin and minutes-to-close
    bucket — both evolve along the path, so a single that goes from ATM to
    ITM picks up delta as it should. theta is signed points per minute and is
    expected negative (0DTE decay).

    ``path_cells`` is the single source of the state convention (which
    minute's moneyness and time-to-close key the step). Calibration fitting
    and path walking both consume it, so they cannot disagree.

THE COVERAGE BOUND
    Prints exist 13:00-15:00 CT only (measured, strader/marks/prints.py), so
    the calibration can only ever be validated there. ``estimated_path``
    REFUSES an entry outside that window unless the caller passes
    ``allow_extrapolation=True``, and then every emitted point outside the
    window carries ``extrapolated=True``. Silent extrapolation is not a mode
    this module has.

    Spot is carried from the entry as spot_entry + (ES(t) - ES(entry)); the
    ES/SPX basis drift over a <=2h window is ignored (reasoned, not measured
    — the moneyness bins are 10 pts wide and basis drift over two hours is a
    fraction of that).

DETERMINISM
    Pure functions of their inputs, stdlib only, no network, no clock reads.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from strader.marks.prints import WINDOW_END_S, WINDOW_START_S

#: Moneyness bin edges, SPX pts ITM (negative = OTM). Bins:
#:   0: OTM by more than 5 · 1: within 5 of the money · 2: ITM by more than 5
MBIN_EDGES = (-5.0, 5.0)
MBIN_NAMES = ("otm", "near", "itm")

#: Minutes-to-close bucket edges. Buckets:
#:   0: (0, 15] · 1: (15, 30] · 2: (30, 60] · 3: (60, 90] · 4: over 90
TTC_EDGES = (15.0, 30.0, 60.0, 90.0)

#: A calibration cell with fewer samples than this falls back to the
#: pooled-over-time fit for its moneyness bin.
MIN_CELL_N = 100

#: The operative calibration artifact, repo-root relative — regenerate with
#: scripts/measurement/estimated_mark_calibrate.py.
DEFAULT_CALIBRATION_PATH = "data/measurement/estimated-mark-calibration-2026-09-01.json"


class CoverageBound(Exception):
    """Asked for estimated marks outside the calibrated 13:00-15:00 CT window
    without saying so. Pass allow_extrapolation=True to get labelled
    extrapolation instead of this refusal."""


def mbin(moneyness_pts: float) -> int:
    """SPX pts ITM (negative = OTM) -> moneyness bin index."""
    if moneyness_pts <= MBIN_EDGES[0]:
        return 0
    if moneyness_pts < MBIN_EDGES[1]:
        return 1
    return 2


def ttc_bucket(minutes_to_close: float) -> int:
    """Minutes to the 15:00 CT close -> bucket index."""
    for i, edge in enumerate(TTC_EDGES):
        if minutes_to_close <= edge:
            return i
    return len(TTC_EDGES)


@dataclass(frozen=True)
class Calibration:
    """The fitted (delta, theta) table.

    ``table`` maps (mbin, ttc_bucket) -> (delta, theta_pts_per_min, n).
    ``fallback`` maps mbin -> the same, pooled over all time buckets.
    ``pooled`` is the fit over everything, the last resort.
    ``fit_days`` names the day range the fit consumed — provenance, so a
    calibration file always says what it was fitted on.
    """

    table: dict = field(default_factory=dict)
    fallback: dict = field(default_factory=dict)
    pooled: tuple = (0.0, 0.0, 0)
    fit_days: str = ""
    version: int = 1

    def cell(self, mi: int, ti: int) -> tuple[float, float]:
        """(delta, theta) for a state, falling back when the cell is thin."""
        got = self.table.get((mi, ti))
        if got and got[2] >= MIN_CELL_N:
            return got[0], got[1]
        got = self.fallback.get(mi)
        if got and got[2] >= MIN_CELL_N:
            return got[0], got[1]
        return self.pooled[0], self.pooled[1]

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "fit_days": self.fit_days,
                "mbin_edges": list(MBIN_EDGES),
                "ttc_edges": list(TTC_EDGES),
                "table": {f"{mi},{ti}": list(v) for (mi, ti), v in sorted(self.table.items())},
                "fallback": {str(mi): list(v) for mi, v in sorted(self.fallback.items())},
                "pooled": list(self.pooled),
            },
            indent=1,
        )

    @classmethod
    def from_json(cls, text: str) -> "Calibration":
        d = json.loads(text)
        if list(d.get("mbin_edges", [])) != list(MBIN_EDGES) or list(d.get("ttc_edges", [])) != list(TTC_EDGES):
            raise ValueError(
                "calibration bin edges do not match this code's: refit rather than reinterpret"
            )
        return cls(
            table={
                (int(k.split(",")[0]), int(k.split(",")[1])): tuple(v)
                for k, v in d["table"].items()
            },
            fallback={int(k): tuple(v) for k, v in d["fallback"].items()},
            pooled=tuple(d["pooled"]),
            fit_days=d.get("fit_days", ""),
            version=int(d.get("version", 1)),
        )

    @classmethod
    def load(cls, path: str) -> "Calibration":
        with open(path) as f:
            return cls.from_json(f.read())


def path_cells(side: str, strike: float, spot_entry: float, entry_ct_s: int,
               es_minutes: list[tuple[int, float]]):
    """The state convention, in one place.

    Yields one step per ES minute after entry:
    ``(t_ct_s, d_fav_pts, mi, ti)`` where d_fav is the ES move in the
    option's favour over the step and (mi, ti) key the step from the state at
    the step's START — the moneyness and time-to-close the option had before
    the move, which is what both calibration and walking must use.

    ``es_minutes`` is a whole-minute CT grid ascending (see
    prints.load_day_es_minutes). Steps are emitted only between consecutive
    grid minutes at or after the entry minute.
    """
    sign = 1 if side == "C" else -1
    prev_t = prev_es = es_entry = None
    for t, es in es_minutes:
        if t < entry_ct_s:
            continue
        if prev_t is None:
            prev_t, prev_es, es_entry = t, es, es
            continue
        if t - prev_t != 60:  # a hole in the grid: re-anchor, emit nothing
            prev_t, prev_es = t, es
            continue
        spot_prev = spot_entry + (prev_es - es_entry)
        m = (spot_prev - strike) if side == "C" else (strike - spot_prev)
        ti = ttc_bucket((WINDOW_END_S - prev_t) / 60.0)
        d_fav = sign * (es - prev_es)
        yield t, d_fav, mbin(m), ti
        prev_t, prev_es = t, es


@dataclass(frozen=True)
class MarkPoint:
    ct_s: int
    mark: float
    extrapolated: bool


def estimated_path(side: str, strike: float, entry_premium: float,
                   spot_entry: float, entry_ct_s: int,
                   es_minutes: list[tuple[int, float]], cal: Calibration,
                   allow_extrapolation: bool = False) -> list[MarkPoint]:
    """The proxy path: entry point plus one MarkPoint per ES minute after it.

    Refuses (CoverageBound) when the entry or any requested minute lies
    outside 13:00-15:00 CT, unless ``allow_extrapolation=True`` — in which
    case those points are emitted with ``extrapolated=True`` so no consumer
    can mistake them for calibrated marks.
    """
    if side not in ("C", "P"):
        raise ValueError(f"side must be 'C' or 'P', got {side!r}")
    if entry_premium <= 0:
        raise ValueError(f"entry_premium must be positive, got {entry_premium}")

    def outside(t: int) -> bool:
        return t < WINDOW_START_S or t > WINDOW_END_S

    if outside(entry_ct_s) and not allow_extrapolation:
        raise CoverageBound(
            f"entry {entry_ct_s} ({entry_ct_s // 3600:02d}:{entry_ct_s % 3600 // 60:02d} CT) is outside "
            f"the calibrated 13:00-15:00 CT window; prints to validate against do not exist there. "
            f"Pass allow_extrapolation=True to get labelled extrapolation."
        )

    out = [MarkPoint(entry_ct_s, entry_premium, outside(entry_ct_s))]
    mark = entry_premium
    for t, d_fav, mi, ti in path_cells(side, strike, spot_entry, entry_ct_s, es_minutes):
        if outside(t) and not allow_extrapolation:
            raise CoverageBound(
                f"minute {t} is outside the calibrated 13:00-15:00 CT window; "
                f"pass allow_extrapolation=True to get labelled extrapolation."
            )
        delta, theta = cal.cell(mi, ti)
        mark = max(0.0, mark + delta * d_fav + theta * 1.0)
        out.append(MarkPoint(t, mark, outside(t)))
    return out


def first_at_or_below(path: list[MarkPoint], level: float) -> MarkPoint | None:
    """First point after the entry at/below ``level`` — the proxy-resolution
    stop fire. Minute resolution: that is all the proxy has, and the
    validation reports what that costs."""
    for pt in path[1:]:
        if pt.mark <= level:
            return pt
    return None


def first_at_or_above(path: list[MarkPoint], level: float) -> MarkPoint | None:
    """First point after the entry at/above ``level`` — the proxy-resolution
    target touch."""
    for pt in path[1:]:
        if pt.mark >= level:
            return pt
    return None


def fit_calibration(samples, fit_days: str) -> Calibration:
    """OLS per cell over per-minute samples ``(mi, ti, d_fav_pts, d_mark_pts)``.

    delta is the slope of d_mark on d_fav; theta is the intercept (pts per
    minute, the drift with no ES move — the decay term). Cells, per-mbin
    fallbacks and the pooled fit are all fitted the same way. Sample order is
    the caller's; feed a deterministic order and the fit is deterministic.
    """
    acc: dict[tuple, list[float]] = {}

    def add(key, x, y):
        a = acc.setdefault(key, [0.0, 0.0, 0.0, 0.0, 0.0])  # n, sx, sy, sxx, sxy
        a[0] += 1
        a[1] += x
        a[2] += y
        a[3] += x * x
        a[4] += x * y

    for mi, ti, x, y in samples:
        add((mi, ti), x, y)
        add(("mbin", mi), x, y)
        add(("all",), x, y)

    def fit(a) -> tuple[float, float, int]:
        n, sx, sy, sxx, sxy = a
        n = int(n)
        if n == 0:
            return 0.0, 0.0, 0
        var = sxx - sx * sx / n
        if var <= 1e-12:
            return 0.0, round(sy / n, 6), n
        slope = (sxy - sx * sy / n) / var
        intercept = (sy - slope * sx) / n
        return round(slope, 6), round(intercept, 6), n

    table = {k: fit(v) for k, v in acc.items() if isinstance(k[0], int)}
    fallback = {k[1]: fit(v) for k, v in acc.items() if k[0] == "mbin"}
    pooled = fit(acc.get(("all",), [0.0] * 5))
    return Calibration(table=table, fallback=fallback, pooled=pooled, fit_days=fit_days)
