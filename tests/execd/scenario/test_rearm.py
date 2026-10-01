"""The offer, the default stop and the re-arm after a stop-out. [st-d7nt]

Steve, 2026-10-01: the entry offers "Mid + $5 hoping for better / quicker
fills", never above the ask; "update my default SL to .3"; and after a stop
fill the form is re-armed — same side and strike, pinned, the limit at the
plain mid, the default stop — prepopulated only, SEND stays his tap.
"""

from __future__ import annotations

import re

from execd.bounds import Bounds
from execd.orderform import Selection, limit_at, mid_at, price

from .screen import OrderScreen
from .tape import ramp


def test_the_offer_is_mid_plus_a_nickel_capped_at_the_ask():
    assert limit_at(2.00, 2.40) == 2.25            # mid 2.20 + 0.05
    assert limit_at(8.70, 9.20) == 9.00            # 8.95 + 0.05, the 0.10 grid above $3
    assert limit_at(2.00, 2.10) == 2.10            # 2.10 is the ask: mid + 0.05 == ask
    assert limit_at(9.10, 9.20) == 9.20            # 9.20 rounds up to 9.20, never past it
    assert limit_at(2.00, 2.05) == 2.05            # mid + 0.05 = 2.075 > the ask: the ask
    assert limit_at(0.0, 0.40) == 0.40             # no bid, no mid: the ask
    assert mid_at(8.70, 9.20) == 9.00 and mid_at(2.00, 2.40) == 2.20


def test_the_ticket_offers_under_the_ask_in_a_wide_market_and_stops_30_under(make):
    scn = make(ramp((0, 6380), (60, 6380), spread=0.40))
    t = scn.ticket("call", delta=0.5)
    c = t.contract
    assert t.limit == limit_at(c.bid_pts, c.ask_pts) < c.ask_pts
    assert round(t.limit - t.stop_price, 2) == 0.30 and t.stop_loss_usd == 30.0
    two = scn.ticket("call", delta=0.5, lots=2)
    assert round(two.limit - two.stop_price, 2) == 0.30 and two.stop_loss_usd == 60.0
    locked = scn.ticket("call", strike=c.strike, limit=c.ask_pts)   # his price wins
    assert locked.limit == c.ask_pts


def rearm_of(state):
    return state.get("rearm")


def test_a_stop_fill_re_arms_the_form_and_never_sends(make):
    scn = make(ramp((0, 6380), (15, 6380), (75, 6372), (150, 6372)))
    screen = OrderScreen(scn)
    screen.pick("call", delta=0.5)
    screen.lots(2)
    answer = screen.send()
    assert answer["ok"], answer.get("bad")
    sym = answer["_received"]["symbol"]
    strike = float(answer["_received"]["symbol"][-8:]) / 1000
    assert rearm_of(screen.poll()) is None
    scn.run(120, until=lambda s: not s.held())
    close, = scn.closes()
    assert close["kind"] in ("protective-stop", "spx-stop") and close["exit_price"] > 0
    sends = len(scn.events("sending"))
    state = screen.poll()
    r = rearm_of(state)
    assert r and "atmid=1" in r["url"] and f"strike={strike:g}" in r["url"]
    assert "side=call" in r["url"] and "lots=2" in r["url"] and "stopoff=0.30" in r["url"]
    # the traffic pane says it, inside the SEND's block
    lines = re.findall(r"<div class='tl [a-z-]+'>([^<]*)</div>", state["traffic_html"])
    assert sum(ln.startswith("── ") for ln in lines) == 1
    assert re.search(rf"← STOP FILLED 2 @ {close['exit_price']:.2f} — form re-armed: CALL "
                     rf"{strike:g} @ mid", lines[-1].replace("&amp;", "&")), lines[-1]
    # the page loads the prepopulated ticket: same strike, pinned, at the mid
    page = screen.client.get(r["url"]).get_data(as_text=True)
    assert "class='pin manual' id=strikepin" in page and f"value='{strike:g}'" in page
    q = scn.quote(sym)
    sel = Selection.from_args({k: v for k, v in (p.split("=") for p in r["url"].split("?")[1].split("&"))},
                              today=scn.clock().date(), lots_cap=99)
    ticket = price(scn.service, sel)
    assert ticket.limit == mid_at(q.bid, q.ask) and round(ticket.limit - ticket.stop_price, 2) == 0.30
    # nothing was sent for him
    scn.run(30)
    assert len(scn.events("sending")) == sends and scn.held() == {}
    # a new strike drops the mid: the offer is mid + 0.05 again
    moved = Selection.from_args({"side": "call", "strike": f"{strike + 5:g}",
                                 "expiry": sel.expiry.isoformat()}, today=scn.clock().date())
    t2 = price(scn.service, moved)
    assert not moved.atmid and t2.limit == limit_at(t2.contract.bid_pts, t2.contract.ask_pts)
    href = re.search(r"href='([^']*strike=[^']*)'", state.get("strikes_html") or page).group(1)
    assert "atmid" not in href


def test_a_target_fill_does_not_re_arm(make):
    scn = make(ramp((0, 6380), (15, 6380), (90, 6400), (120, 6400)),
               bounds=Bounds(take_profit_multiple=1.5, trail_arm_usd=0))
    screen = OrderScreen(scn)
    screen.pick("call", delta=0.5)
    screen.send()
    scn.run(110, until=lambda s: not s.held())
    close, = scn.closes()
    assert close["kind"] in ("target", "take-profit", "spx-target")
    assert rearm_of(screen.poll()) is None and scn.events("form_rearmed") == []


