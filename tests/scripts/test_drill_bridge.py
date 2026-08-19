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


def test_coach_point_and_clear_are_accepted(state):
    """The coach cursor verbs [st-135m]: point {bar, price, text, pulse, hold_ms}
    and clear — the page draws/removes a pointer; the bridge only relays."""
    a = state.add_coach({"type": "point", "bar": 66, "price": 7730.75,
                         "text": "POC of the 730-delta bar", "pulse": True})
    b = state.add_coach({"type": "clear"})
    got = state.commands_since(0)
    assert [c["type"] for c in got] == ["point", "clear"]
    assert got[0]["price"] == 7730.75 and got[0]["bar"] == 66 and got[0]["pulse"] is True
    assert (a["id"], b["id"]) == (1, 2)


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


def test_alerts_append_with_ids_and_poll_incrementally(state):
    """[st-n0qm.9] Sentinel alerts ride their own append-only channel; the
    bridge adds id + received_utc and nothing else — the shape is the
    sentinel's."""
    a1 = state.add_alert({"kind": "approach", "strike": 7805, "ts_row": "2026-08-14T13:30:04Z"})
    a2 = state.add_alert({"kind": "contested", "strike": 7800})
    assert (a1["id"], a2["id"]) == (1, 2) and "received_utc" in a1
    assert a1["kind"] == "approach" and a1["strike"] == 7805
    r = state.alerts_since(0)
    assert [a["id"] for a in r["alerts"]] == [1, 2] and r["total"] == 2
    r = state.alerts_since(2)
    assert r["alerts"] == [] and r["total"] == 2
    assert state.alerts_since(99)["alerts"] == []
    with pytest.raises(ValueError):
        state.add_alert({})
    with pytest.raises(ValueError):
        state.add_alert(["nope"])
    log = state.log_path.read_text().splitlines()
    assert any('"channel":"alerts"' in l and '"kind":"approach"' in l for l in log)


def test_a_new_session_day_resets_everything_the_day_owns(state):
    """[st-n0qm.9] The bridge outlives the day; the feeder does not. When a
    /bars push carries meta.day different from the held day, bars, final,
    developing, profile and alerts all reset — Tuesday never appends onto
    Monday. Same-day meta (a feeder restart mid-day) resets nothing."""
    state.add_bars([{"o": 1}, {"o": 2}], {"day": "2026-08-17", "bar_n": 2000},
                   [{"type": "Level"}], {"v": 5}, {"v": 1, "n": 9})
    state.add_alert({"kind": "approach", "strike": 7805})
    # same day, meta re-posted (feeder restarted): keep it all
    state.add_bars([{"o": 3}], {"day": "2026-08-17", "bar_n": 2000})
    r = state.bars_since(0)
    assert r["total"] == 3 and r["final"] and r["profile"]
    assert state.alerts_since(0)["total"] == 1
    # new day: everything goes, the new push is index 0
    state.add_bars([{"o": 10}], {"day": "2026-08-18", "bar_n": 2000})
    r = state.bars_since(0)
    assert r["total"] == 1 and r["bars"][0]["i"] == 0 and r["bars"][0]["o"] == 10
    assert r["final"] == [] and r["developing"] is None and r["profile"] is None
    assert r["meta"]["day"] == "2026-08-18"
    a = state.alerts_since(0)
    assert a["total"] == 0 and a["day"] == "2026-08-18"
    log = state.log_path.read_text().splitlines()
    assert any('"kind":"day_reset"' in l and '"dropped_bars":3' in l
               and '"dropped_alerts":1' in l for l in log)


def test_alerts_seed_from_the_days_durable_file_at_start(state, tmp_path):
    """[st-n0qm.9] orderflow_alerts.jsonl is the record; the bridge is a
    display. At start it loads the day's file so a restart or a late-opened
    page still shows the morning's rows; a non-empty channel is left alone."""
    f = tmp_path / "orderflow_alerts.jsonl"
    f.write_text('{"kind":"approach","strike":7805,"ts_alert_utc":"2026-08-14T13:30:04Z"}\n'
                 'not json\n\n'
                 '{"kind":"contested","strike":7800,"ts_alert_utc":"2026-08-14T13:31:12Z"}\n',
                 encoding="utf-8")
    assert state.seed_alerts(f) == 2
    r = state.alerts_since(0)
    assert [a["id"] for a in r["alerts"]] == [1, 2] and all(a["seeded"] for a in r["alerts"])
    assert r["alerts"][0]["received_utc"] == "2026-08-14T13:30:04Z"
    assert state.seed_alerts(f) == 0, "a second seed onto a non-empty channel is a no-op"
    live = state.add_alert({"kind": "approach", "strike": 7810})
    assert live["id"] == 3 and "seeded" not in live
    assert state.seed_alerts(tmp_path / "missing.jsonl") == 0


