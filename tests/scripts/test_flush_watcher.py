"""Flush watcher — shadow safety, dedupe, caps, gating. [st-kos7]

The single most important test here is that shadow mode cannot send: the whole
point of shipping this before st-rtuu measures the trigger is that it is
incapable of reaching Steve's phone.
"""
import json
from datetime import datetime, timezone

import pytest

import scripts.flush_watcher as fw


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "JOURNAL_DIR", tmp_path)
    return tmp_path


def _frame(size=40.0, direction=-1, hhmm="09:15", stale=0.5, start="08:40",
           contested=False, **over):
    f = {
        "ts": f"2026-08-05T{hhmm}:00-05:00",
        "stale_min": stale,
        "levels": {"spx": 7600.0, "vix": 18.2},
        "move": {"size": size, "dir": direction,
                 "start_t": f"2026-08-05T{start}:00-05:00",
                 "contested": contested},
    }
    f.update(over)
    return f


def _events(rig):
    out = []
    for p in rig.glob("flush-watcher-*.jsonl"):
        out += [json.loads(l) for l in p.read_text().splitlines()]
    return out


def test_shadow_mode_cannot_send(rig, monkeypatch):
    """The safety property this whole design rests on."""
    calls = []
    monkeypatch.setattr(fw.alerts, "send",
                        lambda *a, **k: calls.append(a) or pytest.fail("sent in shadow"))
    st = fw.WatchState()
    assert fw.handle(_frame(), st, live=False) is True      # it DID decide to fire
    assert not calls                                        # but nothing was sent
    ev = _events(rig)[-1]
    assert ev["event"] == "would_alert" and ev["mode"] == "shadow"


def test_live_mode_sends_and_journals(rig, monkeypatch):
    sent = {}
    monkeypatch.setattr(fw.alerts, "send",
                        lambda t, m, **k: sent.update(title=t, message=m)
                        or fw.alerts.AlertResult(True, "pushover", "ok", 1))
    st = fw.WatchState()
    assert fw.handle(_frame(), st, live=True)
    assert "FLUSH" in sent["title"] and fw.FIRE_URL in sent["message"]
    assert _events(rig)[-1]["event"] == "alerted"


def test_one_alert_per_move(rig, monkeypatch):
    monkeypatch.setattr(fw.alerts, "send",
                        lambda *a, **k: fw.alerts.AlertResult(True, "x", "ok", 1))
    st = fw.WatchState()
    assert fw.handle(_frame(size=40), st, live=True)
    # same move, now bigger — an extension, not a new event
    assert not fw.handle(_frame(size=55), st, live=True)
    assert _events(rig)[-1]["reason"] == "already alerted this move"


def test_new_move_alerts_again(rig, monkeypatch):
    monkeypatch.setattr(fw.alerts, "send",
                        lambda *a, **k: fw.alerts.AlertResult(True, "x", "ok", 1))
    st = fw.WatchState()
    assert fw.handle(_frame(start="08:40"), st, live=True)
    assert fw.handle(_frame(start="09:50", hhmm="10:00"), st, live=True)


def test_daily_cap_enforced(rig, monkeypatch):
    monkeypatch.setattr(fw.alerts, "send",
                        lambda *a, **k: fw.alerts.AlertResult(True, "x", "ok", 1))
    st = fw.WatchState()
    for i in range(fw.MAX_ALERTS_PER_DAY):
        assert fw.handle(_frame(start=f"09:{10+i}", hhmm=f"09:{20+i}"), st, live=True)
    assert not fw.handle(_frame(start="10:30", hhmm="10:40"), st, live=True)
    assert "daily cap" in _events(rig)[-1]["reason"]


@pytest.mark.parametrize("frame,expect", [
    (_frame(direction=1), "up"),
    (_frame(size=10), "under the"),
    (_frame(hhmm="13:30"), "outside the measured morning window"),
    (_frame(stale=30), "stale"),
    ({"ts": "2026-08-05T09:00:00-05:00", "no_data": True}, "no data"),
    ({"ts": "2026-08-05T07:00:00-05:00", "preopen": True, "opens_in_min": 90}, "pre-open"),
    (_frame(move=None), "no primary move"),
])
def test_gates_stay_quiet_and_say_why(rig, frame, expect):
    fire, reason = fw.evaluate(frame, fw.WatchState())
    assert not fire and expect in reason


def test_quiet_frames_are_journaled_with_reason(rig):
    fw.handle(_frame(size=5), fw.WatchState(), live=False)
    ev = _events(rig)[-1]
    assert ev["event"] == "quiet" and "under the" in ev["reason"]


def test_contested_direction_is_surfaced_in_the_message(rig, monkeypatch):
    sent = {}
    monkeypatch.setattr(fw.alerts, "send",
                        lambda t, m, **k: sent.update(message=m)
                        or fw.alerts.AlertResult(True, "x", "ok", 1))
    fw.handle(_frame(contested=True), fw.WatchState(), live=True)
    assert "CONTESTED" in sent["message"]


def test_read_frames_tolerates_a_partial_last_line(rig, tmp_path):
    p = tmp_path / "meter.jsonl"
    p.write_text(json.dumps({"ts": "x"}) + "\n" + '{"ts": "part')
    frames, off = fw.read_frames(p)
    assert len(frames) == 1 and off > 0
