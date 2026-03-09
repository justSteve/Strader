-- Strader trade history schema

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(64) UNIQUE NOT NULL,
    symbol VARCHAR(32) NOT NULL DEFAULT '$SPX',
    strategy VARCHAR(32) NOT NULL,
    direction VARCHAR(8) NOT NULL,
    legs JSONB NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price NUMERIC(12, 2) NOT NULL,
    exit_price NUMERIC(12, 2),
    entry_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exit_time TIMESTAMPTZ,
    pnl NUMERIC(12, 2),
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id SERIAL PRIMARY KEY,
    trade_date DATE UNIQUE NOT NULL,
    realized_pnl NUMERIC(12, 2) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_pnl NUMERIC(12, 2) NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    win_count INTEGER NOT NULL DEFAULT 0,
    loss_count INTEGER NOT NULL DEFAULT 0,
    max_drawdown NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(32) NOT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    data JSONB,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_entry_time ON trades(entry_time);
CREATE INDEX idx_daily_pnl_date ON daily_pnl(trade_date);
CREATE INDEX idx_alerts_created ON alerts(created_at);
CREATE INDEX idx_alerts_type ON alerts(alert_type);
