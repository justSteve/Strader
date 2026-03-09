"""Market data service — SPX spot, VIX, expected move."""

import logging
from datetime import datetime, timezone

import redis.asyncio as redis

from ..core.redis import redis_client
from ..schemas.options import MarketContext
from .schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

CACHE_TTL = 5  # seconds


async def get_market_context() -> MarketContext:
    """Get current market context: SPX, VIX, expected move."""
    cached = await redis_client.get("market:context")
    if cached:
        return MarketContext.model_validate_json(cached)

    client = get_schwab_client()
    now = datetime.now(timezone.utc)

    if client is None:
        return _demo_market_context(now)

    try:
        spx_resp = client.get_quote("$SPX")
        spx_data = spx_resp.json().get("$SPX", {}).get("quote", {})

        vix_resp = client.get_quote("$VIX")
        vix_data = vix_resp.json().get("$VIX", {}).get("quote", {})

        spx_price = spx_data.get("lastPrice", 0)
        spx_close = spx_data.get("closePrice", spx_price)
        spx_change = spx_price - spx_close
        spx_change_pct = (spx_change / spx_close * 100) if spx_close else 0

        vix_price = vix_data.get("lastPrice", 0)
        vix_close = vix_data.get("closePrice", vix_price)
        vix_change = vix_price - vix_close

        # Expected move = SPX * VIX / sqrt(252) / 100
        expected_move = spx_price * vix_price / 15.87 / 100
        expected_move_pct = (expected_move / spx_price * 100) if spx_price else 0

        ctx = MarketContext(
            spx_price=round(spx_price, 2),
            spx_change=round(spx_change, 2),
            spx_change_pct=round(spx_change_pct, 2),
            vix=round(vix_price, 2),
            vix_change=round(vix_change, 2),
            expected_move=round(expected_move, 2),
            expected_move_pct=round(expected_move_pct, 2),
            time_to_close=_time_to_close(now),
            market_status=_market_status(now),
            updated_at=now,
        )

        await redis_client.setex("market:context", CACHE_TTL, ctx.model_dump_json())
        return ctx

    except Exception:
        logger.exception("Failed to fetch market data")
        return _demo_market_context(now)


def _demo_market_context(now: datetime) -> MarketContext:
    """Demo data when Schwab API is unavailable."""
    return MarketContext(
        spx_price=5850.25,
        spx_change=12.50,
        spx_change_pct=0.21,
        vix=16.35,
        vix_change=-0.45,
        expected_move=23.30,
        expected_move_pct=0.40,
        time_to_close=_time_to_close(now),
        market_status=_market_status(now),
        updated_at=now,
    )


def _market_status(now: datetime) -> str:
    """Determine market status based on ET hours."""
    # Simplified — doesn't handle holidays
    hour = now.hour - 5  # Rough UTC to ET
    if hour < 0:
        hour += 24
    weekday = now.weekday()

    if weekday >= 5:
        return "closed"
    if hour < 9 or (hour == 9 and now.minute < 30):
        return "pre"
    if hour < 16:
        return "open"
    if hour < 20:
        return "after"
    return "closed"


def _time_to_close(now: datetime) -> str:
    """Calculate time remaining until market close."""
    hour = now.hour - 5
    if hour < 0:
        hour += 24

    if hour >= 16 or hour < 9:
        return "CLOSED"

    remaining_minutes = (16 * 60) - (hour * 60 + now.minute)
    hours = remaining_minutes // 60
    minutes = remaining_minutes % 60
    return f"{hours}h {minutes}m"
