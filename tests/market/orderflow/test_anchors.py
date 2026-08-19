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


def test_live_anchors_ignore_bars_that_start_before_the_session_open():
    """[st-fgno] The tape starts at 02:50 CT; the day's range edges must not.
    Bars starting before ``session_open`` neither seed nor extend; the first
    bar at/after it seeds, later ones extend as before."""
    from datetime import datetime, timezone
    from market.orderflow.anchors import LiveAnchors

    class _TBar:
        def __init__(self, high, low, start_ts):
            self.high, self.low, self.start_ts = high, low, start_ts

    open_utc = datetime(2026, 8, 18, 13, 30, tzinfo=timezone.utc)   # 08:30 CT
    la = LiveAnchors([6212.0], session_open=open_utc)
    la.observe(_TBar(6300.0, 6100.0, datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)))   # 03:00 CT
    assert (la.high.price, la.low.price) == (0.0, 0.0)          # still placeholders
    la.observe(_TBar(6220.0, 6210.0, open_utc))                  # 08:30:00 CT seeds
    assert (la.high.price, la.low.price) == (6220.0, 6210.0)
    la.observe(_TBar(6231.0, 6215.0, datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc)))
    assert (la.high.price, la.low.price) == (6231.0, 6210.0)
    # a bar without start_ts (legacy fixture) is not filtered
    class _Bar:
        def __init__(self, high, low): self.high, self.low = high, low
    la.observe(_Bar(6240.0, 6200.0))
    assert (la.high.price, la.low.price) == (6240.0, 6200.0)


# --- anchor KIND from the parse [st-tme, st-q5xu] ---------------------------

PARSE_LEVELS = [
    {"price": 7716.0, "kind": "support", "label": "major"},
    {"price": 7742.0, "kind": "resistance", "label": "major"},
    {"price": 7738.0, "kind": "trigger", "label": "reclaims are a possible long trigger"},
    {"price": 7760.0, "kind": "target", "label": "breakout target"},
    {"price": 7760.0, "kind": "resistance", "label": ""},     # target that is also a resistance
    {"price": 7730.0, "kind": "pivot", "label": "major pivot inside range"},
    {"price": 4000.0, "kind": "support", "label": "out of band"},
]


def _write_parse(tmp_path, monkeypatch, day, levels=PARSE_LEVELS):
    import json
    from market.orderflow import anchors as A
    (tmp_path / f"{day.isoformat()}.json").write_text(json.dumps({"levels": levels}))
    monkeypatch.setattr(A, "PARSED", tmp_path)
    return A


def test_parsed_kinds_follow_the_letter(tmp_path, monkeypatch):
    A = _write_parse(tmp_path, monkeypatch, date(2026, 8, 19))
    kinds = A.mancini_kinds_for(date(2026, 8, 19))
    assert kinds == {
        7716.0: ("support",),
        7730.0: ("support", "resistance"),   # pivot: engaged from either side
        7738.0: (),                          # trigger: on the chart, not watched
        7742.0: ("resistance",),
        7760.0: ("resistance",),             # the target's price is also a resistance
    }
    # every chart price is a key, so the two cannot drift apart
    assert set(A.mancini_levels_for(date(2026, 8, 19))) == set(kinds)


def test_day_anchors_carry_the_parsed_kind(tmp_path, monkeypatch):
    A = _write_parse(tmp_path, monkeypatch, date(2026, 8, 19))
    d = date(2026, 8, 19)
    a = day_anchors(A.mancini_levels_for(d), 7770.0, 7700.0, A.mancini_kinds_for(d))
    assert [(x.price, x.kind, x.mancini) for x in a] == [
        (7716.0, "support", True),
        (7730.0, "support", True),
        (7730.0, "resistance", True),
        (7742.0, "resistance", True),
        (7760.0, "resistance", True),
        (7770.0, "range_high", False),
        (7700.0, "range_low", False),
    ]


def test_day_anchors_without_kinds_is_all_supports():
    """The legacy / test default, and what a bare --mancini-levels list means."""
    a = day_anchors([7716.0, 7742.0], 7770.0, 7700.0)
    assert [(x.price, x.kind) for x in a][:2] == [(7716.0, "support"), (7742.0, "support")]


def test_labeled_day_kinds_are_supports(monkeypatch, tmp_path):
    import json
    from market.orderflow import anchors as A
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps([{"session_date": "2026-03-03", "setup": "failed_breakdown",
                                   "es_levels": [6212.0, 6230.0]}]))
    monkeypatch.setattr(A, "LABELS", labels)
    assert A.mancini_levels_for(date(2026, 3, 3)) == [6212.0, 6230.0]
    assert A.mancini_kinds_for(date(2026, 3, 3)) == {6212.0: ("support",), 6230.0: ("support",)}
    assert A.mancini_source_for(date(2026, 3, 3)) == "labels"


def test_levels_from_arg_grammar():
    from market.orderflow.anchors import levels_from_arg
    prices, kinds = levels_from_arg("7800, 7815:resistance,7820:pivot,7800")
    assert prices == [7800.0, 7815.0, 7820.0]
    assert kinds == {7800.0: ("support",), 7815.0: ("resistance",),
                     7820.0: ("support", "resistance")}
    import pytest
    with pytest.raises(ValueError):
        levels_from_arg("7800:target")


def test_kinds_round_trip_through_records():
    from market.orderflow.anchors import kinds_from_records, kinds_to_records
    kinds = {7716.0: ("support",), 7730.0: ("support", "resistance"), 7738.0: ()}
    rows = kinds_to_records(kinds)
    assert rows == [[7716.0, "support"], [7730.0, "support"], [7730.0, "resistance"]]
    back = kinds_from_records(rows)
    assert back == {7716.0: ("support",), 7730.0: ("support", "resistance")}
    assert kinds_to_records(None) is None and kinds_from_records(None) is None
    # a price whose kinds were () is simply absent after the round trip, and an
    # absent price is "not watched" — the same meaning
    assert day_anchors([7738.0], 1.0, 0.0, back)[0].kind == "range_high"


def test_live_anchors_take_kinds():
    from market.orderflow.anchors import LiveAnchors
    la = LiveAnchors([7716.0, 7742.0], kinds={7716.0: ("support",), 7742.0: ("resistance",)})
    assert [(a.price, a.kind) for a in la.anchors if a.mancini] == [
        (7716.0, "support"), (7742.0, "resistance")]
