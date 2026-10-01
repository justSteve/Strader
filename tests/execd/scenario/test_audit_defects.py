"""The 2026-10-01 audit's fifteen defects, each as a scenario. [st-ug1h]

Every test here is ``xfail(strict=True)`` and names its defect
(``known_bugs.KNOWN["D<n>"]``): it runs the sequence that reaches the
defect over the real service and the paper book and asserts what SHOULD
happen. It fails today; when the defect is fixed it passes, the strict
xfail turns red, and the fixer deletes the marker and the ``KNOWN`` entry
together.

Where the paper book cannot express the broker behaviour a defect needs —
an answer lost, a cancel only acknowledged, a fill in two prints, a partly
filled entry, a fill the service did not send — the scenario uses
``faults.FaultBook`` and says which knob. The two stream/doorbell defects
(D14) run against ``AccountStream`` and the ``Watcher`` directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execd.broker import BrokerError
from execd.intent import OrderIntent, OrderType, Side

from .faults import FaultBook
from .known_bugs import reason
from .tape import CT, Frame, occ, ramp, scripted

T0 = datetime(2026, 9, 30, 13, 23, 50, tzinfo=CT).astimezone(timezone.utc)
DAY = T0.astimezone(CT).date()
C = occ(DAY, "C", 7690)
C3 = occ(DAY, "C", 7720)
P = occ(DAY, "P", 7700)


def pinned(*rows, sym=C, delta=0.60, spx=7696.0):
    """Frames at ``(t, bid, ask)`` for one contract, delta pinned, and the
    index moving with the contract through that delta — an option that
    rises while SPX stands still would walk its own stop level past the
    mark and be sold by the SPX loop for the tape's inconsistency."""
    mid0 = (rows[0][1] + rows[0][2]) / 2
    sign = 1 if sym[12] == "C" else -1
    return scripted([Frame(t, round(spx + sign * ((b + a) / 2 - mid0) / delta, 2),
                           quotes={sym: (b, a)}, deltas={sym: delta if sign > 0 else -delta})
                     for t, b, a in rows], start=T0)


def stops(scn, sym=C):
    return scn.resting(sym)["stop"]


# ── D1 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("move", ["follows-fill-then-trail", "hand"])
def test_d1_restart_after_a_replace(make, move):
    """A better fill moves the stop (a replace), the trail moves it again (a
    replace); the box restarts. Exactly one stop must rest — and when the
    market gaps through, the account must not go short."""
    scn = make(pinned((0, 9.10, 9.20), (2, 9.00, 9.10), (6, 9.80, 9.90),
                      (30, 9.80, 9.90), (40, 7.90, 8.00), (80, 7.90, 8.00)))
    t = scn.ticket("call", strike=7690, limit=9.20, stopoff=0.50)
    scn.wait_until(2)
    scn.send(t)                                     # fills 9.10: the stop follows to 8.60
    if move == "hand":
        scn.adjust(C, stop_price=8.50)
    else:
        scn.run(6)                                  # +$68.70: the trail's tier 0
        assert scn.position(C).trail_tier >= 0
    scn.restart()
    scn.tick()
    assert len(stops(scn)) == 1
    scn.run(40)                                     # gap through every stop resting
    assert scn.held() == {}


# ── D2 ───────────────────────────────────────────────────────────────────

def test_d2_a_triggered_send_whose_answer_was_lost(make):
    """The book takes the entry with its bracket and fills it; the answer
    never comes back. The orphan sweep finds the order — and must not put a
    second bracket beside the one the order carried."""
    scn = make(pinned((0, 9.10, 9.20), (60, 9.10, 9.20)), book=FaultBook)
    scn.paper.lose_answer = True
    scn.send(scn.ticket("call", strike=7690), raises=BrokerError)
    scn.paper.lose_answer = False
    scn.wait_until(5)
    scn.step("reconcile (a page poll)", scn.service.reconcile)
    assert scn.held() == {C: 1} and len(stops(scn)) == 1


# ── D3 ───────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=reason("D3"))
@pytest.mark.parametrize("fault", ["children-read-fails", "fallback-cancel-pending"])
def test_d3_the_childrens_read_fails(make, fault):
    scn = make(pinned((0, 9.10, 9.20), (60, 9.10, 9.20)), book=FaultBook)
    if fault == "children-read-fails":
        scn.paper.children_fail = 1
    else:
        # the listing shows the stop and not yet the target; the fallback's
        # cancel of the stop is acknowledged, not done
        scn.paper.hide_target = 1
        scn.paper.pending_cancel_if = lambda o: o.order_type is OrderType.STOP
    scn.send(scn.ticket("call", strike=7690))
    scn.run(9)
    assert len(stops(scn)) == 1 and len(scn.resting(C)["target"]) == 1


