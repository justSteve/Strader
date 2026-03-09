"""Options chain service — fetches and caches SPX option chains."""

import logging
from datetime import datetime, date, timezone

from ..core.redis import redis_client
from ..schemas.options import OptionQuote, OptionsChainResponse
from .schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

CACHE_TTL = 3  # seconds


async def get_options_chain(
    symbol: str = "$SPX",
    expiration: date | None = None,
    strike_count: int = 20,
) -> OptionsChainResponse:
    """Fetch options chain for symbol."""
    cache_key = f"chain:{symbol}:{expiration or 'all'}:{strike_count}"
    cached = await redis_client.get(cache_key)
    if cached:
        return OptionsChainResponse.model_validate_json(cached)

    client = get_schwab_client()
    now = datetime.now(timezone.utc)

    if client is None:
        return _demo_chain(symbol, now)

    try:
        kwargs = {
            "symbol": symbol,
            "contract_type": schwab.Client.Options.ContractType.ALL,
            "strike_count": strike_count,
            "include_underlying_quote": True,
        }
        if expiration:
            kwargs["from_date"] = expiration
            kwargs["to_date"] = expiration

        import schwab
        resp = client.get_option_chain(**kwargs)
        data = resp.json()

        underlying_price = data.get("underlyingPrice", 0)
        calls = _parse_options(data.get("callExpDateMap", {}), "CALL")
        puts = _parse_options(data.get("putExpDateMap", {}), "PUT")

        expirations = sorted(set(
            str(c.expiration) for c in calls
        ))
        strikes = sorted(set(c.strike for c in calls))

        chain = OptionsChainResponse(
            symbol=symbol,
            underlying_price=underlying_price,
            expirations=expirations,
            strikes=strikes,
            calls=calls,
            puts=puts,
            updated_at=now,
        )

        await redis_client.setex(cache_key, CACHE_TTL, chain.model_dump_json())
        return chain

    except Exception:
        logger.exception("Failed to fetch options chain")
        return _demo_chain(symbol, now)


def _parse_options(exp_date_map: dict, option_type: str) -> list[OptionQuote]:
    """Parse Schwab option chain response into OptionQuote list."""
    options = []
    for exp_date, strikes in exp_date_map.items():
        exp = exp_date.split(":")[0]
        for strike_str, contracts in strikes.items():
            for contract in contracts:
                options.append(OptionQuote(
                    symbol=contract.get("symbol", ""),
                    strike=float(strike_str),
                    expiration=date.fromisoformat(exp),
                    option_type=option_type,
                    bid=contract.get("bid", 0),
                    ask=contract.get("ask", 0),
                    last=contract.get("last", 0),
                    volume=contract.get("totalVolume", 0),
                    open_interest=contract.get("openInterest", 0),
                    delta=contract.get("delta"),
                    gamma=contract.get("gamma"),
                    theta=contract.get("theta"),
                    vega=contract.get("vega"),
                    iv=contract.get("volatility"),
                    in_the_money=contract.get("inTheMoney", False),
                ))
    return options


def _demo_chain(symbol: str, now: datetime) -> OptionsChainResponse:
    """Generate demo options chain data."""
    from datetime import timedelta
    import math

    base_price = 5850.0
    today = date.today()
    expirations = [today, today + timedelta(days=1), today + timedelta(days=7)]
    strikes = [base_price + (i - 10) * 5 for i in range(21)]

    calls = []
    puts = []

    for exp in expirations:
        dte = max((exp - today).days, 0.25)
        for strike in strikes:
            moneyness = (base_price - strike) / base_price
            iv = 0.16 + abs(moneyness) * 0.5  # Simple skew

            # Simplified BS-like pricing
            time_value = base_price * iv * math.sqrt(dte / 365) * 0.4
            call_intrinsic = max(base_price - strike, 0)
            put_intrinsic = max(strike - base_price, 0)

            call_price = round(call_intrinsic + time_value, 2)
            put_price = round(put_intrinsic + time_value, 2)

            # Approximate greeks
            call_delta = round(0.5 + moneyness * 3, 4)
            call_delta = max(-1, min(1, call_delta))

            calls.append(OptionQuote(
                symbol=f"SPX {exp} C{strike}",
                strike=strike,
                expiration=exp,
                option_type="CALL",
                bid=round(call_price * 0.97, 2),
                ask=round(call_price * 1.03, 2),
                last=call_price,
                volume=int(1000 * (1 - abs(moneyness) * 5)),
                open_interest=int(5000 * (1 - abs(moneyness) * 3)),
                delta=call_delta,
                gamma=round(0.001 / (1 + abs(moneyness) * 20), 6),
                theta=round(-time_value / max(dte, 0.25) * 0.5, 4),
                vega=round(base_price * math.sqrt(dte / 365) * 0.004, 4),
                iv=round(iv * 100, 2),
                in_the_money=strike < base_price,
            ))

            puts.append(OptionQuote(
                symbol=f"SPX {exp} P{strike}",
                strike=strike,
                expiration=exp,
                option_type="PUT",
                bid=round(put_price * 0.97, 2),
                ask=round(put_price * 1.03, 2),
                last=put_price,
                volume=int(800 * (1 - abs(moneyness) * 5)),
                open_interest=int(4000 * (1 - abs(moneyness) * 3)),
                delta=round(call_delta - 1, 4),
                gamma=round(0.001 / (1 + abs(moneyness) * 20), 6),
                theta=round(-time_value / max(dte, 0.25) * 0.5, 4),
                vega=round(base_price * math.sqrt(dte / 365) * 0.004, 4),
                iv=round(iv * 100, 2),
                in_the_money=strike > base_price,
            ))

    return OptionsChainResponse(
        symbol=symbol,
        underlying_price=base_price,
        expirations=[str(e) for e in expirations],
        strikes=strikes,
        calls=calls,
        puts=puts,
        updated_at=now,
    )
