"""The four bugs that reached the paper account on 2026-09-30, as scenarios. [st-ug1h]

Each would have failed before its fix and passes now (verified by running
this file against the parent of each fix commit — the README says how):

1. **st-0f5q, bracket_fired (5ad0386).** The stop sent WITH the entry
   filled within a second of the entry, before the service first read the
   bracket. Read as a bracket that failed to rest, a second one went on,
   the close was booked ``external``, and at 13:24 the second stop filled
   too: the paper account went short one.
2. **st-0f5q, _stop_follows_fill (5ad0386).** The stop is struck under the
   LIMIT; a fill better than the limit left it nearer the fill than the
   ticket said.
3. **st-7p5u, "twenty means twenty" (87ced9c).** The stop box read .3; the
   SPX level struck at pricing was walked again at the send's mark and
   rounded up the grid — 11.60 rested, 0.20 under the 11.80 limit.
4. **13e43dd, the day's total.** After a close the closed cards repainted
   and the 'today' line under them kept the old total until a reload.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from .screen import OrderScreen
from .tape import CT, Frame, occ, scripted

T1324 = datetime(2026, 9, 30, 13, 23, 50, tzinfo=CT).astimezone(timezone.utc)
T1338 = datetime(2026, 9, 30, 13, 37, 50, tzinfo=CT).astimezone(timezone.utc)
DAY = T1324.astimezone(CT).date()
C7690 = occ(DAY, "C", 7690)
C7720 = occ(DAY, "C", 7720)
C7685 = occ(DAY, "C", 7685)


def frames(sym, delta, spx0, *rows):
    """``(t, bid, ask)`` rows for ``sym``, the index moving with it."""
    mid0 = (rows[0][1] + rows[0][2]) / 2
    return [Frame(t, round(spx0 + ((b + a) / 2 - mid0) / delta, 2),
                  quotes={sym: (b, a)}, deltas={sym: delta}) for t, b, a in rows]


class TestSeed1TheBracketFiredFirst:
    def test_1324_the_stop_that_would_fire_first_is_refused_at_the_ticket(self, make):
        """13:24 CT: the 9.20 limit (locked) went out into a 8.70/8.80
        market, filled 8.80 under its 9.00 stop, and the stop fired on the
        first read. Since H1 (st-n3e8) that stop is struck from the 8.80 ask
        and rests under the bid. The other way to the race — a market wider
        than the stop's distance at the limit, 8.70/9.20, the 9.00 stop over
        the bid — is refused at the ticket since 2026-10-01 (st-yeph: "in
        those conditions it should refuse"), so nothing is sent. The race
        itself, a stop that fills before the bracket is first read, is still
        reached by a gap between two passes (the next test)."""
        tape = scripted(frames(C7690, 0.60, 7696.0, (0, 9.10, 9.20), (2, 8.70, 9.20),
                               (60, 8.70, 9.20)), start=T1324)
        scn = make(tape)
        scn.wait_until(2)
        t = scn.ticket("call", strike=7690, limit=9.20)
        assert t.stop_price == 9.00 and "at or above the 8.70 bid" in t.error
        with pytest.raises(ValueError, match="widen the stop"):
            scn.intent(t)
        scn.run(30)
        assert scn.events("sending") == [] and scn.closes() == []
        assert scn.held() == {} and scn.working() == []

    def test_a_gap_through_entry_and_stop_between_two_passes(self, make):
        """The same race from a resting entry: the market gaps through the
        limit and the stop between two watcher passes."""
        tape = scripted(frames(C7690, 0.60, 7696.0, (0, 9.20, 9.30), (2, 8.50, 8.60),
                               (60, 8.50, 8.60)), start=T1324)
        scn = make(tape)
        scn.send(scn.ticket("call", strike=7690, limit=9.20))
        scn.run(30)
        close, = scn.closes()
        assert close["kind"] == "protective-stop" and close["exit_price"] == 8.50
        assert scn.held() == {} and scn.working() == []


class TestSeed2TheStopFollowsTheFill:
    def test_a_fill_under_the_limit_keeps_the_tickets_dollars(self, make):
        """A 2.10 limit (locked) into a 1.95/2.00 market fills at 2.00; the
        1.90 stop it carried moves to 1.80 — $20 from the fill."""
        tape = scripted(frames(C7720, 0.30, 7696.0, (0, 1.95, 2.00), (60, 1.95, 2.00)),
                        start=T1324)
        scn = make(tape)
        t = scn.ticket("call", strike=7720, limit=2.10)
        assert t.stop_price == 1.90
        scn.send(t)
        assert scn.position(C7720).entry_price == 2.00
        assert scn.resting(C7720)["stop"] == [1.80]
        scn.run(30)


class TestSeed3TwentyMeansTwenty:
    def test_1338_the_stop_box_reads_point_three_and_point_three_rests(self, make):
        """13:38 CT: the page priced the ticket from the chain (SPX 7693.71)
        and the service sent on the $SPX quote (7693.68). The stop box said
        .3 under an 11.80 limit; 11.50 must rest — not 11.60."""
        tape = scripted([Frame(0, 7693.68, chain_spx=7693.71,
                               quotes={C7685: (11.70, 11.80)}, deltas={C7685: 0.70}),
                         Frame(60, 7693.68, chain_spx=7693.71,
                               quotes={C7685: (11.70, 11.80)}, deltas={C7685: 0.70})],
                        start=T1338)
        scn = make(tape)
        screen = OrderScreen(scn)
        screen.pick("call")
        screen.tap(7685)
        shown = screen.step_stop(+1)                     # the .2 default, one tap: .3
        assert (shown["limit"], shown["stop_price"]) == (11.80, 11.50)
        answer = screen.send()
        assert answer["ok"] is True, answer.get("bad")
        assert scn.resting(C7685)["stop"] == [11.50]


class TestSeed4TheDaysTotal:
    def test_the_poll_repaints_today_with_the_closed_cards(self, make):
        tape = scripted(frames(C7690, 0.60, 7696.0, (0, 9.10, 9.20), (6, 8.80, 8.90),
                               (60, 8.80, 8.90)), start=T1324)
        scn = make(tape)
        screen = OrderScreen(scn)
        screen.pick("call")
        screen.tap(7690)
        screen.send()
        before = screen.poll()
        scn.run(12, until=lambda s: not s.held())
        after = screen.poll()
        close, = scn.closes()
        assert screen.closed_cards(after) == [close["net_pnl_usd"]]
        assert screen.today(after) == close["net_pnl_usd"] != screen.today(before)
