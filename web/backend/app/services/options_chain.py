"""Options chain service — provides strike/expiration grid with greeks."""

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
from scipy.stats import norm

from app.config import settings
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


def _black_scholes_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
) -> dict[str, float]:
    """Calculate Black-Scholes greeks for a single option."""
    if T <= 0 or sigma <= 0:
        return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "price": 0}

    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "CALL":
        delta = float(norm.cdf(d1))
        price = float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
    else:
        delta = float(norm.cdf(d1) - 1)
        price = float(K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))

    gamma = float(norm.pdf(d1) / (S * sigma * math.sqrt(T)))
    theta = float(
        -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
        - r * K * math.exp(-r * T) * norm.cdf(d2 if option_type == "CALL" else -d2)
    ) / 365.0
    vega = float(S * norm.pdf(d1) * math.sqrt(T)) / 100.0

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
        "price": round(price, 2),
    }


class OptionsChainService:
    """Builds options chain grid: strikes × expirations with greeks, bid/ask, volume/OI."""

    def __init__(self) -> None:
        self._risk_free_rate = 0.05
        self._default_iv = 0.18

    async def get_chain(
        self,
        underlying: str = "SPX",
        expiration: Optional[str] = None,
        strike_range: int = 50,
    ) -> dict[str, Any]:
        """Get options chain for a given underlying and expiration."""
        context = await market_data_service.get_market_context()
        spot = context.get("spx_price", 5800.0) or 5800.0
        vix = context.get("vix", 18.0) or 18.0
        iv = vix / 100.0

        if expiration:
            exp_date = datetime.fromisoformat(expiration).replace(tzinfo=timezone.utc)
        else:
            # Default to next expiration (0DTE)
            now = datetime.now(timezone.utc)
            exp_date = now.replace(hour=20, minute=0, second=0, microsecond=0)
            if now > exp_date:
                exp_date += timedelta(days=1)

        dte = max((exp_date - datetime.now(timezone.utc)).total_seconds() / 86400.0, 0.001)

        center_strike = round(spot / 5) * 5
        strikes = list(
            range(center_strike - strike_range, center_strike + strike_range + 1, 5)
        )

        chain: list[dict[str, Any]] = []
        for strike in strikes:
            call_greeks = _black_scholes_greeks(
                spot, strike, dte / 365.0, self._risk_free_rate, iv, "CALL"
            )
            put_greeks = _black_scholes_greeks(
                spot, strike, dte / 365.0, self._risk_free_rate, iv, "PUT"
            )

            spread = max(0.05, call_greeks["price"] * 0.02)
            call_bid = round(max(0, call_greeks["price"] - spread / 2), 2)
            call_ask = round(call_greeks["price"] + spread / 2, 2)
            put_bid = round(max(0, put_greeks["price"] - spread / 2), 2)
            put_ask = round(put_greeks["price"] + spread / 2, 2)

            # Simulated volume/OI — heavier near ATM
            dist = abs(strike - spot)
            vol_factor = max(0.1, 1.0 - dist / 200.0)
            call_volume = int(np.random.poisson(500 * vol_factor))
            put_volume = int(np.random.poisson(500 * vol_factor))
            call_oi = int(np.random.poisson(5000 * vol_factor))
            put_oi = int(np.random.poisson(5000 * vol_factor))

            chain.append(
                {
                    "strike": strike,
                    "call": {
                        "bid": call_bid,
                        "ask": call_ask,
                        "last": round((call_bid + call_ask) / 2, 2),
                        "volume": call_volume,
                        "open_interest": call_oi,
                        "iv": round(iv + np.random.normal(0, 0.005), 4),
                        **call_greeks,
                    },
                    "put": {
                        "bid": put_bid,
                        "ask": put_ask,
                        "last": round((put_bid + put_ask) / 2, 2),
                        "volume": put_volume,
                        "open_interest": put_oi,
                        "iv": round(iv + np.random.normal(0, 0.005), 4),
                        **put_greeks,
                    },
                }
            )

        return {
            "underlying": underlying,
            "spot": spot,
            "expiration": exp_date.isoformat(),
            "dte": round(dte, 2),
            "chain": chain,
        }

    async def get_expirations(self, underlying: str = "SPX") -> list[dict[str, Any]]:
        """Return available expirations."""
        now = datetime.now(timezone.utc)
        expirations = []
        for i in range(30):
            exp = now + timedelta(days=i)
            if exp.weekday() < 5:  # SPX has daily expirations on weekdays
                dte = i if i > 0 else 0
                expirations.append(
                    {
                        "date": exp.strftime("%Y-%m-%d"),
                        "dte": dte,
                        "label": f"{dte}DTE" if dte <= 7 else exp.strftime("%b %d"),
                    }
                )
        return expirations


options_chain_service = OptionsChainService()
