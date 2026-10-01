"""The recorded tape: 2026-09-30, 13:15–13:45 CT, the half hour of the incidents. [st-ug1h]

The index path is the day's Databento ES tape less one Schwab-measured
basis, second by second; the options are priced from that day's 18:00 UTC
Schwab chain (its IV per strike and its spreads) as the path moves
(``fixtures/build_recorded.py``). Steve's two paper tickets of that
afternoon went out at 13:24 and 13:38; these sessions send at those
moments with the form's own defaults and let the recorded market do what
it did.
"""

from __future__ import annotations

import pytest

from .known_bugs import reason
from .screen import OrderScreen
from .tape import recorded


#: The recorded chain quotes the in-the-money calls 0.20 wide (7685: 21.70/
#: 21.90 at 18:00 UTC), so the form's default $20 stop rests AT the bid —
#: H2, pinned on this very market below. Sessions that are about something
#: else waive it.
H2 = {"stop_not_below_bid_when_placed": "H2"}


@pytest.mark.xfail(strict=True, reason=reason("H2"))
def test_the_default_stop_on_the_recorded_chain_rests_below_the_bid(make):
    scn = make(recorded(from_s=540, to_s=600))           # 13:24 CT
    t = scn.ticket("call")
    q = scn.quote(t.contract.symbol)
    assert round(q.ask - q.bid, 2) == 0.20 and t.stop_price == q.bid
    scn.send(t)


def test_1320_to_1330_two_entries_on_the_recorded_market(make):
    scn = make(recorded(from_s=300, to_s=900), waive=H2)  # 13:20:00–13:30:00 CT
    scn.run(240)                                         # 13:24
    t = scn.ticket("call")                               # the default: highest delta ≤ 0.80
    assert t.ready and not t.error, t.error
    scn.send(t)
    scn.run(180, until=lambda s: not s.held())
    scn.wait_until(scn.elapsed + 3)
    if scn.held():
        scn.flatten()
    put = scn.ticket("put", stopoff=0.30)
    scn.send(put)
    scn.run(scn.tape.length_s - scn.elapsed - 3)
    if scn.held():
        scn.flatten()
    assert len({c["intent_id"] for c in scn.closes()}) == 2
    assert scn.held() == {} and scn.working() == []


@pytest.mark.scenario_wide
def test_the_whole_half_hour_an_entry_every_three_minutes(make):
    scn = make(recorded(), waive=H2)
    styles = [dict(), dict(stopoff=0.30), dict(delta=0.5, stopoff=0.50),
              dict(delta=0.6, exitspx=None)]
    n = 0
    while scn.elapsed + 200 < scn.tape.length_s:
        scn.run(180, until=lambda s: False)
        if scn.held():
            scn.flatten()
        side = "call" if n % 2 == 0 else "put"
        sel = dict(styles[n % len(styles)])
        if "exitspx" in sel:
            sel["exitspx"] = round(scn.spx + (-3 if side == "call" else 3))
        scn.send(scn.ticket(side, **sel))
        n += 1
    scn.run(scn.tape.length_s - scn.elapsed - 3)
    scn.flatten()
    assert n >= 9 and scn.held() == {}


def test_1338_through_the_page_on_the_recorded_market(make):
    """The 13:38 ticket again, on the recorded market: the page, the strike
    the form chooses, the stop box stepped to .3, SEND — then the poll."""
    scn = make(recorded(from_s=23 * 60 - 10, to_s=23 * 60 + 300), waive=H2)
    screen = OrderScreen(scn)
    screen.pick("call")
    shown = screen.step_stop(+1)
    answer = screen.send()
    assert answer["ok"] is True, answer.get("bad")
    got = answer["_received"]
    assert got["symbol"] == shown["contract"]["symbol"] and got["stop_price"] == shown["stop_price"]
    sym = shown["contract"]["symbol"]
    entry = scn.position(sym).entry_price
    assert round(entry - scn.resting(sym)["stop"][0], 2) == round(shown["limit"] - shown["stop_price"], 2)
    scn.run(280, until=lambda s: not s.held())
    state = screen.poll()
    assert screen.today(state) == scn.service.status()["pnl"]["day_usd"]
