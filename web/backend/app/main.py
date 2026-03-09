"""Strader — SPX Options Trading Web App."""

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import market, options, positions, risk, trades
from app.services.alerts import alert_service
from app.services.market_data import market_data_service
from app.ws.manager import ws_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Strader", version="1.0.0", description="SPX Options Trading Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(options.router)
app.include_router(positions.router)
app.include_router(trades.router)
app.include_router(risk.router)

_background_tasks: list[asyncio.Task] = []


@app.on_event("startup")
async def startup():
    await market_data_service.connect()

    async def broadcast_alert(alert):
        await ws_manager.broadcast({"type": "alert", "data": alert})

    alert_service.on_alert(broadcast_alert)

    _background_tasks.append(asyncio.create_task(market_data_service.start_streaming()))
    _background_tasks.append(asyncio.create_task(alert_service.start_monitoring()))
    logger.info("Strader backend started")


@app.on_event("shutdown")
async def shutdown():
    market_data_service.stop_streaming()
    alert_service.stop_monitoring()
    for task in _background_tasks:
        task.cancel()
    await market_data_service.close()
    logger.info("Strader backend stopped")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "ws_clients": ws_manager.client_count,
        "app": settings.app_name,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle client messages (subscriptions, etc.)
            if data == "ping":
                await ws_manager.send_to(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
