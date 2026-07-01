"""HTML → visible text for Mancini email blobs. [co-ylhf]

The email→Azure-blob pipeline stores the *raw HTML* email (~100KB). The parser's
fixtures and the extraction prompt expect the letter's plain visible text (the
"clean letter" format, ~30-40KB). Feeding raw HTML to the model wastes tokens
and mangles the level lists. This strips HTML to visible text: drop
script/style/head, turn block-level tags into line breaks, unescape entities,
collapse runaway whitespace.

Stdlib only (``html.parser``) — no bs4 / lxml / html2text dependency.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Container tags whose *content* is not visible letter text. These all have a
# matching close tag, so counting open/close is balanced. Void elements (meta,
# link, img, ...) are deliberately NOT here: they never emit a close tag, so
# counting them would leave the skip depth stuck > 0 and swallow the whole body.
_DROP_TAGS = {"script", "style", "head", "title", "noscript"}
# Block-level tags that should produce a line break around their content.
_BLOCK_TAGS = {
    "p", "div", "br", "tr", "table", "li", "ul", "ol",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "section", "article", "header", "footer", "hr",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # entities arrive already unescaped
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _DROP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag in _BLOCK_TAGS:  # e.g. <br/>, <hr/>
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def looks_like_html(raw: str) -> bool:
    head = raw.lstrip()[:256].lower()
    if head.startswith("<!doctype") or head.startswith("<html"):
        return True
    # Fallback: dense tag markup near the top.
    sample = raw[:4000].lower()
    return ("<div" in sample or "<table" in sample) and "</" in sample


def html_to_text(raw: str) -> str:
    """Convert an HTML document to its visible text."""
    parser = _TextExtractor()
    parser.feed(raw)
    text = parser.text()
    text = re.sub(r"[ \t ]+", " ", text)          # collapse spaces (incl. &nbsp;)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)             # cap blank-line runs
    return text.strip()


def clean_newsletter(raw: str) -> str:
    """Return the letter's visible text, converting from HTML only if needed.

    Plain-text blobs (and the test fixtures) pass through untouched, so the
    parser sees the same format whether the source is a clean letter or the raw
    HTML email from the blob.
    """
    return html_to_text(raw) if looks_like_html(raw) else raw
