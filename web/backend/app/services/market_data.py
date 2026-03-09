"""Market data service — relays Schwab streaming API data via Redis pub/sub."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class MarketDataService:
    """Fetches and caches market data from Schwab API, publishes updates via Redis."""

    def __init__(self) -> None:
        self._redis: Optional[redis.Redis] = None
        self._running = False
        self._spx_price: float = 0.0
        self._vix: float = 0.0
        self._expected_move: float = 0.0
        self._last_update: Optional[datetime] = None

    async def connect(self) -> None:
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    async def get_market_context(self) -> dict[str, Any]:
        """Return current market context bar data."""
        cached = await self._get_cached("market:context")
        if cached:
            return cached
        return {
            "spx_price": self._spx_price,
            "spx_change": 0.0,
            "spx_change_pct": 0.0,
            "vix": self._vix,
            "expected_move": self._expected_move,
            "time_to_close": self._time_to_close(),
            "updated_at": (
                self._last_update.isoformat() if self._last_update else None
            ),
        }

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        cached = await self._get_cached(f"quote:{symbol}")
        if cached:
            return cached
        # Fallback: return empty quote
        return {"symbol": symbol, "bid": 0, "ask": 0, "last": 0, "volume": 0}

    async def publish_update(self, channel: str, data: dict[str, Any]) -> None:
        if self._redis:
            await self._redis.publish(channel, json.dumps(data))

    async def cache_market_data(self, key: str, data: dict[str, Any], ttl: int = 5) -> None:
        if self._redis:
            await self._redis.setex(f"market:{key}", ttl, json.dumps(data))

    async def start_streaming(self) -> None:
        """Start background streaming loop. In production, connects to Schwab streaming."""
        self._running = True
        logger.info("Market data streaming started (demo mode)")
        while self._running:
            now = datetime.now(timezone.utc)
            self._last_update = now
            # Demo data — in production, this reads from schwab-py streaming
            context = await self.get_market_context()
            await self.cache_market_data("context", context, ttl=5)
            if self._redis:
                await self._redis.publish("market:updates", json.dumps(context))
            await asyncio.sleep(1)

    def stop_streaming(self) -> None:
        self._running = False

    async def _get_cached(self, key: str) -> Optional[dict[str, Any]]:
        if not self._redis:
            return None
        raw = await self._redis.get(key)
        if raw:
            return json.loads(raw)
        return None

    @staticmethod
    def _time_to_close() -> str:
        """Calculate time remaining to 4:00 PM ET market close."""
        now = datetime.now(timezone.utc)
        close_hour = 20  # 4 PM ET = 20:00 UTC (EST, approximate)
        close_minute = 0
        remaining_minutes = (close_hour * 60 + close_minute) - (
            now.hour * 60 + now.minute
        )
        if remaining_minutes < 0:
            return "CLOSED"
        hours = remaining_minutes // 60
        minutes = remaining_minutes % 60
        return f"{hours}h {minutes}m"


market_data_service = MarketDataService()