# ── D4 ───────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=reason("D4"))
@pytest.mark.parametrize("prints", ["5ms-apart", "same-ms", "working-between"])
def test_d4_a_close_in_two_prints(make, prints):
    """Two lots; the stop executes as 1 + 1. The whole close is booked, and
    nothing is re-rested on a flat account."""
    scn = make(pinned((0, 9.10, 9.20), (3, 9.10, 9.20), (6, 8.50, 8.60), (60, 8.50, 8.60)),
               book=FaultBook)
    if prints == "working-between":
        scn.paper.partial = {"side": Side.SELL_TO_CLOSE, "first": 1, "hold_s": 5}
    else:
        scn.paper.split_prints = True
        scn.paper.print_gap_ms = 5 if prints == "5ms-apart" else 0
    scn.send(scn.ticket("call", strike=7690, lots=2, stopoff=0.50))
    scn.run(30)
    assert scn.held() == {} and scn.working() == []
    assert sum(c["qty"] for c in scn.closes()) == 2


# ── D5 ───────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=reason("D5"))
def test_d5_a_partly_filled_entry(make):
    """A two-lot limit fills one, rests the other a few seconds, then fills
    it: one position of two with one bracket of two."""
    scn = make(pinned((0, 9.20, 9.30), (3, 9.10, 9.20), (60, 9.10, 9.20)), book=FaultBook)
    scn.paper.partial = {"side": Side.BUY_TO_OPEN, "first": 1, "hold_s": 6}
    scn.send(scn.ticket("call", strike=7690, lots=2, limit=9.20, stopoff=0.50))
    scn.run(20)
    assert scn.position(C).qty == 2 and scn.held() == {C: 2}
    assert [o.qty for o in scn.working(C)] == [2, 2]


# ── D6 ───────────────────────────────────────────────────────────────────

def test_d6_the_watcher_sleeps_on_an_unconfirmed_send(make):
    """The send's answer is lost while the order rests; nothing else is
    happening, so only the watcher can find it — and it must."""
    scn = make(pinned((0, 9.20, 9.30), (60, 9.20, 9.30)), book=FaultBook)
    scn.paper.lose_answer = True
    scn.send(scn.ticket("call", strike=7690, limit=9.20), raises=BrokerError)
    assert scn.service._unconfirmed
    scn.run(90)                                     # past SEND_SETTLE_S
    assert scn.service._working, "the watcher never looked for the unanswered send"


# ── D7 ───────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=reason("D7"))
def test_d7_a_close_deferred_by_a_pending_cancel(make):
    """FLATTEN; the target's cancel is only acknowledged. The close defers
    — and must not leave a stop resting unlinked beside the target."""
    scn = make(pinned((0, 9.10, 9.20), (60, 9.10, 9.20)), book=FaultBook)
    scn.send(scn.ticket("call", strike=7690))
    scn.paper.pending_cancel_if = lambda o: o.order_type is OrderType.LIMIT
    out = scn.flatten()
    assert out["closed"][0]["status"] == "DEFERRED"
    scn.run(9)


# ── D8 ───────────────────────────────────────────────────────────────────

def test_d8_tier_zero_locks_a_loss(make):
    """Seven lots in at 3.00; the bid 3.10 nets +$60.90, so the trail arms
    and promises +$30 — and rests the stop at 3.00, −$9.10 after fees."""
    scn = make(pinned((0, 2.90, 3.00), (3, 3.10, 3.20), (30, 3.10, 3.20), sym=C3, delta=0.30))
    scn.send(scn.ticket("call", strike=7720, lots=7, stopoff=0.50))
    scn.run(9)


# ── D9 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("part", ["close-is-net", "promoted-commission"])
def test_d9_the_day_is_continuous_through_a_close(make, part):
    if part == "close-is-net":
        scn = make(pinned((0, 9.10, 9.20), (3, 9.05, 9.15), (6, 8.95, 9.05), (30, 8.95, 9.05)))
        scn.send(scn.ticket("call", strike=7690))
        scn.tick()
        pos = scn.position(C)
        fees = pos.entry_commission_usd + 0.65
        scn.run(6, until=lambda s: not s.held())
        close, = scn.closes()
        # the card's arithmetic at the price it closed at
        net = round((close["exit_price"] - close["entry_price"]) * 100 - fees, 2)
        assert scn.service.status()["pnl"]["day_usd"] == net
    else:
        scn = make(pinned((0, 9.20, 9.30), (3, 9.10, 9.20), (30, 9.10, 9.20)))
        scn.send(scn.ticket("call", strike=7690, limit=9.20, stopoff=0.50))
        scn.run(6, until=lambda s: bool(s.held()))
        assert scn.position(C).entry_commission_usd == 0.65


# ── D10 ──────────────────────────────────────────────────────────────────

def test_d10_eight_lots_are_not_refused_by_the_preview(make):
    scn = make(pinned((0, 9.10, 9.20), (60, 9.10, 9.20)))
    out = scn.send(scn.ticket("call", strike=7690, lots=8, stopoff=0.50))
    assert out["refused"] is None, out["refused"]


