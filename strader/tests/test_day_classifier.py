"""Tests for the day-type classifier (strader/evaluate/day_classifier.py)."""

from __future__ import annotations

from strader.entities.playbook import PlaybookCatalog
from strader.evaluate import (
    ClassifierConfig,
    DayTypeClassifier,
    MarketPrimitives,
    PlaybookEvaluator,
    SubjectiveRead,
)


def test_objective_tags_from_primitives():
    clf = DayTypeClassifier()
    c = clf.classify(
        MarketPrimitives(
            realized_range=40, typical_range=20,  # ratio 2.0 -> vol-high
            iv_rank=70,                            # -> ivr-high
            gex_sign="neg",                        # -> gex-neg
            points_to_nearest_magnet=25,           # -> room-to-travel
            points_to_next_level=15,               # -> level-to-level-room
            gap_pct=0.8,                           # -> gap-up
            on_key_level=True,                     # -> at-key-level
            mancini_carmine_confluence=True,       # -> confluence
            news_scheduled=True,                   # -> news-scheduled
        )
    )
    expected = {
        "vol-high", "ivr-high", "gex-neg", "room-to-travel", "level-to-level-room",
        "gap-up", "at-key-level", "mancini-carmine-confluence", "news-scheduled",
    }
    assert expected <= c.tags
    assert all(c.provenance[t] == "objective" for t in expected)
    # opposite-pole tags must not co-fire
    assert "vol-low" not in c.tags
    assert "near-magnet" not in c.tags
    assert "gap-down" not in c.tags


def test_low_pole_tags():
    c = DayTypeClassifier().classify(
        MarketPrimitives(
            realized_range=10, typical_range=20,   # ratio 0.5 -> vol-low
            iv_rank=10,                             # -> ivr-low
            gex_sign="pos",                         # -> gex-pos
            points_to_nearest_magnet=1.0,           # -> near-magnet
            gap_pct=-0.9,                           # -> gap-down
        )
    )
    assert {"vol-low", "ivr-low", "gex-pos", "near-magnet", "gap-down"} <= c.tags
    assert "vol-high" not in c.tags
    assert "room-to-travel" not in c.tags


def test_threshold_boundary_is_inclusive():
    cfg = ClassifierConfig()
    clf = DayTypeClassifier(config=cfg)
    at = clf.classify(MarketPrimitives(realized_range=cfg.vol_high_ratio * 20, typical_range=20))
    assert "vol-high" in at.tags
    under = clf.classify(MarketPrimitives(realized_range=(cfg.vol_high_ratio - 0.01) * 20, typical_range=20))
    assert "vol-high" not in under.tags and "vol-low" not in under.tags


def test_config_override_moves_the_line():
    strict = ClassifierConfig(vol_high_ratio=3.0)
    c = DayTypeClassifier(config=strict).classify(
        MarketPrimitives(realized_range=40, typical_range=20)  # ratio 2.0 < 3.0
    )
    assert "vol-high" not in c.tags


def test_subjective_trend_and_news_adhoc():
    c = DayTypeClassifier().classify(
        MarketPrimitives(), SubjectiveRead(trend="up", news_adhoc=True)
    )
    assert c.provenance["trend-up"] == "subjective"
    assert c.provenance["news-adhoc"] == "subjective"


def test_objective_trend_baseline_and_subjective_override():
    clf = DayTypeClassifier()
    baseline = clf.classify(MarketPrimitives(trend_slope=0.6))
    assert baseline.provenance["trend-up"] == "objective-baseline"

    overridden = clf.classify(MarketPrimitives(trend_slope=0.6), SubjectiveRead(trend="range"))
    assert "range-chop" in overridden.tags
    assert "trend-up" not in overridden.tags
    assert overridden.provenance["range-chop"] == "subjective"


def test_news_adhoc_is_subjective_only():
    # no primitive can produce news-adhoc; without a subjective read it never fires
    c = DayTypeClassifier().classify(MarketPrimitives(news_scheduled=True))
    assert "news-adhoc" not in c.tags


def test_roundtrip_classify_then_rank():
    """The loop: primitives -> classify -> DayContext -> evaluator.rank."""
    cls = DayTypeClassifier().classify(
        MarketPrimitives(
            realized_range=40, typical_range=20,
            points_to_nearest_magnet=25, gex_sign="neg",
            mancini_carmine_confluence=True,
        ),
        SubjectiveRead(trend="up"),
    )
    ranked = PlaybookEvaluator(PlaybookCatalog()).rank(cls.context)
    assert ranked                      # a ranking was produced with no validation error
    assert ranked[0].playbook.code     # a top pick exists
    # sanity: the trending/confluence read favors Momentum Breakout
    assert ranked[0].playbook.code == "MB"
