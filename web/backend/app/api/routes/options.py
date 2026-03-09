"""Options chain API routes."""

from datetime import date

from fastapi import APIRouter, Query

from ...services.options_chain import get_options_chain
from ...schemas.options import OptionsChainResponse

router = APIRouter(prefix="/api/options", tags=["options"])


@router.get("/chain", response_model=OptionsChainResponse)
async def options_chain(
    symbol: str = Query("$SPX", description="Underlying symbol"),
    expiration: date | None = Query(None, description="Filter by expiration date"),
    strike_count: int = Query(20, description="Number of strikes around ATM"),
):
    """Get options chain with greeks, bid/ask, volume/OI."""
    return await get_options_chain(symbol, expiration, strike_count)
