"""Alert/notification service — WebSocket push to browser clients."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.risk_engine import risk_engine

logger = logging.getLogger(__name__)


class AlertService:
    """Monitors risk engine and pushes alerts to connected WebSocket clients."""

    def __init__(self) -> None:
        self._running = False
        self._alert_history: list[dict[str, Any]] = []
        self._on_alert_callbacks: list = []

    def on_alert(self, callback):
        self._on_alert_callbacks.append(callback)

    async def get_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._alert_history[-limit:]

    async def start_monitoring(self, interval: float = 5.0) -> None:
        """Periodically check risk and push alerts."""
        self._running = True
        logger.info("Alert monitoring started")
        while self._running:
            try:
                risk_status = await risk_engine.check_risk()
                for alert in risk_status.get("alerts", []):
                    if alert not in self._alert_history[-10:]:
                        self._alert_history.append(alert)
                        for cb in self._on_alert_callbacks:
                            await cb(alert)
            except Exception as e:
                logger.error(f"Alert check failed: {e}")
            await asyncio.sleep(interval)

    def stop_monitoring(self) -> None:
        self._running = False


alert_service = AlertService()
