import json
from datetime import date
from pathlib import Path

import pytest

from market.entities.gex_profile import GexProfile
from market.ingest import chain_from_schwab
from market.indicators.gex_calc import compute_gex


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "schwab_chain_spx.json"


def _chain():
    return chain_from_schwab(json.loads(FIXTURE.read_text()), expiry=date(2026, 5, 17))


def test_returns_gex_profile():
    profile = compute_gex(_chain())
    assert isinstance(profile, GexProfile)


def test_spot_defaults_to_chain_underlying_price():
    chain = _chain()
    profile = compute_gex(chain)
    assert profile.spot == chain.underlying_price


def test_spot_override():
    profile = compute_gex(_chain(), spot=5900.0)
    assert profile.spot == 5900.0


def test_by_strike_contains_all_strikes():
    chain = _chain()
    profile = compute_gex(chain)
    # Fixture has 5 strikes
    assert len(profile.by_strike) == 5
    expected_strikes = {5790.0, 5800.0, 5810.0, 5820.0, 5830.0}
    assert set(profile.by_strike.keys()) == expected_strikes


def test_strike_5800_hand_calculation():
    """Verify a single strike's contribution against hand math.

    From fixture: call_5800 gamma=0.021 OI=4521, put_5800 gamma=0.021 OI=3600.
    spot = 5820.5, spot² = 33_878_220.25, contract multiplier = 100.
    """
    chain = _chain()
    profile = compute_gex(chain)

    spot_sq = chain.underlying_price ** 2
    expected_call_5800 = 0.021 * 4521 * 100 * spot_sq
    expected_put_5800 = -(0.021 * 3600 * 100 * spot_sq)
    expected_strike_5800 = expected_call_5800 + expected_put_5800

    assert profile.by_strike[5800.0] == pytest.approx(expected_strike_5800, rel=1e-9)


def test_net_gex_equals_calls_plus_puts():
    profile = compute_gex(_chain())
    assert profile.net_gex == pytest.approx(profile.net_gex_calls + profile.net_gex_puts)


def test_net_gex_calls_is_positive_when_calls_have_positive_gamma():
    profile = compute_gex(_chain())
    # Calls in fixture have positive gamma and positive OI → positive contribution.
    assert profile.net_gex_calls > 0


def test_net_gex_puts_is_negative_with_convention():
    profile = compute_gex(_chain())
    # Per squeezemetrics convention, puts subtract from net GEX.
    assert profile.net_gex_puts < 0


def test_gex_scales_with_spot_squared():
    chain = _chain()
    p1 = compute_gex(chain, spot=100.0)
    p2 = compute_gex(chain, spot=200.0)
    # Doubling spot → net_gex scales by 4 (spot² factor).
    assert p2.net_gex == pytest.approx(p1.net_gex * 4.0, rel=1e-9)


def test_empty_chain_returns_zero_gex():
    from market.entities.chain import Chain

    empty = Chain(
        underlying="$SPX",
        expiry=date(2026, 5, 17),
        calls={},
        puts={},
        underlying_price=5820.5,
    )
    profile = compute_gex(empty)
    assert profile.net_gex == 0.0
    assert profile.net_gex_calls == 0.0
    assert profile.net_gex_puts == 0.0
    assert profile.by_strike == {}
