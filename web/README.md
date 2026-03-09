# Strader — SPX Options Trading Platform

Real-time SPX options trading web app for 0DTE butterflies and directional plays.

## Quick Start

```bash
docker-compose up
```

Open http://localhost:8080

## Architecture

| Component | Tech | Port |
|-----------|------|------|
| Frontend | React + TypeScript + Vite | 3000 |
| Backend | Python FastAPI | 8000 |
| Database | PostgreSQL 16 | 5432 |
| Cache | Redis 7 | 6379 |
| Proxy | Nginx | 8080 |

## Surfaces

| Key | Surface | Description |
|-----|---------|-------------|
| 1 | Options Chain | Strike × expiration grid with real-time greeks, bid/ask, volume/OI |
| 2 | Positions | Open positions with live P&L and portfolio greeks rollup |
| 3 | Trade Builder | Butterfly constructor + vertical spread builder with risk graph |
| 4 | P&L Chart | Intraday real-time + 30-day history |
| 5 | Risk Panel | Portfolio greeks, max loss scenarios, breach alerts |

Keyboard: `1-5` to switch tabs, `h/l` or arrow keys to navigate.

## Backend Services

- **Market Data** — Schwab streaming API relay via Redis pub/sub
- **Options Chain** — Black-Scholes greeks with simulated bid/ask/volume
- **Position Service** — Portfolio tracking with greeks rollup
- **Risk Engine** — Limit monitoring (daily loss, position count, delta, notional)
- **Alert Service** — WebSocket push for breach notifications

## Configuration

Copy `.env.example` to `.env` and set your Schwab API credentials for live data.
Without credentials, the app runs with simulated demo data.

## Risk Limits (defaults)

| Limit | Default |
|-------|---------|
| Max daily loss | $5,000 |
| Max positions | 10 |
| Max single position | $5,000 notional |
| Max portfolio delta | 50 |
| Risk per trade | 2% |

## Development

Backend hot-reloads via uvicorn `--reload`. Frontend hot-reloads via Vite HMR.
Both source directories are volume-mounted in docker-compose.