def test_flatten_does_not_re_arm(make):
    scn = make(ramp((0, 6380), (60, 6380)))
    screen = OrderScreen(scn)
    screen.pick("call", delta=0.5)
    screen.send()
    scn.flatten()
    assert rearm_of(screen.poll()) is None and scn.events("form_rearmed") == []


def test_an_oco_cancel_read_as_a_zero_fill_does_not_re_arm(make):
    """st-5n3s: a cancelled OCO sibling can read back FILLED at 0.00. Booked
    as the stop at 0.00, it is not a stop-out."""
    scn = make(ramp((0, 6380), (60, 6380)))
    t = scn.ticket("call", delta=0.5)
    scn.send(t)
    pos = scn.position(t.contract.symbol)
    svc = scn.service
    with svc._lock:
        svc._book_close_inner(pos, order_id="oco-ghost", exit_px=0.0, closed_qty=pos.qty,
                              reason="protective-stop", why="resting-stop")
    assert svc._rearm is None and scn.events("form_rearmed") == []


def test_the_re_arm_is_its_own_sides_only(make):
    scn = make(ramp((0, 6380), (15, 6380), (75, 6372), (150, 6372)))
    scn.send(scn.ticket("call", delta=0.5))
    scn.run(120, until=lambda s: not s.held())
    assert scn.service.status()["rearm"]["mode"] == "paper"
    scn.lock()
    scn.service.set_mode("live")
    assert scn.service.status()["rearm"] is None
    scn.service.set_mode("paper")
    assert scn.service.status()["rearm"] is None        # a switch spends it


# ── the stop from the mark, no preview, the room (st-qbh6) ────────────────

from .tape import CT, Frame, occ, scripted  # noqa: E402
from datetime import datetime, timezone      # noqa: E402

T1432 = datetime(2026, 10, 1, 14, 31, 50, tzinfo=CT).astimezone(timezone.utc)
P7680 = occ(T1432.astimezone(CT).date(), "P", 7680)


def test_the_1432_shape_rests_the_stop_at_mid_less_point_four_not_fill_less(make):
    """14:32 CT 2026-10-01, P7680: filled 7.70 at the ask, a 0.40 stop, the
    best mark after the fill 7.40 — the stop at 7.30 had 0.10 of room and
    went 5 s later. Struck from the mid at the fill it rests at 7.20."""
    tape = scripted([Frame(0, 7690.0, quotes={P7680: (7.50, 7.70)}, deltas={P7680: 0.45}),
                     Frame(5, 7690.2, quotes={P7680: (7.30, 7.50)}, deltas={P7680: 0.45}),
                     Frame(60, 7690.2, quotes={P7680: (7.30, 7.50)}, deltas={P7680: 0.45})],
                    start=T1432)
    scn = make(tape)
    t = scn.ticket("put", strike=7680, limit=7.70, stopoff=0.40)
    assert t.stop_price == 7.30                       # struck under the limit at the send
    out = scn.send(t)
    assert out["order"]["fill_price"] == 7.70
    line, = scn.events("stop_from_mark")
    assert (line["mark_at_fill"], line["stop_was"], line["stop_to"]) == (7.6, 7.3, 7.2)
    assert scn.resting(P7680)["stop"] == [7.20]
    scn.run(9)
    assert scn.held() == {P7680: 1}                   # the 7.40 mark no longer takes it


def test_a_typed_stop_price_stays_as_typed(make):
    tape = scripted([Frame(0, 7690.0, quotes={P7680: (7.50, 7.70)}, deltas={P7680: 0.45}),
                     Frame(60, 7690.0, quotes={P7680: (7.50, 7.70)}, deltas={P7680: 0.45})],
                    start=T1432)
    scn = make(tape)
    scn.send(scn.ticket("put", strike=7680, limit=7.70, stop="7.30"))
    assert scn.events("stop_from_mark") == [] and scn.resting(P7680)["stop"] == [7.30]


def test_no_preview_call_on_send(make):
    scn = make(ramp((0, 6380), (60, 6380)))
    calls = []
    real = scn.paper.live.preview
    scn.paper.live.preview = lambda i: (calls.append(i), real(i))[1]
    scn.send(scn.ticket("call", delta=0.5))
    assert calls == [] and scn.events("preview") == [] and scn.held()
    assert isinstance(scn.events("placed")[0]["latency_ms"], float)


def test_the_room_in_a_wide_and_a_tight_market(make):
    wide = make(ramp((0, 6380), (60, 6380), spread=0.40)).ticket("call", delta=0.5)
    c = wide.contract
    r = wide.room()
    mid = (c.bid_pts + c.ask_pts) / 2
    assert r["room"] == round(mid - r["stop"], 2) and 0.30 <= r["room"] < 0.40
    assert r["room_spx"] == round(r["room"] / c.abs_delta, 2)
    assert r["loss_usd"] == round((r["room"] + 0.20) * 100, 2)          # + half the 0.40 spread
    tight = make(ramp((0, 6380), (60, 6380), spread=0.10)).ticket("call", delta=0.5, lots=2)
    rt = tight.room()
    assert 0.30 <= rt["room"] < 0.40 and rt["loss_usd"] == round((rt["room"] + 0.05) * 200, 2)
