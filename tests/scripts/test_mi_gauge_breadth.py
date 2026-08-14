"""mi_gauge live breadth + persisted read [st-9573, architecture step 0].

What is actually being protected:

  - **$ADD/$VOLD are computed from components, never requested as symbols.**
    They are spreads thinkorswim computes on its own platform. Schwab registers
    the spread symbols, describes them correctly, and serves 0.0 intraday —
    which is exactly how they came to be written off as "not served intraday
    on either Schwab surface" (st-9573's original title). Measured live
    2026-08-14 12:04 CT: $ADVN 1396 · $DECN 1311 · $UVOL 6.81B · $DVOL 2.53B,
    while a direct request for $ADD/$VOLD returned 0.0 for both.

  - **A missing leg must not read as zero.** "Zero advancers" is a real market
    state and a catastrophic one; "the quote did not arrive" is a Tuesday. If
    breadth ever emits 0 for an absent component, every downstream slope reads
    a cliff that never happened.

  - **The capture file's spine survives extra keys.** The live daemon appends
    to this file continuously and rebuilds its cumulative-TICK spine from it on
    respawn. restore_state() reads ts/high/low/close and nothing else, so extras
    must be invisible to it — asserted by round-trip, not by reading the code.
"""
from __future__ import annotations

import json
import sys
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from market.internals.gauge import MIGauge, TickMinute  # noqa: E402
from mi_gauge import (  # noqa: E402
    POLL_SYMBOLS,
    append_capture,
    breadth,
    quote_prices,
    render,
    restore_state,
)

CENTRAL = ZoneInfo("America/Chicago")
DAY = _date(2026, 8, 14)


def at(h, m):
    return datetime(2026, 8, 14, h, m, tzinfo=CENTRAL)


def payload(**syms):
    return {s: {"quote": {"lastPrice": v}} for s, v in syms.items()}


# --- the poll set --------------------------------------------------------

def test_poll_set_asks_for_components_not_spreads():
    # The regression this guards: someone "simplifies" by asking for $ADD.
    assert "$ADVN" in POLL_SYMBOLS and "$DECN" in POLL_SYMBOLS
    assert "$UVOL" in POLL_SYMBOLS and "$DVOL" in POLL_SYMBOLS
    assert "$ADD" not in POLL_SYMBOLS, "$ADD is a spread; Schwab serves 0.0"
    assert "$VOLD" not in POLL_SYMBOLS, "$VOLD is a spread; Schwab serves 0.0"
    assert "$TICK" in POLL_SYMBOLS


# --- quote extraction ----------------------------------------------------

def test_quote_prices_extracts_present_symbols():
    p = quote_prices(payload(**{"$TICK": -53.0, "$ADVN": 1396.0}))
    assert p == {"$TICK": -53.0, "$ADVN": 1396.0}


def test_quote_prices_skips_absent_and_non_numeric():
    raw = {"$TICK": {"quote": {"lastPrice": -53.0}},
           "$ADVN": {"quote": {}},              # no price
           "$DECN": {},                          # no quote block
           "$UVOL": {"quote": {"lastPrice": None}},
           "$DVOL": {"quote": {"lastPrice": "n/a"}}}
    assert quote_prices(raw) == {"$TICK": -53.0}
    assert quote_prices({}) == {}
    assert quote_prices(None) == {}


# --- the computation -----------------------------------------------------

def test_breadth_computes_both_spreads():
    b = breadth({"$ADVN": 1396.0, "$DECN": 1311.0,
                 "$UVOL": 6_807_422_280.0, "$DVOL": 2_525_517_570.0})
    assert b["add"] == 85.0
    assert b["vold"] == 4_281_904_710.0
    assert b["advn"] == 1396.0 and b["decn"] == 1311.0


def test_breadth_carries_sign_on_negative_days():
    # The whole point of computing it: the bearish half is visible. Same-day
    # minute HISTORY floors negatives at zero; quotes do not, and neither does
    # arithmetic on quotes.
    assert breadth({"$ADVN": 700.0, "$DECN": 2100.0})["add"] == -1400.0


def test_breadth_omits_a_pair_with_a_missing_leg():
    assert "add" not in breadth({"$ADVN": 1396.0})
    assert "vold" not in breadth({"$UVOL": 1.0})
    # A partial payload still yields the pair that IS complete.
    b = breadth({"$ADVN": 10.0, "$DECN": 4.0, "$UVOL": 5.0})
    assert b["add"] == 6.0 and "vold" not in b


