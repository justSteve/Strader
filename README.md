# Strader

SPX options trading analysis and position management.

## Setup

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Structure

- `/brokers/schwab` - Schwab API integration and scripts
- `/indicators` - LuxAlgo indicator documentation for /ES price action
- `/tui` - Terminal UI components
- `/web` - Web interface (separate component)
- `.beads/` - Task tracking (beads-first workflow)

## Authentication

See [brokers/schwab/README.md](brokers/schwab/README.md) for Schwab authentication setup.

## Environment

Copy `.env.template` to `.env` and configure:
- Schwab API credentials
- Risk limits
- Account settings
