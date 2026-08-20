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
        max_reconnects: int = 5,
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
        self.max_reconnects = max_reconnects
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

    # -- lifecycle -------------------------------------------------------

    @property
    def gave_up(self) -> bool:
        """True once this stream exhausted its reconnect budget and stopped
        unasked — as opposed to stop_event (scheduled/signalled stop) or
        _done (own tick cap). reconnects only exceeds max_reconnects in the
        give-up branch, which breaks the loop immediately after, so this is
        stable once the thread has exited. main() needs the distinction: a
        stream that quietly dies must not look like a clean scheduled stop,
        or systemd's Restart=on-failure never sees a reason to fire."""
        return self.status.reconnects > self.max_reconnects

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
                self._commit_counts(
                    note=f"live stream ended — {self.status.ticks} ticks, "
                         f"{self.status.reconnects} reconnect(s)",
                    errors=self.status.errors or None,
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
                if not self.probe:
                    note = (None if not first else
                            f"live stream start — {self.spec.dataset} "
                            f"{self.spec.schema} {self.spec.symbols}")
                    self._commit_counts(note=note)
                first = False
                self._consume(client)
                # Clean end of iterator without an exception => either we
                # hit our own cap (_done) / were asked to stop, or the
                # server hung up. The former two are deliberate; the latter
                # is a drop we should reconnect on.
                if self.stop_event.is_set() or self._done.is_set():
                    break
                self._note_reconnect("stream ended unexpectedly")
            except Exception as e:  # connection drop, auth blip, etc.
                if self.stop_event.is_set():
                    break
                self._note_reconnect(f"{type(e).__name__}: {e}")
            finally:
                with self._client_lock:
                    if self._client is not None:
                        try:
                            self._client.close()
                        except Exception:
                            pass
                    self._client = None
                self._close_raw()

            if self.status.reconnects > self.max_reconnects:
                self.status.errors.append(
                    f"giving up after {self.status.reconnects} reconnects")
                print(f"[ALERT] {self.spec.name}: giving up after "
                      f"{self.status.reconnects} reconnects", file=sys.stderr)
                break
            # Retry the first drop immediately (transient blips recover
            # fast); back off exponentially thereafter, capped at 30s.
            backoff = 0 if self.status.reconnects <= 1 else \
                min(2 ** (self.status.reconnects - 1), 30)
            if backoff:
                self.stop_event.wait(backoff)

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

    def _note_reconnect(self, reason: str) -> None:
        self.status.reconnects += 1
        msg = f"reconnect #{self.status.reconnects}: {reason} (possible gap)"
        self.status.errors.append(msg)
        print(f"[ALERT] {self.spec.name}: {msg}", file=sys.stderr)
        if not self.probe:
            self._commit_counts(note=msg)

    def _commit_counts(self, note: str | None = None,
                       errors: list[str] | None = None) -> None:
        """Persist tick delta + optional note to the shared manifest."""
        delta = self.status.ticks - self._committed
        with self.manifest_lock:
            update_manifest(
                d=self.d,
                stream=self.spec.name,
                increment_cycles=delta,
                note=note,
                errors=errors,
            )
        self._committed = self.status.ticks


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
    parser.add_argument("--max-reconnects", type=int, default=5,
                        help="Give up a stream after this many reconnects (default 5)")
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
            max_reconnects=args.max_reconnects,
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
        print(f"[ALERT] stream(s) exhausted their reconnect budget and were "
              f"not recovered this run: {', '.join(gave_up)}", file=sys.stderr)

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
