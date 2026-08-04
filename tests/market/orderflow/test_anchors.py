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


# --- live anchor set [st-b0n9] ---------------------------------------------

class _Bar:
    """Minimal stand-in — LiveAnchors reads only high/low."""
    def __init__(self, high, low):
        self.high, self.low = high, low


def test_live_anchors_seed_from_the_first_bar():
    """A live session has no session high/low at boot. The first bar seeds
    both edges rather than leaving them at a placeholder price."""
    from market.orderflow.anchors import LiveAnchors

    la = LiveAnchors([6212.0])
    la.observe(_Bar(6220.0, 6210.0))
    assert la.high.price == 6220.0
    assert la.low.price == 6210.0


def test_live_anchors_extend_with_the_developing_session():
    from market.orderflow.anchors import LiveAnchors

    la = LiveAnchors([])
    la.observe(_Bar(6220.0, 6210.0))
    la.observe(_Bar(6218.0, 6205.0))     # new low only
    assert (la.high.price, la.low.price) == (6220.0, 6205.0)
    la.observe(_Bar(6231.0, 6215.0))     # new high only
    assert (la.high.price, la.low.price) == (6231.0, 6205.0)


def test_live_anchors_converge_on_the_replay_anchor_set():
    """The point of extending: by the close, live is watching exactly what a
    replay of the same day watches. Any other rule diverges permanently."""
    from market.orderflow.anchors import LiveAnchors

    bars = [_Bar(6220.0, 6210.0), _Bar(6218.0, 6205.0), _Bar(6231.0, 6215.0)]
    la = LiveAnchors([6212.0])
    for b in bars:
        la.observe(b)
    replay = day_anchors([6212.0], max(b.high for b in bars), min(b.low for b in bars))
    assert [(a.price, a.kind) for a in la.anchors] == [(a.price, a.kind) for a in replay]


def test_engaged_range_edge_is_frozen_until_it_goes_idle():
    """A range edge breaks exactly when a new extreme prints — the same bar
    that would extend it. Extending mid-engagement rewrites the level under the
    read, so no range_trap could ever complete."""
    from market.orderflow.anchors import LiveAnchors
    from market.orderflow.recognizer import SetupRecognizer

    la = LiveAnchors([])
    rec = SetupRecognizer(la.anchors)
    la.attach(rec)
    la.observe(_Bar(6220.0, 6210.0))
    assert (la.high.price, la.low.price) == (6220.0, 6210.0)

    # engage both edges by hand — the swap must refuse while state is held
    rec._active[id(la.high)] = object()
    rec._blocked[id(la.low)] = -1
    la.observe(_Bar(6240.0, 6200.0))
    assert (la.high.price, la.low.price) == (6220.0, 6210.0)

    rec._active.clear(); rec._blocked.clear()
    la.observe(_Bar(6240.0, 6200.0))
    assert (la.high.price, la.low.price) == (6240.0, 6200.0)


def test_attached_anchor_set_shares_one_list_with_the_recognizer():
    """Two lists holding the same anchors is a sync invariant waiting to rot —
    a swap that updated one and not the other would leave the recognizer
    judging against a level nobody can see."""
    from market.orderflow.anchors import LiveAnchors
    from market.orderflow.recognizer import SetupRecognizer

    la = LiveAnchors([6212.0])
    rec = SetupRecognizer(la.anchors)
    la.attach(rec)
    assert la.anchors is rec.anchors
    la.observe(_Bar(6220.0, 6210.0))
    assert rec.anchors[la._hi].price == 6220.0


def test_retarget_carries_confluence_and_fire_history():
    """The moved anchor is the SAME level ("day high") at a new price. Losing
    its fire count would quietly re-arm the >= 4th-fire damping on every new
    session extreme."""
    from market.orderflow.recognizer import Anchor, SetupRecognizer

    a = Anchor(6212.0, "support", "x")
    rec = SetupRecognizer([a], mancini_prices=[6212.0])
    assert rec._confluent[id(a)] is True
    rec._fires[id(a)] = 3

    b = rec.retarget(a, 6215.0)
    assert b is not None and b.price == 6215.0
    assert rec.anchors[0] is b
    assert rec._confluent[id(b)] is True
    assert rec._fires[id(b)] == 3
    assert id(a) not in rec._fires


def test_retarget_refuses_an_engaged_anchor():
    from market.orderflow.recognizer import Anchor, SetupRecognizer

    a = Anchor(6212.0, "support", "x")
    rec = SetupRecognizer([a])
    rec._active[id(a)] = object()
    assert rec.retarget(a, 6215.0) is None
    assert rec.anchors[0] is a


def test_recognizer_reports_idle_only_when_the_anchor_is_free():
    from market.orderflow.recognizer import Anchor, SetupRecognizer

    a = Anchor(6212.0, "support", "x")
    rec = SetupRecognizer([a])
    assert rec.is_idle(a)
    rec._active[id(a)] = object()
    assert not rec.is_idle(a)
    del rec._active[id(a)]
    rec._blocked[id(a)] = -1
    assert not rec.is_idle(a)
