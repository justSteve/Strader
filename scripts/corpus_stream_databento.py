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

Two datasets, two gateways
--------------------------
A Databento Live session is bound to a single dataset, so OPRA.PILLAR and
GLBX.MDP3 cannot share one connection. Each requested stream therefore runs
on its own worker thread with its own `LiveClient`, its own file handle, and
independent reconnect handling. The shared manifest is updated under a lock.

Cost
----
Live OPRA is covered by the account's flat OPRA subscription (no per-GB
charge), so this collector defaults to OPRA only. ES (GLBX.MDP3) is NOT
subscribed for live — keep collecting ES via the T+1 batch puller
(`corpus_pull_databento_es.py`), which is cheap historical usage. `--probe`,
`--max-ticks`, and `--max-seconds` are for mechanical validation and scope
control, not cost gating. Requesting `--streams es` would stream live GLBX at
pay-as-you-go rates; don't, unless a GLBX live subscription is added.

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
    databento_glbx_es_path,
    databento_path,
    day_dir,
)
from market.corpus.writer import update_manifest, utc_now_iso  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def _load_env() -> None:
    """Hydrate DATABENTO_* from .env (manual parse to skip comments)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    import os
    for line in env_path.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s and "DATABENTO" in s:
            k, _, v = s.partition("=")
            os.environ.setdefault(k.strip(), v.split("#", 1)[0].strip())


def _ct_to_dt(d: _date, hhmm: str) -> datetime:
    """Combine a CT date + HH:MM clock-time into an aware Central datetime."""
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, _time(h, m, 0), tzinfo=CENTRAL)


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


def default_specs(schema: str) -> dict[str, StreamSpec]:
    return {
        "opra": StreamSpec(
            name="databento_opra",
            dataset="OPRA.PILLAR",
            schema=schema,
            symbols=["SPXW.OPT"],
            stype_in="parent",
            out_path=databento_path,
        ),
        "es": StreamSpec(
            name="databento_glbx_es",
            dataset="GLBX.MDP3",
            schema=schema,
            symbols=["ES.c.0"],
            stype_in="continuous",
            out_path=databento_glbx_es_path,
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
        for trade in client.trades():
            if self.stop_event.is_set() or self._done.is_set():
                break

            self.status.ticks += 1
            self.status.last_symbol = trade.symbol or "?"
            self.status.last_price = trade.price
            self.status.last_ts = trade.ts.isoformat()
            if not trade.symbol:
                self.status.unmapped += 1

            if not self.probe:
                self._fh.write(self._row(trade))
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
    parser.add_argument("--streams", default="opra",
                        help="Comma list of streams: opra,es (default opra — "
                             "ES has no live sub; collect ES via T+1 batch)")
    parser.add_argument("--schema", default="trades",
                        help="Databento schema (default trades)")
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
    print(f"  schema   = {args.schema}")
    if probe:
        print(f"  MODE     = PROBE {args.probe}s (no corpus writes)")
    else:
        print(f"  window   = {start_dt:%H:%M} → {args.until_ct} CT")
        print(f"  out      = {day_dir(d)}")
        print("  [metered] Databento Live bills by data volume. Ctrl-C to stop.")

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
