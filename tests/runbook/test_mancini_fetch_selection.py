"""The Mancini fetch must return a LETTER, not whatever sorted last. [st-znw6]

On 2026-09-01 a Substack subscription receipt landed in the ingress container
and sorted after Monday evening's real letter. `fetch_latest()` took
`names[-1]`, so the morning parse would have run against a billing email and
produced nothing. The container is an email ingress, not a letter store —
anything the sender mails ends up in it.

These pin the selection, not the network. `select_letter` takes its reader as
an argument for exactly that reason.
"""

from __future__ import annotations

import logging

import pytest

from runbook.mancini.fetch import MAX_CANDIDATES, is_letter, select_letter

# Trimmed from the real 2026-09-01 receipt (data/mancini-letters/2026-09-01-065032.txt).
RECEIPT = """Receipt from Adam Mancini's S&P 500 (SPX/ES Futures) Trade Companion
Thank you for subscribing, amSteve! Learn how to manage your subscriptions.
Subscription for amsteve@gmail.com
Sep 1, 2026 through Oct 1, 2026
$23
"""

# The shape segment() anchors on — Mancini's own section markers, not a
# paraphrase. Using his literal phrasings ("Supports are:", "Bull case
# Tuesday:") is the point: a fixture that anchors for a reason the production
# regexes do not share would pass while proving nothing.
LETTER = """Trade Plan Tuesday

Recap of Monday: ES chopped in a 20 handle range all session.

Supports are: 6870, 6855-6860, 6840, 6825
Resistances are: 6890, 6902, 6915-6920, 6935

In terms of lvls I'd bid direct: 6855-6860 is the one I want.

Bull case Tuesday: acceptance over 6902 opens 6915-6920.

Bear case Tuesday: failure at 6890 targets 6855-6860.

In summary: patience at the edges, nothing in the middle.
"""


def _reader(store: dict[str, str]):
    """A blob reader over an in-memory container, recording call order."""
    calls: list[str] = []

    def read(name: str) -> str:
        calls.append(name)
        return store[name]

    read.calls = calls  # type: ignore[attr-defined]
    return read


# ------------------------------------------------------------- is_letter ----

def test_the_real_receipt_is_not_a_letter():
    ok, reason = is_letter(RECEIPT)
    assert ok is False
    assert "anchored=False" in reason


def test_a_letter_is_a_letter():
    ok, reason = is_letter(LETTER)
    assert ok is True
    assert "anchored" in reason


def test_empty_text_is_not_a_letter():
    assert is_letter("")[0] is False


def test_unparseable_input_is_refused_rather_than_raising():
    """A blob that breaks the cleaner must be skipped, not crash the morning."""
    ok, reason = is_letter("\x00\xff" * 500)
    assert ok is False


# --------------------------------------------------------- select_letter ----

def test_skips_the_receipt_and_returns_the_letter():
    """The 2026-09-01 case, exactly."""
    store = {
        "2026-08-31-184911.txt": LETTER,
        "2026-09-01-065032.txt": RECEIPT,
    }
    name, raw = select_letter(sorted(store), _reader(store))
    assert name == "2026-08-31-184911.txt"
    assert raw == LETTER


def test_returns_the_newest_when_it_is_already_a_letter():
    store = {"2026-08-28-192906.txt": LETTER, "2026-08-31-184911.txt": LETTER}
    name, _ = select_letter(sorted(store), _reader(store))
    assert name == "2026-08-31-184911.txt"


def test_stops_at_the_first_letter_and_downloads_no_further():
    """Each candidate costs an Azure download; it must not read past the hit."""
    store = {
        "a.txt": LETTER, "b.txt": LETTER,
        "c.txt": RECEIPT, "d.txt": RECEIPT,
    }
    read = _reader(store)
    name, _ = select_letter(sorted(store), read)
    assert name == "b.txt"
    assert read.calls == ["d.txt", "c.txt", "b.txt"]  # newest-first, then stop


def test_walks_several_non_letters():
    store = {
        "a.txt": LETTER,
        "b.txt": RECEIPT, "c.txt": RECEIPT, "d.txt": RECEIPT,
    }
    name, _ = select_letter(sorted(store), _reader(store))
    assert name == "a.txt"


def test_raises_naming_every_candidate_when_none_is_a_letter():
    """The failure must say what it looked at — a bare 'no letter' is unactionable."""
    store = {"b.txt": RECEIPT, "c.txt": RECEIPT}
    with pytest.raises(RuntimeError) as exc:
        select_letter(sorted(store), _reader(store))
    msg = str(exc.value)
    assert "b.txt" in msg and "c.txt" in msg
    assert "anchored=False" in msg


def test_attempts_are_bounded_so_a_bad_container_cannot_walk_history():
    store = {f"{i:03d}.txt": RECEIPT for i in range(50)}
    store["000.txt"] = LETTER  # a letter exists, but far beyond the cap
    read = _reader(store)
    with pytest.raises(RuntimeError):
        select_letter(sorted(store), read, max_attempts=3)
    assert len(read.calls) == 3


def test_default_cap_is_the_module_constant():
    store = {f"{i:03d}.txt": RECEIPT for i in range(50)}
    read = _reader(store)
    with pytest.raises(RuntimeError):
        select_letter(sorted(store), read)
    assert len(read.calls) == MAX_CANDIDATES


def test_a_single_blob_container_still_works():
    store = {"only.txt": LETTER}
    assert select_letter(sorted(store), _reader(store))[0] == "only.txt"


def test_every_skip_is_logged_with_its_reason(caplog):
    """A silent skip is how this bug hid until a receipt landed on a plan-day."""
    store = {"a.txt": LETTER, "z.txt": RECEIPT}
    with caplog.at_level(logging.WARNING, logger="runbook.mancini.fetch"):
        select_letter(sorted(store), _reader(store))
    text = caplog.text
    assert "skipping z.txt" in text
    assert "anchored=False" in text
