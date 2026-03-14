# Schwab API Integration

Schwab-specific scripts and utilities for market data and authentication.

## Authentication

Use `auth_manual.py` for authentication flow. This script handles the OAuth callback manually.

## Scripts

- `auth_manual.py` - Manual OAuth authentication flow
- `hello_schwab.py` - Connection test script
- `get_spx_options.py` - Fetch SPX options chain
- `stream_spx_options.py` - Stream SPX options data

## Setup

From repo root with venv activated:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Tokens stored in `/tokens` (gitignored).
