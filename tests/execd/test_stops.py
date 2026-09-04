"""The protective stop — the arithmetic that has to be right offline. [st-eznu]

This is the number that stands alone if the box dies, so its edge cases are
tested rather than assumed: the rounding direction, the two clamps, and the
transposed sign that would place an already-triggered stop.
"""

from __future__ import annotations

import pytest

from execd.stops import (
    PREMIUM_TICK_PTS, PREMIUM_TICK_PTS_ABOVE_3, TICK_BOUNDARY_PTS, exit_triggered,
    premium_at_stop, protective_stop_price, risk_usd, stop_distance_spx,
    stop_is_consistent, tick_for,
)


class TestTheArithmetic:
    def test_the_spx_distance_walks_through_delta_into_premium(self):
        # 12 SPX points at 0.30 delta = 3.60 of premium; a 5.00 fill stops at 1.40.
        assert premium_at_stop(5.00, 0.30, 6380.0, 6368.0) == pytest.approx(1.40)
        assert protective_stop_price(5.00, 0.30, 6380.0, 6368.0) == 1.40

    def test_distance_is_unsigned(self):
        assert stop_distance_spx(6380.0, 6368.0) == 12.0
        assert stop_distance_spx(6368.0, 6380.0) == 12.0

    def test_a_put_stop_above_spot_gives_the_same_price_as_a_call_below(self):
        assert (protective_stop_price(5.00, 0.30, 6380.0, 6392.0)
                == protective_stop_price(5.00, 0.30, 6380.0, 6368.0))

    def test_risk_is_the_gap_times_the_multiplier(self):
        assert risk_usd(5.00, 1.40, qty=1) == 360.0
        assert risk_usd(2.10, 1.45, qty=2) == 130.0


class TestRounding:
    def test_the_stop_lands_on_a_tick(self):
        price = protective_stop_price(2.10, 0.31, 6380.0, 6378.7)
        assert round(price / PREMIUM_TICK_PTS, 6) == int(round(price / PREMIUM_TICK_PTS, 6))

    def test_it_rounds_up_toward_the_fill_never_down(self):
        """Rounding down would let the loss run one tick past the budget the
        distance was derived from. Read the module docstring in execd/stops.py."""
        # raw stop = 2.10 - (1.3 × 0.31) = 1.697 → 1.70, not 1.65
        assert protective_stop_price(2.10, 0.31, 6380.0, 6378.7) == 1.70

    def test_a_price_already_on_a_tick_is_left_alone(self):
        assert protective_stop_price(5.00, 0.30, 6380.0, 6368.0) == 1.40


class TestTheTickAboveThree:
    """SPX options quote in 0.10 at and above $3.00 — measured 2026-09-04
    (st-pohq, docs/measurement/spx-option-tick-2026-09-04.md): 205 of 205
    quoted sides at or above $3.00 on the 0.10 grid. A stop at 3.05 is a stop
    the exchange refuses under a live position."""

    def test_the_grid_changes_at_three(self):
        assert tick_for(2.95) == PREMIUM_TICK_PTS
        assert tick_for(TICK_BOUNDARY_PTS) == PREMIUM_TICK_PTS_ABOVE_3
        assert tick_for(57.80) == PREMIUM_TICK_PTS_ABOVE_3

    def test_a_stop_that_rounds_across_three_lands_on_the_coarse_grid(self):
        # 5.00 fill, 0.30 delta, 6.63 SPX points → 5.00 - 1.989 = 3.011 → 3.10, not 3.05
        assert protective_stop_price(5.00, 0.30, 6380.0, 6373.37) == 3.10

    def test_a_stop_just_under_three_rounds_up_onto_the_boundary(self):
        # 5.00 - (6.8 × 0.30) = 2.96 → 3.00 (on both grids)
        assert protective_stop_price(5.00, 0.30, 6380.0, 6373.2) == 3.00

    def test_a_stop_already_on_the_coarse_grid_is_left_alone(self):
        # 5.00 - (6.0 × 0.30) = 3.20
        assert protective_stop_price(5.00, 0.30, 6380.0, 6374.0) == 3.20

    def test_a_stop_below_three_still_uses_the_fine_grid(self):
        # 2.10 - (1.3 × 0.31) = 1.697 → 1.70, unchanged by the rule above
        assert protective_stop_price(2.10, 0.31, 6380.0, 6378.7) == 1.70

    @pytest.mark.parametrize("fill,delta,spx,stop_spx", [
        (5.00, 0.30, 6380.0, 6373.37), (12.50, 0.55, 7747.0, 7740.0),
        (57.80, 0.84, 7747.0, 7700.0), (3.10, 0.20, 6380.0, 6379.9),
        (8.00, 0.45, 6380.0, 6370.0), (3.05, 0.30, 6380.0, 6379.9),
    ])
    def test_every_stop_at_or_above_three_sits_on_the_coarse_grid(self, fill, delta, spx, stop_spx):
        price = protective_stop_price(fill, delta, spx, stop_spx)
        tick = tick_for(price)
        assert round(price * 100) % round(tick * 100) == 0, (price, tick)
        assert price < fill

    def test_the_cap_below_a_fill_above_three_is_one_coarse_tick_down(self):
        # A distance too small to matter: the cap applies, one 0.10 tick under 3.10.
        assert protective_stop_price(3.10, 0.30, 6380.0, 6379.99) == 3.00

    def test_the_cap_below_a_fill_straddling_the_boundary(self):
        # A 3.05 fill (an average of partials) caps at 2.95, which is on the fine grid.
        assert protective_stop_price(3.05, 0.30, 6380.0, 6379.99) == 2.95


