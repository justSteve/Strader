"""ReplayMarket — the live side the paper book reads, served from a tape. [st-ug1h]

In production the paper book wraps the Schwab transport
(``execd/__main__.py``: ``ModeSwitch(PaperBroker(broker, book_path=...),
broker, mode)``): every read and the broker's preview go to Schwab, every
order stays in the book. Here the transport is this class. It answers the
reads the service and the order page make — ``quote``, ``chain``,
``market_read`` (quotes and Schwab-shaped chains), ``preview``,
``balances`` — from the tape at the clock's moment, and it refuses the four
calls that would trade: the book must never pass an order through to the
live side, and a scenario that makes it try fails loudly.

Every quote is a pure function of time (``quote_at``), which is what lets
the invariants ask "where was the bid when this stop was placed?" of any
order in the book after the fact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from execd.broker import (
    COMMISSION_PER_CONTRACT_USD, CONTRACT_MULTIPLIER, MARKET_READS, BrokerError, Preview, Quote,
)
from execd.intent import OrderIntent, OrderType, Side, parse_occ

from .tape import INDEX_HALF_SPREAD, Tape

INDEX = "$SPX"


class LiveSideTraded(AssertionError):
    """The paper book passed an order through to the live side."""


class ReplayMarket:
    """Broker-shaped reads over a :class:`~.tape.Tape`, advanced by ``clock``."""

    def __init__(self, tape: Tape, clock: Callable[[], datetime], *,
                 funds: float = 250_000.0) -> None:
        self.tape = tape
        self.clock = clock
        self.funds = funds
        #: a symbol whose quote read raises (a dead feed for one contract)
        self.dead: set[str] = set()
        self.reads = 0

    # ── the quote, as a function of time ─────────────────────────────────
    def quote_at(self, symbol: str, at: datetime) -> Quote:
        frame, as_of = self.tape.fresh(at)
        if symbol == INDEX:
            spx = frame.spx
            return Quote(INDEX, round(spx - INDEX_HALF_SPREAD, 2),
                         round(spx + INDEX_HALF_SPREAD, 2), spx, as_of)
        try:
            occ = parse_occ(symbol)
        except ValueError:
            raise BrokerError(f"replay: no quote for {symbol!r}") from None
        if occ.expiry != self.tape.expiry:
            raise BrokerError(f"replay: {symbol.strip()} is not on this tape's expiry")
        pinned = frame.quotes.get(symbol)
        if pinned is not None:
            bid, ask = pinned
            return Quote(symbol, float(bid), float(ask), round((bid + ask) / 2, 2), as_of)
        bid, ask, _delta = self.tape.model.quote(occ.right, occ.strike, frame.spx, as_of,
                                                 spread=frame.spread)
        return Quote(symbol, bid, ask, round((bid + ask) / 2, 2), as_of)

    def delta_at(self, symbol: str, at: datetime) -> float:
        frame, as_of = self.tape.fresh(at)
        if symbol in frame.deltas:
            return float(frame.deltas[symbol])
        occ = parse_occ(symbol)
        return self.tape.model.theo(occ.right, occ.strike, frame.spx, as_of)[1]

    # ── the Broker protocol's reads ──────────────────────────────────────
    def quote(self, symbol: str) -> Quote:
        self.reads += 1
        if symbol in self.dead:
            raise BrokerError(f"replay: the feed for {symbol.strip()} is down")
        return self.quote_at(symbol, self.clock())

    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]:
        return self._chain_maps(None)

    def market_read(self, kind: str, params: dict[str, str]) -> Any:
        self.reads += 1
        if kind not in MARKET_READS:
            raise BrokerError(f"replay: no such market read: {kind}")
        now = self.clock()
        if kind == "quotes":
            out: dict[str, Any] = {}
            for sym in str(params.get("symbols", "")).split(","):
                sym = sym.strip()
                if not sym:
                    continue
                q = self.quote_at(sym, now)
                ms = int(q.as_of.timestamp() * 1000)
                out[sym] = {"symbol": sym, "quote": {"bidPrice": q.bid, "askPrice": q.ask,
                                                     "lastPrice": q.last, "mark": q.mid,
                                                     "quoteTime": ms, "tradeTime": ms}}
            return out
        if kind == "chains":
            right = str(params.get("contractType", "ALL")).upper()
            maps = self._chain_maps(right if right in ("CALL", "PUT") else None)
            frame = self.tape.fresh(now)[0]
            spx = frame.chain_spx if frame.chain_spx is not None else frame.spx
            return {"symbol": params.get("symbol"), "status": "SUCCESS",
                    "underlyingPrice": spx,
                    "callExpDateMap": maps["calls"], "putExpDateMap": maps["puts"]}
        return {"symbol": params.get("symbol"), "candles": [], "empty": True}

    def _chain_maps(self, right: str | None) -> dict[str, Any]:
        now = self.clock()
        frame, as_of = self.tape.fresh(now)
        expiry = self.tape.expiry
        key = f"{expiry.isoformat()}:0"
        out: dict[str, Any] = {"calls": {key: {}}, "puts": {key: {}}}
        for r, mapname in (("CALL", "calls"), ("PUT", "puts")):
            if right is not None and r != right:
                continue
            for k in self.tape.strikes:
                sym = self.tape.symbol(r, k)
                q = self.quote_at(sym, now)
                delta = self.delta_at(sym, now)
                out[mapname][key][f"{k:.1f}"] = [{
                    "symbol": sym, "strikePrice": k,
                    "expirationDate": f"{expiry.isoformat()}T15:00:00-05:00",
                    "bid": q.bid, "ask": q.ask, "last": q.last, "delta": round(delta, 3),
                    "daysToExpiration": 0, "totalVolume": 1000, "openInterest": 500}]
        return out

    def preview(self, intent: OrderIntent) -> Preview:
        """The broker's own pricing of an order, the way the mock prices one:
        a buy never above its limit nor the offer."""
        q = self.quote(intent.symbol)
        if intent.order_type is OrderType.MARKET:
            px = q.ask if intent.side is Side.BUY_TO_OPEN else q.bid
        elif intent.order_type is OrderType.STOP:
            px = intent.stop_price or q.bid
        else:
            limit = intent.limit if intent.limit is not None else q.ask
            px = min(limit, q.ask) if intent.side is Side.BUY_TO_OPEN else max(limit, q.bid)
        return Preview(symbol=intent.symbol, side=intent.side, qty=intent.qty,
                       order_type=intent.order_type, price=px,
                       cost_usd=round(px * CONTRACT_MULTIPLIER * intent.qty, 2),
                       commission_usd=round(COMMISSION_PER_CONTRACT_USD * intent.qty, 2))

    def balances(self) -> dict[str, float | None]:
        return {"available_funds": self.funds, "option_buying_power": self.funds,
                "buying_power": self.funds, "cash_balance": self.funds,
                "liquidation_value": self.funds}

    # ── the four calls that would trade: never, from the paper book ──────
    def place(self, intent: OrderIntent):
        raise LiveSideTraded(f"the paper book sent {intent.intent_id} to the live side")

    def cancel(self, order_id: str):
        raise LiveSideTraded(f"the paper book sent a cancel of {order_id} to the live side")

    def orders(self):
        raise LiveSideTraded("the paper book read the live side's orders")

    def positions(self):
        raise LiveSideTraded("the paper book read the live side's positions")

    def fills_since(self, since):
        raise LiveSideTraded("the paper book read the live side's fills")
