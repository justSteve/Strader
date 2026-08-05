#!/usr/bin/env python3
"""Drill bridge — two-way channel between the browser drill and a coach agent. [st-ago]

The drill (a file:// page in the Windows browser) POSTs state events here and
polls for coach commands; a coach agent (a Claude Code session in this repo)
tails the state log and POSTs guidance back. WSL binds localhost; Windows
browsers reach WSL localhost natively — no browser automation, no CDP.

Endpoints (all JSON; POST bodies are sent as text/plain so file:// pages make
"simple" CORS requests — no preflight):
  GET  /health                     -> {ok, started, events, queued}
  POST /state                      <- drill state event; appended to the log
  GET  /state/tail?n=50            -> last n logged events (coach convenience)
  POST /coach                      <- {type: say|arm|jump|pause|play, ...}
  GET  /commands?since=<id>        -> {commands: [...], last: <id>} (drill poll)
  POST /bars                       <- {bars: [...], meta: {...}, final: [...]} from the feeder
  GET  /bars?since=<n>             -> {bars: [...], total, meta, final} (live footprint)

The bar channel [st-re1o] carries a LIVE session into the same surface the
replay drills use. ``since`` is a count, not an id: a page asks for everything
past what it already holds, so one that connects mid-session gets the whole
backlog plus ``meta`` in a single response and renders identically to one that
was open from the first bar.

State and coach append to data/drill-bridge/state-YYYY-MM-DD.jsonl (gitignored
via data/): the session transcript IS the artifact — replayable, reviewable,
and the raw material for coached-session study later. Bars are held in memory
and logged only as a compact per-push marker; the corpus JSONL is their durable
record and the feeder can rebuild them from it.

Run:      .venv/bin/python scripts/drill_bridge.py           # port 7788
Override: DRILL_BRIDGE_PORT=7799 (must match BRIDGE in the drill template)
Stop:     Ctrl-C (or kill; the log is append-only, nothing to corrupt)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("drill_bridge")

PORT = int(os.environ.get("DRILL_BRIDGE_PORT", "7788"))
LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "drill-bridge"

COACH_TYPES = {"say", "arm", "jump", "pause", "play"}


class BridgeState:
    """Append-only event log + monotonic coach-command queue. Thread-safe."""

    def __init__(self, log_dir: Path = LOG_DIR):
        self._lock = threading.Lock()
        self._commands: list[dict] = []   # each carries "id" (1-based, monotonic)
        # Live footprint bars [st-re1o]: append-only, index == position. Held in
        # memory only — the corpus JSONL is the durable record and these are
        # derived from it, so persisting them here would duplicate data the
        # feeder can rebuild. The log gets a compact marker per push instead,
        # which is what makes the session transcript show live cadence.
        self._bars: list[dict] = []
        self._bar_meta: dict = {}
        self._final: list[dict] = []   # end-of-stream emissions [st-b0n9]
        self._developing: dict | None = None  # the bar still forming [st-e91l]
        self._events = 0
        self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"state-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        self._append({"kind": "bridge_start", "started": self.started})

    @property
    def log_path(self) -> Path:
        return self._log_path

    def _append(self, record: dict) -> None:
        record.setdefault("logged", datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    def add_state(self, event: dict) -> None:
        with self._lock:
            self._events += 1
            self._append({"channel": "drill", **event})

    def add_coach(self, cmd: dict) -> dict:
        if cmd.get("type") not in COACH_TYPES:
            raise ValueError(f"coach type must be one of {sorted(COACH_TYPES)}")
        with self._lock:
            cmd = {**cmd, "id": len(self._commands) + 1}
            self._commands.append(cmd)
            self._append({"channel": "coach", **cmd})
            return cmd

    def add_bars(self, bars: list[dict], meta: dict | None = None,
                 final: list[dict] | None = None,
                 developing: dict | None = None) -> int:
        """Append closed footprint bars from the live feeder. [st-re1o]

        Returns the new total. ``meta`` (bar size, tick, anchors, session day)
        is replaced wholesale when supplied, so a page that connects mid-session
        gets the setup along with the backlog rather than having to infer it.

        ``final`` is the end-of-stream emission block — engine flush signals and
        the session's profile levels, which belong to no bar [st-b0n9]. Held
        like meta (replaced, not appended) and served on every /bars response,
        so a page that connects after the close still gets it.

        ``developing`` is the bar the tape is currently writing [st-e91l]:
        REPLACED on every push, never appended, and cleared the moment real bars
        arrive — because a closed bar IS the developing one, finished. Holding a
        single slot rather than a list is what keeps it from ever being mistaken
        for history: there is nothing here to accumulate, seek through or
        replay.
        """
        if not isinstance(bars, list):
            raise ValueError("bars must be a list")
        if final is not None and not isinstance(final, list):
            raise ValueError("final must be a list")
        if developing is not None and not isinstance(developing, dict):
            raise ValueError("developing must be an object")
        with self._lock:
            if meta:
                self._bar_meta = meta
            if final:
                self._final = final
            for b in bars:
                if not isinstance(b, dict):
                    raise ValueError("each bar must be an object")
                self._bars.append({**b, "i": len(self._bars)})
            # Order matters: a push carrying closed bars retires whatever was
            # developing, even if this same push also carries a newer one.
            if bars:
                self._developing = None
            if developing is not None:
                self._developing = developing
            total = len(self._bars)
            if bars or final:
                self._append({"channel": "bars", "kind": "bar_push",
                              "n": len(bars), "total": total,
                              "final": len(final or [])})
            return total

    def bars_since(self, n: int) -> dict:
        with self._lock:
            start = max(0, min(n, len(self._bars)))
            return {"bars": self._bars[start:], "total": len(self._bars),
                    "meta": self._bar_meta, "final": self._final,
                    "developing": self._developing}

    def commands_since(self, last_id: int) -> list[dict]:
        with self._lock:
            return [c for c in self._commands if c["id"] > last_id]

    def tail(self, n: int) -> list[dict]:
        with self._lock:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-max(1, min(n, 500)):]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def stats(self) -> dict:
        with self._lock:
            return {"ok": True, "started": self.started,
                    "events": self._events, "queued": len(self._commands),
                    "bars": len(self._bars),
                    "log": str(self._log_path)}


STATE = BridgeState()


class _Handler(BaseHTTPRequestHandler):
    server_version = "DrillBridge/1.0"

    # ── plumbing ────────────────────────────────────────────────────────────
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 1_000_000:
            raise ValueError("missing or oversized body")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def log_message(self, fmt, *args):  # route http.server chatter to logging
        logger.debug(fmt, *args)

    def do_OPTIONS(self):  # belt-and-braces preflight support
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── routes ──────────────────────────────────────────────────────────────
    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/health":
                self._send(200, STATE.stats())
            elif url.path == "/commands":
                since = int(parse_qs(url.query).get("since", ["0"])[0])
                cmds = STATE.commands_since(since)
                self._send(200, {"commands": cmds,
                                 "last": cmds[-1]["id"] if cmds else since})
            elif url.path == "/bars":
                since = int(parse_qs(url.query).get("since", ["0"])[0])
                self._send(200, STATE.bars_since(since))
            elif url.path == "/state/tail":
                n = int(parse_qs(url.query).get("n", ["50"])[0])
                self._send(200, {"events": STATE.tail(n)})
            else:
                self._send(404, {"error": f"no route {url.path}"})
        except (ValueError, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})

    def do_POST(self):
        url = urlparse(self.path)
        try:
            payload = self._body()
            if url.path == "/state":
                STATE.add_state(payload)
                self._send(200, {"ok": True})
            elif url.path == "/bars":
                total = STATE.add_bars(payload.get("bars") or [],
                                       payload.get("meta"),
                                       payload.get("final"),
                                       payload.get("developing"))
                self._send(200, {"ok": True, "total": total})
            elif url.path == "/coach":
                cmd = STATE.add_coach(payload)
                self._send(200, {"ok": True, "id": cmd["id"]})
            else:
                self._send(404, {"error": f"no route {url.path}"})
        except (ValueError, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    logger.info("drill bridge on http://127.0.0.1:%d — log %s", PORT, STATE.log_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("bridge stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
