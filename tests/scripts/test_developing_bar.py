"""The developing bar — the column for a bar the tape is still writing. [st-e91l]

The safety property under test is not "it renders" but "it stays out of the
record": a partial bar must never become history, never reach the engine, and
never survive the arrival of its own closed version.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from drill_bridge import BridgeState                     # noqa: E402
from live_footprint_feed import developing_payload       # noqa: E402
from market.entities.trade import Trade                  # noqa: E402
from market.orderflow.bars import build_bars             # noqa: E402

CT = ZoneInfo("America/Chicago")
BAR_N = 2000


def _trades(n: int, size: int = 10, start_price: float = 7800.0) -> list[Trade]:
    t0 = datetime(2026, 8, 5, 9, 30, tzinfo=CT)
    return [
        Trade(ts=t0 + timedelta(seconds=i), symbol="ESU6", instrument_id=1,
              price=start_price + 0.25 * (i % 5), size=size,
              side="B" if i % 3 else "A")
        for i in range(n)
    ]


def test_partial_slice_yields_one_developing_bar():
    pending = _trades(30)                      # 300 contracts against N=2000
    p = developing_payload(pending, BAR_N)
    assert p is not None
    assert p["v"] == 300 < BAR_N
    assert p["cells"], "a developing bar still carries its footprint cells"


def test_developing_bar_matches_the_closed_bar_it_becomes():
    """The whole reason for reusing build_bars: the column cannot change shape
    when the bar closes. Feed the SAME trades as a completed bar and the
    price/delta fields must agree field for field."""
    pending = _trades(200)                      # exactly 2000 contracts
    dev = developing_payload(pending, BAR_N)
    closed = list(build_bars(iter(pending), n=BAR_N))
    assert len(closed) == 1
    b = closed[0]
    assert (dev["o"], dev["h"], dev["l"], dev["c"]) == (b.open, b.high, b.low, b.close)
    assert dev["d"] == b.delta and dev["v"] == b.volume
    assert dev["poc"] == b.poc_price
    assert len(dev["cells"]) == len(b.cells)


def test_developing_carries_no_emissions_and_no_fill_steps():
    """Emissions would mean the engine ran on a partial bar — the one thing
    that would corrupt recognizer state. Steps are animation for a finished
    bar and pure waste once a second."""
    p = developing_payload(_trades(40), BAR_N)
    assert p["ev"] == []
    assert p["steps"] == []


def test_empty_pending_yields_nothing():
    assert developing_payload([], BAR_N) is None


def test_bridge_replaces_rather_than_accumulates(tmp_path):
    st = BridgeState(log_dir=tmp_path)
    st.add_bars([], developing={"v": 100, "d": -5})
    st.add_bars([], developing={"v": 400, "d": -22})
    out = st.bars_since(0)
    assert out["developing"] == {"v": 400, "d": -22}
    assert out["bars"] == [], "a developing bar must never enter the bar list"
    assert out["total"] == 0


def test_closed_bars_retire_the_developing_one(tmp_path):
    st = BridgeState(log_dir=tmp_path)
    st.add_bars([], developing={"v": 1900, "d": -40})
    assert st.bars_since(0)["developing"] is not None
    st.add_bars([{"t0": "x", "t1": "y", "v": 2000, "d": -41}])
    out = st.bars_since(0)
    assert out["developing"] is None, "the closed bar IS the developing one, finished"
    assert out["total"] == 1


def test_a_push_carrying_both_keeps_the_newer_developing(tmp_path):
    """A close and the next bar's first prints can land in one push; the new
    developing bar must survive the retirement of the old one."""
    st = BridgeState(log_dir=tmp_path)
    st.add_bars([], developing={"v": 1990, "d": -3})
    st.add_bars([{"v": 2000, "d": -4}], developing={"v": 12, "d": +1})
    out = st.bars_since(0)
    assert out["total"] == 1
    assert out["developing"] == {"v": 12, "d": +1}


def test_developing_must_be_an_object(tmp_path):
    st = BridgeState(log_dir=tmp_path)
    for bad in ([], "x", 3):
        try:
            st.add_bars([], developing=bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r} as a developing bar")


def test_bars_since_always_reports_the_field(tmp_path):
    """The page reads d.developing on every poll; the key must exist even when
    nothing is forming, so the live path never sees `undefined`."""
    st = BridgeState(log_dir=tmp_path)
    assert "developing" in st.bars_since(0)
    assert st.bars_since(0)["developing"] is None


def _none_side_trades(n: int, size: int = 1) -> list[Trade]:
    """Reopen-shaped prints: an aggressor side of "N" adds to none_vol and
    creates no footprint cell (market/orderflow/bars.py _BarAccumulator.add)."""
    t0 = datetime(2026, 8, 23, 17, 0, tzinfo=CT)
    return [
        Trade(ts=t0 + timedelta(seconds=i), symbol="ESU6", instrument_id=1,
              price=7680.0, size=size, side="N")
        for i in range(n)
    ]


def test_all_none_side_pending_slice_yields_no_developing_column():
    """[st-wnuk] 2026-08-23 17:00 CT: the first prints after the Sunday reopen
    carried no aggressor side, the developing bar had volume and zero cells,
    poc_price raised 'bar has no cells' and the feeder died — eleven times,
    until systemd gave up. A bar with nothing to draw is 'not yet', not a
    fault: the developing column must be absent, and nothing may raise."""
    pending = _none_side_trades(5)
    assert developing_payload(pending, BAR_N) is None


def test_developing_column_appears_once_a_sided_print_arrives():
    """The same slice with one sided print after the N run: the column exists
    and its footprint holds exactly that print, with the N volume counted."""
    pending = _none_side_trades(5) + _trades(1)[:1]
    pending[-1] = Trade(ts=pending[-2].ts + timedelta(seconds=1), symbol="ESU6",
                        instrument_id=1, price=7680.0, size=3, side="B")
    p = developing_payload(pending, BAR_N)
    assert p is not None
    assert p["cells"] and p["poc"] == 7680.0
    assert p["v"] == 8 and p["nv"] == 5
