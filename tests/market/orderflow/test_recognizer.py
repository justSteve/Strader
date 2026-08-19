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


# ── proximity gate: born-dead engagements rejected (st-98z item 4) ──────────
def test_far_anchor_beyond_invalidation_depth_never_engages():
    """Anchor sitting past invalidation depth above the whole tape (the 7/22
    support-anchor-7575 pattern): first with-break-delta bar must NOT engage —
    such an engagement can only invalidate, never confirm."""
    gate = INVALIDATE_TICKS * TICK  # 15 pts
    bars = [_bar(0, L - gate - 2, L - gate, L - gate - 3, L - gate - 1,
                 -(FLUSH_DELTA_MIN + 100))]
    assert _drive(Anchor(L, "support"), bars) == []


def test_flush_just_inside_invalidation_depth_still_engages():
    """Boundary: a first bar whose beyond is one point inside the gate engages
    normally (the gate is >= INVALIDATE_TICKS, not looser)."""
    depth = INVALIDATE_TICKS * TICK - 1.0  # 14 pts beyond
    bars = [_bar(0, L + 1, L + 1, L - depth, L - depth + 0.5,
                 -(FLUSH_DELTA_MIN + 10))]
    recs = _drive(Anchor(L, "support"), bars)
    assert [r.state for r in recs] == ["forming"]
    assert recs[0].beats == ("flush",)


# ── beat-4 stacked-imbalance branch: 0.9-confidence path (st-98z item 3) ────
def _stacked_reclose_bar(i):
    """Reclose bar closing back above L whose cells carry a 3-level adjacent
    buy imbalance stack (each ask cell ≥ IMBALANCE_FLOOR with an empty/quiet
    diagonal below), while bar delta (+100) stays below CONFIRM_DELTA_MIN —
    so only the ImbalanceStack evidence can confirm."""
    cells = (
        FootprintCell(price=L - 1.0, bid_vol=260, ask_vol=0),    # lone sell imb., gap-isolated
        FootprintCell(price=L, bid_vol=0, ask_vol=120),
        FootprintCell(price=L + 0.25, bid_vol=0, ask_vol=120),
        FootprintCell(price=L + 0.5, bid_vol=0, ask_vol=120),
    )
    return FootprintBar(symbol="ES.c.0", start_ts=T0 + timedelta(minutes=i),
                        end_ts=T0 + timedelta(minutes=i, seconds=40),
                        open=L - 0.75, high=L + 0.75, low=L - 1.0, close=L + 0.5,
                        volume=620, delta=+100, none_vol=0, cells=cells)


STACKED_BARS = [
    _bar(0, L + 2, L + 2, L - 2, L - 1.5, -FLUSH_DELTA_MIN),   # flush: violent break of support
    _bar(1, L - 1.5, L - 0.5, L - 1.75, L - 1, FLIP_DELTA_MIN),  # flip: delta turns up
    _stacked_reclose_bar(2),                                   # reclose w/ buy stack, Δ+100 < CONFIRM_DELTA_MIN
]


def test_stacked_imbalance_confirms_at_higher_confidence():
    recs = _drive(Anchor(L, "support"), STACKED_BARS)
    final = recs[-1]
    assert final.state == "confirmed" and final.setup == "failed_breakdown"
    assert final.bias == "bullish"
    assert final.beats == ("flush", "flip", "confirm")
    assert final.confidence == 0.9
    assert "confirmed with stacked imbalance" in final.reason


def test_delta_only_confirm_stays_at_base_confidence():
    final = _drive(Anchor(L, "support"), FBD_BARS)[-1]
    assert final.state == "confirmed"
    assert final.confidence == 0.8
    assert "confirmed on opposite delta" in final.reason


def test_determinism_double_run():
    a = _drive(Anchor(L, "support"), FBD_BARS)
    b = _drive(Anchor(L, "support"), FBD_BARS)
    assert a == b


# ── per-anchor fire counting (st-98z item 2; damp removed st-7kmt) ──────────
def _fbd_cycle(base, start_i):
    """One full flush→stall→flip→confirm cycle at ``base``. The leading
    above-level bar clears any re-engagement block from a prior cycle."""
    return [
        _bar(start_i + 0, base + 3, base + 3.5, base + 2.5, base + 2.8, +50),
        _bar(start_i + 1, base + 2, base + 2, base - 2, base - 1.5, -(FLUSH_DELTA_MIN + 50)),
        _bar(start_i + 2, base - 1.5, base - 1, base - 2.25, base - 1.75, -(FLIP_DELTA_MIN + 10)),
        _bar(start_i + 3, base - 1.75, base - 0.5, base - 2, base - 0.75, FLIP_DELTA_MIN + 20),
        _bar(start_i + 4, base - 0.75, base + 1.5, base - 1, base + 1, CONFIRM_DELTA_MIN + 30),
    ]


