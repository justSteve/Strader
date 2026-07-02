"""Tests for the playbook fit evaluator (strader/evaluate/playbook_evaluator.py)."""

from __future__ import annotations

import pytest

from strader.entities.playbook import PlaybookCatalog, PlaybookError
from strader.evaluate import DayContext, PlaybookEvaluator


@pytest.fixture(scope="module")
def evaluator() -> PlaybookEvaluator:
    return PlaybookEvaluator(PlaybookCatalog())


def _score_for(ranked, code):
    return next(s for s in ranked if s.playbook.code == code)


def test_rank_scores_all_worthy_and_is_deterministic(evaluator):
    ranked = evaluator.rank(DayContext.of("trend-up", "vol-high", "room-to-travel"))
    assert len(ranked) == len(evaluator.catalog.worthy())
    # sorted by score descending, then code ascending
    keys = [(-s.score, s.playbook.code) for s in ranked]
    assert keys == sorted(keys)


def test_matched_tags_and_arithmetic(evaluator):
    # MB favors trend-up (+1) and avoids range-chop (-1) → net 0.
    mb = _score_for(evaluator.rank(DayContext.of("trend-up", "range-chop")), "MB")
    assert "trend-up" in mb.matched_favored
    assert "range-chop" in mb.matched_avoid
    assert mb.score == 0.0


def test_weighted_confluence_outranks_plain_tag(evaluator):
    # trend-up is weight 1.0; mancini-carmine-confluence is weight 2.0. MB favors both.
    mb_plain = _score_for(evaluator.rank(DayContext.of("trend-up")), "MB")
    mb_conf = _score_for(evaluator.rank(DayContext.of("mancini-carmine-confluence")), "MB")
    assert mb_plain.score == 1.0
    assert mb_conf.score == 2.0


def test_regime_picks_the_right_playbook(evaluator):
    # A rich-IV, ranging, pinning tape should surface the premium-harvest play.
    top = evaluator.surface(DayContext.of("ivr-high", "range-chop", "gex-pos", "near-magnet"))
    assert top is not None
    assert top.playbook.code == "OPH"


def test_unknown_context_tag_rejected(evaluator):
    with pytest.raises(PlaybookError):
        evaluator.rank(DayContext.of("not-a-real-tag"))


def test_instrument_emits_indicators_and_checklists(evaluator):
    top = evaluator.surface(DayContext.of("trend-up", "vol-high", "gex-neg", "room-to-travel"))
    kit = evaluator.instrument(top)
    assert kit["indicators"]
    assert kit["entry_checklist"] and all(isinstance(i, str) for i in kit["entry_checklist"])
    assert kit["management_checklist"]
    # checkbox markers are stripped from the emitted items
    assert not kit["entry_checklist"][0].startswith("[")