# ── drill mode [st-v7a0] ─────────────────────────────────────────────────────

def _corpus_with_days(root, days):
    for d in days:
        (root / d).mkdir(parents=True)
        (root / d / "databento_glbx_es.jsonl").write_text('{"x":1}\n')
    # a packed day and a day with no ES tape (must not be listed)
    (root / "2026-07-01").mkdir(parents=True)
    (root / "2026-07-01" / "databento_glbx_es.jsonl.gz").write_bytes(b"\x1f\x8b")
    (root / "2026-07-04").mkdir(parents=True)
    (root / "2026-07-04" / "gexbot.jsonl").write_text("")
    (root / "notaday").mkdir(parents=True)


def test_corpus_days_lists_es_days_newest_first(tmp_path):
    import drill_bridge as db
    root = tmp_path / "corpus"
    _corpus_with_days(root, ["2026-08-17", "2026-08-14", "2026-08-18"])
    assert db.corpus_days(corpus_root=root) == ["2026-08-18", "2026-08-17", "2026-08-14", "2026-07-01"]
    assert db.corpus_days(limit=2, corpus_root=root) == ["2026-08-18", "2026-08-17"]
    assert db.corpus_days(corpus_root=tmp_path / "missing") == []


def test_ensure_drill_renders_once_and_rerenders_when_the_tape_grows(monkeypatch, tmp_path):
    import os
    import time
    import drill_bridge as db
    root = tmp_path / "corpus"
    _corpus_with_days(root, ["2026-08-17"])
    monkeypatch.setattr(db, "CORPUS_ROOT", root)
    monkeypatch.setattr(db, "DRILL_TEMPLATE", tmp_path / "no-template.html")
    ddir = tmp_path / "drills"
    calls = []

    def fake_render(day, out):
        calls.append(day)
        out.write_text(f"<html>drill {day} v{len(calls)}</html>")
        (out.parent / f"desk-candles-{day}.html").write_text("<html>candles</html>")

    src = root / "2026-08-17" / "databento_glbx_es.jsonl"
    t = 1_800_000_000
    os.utime(src, (t, t))
    p = db.ensure_drill("2026-08-17", drill_dir=ddir, render=fake_render, now=t + 10)
    assert p == ddir / "drill-2026-08-17.html" and calls == ["2026-08-17"]
    os.utime(p, (t + 10, t + 10))
    # source untouched → cache served, no re-render
    db.ensure_drill("2026-08-17", drill_dir=ddir, render=fake_render, now=t + 20)
    assert calls == ["2026-08-17"]
    # source grew (still-capturing day) but the cache is < 60 s old → still cached
    os.utime(src, (t + 15, t + 15))
    db.ensure_drill("2026-08-17", drill_dir=ddir, render=fake_render, now=t + 30)
    assert calls == ["2026-08-17"]
    # source newer AND cache older than the re-render floor → re-render
    db.ensure_drill("2026-08-17", drill_dir=ddir, render=fake_render, now=t + 10 + 61)
    assert calls == ["2026-08-17", "2026-08-17"]
    assert "v2" in p.read_text()
    # the template changed after the cache was built → re-render even though
    # the tape did not move (a template fix must reach already-rendered days)
    os.utime(p, (t + 200, t + 200)); os.utime(src, (t + 15, t + 15))
    tpl = tmp_path / "tpl.html"; tpl.write_text("<html>"); os.utime(tpl, (t + 300, t + 300))
    monkeypatch.setattr(db, "DRILL_TEMPLATE", tpl)
    db.ensure_drill("2026-08-17", drill_dir=ddir, render=fake_render, now=t + 210)
    assert calls == ["2026-08-17"] * 3
    os.utime(p, (t + 400, t + 400))
    db.ensure_drill("2026-08-17", drill_dir=ddir, render=fake_render, now=t + 410)
    assert calls == ["2026-08-17"] * 3
    # no tape for the day → FileNotFoundError; garbage → ValueError
    with pytest.raises(FileNotFoundError):
        db.ensure_drill("2026-08-19", drill_dir=ddir, render=fake_render)
    with pytest.raises(ValueError):
        db.ensure_drill("../etc/passwd", drill_dir=ddir, render=fake_render)


