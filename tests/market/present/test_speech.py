"""Tests for present/speech.py — the ear-side rendering of emitted Signals.

Bead: st-mhkp. These are pure-function tests; nothing here touches audio.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market.signals.types import Bias, Regime, Level, Alert, Action, InferenceRequest
from market.signals.orderflow import (
    SweepPrint, DeltaDivergence, ImbalanceStack, AbsorptionRead, SetupRecognition,
)
from present.speech import speak, spoken_price, spoken_count, HindsightLeak
import present.speech as speech

CENTRAL = ZoneInfo("America/Chicago")
TS = datetime(2026, 7, 24, 9, 41, tzinfo=CENTRAL)


def _base(**kw):
    """Signal's four required fields, overridable."""
    return {"timestamp": TS, "source": "recognizer", "confidence": 0.8,
            "reason": "harness vocabulary that must not be spoken", **kw}


# ---------------------------------------------------------------- prices ---

@pytest.mark.parametrize("price,expected", [
    (7438.0,  "seventy-four thirty-eight"),
    (7438.25, "seventy-four thirty-eight and a quarter"),
    (7438.5,  "seventy-four thirty-eight and a half"),
    (7438.75, "seventy-four thirty-eight and three quarters"),
    (7400.0,  "seventy-four hundred"),
    (7405.0,  "seventy-four oh five"),
    (7405.5,  "seventy-four oh five and a half"),
    (7000.0,  "seven thousand"),
    (5820.5,  "fifty-eight twenty and a half"),
    (6011.75, "sixty eleven and three quarters"),
])
def test_spoken_price(price, expected):
    assert spoken_price(price) == expected


def test_spoken_price_rounds_float_noise_up_to_the_tick():
    # 7437.999... must not become "seventy-four thirty-seven point nine nine".
    assert spoken_price(7437.9999) == "seventy-four thirty-eight"


def test_spoken_price_off_tick_says_the_decimal_rather_than_rounding():
    # A non-ES instrument's real price beats a tidy ES-shaped lie.
    said = spoken_price(7438.10)
    assert "point" in said
    assert "quarter" not in said


def test_spoken_price_outside_four_digits_drops_the_pair_form():
    assert spoken_price(84.0) == "eighty-four"


@pytest.mark.parametrize("n,expected", [
    (0, "zero"), (7, "seven"), (19, "nineteen"), (20, "twenty"),
    (38, "thirty-eight"), (90, "ninety"), (100, "one hundred"),
    (405, "four hundred five"), (999, "nine hundred ninety-nine"),
    (1250, "1250"),
])
def test_spoken_count(n, expected):
    assert spoken_count(n) == expected


def test_spoken_count_handles_negative():
    assert spoken_count(-8) == "minus eight"


# ------------------------------------------------------- setup recognition ---

def test_confirmed_setup_names_side_price_and_anchor_kind():
    said = speak(SetupRecognition(**_base(), bias="bullish", anchor_price=7438.0,
                                  anchor_kind="support", state="confirmed"))
    assert said.startswith("Buy signal at seventy-four thirty-eight, support.")


def test_confirmed_bearish_setup_says_sell():
    said = speak(SetupRecognition(**_base(), bias="bearish", anchor_price=7450.25,
                                  anchor_kind="resistance", state="confirmed"))
    assert said.startswith("Sell signal at seventy-four fifty and a quarter, resistance.")


def test_first_fire_does_not_mention_the_count():
    said = speak(SetupRecognition(**_base(), anchor_price=7438.0,
                                  state="confirmed", fire_index=1))
    assert "time at this level" not in said


def test_fourth_fire_is_spoken_aloud():
    # st-m3f — the fourth fire is a materially different call from the first.
    said = speak(SetupRecognition(**_base(), anchor_price=7438.0,
                                  state="confirmed", fire_index=4))
    assert "the fourth time at this level today" in said


def test_damped_confidence_is_named():
    said = speak(SetupRecognition(**_base(confidence=0.6), anchor_price=7438.0,
                                  state="confirmed", fire_index=4))
    assert "Lower confidence." in said


def test_undamped_confidence_is_not_editorialised():
    said = speak(SetupRecognition(**_base(confidence=0.9), anchor_price=7438.0,
                                  state="confirmed"))
    assert "confidence" not in said.lower()


def test_mancini_confluence_is_called_out():
    said = speak(SetupRecognition(**_base(), anchor_price=7438.0,
                                  state="confirmed", mancini_confluence=True))
    assert "Mancini level" in said


def test_forming_setup_reports_beats_in_plain_words():
    said = speak(SetupRecognition(**_base(), anchor_price=7438.0, state="forming",
                                  beats=("flush", "stall")))
    assert "pushed through" in said and "failed to hold" in said
    assert "Not confirmed." in said


