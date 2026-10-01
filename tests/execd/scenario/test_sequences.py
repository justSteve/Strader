"""Named sequences — the real service over the paper book on a tape. [st-ug1h]

Each test is a short session: the market moves, Steve does something, the
watcher passes. After every step the harness checks every invariant
(``invariants.py``); the asserts here are about what the sequence is FOR.
The prices are the model's (Black-Scholes on the 0DTE clock, ``tape.py``)
except where a test pins the numbers of a real ticket.

Steve, 2026-09-30: "There is a CLI backing the GUI form, right? Seems like
tests should have caught these bugs and edge cases." The entries here go in
through that CLI — ``orderform.price`` and ``intent_for``, the code behind
the page's SEND — not hand-built intents.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execd.bounds import Bounds
from execd.stops import take_profit_price

from .known_bugs import reason
from .tape import CT, Frame, occ, ramp, scripted

#: 13:23:50 CT on 2026-09-30, for the tickets with that day's numbers
T1324 = datetime(2026, 9, 30, 13, 23, 50, tzinfo=CT).astimezone(timezone.utc)
C7690 = occ(T1324.astimezone(CT).date(), "C", 7690)


def flat(seconds: float = 120.0, spx: float = 6380.0, **kw):
    return ramp((0, spx), (seconds, spx), **kw)


def sole_stop(scn, sym) -> float:
    r = scn.resting(sym)
    assert len(r["stop"]) == 1, r
    return r["stop"][0]


# ── entries ──────────────────────────────────────────────────────────────

class TestEntries:
    def test_an_unlocked_ticket_fills_at_the_ask_with_its_bracket_resting(self, make):
        scn = make(flat())
        t = scn.ticket("call", delta=0.5)
        assert t.limit == t.contract.ask_pts
        out = scn.send(t)
        sym = t.contract.symbol
        assert out["order"]["status"] == "FILLED" and out["order"]["fill_price"] == t.limit
        assert scn.resting(sym) == {"stop": [t.stop_price],
                                    "target": [take_profit_price(t.limit, 5.0)]}
        assert round(t.limit - t.stop_price, 2) == 0.20            # the flat $20
        scn.run(30)
        assert scn.held() == {sym: 1}

    def test_a_locked_limit_under_the_ask_rests_then_fills_as_the_offer_comes_down(self, make):
        """A limit 0.10 under the offer with a 0.50 stop: the dip that fills
        it is shorter than the stop's distance (the deeper dip is the next test)."""
        scn = make(ramp((0, 6380), (30, 6380), (90, 6378), (150, 6378)))
        live = scn.ticket("call", strike=6380)
        locked = round(live.limit - 0.10, 2)
        t = scn.ticket("call", strike=6380, limit=locked, stopoff=0.50)
        out = scn.send(t)
        sym = t.contract.symbol
        assert out["order"]["status"] == "WORKING" and out["working"]["triggered"] is True
        assert scn.resting(sym) == {"stop": [], "target": []}       # nothing rests yet
        scn.run(150, until=lambda s: bool(s.held()))
        pos = scn.position(sym)
        assert pos is not None and pos.entry_price <= locked
        assert len(scn.resting(sym)["stop"]) == 1 and len(scn.resting(sym)["target"]) == 1
        scn.run(30)

    def test_a_dip_buy_limit_is_not_sold_by_its_own_level(self, make):
        """60 cents under the offer with the default $20 stop: the dip that
        fills it is longer than the stop's distance. The level is struck
        again from the mark at the fill (st-d3va), so the pass that fills it
        does not sell it; the dip going on another 2.8 points afterwards
        takes the $20 stop, measured from the fill, as the market."""
        scn = make(ramp((0, 6380), (30, 6380), (90, 6376), (150, 6376)))
        live = scn.ticket("call", strike=6380)
        t = scn.ticket("call", strike=6380, limit=round(live.limit - 0.60, 2))
        scn.send(t)
        scn.run(150, until=lambda s: bool(s.held()))
        assert scn.held() == {t.contract.symbol: 1}, "sold on the pass that filled it"
        fill, = scn.events("filled")
        # the ticket's $20 behind the mark at the fill, not the send's
        assert abs(fill["spx"] - fill["stop_spx"] - 0.20 / abs(fill["delta"])) <= 0.011
        scn.run(9)
        assert all(c["kind"] != "spx-stop" or c["exit_price"] <= round(t.limit - 0.20, 2)
                   for c in scn.closes())

    def test_an_entry_carrying_an_spx_stop_is_refused(self, make):
        """H5 was a dip-buy limit with his close-at-SPX level under the
        send's mark: it filled past the level and the level sold it on the
        pass that filled it (st-a54y). Steve, 2026-10-01: "At entry, only
        permit a $$ SL but after a fill the level should become an option
        again." The ticket refuses the level in words, and the service
        refuses an intent that carries one — a level with no dollar price,
        or a close-at level — so a stale page or a direct call cannot send
        it. Nothing rests, nothing is held."""
        from dataclasses import replace
        scn = make(ramp((0, 6380), (30, 6380), (90, 6376), (150, 6376)))
        live = scn.ticket("call", strike=6380)
        dip = round(live.limit - 0.60, 2)
        t = scn.ticket("call", strike=6380, limit=dip, exitspx=6379.5)
        assert t.error and "dollars only" in t.error
        with pytest.raises(ValueError, match="dollars only"):
            scn.intent(t)
        ok = scn.intent(scn.ticket("call", strike=6380, limit=dip))
        for i, bad in enumerate((replace(ok, intent_id="lvl-1", stop_price=None),
                                 replace(ok, intent_id="lvl-2", exit_spx=6379.5))):
            out = scn.send(bad)
            assert out["refused"]["bound"] == "entry_stop_dollars", out
        scn.run(150)
        assert scn.held() == {} and scn.working() == []
        assert scn.events("sending") == []

    def test_the_unlocked_ticket_follows_the_ask(self, make):
        scn = make(ramp((0, 6380), (30, 6384)))
        before = scn.ticket("call", strike=6380)
        scn.wait_until(30)
        after = scn.ticket("call", strike=6380)
        assert after.limit > before.limit and after.limit == after.contract.ask_pts
        assert round(after.limit - after.stop_price, 2) == 0.20


