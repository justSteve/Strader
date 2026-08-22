"""Spoken prices to numbers, and back through the speech phrasebook. [st-79z.3]"""
from __future__ import annotations

import pytest

from present.speech import spoken_price
from strader.intent.numbers import find_numbers, small_number, words_to_number


@pytest.mark.parametrize("words, value", [
    ("sixty-four twelve", 6412.0),
    ("sixty four twelve", 6412.0),
    ("seventy-four seventy-four", 7474.0),
    ("sixty-three hundred", 6300.0),
    ("seventy-four oh five", 7405.0),
    ("seventy-seven twenty", 7720.0),
    ("six thousand four hundred twelve", 6412.0),
    ("seven thousand", 7000.0),
    ("sixty four", 64.0),            # not a pair — a width or a count
    ("twenty", 20.0),
    ("nineteen ninety", 1990.0),
])
def test_words_to_number(words, value):
    assert words_to_number(words) == value


def test_words_to_number_refuses_non_prices():
    assert words_to_number("hundred and") is None
    assert words_to_number("") is None


def test_find_numbers_spoken_digits_fractions_and_frames():
    found = find_numbers("mancini has sixty-four twelve as the major support and 6,412.25 was the low; "
                         "consolidation around sixty-three twenty spx; seventy-four thirty-eight and a quarter")
    values = [(n.value, n.frame) for n in found]
    assert (6412.0, None) in values
    assert (6412.25, None) in values
    assert (6320.0, "SPX") in values
    assert (7438.25, None) in values


def test_whisper_decimal_pair_is_a_price_but_a_premium_is_not():
    # the 07-24 drill file came back from Whisper as "Buy signal at 74.47, support" (co-2a7ft)
    assert [n.value for n in find_numbers("Buy signal at 74.47, support")] == [7447.0]
    assert [n.value for n in find_numbers("fifty-five cents, 1.55 debit, .55")] == []


def test_find_numbers_keeps_times_for_the_grammar_to_refuse():
    # "ten thirty" is a time; numbers.py reports it, grammar.py's PRICE_FLOOR refuses it
    assert [n.value for n in find_numbers("found its low around ten thirty")] == [1030.0]


def test_small_number():
    assert small_number("twenty wide") == 20
    assert small_number("two lots") == 2
    assert small_number("20") == 20
    assert small_number("wide") is None


@pytest.mark.parametrize("price", [7438.0, 7438.25, 7438.5, 7438.75, 7400.0, 7405.0, 6412.0, 7000.0, 6320.5])
def test_round_trip_with_the_phrasebook(price):
    """The speech phrasebook (st-mhkp) says prices; this module hears them. Same words."""
    words = spoken_price(price)
    found = find_numbers(words)
    assert found and found[0].value == price, (words, found)
