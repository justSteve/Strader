"""Open defects the scenarios pin — one place. [st-ug1h]

``D1``–``D15`` are the 2026-10-01 audit's findings (handed to this harness
to pin, each as a scenario); ``H1``–``H4`` are what the harness itself found
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
    # ── the audit (2026-10-01) ───────────────────────────────────────────
    "D7": {"invariant": "bracket_not_linked", "pinned_by": _T + "test_d7_a_close_deferred_by_a_pending_cancel",
           "title": "a close deferred by a PENDING_CANCEL target re-rests an unlinked stop "
                    "beside the target every pass",
           "detail": "_take_bracket_off → DEFERRED → _rest_stop_at as a single order (the pair "
                     "cannot be cleared), then observe fires again next pass and churns it."},
    "D13": {"invariant": "(assertion)", "pinned_by": _T + "test_d13_what_a_restart_forgets",
            "title": "the fill watermark resets on restart and trail_tier is not recovered",
            "detail": "_last_fill_poll = clock() at construction; nothing journals or replays "
                      "the tier."},
    # ── found by the harness ─────────────────────────────────────────────
    "H1": {"invariant": "stop_not_below_bid_when_placed, stop_dollars_off_ticket",
           "pinned_by": _S + "TestFills::test_fill_much_better_than_the_limit",
           "title": "the stop sent with the entry is struck under the LIMIT, not the market — a "
                    "market already under the limit by the stop distance fills the entry under "
                    "a stop above the bid, and it fires at once",
           "detail": "13:24 CT 09-30: 9.20 limit, market 8.70/8.80 → 9.00 stop over an 8.70 bid; "
                     "paper fires it on the first read (−$10). bracket_fired books it right; "
                     "_stop_follows_fill never gets the chance. The same root from a resting "
                     "entry filled in a wide or gapped market (generated wide seed 90): the "
                     "follow is refused ('not below the bid') and the stop stays struck from "
                     "the limit, 0.80 from a 15.20 fill on a 1.00 ticket."},
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
