#!/usr/bin/env python3
"""
GEX series loop: snapshot dealer gamma exposure on a cadence and persist
each snapshot to a date-rotated JSONL file.

Bridges the one-shot `gex_now.py` read into a trajectory tracker. With a
running series you can answer questions the static snapshot can't:
  - Is GEX rising or falling into the close?
  - Are gamma walls growing or eroding?
  - Has the regime flipped (positive ↔ negative)?

USAGE:
    .venv/bin/python scripts/gex_series.py                        # 60s cadence, today's expiry, indefinite
    .venv/bin/python scripts/gex_series.py --interval 30          # half-minute cadence
    .venv/bin/python scripts/gex_series.py --max-runs 1           # smoke test (one cycle)
    .venv/bin/python scripts/gex_series.py --dte 7                # multi-day expiry window

REQUIRES:
    1. `touch ~/.schwab_gate_key` to authorize agent-driven API access
    2. .env with SCHWAB_API_KEY, SCHWAB_APP_SECRET, SCHWAB_TOKEN_PATH

OUTPUT:
    data/gex_series/SYMBOL_YYYY-MM-DD.jsonl    (one line per cycle, US/Central date)
    Console one-liner per cycle.

EACH SNAPSHOT CAPTURES BOTH SPX CASH AND ES FUTURES SPOT.
    Levels on ES-based charts (LuxAlgo order blocks, ICT FVGs, etc.) don't
    line up 1:1 with SPX cash levels — there's a basis that varies through
    the session (carry, dividends, expiry distance). Each JSONL record
    stores `spot` (SPX cash), `spot_es` (ES quote), and `es_basis`
    (ES − SPX), so a cross-reference to any ES screen capture can subtract
    the basis to map ES level → SPX level (and vice versa).

    To translate: SPX_level = ES_level - es_basis
                  ES_level  = SPX_level + es_basis

The Schwab gammas update slowly (≈ chain refresh cadence ~30s), so an
interval below 30s is wasteful. Default 60s is conservative for both
API politeness and signal-to-noise.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add Strader root for `market.*` and `broker_schwab.*` imports. No sys.path
# gymnastics needed for `schwab` — the upstream hobbled fork resolves cleanly
# from site-packages now that st-8cx renamed the local wrapper.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker_schwab.client import create_client  # noqa: E402
from market.ingest import chain_from_schwab  # noqa: E402
from market.indicators.gex_calc import compute_gex  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CENTRAL = ZoneInfo("America/Chicago")

_stop_flag = False


def _handle_sigint(signum, frame):
    global _stop_flag
    _stop_flag = True


def _try_quote(client, symbol: str) -> float | None:
    """Best-effort spot fetch for a single symbol. Returns None on any failure
    (entitlement, market closed, malformed response). Used to capture the ES
    print alongside SPX so cross-references against ES-based charts (LuxAlgo
    order blocks, etc.) account for the cash-vs-futures basis."""
    try:
        # get_quotes (plural) sends symbol as query param; get_quote (singular)
        # interpolates into the path and double-slashes for symbols like /ESM26.
        # See st-oit and schwab-py base.py:176-179.
        resp = client.get_quotes([symbol])
        resp.raise_for_status()
        payload = resp.json()
        # Schwab quote shape varies by instrument type; try common paths.
        for instrument in payload.values():
            q = instrument.get("quote", {})
            for key in ("lastPrice", "mark", "closePrice"):
                if key in q and q[key]:
                    return float(q[key])
    except Exception:
        return None
    return None


def _snapshot(client, symbol: str, strikes: int, dte: int, window: int,
              es_symbol: str | None) -> dict:
    """Pull one chain, compute GEX, build the JSONL record."""
    to_date = date.today() + timedelta(days=dte)
    resp = client.get_option_chain(
        symbol=symbol,
        strike_count=strikes,
        from_date=date.today(),
        to_date=to_date,
        include_underlying_quote=True,
    )
    resp.raise_for_status()
    data = resp.json()

    # Optional ES quote for SPX/ES basis tracking.
    spot_es = _try_quote(client, es_symbol) if es_symbol else None

    chain = chain_from_schwab(data, expiry=date.today())
    if not chain.calls and not chain.puts:
        # Fall back: maybe expiry isn't today. Use the first available
        # expiry date from the response.
        any_exp = next(
            iter(data.get("callExpDateMap", {})),
            next(iter(data.get("putExpDateMap", {})), None),
        )
        if any_exp:
            chain = chain_from_schwab(
                data, expiry=date.fromisoformat(any_exp.split(":")[0]))

    profile = compute_gex(chain)
    spot = profile.spot

    # Top wall = largest positive by-strike contribution.
    # Top slide = most-negative by-strike contribution.
    by_strike = profile.by_strike
    if by_strike:
        top_wall_strike = max(by_strike.keys(), key=lambda k: by_strike[k])
        top_slide_strike = min(by_strike.keys(), key=lambda k: by_strike[k])
        top_wall = {"strike": top_wall_strike,
                    "gex": by_strike[top_wall_strike],
                    "delta_spot": top_wall_strike - spot}
        top_slide = {"strike": top_slide_strike,
                     "gex": by_strike[top_slide_strike],
                     "delta_spot": top_slide_strike - spot}
    else:
        top_wall = top_slide = None

    nearby = {k: v for k, v in by_strike.items() if abs(k - spot) <= window}

    record = {
        "ts": datetime.now(CENTRAL).isoformat(),
        "symbol": symbol,
        "spot": spot,
        "spot_es": spot_es,
        "es_basis": (spot_es - spot) if spot_es is not None else None,
        "n_strikes": len(by_strike),
        "net_gex": profile.net_gex,
        "net_gex_calls": profile.net_gex_calls,
        "net_gex_puts": profile.net_gex_puts,
        "regime": "SUPPRESSIVE" if profile.net_gex > 0 else "AMPLIFYING",
        "top_wall": top_wall,
        "top_slide": top_slide,
        "by_strike_window": nearby,
    }
    return record


def _output_path(symbol: str, output_dir: Path) -> Path:
    today = datetime.now(CENTRAL).strftime("%Y-%m-%d")
    safe_symbol = symbol.replace("$", "").replace("/", "_")
    return output_dir / f"{safe_symbol}_{today}.jsonl"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GEX series loop")
    p.add_argument("--symbol", default="$SPX",
                   help="Underlying symbol (default: $SPX)")
    p.add_argument("--interval", type=int, default=60,
                   help="Seconds between cycles (default: 60). "
                        "Schwab gammas update slowly; <30 is wasteful.")
    p.add_argument("--strikes", type=int, default=30,
                   help="Strikes above and below ATM per request (default: 30)")
    p.add_argument("--dte", type=int, default=0,
                   help="Max days-to-expiration (default: 0 = today only)")
    p.add_argument("--window", type=int, default=50,
                   help="± points around spot to persist in by_strike_window")
    p.add_argument("--max-runs", type=int, default=None,
                   help="Stop after this many cycles (default: indefinite)")
    p.add_argument("--output-dir", default="data/gex_series",
                   help="Output directory for JSONL (default: data/gex_series)")
    p.add_argument("--es-symbol", default="/ES",
                   help="Companion futures symbol for basis tracking "
                        "(default: /ES). Use --es-symbol '' to skip.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGINT, _handle_sigint)

    print(f"GEX series loop")
    print(f"  symbol={args.symbol}  interval={args.interval}s  "
          f"strikes={args.strikes}  dte={args.dte}  max_runs={args.max_runs}")

    client = create_client()

    out_path = _output_path(args.symbol, output_dir)
    print(f"  output:  {out_path}")
    print(f"  press Ctrl-C to stop\n")

    cycles = 0
    started = time.time()

    while not _stop_flag:
        try:
            record = _snapshot(client, args.symbol, args.strikes,
                               args.dte, args.window,
                               args.es_symbol if args.es_symbol else None)
        except Exception as e:
            print(f"  [{datetime.now(CENTRAL):%H:%M:%S}] FETCH ERROR: {e}",
                  file=sys.stderr)
            # Sleep and retry rather than crash — the loop tolerates
            # transient Schwab 502s and rate-limit blips.
            if _wait_with_stop(args.interval):
                break
            continue

        # Re-open path each cycle in case the date rolled (clock past midnight).
        out_path = _output_path(args.symbol, output_dir)
        with out_path.open("a") as f:
            f.write(json.dumps(record) + "\n")

        wall = record["top_wall"]
        wall_str = (f"wall {wall['strike']:.0f}@"
                    f"${wall['gex']/1e9:.0f}B  ({wall['delta_spot']:+.1f})"
                    if wall else "—")
        # ES print + basis when available so cross-refs to ES charts are explicit.
        es_str = ""
        if record["spot_es"] is not None:
            es_str = (f"  ES={record['spot_es']:.2f}  "
                      f"basis={record['es_basis']:+.1f}")
        print(f"  [{record['ts'][11:19]}] "
              f"SPX={record['spot']:.2f}{es_str}  "
              f"NetGEX={record['net_gex']/1e9:+.1f}B  "
              f"{record['regime'][:4]}  "
              f"top {wall_str}")

        cycles += 1
        if args.max_runs is not None and cycles >= args.max_runs:
            break

        if _wait_with_stop(args.interval):
            break

    duration = time.time() - started
    print(f"\nDone. {cycles} cycles in {duration:.1f}s. "
          f"Output: {out_path}")
    return 0


def _wait_with_stop(seconds: int) -> bool:
    """Sleep up to `seconds`, but bail early on SIGINT. Returns True if stopped."""
    end = time.time() + seconds
    while time.time() < end:
        if _stop_flag:
            return True
        time.sleep(0.5)
    return _stop_flag


if __name__ == "__main__":
    sys.exit(main())
