"""Order book rebuilt from Databento MBO, read out as MBP-1 BookEvents. [co-4owbx]

Why: absorption so far sees one level (MBP-1). MBO is every order — adds,
cancels, modifies, fills — so a rebuilt book answers what top-of-book cannot:
whether size leaving a defended price was filled or pulled, whether fills ran
past the size that was showing (hidden or iceberg size), and what stood behind
the level. The same rebuild, read out at top of book, reproduces Databento's
own MBP-1 exactly (2026-07-02, 522,328 RTH trades: best bid, best ask and
both sizes identical at every one), so anything built on it sits on the same
top-of-book stream the trackers were calibrated on.

Databento MBO semantics on GLBX.MDP3, as this module relies on them:
  - Add (A), Cancel (C), Modify (M) and Clear (R) change the book. A Cancel
    carries the size removed; a partial cancel leaves the order resting.
  - Trade (T) and Fill (F) do NOT change the book. A resting order's
    reduction by a fill arrives as its own Cancel or Modify in the same event,
    which is how ``MboEvent.filled`` tells consumed from pulled.
  - Trade side is the aggressor ('B' lifted the ask, 'A' hit the bid) — the
    BookEvent convention. Fill side is the resting order's side.
  - F_LAST (0x80) marks the last record of one exchange event; the book is
    read out there, and on every trade, as MBP-1 is.
  - A request starting at 00:00 UTC opens with a Clear and a synthetic
    snapshot of the whole book; a later start has no snapshot and the book
    would be wrong. scripts/measurement/pull_mbo_depth.py starts at midnight.

Determinism: a pure function of the record stream.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from market.entities.book import BookEvent

CENTRAL = ZoneInfo("America/Chicago")
F_LAST = 0x80
PX = 1e-9                     # Databento fixed-point price scale
UNDEF_PX = 2**63 - 1          # Databento's undefined price


class SideBook:
    """One side: price (fixed-point int) -> [size, order count]."""

    __slots__ = ("levels",)

    def __init__(self) -> None:
        self.levels: dict[int, list[int]] = {}

    def add(self, px: int, sz: int) -> None:
        lv = self.levels.get(px)
        if lv is None:
            self.levels[px] = [sz, 1]
        else:
            lv[0] += sz
            lv[1] += 1

    def remove(self, px: int, sz: int, whole: bool) -> None:
        lv = self.levels.get(px)
        if lv is None:
            return
        lv[0] -= sz
        if whole:
            lv[1] -= 1
        if lv[1] <= 0 or lv[0] <= 0:
            del self.levels[px]


class Book:
    """One instrument's order book. Best prices are cached and recomputed
    only when the cached level vanished or a better price arrived."""

    def __init__(self) -> None:
        self.orders: dict[int, tuple[str, int, int]] = {}   # order_id -> (side, px, size)
        self.bid = SideBook()
        self.ask = SideBook()
        self.best_bid: int | None = None
        self.best_ask: int | None = None
        self._bid_hint: int | None = None
        self._ask_hint: int | None = None
        self._dirty = True

    def _side(self, s: str) -> SideBook:
        return self.bid if s == "B" else self.ask

    def clear(self) -> None:
        self.orders.clear()
        self.bid = SideBook()
        self.ask = SideBook()
        self.best_bid = self.best_ask = None
        self._bid_hint = self._ask_hint = None
        self._dirty = True

    def _hint(self, side: str, px: int) -> None:
        if side == "B":
            if self._bid_hint is None or px > self._bid_hint:
                self._bid_hint = px
        elif self._ask_hint is None or px < self._ask_hint:
            self._ask_hint = px

    def apply(self, action: str, side: str, px: int, sz: int, oid: int) -> tuple[str, int, int] | None:
        """Apply one record. Returns the order as it stood before a Cancel or
        Modify (side, px, size), or None."""
        if action == "A":
            if side not in ("B", "A"):
                return None
            self.orders[oid] = (side, px, sz)
            self._side(side).add(px, sz)
            self._hint(side, px)
        elif action == "C":
            o = self.orders.get(oid)
            if o is None:
                return None
            s, opx, osz = o
            take = min(sz, osz)
            left = osz - take
            self._side(s).remove(opx, take, whole=left <= 0)
            if left <= 0:
                del self.orders[oid]
            else:
                self.orders[oid] = (s, opx, left)
            self._dirty = True
            return o
        elif action == "M":
            o = self.orders.get(oid)
            if o is None:
                if side in ("B", "A"):
                    self.orders[oid] = (side, px, sz)
                    self._side(side).add(px, sz)
                    self._hint(side, px)
                    self._dirty = True
                return None
            s, opx, osz = o
            self._side(s).remove(opx, osz, whole=True)
            self.orders[oid] = (s, px, sz)
            self._side(s).add(px, sz)
            self._hint(s, px)
            self._dirty = True
            return o
        elif action == "R":
            self.clear()
            return None
        else:
            return None
        self._dirty = True
        return None

    def top(self) -> tuple[int | None, int | None]:
        if self._dirty:
            bl, al = self.bid.levels, self.ask.levels
            b, a = self.best_bid, self.best_ask
            if b is None or b not in bl or (self._bid_hint is not None and self._bid_hint > b):
                b = max(bl) if bl else None
            if a is None or a not in al or (self._ask_hint is not None and self._ask_hint < a):
                a = min(al) if al else None
            self.best_bid, self.best_ask = b, a
            self._bid_hint = self._ask_hint = None
            self._dirty = False
        return self.best_bid, self.best_ask

    def size_at(self, side: str, px: int) -> int:
        lv = (self.bid if side == "B" else self.ask).levels.get(px)
        return lv[0] if lv else 0


@dataclass(slots=True)
class MboEvent:
    """One MBO record after it was applied, for depth consumers.

    ``filled`` is True on a Cancel or Modify that follows a Fill of the same
    order inside one exchange event: size consumed by trading, not pulled.
    ``before`` is the order as it stood before a Cancel/Modify."""
    ts_ns: int
    instrument_id: int
    action: str
    side: str
    px: int
    size: int
    order_id: int
    filled: bool
    before: tuple[str, int, int] | None
    last: bool


def iter_mbo_records(path: Path):
    import databento as db

    for rec in db.DBNStore.from_file(path):
        if type(rec).__name__ == "MBOMsg":
            yield rec


def _val(x) -> str:
    return x if isinstance(x, str) else x.value


def replay(path: Path, instrument_id: int | None = None) -> Iterator[tuple[MboEvent, Book, BookEvent | None]]:
    """Replay one MBO file. Yields every applied record as an MboEvent with the
    book after it, and an MBP-1-shaped BookEvent on trades and on the last
    record of each exchange event (None otherwise)."""
    books: dict[int, Book] = {}
    filled_now: set[int] = set()
    for r in iter_mbo_records(path):
        iid = int(r.instrument_id)
        if instrument_id is not None and iid != instrument_id:
            continue
        bk = books.get(iid)
        if bk is None:
            bk = books[iid] = Book()
        action, side = _val(r.action), _val(r.side)
        px, sz, oid = int(r.price), int(r.size), int(r.order_id)
        if action == "F":
            filled_now.add(oid)
        before = bk.apply(action, side, px, sz, oid)
        last = bool(r.flags & F_LAST)
        ns = int(r.ts_event)
        me = MboEvent(ns, iid, action, side, px, sz, oid,
                      filled=action in ("C", "M") and oid in filled_now,
                      before=before, last=last)
        be = None
        if action == "T" or last:
            b, a = bk.top()
            bl = bk.bid.levels.get(b) if b is not None else None
            al = bk.ask.levels.get(a) if a is not None else None
            be = BookEvent(
                ts=datetime.fromtimestamp(ns // 1_000 / 1e6, tz=CENTRAL),
                symbol="", instrument_id=iid,
                action=action if action in ("A", "C", "M", "T", "F", "R") else "N",  # type: ignore[arg-type]
                side=side if side in ("A", "B") else "N",  # type: ignore[arg-type]
                price=px * PX if px != UNDEF_PX else None, size=sz,
                bid_px=b * PX if b is not None else None,
                ask_px=a * PX if a is not None else None,
                bid_sz=bl[0] if bl else 0, ask_sz=al[0] if al else 0,
                bid_ct=bl[1] if bl else 0, ask_ct=al[1] if al else 0,
                sequence=int(r.sequence), ts_ns=ns,
            )
        if last:
            filled_now.clear()
        yield me, bk, be
