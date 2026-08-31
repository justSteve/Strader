"""Every bound refuses, and refuses under its own name. [st-eznu]

The name matters as much as the refusal. A journal line reading
``{"bound": "ceiling"}`` is something Steve can act on; ``{"bound": "invalid"}``
is not, and a service whose refusals all collapse to one label cannot be
audited after a bad day.

So each test here asserts the ``bound`` field, not merely that something said
no — and ``TestOrderOfChecks`` pins the sequence, because an intent that breaks
three bounds must be refused for the most fundamental one rather than for
whichever check the code happens to reach first.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execd.bounds import (
    Bounds, DayState, QuoteView, check_entry, check_exit, check_instrument,
    check_preview_cost, check_price_band, check_window, load_bounds, session_close,
)
from execd.intent import OrderIntent, OrderType, Side

from .conftest import CALL, CT, MIDSESSION, PUT, SPX_NOW, entry, exit_intent

GOOD_QUOTE = QuoteView(bid=2.00, ask=2.10, age_s=1.0)
NO_STATE = DayState()


def refusal(intent, *, bounds=None, state=NO_STATE, quote=GOOD_QUOTE,
            now=MIDSESSION, killed=False):
    return check_entry(intent, bounds or Bounds(), state, quote, now, killed=killed)


class TestTheHappyPath:
    def test_a_well_formed_entry_mid_session_is_not_refused(self):
        assert refusal(entry()) is None

    def test_a_put_entry_with_its_stop_above_spot_is_not_refused(self):
        assert refusal(entry(symbol=PUT, limit=1.90, stop_spx=SPX_NOW + 12,
                             delta=0.28),
                       quote=QuoteView(1.80, 1.90, 1.0)) is None


class TestEachBoundRefusesByName:
    def test_instrument(self):
        r = refusal(entry(symbol="AAPL  260826C00190000"))
        assert r.bound == "instrument" and "AAPL" in r.reason

    def test_instrument_refuses_a_symbol_that_is_not_an_option_at_all(self):
        r = check_instrument(OrderIntent("t", "SPX", Side.BUY_TO_OPEN, 1), Bounds())
        assert r.bound == "instrument"

    def test_side_refuses_a_close_arriving_on_the_entry_path(self):
        r = refusal(OrderIntent("t", CALL, Side.SELL_TO_CLOSE, 1,
                                order_type=OrderType.LIMIT, limit=2.10,
                                stop_spx=SPX_NOW - 12, delta=0.3))
        assert r.bound == "side" and "long premium only" in r.reason

    def test_order_type_refuses_a_market_entry(self):
        r = refusal(OrderIntent("t", CALL, Side.BUY_TO_OPEN, 1,
                                order_type=OrderType.MARKET,
                                stop_spx=SPX_NOW - 12, delta=0.3))
        assert r.bound == "order_type" and "blank cheque" in r.reason

    def test_qty_refuses_more_than_the_cap(self):
        r = refusal(entry(qty=2))
        assert r.bound == "qty" and "1-contract cap" in r.reason

    def test_qty_allows_exactly_the_cap(self):
        assert refusal(entry(qty=2), bounds=Bounds(qty_cap=2)) is None

    def test_stop_refuses_while_the_kill_file_is_present(self):
        r = refusal(entry(), killed=True)
        assert r.bound == "stop" and "STOP is on" in r.reason

    def test_protective_stop_refuses_an_entry_with_no_stop_level(self):
        r = refusal(entry(stop_spx=None))
        assert r.bound == "protective_stop"

    def test_protective_stop_refuses_an_entry_with_no_delta(self):
        r = refusal(entry(delta=None))
        assert r.bound == "protective_stop"

    def test_window_refuses_before_the_open(self):
        r = refusal(entry(), now=datetime(2026, 8, 26, 8, 0, tzinfo=CT))
        assert r.bound == "window" and "before" in r.reason

    def test_window_refuses_a_new_position_after_the_late_cutoff(self):
        # 14:55 CT is inside the session but past no_open_after (14:50).
        r = refusal(entry(), now=datetime(2026, 8, 26, 14, 55, tzinfo=CT))
        assert r.bound == "window" and "no new positions" in r.reason

    def test_window_refuses_a_weekend(self):
        r = refusal(entry(), now=datetime(2026, 8, 30, 10, 0, tzinfo=CT))
        assert r.bound == "window" and "Sunday" in r.reason

    def test_positions_refuses_a_second_open_position(self):
        r = refusal(entry(), state=DayState(open_positions=1))
        assert r.bound == "positions"

    def test_ceiling_refuses_once_the_attempts_are_spent(self):
        r = refusal(entry(), state=DayState(attempts_used=2))
        assert r.bound == "ceiling" and "attempts" in r.reason

    def test_ceiling_refuses_at_the_daily_loss_limit(self):
        r = refusal(entry(), state=DayState(realized_loss_usd=100.0))
        assert r.bound == "ceiling" and "$100.00 ceiling" in r.reason

    def test_ceiling_allows_a_dollar_short_of_the_limit(self):
        assert refusal(entry(), state=DayState(realized_loss_usd=99.0)) is None

    def test_price_band_refuses_a_limit_far_above_the_offer(self):
        r = refusal(entry(limit=4.00))
        assert r.bound == "price_band" and "above" in r.reason

    def test_price_band_refuses_a_limit_far_below_the_bid(self):
        r = refusal(entry(limit=0.50))
        assert r.bound == "price_band" and "below" in r.reason

    def test_price_band_refuses_a_stale_quote(self):
        r = refusal(entry(), quote=QuoteView(2.00, 2.10, age_s=120))
        assert r.bound == "price_band" and "old" in r.reason

    def test_price_band_refuses_a_one_sided_market(self):
        r = refusal(entry(), quote=QuoteView(0.0, 2.10, 1.0))
        assert r.bound == "price_band" and "two-sided" in r.reason

    def test_price_band_refuses_to_price_with_no_quote_at_all(self):
        r = refusal(entry(), quote=None)
        assert r.bound == "price_band" and "blind" in r.reason

    def test_preview_cost_refuses_when_the_broker_disagrees_with_the_intent(self):
        r = check_preview_cost(entry(limit=2.10), previewed_usd=260.0, bounds=Bounds())
        assert r.bound == "preview_cost" and "$260.00" in r.reason

    def test_preview_cost_tolerates_the_commission(self):
        assert check_preview_cost(entry(limit=2.10), 210.65, Bounds()) is None


class TestOrderOfChecks:
    """An intent that breaks several bounds names the most fundamental one."""

    def test_the_wrong_instrument_outranks_everything_else(self):
        r = refusal(entry(symbol="AAPL  260826C00190000", qty=99, limit=99.0,
                          stop_spx=None, delta=None),
                    state=DayState(open_positions=3, realized_loss_usd=500),
                    now=datetime(2026, 8, 30, 3, 0, tzinfo=CT), killed=True)
        assert r.bound == "instrument"

    def test_quantity_outranks_the_kill_file(self):
        assert refusal(entry(qty=99), killed=True).bound == "qty"

    def test_the_kill_file_outranks_the_window(self):
        r = refusal(entry(), now=datetime(2026, 8, 26, 3, 0, tzinfo=CT), killed=True)
        assert r.bound == "stop"

    def test_the_window_outranks_the_position_limit(self):
        r = refusal(entry(), state=DayState(open_positions=9),
                    now=datetime(2026, 8, 26, 3, 0, tzinfo=CT))
        assert r.bound == "window"

    def test_the_ceiling_outranks_the_price_band(self):
        r = refusal(entry(limit=99.0), state=DayState(realized_loss_usd=500))
        assert r.bound == "ceiling"


class TestExitsClearAlmostNothing:
    """Read ``check_exit``'s docstring before relaxing any of these."""

    def test_an_exit_passes_while_the_kill_file_is_on(self):
        assert check_exit(exit_intent(), Bounds()) is None

    def test_an_exit_passes_outside_the_session_window(self):
        # check_exit takes no clock at all — that is the assertion.
        assert check_exit(exit_intent(), Bounds()) is None

    def test_an_exit_passes_with_the_ceiling_breached(self):
        assert check_exit(exit_intent(), Bounds()) is None

    def test_an_exit_still_refuses_an_instrument_this_service_does_not_trade(self):
        r = check_exit(exit_intent(symbol="AAPL  260826C00190000"), Bounds())
        assert r.bound == "instrument"

    def test_an_exit_that_would_open_risk_is_refused(self):
        r = check_exit(entry(), Bounds())
        assert r.bound == "side" and "open risk" in r.reason

    def test_closing_more_than_is_held_would_leave_a_short_and_is_refused(self):
        r = check_exit(exit_intent(qty=3), Bounds(), held_qty=1)
        assert r.bound == "qty" and "short" in r.reason

    def test_closing_exactly_what_is_held_passes(self):
        assert check_exit(exit_intent(qty=2), Bounds(), held_qty=2) is None

    def test_closing_part_of_what_is_held_passes(self):
        assert check_exit(exit_intent(qty=1), Bounds(), held_qty=2) is None

    def test_an_unknown_position_size_does_not_block_the_exit(self):
        """Refusing on ignorance is how an exit gate traps someone. A position
        the service did not open still has to be closable."""
        assert check_exit(exit_intent(qty=5), Bounds(), held_qty=None) is None


