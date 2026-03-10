#!/usr/bin/env python3
"""
Poll market data from Schwab API and update Excel.
Simpler alternative to streaming - polls every N seconds.
Requires: xlwings, Excel running on Windows/Mac
"""
import sys
import os
import time
from datetime import datetime
from pathlib import Path

# Add schwab-py submodule to path
sys.path.insert(0, 'lib/schwab-py')

from schwab import auth
from dotenv import load_dotenv

try:
    import xlwings as xw
except ImportError:
    print("[ALERT] xlwings not available on this platform")
    print("This script requires Windows or macOS with Excel installed")
    sys.exit(1)


class ExcelUpdater:
    """Poll and update market data in Excel"""

    def __init__(self, client, workbook_name="Strader_Quotes.xlsx"):
        self.client = client
        self.workbook_name = workbook_name
        self.wb = None
        self.sheet = None

    def setup_workbook(self):
        """Create or connect to Excel workbook"""
        try:
            self.wb = xw.Book(self.workbook_name)
            print(f"✓ Connected to: {self.workbook_name}")
        except:
            self.wb = xw.Book()
            self.wb.save(self.workbook_name)
            print(f"✓ Created: {self.workbook_name}")

        # Get or create sheet
        if "Quotes" in [s.name for s in self.wb.sheets]:
            self.sheet = self.wb.sheets["Quotes"]
            self.sheet.clear()
        else:
            self.sheet = self.wb.sheets.add("Quotes")

        # Headers
        headers = ["Symbol", "Last", "Bid", "Ask", "Change", "Change %", "Volume", "Updated"]
        self.sheet.range("A1").value = [headers]
        self.sheet.range("A1:H1").font.bold = True
        self.sheet.range("A1:H1").color = (200, 200, 200)

    def update_quotes(self, symbols):
        """Fetch and update quotes for symbols"""
        try:
            # Fetch quotes
            r = self.client.get_quotes(symbols)
            r.raise_for_status()
            data = r.json()

            timestamp = datetime.now().strftime("%H:%M:%S")

            # Update each symbol
            for row_idx, symbol in enumerate(symbols, start=2):
                quote = data.get(symbol, {}).get('quote', {})

                last = quote.get('lastPrice', 0)
                bid = quote.get('bidPrice', 0)
                ask = quote.get('askPrice', 0)
                change = quote.get('netChange', 0)
                change_pct = quote.get('netPercentChange', 0)
                volume = quote.get('totalVolume', 0)

                self.sheet.range(f"A{row_idx}").value = [
                    symbol,
                    f"{last:.2f}" if last else "-",
                    f"{bid:.2f}" if bid else "-",
                    f"{ask:.2f}" if ask else "-",
                    f"{change:+.2f}" if change else "-",
                    f"{change_pct:+.2f}%" if change_pct else "-",
                    f"{volume:,}" if volume else "-",
                    timestamp
                ]

                # Color code change
                change_cell = self.sheet.range(f"E{row_idx}")
                if change > 0:
                    change_cell.color = (200, 255, 200)  # Green
                elif change < 0:
                    change_cell.color = (255, 200, 200)  # Red

        except Exception as e:
            print(f"[ALERT] Update failed: {e}")

    def poll_loop(self, symbols, interval=5):
        """Poll quotes at interval (seconds)"""
        print(f"\nPolling {symbols} every {interval}s")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                self.update_quotes(symbols)
                print(f"Updated {len(symbols)} symbols at {datetime.now().strftime('%H:%M:%S')}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n✓ Stopped polling")


def main():
    """Main entry point"""
    # Load environment
    load_dotenv()

    api_key = os.getenv('SCHWAB_API_KEY')
    app_secret = os.getenv('SCHWAB_APP_SECRET')
    callback_url = os.getenv('SCHWAB_CALLBACK_URL', 'https://127.0.0.1:8182/')
    token_path = os.getenv('SCHWAB_TOKEN_PATH', './tokens/schwab_token.json')

    if not api_key or not app_secret:
        print("[ALERT] Missing SCHWAB_API_KEY or SCHWAB_APP_SECRET")
        return 1

    # Check token exists
    if not Path(token_path).exists():
        print("[ALERT] Token not found. Run hello_schwab.py first to authenticate.")
        return 1

    # Create client
    print("Connecting to Schwab API...")
    try:
        c = auth.easy_client(api_key, app_secret, callback_url, token_path)
        print("✓ Authenticated")
    except Exception as e:
        print(f"[ALERT] Authentication failed: {e}")
        return 1

    # Setup Excel
    print("Setting up Excel...")
    updater = ExcelUpdater(c)
    updater.setup_workbook()

    # Define symbols to track
    symbols = ['$SPX']  # Add more: ['$SPX', 'SPY', 'AAPL']

    # Poll loop
    updater.poll_loop(symbols, interval=5)

    return 0


if __name__ == '__main__':
    sys.exit(main())
