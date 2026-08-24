"""Trapped-seller fuel scorer tests. [st-aq1n]

Synthetic-bar tests pin each component's arithmetic and the tracker's
emission cadence; the corpus test pins the worked example the concept was
written from (ES 2026-08-19, the 7738/39 lid — knowledge/trapped-seller-fuel.md)
and skips when the corpus day is not on this machine.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from market.entities.footprint import FootprintBar, FootprintCell
from market.orderflow.fuel import (
    FuelKnobs, FuelTracker, load_level_history,
    _absorbed, _lid_rejections, _thin_above, _underwater,
)

CT = timezone(timedelta(hours=-5))
T0 = datetime(2026, 8, 19, 9, 0, tzinfo=CT)


def bar(i: int, o: float, h: float, l: float, c: float, *,
        delta: int = 0, cells: list[tuple[float, int, int]] | None = None,
        minutes: float = 1.0) -> FootprintBar:
    """A synthetic bar i minutes after T0. cells = [(price, bid_vol, ask_vol)]."""
    cs = tuple(FootprintCell(price=p, bid_vol=bv, ask_vol=av)
               for p, bv, av in sorted(cells or []))
    vol = sum(cv.bid_vol + cv.ask_vol for cv in cs) or 100
    return FootprintBar(
        symbol="ES.c.0",
        start_ts=T0 + timedelta(minutes=i * minutes),
        end_ts=T0 + timedelta(minutes=(i + 1) * minutes),
        open=o, high=h, low=l, close=c,
        volume=vol, delta=delta, none_vol=0, cells=cs,
    )


# ---------------------------------------------------------------- components

def test_underwater_sums_hit_bid_in_band_long():
    bars = [
        bar(0, 7737, 7739, 7736, 7737,
            cells=[(7736.0, 100, 40), (7739.0, 582, 60), (7743.0, 999, 0)]),
        bar(1, 7737, 7738, 7735, 7736,
            cells=[(7735.0, 800, 20), (7740.0, 50, 30)]),
    ]
    # band for L=7739 long: [7736, 7740] -> bid_vol at 7736,7739,7735? 7735 out.
    assert _underwater(bars, 7739.0, "long", FuelKnobs()) == 100 + 582 + 50


def test_underwater_short_mirror_uses_ask_side():
    bars = [bar(0, 7741, 7743, 7740, 7742,
                cells=[(7740.0, 10, 300), (7742.0, 5, 200), (7735.0, 0, 999)])]
    # band for L=7739 short: [7738, 7742] -> ask at 7740 + 7742
    assert _underwater(bars, 7739.0, "short", FuelKnobs()) == 500


def test_lid_rejections_counts_failed_presses():
    k = FuelKnobs()
    bars = [
        bar(0, 7735, 7738.25, 7734, 7736),   # pressed within 2, closed under: rejection
        bar(1, 7736, 7740.25, 7735, 7737),   # spiked THROUGH, closed under: rejection
        bar(2, 7737, 7739.25, 7736, 7738),   # pressed, closed under: rejection
        bar(3, 7738, 7741.0, 7736, 7740),    # closed above L: no
        bar(4, 7735, 7736.0, 7733, 7734),    # never pressed the lid: no
    ]
    assert _lid_rejections(bars, 7739.0, "long", k) == 3


def test_absorbed_trailing_run_of_higher_lows():
    rows = [
        bar(0, 7736, 7737, 7733, 7734, delta=-200),      # breaks the ascent
        bar(1, 7733, 7735, 7726.5, 7734, delta=666),     # higher-low run starts
        bar(2, 7734, 7738, 7728.75, 7735, delta=391),
        bar(3, 7735, 7741, 7731.5, 7736, delta=125),
    ]
    n, d = _absorbed(rows, "long")
    assert n == 3
    assert d == 391 + 125          # low-maker row (666) excluded


def test_absorbed_absent_when_lows_descend():
    rows = [
        bar(0, 7740, 7741, 7735, 7738, delta=50),
        bar(1, 7738, 7739, 7730, 7736, delta=60),
        bar(2, 7736, 7738, 7725, 7735, delta=10),    # lower low
        bar(3, 7735, 7736, 7727, 7733, delta=70),
    ]
    n, _ = _absorbed(rows, "long")
    assert n == 0


def test_thin_above_finds_shelf_and_ratio():
    vols = {7738.0: 900, 7739.0: 1000, 7740.0: 800,     # seed zone; 7740 = shoulder
            7741.0: 100, 7742.0: 150, 7743.0: 120,      # thin stretch (7744-46 empty)
            7747.0: 700}                                # shelf: >= 0.5 x 1000
    ratio, shelf = _thin_above(vols, 7739.0, "long", FuelKnobs())
    assert shelf == 7747.0
    # gap buckets 7741..7746, empties included
    assert ratio == pytest.approx((100 + 150 + 120 + 0 + 0 + 0) / 6 / 1000, abs=0.01)


def test_thin_above_heavy_all_the_way_is_flagged():
    vols = {float(p): 1000 for p in range(7735, 7760)}
    assert _thin_above(vols, 7739.0, "long", FuelKnobs()) == (1.0, None)


def test_thin_above_none_without_profile():
    assert _thin_above({}, 7739.0, "long", FuelKnobs()) == (None, None)


def test_roll_groups_by_wall_time():
    from market.orderflow.fuel import _roll
    bars = [bar(i, 7700 + i, 7701 + i, 7699 + i, 7700.5 + i, delta=10) for i in range(7)]
    rows = _roll(bars, 300.0)          # 1-min bars -> 5-min groups
    assert 1 <= len(rows) <= 3
    assert sum(r.delta for r in rows) == 70
    assert rows[0].low == 7699.0
    assert rows[-1].close == 7706.5


# ---------------------------------------------------------------- tracker

def close_seq(prices: list[float], level_cells: bool = False):
    """Bars stepping through closes, flat shape around each close."""
    out = []
    for i, c in enumerate(prices):
        cells = [(round(c, 2), 50, 50)] if level_cells else []
        out.append(bar(i, c, c + 0.5, c - 0.5, c, cells=cells))
    return out


def test_tracker_emits_on_engage_and_refresh_cadence():
    k = FuelKnobs(refresh_bars=3)
    tr = FuelTracker([7739.0], knobs=k)
    events = [tr.on_bar(b) for b in close_seq(
        [7750, 7749,                    # outside engage_pts: silent
         7742, 7741, 7740, 7742,        # engaged at 7742 (3 pts): emit, then cadence
         7750, 7751,                    # disengaged
         7741])]                        # re-engaged: emit again
    got = [i for i, e in enumerate(events) if e]
    assert got[0] == 2                  # engagement start
    assert 5 in got                     # refresh after 3 engaged bars
    assert got[-1] == 8                 # re-engagement
    assert events[0] is None and events[7] is None


def test_tracker_read_side_is_mechanical():
    tr = FuelTracker([7739.0])
    below = tr.on_bar(bar(0, 7736, 7737, 7735, 7736))
    assert below and below["read"] == "long"
    tr2 = FuelTracker([7739.0])
    above = tr2.on_bar(bar(0, 7741, 7742, 7740, 7741.5))
    assert above and above["read"] == "short"


def test_absent_components_render_absent():
    tr = FuelTracker([7739.0])          # no history, no cells, one bar
    ev = tr.on_bar(bar(0, 7737, 7737.5, 7736.5, 7737))
    assert ev is not None
    assert "no level history" in ev["reason"]
    assert "no lid yet" in ev["reason"]
    assert "no aggression at the level yet" in ev["reason"]
    assert ev["history"] is None
    assert ev["type"] == "Fuel" and ev["context"] is True


def test_tracker_never_raises_into_the_feed():
    tr = FuelTracker([7739.0])
    assert tr.on_bar(object()) is None            # malformed bar -> None, no raise
    # and it still works afterwards
    assert tr.on_bar(bar(0, 7737, 7738, 7736, 7737)) is not None


def test_history_phrase_reaches_reason(tmp_path: Path):
    state = tmp_path / "2026-08-19.json"
    state.write_text(
        '{"levels": [{"price": 7739.0, "n_touches": 100, "n_defenses": 56,'
        ' "first_touch": "2026-08-19T03:00:00+00:00", "state": "reclaimed"}]}',
        encoding="utf-8")
    hist = load_level_history(date(2026, 8, 19), path=state)
    assert 7739.0 in hist
    tr = FuelTracker([7739.0], history=hist)
    ev = tr.on_bar(bar(0, 7737, 7738, 7736, 7737))
    assert ev and "touched 100x / defended 56x" in ev["reason"]
    assert ev["history"]["n_touches"] == 100


def test_load_level_history_missing_file_is_empty():
    assert load_level_history(date(1999, 1, 1)) == {}


# ---------------------------------------------------------------- worked example

_C = Path(__file__).resolve().parents[3] / "data/corpus/2026-08-19"
_HAVE_0819 = ((_C / "databento_glbx_es.jsonl.gz").exists()
              or (_C / "databento_glbx_es.jsonl").exists())


@pytest.mark.skipif(not _HAVE_0819, reason="2026-08-19 corpus not present")
def test_worked_example_es_2026_08_19_7739_lid():
    """The concept's worked example: the 08:30-09:30 CT stall under 7738/39.

    Pinned loosely (ranges, not exact counts) — the knowledge file's numbers
    came from 5-min rolled bridge bars; these are raw 2000-lot bars.
    """
    from market.orderflow.bars import build_bars
    from market.orderflow.replay import read_corpus_day

    day = date(2026, 8, 19)
    t_lo = datetime(2026, 8, 19, 8, 30, tzinfo=CT)
    # End inside the stall: at 09:30 the tape cleared 7741 and the mechanical
    # read (close above the level) correctly flips to the short mirror.
    t_hi = datetime(2026, 8, 19, 9, 25, tzinfo=CT)
    trades = (t for t in read_corpus_day(day) if t_lo <= t.ts <= t_hi)
    tr = FuelTracker([7739.0], knobs=FuelKnobs(refresh_bars=1))
    last = None
    for b in build_bars(trades, n=2000):
        ev = tr.on_bar(b)
        if ev is not None:
            last = ev
    assert last is not None, "price engaged 7739 during the stall"
    assert last["read"] == "long"
    # Five rejections at 7738-41 in 25 min on 5-min bars; raw bars see more
    # presses. At least the concept's count must be visible.
    assert last["lid_rejections"] >= 4
    # The -582 print at 7739.00 alone beats this floor.
    assert last["underwater_vol"] > 2000
    # 7742-46 traded about a quarter of 7739's volume.
    assert last["thin_ratio"] is not None and last["thin_ratio"] < 0.6


def test_history_loader_retries_until_rows_arrive():
    """The level-state artifact lands at 08:20 CT, after a pre-open boot: an
    empty history retries the loader on a 15-min bar-time cadence."""
    calls = []
    store = {}

    def loader():
        calls.append(1)
        return dict(store)

    tr = FuelTracker([7739.0], history_loader=loader,
                     knobs=FuelKnobs(refresh_bars=1))
    tr.on_bar(bar(0, 7737, 7738, 7736, 7737))          # engage: loader tried
    assert len(calls) == 1
    tr.on_bar(bar(1, 7737, 7738, 7736, 7737))          # inside 15 min: no retry
    assert len(calls) == 1
    store[7739.0] = {"n_touches": 7, "n_defenses": 3}
    ev = tr.on_bar(bar(20, 7737, 7738, 7736, 7737))    # past 15 min: retry, rows land
    assert len(calls) == 2
    assert ev and "touched 7x / defended 3x" in ev["reason"]
    tr.on_bar(bar(40, 7737, 7738, 7736, 7737))         # loaded: no more calls
    assert len(calls) == 2
