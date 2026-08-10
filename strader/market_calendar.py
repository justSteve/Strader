"""US equity-market session calendar — holidays, early closes, collect windows.

Written for the GexBot collector's session gate [st-p3lv], which had none: a bare
`--interval 60` loop wrote 58.4 MB into `data/corpus/2026-08-08/gexbot.jsonl` on
a Saturday, and CurrentStatus.md claimed the feed was RTH-only the whole time.

WHY THIS EXISTS AT ALL, given `market/corpus/paths.py` deliberately declines to
model holidays. That module's docstring is right for *its* job: it answers "which
day's data should already be complete", and there a holiday yields an empty day
the datastream gate flags — an alert, which is the safe failure. This module
answers a different question — "should a paid API be polled right now" — where
the safe failure runs the other way. A holiday we fail to model is a full day of
QUANT-tier request quota spent on a frozen snapshot, silently, with nobody
looking at a gate.

UNKNOWN YEARS DEGRADE TOWARD COLLECTING, NEVER TOWARD SKIPPING. The tables below
are hand-maintained and will eventually run out. When they do, `is_trading_day`
falls back to weekday-only — so the cost of a stale table is one wasted holiday,
never a missed session. `year_is_known` lets a caller warn about it; the
collector prints that warning on startup so the table gets extended by someone
reading a log rather than by someone noticing a hole in the corpus months later.

Times are US/Central throughout, matching the rest of the corpus layer.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")

#: Regular cash-session close, US/Central. SPX 0DTE settles off this print.
REGULAR_CLOSE_CT = time(15, 0)
#: NYSE early-close time (13:00 ET), US/Central.
EARLY_CLOSE_CT = time(12, 0)
#: Cash-session open, US/Central.
SESSION_OPEN_CT = time(8, 30)

#: The GexBot collect window [st-a6zm]. 07:30 gives the pre-open ramp; 15:05
#: matches the ES capture supervisor's stop, so both live feeds close the day on
#: the same boundary. Defined here rather than in the collector because the EOD
#: packet audits rows against this window and the two must not drift.
GEX_COLLECT_START_CT = "07:30"
GEX_COLLECT_UNTIL_CT = "15:05"

#: NYSE full-closure holidays, keyed by year. Observed dates, not nominal ones —
#: 2026-07-03 is here because July 4 falls on a Saturday, and 2027-12-24 because
#: Christmas falls on a Saturday. A test asserts none of these lands on a
#: weekend, which is what a mis-derived observed date looks like.
HOLIDAYS: dict[int, frozenset[date]] = {
    2026: frozenset({
        date(2026, 1, 1),    # New Year's Day (Thu)
        date(2026, 1, 19),   # MLK Day (Mon)
        date(2026, 2, 16),   # Presidents' Day (Mon)
        date(2026, 4, 3),    # Good Friday
        date(2026, 5, 25),   # Memorial Day (Mon)
        date(2026, 6, 19),   # Juneteenth (Fri)
        date(2026, 7, 3),    # Independence Day observed (Jul 4 = Sat)
        date(2026, 9, 7),    # Labor Day (Mon)
        date(2026, 11, 26),  # Thanksgiving (Thu)
        date(2026, 12, 25),  # Christmas (Fri)
    }),
    2027: frozenset({
        date(2027, 1, 1),    # New Year's Day (Fri)
        date(2027, 1, 18),   # MLK Day (Mon)
        date(2027, 2, 15),   # Presidents' Day (Mon)
        date(2027, 3, 26),   # Good Friday
        date(2027, 5, 31),   # Memorial Day (Mon)
        date(2027, 6, 18),   # Juneteenth observed (Jun 19 = Sat)
        date(2027, 7, 5),    # Independence Day observed (Jul 4 = Sun)
        date(2027, 9, 6),    # Labor Day (Mon)
        date(2027, 11, 25),  # Thanksgiving (Thu)
        date(2027, 12, 24),  # Christmas observed (Dec 25 = Sat)
    }),
}

#: Sessions that close at 13:00 ET / 12:00 CT. Not a closure — collection should
#: still run, just stop earlier. Note the asymmetry with HOLIDAYS: 2026 has no
#: July 3 early close because July 3 is itself the holiday that year.
EARLY_CLOSES: dict[int, frozenset[date]] = {
    2026: frozenset({
        date(2026, 11, 27),  # day after Thanksgiving
        date(2026, 12, 24),  # Christmas Eve
    }),
    2027: frozenset({
        date(2027, 7, 2),    # Friday before observed Independence Day
        date(2027, 11, 26),  # day after Thanksgiving
    }),
}


def year_is_known(d: date) -> bool:
    """True when `d`'s year has a hand-maintained holiday table."""
    return d.year in HOLIDAYS


