"""Tests for strader/execution/compose.py — FD0 strike pick and budget engine.

Bead: Cut And Await (st-apzt).

These are unit tests over pure functions. Nothing here opens a socket, reads a
credential, or transmits an order — the module cannot, by construction.

Note on fixtures: ``schwab_chain_spx_0dte.json`` is SYNTHETIC. The build plan
asked for a fresh Friday chain snapshot and the markets were shut when this was
written, so no test here may be read as evidence about live pricing. What they
do prove is the arithmetic, the unit discipline, and the refusals.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from strader.execution.compose import (
    Budget, Contract, CannotFund, NoStrikeInBand,
    compose, derive, noise_floor_spx, order_string, parse_chain, pick_strike,
    CONTRACT_MULTIPLIER,
)

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "market" / "fixtures"


def _chain(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _contract(delta=-0.30, bid=1.45, ask=1.60, strike=7415.0) -> Contract:
    return Contract(symbol="SPXW  260803P07415000", strike=strike, bid_pts=bid,
                    ask_pts=ask, delta=delta, expiration="2026-08-03", dte=0)


# ---------------------------------------------------------------- budget ---

def test_budget_starts_at_the_ceiling():
    b = Budget()
    assert (b.total_usd, b.attempts, b.remaining_usd, b.attempts_left) == (100.0, 2, 100.0, 2)


def test_debit_books_a_loss_and_consumes_an_attempt():
    b = Budget().debit(38.0)
    assert b.remaining_usd == 62.0
    assert b.attempts_left == 1


def test_debit_is_a_value_not_a_mutation():
    original = Budget()
    original.debit(38.0)
    assert original.remaining_usd == 100.0     # untouched


def test_a_winning_attempt_consumes_an_attempt_but_not_budget():
    b = Budget().debit(-25.0)
    assert b.remaining_usd == 100.0
    assert b.attempts_left == 1


# ----------------------------------------------------------------- chain ---

def test_parse_chain_takes_the_front_expiry_by_default():
    contracts = parse_chain(_chain("schwab_chain_spx_0dte.json"))
    assert {c.expiration for c in contracts} == {"2026-08-03"}


def test_parse_chain_can_select_an_expiry():
    contracts = parse_chain(_chain("schwab_chain_spx_0dte.json"), expiration="2026-08-04")
    assert [c.strike for c in contracts] == [7415.0]
    assert contracts[0].dte == 1


def test_parse_chain_drops_unpriceable_lines_rather_than_defaulting_them():
    # 7412 has ask=0 — a strike we cannot price is a strike we must not pick.
    contracts = parse_chain(_chain("schwab_chain_spx_0dte.json"))
    assert 7412.0 not in {c.strike for c in contracts}


def test_parse_chain_of_an_unknown_expiry_is_empty_not_an_exception():
    assert parse_chain(_chain("schwab_chain_spx_0dte.json"), expiration="2026-12-25") == []


def test_parse_chain_survives_an_empty_payload():
    assert parse_chain({}) == []


def test_put_deltas_stay_signed_so_a_misparsed_chain_is_visible():
    contracts = parse_chain(_chain("schwab_chain_spx_0dte.json"))
    assert all(c.delta < 0 for c in contracts)
    assert all(c.abs_delta > 0 for c in contracts)


# ------------------------------------------------------------ strike pick ---

def test_pick_strike_takes_the_delta_nearest_target_inside_the_band():
    contracts = parse_chain(_chain("schwab_chain_spx_0dte.json"))
    assert pick_strike(contracts).strike == 7415.0     # |delta| 0.30


def test_pick_strike_refuses_rather_than_reaching_outside_the_band():
    # The recorded fixture's tightest put is 0.38 delta. Reaching for it would
    # roughly double the dollar risk per SPX point and break the derivation.
    contracts = parse_chain(_chain("schwab_chain_spx.json"))
    with pytest.raises(NoStrikeInBand) as exc:
        pick_strike(contracts)
    assert "0.38" in str(exc.value)


def test_pick_strike_breaks_ties_toward_the_tighter_spread():
    wide = _contract(delta=-0.32, bid=1.40, ask=1.80, strike=7418.0)
    tight = _contract(delta=-0.28, bid=1.45, ask=1.60, strike=7414.0)
    assert pick_strike([wide, tight]).strike == 7414.0


# ---------------------------------------------------------- budget engine ---

def test_derive_matches_the_designs_worked_illustration():
    # Design §budget engine: ~0.30 delta, ~$15 spread, $3 fees
    #   attempt 1 = $50 − $18 = $32 premium risk
    #             = 0.32 pts of premium
    #             ≈ 1.1 SPX pts of stop
    c = _contract(delta=-0.30, bid=1.45, ask=1.60)      # 0.15 pts = $15
    d = derive(Budget(), c, recent_minute_ranges_spx=[0.5] * 15)

    assert d.friction_usd == pytest.approx(18.0)
    assert d.attempt_risk_usd == pytest.approx(32.0)
    assert d.stop_premium_pts == pytest.approx(0.32)
    assert d.stop_distance_spx == pytest.approx(1.0667, abs=1e-3)


def test_the_second_attempt_re_derives_from_what_is_actually_left():
    c = _contract()
    after_loss = Budget().debit(32.0)                    # $68 left, 1 attempt
    d = derive(after_loss, c, recent_minute_ranges_spx=[0.5] * 15)
    assert d.attempt_risk_usd == pytest.approx(68.0 - 18.0)
    assert d.stop_distance_spx > 1.0667                  # more room, not less


def test_a_wider_spread_buys_a_tighter_stop():
    tight = derive(Budget(), _contract(bid=1.50, ask=1.60), recent_minute_ranges_spx=[0.5])
    wide = derive(Budget(), _contract(bid=1.35, ask=1.75), recent_minute_ranges_spx=[0.5])
    assert wide.stop_distance_spx < tight.stop_distance_spx


def test_a_lower_delta_buys_a_wider_stop_in_spx_points():
    # Same dollars of premium risk travels further in SPX terms at low delta.
    lo = derive(Budget(), _contract(delta=-0.25), recent_minute_ranges_spx=[0.5])
    hi = derive(Budget(), _contract(delta=-0.35), recent_minute_ranges_spx=[0.5])
    assert lo.stop_distance_spx > hi.stop_distance_spx


def test_refuses_to_fund_when_friction_eats_the_slice():
    c = _contract(bid=1.00, ask=1.60)                    # $60 spread
    with pytest.raises(CannotFund) as exc:
        derive(Budget(spent_usd=20.0), c)                # $80 / 2 = $40 slice
    msg = str(exc.value)
    assert "$40.00 per attempt" in msg and "$63.00" in msg   # arithmetic printed


def test_refuses_when_the_attempts_are_used_up():
    with pytest.raises(CannotFund) as exc:
        derive(Budget(attempts_used=2), _contract())
    assert "no attempts left" in str(exc.value)


def test_premium_to_dollars_uses_the_contract_multiplier():
    d = derive(Budget(), _contract(), recent_minute_ranges_spx=[0.5])
    assert d.stop_premium_pts * CONTRACT_MULTIPLIER == pytest.approx(d.attempt_risk_usd)


# ------------------------------------------------------------ noise floor ---

def test_noise_floor_takes_the_larger_of_spread_and_tape_fidget():
    # spread term = 0.15 / 0.30 = 0.5 SPX pts; tape median = 1.4 -> tape wins
    assert noise_floor_spx(0.15, 0.30, [1.2, 1.4, 1.6]) == pytest.approx(1.4)
    # tape quiet -> spread term wins
    assert noise_floor_spx(0.15, 0.30, [0.2, 0.3, 0.1]) == pytest.approx(0.5)


def test_noise_floor_without_recent_bars_uses_the_spread_alone_and_warns(caplog):
    with caplog.at_level("WARNING"):
        assert noise_floor_spx(0.15, 0.30) == pytest.approx(0.5)
    assert "no recent 1-min ranges" in caplog.text


def test_noise_floor_refuses_a_zero_delta():
    with pytest.raises(ValueError):
        noise_floor_spx(0.15, 0.0, [0.5])


# -------------------------------------------------------------- rendering ---

def test_order_string_matches_the_validated_spine():
    assert order_string(_contract(), 1.60) == (
        "BUY +1 SPX 100 (Weeklys) 3 AUG 26 7415 PUT @1.60 LMT"
    )


def test_order_string_carries_no_exit_leg():
    # Whether the paste grammar can express an SPX-underlying condition is the
    # open question on Steve's TOS card. Until answered, it is not guessed at.
    s = order_string(_contract(), 1.60)
    assert "SELL" not in s and "SPX >" not in s


# --------------------------------------------------------------- compose ---

def _composed(**kw):
    return compose(_chain("schwab_chain_spx_0dte.json"), 7440.25, Budget(),
                   recent_minute_ranges_spx=[0.4] * 15,
                   now=datetime(2026, 8, 3, 8, 47), **kw)


def test_compose_end_to_end():
    t = _composed()
    assert t.contract.strike == 7415.0
    assert t.limit_pts == 1.60                       # ask, on a nickel
    assert t.stop_trigger_spx == pytest.approx(7440.25 + t.derivation.stop_distance_spx)
    assert t.order_string.endswith("7415 PUT @1.60 LMT")


def test_compose_defaults_to_a_marketable_limit():
    # The engine charges the full spread as friction; bidding mid would
    # understate the risk it just priced.
    assert _composed().limit_pts == 1.60
    assert _composed(limit_mode="mid").limit_pts == pytest.approx(1.55)


def test_a_buy_limit_rounds_up_never_down():
    # 1.45/1.60 mids at 1.525. Banker's rounding would land 1.50 — below the
    # book, i.e. a miss. On a flush entry that costs the trade.
    from strader.execution.compose import _round_limit_up
    assert _round_limit_up(1.525) == 1.55
    assert _round_limit_up(1.60) == 1.60      # already on a tick, unchanged
    assert _round_limit_up(1.51) == 1.55


def test_the_stop_sits_above_spx_because_a_long_put_loses_on_a_rally():
    t = _composed()
    assert t.stop_trigger_spx > t.spx_at_compose


def test_max_loss_stays_inside_the_ceiling():
    t = _composed()
    assert t.max_loss_usd <= Budget().total_usd / Budget().attempts + 1e-9


def test_warns_loudly_when_the_stop_sits_inside_the_noise_floor():
    t = compose(_chain("schwab_chain_spx_0dte.json"), 7440.25, Budget(),
                recent_minute_ranges_spx=[3.0] * 15)     # rowdy tape
    assert any("NOISE FLOOR" in w for w in t.warnings)
    assert t.derivation.inside_noise_floor


def test_a_quiet_tape_produces_no_noise_warning():
    t = _composed()
    assert not any("NOISE FLOOR" in w for w in t.warnings)


def test_missing_tape_context_is_surfaced_not_silently_accepted():
    t = compose(_chain("schwab_chain_spx_0dte.json"), 7440.25, Budget())
    assert any("spread only" in w for w in t.warnings)


def test_template_fields_are_the_two_numbers_to_overwrite():
    f = _composed().template_fields
    assert f["strike"] == 7415.0
    assert f["condition_spx"] == pytest.approx(7441.32, abs=0.01)
    assert f["expiry"] == "3 AUG 26"


def test_the_record_carries_the_whole_derivation_chain():
    rec = _composed().as_record()
    for key in ("budget_remaining_usd", "friction_usd", "attempt_risk_usd",
                "stop_premium_pts", "delta_live", "stop_distance_spx",
                "noise_floor_spx", "inside_noise_floor"):
        assert key in rec["derivation"]
    assert json.dumps(rec)          # journal-serializable


# ------------------------------------------- TOS paste grammar (08-03 research) ---

def test_order_string_is_bare_with_no_stray_whitespace():
    # TOS's paste-from-clipboard breaks on extra spaces or text. This value
    # goes to the clipboard verbatim, so it must carry nothing else.
    s = order_string(_contract(), 1.60)
    assert s == s.strip()
    assert "\n" not in s and "\t" not in s
    assert "  " not in s          # no doubled spaces anywhere


def test_exit_fields_trigger_on_the_cash_index_not_the_option():
    # The stop distance is derived in SPX index points, so the condition must
    # watch the same instrument the arithmetic is denominated in.
    from strader.execution.compose import exit_fields
    f = exit_fields(7441.32)
    assert f["trigger_symbol"] == "SPX"
    assert f["trigger_price"] == 7441.32
    assert f["trigger_direction"] == "at or above"
    assert "MARKET" in f["action"]


def test_exit_fields_stay_a_plain_price_comparison():
    # A saved TOS template is documented to lose a *custom study* condition on
    # reload, keeping only its name. A plain comparison sidesteps that entirely,
    # so nothing here may imply a study or a script.
    from strader.execution.compose import exit_fields
    blob = " ".join(str(v) for v in exit_fields(7441.32).values()).lower()
    for forbidden in ("study", "script", "thinkscript", "plot"):
        assert forbidden not in blob
