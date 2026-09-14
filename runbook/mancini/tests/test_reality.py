"""The letter measured against the tape — contract resolution and note status. [st-7xzw]

The 2026-09-14 shape, synthetic: Mancini's ladder sits on the September
contract (gap 7663 / 7671 at write-time), December trades ~67 higher, and
overnight the September contract closes through 7620, 7610 and 7605 and
tests 7595. The old brief, fed December candles, said 54 of 58 untouched.
"""
from __future__ import annotations

from runbook.mancini import reality
from runbook.mancini.overnight import (
    OvernightReport,
    build_overnight_report,
    quarterly_contracts,
    resolve_letter_contract,
    letter_window_start,
)
from runbook.mancini.run import _render_desk_plan
from runbook.mancini.schema import Commentary, Level, ParseResult, Trigger

T0 = 1_789_000_000_000


def bar(i, o, h, l, c):
    return {"datetime": T0 + i * 300_000, "open": o, "high": h, "low": l,
            "close": c, "volume": 100}


def lv(price, kind, label="", intent="unstated", setup="none"):
    return Level(price=float(price), kind=kind, label=label, source_quote=str(price),
                 intent=intent, setup=setup)


def note(text, tags, ttype, anchors):
    return Commentary(text=text, tags=tags, source_quote=text,
                      trigger=Trigger(type=ttype, anchor_prices=[float(a) for a in anchors],
                                      condition_text=""))


def sept_letter() -> ParseResult:
    levels = [
        lv(7663, "support"), lv(7650, "support", "major"), lv(7627, "support"),
        lv(7620, "support", "major · must hold lowest", "trade", "failed_breakdown"),
        lv(7610, "support"), lv(7605, "trigger"), lv(7604, "support"),
        lv(7595, "support", "major"), lv(7588, "support", "major"),
        lv(7671, "resistance", "major"), lv(7680, "resistance"),
        lv(7693, "resistance", "major"), lv(7714, "resistance", "major"),
    ]
    commentary = [
        note("Bulls need to hold ~7620 to keep full control.", ["bull_case"], "price_zone", [7620]),
        note("Strong case: defend 7650, targets 7693, 7714.", ["bull_case", "breakout_target"],
             "price_zone", [7650, 7693, 7714]),
        note("Breakout above 7714 opens 7746.", ["bull_case", "breakout_target"], "price_cross", [7714]),
        note("No adds on strength.", ["bull_case", "no_entry"], "unconditional", []),
        note("Failed Breakdown of 7620 is highly actionable; bonus tag 7610.",
             ["bid_direct", "failed_breakdown", "long_entry"], "price_zone", [7620, 7610]),
        note("Bear case begins below 7610; likely 7605 trigger down.",
             ["bear_case", "breakdown_short", "short_entry"], "price_cross", [7610, 7605]),
        note("Shorts to try at 7693, 7714.", ["short_entry", "risk"], "price_zone", [7693, 7714]),
        note("Summary: 7620 must hold lowest; 7650 in a strong case.", ["summary", "regime"],
             "price_zone", [7620, 7650, 7693]),
    ]
    return ParseResult(date="2026-09-14", instrument="ES", session_bias="Defer to the trend.",
                       levels=levels, commentary=commentary, raw_excerpt="", model="t",
                       parsed_at="2026-09-14T12:50:00Z")


# September: opens 7667 (inside the 7663/7671 gap), pokes 7693, then loses
# 7620 / 7610 / 7605 / 7604, runs to 7593.75, and sits at 7603.
SEPT = [
    bar(0, 7667, 7670, 7664, 7668),
    bar(1, 7668, 7695.5, 7667, 7690),     # closes above 7693? no — 7690 < 7693+2: poke only
    bar(2, 7690, 7701.25, 7688, 7696),    # close 7696 > 7695: 7693 broken (poked)
    bar(3, 7696, 7697, 7685, 7688),       # back under: 7693 reclaimed (rejected)
    bar(4, 7688, 7689, 7640, 7645),
    bar(5, 7645, 7646, 7622, 7625),       # 7627 touched, close above
    bar(6, 7625, 7626, 7612, 7615),       # 7620 broken (close 7615 < 7618)
    bar(7, 7615, 7616, 7600, 7602),       # 7610, 7604 broken; 7605 trigger passed
    bar(8, 7602, 7606, 7593.75, 7598),    # 7595 touched, close above (held)
    bar(9, 7598, 7605, 7597, 7603.25),
]
# December: the same path shifted +67 — never near the September levels.
DEC = [dict(b, open=b["open"] + 67, high=b["high"] + 67, low=b["low"] + 67,
            close=b["close"] + 67) for b in SEPT]


