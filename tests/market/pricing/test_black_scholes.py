"""
Tests for the Black-Scholes pricing module.

Reference values from Hull, Options, Futures, and Other Derivatives.
"""
from __future__ import annotations

from math import exp

import pytest

from market.pricing.black_scholes import greeks, implied_vol, price


# ─── Reference cases ────────────────────────────────────────────────────────

def test_hull_atm_call():
    """S=100, K=100, r=0.05, σ=0.20, T=1, q=0 → C ≈ 10.4506."""
    c = price(spot=100.0, strike=100.0, T=1.0, r=0.05, sigma=0.20, opt_type="CALL")
    assert c == pytest.approx(10.45058, abs=1e-4)


def test_hull_atm_put():
    """Same as above → P ≈ 5.5735."""
    p = price(spot=100.0, strike=100.0, T=1.0, r=0.05, sigma=0.20, opt_type="PUT")
    assert p == pytest.approx(5.57353, abs=1e-4)


def test_hull_with_dividend_yield():
    """S=100, K=100, r=0.05, q=0.03, σ=0.20, T=1 → C ≈ 8.6525.

    Closed-form check: d1 = (ln 1 + (0.05 - 0.03 + 0.02)·1)/0.20 = 0.20;
    d2 = 0.00. C = 100·e^-0.03·N(0.20) - 100·e^-0.05·N(0.00).
    """
    c = price(spot=100.0, strike=100.0, T=1.0, r=0.05, sigma=0.20,
              opt_type="CALL", q=0.03)
    assert c == pytest.approx(8.6525, abs=1e-3)


# ─── Put-call parity ────────────────────────────────────────────────────────

def test_put_call_parity():
    """C - P = S·e^(-qT) - K·e^(-rT)."""
    S, K, T, r, sigma, q = 5820.5, 5800.0, 30 / 365, 0.045, 0.18, 0.015
    c = price(S, K, T, r, sigma, "CALL", q)
    p = price(S, K, T, r, sigma, "PUT", q)
    expected = S * exp(-q * T) - K * exp(-r * T)
    assert (c - p) == pytest.approx(expected, abs=1e-9)


def test_put_call_parity_zero_dividend():
    S, K, T, r, sigma = 100.0, 105.0, 0.5, 0.05, 0.25
    c = price(S, K, T, r, sigma, "CALL")
    p = price(S, K, T, r, sigma, "PUT")
    expected = S - K * exp(-r * T)
    assert (c - p) == pytest.approx(expected, abs=1e-9)


# ─── Greeks ─────────────────────────────────────────────────────────────────

def test_call_delta_is_positive_and_bounded():
    g = greeks(100.0, 100.0, 1.0, 0.05, 0.20, "CALL")
    assert 0.0 < g["delta"] < 1.0


def test_put_delta_is_negative_and_bounded():
    g = greeks(100.0, 100.0, 1.0, 0.05, 0.20, "PUT")
    assert -1.0 < g["delta"] < 0.0


def test_gamma_is_identical_call_vs_put():
    """Gamma is sign-independent — calls and puts at same strike share gamma."""
    args = dict(spot=100.0, strike=100.0, T=0.5, r=0.05, sigma=0.20)
    g_call = greeks(**args, opt_type="CALL")
    g_put = greeks(**args, opt_type="PUT")
    assert g_call["gamma"] == pytest.approx(g_put["gamma"], abs=1e-12)


def test_vega_is_identical_call_vs_put():
    """Vega is sign-independent — calls and puts at same strike share vega."""
    args = dict(spot=100.0, strike=100.0, T=0.5, r=0.05, sigma=0.20)
    g_call = greeks(**args, opt_type="CALL")
    g_put = greeks(**args, opt_type="PUT")
    assert g_call["vega"] == pytest.approx(g_put["vega"], abs=1e-12)


def test_call_theta_is_negative_otm():
    """A call far OTM has negative theta (time decay)."""
    g = greeks(100.0, 120.0, 0.25, 0.05, 0.20, "CALL")
    assert g["theta"] < 0


def test_atm_gamma_hull_value():
    """Hull Ch.19: S=K=49, r=0.05, σ=0.20, T=20/52 → gamma ≈ 0.066."""
    g = greeks(49.0, 50.0, 20 / 52, 0.05, 0.20, "CALL")
    assert g["gamma"] == pytest.approx(0.0656, abs=5e-4)


# ─── Implied volatility ─────────────────────────────────────────────────────

def test_implied_vol_round_trip():
    """price(σ_in) → market; implied_vol(market) → σ_out ≈ σ_in."""
    sigma_in = 0.25
    market = price(100.0, 100.0, 1.0, 0.05, sigma_in, "CALL")
    sigma_out = implied_vol(market, 100.0, 100.0, 1.0, 0.05, "CALL")
    assert sigma_out == pytest.approx(sigma_in, abs=1e-6)


def test_implied_vol_round_trip_put():
    sigma_in = 0.30
    market = price(100.0, 95.0, 0.5, 0.04, sigma_in, "PUT", q=0.02)
    sigma_out = implied_vol(market, 100.0, 95.0, 0.5, 0.04, "PUT", q=0.02)
    assert sigma_out == pytest.approx(sigma_in, abs=1e-6)


def test_implied_vol_rejects_below_intrinsic():
    """A call priced below intrinsic value violates no-arbitrage."""
    with pytest.raises(ValueError, match="below intrinsic"):
        implied_vol(market_price=0.01, spot=110.0, strike=100.0,
                    T=1.0, r=0.05, opt_type="CALL")


def test_implied_vol_rejects_above_upper_bound():
    """A call priced above the underlying (in PV terms) violates no-arbitrage."""
    with pytest.raises(ValueError, match="above no-arbitrage upper"):
        implied_vol(market_price=200.0, spot=100.0, strike=50.0,
                    T=1.0, r=0.05, opt_type="CALL")


def test_implied_vol_converges_far_otm():
    """IV solver should still converge for a far-OTM call with realistic σ."""
    sigma_in = 0.35
    market = price(100.0, 130.0, 0.1, 0.05, sigma_in, "CALL")
    sigma_out = implied_vol(market, 100.0, 130.0, 0.1, 0.05, "CALL")
    assert sigma_out == pytest.approx(sigma_in, abs=1e-5)


# ─── Expiry boundary ────────────────────────────────────────────────────────

def test_price_at_expiry_is_intrinsic_call():
    assert price(110.0, 100.0, 0.0, 0.05, 0.20, "CALL") == pytest.approx(10.0)
    assert price(90.0, 100.0, 0.0, 0.05, 0.20, "CALL") == pytest.approx(0.0)


def test_price_at_expiry_is_intrinsic_put():
    assert price(90.0, 100.0, 0.0, 0.05, 0.20, "PUT") == pytest.approx(10.0)
    assert price(110.0, 100.0, 0.0, 0.05, 0.20, "PUT") == pytest.approx(0.0)


# ─── Symmetry: ATM call delta at zero rate/dividend is ~0.5 ────────────────

def test_atm_call_delta_near_half_at_zero_rate():
    """When r = q = 0, an ATM European call has delta ≈ 0.5 (slight upward
    drift from σ²/2 term in d1). Sanity-check our greek wiring is sane."""
    g = greeks(100.0, 100.0, 0.25, 0.0, 0.20, "CALL", q=0.0)
    # d1 = (0 + 0·0.5·σ²·T)/(σ√T) = σ√T/2; N(σ√T/2) is slightly > 0.5
    assert 0.50 < g["delta"] < 0.55
