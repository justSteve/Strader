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
    "D3": {"invariant": "two_stops", "pinned_by": _T + "test_d3_the_childrens_read_fails",
           "title": "children_of raising, or a fallback cancel answered PENDING_CANCEL, puts a "
                    "second bracket beside the one the entry carried",
           "detail": "_attach_triggered falls back and places a pair whatever the cancel of "
                     "the carried children answered (or with no ids to cancel at all)."},
    "D4": {"invariant": "resting_sell_without_position, short_position",
           "pinned_by": _T + "test_d4_a_close_in_two_prints",
           "title": "a close in two prints books only the first; the stop and target are "
                    "re-rested on a flat account (and two prints in one millisecond collide)",
           "detail": "_pick_up_fills books per print, clears the leg id although the order "
                     "may still be WORKING, and dedupes on (order_id, leg_id, at)."},
    "D5": {"invariant": "two_stops", "pinned_by": _T + "test_d5_a_partly_filled_entry",
           "title": "a partly filled working entry is adopted, then added to when it completes: "
                    "the tracked size doubles",
           "detail": "_reconcile_working skips a WORKING order with filledQuantity; the "
                     "position sweep adopts the part, _promote adds the whole."},
    "D7": {"invariant": "bracket_not_linked", "pinned_by": _T + "test_d7_a_close_deferred_by_a_pending_cancel",
           "title": "a close deferred by a PENDING_CANCEL target re-rests an unlinked stop "
                    "beside the target every pass",
           "detail": "_take_bracket_off → DEFERRED → _rest_stop_at as a single order (the pair "
                     "cannot be cleared), then observe fires again next pass and churns it."},
    "D9": {"invariant": "(assertion)", "pinned_by": _T + "test_d9_the_day_is_continuous_through_a_close",
           "title": "closed lines are gross while the card is net of fees; a promoted or "
                    "recovered position carries entry commission 0",
           "detail": "the day total jumps by the fees at the close; _promote/_recover never "
                     "set entry_commission_usd."},
    "D13": {"invariant": "(assertion)", "pinned_by": _T + "test_d13_what_a_restart_forgets",
            "title": "the fill watermark resets on restart and trail_tier is not recovered",
            "detail": "_last_fill_poll = clock() at construction; nothing journals or replays "
                      "the tier."},
    "D15": {"invariant": "(assertion)", "pinned_by": _T + "test_d15_the_restrike",
            "title": "the re-strike at the $3.00 boundary rests a 2.95 stop at 2.90; a "
                     "negative-delta put intent is flipped",
            "detail": "protective_stop_price caps one 0.10 tick under a 3.00 limit; level_for "
                      "divides by a signed delta."},
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
    "H4": {"invariant": "stop_level_crossed_at_fill",
           "pinned_by": _S + "TestEntries::test_a_dip_buy_limit_is_not_sold_by_its_own_level",
           "title": "a resting limit under the market fills with its SPX stop level already "
                    "behind the index — the SPX loop market-sells it on the same pass",
           "detail": "the level is struck at the SEND's mark; a call limit 0.60 under the ask "
                     "fills ~1.2 SPX points lower, past a level 0.4 under the send's mark: "
                     "filled at 8.60, sold at 8.50 by spx-stop in the same watcher pass."},
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
