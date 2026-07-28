"""Fundamental units of orderflow — 1-minute effort/effect atoms and graded
moves. [st-kaf]

The atom is the 1-minute bar, identified by the effort-vs-effect matrix
(docs/foundation/02-volume.md): effort = volume traded, effect = net price
movement. The four cells carry the drill-frame names already ratified in
docs/drills/scenario-catalog.md:

    F1 conviction  — effort AND effect (the move is paid for)
    F2 absorption  — effort, no effect (someone is standing there)
    F3 hollow      — effect, no effort (price drifting on air)
    F4 dead        — neither

Grades, not gates: every atom carries day-relative percentile grades
(effort_pct, effect_pct in 0-100) and its cell is reported WITH the distance
from the 50/50 boundary (cell_grade) — an atom at the median is a coin flip
and says so. Hindsight is deliberate: percentiles are computed against the
full day (Steve ruling 2026-07-28, full advantage of hindsight).

A MOVE is a maximal directional leg: zigzag over 1-minute closes with a
reversal threshold of REVERSAL_FRAC of the day's full range (floored at
REVERSAL_MIN_PTS). Each move records its atom sequence, summed effort,
net/max effect, signed delta (force — recorded, not part of the matrix),
and grades. Moves are the units the taxonomy names; atoms are what they
are made of.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from market.orderflow.replay import Trade

REVERSAL_FRAC = 0.20      # of the day's final high-low range
REVERSAL_MIN_PTS = 1.5

CELLS = {(True, True): "F1", (True, False): "F2",
         (False, True): "F3", (False, False): "F4"}
CELL_NAMES = {"F1": "conviction", "F2": "absorption",
              "F3": "hollow", "F4": "dead"}


@dataclass
class Atom:
    """One 1-minute bar, graded."""
    ts: datetime                # minute start
    open: float
    high: float
    low: float
    close: float
    volume: int                 # effort, raw
    delta: int                  # force (signed), recorded not matrixed
    net: float = 0.0            # effect as displacement, signed (close - open)
    range_pts: float = 0.0      # effect as travel (high - low)
    travel_ratio: float = 1.0   # |net| / range — 1 = one-way, ~0 = round trip
    effort_pct: float = 0.0     # day-relative percentile, 0-100
    effect_pct: float = 0.0     # percentile of |net| (displacement)
    cell: str = "F4"
    cell_grade: float = 0.0     # 0 at the 50/50 boundary, 1 at the corner


@dataclass
class Move:
    """A maximal directional leg of the zigzag."""
    start_ts: datetime
    end_ts: datetime
    direction: int              # +1 up, -1 down
    start_price: float
    end_price: float
    net_pts: float              # signed
    extreme_pts: float          # max favorable excursion of the leg
    minutes: int
    effort: int                 # summed volume
    force: int                  # summed delta
    atoms: list[str] = field(default_factory=list)   # cell sequence
    effort_pct: float = 0.0     # leg effort vs all legs of the day
    effect_pct: float = 0.0     # |net| vs all legs of the day
    cell: str = "F4"            # leg-level matrix identity
    cell_grade: float = 0.0


def one_minute_atoms(trades: list[Trade]) -> list[Atom]:
    """Aggregate the tape into 1-minute atoms (clock minutes, CT tape time)."""
    atoms: list[Atom] = []
    cur: Atom | None = None
    for t in trades:
        m = t.ts.replace(second=0, microsecond=0)
        if cur is None or m != cur.ts:
            if cur is not None:
                _finish_atom(cur)
                atoms.append(cur)
            cur = Atom(ts=m, open=t.price, high=t.price, low=t.price,
                       close=t.price, volume=0, delta=0)
        cur.high = max(cur.high, t.price)
        cur.low = min(cur.low, t.price)
        cur.close = t.price
        cur.volume += t.size
        if t.side == "B":       # buy-aggressor lifted the offer (bars.py convention)
            cur.delta += t.size
        elif t.side == "A":     # sell-aggressor hit the bid
            cur.delta -= t.size
    if cur is not None:
        _finish_atom(cur)
        atoms.append(cur)
    return atoms


def _finish_atom(a: Atom) -> None:
    a.net = round(a.close - a.open, 2)
    a.range_pts = round(a.high - a.low, 2)
    a.travel_ratio = round(abs(a.net) / a.range_pts, 3) if a.range_pts > 0 else 1.0


def _pctl_rank(sorted_vals: list[float], v: float) -> float:
    """Percentile rank of v within sorted_vals, 0-100."""
    if not sorted_vals:
        return 0.0
    i = bisect.bisect_right(sorted_vals, v)
    return round(100.0 * i / len(sorted_vals), 1)


def _grade(effort_pct: float, effect_pct: float) -> tuple[str, float]:
    """Cell + distance-from-boundary grade. Grades, not gates: the grade is
    min(distance from 50) scaled to 0-1 — 0 at the boundary, 1 at a corner."""
    cell = CELLS[(effort_pct >= 50.0, effect_pct >= 50.0)]
    grade = round(min(abs(effort_pct - 50.0), abs(effect_pct - 50.0)) / 50.0, 3)
    return cell, grade


def grade_atoms(atoms: list[Atom]) -> list[Atom]:
    """Day-relative percentile grades + matrix cell per atom (in place)."""
    efforts = sorted(a.volume for a in atoms)
    effects = sorted(abs(a.net) for a in atoms)
    for a in atoms:
        a.effort_pct = _pctl_rank(efforts, a.volume)
        a.effect_pct = _pctl_rank(effects, abs(a.net))
        a.cell, a.cell_grade = _grade(a.effort_pct, a.effect_pct)
    return atoms


def segment_moves(atoms: list[Atom]) -> list[Move]:
    """Zigzag over minute closes: a move ends when price retraces
    REVERSAL_FRAC of the day range (floor REVERSAL_MIN_PTS) from its
    extreme. Every atom belongs to exactly one move."""
    if not atoms:
        return []
    day_hi = max(a.high for a in atoms)
    day_lo = min(a.low for a in atoms)
    rev = max(REVERSAL_MIN_PTS, round(REVERSAL_FRAC * (day_hi - day_lo), 2))

    moves: list[Move] = []
    start = 0
    direction = 0
    ext_i = 0                                    # index of the leg extreme
    for i in range(1, len(atoms)):
        c = atoms[i].close
        if direction == 0:
            if abs(c - atoms[0].close) >= rev:
                direction = 1 if c > atoms[0].close else -1
                ext_i = i
            continue
        ext = atoms[ext_i].close
        if (c - ext) * direction > 0:
            ext_i = i
            continue
        if (ext - c) * direction >= rev:         # reversal: close the leg
            moves.append(_build_move(atoms, start, ext_i, direction))
            start = ext_i
            direction = -direction
            ext_i = i
    moves.append(_build_move(atoms, start, len(atoms) - 1,
                             direction if direction else
                             (1 if atoms[-1].close >= atoms[0].close else -1)))

    lefforts = sorted(m.effort for m in moves)
    leffects = sorted(abs(m.net_pts) for m in moves)
    for m in moves:
        m.effort_pct = _pctl_rank(lefforts, m.effort)
        m.effect_pct = _pctl_rank(leffects, abs(m.net_pts))
        m.cell, m.cell_grade = _grade(m.effort_pct, m.effect_pct)
    return moves


def _build_move(atoms: list[Atom], i0: int, i1: int, direction: int) -> Move:
    seg = atoms[i0:i1 + 1]
    p0, p1 = seg[0].open, seg[-1].close
    extreme = (max(a.high for a in seg) - p0) if direction > 0 \
        else (p0 - min(a.low for a in seg))
    return Move(
        start_ts=seg[0].ts, end_ts=seg[-1].ts + timedelta(minutes=1),
        direction=direction if direction else (1 if p1 >= p0 else -1),
        start_price=p0, end_price=p1, net_pts=round(p1 - p0, 2),
        extreme_pts=round(extreme, 2), minutes=len(seg),
        effort=sum(a.volume for a in seg), force=sum(a.delta for a in seg),
        atoms=[a.cell for a in seg])
