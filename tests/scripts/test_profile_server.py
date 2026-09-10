"""scripts/profile_server.py — the on-refresh profile pages. [Steve 2026-09-10]

Each route renders on request, serves a render newer than the cache window
as-is, renders once under concurrent refreshes, serves the last good page
with a stale header when a render fails, answers 503 in plain words when it
has never rendered, and resolves the tailnet prefix the way the bridge does.
The builders are replaced with fakes; no corpus is read.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import profile_server as ps  # noqa: E402


class Counter:
    def __init__(self, html="<html>page</html>", delay=0.0, fail=False):
        self.n, self.html, self.delay, self.fail = 0, html, delay, fail
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            self.n += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("tape unreadable")
        return self.html


@pytest.fixture
def server(monkeypatch):
    vol, mkt = Counter("<html>vol</html>"), Counter("<html>mkt</html>")
    routes = {"volprofile": ps.Route("volprofile", vol, cache_s=0.5),
              "mktprofile": ps.Route("mktprofile", mkt, cache_s=0.5)}
    monkeypatch.setattr(ps, "ROUTES", routes)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ps.Handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, routes, vol, mkt
    httpd.shutdown(); httpd.server_close()


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def test_route_for_is_prefix_tolerant():
    assert ps.route_for("/volprofile") == "volprofile"
    assert ps.route_for("/volprofile/") == "volprofile"
    assert ps.route_for("/volprofile/index.html") == "volprofile"
    assert ps.route_for("/mktprofile/?x=1") == "mktprofile"
    assert ps.route_for("/") is None
    assert ps.route_for("/footprint/") is None


def test_a_refresh_renders_and_the_cache_window_serves_the_same_page(server):
    base, routes, vol, _ = server
    s1, _, b1 = get(base + "/volprofile/")
    s2, _, b2 = get(base + "/volprofile")
    assert (s1, s2) == (200, 200) and b1 == b2 == "<html>vol</html>"
    assert vol.n == 1                      # second hit inside the cache window
    time.sleep(0.6)
    get(base + "/volprofile/")
    assert vol.n == 2                      # past the window: a refresh re-renders


def test_concurrent_refreshes_render_once(server):
    base, routes, vol, _ = server
    vol.delay = 0.3
    results = []
    ts = [threading.Thread(target=lambda: results.append(get(base + "/volprofile/"))) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert all(s == 200 for s, _, _ in results) and vol.n == 1


def test_a_failed_render_serves_last_good_with_a_stale_header(server):
    base, routes, vol, _ = server
    assert get(base + "/volprofile/")[0] == 200
    time.sleep(0.6)
    vol.fail = True
    s, h, b = get(base + "/volprofile/")
    assert s == 200 and b == "<html>vol</html>" and h.get("X-Profile-Stale") == "1"
    assert "tape unreadable" in routes["volprofile"].last_error


def test_never_rendered_and_failing_answers_503_in_words(server):
    base, routes, _, mkt = server
    mkt.fail = True
    s, _, b = get(base + "/mktprofile/")
    assert s == 503 and "mktprofile" in b and "tape unreadable" in b


def test_health_reports_each_route(server):
    base, routes, vol, _ = server
    get(base + "/volprofile/")
    s, _, b = get(base + "/health")
    d = json.loads(b)
    assert s == 200 and d["ok"] is True
    assert d["routes"]["volprofile"]["renders"] == 1
    assert d["routes"]["volprofile"]["last_render_ms"] is not None
    assert d["routes"]["mktprofile"]["renders"] == 0


def test_unknown_path_is_404_naming_the_pages(server):
    base, *_ = server
    s, _, b = get(base + "/nothing/")
    assert s == 404 and "/volprofile/" in b and "/mktprofile/" in b


def test_the_real_builders_are_wired():
    assert set(ps.BUILDERS) == {"volprofile", "mktprofile"}
