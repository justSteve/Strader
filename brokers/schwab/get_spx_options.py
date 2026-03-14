#!/usr/bin/env python3
"""
Fetch available SPX options and show symbol format for streaming.
"""
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, 'lib/schwab-py')

from schwab import auth
from schwab.client import Client
from dotenv import load_dotenv


def main():
    load_dotenv()

    api_key = os.getenv('SCHWAB_API_KEY')
    app_secret = os.getenv('SCHWAB_APP_SECRET')
    token_path = os.getenv('SCHWAB_TOKEN_PATH', './tokens/schwab_token.json')

    if not api_key or not app_secret:
        print("[ALERT] Missing credentials")
        return 1

    if not Path(token_path).exists():
        print(f"[ALERT] Token not found at {token_path}")
        return 1

    print("Loading SPX option chain...")

    c = auth.client_from_token_file(token_path, api_key, app_secret)

    # Get SPX quote to know current price
    r = c.get_quote('$SPX')
    r.raise_for_status()
    spx_price = r.json()['$SPX']['quote']['lastPrice']

    print(f"\n$SPX Last: {spx_price:.2f}\n")

    # Fetch option chain for 0DTE and next few expirations
    # Schwab API uses different params than TDA, checking what's available
    try:
        from_date = datetime.now().strftime('%Y-%m-%d')
        to_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        r = c.get_option_chain(
            '$SPX',
            contract_type=Client.Options.ContractType.ALL,
            strike_count=10,
            from_date=from_date,
            to_date=to_date
        )
        r.raise_for_status()
        chain = r.json()

        print("Available expirations:")
        print("="*80)

        # Parse available options
        call_map = chain.get('callExpDateMap', {})
        put_map = chain.get('putExpDateMap', {})

        for exp_date in sorted(set(list(call_map.keys()) + list(put_map.keys())))[:5]:
            print(f"\nExpiration: {exp_date}")

            # Show a few ATM strikes for calls
            if exp_date in call_map:
                strikes = sorted([float(k) for k in call_map[exp_date].keys()])
                atm_strikes = [s for s in strikes if abs(s - spx_price) < 100][:3]

                print(f"  Calls (ATM):")
                for strike in atm_strikes:
                    strike_str = f"{strike:.1f}"
                    if strike_str in call_map[exp_date]:
                        opt = call_map[exp_date][strike_str][0]
                        symbol = opt.get('symbol', 'N/A')
                        bid = opt.get('bid', 0)
                        ask = opt.get('ask', 0)
                        delta = opt.get('delta', 0)
                        print(f"    {strike:7.0f} | {symbol:<25} | Bid: {bid:6.2f} | Ask: {ask:6.2f} | Δ: {delta:5.3f}")

            # Show a few ATM strikes for puts
            if exp_date in put_map:
                strikes = sorted([float(k) for k in put_map[exp_date].keys()], reverse=True)
                atm_strikes = [s for s in strikes if abs(s - spx_price) < 100][:3]

                print(f"  Puts (ATM):")
                for strike in atm_strikes:
                    strike_str = f"{strike:.1f}"
                    if strike_str in put_map[exp_date]:
                        opt = put_map[exp_date][strike_str][0]
                        symbol = opt.get('symbol', 'N/A')
                        bid = opt.get('bid', 0)
                        ask = opt.get('ask', 0)
                        delta = opt.get('delta', 0)
                        print(f"    {strike:7.0f} | {symbol:<25} | Bid: {bid:6.2f} | Ask: {ask:6.2f} | Δ: {delta:6.3f}")

        print("\n" + "="*80)
        print("\nTo stream these options, use the symbols shown above in stream_spx_options.py")

        return 0

    except Exception as e:
        print(f"[ALERT] Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
