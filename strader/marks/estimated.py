"""Estimated mark path — a per-minute ES->premium proxy for a 0DTE SPX single. [st-9hhc]

WHY
    The blotter marks OPRA-less days from the ES tape. The number it inherited
    for that, "+0.91", is a Pearson correlation between the ES net move and the
    option's close-to-close return (docs/measurement/final-hour-premium-vs-es-
    2026-08-29.md:31), not premium points per ES point, and the real conversion
    in that document is close-only: one number per day at 15:00. A stop or a
    target needs a path, not a close. This module is the path.

WHAT
    A pure function of its inputs. Given a leg (right, strike, entry premium,
    SPX and ES at entry, entry minute) and the ES minute bars that follow, it
    returns a premium mark per minute:

        mark(t) = max( intrinsic(S(t)),
                       P_entry + delta_hat * fav_move(t)
                               - TV_entry * (1 - (tau(t) / tau_entry) ** kappa) )

    where
        S(t)        = S_entry + (ES(t) - ES_entry)            reasoned: the
                      SPX-ES basis is taken as constant over the window
        fav_move(t) = ES move in the option's favour, SPX points (put: down)
        TV_entry    = max(0, P_entry - intrinsic(S_entry))    the time value
                      bought at entry, which decays to zero at the close
        tau(t)      = minutes to 15:00 CT; tau_entry likewise at entry
        delta_hat   = premium points per favourable ES point, calibrated per
                      (right, moneyness bin at entry)
        kappa       = the decay shape, calibrated per the same bin; 0.5 is the
                      square-root-of-time an at-the-money option decays on

    Both calibrated numbers come from prints (scripts/measurement/
    estimated_mark_calibrate.py) and arrive in a :class:`Calibration`. There is
    no default calibration in code. A leg whose bin was not calibrated is
    refused (:class:`Uncalibrated`), not guessed.

    Two marks per minute: at the minute's closing ES, and at the minute's ES
    extreme against the position. A 0.30 stop is touched by the extreme, not
    the close, so the validation scores stop timing on both and the blotter
    has to pick one on the record.

THE COVERAGE GUARD
    Prints exist 13:00-15:00 CT only, on every corpus day, so that is the only
    window the calibration can speak for. A minute outside the calibration's
    window raises :class:`CoverageError` unless the caller passes
    ``allow_extrapolation=True``, and then every such point carries
    ``extrapolated=True``. Nothing here applies a late-day calibration to a
    10:15 fire silently.

UNITS
    ``*_pts``  option premium in points (1 pt = $100 on one contract).
    ``*_spx``  SPX index points; ES points are treated as SPX points through
               the constant-basis assumption above.
    Minutes are CT wall-clock strings "HH:MM". Never UTC.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

__all__ = [
    "BinFit", "Calibration", "CoverageError", "Uncalibrated",
    "LegEntry", "MinuteBar", "MarkPoint", "CalibrationRow",
    "SESSION_CLOSE_CT", "DEFAULT_WINDOW_CT", "BIN_WIDTH_SPX", "BIN_EDGES_SPX",
    "KAPPA_GRID", "MIN_ROWS_PER_BIN", "MIN_LEGS_PER_BIN", "DEAD_PTS",
    "minute_index", "minutes_to_close", "moneyness_spx", "bin_lower_edge",
    "intrinsic_pts", "estimate_mark", "estimate_path", "fit_bin",
]

SESSION_CLOSE_CT = "15:00"
DEFAULT_WINDOW_CT = ("13:00", "15:00")

# Moneyness at entry, ITM-positive, SPX points. A ~10 ITM single lands in the
# [10, 15) bin; ATM in [0, 5); ~10 OTM in [-10, -5). Outside the edges the
# model refuses rather than reaching for the nearest bin.
BIN_WIDTH_SPX = 5
BIN_EDGES_SPX = (-20, 20)

# Decay-shape candidates for the grid search. Deterministic by construction.
# A fit that lands on either edge is reported as such by the write-up: the
# data wanted to go further than the grid allows, and that is worth a look.
KAPPA_GRID = (0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)

MIN_ROWS_PER_BIN = 200
MIN_LEGS_PER_BIN = 5

# A print at or below this is a dead option sitting on the zero floor. Such
# rows say nothing about the slope — the floor answers them — so the fit
# leaves them out and the residual puts them back in.
DEAD_PTS = 0.10


class CoverageError(ValueError):
    """A minute outside the calibration window was asked for without
    ``allow_extrapolation``. The proxy knows nothing about that minute and
    says so, instead of drawing a number a P&L column would trust."""


class Uncalibrated(LookupError):
    """No fit exists for this (right, moneyness bin). The calibration either
    never saw enough legs there or was never run; either way the model has no
    number to offer."""


# ---------------------------------------------------------------- time ---

def minute_index(hhmm: str) -> int:
    """"14:03" -> 843, minutes since midnight CT. Strict: two-digit fields."""
    if len(hhmm) != 5 or hhmm[2] != ":":
        raise ValueError(f"minute must be 'HH:MM' CT, got {hhmm!r}")
    h, m = int(hhmm[:2]), int(hhmm[3:])
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"minute out of range: {hhmm!r}")
    return h * 60 + m


def minute_label(idx: int) -> str:
    return f"{idx // 60:02d}:{idx % 60:02d}"


def minutes_to_close(hhmm: str, close: str = SESSION_CLOSE_CT) -> int:
    """tau: whole minutes from ``hhmm`` to the session close, floored at 0."""
    return max(0, minute_index(close) - minute_index(hhmm))


# ----------------------------------------------------------- moneyness ---

def moneyness_spx(right: str, strike: float, spx: float) -> float:
    """ITM-positive distance in SPX points: put above spot, call below."""
    r = _right(right)
    return (strike - spx) if r == "P" else (spx - strike)


def bin_lower_edge(moneyness: float, width: int = BIN_WIDTH_SPX) -> int:
    return int(math.floor(moneyness / width) * width)


def intrinsic_pts(right: str, strike: float, spx: float) -> float:
    r = _right(right)
    return max(0.0, (strike - spx) if r == "P" else (spx - strike))


def _right(right: str) -> str:
    r = right.upper()[:1]
    if r not in ("P", "C"):
        raise ValueError(f"right must be P or C (or PUT/CALL), got {right!r}")
    return r


# ---------------------------------------------------------------- types ---

@dataclass(frozen=True)
class BinFit:
    """One calibrated cell: a (right, moneyness bin) pair and its two numbers."""

    right: str                  # "P" | "C"
    bin_lo: int                 # lower edge of the moneyness bin, SPX pts, ITM-positive
    delta_pts_per_es: float     # premium points per favourable ES point
    kappa: float                # decay exponent on tau/tau_entry
    n_rows: int                 # minute rows in the bin, dead ones included
    n_live: int                 # rows the slope was fitted on (print > DEAD_PTS)
    n_legs: int                 # distinct leg-days behind those rows
    resid_mae_pts: float        # mean |proxy - print| over ALL rows, floors applied, pts
    resid_p50_pts: float        # median signed (proxy - print) over all rows, pts

    def to_dict(self) -> dict:
        return {
            "right": self.right, "bin_lo": self.bin_lo,
            "delta_pts_per_es": self.delta_pts_per_es, "kappa": self.kappa,
            "n_rows": self.n_rows, "n_live": self.n_live, "n_legs": self.n_legs,
            "resid_mae_pts": self.resid_mae_pts, "resid_p50_pts": self.resid_p50_pts,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "BinFit":
        return cls(right=str(d["right"]), bin_lo=int(d["bin_lo"]),
                   delta_pts_per_es=float(d["delta_pts_per_es"]), kappa=float(d["kappa"]),
                   n_rows=int(d["n_rows"]), n_live=int(d.get("n_live", d["n_rows"])), n_legs=int(d["n_legs"]),
                   resid_mae_pts=float(d["resid_mae_pts"]), resid_p50_pts=float(d["resid_p50_pts"]))


@dataclass(frozen=True)
class Calibration:
    """The proxy's numbers, and the record of where they came from.

    ``window_ct`` is the only span the fits can speak for. ``days`` is every
    corpus day the fit consumed, so a validation can tell in-sample from
    holdout by membership. ``coverage`` is the measured print coverage of
    those days (first/last print minute per day), carried here so the
    coverage bound travels with the numbers it bounds.
    """

    window_ct: tuple[str, str] = DEFAULT_WINDOW_CT
    bin_width: int = BIN_WIDTH_SPX
    fits: dict[tuple[str, int], BinFit] = field(default_factory=dict)
    days: tuple[str, ...] = ()
    coverage: dict = field(default_factory=dict)
    source: dict = field(default_factory=dict)   # script, arguments, corpus root

    def fit_for(self, right: str, moneyness: float) -> BinFit:
        r = _right(right)
        lo, hi = BIN_EDGES_SPX
        if not (lo <= moneyness < hi):
            raise Uncalibrated(
                f"moneyness {moneyness:+.1f} SPX pts lies outside the calibrated "
                f"edges [{lo:+d}, {hi:+d}); the proxy has no fit there")
        key = (r, bin_lower_edge(moneyness, self.bin_width))
        try:
            return self.fits[key]
        except KeyError:
            raise Uncalibrated(
                f"no fit for right={r} moneyness bin [{key[1]:+d}, "
                f"{key[1] + self.bin_width:+d}); calibrated bins: "
                f"{sorted(self.fits)}") from None

    def in_window(self, hhmm: str) -> bool:
        a, b = self.window_ct
        return minute_index(a) <= minute_index(hhmm) < minute_index(b)

    def to_dict(self) -> dict:
        return {
            "window_ct": list(self.window_ct),
            "bin_width": self.bin_width,
            "fits": [self.fits[k].to_dict() for k in sorted(self.fits)],
            "days": list(self.days),
            "coverage": self.coverage,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "Calibration":
        fits = {}
        for row in d.get("fits", []):
            f = BinFit.from_dict(row)
            fits[(f.right, f.bin_lo)] = f
        w = d.get("window_ct", list(DEFAULT_WINDOW_CT))
        return cls(window_ct=(str(w[0]), str(w[1])), bin_width=int(d.get("bin_width", BIN_WIDTH_SPX)),
                   fits=fits, days=tuple(d.get("days", ())), coverage=dict(d.get("coverage", {})),
                   source=dict(d.get("source", {})))

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=1, sort_keys=True) + "\n")

    @classmethod
    def load(cls, path: Path) -> "Calibration":
        with open(path) as f:
            return cls.from_dict(json.load(f))


@dataclass(frozen=True)
class LegEntry:
    """A single, as bought: what the proxy is asked to mark."""

    right: str                  # "P" | "C"
    strike: float
    entry_premium_pts: float
    entry_spx: float            # SPX at the entry print (parity-inferred on the corpus)
    entry_es: float             # last ES print at or before the entry print
    entry_minute: str           # "HH:MM" CT, the minute the entry printed in

    @property
    def moneyness(self) -> float:
        return moneyness_spx(self.right, self.strike, self.entry_spx)

    @property
    def time_value_pts(self) -> float:
        return max(0.0, self.entry_premium_pts - intrinsic_pts(self.right, self.strike, self.entry_spx))

    @property
    def fav_sign(self) -> float:
        return -1.0 if _right(self.right) == "P" else 1.0


@dataclass(frozen=True, slots=True)
class MinuteBar:
    minute: str                 # "HH:MM" CT; the bar covers HH:MM:00-HH:MM:59
    open: float
    high: float
    low: float
    close: float
    n: int = 0


@dataclass(frozen=True, slots=True)
class MarkPoint:
    minute: str
    premium_pts: float          # proxy at the minute's closing ES
    adverse_pts: float          # proxy at the minute's ES extreme against the leg
    favourable_pts: float       # proxy at the minute's ES extreme for the leg
    extrapolated: bool          # outside the calibration window


@dataclass(frozen=True, slots=True)
class CalibrationRow:
    """One minute of one leg-day, as the fit consumes it. Slotted: the full
    corpus produces on the order of a million of these in one process."""

    leg_id: str
    right: str                  # "P" | "C"
    bin_lo: int                 # the leg's moneyness bin at entry
    fav_move: float             # ES move in the leg's favour since entry, pts
    tau_ratio: float            # tau(t) / tau_entry in (0, 1]
    tv_entry_pts: float
    y_pts: float                # print mark - entry premium
    entry_premium_pts: float = 0.0
    intrinsic_now_pts: float = 0.0   # intrinsic at this minute's ES, through the constant basis

    @property
    def print_pts(self) -> float:
        return self.entry_premium_pts + self.y_pts


# ---------------------------------------------------------------- model ---

def estimate_mark(*, entry_premium_pts: float, tv_entry_pts: float, delta: float, kappa: float,
                  fav_move: float, tau_ratio: float, intrinsic_now_pts: float) -> float:
    """The proxy at one instant. See the module docstring for the formula."""
    if tau_ratio < 0.0 or tau_ratio > 1.0:
        raise ValueError(f"tau_ratio must lie in [0, 1], got {tau_ratio}")
    decayed = tv_entry_pts * (1.0 - tau_ratio ** kappa)
    raw = entry_premium_pts + delta * fav_move - decayed
    return max(0.0, intrinsic_now_pts, raw)


def estimate_path(leg: LegEntry, bars: Sequence[MinuteBar], cal: Calibration, *,
                  allow_extrapolation: bool = False,
                  close: str = SESSION_CLOSE_CT) -> list[MarkPoint]:
    """Mark ``leg`` at every bar at or after its entry minute, up to the close.

    Bars before the entry minute are ignored; bars at or after ``close`` are
    ignored (the session is over). Bars need not be contiguous — a missing
    minute is simply absent from the result, never filled in.
    """
    fit = cal.fit_for(leg.right, leg.moneyness)
    entry_idx = minute_index(leg.entry_minute)
    close_idx = minute_index(close)
    tau_entry = close_idx - entry_idx
    if tau_entry <= 0:
        raise ValueError(f"entry minute {leg.entry_minute} is not before the close {close}")
    if not cal.in_window(leg.entry_minute) and not allow_extrapolation:
        raise CoverageError(
            f"entry minute {leg.entry_minute} CT is outside the calibrated window "
            f"{cal.window_ct[0]}-{cal.window_ct[1]} CT; pass allow_extrapolation=True "
            f"to mark it anyway, labelled")
    sign = leg.fav_sign
    tv = leg.time_value_pts
    out: list[MarkPoint] = []
    for bar in sorted(bars, key=lambda b: minute_index(b.minute)):
        idx = minute_index(bar.minute)
        if idx < entry_idx or idx >= close_idx:
            continue
        inside = cal.in_window(bar.minute)
        if not inside and not allow_extrapolation:
            raise CoverageError(
                f"minute {bar.minute} CT is outside the calibrated window "
                f"{cal.window_ct[0]}-{cal.window_ct[1]} CT")
        # tau at the bar's close: the bar ends at idx+1.
        tau_ratio = max(0, close_idx - (idx + 1)) / tau_entry
        adverse_es = bar.low if sign > 0 else bar.high
        favour_es = bar.high if sign > 0 else bar.low
        marks = []
        for es in (bar.close, adverse_es, favour_es):
            spx_now = leg.entry_spx + (es - leg.entry_es)
            marks.append(estimate_mark(
                entry_premium_pts=leg.entry_premium_pts, tv_entry_pts=tv,
                delta=fit.delta_pts_per_es, kappa=fit.kappa,
                fav_move=sign * (es - leg.entry_es), tau_ratio=tau_ratio,
                intrinsic_now_pts=intrinsic_pts(leg.right, leg.strike, spx_now)))
        out.append(MarkPoint(minute=bar.minute, premium_pts=round(marks[0], 4),
                             adverse_pts=round(marks[1], 4), favourable_pts=round(marks[2], 4),
                             extrapolated=not inside))
    return out


# ------------------------------------------------------------------ fit ---

def fit_bin(right: str, bin_lo: int, rows: Iterable[CalibrationRow], *,
            kappa_grid: Sequence[float] = KAPPA_GRID,
            min_rows: int = MIN_ROWS_PER_BIN, min_legs: int = MIN_LEGS_PER_BIN) -> BinFit | None:
    """Least squares through the origin for delta, grid search for kappa.

    The slope is fitted on the LIVE rows — prints above :data:`DEAD_PTS`. A
    dead option sits on the zero floor whatever ES does next, so its rows
    carry no slope information and would only drag delta toward zero; at
    prediction time the floor answers them. For each candidate kappa the
    decay is removed from the observed premium change, leaving
    z = y + TV_entry * (1 - r**kappa), and delta is the slope of z on the
    favourable move with no intercept — at zero move and zero decay the mark
    is the entry premium by construction. The kappa with the smallest squared
    residual on the live rows wins.

    The residual is then measured on ALL rows with the floors applied,
    exactly as :func:`estimate_mark` predicts, so the number reported is the
    number the blotter would see. Sums are ``math.fsum`` over rows sorted by
    (leg_id, tau_ratio) so two runs over the same rows agree to the bit.

    Returns None when the bin is too thin to trust; the caller records the
    gap rather than filling it.
    """
    r = _right(right)
    rows = sorted(rows, key=lambda x: (x.leg_id, -x.tau_ratio, x.fav_move))
    n_legs = len({x.leg_id for x in rows})
    if len(rows) < min_rows or n_legs < min_legs:
        return None
    live = [x for x in rows if x.print_pts > DEAD_PTS]
    if len(live) < min_rows or len({x.leg_id for x in live}) < min_legs:
        return None
    sxx = math.fsum(x.fav_move * x.fav_move for x in live)
    best: tuple[float, float, float] | None = None   # (sse, kappa, delta)
    for kappa in kappa_grid:
        z = [x.y_pts + x.tv_entry_pts * (1.0 - x.tau_ratio ** kappa) for x in live]
        delta = math.fsum(zi * x.fav_move for zi, x in zip(z, live)) / sxx if sxx > 0 else 0.0
        delta = max(0.0, delta)
        sse = math.fsum((zi - delta * x.fav_move) ** 2 for zi, x in zip(z, live))
        if best is None or sse < best[0] - 1e-12:
            best = (sse, kappa, delta)
    assert best is not None
    _, kappa, delta = best
    resid = sorted(
        estimate_mark(entry_premium_pts=x.entry_premium_pts, tv_entry_pts=x.tv_entry_pts, delta=delta,
                      kappa=kappa, fav_move=x.fav_move, tau_ratio=x.tau_ratio,
                      intrinsic_now_pts=x.intrinsic_now_pts) - x.print_pts
        for x in rows)
    mae = math.fsum(abs(e) for e in resid) / len(resid)
    p50 = resid[len(resid) // 2] if len(resid) % 2 else (resid[len(resid) // 2 - 1] + resid[len(resid) // 2]) / 2
    return BinFit(right=r, bin_lo=int(bin_lo), delta_pts_per_es=round(delta, 4), kappa=kappa,
                  n_rows=len(rows), n_live=len(live), n_legs=n_legs,
                  resid_mae_pts=round(mae, 4), resid_p50_pts=round(p50, 4))
