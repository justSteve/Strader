"""GexBot LIVE orderflow leg — one endpoint, ~1 Hz, session-gated. [st-ipn0]

Why this exists next to corpus_poll_gexbot.py instead of inside it: the main
collector's job is the archival cycle — all 10 endpoints, once a minute — and
the nightly /hist harvest already delivers every day at the feed's native ~1.3s
cadence retrospectively. What neither pipe provides is the spike TRAIN as it
happens: the gex/convexity orderflow panes are per-snapshot deltas, and a 70s
sample of a 1.3s process sees isolated bars, never the sequence. Steve's
2026-08-10 direction makes real-time direction reads the target, so the live
gap is now the gap that matters.

Vendor ceiling (AGENTS.md, quoted in docs/gexbot/vendor-docs-survey-2026-08-06.md):
"Data is not updated more than once per second. Requests should not exceed one
request per second per ticker per metric." This poller touches ONE metric on
ONE ticker with end-to-start spacing >= --interval (default 1.1s), so it can
never exceed 1 req/s no matter how fast responses return. The 10-endpoint
collector polls the same metric once a minute alongside; combined worst case
stays comfortably under the ceiling.

Inherits the session-gate doctrine from corpus_poll_gexbot.py verbatim: the
gate lives HERE in the process, not in the scheduler, because hand-run panes
are how collectors actually get started. Window 08:30-15:05 CT — measured
(see the constants block in corpus_poll_gexbot.py; the feed is frozen outside
cash hours, and a Saturday of 1 Hz polling would be ~23,000 wasted requests
against whatever unpublished QUANT quota exists).

Output: data/corpus/<date>/gexbot_orderflow_1s.jsonl — one FLAT row per new
snapshot: {"ts_pull_utc": ..., <the 34+ orderflow scalars>}. Consecutive
identical payloads are NOT rewritten (the feed snaps every ~1.3s; polling at
~1.2s effective means occasional duplicates carrying zero information — the
dedup count is reported at exit and in the manifest note). Anomalies land as
{"ts_pull_utc": ..., "anomaly": {...}} rows so a gap is always explained
in-band.

Entitlement lapse (401/403, or the vendor's in-200 {"error": ...} body) backs
off to 5 minutes instead of spinning — the ~Sep 1 tier decision must not turn
this into a 1 Hz error loop. Transport failures back off to 5 minutes after 5
consecutive, mirroring the main collector.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Private-name imports are deliberate: one auth/transport truth in
# gexbot_stream.py, not a second copy here. [st-ipn0]
from market.corpus.gexbot_stream import (  # noqa: E402
    BASE_URL,
    LOCAL_ADDR_V4,
    TIMEOUT_S,
    _load_api_key,
    _make_headers,
)
from market.corpus.paths import CORPUS_ROOT, central_date  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest, utc_now_iso  # noqa: E402
from strader.market_calendar import (  # noqa: E402
    CENTRAL,
    describe,
    window_state,
    year_is_known,
)

import httpx  # noqa: E402

STREAM = "gexbot_orderflow_1s"
ENDPOINT = "/{ticker}/orderflow/orderflow"
DEFAULT_START_CT = "08:30"
DEFAULT_UNTIL_CT = "15:05"
DEFAULT_INTERVAL_S = 1.1
MANIFEST_BATCH = 60          # ~every 80s at the default interval
ENTITLEMENT_BACKOFF_S = 300
FAILURE_BACKOFF_S = 300
FAILURE_BACKOFF_AFTER = 5

_stop = False


def _handle_stop(signum, frame):
    global _stop
    _stop = True
    print(f"\nsignal {signum} — finishing poll then exiting", file=sys.stderr)


def _sleep(seconds: float) -> None:
    """Sleep in <=1s slices so a signal is honoured promptly."""
    remaining = seconds
    while remaining > 0 and not _stop:
        time.sleep(min(1.0, remaining))
        remaining -= 1.0


def _await_window(start_ct: str, until_ct: str) -> bool:
    """Block until the collect window is open. False means stop, don't poll."""
    announced = False
    while not _stop:
        now = datetime.now(CENTRAL)
        state, resume_at = window_state(now, start_ct, until_ct)
        if state == "open":
            return True
        if state == "closed":
            print(f"  window closed — {describe(now.date())}; "
                  f"next session opens {resume_at:%Y-%m-%d %H:%M} CT. Exiting.",
                  flush=True)
            return False
        wait = (resume_at - now).total_seconds()
        if not announced:
            print(f"  before the window — sleeping {wait / 60:.0f} min until "
                  f"{resume_at:%H:%M} CT ({describe(now.date())})", flush=True)
            announced = True
        _sleep(max(1, min(wait, 60)))
    return False


def _out_path() -> Path:
    return CORPUS_ROOT / central_date().isoformat() / "gexbot_orderflow_1s.jsonl"


