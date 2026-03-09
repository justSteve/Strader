"""Strader — SPX Options Trading Web App."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.routers import market, options, positions, trades, risk, pnl
from app.services.market_data import market_data_service
from app.services.options_chain import options_chain_service
from app.ws.manager import ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await market_data_service.connect_redis()
    await options_chain_service.connect_redis()
    yield


app = FastAPI(
    title="Strader",
    description="SPX Options Trading Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(market.router, prefix="/api")
app.include_router(options.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(pnl.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "strader"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle subscription messages from client
            import json
            msg = json.loads(data)
            if msg.get("type") == "subscribe":
                await ws_manager.send_personal(
                    websocket, "subscribed", {"channel": msg.get("channel")}
                )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