def is_holiday(d: date) -> bool:
    """True on a full NYSE closure. False for any year with no table."""
    return d in HOLIDAYS.get(d.year, frozenset())


def is_early_close(d: date) -> bool:
    """True on a 12:00 CT close. False for any year with no table."""
    return d in EARLY_CLOSES.get(d.year, frozenset())


def is_trading_day(d: date) -> bool:
    """True when the US cash equity market holds a session on `d`.

    Weekday-only for years with no holiday table — see the module docstring on
    why the fallback errs toward collecting.
    """
    return d.weekday() < 5 and not is_holiday(d)


def session_close_ct(d: date) -> time:
    """Cash close for `d`, US/Central — 12:00 on an early-close session."""
    return EARLY_CLOSE_CT if is_early_close(d) else REGULAR_CLOSE_CT


def next_trading_day(d: date) -> date:
    """First trading day strictly after `d`."""
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def parse_hm(s: str) -> time:
    """Parse an ``HH:MM`` clock string. Raises ValueError on anything else."""
    h, m = (int(x) for x in s.split(":"))
    return time(h, m)


def collect_window(d: date, start: str, until: str) -> tuple[time, time]:
    """Resolve the configured collect window against `d`'s actual close.

    The `until` bound is clamped to the session close plus the same tail the
    caller asked for on a regular day. Without this, an early-close session
    keeps polling for three hours after the market has stopped moving — the
    exact waste this module exists to prevent, just on a rarer day.
    """
    start_t = parse_hm(start)
    until_t = parse_hm(until)
    tail = (
        datetime.combine(d, until_t) - datetime.combine(d, REGULAR_CLOSE_CT)
    )
    if tail.total_seconds() < 0:
        tail = timedelta(0)
    close = datetime.combine(d, session_close_ct(d)) + tail
    return start_t, min(until_t, close.time())


def window_state(
    now_ct: datetime, start: str, until: str
) -> tuple[str, datetime | None]:
    """Classify `now_ct` against the collect window.

    Returns ``(state, resume_at)`` where state is one of:

        ``"open"``    inside the window — collect.
        ``"early"``   trading day, before the window opens. ``resume_at`` is the
                      window open; a caller should sleep until then.
        ``"closed"``  past the window on a trading day, or not a trading day at
                      all. ``resume_at`` is the next session's window open, for
                      the log line only — the collector exits rather than
                      sleeping through it, because a supervisor owns restart.
    """
    d = now_ct.date()
    if is_trading_day(d):
        start_t, until_t = collect_window(d, start, until)
        if now_ct.time() < start_t:
            return "early", datetime.combine(d, start_t, tzinfo=now_ct.tzinfo)
        if now_ct.time() <= until_t:
            return "open", None
    nxt = next_trading_day(d)
    nxt_start, _ = collect_window(nxt, start, until)
    return "closed", datetime.combine(nxt, nxt_start, tzinfo=now_ct.tzinfo)


def describe(d: date) -> str:
    """One-line human reason a day is or isn't collectable — for log lines."""
    if d.weekday() >= 5:
        return f"{d.isoformat()} is a {d.strftime('%A')} — market closed"
    if is_holiday(d):
        return f"{d.isoformat()} is a market holiday"
    if is_early_close(d):
        return f"{d.isoformat()} is an early close (12:00 CT)"
    return f"{d.isoformat()} is a regular session"
