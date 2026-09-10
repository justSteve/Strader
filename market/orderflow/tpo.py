"""TPO (Market Profile) construction + reads — time-at-price. [st-3zh]

Builds a ``TPOProfile`` from the canonical trade stream (same input as the
volume sibling ``profile.py``) by bracketing the RTH session into half-hour
letter periods and recording which price rows each period visited.

Reads implemented here, per foundation doc 03:

  POC (time)   — row with the most TPO letters. Tie-break: the row closest
                 to the middle of the profile's price range (Dalton
                 convention), then the LOWER row. NOTE: this deliberately
                 differs from the volume-POC "lower price wins" rule —
                 mid-range proximity is the Market Profile convention and
                 the drill teaches the authentic read.
  Value Area   — ~70% of total TPOs, grown outward from the POC by the
                 standard two-row comparison (add the adjacent pair with
                 the larger TPO sum; upper pair wins ties).
  Initial Balance — high/low of the first two brackets (A + B).
  Single prints — interior rows printed by exactly one letter. Runs that
                 touch the profile's current high/low are TAILS (excess),
                 not single prints, and are excluded.
  Day type     — heuristic v1 classifier (D / P / b / trend) from final
                 shape: IB range extension, POC position, elongation.
                 Deck labels are hand-reviewed; this seeds them.

Deterministic by construction — pure functions of the trade list and the
named constants.

The bottom half of this module (``bracket_index`` onward) covers the ANCHORED
case [st-jz12]: one profile that starts at an explicit moment — the prior
day's RTH open — and runs to *now*, so the prior cash session, the overnight
and today so far form ONE distribution. Same reads, same rules; what changes
is that brackets are counted from the anchor rather than from one session's
open, and they carry the session segment they fall in so a page can colour
them. ``build_tpo`` and its single-session callers (the drill) are untouched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as _date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from market.entities.tpo_profile import TPOBracket, TPOProfile
from market.entities.trade import Trade
from market.signals.orderflow_config import TICK

logger = logging.getLogger(__name__)

CENTRAL = ZoneInfo("America/Chicago")

TPO_ROW_TICKS = 4                 # 4 ticks = 1.0 pt rows — readable ES profile
RTH_START = time(8, 30)           # US/Central cash open (matches CVD_RESET_CT)
RTH_END = time(15, 0)             # cash close
BRACKET_MIN = 30                  # one letter per half hour
LETTERS = "ABCDEFGHIJKLM"         # 13 brackets in a full 8:30–15:00 session
VALUE_AREA_FRACTION = 0.70
IB_BRACKETS = 2                   # Initial Balance = A + B (first hour)


def build_tpo(trades: Iterable[Trade], row_ticks: int = TPO_ROW_TICKS) -> TPOProfile:
    """Bracket one session's RTH trades into a TPO profile.

    Trades outside [RTH_START, RTH_END) US/Central are ignored — the Market
    Profile convention is a cash-session profile. Row floor = floor(price /
    row) × row, contiguous across the traded range (zero-TPO rows included)
    so row indices are stable and adjacency tests are well-defined.
    """
    row = row_ticks * TICK
    per_bracket: dict[int, list[Trade]] = {}
    for t in trades:
        tt = t.ts.time()
        if not (RTH_START <= tt < RTH_END):
            continue
        idx = int((t.ts - t.ts.replace(hour=RTH_START.hour, minute=RTH_START.minute,
                                       second=0, microsecond=0))
                  // timedelta(minutes=BRACKET_MIN))
        if 0 <= idx < len(LETTERS):
            per_bracket.setdefault(idx, []).append(t)
    if not per_bracket:
        raise ValueError("no RTH trades — cannot build a TPO profile")

    all_keys = [int(t.price // row)
                for ts in per_bracket.values() for t in ts]
    lo, hi = min(all_keys), max(all_keys)
    prices = tuple(round(k * row, 2) for k in range(lo, hi + 1))

    brackets = []
    for idx in sorted(per_bracket):
        ts = per_bracket[idx]
        touched = sorted({int(t.price // row) - lo for t in ts})
        brackets.append(TPOBracket(
            letter=LETTERS[idx],
            start_ts=ts[0].ts, end_ts=ts[-1].ts,
            row_indices=tuple(touched),
            close=ts[-1].price,
        ))
    first = min(per_bracket)
    sample = per_bracket[first][0]
    return TPOProfile(
        symbol=sample.symbol,
        session_date=sample.ts.date(),
        row_pts=row,
        prices=prices,
        brackets=tuple(brackets),
    )


# ── reads ────────────────────────────────────────────────────────────────────

def poc_row(profile: TPOProfile, upto: int | None = None) -> int:
    """Time-POC row index. Longest row; ties resolved toward the middle of
    the (developing) range, then the lower row — see module docstring."""
    counts = profile.counts(upto)
    printed = [i for i, c in enumerate(counts) if c > 0]
    mid = (printed[0] + printed[-1]) / 2
    best = max(counts)
    cands = [i for i, c in enumerate(counts) if c == best]
    return min(cands, key=lambda i: (abs(i - mid), i))


def value_area(profile: TPOProfile, upto: int | None = None) -> tuple[int, int]:
    """(val_row, vah_row) — the standard 70% expansion from the POC.

    Compare the two rows above the accepted band with the two rows below;
    add the pair with more TPOs (upper pair wins ties); repeat until the
    band holds ≥ VALUE_AREA_FRACTION of total TPOs.
    """
    counts = profile.counts(upto)
    total = sum(counts)
    target = total * VALUE_AREA_FRACTION
    lo = hi = poc_row(profile, upto)
    acc = counts[lo]
    n = len(counts)
    while acc < target:
        up = sum(counts[hi + 1:hi + 3])
        dn = sum(counts[max(0, lo - 2):lo])
        can_up, can_dn = hi + 1 < n, lo > 0
        if can_up and (up >= dn or not can_dn):
            take = min(2, n - 1 - hi)
            acc += sum(counts[hi + 1:hi + 1 + take])
            hi += take
        elif can_dn:
            take = min(2, lo)
            acc += sum(counts[lo - take:lo])
            lo -= take
        else:                                    # profile exhausted
            break
    # trim zero-TPO edge rows so VA bounds are printed prices
    while counts[lo] == 0 and lo < hi:
        lo += 1
    while counts[hi] == 0 and hi > lo:
        hi -= 1
    return lo, hi


def single_print_rows(profile: TPOProfile, upto: int | None = None) -> list[int]:
    """Interior single-print rows: count == 1 and the contiguous single run
    does NOT touch the (developing) profile high or low — those are tails."""
    counts = profile.counts(upto)
    printed = [i for i, c in enumerate(counts) if c > 0]
    lo, hi = printed[0], printed[-1]
    out: list[int] = []
    i = lo
    while i <= hi:
        if counts[i] == 1:
            j = i
            while j + 1 <= hi and counts[j + 1] == 1:
                j += 1
            if i != lo and j != hi:              # interior run only
                out.extend(range(i, j + 1))
            i = j + 1
        else:
            i += 1
    return out


def initial_balance(profile: TPOProfile,
                    upto: int | None = None) -> tuple[float, float] | None:
    """(ib_low, ib_high) row-floor prices from brackets A+B; None until the
    session has both. Row floors, consistent with every other read here.

    ``upto`` restricts to brackets[:upto] (the developing state) so a
    mid-flight caller never sees an IB before both A and B have printed.
    A and B occupy the first two positions whenever they exist at all, so
    for ``upto >= 2`` this matches the full-session read; for a session
    whose tape starts after 09:30 (no A/B brackets) it stays None.
    """
    ib = [b for b in profile.brackets[:upto] if b.letter in LETTERS[:IB_BRACKETS]]
    if len(ib) < IB_BRACKETS:
        return None
    idxs = [i for b in ib for i in b.row_indices]
    return profile.prices[min(idxs)], profile.prices[max(idxs)]


def developing_upto(profile: TPOProfile, ts) -> int:
    """Positional ``upto`` for the developing reads at wall-clock ``ts``.

    Counts the profile brackets whose half-hour period ENDS strictly before
    the bracket containing ``ts`` — the bracket in progress is excluded,
    because the profile is built from the full day's tape and including it
    would leak up to 30 minutes of future trades into a "live" read.

    Maps time to position via bracket letters, so a late-start tape (first
    trade 13:00 → letters J..M) yields the count of its own completed
    brackets, not the wall-clock bracket number.
    """
    open_ts = ts.replace(hour=RTH_START.hour, minute=RTH_START.minute,
                         second=0, microsecond=0)
    idx = int((ts - open_ts) // timedelta(minutes=BRACKET_MIN))
    idx = max(0, min(idx, len(LETTERS)))
    return sum(1 for b in profile.brackets if LETTERS.index(b.letter) < idx)


def classify_day_type(profile: TPOProfile,
                      upto: int | None = None) -> tuple[str, str]:
    """Heuristic v1 day-type call: ('D'|'P'|'b'|'trend', one-line why).

    Seeds deck labels — hand-review before a day enters the drill deck.

    ``upto=None`` (default) is the full-session, lookahead read — unchanged
    behavior for all existing callers. ``upto=k`` is the DEVELOPING call
    after the k-th bracket (positional, matching ``TPOProfile.counts``):
    counts, POC, range, and close all come from brackets[:k] only, so the
    call is valid mid-session. Returns ("unknown", "IB incomplete") while
    fewer than IB_BRACKETS brackets have completed [st-98z].
    """
    if upto is not None:
        upto = min(upto, len(profile.brackets))
        if upto < IB_BRACKETS:
            return "unknown", "IB incomplete"
    counts = profile.counts(upto)
    printed = [i for i, c in enumerate(counts) if c > 0]
    lo, hi = printed[0], printed[-1]
    rng = hi - lo + 1
    poc = poc_row(profile, upto)
    poc_pos = (poc - lo) / max(1, rng - 1)       # 0 = at low, 1 = at high
    last_bracket = profile.brackets[-1 if upto is None else upto - 1]
    close_row = int(last_bracket.close // profile.row_pts
                    ) - int(profile.prices[0] // profile.row_pts)
    close_pos = (close_row - lo) / max(1, rng - 1)
    ib = initial_balance(profile, upto)
    if ib:
        ib_rows = max(1, round((ib[1] - ib[0]) / profile.row_pts) + 1)
        ext = rng / ib_rows
    else:
        ext = 1.0
    n_letters = len(profile.brackets) if upto is None else upto
    max_frac = max(counts) / max(1, n_letters)

    if ext >= 2.0 and max_frac <= 0.45 and (close_pos >= 0.75 or close_pos <= 0.25):
        return "trend", (f"range {ext:.1f}× the IB, thin profile "
                         f"(longest row {max(counts)} of {n_letters} letters), "
                         f"close pinned at the {'high' if close_pos >= 0.75 else 'low'}")
    if poc_pos >= 0.62:
        return "P", (f"bulge sits in the upper range (POC at {poc_pos:.0%} of range) "
                     "over a thin lower stem — one-sided push up, then acceptance on top")
    if poc_pos <= 0.38:
        return "b", (f"bulge sits in the lower range (POC at {poc_pos:.0%} of range) "
                     "under a thin upper stem — one-sided push down, then acceptance below")
    return "D", (f"balanced two-sided rotation — POC mid-range ({poc_pos:.0%}), "
                 f"range only {ext:.1f}× the IB")


# ── anchored, multi-session profiles [st-jz12] ───────────────────────────────
#
# Everything above builds ONE cash session, letters A..M from 08:30 CT. The
# anchored form spans a window that starts at a named moment (the prior day's
# RTH open) and runs to now, so it crosses the cash close, the overnight and
# today's open. Three things change and nothing else:
#
#   * brackets are indexed from the ANCHOR, not from a session open;
#   * each bracket carries the SEGMENT it falls in (cash session vs overnight),
#     so the page can colour the three stretches apart;
#   * letters restart at every segment boundary, so a cash session still reads
#     A, B, C … exactly as the drill teaches, and the overnight reads in its
#     own lower-case run.
#
# The reads themselves — poc_row, value_area, single_print_rows — are the ones
# above, unchanged: they take a TPOProfile and know nothing about anchors.

#: Cash-session brackets. 13 half hours fit inside 08:30–15:00, so a normal
#: RTH segment never leaves A..M and matches ``LETTERS`` exactly.
RTH_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
#: Overnight brackets. Lower case so the eye separates them from a cash
#: session at a glance, extended with digits to 36 symbols: a weeknight
#: (15:00 CT → 08:30 CT = 35 half hours) fits without repeating. A weekend
#: window repeats the run; the bracket's exact clock time is in its tooltip.
GLOBEX_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"

SEG_RTH = "rth"
SEG_GLOBEX = "globex"

ROLE_PRIOR_RTH = "prior_rth"
ROLE_OVERNIGHT = "overnight"
ROLE_TODAY_RTH = "today_rth"

#: A silence at least this long between consecutive prints is a hole in the
#: TAPE, not a quiet market — ES prints many times a minute whenever Globex is
#: open. Same threshold and same meaning as ``anchored_profile.HOLE_MIN_S``.
HOLE_MIN_S = 30 * 60

#: CME's daily maintenance halt, US/Central. A silence that sits inside it is
#: the exchange being shut, not a capture that died, and the page says so.
HALT_START = time(16, 0)
HALT_END = time(17, 0)


def bracket_index(ts: datetime, anchor: datetime,
                  bracket_min: int = BRACKET_MIN) -> int:
    """Which bracket ``ts`` falls in, counted from ``anchor`` (0-based).

    Elapsed time, not wall clock: monotonic by construction and immune to a
    tape that skips days. Both arguments must be timezone-aware. Because the
    anchor is a cash open (08:30 CT) and ``bracket_min`` divides 30, bracket
    edges land on :00 / :30 CT — except across a DST change, where a bracket
    edge shifts by the hour the clocks moved.
    """
    return (ts - anchor) // timedelta(minutes=bracket_min)


def bracket_start(anchor: datetime, index: int,
                  bracket_min: int = BRACKET_MIN) -> datetime:
    """Wall-clock start of bracket ``index``, in the anchor's zone."""
    return anchor + timedelta(minutes=bracket_min * index)


