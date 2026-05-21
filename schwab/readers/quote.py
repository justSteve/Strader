#!/usr/bin/env python3
"""Read-only: fetch quotes for given symbols. Auto-allowed for agent use."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from schwab.client import create_client


def main():
    symbols = sys.argv[1:] or ['$SPX', '/ES']
    c = create_client()

    # Always use get_quotes (plural): the singular form interpolates the symbol
    # into the URL path and 400s on symbols with non-alphanumeric chars (st-oit).
    r = c.get_quotes(symbols)

    r.raise_for_status()
    data = r.json()

    for sym, info in data.items():
        q = info.get('quote', {})
        ref = info.get('reference', {})
        print(f"\n{sym}")
        print(f"  Last:    {q.get('lastPrice', 'N/A')}")
        print(f"  Bid/Ask: {q.get('bidPrice', 'N/A')} / {q.get('askPrice', 'N/A')}")
        print(f"  Change:  {q.get('netChange', 0):+.2f} ({q.get('netPercentChange', 0):+.2f}%)")
        print(f"  High:    {q.get('highPrice', 'N/A')}")
        print(f"  Low:     {q.get('lowPrice', 'N/A')}")
        print(f"  Volume:  {q.get('totalVolume', 'N/A')}")
        desc = ref.get('description') or q.get('description', '')
        if desc:
            print(f"  Desc:    {desc}")

    if '--json' in sys.argv:
        print(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