class ManifestBatcher:
    """update_manifest() rewrites the file; at 1 Hz that must be batched."""

    def __init__(self) -> None:
        self.pending_cycles = 0
        self.pending_errors: list[str] = []

    def bump(self, error: str | None = None) -> None:
        self.pending_cycles += 1
        if error and len(self.pending_errors) < 20:
            self.pending_errors.append(error)
        if self.pending_cycles >= MANIFEST_BATCH:
            self.flush()

    def flush(self, note: str | None = None) -> None:
        if not (self.pending_cycles or self.pending_errors or note):
            return
        try:
            update_manifest(d=None, stream=STREAM,
                            increment_cycles=self.pending_cycles,
                            errors=self.pending_errors or None,
                            note=note)
            self.pending_cycles = 0
            self.pending_errors = []
        except Exception as e:  # bookkeeping must never kill the collector
            print(f"  manifest update failed: {e}", file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="GexBot live orderflow poller — one endpoint at ~1 Hz (session-gated)")
    ap.add_argument("--ticker", default="SPX")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S,
                    help=f"Seconds from one request's END to the next START "
                         f"(default {DEFAULT_INTERVAL_S}; keep >= 1.1 — vendor "
                         f"ceiling is 1 req/s per ticker per metric)")
    ap.add_argument("--max-cycles", type=int, default=None,
                    help="Stop after N polls (testing)")
    ap.add_argument("--start-ct", default=DEFAULT_START_CT)
    ap.add_argument("--until-ct", default=DEFAULT_UNTIL_CT)
    ap.add_argument("--all-hours", action="store_true",
                    help="Disable the session gate. Testing only — the feed is "
                         "frozen off-session and 1 Hz burns quota fast.")
    args = ap.parse_args()

    if args.interval < 1.1:
        print(f"  --interval {args.interval} < 1.1 refused: vendor ceiling is "
              f"1 req/s per ticker per metric.", file=sys.stderr)
        return 2

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    if args.all_hours:
        print("  --all-hours: session gate DISABLED.", file=sys.stderr, flush=True)
    elif not year_is_known(datetime.now(CENTRAL).date()):
        print("  WARN: no holiday table for this year — weekday-only gating.",
              file=sys.stderr, flush=True)

    endpoint = ENDPOINT.format(ticker=args.ticker)
    url = f"{BASE_URL}{endpoint}"
    headers = _make_headers(_load_api_key())
    transport = httpx.HTTPTransport(local_address=LOCAL_ADDR_V4)

    polls = written = deduped = 0
    consecutive_failures = 0
    last_body: dict | None = None
    batcher = ManifestBatcher()
    client = httpx.Client(transport=transport, timeout=TIMEOUT_S)

    try:
        while not _stop:
            if not args.all_hours and not _await_window(args.start_ct, args.until_ct):
                break
            backoff = None
            try:
                resp = client.get(url, headers=headers)
                if resp.status_code in (401, 403):
                    msg = f"HTTP {resp.status_code} — entitlement lapsed?"
                    print(f"  {msg} backing off {ENTITLEMENT_BACKOFF_S}s",
                          file=sys.stderr, flush=True)
                    append_jsonl(_out_path(), {"ts_pull_utc": utc_now_iso(),
                                               "anomaly": {"status_code": resp.status_code}})
                    batcher.bump(msg)
                    backoff = ENTITLEMENT_BACKOFF_S
                elif resp.status_code >= 400:
                    consecutive_failures += 1
                    batcher.bump(f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    body = resp.json()
                    if isinstance(body, dict) and set(body) == {"error"}:
                        msg = f"in-200 error body: {body['error']}"
                        print(f"  {msg} — backing off {ENTITLEMENT_BACKOFF_S}s",
                              file=sys.stderr, flush=True)
                        append_jsonl(_out_path(), {"ts_pull_utc": utc_now_iso(),
                                                   "anomaly": body})
                        batcher.bump(msg)
                        backoff = ENTITLEMENT_BACKOFF_S
                    else:
                        consecutive_failures = 0
                        if body == last_body:
                            deduped += 1
                        else:
                            append_jsonl(_out_path(),
                                         {"ts_pull_utc": utc_now_iso(), **body})
                            written += 1
                            last_body = body
                        batcher.bump()
            except httpx.HTTPError as e:
                consecutive_failures += 1
                batcher.bump(f"transport {type(e).__name__}: {e}")
                # A persistent client can hold a broken connection; start fresh.
                client.close()
                client = httpx.Client(transport=transport, timeout=TIMEOUT_S)

            polls += 1
            if polls % 600 == 0:
                print(f"  [{utc_now_iso()}] {polls} polls, {written} rows, "
                      f"{deduped} duplicate snapshots skipped", flush=True)
            if args.max_cycles is not None and polls >= args.max_cycles:
                break

            if backoff is None and consecutive_failures >= FAILURE_BACKOFF_AFTER:
                if consecutive_failures == FAILURE_BACKOFF_AFTER:
                    print(f"  {FAILURE_BACKOFF_AFTER} consecutive failures — "
                          f"backing off to {FAILURE_BACKOFF_S}s polls",
                          file=sys.stderr, flush=True)
                backoff = FAILURE_BACKOFF_S
            _sleep(backoff if backoff is not None else args.interval)
    finally:
        client.close()
        batcher.flush(note=f"{STREAM}: exit after {polls} polls, {written} rows "
                           f"written, {deduped} duplicates skipped")

    print(f"stopped after {polls} polls ({written} rows, {deduped} dups)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
