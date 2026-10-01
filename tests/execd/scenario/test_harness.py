"""The harness itself — the tape, the replay, the invariants, the waivers. [st-ug1h]

A harness that silently checked nothing would pass forever, so each
invariant is shown here to fire on the state it names, the tape is shown to
be reproducible and to move the options the way the index moves, the live
side is shown to refuse every order, and the fault book with its knobs off
is shown to be the paper book.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from execd.broker import Fill, OrderLeg, OrderResult, OrderStatus, Position
from execd.intent import OrderIntent, OrderType, Side
from execd.paper import PaperBroker

from .faults import FaultBook
from .invariants import InvariantViolation
from .market import LiveSideTraded
from .tape import Frame, GENERATED_START, random_walk, ramp, recorded, scripted
from .test_generated import session


# ── the tape ─────────────────────────────────────────────────────────────

def test_a_seed_is_a_tape():
    a, b, c = random_walk(7), random_walk(7), random_walk(8)
    assert a.path() == b.path() and a.path() != c.path()
    assert [f.stale for f in a.frames] == [f.stale for f in b.frames]


def test_the_option_moves_with_the_index_through_its_delta(make):
    scn = make(ramp((0, 6380), (60, 6384)))
    sym = scn.tape.symbol("C", 6380)
    q0, d0 = scn.quote(sym), scn.market.delta_at(sym, scn.clock())
    scn.wait_until(60)
    q1 = scn.quote(sym)
    moved = (q1.bid + q1.ask) / 2 - (q0.bid + q0.ask) / 2
    assert 0.8 * d0 * 4 <= moved <= 1.3 * d0 * 4
    put = scn.quote(scn.tape.symbol("P", 6380))
    assert put.bid < q1.bid                         # the put fell as the call rose


def test_a_stale_stretch_holds_the_quote_and_ages_it():
    tape = scripted([Frame(0, 6380.0), Frame(3, 6381.0, stale=True), Frame(6, 6382.0)])
    from .market import ReplayMarket
    clock = {"now": tape.start}
    m = ReplayMarket(tape, lambda: clock["now"])
    sym = tape.symbol("C", 6380)
    first = m.quote(sym)
    clock["now"] = tape.start.replace(second=4)
    held = m.quote(sym)
    assert (held.bid, held.ask, held.as_of) == (first.bid, first.ask, first.as_of)
    assert m.quote("$SPX").last == 6380.0


def test_the_recorded_tape_is_the_recorded_path():
    t = recorded(every_s=60)
    assert t.start.isoformat() == "2026-09-30T18:15:00+00:00"
    assert 7685 < min(s for _, s in t.path()) and max(s for _, s in t.path()) < 7705
    assert t.strikes[0] == 7660.0 and t.strikes[-1] == 7755.0


def test_the_live_side_never_trades(make):
    scn = make(ramp((0, 6380), (30, 6380)))
    intent = OrderIntent(intent_id="x-1", symbol=scn.tape.symbol("C", 6380),
                         side=Side.BUY_TO_OPEN, qty=1, order_type=OrderType.LIMIT, limit=1.0)
    for call in (lambda: scn.market.place(intent), lambda: scn.market.cancel("x"),
                 scn.market.orders, scn.market.positions,
                 lambda: scn.market.fills_since(scn.clock())):
        with pytest.raises(LiveSideTraded):
            call()
    assert scn.service.broker.current is scn.paper and scn.service.config.mode == "paper"


# ── the fault book, knobs off, is the paper book ─────────────────────────

def test_the_fault_book_with_its_knobs_off_is_the_paper_book(make):
    runs = []
    for book in (PaperBroker, FaultBook):
        scn = make(random_walk(3, steps=150), book=book)
        session(scn, random.Random(11), resting=False)
        runs.append([(e["event"], e.get("order_id"), e.get("price"), e.get("exit_price"))
                     for e in scn.journal() if e["event"] not in ("order_raw",)])
    assert runs[0] == runs[1] and len(runs[0]) > 20


# ── each invariant fires on the state it names ───────────────────────────

def _holding(make):
    scn = make(ramp((0, 6380), (60, 6380)))
    t = scn.ticket("call", delta=0.5)
    scn.send(t)
    return scn, t.contract.symbol


def _names(scn):
    with pytest.raises(InvariantViolation) as err:
        scn.check("forced")
    return err.value.names


def test_a_short_in_the_book(make):
    scn, sym = _holding(make)
    scn.paper._positions[sym] = Position(sym, -1, 1.0)
    assert "short_position" in _names(scn)


def test_a_second_stop(make):
    scn, sym = _holding(make)
    stop = next(o for o in scn.working(sym) if o.order_type is OrderType.STOP)
    scn.paper._orders["extra"] = replace(stop, order_id="extra")
    assert {"two_stops", "resting_sell_exceeds_held"} <= set(_names(scn))


def test_a_stop_at_the_bid(make):
    scn, sym = _holding(make)
    q = scn.quote(sym)
    stop = next(o for o in scn.working(sym) if o.order_type is OrderType.STOP)
    scn.paper._orders[stop.order_id] = replace(stop, price=q.bid)
    assert "stop_not_below_bid_when_placed" in _names(scn)


def test_what_the_service_holds_against_the_book(make):
    scn, sym = _holding(make)
    scn.paper._positions[sym] = Position(sym, 2, 1.0)
    assert "open_mismatch" in _names(scn)


def test_an_external_close_of_its_own_order_and_an_unknown_kind(make):
    scn, sym = _holding(make)
    stop = next(o for o in scn.working(sym) if o.order_type is OrderType.STOP)
    scn.service.journal.record("closed", symbol=sym, qty=1, entry_price=1.0, exit_price=1.0,
                               pnl_usd=0.0, kind="external", reason="closed-outside-this-service",
                               order_id=stop.order_id)
    scn.service.journal.record("closed", symbol=sym, qty=1, entry_price=1.0, exit_price=1.0,
                               pnl_usd=0.0, kind="bogus", reason="bogus", order_id="nope")
    assert {"external_close_of_own_order", "closed_kind_unknown"} <= set(_names(scn))


def test_a_close_booked_at_a_price_the_book_did_not_fill(make):
    scn, sym = _holding(make)
    entry = next(o for o in scn.paper._orders.values() if o.side is Side.BUY_TO_OPEN)
    scn.service.journal.record("closed", symbol=sym, qty=1, entry_price=1.0, exit_price=2.0,
                               pnl_usd=50.0, kind="flatten", reason="flatten",
                               order_id=entry.order_id)
    assert "pnl_mismatch" in _names(scn)


def test_a_trailing_stop_that_falls(make):
    scn, sym = _holding(make)
    scn.position(sym).trail_tier = 0            # armed by hand, the stop not yet raised:
    scn.waived["trail_locked_a_loss"] = "setup"  # (that state is its own invariant)
    scn.check("armed")
    stop = next(o for o in scn.working(sym) if o.order_type is OrderType.STOP)
    scn.paper._orders[stop.order_id] = replace(stop, price=round(stop.price - 0.5, 2))
    assert "trail_moved_down" in _names(scn)


def test_a_dollar_stop_off_the_ticket(make):
    scn, sym = _holding(make)
    stop = next(o for o in scn.working(sym) if o.order_type is OrderType.STOP)
    scn.paper._orders[stop.order_id] = replace(stop, price=round(stop.price - 0.5, 2))
    assert "stop_dollars_off_ticket" in _names(scn)


def test_an_unlinked_bracket(make):
    scn, sym = _holding(make)
    scn.paper._oco.clear()
    assert "bracket_not_linked" in _names(scn)


def test_a_false_alarm(make):
    scn, sym = _holding(make)
    scn.flatten()
    oid = scn.closes()[-1]["order_id"]
    scn.service.journal.record("unattributed_sell", symbol=sym, order_id=oid, qty=1)
    assert "false_short_alarm" in _names(scn)


# ── waivers cite open defects only ───────────────────────────────────────

def test_a_waiver_must_cite_an_open_defect_for_that_invariant(make):
    tape = ramp((0, 6380), (30, 6380))
    with pytest.raises(KeyError):
        make(tape, waive={"two_stops": "D99"})
    with pytest.raises(ValueError):
        make(tape, waive={"short_position": "H6"})
    scn = make(tape, waive={"stop_dollars_off_ticket": "H6"})
    assert scn.waived == {"stop_dollars_off_ticket": "H6"}
