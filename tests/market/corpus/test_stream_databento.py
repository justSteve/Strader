"""Offline tests for the Databento LIVE corpus streamer.

No network, no metered cost: a FakeLiveClient yields canned trades and the
corpus root is redirected to a tmp dir. We verify the streamer produces rows
in the same schema as the T+1 batch puller (tagged source="live"), keeps the
manifest in step, honors the per-stream tick cap, writes nothing in probe
mode, flags unmapped symbols, and recovers across a mid-stream drop.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import market.corpus.paths as paths

CENTRAL = ZoneInfo("America/Chicago")
REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_streamer():
    """Import scripts/corpus_stream_databento.py as a module (not a package)."""
    path = REPO_ROOT / "scripts" / "corpus_stream_databento.py"
    spec = importlib.util.spec_from_file_location("corpus_stream_databento", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses needs the module discoverable
    spec.loader.exec_module(mod)
    return mod


streamer = _load_streamer()
D = date(2026, 6, 8)


class FakeTrade:
    """Stand-in for the typed Trade entity the streamer consumes."""
    def __init__(self, symbol, instrument_id, price, size, side, minute=0,
                 sequence=None):
        self.ts = datetime(2026, 6, 8, 13, minute, 0, tzinfo=CENTRAL)
        self.symbol = symbol
        self.instrument_id = instrument_id
        self.price = price
        self.size = size
        self.side = side
        self.sequence = sequence


class FakeQuote:
    """Stand-in for the typed Quote entity a book stream yields. [st-jy3i]"""
    def __init__(self, symbol, instrument_id, bid_price, bid_size,
                 ask_price, ask_size, minute=0):
        self.ts = datetime(2026, 6, 8, 13, minute, 0, tzinfo=CENTRAL)
        self.symbol = symbol
        self.instrument_id = instrument_id
        self.bid_price = bid_price
        self.bid_size = bid_size
        self.ask_price = ask_price
        self.ask_size = ask_size

    @property
    def mid(self):
        return (self.bid_price + self.ask_price) / 2.0


class FakeLiveClient:
    """Yields a fixed list of records, optionally raising after some of them.

    Serves both iterators: ``trades()`` for print streams and ``quotes()`` for
    book streams. A worker only ever calls the one its schema selects.
    """
    def __init__(self, trades, raise_after=None):
        self._trades = trades
        self._raise_after = raise_after
        self.closed = False
        self.raw_stream = None

    def subscribe(self, **kwargs):
        self.subscribe_kwargs = kwargs

    def tee_raw(self, stream, exception_callback=None):
        self.raw_stream = stream

    def _iter(self):
        for i, t in enumerate(self._trades):
            yield t
            if self._raise_after is not None and i + 1 >= self._raise_after:
                raise RuntimeError("simulated gateway drop")

    def trades(self):
        yield from self._iter()

    def quotes(self):
        yield from self._iter()

    def close(self):
        self.closed = True


@pytest.fixture
def corpus_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CORPUS_ROOT", tmp_path)
    return tmp_path


def _make_worker(spec, factory, **kw):
    kw.setdefault("raw", False)  # JSONL-only unless a test opts into raw
    return streamer.StreamWorker(
        spec, D, threading.Event(), threading.Lock(),
        flush_interval=0.0, client_factory=factory, **kw,
    )


def _read_rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_writes_corpus_rows_matching_batch_schema(corpus_tmp):
    spec = streamer.default_specs("trades")["opra"]
    trades = [
        FakeTrade("SPXW  260608C05500000", 101, 2.35, 4, "B", minute=1,
                  sequence=29785284),
        FakeTrade("SPXW  260608P05400000", 102, 1.10, 2, "A", minute=2),
        FakeTrade("SPXW  260608C05600000", 103, 0.55, 9, "N", minute=3),
    ]
    worker = _make_worker(spec, lambda: FakeLiveClient(trades), max_ticks=3)
    worker.run()

    out = paths.databento_path(D)
    rows = _read_rows(out)
    assert len(rows) == 3

    r = rows[0]
    assert r["stream"] == "databento_opra"
    assert r["provenance"]["source"] == "live"
    assert r["provenance"]["dataset"] == "OPRA.PILLAR"
    assert r["provenance"]["parent_symbol"] == "SPXW.OPT"
    assert r["provenance"]["ts_event"].endswith("+00:00")  # UTC, like batch
    assert r["data"]["symbol"] == "SPXW  260608C05500000"
    assert r["data"]["instrument_id"] == 101
    assert r["data"]["price"] == 2.35
    assert r["data"]["size"] == 4
    assert r["data"]["side"] == "B"
    assert r["data"]["action"] == "T"
    # The venue sequence rides through verbatim — the dedup key needs it
    # [st-n0qm.1]; a source without one still writes None (row 2).
    assert r["data"]["sequence"] == 29785284
    assert rows[1]["data"]["sequence"] is None

    manifest = json.loads(paths.manifest_path(D).read_text())
    assert manifest["streams"]["databento_opra"]["cycles"] == 3


def test_es_stream_uses_continuous_symbol_key(corpus_tmp):
    spec = streamer.default_specs("trades")["es"]
    trades = [FakeTrade("ES.c.0", 7, 5512.25, 1, "B")]
    worker = _make_worker(spec, lambda: FakeLiveClient(trades), max_ticks=1)
    worker.run()

    rows = _read_rows(paths.databento_glbx_es_path(D))
    assert rows[0]["provenance"]["continuous_symbol"] == "ES.c.0"
    assert rows[0]["provenance"]["dataset"] == "GLBX.MDP3"


def test_probe_mode_writes_nothing(corpus_tmp):
    spec = streamer.default_specs("trades")["opra"]
    trades = [FakeTrade("SPXW  X", 1, 1.0, 1, "B")] * 5
    worker = _make_worker(spec, lambda: FakeLiveClient(trades), max_ticks=2, probe=True)
    worker.run()

    assert worker.status.ticks == 2
    assert not paths.databento_path(D).exists()
    assert not paths.manifest_path(D).exists()


def test_unmapped_symbol_recorded_as_null(corpus_tmp):
    spec = streamer.default_specs("trades")["opra"]
    trades = [FakeTrade("", 999, 1.5, 3, "N")]  # symbol not yet resolved
    worker = _make_worker(spec, lambda: FakeLiveClient(trades), max_ticks=1)
    worker.run()

    rows = _read_rows(paths.databento_path(D))
    assert rows[0]["data"]["symbol"] is None
    assert rows[0]["data"]["instrument_id"] == 999
    assert worker.status.unmapped == 1


def test_reconnect_recovers_and_keeps_both_segments(corpus_tmp):
    spec = streamer.default_specs("trades")["opra"]
    seg1 = [FakeTrade("SPXW A", 1, 1.0, 1, "B"),
            FakeTrade("SPXW B", 2, 2.0, 1, "A")]
    seg2 = [FakeTrade("SPXW C", 3, 3.0, 1, "N"),
            FakeTrade("SPXW D", 4, 4.0, 1, "B"),
            FakeTrade("SPXW E", 5, 5.0, 1, "A")]
    clients = iter([
        FakeLiveClient(seg1, raise_after=2),  # drops after 2 trades
        FakeLiveClient(seg2),                 # clean end -> treated as drop
    ])
    worker = _make_worker(spec, lambda: next(clients), max_reconnects=1)
    worker.run()

    rows = _read_rows(paths.databento_path(D))
    assert len(rows) == 5                    # no data lost across the drop
    assert worker.status.ticks == 5
    assert worker.status.reconnects == 2     # one real drop + one clean-end drop
    assert any("possible gap" in e for e in worker.status.errors)


def test_raw_tee_creates_dbn_and_registers_stream(corpus_tmp):
    spec = streamer.default_specs("trades")["opra"]
    trades = [FakeTrade("SPXW A", 1, 1.0, 1, "B"),
              FakeTrade("SPXW B", 2, 2.0, 1, "A")]
    holder = {}

    def factory():
        holder["client"] = FakeLiveClient(trades)
        return holder["client"]

    worker = _make_worker(spec, factory, max_ticks=2, raw=True)
    worker.run()

    dbn = paths.databento_path(D).with_name("databento_opra.0.dbn")
    assert dbn.exists()                         # raw segment opened
    assert holder["client"].raw_stream is not None  # handed to add_stream/tee_raw


def test_raw_tee_segments_per_connection(corpus_tmp):
    spec = streamer.default_specs("trades")["opra"]
    clients = iter([
        FakeLiveClient([FakeTrade("A", 1, 1.0, 1, "B")], raise_after=1),
        FakeLiveClient([FakeTrade("B", 2, 2.0, 1, "A")]),
    ])
    worker = _make_worker(spec, lambda: next(clients), max_reconnects=1, raw=True)
    worker.run()

    ddir = paths.databento_path(D).parent
    segs = sorted(p.name for p in ddir.glob("databento_opra.*.dbn"))
    assert segs == ["databento_opra.0.dbn", "databento_opra.1.dbn"]


def test_probe_mode_skips_raw(corpus_tmp):
    spec = streamer.default_specs("trades")["opra"]
    trades = [FakeTrade("SPXW X", 1, 1.0, 1, "B")] * 3
    worker = _make_worker(spec, lambda: FakeLiveClient(trades),
                          max_ticks=2, probe=True, raw=True)
    worker.run()

    ddir = paths.databento_path(D).parent
    assert not ddir.exists() or not list(ddir.glob("*.dbn"))


# --- Phase B: the ES book stream [st-jy3i] ----------------------------------
# Absorption's refill_events needs MBP-1, and MBP-1 is never backfilled — it is
# captured forward from this stream or not at all. Two things must hold: the
# book stream reaches quotes() rather than trades(), and its rows land in the
# same shape the T+1 batch puller writes, so one file holds both sources.

def test_es_mbp1_spec_defaults_to_the_book_schema():
    specs = streamer.default_specs()
    assert specs["es"].schema == "trades"
    assert specs["es-mbp1"].schema == "mbp-1"
    assert specs["es-mbp1"].dataset == "GLBX.MDP3"
    assert specs["es-mbp1"].schema in streamer.BOOK_SCHEMAS
    # Trades and quotes must not collide in one file.
    assert specs["es"].out_path(D) != specs["es-mbp1"].out_path(D)


def test_global_schema_override_still_applies_to_every_stream():
    # Backward compatibility: --schema trades is how the pre-Phase-B callers
    # (and this module's other tests) drive the streamer.
    specs = streamer.default_specs("trades")
    assert {s.schema for s in specs.values()} == {"trades"}


def test_book_stream_writes_rows_matching_the_batch_mbp1_schema(corpus_tmp):
    spec = streamer.default_specs()["es-mbp1"]
    quotes = [
        FakeQuote("ESU6", 501, 7562.75, 12, 7563.00, 8, minute=1),
        FakeQuote("ESU6", 501, 7563.00, 3, 7563.25, 21, minute=2),
    ]
    worker = _make_worker(spec, lambda: FakeLiveClient(quotes), max_ticks=2)
    worker.run()

    rows = _read_rows(paths.databento_glbx_es_mbp1_path(D))
    assert len(rows) == 2

    r = rows[0]
    assert r["stream"] == "databento_glbx_es_mbp1"
    assert r["provenance"]["source"] == "live"
    assert r["provenance"]["dataset"] == "GLBX.MDP3"
    assert r["provenance"]["schema"] == "mbp-1"
    assert r["provenance"]["continuous_symbol"] == "ES.c.0"
    assert r["provenance"]["ts_event"].endswith("+00:00")

    d = r["data"]
    assert d["bid_px"] == 7562.75 and d["bid_sz"] == 12
    assert d["ask_px"] == 7563.00 and d["ask_sz"] == 8
    assert d["instrument_id"] == 501
    # Key names must match corpus_pull_databento_es_mbp1.py exactly, including
    # the columns the live Quote entity cannot fill.
    assert set(d) == {
        "symbol", "instrument_id", "action", "side", "price", "size",
        "bid_px", "ask_px", "bid_sz", "ask_sz", "bid_ct", "ask_ct",
        "sequence", "flags",
    }
    for absent in ("action", "side", "price", "size", "bid_ct", "ask_ct",
                   "sequence", "flags"):
        assert d[absent] is None

    manifest = json.loads(paths.manifest_path(D).read_text())
    assert manifest["streams"]["databento_glbx_es_mbp1"]["cycles"] == 2


def test_trade_stream_untouched_by_the_book_path(corpus_tmp):
    # The es spec must still go through trades() and keep the print row shape.
    spec = streamer.default_specs()["es"]
    trades = [FakeTrade("ESU6", 501, 7562.75, 5, "B", minute=1)]
    worker = _make_worker(spec, lambda: FakeLiveClient(trades), max_ticks=1)
    worker.run()

    d = _read_rows(paths.databento_glbx_es_path(D))[0]["data"]
    assert d["price"] == 7562.75 and d["size"] == 5 and d["action"] == "T"
    assert "bid_px" not in d