# ── fills against the stop sent with them ────────────────────────────────

class TestFills:
    def test_fill_at_the_limit_rests_the_tickets_stop(self, make):
        scn = make(flat())
        t = scn.ticket("put", delta=0.4, stopoff=0.5)
        scn.send(t)
        assert sole_stop(scn, t.contract.symbol) == t.stop_price == round(t.limit - 0.5, 2)

    def test_fill_a_little_better_than_the_limit_moves_the_stop_down(self, make):
        """The improvement is under the stop distance, so the stop sent with
        the entry is still under the market when it lands; then it follows
        the fill (``_stop_follows_fill``, st-0f5q)."""
        sym = occ(T1324.astimezone(CT).date(), "C", 7720)
        tape = scripted([Frame(0, 7696.0, quotes={sym: (2.05, 2.10)}),
                         Frame(2, 7696.0, quotes={sym: (1.95, 2.00)}),
                         Frame(60, 7696.0, quotes={sym: (1.95, 2.00)})], start=T1324)
        scn = make(tape)
        t = scn.ticket("call", strike=7720, limit=2.10)
        assert t.stop_price == 1.90
        scn.wait_until(2)
        scn.send(t)
        assert scn.position(sym).entry_price == 2.00
        assert sole_stop(scn, sym) == 1.80
        scn.run(30)

    def test_fill_much_better_than_the_limit(self, make):
        """13:24 CT 2026-09-30, the numbers of the day: a 9.20 limit, the
        market 8.70/8.80 when it went — filled at 8.80 under a 9.00 stop."""
        tape = scripted([Frame(0, 7696.0, quotes={C7690: (9.10, 9.20)}),
                         Frame(2, 7696.0, quotes={C7690: (8.70, 8.80)}),
                         Frame(60, 7696.0, quotes={C7690: (8.70, 8.80)})], start=T1324)
        scn = make(tape)
        t = scn.ticket("call", strike=7690, limit=9.20)
        scn.wait_until(2)
        scn.send(t)
        scn.run(30)
        assert scn.held() == {C7690: 1}             # not stopped out by its own stop

    @pytest.mark.xfail(strict=True, reason=reason("H6"))
    def test_a_resting_entry_filled_in_a_market_wider_than_its_stop(self, make):
        """A 9.20 limit with a 0.50 stop rests under 9.30/9.40; the market
        drops to 8.50/9.00 and fills it at 9.00. Measured from the fill the
        stop is 8.50 — at the 8.50 bid, so the follow is refused and the
        stop stays 8.70, 0.30 from the fill on a 0.50 ticket."""
        tape = scripted([Frame(0, 7696.0, quotes={C7690: (9.30, 9.40)}, deltas={C7690: 0.60}),
                         Frame(3, 7695.0, quotes={C7690: (8.50, 9.00)}, deltas={C7690: 0.60}),
                         Frame(60, 7695.0, quotes={C7690: (8.50, 9.00)}, deltas={C7690: 0.60})],
                        start=T1324)
        scn = make(tape)
        t = scn.ticket("call", strike=7690, limit=9.20, stopoff=0.50)
        scn.send(t)
        scn.run(9)

    @pytest.mark.parametrize("spread, lots", [(0.30, 1), (0.10, 2)], ids=["wide", "two-lots"])
    def test_a_stop_at_or_over_the_bid_is_refused_at_the_ticket(self, make, spread, lots):
        """H2 (st-yeph): 0.30 wide under the 0.20 default; or the case that
        raised it, an ordinary 0.10 market at two lots, where the flat $20
        is 0.10 a contract — the stop at the bid, sold on the fill. Steve,
        2026-10-01: "in those conditions it should refuse". The ticket says
        so and offers no intent; the service refuses the same intent sent
        around the page, and nothing goes to the book."""
        from dataclasses import replace
        scn = make(flat(spread=spread))
        t = scn.ticket("call", delta=0.5, lots=lots)
        q = scn.quote(t.contract.symbol)
        assert t.stop_price >= q.bid
        assert t.error == (f"the stop {t.stop_price:.2f} would rest at or above the "
                           f"{q.bid:.2f} bid and sell on the fill — widen the stop")
        with pytest.raises(ValueError, match="widen the stop"):
            scn.intent(t)
        wide = scn.intent(scn.ticket("call", delta=0.5, lots=lots, stopoff=spread + 0.10))
        out = scn.send(replace(wide, intent_id="around-the-page", stop_price=t.stop_price))
        assert out["refused"]["bound"] == "stop_over_bid", out
        assert "at or above" in out["refused"]["reason"]
        assert scn.events("sending") == [] and scn.held() == {}

    @pytest.mark.parametrize("spread, lots", [(0.30, 1), (0.10, 2)], ids=["wide", "two-lots"])
    def test_the_same_ticket_widened_goes_through(self, make, spread, lots):
        """He widens the stop one step past the spread and the same ticket
        is sent, fills, and its stop rests under the bid."""
        scn = make(flat(spread=spread))
        t = scn.ticket("call", delta=0.5, lots=lots, stopoff=round(spread + 0.10, 2))
        assert t.error is None
        out = scn.send(t)
        assert out["refused"] is None and out["order"]["status"] == "FILLED"
        sym = t.contract.symbol
        assert sole_stop(scn, sym) < scn.quote(sym).bid
        scn.run(30)
        assert scn.held() == {sym: lots}

    def test_a_dollar_stop_survives_spx_moving_before_the_send(self, make):
        """Priced at 7696.00, sent with SPX at 7695.60: the ticket's level
        (0.20 at delta ~0.7 is 0.29 points) is behind the mark."""
        tape = scripted([Frame(0, 7696.0, quotes={C7690: (9.10, 9.20)}, deltas={C7690: 0.70}),
                         Frame(2, 7695.6, quotes={C7690: (8.85, 8.95)}, deltas={C7690: 0.70})],
                        start=T1324)
        scn = make(tape)
        t = scn.ticket("call", strike=7690, limit=9.20)
        scn.wait_until(2)
        out = scn.send(t)
        assert out["refused"] is None, out["refused"]


