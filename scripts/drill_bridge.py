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
  GET  /bars?since=<n>             -> {bars: [...], total, meta, final, developing, profile}
  GET  /                           -> the LIVE page itself (text/html) [st-n0qm.3]
  GET  /health/producers           -> ages of the producer health files (tape,
                                      1 Hz feed, sentinel, footprint feed) for the HUD dots
  GET  /days                       -> corpus days with an ES tape, newest first [st-v7a0]
  GET  /drill-<YYYY-MM-DD>.html    -> that day's DRILL page, rendered on demand and cached
  GET  /desk-candles-<day>.html    -> the drill's minute-candle companion window

Serving the page [st-n0qm.3]: the page used to exist only as a file:// bookmark
on the desktop. Steve, 2026-08-16: "any instrument at the level of the FP chart
will favor a web page for output over the tmux" — and he reads from an iPad
over the tailnet, where file:// is not reachable. The bridge now serves the
rendered page (DRILL_BRIDGE_PAGE, default /tmp/desk-live-footprint.html — the
same file the bookmark points at) so `tailscale serve --set-path /footprint
http://127.0.0.1:7788` publishes it at https://mydesk-1.tail89f676.ts.net/footprint/.
Every route tolerates that `/footprint` prefix, and the page derives its bridge
address from its own URL, so one HTML file works from file://, from
http://127.0.0.1:7788/ and from the tailnet path alike.

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

Drill mode [st-v7a0]: the header of every page (live or drill) carries a
"Drill <day>" picker fed by /days; choosing a day loads drill-<day>.html from
the same origin, and a drill page carries "Live" back to today. Rendering
shells out to scripts/orderflow_drill.py (~3 s); the cache lives under
DRILL_BRIDGE_DRILL_DIR (default /var/moo/desk/drills) and is refreshed when the
day's ES file is newer than the cached page.

Run:      .venv/bin/python scripts/drill_bridge.py           # port 7788
Override: DRILL_BRIDGE_PORT=7799 (must match BRIDGE in the drill template)
          DRILL_BRIDGE_DRILL_DIR=/somewhere (drill cache), DRILL_BRIDGE_DAYS_LIMIT=90
Stop:     Ctrl-C (or kill; the log is append-only, nothing to corrupt)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("drill_bridge")

PORT = int(os.environ.get("DRILL_BRIDGE_PORT", "7788"))
REPO = Path(__file__).resolve().parent.parent
LOG_DIR = REPO / "data" / "drill-bridge"
# Same override market/corpus/paths.py honours [Phase 4]; the bridge does not
# import market/ (dependency-light on purpose), so it reads the variable itself.
CORPUS_ROOT = Path(os.environ.get("STRADER_CORPUS_ROOT") or (REPO / "data" / "corpus"))
# The rendered LIVE page. Same path live_footprint_page.py writes and the
# desktop bookmark reads — one file, three ways in.
PAGE_PATH = Path(os.environ.get("DRILL_BRIDGE_PAGE", "/tmp/desk-live-footprint.html"))
# Path prefix a reverse proxy may leave on the request (tailscale serve
# --set-path /footprint). Stripped before routing; the page derives its bridge
# URL from its own location so it asks under the same prefix.
PATH_PREFIXES = ("/footprint",)
# Producer health files the HUD dots read [st-n0qm.3]. Per-day files live under
# data/corpus/<CT day>/; the collector assessors write day-independent files at
# the corpus root. `fresh_s` is the age past which the dot goes red.
PRODUCERS = {
    "tape":     {"file": "_capture_health.json",     "per_day": False, "fresh_s": 180},
    "gex_1s":   {"file": "_gexbot_of1s_health.json", "per_day": False, "fresh_s": 180},
    "sentinel": {"file": "_sentinel_health.json",    "per_day": True,  "fresh_s": 90},
    "feed":     {"file": "_footprint_health.json",   "per_day": True,  "fresh_s": 90},
}

COACH_TYPES = {"say", "arm", "jump", "pause", "play"}

