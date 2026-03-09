"""Options chain endpoints."""

from typing import Optional

from fastapi import APIRouter, Query

from app.services.options_chain import options_chain_service

router = APIRouter(prefix="/api/options", tags=["options"])


@router.get("/chain")
async def get_chain(
    underlying: str = Query("SPX"),
    expiration: Optional[str] = Query(None),
    strike_range: int = Query(50, ge=10, le=200),
):
    return await options_chain_service.get_chain(underlying, expiration, strike_range)


@router.get("/expirations")
async def get_expirations(underlying: str = Query("SPX")):
    return await options_chain_service.get_expirations(underlying)