def segment_kind(start_ct: datetime) -> str:
    """``SEG_RTH`` if the bracket opens inside a weekday cash session.

    Judged on the bracket's START, so a bracket that straddles the bell (only
    possible when ``bracket_min`` does not divide 30) belongs to the session it
    opened in. Holidays are not modelled: a holiday's "RTH" brackets simply
    hold no trades and drop out of the profile.
    """
    if start_ct.weekday() >= 5:                       # Sat / Sun
        return SEG_GLOBEX
    return SEG_RTH if RTH_START <= start_ct.time() < RTH_END else SEG_GLOBEX


@dataclass(frozen=True)
class TPOSegment:
    """One unbroken run of same-kind brackets inside an anchored window.

    ``role`` is what the page colours by: the newest cash session is
    ``today_rth`` when it is the current CT date, every earlier cash session is
    ``prior_rth``, and everything between them is ``overnight``.
    """
    kind: str                        # SEG_RTH | SEG_GLOBEX
    role: str                        # ROLE_* — the page's colour key
    day: _date                       # CT date the segment opens on
    start_ct: datetime               # first bracket edge in the segment
    end_ct: datetime                 # one past the last bracket edge
    first_index: int                 # bracket index (from the anchor) of start_ct
    indices: tuple[int, ...]         # bracket indices that actually printed
    letters: tuple[str, ...]         # label per entry of ``indices``

    @property
    def label(self) -> str:
        """"A–M" — the letter run a reader sees for this segment."""
        if not self.letters:
            return ""
        if len(self.letters) == 1:
            return self.letters[0]
        return f"{self.letters[0]}–{self.letters[-1]}"