def test_fourth_confirm_carries_fire_index_4_at_full_confidence():
    """Every confirm carries its fire number; none is confidence-damped. The
    st-98z fi>=4 step-damp (0.6) was removed under st-7kmt — the cliff does
    not reproduce on the enriched corpus on either side — so fire 4 confirms
    at the same 0.8 as fires 1-3, and consumers weigh fire_index directly."""
    bars = [b for cyc in range(4) for b in _fbd_cycle(L, cyc * 5)]
    recs = _drive(Anchor(L, "support"), bars)
    confirms = [r for r in recs if r.state == "confirmed"]
    assert [c.fire_index for c in confirms] == [1, 2, 3, 4]
    assert [c.confidence for c in confirms] == [0.8, 0.8, 0.8, 0.8]
    # forming emissions of the 4th engagement already carry its fire number
    assert all(r.fire_index == 4 for r in recs if r.state == "forming"
               and r.timestamp >= confirms[2].timestamp)


def test_independent_anchors_do_not_share_fire_counters():
    """After 4 confirms at L, a first confirm at a different anchor is fire 1
    at full confidence. The second anchor sits 20 pts up — past the proximity
    gate — so the L-cycle bars never engage it."""
    B = L + 20.0
    bars = [b for cyc in range(4) for b in _fbd_cycle(L, cyc * 5)]
    bars += _fbd_cycle(B, 20)
    recs = SetupRecognizer([Anchor(L, "support"), Anchor(B, "support")]).run(bars)
    confirms_b = [r for r in recs if r.state == "confirmed" and r.anchor_price == B]
    assert [c.fire_index for c in confirms_b] == [1]
    assert confirms_b[0].confidence == 0.8
    confirms_l = [r for r in recs if r.state == "confirmed" and r.anchor_price == L]
    assert [c.fire_index for c in confirms_l] == [1, 2, 3, 4]


def test_fire_counter_survives_block_and_invalidation_cycles():
    """The counter counts CONFIRMS per anchor across the recognizer's whole
    lifetime: an invalidated engagement in between neither increments it nor
    resets it — the count is the anchor's session-long history."""
    deep = INVALIDATE_TICKS * TICK + 1
    bars = list(_fbd_cycle(L, 0))                                # confirm: fire 1
    bars += [
        _bar(5, L + 3, L + 3.5, L + 0.5, L + 2, +50),            # clears the block
        _bar(6, L + 2, L + 2, L - 2, L - 1.5, -(FLUSH_DELTA_MIN + 10)),   # re-engage
        _bar(7, L - 1.5, L - 1.5, L - deep, L - deep + 0.5, -(FLUSH_DELTA_MIN + 10)),  # invalidate
    ]
    bars += _fbd_cycle(L, 8)                                     # confirm: fire 2
    recs = _drive(Anchor(L, "support"), bars)
    confirms = [r for r in recs if r.state == "confirmed"]
    invalidated = [r for r in recs if r.state == "invalidated"]
    assert [c.fire_index for c in confirms] == [1, 2]
    assert [c.confidence for c in confirms] == [0.8, 0.8]
    assert len(invalidated) == 1 and invalidated[0].fire_index == 2  # would-be fire 2, didn't count


# ── the upside mirror at a RESISTANCE anchor [st-q5xu, st-tme] ───────────────
# Same four beats read upward: push above on buying, stall, delta flips down,
# close back beneath on selling. The name says which way the break went —
# failed_breakout / level_reject — and the bias is bearish.
R = 7815.0
FBO_BARS = [
    _bar(0, R - 3, R - 2.5, R - 3.5, R - 2.8, -50),                      # below, no engagement
    _bar(1, R - 2, R + 2, R - 2, R + 1.5, FLUSH_DELTA_MIN + 50),         # beat 1: violent push above
    _bar(2, R + 1.5, R + 2.25, R + 1, R + 1.75, FLIP_DELTA_MIN + 10),    # beat 2: buyers press, 1-tick extension
    _bar(3, R + 1.75, R + 2, R + 0.5, R + 0.75, -(FLIP_DELTA_MIN + 20)), # beat 3: delta flips down
    _bar(4, R + 0.75, R + 1, R - 1.5, R - 1, -(CONFIRM_DELTA_MIN + 30)), # beat 4: recloses beneath R
]


