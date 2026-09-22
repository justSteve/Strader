"""ImpactAbsorptionTracker (co-qp8cn): the trailing impact rate, the scaled
floor, and the held/broke outcome on the read. Synthetic streams only."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market.entities.book import BookEvent
from market.orderflow.absorption import AbsorptionTracker
from market.orderflow.absorption_impact import ImpactAbsorptionTracker, ImpactEstimator
from market.signals.orderflow import ImpactAbsorptionRead

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 9, 10, 9, 0, 0, tzinfo=CENTRAL)


def ev(t, action="M", side="N", price=None, size=None, bid=(7500.0, 100), ask=(7500.25, 100)):
    return BookEvent(ts=t, symbol="ESZ6", instrument_id=1, action=action, side=side,
                     price=price, size=size, bid_px=bid[0], bid_sz=bid[1],
                     ask_px=ask[0], ask_sz=ask[1])


def warm_tape(t0, bins, ticks_per_contract, contracts_per_bin=50, bin_s=10):
    """`bins` closed bins in which `contracts_per_bin` buys move the mid by
    exactly rate × contracts ticks: a tape with a known impact rate."""
    out, px = [], 7500.0
    for i in range(bins):
        t = t0 + timedelta(seconds=i * bin_s)
        out.append(ev(t, bid=(px, 50), ask=(px + 0.25, 50)))
        out.append(ev(t + timedelta(seconds=1), action="T", side="B", price=px + 0.25,
                      size=contracts_per_bin, bid=(px, 50), ask=(px + 0.25, 50)))
        px = round(px + ticks_per_contract * contracts_per_bin * 0.25, 2)
        out.append(ev(t + timedelta(seconds=2), bid=(px, 50), ask=(px + 0.25, 50)))
    return out, px


def bid_reads(reads):
    """The warm tape's own buys make ask-side reads at exactly the floor; the
    defended episode under test is the bid side."""
    return [r for r in reads if r.side == "bid"]


def defended_bid(t0, price, vol_each, refills=2, hold_s=0.03, broke=False):
    """Sellers hit `price` `refills+1` times; size refills `refills` times; then
    the bid either lifts away (held) or trades through (broke)."""
    out = [ev(t0, bid=(price, 100), ask=(price + 0.25, 100))]
    t = t0
    step = timedelta(seconds=hold_s / (2 * refills + 1))
    for i in range(refills + 1):
        t += step
        out.append(ev(t, action="T", side="A", price=price, size=vol_each,
                      bid=(price, 20), ask=(price + 0.25, 100)))
        if i < refills:
            t += step
            out.append(ev(t, bid=(price, 100), ask=(price + 0.25, 100)))
    t += timedelta(milliseconds=10)
    if broke:
        out.append(ev(t, action="T", side="A", price=price, size=5,
                      bid=(price - 0.25, 60), ask=(price, 80)))
    else:
        out.append(ev(t, bid=(price + 5.0, 60), ask=(price + 5.25, 80)))
    return out


def test_estimator_recovers_a_known_rate_and_holds_the_seed_until_warm():
    est = ImpactEstimator(bin_s=10, window_s=900, min_bins=30, seed=0.02)
    tape, _ = warm_tape(T0, bins=40, ticks_per_contract=0.04)
    rates = []
    for e in tape:
        est.observe(e)
        rates.append(est.rate)
    assert rates[0] == 0.02                       # seed in force before any bin closed
    assert abs(est.rate - 0.04) < 1e-9            # the fit recovers the tape's rate
    assert est.closed_bins == 39                  # the last bin is still open


def test_estimator_floors_a_flat_tape():
    est = ImpactEstimator(min_bins=5, floor=0.002)
    tape, _ = warm_tape(T0, bins=10, ticks_per_contract=0.0)
    for e in tape:
        est.observe(e)
    assert est.rate == 0.002


def test_floor_scales_with_the_rate_not_a_fixed_count():
    # 3 × 20 = 60 contracts: below the old fixed floor of 100, but at 0.06
    # ticks/contract that is 3.6 expected ticks, above the 3-tick floor
    fast, px = warm_tape(T0, bins=35, ticks_per_contract=0.06)
    ep_t = T0 + timedelta(seconds=35 * 10 + 5)
    stream = fast + defended_bid(ep_t, px, vol_each=20)
    reads = bid_reads(ImpactAbsorptionTracker(expected_ticks_min=3.0).run(stream))
    assert len(reads) == 1 and isinstance(reads[0], ImpactAbsorptionRead)
    r = reads[0]
    assert r.aggressive_vol == 60 and r.expected_ticks > 3.0 and r.held is True
    assert r.displacement_ticks == 20 and r.refill_events == 2
    assert 0.0 <= r.confidence <= 1.0

    # the same 60 contracts on a slow tape (0.01 ticks/contract = 0.6 expected
    # ticks) do not clear, though the old tracker's refill count is identical
    slow, px2 = warm_tape(T0, bins=35, ticks_per_contract=0.01)
    stream2 = slow + defended_bid(ep_t, px2, vol_each=20)
    assert bid_reads(ImpactAbsorptionTracker(expected_ticks_min=3.0).run(stream2)) == []


def test_read_marks_broke_when_the_level_trades_through():
    fast, px = warm_tape(T0, bins=35, ticks_per_contract=0.06)
    ep_t = T0 + timedelta(seconds=35 * 10 + 5)
    stream = fast + defended_bid(ep_t, px, vol_each=20, broke=True)
    (r,) = bid_reads(ImpactAbsorptionTracker(expected_ticks_min=3.0).run(stream))
    assert r.held is False and r.displacement_ticks == -1
    assert "broke" in r.reason


def test_hold_time_gate_and_refills_as_evidence_only():
    fast, px = warm_tape(T0, bins=35, ticks_per_contract=0.06)
    ep_t = T0 + timedelta(seconds=35 * 10 + 5)
    # a fresh price, four ticks off the warm tape's bid, so the episode opens
    # at ep_t rather than inheriting the warm tape's last quote
    px = round(px + 1.0, 2)
    quick = fast + defended_bid(ep_t, px, vol_each=20, hold_s=0.03)
    assert bid_reads(ImpactAbsorptionTracker(expected_ticks_min=3.0, hold_min_s=1.0).run(quick)) == []
    long = fast + defended_bid(ep_t, px, vol_each=20, hold_s=2.0)
    (r,) = bid_reads(ImpactAbsorptionTracker(expected_ticks_min=3.0, hold_min_s=1.0).run(long))
    assert r.hold_s >= 1.0
    # zero refills still emits: refills are evidence here, not a gate
    none = fast + defended_bid(ep_t, px, vol_each=60, refills=0)
    (r0,) = bid_reads(ImpactAbsorptionTracker(expected_ticks_min=3.0).run(none))
    assert r0.refill_events == 0 and r0.aggressive_vol == 60


def test_episode_mechanics_are_the_inherited_ones():
    # with a huge rate every episode clears the floor, so the impact tracker
    # must emit at exactly the moments the fixed tracker would (same episodes)
    fast, px = warm_tape(T0, bins=35, ticks_per_contract=0.06)
    ep_t = T0 + timedelta(seconds=35 * 10 + 5)
    stream = fast + defended_bid(ep_t, px, vol_each=200, refills=3)
    old = AbsorptionTracker().run(stream)
    new = ImpactAbsorptionTracker(expected_ticks_min=0.0).run(stream)
    assert [(r.timestamp, r.side, r.price, r.aggressive_vol, r.refill_events, r.displacement_ticks)
            for r in old if r.aggressive_vol >= 100 and r.refill_events >= 2] == \
           [(r.timestamp, r.side, r.price, r.aggressive_vol, r.refill_events, r.displacement_ticks)
            for r in new if r.aggressive_vol >= 100 and r.refill_events >= 2]


def test_deterministic_and_flush_is_not_a_hold():
    fast, px = warm_tape(T0, bins=35, ticks_per_contract=0.06)
    ep_t = T0 + timedelta(seconds=35 * 10 + 5)
    stream = fast + defended_bid(ep_t, px, vol_each=20)[:-1]   # never ends
    a = ImpactAbsorptionTracker().run(stream)
    b = ImpactAbsorptionTracker().run(stream)
    assert a == b
    (r,) = bid_reads(a)
    assert r.held is False and "end of stream" in r.reason
