# Strader — SPX Options Trading Platform

Real-time SPX options trading dashboard for 0DTE butterflies, verticals, and long puts/calls.

## Quick Start

```bash
docker-compose up
```

Open http://localhost (nginx proxy) or http://localhost:5173 (Vite dev server).

## Architecture

| Component | Port | Tech |
|-----------|------|------|
| Frontend | 5173 | React 18 + TypeScript + Vite + Recharts |
| Backend | 8000 | Python FastAPI + WebSocket |
| PostgreSQL | 5432 | Trade history, daily P&L, alerts |
| Redis | 6379 | Real-time cache, pub/sub |
| nginx | 80 | Reverse proxy |

## Features

### Surfaces

1. **Options Chain** — Strikes x expirations grid with real-time Greeks, bid/ask, volume/OI
2. **Position Dashboard** — Open positions with live P&L, per-position and portfolio Greeks rollup
3. **Trade Builder** — Butterfly constructor with risk graph, vertical spread builder
4. **P&L Chart** — Intraday real-time curve + daily bar chart history
5. **Risk Panel** — Portfolio Greeks, max loss scenarios, breach alerts, limit monitoring

### Market Context Bar

Persistent top bar showing SPX spot, VIX, expected move, market status, time to close.

### Keyboard Navigation

Press `1`-`5` to switch between tabs.

## Backend Services

- **Market Data Service** — SPX/VIX quotes via Schwab API with Redis caching
- **Options Chain Service** — Full chain with Greeks, strike filtering, expiration selection
- **Account Service** — Positions, portfolio Greeks, account balance
- **Risk Engine** — Real-time limit monitoring (daily loss, position count, delta, notional)
- **Trade Builder** — Butterfly and vertical spread construction with expiration P&L graphs
- **WebSocket Manager** — Real-time push to browser clients

## Schwab API Integration

Set environment variables for live data:

```bash
SCHWAB_API_KEY=your_key
SCHWAB_APP_SECRET=your_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8443/callback
```

Place your token file at `backend/data/schwab_token.json`, or run the Schwab auth flow.

Without credentials, the app runs in **demo mode** with realistic simulated data.

## Risk Limits (configurable via env)

| Limit | Default | Env Var |
|-------|---------|---------|
| Max daily loss | $2,000 | MAX_DAILY_LOSS |
| Max positions | 10 | MAX_POSITION_COUNT |
| Max single position | $5,000 | MAX_SINGLE_POSITION_SIZE |
| Max portfolio delta | 50 | MAX_PORTFOLIO_DELTA |
| Max risk per trade | 2% | MAX_RISK_PER_TRADE_PCT |

Positions exceeding $5,000 notional require Steve's approval (escalation alert).

## Development

```bash
# Backend only
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# Frontend only
cd frontend && npm install && npm run dev
```

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), asyncpg, redis-py, schwab-py
- **Frontend**: React 18, TypeScript, Vite, Recharts, JetBrains Mono
- **Infra**: PostgreSQL 16, Redis 7, nginx, Docker Compose