# ── drill mode [st-v7a0] ────────────────────────────────────────────────────
# The live page is one day's tape; the drill is a past day's tape with the
# playback controls. Both come from orderflow_drill_template.html. Until now the
# drill existed only as a file scripts/orderflow_drill.py wrote to /tmp and a
# desktop browser opened — unreachable from the /footprint/ page Steve actually
# has open, and unreachable at all before 02:50 CT when the live page has no
# bars to show. These routes make any corpus day one click away on the same
# origin:
#     GET /days                       days with an ES tape, newest first
#     GET /drill-<YYYY-MM-DD>.html    the drill for that day (rendered on demand)
#     GET /desk-candles-<date>.html   its minute-candle companion window
# Rendering shells out to scripts/orderflow_drill.py (the tested entry point;
# ~3 s for a full session) so the bridge stays dependency-light. Rendered files
# are cached under DRILL_DIR and re-rendered when the day's ES file is newer
# than the cache (a day still being captured grows), rate-limited to once per
# DRILL_MIN_RERENDER_S per day.
DRILL_DIR = Path(os.environ.get("DRILL_BRIDGE_DRILL_DIR", "/var/moo/desk/drills"))
DRILL_SCRIPT = REPO / "scripts" / "orderflow_drill.py"
# A cached drill is also stale when the page template it was baked from has
# changed since — otherwise a template fix reaches new days only.
DRILL_TEMPLATE = REPO / "scripts" / "orderflow_drill_template.html"
DRILL_PYTHON = Path(os.environ.get("DRILL_BRIDGE_PYTHON", sys.executable))
DRILL_MIN_RERENDER_S = 60.0
DRILL_RENDER_TIMEOUT_S = 120.0
DRILL_DAYS_LIMIT = int(os.environ.get("DRILL_BRIDGE_DAYS_LIMIT", "90"))
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ES_NAMES = ("databento_glbx_es.jsonl", "databento_glbx_es.jsonl.gz")
_drill_locks: dict[str, threading.Lock] = {}
_drill_locks_guard = threading.Lock()


def _es_source(day: str) -> Path | None:
    """The day's ES tape file, plain or compaction-packed, or None."""
    for name in _ES_NAMES:
        p = CORPUS_ROOT / day / name
        if p.exists():
            return p
    return None


def corpus_days(limit: int = DRILL_DAYS_LIMIT, corpus_root: Path | None = None) -> list[str]:
    """Days under the corpus root that hold an ES tape, newest first."""
    root = corpus_root or CORPUS_ROOT
    if not root.is_dir():
        return []
    out = []
    for d in root.iterdir():
        if d.is_dir() and _DAY_RE.match(d.name) and any((d / n).exists() for n in _ES_NAMES):
            out.append(d.name)
    out.sort(reverse=True)
    return out[:limit]


def drill_paths(day: str, drill_dir: Path | None = None) -> tuple[Path, Path]:
    d = drill_dir or DRILL_DIR
    return d / f"drill-{day}.html", d / f"desk-candles-{day}.html"


def _drill_lock(day: str) -> threading.Lock:
    with _drill_locks_guard:
        return _drill_locks.setdefault(day, threading.Lock())


def ensure_drill(day: str, *, drill_dir: Path | None = None,
                 render=None, now: float | None = None) -> Path:
    """Return the rendered drill for ``day``, rendering it if absent or stale.

    Stale = the ES source is newer than the cached page (the day is still being
    captured) and the cache is older than DRILL_MIN_RERENDER_S — or the page
    template is newer than the cached page (a template fix must reach every
    day, not only days not yet rendered). ``render`` is injectable for tests;
    the default shells out to orderflow_drill.py.
    Raises FileNotFoundError when the day has no ES tape, RuntimeError when the
    renderer fails (its stderr tail is the message).
    """
    if not _DAY_RE.match(day):
        raise ValueError(f"not a day: {day!r}")
    src = _es_source(day)
    if src is None:
        raise FileNotFoundError(f"no ES tape for {day} under {CORPUS_ROOT}")
    html, _candles = drill_paths(day, drill_dir)
    now = time.time() if now is None else now
    with _drill_lock(day):
        if html.exists():
            built = html.stat().st_mtime
            age = now - built
            template_newer = DRILL_TEMPLATE.exists() and DRILL_TEMPLATE.stat().st_mtime > built
            if not template_newer and (src.stat().st_mtime <= built or age < DRILL_MIN_RERENDER_S):
                return html
        html.parent.mkdir(parents=True, exist_ok=True)
        (render or _render_drill)(day, html)
        if not html.exists():
            raise RuntimeError(f"renderer produced no file at {html}")
        return html