# ── D11 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("where", ["another-contract", "the-held-contract"])
def test_d11_a_sell_to_open_is_not_a_close(make, where):
    """Steve sells a fly's body in TOS (SELL_TO_OPEN). Not a close of
    anything the service holds, and not an alarm."""
    scn = make(pinned((0, 9.10, 9.20), (60, 9.10, 9.20)), book=FaultBook)
    scn.send(scn.ticket("call", strike=7690, stopoff=0.50))
    sym = occ(DAY, "C", 7700) if where == "another-contract" else C
    oid = scn.paper.outside_fill(sym, 2, 5.00, instruction="SELL_TO_OPEN")
    scn.memory.outside_orders.add(oid)
    scn.tick()
    assert scn.events("unattributed_sell") == []
    assert [c for c in scn.closes() if c["order_id"] == oid] == []
    assert scn.service._open.get(C) is not None


# ── D12 ──────────────────────────────────────────────────────────────────

def test_d12_rest_fill_and_fire_between_passes(make):
    """A 9.20 limit rests under a 9.20/9.30 market; the market gaps to
    8.50/8.60 between two passes — the entry fills and its stop fires before
    the service looks. The close is right; there must be no false alarm."""
    scn = make(pinned((0, 9.20, 9.30), (2, 8.50, 8.60), (60, 8.50, 8.60)))
    scn.send(scn.ticket("call", strike=7690, limit=9.20))
    scn.run(9)


# ── D13 ──────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=reason("D13"))
@pytest.mark.parametrize("forgets", ["trail-tier", "fill-watermark"])
def test_d13_what_a_restart_forgets(make, forgets):
    scn = make(pinned((0, 9.10, 9.20), (3, 9.80, 9.90), (60, 9.80, 9.90)), strict=False)
    scn.send(scn.ticket("call", strike=7690))
    scn.run(9)
    tier = scn.position(C).trail_tier
    assert tier >= 0
    died_at = scn.clock()
    last_poll = scn.service._last_fill_poll
    scn.wait_until(300)                             # five minutes down
    scn.restart()
    if forgets == "trail-tier":
        assert scn.position(C).trail_tier == tier
    else:
        assert scn.service._last_fill_poll <= died_at and last_poll <= died_at


# ── D14 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("part", ["backoff-resets", "ring-during-reconcile"])
def test_d14_the_doorbell(make, part):
    if part == "backoff-resets":
        from execd.schwab import AccountStream

        from ..test_stream import FakeBroker, FakeWS, activity, ok
        scripts = [[json_refused()],                                   # down
                   [ok("LOGIN"), ok("SUBS"), activity("OrderCreated")],  # up, then drops
                   [json_refused()]]
        slept: list[float] = []
        stream = AccountStream(FakeBroker(), lambda t: None,
                               connect=lambda url, **kw: FakeWS(scripts.pop(0)))

        def sleep(s):
            slept.append(s)
            if not scripts:
                stream._stop.set()
        stream._sleep = sleep
        stream.run()
        # after a session that came UP, the next retry starts from the first step
        assert slept[1] == slept[0], slept
    else:
        scn = make(pinned((0, 9.10, 9.20), (60, 9.10, 9.20)))
        scn.send(scn.ticket("call", strike=7690))
        svc, w = scn.service, scn.watcher
        real = svc.reconcile

        def reconcile_then_ring():
            out = real()
            w.ring(["OrderFilled"])         # an account event lands mid-reconcile
            return out
        svc.reconcile = reconcile_then_ring
        scn.tick()
        scn.clock.advance(seconds=0.5)       # the wait ends at once: the bell rang
        out = w.once()
        assert out.get("rung") is True and out.get("reconcile"), out


def json_refused() -> str:
    import json
    return json.dumps({"response": [{"command": "LOGIN", "content": {"code": 3, "msg": "no"}}]})


# ── D15 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("part", ["three-dollar-boundary", "negative-put-delta"])
def test_d15_the_restrike(make, part):
    if part == "three-dollar-boundary":
        # a 3.00 limit rests under 3.00/3.10, fills when the offer comes to
        # it; the stop he typed is 2.95
        scn = make(pinned((0, 3.00, 3.10), (3, 2.95, 3.00), (30, 2.95, 3.00),
                          sym=C3, delta=0.30))
        t = scn.ticket("call", strike=7720, limit=3.00, stop="2.95")
        assert t.stop_price == 2.95
        scn.send(t)
        scn.run(6, until=lambda s: bool(s.held()))
        assert stops(scn, C3) == [2.95]
    else:
        scn = make(scripted([Frame(0, 7696.0, quotes={P: (9.10, 9.20)}, deltas={P: -0.45}),
                             Frame(60, 7696.0, quotes={P: (9.10, 9.20)}, deltas={P: -0.45})],
                            start=T0))
        level = round(7696.0 + 0.20 / 0.45, 2)
        intent = OrderIntent(intent_id="api-put-1", symbol=P, side=Side.BUY_TO_OPEN, qty=1,
                             order_type=OrderType.LIMIT, limit=9.20, stop_price=9.00,
                             stop_spx=level, delta=-0.45, source="api")
        out = scn.send(intent)
        assert out["refused"] is None, out["refused"]
        assert stops(scn, P) == [9.00]
