#!/usr/bin/env python3
"""Corpus Databento LIVE streamer — append trade ticks during the session.

Companion to the T+1 batch puller (`corpus_pull_databento.py`). Where the
batch script pulls a finished day after the close, this daemon connects to
the Databento *Live* gateway during the session and appends trade ticks to
the corpus in real time.

Rows are written in the SAME schema and the SAME per-day files as the batch
puller so the corpus stays homogeneous — `databento_opra.jsonl` for SPXW
options, `databento_glbx_es.jsonl` for ES futures — with one extra marker,
`provenance.source = "live"`, so a consumer can tell a live-collected row
from a T+1 batch row.

One worker per stream
---------------------
A Databento Live session is bound to a single dataset, so OPRA.PILLAR and
GLBX.MDP3 cannot share one connection. Each requested stream therefore runs
on its own worker thread with its own `LiveClient`, its own file handle, and
independent reconnect handling. The shared manifest is updated under a lock.

`es` and `es-mbp1` are two sessions against the SAME dataset rather than one
session carrying both schemas. `DatabentoLive.events()` could interleave them,
but a worker owns exactly one output file, and trades and quotes belong in
different corpus files. Two workers keeps the file-per-stream invariant.

Cost
----
GLBX/ES live is covered by a flat subscription — the CME Standard plan added
2026-08-01, verified live 2026-08-03. It incurs no per-GB charge.

OPRA live is NOT. The $199 OPRA Equity Options plan was replaced by the
CME/Futures plan, confirmed on the portal 2026-08-04 (st-7av4) — so `opra`
here names a subscription the account no longer holds, and streaming it would
fall to pay-as-you-go rather than being sub-covered. Options tape is now pulled
retrospectively on demand (`corpus_backfill_databento.py --opra`) for specific
sessions worth assessing, not collected forward.

Do NOT quote `metadata.list_unit_prices` as the cost of the *subscribed*
streams: that endpoint returns pay-as-you-go list rates, and it returns them
identically whether or not the account is subscribed. Historical (batch) pulls
remain usage-rated; subscribed live is not. Note the trap that reading applies
only to plans actually held — it was written when OPRA was one of them.

`--probe`, `--max-ticks`, and `--max-seconds` are for mechanical validation
and scope control, not cost gating.

Outages (revised 2026-09-04, co-8b60y)
--------------------------------------
A worker never gives up on the network. When the connection drops or cannot
be made it reconnects with a backoff of 0, 2, 4, … 256, 300 s (capped at five
minutes) for as long as the window is open, and the manifest carries ONE
error entry and ONE note per outage — the note rewritten in place with the
attempt count, then closed as "reconnected" or "stream ended without
reconnecting". The old rule gave up after six attempts (~90 s) and exited 1,
which the unit restarted two seconds later: a 42-hour outage produced 1,624
restarts and 6,466 error entries per stream. The only errors that end a
worker are the ones a retry cannot fix — a bad key, a rejected subscription,
a bug in this file (`is_transport_error`). Those exit 1 so the unit's
stretching restart (30 s → 5 min) handles them, loudly.

Persistence (two layers)
------------------------
1. Lossless archive (source of truth) — the raw DBN byte stream is teed to
   `databento_opra.{N}.dbn`, one segment per connection (reconnects/relaunches
   never clobber). Carries every field and record type — sequence, flags,
   nanosecond ts, SymbolMappingMsg — and is replayable via
   `databento.DBNStore.from_file()`. T+1 `corpus_compact_databento.py`
   zstd-packs it to `.dbn.zst` (still DBNStore-readable). Disable with --no-raw.
2. Working copy — the typed-Trade JSONL projection (`databento_opra.jsonl`),
   schema-matched to the batch puller so existing tooling just works. Carries
   symbol/instrument_id/price/size/side and nanosecond event ts; `action` is
   "T" and `sequence`/`flags` are null here (recover them from the DBN
   archive if microstructure dedup ever needs them).

Usage
-----
    # Probe the firehose for 30s — write nothing, just report volume
    .venv/bin/python scripts/corpus_stream_databento.py --probe 30

    # Stream OPRA (default) for the late-day window (waits until 13:00 CT)
    .venv/bin/python scripts/corpus_stream_databento.py

    # Start now, hard stop at 15:00 CT or 500k ticks
    .venv/bin/python scripts/corpus_stream_databento.py \\
        --now --max-ticks 500000
"""
from __future__ import annotations