def test_breadth_never_substitutes_zero_for_absent():
    assert breadth({}) == {}
    for k, v in breadth({"$DECN": 1311.0}).items():
        assert v != 0 or k not in ("add", "vold")


# --- capture: additive, and the spine is untouchable ---------------------

def test_append_capture_writes_extras(tmp_path):
    cap = tmp_path / "mi_gauge_live.jsonl"
    m = TickMinute(ts=at(9, 30), high=200, low=-100, close=50)
    assert append_capture(cap, m, day=DAY,
                          extra={"add": 85.0, "score": -12, "band": "neutral"})
    rec = json.loads(cap.read_text().splitlines()[0])
    assert rec["high"] == 200 and rec["low"] == -100 and rec["close"] == 50
    assert rec["add"] == 85.0 and rec["score"] == -12 and rec["band"] == "neutral"


def test_extras_cannot_shadow_the_spine(tmp_path):
    # If a caller ever passes a key that collides, the candle wins. Corrupting
    # high/low/close would silently rewrite the cumulative spine on next restore.
    cap = tmp_path / "c.jsonl"
    m = TickMinute(ts=at(9, 31), high=200, low=-100, close=50)
    append_capture(cap, m, day=DAY,
                   extra={"high": 999, "low": 999, "close": 999,
                          "ts": "1999-01-01T00:00:00", "add": 1.0})
    rec = json.loads(cap.read_text().splitlines()[0])
    assert (rec["high"], rec["low"], rec["close"]) == (200, -100, 50)
    assert rec["ts"].startswith("2026-08-14")
    assert rec["add"] == 1.0


def test_append_capture_day_guard_still_holds(tmp_path):
    cap = tmp_path / "c.jsonl"
    other = TickMinute(ts=datetime(2026, 8, 15, 9, 30, tzinfo=CENTRAL),
                       high=1, low=1, close=1)
    assert append_capture(cap, other, day=DAY, extra={"add": 1.0}) is False
    assert not cap.exists()


def test_restore_ignores_extras_and_rebuilds_the_same_spine(tmp_path):
    """Round-trip: a file written WITH extras must restore identically to one
    written without. This is what makes the change safe to land under a daemon
    that is already appending."""
    minutes = [TickMinute(ts=at(9, 30 + i), high=300 + i, low=-200 - i, close=40 + i)
               for i in range(8)]

    plain = tmp_path / "plain.jsonl"
    rich = tmp_path / "rich.jsonl"
    for m in minutes:
        append_capture(plain, m, day=DAY)
        append_capture(rich, m, day=DAY,
                       extra={"add": 85.0, "vold": 4.2e9, "advn": 1396.0,
                              "decn": 1311.0, "score": -12, "band": "neutral",
                              "driver": "quiet tape", "bucket": "am",
                              "instant": -3, "cum": -9, "cum_tick": -77})

    g_plain, g_rich = MIGauge(), MIGauge()
    ts_plain = restore_state(plain, g_plain, DAY, echo=False)
    ts_rich = restore_state(rich, g_rich, DAY, echo=False)

    assert ts_plain == ts_rich
    assert g_plain.cum_tick == g_rich.cum_tick
    assert g_plain.minutes == g_rich.minutes


def test_restore_tolerates_an_old_file_with_no_extras(tmp_path):
    # Forward compatibility in the other direction: capture files written before
    # this change must keep restoring.
    cap = tmp_path / "old.jsonl"
    cap.write_text(json.dumps(
        {"ts": at(9, 30).isoformat(), "high": 300, "low": -200, "close": 40}) + "\n")
    g = MIGauge()
    assert restore_state(cap, g, DAY, echo=False) == at(9, 30)


# --- the pane ------------------------------------------------------------

class _Read:
    timestamp = at(9, 30)
    score = -12
    band = "neutral"
    driver = "quiet tape"
    tick_high = 300
    tick_low = -200
    cum_tick = -77


def test_render_shows_breadth_when_present_and_omits_it_when_not():
    assert "ADD" not in render(_Read())
    assert "ADD" not in render(_Read(), {})
    line = render(_Read(), {"add": 85.0, "vold": 4_281_904_710.0})
    assert "ADD    +85" in line
    assert "VOLD +4.28B" in line
    # add without vold still renders, rather than raising
    assert "ADD" in render(_Read(), {"add": -1400.0})
