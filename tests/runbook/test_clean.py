"""Tests for runbook.mancini.clean — HTML→visible-text for blob letters. [co-ylhf]"""

from __future__ import annotations

from runbook.mancini.clean import clean_newsletter, html_to_text, looks_like_html


def test_plain_text_passes_through():
    txt = "Supports are: 7383, 7377 (major)\nBull case tomorrow: rip to 7451."
    assert clean_newsletter(txt) == txt


def test_detects_html():
    assert looks_like_html("<!DOCTYPE html><html><body>x</body></html>")
    assert looks_like_html('<html lang="en"><head></head><body>y</body></html>')
    assert not looks_like_html("Supports are: 7383, 7377")


def test_strips_tags_keeps_visible_text():
    html = "<html><body><p>Bias: bullish</p><p>Hold <b>7435</b> then rip.</p></body></html>"
    out = html_to_text(html)
    assert "Bias: bullish" in out
    assert "Hold 7435 then rip." in out
    assert "<" not in out and ">" not in out


def test_drops_script_and_style():
    html = "<html><head><style>.x{color:red}</style></head><body><script>evil()</script><p>7451 resistance</p></body></html>"
    out = html_to_text(html)
    assert "7451 resistance" in out
    assert "color:red" not in out
    assert "evil()" not in out


def test_level_list_survives_html():
    html = "<html><body><p>Supports are: 7383, 7377 (major), 7365 (major), 7355.</p></body></html>"
    out = clean_newsletter(html)
    assert "Supports are: 7383, 7377 (major), 7365 (major), 7355." in out


def test_unescapes_entities():
    html = "<html><body><p>bulls &amp; bears &lt;here&gt;</p></body></html>"
    out = html_to_text(html)
    assert "bulls & bears <here>" in out
