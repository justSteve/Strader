#!/usr/bin/env python3
"""
Manual Schwab authentication - prints URL, you copy/paste.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, 'lib/schwab-py')

from schwab import auth
from dotenv import load_dotenv

def main():
    load_dotenv()

    api_key = os.getenv('SCHWAB_API_KEY')
    app_secret = os.getenv('SCHWAB_APP_SECRET')
    callback_url = os.getenv('SCHWAB_CALLBACK_URL', 'https://127.0.0.1:8182')
    token_path = os.getenv('SCHWAB_TOKEN_PATH', './tokens/schwab_token.json')

    if not api_key or not app_secret:
        print("[ALERT] Missing SCHWAB_API_KEY or SCHWAB_APP_SECRET")
        return 1

    Path(token_path).parent.mkdir(parents=True, exist_ok=True)

    print("Using manual authentication flow...")
    print()
    try:
        c = auth.client_from_manual_flow(
            api_key, app_secret, callback_url, token_path
        )
        print("\n✓ Authentication successful")

        # Test with SPX quote
        print("\nFetching $SPX quote...")
        r = c.get_quote('$SPX')
        r.raise_for_status()
        data = r.json()
        spx = data['$SPX']['quote']
        print(f"\n$SPX Last: {spx['lastPrice']:.2f}")

        return 0
    except Exception as e:
        print(f"[ALERT] Failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
