"""Recognizer tests: one synthetic stream per setup encoding its research-doc
signature (st-2kf AC-2), plus lifecycle, wiring, and confluence coverage."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market.entities.footprint import FootprintBar, FootprintCell
from strader.entities.singleton import SingletonSetup
from market.orderflow.recognizer import Anchor, SetupRecognizer, orderflow_confirm, to_singleton_setup
from market.signals.orderflow_config import (
    CONFIRM_DELTA_MIN, FLIP_DELTA_MIN, FLUSH_DELTA_MIN, INVALIDATE_TICKS,
    ENGAGEMENT_WINDOW_BARS, QUIET_DELTA_MAX, TICK,
)

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 7, 2, 9, 0, 0, tzinfo=CENTRAL)
L = 7541.0


def _bar(i, o, h, l, c, delta):
    cells = (FootprintCell(price=round(l, 2), bid_vol=max(-delta, 0) or 1,
                           ask_vol=max(delta, 0) or 1),)
    return FootprintBar(symbol="ES.c.0", start_ts=T0 + timedelta(minutes=i),
                        end_ts=T0 + timedelta(minutes=i, seconds=40),
                        open=o, high=h, low=l, close=c,
                        volume=abs(delta) + 2, delta=delta, none_vol=0, cells=cells)


def _drive(anchor, bars, mancini=()):
    return SetupRecognizer([anchor], mancini_prices=mancini).run(bars)


# ── failed_breakdown: flush → stall → flip → confirm (research Q2.1) ────────
FBD_BARS = [
    _bar(0, L + 3, L + 3.5, L + 2.5, L + 2.8, +50),                    # above, no engagement
    _bar(1, L + 2, L + 2, L - 2, L - 1.5, -(FLUSH_DELTA_MIN + 50)),    # beat 1: violent flush
    _bar(2, L - 1.5, L - 1, L - 2.25, L - 1.75, -(FLIP_DELTA_MIN + 10)),  # beat 2: sellers press, 1-tick extension
    _bar(3, L - 1.75, L - 0.5, L - 2, L - 0.75, FLIP_DELTA_MIN + 20),  # beat 3: delta flips
    _bar(4, L - 0.75, L + 1.5, L - 1, L + 1, CONFIRM_DELTA_MIN + 30),  # beat 4: recloses above L
]


def test_failed_breakdown_full_sequence():
    recs = _drive(Anchor(L, "support"), FBD_BARS)
    assert [r.state for r in recs] == ["forming", "forming", "forming", "confirmed"]
    final = recs[-1]
    assert final.setup == "failed_breakdown"
    assert final.bias == "bullish"
    assert final.beats == ("flush", "stall", "flip", "confirm")


def test_confirmed_builds_singleton_setup():
    recs = _drive(Anchor(L, "support"), FBD_BARS, mancini=[L + 0.5])
    final = recs[-1]
    assert final.mancini_confluence is True
    s = to_singleton_setup(final)
    assert isinstance(s, SingletonSetup)
    assert s.bias == "bullish" and s.trigger == "failed_breakdown"
    assert s.anchor.price == L and s.mancini_confluence
    assert orderflow_confirm(recs, "bullish") and not orderflow_confirm(recs, "bearish")


def test_forming_rejected_by_singleton_wiring():
    recs = _drive(Anchor(L, "support"), FBD_BARS[:3])
    with pytest.raises(ValueError, match="confirmed"):
        to_singleton_setup(recs[-1])


# ── range_trap at the top: poke up, fail, reverse back inside (Q2.4) ────────
def test_range_trap_bearish_at_range_high():
    R = 7580.0
    bars = [
        _bar(0, R - 2, R - 1, R - 3, R - 1.5, +40),
        _bar(1, R - 1, R + 1.5, R - 1, R + 1, FLUSH_DELTA_MIN + 20),        # poke above on buying
        _bar(2, R + 1, R + 1.75, R + 0.5, R + 0.9, FLIP_DELTA_MIN + 5),     # buyers press, no progress
        _bar(3, R + 0.9, R + 1, R - 0.5, R - 0.2, -(FLIP_DELTA_MIN + 15)),  # delta flips down
        _bar(4, R - 0.2, R, R - 2, R - 1.5, -(CONFIRM_DELTA_MIN + 40)),     # back inside
    ]
    recs = _drive(Anchor(R, "range_high"), bars)
    final = recs[-1]
    assert final.setup == "range_trap" and final.state == "confirmed"
    assert final.bias == "bearish"
    assert final.beats == ("flush", "stall", "flip", "confirm")


# ── level_reclaim: QUIET loss discriminates from failed_breakdown (Q2.2) ────
def test_quiet_loss_is_level_reclaim_not_failed_breakdown():
    bars = [
        _bar(0, L + 2, L + 2.5, L + 1, L + 1.2, +30),
        _bar(1, L + 1, L + 1, L - 1, L - 0.75, -(QUIET_DELTA_MAX - 10)),   # quiet drift under
        _bar(2, L - 0.75, L + 0.5, L - 1.25, L + 0.25, FLIP_DELTA_MIN + 5),
        _bar(3, L + 0.25, L + 2, L, L + 1.5, CONFIRM_DELTA_MIN + 10),
    ]
    recs = _drive(Anchor(L, "support"), bars)
    assert recs[-1].setup == "level_reclaim"
    assert recs[-1].state == "confirmed"
    assert "stall" not in recs[-1].beats  # weaker instance surfaced, not suppressed


# ── return_to_lvn: both branches, labeled proposed (Q2.3) ────────────────────
def test_lvn_reject_branch():
    N = 7513.0
    bars = [
        _bar(0, N + 4, N + 4.5, N + 3.5, N + 4, -20),                       # approach from above
        _bar(1, N + 3, N + 3, N - 1, N - 0.5, -(FLUSH_DELTA_MIN + 10)),     # into the node
        _bar(2, N - 0.5, N + 1, N - 1.25, N + 0.5, FLIP_DELTA_MIN + 25),    # flips
        _bar(3, N + 0.5, N + 2, N, N + 1.5, CONFIRM_DELTA_MIN + 5),         # rejects back up
    ]
    recs = _drive(Anchor(N, "lvn"), bars)
    final = recs[-1]
    assert final.setup == "return_to_lvn" and final.state == "confirmed"
    assert final.bias == "bullish"
    assert "proposed" in final.reason


def test_lvn_accept_branch_bias_follows_break():
    N = 7513.0
    deep = INVALIDATE_TICKS * TICK + 0.5
    bars = [
        _bar(0, N + 4, N + 4.5, N + 3.5, N + 4, -20),
        _bar(1, N + 3, N + 3, N - 1, N - 0.75, -(FLUSH_DELTA_MIN + 10)),
        _bar(2, N - 0.75, N - 0.5, N - deep, N - deep + 0.5, -(FLIP_DELTA_MIN + 50)),  # extends hard
    ]
    recs = _drive(Anchor(N, "lvn"), bars)
    final = recs[-1]
    assert final.state == "confirmed" and final.bias == "bearish"
    assert "ACCEPT" in final.reason and "proposed" in final.reason
    assert final.beats[-1] == "extend"


# ── lifecycle edges ──────────────────────────────────────────────────────────
def test_deep_acceptance_invalidates():
    deep = INVALIDATE_TICKS * TICK + 1
    bars = [
        _bar(0, L + 2, L + 2, L - 2, L - 1.5, -(FLUSH_DELTA_MIN + 10)),
        _bar(1, L - 1.5, L - 1.5, L - deep, L - deep + 0.5, -(FLUSH_DELTA_MIN + 10)),
    ]
    recs = _drive(Anchor(L, "support"), bars)
    assert recs[-1].state == "invalidated"
    assert recs[-1].beats == ("flush",)


def test_window_expiry_invalidates_but_forming_was_emitted():
    bars = [_bar(0, L + 2, L + 2, L - 2, L - 1.5, -(FLUSH_DELTA_MIN + 10))]
    bars += [_bar(i, L - 1.5, L - 1, L - 2, L - 1.5, -5) for i in range(1, ENGAGEMENT_WINDOW_BARS + 2)]
    recs = _drive(Anchor(L, "support"), bars)
    assert recs[0].state == "forming" and recs[0].beats == ("flush",)
    assert recs[-1].state == "invalidated"


def test_drift_through_without_aggression_is_no_engagement():
    bars = [_bar(0, L + 2, L + 2, L - 2, L - 1.5, +80)]  # broke below on BUY delta: drift
    assert _drive(Anchor(L, "support"), bars) == []


def test_determinism_double_run():
    a = _drive(Anchor(L, "support"), FBD_BARS)
    b = _drive(Anchor(L, "support"), FBD_BARS)
    assert a == b
