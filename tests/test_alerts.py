"""Operator alert module — config, retry, journaling. [st-mk56]

No network: the backend callable is monkeypatched. What matters here is that a
failure is loud and journaled, never silent — a dropped meltdown alert must be
visible after the fact.
"""
import json

import pytest

from strader import alerts


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "JOURNAL_DIR", tmp_path)
    return tmp_path


def _env(tmp_path, **kv):
    p = tmp_path / ".env"
    p.write_text("\n".join(f"{k}={v}" for k, v in kv.items()) + "\n")
    return p


def _journal(rig):
    out = []
    for p in rig.glob("alert-journal-*.jsonl"):
        out += [json.loads(l) for l in p.read_text().splitlines()]
    return out


def test_missing_config_fails_loudly_and_journals(rig, tmp_path):
    r = alerts.send("t", "m", env_path=tmp_path / "nonexistent.env")
    assert not r.ok and r.backend == "none"
    ev = _journal(rig)
    assert ev and ev[-1]["event"] == "alert_failed" and ev[-1]["attempts"] == 0


def test_unknown_backend_is_rejected(rig, tmp_path):
    env = _env(tmp_path, ALERT_BACKEND="carrier-pigeon")
    r = alerts.send("t", "m", env_path=env)
    assert not r.ok and "carrier-pigeon" in r.detail


def test_pushover_urgent_uses_emergency_priority(rig, tmp_path, monkeypatch):
    env = _env(tmp_path, ALERT_BACKEND="pushover",
               PUSHOVER_TOKEN="a" * 30, PUSHOVER_USER="b" * 30)
    seen = {}
    monkeypatch.setattr(alerts, "_post",
                        lambda url, data, auth=None: seen.update(data) or '{"status":1}')
    assert alerts.send("Flush", "SPX -40", urgent=True, env_path=env)
    assert seen["priority"] == 2 and seen["retry"] == 60 and seen["expire"] == 1800
    seen.clear()          # the payloads are separate calls, not a merged view
    assert alerts.send("Note", "calm", urgent=False, env_path=env)
    assert seen["priority"] == 1 and "retry" not in seen


def test_retries_then_journals_failure(rig, tmp_path, monkeypatch):
    env = _env(tmp_path, ALERT_BACKEND="pushover",
               PUSHOVER_TOKEN="a" * 30, PUSHOVER_USER="b" * 30)
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise OSError("network down")

    monkeypatch.setattr(alerts, "_post", boom)
    r = alerts.send("Flush", "SPX -40", env_path=env)
    assert not r.ok and len(calls) == alerts.RETRIES and r.attempts == alerts.RETRIES
    ev = _journal(rig)[-1]
    assert ev["event"] == "alert_failed" and "network down" in ev["detail"]


def test_success_after_transient_failure(rig, tmp_path, monkeypatch):
    env = _env(tmp_path, ALERT_BACKEND="pushover",
               PUSHOVER_TOKEN="a" * 30, PUSHOVER_USER="b" * 30)
    n = {"i": 0}

    def flaky(*a, **k):
        n["i"] += 1
        if n["i"] < 2:
            raise OSError("transient")
        return '{"status":1}'

    monkeypatch.setattr(alerts, "_post", flaky)
    r = alerts.send("Flush", "SPX -40", env_path=env)
    assert r.ok and r.attempts == 2
    assert _journal(rig)[-1]["event"] == "alert_sent"


def test_twilio_sends_sms_body(rig, tmp_path, monkeypatch):
    env = _env(tmp_path, ALERT_BACKEND="twilio", TWILIO_SID="sid",
               TWILIO_AUTH="auth", TWILIO_FROM="+15550000", TWILIO_TO="+15551111")
    seen = {}
    monkeypatch.setattr(alerts, "_post",
                        lambda url, data, auth=None: seen.update(data, _auth=auth) or "ok")
    assert alerts.send("Flush", "SPX -40", env_path=env)
    assert seen["To"] == "+15551111" and "Flush: SPX -40" == seen["Body"]
    assert seen["_auth"] == ("sid", "auth")


def test_send_never_raises_on_any_backend_error(rig, tmp_path, monkeypatch):
    env = _env(tmp_path, ALERT_BACKEND="pushover",
               PUSHOVER_TOKEN="a" * 30, PUSHOVER_USER="b" * 30)
    monkeypatch.setattr(alerts, "_post",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("weird")))
    r = alerts.send("t", "m", env_path=env)      # must not propagate
    assert not r.ok


def test_pushover_email_paste_is_caught_with_the_fix(rig, tmp_path):
    """Pasting the email-gateway address into PUSHOVER_USER must fail here,
    not opaquely at the API. Steve hit this during setup 2026-08-05."""
    env = _env(tmp_path, ALERT_BACKEND="pushover",
               PUSHOVER_TOKEN="a" * 30, PUSHOVER_USER="steve+abc123@pomail.net")
    r = alerts.send("t", "m", env_path=env)
    assert not r.ok
    assert "email gateway" in r.detail and "apps/build" in r.detail


def test_pushover_wrong_length_key_is_caught(rig, tmp_path):
    env = _env(tmp_path, ALERT_BACKEND="pushover",
               PUSHOVER_TOKEN="short", PUSHOVER_USER="b" * 30)
    r = alerts.send("t", "m", env_path=env)
    assert not r.ok and "30 alphanumeric" in r.detail
