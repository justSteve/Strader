"""The completeness floor: how rich the parse is, not whether it is true. [st-9r51]

`validate` proves nothing was invented; `parity_check` proves no *listed* level
was dropped. The 2026-08-10 parse passed both carrying two callouts whose full
text was "range high" and "range low". This floor is what would have said so.

It must never block. Every assertion here is about what gets *reported* — the
run publishes either way, and a test that let this raise or return non-zero
would be pinning the wrong contract.
"""
import pytest

from runbook.mancini import completeness
from runbook.mancini.schema import Level, ParseResult

LETTER = """\
Yesterday's recap. Bull case tomorrow: this is the QUOTED prior letter and
names 7100, which is not part of today's plan.

Trade Plan Friday

Supports are: 7734, 7723, 7714 (major), 7704, 7671 (major).

Resistances are: 7745, 7758 (major), 7771 (major).

Bull case tomorrow: ES can continue to defend 7714 (or quick traps below).
7758 and 7771 are targets. On August 4th we set a massive low at 7632 from
which we rallied to current highs.

Bear case tomorrow: Begins below 7671. Likely 7704 trigger down.

In summary for tomorrow: lean is up toward 7745.
"""


def _result(levels):
    return ParseResult(date="2026-08-28", instrument="ES", session_bias="b",
                       levels=levels, commentary=[])


def _rich(price, kind="support"):
    return Level(price=price, kind=kind,
                 label=f"major · a real callout about {price:g} with substance",
                 source_quote=f"{price:g} (major)")


def _bare(price, kind="support"):
    return Level(price=price, kind=kind, label="major",
                 source_quote=f"{price:g} (major)")


def test_a_rich_parse_clears_the_floor():
    levels = [_rich(p) for p in (7734, 7723, 7714, 7704, 7671)]
    levels += [_rich(p, "resistance") for p in (7745, 7758, 7771)]
    rep = completeness.check(_result(levels), LETTER)
    assert rep.checked
    assert rep.warnings == []
    assert rep.ok
    assert "completeness: OK" in completeness.render(rep)


def test_the_2026_08_10_shape_fires_the_callout_floor():
    """Two callouts on a full ladder — the parse this floor exists for."""
    levels = [_bare(p) for p in (7734, 7723, 7714, 7704, 7671)]
    levels += [_bare(p, "resistance") for p in (7745, 7758, 7771)]
    levels[0].label = "major · range high"
    rep = completeness.check(_result(levels), LETTER)
    assert any("carry a real callout" in w for w in rep.warnings)
    assert "COMPLETENESS FLOOR" in completeness.render(rep)


def test_a_level_named_only_in_forward_prose_is_reported_missing():
    """parity_check compares against the two lists and is blind to this."""
    levels = [_rich(p) for p in (7734, 7723, 7714, 7704, 7671)]
    levels += [_rich(p, "resistance") for p in (7745, 7758)]   # 7771 dropped
    rep = completeness.check(_result(levels), LETTER)
    assert 7771.0 in rep.prose_missing
    assert any("absent from the parse entirely" in w for w in rep.warnings)


def test_a_dated_anecdote_is_not_reported_as_a_missing_level():
    """'On August 4th we set a massive low at 7632' is history, not a plan
    level. It recurred in five parses in a fortnight before being separated
    out; a warning wrong that often is one you learn to skip."""
    levels = [_rich(p) for p in (7734, 7723, 7714, 7704, 7671)]
    levels += [_rich(p, "resistance") for p in (7745, 7758, 7771)]
    rep = completeness.check(_result(levels), LETTER)
    assert 7632.0 in rep.anecdotal_prices
    assert 7632.0 not in rep.prose_missing
    assert rep.warnings == []


def test_the_quoted_prior_letter_is_not_scanned():
    """7100 is named in the recap's quoted bull case. Segmentation drops it
    before this module ever sees it — the same trap segment.py is built on."""
    levels = [_rich(p) for p in (7734, 7723, 7714, 7704, 7671)]
    levels += [_rich(p, "resistance") for p in (7745, 7758, 7771)]
    rep = completeness.check(_result(levels), LETTER)
    assert 7100.0 not in rep.prose_missing
    assert 7100.0 not in rep.prose_prices


def test_prose_levels_without_callouts_are_reported_over_the_threshold():
    levels = [_bare(p) for p in (7734, 7723, 7714, 7704, 7671)]
    levels += [_bare(p, "resistance") for p in (7745, 7758, 7771)]
    # Enough rich callouts elsewhere that only the prose check can fire.
    levels += [_rich(p) for p in (7600, 7610, 7620, 7630, 7640)]
    rep = completeness.check(_result(levels), LETTER)
    assert set(rep.prose_without_callout) >= {7714.0, 7758.0, 7771.0}
    assert any("carry no callout" in w for w in rep.warnings)


def test_out_of_band_numbers_are_not_read_as_levels():
    """A four-digit number nowhere near the ladder — a year, a size — is not a
    level Mancini named."""
    letter = LETTER.replace("lean is up toward 7745.",
                            "lean is up toward 7745. © 2026 AM Trade Companion Inc.")
    levels = [_rich(p) for p in (7734, 7723, 7714, 7704, 7671)]
    levels += [_rich(p, "resistance") for p in (7745, 7758, 7771)]
    rep = completeness.check(_result(levels), letter)
    assert 2026.0 not in rep.prose_prices
    assert 2026.0 not in rep.prose_missing


def test_unsegmentable_letter_returns_unchecked_not_a_verdict():
    levels = [_rich(7734)]
    rep = completeness.check(_result(levels), "prose with no ladder at all")
    assert not rep.checked
    assert rep.warnings == []
    assert completeness.render(rep) == ""


def test_empty_parse_is_unchecked():
    rep = completeness.check(_result([]), LETTER)
    assert not rep.checked


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_check_never_raises_on_junk_input(bad):
    levels = [_rich(7734)]
    rep = completeness.check(_result(levels), bad or "")
    assert not rep.checked


def test_render_is_empty_when_unchecked_and_loud_when_thin():
    thin = completeness.check(_result([_bare(7734), _bare(7723)]), LETTER)
    out = completeness.render(thin)
    assert out.startswith("!!")
    assert "Publishing anyway" in out
