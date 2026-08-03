"""Tests for strader/execution/feed.py — the FD0 feed adapter and preflight.

Bead: Cut And Await (st-apzt). Nothing here touches the network: the live path
is exercised through injected fakes, and the fixture path through real files.

The property worth defending is that a *broken feed produces FAIL lines rather
than an exception*. A preflight that crashes tells you nothing; a preflight that
prints six FAILs tells you exactly what is wrong on a morning when you have
fifteen minutes.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from strader.execution.compose import Budget
from strader.execution.feed import (
    FeedError, FixtureFeed, Quote, SPX_SYMBOL, preflight, spx_price_diagnostic,
)

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "market" / "fixtures"
CHAIN = FIXTURES / "schwab_chain_spx_0dte.json"


def _q(last=7440.25, bid=7440.20, ask=7440.30, mark=7440.25) -> Quote:
    return Quote(symbol=SPX_SYMBOL, last=last, bid=bid, ask=ask, mark=mark,
                 at=datetime(2026, 8, 3, 8, 45))


class _DeadFeed:
    def spx(self): raise FeedError("connection refused")
    def put_chain(self, *, dte=0): raise FeedError("connection refused")


# ---------------------------------------------------------------- quotes ---

def test_quote_derives_midpoint_and_spread():
    q = _q(bid=7440.0, ask=7441.0)
    assert q.midpoint == pytest.approx(7440.5)
    assert q.spread == pytest.approx(1.0)


def test_quote_tolerates_missing_sides():
    q = Quote(SPX_SYMBOL, last=7440.0, bid=None, ask=None, mark=None,
              at=datetime(2026, 8, 3, 8, 45))
    assert q.midpoint is None and q.spread is None


# ------------------------------------------------------- mark diagnostic ---

def test_a_sane_index_quote_reads_as_sane():
    d = spx_price_diagnostic(_q())
    assert "sane" in d["verdict"]
    assert d["mark_tracks_last"] is True


def test_the_premarket_shape_is_called_out_as_synthetic():
    # The literal numbers off the 08-03 TOS confirm dialog.
    d = spx_price_diagnostic(_q(last=7489.72, bid=7440.83, ask=7519.05, mark=None))
    assert "synthetic" in d["verdict"]
    assert d["spread"] == pytest.approx(78.22)
    assert d["midpoint_minus_last"] == pytest.approx(-9.78)


def test_a_mark_that_drifts_from_last_is_flagged():
    d = spx_price_diagnostic(_q(last=7489.72, bid=7440.83, ask=7519.05, mark=7479.94))
    assert d["mark_tracks_last"] is False
    assert d["mark_minus_last"] == pytest.approx(-9.78)


def test_diagnostic_without_a_last_price_declines_to_judge():
    d = spx_price_diagnostic(Quote(SPX_SYMBOL, None, 1.0, 2.0, None,
                                   datetime(2026, 8, 3, 8, 45)))
    assert "cannot judge" in d["verdict"]


# --------------------------------------------------------- fixture feed ---

def test_fixture_feed_walks_the_tape_then_holds_the_last_tick():
    f = FixtureFeed(CHAIN, [7440.0, 7441.0])
    assert [f.spx().last for _ in range(4)] == [7440.0, 7441.0, 7441.0, 7441.0]


def test_fixture_feed_reads_the_chain():
    assert FixtureFeed(CHAIN, [7440.0]).put_chain()["putExpDateMap"]


def test_fixture_feed_with_no_ticks_is_an_error_not_a_crash():
    with pytest.raises(FeedError):
        FixtureFeed(CHAIN, []).spx()


def test_a_missing_fixture_chain_raises_feed_error():
    with pytest.raises(FeedError):
        FixtureFeed(Path("/nonexistent/chain.json"), [7440.0]).put_chain()


# ------------------------------------------------------------- preflight ---

def _run(feed, tmp_path, **kw):
    return preflight(feed, token_path=tmp_path / "no_token.json",
                     budget=Budget(), journal_path=tmp_path / "fd0.jsonl", **kw)


def test_a_dead_feed_produces_fail_lines_not_an_exception(tmp_path):
    lines, diag = _run(_DeadFeed(), tmp_path)
    assert not all(l.passed for l in lines)
    assert "connection refused" in diag["spx_error"]
    quote_line = [l for l in lines if l.name == "SPX quote stream"][0]
    assert not quote_line.passed


def test_human_facts_default_to_false(tmp_path):
    # An unverified morning must not render a clean checklist.
    lines, _ = _run(FixtureFeed(CHAIN, [7440.0, 7440.5, 7441.0]), tmp_path)
    by = {l.name: l for l in lines}
    assert not by["TOS order construct"].passed
    assert not by["Build plan complete"].passed


def test_a_working_fixture_feed_passes_the_machine_checkable_lines(tmp_path):
    lines, diag = _run(FixtureFeed(CHAIN, [7440.0, 7440.5, 7441.0]), tmp_path)
    by = {l.name: l for l in lines}
    assert by["SPX quote stream"].passed
    assert by["Chain / delta band"].passed
    assert by["Journal writable"].passed
    assert by["Budget ledger armed"].passed
    assert diag["pick"]["strike"] == 7415.0


def test_a_frozen_tape_fails_the_quote_line(tmp_path):
    # Three identical prints is a stalled feed, not a live one.
    lines, _ = _run(FixtureFeed(CHAIN, [7440.0]), tmp_path)
    assert not [l for l in lines if l.name == "SPX quote stream"][0].passed


def test_a_chain_with_no_band_strike_fails_with_the_reason(tmp_path):
    lines, _ = _run(FixtureFeed(FIXTURES / "schwab_chain_spx.json",
                                [7440.0, 7440.5, 7441.0]), tmp_path)
    line = [l for l in lines if l.name == "Chain / delta band"][0]
    assert not line.passed
    assert "0.38" in line.detail          # names what it found instead


def test_a_missing_token_fails_rather_than_being_assumed_ok(tmp_path):
    lines, _ = _run(FixtureFeed(CHAIN, [7440.0, 7440.5, 7441.0]), tmp_path)
    assert not [l for l in lines if l.name == "Schwab token"][0].passed


def test_preflight_records_a_diagnostic_per_sample(tmp_path):
    _, diag = _run(FixtureFeed(CHAIN, [7440.0, 7440.5, 7441.0]), tmp_path, samples=3)
    assert len(diag["spx_samples"]) == 3
    assert json.dumps(diag)               # serializable for the journal


def test_a_cash_index_with_no_book_is_named_as_such_not_treated_as_a_gap():
    # Observed live 2026-08-03: Schwab's $SPX quote carries lastPrice and
    # closePrice and no bid/ask/mark at all. A cash index has no book, so a
    # midpoint-derived quantity is fabricated rather than merely missing.
    d = spx_price_diagnostic(
        Quote(SPX_SYMBOL, last=7489.72, bid=None, ask=None, mark=None,
              at=datetime(2026, 8, 3, 7, 28))
    )
    assert "no bid/ask on the cash index" in d["verdict"]
    assert "use last" in d["verdict"]
    assert d["midpoint"] is None and d["spread"] is None
    assert "mark_tracks_last" not in d       # nothing to compare, so no verdict
