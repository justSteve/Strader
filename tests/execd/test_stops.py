"""The protective stop — the arithmetic that has to be right offline. [st-eznu]

This is the number that stands alone if the box dies, so its edge cases are
tested rather than assumed: the rounding direction, the two clamps, and the
transposed sign that would place an already-triggered stop.
"""

from __future__ import annotations

import pytest

from execd.stops import (
    PREMIUM_TICK_PTS, exit_triggered, premium_at_stop, protective_stop_price,
    risk_usd, stop_distance_spx, stop_is_consistent,
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
