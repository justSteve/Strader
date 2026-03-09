"""Trade builder API routes."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from ...services.trade_builder import build_butterfly, build_vertical, evaluate_trade
from ...schemas.options import TradeSetup, TradeEvaluation

router = APIRouter(prefix="/api/trades", tags=["trades"])


class ButterflyRequest(BaseModel):
    center_strike: float
    width: float
    expiration: date
    option_type: str = "CALL"
    prices: dict[str, float] | None = None


class VerticalRequest(BaseModel):
    long_strike: float
    short_strike: float
    expiration: date
    option_type: str = "CALL"
    prices: dict[str, float] | None = None


class EvaluateRequest(BaseModel):
    setup: TradeSetup
    underlying_price: float


@router.post("/butterfly", response_model=TradeSetup)
async def create_butterfly(req: ButterflyRequest):
    """Build a butterfly spread."""
    prices = {float(k): v for k, v in req.prices.items()} if req.prices else None
    return build_butterfly(
        req.center_strike, req.width, req.expiration, req.option_type, prices
    )


@router.post("/vertical", response_model=TradeSetup)
async def create_vertical(req: VerticalRequest):
    """Build a vertical spread."""
    prices = {float(k): v for k, v in req.prices.items()} if req.prices else None
    return build_vertical(
        req.long_strike, req.short_strike, req.expiration, req.option_type, prices
    )


@router.post("/evaluate", response_model=TradeEvaluation)
async def evaluate(req: EvaluateRequest):
    """Evaluate a trade setup and generate risk graph."""
    return evaluate_trade(req.setup, req.underlying_price)