import argparse
import json
import re
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date as _date, datetime, time as _time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import (  # noqa: E402
    central_date,
    databento_glbx_es_mbp1_path,
    databento_glbx_es_path,
    databento_path,
    day_dir,
)
from market.corpus.writer import update_manifest, utc_now_iso  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def _load_env() -> None:
    """Validate DATABENTO_API_KEY and publish the clean value to os.environ so
    db.Live() (which reads the key from the environment) sees the authoritative
    token. Routes through the shared fail-fast loader instead of an ad-hoc parse
    — the .env file wins over any polluted process env, and a malformed key
    fails loudly here rather than as an opaque gateway error (2026-06-30
    invalid_client class of bug). [st-cir]"""
    from strader.settings import load_databento

    load_databento()


def _ct_to_dt(d: _date, hhmm: str) -> datetime:
    """Combine a CT date + HH:MM[:SS] clock-time into an aware Central datetime.

    Seconds are accepted so a window can end at 23:59:59 — the evening capture
    (st-9olq) runs to the end of the calendar day and the next calendar day's
    early capture picks up at 00:00, one process per day directory.
    """
    parts = [int(x) for x in hhmm.split(":")]
    if len(parts) == 2:
        parts.append(0)
    h, m, sec = parts
    return datetime.combine(d, _time(h, m, sec), tzinfo=CENTRAL)


# --------------------------------------------------------------------------
# Stream specs
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class StreamSpec:
    """One Databento Live subscription bound to one corpus file."""
    name: str                       # corpus stream key + manifest key
    dataset: str
    schema: str
    symbols: list[str]
    stype_in: str
    out_path: Callable[[_date], Path]

    @property
    def symbol_key(self) -> str:
        """Provenance key name matching the batch puller's convention."""
        return {
            "parent": "parent_symbol",
            "continuous": "continuous_symbol",
        }.get(self.stype_in, "symbol")


#: Schemas whose records are top-of-book snapshots rather than prints. These
#: are consumed through ``quotes()`` and serialised with the book row shape.
BOOK_SCHEMAS = ("mbp-1", "tbbo")


def default_specs(schema: str | None = None) -> dict[str, StreamSpec]:
    """The named streams, each carrying its own natural schema. [st-jy3i]

    ``schema`` is a manual override applied to every stream — useful for
    probing one schema across the board, wrong for normal operation. Leave it
    None so ``es-mbp1`` keeps ``mbp-1`` while the trade streams keep ``trades``;
    a single global schema is exactly what stopped trades and quotes running
    together before Phase B.
    """
    def _schema(natural: str) -> str:
        return schema or natural

    return {
        "opra": StreamSpec(
            name="databento_opra",
            dataset="OPRA.PILLAR",
            schema=_schema("trades"),
            symbols=["SPXW.OPT"],
            stype_in="parent",
            out_path=databento_path,
        ),
        "es": StreamSpec(
            name="databento_glbx_es",
            dataset="GLBX.MDP3",
            schema=_schema("trades"),
            symbols=["ES.c.0"],
            stype_in="continuous",
            out_path=databento_glbx_es_path,
        ),
        # Phase B (st-d5f): the book stream absorption's refill_events needs.
        # Quotes are NEVER backfilled — captured forward from here or not at all.
        "es-mbp1": StreamSpec(
            name="databento_glbx_es_mbp1",
            dataset="GLBX.MDP3",
            schema=_schema("mbp-1"),
            symbols=["ES.c.0"],
            stype_in="continuous",
            out_path=databento_glbx_es_mbp1_path,
        ),
    }


# --------------------------------------------------------------------------
# Error classification — the network, or something a retry cannot fix
# --------------------------------------------------------------------------

#: Longest wait between reconnect attempts inside one outage, in seconds.
MAX_BACKOFF_S = 300

