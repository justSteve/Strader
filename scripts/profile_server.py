#!/usr/bin/env python3
"""Profile server — the anchored profiles, rendered on every page refresh. [st-ad4c]

Steve, 2026-09-10: "I'd prefer it re-gen on a page refresh. It should live at
https://mydesk-1.tail89f676.ts.net/volprofile/ — and I'll have the same ask of
a Market Profile." And: "if there is substantive computation overhead — 30
minutes is fine." Measured: the volume profile renders in ~4 s over a full
two-session window, so refresh-driven is the design, with a short cache so a
double refresh (or two devices) renders once.

Routes (prefix-tolerant, so `tailscale serve --set-path /volprofile
http://127.0.0.1:7790/volprofile` works — tailscale strips the mount path, so
the backend URL carries the route):

    GET /volprofile/[?anchor=prior|overnight|today]   anchored volume profile
    GET /mktprofile/[?anchor=…]                        anchored market profile
    GET /health                                        JSON per route and anchor

The three anchors (Steve: "those 3 are sufficient") are defined once in
market/orderflow/anchored_profile.ANCHORS; the default is `prior`.

Contract, per (route, anchor):
  * one render at a time — a lock; a second request during a render waits and
    receives the same page rather than starting another render;
  * a render newer than CACHE_S seconds is served as-is;
  * a render failure serves the LAST GOOD page with an `X-Profile-Stale` header
    and logs the error; with no last-good page it answers 503 in plain words.
    Same last-good stance as the 08:15 cron's "published page LEFT AS-IS".

Bind is 127.0.0.1 only; the tailnet reaches it through tailscale serve, never
funnel. Run:  .venv/bin/python scripts/profile_server.py   (systemd:
deploy/systemd/strader-profile-server.service). Override the port with
PROFILE_SERVER_PORT, the cache with PROFILE_CACHE_S.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from market.orderflow.anchored_profile import ANCHORS  # noqa: E402

logger = logging.getLogger("profile_server")

PORT = int(os.environ.get("PROFILE_SERVER_PORT", "7790"))
CACHE_S = float(os.environ.get("PROFILE_CACHE_S", "10"))
DEFAULT_ANCHOR = "prior"


# ── builders ─────────────────────────────────────────────────────────────────
# Each takes the anchor kind and returns the page HTML. Imported lazily so a
# route whose renderer is not on disk yet (the market profile lands
# separately) answers 503 with a plain sentence instead of taking the whole
# server down at import time.

def _build_volprofile(anchor: str) -> str:
    mod = importlib.import_module("premarket_volume_profile")
    html, summary = mod.build_page(anchor=anchor)
    logger.info("volprofile[%s]: %s", anchor, summary.replace("\n", " | "))
    return html


def _build_mktprofile(anchor: str) -> str:
    mod = importlib.import_module("anchored_market_profile")
    payload = mod.build(anchor=anchor)
    return mod.render_html(payload)


BUILDERS: dict[str, Callable[[str], str]] = {
    "volprofile": _build_volprofile,
    "mktprofile": _build_mktprofile,
}


# ── one cache entry per (route, anchor) ──────────────────────────────────────

class Entry:
    def __init__(self, name: str, anchor: str, build: Callable[[str], str], cache_s: float):
        self.name, self.anchor, self.build, self.cache_s = name, anchor, build, cache_s
        self.lock = threading.Lock()
        self.html: str | None = None
        self.built_at: float = 0.0           # time.monotonic()
        self.built_wall: str | None = None   # ISO, for /health
        self.last_ms: float | None = None
        self.renders = 0
        self.last_error: str | None = None

    def get(self) -> tuple[str | None, bool]:
        """(html, stale). stale=True means the render failed and this is the
        last good page; html=None means there is no page at all."""
        with self.lock:                      # a concurrent refresh waits, then reads the fresh page
            now = time.monotonic()
            if self.html is not None and now - self.built_at < self.cache_s:
                return self.html, False
            t0 = time.monotonic()
            try:
                html = self.build(self.anchor)
            except Exception as e:  # noqa: BLE001 — last-good contract
                self.last_error = f"{type(e).__name__}: {e}"
                logger.error("%s[%s]: render failed, serving last good: %s",
                             self.name, self.anchor, self.last_error)
                return self.html, True
            self.html, self.built_at = html, time.monotonic()
            self.built_wall = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.last_ms = (self.built_at - t0) * 1000
            self.renders += 1
            self.last_error = None
            logger.info("%s[%s]: rendered in %.0f ms (%d bytes)",
                        self.name, self.anchor, self.last_ms, len(html))
            return self.html, False

    def health(self) -> dict:
        age = None if self.html is None else round(time.monotonic() - self.built_at, 1)
        return {"renders": self.renders, "last_render_utc": self.built_wall,
                "last_render_ms": None if self.last_ms is None else round(self.last_ms),
                "cache_age_s": age, "cache_s": self.cache_s, "last_error": self.last_error}


class Route:
    """A page name with one Entry per anchor."""

    def __init__(self, name: str, build: Callable[[str], str], cache_s: float = CACHE_S):
        self.name, self.build, self.cache_s = name, build, cache_s
        self.entries: dict[str, Entry] = {a: Entry(name, a, build, cache_s) for a in ANCHORS}

    def get(self, anchor: str = DEFAULT_ANCHOR) -> tuple[str | None, bool]:
        return self.entries[anchor].get()

    def last_error(self, anchor: str = DEFAULT_ANCHOR) -> str | None:
        return self.entries[anchor].last_error

    def health(self) -> dict:
        return {a: e.health() for a, e in self.entries.items()}


ROUTES: dict[str, Route] = {name: Route(name, fn) for name, fn in BUILDERS.items()}


def route_for(path: str) -> str | None:
    """'/volprofile', '/volprofile/', '/x/volprofile/index.html' → 'volprofile'.
    Prefix-tolerant so the tailnet path and the bare port agree."""
    parts = [p for p in urlsplit(path).path.split("/") if p]
    for p in parts:
        if p in ROUTES:
            return p
    return None


def anchor_for(url: str) -> str | None:
    """The ?anchor= value, DEFAULT_ANCHOR when absent, None when not a known kind."""
    q = parse_qs(urlsplit(url).query)
    vals = q.get("anchor")
    if not vals:
        return DEFAULT_ANCHOR
    a = vals[-1].strip().lower()
    return a if a in ANCHORS else None


class Handler(BaseHTTPRequestHandler):
    server_version = "strader-profile-server/1"

    def log_message(self, fmt, *args):   # one line per request into the journal
        logger.debug("%s " + fmt, self.address_string(), *args)

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # the page is the render
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.rstrip("/").endswith("/health") or path == "/health":
            body = json.dumps({"ok": True, "anchors": list(ANCHORS),
                               "routes": {n: r.health() for n, r in ROUTES.items()}},
                              indent=1).encode()
            return self._send(200, body, "application/json")
        name = route_for(path)
        if name is None:
            names = ", ".join(f"/{n}/" for n in ROUTES)
            return self._send(404, f"no such profile page; the pages are {names}\n".encode(),
                              "text/plain; charset=utf-8")
        anchor = anchor_for(self.path)
        if anchor is None:
            return self._send(400, (f"anchor must be one of {', '.join(ANCHORS)}\n").encode(),
                              "text/plain; charset=utf-8")
        html, stale = ROUTES[name].get(anchor)
        if html is None:
            err = ROUTES[name].last_error(anchor) or "not rendered yet"
            return self._send(503, (f"{name}: no page could be rendered — {err}\n").encode(),
                              "text/plain; charset=utf-8")
        extra = {"X-Profile-Stale": "1"} if stale else {}
        return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", extra)


def serve(port: int = PORT) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    logger.info("profile server on http://127.0.0.1:%d  routes %s  anchors %s  cache %.0fs",
                port, " ".join(f"/{n}/" for n in ROUTES), "/".join(ANCHORS), CACHE_S)
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    serve()
