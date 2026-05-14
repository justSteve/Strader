#!/usr/bin/env python3
"""
Hello World for Schwab API integration.
Tests authentication and fetches SPX quote.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schwab.client import create_client


def main():
    print("Authenticating with Schwab API...")
    try:
        c = create_client()
        print("  Authentication successful")
    except Exception as e:
        print(f"[ALERT] {e}")
        return 1

    print("\nFetching $SPX quote...")
    try:
        r = c.get_quote('$SPX')
        r.raise_for_status()
        data = r.json()

        spx = data['$SPX']['quote']
        print("\n$SPX Quote:")
        print(f"  Last:   {spx.get('lastPrice', 0):.2f}")
        print(f"  Close:  {spx.get('closePrice', 0):.2f}")
        print(f"  High:   {spx.get('highPrice', 0):.2f}")
        print(f"  Low:    {spx.get('lowPrice', 0):.2f}")
        print(f"  Change: {spx.get('netChange', 0):.2f} ({spx.get('netPercentChange', 0):.2f}%)")
        return 0

    except Exception as e:
        print(f"[ALERT] Quote fetch failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
