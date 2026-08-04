"""Pre-open heartbeat — runbook #11 minimal. [st-66u]

The contract under test: hard failures (corpus gate, mancini parse) fail the
run and emit exactly one alert; the soft schwab check never does; the verdict
and every check land as one durable line in the health log.
"""
import json
from datetime import date

import pytest

from runbook import heartbeat


GOOD = {"name": "corpus", "hard": True, "ok": True, "day": "2026-07-30", "reasons": []}
BAD = {"name": "mancini", "hard": True, "ok": False, "day": "2026-07-31",
       "reasons": ["missing 2026-07-31.json — 08:15 parse did not land"]}
SOFT_BAD = {"name": "schwab", "hard": False, "ok": False, "day": "2026-07-31",
            "reasons": ["no clean schwab snapshot — 07:00 premarket stage did not land"]}


def _wire(monkeypatch, checks):
    health, alerts = [], []
    monkeypatch.setattr(heartbeat, "run_checks", lambda: list(checks))
    import scripts.corpus_daily as cd
    monkeypatch.setattr(cd, "_append_health", health.append)
    monkeypatch.setattr(cd, "emit_alert",
                        lambda kind, msg, detail: alerts.append((kind, msg, detail)))
    return health, alerts


def test_all_ok_exits_zero_no_alert(monkeypatch, capsys):
    health, alerts = _wire(monkeypatch, [GOOD])
    assert heartbeat.main([]) == 0
    assert alerts == []
    assert health[0]["level"] == "heartbeat" and health[0]["ok"] is True
    assert "OK" in capsys.readouterr().out


def test_hard_failure_exits_one_and_alerts(monkeypatch, capsys):
    health, alerts = _wire(monkeypatch, [GOOD, BAD])
    assert heartbeat.main([]) == 1
    assert len(alerts) == 1
    kind, msg, _ = alerts[0]
    assert kind == "preopen_heartbeat"
    assert "08:15 parse did not land" in msg
    assert health[0]["ok"] is False


def test_soft_failure_is_reported_but_never_fails(monkeypatch, capsys):
    health, alerts = _wire(monkeypatch, [GOOD, SOFT_BAD])
    assert heartbeat.main([]) == 0
    assert alerts == []
    out = capsys.readouterr().out
    assert "schwab" in out and "premarket stage did not land" in out


def test_broken_check_exits_two(monkeypatch):
    def boom():
        raise RuntimeError("gate exploded")
    monkeypatch.setattr(heartbeat, "run_checks", boom)
    assert heartbeat.main([]) == 2


def test_json_mode(monkeypatch, capsys):
    _wire(monkeypatch, [GOOD, SOFT_BAD])
    assert heartbeat.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert [c["name"] for c in payload["checks"]] == ["corpus", "schwab"]


# --- the real check functions against a fixture tree ------------------------

def _capture_state(tmp_path, monkeypatch, **fields):
    from datetime import datetime, timezone
    doc = {"status": "ok", "message": "capture alive and receiving",
           "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "day": "2026-07-31", "restarts": 0}
    doc.update(fields)
    p = tmp_path / "_capture_health.json"
    p.write_text(json.dumps(doc))
    monkeypatch.setattr(heartbeat, "CAPTURE_STATE", p)
    return p


# --- capture: the overnight streamer, surfaced where it gets read [st-6qx4] --

def test_check_capture_healthy(monkeypatch, tmp_path):
    _capture_state(tmp_path, monkeypatch)
    c = heartbeat.check_capture()
    assert c["ok"] and c["hard"] is False and c["reasons"] == []


def test_check_capture_missing_state_reports_the_supervisor_itself(monkeypatch, tmp_path):
    """No state file means nobody is watching. The absence of the guard has to
    show up on the surface, or it is the Mancini silent-rc=0 failure again."""
    monkeypatch.setattr(heartbeat, "CAPTURE_STATE", tmp_path / "nope.json")
    c = heartbeat.check_capture()
    assert not c["ok"]
    assert "capture-supervisor-wrapper.sh" in c["reasons"][0]


def test_check_capture_reports_a_bad_verdict(monkeypatch, tmp_path):
    _capture_state(tmp_path, monkeypatch, status="dead",
                   message="no capture process, and one is expected")
    c = heartbeat.check_capture()
    assert not c["ok"]
    assert "dead: no capture process" in c["reasons"][0]


def test_check_capture_detects_a_dead_watcher(monkeypatch, tmp_path):
    """A stale state file is its own alarm: the verdict says ok, but it is an
    ok from hours ago and nothing has looked since."""
    _capture_state(tmp_path, monkeypatch, checked_at="2026-07-31T02:00:00Z")
    c = heartbeat.check_capture()
    assert not c["ok"]
    assert "supervisor itself has stopped" in " ".join(c["reasons"])


def test_check_capture_surfaces_overnight_restarts(monkeypatch, tmp_path):
    """Healthy now, but the night had holes — the gap is the thing worth reading."""
    _capture_state(tmp_path, monkeypatch, restarts=3,
                   last_restart_utc="2026-07-31T07:14:00Z")
    c = heartbeat.check_capture()
    assert c["ok"]
    assert "3 supervisor restart(s)" in c["reasons"][0]


def test_capture_is_in_the_default_check_set(monkeypatch, tmp_path):
    _capture_state(tmp_path, monkeypatch)
    monkeypatch.setattr(heartbeat, "check_corpus", lambda: dict(GOOD))
    monkeypatch.setattr(heartbeat, "check_mancini", lambda: dict(GOOD, name="mancini"))
    monkeypatch.setattr(heartbeat, "check_risk", lambda: dict(GOOD, name="risk"))
    monkeypatch.setattr(heartbeat, "check_schwab", lambda: dict(SOFT_BAD))
    assert [c["name"] for c in heartbeat.run_checks()][-1] == "capture"


def test_check_mancini_reads_todays_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat, "PARSED_ROOT", tmp_path)
    monkeypatch.setattr(heartbeat, "central_date", lambda: date(2026, 7, 31))
    assert heartbeat.check_mancini()["ok"] is False
    (tmp_path / "2026-07-31.json").write_text("{}")
    assert heartbeat.check_mancini()["ok"] is True


def test_check_schwab_soft_states(monkeypatch, tmp_path):
    manifest = tmp_path / "manifest.json"
    monkeypatch.setattr(heartbeat, "manifest_path", lambda d: manifest)
    monkeypatch.setattr(heartbeat, "central_date", lambda: date(2026, 7, 31))
    c = heartbeat.check_schwab()
    assert c["ok"] is False and c["hard"] is False

    manifest.write_text(json.dumps({"streams": {"schwab": {"cycles": 1, "errors": []}}}))
    assert heartbeat.check_schwab()["ok"] is True

    manifest.write_text(json.dumps(
        {"streams": {"schwab": {"cycles": 1, "errors": ["get_quotes: boom"]}}}))
    assert heartbeat.check_schwab()["ok"] is False
