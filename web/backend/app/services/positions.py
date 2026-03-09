"""Account and position service."""

import logging
from datetime import datetime, timezone

from ..core.redis import redis_client
from ..schemas.options import PositionResponse, PortfolioGreeks
from .schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

CACHE_TTL = 5


async def get_positions() -> list[PositionResponse]:
    """Get current positions from Schwab account."""
    cached = await redis_client.get("positions:current")
    if cached:
        import json
        return [PositionResponse.model_validate(p) for p in json.loads(cached)]

    client = get_schwab_client()
    if client is None:
        return _demo_positions()

    try:
        resp = client.get_accounts(fields=[client.Account.Fields.POSITIONS])
        accounts = resp.json()

        positions = []
        for account in accounts:
            acct = account.get("securitiesAccount", {})
            account_hash = acct.get("accountNumber", "")

            for pos in acct.get("positions", []):
                instrument = pos.get("instrument", {})
                if instrument.get("underlyingSymbol") != "$SPX" and instrument.get("symbol") != "$SPX":
                    continue

                positions.append(PositionResponse(
                    symbol=instrument.get("underlyingSymbol", instrument.get("symbol", "")),
                    option_symbol=instrument.get("symbol") if instrument.get("assetType") == "OPTION" else None,
                    quantity=int(pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)),
                    avg_price=pos.get("averagePrice", 0),
                    current_price=pos.get("marketValue", 0) / max(abs(pos.get("longQuantity", 1) - pos.get("shortQuantity", 0)), 1),
                    market_value=pos.get("marketValue", 0),
                    pnl_day=pos.get("currentDayProfitLoss", 0),
                    pnl_total=pos.get("marketValue", 0) - pos.get("averagePrice", 0) * abs(pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)),
                ))

        import json
        await redis_client.setex("positions:current", CACHE_TTL,
                                 json.dumps([p.model_dump() for p in positions]))
        return positions

    except Exception:
        logger.exception("Failed to fetch positions")
        return _demo_positions()


async def get_portfolio_greeks() -> PortfolioGreeks:
    """Calculate aggregate portfolio greeks."""
    positions = await get_positions()

    total_delta = sum(p.delta or 0 for p in positions)
    total_gamma = sum(p.gamma or 0 for p in positions)
    total_theta = sum(p.theta or 0 for p in positions)
    total_vega = sum(p.vega or 0 for p in positions)
    net_premium = sum(p.market_value or 0 for p in positions)

    return PortfolioGreeks(
        total_delta=round(total_delta, 4),
        total_gamma=round(total_gamma, 6),
        total_theta=round(total_theta, 4),
        total_vega=round(total_vega, 4),
        net_premium=round(net_premium, 2),
    )


def _demo_positions() -> list[PositionResponse]:
    """Demo position data."""
    return [
        PositionResponse(
            symbol="$SPX",
            option_symbol="SPX 240309 C5850",
            quantity=-2,
            avg_price=8.50,
            current_price=6.20,
            market_value=-1240.00,
            pnl_day=180.00,
            pnl_total=460.00,
            delta=-0.35,
            gamma=-0.002,
            theta=4.50,
            vega=-1.20,
        ),
        PositionResponse(
            symbol="$SPX",
            option_symbol="SPX 240309 C5855",
            quantity=2,
            avg_price=5.80,
            current_price=4.10,
            market_value=820.00,
            pnl_day=-120.00,
            pnl_total=-340.00,
            delta=0.25,
            gamma=0.002,
            theta=-3.80,
            vega=1.10,
        ),
        PositionResponse(
            symbol="$SPX",
            option_symbol="SPX 240309 P5830",
            quantity=1,
            avg_price=3.20,
            current_price=2.80,
            market_value=280.00,
            pnl_day=-40.00,
            pnl_total=-40.00,
            delta=-0.20,
            gamma=0.001,
            theta=-2.10,
            vega=0.80,
        ),
    ]
