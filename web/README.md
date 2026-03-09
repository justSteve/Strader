# Strader Web — SPX Options Trading Platform

Real-time SPX options trading dashboard with 0DTE butterfly/spread builder, live greeks, risk monitoring, and P&L tracking.

## Quick Start

```bash
cd web/
docker-compose up
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Architecture

```
Frontend (React + TypeScript + Vite)
  ├── Market Context Bar — SPX spot, VIX, expected move, time to close
  ├── Options Chain Grid — strikes x expirations, greeks, bid/ask, volume/OI
  ├── Position Dashboard — open positions, live P&L, greeks rollup
  ├── Trade Builder — butterfly constructor, vertical spread builder, risk graph
  ├── P&L Chart — intraday + daily history (Recharts)
  └── Risk Panel — portfolio greeks, max loss scenarios, breach alerts

Backend (Python FastAPI)
  ├── Market Data Service — Schwab API relay, Redis-cached
  ├── Options Chain Service — chain fetching with demo fallback
  ├── Account/Position Service — live positions from Schwab
  ├── Risk Engine — continuous limit monitoring, alert persistence
  ├── Trade Builder — butterfly/vertical construction, risk graph generation
  ├── P&L Service — daily tracking, history
  └── WebSocket Server — real-time push to browser

Infrastructure
  ├── PostgreSQL 16 — trade history, risk limits, alerts
  ├── Redis 7 — real-time cache, pubsub
  └── Docker Compose — single-command orchestration
```

## Configuration

Copy `.env.example` to `.env` and set Schwab API credentials:

```
SCHWAB_APP_KEY=your_app_key
SCHWAB_APP_SECRET=your_app_secret
```

Without credentials, the app runs with demo data.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Alt+1 | Options Chain |
| Alt+2 | Position Dashboard |
| Alt+3 | Trade Builder |
| Alt+4 | P&L Chart |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy, schwab-py
- **Frontend**: React 18, TypeScript, Vite, Recharts, Zustand
- **Infrastructure**: PostgreSQL 16, Redis 7, Docker Compose
