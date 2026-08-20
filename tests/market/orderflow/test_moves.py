"""Fundamental-units extractor — atoms, grading, zigzag legs. [st-kaf]"""
from datetime import datetime, timedelta

from market.entities.trade import Trade
from market.orderflow.moves import (grade_atoms, grade_atoms_developing,
                                    one_minute_atoms, segment_moves)

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


def test_developing_grade_is_causal_not_day_relative():
    """The whole point of grade_atoms_developing: atom i's grade must not
    move when atoms are appended after it — a live session and this offline
    call over a truncated prefix must see the identical number at atom i."""
    trades = []
    for m in range(8):                               # rising then falling effort
        px = 100.0 + m
        vol = 10 * (m + 1) if m < 4 else 10 * (8 - m)
        trades += [_t(m * 60, px, vol, "B"), _t(m * 60 + 30, px + 0.5, vol, "B")]
    atoms = one_minute_atoms(trades)

    full = grade_atoms_developing(atoms)
    prefix = grade_atoms_developing(atoms[:5])
    assert prefix == full[:5]                        # unchanged by the future
    assert full[0]["n_atoms"] == 1
    assert full[-1]["n_atoms"] == len(atoms)
    for row in full:
        assert row["cell_dev"] in ("F1", "F2", "F3", "F4")
        assert 0.0 <= row["cell_grade_dev"] <= 1.0

    # The hindsight grade is free to differ atom-by-atom from the developing
    # one — that divergence is the entire reason the two are separate fields.
    hindsight = grade_atoms(list(atoms))
    assert not all(h.effort_pct == d["effort_pct_dev"] for h, d in zip(hindsight, full))


def test_developing_grade_is_damped_by_sample_size():
    """COO, 2026-08-20: _pctl_rank ranks a lone value at its own 100th
    percentile, so atom 1 is unconditionally F1 at raw grade 1.0 — maximum
    confidence with zero information. cell_grade_dev must not report that
    raw value; it has to start near zero and grow with n."""
    trades = []
    for m in range(6):
        px = 100.0 + m * 3          # deliberately extreme: max effort AND effect
        trades += [_t(m * 60, px, 100, "B"), _t(m * 60 + 30, px + 2.0, 100, "B")]
    atoms = one_minute_atoms(trades)
    dev = grade_atoms_developing(atoms)

    assert dev[0]["n_atoms"] == 1
    assert dev[0]["cell_dev"] == "F1"          # still the right cell...
    assert dev[0]["cell_grade_dev"] < 0.1      # ...but not reported as certain
    # confidence rises monotonically as n grows (grade held ~constant by
    # construction — every atom here is the new extreme)
    grades = [row["cell_grade_dev"] for row in dev]
    assert grades == sorted(grades)
    assert grades[-1] > grades[0]


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
