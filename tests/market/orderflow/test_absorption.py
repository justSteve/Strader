"""AbsorptionTracker unit tests (st-9vl) — synthetic MBP-1 streams.

Each test builds a small deterministic book-event sequence around the
production floors (ABSORPTION_VOL_MIN=300, ABSORPTION_REFILL_MIN=2,
REFILL_DEPLETION_MIN=REFILL_RECOVERY_MIN=25). The canonical "defended bid"
story: sellers hit the bid at P, resting size depletes and refills twice,
then price lifts away — one AbsorptionRead, positive displacement.
"""
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market.entities.book import BookEvent
from market.orderflow.absorption import AbsorptionTracker
from market.signals.orderflow import AbsorptionRead

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 7, 2, 13, 30, 0, tzinfo=CENTRAL)


def ev(ms, action="M", side="N", price=None, size=None,
       bid=(7500.0, 100), ask=(7500.25, 100)):
    """Book event `ms` milliseconds after T0 with post-event top-of-book."""
    return BookEvent(
        ts=T0 + timedelta(milliseconds=ms), symbol="ESU6", instrument_id=1,
        action=action, side=side, price=price, size=size,
        bid_px=bid[0], bid_sz=bid[1], ask_px=ask[0], ask_sz=ask[1],
    )


def defended_bid_stream(price=7500.0, refills=2, vol_each=200):
    """Sellers throw `refills+1` prints at the bid; size refills `refills`
    times; then the bid steps UP (defense won). Aggr vol = (refills+1)*vol_each."""
    s = [ev(0, bid=(price, 100))]
    ms = 10
    for i in range(refills + 1):
        # a sell aggressor consumes most of the level (100 -> 20)
        s.append(ev(ms, action="T", side="A", price=price, size=vol_each,
                    bid=(price, 20)))
        ms += 10
        if i < refills:
            # passive size steps back in (20 -> 100): one refill event
            s.append(ev(ms, bid=(price, 100)))
            ms += 10
    # defense wins: bid lifts beyond the 2-tick band, episode at `price` closes
    s.append(ev(ms, bid=(price + 0.75, 60), ask=(price + 1.0, 80)))
    return s


def only_absorption(signals):
    return [s for s in signals if isinstance(s, AbsorptionRead)]


def test_defended_bid_emits_with_positive_displacement():
    tracker = AbsorptionTracker()
    reads = only_absorption(tracker.run(defended_bid_stream()))
    assert len(reads) == 1
    r = reads[0]
    assert r.side == "bid"
    assert r.price == 7500.0
    assert r.aggressive_vol == 600
    assert r.refill_events == 2
    assert r.displacement_ticks == 3          # bid lifted past the band = defense won
    assert 0.0 < r.confidence <= 1.0
    assert "absorbed" in r.reason and "lifted away" in r.reason


def test_broken_bid_reports_negative_displacement():
    s = defended_bid_stream()
    # overwrite the close: bid steps DOWN instead — the level finally broke
    s[-1] = ev(9_000, bid=(7499.75, 40))
    reads = only_absorption(AbsorptionTracker().run(s))
    assert len(reads) == 1
    assert reads[0].displacement_ticks == -1
    assert "broke" in reads[0].reason


def test_ask_side_symmetry():
    price = 7500.25
    s = [ev(0, ask=(price, 100))]
    ms = 10
    for i in range(3):
        s.append(ev(ms, action="T", side="B", price=price, size=150,
                    ask=(price, 15)))
        ms += 10
        if i < 2:
            s.append(ev(ms, ask=(price, 90)))
            ms += 10
    s.append(ev(ms, ask=(price + 0.25, 50), bid=(7499.75, 60)))  # ask stepped up = consumed
    reads = only_absorption(AbsorptionTracker().run(s))
    assert len(reads) == 1
    r = reads[0]
    assert r.side == "ask"
    assert r.aggressive_vol == 450
    assert r.refill_events == 2
    assert r.displacement_ticks == -1         # ask stepping up = buyers broke the level
    assert "buyers" in r.reason and "broke" in r.reason


