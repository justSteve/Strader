"""Open defects the scenarios pin — one place. [st-ug1h]

``D1``–``D15`` are the 2026-10-01 audit's findings (handed to this harness
to pin, each as a scenario); ``H1``–``H6`` are what the harness itself found
running its own sequences. Each entry names the invariant (or the assertion)
it breaks and the test that pins it — an ``xfail(strict=True)``: when the
defect is fixed that test passes, the strict xfail turns red, and whoever
fixed it deletes the entry here and the marker there in the same commit.

A scenario that must run past an open defect to test something else — a
seed case for a different 09-30 bug, a generated walk — may ``waive`` the
invariant, citing the entry by key. A waiver whose key is not here is
refused (``harness.Scenario``), so a fixed defect cannot stay waived.
"""

from __future__ import annotations

_T = "test_audit_defects.py::"
_S = "test_sequences.py::"

KNOWN: dict[str, dict[str, str]] = {
    # ── the audit (2026-10-01): all fifteen fixed ───────────────────────
    # ── found by the harness ─────────────────────────────────────────────
    # H2 (st-yeph) fixed 2026-10-01 by Steve's ruling "in those conditions it
    # should refuse": the ticket and the service refuse a stop that would
    # rest at or above the bid (TestFills::test_a_stop_at_or_over_the_bid_
    # is_refused_at_the_ticket). H5 (st-a54y) closed by his ruling the same
    # day, "At entry, only permit a $$ SL": no entry carries an SPX stop
    # level (TestEntries::test_an_entry_carrying_an_spx_stop_is_refused).
    # H6 (st-91yu) fixed 2026-10-01 by st-qbh6: the stop is struck from the
    # MID at the fill, so a resting limit filled later in a wide market rests
    # its stop the ticket's distance under the mid, under the bid
    # (TestFills::test_a_resting_entry_filled_in_a_market_wider_than_its_stop).
}


def require(key: str) -> dict[str, str]:
    if key not in KNOWN:
        raise KeyError(f"{key} is not an open defect (tests/execd/scenario/known_bugs.py) — "
                       f"if it was fixed, remove the waiver that cites it")
    return KNOWN[key]


def reason(key: str) -> str:
    """The xfail reason for the scenario that pins ``key``."""
    k = require(key)
    return f"{key} ({k['invariant']}): {k['title']}"