def plan_segments(anchor_ct: datetime, end_ct: datetime,
                  bracket_min: int = BRACKET_MIN) -> list[tuple]:
    """Split ``[anchor, end]`` into (kind, role, day, first_index, last_index).

    Pure function of the clock — it does not look at the tape, so a segment
    with no prints (a holiday, a weekend) is planned and then dropped by
    ``build_anchored_tpo`` when nothing printed in it. ``last_index`` is
    inclusive.
    """
    if end_ct < anchor_ct:
        raise ValueError("end precedes the anchor")
    last = bracket_index(end_ct, anchor_ct, bracket_min)
    runs: list[list] = []
    for idx in range(last + 1):
        start = bracket_start(anchor_ct, idx, bracket_min).astimezone(CENTRAL)
        kind = segment_kind(start)
        day = start.date()
        if runs and runs[-1][0] == kind and runs[-1][2] == day:
            runs[-1][4] = idx
        elif runs and runs[-1][0] == kind == SEG_GLOBEX:
            # An overnight crosses midnight (and a weekend): keep it one run
            # rather than one per calendar date.
            runs[-1][4] = idx
        else:
            runs.append([kind, None, day, idx, idx])
    today = end_ct.astimezone(CENTRAL).date()
    last_rth = max((i for i, r in enumerate(runs) if r[0] == SEG_RTH), default=None)
    for i, r in enumerate(runs):
        if r[0] == SEG_GLOBEX:
            r[1] = ROLE_OVERNIGHT
        elif i == last_rth and r[2] == today:
            r[1] = ROLE_TODAY_RTH
        else:
            r[1] = ROLE_PRIOR_RTH
    return [tuple(r) for r in runs]


