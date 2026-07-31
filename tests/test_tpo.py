"""TPO construction + reads — hand-computed fixtures. [st-3zh]"""
from __future__ import annotations

from datetime import datetime

import pytest

from market.entities.trade import Trade
from market.orderflow.tpo import (
    build_tpo,
    classify_day_type,
    developing_upto,
    initial_balance,
    poc_row,
    single_print_rows,
    value_area,
)


def mk(h: int, m: int, price: float, size: int = 1) -> Trade:
    return Trade(ts=datetime(2026, 7, 2, h, m), symbol="ES.c.0",
                 instrument_id=1, price=price, size=size)


def from_rows(bracket_rows: list[list[int]], base: float = 7400.0) -> "TPOProfile":
    """Build a profile where bracket k touches exactly the given row offsets
    (1.0-pt rows). Bracket k = the k-th half hour from 08:30."""
    trades = []
    for k, rows in enumerate(bracket_rows):
        h, m = divmod(8 * 60 + 30 + k * 30, 60)
        for r in rows:
            trades.append(mk(h, m + 1, base + r))
    return build_tpo(trades)


# ── construction ─────────────────────────────────────────────────────────────

def test_brackets_letters_rows_and_range():
    p = from_rows([[0, 1, 2], [1, 3]])
    assert [b.letter for b in p.brackets] == ["A", "B"]
    assert p.prices == (7400.0, 7401.0, 7402.0, 7403.0)   # contiguous
    assert p.brackets[0].row_indices == (0, 1, 2)
    assert p.brackets[1].row_indices == (1, 3)
    assert p.counts() == (1, 2, 1, 1)
    assert p.row_pts == 1.0


def test_rth_filter_and_empty_session():
    pre = mk(7, 59, 7400.0)                                # pre-open: ignored
    p = build_tpo([pre, mk(8, 31, 7400.0)])
    assert p.counts() == (1,)
    with pytest.raises(ValueError):
        build_tpo([pre])


def test_intrabracket_prices_collapse_to_one_tpo():
    # many trades in one bracket at one row = one TPO, not many
    trades = [mk(8, 31, 7400.0), mk(8, 40, 7400.25), mk(8, 55, 7400.75)]
    p = build_tpo(trades)
    assert p.counts() == (1,)


# ── reads ────────────────────────────────────────────────────────────────────

def test_poc_unique_max():
    p = from_rows([[2], [1, 2, 3], [1, 2, 3], [0, 2, 4]])  # counts 1,2,4,2,1
    assert poc_row(p) == 2


def test_poc_tie_breaks_toward_mid_then_lower():
    p = from_rows([[0, 1, 2, 3], [0, 3]])                  # counts 2,1,1,2
    assert poc_row(p) == 0                                  # equidistant → lower


def test_value_area_70pct_two_row_expansion():
    p = from_rows([[2], [1, 2, 3], [1, 2, 3], [0, 2, 4]])  # counts 1,2,4,2,1
    # total 10, target 7: POC row2 (4), pairs tie 3v3 → upper wins → rows 2..4
    assert value_area(p) == (2, 4)


def test_initial_balance():
    p = from_rows([[0, 1, 2], [1, 3]])
    assert initial_balance(p) == (7400.0, 7403.0)
    assert initial_balance(from_rows([[0, 1]])) is None     # no B yet


def test_single_prints_interior_only():
    # counts 1,1,3,1,2,1,1 — edge runs are tails, row 3 is the single print
    p = from_rows([[0, 1, 2], [2, 3, 4], [2, 4, 5, 6]])
    assert p.counts() == (1, 1, 3, 1, 2, 1, 1)
    assert single_print_rows(p) == [3]


def test_developing_reads_via_upto():
    p = from_rows([[0, 1, 2], [2, 3, 4], [2, 4, 5, 6]])
    assert p.counts(1) == (1, 1, 1, 0, 0, 0, 0)
    assert poc_row(p, 2) == 2                               # after B: rows0-4, count2 at row2
    assert single_print_rows(p, 2) == []                    # all runs touch an edge


