# Strader → Excel Integration

Live market data from Schwab API to Excel workbooks.

## Requirements

- Windows or macOS with Excel installed
- Authenticated Schwab API credentials (run `hello_schwab.py` first)
- Python packages: `schwab-py`, `xlwings`, `python-dotenv`

## Scripts

### 1. `poll_to_excel.py` (Recommended)

Polls Schwab API every N seconds and updates Excel.

**Usage:**
```bash
python poll_to_excel.py
```

**Features:**
- Simpler setup, no streaming complexity
- Configurable poll interval (default: 5s)
- Color-coded price changes (green/red)
- Auto-creates `Strader_Quotes.xlsx`

**Customize symbols:**
Edit line 163 in script:
```python
symbols = ['$SPX', 'SPY', 'AAPL', 'TSLA']
```

---

### 2. `stream_to_excel.py` (Advanced)

True real-time streaming via Schwab websocket API.

**Usage:**
```bash
python stream_to_excel.py
```

**Features:**
- Real-time updates (no polling delay)
- Lower API usage
- Requires account ID for streaming auth
- Auto-creates `Strader_Live_Data.xlsx`

**Note:** Streaming is more complex and may have additional API requirements.

---

## Setup Steps

1. **Authenticate first:**
   ```bash
   python hello_schwab.py
   ```
   Complete OAuth flow in browser. Token saved to `./tokens/schwab_token.json`

2. **Open Excel** (script will connect to running instance)

3. **Run poller:**
   ```bash
   python poll_to_excel.py
   ```

4. **Watch Excel update** every 5 seconds

5. **Stop:** Press `Ctrl+C`

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `xlwings not available` | Linux/WSL not supported. Use Windows/Mac with Excel |
| `Token not found` | Run `hello_schwab.py` first to authenticate |
| `Authentication failed` | Check `.env` credentials, regenerate if stale |
| Excel won't open | Ensure Excel is installed and licensed |
| Quotes not updating | Verify symbols are valid (use `$SPX` for index) |

---

## Market Data Symbols

- **SPX Index:** `$SPX` (note the `$` prefix)
- **ETFs:** `SPY`, `QQQ`, `IWM`
- **Stocks:** `AAPL`, `MSFT`, `TSLA`
- **Options:** Not supported in basic quote API (use options chain)

---

## Excel Workbook Structure

### Sheet: "Quotes" / "Live_Quotes"

| Column | Data |
|--------|------|
| A | Symbol |
| B | Last Price |
| C | Bid |
| D | Ask |
| E | Change ($ color-coded) |
| F | Change % |
| G | Volume |
| H | Updated Time |

---

## Rate Limits

Schwab API limits:
- **Quote polling:** 120 requests/minute
- **Streaming:** No explicit limit but may throttle

Polling every 5s = 12 req/min (well within limits)

---

## Next Steps

- Add options chain streaming
- Build position monitor with P&L
- Implement Greeks calculation overlay
- Create risk dashboard in Excel