@dataclass(frozen=True)
class AnchoredTPO:
    """An anchored TPO profile plus everything the page stamps around it."""
    profile: TPOProfile
    anchor_ct: datetime
    end_ct: datetime                 # last print in the window
    bracket_min: int
    segments: tuple[TPOSegment, ...]
    n_trades: int
    last_price: float
    holes: tuple[tuple[datetime, datetime], ...]

    def segment_of(self, index: int) -> TPOSegment | None:
        """The segment a bracket belongs to, keyed by its anchor-relative
        INDEX — never by its letter. Letters restart per segment, so an
        anchored window that holds two cash sessions holds two brackets
        labelled "A", and a letter lookup would silently pick one of them."""
        for seg in self.segments:
            if seg.indices and seg.indices[0] <= index <= seg.indices[-1]:
                return seg
        return None

    def roles(self) -> dict[int, str]:
        """Bracket index → segment role, for a renderer colouring cells."""
        return {i: seg.role for seg in self.segments for i in seg.indices}

    @property
    def widest_hole(self) -> tuple[datetime, datetime] | None:
        if not self.holes:
            return None
        return max(self.holes, key=lambda h: h[1] - h[0])


def segment_initial_balance(anchored: AnchoredTPO,
                            seg: TPOSegment) -> tuple[float, float] | None:
    """(ib_low, ib_high) for one cash session inside the window.

    Initial Balance is the first ``IB_BRACKETS`` half hours of a CASH session —
    the same definition ``initial_balance`` uses for a single-session profile,
    read per RTH segment because an anchored window holds more than one. The
    brackets must be the segment's FIRST two by clock position (indices
    ``first_index`` and ``first_index + 1``), so a session whose tape starts
    late has no IB rather than a misplaced one. ``None`` for an overnight
    segment or an incomplete first hour.
    """
    if seg.kind != SEG_RTH:
        return None
    want = {seg.first_index + k for k in range(IB_BRACKETS)}
    rows = [i for b in anchored.profile.brackets
            if b.index in want for i in b.row_indices]
    got = {b.index for b in anchored.profile.brackets if b.index in want}
    if len(got) < IB_BRACKETS or not rows:
        return None
    prices = anchored.profile.prices
    return prices[min(rows)], prices[max(rows)]