def _render_drill(day: str, out: Path) -> None:
    cmd = [str(DRILL_PYTHON), str(DRILL_SCRIPT), "--date", day, "--out", str(out), "--no-open"]
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                           timeout=DRILL_RENDER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"drill render for {day} exceeded {DRILL_RENDER_TIMEOUT_S:.0f}s")
    if r.returncode != 0:
        tail = "\n".join((r.stderr or r.stdout or "").strip().splitlines()[-6:])
        logger.error("drill render for %s failed rc=%d: %s", day, r.returncode, tail)
        raise RuntimeError(f"drill render for {day} failed (rc={r.returncode}): {tail}")
    logger.info("drill rendered for %s in %.1fs → %s", day, time.monotonic() - t0, out)


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
        self._profile: dict | None = None     # the anchored aggressor profile [st-n0qm.4]
        # Sentinel alerts [st-n0qm.9]: append-only like bars, index == id − 1.
        # The sentinel posts each alert best-effort as it writes it to
        # orderflow_alerts.jsonl (which stays the durable record); the page
        # polls /alerts?since=N and paints SPX rows at strike + basis.
        self._alerts: list[dict] = []
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
                 developing: dict | None = None,
                 profile: dict | None = None) -> int:
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

        ``profile`` is the anchored aggressor volume profile [st-n0qm.4]: like
        ``developing``, a single REPLACED slot (a profile is a state, not a
        history), served on every /bars response and never retired by bars —
        it outlives the day's last bar because it IS the day.
        """
        if profile is not None and not isinstance(profile, dict):
            raise ValueError("profile must be an object")
        if not isinstance(bars, list):
            raise ValueError("bars must be a list")
        if final is not None and not isinstance(final, list):
            raise ValueError("final must be a list")
        if developing is not None and not isinstance(developing, dict):
            raise ValueError("developing must be an object")
        with self._lock:
            if meta:
                # A new session day on a bridge that outlived the last one
                # [st-n0qm.9]: the feeder restarts at the CT midnight and posts
                # the new day's bars from index 0 with a fresh meta. Without
                # this reset Tuesday appended onto Monday, and a page loading
                # fresh got both days as one tape. Everything the day owns
                # goes: bars, final, developing, profile, alerts.
                old_day = self._bar_meta.get("day") if self._bar_meta else None
                new_day = meta.get("day")
                if old_day and new_day and new_day != old_day:
                    self._append({"channel": "bars", "kind": "day_reset",
                                  "from": old_day, "to": new_day,
                                  "dropped_bars": len(self._bars),
                                  "dropped_alerts": len(self._alerts)})
                    self._bars, self._final, self._alerts = [], [], []
                    self._developing = self._profile = None
                elif (old_day and new_day == old_day and self._bar_meta.get("started")
                      and meta.get("started") and meta["started"] != self._bar_meta["started"]
                      and self._bars):
                    # Same day, NEW feeder run [st-fgno]: the feeder posts meta
                    # only on its first push, and on a restart it re-reads the
                    # day's file from the top and re-posts every bar from index
                    # 0. Appending those onto the bars already held doubled the
                    # tape. A different `started` on the same day is that
                    # re-run: drop the bars (and what rides on them) and let
                    # the re-post rebuild them; alerts are the sentinel's, and
                    # the profile is re-pushed with the next tick — both stay.
                    self._append({"channel": "bars", "kind": "rerun_reset",
                                  "day": new_day, "from_started": self._bar_meta["started"],
                                  "to_started": meta["started"],
                                  "dropped_bars": len(self._bars)})
                    self._bars, self._final = [], []
                    self._developing = None
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
            if profile is not None:
                self._profile = profile
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
                    "developing": self._developing,
                    "profile": self._profile}

    def add_alert(self, alert: dict) -> dict:
        """Append one sentinel alert; returns it with its ``id`` (1-based). The
        shape of the alert is the sentinel's (Strader's schema bead owns it);
        the bridge adds only ``id`` and ``received_utc``. [st-n0qm.9]"""
        if not isinstance(alert, dict) or not alert:
            raise ValueError("alert must be a non-empty object")
        with self._lock:
            rec = {**alert, "id": len(self._alerts) + 1,
                   "received_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self._alerts.append(rec)
            self._append({"channel": "alerts", **rec})
            return rec

    def seed_alerts(self, path: Path) -> int:
        """Load the day's durable ``orderflow_alerts.jsonl`` into the alerts
        channel at bridge start [st-n0qm.9]. The sentinel posts live alerts
        best-effort and never re-posts, so without this a bridge restart — or a
        page opened at 10:00 — would show none of the morning's rows although
        the file has them all. Returns how many were loaded; never raises.
        Only meaningful before any live alert has arrived (ids must stay
        monotonic in arrival order), so a non-empty channel is left alone."""
        try:
            if not path.exists():
                return 0
            with self._lock:
                if self._alerts:
                    return 0
            n = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(a, dict) and a:
                    with self._lock:
                        rec = {**a, "id": len(self._alerts) + 1,
                               "received_utc": a.get("ts_alert_utc")
                               or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "seeded": True}
                        self._alerts.append(rec)
                    n += 1
            if n:
                self._append({"channel": "alerts", "kind": "alerts_seeded",
                              "n": n, "from": str(path)})
            return n
        except OSError as e:
            logger.warning("alerts seed: could not read %s (%s)", path, e)
            return 0

    def alerts_since(self, n: int) -> dict:
        with self._lock:
            start = max(0, min(n, len(self._alerts)))
            return {"alerts": self._alerts[start:], "total": len(self._alerts),
                    "day": self._bar_meta.get("day") if self._bar_meta else None}

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
                    "bars": len(self._bars), "alerts": len(self._alerts),
                    "log": str(self._log_path),
                    "page": str(PAGE_PATH), "page_present": PAGE_PATH.exists()}


def _central_day() -> str:
    try:
        from market.corpus.paths import central_date  # noqa: WPS433 — optional dep
        return central_date().isoformat()
    except Exception:  # noqa: BLE001 — the bridge must serve without the package
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Chicago")).date().isoformat()


def producers_health(now: datetime | None = None, corpus_root: Path | None = None) -> dict:
    """Age of each producer's health file, and whether it is fresh. Read-only,
    dependency-free: a dot that lies is worse than no dot, so this reports what
    is ON DISK and lets the page draw the verdict. `status` is passed through
    when the file carries one (the collector assessors do)."""
    now = now or datetime.now(timezone.utc)
    corpus_root = corpus_root or CORPUS_ROOT   # resolved at call time (tests repoint the module global)
    day = _central_day()
    out = {"day": day, "checked_utc": now.isoformat(timespec="seconds"), "producers": {}}
    for name, spec in PRODUCERS.items():
        path = (corpus_root / day / spec["file"]) if spec["per_day"] else (corpus_root / spec["file"])
        row = {"path": str(path), "present": path.exists(), "age_s": None,
               "fresh": False, "fresh_s": spec["fresh_s"], "status": None}
        if path.exists():
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                row["age_s"] = round((now - mtime).total_seconds(), 1)
                row["fresh"] = row["age_s"] <= spec["fresh_s"]
                try:
                    body = json.loads(path.read_text(encoding="utf-8"))
                    row["status"] = body.get("status")
                    if name == "sentinel":
                        row["rows_today"] = body.get("rows_today")
                        row["last_row_pull_utc"] = body.get("last_row_pull_utc")
                    if name == "feed":
                        row["sent"] = body.get("sent")
                        row["last_bar_t1"] = body.get("last_bar_t1")
                except (ValueError, OSError):
                    row["status"] = "unreadable"
            except OSError:
                pass
        out["producers"][name] = row
    return out


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

    def _send_page(self) -> None:
        if not PAGE_PATH.exists():
            self._send(503, {"error": f"live page not rendered yet: {PAGE_PATH}",
                             "hint": "scripts/live_footprint_page.py writes it; the feed unit renders it at start"})
            return
        body = PAGE_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # the page is regenerated daily
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: bytes, cache: str = "no-store") -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _send_drill(self, day: str) -> None:
        try:
            html = ensure_drill(day)
        except FileNotFoundError as e:
            self._send(404, {"error": str(e), "days": corpus_days(limit=10)})
            return
        except ValueError as e:
            self._send(400, {"error": str(e)})
            return
        except RuntimeError as e:
            self._send(500, {"error": str(e)})
            return
        self._send_html(html.read_bytes())

    def _send_candles(self, day: str) -> None:
        _html, candles = drill_paths(day)
        if not candles.exists():
            self._send(404, {"error": f"no candles companion for {day} — open drill-{day}.html first"})
            return
        self._send_html(candles.read_bytes())

    @staticmethod
    def _route(path: str) -> str:
        """Strip a reverse-proxy prefix so /footprint/bars routes as /bars."""
        for pre in PATH_PREFIXES:
            if path == pre or path.startswith(pre + "/"):
                return path[len(pre):] or "/"
        return path

    # ── routes ──────────────────────────────────────────────────────────────
    def do_GET(self):
        url = urlparse(self.path)
        try:
            route = self._route(url.path)
            if url.path in PATH_PREFIXES:
                # /footprint → /footprint/ so the page's relative bridge URL
                # (its own directory) is the prefix, not the origin root.
                self.send_response(302)
                self.send_header("Location", url.path + "/")
                self.end_headers()
                return
            if route in ("/", "/index.html"):
                self._send_page()
            elif route == "/days":
                self._send(200, {"days": corpus_days(), "live_day": _central_day()})
            elif route.startswith("/drill-") and route.endswith(".html"):
                self._send_drill(route[len("/drill-"):-len(".html")])
            elif route.startswith("/desk-candles-") and route.endswith(".html"):
                self._send_candles(route[len("/desk-candles-"):-len(".html")])
            elif route == "/health/producers":
                self._send(200, producers_health())
            elif route == "/health":
                self._send(200, STATE.stats())
            elif route == "/commands":
                since = int(parse_qs(url.query).get("since", ["0"])[0])
                cmds = STATE.commands_since(since)
                self._send(200, {"commands": cmds,
                                 "last": cmds[-1]["id"] if cmds else since})
            elif route == "/alerts":
                since = int(parse_qs(url.query).get("since", ["0"])[0])
                self._send(200, STATE.alerts_since(since))
            elif route == "/bars":
                since = int(parse_qs(url.query).get("since", ["0"])[0])
                self._send(200, STATE.bars_since(since))
            elif route == "/state/tail":
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
            route = self._route(url.path)
            if route == "/state":
                STATE.add_state(payload)
                self._send(200, {"ok": True})
            elif route == "/bars":
                total = STATE.add_bars(payload.get("bars") or [],
                                       payload.get("meta"),
                                       payload.get("final"),
                                       payload.get("developing"),
                                       payload.get("profile"))
                self._send(200, {"ok": True, "total": total})
            elif route == "/alerts":
                rec = STATE.add_alert(payload)
                self._send(200, {"ok": True, "id": rec["id"]})
            elif route == "/coach":
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
    seeded = STATE.seed_alerts(CORPUS_ROOT / _central_day() / "orderflow_alerts.jsonl")
    logger.info("drill bridge on http://127.0.0.1:%d — log %s — page %s%s — %d alert(s) seeded from today's file",
                PORT, STATE.log_path, PAGE_PATH, "" if PAGE_PATH.exists() else " (not rendered yet)", seeded)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("bridge stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
