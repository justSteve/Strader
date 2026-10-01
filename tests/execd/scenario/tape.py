"""Tapes — the market a scenario runs against. [st-ug1h]

A :class:`Tape` is the index path (one :class:`Frame` per moment, seconds
from the tape's start) plus the rule that turns an index level into an
option quote (:class:`OptionModel`). Every quote the replay serves is a pure
function of the clock, so a scenario is reproducible to the cent: the same
tape and the same steps give the same journal.

Three ways to make one:

``random_walk``
    Seeded. Gaussian steps of the index, optional gaps (a jump of several
    points in one frame), optional stale stretches (the feed stops: quotes
    hold and their ``as_of`` ages), a configurable spread. The options move
    with the index through their own delta — Black-Scholes at one IV with
    the clock running down to the 15:00 CT close — so a call's bid falls as
    SPX falls by about delta per point, and gamma is there too.
``scripted``
    A hand-written path: ``[(t, spx), ...]``, each level held until the
    next. Frames may pin exact option quotes (``Frame.quotes``) — the
    hand-recorded 2026-09-30 incidents are written this way, from the
    numbers in the journal and Steve's screenshots.
``recorded``
    ``fixtures/recorded_2026-09-30.json``: the real index path, 13:15–13:45
    CT on 2026-09-30, from the Databento ES tape less one Schwab-measured
    basis, with the options priced from that day's 18:00 UTC Schwab chain
    (its own IV per strike, its own spreads). See
    ``fixtures/build_recorded.py`` for provenance.

Nothing here reads the wall clock, the network or anything under
``/var/lib/execd``.
"""

from __future__ import annotations

import bisect
import json
import math
import random
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from execd.stops import tick_for

CT = ZoneInfo("America/Chicago")
FIXTURES = Path(__file__).with_name("fixtures")

#: Wednesday 2026-08-26 10:00 CT — the conftest's mid-session moment.
GENERATED_START = datetime(2026, 8, 26, 10, 0, tzinfo=CT).astimezone(timezone.utc)
GENERATED_SPX = 6380.0
#: SPX's own quote: the index has a bid and an ask a little either side of
#: its last; the service marks on ``last``.
INDEX_HALF_SPREAD = 0.25


def occ(expiry: date, right: str, strike: float, root: str = "SPXW") -> str:
    """The 21-character OCC symbol the service and the paper book use."""
    r = right.upper()[0]
    return f"{root:<6}{expiry:%y%m%d}{r}{int(round(strike * 1000)):08d}"


def _floor_tick(px: float) -> float:
    t = tick_for(px)
    return round(math.floor(round(px / t, 6)) * t, 2)


def _ceil_tick(px: float) -> float:
    t = tick_for(px)
    return round(math.ceil(round(px / t, 6)) * t, 2)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class Frame:
    """The market from ``t`` seconds after the tape's start until the next
    frame. ``stale`` freezes every quote at the last fresh frame (and their
    ``as_of`` with it); ``spread`` widens or narrows the option spread for
    this frame; ``quotes`` pins exact option quotes, ``{symbol: (bid, ask)}``,
    over the model, and ``deltas`` their chain deltas. ``chain_spx`` is the
    index level the chain body reports beside its maps when it differs from
    the ``$SPX`` quote — the page prices a ticket from the first and the
    service sends on the second (the 13:38 CT ticket: 7693.71 vs 7693.68)."""

    t: float
    spx: float
    stale: bool = False
    spread: float | None = None
    quotes: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    deltas: Mapping[str, float] = field(default_factory=dict)
    chain_spx: float | None = None


