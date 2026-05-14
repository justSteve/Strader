#!/usr/bin/env python3
"""
Stream live market data from Schwab API to Excel.
Requires: xlwings, Excel running on Windows/Mac
"""
import sys
import asyncio
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schwab.client import create_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'lib' / 'schwab-py'))
from schwab.streaming import StreamClient

try:
    import xlwings as xw
except ImportError:
    print("[ALERT] xlwings not available on this platform")
    print("This script requires Windows or macOS with Excel installed")
    sys.exit(1)


class ExcelStreamer:
    """Stream market data to Excel workbook"""

    def __init__(self, workbook_name="Strader_Live_Data.xlsx"):
        self.workbook_name = workbook_name
        self.wb = None
        self.sheet = None

    def setup_workbook(self):
        try:
            self.wb = xw.Book(self.workbook_name)
            print(f"Connected to existing workbook: {self.workbook_name}")
        except Exception:
            self.wb = xw.Book()
            self.wb.save(self.workbook_name)
            print(f"Created new workbook: {self.workbook_name}")

        if "Live_Quotes" in [s.name for s in self.wb.sheets]:
            self.sheet = self.wb.sheets["Live_Quotes"]
        else:
            self.sheet = self.wb.sheets.add("Live_Quotes")

        self.sheet.range("A1").value = ["Symbol", "Last", "Bid", "Ask", "Change", "Change %", "Volume", "Time"]
        self.sheet.range("A1:H1").font.bold = True

    def update_quote(self, symbol, quote_data):
        row = self._get_symbol_row(symbol)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.sheet.range(f"A{row}").value = [
            symbol,
            quote_data.get('lastPrice', 0),
            quote_data.get('bidPrice', 0),
            quote_data.get('askPrice', 0),
            quote_data.get('netChange', 0),
            quote_data.get('netPercentChange', 0),
            quote_data.get('totalVolume', 0),
            timestamp
        ]

    def _get_symbol_row(self, symbol):
        symbols_col = self.sheet.range("A2:A100").value
        for idx, val in enumerate(symbols_col):
            if val == symbol:
                return idx + 2
        for idx, val in enumerate(symbols_col):
            if not val:
                return idx + 2
        return 2


async def stream_quotes(client, symbols, excel_streamer):
    stream = StreamClient(client, account_id=await get_account_id(client))
    await stream.login()
    await stream.quality_of_service(StreamClient.QOSLevel.EXPRESS)
    await stream.level_one_equity_subs(symbols)

    print(f"Streaming {symbols} to Excel...")
    print("Press Ctrl+C to stop")

    async for msg in stream.listen():
        if msg['service'] == 'LEVELONE_EQUITIES':
            for content in msg.get('content', []):
                symbol = content.get('key', 'UNKNOWN')
                excel_streamer.update_quote(symbol, content)


async def get_account_id(client):
    r = client.get_account_numbers()
    r.raise_for_status()
    accounts = r.json()
    return accounts[0]['accountNumber']


async def main():
    print("Connecting to Schwab API...")
    try:
        c = create_client()
        print("  Connected")
    except Exception as e:
        print(f"[ALERT] {e}")
        return 1

    print("Setting up Excel...")
    excel_streamer = ExcelStreamer()
    excel_streamer.setup_workbook()
    print("  Excel ready")

    try:
        symbols = ['$SPX']
        await stream_quotes(c, symbols, excel_streamer)
    except KeyboardInterrupt:
        print("\nStopping stream...")
    except Exception as e:
        print(f"[ALERT] Stream error: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