# ── the bracket at work ──────────────────────────────────────────────────

class TestTheBracket:
    def test_a_falling_tape_takes_the_stop_and_the_target_comes_off(self, make):
        scn = make(ramp((0, 6380), (15, 6380), (75, 6372), (120, 6372)))
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        scn.run(120, until=lambda s: not s.held())
        close, = scn.closes()
        assert (close["kind"], close["reason"]) in {("protective-stop", "resting-stop"),
                                                    ("spx-stop", "spx-stop")}
        assert close["pnl_usd"] < 0 and scn.working(sym) == []
        scn.run(9)

    def test_the_target_fills_first_and_the_stop_comes_off(self, make):
        scn = make(ramp((0, 6380), (15, 6380), (90, 6400), (120, 6400)),
                   bounds=Bounds(take_profit_multiple=1.5, trail_arm_usd=0))
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        assert scn.resting(sym)["target"] == [take_profit_price(t.limit, 1.5)]
        scn.run(120, until=lambda s: not s.held())
        close, = scn.closes()
        assert (close["kind"], close["reason"]) == ("target", "resting-target")
        assert close["exit_price"] >= take_profit_price(t.limit, 1.5)
        assert scn.working(sym) == []

    def test_flatten_sells_at_the_bid_and_leaves_nothing_resting(self, make):
        scn = make(flat())
        t = scn.ticket("put", delta=0.5)
        scn.send(t)
        scn.run(9)
        bid = scn.quote(t.contract.symbol).bid
        out = scn.flatten()
        assert out["errors"] == [] and scn.held() == {}
        close, = scn.closes()
        assert (close["kind"], close["exit_price"]) == ("flatten", bid)
        assert scn.working() == []

    def test_two_lots_a_partial_exit_resizes_both_legs(self, make):
        scn = make(ramp((0, 6380), (30, 6380), (120, 6370)))
        t = scn.ticket("call", delta=0.5, lots=2, stopoff=0.50)
        scn.send(t)
        sym = t.contract.symbol
        assert {o.qty for o in scn.working(sym)} == {2}
        scn.exit(sym, 1)
        assert scn.held() == {sym: 1} and {o.qty for o in scn.working(sym)} == {1}
        scn.run(120, until=lambda s: not s.held())
        assert [c["qty"] for c in scn.closes()] == [1, 1]

    def test_an_add_is_one_position_and_one_bracket(self, make):
        scn = make(flat())
        t = scn.ticket("call", strike=6385)
        scn.send(t)
        scn.tick()
        scn.send(scn.ticket("call", strike=6385))
        sym = t.contract.symbol
        assert scn.held() == {sym: 2}
        assert sorted((o.order_type.value, o.qty) for o in scn.working(sym)) == \
            [("LIMIT", 2), ("STOP", 2)]
        scn.run(30)


