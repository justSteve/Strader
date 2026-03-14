#!/usr/bin/env python3
"""
Stream real-time SPX option quotes with Greeks.
"""
import sys
import os
import asyncio
from datetime import datetime
from pathlib import Path

sys.path.insert(0, 'lib/schwab-py')

from schwab import auth
from schwab.streaming import StreamClient
from dotenv import load_dotenv


class SPXOptionsStreamer:
    def __init__(self, api_key, app_secret, token_path):
        self.api_key = api_key
        self.app_secret = app_secret
        self.token_path = token_path

        self.client = None
        self.stream_client = None
        self.account_id = None

        # Example SPX option symbols - update these to current strikes/expirations
        # Format: SPXW_MMDDYY[C|P]STRIKE (e.g., SPXW_031425C5900 for March 14 2025 5900 Call)
        self.symbols = []

        self.queue = asyncio.Queue()

    def initialize(self):
        """Load token and get account info."""
        print("Loading token and account info...")

        self.client = auth.client_from_token_file(
            self.token_path,
            api_key=self.api_key,
            app_secret=self.app_secret
        )

        # Get account number
        account_info = self.client.get_account_numbers().json()
        self.account_id = int(account_info[0]['accountNumber'])

        print(f"✓ Account: {self.account_id}")

        # Create stream client
        self.stream_client = StreamClient(self.client, account_id=self.account_id)
        self.stream_client.add_level_one_option_handler(self.handle_option_quote)

    async def handle_option_quote(self, msg):
        """Process incoming option quote."""
        if self.queue.full():
            await self.queue.get()
        await self.queue.put(msg)

    async def display_quotes(self):
        """Pull quotes from queue and display."""
        print("\n" + "="*120)
        print(f"{'Symbol':<20} {'Bid':<8} {'Ask':<8} {'Last':<8} {'Delta':<8} {'Gamma':<8} {'Theta':<8} {'Vega':<8} {'IV':<8}")
        print("="*120)

        while True:
            msg = await self.queue.get()

            if msg.get('service') == 'LEVELONE_OPTIONS' and msg.get('content'):
                for quote in msg['content']:
                    symbol = quote.get('key', 'N/A')
                    bid = quote.get('BID_PRICE', 0)
                    ask = quote.get('ASK_PRICE', 0)
                    last = quote.get('LAST_PRICE', 0)
                    delta = quote.get('DELTA', 0)
                    gamma = quote.get('GAMMA', 0)
                    theta = quote.get('THETA', 0)
                    vega = quote.get('VEGA', 0)
                    iv = quote.get('VOLATILITY', 0)

                    print(f"{symbol:<20} {bid:<8.2f} {ask:<8.2f} {last:<8.2f} {delta:<8.4f} {gamma:<8.4f} {theta:<8.4f} {vega:<8.4f} {iv:<8.2f}")

    async def stream(self):
        """Main streaming loop."""
        await self.stream_client.login()
        print("✓ Logged into streaming service")

        if not self.symbols:
            print("\n[ALERT] No symbols configured. Add SPX option symbols to self.symbols list.")
            print("Example format: SPXW_031425C5900 (SPXW_MMDDYYC/PSTRIKE)")
            print("\nWaiting for symbols to be added programmatically...")
            # For demo, wait indefinitely - user would add symbols here
            await asyncio.sleep(3600)
            return

        # Subscribe to option quotes
        await self.stream_client.level_one_option_subs(self.symbols)
        print(f"✓ Subscribed to {len(self.symbols)} option contracts\n")

        # Start display task
        asyncio.ensure_future(self.display_quotes())

        # Handle incoming messages
        while True:
            await self.stream_client.handle_message()


async def main():
    load_dotenv()

    api_key = os.getenv('SCHWAB_API_KEY')
    app_secret = os.getenv('SCHWAB_APP_SECRET')
    token_path = os.getenv('SCHWAB_TOKEN_PATH', './tokens/schwab_token.json')

    if not api_key or not app_secret:
        print("[ALERT] Missing SCHWAB_API_KEY or SCHWAB_APP_SECRET")
        return 1

    if not Path(token_path).exists():
        print(f"[ALERT] Token not found at {token_path}")
        print("Run: python3 schwab_auth_manual.py")
        return 1

    streamer = SPXOptionsStreamer(api_key, app_secret, token_path)
    streamer.initialize()

    # TODO: Add current SPX option symbols here
    # You can fetch available options using:
    # r = streamer.client.get_option_chain('$SPX')
    # then parse strikes/expirations and build symbol list

    await streamer.stream()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✓ Stream stopped")