def two_contract_fetch(start, end=None, symbol="/ES"):
    return {"/ESU26": SEPT, "/ESZ26": DEC}[symbol]


def test_quarterlies_from_plan_day():
    assert quarterly_contracts("2026-09-14") == ["/ESU26", "/ESZ26"]
    assert quarterly_contracts("2026-09-18") == ["/ESU26", "/ESZ26"]   # expiry day: still front
    assert quarterly_contracts("2026-09-21") == ["/ESZ26", "/ESH27"]
    assert quarterly_contracts("2026-12-21") == ["/ESH27", "/ESM27"]


def test_resolver_picks_the_contract_inside_the_ladder_gap():
    r = sept_letter()
    res = resolve_letter_contract(r, letter_window_start(r.date), fetch=two_contract_fetch)
    assert res.symbol == "/ESU26"
    assert "inside the letter's gap" in res.reason
    assert res.basis_contract == "/ESZ26" and res.basis == 67.0


def test_resolver_survives_one_dead_candidate():
    def one_dead(start, end=None, symbol="/ES"):
        if symbol == "/ESZ26":
            raise RuntimeError("HTTP 400")
        return SEPT

    r = sept_letter()
    res = resolve_letter_contract(r, letter_window_start(r.date), fetch=one_dead)
    assert res.symbol == "/ESU26" and res.basis is None
    assert "only contract with data" in res.reason


def test_resolver_falls_back_to_continuous_for_symbol_blind_fetch():
    r = sept_letter()
    res = resolve_letter_contract(r, letter_window_start(r.date), fetch=lambda start: SEPT)
    assert res.symbol == "/ES" and "continuous" in res.reason


def test_report_measures_september_not_december():
    r = sept_letter()
    rep = build_overnight_report(r, fetch=two_contract_fetch)
    assert rep.error is None and rep.contract == "/ESU26" and rep.last_close == 7603.25
    st = {it.price: it.state for it in rep.interactions}
    assert st[7620] == "broken" and st[7610] == "broken" and st[7604] == "broken"
    assert st[7595] == "tested-held"
    assert st[7693] == "reclaimed"          # poked to 7701.25 and rejected
    assert st[7714] == "untouched"


def test_note_statuses_follow_the_tape():
    r = sept_letter()
    rep = build_overnight_report(r, fetch=two_contract_fetch)
    verdicts = {c.text: reality.note_status(c, r, rep)[0] for c in r.commentary}
    assert verdicts["Bulls need to hold ~7620 to keep full control."] == "VOID"
    assert verdicts["Strong case: defend 7650, targets 7693, 7714."] == "VOID"
    assert verdicts["Breakout above 7714 opens 7746."] == "AHEAD"
    assert verdicts["No adds on strength."] == ""
    assert verdicts["Failed Breakdown of 7620 is highly actionable; bonus tag 7610."] == "ARMED"
    assert verdicts["Bear case begins below 7610; likely 7605 trigger down."] == "LIVE"
    assert verdicts["Shorts to try at 7693, 7714."] == "TAGGED"
    assert verdicts["Summary: 7620 must hold lowest; 7650 in a strong case."] == "VOID"


def test_reclaimed_floor_reads_intact_via_trap_and_bear_trapped():
    r = sept_letter()
    trap = SEPT[:8] + [bar(8, 7602, 7626, 7601, 7624), bar(9, 7624, 7630, 7622, 7628)]
    # Both months answer the same series → the resolver asks quotes; hand it
    # none so this stays offline and the front contract wins the tie.
    rep = build_overnight_report(r, fetch=lambda s, e=None, symbol="/ES": trap,
                                 quote_fetch=lambda syms: {})
    verdicts = {c.text: reality.note_status(c, r, rep)[0] for c in r.commentary}
    assert verdicts["Bulls need to hold ~7620 to keep full control."] == "INTACT via trap"
    assert verdicts["Failed Breakdown of 7620 is highly actionable; bonus tag 7610."] == "PRINTED"
    assert verdicts["Bear case begins below 7610; likely 7605 trigger down."] == "TRAPPED"


def test_reality_block_names_floor_trigger_and_basis():
    r = sept_letter()
    rep = build_overnight_report(r, fetch=two_contract_fetch)
    block = reality.render_reality_block(r, rep)
    assert block.startswith("## Where price is against the letter — ESU26 7603.25")
    assert "ESZ26 trades 67 higher" in block
    assert "Supports lost since the letter" in block and "**7620** major" in block
    assert "The letter's floor, 7620" in block and "**BROKEN**" in block
    assert "bear trigger, below 7610: **LIVE**" in block
    assert "7693 major (to 7701.25" in block


