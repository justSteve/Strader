"""Tests for the singleton entity (0DTE long single as futures proxy)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from market.entities.instrument import Contract
from market.entities.level import Level
from strader2.entities.singleton import SingletonPosition, SingletonSetup


def _contract(right: str, delta: float) -> Contract:
    return Contract(
        symbol=f"SPXW260701{right[0]}05500000",
        underlying="SPX",
        strike=5500.0,
        expiry=date(2026, 7, 1),
        contract_type=right,
        bid=9.8, ask=10.2, last=10.0,
        volume=100, open_interest=500,
        delta=delta, gamma=0.01, theta=-0.5, vega=0.2,
        implied_volatility=0.15,
    )


def _level(price: float = 5500.0) -> Level:
    return Level(price=price, label="support", source="mancini", annotation="major")


def _setup(bias: str = "bullish", confluence: bool = False) -> SingletonSetup:
    return SingletonSetup(bias=bias, trigger="failed_breakdown", anchor=_level(), mancini_confluence=confluence)


def _pos(bias="bullish", *, delta=None, entry=10.0, current=12.0, qty=2,
         u_entry=5500.0, u_now=5505.0, target=5512.0, stop=5495.0) -> SingletonPosition:
    right = "CALL" if bias == "bullish" else "PUT"
    if delta is None:
        delta = 0.55 if bias == "bullish" else -0.55
    return SingletonPosition(
        contract=_contract(right, delta),
        setup=_setup(bias),
        entry_price=entry, quantity=qty, entry_time=datetime(2026, 7, 1, 9, 40, tzinfo=timezone.utc),
        underlying_at_entry=u_entry, underlying_now=u_now, target=target, stop=stop, current_value=current,
    )


# ── setup ────────────────────────────────────────────────────────────────────

def test_right_mapping():
    assert _setup("bullish").right == "CALL"
    assert _setup("bearish").right == "PUT"


def test_confluence_flag():
    assert _setup(confluence=True).mancini_confluence is True
    assert _setup().mancini_confluence is False


# ── construction guards ──────────────────────────────────────────────────────

def test_rejects_mismatched_contract():
    with pytest.raises(ValueError, match="needs a CALL leg"):
        SingletonPosition(
            contract=_contract("PUT", -0.5), setup=_setup("bullish"),
            entry_price=10, quantity=1, entry_time=datetime(2026, 7, 1, tzinfo=timezone.utc),
            underlying_at_entry=5500, underlying_now=5500, target=5510, stop=5495, current_value=10,
        )


def test_rejects_nonpositive_quantity():
    with pytest.raises(ValueError, match="quantity must be positive"):
        _pos(qty=0)


# ── futures-proxy lenses ─────────────────────────────────────────────────────

def test_net_delta_sign():
    assert _pos("bullish").net_delta == pytest.approx(1.1)    # long call, +delta
    assert _pos("bearish").net_delta == pytest.approx(-1.1)   # long put, -delta


def test_delta_exposure_is_absolute():
    assert _pos("bearish").delta_exposure == pytest.approx(0.55 * 100 * 2)


def test_unrealized_pnl_and_risk():
    p = _pos(entry=10.0, current=12.0, qty=2)
    assert p.unrealized_pnl == pytest.approx(400.0)   # (12-10)*2*100
    assert p.max_loss == pytest.approx(2000.0)        # 10*2*100 (defined risk)
    assert p.r_multiple == pytest.approx(0.2)         # 400/2000


# ── distance to exits, signed by direction ───────────────────────────────────

def test_bullish_target_and_stop():
    p = _pos("bullish", u_now=5505.0, target=5512.0, stop=5495.0)
    assert p.pts_to_target == pytest.approx(7.0)
    assert p.pts_to_stop == pytest.approx(10.0)
    assert not p.at_target and not p.at_stop
    assert _pos("bullish", u_now=5513.0, target=5512.0).at_target
    assert _pos("bullish", u_now=5494.0, stop=5495.0).at_stop


def test_bearish_target_and_stop():
    # bearish: target below spot, stop above
    p = _pos("bearish", u_now=5495.0, target=5488.0, stop=5505.0)
    assert p.pts_to_target == pytest.approx(7.0)
    assert p.pts_to_stop == pytest.approx(10.0)
    assert not p.at_target and not p.at_stop
    assert _pos("bearish", u_now=5487.0, target=5488.0).at_target
    assert _pos("bearish", u_now=5506.0, stop=5505.0).at_stop
