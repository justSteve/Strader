"""FD0 feed adapter — live quotes and chain, or fixtures, behind one interface.

Design: ``docs/superpowers/specs/2026-08-02-fd0-flushdown-design.md``.
Bead: Cut And Await (st-apzt). Build-plan steps 3 and 4.

``compose.py`` and ``fd0.py`` take injected data and know nothing about where it
came from. This module is the only place that talks to a broker, which keeps the
arithmetic testable offline and keeps credentials out of the pure layer.

Read-only by construction. It fetches quotes and chains. There is no order path
here — that wall belongs to st-5ey and this module does not approach it.

Two implementations behind :class:`Feed`:

- :class:`SchwabFeed` — live, via ``broker_schwab.client.create_client``, which
  refuses to build without Steve's ``~/.schwab_gate_key``. This module does not
  work around that gate; it surfaces the message.
- :class:`FixtureFeed` — deterministic, from JSON on disk. Tests and replay.

It also carries :func:`spx_price_diagnostic`, which exists to settle a specific
open question rather than to be generally useful — see its docstring.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, Sequence

from strader.execution.compose import Budget, NoStrikeInBand, parse_chain, pick_strike
from strader.execution.fd0 import CheckLine, checklist

log = logging.getLogger(__name__)

__all__ = [
    "Quote", "Feed", "SchwabFeed", "FixtureFeed", "FeedError",
    "spx_price_diagnostic", "preflight", "SPX_SYMBOL",
]

# Schwab's symbol for the cash index. The '$' prefix is required; the bare
# form resolves to something else or 404s.
SPX_SYMBOL = "$SPX"


class FeedError(Exception):
    """The feed could not answer. Carries why, so the checklist can print it."""


@dataclass(frozen=True)
class Quote:
    symbol: str
    last: float | None
    bid: float | None
    ask: float | None
    mark: float | None
    at: datetime

    @property
    def midpoint(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid


class Feed(Protocol):
    def spx(self) -> Quote: ...
    def put_chain(self, *, dte: int = 0) -> dict: ...


# ------------------------------------------------------------------ live ---

class SchwabFeed:
    """Live read-only feed. Constructing it does not authenticate; the first
    call does, so a preflight failure is a caught exception rather than an
    import-time crash."""

    def __init__(self, symbol: str = SPX_SYMBOL):
        self.symbol = symbol
        self._client = None

    def _c(self):
        if self._client is None:
            try:
                from broker_schwab.client import create_client
                self._client = create_client()
            except Exception as exc:                      # gate key, .env, token
                raise FeedError(f"cannot create Schwab client: {exc}") from exc
        return self._client

    def spx(self) -> Quote:
        try:
            # get_quotes (plural) always: the singular form interpolates the
            # symbol into the URL path and 400s on '$SPX' (st-oit).
            r = self._c().get_quotes([self.symbol])
            r.raise_for_status()
            payload = r.json()
        except FeedError:
            raise
        except Exception as exc:
            raise FeedError(f"SPX quote failed: {exc}") from exc

        info = payload.get(self.symbol) or {}
        q = info.get("quote") or {}
        if not q:
            raise FeedError(f"SPX quote payload had no 'quote' block: {list(payload)}")

        return Quote(
            symbol=self.symbol,
            last=q.get("lastPrice"),
            bid=q.get("bidPrice"),
            ask=q.get("askPrice"),
            mark=q.get("mark"),
            at=datetime.now(),
        )

    def put_chain(self, *, dte: int = 0) -> dict:
        try:
            from schwab.client import Client
            r = self._c().get_option_chain(
                self.symbol,
                contract_type=Client.Options.ContractType.PUT,
            )
            r.raise_for_status()
            data = r.json()
        except FeedError:
            raise
        except Exception as exc:
            raise FeedError(f"option chain failed: {exc}") from exc

        if not data.get("putExpDateMap"):
            raise FeedError(f"chain returned no puts (status {data.get('status')!r})")
        return data


# --------------------------------------------------------------- fixture ---

class FixtureFeed:
    """Deterministic feed from files on disk. Used by tests and by replay.

    ``spx_ticks`` is consumed one call at a time so a caller can walk a tape;
    the last tick repeats once exhausted rather than raising, because a
    preflight that samples three times should not be the thing that ends a
    replay.
    """

    def __init__(self, chain_path: Path | str, spx_ticks: Sequence[float]):
        self.chain_path = Path(chain_path)
        self._ticks = list(spx_ticks)
        self._i = 0

    def spx(self) -> Quote:
        if not self._ticks:
            raise FeedError("FixtureFeed built with no SPX ticks")
        price = self._ticks[min(self._i, len(self._ticks) - 1)]
        self._i += 1
        return Quote(symbol=SPX_SYMBOL, last=price, bid=price - 0.05,
                     ask=price + 0.05, mark=price, at=datetime.now())

    def put_chain(self, *, dte: int = 0) -> dict:
        try:
            return json.loads(self.chain_path.read_text())
        except OSError as exc:
            raise FeedError(f"fixture chain unreadable: {exc}") from exc


# ------------------------------------------------------- mark diagnostic ---

def spx_price_diagnostic(quote: Quote) -> dict:
    """Answer one question with data: **is `mark` on the cash index usable?**

    Origin: on 2026-08-03 pre-market, a TOS confirm dialog showed
    ``SPX Last 7489.72  Bid 7440.83  Ask 7519.05`` — a 78-point spread on the
    index. If TOS derives a condition's ``mark`` from that midpoint, an
    SPX-conditional stop would trigger ~10 points off, against a stop distance
    near 1 point. Steve judged those quotes a pre-market artifact and deferred
    the check to the open; this makes the check automatic instead of visual.

    Returns the comparison rather than a verdict on TOS. Schwab's ``mark`` and
    thinkorswim's Method-``mark`` are not guaranteed to be the same quantity —
    what this establishes is whether the *underlying quote* is sane once the
    session is live, which is the precondition either way.
    """
    out = {
        "at": quote.at.isoformat(),
        "last": quote.last,
        "bid": quote.bid,
        "ask": quote.ask,
        "mark": quote.mark,
        "midpoint": quote.midpoint,
        "spread": quote.spread,
    }

    if quote.last is None:
        out["verdict"] = "no last price — cannot judge"
        return out

    if quote.spread is None:
        # Observed live 2026-08-03: Schwab returns no bid/ask for $SPX at all.
        # A cash index has no book, so this is the honest answer rather than a
        # gap — and it means any midpoint-derived quantity is fiction.
        out["verdict"] = (
            "no bid/ask on the cash index — there is no book to quote. "
            "Any midpoint-derived mark is fabricated; use last."
        )
    elif quote.spread > 5.0:
        out["verdict"] = (
            f"index bid/ask spread is {quote.spread:.2f} pts — synthetic. "
            "A midpoint-derived mark is not trustworthy here."
        )
    else:
        out["verdict"] = f"index bid/ask spread {quote.spread:.2f} pts — sane"

    if quote.mark is not None:
        out["mark_minus_last"] = round(quote.mark - quote.last, 2)
        out["mark_tracks_last"] = abs(quote.mark - quote.last) <= 1.0
    if quote.midpoint is not None:
        out["midpoint_minus_last"] = round(quote.midpoint - quote.last, 2)

    return out


# ------------------------------------------------------------- preflight ---

def preflight(
    feed: Feed,
    *,
    token_path: Path | str,
    budget: Budget,
    journal_path: Path,
    build_complete: bool = False,
    build_detail: str = "",
    tos_validated: bool = False,
    samples: int = 3,
) -> tuple[list[CheckLine], dict]:
    """Run the go/no-go checks against a live (or fixture) feed.

    Returns the checklist lines and a diagnostics blob. Never raises for feed
    failure — a dead feed is a FAIL line, which is the whole point of a
    preflight. ``build_complete`` and ``tos_validated`` default to **False**:
    they are human facts, and defaulting them to True would let an unverified
    morning render a clean checklist.
    """
    diag: dict = {}

    # 1. token
    try:
        from strader.schwab_token import assess_token
        health = assess_token(token_path)
        token_status, diag["token"] = health.status, health.to_dict()
    except Exception as exc:
        token_status = f"unreadable ({exc})"
        diag["token"] = {"error": str(exc)}

    # 2. quote stream — sample it, do not trust a single print
    ticks: list[tuple[datetime, float]] = []
    try:
        for _ in range(samples):
            q = feed.spx()
            if q.last is not None:
                ticks.append((q.at, q.last))
            diag.setdefault("spx_samples", []).append(spx_price_diagnostic(q))
    except FeedError as exc:
        diag["spx_error"] = str(exc)
        log.error("preflight: SPX feed failed: %s", exc)

    # 3. chain, and a strike actually inside the band
    chain_ok, chain_detail = False, "not fetched"
    try:
        chain = feed.put_chain()
        contracts = parse_chain(chain)
        try:
            pick = pick_strike(contracts)
            chain_ok = True
            chain_detail = (f"{pick.strike:g} put, |delta| {pick.abs_delta:.2f}, "
                            f"spread ${pick.spread_usd:.2f}")
            diag["pick"] = {"strike": pick.strike, "delta": pick.delta,
                            "bid": pick.bid_pts, "ask": pick.ask_pts}
        except NoStrikeInBand as exc:
            chain_detail = str(exc)
    except FeedError as exc:
        chain_detail = str(exc)
        log.error("preflight: chain failed: %s", exc)

    lines = checklist(
        token_status=token_status,
        spx_ticks=ticks,
        chain_ok=chain_ok,
        chain_detail=chain_detail,
        tos_validated=tos_validated,
        budget=budget,
        journal_path=journal_path,
        build_complete=build_complete,
        build_detail=build_detail,
    )
    return lines, diag


def main(argv: list[str] | None = None) -> int:
    """``python -m strader.execution.feed --probe`` — read-only diagnostics."""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--probe", action="store_true",
                    help="sample the SPX quote and report whether mark tracks last")
    ap.add_argument("--preflight", action="store_true", help="run the go/no-go checks")
    ap.add_argument("--fixture", type=Path, help="use a fixture chain instead of live")
    ap.add_argument("--token", type=Path, default=Path.home() / "schwab_token.json")
    ap.add_argument("--samples", type=int, default=3)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    feed: Feed = (FixtureFeed(args.fixture, [7440.25, 7440.5, 7440.75])
                  if args.fixture else SchwabFeed())

    if args.probe or not args.preflight:
        for _ in range(args.samples):
            try:
                print(json.dumps(spx_price_diagnostic(feed.spx()), indent=2))
            except FeedError as exc:
                print(f"FEED ERROR: {exc}")
                return 1

    if args.preflight:
        lines, diag = preflight(
            feed, token_path=args.token, budget=Budget(),
            journal_path=Path("data/exec/fd0-preflight.jsonl"),
        )
        print()
        for line in lines:
            print(line.render())
        print()
        print("  VERDICT:", "GO" if all(l.passed for l in lines) else "NO-GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