def test_desk_doc_puts_reality_above_bias_and_tags_notes():
    r = sept_letter()
    rep = build_overnight_report(r, fetch=two_contract_fetch)
    doc = _render_desk_plan(r, overnight_section="## Overnight interaction\n\nx", report=rep)
    assert doc.index("## Where price is against the letter") < doc.index("## Bias")
    assert "- **VOID** — Bulls need to hold ~7620" in doc
    assert "- **LIVE** — Bear case begins below 7610" in doc
    assert "- No adds on strength." in doc            # unconditional: untagged


def test_desk_doc_without_report_is_unchanged_shape():
    r = sept_letter()
    doc = _render_desk_plan(r)
    assert "## Where price is against the letter" not in doc
    assert "- Bulls need to hold ~7620 to keep full control." in doc


def test_reality_block_degrades_with_the_report():
    r = sept_letter()
    rep = OvernightReport(error="token expired")
    block = reality.render_reality_block(r, rep)
    assert "Tape unavailable (token expired)" in block
    assert all(reality.note_status(c, r, rep)[0] == "" for c in r.commentary)


def test_collapsed_series_are_separated_by_live_quotes():
    """Schwab hands back the same (December) candles for both month symbols;
    quotes say ESU26 is 67 under ESZ26. The resolver must shift the served
    series onto September and pick it by the ladder gap."""
    def collapsed(start, end=None, symbol="/ES"):
        return DEC                                  # whatever you ask for

    def quotes(symbols):
        return {"/ESU26": {"last": 7603.25, "close": 7659.5},
                "/ESZ26": {"last": 7670.25, "close": 7727.25}}

    r = sept_letter()
    res = resolve_letter_contract(r, letter_window_start(r.date), fetch=collapsed,
                                  quote_fetch=quotes)
    assert res.symbol == "/ESU26"
    assert res.candles[0]["open"] == 7667 and res.candles[-1]["close"] == 7603.25
    assert res.basis == 67.0 and res.basis_contract == "/ESZ26"
    assert "served one series" in res.reason and "-67" in res.reason


def test_collapsed_series_without_quotes_still_resolve_nearest():
    def collapsed(start, end=None, symbol="/ES"):
        return DEC

    r = sept_letter()
    res = resolve_letter_contract(r, letter_window_start(r.date), fetch=collapsed,
                                  quote_fetch=lambda syms: {})
    assert res.symbol == "/ESU26"           # front wins the tie
    assert "quotes were unavailable" in res.reason


def test_weekend_gap_does_not_fool_the_resolver():
    """The real 2026-09-14 trap: Schwab's first candle is Sunday 17:00 CT,
    after a 47-point gap, so December's Sunday open (7680) looked nearer the
    7663/7671 gap than September's shifted open. The prior settle from each
    contract's quote — 4pm ET Friday, his write time — puts September
    (7659.5 → inside the gap once he wrote 'first support 7650'... nearest)
    and December (7727.25) where they belong."""
    dec_gapped = [dict(b, open=b["open"] + 13, high=b["high"] + 13, low=b["low"] + 13,
                       close=b["close"] + 13) for b in DEC]          # Sunday open 7680

    def collapsed(start, end=None, symbol="/ES"):
        return dec_gapped

    def quotes(symbols):
        return {"/ESU26": {"last": 7616.25, "close": 7665.0},
                "/ESZ26": {"last": 7683.25, "close": 7727.25}}

    r = sept_letter()
    res = resolve_letter_contract(r, letter_window_start(r.date), fetch=collapsed,
                                  quote_fetch=quotes)
    assert res.symbol == "/ESU26"
    assert "prior settle from quotes" in res.reason and "inside the letter's gap" in res.reason
    assert res.write_prices["/ESU26"] == 7665.0 and res.write_prices["/ESZ26"] == 7727.25


def test_collapse_detected_despite_a_moving_last_candle():
    """Two pulls seconds apart: same series, but the forming candle differs
    and one pull has an extra bar. Still one series."""
    calls = {"n": 0}

    def collapsed_live(start, end=None, symbol="/ES"):
        calls["n"] += 1
        if calls["n"] == 1:
            return DEC
        return DEC[:-1] + [dict(DEC[-1], close=DEC[-1]["close"] + 1.5)] + [bar(10, 7671, 7672, 7669, 7670)]

    def quotes(symbols):
        return {"/ESU26": {"last": 7603.25, "close": 7659.5},
                "/ESZ26": {"last": 7670.25, "close": 7727.25}}

    r = sept_letter()
    res = resolve_letter_contract(r, letter_window_start(r.date), fetch=collapsed_live,
                                  quote_fetch=quotes)
    assert res.symbol == "/ESU26" and "served one series" in res.reason
    assert res.candles[0]["open"] == 7667
