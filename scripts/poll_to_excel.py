#!/usr/bin/env python3
"""
Poll market data from Schwab API and update Excel.
Requires: xlwings, Excel running on Windows/Mac
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker_schwab.client import create_client

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
        try:
            self.wb = xw.Book(self.workbook_name)
            print(f"  Connected to: {self.workbook_name}")
        except Exception:
            self.wb = xw.Book()
            self.wb.save(self.workbook_name)
            print(f"  Created: {self.workbook_name}")

        if "Quotes" in [s.name for s in self.wb.sheets]:
            self.sheet = self.wb.sheets["Quotes"]
            self.sheet.clear()
        else:
            self.sheet = self.wb.sheets.add("Quotes")

        headers = ["Symbol", "Last", "Bid", "Ask", "Change", "Change %", "Volume", "Updated"]
        self.sheet.range("A1").value = [headers]
        self.sheet.range("A1:H1").font.bold = True
        self.sheet.range("A1:H1").color = (200, 200, 200)

    def update_quotes(self, symbols):
        try:
            r = self.client.get_quotes(symbols)
            r.raise_for_status()
            data = r.json()
            timestamp = datetime.now().strftime("%H:%M:%S")

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

                change_cell = self.sheet.range(f"E{row_idx}")
                if change > 0:
                    change_cell.color = (200, 255, 200)
                elif change < 0:
                    change_cell.color = (255, 200, 200)

        except Exception as e:
            print(f"[ALERT] Update failed: {e}")

    def poll_loop(self, symbols, interval=5):
        print(f"\nPolling {symbols} every {interval}s")
        print("Press Ctrl+C to stop\n")
        try:
            while True:
                self.update_quotes(symbols)
                print(f"Updated {len(symbols)} symbols at {datetime.now().strftime('%H:%M:%S')}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n  Stopped polling")


def main():
    print("Connecting to Schwab API...")
    try:
        c = create_client()
        print("  Authenticated")
    except Exception as e:
        print(f"[ALERT] {e}")
        return 1

    print("Setting up Excel...")
    updater = ExcelUpdater(c)
    updater.setup_workbook()

    symbols = ['$SPX']
    updater.poll_loop(symbols, interval=5)
    return 0


if __name__ == '__main__':
    sys.exit(main())