# ── a cancel against a fill ──────────────────────────────────────────────

class TestCancel:
    def test_a_cancel_that_loses_the_race_leaves_a_protected_position(self, make):
        """The offer comes down to the resting limit between two watcher
        passes; Steve's CANCEL reaches the book first, finds it FILLED, and
        the fill is promoted with its bracket — never adopted bare."""
        scn = make(ramp((0, 6380), (3, 6380), (4, 6379.6), (60, 6379.6)))
        live = scn.ticket("call", strike=6380)
        t = scn.ticket("call", strike=6380, limit=round(live.limit - 0.20, 2), stopoff=0.50)
        out = scn.send(t)
        oid = out["order"]["order_id"]
        scn.wait_until(5)                       # the offer is at the limit; no pass yet
        res = scn.cancel(oid)
        assert res["filled"] is True and res["confirmed"] is False
        sym = t.contract.symbol
        assert scn.held() == {sym: 1}
        assert len(scn.resting(sym)["stop"]) == 1
        assert scn.events("stop_unprotected") == []
        scn.run(30)

    def test_a_cancel_in_time_leaves_nothing(self, make):
        scn = make(flat())
        live = scn.ticket("call", strike=6380)
        out = scn.send(scn.ticket("call", strike=6380, limit=round(live.limit - 1.0, 2)))
        scn.tick()
        res = scn.cancel(out["order"]["order_id"])
        assert res["confirmed"] is True and scn.service._working == {}
        scn.run(30)
        assert scn.held() == {} and scn.working() == []


# ── Steve moves a leg ────────────────────────────────────────────────────

