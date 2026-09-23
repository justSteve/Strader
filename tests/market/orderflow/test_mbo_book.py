"""Book rebuilt from MBO records [co-4owbx]. The rebuild's parity with
Databento's own MBP-1 is measured on real data (module docstring); these pin
the record semantics it relies on."""
from types import SimpleNamespace

from market.orderflow import mbo_book
from market.orderflow.mbo_book import F_LAST, Book, replay

P = 1_000_000_000          # one point in Databento fixed-point
ES = 5000 * P


def rec(action, side, px, size, oid, ts=1, last=True, seq=1):
    return SimpleNamespace(action=action, side=side, price=px, size=size, order_id=oid,
                           instrument_id=7, flags=F_LAST if last else 0, ts_event=ts,
                           sequence=seq)


def test_add_cancel_modify_track_levels_and_best():
    b = Book()
    b.apply("A", "B", ES, 5, 1)
    b.apply("A", "B", ES, 3, 2)
    b.apply("A", "A", ES + P // 4, 4, 3)
    assert b.top() == (ES, ES + P // 4)
    assert b.bid.levels[ES] == [8, 2]
    b.apply("C", "B", ES, 2, 1)              # partial cancel: order 1 still rests with 3
    assert b.bid.levels[ES] == [6, 2]
    b.apply("C", "B", ES, 3, 1)
    assert b.bid.levels[ES] == [3, 1]
    b.apply("M", "B", ES + P // 4 * -1, 3, 2)  # order 2 moves down a tick
    assert ES not in b.bid.levels
    assert b.top() == (ES - P // 4, ES + P // 4)


def test_better_price_replaces_cached_best():
    b = Book()
    b.apply("A", "B", ES, 1, 1)
    assert b.top()[0] == ES
    b.apply("A", "B", ES + P // 4, 1, 2)
    assert b.top()[0] == ES + P // 4
    b.apply("C", "B", ES + P // 4, 1, 2)
    assert b.top()[0] == ES


def test_trade_and_fill_do_not_change_the_book():
    b = Book()
    b.apply("A", "B", ES, 5, 1)
    b.apply("T", "A", ES, 2, 0)
    b.apply("F", "B", ES, 2, 1)
    assert b.bid.levels[ES] == [5, 1]


def test_clear_empties_the_book():
    b = Book()
    b.apply("A", "B", ES, 5, 1)
    b.apply("R", "N", mbo_book.UNDEF_PX, 0, 0)
    assert b.top() == (None, None)
    assert not b.orders


def test_replay_tags_cancels_after_a_fill_as_filled(monkeypatch):
    records = [
        rec("A", "B", ES, 5, 1, ts=1),
        rec("A", "A", ES + P // 4, 5, 2, ts=2),
        # one exchange event: sell aggressor hits order 1 for 2, the fill, then the reduction
        rec("T", "A", ES, 2, 0, ts=3, last=False),
        rec("F", "B", ES, 2, 1, ts=3, last=False),
        rec("C", "B", ES, 2, 1, ts=3, last=True),
        # a separate event: order 1 pulls its remaining 3
        rec("C", "B", ES, 3, 1, ts=4, last=True),
    ]
    monkeypatch.setattr(mbo_book, "iter_mbo_records", lambda path: iter(records))
    out = list(replay(None))
    cancels = [(me.size, me.filled) for me, _, _ in out if me.action == "C"]
    assert cancels == [(2, True), (3, False)]
    trade_ev = [be for me, _, be in out if me.action == "T"][0]
    assert trade_ev.side == "A" and trade_ev.bid_sz == 5     # book as of the trade message
    last_ev = [be for _, _, be in out if be is not None][-1]
    assert last_ev.bid_px is None and last_ev.ask_px == (ES + P // 4) * 1e-9
