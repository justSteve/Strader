"""
Boundary layer: Schwab API responses -> typed market entities.

Timezone normalization happens at this boundary. Inputs are raw dicts
from the Schwab client; outputs are typed entities with US/Central
datetimes.
"""
from __future__ import annotations
from datetime import date, datetime
from zoneinfo import ZoneInfo

from market.entities.chain import Chain, strike_key
from market.entities.instrument import Contract

CENTRAL = ZoneInfo("America/Chicago")


def chain_from_schwab(data: dict, expiry: date) -> Chain:
    """Normalize a Schwab get_option_chain() response to a typed Chain.

    Only processes the single expiry matching the `expiry` argument.
    Schwab keys expiry maps as "YYYY-MM-DD:DTE" (e.g. "2026-05-17:0").
    """
    underlying = data.get("symbol", "")
    underlying_price = float(data.get("underlyingPrice", 0.0))
    expiry_prefix = expiry.isoformat()

    calls: dict[int, Contract] = {}
    for exp_key, strikes in data.get("callExpDateMap", {}).items():
        if not exp_key.startswith(expiry_prefix):
            continue
        for strike_str, contracts in strikes.items():
            if not contracts:
                continue
            key = strike_key(float(strike_str))
            calls[key] = _contract_from_schwab(contracts[0], underlying, "CALL")

    puts: dict[int, Contract] = {}
    for exp_key, strikes in data.get("putExpDateMap", {}).items():
        if not exp_key.startswith(expiry_prefix):
            continue
        for strike_str, contracts in strikes.items():
            if not contracts:
                continue
            key = strike_key(float(strike_str))
            puts[key] = _contract_from_schwab(contracts[0], underlying, "PUT")

    return Chain(
        underlying=underlying,
        expiry=expiry,
        calls=calls,
        puts=puts,
        underlying_price=underlying_price,
    )


def _contract_from_schwab(raw: dict, underlying: str, side: str) -> Contract:
    return Contract(
        symbol=raw.get("symbol", ""),
        underlying=underlying,
        strike=float(raw.get("strikePrice", 0.0)),
        expiry=_parse_expiry(raw.get("expirationDate", "")),
        contract_type=side,
        bid=float(raw.get("bid", 0.0)),
        ask=float(raw.get("ask", 0.0)),
        last=float(raw.get("last", 0.0)),
        volume=int(raw.get("totalVolume", 0)),
        open_interest=int(raw.get("openInterest", 0)),
        delta=float(raw.get("delta", 0.0)),
        gamma=float(raw.get("gamma", 0.0)),
        theta=float(raw.get("theta", 0.0)),
        vega=float(raw.get("vega", 0.0)),
        implied_volatility=float(raw.get("volatility", 0.0)),
    )


def _parse_expiry(expiration_date: str) -> date:
    if not expiration_date:
        return date.today()
    return datetime.fromisoformat(expiration_date).date()
