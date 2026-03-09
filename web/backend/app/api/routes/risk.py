"""Risk monitoring API routes."""

from fastapi import APIRouter

from ...services.risk_engine import check_risk_limits, get_cached_alerts
from ...schemas.options import RiskAlert

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/alerts", response_model=list[RiskAlert])
async def risk_alerts():
    """Get current risk alerts."""
    return await get_cached_alerts()


@router.post("/check", response_model=list[RiskAlert])
async def check_risks():
    """Force a risk limit check."""
    return await check_risk_limits()
