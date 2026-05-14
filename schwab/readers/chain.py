#!/usr/bin/env python3
"""Read-only: fetch option chain for a symbol. Auto-allowed for agent use."""
import sys
import json
import argparse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from schwab.client import create_client


def parse_args():
    p = argparse.ArgumentParser(description='Fetch option chain')
    p.add_argument('symbol', nargs='?', default='$SPX', help='Symbol (default: $SPX)')
    p.add_argument('--strikes', type=int, default=10, help='Strikes above/below ATM')
    p.add_argument('--type', choices=['CALL', 'PUT', 'ALL'], default='ALL', dest='contract_type')
    p.add_argument('--from-date', type=str, help='YYYY-MM-DD')
    p.add_argument('--to-date', type=str, help='YYYY-MM-DD')
    p.add_argument('--dte', type=int, help='Max days to expiration (shorthand for --to-date)')
    p.add_argument('--json', action='store_true', help='Raw JSON output')
    return p.parse_args()


def format_chain(data):
    underlying = data.get('underlyingPrice', 'N/A')
    symbol = data.get('symbol', '?')
    print(f"\n{symbol}  underlying: {underlying}")
    print(f"  Status: {data.get('status', 'N/A')}")
    print(f"  Strategy: {data.get('strategy', 'SINGLE')}")
    print(f"  Volatility: {data.get('volatility', 'N/A')}")

    for side in ('callExpDateMap', 'putExpDateMap'):
        exp_map = data.get(side, {})
        if not exp_map:
            continue
        label = 'CALLS' if 'call' in side.lower() else 'PUTS'
        print(f"\n  === {label} ===")

        for exp_key, strikes in exp_map.items():
            exp_label = exp_key.split(':')[0]
            print(f"\n  Exp: {exp_label}")
            print(f"  {'Strike':>10}  {'Bid':>8}  {'Ask':>8}  {'Last':>8}  {'Vol':>8}  {'OI':>8}  {'Delta':>7}  {'IV':>7}")
            print(f"  {'-'*10}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*7}")

            for strike_price, contracts in sorted(strikes.items(), key=lambda x: float(x[0])):
                for c in contracts:
                    bid = c.get('bid', 0)
                    ask = c.get('ask', 0)
                    last = c.get('last', 0)
                    vol = c.get('totalVolume', 0)
                    oi = c.get('openInterest', 0)
                    delta = c.get('delta', 0)
                    iv = c.get('volatility', 0)
                    print(f"  {float(strike_price):10.1f}  {bid:8.2f}  {ask:8.2f}  {last:8.2f}  {vol:8d}  {oi:8d}  {delta:7.3f}  {iv:7.1f}")


def main():
    args = parse_args()
    c = create_client()

    kwargs = {
        'strike_count': args.strikes,
        'include_underlying_quote': True,
    }

    if args.contract_type != 'ALL':
        kwargs['contract_type'] = args.contract_type

    if args.from_date:
        kwargs['from_date'] = date.fromisoformat(args.from_date)

    if args.to_date:
        kwargs['to_date'] = date.fromisoformat(args.to_date)
    elif args.dte:
        kwargs['to_date'] = date.today() + timedelta(days=args.dte)

    r = c.get_option_chain(args.symbol, **kwargs)
    r.raise_for_status()
    data = r.json()

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        format_chain(data)


if __name__ == '__main__':
    main()
