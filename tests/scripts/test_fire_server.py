"""Fire server Phase 1 rails. [st-1o47]

Every test drives the real Flask app through its test client with the data
paths pointed at tmp_path — no tailscale, no network, no real journal.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import scripts.fire_server as fs


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "TICKET_PATH", tmp_path / "fire-ticket.json")
    monkeypatch.setattr(fs, "KILL_PATH", tmp_path / "FIRE_DISABLED")
    monkeypatch.setattr(fs, "JOURNAL_DIR", tmp_path)
    fs._nonces.clear()
    return tmp_path


def _stage(rig, **over):
    t = dict(id="t1", ts_staged=datetime.now(timezone.utc).isoformat(),
             symbol="SPXW  260805P07700000", side="BUY_TO_OPEN", qty=1,
             limit=5.5, note="test", staged_by="test")
    t.update(over)
    (rig / "fire-ticket.json").write_text(json.dumps(t))
    return t


def _journal_events(rig):
    out = []
    for p in rig.glob("fire-journal-*.jsonl"):
        out += [json.loads(l) for l in p.read_text().splitlines()]
    return out


def _client():
    fs.app.config["TESTING"] = True
    return fs.app.test_client()


def test_no_ticket_shows_empty_state(rig):
    r = _client().get("/")
    assert b"No ticket staged" in r.data and b"ARM" not in r.data


def test_arm_then_fire_dry_run_journals(rig):
    _stage(rig)
    c = _client()
    r = c.post("/arm")
    assert r.status_code == 200 and b"FIRE" in r.data
    nonce = r.data.split(b"name=nonce value='")[1].split(b"'")[0].decode()
    r2 = c.post("/fire", data={"nonce": nonce})
    assert r2.status_code == 200 and b"DRY RUN COMPLETE" in r2.data
    events = [e["event"] for e in _journal_events(rig)]
    assert events == ["armed", "fire"]
    fired = _journal_events(rig)[-1]
    assert fired["transmitted"] is False and fired["mode"] == "dry-run"


def test_nonce_is_single_use(rig):
    _stage(rig)
    c = _client()
    nonce = c.post("/arm").data.split(b"name=nonce value='")[1].split(b"'")[0].decode()
    assert c.post("/fire", data={"nonce": nonce}).status_code == 200
    r = c.post("/fire", data={"nonce": nonce})
    assert r.status_code == 409 and b"re-ARM" in r.data


def test_nonce_expires(rig, monkeypatch):
    _stage(rig)
    c = _client()
    nonce = c.post("/arm").data.split(b"name=nonce value='")[1].split(b"'")[0].decode()
    monkeypatch.setattr(fs._time, "time", lambda: 10**12)   # far future
    assert c.post("/fire", data={"nonce": nonce}).status_code == 409


def test_kill_switch_blocks_everything(rig):
    _stage(rig)
    (rig / "FIRE_DISABLED").touch()
    c = _client()
    assert b"KILL SWITCH" in c.get("/").data
    assert c.post("/arm").status_code == 409
    assert c.post("/fire", data={"nonce": "x"}).status_code == 409


def test_stale_ticket_cannot_arm(rig):
    old = (datetime.now(timezone.utc) - timedelta(minutes=fs.STALE_MIN + 1)).isoformat()
    _stage(rig, ts_staged=old)
    c = _client()
    assert b"STALE" in c.get("/").data
    assert c.post("/arm").status_code == 409


def test_qty_over_cap_cannot_arm(rig):
    _stage(rig, qty=fs.QTY_CAP + 1)
    c = _client()
    assert b"exceeds hard cap" in c.get("/").data
    assert c.post("/arm").status_code == 409


def test_malformed_json_is_loud_not_silent(rig):
    (rig / "fire-ticket.json").write_text("{not json")
    r = _client().get("/")
    assert b"not valid JSON" in r.data
    assert _client().post("/arm").status_code == 409


def test_fire_rechecks_stale_after_arm(rig, monkeypatch):
    """The market can go stale between ARM and FIRE — FIRE re-validates."""
    _stage(rig)
    c = _client()
    nonce = c.post("/arm").data.split(b"name=nonce value='")[1].split(b"'")[0].decode()
    old = (datetime.now(timezone.utc) - timedelta(minutes=fs.STALE_MIN + 1)).isoformat()
    _stage(rig, ts_staged=old)
    r = c.post("/fire", data={"nonce": nonce})
    assert r.status_code == 409 and b"stale" in r.data


def test_idle_page_refreshes_armed_page_does_not(rig):
    """Auto-refresh on the armed page would 405 and yank FIRE mid-decision."""
    _stage(rig)
    c = _client()
    assert b"http-equiv=refresh" in c.get("/").data
    assert b"http-equiv=refresh" not in c.post("/arm").data


def test_get_on_action_routes_redirects_home_not_405(rig):
    _stage(rig)
    c = _client()
    for path in ("/arm", "/fire"):
        r = c.get(path)
        assert r.status_code == 303, f"{path} should redirect, got {r.status_code}"
        assert r.headers["Location"].endswith("/")