def test_failed_breakout_bearish_at_resistance():
    recs = _drive(Anchor(R, "resistance"), FBO_BARS, mancini=[R])
    assert [r.state for r in recs] == ["forming", "forming", "forming", "confirmed"]
    final = recs[-1]
    assert final.setup == "failed_breakout"
    assert final.bias == "bearish"
    assert final.anchor_kind == "resistance"
    assert final.beats == ("flush", "stall", "flip", "confirm")
    assert final.reason.startswith("failed_breakout confirmed @ 7815.00 (resistance ∩ mancini)")
    s = to_singleton_setup(final)
    assert s.bias == "bearish" and s.trigger == "failed_breakout" and s.right == "PUT"
    assert s.anchor.label == "resistance"
    assert orderflow_confirm(recs, "bearish") and not orderflow_confirm(recs, "bullish")


def test_same_bars_at_a_support_anchor_read_the_other_way():
    """The 2026-08-05 inversion, pinned: 7815 was a resistance in the parse and
    entered as a support. On the same tape the support anchor reads price
    falling back beneath 7815 as a flush below a support — a BULLISH
    failed-breakdown family read forming — where the resistance anchor reads
    the push-and-fail as the bear signal it is. Same silhouette, opposite
    meaning; the anchor's kind is what decides it."""
    as_support = _drive(Anchor(R, "support"), FBO_BARS)
    assert as_support and all(r.bias == "bullish" for r in as_support)
    assert {r.setup for r in as_support} <= {"failed_breakdown", "level_reclaim"}
    as_resistance = _drive(Anchor(R, "resistance"), FBO_BARS)
    assert all(r.bias == "bearish" and r.setup == "failed_breakout" for r in as_resistance)
    assert as_resistance[-1].state == "confirmed"


def test_quiet_push_is_level_reject_not_failed_breakout():
    bars = [
        _bar(0, R - 2, R - 1, R - 2.5, R - 1.2, -30),
        _bar(1, R - 1, R + 1, R - 1, R + 0.75, QUIET_DELTA_MAX - 10),      # quiet drift over
        _bar(2, R + 0.75, R + 1.25, R - 0.5, R - 0.25, -(FLIP_DELTA_MIN + 5)),
        _bar(3, R - 0.25, R, R - 2, R - 1.5, -(CONFIRM_DELTA_MIN + 10)),
    ]
    recs = _drive(Anchor(R, "resistance"), bars)
    assert recs[-1].setup == "level_reject"
    assert recs[-1].state == "confirmed" and recs[-1].bias == "bearish"
    assert "stall" not in recs[-1].beats


def test_resistance_invalidation_reads_upward():
    """Acceptance above a resistance is the breakout holding — the word is
    not 'no reclaim' (a support never recovered) but its mirror."""
    bars = [
        _bar(0, R - 2, R - 1, R - 3, R - 1.5, -40),
        _bar(1, R - 1, R + 2, R - 1, R + 1.5, FLUSH_DELTA_MIN + 20),
        _bar(2, R + 1.5, R + INVALIDATE_TICKS * TICK + 1, R + 1, R + INVALIDATE_TICKS * TICK,
             FLIP_DELTA_MIN + 50),
    ]
    recs = _drive(Anchor(R, "resistance"), bars)
    assert recs[-1].state == "invalidated" and recs[-1].setup == "failed_breakout"
    assert "held above, no reject" in recs[-1].reason
    down = _drive(Anchor(L, "support"), [
        _bar(0, L + 3, L + 3.5, L + 2.5, L + 2.8, +50),
        _bar(1, L + 2, L + 2, L - 2, L - 1.5, -(FLUSH_DELTA_MIN + 50)),
        _bar(2, L - 1.5, L - 1, L - INVALIDATE_TICKS * TICK - 1, L - INVALIDATE_TICKS * TICK,
             -(FLIP_DELTA_MIN + 50)),
    ])
    assert "no reclaim" in down[-1].reason


def test_pivot_is_two_anchors_engaged_from_either_side():
    """A Mancini pivot enters as a support AND a resistance at one price. Each
    is engaged from its own side and emits under its own kind and name;
    neither's state leaks into the other."""
    sup, res = Anchor(R, "support", "mancini"), Anchor(R, "resistance", "mancini")
    recs = SetupRecognizer([sup, res]).run(FBO_BARS)
    by_kind = {}
    for r in recs:
        by_kind.setdefault(r.anchor_kind, set()).add((r.setup, r.bias))
    assert by_kind["resistance"] == {("failed_breakout", "bearish")}
    assert by_kind["support"] <= {("failed_breakdown", "bullish"), ("level_reclaim", "bullish")}
    assert [r for r in recs if r.anchor_kind == "resistance"][-1].state == "confirmed"
