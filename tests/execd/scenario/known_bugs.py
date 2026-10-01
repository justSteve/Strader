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
    "H2": {"invariant": "stop_not_below_bid_when_placed",
           "pinned_by": _S + "TestFills::test_spread_wider_than_the_stop_distance",
           "title": "the entry's stop is never judged against the bid — a spread as wide as the "
                    "stop distance rests it at or over the bid",
           "detail": "adjust refuses a stop at or over the bid; the triggered bracket does not "
                     "ask. 0.30 wide with the 0.20 default: 0.10 over the bid, fired by the "
                     "first 0.05 down-tick of the mark. And at TWO lots the flat $20 ticket "
                     "is $10 a contract — 0.10 under the ask, which is the bid of an ordinary "
                     "0.10-wide market above $3 (seen first in the two-lot partial-exit "
                     "sequence)."},
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
                     "spread wider than the stop distance — so it waits on Steve's H2 decision "
                     "(no refusal or warning is added here: tests/execd/test_no_hand_holding.py)."},
    "H5": {"invariant": "stop_level_crossed_at_fill",
           "pinned_by": _S + "TestEntries::test_a_dip_buy_with_a_level_stop_fills_past_its_level",
           "title": "a resting limit with a LEVEL stop (his close-at-SPX box) fills with the "
                    "index already past his level — the SPX loop market-sells it on the same "
                    "pass",
           "detail": "the residual of H4 (st-d3va): a dollar stop is now struck again from the "
                     "mark at the fill, but a level stop keeps the level he typed, so a dip "
                     "that fills the limit past it closes the position at once. Whether a "
                     "level the market has already crossed at the fill should still fire is "
                     "Steve's call, not a mechanical fix — open for his decision."},
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