# ── day type ─────────────────────────────────────────────────────────────────

def test_day_type_trend():
    p = from_rows([[0, 1, 2], [1, 2, 3], [3, 4, 5], [5, 6, 7],
                   [7, 8, 9], [9, 10, 11]])
    label, why = classify_day_type(p)
    assert label == "trend"
    assert "IB" in why


def test_day_type_p_shape():
    p = from_rows([[0, 1, 2, 3, 4, 5], [6, 7, 8], [6, 7, 8], [6, 7, 8], [6, 7, 8]])
    assert classify_day_type(p)[0] == "P"


def test_day_type_b_shape():
    p = from_rows([[3, 4, 5, 6, 7, 8], [0, 1, 2], [0, 1, 2], [0, 1, 2], [0, 1, 2]])
    assert classify_day_type(p)[0] == "b"


def test_day_type_d_shape():
    p = from_rows([[1, 2, 3], [0, 2, 4], [1, 2, 3], [1, 3, 4], [0, 1, 2]])
    assert classify_day_type(p)[0] == "D"


# ── developing day type (non-lookahead, st-98z) ──────────────────────────────

def test_developing_day_type_progressive_b():
    # Push up + acceptance on top (P-ish early), then sell-off and acceptance
    # below: the developing call moves unknown → P → b as brackets complete.
    p = from_rows([[0, 1, 2, 3, 4, 5], [4, 5],
                   [0, 1], [0, 1], [0, 1], [0, 1]])
    assert classify_day_type(p, upto=0) == ("unknown", "IB incomplete")
    assert classify_day_type(p, upto=1) == ("unknown", "IB incomplete")
    assert classify_day_type(p, upto=2)[0] == "P"     # POC pinned high so far
    assert classify_day_type(p, upto=3)[0] == "b"     # sell-off flips the read
    assert classify_day_type(p, upto=6)[0] == "b"
    assert classify_day_type(p)[0] == "b"             # full-session agrees


def test_developing_upto_none_equivalence():
    # upto=len(brackets) must reproduce the full-session call exactly.
    for rows in (
        [[0, 1, 2], [1, 2, 3], [3, 4, 5], [5, 6, 7], [7, 8, 9], [9, 10, 11]],
        [[0, 1, 2, 3, 4, 5], [6, 7, 8], [6, 7, 8], [6, 7, 8], [6, 7, 8]],
        [[3, 4, 5, 6, 7, 8], [0, 1, 2], [0, 1, 2], [0, 1, 2], [0, 1, 2]],
        [[1, 2, 3], [0, 2, 4], [1, 2, 3], [1, 3, 4], [0, 1, 2]],
    ):
        p = from_rows(rows)
        assert classify_day_type(p, upto=len(p.brackets)) == classify_day_type(p)


def test_developing_initial_balance_upto():
    p = from_rows([[0, 1, 2], [1, 3], [2, 4]])
    assert initial_balance(p, upto=1) is None          # B not complete yet
    assert initial_balance(p, upto=2) == initial_balance(p) == (7400.0, 7403.0)


def test_developing_upto_excludes_bracket_in_progress():
    p = from_rows([[0, 1], [1, 2], [2, 3]])            # A, B, C from 08:30
    assert developing_upto(p, datetime(2026, 7, 2, 8, 45)) == 0   # inside A
    assert developing_upto(p, datetime(2026, 7, 2, 9, 31)) == 2   # inside C
    assert developing_upto(p, datetime(2026, 7, 2, 15, 10)) == 3  # all done


def test_developing_upto_late_start_tape_maps_by_letter():
    # Tape starts 13:00 (letters J, K): at 13:40 only J has completed —
    # positional upto is 1, not the wall-clock bracket number 10.
    p = build_tpo([mk(13, 5, 7400.0), mk(13, 35, 7401.0)])
    assert [b.letter for b in p.brackets] == ["J", "K"]
    assert developing_upto(p, datetime(2026, 7, 2, 13, 40)) == 1
    assert classify_day_type(p, upto=1) == ("unknown", "IB incomplete")
