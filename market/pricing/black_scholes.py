"""
Black-Scholes-Merton pricing module.

Pure-function closed-form pricing, greeks, and implied volatility solver for
European options. No state, no I/O, no dependencies beyond numpy + stdlib.

Convention:
    spot  S     — underlying spot price
    strike K    — option strike
    T          — time to expiry in years (e.g. 30 DTE = 30/365)
    r          — risk-free rate (continuous)
    sigma  σ   — volatility (annualized, e.g. 0.20 = 20%)
    q          — continuous dividend yield (0.0 for non-dividend)
    opt_type   — "CALL" or "PUT"

Greeks units:
    delta    — per 1.0 unit of spot
    gamma    — per 1.0 unit of spot (so d(delta)/dS)
    theta    — per 1 day (not per year)
    vega     — per 1.0 unit of sigma (divide by 100 for per-1%-vol)
    rho      — per 1.0 unit of rate (divide by 100 for per-1%-rate)
    vanna    — d(delta)/d(sigma) = d(vega)/dS, per 1.0 unit of sigma per 1.0 unit of spot
    charm    — d(delta)/dT, per 1 day of time-to-expiry (equivalently, -d(delta)/dt where t = clock time). Sign convention: positive charm = delta increases with more T (i.e. delta decays toward 0 as expiration nears, typical for OTM)

References: Hull, Options, Futures, and Other Derivatives, Ch. 15.
"""
from __future__ import annotations

from math import erf, exp, log, pi, sqrt
from typing import Literal

OptType = Literal["CALL", "PUT"]

DAYS_PER_YEAR = 365.0


def _phi(opt_type: OptType) -> int:
    if opt_type == "CALL":
        return 1
    if opt_type == "PUT":
        return -1
    raise ValueError(f"opt_type must be 'CALL' or 'PUT', got {opt_type!r}")


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf. Pure stdlib; matches scipy.stats.norm.cdf."""
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return exp(-0.5 * x * x) / sqrt(2.0 * pi)


def _d1_d2(spot: float, strike: float, T: float, r: float, sigma: float,
           q: float = 0.0) -> tuple[float, float]:
    if T <= 0.0 or sigma <= 0.0:
        raise ValueError("T and sigma must be positive")
    sqrt_T = sqrt(T)
    d1 = (log(spot / strike) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


def price(spot: float, strike: float, T: float, r: float, sigma: float,
          opt_type: OptType, q: float = 0.0) -> float:
    """Closed-form Black-Scholes-Merton price.

    Handles expiry boundary (T == 0) by returning intrinsic value.
    """
    if T == 0.0:
        if opt_type == "CALL":
            return max(spot - strike, 0.0)
        if opt_type == "PUT":
            return max(strike - spot, 0.0)
        raise ValueError(f"opt_type must be 'CALL' or 'PUT', got {opt_type!r}")

    phi = _phi(opt_type)
    d1, d2 = _d1_d2(spot, strike, T, r, sigma, q)

    return phi * (
        spot * exp(-q * T) * _norm_cdf(phi * d1)
        - strike * exp(-r * T) * _norm_cdf(phi * d2)
    )


def greeks(spot: float, strike: float, T: float, r: float, sigma: float,
           opt_type: OptType, q: float = 0.0) -> dict[str, float]:
    """Primary greeks (delta/gamma/theta/vega/rho) + second-order (vanna/charm).

    Returns: {'delta', 'gamma', 'theta', 'vega', 'rho', 'vanna', 'charm'}.
    See module docstring for units.
    """
    phi = _phi(opt_type)
    d1, d2 = _d1_d2(spot, strike, T, r, sigma, q)

    pdf_d1 = _norm_pdf(d1)
    disc_q = exp(-q * T)
    disc_r = exp(-r * T)
    sqrt_T = sqrt(T)

    delta = phi * disc_q * _norm_cdf(phi * d1)
    gamma = disc_q * pdf_d1 / (spot * sigma * sqrt_T)
    vega = spot * disc_q * pdf_d1 * sqrt_T

    # Theta per year, then convert to per-day.
    theta_annual = (
        -spot * disc_q * pdf_d1 * sigma / (2.0 * sqrt_T)
        - phi * r * strike * disc_r * _norm_cdf(phi * d2)
        + phi * q * spot * disc_q * _norm_cdf(phi * d1)
    )
    theta = theta_annual / DAYS_PER_YEAR

    rho = phi * strike * T * disc_r * _norm_cdf(phi * d2)

    # Second-order. Vanna is sign-independent (same for call and put); charm
    # has a sign flip via phi on the q-dividend term.
    # Vanna = d(delta)/d(sigma) = -e^(-qT) · φ(d1) · d2 / σ.
    vanna = -disc_q * pdf_d1 * d2 / sigma

    # Charm = d(delta)/dT — per year, then per-day. For an OTM call charm > 0
    # (longer T → larger delta, equivalently delta decays toward 0 as T → 0).
    charm_annual = (
        -phi * q * disc_q * _norm_cdf(phi * d1)
        + disc_q * pdf_d1
        * (2.0 * (r - q) * T - d2 * sigma * sqrt_T) / (2.0 * T * sigma * sqrt_T)
    )
    charm = charm_annual / DAYS_PER_YEAR

    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "rho": rho,
        "vanna": vanna,
        "charm": charm,
    }


def implied_vol(market_price: float, spot: float, strike: float, T: float,
                r: float, opt_type: OptType, q: float = 0.0,
                tol: float = 1e-7, max_iter: int = 100,
                sigma_init: float = 0.20) -> float:
    """Solve for sigma such that BS price ≈ market_price.

    Newton-Raphson on the price-vs-sigma curve (vega is the derivative);
    falls back to bisection if Newton goes off-rails (vega tiny, sigma drifts
    outside a reasonable range).

    Raises ValueError if market_price violates no-arbitrage bounds
    (i.e. lies outside [intrinsic, spot] for calls or [intrinsic, strike] for puts).
    """
    if T <= 0.0:
        raise ValueError("T must be positive")
    if market_price <= 0.0:
        raise ValueError(f"market_price must be positive, got {market_price}")

    # No-arbitrage bounds.
    intrinsic = max((spot * exp(-q * T) - strike * exp(-r * T))
                    if opt_type == "CALL"
                    else (strike * exp(-r * T) - spot * exp(-q * T)),
                    0.0)
    upper = spot * exp(-q * T) if opt_type == "CALL" else strike * exp(-r * T)
    if market_price < intrinsic - tol:
        raise ValueError(
            f"market_price {market_price} below intrinsic {intrinsic}")
    if market_price > upper + tol:
        raise ValueError(
            f"market_price {market_price} above no-arbitrage upper {upper}")

    # Newton-Raphson.
    sigma = sigma_init
    for _ in range(max_iter):
        p = price(spot, strike, T, r, sigma, opt_type, q)
        diff = p - market_price
        if abs(diff) < tol:
            return sigma
        v = greeks(spot, strike, T, r, sigma, opt_type, q)["vega"]
        if v < 1e-10:
            break  # vega vanished; switch to bisection
        sigma -= diff / v
        if sigma <= 0.0 or sigma > 5.0:
            break  # diverged; switch to bisection

    # Bisection fallback.
    lo, hi = 1e-6, 5.0
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        p = price(spot, strike, T, r, mid, opt_type, q)
        if abs(p - market_price) < tol:
            return mid
        if p < market_price:
            lo = mid
        else:
            hi = mid

    raise RuntimeError(
        f"implied_vol failed to converge after {max_iter} Newton + bisection steps"
    )