@dataclass
class OptionModel:
    """Index level → option quote. Black-Scholes on the 0DTE clock, no rate.

    ``iv`` is one number, or a function of ``(right, strike)`` for a chain
    recorded with its own smile. ``spread`` is the full bid-ask width in
    points: a number, or a function of ``(right, strike, mid)``. The bid is
    floored and the ask ceilinged onto the exchange grid in force at each
    (0.05 under $3, 0.10 at and above), so the paper book fills on prices
    the exchange could print."""

    expiry: date
    iv: float | Callable[[str, float], float] = 0.15
    spread: float | Callable[[str, float, float], float] = 0.10
    close_ct: time = time(15, 0)

    def years_left(self, at: datetime) -> float:
        close = datetime.combine(self.expiry, self.close_ct, tzinfo=CT)
        secs = (close - at).total_seconds()
        return max(secs, 60.0) / (365.0 * 86400.0)

    def _iv(self, right: str, strike: float) -> float:
        return self.iv(right, strike) if callable(self.iv) else float(self.iv)

    def theo(self, right: str, strike: float, spx: float, at: datetime) -> tuple[float, float]:
        """``(mid, delta)`` — delta signed, negative for a put."""
        sigma = self._iv(right, strike)
        T = self.years_left(at)
        sd = sigma * math.sqrt(T)
        d1 = (math.log(spx / strike) + 0.5 * sd * sd) / sd
        d2 = d1 - sd
        if right.upper().startswith("C"):
            return spx * _ncdf(d1) - strike * _ncdf(d2), _ncdf(d1)
        return strike * _ncdf(-d2) - spx * _ncdf(-d1), _ncdf(d1) - 1.0

    def quote(self, right: str, strike: float, spx: float, at: datetime,
              spread: float | None = None) -> tuple[float, float, float]:
        """``(bid, ask, delta)`` on the grid. A bid that would be under one
        tick is 0 — a one-sided quote, as far out-of-the-money strikes are."""
        mid, delta = self.theo(right, strike, spx, at)
        if spread is not None:
            width = spread
        elif callable(self.spread):
            width = self.spread(right, strike, mid)
        else:
            width = float(self.spread)
        # the bid to the nearest tick under the half-width, the ask the
        # width above it rounded up to the grid: a 0.10 width quotes 0.10
        # wide wherever the mid sits, as the recorded chain does
        low = max(mid - width / 2.0, 0.0)
        bid = _floor_tick(low + tick_for(low) / 2.0)
        if bid < 0.05:
            bid = 0.0
        ask = max(_ceil_tick(max(bid + width, 0.05)), round(bid + tick_for(bid), 2))
        return bid, round(ask, 2), delta


@dataclass
class Tape:
    """An index path and the option model on it, from ``start`` (UTC)."""

    name: str
    start: datetime
    frames: list[Frame]
    model: OptionModel
    #: strikes the chain lists (both rights), every 5 points
    strikes: tuple[float, ...] = ()
    #: the recorded deltas, for a recorded tape; the model's otherwise
    note: str = ""

    def __post_init__(self) -> None:
        self.frames.sort(key=lambda f: f.t)
        if not self.frames or self.frames[0].t != 0:
            raise ValueError(f"tape {self.name}: the first frame must be at t=0")
        self._ts = [f.t for f in self.frames]
        if not self.strikes:
            lo = 5 * round(min(f.spx for f in self.frames) / 5) - 120
            hi = 5 * round(max(f.spx for f in self.frames) / 5) + 120
            self.strikes = tuple(float(k) for k in range(int(lo), int(hi) + 5, 5))

    @property
    def expiry(self) -> date:
        return self.model.expiry

    @property
    def length_s(self) -> float:
        return self.frames[-1].t

    def frame_index(self, at: datetime) -> int:
        t = (at - self.start).total_seconds()
        return max(0, bisect.bisect_right(self._ts, t) - 1)

    def frame(self, at: datetime) -> Frame:
        return self.frames[self.frame_index(at)]

    def fresh(self, at: datetime) -> tuple[Frame, datetime]:
        """The frame whose quotes are on the screen at ``at`` and when they
        were struck: the last frame that is not stale, at or before ``at``."""
        i = self.frame_index(at)
        while i > 0 and self.frames[i].stale:
            i -= 1
        f = self.frames[i]
        return f, self.start + timedelta(seconds=f.t)

    def symbol(self, right: str, strike: float) -> str:
        return occ(self.expiry, right, strike)

    def spx_at(self, at: datetime) -> float:
        return self.fresh(at)[0].spx

    def path(self) -> list[tuple[float, float]]:
        return [(f.t, f.spx) for f in self.frames]

    def shifted(self, **kw) -> "Tape":
        return replace(self, **kw)


# ── generators ───────────────────────────────────────────────────────────

