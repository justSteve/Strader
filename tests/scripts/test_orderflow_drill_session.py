"""Cash-session semantics of the drill's level chips. [st-fgno]

The tape starts at 02:50 CT (st-btu). Until 2026-08-18 the drill's "Open" was
the 02:50 print, "AM" ran 02:50-11:00 and "Day Hi/Lo" spanned the overnight.
Steve: session means the cash session.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from scripts.orderflow_drill import session_levels

CT = ZoneInfo("America/Chicago")
DAY = date(2026, 8, 17)


class _Bar:
    def __init__(self, hhmm, o, h, l):
        hh, mm = (int(x) for x in hhmm.split(":"))
        self.start_ts = datetime(2026, 8, 17, hh, mm, tzinfo=CT)
        self.open, self.high, self.low = o, h, l


def test_levels_come_from_the_cash_session_only():
    bars = [
        _Bar("02:50", 7820.0, 7830.0, 7815.0),   # overnight — highest high of the day
        _Bar("06:10", 7818.0, 7822.0, 7760.0),   # overnight — lowest low of the day
        _Bar("08:29", 7801.0, 7804.0, 7799.0),   # straddles the open → pre-open
        _Bar("08:30", 7803.0, 7809.5, 7800.0),   # first RTH bar
        _Bar("10:59", 7805.0, 7808.0, 7788.25),  # last AM bar
        _Bar("11:00", 7790.0, 7795.0, 7766.0),   # PM
        _Bar("14:50", 7770.0, 7780.0, 7768.0),
    ]
    levels, first, n = session_levels(bars, DAY)
    assert first == 3 and n == 4
    assert levels == {"open": 7803.0, "am_high": 7809.5, "am_low": 7788.25,
                      "session_high": 7809.5, "session_low": 7766.0}


def test_a_tape_with_no_rth_bar_falls_back_to_the_whole_tape():
    bars = [_Bar("02:50", 7820.0, 7830.0, 7815.0), _Bar("05:00", 7818.0, 7822.0, 7760.0)]
    levels, first, n = session_levels(bars, DAY)
    assert first is None and n == 0
    assert levels["open"] == 7820.0 and levels["session_low"] == 7760.0