def test_forming_with_no_beats_says_still_early():
    said = speak(SetupRecognition(**_base(), anchor_price=7438.0, state="forming"))
    assert "still early" in said


def test_invalidated_setup_is_short_and_final():
    said = speak(SetupRecognition(**_base(), anchor_price=7438.0, state="invalidated"))
    assert said == "Seventy-four thirty-eight is off. The setup there failed." or \
           said == "seventy-four thirty-eight is off. The setup there failed."


@pytest.mark.parametrize("token,plain", [
    ("flush", "pushed through"), ("stall", "failed to hold"),
    ("flip", "the delta turned"), ("confirm", "came back through"),
])
def test_frozen_beat_tokens_are_never_spoken(token, plain):
    # The tokens are a record contract [st-g9y]; they are also exactly the
    # jargon st-v95 was raised over. They must not survive into speech.
    # Word-boundary match: "Not confirmed." is plain English, not the token.
    said = speak(SetupRecognition(**_base(), anchor_price=7438.0,
                                  state="forming", beats=(token,)))
    assert plain in said
    assert not re.search(rf"\b{token}\b", said.lower())


# -------------------------------------------------------- other orderflow ---

def test_sweep_print():
    said = speak(SweepPrint(**_base(), direction="buy", start_price=7436.0,
                            end_price=7438.0, ticks_swept=8, total_size=412))
    assert said == ("Buy sweep, eight ticks through to seventy-four thirty-eight, "
                    "four hundred twelve contracts.")


def test_delta_divergence_bearish_names_the_high():
    said = speak(DeltaDivergence(**_base(), kind="bearish", price_extreme=7452.0))
    assert "New high" in said and "did not follow" in said


def test_imbalance_stack_spans_first_to_last():
    said = speak(ImbalanceStack(**_base(), direction="sell",
                                prices=(7438.0, 7438.25, 7438.5)))
    assert said == ("Sell stack, three levels, seventy-four thirty-eight to "
                    "seventy-four thirty-eight and a half.")


def test_imbalance_stack_with_no_prices_degrades_quietly():
    assert speak(ImbalanceStack(**_base(), direction="buy", prices=())) == "Buy stack."


def test_absorption_defence_held():
    said = speak(AbsorptionRead(**_base(), side="bid", price=7438.0,
                                aggressive_vol=900, displacement_ticks=6,
                                refill_events=4))
    assert "Buyers defended seventy-four thirty-eight" in said
    assert "held" in said


def test_absorption_level_broke():
    said = speak(AbsorptionRead(**_base(), side="bid", price=7438.0,
                                aggressive_vol=900, displacement_ticks=-6,
                                refill_events=4))
    assert "the level broke" in said


def test_absorption_without_quotes_admits_the_gap():
    # refill_events == 0 means trades-only. The sentence must not imply a read
    # the data cannot support.
    said = speak(AbsorptionRead(**_base(), side="ask", price=7438.0,
                                aggressive_vol=900, displacement_ticks=3,
                                refill_events=0))
    assert "No quote data behind that." in said


# -------------------------------------------------------------- base types ---

def test_action_is_phrased_as_a_suggestion_not_a_report():
    # Actions are recommendations; Steve confirms before anything executes.
    said = speak(Action(**_base(), verb="buy one lot"))
    assert said.startswith("Suggestion:")


def test_alert_prefers_its_message():
    assert speak(Alert(**_base(), message="feed stalled")) == "feed stalled"


def test_bias_and_regime():
    assert speak(Bias(**_base(), direction="bearish")) == "Bias is bearish."
    assert speak(Regime(**_base(), state="compressed")) == "The tape is compressed."


# ------------------------------------------------------------- refusals ---

def test_unknown_signal_type_stays_silent_rather_than_reading_its_reason():
    said = speak(InferenceRequest(**_base(), question="what is this?"))
    assert said is None


def test_reason_field_never_leaks_into_speech():
    sig = SetupRecognition(**_base(reason="fire_index=4 anchor=7438 stage=confirm"),
                           anchor_price=7438.0, state="confirmed", fire_index=4)
    said = speak(sig)
    assert "fire_index" not in said and "stage=" not in said


def test_hindsight_quantities_cannot_be_spoken(monkeypatch):
    # Defensive net: a future phrasing that narrates a HINDSIGHT term must fail
    # loudly rather than assert something unknowable mid-session.
    monkeypatch.setattr(speech, "_bias", lambda s: "Bias is bullish, a hollow-glide leg.")
    monkeypatch.setattr(speech, "_PHRASINGS", ((Bias, speech._bias),))
    with pytest.raises(HindsightLeak):
        speak(Bias(**_base(), direction="bullish"))