def random_walk(seed: int, *, steps: int = 200, dt_s: float = 3.0,
                start: datetime = GENERATED_START, spx0: float = GENERATED_SPX,
                sigma_pts: float = 0.9, drift_pts: float = 0.0,
                gap_prob: float = 0.0, gap_pts: float = 6.0,
                stale_prob: float = 0.0, stale_len: int = 4,
                spread: float = 0.10, wide_prob: float = 0.0, wide_spread: float = 1.20,
                iv: float = 0.15, name: str | None = None) -> Tape:
    """A seeded random walk of the index, ``steps`` frames ``dt_s`` apart.

    ``sigma_pts`` is the standard deviation of one step in index points
    (0.9 every 3 s is an ordinary midday tape); ``gap_prob`` the chance a
    step is a gap of ``±gap_pts`` instead; ``stale_prob`` the chance a stale
    stretch of ``stale_len`` frames begins; ``wide_prob`` the chance a frame's
    option spread is ``wide_spread`` (wider than a $20 stop) instead of
    ``spread``. Same seed, same tape."""
    rng = random.Random(seed)
    frames: list[Frame] = []
    spx = spx0
    stale_left = 0
    for i in range(steps):
        if i:
            if gap_prob and rng.random() < gap_prob:
                spx += gap_pts if rng.random() < 0.5 else -gap_pts
            else:
                spx += rng.gauss(drift_pts, sigma_pts)
        stale = False
        if stale_left:
            stale_left -= 1
            stale = True
        elif i and stale_prob and rng.random() < stale_prob:
            stale_left = stale_len - 1
            stale = True
        width = wide_spread if (wide_prob and rng.random() < wide_prob) else None
        frames.append(Frame(t=i * dt_s, spx=round(spx, 2), stale=stale, spread=width))
    model = OptionModel(expiry=start.astimezone(CT).date(), iv=iv, spread=spread)
    return Tape(name=name or f"walk-{seed}", start=start, frames=frames, model=model,
                note=f"random_walk(seed={seed}, steps={steps}, dt={dt_s}, sigma={sigma_pts}, "
                     f"drift={drift_pts}, gap={gap_prob}/{gap_pts}, stale={stale_prob}/"
                     f"{stale_len}, spread={spread}, wide={wide_prob}/{wide_spread})")


def scripted(points: Sequence[tuple[float, float]] | Iterable[Frame], *,
             start: datetime = GENERATED_START, iv: float = 0.15, spread: float = 0.10,
             name: str = "scripted", model: OptionModel | None = None,
             strikes: tuple[float, ...] = ()) -> Tape:
    """A hand-written path: ``(t, spx)`` pairs or :class:`Frame` s, each held
    until the next."""
    frames = [p if isinstance(p, Frame) else Frame(t=float(p[0]), spx=float(p[1]))
              for p in points]
    model = model or OptionModel(expiry=start.astimezone(CT).date(), iv=iv, spread=spread)
    return Tape(name=name, start=start, frames=frames, model=model, strikes=strikes)


def ramp(*knots: tuple[float, float], every: float = 1.0, **kw) -> Tape:
    """A piecewise-linear index path through ``(t, spx)`` knots, one frame
    every ``every`` seconds — "SPX drifts 8 points down over two minutes,
    then rallies 20" in one line. Keywords go to :func:`scripted`."""
    pts: list[tuple[float, float]] = []
    for (t0, s0), (t1, s1) in zip(knots, knots[1:]):
        n = max(1, int(round((t1 - t0) / every)))
        for i in range(n):
            pts.append((t0 + i * (t1 - t0) / n, round(s0 + i * (s1 - s0) / n, 2)))
    pts.append((float(knots[-1][0]), float(knots[-1][1])))
    return scripted(pts, **kw)


def recorded(*, from_s: float = 0.0, to_s: float | None = None, every_s: float = 1.0,
             path: Path | None = None) -> Tape:
    """The 2026-09-30 13:15–13:45 CT tape (``fixtures/recorded_2026-09-30.json``),
    from ``from_s`` seconds into it. The options are priced from the
    recorded chain's IV per strike; each strike keeps its recorded spread."""
    data = json.loads((path or FIXTURES / "recorded_2026-09-30.json").read_text())
    base = datetime.fromisoformat(data["start_utc"])
    spx = data["spx"]
    step = float(data.get("step_s", 1))
    end = len(spx) * step if to_s is None else min(to_s, len(spx) * step)
    frames: list[Frame] = []
    t = from_s
    while t < end:
        frames.append(Frame(t=t - from_s, spx=float(spx[int(t // step)])))
        t += every_s
    ivs = {(r["side"][0], float(r["strike"])): float(r["iv"]) / 100.0 for r in data["chain"]}
    widths = {(r["side"][0], float(r["strike"])): round(float(r["ask"]) - float(r["bid"]), 2)
              for r in data["chain"]}
    strikes = tuple(sorted({float(r["strike"]) for r in data["chain"]}))
    nearest = lambda k: min(strikes, key=lambda s: abs(s - k))  # noqa: E731

    def iv(right: str, strike: float) -> float:
        return ivs.get((right[0].upper(), nearest(strike)), 0.15)

    def width(right: str, strike: float, mid: float) -> float:
        return widths.get((right[0].upper(), nearest(strike)), 0.10)

    start = base + timedelta(seconds=from_s)
    model = OptionModel(expiry=date.fromisoformat(data["day"]), iv=iv, spread=width)
    return Tape(name=f"recorded-{data['day']}+{from_s:g}s", start=start, frames=frames,
                model=model, strikes=strikes,
                note=f"recorded {data['day']} from {start.astimezone(CT):%H:%M:%S} CT; "
                     + "; ".join(f"{k}: {v}" for k, v in data["source"].items()))
