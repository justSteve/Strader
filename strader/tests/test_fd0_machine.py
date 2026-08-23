"""Tests for strader/execution/fd0.py — state machine, ledger, journal, checklist.

Bead: Cut And Await (st-apzt). Pure-logic: no feed, no broker, no clock
dependence beyond injected timestamps.

The properties worth defending here are the *refusals* — that no path opens a
position, that a presumed cut cannot double-debit the budget, and that an
unknown key is rejected rather than swallowed.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from strader.execution.compose import Budget, CannotFund
from strader.execution.fd0 import (
    Fd0, State, IllegalTransition, checklist, journal_path_for,
)

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "market" / "fixtures"
SPX = 7440.25


def _chain() -> dict:
    return json.loads((FIXTURES / "schwab_chain_spx_0dte.json").read_text())


def _harness(tmp_path: Path | None = None, **kw) -> Fd0:
    return Fd0(journal_path=(tmp_path / "fd0.jsonl") if tmp_path else None, **kw)


def _quiet(h: Fd0):
    return h.compose(_chain(), SPX, recent_minute_ranges_spx=[0.4] * 15)


# ------------------------------------------------------------ happy path ---

def test_full_cycle_compose_fill_cut_confirm_reload():
    h = _harness()
    assert h.state is State.IDLE

    t = _quiet(h)
    assert h.state is State.COMPOSED
    assert t.contract.strike == 7415.0

    h.confirm_fill(1.60)
    assert h.state is State.OPEN

    assert h.observe(t.stop_trigger_spx - 0.01) is False       # not yet
    assert h.state is State.OPEN

    assert h.observe(t.stop_trigger_spx) is True               # trigger
    assert h.state is State.CUT_PRESUMED

    h.confirm_exit(1.28)
    assert h.state is State.WAITING
    assert h.budget.attempts_left == 1

    _quiet(h)                                                  # reload is manual
    assert h.state is State.COMPOSED


def test_discarding_a_ticket_returns_to_idle_and_spends_nothing():
    h = _harness()
    _quiet(h)
    h.discard()
    assert h.state is State.IDLE
    assert h.budget.remaining_usd == 100.0
    assert h.budget.attempts_left == 2


def test_end_is_legal_from_any_state():
    for setup in (lambda h: None,
                  lambda h: _quiet(h),
                  lambda h: (_quiet(h), h.confirm_fill(1.60))):
        h = _harness()
        setup(h)
        h.end()
        assert h.state is State.DONE


# --------------------------------------------------------------- ledger ---

def test_confirmed_exit_corrects_the_tape_estimate_without_double_debiting():
    h = _harness()
    t = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t.stop_trigger_spx)

    estimated = h.budget.spent_usd
    assert estimated == pytest.approx(t.derivation.attempt_risk_usd)
    assert len(h.attempts) == 1

    h.confirm_exit(1.28)                       # actual loss = (1.60-1.28)*100 = $32
    assert len(h.attempts) == 1                # corrected, not appended
    assert h.budget.spent_usd == pytest.approx(32.0)
    assert h.attempts[0].estimated is False


def test_a_better_than_estimated_exit_gives_the_budget_back():
    h = _harness()
    t = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t.stop_trigger_spx)
    h.confirm_exit(1.45)                       # only $15 lost
    assert h.budget.spent_usd == pytest.approx(15.0)
    assert h.budget.remaining_usd == pytest.approx(85.0)


def test_an_attempt_closed_for_a_gain_costs_an_attempt_but_no_budget():
    h = _harness()
    t = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t.stop_trigger_spx)
    h.confirm_exit(2.10)                       # exited higher — a gain
    assert h.budget.spent_usd == 0.0
    assert h.budget.attempts_left == 1


def test_the_second_attempt_re_derives_a_wider_stop_from_what_is_left():
    h = _harness()
    t1 = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t1.stop_trigger_spx)
    h.confirm_exit(1.28)                       # $32 gone, 1 attempt left

    t2 = _quiet(h)
    # $68 on one attempt buys more room than $50 did.
    assert t2.derivation.stop_distance_spx > t1.derivation.stop_distance_spx


def test_a_stop_can_fill_worse_than_estimated_and_the_ledger_takes_it():
    # The stop is TOS-resident and market-on-trigger. A fast rally fills where
    # it fills, which can be well past the derived risk. The ledger must book
    # what actually happened, not what was budgeted.
    h = _harness()
    t = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t.stop_trigger_spx)
    assert h.budget.spent_usd == pytest.approx(t.derivation.attempt_risk_usd)  # $32 est
    h.confirm_exit(1.05)                       # actually lost $55
    assert h.budget.spent_usd == pytest.approx(55.0)
    assert h.budget.remaining_usd == pytest.approx(45.0)


def test_budget_exhaustion_refuses_the_next_compose_with_arithmetic():
    h = _harness(budget_total_usd=40.0)
    t = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t.stop_trigger_spx)
    h.confirm_exit(1.20)                       # $40 gone — the whole ceiling

    with pytest.raises(CannotFund) as exc:
        _quiet(h)
    assert "$0.00 remaining" in str(exc.value)  # the division is printed


def test_an_overrun_past_the_ceiling_is_shown_not_clamped():
    # Losing more than the ceiling is a fact about the session, and hiding it
    # behind a floor of zero would make the ledger lie about what happened.
    h = _harness(budget_total_usd=40.0)
    t = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t.stop_trigger_spx)
    h.confirm_exit(1.00)                       # $60 lost against a $40 ceiling
    assert h.budget.remaining_usd == pytest.approx(-20.0)
    with pytest.raises(CannotFund):
        _quiet(h)


# ------------------------------------------------------------- refusals ---

@pytest.mark.parametrize("action", [
    lambda h: h.confirm_fill(1.60),
    lambda h: h.discard(),
    lambda h: h.confirm_exit(1.20),
])
def test_keys_that_mean_nothing_in_idle_are_refused_not_swallowed(action):
    with pytest.raises(IllegalTransition):
        action(_harness())


def test_cannot_compose_while_a_position_is_open():
    h = _harness()
    _quiet(h)
    h.confirm_fill(1.60)
    with pytest.raises(IllegalTransition):
        _quiet(h)


def test_manual_cut_from_open_books_the_attempt_on_his_word(tmp_path):
    """2026-08-23: ``out`` is legal straight from OPEN. At the dictation pane
    nothing feeds the tape, so a presumption may never come; Steve saying he
    is out is the ledger's truth either way, and it is journaled as manual."""
    h = _harness(tmp_path)
    _quiet(h)
    h.confirm_fill(1.60)
    a = h.confirm_exit(1.20)
    assert h.state is State.WAITING
    assert a.closed and a.estimated is False and a.exit_premium_pts == 1.20
    assert a.realized_usd == pytest.approx(40.0)
    assert len(h.attempts) == 1 and h.budget.attempts_left == 1
    events = [json.loads(l) for l in (tmp_path / "fd0.jsonl").read_text().splitlines()]
    exit_ev = [e for e in events if e["event"] == "confirm_exit"][0]
    assert exit_ev["manual_cut"] is True