class TestAdjust:
    def test_the_stop_in_dollars_wider_then_tighter(self, make):
        scn = make(flat())
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        wider = round(t.stop_price - 1.0, 2)
        assert scn.adjust(sym, stop_price=wider)["refused"] is None
        assert scn.resting(sym)["stop"] == [wider]
        tighter = round(t.stop_price + 0.0, 2)
        assert scn.adjust(sym, stop_price=tighter)["refused"] is None
        assert scn.resting(sym)["stop"] == [tighter]
        assert len(scn.resting(sym)["target"]) == 1
        scn.run(30)

    def test_the_stop_as_an_spx_level(self, make):
        scn = make(flat())
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        out = scn.adjust(sym, stop_spx=6374.0)
        assert out["refused"] is None and scn.position(sym).stop_spx == 6374.0
        assert scn.resting(sym)["stop"] == [out["stop"]["new_price"]]
        scn.run(30)

    def test_the_target_in_dollars_and_as_a_level(self, make):
        scn = make(flat())
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        assert scn.adjust(sym, target_price=round(t.limit + 3.0, 2))["refused"] is None
        assert scn.resting(sym)["target"] == [round(t.limit + 3.0, 2)]
        out = scn.adjust(sym, target_spx=6390.0)
        assert out["refused"] is None and scn.position(sym).target_spx == 6390.0
        assert len(scn.resting(sym)["target"]) == 1 and len(scn.resting(sym)["stop"]) == 1
        scn.run(30)

    def test_a_stop_at_the_bid_is_refused_and_nothing_moves(self, make):
        scn = make(flat())
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        bid = scn.quote(sym).bid
        out = scn.adjust(sym, stop_price=bid)
        assert out["refused"]["bound"] == "bracket"
        assert scn.resting(sym)["stop"] == [t.stop_price]

    def test_a_level_target_reached_closes_through_the_loop(self, make):
        scn = make(ramp((0, 6380), (15, 6380), (60, 6386), (90, 6386)),
                   bounds=Bounds(trail_arm_usd=0))
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        scn.adjust(t.contract.symbol, target_spx=6384.0)
        scn.run(90, until=lambda s: not s.held())
        close, = scn.closes()
        assert close["kind"] in ("spx-target", "target")


# ── LOCK with a position open ────────────────────────────────────────────

class TestLock:
    def test_locked_through_the_stop_then_unlocked(self, make):
        """LOCKED, the watcher does nothing and the paper book is not read —
        it has no clock of its own, so a stop the market crossed fills at the
        first read after the unlock, at that moment's bid (live, Schwab
        would have filled it on the cross)."""
        scn = make(ramp((0, 6380), (15, 6380), (60, 6372), (90, 6372)))
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        scn.lock()
        scn.run(60)
        assert scn.held() == {sym: 1} and scn.closes() == []
        scn.unlock()
        close, = scn.closes()
        assert (close["kind"], close["reason"]) == ("protective-stop", "resting-stop")
        assert scn.held() == {} and scn.working() == []
        scn.run(9)


# ── restart: a new service over the same state ──────────────────────────

class TestRestart:
    def test_a_position_and_its_bracket_come_back_and_the_stop_still_books(self, make):
        scn = make(ramp((0, 6380), (30, 6380), (90, 6372), (120, 6372)))
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        stop_id = scn.position(sym).stop_order_id
        scn.run(9)
        scn.restart()
        assert scn.position(sym).stop_order_id == stop_id
        scn.run(110, until=lambda s: not s.held())
        close, = scn.closes()
        assert close["order_id"] == stop_id

    def test_a_working_entry_comes_back_and_fills_with_its_bracket(self, make):
        scn = make(ramp((0, 6380), (30, 6380), (90, 6376), (120, 6376)))
        live = scn.ticket("call", strike=6380)
        t = scn.ticket("call", strike=6380, limit=round(live.limit - 0.10, 2), stopoff=0.50)
        out = scn.send(t)
        scn.tick()
        scn.restart()
        assert out["order"]["order_id"] in scn.service._working
        scn.run(110, until=lambda s: bool(s.held()))
        sym = t.contract.symbol
        assert len(scn.resting(sym)["stop"]) == 1 and len(scn.resting(sym)["target"]) == 1

    # a restart after a replaced leg: test_audit_defects.py::test_d1 (D1)


# ── the trailing stop ────────────────────────────────────────────────────

