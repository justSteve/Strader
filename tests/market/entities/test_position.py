import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from market.entities.instrument import Contract
from market.entities.spread import ButterflyTemplate, ButterflyInstance
from market.entities.position import Position

CENTRAL = ZoneInfo("America/Chicago")

def _contract(strike: float) -> Contract:
    return Contract(
        symbol=f"SPXW260517C{int(strike)}000", underlying="$SPX",
        strike=strike, expiry=date(2026, 5, 17), contract_type="CALL",
        bid=10.0, ask=10.5, last=10.2, volume=100, open_interest=500,
        delta=0.3, gamma=0.01, theta=-5.0, vega=1.5, implied_volatility=14.0,
    )

def _instance() -> ButterflyInstance:
    return ButterflyInstance(
        template=ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL"),
        lower=_contract(5790.0), center=_contract(5800.0), upper=_contract(5810.0),
        net_debit=2.5, max_profit=7.5, max_loss=2.5,
        breakeven_lower=5792.5, breakeven_upper=5807.5,
    )

def test_position_construction():
    p = Position(
        spread=_instance(), entry_price=2.5, quantity=1,
        entry_time=datetime(2026, 5, 17, 14, 30, tzinfo=CENTRAL),
        current_value=3.0, net_delta=0.05, net_gamma=0.002,
        net_theta=-2.5, net_vega=0.8,
    )
    assert p.entry_price == 2.5
    assert p.quantity == 1

def test_position_unrealized_pnl():
    p = Position(
        spread=_instance(), entry_price=2.5, quantity=1,
        entry_time=datetime(2026, 5, 17, 14, 30, tzinfo=CENTRAL),
        current_value=3.0, net_delta=0.05, net_gamma=0.002,
        net_theta=-2.5, net_vega=0.8,
    )
    assert p.unrealized_pnl == 50.0  # (3.0 - 2.5) * 1 * 100

def test_position_is_frozen():
    p = Position(
        spread=_instance(), entry_price=2.5, quantity=1,
        entry_time=datetime(2026, 5, 17, 14, 30, tzinfo=CENTRAL),
        current_value=3.0, net_delta=0.05, net_gamma=0.002,
        net_theta=-2.5, net_vega=0.8,
    )
    with pytest.raises((AttributeError, TypeError)):
        p.current_value = 4.0  # type: ignore
