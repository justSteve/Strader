import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from drill_bridge import BridgeState  # noqa: E402


@pytest.fixture
def state(tmp_path):
    return BridgeState(log_dir=tmp_path)


def test_log_starts_with_bridge_start(state):
    events = state.tail(10)
    assert events[0]["kind"] == "bridge_start"


def test_state_events_append_and_count(state):
    state.add_state({"kind": "level_armed", "level": 7541.0})
    state.add_state({"kind": "call", "call": "reject"})
    assert state.stats()["events"] == 2
    kinds = [e.get("kind") for e in state.tail(10)]
    assert kinds[-2:] == ["level_armed", "call"]
    assert state.tail(10)[-1]["channel"] == "drill"


def test_coach_ids_are_monotonic_and_polled_incrementally(state):
    a = state.add_coach({"type": "say", "text": "watch the delta"})
    b = state.add_coach({"type": "jump", "bar": 190})
    assert (a["id"], b["id"]) == (1, 2)
    assert [c["id"] for c in state.commands_since(0)] == [1, 2]
    assert [c["id"] for c in state.commands_since(1)] == [2]
    assert state.commands_since(2) == []


def test_invalid_coach_type_rejected(state):
    with pytest.raises(ValueError, match="coach type"):
        state.add_coach({"type": "format_disk"})
    assert state.commands_since(0) == []


def test_coach_commands_also_land_in_log(state):
    state.add_coach({"type": "say", "text": "hello"})
    last = state.tail(5)[-1]
    assert last["channel"] == "coach" and last["type"] == "say"


def test_log_is_valid_jsonl(state):
    state.add_state({"kind": "bar", "bar": 1})
    for line in state.log_path.read_text().splitlines():
        json.loads(line)  # raises on corruption


def test_tail_bounds(state):
    for i in range(30):
        state.add_state({"kind": "bar", "bar": i})
    assert len(state.tail(5)) == 5
    assert len(state.tail(10_000)) == 31  # capped read, full log smaller


# --- end-of-session emissions channel [st-b0n9] ----------------------------

def test_final_emissions_are_served_on_every_bars_response(state):
    """Flush signals and the day's profile levels belong to no bar. They are
    held like meta — replaced, not appended — so a page that opens AFTER the
    close still receives them instead of having missed the one push."""
    state.add_bars([{"o": 1.0}], {"bar_n": 500})
    assert state.bars_since(0)["final"] == []

    final = [{"type": "Level", "price": 7541.0, "bar_i": None}]
    state.add_bars([], None, final)
    # served regardless of `since` — a late page asks for nothing new and must
    # still get the block
    assert state.bars_since(0)["final"] == final
    assert state.bars_since(99)["final"] == final
    assert state.bars_since(0)["total"] == 1     # no phantom bar appended


def test_final_block_is_replaced_not_accumulated(state):
    state.add_bars([], None, [{"type": "Level", "price": 1.0}])
    state.add_bars([], None, [{"type": "Level", "price": 2.0}])
    assert state.bars_since(0)["final"] == [{"type": "Level", "price": 2.0}]


def test_final_must_be_a_list(state):
    with pytest.raises(ValueError, match="final must be a list"):
        state.add_bars([], None, {"not": "a list"})


def test_bars_carry_their_emissions_through_the_bridge(state):
    ev = [{"type": "SweepPrint", "bar_i": 0, "direction": "buy"}]
    state.add_bars([{"o": 1.0, "ev": ev}], {"bar_n": 500})
    got = state.bars_since(0)["bars"]
    assert got[0]["ev"] == ev
    assert got[0]["i"] == 0


# ── page serving, prefix routing, producer health [st-n0qm.3] ─────────────────

def _serve(monkeypatch, tmp_path, page_body=None):
    """Spin the real handler on an ephemeral port with PAGE_PATH/CORPUS_ROOT
    pointed at tmp_path. Returns (base_url, shutdown)."""
    import threading
    from http.server import ThreadingHTTPServer
    import drill_bridge as db
    page = tmp_path / "live.html"
    if page_body is not None:
        page.write_text(page_body, encoding="utf-8")
    monkeypatch.setattr(db, "PAGE_PATH", page)
    monkeypatch.setattr(db, "CORPUS_ROOT", tmp_path / "corpus")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), db._Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv.shutdown


