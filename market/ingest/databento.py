"""
Boundary layer: Databento Live API records -> typed market entities.

Databento streams typed messages (TradeMsg, MBP1Msg, OHLCVMsg, ...) from
its `databento_dbn` package. This module:

  1. Wraps the Databento `Live` client with a thin `LiveClient` that
     maintains the instrument_id ↔ symbol mapping the stream carries
     in `SymbolMappingMsg` records.
  2. Converts typed Databento records into Strader's market entities.

Timezone normalization to US/Central happens at this boundary, matching
the Schwab/Mancini convention.

Cost note: subscribing to a Databento Live stream incurs metered cost.
Callers are responsible for narrow subscriptions and prompt disconnect.
"""
from __future__ import annotations

import os
from typing import Iterator
from zoneinfo import ZoneInfo

from databento import Live
from databento_dbn import MBP1Msg, SymbolMappingMsg, TradeMsg

from market.entities.quote import Quote
from market.entities.trade import Trade

CENTRAL = ZoneInfo("America/Chicago")


def trade_from_databento(record: "TradeMsg", symbol_map: dict[int, str]) -> Trade:
    """Convert a Databento TradeMsg into a typed Trade entity.

    `symbol_map` resolves Databento's internal `instrument_id` to the raw
    symbol the caller subscribed with (e.g. "ES.c.0", "AAPL"). The Live
    stream delivers this mapping via `SymbolMappingMsg` records before
    any data records.
    """
    symbol = symbol_map.get(record.instrument_id, "")
    side_raw = record.side
    side = chr(side_raw) if isinstance(side_raw, int) else str(side_raw)
    if side not in ("B", "A", "N"):
        side = "N"

    return Trade(
        ts=record.pretty_ts_event.astimezone(CENTRAL),
        symbol=symbol,
        instrument_id=int(record.instrument_id),
        price=float(record.pretty_price),
        size=int(record.size),
        side=side,  # type: ignore[arg-type]
        sequence=int(seq) if (seq := getattr(record, "sequence", None)) is not None else None,
    )


def quote_from_databento(record: "MBP1Msg", symbol_map: dict[int, str]) -> Quote:
    """Convert a Databento MBP1Msg (top-of-book) into a typed Quote entity."""
    symbol = symbol_map.get(record.instrument_id, "")
    return Quote(
        ts=record.pretty_ts_event.astimezone(CENTRAL),
        symbol=symbol,
        instrument_id=int(record.instrument_id),
        bid_price=float(record.pretty_bid_px_00),
        bid_size=int(record.bid_sz_00),
        ask_price=float(record.pretty_ask_px_00),
        ask_size=int(record.ask_sz_00),
    )


class LiveClient:
    """Thin wrapper over `databento.Live` that yields typed entities.

    Usage:
        client = LiveClient()  # reads DATABENTO_API_KEY from env
        client.subscribe(dataset="GLBX.MDP3", schema="trades", symbols=["ES.c.0"])
        for trade in client.trades():
            ...

    The client maintains the symbol map automatically. Non-data records
    (SymbolMappingMsg, ErrorMsg, ...) are consumed silently; only typed
    entities reach the caller.
    """

    def __init__(self, key: str | None = None):
        resolved = key or os.getenv("DATABENTO_API_KEY")
        if not resolved:
            raise ValueError(
                "Databento API key not provided "
                "(pass key= or set DATABENTO_API_KEY env var)"
            )
        self._client = Live(key=resolved)
        self._symbol_map: dict[int, str] = {}

    def subscribe(
        self,
        dataset: str,
        schema: str,
        symbols: list[str],
        stype_in: str = "raw_symbol",
        start: str | None = None,
    ) -> None:
        """Add a subscription to the Live session.

        Multiple subscribe() calls accumulate. See Databento docs for valid
        (dataset, schema, stype_in) combinations.
        """
        self._client.subscribe(
            dataset=dataset,
            schema=schema,
            symbols=symbols,
            stype_in=stype_in,
            start=start,
        )

    def tee_raw(self, stream, exception_callback=None) -> None:
        """Tee the raw DBN byte stream to a writable binary IO — a lossless,
        compact archive of *every* record and field (sequence, flags, ns ts,
        SymbolMappingMsg) that the typed Trade projection drops.

        Call after subscribe() and before iterating. databento writes a
        complete DBN stream (metadata + records) to `stream`, replayable via
        `databento.DBNStore.from_file()`. All subscriptions on this session
        write to the same stream. The caller owns the handle (flush/close).
        """
        self._client.add_stream(stream, exception_callback=exception_callback)

    def trades(self) -> Iterator[Trade]:
        """Yield typed Trade entities. Blocks on the underlying stream.

        Symbol-mapping and other non-trade records are absorbed silently.
        Caller is responsible for breaking the loop (signal, count, timeout).
        """
        for record in self._client:
            if isinstance(record, SymbolMappingMsg):
                # stype_OUT resolves the parent/continuous input symbol to the
                # actual instrument (e.g. SPXW.OPT -> "SPXW  260608C05500000").
                # stype_in_symbol would collapse every contract to the parent.
                self._symbol_map[int(record.instrument_id)] = record.stype_out_symbol
                continue
            if isinstance(record, TradeMsg):
                yield trade_from_databento(record, self._symbol_map)

    def quotes(self) -> Iterator[Quote]:
        """Yield typed Quote entities (top-of-book snapshots) from MBP-1/TBBO.

        Symbol-mapping records are absorbed silently. Subscribe with schema
        'mbp-1' or 'tbbo' before iterating.
        """
        for record in self._client:
            if isinstance(record, SymbolMappingMsg):
                # stype_OUT resolves the parent/continuous input symbol to the
                # actual instrument (e.g. SPXW.OPT -> "SPXW  260608C05500000").
                # stype_in_symbol would collapse every contract to the parent.
                self._symbol_map[int(record.instrument_id)] = record.stype_out_symbol
                continue
            if isinstance(record, MBP1Msg):
                yield quote_from_databento(record, self._symbol_map)

    def close(self) -> None:
        """Disconnect from the gateway. Safe to call multiple times."""
        try:
            self._client.stop()
        except Exception:
            pass
