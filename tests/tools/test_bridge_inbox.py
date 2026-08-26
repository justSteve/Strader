"""In-session surfacing of bridge memos addressed to Strader. [st-92m7]

The bug this guards: on 2026-08-25 a Desk ruling sat unread for 9h35m, not
because it was mis-routed but because Strader's only surfacing ran at tap-in.
So the tests that matter are about the SESSION-SCALE behaviour — a memo that
arrives after start-up is reported, a quiet bridge says nothing, and an absent
Windows mount is silence rather than a crash.
"""
import json
import time
from pathlib import Path

import pytest

from tools import bridge_inbox as bi


HEADER = ("# {title}\n\n"
          "**class:** {klass} · **from:** {sender} · **for:** COO, Strader\n\n"
          "body\n")


@pytest.fixture
def bridge(tmp_path):
    (tmp_path / "Strader" / "inbox").mkdir(parents=True)
    return tmp_path


def drop(bridge, name, sender="Desk", klass="ruling", age_s=0):
    p = bridge / "Strader" / "inbox" / name
    p.write_text(HEADER.format(title=name, klass=klass, sender=sender),
                 encoding="utf-8")
    if age_s:
        old = time.time() - age_s
        import os
        os.utime(p, (old, old))
    return p


# ── reading ────────────────────────────────────────────────────────────────

def test_an_empty_inbox_reports_nothing_and_exits_clean(bridge, capsys):
    assert bi.main(["--bridge", str(bridge)]) == 0
    assert "empty" in capsys.readouterr().out


def test_an_absent_mount_is_silence_not_a_crash(tmp_path):
    """The Windows host is often away. A start-up path must never die on it."""
    assert bi.scan(str(tmp_path / "no-such-bridge")) == []


def test_a_waiting_memo_is_reported_with_sender_class_and_recipients(bridge, capsys):
    drop(bridge, "20260826T012334__Desk__ruling-9.md", klass="ruling")
    assert bi.main(["--bridge", str(bridge)]) == 1
    out = capsys.readouterr().out
    assert "1 waiting for Strader" in out
    assert "Desk" in out and "ruling" in out
    assert "COO, Strader" in out


def test_exit_code_one_means_something_is_waiting(bridge):
    assert bi.main(["--bridge", str(bridge)]) == 0
    drop(bridge, "20260826T012334__Desk__x.md")
    assert bi.main(["--bridge", str(bridge)]) == 1


def test_the_oldest_memo_sorts_first(bridge, capsys):
    drop(bridge, "20260826T010000__Desk__new.md", age_s=60)
    drop(bridge, "20260826T000000__Desk__old.md", age_s=36000)
    bi.main(["--bridge", str(bridge)])
    out = capsys.readouterr().out
    assert out.index("old") < out.index("new")


def test_a_headerless_memo_still_surfaces(bridge, capsys):
    """Pre-2026-08 memos carry no header. A parser that refused them would
    silence exactly the backlog this tool exists to surface, so the filename
    convention is the fallback."""
    p = bridge / "Strader" / "inbox" / "20260819T054837__co__bar-339.md"
    p.write_text("# just a title\n\nbody\n", encoding="utf-8")
    assert bi.main(["--bridge", str(bridge)]) == 1
    out = capsys.readouterr().out
    assert "co" in out and "bar-339" in out


