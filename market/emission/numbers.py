"""Numbers as a trader says them, for the surfaces that speak.

Lifted verbatim from ``present/speech.py`` under st-bkvt so that
``market/emission/renderer.py`` can reach them. The renderer serves both the
written surface (``market/orderflow/engine.py``) and the spoken one
(``present/speech.py``); if it imported these from ``present`` the market
layer would depend on the presentation layer, which is backwards.
``present.speech`` re-exports both names, so its public API is unchanged.

Number words are generated here rather than handed to the TTS engine as
digits. espeak-ng, piper and any cloud voice each read "74" and "7438.25"
differently; generating the words in-process makes output engine-independent
and testable without audio.
"""
from __future__ import annotations

__all__ = ["spoken_price", "spoken_count"]

_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = (
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
)

# ES trades in quarter points. Anything else is spoken digit-wise rather than
# silently rounded onto a tick that the instrument may not have.
_FRACTIONS = {0: "", 25: " and a quarter", 50: " and a half", 75: " and three quarters"}


def _under_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] if ones == 0 else f"{_TENS[tens]}-{_ONES[ones]}"


def spoken_count(n: int) -> str:
    """A plain cardinal, for sizes and tick counts. Falls back to digits above
    999 — every engine reads large integers acceptably, and spelling them out
    makes a sentence longer than the move it describes."""
    if n < 0:
        return f"minus {spoken_count(-n)}"
    if n < 100:
        return _under_hundred(n)
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        head = f"{_ONES[hundreds]} hundred"
        return head if rest == 0 else f"{head} {_under_hundred(rest)}"
    return str(n)


def spoken_price(price: float) -> str:
    """Speak a price the way a trader says it.

    >>> spoken_price(7438.0)
    'seventy-four thirty-eight'
    >>> spoken_price(7438.25)
    'seventy-four thirty-eight and a quarter'
    >>> spoken_price(7400.0)
    'seventy-four hundred'
    >>> spoken_price(7405.0)
    'seventy-four oh five'
    """
    whole = int(price)
    cents = round(round(price - whole, 2) * 100)
    if cents == 100:            # 7437.999 -> 7438.0
        whole, cents = whole + 1, 0

    tail = _FRACTIONS.get(cents)
    if tail is None:
        # Not on a quarter. Say the decimal rather than round it away — a
        # non-ES instrument's real price beats a tidy ES-shaped lie.
        tail = f" point {''.join(_ONES[int(d)] + ' ' for d in f'{cents:02d}').strip()}"

    # The four-digit pair form ("seventy-four thirty-eight") is how ES and SPX
    # are spoken. Outside that range it stops being idiomatic, so fall back.
    if 1000 <= whole < 10000:
        hi, lo = divmod(whole, 100)
        if whole % 1000 == 0:
            # 7400 is "seventy-four hundred", but 7000 is "seven thousand" —
            # nobody says "seventy hundred".
            head = f"{_ONES[whole // 1000]} thousand"
        elif lo == 0:
            head = f"{_under_hundred(hi)} hundred"
        elif lo < 10:
            head = f"{_under_hundred(hi)} oh {_ONES[lo]}"
        else:
            head = f"{_under_hundred(hi)} {_under_hundred(lo)}"
    else:
        head = spoken_count(whole)

    return head + tail
