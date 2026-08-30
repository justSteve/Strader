"""The journal, and the day it reconstructs. [st-eznu]

Two claims are tested here that the rest of the service depends on:

``day_state`` is **derived**, so a restart recovers the ceiling rather than
resetting it — a bug that would hand Steve a fresh $100 of loss and two fresh
attempts every time the box came back, which on this box is not hypothetical.

And **losses only debit**: a winner does not buy back an attempt or raise the
ceiling. That is FD0's ``Budget`` semantics, and it is the difference between a
ceiling on the day's damage and a running P&L.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from execd.journal import Journal

from .conftest import CALL, CT, Clock


@pytest.fixture
def journal(tmp_path, clock: Clock) -> Journal:
    return Journal(tmp_path / "journal", sha="abc1234", clock=clock)


def fill(journal, price=2.10, qty=1, intent_id="t-1", symbol=CALL):
    return journal.record("filled", kind="entry", symbol=symbol, qty=qty,
                          price=price, intent_id=intent_id)


def close(journal, pnl, intent_id="t-1", symbol=CALL):
    return journal.record("closed", symbol=symbol, qty=1, pnl_usd=pnl,
                          intent_id=intent_id)


class TestWriting:
    def test_every_line_carries_a_timestamp_and_the_installed_sha(self, journal):
        line = journal.record("unlock", state="ARMED")
        assert line["sha"] == "abc1234"
        assert line["event"] == "unlock"
        assert line["ts_ct"].startswith("2026-08-26")

    def test_lines_are_appended_not_replaced(self, journal):
        for i in range(5):
            journal.record("request", intent_id=f"t-{i}")
        assert len(journal.read()) == 5

    def test_the_file_is_named_by_the_central_date(self, journal, clock):
        # 01:00 UTC on the 27th is still the 26th in Chicago; a journal named
        # by UTC would split a trading day across two files.
        clock.set(datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc))
        journal.record("request")
        assert journal.path_for().name == "2026-08-26.jsonl"

    def test_a_new_central_day_opens_a_new_file(self, journal, clock):
        journal.record("request", intent_id="day-1")
        clock.set(datetime(2026, 8, 27, 10, 0, tzinfo=CT))
        journal.record("request", intent_id="day-2")
        assert journal.days() == [date(2026, 8, 26), date(2026, 8, 27)]
        assert len(journal.read(date(2026, 8, 26))) == 1

    def test_each_line_is_valid_json_on_its_own(self, journal):
        journal.record("filled", symbol=CALL, price=2.10)
        raw = journal.path_for().read_text().strip().splitlines()
        assert json.loads(raw[0])["symbol"] == CALL

    def test_values_that_are_not_json_are_made_plain_rather_than_dropped(self, journal):
        from execd.intent import Side

        line = journal.record("placed", side=Side.BUY_TO_OPEN, when=journal.clock(),
                              nested={"a": [1, 2]}, path=journal.dir)
        assert line["side"] == "BUY_TO_OPEN"
        assert line["nested"] == {"a": [1, 2]}
        assert isinstance(line["path"], str)
        json.dumps(line)   # the assertion: it survives serialisation


class TestReading:
    def test_find_returns_every_line_an_intent_produced(self, journal):
        journal.record("request", intent_id="t-1")
        journal.record("placed", intent_id="t-1", order={"order_id": "x"})
        journal.record("request", intent_id="t-2")
        assert [e["event"] for e in journal.find("t-1")] == ["request", "placed"]

    def test_find_on_an_unknown_id_is_empty_not_an_error(self, journal):
        assert journal.find("never-seen") == []

    def test_tail_returns_the_last_n(self, journal):
        for i in range(10):
            journal.record("request", intent_id=f"t-{i}")
        assert [e["intent_id"] for e in journal.tail(3)] == ["t-7", "t-8", "t-9"]

    def test_events_filters_by_name(self, journal):
        journal.record("request", intent_id="t-1")
        journal.record("refused", intent_id="t-1")
        journal.record("placed", intent_id="t-2")
        assert len(journal.events("refused", "placed")) == 2

    def test_reading_an_untouched_day_is_empty_not_an_error(self, journal):
        assert journal.read(date(2020, 1, 1)) == []

    def test_a_truncated_last_line_does_not_take_the_day_with_it(self, journal):
        journal.record("filled", kind="entry", symbol=CALL, qty=1, price=2.10)
        with journal.path_for().open("a") as fh:
            fh.write('{"event": "placed", "trunc')     # what a kill mid-write leaves
        entries = journal.read()
        assert entries[0]["event"] == "filled"
        assert entries[1]["event"] == "unreadable" and entries[1]["line_no"] == 2
        # and the day still reconstructs
        assert journal.day_state().attempts_used == 1


class TestDayState:
    def test_a_quiet_day_is_all_zeroes(self, journal):
        assert journal.day_state() == journal.day_state()
        s = journal.day_state()
        assert (s.open_positions, s.realized_loss_usd, s.attempts_used) == (0, 0.0, 0)

    def test_an_entry_counts_as_an_attempt_and_an_open_position(self, journal):
        fill(journal)
        s = journal.day_state()
        assert (s.open_positions, s.attempts_used) == (1, 1)

    def test_a_close_frees_the_position_but_not_the_attempt(self, journal):
        fill(journal)
        close(journal, pnl=-40.0)
        s = journal.day_state()
        assert (s.open_positions, s.attempts_used) == (0, 1)

    def test_a_loss_debits_the_ceiling(self, journal):
        fill(journal)
        close(journal, pnl=-40.0)
        assert journal.day_state().realized_loss_usd == 40.0

    def test_a_win_does_not_credit_it_back(self, journal):
        """Read the module docstring. This is the bound, not a P&L."""
        fill(journal, intent_id="t-1")
        close(journal, pnl=-60.0, intent_id="t-1")
        fill(journal, intent_id="t-2")
        close(journal, pnl=+500.0, intent_id="t-2")
        s = journal.day_state()
        assert s.realized_loss_usd == 60.0
        assert s.attempts_used == 2

    def test_losses_accumulate(self, journal):
        for i, pnl in enumerate((-30.0, -45.5)):
            fill(journal, intent_id=f"t-{i}")
            close(journal, pnl=pnl, intent_id=f"t-{i}")
        assert journal.day_state().realized_loss_usd == 75.5

    def test_a_close_with_no_matching_entry_never_drives_positions_negative(self, journal):
        close(journal, pnl=-10.0)
        assert journal.day_state().open_positions == 0

    def test_a_refusal_costs_neither_an_attempt_nor_the_ceiling(self, journal):
        journal.record("refused", intent_id="t-1", refused={"bound": "window"})
        s = journal.day_state()
        assert (s.attempts_used, s.realized_loss_usd) == (0, 0.0)

    def test_a_protective_stop_is_not_an_entry(self, journal):
        """The resting stop is placed as an order; counting it as an attempt
        would spend the day's budget on protecting the position."""
        fill(journal)
        journal.record("placed", kind="protective-stop", symbol=CALL)
        journal.record("stop_placed", symbol=CALL, stop_price=1.75)
        assert journal.day_state().attempts_used == 1

    def test_yesterdays_losses_do_not_bind_today(self, journal, clock):
        fill(journal)
        close(journal, pnl=-100.0)
        clock.set(datetime(2026, 8, 27, 10, 0, tzinfo=CT))
        s = journal.day_state()
        assert (s.realized_loss_usd, s.attempts_used) == (0.0, 0)

    def test_a_restart_recovers_the_ceiling_from_the_file(self, tmp_path, clock):
        first = Journal(tmp_path / "journal", sha="abc1234", clock=clock)
        fill(first)
        close(first, pnl=-80.0)
        # a second process over the same directory — what a restart looks like
        second = Journal(tmp_path / "journal", sha="abc1234", clock=clock)
        s = second.day_state()
        assert (s.realized_loss_usd, s.attempts_used) == (80.0, 1)
