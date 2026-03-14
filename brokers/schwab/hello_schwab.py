#!/usr/bin/env python3
"""
Hello World for Schwab API integration.
Tests authentication and fetches SPX quote.
"""
import sys
import os
from pathlib import Path

# Add schwab-py submodule to path
sys.path.insert(0, 'lib/schwab-py')

from schwab import auth
from dotenv import load_dotenv

def main():
    # Load environment variables
    load_dotenv()

    api_key = os.getenv('SCHWAB_API_KEY')
    app_secret = os.getenv('SCHWAB_APP_SECRET')
    callback_url = os.getenv('SCHWAB_CALLBACK_URL', 'https://127.0.0.1:8182/')
    token_path = os.getenv('SCHWAB_TOKEN_PATH', './tokens/schwab_token.json')

    if not api_key or not app_secret:
        print("[ALERT] Missing SCHWAB_API_KEY or SCHWAB_APP_SECRET")
        print("Copy .env.template to .env and fill in your credentials")
        print("Get credentials from https://developer.schwab.com")
        return 1

    # Ensure token directory exists
    Path(token_path).parent.mkdir(parents=True, exist_ok=True)

    print("Authenticating with Schwab API...")
    try:
        c = auth.easy_client(api_key, app_secret, callback_url, token_path, interactive=False)
        print("✓ Authentication successful")
    except Exception as e:
        print(f"[ALERT] Authentication failed: {e}")
        return 1

    # Fetch SPX quote
    print("\nFetching $SPX quote...")
    try:
        r = c.get_quote('$SPX')
        r.raise_for_status()
        data = r.json()

        spx = data['$SPX']['quote']
        print("\n$SPX Quote:")
        print(f"  Last:   {spx['lastPrice']:.2f}")
        print(f"  Bid:    {spx['bidPrice']:.2f}")
        print(f"  Ask:    {spx['askPrice']:.2f}")
        print(f"  Change: {spx['netChange']:.2f} ({spx['netPercentChange']:.2f}%)")

        return 0

    except Exception as e:
        print(f"[ALERT] Quote fetch failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())