def test_cannot_confirm_an_exit_with_nothing_open():
    h = _harness()
    with pytest.raises(IllegalTransition):
        h.confirm_exit(1.20)                       # IDLE
    _quiet(h)
    with pytest.raises(IllegalTransition):
        h.confirm_exit(1.20)                       # COMPOSED, never filled


def test_observe_is_inert_unless_a_position_is_open():
    h = _harness()
    assert h.observe(99999.0) is False         # IDLE
    _quiet(h)
    assert h.observe(99999.0) is False         # COMPOSED — not filled yet
    assert h.state is State.COMPOSED


def test_nothing_in_the_machine_re_enters_by_itself():
    # Cut and WAIT is the whole generation. After a presumed cut and a
    # confirmed exit, no amount of tape moves the machine back to OPEN.
    h = _harness()
    t = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t.stop_trigger_spx)
    h.confirm_exit(1.28)
    for spx in (7300.0, 7440.0, 7500.0, 7200.0):
        h.observe(spx)
    assert h.state is State.WAITING


# -------------------------------------------------------------- journal ---

def test_journal_records_the_whole_cycle_with_the_derivation(tmp_path):
    h = _harness(tmp_path)
    t = _quiet(h)
    h.confirm_fill(1.60)
    h.observe(t.stop_trigger_spx)
    h.confirm_exit(1.28)
    h.end()

    events = [json.loads(l) for l in (tmp_path / "fd0.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == [
        "compose", "confirm_fill", "presume_cut", "confirm_exit", "end",
    ]
    assert "derivation" in events[0]["ticket"]
    assert events[3]["realized_usd"] == pytest.approx(32.0)


def test_a_refusal_is_journalled(tmp_path):
    h = _harness(tmp_path, budget_total_usd=1.0)
    with pytest.raises(CannotFund):
        _quiet(h)
    events = [json.loads(l) for l in (tmp_path / "fd0.jsonl").read_text().splitlines()]
    assert events[0]["event"] == "refuse"
    assert events[0]["reason"] == "CannotFund"


def test_a_noise_floor_warning_is_journalled(tmp_path):
    h = _harness(tmp_path)
    h.compose(_chain(), SPX, recent_minute_ranges_spx=[3.0] * 15)
    events = [json.loads(l) for l in (tmp_path / "fd0.jsonl").read_text().splitlines()]
    assert any(e["event"] == "warn" and "NOISE FLOOR" in e["message"] for e in events)


def test_an_unwritable_journal_is_loud_but_does_not_take_the_surface_down(tmp_path, caplog):
    h = Fd0(journal_path=tmp_path / "nope" / "fd0.jsonl")
    (tmp_path / "nope").write_text("I am a file, not a directory")
    with caplog.at_level("ERROR"):
        t = _quiet(h)
    assert t is not None                       # the surface kept working
    assert "JOURNAL WRITE FAILED" in caplog.text


def test_journal_path_is_per_day():
    p = journal_path_for(date(2026, 8, 3), Path("data/exec"))
    assert p.name == "fd0-2026-08-03.jsonl"


# ------------------------------------------------------------ checklist ---

def _ticks(n=3, moving=True):
    return [(datetime(2026, 8, 3, 8, 15, s), 7440.0 + (s if moving else 0))
            for s in range(n)]


def _lines(**kw):
    base = dict(token_status="ok", spx_ticks=_ticks(), chain_ok=True,
                chain_detail="0.30d put at 7415, $15 spread", tos_validated=True,
                budget=Budget(), journal_path=Path("data/exec/fd0-test.jsonl"),
                build_complete=True)
    return checklist(**{**base, **kw})


def test_a_clean_checklist_passes_every_line(tmp_path):
    lines = _lines(journal_path=tmp_path / "fd0.jsonl")
    assert all(l.passed for l in lines)
    assert len(lines) == 7


def test_a_stale_token_fails():
    assert not [l for l in _lines(token_status="warn") if l.name == "Schwab token"][0].passed


def test_a_frozen_quote_stream_fails_even_with_three_ticks():
    line = [l for l in _lines(spx_ticks=_ticks(moving=False))
            if l.name == "SPX quote stream"][0]
    assert not line.passed


def test_too_few_ticks_fails():
    assert not [l for l in _lines(spx_ticks=_ticks(2))
                if l.name == "SPX quote stream"][0].passed


def test_an_unarmed_ledger_fails():
    line = [l for l in _lines(budget=Budget(spent_usd=32.0, attempts_used=1))
            if l.name == "Budget ledger armed"][0]
    assert not line.passed


def test_an_unanswered_tos_card_fails():
    assert not [l for l in _lines(tos_validated=False)
                if l.name == "TOS order construct"][0].passed


def test_an_incomplete_build_is_a_checklist_line_not_a_footnote():
    # The design: "If any of 1-4 slips past Sunday, that is a NO-GO input,
    # stated plainly in Monday's checklist."
    line = [l for l in _lines(build_complete=False) if l.name == "Build plan complete"][0]
    assert not line.passed
    assert "NO-GO" in line.detail


def test_lines_render_with_a_verdict():
    assert _lines()[0].render().startswith("  [PASS]  Schwab token")
