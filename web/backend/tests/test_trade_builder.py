"""Tests for trade builder service."""

from datetime import date
from app.services.trade_builder import build_butterfly, build_vertical, evaluate_trade


def test_butterfly_construction():
    setup = build_butterfly(
        center_strike=5850,
        width=5,
        expiration=date.today(),
        option_type="CALL",
    )
    assert setup.strategy == "butterfly"
    assert len(setup.legs) == 3
    assert setup.legs[0].strike == 5845
    assert setup.legs[1].strike == 5850
    assert setup.legs[2].strike == 5855
    assert setup.legs[0].action == "BUY"
    assert setup.legs[1].action == "SELL"
    assert setup.legs[1].quantity == 2
    assert setup.legs[2].action == "BUY"


def test_vertical_construction():
    setup = build_vertical(
        long_strike=5850,
        short_strike=5860,
        expiration=date.today(),
        option_type="CALL",
    )
    assert setup.strategy == "vertical"
    assert len(setup.legs) == 2
    assert setup.legs[0].action == "BUY"
    assert setup.legs[1].action == "SELL"


def test_risk_graph_generation():
    setup = build_butterfly(
        center_strike=5850,
        width=5,
        expiration=date.today(),
        prices={5845: 10.0, 5850: 7.0, 5855: 5.0},
    )
    eval_ = evaluate_trade(setup, underlying_price=5850)
    assert len(eval_.risk_graph) > 0
    assert eval_.max_profit > 0
    assert eval_.max_loss < 0
    assert eval_.risk_reward_ratio > 0