def test_ensure_drill_surfaces_a_renderer_failure(monkeypatch, tmp_path):
    import drill_bridge as db
    root = tmp_path / "corpus"
    _corpus_with_days(root, ["2026-08-17"])
    monkeypatch.setattr(db, "CORPUS_ROOT", root)

    def broken(day, out):
        raise RuntimeError("drill render for 2026-08-17 failed (rc=1): boom")
    with pytest.raises(RuntimeError, match="boom"):
        db.ensure_drill("2026-08-17", drill_dir=tmp_path / "drills", render=broken)


def test_drill_routes_serve_days_drill_and_candles_under_the_prefix(monkeypatch, tmp_path):
    """/days lists the tape days; /drill-<day>.html renders on demand and serves
    the drill; /desk-candles-<day>.html serves the companion the drill's
    'Candles ↗' opens beside itself; all under the /footprint mount."""
    import drill_bridge as db
    base, stop = _serve(monkeypatch, tmp_path, "<title>x</title>")
    root = tmp_path / "corpus"
    _corpus_with_days(root, ["2026-08-17", "2026-08-18"])
    ddir = tmp_path / "drills"
    monkeypatch.setattr(db, "DRILL_DIR", ddir)

    def fake_render(day, out):
        out.write_text(f"<html><title>Orderflow Drill</title>{day}</html>")
        (out.parent / f"desk-candles-{day}.html").write_text(f"<html>candles {day}</html>")
    monkeypatch.setattr(db, "_render_drill", fake_render)
    try:
        code, _, body = _get(base + "/footprint/days")
        d = json.loads(body)
        assert code == 200 and d["days"][:2] == ["2026-08-18", "2026-08-17"] and "live_day" in d
        code, hdrs, body = _get(base + "/footprint/drill-2026-08-17.html")
        assert code == 200 and hdrs["Content-Type"].startswith("text/html")
        assert b"Orderflow Drill" in body and b"2026-08-17" in body
        code, _, body = _get(base + "/footprint/desk-candles-2026-08-17.html")
        assert code == 200 and b"candles 2026-08-17" in body
        # unknown day: 404 with the days on offer; candles before drill: 404
        code, _, body = _get(base + "/footprint/drill-2026-08-19.html")
        assert code == 404 and "days" in json.loads(body)
        code, _, _ = _get(base + "/footprint/desk-candles-2026-08-18.html")
        assert code == 404
        code, _, _ = _get(base + "/drill-nope.html")
        assert code == 400
    finally:
        stop()


def test_a_feeder_rerun_on_the_same_day_replaces_the_bars_instead_of_doubling_them(state):
    """[st-fgno] A restarted feeder re-posts the day from index 0 with a meta
    whose `started` differs. That must replace the held bars, not append to
    them; alerts and the profile survive (they are not the feeder's to drop).
    A same-day meta with the SAME started (or none) still resets nothing."""
    m1 = {"day": "2026-08-18", "bar_n": 2000, "started": "2026-08-18T00:00:10"}
    state.add_bars([{"o": 1}, {"o": 2}, {"o": 3}], m1, None, None, {"v": 1, "n": 9})
    state.add_alert({"kind": "approach", "strike": 7805})
    state.add_bars([{"o": 4}], m1)                       # same run, meta re-sent
    assert state.bars_since(0)["total"] == 4
    m2 = {"day": "2026-08-18", "bar_n": 2000, "started": "2026-08-18T09:15:02"}
    state.add_bars([{"o": 1}, {"o": 2}], m2)             # new run re-posting from 0
    r = state.bars_since(0)
    assert r["total"] == 2 and [b["o"] for b in r["bars"]] == [1, 2]
    assert r["profile"] == {"v": 1, "n": 9}
    assert state.alerts_since(0)["total"] == 1
    assert any('"kind":"rerun_reset"' in l and '"dropped_bars":4' in l
               for l in state.log_path.read_text().splitlines())
    # meta without `started` on either side: legacy shape, no reset
    state.add_bars([{"o": 9}], {"day": "2026-08-18", "bar_n": 2000})
    assert state.bars_since(0)["total"] == 3