def _get(url, allow_redirects=True):
    import urllib.request
    import urllib.error
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener() if allow_redirects else urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(url, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_root_serves_the_rendered_page(monkeypatch, tmp_path):
    base, stop = _serve(monkeypatch, tmp_path, "<!doctype html><title>Live Footprint</title>")
    try:
        code, hdrs, body = _get(base + "/")
        assert code == 200 and hdrs["Content-Type"].startswith("text/html")
        assert b"Live Footprint" in body
        assert hdrs.get("Cache-Control") == "no-store"
    finally:
        stop()


def test_root_is_503_until_the_page_is_rendered(monkeypatch, tmp_path):
    base, stop = _serve(monkeypatch, tmp_path, None)
    try:
        code, _, body = _get(base + "/")
        assert code == 503 and b"not rendered" in body
    finally:
        stop()


def test_footprint_prefix_routes_like_root(monkeypatch, tmp_path):
    """tailscale serve --set-path /footprint may leave the prefix on the
    request; every route must answer under it, and the bare prefix must
    redirect to the slash form so the page's own-directory bridge URL is the
    prefix, not the origin root."""
    base, stop = _serve(monkeypatch, tmp_path, "<title>x</title>")
    try:
        code, hdrs, _ = _get(base + "/footprint", allow_redirects=False)
        assert code == 302 and hdrs["Location"] == "/footprint/"
        code, hdrs, body = _get(base + "/footprint/")
        assert code == 200 and b"<title>x</title>" in body
        code, _, body = _get(base + "/footprint/bars?since=0")
        assert code == 200 and "bars" in json.loads(body)
        code, _, body = _get(base + "/footprint/health")
        assert code == 200 and json.loads(body)["ok"] is True
        code, _, body = _get(base + "/footprint/health/producers")
        assert code == 200 and "producers" in json.loads(body)
    finally:
        stop()


def test_producers_health_reports_age_and_freshness(monkeypatch, tmp_path):
    import os
    import time
    import drill_bridge as db
    from datetime import datetime, timezone
    corpus = tmp_path / "corpus"
    monkeypatch.setattr(db, "CORPUS_ROOT", corpus)
    monkeypatch.setattr(db, "_central_day", lambda: "2026-08-17")
    day = corpus / "2026-08-17"
    day.mkdir(parents=True)
    (day / "_sentinel_health.json").write_text(json.dumps({"rows_today": 5, "last_row_pull_utc": "x"}))
    (corpus / "_capture_health.json").write_text(json.dumps({"status": "ok"}))
    old = day / "_footprint_health.json"
    old.write_text(json.dumps({"sent": 12}))
    stale = time.time() - 1000
    os.utime(old, (stale, stale))
    h = db.producers_health(now=datetime.now(timezone.utc))
    p = h["producers"]
    assert p["sentinel"]["present"] and p["sentinel"]["fresh"] and p["sentinel"]["rows_today"] == 5
    assert p["tape"]["present"] and p["tape"]["status"] == "ok"
    assert p["feed"]["present"] and not p["feed"]["fresh"] and p["feed"]["age_s"] > 900
    assert p["gex_1s"]["present"] is False and p["gex_1s"]["fresh"] is False
    assert h["day"] == "2026-08-17"


def test_profile_slot_is_replaced_not_appended_and_served_at_the_tip(state):
    """[st-n0qm.4] The anchored profile rides its own slot: replaced on every
    push, served on every /bars (including since >= total), never retired by
    closed bars — unlike `developing`, which a closed bar supersedes."""
    state.add_bars([], None, None, None, {"v": 1, "n": 10, "buy": [1], "sell": [2]})
    state.add_bars([{"o": 1}], None, None, {"v": 900}, {"v": 1, "n": 25, "buy": [3], "sell": [4]})
    r = state.bars_since(99)
    assert r["bars"] == [] and r["total"] == 1
    assert r["profile"] == {"v": 1, "n": 25, "buy": [3], "sell": [4]}
    assert r["developing"] == {"v": 900}
    state.add_bars([{"o": 2}])            # a bar push without a profile keeps the last profile
    r = state.bars_since(0)
    assert r["profile"]["n"] == 25 and r["developing"] is None
    with pytest.raises(ValueError):
        state.add_bars([], None, None, None, ["not", "an", "object"])
