"""Market data and context bar endpoints."""

from fastapi import APIRouter

from app.services.market_data import market_data_service

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/context")
async def get_market_context():
    return await market_data_service.get_market_context()


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    return await market_data_service.get_quote(symbol)
