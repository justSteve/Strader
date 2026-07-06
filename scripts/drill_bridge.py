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

Everything (state + coach) appends to data/drill-bridge/state-YYYY-MM-DD.jsonl
(gitignored via data/): the session transcript IS the artifact — replayable,
reviewable, and the raw material for coached-session study later.

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
