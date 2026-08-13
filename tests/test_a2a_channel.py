"""Anchors for the A2A channel: the inbox ledger parser and the gc-mail stub.

These exist because both pieces fail in the same silent way if they rot — a
malformed ledger line that stops being counted, or a hook regex that stops
matching, reproduces exactly the "channel is dead and says nothing" failure the
channel was built to end (st-75z0).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "a2a_inbox.py"
STUB = REPO / ".claude" / "hooks" / "scripts" / "gc-mail-stub.sh"
INBOX = REPO / "docs" / "a2a" / "inbox.md"


def _load_tool():
    spec = importlib.util.spec_from_file_location("a2a_inbox", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


a2a = _load_tool()


def _ledger(rows: str) -> str:
    return "# fake\n\n## Ledger\n\n| WHEN | ACTOR | KIND | BEAD | REF | PATHS | WHY |\n|---|---|---|---|---|---|---|\n" + rows


# --- ledger parsing -------------------------------------------------------


def test_real_inbox_has_no_malformed_lines():
    """The live ledger must parse clean — a dropped row is an unseen event."""
    events, problems = a2a.parse_inbox(INBOX)
    assert problems == []
    assert events, "ledger parsed to zero events"


def test_example_rows_above_the_ledger_are_not_counted(tmp_path):
    """Doc examples live in the header; only rows under `## Ledger` are events."""
    p = tmp_path / "inbox.md"
    p.write_text(
        "# doc\n\n| 2026-08-13 09:14 CT | COO | COMMIT | co-x | abc1234 | CLAUDE.md | header example |\n"
        + _ledger("| 2026-08-13 10:00 CT | COO | COMMIT | co-y | def5678 | CLAUDE.md | real |\n"),
        encoding="utf-8",
    )
    events, problems = a2a.parse_inbox(p)
    assert problems == []
    assert [e.bead for e in events] == ["co-y"]


def test_malformed_rows_are_reported_not_swallowed(tmp_path):
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger(
            "| 2026-08-13 10:00 CT | COO | COMMIT | co-y | def5678 | CLAUDE.md |\n"  # 6 fields
            "| yesterday | COO | MEMO | co-z | ref | - | bad timestamp |\n"
            "| 2026-08-13 11:00 CT | COO | SHOUT | co-w | ref | - | unknown kind |\n"
        ),
        encoding="utf-8",
    )
    events, problems = a2a.parse_inbox(p)
    assert events == []
    assert len(problems) == 3


def test_retired_kind_still_parses_on_historical_rows(tmp_path):
    """Retiring a word must not rewrite history. [st-qfsz]

    COMMIT was the vocabulary before 2026-08-13. Rows written under it are
    valid history and must keep parsing, or the ledger loses its own past the
    day the vocabulary changes.
    """
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger("| 2026-08-11 09:00 CT | COO | COMMIT | co-y | ref | CLAUDE.md | old vocabulary |\n"),
        encoding="utf-8")
    events, problems = a2a.parse_inbox(p)
    assert problems == []
    assert [e.kind for e in events] == ["COMMIT"]


def test_retired_kind_is_flagged_on_new_rows_but_the_event_is_kept(tmp_path):
    """The enforcement, and the thing it must not do. [st-qfsz]

    A COMMIT dated after the ruling is a problem — that is what turns the suite
    red the first time anyone writes the retired word. But the row is STILL
    recorded, because losing an event to a vocabulary complaint is exactly the
    failure this reconciliation came from: four correctly-announced COO rows
    went invisible on the day one reported a live risk to the corpus.
    """
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger("| 2026-08-14 09:00 CT | COO | COMMIT | co-y | ref | CLAUDE.md | new row |\n"),
        encoding="utf-8")
    events, problems = a2a.parse_inbox(p)
    assert len(problems) == 1 and "retired" in problems[0] and "WRITE" in problems[0]
    assert [e.kind for e in events] == ["COMMIT"]   # flagged, not swallowed


@pytest.mark.parametrize("kind", sorted(a2a.WRITABLE_KINDS))
def test_every_writable_kind_parses(kind):
    """No word a peer is told to use may be rejected by the parser. [st-qfsz]"""
    assert kind in a2a.KINDS
    assert kind not in a2a.RETIRED_KINDS


# --- receipts -------------------------------------------------------------


def test_memo_without_receipt_is_open(tmp_path):
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger("| 2026-08-11 07:52 CT | COO | MEMO | co-65gj | 2026-08-11-coo-to-strader-x | - | asks |\n"),
        encoding="utf-8",
    )
    events, _ = a2a.parse_inbox(p)
    assert [e.ref for e in a2a.open_memos(events)] == ["2026-08-11-coo-to-strader-x"]


@pytest.mark.parametrize("kind", ["ACK", "SERVICED"])
def test_receipt_closes_the_memo(tmp_path, kind):
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger(
            "| 2026-08-11 07:52 CT | COO | MEMO | co-65gj | 2026-08-11-coo-to-strader-x | - | asks |\n"
            f"| 2026-08-11 09:00 CT | Strader | {kind} | st-1 | 2026-08-11-coo-to-strader-x | - | answered |\n"
        ),
        encoding="utf-8",
    )
    events, _ = a2a.parse_inbox(p)
    assert a2a.open_memos(events) == []


def test_receipt_must_match_the_ref(tmp_path):
    """A receipt with the wrong REF leaves the memo open — the failure to catch."""
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger(
            "| 2026-08-11 07:52 CT | COO | MEMO | co-65gj | 2026-08-11-coo-to-strader-x | - | asks |\n"
            "| 2026-08-11 09:00 CT | Strader | ACK | st-1 | 2026-08-11-coo-to-strader-TYPO | - | answered |\n"
        ),
        encoding="utf-8",
    )
    events, _ = a2a.parse_inbox(p)
    assert len(a2a.open_memos(events)) == 1


def test_staleness_threshold_is_three_sessions():
    memo = datetime(2026, 8, 1, 9, 0)
    stamps = [datetime(2026, 8, d, 9, 0) for d in (2, 3, 4)]
    assert a2a.sessions_since(memo, stamps[:2]) < a2a.STALE_SESSIONS
    assert a2a.sessions_since(memo, stamps) >= a2a.STALE_SESSIONS


def test_session_clock_reads_handoff_headings():
    """Handoffs are the session clock; if this returns nothing, staleness dies."""
    assert len(a2a.session_times(REPO)) > 10


# --- gc-mail stub ---------------------------------------------------------


def _run_stub(command: str) -> int:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        ["bash", str(STUB)], input=payload, capture_output=True, text=True
    ).returncode


@pytest.mark.parametrize(
    "command",
    [
        "gc mail send coo",
        "gc",
        "/usr/local/bin/gc doctor",
        "cat foo.txt && gc mail check",
        "ls | gc mail",
        "echo hi; gc mail count",
        "sudo gc mail",
    ],
)
def test_gc_invocation_is_blocked(command):
    assert _run_stub(command) == 2


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "gc mail is dead"',
        "grep -rn gc docs/",
        "gcc --version",
        "gcloud auth list",
        "python3 tools/a2a_inbox.py",
        "python3 tools/gc.py",
    ],
)
def test_non_gc_commands_pass(command):
    assert _run_stub(command) == 0


def test_stub_points_at_the_replacement_channel():
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "gc mail send coo"}})
    out = subprocess.run(["bash", str(STUB)], input=payload, capture_output=True, text=True)
    assert "docs/a2a/" in out.stderr
    assert out.stdout == ""  # hook messaging goes to stderr, never stdout
