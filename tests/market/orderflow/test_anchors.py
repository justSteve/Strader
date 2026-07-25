"""Anchor-derivation rule tests. [st-055]"""
from datetime import date

from market.orderflow.anchors import day_anchors, mancini_levels_for


def test_day_anchors_mancini_plus_range_edges():
    a = day_anchors([6212.0, 6230.0], 6250.0, 6200.0)
    assert [(x.price, x.kind, x.mancini) for x in a] == [
        (6212.0, "support", True),
        (6230.0, "support", True),
        (6250.0, "range_high", False),
        (6200.0, "range_low", False),
    ]


def test_day_anchors_dedup_on_price_and_kind():
    # duplicate mancini level collapses; a level equal to the session low is a
    # different KIND, so both survive
    a = day_anchors([6200.0, 6200.0], 6250.0, 6200.0)
    assert len(a) == 3
    kinds = {x.kind for x in a}
    assert kinds == {"support", "range_high", "range_low"}


def test_mancini_levels_for_unlabeled_day_is_empty():
    assert mancini_levels_for(date(1999, 1, 1)) == []
