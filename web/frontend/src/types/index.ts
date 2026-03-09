export interface MarketContext {
  spx_price: number;
  spx_change: number;
  spx_change_pct: number;
  vix: number;
  expected_move: number;
  time_to_close: string;
  updated_at: string | null;
}

export interface Greeks {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

export interface OptionQuote {
  bid: number;
  ask: number;
  last: number;
  volume: number;
  open_interest: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  price: number;
}

export interface ChainRow {
  strike: number;
  call: OptionQuote;
  put: OptionQuote;
}

export interface OptionsChain {
  underlying: string;
  spot: number;
  expiration: string;
  dte: number;
  chain: ChainRow[];
}

export interface Position {
  id: number;
  symbol: string;
  underlying: string;
  instrument_type: string;
  put_call: string;
  strike: number;
  expiration: string;
  quantity: number;
  average_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  day_pnl: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  strategy: string;
}

export interface PortfolioSummary {
  position_count: number;
  total_market_value: number;
  total_cost_basis: number;
  unrealized_pnl: number;
  day_pnl: number;
  greeks: Greeks;
  updated_at: string;
}

export interface PnLPoint {
  date?: string;
  time?: string;
  pnl: number;
  daily_pnl?: number;
  cumulative_pnl?: number;
  trade_count?: number;
  minute?: number;
}

export interface RiskCheck {
  value: number;
  limit: number;
  breached: boolean;
  pct_used: number;
}

export interface Alert {
  level: string;
  category: string;
  message: string;
  value: number;
  limit: number;
  timestamp: string;
}

export interface RiskStatus {
  status: string;
  checks: Record<string, RiskCheck>;
  alerts: Alert[];
  summary: PortfolioSummary;
  limits: Record<string, number>;
  checked_at: string;
}

export interface Scenario {
  move_pct: number;
  estimated_pnl: number;
}

export interface TradeLeg {
  strike: number;
  action: string;
  quantity: number;
  type: string;
}

export interface TradeAnalysis {
  strategy: string;
  legs: TradeLeg[];
  net_debit: number;
  max_profit: number;
  max_loss: number;
  breakevens?: number[];
  greeks: Greeks;
  risk_graph: { price: number; pnl: number }[];
  dte: number;
}

export interface Expiration {
  date: string;
  dte: number;
  label: string;
}
