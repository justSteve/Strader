#!/usr/bin/env python3
"""EOD analytical view from Schwab data only. [no bead — exploratory]

Pulls the minimum data for a "where does today close" framing using only
the Schwab feed (no GexBot, no chart inference). Outputs structured
observations with full provenance — each number cites the field name it
came from. No interpretive labels imposed by the script; reader composes
the read.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker_schwab.client import create_client  # noqa: E402


def _fmt(v, w=10, dp=2):
    if v is None:
        return "None"
    if isinstance(v, float):
        return f"{v:>{w},.{dp}f}"
    return f"{v:>{w}}"


def main() -> int:
    c = create_client()
    now = datetime.now(timezone.utc)
    print(f"# EOD view — Schwab feed only")
    print(f"# pull_ts (UTC) = {now.isoformat()}\n")

    # --- spot quotes for SPX cash + ES futures ---
    r = c.get_quotes(["$SPX", "/ES"])
    r.raise_for_status()
    qdata = r.json()

    print("## Spot quotes (gex_quotes endpoint)")
    for sym in ("$SPX", "/ES"):
        info = qdata.get(sym, {})
        # /ES via get_quotes resolves to the front-month (was /ESM26 today)
        if not info:
            for k, v in qdata.items():
                if k.startswith("/ES"):
                    sym, info = k, v
                    break
        q = info.get("quote", {})
        print(f"\n  {sym}  (assetMainType={info.get('assetMainType')})")
        for field in ("lastPrice", "mark", "bidPrice", "askPrice",
                      "openPrice", "highPrice", "lowPrice", "closePrice",
                      "netChange", "netPercentChange",
                      "totalVolume", "quoteTime", "tradeTime", "52WeekHigh", "52WeekLow"):
            if field in q:
                print(f"    {field:22s}= {q[field]}")

    # --- 0DTE chain for ATM straddle (implied move into close) ---
    print("\n## 0DTE chain — ATM strikes only")
    try:
        r = c.get_option_chain(
            symbol="$SPX",
            contract_type=c.Options.ContractType.ALL,
            strike_count=6,
            from_date=date.today(),
            to_date=date.today(),
            include_underlying_quote=True,
        )
        r.raise_for_status()
        chain = r.json()
        print(f"  status={chain.get('status')}  isDelayed={chain.get('isDelayed')}")
        print(f"  underlyingPrice (chain): {chain.get('underlyingPrice')}")
        print(f"  interestRate: {chain.get('interestRate')}")
        for side_label, side_key in (("CALLS", "callExpDateMap"), ("PUTS", "putExpDateMap")):
            m = chain.get(side_key, {})
            if not m:
                print(f"\n  {side_label}: (no entries — possibly no 0DTE today)")
                continue
            exp_key = next(iter(m))
            print(f"\n  {side_label} expiry={exp_key}")
            print(f"    {'strike':>8} {'bid':>7} {'ask':>7} {'mark':>7} {'vol':>7} {'oi':>7} {'delta':>7} {'iv%':>6}")
            for strike, contracts in sorted(m[exp_key].items(), key=lambda kv: float(kv[0])):
                for opt in contracts:
                    bid = opt.get("bid") or 0
                    ask = opt.get("ask") or 0
                    mark = opt.get("mark") or 0
                    vol = opt.get("totalVolume") or 0
                    oi = opt.get("openInterest") or 0
                    delta = opt.get("delta")
                    iv = opt.get("volatility")
                    delta_str = f"{delta:.3f}" if isinstance(delta, (int, float)) else "?"
                    iv_str = f"{iv:.1f}" if isinstance(iv, (int, float)) else "?"
                    print(f"    {strike:>8} {bid:>7.2f} {ask:>7.2f} {mark:>7.2f} {vol:>7} {oi:>7} {delta_str:>7} {iv_str:>6}")
    except Exception as e:
        print(f"  chain error: {type(e).__name__}: {e}")

    # --- intraday range (1-min bars today) ---
    print("\n## Intraday 1-min bars (today, SPX cash)")
    try:
        from datetime import datetime as _dt, time as _tm
        today_start = _dt.combine(date.today(), _tm(13, 30), tzinfo=timezone.utc)  # 09:30 ET = 13:30 UTC (DST)
        r = c.get_price_history(
            symbol="$SPX",
            period_type=c.PriceHistory.PeriodType.DAY,
            period=c.PriceHistory.Period.ONE_DAY,
            frequency_type=c.PriceHistory.FrequencyType.MINUTE,
            frequency=c.PriceHistory.Frequency.EVERY_MINUTE,
            need_extended_hours_data=False,
        )
        r.raise_for_status()
        h = r.json()
        candles = h.get("candles", [])
        if candles:
            today_epoch_ms = int(today_start.timestamp() * 1000)
            today_candles = [c for c in candles if c["datetime"] >= today_epoch_ms]
            if today_candles:
                opens = [c["open"] for c in today_candles]
                highs = [c["high"] for c in today_candles]
                lows = [c["low"] for c in today_candles]
                closes = [c["close"] for c in today_candles]
                print(f"  bar_count = {len(today_candles)}")
                print(f"  first_bar_ts = {datetime.fromtimestamp(today_candles[0]['datetime']/1000, tz=timezone.utc).isoformat()}")
                print(f"  last_bar_ts  = {datetime.fromtimestamp(today_candles[-1]['datetime']/1000, tz=timezone.utc).isoformat()}")
                print(f"  session_open  = {opens[0]}")
                print(f"  session_high  = {max(highs)}")
                print(f"  session_low   = {min(lows)}")
                print(f"  current_close = {closes[-1]}")
                print(f"  session_range = {max(highs) - min(lows):.2f}")
                # last 30 bars range and direction
                last30 = today_candles[-30:] if len(today_candles) >= 30 else today_candles
                print(f"  last_30min_high = {max(c['high'] for c in last30)}")
                print(f"  last_30min_low  = {min(c['low'] for c in last30)}")
                print(f"  last_30min_open = {last30[0]['open']}")
                print(f"  last_30min_close = {last30[-1]['close']}")
            else:
                print(f"  no candles inside today_start={today_start.isoformat()}")
        else:
            print(f"  no candles returned")
    except Exception as e:
        print(f"  price history error: {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
