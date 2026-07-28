"""Fundamental-units extractor — atoms, grading, zigzag legs. [st-kaf]"""
from datetime import datetime, timedelta

from market.entities.trade import Trade
from market.orderflow.moves import (grade_atoms, one_minute_atoms,
                                    segment_moves)

T0 = datetime(2026, 7, 22, 8, 30)


def _t(sec: float, price: float, size: int, side: str = "N") -> Trade:
    return Trade(ts=T0 + timedelta(seconds=sec), symbol="ES", instrument_id=1,
                 price=price, size=size, side=side, sequence=None)


def test_atoms_aggregate_by_clock_minute_and_fill_travel():
    trades = [_t(0, 100.0, 5, "B"), _t(30, 104.0, 5, "A"), _t(59, 100.0, 5),
              _t(60, 101.0, 10, "B")]
    atoms = one_minute_atoms(trades)
    assert len(atoms) == 2
    a = atoms[0]
    assert (a.open, a.high, a.low, a.close) == (100.0, 104.0, 100.0, 100.0)
    assert a.volume == 15 and a.delta == 0          # +5 B, -5 A, 5 N
    assert a.net == 0.0 and a.range_pts == 4.0
    assert a.travel_ratio == 0.0                     # full round trip


def test_grades_are_day_relative_percentiles_with_cells():
    trades = []
    for m in range(4):                               # 4 minutes, rising effort
        px = 100.0 + m
        trades += [_t(m * 60, px, 10 * (m + 1), "B"),
                   _t(m * 60 + 30, px + (m * 0.5), 10 * (m + 1), "B")]
    atoms = grade_atoms(one_minute_atoms(trades))
    assert atoms[-1].effort_pct == 100.0
    assert atoms[0].cell in ("F1", "F2", "F3", "F4")
    assert 0.0 <= atoms[0].cell_grade <= 1.0


def test_zigzag_splits_on_reversal_and_covers_every_atom():
    trades = []
    for m in range(10):                              # up 5 minutes, down 5
        px = 100.0 + (m if m < 5 else 8 - m)
        trades.append(_t(m * 60, px, 100, "B"))
        trades.append(_t(m * 60 + 30, px + 0.25, 100, "A"))
    atoms = grade_atoms(one_minute_atoms(trades))
    moves = segment_moves(atoms)
    assert len(moves) >= 2
    assert moves[0].direction == 1 and moves[1].direction == -1
    assert sum(m.minutes for m in moves) >= len(atoms)  # overlap at pivots ok
    assert all(len(m.atoms) == m.minutes for m in moves)
