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
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  iv: number | null;
  in_the_money: boolean;
}

export interface OptionsChain {
  symbol: string;
  underlying_price: number;
  expirations: string[];
  strikes: number[];
  calls: OptionQuote[];
  puts: OptionQuote[];
  updated_at: string;
}

export interface Position {
  symbol: string;
  option_symbol: string | null;
  quantity: number;
  avg_price: number;
  current_price: number | null;
  market_value: number | null;
  pnl_day: number | null;
  pnl_total: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
}

export interface PortfolioGreeks {
  total_delta: number;
  total_gamma: number;
  total_theta: number;
  total_vega: number;
  net_premium: number;
  max_loss: number | null;
}

export interface SpreadLeg {
  strike: number;
  option_type: string;
  action: 'BUY' | 'SELL';
  quantity: number;
  price: number | null;
}

export interface TradeSetup {
  strategy: string;
  direction: string;
  legs: SpreadLeg[];
  expiration: string;
  max_risk: number | null;
  max_reward: number | null;
  breakevens: number[];
}

export interface RiskGraphPoint {
  price: number;
  pnl: number;
}

export interface TradeEvaluation {
  setup: TradeSetup;
  risk_graph: RiskGraphPoint[];
  max_profit: number;
  max_loss: number;
  risk_reward_ratio: number;
  passes_criteria: boolean;
  rejection_reasons: string[];
}

export interface RiskAlert {
  alert_type: string;
  severity: string;
  message: string;
  current_value: number;
  limit_value: number;
  breached: boolean;
}

export interface MarketContext {
  spx_price: number;
  spx_change: number;
  spx_change_pct: number;
  vix: number;
  vix_change: number;
  expected_move: number;
  expected_move_pct: number;
  time_to_close: string;
  market_status: string;
  updated_at: string;
}

export interface PnLSummary {
  date: string;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  fees: number;
  trade_count: number;
  win_rate: number | null;
  max_drawdown: number;
}