class TestWindow:
    @pytest.mark.parametrize("hour,minute,opening,expected", [
        (8, 29, True, "window"), (8, 30, True, None), (14, 49, True, None),
        (14, 50, True, "window"), (14, 55, False, None), (15, 0, False, "window"),
    ])
    def test_the_two_cutoffs(self, hour, minute, opening, expected):
        now = datetime(2026, 8, 26, hour, minute, tzinfo=CT)
        got = check_window(now, Bounds(), opening=opening)
        assert (got.bound if got else None) == expected

    def test_utc_input_is_converted_to_central(self):
        # 15:00 UTC is 10:00 CDT — inside the session, not past the close.
        assert check_window(datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc),
                            Bounds(), opening=True) is None

    def test_session_close_is_todays_close_in_central(self):
        close = session_close(MIDSESSION, Bounds())
        assert close.astimezone(CT).strftime("%Y-%m-%d %H:%M") == "2026-08-26 15:00"

    def test_session_close_after_the_bell_rolls_to_the_next_day(self):
        after = datetime(2026, 8, 26, 16, 0, tzinfo=CT)
        assert session_close(after, Bounds()).astimezone(CT).day == 27


class TestConfiguration:
    def test_the_start_values_are_the_ones_in_the_design(self):
        b = Bounds()
        assert b.instruments == ("SPX", "SPXW")
        assert (b.qty_cap, b.max_open_positions) == (1, 1)
        assert (b.daily_loss_ceiling_usd, b.max_attempts) == (100.0, 2)
        assert (b.open_ct, b.close_ct, b.no_open_after_ct) == ("08:30", "15:00", "14:50")

    def test_steves_file_overrides_the_start_values(self, tmp_path):
        p = tmp_path / "bounds.yaml"
        p.write_text("qty_cap: 2\ndaily_loss_ceiling_usd: 250\ninstruments: [spxw]\n")
        b = load_bounds(p)
        assert (b.qty_cap, b.daily_loss_ceiling_usd, b.instruments) == (2, 250, ("SPXW",))

    def test_a_missing_file_falls_back_to_the_start_values(self, tmp_path):
        assert load_bounds(tmp_path / "absent.yaml") == Bounds()

    def test_a_typo_in_the_file_is_loud_rather_than_silently_defaulted(self, tmp_path):
        p = tmp_path / "bounds.yaml"
        p.write_text("qty_capp: 5\n")
        with pytest.raises(ValueError, match="unknown bound"):
            load_bounds(p)

    def test_an_incoherent_window_is_refused(self):
        with pytest.raises(ValueError, match="must precede"):
            Bounds(open_ct="15:00", close_ct="08:30").validated()

    def test_a_cutoff_outside_the_window_is_refused(self):
        with pytest.raises(ValueError, match="inside the window"):
            Bounds(no_open_after_ct="16:00").validated()

    @pytest.mark.parametrize("kw", [
        {"qty_cap": 0}, {"max_open_positions": 0}, {"daily_loss_ceiling_usd": 0},
        {"max_attempts": 0}, {"price_band_pct": 1.5}, {"max_quote_age_s": 0},
        {"instruments": ()},
    ])
    def test_nonsense_values_are_refused(self, kw):
        with pytest.raises(ValueError, match="bounds:"):
            Bounds(**kw).validated()

    def test_the_protective_stop_cannot_be_switched_off(self):
        """Finding 8, case st-5qjq. The docstring said the shape of the bounds
        is not configurable and then shipped one key that switched one off — the
        key for the bound the design calls not optional."""
        with pytest.raises(ValueError, match="cannot be turned off"):
            Bounds(require_protective_stop=False).validated()
        with pytest.raises(ValueError, match="cannot be turned off"):
            Bounds.from_dict({"require_protective_stop": False})

    def test_to_dict_names_every_bound_the_service_enforces(self):
        assert set(Bounds().to_dict()) == {
            "instruments", "qty_cap", "max_open_positions", "daily_loss_ceiling_usd",
            "max_attempts", "open_ct", "close_ct", "no_open_after_ct", "weekdays_only",
            "price_band_pct", "max_quote_age_s", "preview_cost_tolerance_usd",
            "require_protective_stop",
        }


