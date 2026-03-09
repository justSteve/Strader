from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Strategy(str, Enum):
    BUTTERFLY = "BUTTERFLY"
    VERTICAL = "VERTICAL"
    SINGLE = "SINGLE"
    IRON_CONDOR = "IRON_CONDOR"
    CUSTOM = "CUSTOM"


class OptionLeg(BaseModel):
    symbol: str
    option_type: OptionType
    strike: float
    expiration: date
    direction: Direction
    quantity: int
    price: float = 0.0


class OptionQuote(BaseModel):
    symbol: str
    strike: float
    expiration: date
    option_type: OptionType
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    iv: float = 0.0
    in_the_money: bool = False


class OptionsChainRow(BaseModel):
    strike: float
    call: Optional[OptionQuote] = None
    put: Optional[OptionQuote] = None


class Position(BaseModel):
    symbol: str
    description: str
    quantity: int
    average_price: float
    market_value: float
    day_pnl: float
    total_pnl: float
    pnl_pct: float
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    option_type: Optional[OptionType] = None
    strike: Optional[float] = None
    expiration: Optional[date] = None


class PortfolioGreeks(BaseModel):
    total_delta: float = 0.0
    total_gamma: float = 0.0
    total_theta: float = 0.0
    total_vega: float = 0.0
    net_premium: float = 0.0
    buying_power_used: float = 0.0


class Trade(BaseModel):
    id: int
    trade_id: str
    symbol: str = "$SPX"
    strategy: Strategy
    direction: Direction
    legs: list[OptionLeg]
    quantity: int
    entry_price: float
    exit_price: Optional[float] = None
    entry_time: datetime
    exit_time: Optional[datetime] = None
    pnl: Optional[float] = None
    status: str = "open"
    notes: Optional[str] = None


class TradeCreate(BaseModel):
    strategy: Strategy
    direction: Direction
    legs: list[OptionLeg]
    quantity: int = 1
    notes: Optional[str] = None


class DailyPnL(BaseModel):
    trade_date: date
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    trade_count: int
    win_count: int
    loss_count: int
    max_drawdown: float


class RiskStatus(BaseModel):
    daily_pnl: float
    daily_limit: float
    daily_pnl_pct: float
    position_count: int
    max_positions: int
    max_single_size: float
    portfolio_delta: float
    max_delta: float
    portfolio_greeks: PortfolioGreeks
    breaches: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Alert(BaseModel):
    id: int
    alert_type: str
    severity: str
    message: str
    data: Optional[dict] = None
    acknowledged: bool = False
    created_at: datetime


class MarketContext(BaseModel):
    spx_price: float = 0.0
    spx_change: float = 0.0
    spx_change_pct: float = 0.0
    vix: float = 0.0
    vix_change: float = 0.0
    expected_move: float = 0.0
    expected_move_pct: float = 0.0
    market_open: bool = False
    time_to_close: str = ""
    last_update: Optional[datetime] = None


class ButterflyOrder(BaseModel):
    center_strike: float
    wing_width: float
    expiration: date
    option_type: OptionType = OptionType.CALL
    quantity: int = 1


class VerticalSpreadOrder(BaseModel):
    long_strike: float
    short_strike: float
    expiration: date
    option_type: OptionType
    quantity: int = 1
