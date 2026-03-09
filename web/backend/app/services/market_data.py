"""Market data service — SPX spot, VIX, expected move."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time, timezone, timedelta
from typing import Optional

import redis.asyncio as redis

from app.config import settings
from app.models.schemas import MarketContext
from app.services.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# Demo data for when Schwab API is unavailable
DEMO_CONTEXT = MarketContext(
    spx_price=5850.25,
    spx_change=12.50,
    spx_change_pct=0.21,
    vix=16.42,
    vix_change=-0.35,
    expected_move=32.80,
    expected_move_pct=0.56,
    market_open=True,
    time_to_close="3h 22m",
    last_update=datetime.now(timezone.utc),
)


class MarketDataService:
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._context = DEMO_CONTEXT.model_copy()

    async def connect_redis(self):
        try:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self._redis = None

    async def get_market_context(self) -> MarketContext:
        """Get current market context from cache or API."""
        if self._redis:
            cached = await self._redis.get("market:context")
            if cached:
                return MarketContext.model_validate_json(cached)

        client = get_schwab_client()
        if client is None:
            return self._demo_context()

        try:
            resp = client.get_quotes(["$SPX", "$VIX.X"])
            if resp.status_code == 200:
                data = resp.json()
                ctx = self._parse_quotes(data)
                if self._redis:
                    await self._redis.set(
                        "market:context",
                        ctx.model_dump_json(),
                        ex=5,
                    )
                return ctx
        except Exception as e:
            logger.error(f"Failed to fetch market context: {e}")

        return self._demo_context()

    def _parse_quotes(self, data: dict) -> MarketContext:
        spx = data.get("$SPX", {}).get("quote", {})
        vix = data.get("$VIX.X", {}).get("quote", {})

        spx_price = spx.get("lastPrice", 0)
        spx_close = spx.get("closePrice", spx_price)
        spx_change = spx_price - spx_close
        vix_price = vix.get("lastPrice", 0)
        vix_close = vix.get("closePrice", vix_price)

        # Expected move = SPX * VIX / sqrt(252) / 100
        import math
        em = spx_price * vix_price / math.sqrt(252) / 100 if vix_price else 0

        now = datetime.now(timezone(timedelta(hours=-5)))
        market_open = MARKET_OPEN <= now.time() <= MARKET_CLOSE and now.weekday() < 5
        ttc = ""
        if market_open:
            close_dt = now.replace(hour=16, minute=0, second=0)
            remaining = close_dt - now
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            ttc = f"{hours}h {minutes}m"

        return MarketContext(
            spx_price=spx_price,
            spx_change=round(spx_change, 2),
            spx_change_pct=round(spx_change / spx_close * 100, 2) if spx_close else 0,
            vix=vix_price,
            vix_change=round(vix_price - vix_close, 2),
            expected_move=round(em, 2),
            expected_move_pct=round(em / spx_price * 100, 2) if spx_price else 0,
            market_open=market_open,
            time_to_close=ttc,
            last_update=datetime.now(timezone.utc),
        )

    def _demo_context(self) -> MarketContext:
        self._context.last_update = datetime.now(timezone.utc)
        return self._context


market_data_service = MarketDataService()