def test_json_output_is_machine_readable(bridge, capsys):
    drop(bridge, "20260826T012334__Desk__ruling-9.md")
    bi.main(["--bridge", str(bridge), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["memos"][0]["sender"] == "Desk"


# ── the ledger join ────────────────────────────────────────────────────────

def test_the_stem_is_the_join_key_to_the_ledger(bridge, monkeypatch, tmp_path):
    """A MEMO/ACK row's REF column carries the memo filename without `.md`,
    so a memo already logged must not be re-logged."""
    ledger = tmp_path / "inbox.md"
    ledger.write_text("| x | Strader | ACK | st-1 | 20260826T012334__Desk__ruling-9 | - | y |\n")
    monkeypatch.setattr(bi, "LEDGER", ledger)
    drop(bridge, "20260826T012334__Desk__ruling-9.md")
    drop(bridge, "20260826T014102__Desk__ruling-10.md")
    memos = bi.scan(str(bridge))
    assert {m.stem: m.in_ledger for m in memos} == {
        "20260826T012334__Desk__ruling-9": True,
        "20260826T014102__Desk__ruling-10": False,
    }
    rows = bi.ledger_rows(memos, "2026-08-26 02:00 CT")
    assert len(rows) == 1 and "ruling-10" in rows[0]


def test_a_ledger_row_matches_the_format_contract(bridge, monkeypatch, tmp_path):
    ledger = tmp_path / "inbox.md"
    ledger.write_text("")
    monkeypatch.setattr(bi, "LEDGER", ledger)
    drop(bridge, "20260826T012334__Desk__ruling-9.md")
    rows = bi.ledger_rows(bi.scan(str(bridge)), "2026-08-26 02:00 CT")
    fields = [f.strip() for f in rows[0].strip("|").split("|")]
    assert len(fields) == 7, "WHEN|ACTOR|KIND|BEAD|REF|PATHS|WHY"
    assert fields[1] == "Strader" and fields[2] == "MEMO"
    assert fields[3] == "st-92m7" and fields[4] == "20260826T012334__Desk__ruling-9"
    assert "NOTE" not in fields[2], "retired kind, st-xa5p"


def test_appending_no_rows_leaves_the_ledger_untouched(monkeypatch, tmp_path):
    ledger = tmp_path / "inbox.md"
    ledger.write_text("original\n")
    monkeypatch.setattr(bi, "LEDGER", ledger)
    assert bi.append_rows([]) == 0
    assert ledger.read_text() == "original\n"


def test_the_ledger_timestamp_is_central_never_utc(monkeypatch):
    """Every human-facing stamp renders CT. A UTC row in this column reads as
    a five-hour-old memo that just arrived."""
    stamp = bi._now_ct()
    assert stamp.endswith(" CT")
    import datetime
    datetime.datetime.strptime(stamp[:-3].strip(), "%Y-%m-%d %H:%M")


# ── the watch: every printed line is a model wake ──────────────────────────

def test_the_watch_is_seeded_and_does_not_replay_the_backlog(bridge, capsys):
    """Arming mid-session must not re-report what tap-in already showed."""
    drop(bridge, "20260826T010000__Desk__already-here.md")
    bi.watch(interval=1, bridge=str(bridge), once=True)
    assert capsys.readouterr().out == ""


def test_a_quiet_bridge_wakes_nobody(bridge, capsys):
    bi.watch(interval=1, bridge=str(bridge), once=True)
    assert capsys.readouterr().out == ""


def test_an_arrival_prints_exactly_one_wake(bridge, capsys, monkeypatch):
    """The whole point: a memo landing DURING a session is surfaced without
    waiting for the next tap-in."""
    real_sleep = time.sleep

    def sleep_then_deliver(_):
        drop(bridge, "20260826T013442__Desk__intent.md", klass="intent")
        real_sleep(0)

    monkeypatch.setattr(bi.time, "sleep", sleep_then_deliver)
    bi.watch(interval=1, bridge=str(bridge), once=True)
    out = capsys.readouterr().out
    assert out.count("[BRIDGE]") == 1
    assert "intent" in out and "Desk" in out


def test_only_strader_inbox_is_read(bridge, capsys):
    """Deliberate scope. The superseded fix proposed scanning peer OUTBOX and
    _archive folders for a `for:` naming Strader — that addresses a failure
    that did not happen and reads other agents' mail to do it."""
    (bridge / "Desk" / "inbox").mkdir(parents=True)
    (bridge / "Desk" / "inbox" / "20260826T012334__Desk__for-strader.md").write_text(
        HEADER.format(title="t", klass="ruling", sender="Desk"), encoding="utf-8")
    (bridge / "Strader" / "_archive").mkdir(parents=True)
    (bridge / "Strader" / "_archive" / "20260825T143000__Desk__done.md").write_text(
        HEADER.format(title="t", klass="ruling", sender="Desk"), encoding="utf-8")
    assert bi.scan(str(bridge)) == []
