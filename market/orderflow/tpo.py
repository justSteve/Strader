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
"""
from __future__ import annotations

import logging
from datetime import date as _date, time, timedelta
from typing import Iterable

from market.entities.tpo_profile import TPOBracket, TPOProfile
from market.entities.trade import Trade
from market.signals.orderflow_config import TICK

logger = logging.getLogger(__name__)

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