class TestTrail:
    def test_it_walks_up_its_tiers_and_the_reversal_stops_it_out_in_profit(self, make):
        scn = make(ramp((0, 6380), (10, 6380), (100, 6392), (130, 6392), (200, 6376)))
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        scn.run(200, until=lambda s: not s.held())
        tiers = [e["tier"] for e in scn.events("trail")]
        assert tiers == sorted(tiers) and len(tiers) >= 3
        assert [e["stop_to"] for e in scn.events("trail")] == \
            sorted(e["stop_to"] for e in scn.events("trail"))
        close, = scn.closes()
        assert close["kind"] in ("protective-stop", "spx-stop") and close["pnl_usd"] > 0


# ── the SPX-mark exit loop ───────────────────────────────────────────────

class TestTheSpxLoop:
    """An SPX stop is the position card's after the fill (Steve, 2026-10-01,
    st-a54y: "after a fill the level should become an option again"): the
    entry goes in with its dollar stop and the level is set on the card."""

    def test_a_level_set_on_the_card_after_the_fill_fires_once_and_takes_the_bracket_off(self, make):
        scn = make(ramp((0, 6380), (15, 6380), (75, 6370), (100, 6370)))
        t = scn.ticket("call", delta=0.5)
        assert t.stop_set_by is None and t.error is None
        out = scn.send(t)
        assert out["order"]["status"] == "FILLED"
        sym = t.contract.symbol
        moved = scn.adjust(sym, stop_spx=6376)
        assert moved["refused"] is None, moved
        assert scn.position(sym).stop_spx == 6376.0
        scn.run(100, until=lambda s: not s.held())
        close, = scn.closes()
        assert close["kind"] in ("spx-stop", "protective-stop")
        assert scn.working(sym) == []
        if close["kind"] == "spx-stop":
            assert scn.events("exit_triggered")[0]["spx"] <= 6376.0

    def test_a_put_level_from_below(self, make):
        scn = make(ramp((0, 6380), (15, 6380), (75, 6390), (100, 6390)))
        t = scn.ticket("put", delta=0.5)
        scn.send(t)
        sym = t.contract.symbol
        assert scn.adjust(sym, stop_spx=6384)["refused"] is None
        assert scn.position(sym).stop_spx == 6384.0
        scn.run(100, until=lambda s: not s.held())
        close, = scn.closes()
        assert close["kind"] in ("spx-stop", "protective-stop") and close["pnl_usd"] < 0


# ── paper and live never mix (st-n4tr) ───────────────────────────────────

class TestTheSwitch:
    def test_paper_trades_then_live_sees_none_then_paper_is_fresh(self, make):
        """Steve, 2026-10-01: "Live should never see paper's trades and vice
        versa." A paper round trip on the replayed market; the switch to live
        shows no position, no close, no P&L, and the poll's closed cards are
        empty; back to paper starts at $0 with the old paper journal and book
        archived, not deleted."""
        from .screen import OrderScreen
        scn = make(flat())
        t = scn.ticket("call", delta=0.5)
        scn.send(t)
        scn.run(9)
        scn.flatten()
        assert scn.closes() and scn.service.status()["pnl"]["realized_gross_usd"] != 0
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        assert screen.closed_cards(screen.poll())
        scn.lock()           # the replay has no live side to read: switch while LOCKED
        scn.step("switch to live", lambda: scn.service.set_mode("live"))
        st = scn.service.status()
        assert st["mode"] == "live" and st["positions"] == [] and st["pnl"]["realized_usd"] == 0
        state = screen.poll()
        assert screen.closed_cards(state) == [] and screen.today(state) == 0.0
        scn.run(9)
        scn.step("switch to paper", lambda: scn.service.set_mode("paper"))
        scn.unlock()
        assert [e["event"] for e in scn.service.journal.read()][:1] == ["mode_changed"]
        assert not scn.events("closed") and not scn.events("filled")
        assert scn.paper._orders == {} and scn.held() == {}
        root = scn.service.journal.root / "paper-archive"
        assert any(t.contract.symbol in f.read_text() for f in root.rglob("*.jsonl"))
        assert list(root.rglob("paper-book.json"))
        assert screen.closed_cards(screen.poll()) == []
        scn.send(scn.ticket("call", delta=0.5))               # paper trades again, fresh
        assert len(scn.held()) == 1
