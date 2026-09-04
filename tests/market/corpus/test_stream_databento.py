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
    book streams. A worker only ever calls the one its schema selects. The
    simulated drop is a ConnectionError — a transport failure, the class the
    worker reconnects on (see ``is_transport_error``).
    """
    def __init__(self, trades, raise_after=None, exc=None):
        self._trades = trades
        self._raise_after = raise_after
        self._exc = exc or ConnectionError("simulated gateway drop")
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
                raise self._exc

    def trades(self):
        yield from self._iter()

    def quotes(self):
        yield from self._iter()

    def close(self):
        self.closed = True


class RecordingEvent(threading.Event):
    """A stop event that records every wait it is asked for and never blocks —
    the backoff sequence is the thing under test, not the clock."""
    def __init__(self):
        super().__init__()
        self.waits: list[float] = []

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return self.is_set()


@pytest.fixture
def corpus_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CORPUS_ROOT", tmp_path)
    return tmp_path


def _make_worker(spec, factory, stop_event=None, **kw):
    kw.setdefault("raw", False)  # JSONL-only unless a test opts into raw
    return streamer.StreamWorker(
        spec, D, stop_event or threading.Event(), threading.Lock(),
        flush_interval=0.0, client_factory=factory, **kw,
    )


def _scripted(stop_event, clients):
    """A client_factory that hands out ``clients`` in order and, once they are
    spent, asks the worker to stop — a worker no longer gives up on the
    network, so a test that scripts N connections must end it explicitly."""
    it = iter(clients)

    def factory():
        try:
            return next(it)
        except StopIteration:
            stop_event.set()
            raise ConnectionError("script exhausted")
    return factory


def _read_rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def _manifest():
    return json.loads(paths.manifest_path(D).read_text())


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
    stop = RecordingEvent()
    worker = _make_worker(spec, _scripted(stop, [
        FakeLiveClient(seg1, raise_after=2),  # drops after 2 trades
        FakeLiveClient(seg2),                 # clean end -> treated as drop
    ]), stop_event=stop)
    worker.run()

    rows = _read_rows(paths.databento_path(D))
    assert len(rows) == 5                    # no data lost across the drop
    assert worker.status.ticks == 5
    # one real drop + one clean-end drop; the script running out sets the
    # stop event first, and a failure after a stop request is not a drop
    assert worker.status.reconnects == 2
    assert any("possible gap" in e for e in worker.status.errors)
    assert not worker.gave_up


def test_recovered_reconnect_is_not_gave_up(corpus_tmp):
    """A drop followed by a real recovery that runs to its own tick cap —
    this must NOT read as gave_up."""
    spec = streamer.default_specs("trades")["opra"]
    seg1 = [FakeTrade("SPXW A", 1, 1.0, 1, "B")]
    seg2 = [FakeTrade("SPXW B", 2, 2.0, 1, "A")]
    clients = iter([
        FakeLiveClient(seg1, raise_after=1),  # drops after 1 trade
        FakeLiveClient(seg2),
    ])
    worker = _make_worker(spec, lambda: next(clients), max_ticks=2)
    worker.run()

    assert worker.status.ticks == 2
    assert worker.status.reconnects == 1
    assert not worker.gave_up
    assert worker.outage is None


# --- Outages: the worker rides them out [co-8b60y, 2026-09-04] --------------
# A 42-hour network outage under the old six-attempt budget produced 1,624
# unit restarts and 6,466 manifest error entries per stream. The rules now:
# transport failures are retried with a 0 → 300 s backoff for as long as the
# window is open, the manifest carries ONE error and ONE note per outage, and
# only an error a retry cannot fix ends the worker.

def test_fifty_transport_failures_then_success_never_gives_up(corpus_tmp):
    spec = streamer.default_specs("trades")["es"]
    failures = iter(range(50))

    class Refusing(FakeLiveClient):
        def trades(self):
            raise ConnectionError("Connection to gateway timed out")
            yield  # noqa: unreachable — makes this a generator like the real one

    def factory():
        try:
            next(failures)
            return Refusing([])
        except StopIteration:
            return FakeLiveClient([FakeTrade("ES.c.0", 7, 5512.25, 1, "B")])

    stop = RecordingEvent()
    worker = _make_worker(spec, factory, stop_event=stop, max_ticks=1)
    worker.run()

    assert not worker.gave_up
    assert worker.outage is None                 # recovered on the first record
    assert worker.status.ticks == 1
    assert worker.status.reconnects == 50

    # The backoff: immediate, then doubling, capped at five minutes.
    expected = [0, 2, 4, 8, 16, 32, 64, 128, 256] + [300] * 41
    assert stop.waits == expected

    m = _manifest()
    s = m["streams"]["databento_glbx_es"]
    assert len(s["errors"]) == 1                 # one entry per outage, not per attempt
    assert s["errors"][0].startswith("reconnect #1: ")
    assert s["errors"][0].endswith("(possible gap)")
    assert s.get("errors_dropped") is None
    outage_notes = [n for n in m["notes"] if n.get("key", "").startswith("outage:")]
    assert len(outage_notes) == 1                # one line, rewritten in place
    assert "50 attempt(s), reconnected" in outage_notes[0]["note"]
    assert s["cycles"] == 1


def test_backoff_sequence_is_pure():
    b = streamer.backoff_seconds
    assert [b(n) for n in range(1, 12)] == [0, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300]
    assert b(1000) == streamer.MAX_BACKOFF_S == 300


def test_an_outage_open_at_window_close_is_closed_honestly(corpus_tmp):
    spec = streamer.default_specs("trades")["es"]
    stop = RecordingEvent()
    attempts = {"n": 0}

    def factory():
        attempts["n"] += 1
        if attempts["n"] >= 4:
            stop.set()                           # the window closes mid-outage
        raise ConnectionError("Connection to gateway failed: [Errno -3] "
                              "Temporary failure in name resolution")

    worker = _make_worker(spec, factory, stop_event=stop)
    worker.run()

    assert not worker.gave_up                    # an outage is not a failure of ours
    assert worker.outage is not None
    m = _manifest()
    s = m["streams"]["databento_glbx_es"]
    assert len(s["errors"]) == 1
    outage_notes = [n for n in m["notes"] if n.get("key", "").startswith("outage:")]
    assert len(outage_notes) == 1
    assert "3 attempt(s), stream ended without reconnecting" in outage_notes[0]["note"]
    assert m["notes"][-1]["note"].startswith("live stream ended — 0 ticks, 3 reconnect(s)")


def test_two_outages_keep_two_notes_and_two_errors(corpus_tmp):
    spec = streamer.default_specs("trades")["es"]
    stop = RecordingEvent()
    worker = _make_worker(spec, _scripted(stop, [
        FakeLiveClient([FakeTrade("ES.c.0", 7, 1.0, 1, "B")], raise_after=1),
        FakeLiveClient([FakeTrade("ES.c.0", 7, 2.0, 1, "B")], raise_after=1),
        FakeLiveClient([FakeTrade("ES.c.0", 7, 3.0, 1, "B")]),
    ]), stop_event=stop, max_ticks=3)
    worker.run()

    assert worker.status.ticks == 3
    assert worker.status.reconnects == 2
    m = _manifest()
    assert len(m["streams"]["databento_glbx_es"]["errors"]) == 2
    outage_notes = [n for n in m["notes"] if n.get("key", "").startswith("outage:")]
    assert len(outage_notes) == 2
    assert all("1 attempt(s), reconnected" in n["note"] for n in outage_notes)
    assert len({n["key"] for n in outage_notes}) == 2


def test_a_fatal_error_gives_up_at_once_with_a_fatal_entry(corpus_tmp):
    """A bad key is a ValueError from the client's own validation: retrying
    cannot fix it, so the worker ends and main() exits 1 for the unit."""
    spec = streamer.default_specs("trades")["es"]
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        raise ValueError("invalid API key, was db-xxxx")

    stop = RecordingEvent()
    worker = _make_worker(spec, factory, stop_event=stop)
    worker.run()

    assert worker.gave_up
    assert calls["n"] == 1                       # no retry
    assert stop.waits == []                      # no backoff
    assert worker.status.reconnects == 0
    s = _manifest()["streams"]["databento_glbx_es"]
    assert len(s["errors"]) == 1
    assert s["errors"][0].startswith("fatal: ValueError: invalid API key")
    # NOT the transport prefix: the gate must keep reading this as a real error.
    assert not s["errors"][0].startswith("reconnect #")


def test_a_fatal_error_during_an_outage_leaves_both_records(corpus_tmp):
    spec = streamer.default_specs("trades")["es"]
    stop = RecordingEvent()
    worker = _make_worker(spec, _scripted(stop, [
        FakeLiveClient([], exc=ConnectionError("dropped")),   # clean end -> drop
        FakeLiveClient([FakeTrade("ES.c.0", 7, 1.0, 1, "B")],
                       raise_after=1, exc=RuntimeError("row code bug")),
    ]), stop_event=stop)
    worker.run()

    assert worker.gave_up
    m = _manifest()
    s = m["streams"]["databento_glbx_es"]
    kinds = sorted(e.split(":")[0] for e in s["errors"])
    assert kinds == ["fatal", "reconnect #1"]
    # The outage recovered (one record arrived) before the bug hit.
    outage_notes = [n for n in m["notes"] if n.get("key", "").startswith("outage:")]
    assert len(outage_notes) == 1 and "reconnected" in outage_notes[0]["note"]


def test_bookkeeping_commits_do_not_advance_last_pull(corpus_tmp):
    """The gate reads last_pull_utc as 'the tape reaches here'. A reconnect
    attempt that pulled nothing must not move it past the close."""
    spec = streamer.default_specs("trades")["es"]
    stop = RecordingEvent()
    seen = {}

    real_update = streamer.update_manifest

    def spy(**kw):
        seen.setdefault("touch", []).append(kw.get("touch_last_pull"))
        return real_update(**kw)

    import unittest.mock as mock
    with mock.patch.object(streamer, "update_manifest", spy):
        worker = _make_worker(spec, _scripted(stop, [
            FakeLiveClient([FakeTrade("ES.c.0", 7, 1.0, 1, "B")], raise_after=1),
        ]), stop_event=stop)
        worker.run()

    # start note (no ticks), the drop's outage note (no ticks), the script
    # running out (no ticks), the end note: only the commit that carried the
    # tick advanced the field — and it is the drop commit, which flushed the
    # one tick that had landed.
    assert True in seen["touch"] and False in seen["touch"]
    assert seen["touch"][0] is False             # the start note pulled nothing
    assert "last_pull_utc" in _manifest()["streams"]["databento_glbx_es"]


# --- Which errors are the network [co-8b60y] --------------------------------
# databento 0.78.0 wraps every socket/timeout failure into BentoError(<text>)
# `from None`, so the text is the only signal that survives; the transport
# texts below were read in its session.py and one of them was measured 5,544
# times per stream during the 2026-09-02..04 outage.

class BentoError(Exception):
    """Same name as databento.common.error.BentoError — the classifier keys
    on the name so this module stays importable without the vendor package."""


@pytest.mark.parametrize("exc", [
    ConnectionError("simulated gateway drop"),
    ConnectionResetError("reset"),
    TimeoutError("socket timeout"),
    OSError(-9, "Address family for hostname not supported"),
    EOFError(),
    BentoError("Connection to glbx-mdp3.lsg.databento.com:13000 timed out after 10.0 second(s)."),
    BentoError("Connection to glbx-mdp3.lsg.databento.com:13000 failed: [Errno -3] Temporary failure in name resolution"),
    BentoError("Gateway timeout: 40 second(s) since last message"),
    BentoError("connection lost"),
    BentoError("Authentication with glbx-mdp3.lsg.databento.com:13000 timed out after 30.0 second(s)."),
    BentoError("queue is not enabled after 5 second(s)"),
    BentoError("some text this file has never seen"),   # unknown gateway text: keep trying
])
def test_transport_errors_are_retried(exc):
    assert streamer.is_transport_error(exc) is True


@pytest.mark.parametrize("exc", [
    ValueError("invalid API key, was db-xxxx"),
    ValueError("Databento API key not provided (pass key= or set DATABENTO_API_KEY env var)"),
    TypeError("bad argument"),
    AttributeError("'NoneType' object has no attribute 'price'"),
    KeyError("symbol"),
    RuntimeError("row code bug"),
    BentoError("Authentication failed: invalid API key"),
    BentoError("CRAM auth failed"),
    BentoError("Unauthorized: not entitled to GLBX.MDP3"),
    BentoError("invalid dataset OPRA.PILLAR for this subscription"),
])
def test_errors_a_retry_cannot_fix_give_up(exc):
    assert streamer.is_transport_error(exc) is False


def test_the_real_bento_error_class_is_recognised():
    real = pytest.importorskip("databento.common.error")
    assert streamer.is_transport_error(real.BentoError("connection lost")) is True
    assert streamer.is_transport_error(real.BentoError("Authentication failed")) is False


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
    stop = RecordingEvent()
    worker = _make_worker(spec, _scripted(stop, [
        FakeLiveClient([FakeTrade("A", 1, 1.0, 1, "B")], raise_after=1),
        FakeLiveClient([FakeTrade("B", 2, 2.0, 1, "A")]),
    ]), stop_event=stop, raw=True)
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