class TestTheClamps:
    def test_a_stop_wide_enough_to_take_the_option_to_zero_rests_at_one_tick(self):
        # 100 points at 0.30 delta is 30.00 of premium against a 2.10 fill.
        assert protective_stop_price(2.10, 0.30, 6380.0, 6280.0) == PREMIUM_TICK_PTS

    def test_a_stop_that_would_sit_at_or_above_the_fill_is_pulled_one_tick_below(self):
        # A distance so small the derived stop rounds back up to the fill.
        assert protective_stop_price(2.10, 0.30, 6380.0, 6379.99) == 2.05

    def test_a_fill_of_one_tick_leaves_no_room_and_says_so(self):
        with pytest.raises(ValueError, match="no room"):
            protective_stop_price(0.05, 0.30, 6380.0, 6368.0)


class TestRefusalsRatherThanGuesses:
    """A fill with no protective stop is the state this service must not reach
    quietly, so every unusable input raises instead of returning something."""

    @pytest.mark.parametrize("kwargs,match", [
        ({"fill_px": 0.0}, "fill price"),
        ({"fill_px": -1.0}, "fill price"),
        ({"delta_abs": 0.0}, "delta"),
        ({"delta_abs": 1.5}, "delta"),
        ({"stop_spx": 6380.0}, "no distance"),
    ])
    def test_unusable_inputs_raise(self, kwargs, match):
        args = {"fill_px": 2.10, "delta_abs": 0.30, "spx_now": 6380.0, "stop_spx": 6368.0}
        args.update(kwargs)
        with pytest.raises(ValueError, match=match):
            protective_stop_price(**args)

    def test_a_negative_delta_is_read_as_its_magnitude(self):
        """FD0 carries a put's delta signed; the distance arithmetic is blind
        to direction, so -0.30 and 0.30 must give the same stop."""
        assert (protective_stop_price(2.10, -0.30, 6380.0, 6368.0)
                == protective_stop_price(2.10, 0.30, 6380.0, 6368.0))


class TestTheTrigger:
    def test_a_call_stop_fires_on_the_way_down(self):
        assert exit_triggered("C", spx=6367.0, stop_spx=6368.0)
        assert exit_triggered("CALL", spx=6368.0, stop_spx=6368.0)
        assert not exit_triggered("C", spx=6369.0, stop_spx=6368.0)

    def test_a_put_stop_fires_on_the_way_up(self):
        assert exit_triggered("P", spx=6393.0, stop_spx=6392.0)
        assert exit_triggered("PUT", spx=6392.0, stop_spx=6392.0)
        assert not exit_triggered("P", spx=6391.0, stop_spx=6392.0)

    def test_an_unknown_right_raises_rather_than_defaulting(self):
        with pytest.raises(ValueError, match="CALL or PUT"):
            exit_triggered("X", 6380.0, 6368.0)


class TestSignConsistency:
    def test_a_call_stop_below_spot_is_consistent(self):
        assert stop_is_consistent("C", spx_now=6380.0, stop_spx=6368.0)

    def test_a_call_stop_above_spot_is_already_triggered(self):
        assert not stop_is_consistent("C", spx_now=6380.0, stop_spx=6392.0)

    def test_a_put_stop_above_spot_is_consistent(self):
        assert stop_is_consistent("P", spx_now=6380.0, stop_spx=6392.0)

    def test_a_put_stop_below_spot_is_already_triggered(self):
        assert not stop_is_consistent("P", spx_now=6380.0, stop_spx=6368.0)
