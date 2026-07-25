"""Pre-approved MBP-1 window boundary tests. [st-ve6]

The window is a spend authorization: exactly the sessions Steve approved,
nothing before, nothing after. If someone widens MBP1_APPROVED_DAYS without a
matching approval, the docstring in corpus_daily.py is the policy and this
test is the tripwire for the CURRENT approval's boundaries.
"""
from datetime import date, timedelta

from scripts.corpus_daily import MBP1_APPROVED_DAYS, mbp1_approved


def test_approved_week_is_exactly_2026_07_27_to_31():
    assert MBP1_APPROVED_DAYS == {
        date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29),
        date(2026, 7, 30), date(2026, 7, 31),
    }


def test_window_edges_are_closed():
    assert mbp1_approved(date(2026, 7, 27))
    assert mbp1_approved(date(2026, 7, 31))
    # Friday before and Monday after the approved week: no spend
    assert not mbp1_approved(date(2026, 7, 24))
    assert not mbp1_approved(date(2026, 8, 3))


def test_every_approved_day_is_a_weekday():
    assert all(d.weekday() < 5 for d in MBP1_APPROVED_DAYS)
    # contiguous Mon-Fri
    days = sorted(MBP1_APPROVED_DAYS)
    assert days[0].weekday() == 0
    assert all(b - a == timedelta(days=1) for a, b in zip(days, days[1:]))