def test_volume_floor_suppresses():
    # 2 refills but only 99 contracts of aggression (< 100 floor)
    reads = only_absorption(
        AbsorptionTracker().run(defended_bid_stream(vol_each=33)))
    assert reads == []


def test_refill_floor_suppresses():
    # plenty of volume, single refill (< 2 floor)
    reads = only_absorption(
        AbsorptionTracker().run(defended_bid_stream(refills=1, vol_each=400)))
    assert reads == []


def test_sub_threshold_recovery_not_a_refill():
    price = 7500.0
    s = [ev(0, bid=(price, 100))]
    # deplete 100 -> 20, recover only to 40 (< 25 recovery), repeat
    s += [ev(10, action="T", side="A", price=price, size=400, bid=(price, 20)),
          ev(20, bid=(price, 40)),
          ev(30, action="T", side="A", price=price, size=400, bid=(price, 15)),
          ev(40, bid=(price, 35)),
          ev(50, bid=(price + 0.25, 60))]
    assert only_absorption(AbsorptionTracker().run(s)) == []


def test_trade_at_other_price_not_attributed():
    # sells print BELOW the standing bid price — not this level's defense
    price = 7500.0
    s = [ev(0, bid=(price, 100))]
    ms = 10
    for i in range(3):
        s.append(ev(ms, action="T", side="A", price=price - 0.25, size=400,
                    bid=(price, 20)))
        ms += 10
        s.append(ev(ms, bid=(price, 100)))
        ms += 10
    s.append(ev(ms, bid=(price + 0.25, 60)))
    assert only_absorption(AbsorptionTracker().run(s)) == []


def test_buy_aggressor_not_attributed_to_bid():
    s = defended_bid_stream()
    flipped = [replace(e, side="B") if e.action == "T" else e for e in s]
    assert only_absorption(AbsorptionTracker().run(flipped)) == []


def test_flush_closes_open_episode_with_zero_displacement():
    s = defended_bid_stream()[:-1]            # never close the episode in-stream
    reads = only_absorption(AbsorptionTracker().run(s))
    assert len(reads) == 1
    assert reads[0].displacement_ticks == 0
    assert "end of stream" in reads[0].reason


def test_band_survives_topofbook_flicker():
    """The defended price stays alive while better bids sit in front of it;
    the refill cycle pauses there and resumes when P returns to top."""
    price = 7500.0
    s = [ev(0, bid=(price, 100)),
         ev(10, action="T", side="A", price=price, size=200, bid=(price, 20)),
         ev(20, bid=(price + 0.25, 40)),   # better bid in front — P still alive
         ev(30, bid=(price + 0.5, 30)),    # edge of the 2-tick band — still alive
         ev(40, bid=(price, 90)),          # P back on top: 20 -> 90 = one refill
         ev(50, action="T", side="A", price=price, size=200, bid=(price, 15)),
         ev(60, bid=(price, 80)),          # second refill
         ev(70, bid=(price - 0.25, 50))]   # trades through — broke
    reads = only_absorption(AbsorptionTracker().run(s))
    assert len(reads) == 1
    r = reads[0]
    assert r.aggressive_vol == 400
    assert r.refill_events == 2
    assert r.displacement_ticks == -1


def test_out_of_order_raises():
    tracker = AbsorptionTracker()
    tracker.process(ev(100))
    with pytest.raises(ValueError, match="out-of-order"):
        tracker.process(ev(50))


def test_determinism_same_stream_same_reads():
    s = defended_bid_stream(refills=3, vol_each=250)
    a = only_absorption(AbsorptionTracker().run(s))
    b = only_absorption(AbsorptionTracker().run(s))
    assert a == b and len(a) == 1
