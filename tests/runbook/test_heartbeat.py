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
