-- Strader trade history and configuration

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(64) UNIQUE NOT NULL,
    symbol VARCHAR(32) NOT NULL DEFAULT 'SPX',
    strategy VARCHAR(32) NOT NULL,
    direction VARCHAR(8) NOT NULL,
    legs JSONB NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price NUMERIC(12, 2) NOT NULL,
    exit_price NUMERIC(12, 2),
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ,
    pnl NUMERIC(12, 2),
    fees NUMERIC(8, 2) DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    account_hash VARCHAR(128) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    option_symbol VARCHAR(64),
    quantity INTEGER NOT NULL,
    avg_price NUMERIC(12, 2) NOT NULL,
    current_price NUMERIC(12, 2),
    market_value NUMERIC(14, 2),
    delta NUMERIC(8, 4),
    gamma NUMERIC(8, 6),
    theta NUMERIC(8, 4),
    vega NUMERIC(8, 4),
    pnl_day NUMERIC(12, 2),
    pnl_total NUMERIC(12, 2),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL UNIQUE,
    realized_pnl NUMERIC(12, 2) DEFAULT 0,
    unrealized_pnl NUMERIC(12, 2) DEFAULT 0,
    fees NUMERIC(8, 2) DEFAULT 0,
    trade_count INTEGER DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,
    max_drawdown NUMERIC(12, 2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(32) NOT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    data JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS risk_limits (
    id SERIAL PRIMARY KEY,
    limit_name VARCHAR(64) UNIQUE NOT NULL,
    limit_value NUMERIC(14, 2) NOT NULL,
    current_value NUMERIC(14, 2) DEFAULT 0,
    breached BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Default risk limits
INSERT INTO risk_limits (limit_name, limit_value) VALUES
    ('max_daily_loss', -2000.00),
    ('max_position_count', 10),
    ('max_single_position', 5000.00),
    ('max_portfolio_delta', 50.00),
    ('max_portfolio_gamma', 10.00)
ON CONFLICT (limit_name) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades (entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades (strategy);
CREATE INDEX IF NOT EXISTS idx_daily_pnl_date ON daily_pnl (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_positions_account ON positions (account_hash);
