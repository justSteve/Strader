"""Anchors for the A2A channel: the inbox ledger parser and the gc-mail stub.

These exist because both pieces fail in the same silent way if they rot — a
malformed ledger line that stops being counted, or a hook regex that stops
matching, reproduces exactly the "channel is dead and says nothing" failure the
channel was built to end (st-75z0).
"""

from __future__ import annotations

import importlib.util
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "a2a_inbox.py"
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


@pytest.mark.parametrize("kind", sorted(a2a.RETIRED_KINDS))
def test_every_retired_kind_has_its_own_start_date(kind):
    """Retirement is per word. A second retirement must not backdate the first."""
    assert kind in a2a.RETIRED_FROM
    assert a2a.RETIRED_KINDS[kind] in a2a.WRITABLE_KINDS


def test_note_rows_written_before_the_ruling_are_clean_history(tmp_path):
    """COO's 2026-08-18/19 NOTE rows are real events and must count. [st-xa5p]"""
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger("| 2026-08-18 12:58 CT | COO | NOTE | co-y | ref | CLAUDE.md | attribution |\n"),
        encoding="utf-8")
    events, problems = a2a.parse_inbox(p)
    assert problems == []
    assert [e.kind for e in events] == ["NOTE"]


def test_note_written_from_now_on_is_flagged_toward_status(tmp_path):
    """A NOTE dated after its ruling turns the suite red, pointing at STATUS."""
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger("| 2026-08-21 09:00 CT | COO | NOTE | co-y | ref | CLAUDE.md | new row |\n"),
        encoding="utf-8")
    events, problems = a2a.parse_inbox(p)
    assert len(problems) == 1 and "retired" in problems[0] and "STATUS" in problems[0]
    assert [e.kind for e in events] == ["NOTE"]   # flagged, not swallowed


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


def test_directive_starts_no_receipt_clock(tmp_path):
    """Desk Ruling 15: a DIRECTIVE is an order, not an ask — it owes no reply.

    The whole point of admitting the word rather than folding it into MEMO is
    that MEMO starts a clock and a directive must not. If this ever regresses,
    every relayed order from Steve shows up as a peer owing Strader an answer.
    """
    p = tmp_path / "inbox.md"
    p.write_text(
        _ledger("| 2026-08-27 08:40 CT | Desk | DIRECTIVE | st-l711 | 20260827T084005__Desk__ruling-15 | - | orders |\n"),
        encoding="utf-8",
    )
    events, problems = a2a.parse_inbox(p)
    assert problems == []
    assert len(events) == 1 and events[0].kind == "DIRECTIVE"
    assert a2a.open_memos(events) == []


def test_directive_is_writable_not_retired():
    """It is a live word, so a row dated today must not be flagged as retired."""
    assert "DIRECTIVE" in a2a.WRITABLE_KINDS
    assert "DIRECTIVE" not in a2a.RETIRED_KINDS


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


# --- gc-mail stub: RETIRED 2026-09-05 -------------------------------------
#
# Fourteen tests lived here pinning `.claude/hooks/scripts/gc-mail-stub.sh` —
# a PreToolUse hook that refused any `gc` invocation and named docs/a2a/ as the
# replacement channel. The stub was deregistered and deleted on 2026-09-05 with
# Steve's word (9791a83, st-voc5) because the `gc` binary it guarded is itself
# gone, and the tests were left behind pointing at the missing file: 14 red on
# a green tree, which is how a suite stops being read. They are removed rather
# than rewritten because there is no longer a mechanism to test — nothing in
# .claude/settings.json blocks `gc`, and nothing needs to. The channel rule
# survives in prose, not in a hook: docs/a2a/inbox.md is the only channel.
# [st-5wk8 session, follows st-voc5]


# --- peer-ledger receipt backstop [st-1eaw] -------------------------------
#
# The 08-25 failure this pins: COO serviced two Strader memos within a day and
# logged both SERVICED rows in COO's OWN ledger. This tool read only Strader's
# file, printed [ALERT] OPEN for 12 and 9 sessions against finished work, and a
# nudge went out on the false read. The backstop must close such a memo — and
# must never let a peer's file break this repo's parse or its suite.


def _peers(tmp_path, rows: str, name: str = "COO") -> dict:
    p = tmp_path / f"{name}-inbox.md"
    p.write_text(_ledger(rows), encoding="utf-8")
    return {name: p}


def test_peer_ledger_receipt_closes_a_memo_this_ledger_never_got(tmp_path):
    mine = tmp_path / "inbox.md"
    mine.write_text(
        _ledger("| 2026-08-12 07:17 CT | Strader | MEMO | st-nujt | 2026-08-12-strader-to-coo-x | - | asks |\n"),
        encoding="utf-8",
    )
    events, _ = a2a.parse_inbox(mine)
    assert len(a2a.open_memos(events)) == 1, "no backstop: the memo reads as open"

    extra = a2a.peer_receipts(_peers(
        tmp_path,
        "| 2026-08-13 08:11 CT | COO | SERVICED | co-d1o7k | 2026-08-12-strader-to-coo-x | - | landed |\n",
    ))
    assert a2a.open_memos(events, extra) == []


def test_peer_receipt_dated_before_the_memo_does_not_close_it(tmp_path):
    """Ordering still binds across ledgers — an older row is not an answer."""
    mine = tmp_path / "inbox.md"
    mine.write_text(
        _ledger("| 2026-08-12 07:17 CT | Strader | MEMO | st-nujt | 2026-08-12-strader-to-coo-x | - | asks |\n"),
        encoding="utf-8",
    )
    events, _ = a2a.parse_inbox(mine)
    extra = a2a.peer_receipts(_peers(
        tmp_path,
        "| 2026-08-01 08:11 CT | COO | SERVICED | co-d1o7k | 2026-08-12-strader-to-coo-x | - | stale |\n",
    ))
    assert len(a2a.open_memos(events, extra)) == 1


def test_peer_ledger_problems_are_not_this_ledgers_problems(tmp_path):
    """A typo in COO's file must not turn Strader's suite red."""
    peers = _peers(tmp_path, "| 2026-08-13 08:11 CT | COO | SERVICED | co-d | ref-a |\n")
    extra = a2a.peer_receipts(peers)
    assert extra == {}
    events, problems = a2a.parse_inbox(INBOX)
    assert problems == []


def test_missing_peer_repo_degrades_to_the_old_behaviour(tmp_path):
    assert a2a.peer_receipts({"COO": tmp_path / "nope" / "inbox.md"}) == {}


def test_earliest_peer_receipt_wins_across_peers(tmp_path):
    peers = {}
    peers.update(_peers(
        tmp_path,
        "| 2026-08-15 08:00 CT | COO | SERVICED | co-d | ref-a | - | late |\n", name="COO"))
    peers.update(_peers(
        tmp_path,
        "| 2026-08-13 08:00 CT | Desk | ACK | dk-1 | ref-a | - | early |\n", name="Desk"))
    when, who = a2a.peer_receipts(peers)["ref-a"]
    assert (when, who) == (datetime(2026, 8, 13, 8, 0), "Desk")


def test_no_peers_flag_turns_the_backstop_off():
    out = subprocess.run(
        ["python3", str(TOOL), "--open", "--no-peers"],
        capture_output=True, text=True, cwd=REPO, check=True).stdout
    assert "RECEIPTS AWAITED FROM PEERS" in out


def test_live_run_reads_the_peer_ledger_without_crashing():
    out = subprocess.run(
        ["python3", str(TOOL), "--open"],
        capture_output=True, text=True, cwd=REPO, check=True).stdout
    assert "RECEIPTS AWAITED FROM PEERS" in out