#: Gateway texts that mean the network or the gateway is unreachable. Every
#: one of these was read in databento 0.78.0's live client (session.py,
#: protocol.py), which wraps the underlying OSError/timeout into a BentoError
#: with `from None` — so the text is the only signal that survives. Measured
#: 2026-09-02..04: 5,544 copies per stream of "Connection to
#: glbx-mdp3.lsg.databento.com:13000 timed out after 10.0 second(s)."
_TRANSPORT_TEXT = re.compile(
    r"timed out|timeout|connection lost|connection closed|connection to .+ failed"
    r"|since last message|no data received|queue is not enabled"
    r"|name resolution|address family|network is unreachable|connection refused"
    r"|connection reset|broken pipe|\beof\b",
    re.IGNORECASE,
)
#: Gateway texts that say the credentials or the request are wrong. A CRAM
#: rejection arrives as BentoError(<gateway's error text>) and a gateway
#: ErrorMsg record's text is attached to the disconnect the same way. The
#: exact phrasings are the gateway's and were not measured here; the patterns
#: are the vocabulary of the API's documented failures, checked only after the
#: transport patterns above have been ruled out.
_FATAL_TEXT = re.compile(
    r"authentication (?:failed|error|rejected)|auth failed|invalid (?:api )?key"
    r"|api key|unauthori[sz]ed|forbidden|not authori[sz]ed|not entitled|entitlement"
    r"|permission|not subscribed|subscription|invalid (?:dataset|schema|symbol"
    r"|stype|request)|unknown dataset|unsupported|bad request|malformed",
    re.IGNORECASE,
)


def is_transport_error(exc: BaseException) -> bool:
    """True when the failure is the network or the gateway being unreachable —
    the worker keeps trying. False when a retry cannot help — a bad key, a
    rejected subscription, a wrong argument, a bug — the worker gives up and
    the unit restarts it on its stretching schedule.

    OSError covers sockets, DNS (gaierror), SSL and timeouts (TimeoutError is
    an OSError since 3.3). A BentoError is judged by its text, transport
    patterns first — "Authentication with … timed out" is a timeout, not a
    rejection. A BentoError whose text matches neither list is treated as
    transport: the cost of a wrong "give up" is the restart storm this
    function exists to end, and the outage note names the text so an unknown
    shape is still visible. Anything else — ValueError from the client's key
    validation, an AttributeError in our own row code — is not the network.
    """
    if isinstance(exc, (OSError, EOFError)):
        return True
    if any(k.__name__ == "BentoError" for k in type(exc).__mro__):
        text = str(exc)
        if _TRANSPORT_TEXT.search(text):
            return True
        if _FATAL_TEXT.search(text):
            return False
        return True
    return False


def backoff_seconds(attempt: int) -> int:
    """Wait before reconnect attempt ``attempt + 1`` of an outage: the first
    retry is immediate, then 2, 4, 8 … doubling to ``MAX_BACKOFF_S``."""
    if attempt <= 1:
        return 0
    return min(2 ** (attempt - 1), MAX_BACKOFF_S)


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------

@dataclass
class WorkerStatus:
    """Mutable counters a worker exposes for the status line + manifest."""
    ticks: int = 0
    reconnects: int = 0
    unmapped: int = 0          # trades whose symbol wasn't resolved
    errors: list[str] = field(default_factory=list)
    last_symbol: str = ""
    last_price: float = 0.0
    last_ts: str = ""


@dataclass
class Outage:
    """One stretch without a working connection: from the first drop until
    the first record after it. Its manifest note is keyed on ``since`` so
    every attempt rewrites the same line instead of adding one."""
    since: str                  # UTC ISO of the first drop
    ordinal: int = 1            # the worker's Nth outage this run
    attempts: int = 1           # connection attempts that failed so far
    reason: str = ""            # the latest failure's text

    @property
    def key(self) -> str:
        # The ordinal, not the timestamp: two outages can open in one second
        # (drop, one record, drop) and must not share a line.
        return f"outage:{self.ordinal}:{self.since}"

    def open_note(self) -> str:
        return f"outage since {self.since}, {self.attempts} attempt(s): {self.reason}"


def _client_factory_default():
    # Imported lazily so the module imports without a live databento env
    # (and so tests can monkeypatch before any client is built).
    from market.ingest.databento import LiveClient
    return LiveClient()


