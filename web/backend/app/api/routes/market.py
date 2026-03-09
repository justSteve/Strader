"""Market data API routes."""

from fastapi import APIRouter

from ...services.market_data import get_market_context
from ...schemas.options import MarketContext

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/context", response_model=MarketContext)
async def market_context():
    """Get current market context (SPX, VIX, expected move)."""
    return await get_market_context()
