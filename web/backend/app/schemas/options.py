from pydantic import BaseModel
from datetime import datetime, date


class OptionQuote(BaseModel):
    symbol: str
    strike: float
    expiration: date
    option_type: str  # "CALL" or "PUT"
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    iv: float | None = None
    in_the_money: bool = False


class OptionsChainResponse(BaseModel):
    symbol: str
    underlying_price: float
    expirations: list[str]
    strikes: list[float]
    calls: list[OptionQuote]
    puts: list[OptionQuote]
    updated_at: datetime


class SpreadLeg(BaseModel):
    strike: float
    option_type: str
    action: str  # "BUY" or "SELL"
    quantity: int = 1
    price: float | None = None


class TradeSetup(BaseModel):
    strategy: str  # "butterfly", "vertical", "single"
    direction: str  # "long", "short"
    legs: list[SpreadLeg]
    expiration: date
    max_risk: float | None = None
    max_reward: float | None = None
    breakevens: list[float] = []


class RiskGraphPoint(BaseModel):
    price: float
    pnl: float


class TradeEvaluation(BaseModel):
    setup: TradeSetup
    risk_graph: list[RiskGraphPoint]
    max_profit: float
    max_loss: float
    probability_of_profit: float | None = None
    risk_reward_ratio: float
    iv_rank: float | None = None
    passes_criteria: bool
    rejection_reasons: list[str] = []


class PositionResponse(BaseModel):
    symbol: str
    option_symbol: str | None = None
    quantity: int
    avg_price: float
    current_price: float | None = None
    market_value: float | None = None
    pnl_day: float | None = None
    pnl_total: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None


class PortfolioGreeks(BaseModel):
    total_delta: float
    total_gamma: float
    total_theta: float
    total_vega: float
    net_premium: float
    max_loss: float | None = None


class RiskAlert(BaseModel):
    alert_type: str
    severity: str
    message: str
    current_value: float
    limit_value: float
    breached: bool


class MarketContext(BaseModel):
    spx_price: float
    spx_change: float
    spx_change_pct: float
    vix: float
    vix_change: float
    expected_move: float
    expected_move_pct: float
    time_to_close: str
    market_status: str  # "pre", "open", "after", "closed"
    updated_at: datetime


class PnLSummary(BaseModel):
    date: date
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    fees: float
    trade_count: int
    win_rate: float | None = None
    max_drawdown: float
