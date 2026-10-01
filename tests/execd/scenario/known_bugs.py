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
    "H6": {"invariant": "stop_dollars_off_ticket",
           "pinned_by": _S + "TestFills::test_a_resting_entry_filled_in_a_market_wider_than_its_stop",
           "title": "a resting entry filled in a market wider than its stop: the stop cannot "
                    "follow the fill — measured from the fill it would sit over the bid — and "
                    "stays struck from the limit, nearer the fill than the ticket said",
           "detail": "what H1 left (st-n3e8): the stop sent with the entry is now struck from "
                     "the ask when the market is under the limit at the send, but a resting "
                     "limit that fills later in a gapped, wide market (generated wide seed 90: "
                     "15.40 limit, filled 15.20 with the bid 14.00, a 1.00 ticket) still has "
                     "_stop_follows_fill refused 'not below the bid'. The same root as H2 — a "
                     "spread wider than the stop distance. Steve's H2 ruling (st-yeph, "
                     "2026-10-01) refuses it at the entry ticket's send; a limit that rests "
                     "and fills later in a wider market is past that check, and what the "
                     "stop does then is st-91yu, open."},
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
