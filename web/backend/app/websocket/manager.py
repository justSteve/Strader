"""WebSocket connection manager for real-time updates."""

import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._broadcast_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket disconnected. Total: %d", len(self.active_connections))

    async def broadcast(self, channel: str, data: dict):
        """Broadcast message to all connected clients."""
        message = json.dumps({"channel": channel, "data": data})
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, channel: str, data: dict):
        """Send message to a specific client."""
        message = json.dumps({"channel": channel, "data": data})
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)

    async def start_broadcast_loop(self):
        """Start periodic broadcast of market data and risk alerts."""
        from ..services.market_data import get_market_context
        from ..services.risk_engine import check_risk_limits
        from ..services.positions import get_positions, get_portfolio_greeks
        from ..core.config import settings

        async def _loop():
            while True:
                try:
                    if self.active_connections:
                        # Market context
                        ctx = await get_market_context()
                        await self.broadcast("market", ctx.model_dump(mode="json"))

                        # Positions
                        positions = await get_positions()
                        await self.broadcast("positions", [p.model_dump() for p in positions])

                        # Portfolio greeks
                        greeks = await get_portfolio_greeks()
                        await self.broadcast("greeks", greeks.model_dump())

                        # Risk alerts
                        alerts = await check_risk_limits()
                        if alerts:
                            await self.broadcast("alerts", [a.model_dump() for a in alerts])

                except Exception:
                    logger.exception("Broadcast loop error")

                await asyncio.sleep(settings.ws_heartbeat_interval)

        self._broadcast_task = asyncio.create_task(_loop())

    async def stop_broadcast_loop(self):
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass


manager = ConnectionManager()
