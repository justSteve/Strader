"""``python -m strader.intent`` — one verb per line, a read-back after each. [st-79z.3]

    python -m strader.intent                      # a prompt; type or dictate lines
    python -m strader.intent --once "read b-day so far. mancini has ..."
    python -m strader.intent --speak              # read-backs rendered for the ear
    python -m strader.intent --chain FILE.json    # enables 'price' against a chain snapshot
    python -m strader.intent --day 2026-08-22 --plan-dir data/intent

Verbs: read, mark, call, arm, yes, no, fly, single, price, go, stand down, show, frame,
basis. A line with no known verb is read as dictation.

Chain snapshot format (a fixture, or a dump from the feed): {"underlying": "SPX",
"underlying_price": 6320.5, "expiry": "2026-08-22", "calls": [{"strike": 6300, "bid": 8.1,
"ask": 8.4, "delta": 0.62}, ...], "puts": [...]} — the fields Contract needs; missing
greeks default to 0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

from market.entities.chain import Chain, strike_key
from market.entities.instrument import Contract
from strader.intent.session import Session


def load_chain(path: Path) -> Chain:
    d = json.loads(path.read_text(encoding="utf-8"))
    expiry = dt.date.fromisoformat(d["expiry"])

    def mk(side: str, rows: list[dict]) -> dict[int, Contract]:
        out = {}
        for r in rows:
            k = float(r["strike"])
            out[strike_key(k)] = Contract(
                symbol=r.get("symbol", f"SPXW{expiry.strftime('%y%m%d')}{side[0]}{int(k * 1000):08d}"),
                underlying=d.get("underlying", "SPX"), strike=k, expiry=expiry, contract_type=side,
                bid=float(r["bid"]), ask=float(r["ask"]), last=float(r.get("last", (r["bid"] + r["ask"]) / 2)),
                volume=int(r.get("volume", 0)), open_interest=int(r.get("open_interest", 0)),
                delta=float(r.get("delta", 0.0)), gamma=float(r.get("gamma", 0.0)),
                theta=float(r.get("theta", 0.0)), vega=float(r.get("vega", 0.0)),
                implied_volatility=float(r.get("implied_volatility", 0.0)))
        return out

    return Chain(underlying=d.get("underlying", "SPX"), expiry=expiry,
                 calls=mk("CALL", d.get("calls", [])), puts=mk("PUT", d.get("puts", [])),
                 underlying_price=float(d["underlying_price"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the intent dialect — speak the day, read it back")
    ap.add_argument("--once", help="handle one line and exit")
    ap.add_argument("--speak", action="store_true", help="read-backs for the ear")
    ap.add_argument("--chain", help="chain snapshot JSON for 'price'")
    ap.add_argument("--day", help="YYYY-MM-DD (default today, Central)")
    ap.add_argument("--plan-dir", help="where the day's plan JSON lives (default data/intent)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    day = dt.date.fromisoformat(args.day) if args.day else None
    session = Session(plan_dir=Path(args.plan_dir) if args.plan_dir else None, day=day, speak=args.speak)
    chain = None
    if args.chain:
        p = Path(args.chain)
        if not p.is_file():
            print(f"intent: no such chain file: {p}", file=sys.stderr)
            return 2
        chain = load_chain(p)

    def handle(line: str) -> str:
        if line.strip().lower().startswith("price"):
            if chain is None:
                return "No chain loaded — start with --chain FILE.json to price."
            return session.price(chain)
        return session.handle(line)

    if args.once is not None:
        print(handle(args.once))
        return 0

    print(f"intent dialect — plan {session.path} — verbs: read mark call arm yes no fly single price go stand down show")
    try:
        while True:
            try:
                line = input("intent> ")
            except EOFError:
                break
            if line.strip().lower() in ("quit", "exit"):
                break
            print(handle(line))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