class TestTheBoundsAreAllCovered:
    """Stage 1's acceptance says *every* bound has a refusing test. A count of
    tests cannot show that, and a coverage percentage would only show that the
    lines ran. So the names are read out of the service's own source and
    checked against what the suite actually asserts — which means a bound added
    later without a test fails here, on the day it is added."""

    @staticmethod
    def _declared() -> set[str]:
        import re
        from pathlib import Path

        package = Path(__file__).resolve().parents[2] / "execd"
        declared: set[str] = set()
        for module in ("bounds.py", "arming.py"):
            source = (package / module).read_text(encoding="utf-8")
            declared |= set(re.findall(r'Refusal\(\s*"(\w+)"', source))
        return declared

    @staticmethod
    def _asserted() -> set[str]:
        import re
        from pathlib import Path

        asserted: set[str] = set()
        for path in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
            source = path.read_text(encoding="utf-8")
            asserted |= set(re.findall(r'bound\s*==\s*"(\w+)"', source))
            asserted |= set(re.findall(r'"bound":\s*"(\w+)"', source))
        return asserted

    def test_the_scan_finds_the_bounds_it_is_supposed_to(self):
        """A meta-test that silently matched nothing would pass forever."""
        declared = self._declared()
        assert {"instrument", "qty", "ceiling", "window", "stop"} <= declared
        assert len(declared) >= 10

    def test_every_bound_the_service_can_emit_has_a_refusing_test(self):
        missing = self._declared() - self._asserted()
        assert not missing, (
            f"these bounds can be emitted and no test asserts them: {sorted(missing)}"
        )


class TestPriceBandArithmetic:
    def test_the_band_is_a_percentage_of_the_touch(self):
        b = Bounds(price_band_pct=0.10)
        q = QuoteView(2.00, 2.10, 1.0)
        assert check_price_band(entry(limit=2.31), b, q) is None       # 2.10 × 1.10
        assert check_price_band(entry(limit=2.32), b, q).bound == "price_band"
        assert check_price_band(entry(limit=1.80), b, q) is None       # 2.00 × 0.90
        assert check_price_band(entry(limit=1.79), b, q).bound == "price_band"

    def test_a_market_exit_is_not_priced_against_the_band(self):
        assert check_price_band(exit_intent(), Bounds(), QuoteView(2.0, 2.1, 1.0)) is None
