"""Anchored (multi-session) TPO math + the page's marks. [st-jz12]

The single-session builder has its own hand-computed fixtures in
``tests/test_tpo.py``; this file covers only what the anchor adds — bracket
indexing from a named moment, letters that restart per session segment, the
prior/overnight/today split, Initial Balance read per cash session, and the
rendered page carrying every mark it claims.

The synthetic tape is one print per bracket at a chosen row, so every count in
here is countable by hand.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market.entities.trade import Trade
from market.orderflow.tpo import (
    GLOBEX_ALPHABET,
    ROLE_OVERNIGHT,
    ROLE_PRIOR_RTH,
    ROLE_TODAY_RTH,
    SEG_GLOBEX,
    SEG_RTH,
    AnchoredTPOAccumulator,
    bracket_index,
    bracket_start,
    build_anchored_tpo,
    counts_by_role,
    plan_segments,
    poc_row,
    segment_initial_balance,
    segment_kind,
    single_print_rows,
    value_area,
)

CT = ZoneInfo("America/Chicago")
WED = datetime(2026, 9, 9, 8, 30, tzinfo=CT)          # anchor: prior RTH open
THU_NOON = datetime(2026, 9, 10, 12, 0, tzinfo=CT)


def tr(ts: datetime, price: float, size: int = 1) -> Trade:
    return Trade(ts=ts, symbol="ES.c.0", instrument_id=1, price=price, size=size)


def tape(rows_by_bracket: dict[int, list[float]], anchor: datetime = WED,
         base: float = 7600.0, bracket_min: int = 30) -> list[Trade]:
    """One print per (bracket index, row offset). Offsets are 1.0-pt rows."""
    out = []
    for idx in sorted(rows_by_bracket):
        start = bracket_start(anchor, idx, bracket_min)
        for j, r in enumerate(rows_by_bracket[idx]):
            out.append(tr(start + timedelta(minutes=1 + j), base + r))
    return out


# ── bracket indexing ─────────────────────────────────────────────────────────

def test_bracket_index_counts_from_the_anchor():
    assert bracket_index(WED, WED) == 0
    assert bracket_index(WED + timedelta(minutes=29, seconds=59), WED) == 0
    assert bracket_index(WED + timedelta(minutes=30), WED) == 1
    assert bracket_index(WED + timedelta(days=1), WED) == 48       # 24 h later
    assert bracket_index(WED + timedelta(minutes=45), WED, 15) == 3


def test_bracket_start_is_the_inverse():
    for idx in (0, 1, 13, 48, 60):
        assert bracket_index(bracket_start(WED, idx), WED) == idx


def test_segment_kind_splits_cash_from_globex():
    assert segment_kind(WED) == SEG_RTH                             # 08:30 Wed
    assert segment_kind(WED.replace(hour=14, minute=30)) == SEG_RTH
    assert segment_kind(WED.replace(hour=15, minute=0)) == SEG_GLOBEX   # bell
    assert segment_kind(WED.replace(hour=3, minute=0)) == SEG_GLOBEX
    sat = datetime(2026, 9, 12, 10, 0, tzinfo=CT)                   # Saturday
    assert segment_kind(sat) == SEG_GLOBEX


# ── segment plan ─────────────────────────────────────────────────────────────

def test_plan_is_prior_rth_then_overnight_then_today():
    plan = plan_segments(WED, THU_NOON)
    kinds = [(k, role) for k, role, _d, _a, _b in plan]
    assert kinds == [(SEG_RTH, ROLE_PRIOR_RTH),
                     (SEG_GLOBEX, ROLE_OVERNIGHT),
                     (SEG_RTH, ROLE_TODAY_RTH)]
    # 08:30–15:00 is 13 half hours; the overnight runs to the next 08:30.
    assert plan[0][3:] == (0, 12)
    assert plan[1][3:] == (13, 47)
    assert plan[2][3] == 48


def test_overnight_stays_one_segment_across_midnight():
    plan = plan_segments(WED, THU_NOON)
    overnight = [p for p in plan if p[0] == SEG_GLOBEX]
    assert len(overnight) == 1          # not one run per calendar date


def test_weekend_window_still_yields_three_roles():
    fri = datetime(2026, 9, 11, 8, 30, tzinfo=CT)
    mon = datetime(2026, 9, 14, 10, 0, tzinfo=CT)
    plan = plan_segments(fri, mon)
    roles = [r for _k, r, _d, _a, _b in plan]
    assert roles == [ROLE_PRIOR_RTH, ROLE_OVERNIGHT, ROLE_TODAY_RTH]


def test_plan_rejects_an_end_before_the_anchor():
    with pytest.raises(ValueError):
        plan_segments(WED, WED - timedelta(hours=1))


# ── construction ─────────────────────────────────────────────────────────────

def test_letters_restart_at_each_session_boundary():
    a = build_anchored_tpo(tape({0: [0], 1: [1], 13: [2], 14: [3],
                                 48: [1], 49: [0]}), WED)
    got = [(b.letter, b.segment, b.index) for b in a.profile.brackets]
    assert got == [("A", SEG_RTH, 0), ("B", SEG_RTH, 1),
                   ("a", SEG_GLOBEX, 13), ("b", SEG_GLOBEX, 14),
                   ("A", SEG_RTH, 48), ("B", SEG_RTH, 49)]
    assert [s.role for s in a.segments] == [ROLE_PRIOR_RTH, ROLE_OVERNIGHT,
                                            ROLE_TODAY_RTH]
    assert [s.label for s in a.segments] == ["A–B", "a–b", "A–B"]


def test_letters_name_the_half_hour_not_the_printed_order():
    # Bracket 1 never printed (a halt): C still labels bracket 2.
    a = build_anchored_tpo(tape({0: [0], 2: [1]}), WED)
    assert [b.letter for b in a.profile.brackets] == ["A", "C"]


def test_a_weeknight_never_repeats_an_overnight_letter():
    # 15:00 CT → 08:30 CT is 35 half hours and the alphabet holds 36 symbols.
    a = build_anchored_tpo(tape({i: [0] for i in range(13, 48)}), WED)
    letters = [b.letter for b in a.profile.brackets]
    assert len(letters) == len(set(letters)) == 35
    assert letters[0] == "a" and letters[-1] == GLOBEX_ALPHABET[34]


def test_trades_outside_the_window_are_dropped():
    before = tr(WED - timedelta(minutes=5), 7600.0)
    after = tr(THU_NOON + timedelta(hours=2), 7700.0)
    inside = tape({0: [0], 48: [1]})
    a = build_anchored_tpo([before] + inside + [after], WED, end_ct=THU_NOON)
    assert a.n_trades == len(inside)
    assert a.profile.prices == (7600.0, 7601.0)      # 7700 never entered


def test_empty_window_raises():
    with pytest.raises(ValueError):
        build_anchored_tpo([], WED)


def test_accumulator_requires_an_aware_anchor():
    with pytest.raises(ValueError):
        AnchoredTPOAccumulator(datetime(2026, 9, 9, 8, 30))


def test_tape_hole_recorded_and_widest_reported():
    trades = [tr(WED + timedelta(minutes=1), 7600.0),
              tr(WED + timedelta(minutes=40), 7601.0),        # 39 min silence
              tr(WED + timedelta(minutes=200), 7602.0)]       # 160 min silence
    a = build_anchored_tpo(trades, WED)
    assert len(a.holes) == 2
    assert a.widest_hole == (trades[1].ts, trades[2].ts)


# ── reads over the anchored window ───────────────────────────────────────────

def test_poc_value_area_and_singles_read_the_whole_window():
    # counts per row: 1, 2, 4, 2, 1 across all three segments.
    a = build_anchored_tpo(tape({0: [2], 13: [1, 2, 3], 20: [1, 2, 3],
                                 48: [0, 2, 4]}), WED)
    assert a.profile.counts() == (1, 2, 4, 2, 1)
    assert poc_row(a.profile) == 2
    assert value_area(a.profile) == (2, 4)           # total 10, target 7
    assert single_print_rows(a.profile) == []        # both runs touch an edge


def test_single_print_between_segments_is_flagged():
    a = build_anchored_tpo(tape({0: [0, 1, 2], 13: [2, 3, 4],
                                 48: [2, 4, 5, 6]}), WED)
    assert a.profile.counts() == (1, 1, 3, 1, 2, 1, 1)
    assert single_print_rows(a.profile) == [3]


def test_counts_by_role_partitions_the_profile():
    a = build_anchored_tpo(tape({0: [0, 1], 1: [1], 13: [1, 2], 48: [2, 3]}), WED)
    by = counts_by_role(a)
    assert by[ROLE_PRIOR_RTH] == (1, 2, 0, 0)
    assert by[ROLE_OVERNIGHT] == (0, 1, 1, 0)
    assert by[ROLE_TODAY_RTH] == (0, 0, 1, 1)
    total = a.profile.counts()
    assert tuple(sum(by[r][i] for r in by) for i in range(len(total))) == total


def test_roles_key_on_index_because_letters_repeat():
    a = build_anchored_tpo(tape({0: [0], 48: [1]}), WED)
    assert [b.letter for b in a.profile.brackets] == ["A", "A"]   # both are "A"
    assert a.roles() == {0: ROLE_PRIOR_RTH, 48: ROLE_TODAY_RTH}
    assert a.segment_of(0).role == ROLE_PRIOR_RTH
    assert a.segment_of(48).role == ROLE_TODAY_RTH


# ── Initial Balance, per cash session ────────────────────────────────────────

def test_initial_balance_per_rth_session():
    a = build_anchored_tpo(tape({0: [0, 1, 2], 1: [1, 3],       # prior IB 0..3
                                 13: [9], 14: [9],              # overnight
                                 48: [5, 6], 49: [4]}), WED)    # today IB 4..6
    ib = {s.role: segment_initial_balance(a, s) for s in a.segments}
    assert ib[ROLE_PRIOR_RTH] == (7600.0, 7603.0)
    assert ib[ROLE_TODAY_RTH] == (7604.0, 7606.0)
    assert ib[ROLE_OVERNIGHT] is None


def test_initial_balance_none_until_the_first_hour_completes():
    a = build_anchored_tpo(tape({0: [0, 1], 13: [5], 48: [2]}), WED)
    by_role = {s.role: s for s in a.segments}
    assert segment_initial_balance(a, by_role[ROLE_PRIOR_RTH]) is None
    assert segment_initial_balance(a, by_role[ROLE_TODAY_RTH]) is None


def test_initial_balance_needs_the_sessions_own_first_two_brackets():
    # Today's tape starts at 09:30 (brackets C, D): no IB, not a shifted one.
    a = build_anchored_tpo(tape({0: [0], 1: [0], 50: [5], 51: [6]}), WED)
    by_role = {s.role: s for s in a.segments}
    assert segment_initial_balance(a, by_role[ROLE_TODAY_RTH]) is None


def test_extend_matches_add():
    """The batch path hoists every attribute into a local; it must still be
    the same arithmetic as the one-at-a-time path."""
    trades = tape({0: [0, 3, 1], 1: [2], 13: [5, 4], 48: [1, 6], 51: [2]})
    trades += [tr(WED + timedelta(minutes=200), 7602.0)]      # forces a hole
    trades.sort(key=lambda t: t.ts)

    one = AnchoredTPOAccumulator(WED)
    for t in trades:
        one.add(t)
    many = AnchoredTPOAccumulator(WED)
    many.extend(trades)

    a, b = one.build(), many.build()
    assert a.profile == b.profile
    assert a.holes == b.holes
    assert (a.n_trades, a.last_price, a.end_ct) == (b.n_trades, b.last_price, b.end_ct)


def test_extend_resumes_after_add():
    trades = tape({0: [0, 2], 48: [1]})
    acc = AnchoredTPOAccumulator(WED)
    acc.add(trades[0])
    acc.extend(trades[1:])
    assert acc.build().profile == build_anchored_tpo(trades, WED).profile


def test_bracket_min_other_than_thirty():
    a = build_anchored_tpo(tape({0: [0], 1: [1], 2: [2]}, bracket_min=15), WED,
                           bracket_min=15)
    assert [b.letter for b in a.profile.brackets] == ["A", "B", "C"]
    assert a.bracket_min == 15
