"""Trade builder and history endpoints."""
from fastapi import APIRouter

from app.models.schemas import ButterflyOrder, VerticalSpreadOrder
from app.services.trade_builder import build_butterfly, build_vertical
from app.services.risk_engine import risk_engine

router = APIRouter(prefix="/trades", tags=["trades"])


@router.post("/butterfly/preview")
async def preview_butterfly(order: ButterflyOrder):
    result = build_butterfly(order)
    risk_check = await risk_engine.evaluate_entry(
        notional=result["max_loss_estimate"],
        delta_impact=0,  # Butterflies are near delta-neutral
    )
    result["risk_check"] = risk_check
    return result


@router.post("/vertical/preview")
async def preview_vertical(order: VerticalSpreadOrder):
    result = build_vertical(order)
    risk_check = await risk_engine.evaluate_entry(
        notional=result["max_loss"],
        delta_impact=50 * order.quantity,  # Approximate
    )
    result["risk_check"] = risk_check
    return result
