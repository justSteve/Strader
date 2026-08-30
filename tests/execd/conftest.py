"""Fixtures for the execution service. [st-eznu]

Two things every test here needs and must not get from the machine it runs on:

**A clock it controls.** Half the bounds are about time — the session window,
quote staleness, arming expiry — and a suite that consults the wall clock is a
suite that passes in the morning and fails at four. ``clock`` is a callable
frozen at Wednesday 2026-08-26 10:00 CT, mid-session, and every object takes it
by injection.

**A state directory that is thrown away.** The journal is the service's memory;
sharing one between tests would make the daily ceiling depend on test order.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from execd.bounds import Bounds
from execd.broker import MockBroker
from execd.intent import OrderIntent, OrderType, Side
from execd.service import ExecService, ServiceConfig

CT = ZoneInfo("America/Chicago")

#: Wednesday, mid-session, well inside every window.
MIDSESSION = datetime(2026, 8, 26, 10, 0, tzinfo=CT).astimezone(timezone.utc)

#: An SPX weekly call, 21-character OCC form.
CALL = "SPXW  260826C06400000"
PUT = "SPXW  260826P06300000"
SPX_NOW = 6380.0


class Clock:
    """A clock a test can move. ``clock()`` is the reading; ``clock.set`` and
    ``clock.advance`` are the controls."""

    def __init__(self, at: datetime = MIDSESSION) -> None:
        self.now = at

    def __call__(self) -> datetime:
        return self.now

    def set(self, at: datetime) -> datetime:
        self.now = at.astimezone(timezone.utc) if at.tzinfo else at.replace(tzinfo=timezone.utc)
        return self.now

    def set_ct(self, hour: int, minute: int = 0, *, day: int = 26, month: int = 8,
               year: int = 2026) -> datetime:
        return self.set(datetime(year, month, day, hour, minute, tzinfo=CT))

    def advance(self, seconds: float = 0, minutes: float = 0) -> datetime:
        self.now = self.now + timedelta(seconds=seconds, minutes=minutes)
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def bounds() -> Bounds:
    return Bounds()


@pytest.fixture
def broker(clock: Clock) -> MockBroker:
    b = MockBroker(clock=clock)
    b.set_quote(CALL, bid=2.00, ask=2.10)
    b.set_quote(PUT, bid=1.80, ask=1.90)
    b.set_quote("$SPX", bid=SPX_NOW - 0.25, ask=SPX_NOW + 0.25, last=SPX_NOW)
    b.set_chain("SPXW", {"root": "SPXW", "calls": {}, "puts": {}})
    return b


@pytest.fixture
def service(broker: MockBroker, clock: Clock, tmp_path, bounds: Bounds) -> ExecService:
    config = ServiceConfig(state_dir=tmp_path / "execd", bounds=bounds, sha="testsha")
    return ExecService(broker, config, clock=clock)


@pytest.fixture
def armed(service: ExecService) -> ExecService:
    service.unlock({"token": "not-a-real-credential"})
    return service


def entry(intent_id: str = "t-001", symbol: str = CALL, qty: int = 1,
          limit: float = 2.10, stop_spx: float | None = SPX_NOW - 12.0,
          delta: float | None = 0.30, **kw) -> OrderIntent:
    """A well-formed opening intent. A call, so its stop sits below spot."""
    return OrderIntent(
        intent_id=intent_id, symbol=symbol, side=Side.BUY_TO_OPEN, qty=qty,
        order_type=OrderType.LIMIT, limit=limit, stop_spx=stop_spx, delta=delta,
        source="test", **kw,
    )


def exit_intent(intent_id: str = "t-001-x", symbol: str = CALL, qty: int = 1,
                **kw) -> OrderIntent:
    return OrderIntent(
        intent_id=intent_id, symbol=symbol, side=Side.SELL_TO_CLOSE, qty=qty,
        order_type=OrderType.MARKET, source="test", **kw,
    )