def counts_by_role(anchored: AnchoredTPO) -> dict[str, tuple[int, ...]]:
    """Per-row TPO counts split by segment role — the page's colour weights.

    Sums to ``profile.counts()`` row by row, because every bracket carries
    exactly one role.
    """
    role_of = anchored.roles()
    n = len(anchored.profile.prices)
    out = {ROLE_PRIOR_RTH: [0] * n, ROLE_OVERNIGHT: [0] * n, ROLE_TODAY_RTH: [0] * n}
    for b in anchored.profile.brackets:
        row = out[role_of[b.index]]
        for i in b.row_indices:
            row[i] += 1
    return {k: tuple(v) for k, v in out.items()}


class AnchoredTPOAccumulator:
    """Streaming builder for an anchored TPO profile.

    One pass over the trade stream, mirroring ``SplitAccumulator`` in
    ``anchored_profile.py``: the caller hands it prints in time order and it
    keeps only what a profile needs — which price rows each bracket touched,
    the bracket's first and last print, and the gaps in the tape. Streaming
    because the window is two corpus days (650k+ ES prints on a normal
    Wednesday-to-Thursday); materialising them all would cost more memory than
    the profile is worth.

    Trades before the anchor are dropped; trades at or after ``end`` (when one
    is given) are dropped too, so a caller can build a window that ends in the
    past without slicing the stream itself.
    """

    __slots__ = ("anchor", "end", "row", "bracket_min", "_bracket_td", "_hole_td",
                 "_meta", "_lo", "_hi", "n", "symbol", "first_ts", "last_ts",
                 "last_price", "holes")

    def __init__(self, anchor_ct: datetime, *, row_ticks: int = TPO_ROW_TICKS,
                 bracket_min: int = BRACKET_MIN,
                 end_ct: datetime | None = None) -> None:
        if anchor_ct.tzinfo is None:
            raise ValueError("anchor must be timezone-aware")
        if row_ticks < 1:
            raise ValueError("row_ticks must be >= 1")
        if bracket_min < 1:
            raise ValueError("bracket_min must be >= 1")
        self.anchor = anchor_ct
        self.end = end_ct
        self.row = row_ticks * TICK
        self.bracket_min = bracket_min
        self._bracket_td = timedelta(minutes=bracket_min)
        self._hole_td = timedelta(seconds=HOLE_MIN_S)
        # idx -> [first_ts, last_ts, close, {row keys}]
        self._meta: dict[int, list] = {}
        self._lo: int | None = None
        self._hi: int | None = None
        self.n = 0
        self.symbol: str | None = None
        self.first_ts: datetime | None = None
        self.last_ts: datetime | None = None
        self.last_price: float | None = None
        self.holes: list[tuple[datetime, datetime]] = []

    def add(self, t: Trade) -> None:
        ts = t.ts
        if ts < self.anchor or (self.end is not None and ts >= self.end):
            return
        idx = (ts - self.anchor) // self._bracket_td
        key = int(t.price // self.row)
        m = self._meta.get(idx)
        if m is None:
            self._meta[idx] = [ts, ts, t.price, {key}]
        else:
            m[1] = ts
            m[2] = t.price
            m[3].add(key)
        if self._lo is None or key < self._lo:
            self._lo = key
        if self._hi is None or key > self._hi:
            self._hi = key
        if self.n:
            if ts - self.last_ts >= self._hole_td:
                self.holes.append((self.last_ts, ts))
        else:
            self.symbol, self.first_ts = t.symbol, ts
        self.last_ts, self.last_price = ts, t.price
        self.n += 1

    def extend(self, trades: Iterable[Trade]) -> None:
        """Consume a whole stream — the batch path, identical arithmetic.

        Every attribute ``add`` touches is hoisted into a local first. At one
        print per call that is noise; at the 670k prints of a live two-session
        window (measured 2026-09-10) the attribute traffic alone is about a
        fifth of the build, and this page is on a four-second budget.
        ``test_extend_matches_add`` pins the two paths together.
        """
        anchor, end, row = self.anchor, self.end, self.row
        bracket_td, hole_td = self._bracket_td, self._hole_td
        meta, holes = self._meta, self.holes
        lo, hi, n = self._lo, self._hi, self.n
        last_ts, last_price, symbol = self.last_ts, self.last_price, self.symbol
        first_ts = self.first_ts
        for t in trades:
            ts = t.ts
            if ts < anchor or (end is not None and ts >= end):
                continue
            price = t.price
            key = int(price // row)
            idx = (ts - anchor) // bracket_td
            m = meta.get(idx)
            if m is None:
                meta[idx] = [ts, ts, price, {key}]
            else:
                m[1] = ts
                m[2] = price
                m[3].add(key)
            if n:                       # lo/hi and last_ts are live from here
                if key < lo:
                    lo = key
                elif key > hi:
                    hi = key
                if ts - last_ts >= hole_td:
                    holes.append((last_ts, ts))
            else:
                lo = hi = key
                symbol, first_ts = t.symbol, ts
            last_ts, last_price = ts, price
            n += 1
        self._lo, self._hi, self.n = lo, hi, n
        self.last_ts, self.last_price, self.symbol = last_ts, last_price, symbol
        self.first_ts = first_ts

    def build(self) -> AnchoredTPO:
        """Materialise the profile, its segments and its letters."""
        if not self.n:
            raise ValueError("no trades inside the anchored window — "
                             "cannot build a TPO profile")
        lo, hi = self._lo, self._hi
        prices = tuple(round(k * self.row, 4) for k in range(lo, hi + 1))
        plan = plan_segments(self.anchor, self.last_ts, self.bracket_min)

        printed = sorted(self._meta)
        segments: list[TPOSegment] = []
        letter_of: dict[int, str] = {}
        seg_of: dict[int, str] = {}
        for kind, role, day, first_i, last_i in plan:
            alphabet = RTH_ALPHABET if kind == SEG_RTH else GLOBEX_ALPHABET
            idxs = [i for i in printed if first_i <= i <= last_i]
            if not idxs:
                continue                       # holiday, weekend, tape hole
            letters = tuple(alphabet[(i - first_i) % len(alphabet)] for i in idxs)
            for i, ch in zip(idxs, letters):
                letter_of[i], seg_of[i] = ch, kind
            segments.append(TPOSegment(
                kind=kind, role=role, day=day,
                start_ct=bracket_start(self.anchor, first_i,
                                       self.bracket_min).astimezone(CENTRAL),
                end_ct=bracket_start(self.anchor, last_i + 1,
                                     self.bracket_min).astimezone(CENTRAL),
                first_index=first_i, indices=tuple(idxs), letters=letters))

        brackets = []
        for i in printed:
            first_ts, last_ts, close, keys = self._meta[i]
            brackets.append(TPOBracket(
                letter=letter_of[i], start_ts=first_ts, end_ts=last_ts,
                row_indices=tuple(sorted(k - lo for k in keys)),
                close=close, segment=seg_of[i], index=i))

        profile = TPOProfile(
            symbol=self.symbol or "", session_date=self.anchor.date(),
            row_pts=self.row, prices=prices, brackets=tuple(brackets))
        return AnchoredTPO(
            profile=profile, anchor_ct=self.anchor, end_ct=self.last_ts,
            bracket_min=self.bracket_min, segments=tuple(segments),
            n_trades=self.n, last_price=self.last_price,
            holes=tuple(self.holes))


def build_anchored_tpo(trades: Iterable[Trade], anchor_ct: datetime, *,
                       row_ticks: int = TPO_ROW_TICKS,
                       bracket_min: int = BRACKET_MIN,
                       end_ct: datetime | None = None) -> AnchoredTPO:
    """Batch form of ``AnchoredTPOAccumulator`` — one profile from one stream.

    The batch and streaming paths share the one accumulator, the same way
    ``build_split_profile`` and ``SplitAccumulator`` do, so a live caller and a
    replay caller cannot drift apart.
    """
    acc = AnchoredTPOAccumulator(anchor_ct, row_ticks=row_ticks,
                                 bracket_min=bracket_min, end_ct=end_ct)
    acc.extend(trades)
    return acc.build()
