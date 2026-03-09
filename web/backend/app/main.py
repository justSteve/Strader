"""Strader — SPX Options Trading Web App."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import market, options, positions_routes, trades, risk, pnl
from .websocket.manager import manager
from .core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Strader backend")
    await manager.start_broadcast_loop()
    yield
    logger.info("Shutting down Strader backend")
    await manager.stop_broadcast_loop()


app = FastAPI(
    title="Strader",
    description="SPX Options Trading Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(market.router)
app.include_router(options.router)
app.include_router(positions_routes.router)
app.include_router(trades.router)
app.include_router(risk.router)
app.include_router(pnl.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle client messages (subscriptions, pings)
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "strader"}
