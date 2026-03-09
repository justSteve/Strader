export interface OptionQuote {
  symbol: string;
  strike: number;
  expiration: string;
  option_type: 'CALL' | 'PUT';
  bid: number;
  ask: number;
  last: number;
  volume: number;
  open_interest: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  iv: number;
  in_the_money: boolean;
}

export interface OptionsChainRow {
  strike: number;
  call: OptionQuote | null;
  put: OptionQuote | null;
}

export interface Position {
  symbol: string;
  description: string;
  quantity: number;
  average_price: number;
  market_value: number;
  day_pnl: number;
  total_pnl: number;
  pnl_pct: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  option_type: 'CALL' | 'PUT' | null;
  strike: number | null;
  expiration: string | null;
}

export interface PortfolioGreeks {
  total_delta: number;
  total_gamma: number;
  total_theta: number;
  total_vega: number;
  net_premium: number;
  buying_power_used: number;
}

export interface RiskStatus {
  daily_pnl: number;
  daily_limit: number;
  daily_pnl_pct: number;
  position_count: number;
  max_positions: number;
  max_single_size: number;
  portfolio_delta: number;
  max_delta: number;
  portfolio_greeks: PortfolioGreeks;
  breaches: string[];
  warnings: string[];
}

export interface MarketContext {
  spx_price: number;
  spx_change: number;
  spx_change_pct: number;
  vix: number;
  vix_change: number;
  expected_move: number;
  expected_move_pct: number;
  market_open: boolean;
  time_to_close: string;
  last_update: string | null;
}

export interface DailyPnL {
  trade_date: string;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  max_drawdown: number;
}

export interface RiskGraphPoint {
  price: number;
  pnl: number;
}

export interface ButterflyPreview {
  strategy: string;
  legs: OptionLeg[];
  risk_graph: RiskGraphPoint[];
  max_profit: number;
  max_loss_estimate: number;
  breakeven_lower: number;
  breakeven_upper: number;
  risk_check: RiskCheck;
}

export interface VerticalPreview {
  strategy: string;
  spread_type: string;
  legs: OptionLeg[];
  risk_graph: RiskGraphPoint[];
  width: number;
  max_profit: number;
  max_loss: number;
  risk_check: RiskCheck;
}

export interface OptionLeg {
  symbol: string;
  option_type: 'CALL' | 'PUT';
  strike: number;
  expiration: string;
  direction: 'LONG' | 'SHORT';
  quantity: number;
  price: number;
}

export interface RiskCheck {
  approved: boolean;
  issues: string[];
  risk_pct: number;
  delta_after: number;
}

export interface IntradayPoint {
  time: string;
  pnl: number;
}

export type Tab = 'chain' | 'positions' | 'builder' | 'pnl' | 'risk';
