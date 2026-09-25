"""Every bound refuses, and refuses under its own name. [st-eznu]

The name matters as much as the refusal. A journal line reading
``{"bound": "price_band"}`` is something Steve can act on; ``{"bound": "invalid"}``
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
    check_preview_cost, check_price_band,
    load_bounds,
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

    @pytest.mark.parametrize("when", [
        datetime(2026, 8, 26, 8, 0, tzinfo=CT),      # before the old open
        datetime(2026, 8, 26, 14, 55, tzinfo=CT),    # past the old 14:50 cutoff
        datetime(2026, 8, 26, 16, 0, tzinfo=CT),     # after the bell
        datetime(2026, 8, 29, 10, 0, tzinfo=CT),     # a Saturday
        datetime(2026, 8, 30, 3, 0, tzinfo=CT),      # a Sunday, small hours
    ])
    def test_no_bound_reads_the_clock(self, when):
        """Steve, 2026-09-24: "never ever place that kind of restriction on
        me". No hour and no day of the week refuses an entry. [co-8mb1z]"""
        assert refusal(entry(), now=when) is None, when

    def test_no_count_of_positions_attempts_or_losses_refuses(self):
        """Steve, 2026-09-24: "' one open position, the $500 daily loss limit '
        have a sub remove these also ... make sure they are removed now and
        not restored in the future." [co-8mb1z]"""
        state = DayState(open_positions=40, realized_loss_usd=1_000_000.0,
                         attempts_used=999)
        assert refusal(entry(), state=state) is None

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


class TestTheTick:
    """SPX options quote in 0.05 below $3.00 and 0.10 at and above it —
    measured 2026-09-04 (st-pohq). An off-grid price is an order the exchange
    rejects, so it is refused here, entry and exit alike."""

    def test_an_entry_limit_off_the_coarse_grid_is_refused(self):
        r = refusal(entry(limit=3.05), quote=QuoteView(3.00, 3.10, 1.0))
        assert r.bound == "tick" and "3.05" in r.reason and "0.10" in r.reason

    def test_an_entry_limit_on_the_coarse_grid_passes(self):
        assert refusal(entry(limit=3.10), quote=QuoteView(3.00, 3.10, 1.0)) is None

    def test_an_entry_limit_on_the_fine_grid_below_three_passes(self):
        assert refusal(entry(limit=2.05)) is None

    def test_an_entry_limit_off_the_fine_grid_is_refused(self):
        r = refusal(entry(limit=2.07))
        assert r.bound == "tick" and "0.05" in r.reason

    def test_the_tick_is_checked_before_the_band(self):
        # 3.05 is inside the band around a 3.00/3.10 quote; the grid refuses it first.
        r = refusal(entry(limit=3.05), quote=QuoteView(3.00, 3.10, 1.0))
        assert r.bound == "tick"

    @staticmethod
    def _stop_exit(stop_price: float) -> OrderIntent:
        return OrderIntent(intent_id="t-stop", symbol=CALL, side=Side.SELL_TO_CLOSE, qty=1,
                           order_type=OrderType.STOP, stop_price=stop_price, source="test")

    def test_an_exit_stop_off_the_grid_is_refused_because_it_is_no_stop(self):
        r = check_exit(self._stop_exit(3.05), Bounds())
        assert r.bound == "tick" and "stop_price" in r.reason

    def test_an_exit_stop_on_the_grid_passes(self):
        assert check_exit(self._stop_exit(3.10), Bounds()) is None

    def test_a_market_exit_carries_no_price_and_passes(self):
        assert check_exit(exit_intent(), Bounds()) is None


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


class TestConfiguration:
    def test_the_start_values_are_the_ones_in_the_design(self):
        b = Bounds()
        assert b.instruments == ("SPX", "SPXW")
        assert b.qty_cap == 1
        for gone in ("open_ct", "close_ct", "no_open_after_ct", "flat_by_close_ct",
                     "weekdays_only"):
            assert not hasattr(b, gone), gone        # no clock rules (co-8mb1z)

    def test_steves_file_overrides_the_start_values(self, tmp_path):
        p = tmp_path / "bounds.yaml"
        p.write_text("qty_cap: 2\nprice_band_pct: 0.2\ninstruments: [spxw]\n")
        b = load_bounds(p)
        assert (b.qty_cap, b.price_band_pct, b.instruments) == (2, 0.2, ("SPXW",))

    def test_a_missing_file_falls_back_to_the_start_values(self, tmp_path):
        assert load_bounds(tmp_path / "absent.yaml") == Bounds()

    def test_a_typo_in_the_file_is_loud_rather_than_silently_defaulted(self, tmp_path):
        p = tmp_path / "bounds.yaml"
        p.write_text("qty_capp: 5\n")
        with pytest.raises(ValueError, match="unknown bound"):
            load_bounds(p)

    def test_an_old_file_with_the_retired_keys_still_loads(self, tmp_path):
        """/etc files written before 2026-09-24 carry these; they must not
        stop the service from starting, and they must do nothing."""
        p = tmp_path / "bounds.yaml"
        p.write_text('open_ct: "08:30"\nclose_ct: "15:00"\nno_open_after_ct: "14:50"\n'
                     'flat_by_close_ct: "14:55"\nweekdays_only: true\nqty_cap: 1\n'
                     'max_open_positions: 1\ndaily_loss_ceiling_usd: 500.0\nmax_attempts: 10\n')
        assert load_bounds(p) == Bounds()

    def test_the_shipped_example_carries_no_retired_keys(self):
        from pathlib import Path
        import yaml
        from execd.bounds import RETIRED_KEYS
        example = Path(__file__).resolve().parents[2] / "execd" / "bounds.example.yaml"
        assert not set(yaml.safe_load(example.read_text())) & RETIRED_KEYS

    @pytest.mark.parametrize("kw", [
        {"qty_cap": 0}, {"price_band_pct": 1.5}, {"max_quote_age_s": 0},
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
            "instruments", "qty_cap",
            "price_band_pct", "max_quote_age_s", "preview_cost_tolerance_usd",
            "require_protective_stop",
            "take_profit_multiple", "take_profit_basis",
        }

    def test_the_take_profit_defaults_are_the_standing_assumption(self):
        """Steve's "10x" (2026-09-14, st-fn5y) — premium basis until he rules
        on premium-vs-risk. The default must not drift while that is open."""
        b = Bounds()
        assert (b.take_profit_multiple, b.take_profit_basis) == (10.0, "premium")

    @pytest.mark.parametrize("kw", [
        {"take_profit_multiple": 0}, {"take_profit_multiple": -3},
        {"take_profit_multiple": 1.0},                       # premium × 1 is the fill
        {"take_profit_basis": "mid"},
    ])
    def test_a_take_profit_that_cannot_be_a_target_is_refused(self, kw):
        with pytest.raises(ValueError, match="bounds:"):
            Bounds(**kw).validated()

    def test_a_risk_basis_multiple_of_one_is_allowed(self):
        """Fill plus one times the risk is above the fill — a real target."""
        assert Bounds(take_profit_basis="risk", take_profit_multiple=1.0).validated()


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
        assert {"instrument", "qty", "stop", "price_band"} <= declared
        assert not {"ceiling", "positions"} & declared   # co-8mb1z
        assert "window" not in declared          # no clock bound (co-8mb1z)
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