class StreamWorker(threading.Thread):
    """Stream one dataset to one corpus file until stop_event is set."""

    COMMIT_INTERVAL = 10.0          # seconds between manifest count commits

    def __init__(
        self,
        spec: StreamSpec,
        d: _date,
        stop_event: threading.Event,
        manifest_lock: threading.Lock,
        *,
        flush_interval: float = 2.0,
        max_ticks: int | None = None,
        probe: bool = False,
        raw: bool = True,
        client_factory: Callable[[], object] = _client_factory_default,
    ):
        super().__init__(name=spec.name, daemon=True)
        self.spec = spec
        self.d = d
        self.stop_event = stop_event
        self.manifest_lock = manifest_lock
        self.flush_interval = flush_interval
        self.max_ticks = max_ticks
        self.probe = probe
        self.raw = raw                  # tee lossless raw DBN alongside JSONL
        self.client_factory = client_factory

        self.status = WorkerStatus()
        self._client = None
        self._client_lock = threading.Lock()
        self._committed = 0
        self._fh = None
        self._raw_fh = None             # raw DBN handle for the current segment
        self._done = threading.Event()  # this stream finished on its own terms
        self._outage: Outage | None = None
        self._outages_seen = 0
        self._gave_up = False

    # -- lifecycle -------------------------------------------------------

    @property
    def gave_up(self) -> bool:
        """True once this stream stopped on an error a retry cannot fix (see
        ``is_transport_error``) — as opposed to stop_event (scheduled or
        signalled stop) or _done (own tick cap). A network outage never sets
        it. main() needs the distinction: a stream that dies on a bad key must
        not look like a clean scheduled stop, or systemd's Restart=on-failure
        never sees a reason to fire."""
        return self._gave_up

    @property
    def outage(self) -> Outage | None:
        """The outage in progress, or None while the connection is working."""
        return self._outage

    def shutdown(self) -> None:
        """Unblock the record iterator from another thread."""
        with self._client_lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass

    def run(self) -> None:
        if not self.probe:
            out = self.spec.out_path(self.d)
            out.parent.mkdir(parents=True, exist_ok=True)
            self._fh = out.open("a")
        try:
            self._stream_with_reconnect()
        finally:
            self._flush()
            if self._fh is not None:
                self._fh.close()
            if not self.probe:
                # Errors were committed when they happened (_drop, _give_up,
                # _on_raw_error); re-sending status.errors here is what put a
                # second copy of every reconnect line into the manifest.
                if self._outage is not None:
                    o = self._outage
                    self._commit_counts(
                        note=f"outage since {o.since}, {o.attempts} attempt(s), "
                             f"stream ended without reconnecting: {o.reason}",
                        note_key=o.key,
                    )
                self._commit_counts(
                    note=f"live stream ended — {self.status.ticks} ticks, "
                         f"{self.status.reconnects} reconnect(s)",
                )

    # -- streaming -------------------------------------------------------

    def _stream_with_reconnect(self) -> None:
        first = True
        while not self.stop_event.is_set() and not self._done.is_set():
            try:
                client = self.client_factory()
                client.subscribe(
                    dataset=self.spec.dataset,
                    schema=self.spec.schema,
                    symbols=self.spec.symbols,
                    stype_in=self.spec.stype_in,
                )
                with self._client_lock:
                    self._client = client
                if self.raw and not self.probe:
                    self._open_raw(client)
                if not self.probe and first:
                    self._commit_counts(
                        note=f"live stream start — {self.spec.dataset} "
                             f"{self.spec.schema} {self.spec.symbols}")
                first = False
                self._consume(client)
                # Clean end of iterator without an exception => either we
                # hit our own cap (_done) / were asked to stop, or the
                # server hung up. The former two are deliberate; the latter
                # is a drop we should reconnect on.
                if self.stop_event.is_set() or self._done.is_set():
                    break
                self._drop("stream ended unexpectedly")
            except Exception as e:
                if self.stop_event.is_set():
                    break
                if is_transport_error(e):
                    self._drop(f"{type(e).__name__}: {e}")
                else:
                    self._give_up(e)
                    break
            finally:
                with self._client_lock:
                    if self._client is not None:
                        try:
                            self._client.close()
                        except Exception:
                            pass
                    self._client = None
                self._close_raw()

            # Only a drop reaches here (a clean stop and a give-up both break
            # above), so an outage is always open at this point. Wait out its
            # backoff — interruptible, so a window close during a five-minute
            # wait still ends the worker promptly.
            self.stop_event.wait(backoff_seconds(self._outage.attempts))

    def _consume(self, client) -> None:
        last_flush = time.monotonic()
        last_commit = time.monotonic()
        # A book stream yields top-of-book snapshots, not prints: different
        # iterator, different row shape, same bookkeeping. [st-jy3i]
        is_book = self.spec.schema in BOOK_SCHEMAS
        records = client.quotes() if is_book else client.trades()
        for rec in records:
            if self.stop_event.is_set() or self._done.is_set():
                break
            if self._outage is not None:
                # The first record after a drop is the recovery — a connection
                # that authenticates and then yields nothing has not recovered.
                self._recover()

            self.status.ticks += 1
            self.status.last_symbol = rec.symbol or "?"
            # A quote has no single price; mid is the honest one-number summary
            # and is only ever used for the status line.
            self.status.last_price = rec.mid if is_book else rec.price
            self.status.last_ts = rec.ts.isoformat()
            if not rec.symbol:
                self.status.unmapped += 1

            if not self.probe:
                self._fh.write(self._book_row(rec) if is_book else self._row(rec))
                now = time.monotonic()
                if now - last_flush >= self.flush_interval:
                    self._fh.flush()
                    last_flush = now
                if now - last_commit >= self.COMMIT_INTERVAL:
                    self._commit_counts()
                    last_commit = now

            if self.max_ticks is not None and self.status.ticks >= self.max_ticks:
                self._done.set()
                break

    def _row(self, trade) -> str:
        rec = {
            "ts_pull_utc": utc_now_iso(),
            "stream": self.spec.name,
            "provenance": {
                "dataset": self.spec.dataset,
                "schema": self.spec.schema,
                self.spec.symbol_key: self.spec.symbols[0],
                "stype_in": self.spec.stype_in,
                "ts_event": trade.ts.astimezone(UTC).isoformat(),
                "source": "live",
            },
            "data": {
                "symbol": trade.symbol or None,
                "instrument_id": trade.instrument_id,
                "price": trade.price,
                "size": trade.size,
                "side": trade.side,
                "action": "T",
                # The venue sequence the Trade already carries (ingest/databento.py
                # trade_from_databento). It was written as None until 2026-08-16,
                # which collapsed replay.dedup_key to ts_event alone and dropped
                # distinct prints sharing a nanosecond — 3.42 % of 08-14 volume
                # [st-n0qm.1, plan §1]. Batch rows carry the same int.
                "sequence": getattr(trade, "sequence", None),
                "flags": None,
            },
        }
        return json.dumps(rec, default=str) + "\n"

    def _book_row(self, q) -> str:
        """Serialise a top-of-book snapshot. [st-jy3i]

        Key names match `corpus_pull_databento_es_mbp1.py` exactly so live and
        T+1 rows land in one homogeneous file. The fields the live Quote entity
        does not carry — order counts, sequence, flags, and the trade-side
        columns MBP-1 populates only on a trade event — are written null and
        recovered from the raw DBN archive if microstructure work ever needs
        them, the same contract the trade rows already use.
        """
        rec = {
            "ts_pull_utc": utc_now_iso(),
            "stream": self.spec.name,
            "provenance": {
                "dataset": self.spec.dataset,
                "schema": self.spec.schema,
                self.spec.symbol_key: self.spec.symbols[0],
                "stype_in": self.spec.stype_in,
                "ts_event": q.ts.astimezone(UTC).isoformat(),
                "source": "live",
            },
            "data": {
                "symbol": q.symbol or None,
                "instrument_id": q.instrument_id,
                "action": None,
                "side": None,
                "price": None,
                "size": None,
                "bid_px": q.bid_price,
                "ask_px": q.ask_price,
                "bid_sz": q.bid_size,
                "ask_sz": q.ask_size,
                "bid_ct": None,
                "ask_ct": None,
                "sequence": None,
                "flags": None,
            },
        }
        return json.dumps(rec, default=str) + "\n"

    # -- bookkeeping -----------------------------------------------------

    def _flush(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
            except Exception:
                pass

    # -- raw DBN archive -------------------------------------------------

    def _next_raw_path(self) -> Path:
        """`databento_opra.{N}.dbn` next to the JSONL, lowest free N. One
        segment per connection — reconnects/relaunches never clobber, and a
        DBNStore reader gets a clean single-stream file per segment."""
        jsonl = self.spec.out_path(self.d)
        stem = (jsonl.name[:-len(".jsonl")]
                if jsonl.name.endswith(".jsonl") else jsonl.stem)
        n = 0
        while (jsonl.parent / f"{stem}.{n}.dbn").exists():
            n += 1
        return jsonl.parent / f"{stem}.{n}.dbn"

    def _open_raw(self, client) -> None:
        path = self._next_raw_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_fh = path.open("wb")
        client.tee_raw(self._raw_fh, exception_callback=self._on_raw_error)
        print(f"  raw DBN archive -> {path.name}", flush=True)

    def _close_raw(self) -> None:
        if self._raw_fh is not None:
            try:
                self._raw_fh.flush()
                self._raw_fh.close()
            except Exception:
                pass
            self._raw_fh = None

    def _on_raw_error(self, exc: Exception) -> None:
        msg = f"raw DBN write error: {type(exc).__name__}: {exc}"
        self.status.errors.append(msg)
        print(f"[ALERT] {self.spec.name}: {msg}", file=sys.stderr)
        if not self.probe:
            self._commit_counts(errors=[msg])

    def _drop(self, reason: str) -> None:
        """A connection failed or ended. The first drop opens an outage and
        writes its ONE error entry — ``reconnect #N: … (possible gap)``, the
        prefix runbook/datastream/gate.py recognises as transport — and its
        ONE note; every later attempt rewrites that note with the count."""
        self.status.reconnects += 1
        if self._outage is None:
            self._outages_seen += 1
            self._outage = Outage(since=utc_now_iso(), ordinal=self._outages_seen,
                                  attempts=1, reason=reason)
            err = f"reconnect #{self.status.reconnects}: {reason} (possible gap)"
            self.status.errors.append(err)
            print(f"[ALERT] {self.spec.name}: {err}", file=sys.stderr)
            if not self.probe:
                self._commit_counts(note=self._outage.open_note(),
                                    note_key=self._outage.key, errors=[err])
            return
        o = self._outage
        o.attempts += 1
        o.reason = reason
        print(f"[ALERT] {self.spec.name}: reconnect #{self.status.reconnects}: "
              f"{reason} — outage since {o.since}, attempt {o.attempts}, "
              f"next try in {backoff_seconds(o.attempts)}s", file=sys.stderr)
        if not self.probe:
            self._commit_counts(note=o.open_note(), note_key=o.key)

    def _recover(self) -> None:
        """First record after an outage: close its note as reconnected."""
        o = self._outage
        self._outage = None
        end = utc_now_iso()
        msg = f"outage {o.since}–{end}, {o.attempts} attempt(s), reconnected"
        print(f"[INFO] {self.spec.name}: {msg}", file=sys.stderr, flush=True)
        if not self.probe:
            self._commit_counts(note=msg, note_key=o.key)

    def _give_up(self, exc: BaseException) -> None:
        """An error a retry cannot fix. One ``fatal:`` error entry — NOT the
        transport prefix, so the gate keeps reading it as a real error until
        the batch pull resolves it — and the thread ends; main() exits 1."""
        self._gave_up = True
        msg = f"fatal: {type(exc).__name__}: {exc} — not the network, giving up"
        self.status.errors.append(msg)
        print(f"[ALERT] {self.spec.name}: {msg}", file=sys.stderr)
        if not self.probe:
            self._commit_counts(errors=[msg])

    def _commit_counts(self, note: str | None = None,
                       errors: list[str] | None = None,
                       note_key: str | None = None) -> None:
        """Persist tick delta + optional note/errors to the shared manifest.

        ``last_pull_utc`` advances only when ticks actually landed: the gate
        reads it as "the tape reaches here", and a reconnect attempt that
        pulled nothing must not move it past the close."""
        with self.manifest_lock:
            ticks = self.status.ticks
            delta = ticks - self._committed
            update_manifest(
                d=self.d,
                stream=self.spec.name,
                increment_cycles=delta,
                note=note,
                note_key=note_key,
                errors=errors,
                touch_last_pull=delta > 0,
            )
            self._committed = ticks


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _print_status(workers: list[StreamWorker], prev: dict[str, tuple[int, float]],
                  now_mono: float) -> dict[str, tuple[int, float]]:
    parts = []
    snapshot: dict[str, tuple[int, float]] = {}
    for w in workers:
        ticks = w.status.ticks
        p_ticks, p_t = prev.get(w.spec.name, (0, now_mono))
        dt = max(now_mono - p_t, 1e-6)
        rate = (ticks - p_ticks) / dt
        snapshot[w.spec.name] = (ticks, now_mono)
        tag = w.spec.name.replace("databento_", "")
        unmapped = f" unmapped={w.status.unmapped}" if w.status.unmapped else ""
        rc = f" rc={w.status.reconnects}" if w.status.reconnects else ""
        parts.append(
            f"{tag}: {ticks:,} ({rate:,.0f}/s) "
            f"last {w.status.last_symbol}@{w.status.last_price:g}{unmapped}{rc}"
        )
    print(f"[{datetime.now(CENTRAL):%H:%M:%S}] " + "  |  ".join(parts), flush=True)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Corpus Databento LIVE streamer")
    parser.add_argument("--date", default=None,
                        help="Trading date YYYY-MM-DD (US/Central). Default: today CT")
    parser.add_argument("--streams", default="es,es-mbp1",
                        help="Comma list of streams: opra, es, es-mbp1 "
                             "(default 'es,es-mbp1' — trades for the "
                             "footprint, mbp-1 for absorption; the streams the "
                             "CME Standard plan actually covers). 'opra' names "
                             "a subscription no longer held (st-7av4) and would "
                             "bill pay-as-you-go; pull options tape "
                             "retrospectively instead.")
    parser.add_argument("--schema", default=None,
                        help="Override the schema for EVERY stream (manual "
                             "probing only). Leave unset so each stream uses "
                             "its own: trades for opra/es, mbp-1 for es-mbp1.")
    parser.add_argument("--start-ct", default="13:00",
                        help="Begin streaming at this CT HH:MM (default 13:00)")
    parser.add_argument("--until-ct", default="15:00",
                        help="Hard stop at this CT HH:MM (default 15:00)")
    parser.add_argument("--now", action="store_true",
                        help="Ignore --start-ct; begin immediately")
    parser.add_argument("--max-ticks", type=int, default=None,
                        help="Per-stream safety cap; stop the stream at N ticks")
    parser.add_argument("--max-seconds", type=int, default=None,
                        help="Overall safety cap; stop after N seconds of streaming")
    parser.add_argument("--flush-interval", type=float, default=2.0,
                        help="Seconds between file flushes (default 2)")
    parser.add_argument("--status-interval", type=float, default=10.0,
                        help="Seconds between status lines (default 10)")
    parser.add_argument("--no-raw", action="store_true",
                        help="Disable the lossless raw-DBN archive tee (JSONL only)")
    parser.add_argument("--probe", type=int, default=None, metavar="SECONDS",
                        help="Sample tick rate for N seconds, write NOTHING, report volume")
    args = parser.parse_args()

    _load_env()

    d = _date.fromisoformat(args.date) if args.date else central_date()
    specs = default_specs(args.schema)
    requested = [s.strip() for s in args.streams.split(",") if s.strip()]
    unknown = [s for s in requested if s not in specs]
    if unknown:
        print(f"[FAIL] unknown stream(s): {unknown}. Choose from {list(specs)}",
              file=sys.stderr)
        return 2
    chosen = [specs[s] for s in requested]

    probe = args.probe is not None
    stop_event = threading.Event()
    manifest_lock = threading.Lock()

    # ---- timing window --------------------------------------------------
    now_ct = datetime.now(CENTRAL)
    if probe:
        deadline = None  # bounded by elapsed below
        start_dt = now_ct
    else:
        start_dt = now_ct if args.now else _ct_to_dt(d, args.start_ct)
        deadline = _ct_to_dt(d, args.until_ct)
        if now_ct >= deadline:
            print(f"[ALERT] until-ct {args.until_ct} already passed "
                  f"({now_ct:%H:%M:%S} CT). Nothing to do.", file=sys.stderr)
            return 0

    # ---- banner ---------------------------------------------------------
    print("# Databento LIVE streamer")
    print(f"  date     = {d.isoformat()}")
    print(f"  streams  = {[s.name for s in chosen]}")
    # Per-stream now: one global schema is what kept trades and quotes apart.
    print(f"  schemas  = {', '.join(f'{s.name}:{s.schema}' for s in chosen)}")
    if args.schema:
        print(f"  [WARN]   --schema {args.schema} overrides EVERY stream")
    if probe:
        print(f"  MODE     = PROBE {args.probe}s (no corpus writes)")
    else:
        print(f"  window   = {start_dt:%H:%M} → {args.until_ct} CT")
        print(f"  out      = {day_dir(d)}")
        # GLBX live is sub-covered on the CME/Futures plan (config/entitlements.yaml,
        # knowledge/databento-live-collection.md) — this line used to say
        # "metered … bills by data volume", which was the OPRA-era reading.
        print("  [plan] GLBX live is covered by the CME/Futures subscription. Ctrl-C to stop.")

    # ---- wait for start (no connection, no cost) ------------------------
    if not probe and now_ct < start_dt:
        wait_s = (start_dt - now_ct).total_seconds()
        print(f"  waiting {wait_s:.0f}s until {start_dt:%H:%M} CT to connect…",
              flush=True)
        stop_event.wait(wait_s)
        if stop_event.is_set():
            print("  interrupted before start; nothing collected.")
            return 0

    # ---- signal handling ------------------------------------------------
    def _handle(signum, frame):
        if not stop_event.is_set():
            print(f"\n  signal {signum} — shutting down…", flush=True)
        stop_event.set()
    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    # ---- launch workers -------------------------------------------------
    if not probe:
        day_dir(d, create=True)
    workers = [
        StreamWorker(
            spec, d, stop_event, manifest_lock,
            flush_interval=args.flush_interval,
            max_ticks=args.max_ticks,
            probe=probe,
            raw=not args.no_raw,
        )
        for spec in chosen
    ]
    for w in workers:
        w.start()

    started = time.monotonic()
    # Seed each stream at (0 ticks, launch time) so the first status line's
    # rate is computed over real elapsed time, not a near-zero interval.
    prev_snap: dict[str, tuple[int, float]] = {w.spec.name: (0, started) for w in workers}
    last_status = started
    try:
        while not stop_event.is_set():
            now_mono = time.monotonic()
            elapsed = now_mono - started

            if probe and elapsed >= args.probe:
                break
            if args.max_seconds is not None and elapsed >= args.max_seconds:
                print(f"  max-seconds {args.max_seconds} reached.", flush=True)
                break
            if not probe and datetime.now(CENTRAL) >= deadline:
                print(f"  until-ct {args.until_ct} reached.", flush=True)
                break
            if all(not w.is_alive() for w in workers):
                break  # every stream gave up

            if now_mono - last_status >= args.status_interval:
                prev_snap = _print_status(workers, prev_snap, now_mono)
                last_status = now_mono

            stop_event.wait(0.5)
    finally:
        stop_event.set()
        for w in workers:
            w.shutdown()
        for w in workers:
            w.join(timeout=10)

    # ---- summary --------------------------------------------------------
    total = sum(w.status.ticks for w in workers)
    print("\n# done")
    for w in workers:
        unmapped = (f", {w.status.unmapped} unmapped"
                    if w.status.unmapped else "")
        print(f"  {w.spec.name}: {w.status.ticks:,} ticks, "
              f"{w.status.reconnects} reconnect(s){unmapped}")

    gave_up = [w.spec.name for w in workers if w.gave_up]
    if gave_up:
        print(f"[ALERT] stream(s) stopped on an error that is not the network "
              f"and were not recovered this run: {', '.join(gave_up)}",
              file=sys.stderr)
    still_out = [w.spec.name for w in workers if w.outage is not None]
    if still_out:
        print(f"[ALERT] stream(s) still in an outage when the window closed: "
              f"{', '.join(still_out)}", file=sys.stderr)

    if probe:
        secs = max(time.monotonic() - started, 1e-6)
        print(f"\n# PROBE projection (sampled {secs:.0f}s)")
        if not args.now:
            window_min = (_ct_to_dt(d, args.until_ct)
                          - _ct_to_dt(d, args.start_ct)).total_seconds() / 60
        else:
            window_min = 120.0
        for w in workers:
            rate = w.status.ticks / secs
            proj = rate * window_min * 60
            print(f"  {w.spec.name}: {rate:,.0f} ticks/s → "
                  f"~{proj:,.0f} ticks over a {window_min:.0f}-min window")
        print("  (no corpus rows written)")

    return 1 if gave_up else 0


if __name__ == "__main__":
    sys.exit(main())
