"""A tiny, dependency-free loader for the block-YAML subset Strader authors.

Strader's core is intentionally stdlib-only (see pyproject). The playbook
catalog (``strader/playbooks/conditions.yaml`` + per-playbook frontmatter) is
data, and parsing it should not force a third-party dependency on every install.

So this module loads the *specific* YAML subset we author:

  - block mappings, nested by indentation (spaces only);
  - scalars with type coercion (``true``/``false`` -> bool, ``null``/``~`` ->
    None, ints, floats, everything else str), single/double quotes stripped;
  - block sequences (``- item`` lines) and inline flow sequences (``[a, b, c]``);
  - ``#`` comments (whole-line and inline, quote-aware).

It deliberately does **not** implement flow-style mappings (``{k: v}``), anchors,
multi-document streams, or block scalars — our files avoid all of them.

If PyYAML is installed, :func:`safe_load` transparently defers to it (our files
are valid standard YAML, so the result is identical); the bundled subset loader
is the no-dependency fallback and is exercised directly by the tests regardless
of environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # optional acceleration / full-spec parsing when available
    import yaml as _pyyaml
except ImportError:  # pragma: no cover - exercised by absence in CI venv
    _pyyaml = None


class YamlError(ValueError):
    """Raised when the subset loader hits syntax it does not support."""


# ─── public API ──────────────────────────────────────────────────────────────

def safe_load(text: str) -> Any:
    """Parse *text*. Uses PyYAML if importable, else the bundled subset loader."""
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    return _load_subset(text)


def load_file(path: str | Path) -> Any:
    """Read and parse a file (raises ``FileNotFoundError`` if it is absent)."""
    return safe_load(Path(path).read_text())


# ─── scalar + flow parsing ───────────────────────────────────────────────────

def _strip_inline_comment(s: str) -> str:
    """Drop a trailing ``# comment``, honoring quotes. A ``#`` only starts a
    comment when it is at column 0 or preceded by whitespace."""
    out: list[str] = []
    quote: str | None = None
    for i, ch in enumerate(s):
        if quote is not None:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _scalar(s: str) -> Any:
    s = s.strip()
    if s == "":
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~", "none"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _split_flow(inner: str) -> list[str]:
    """Split a flow-sequence body on commas, ignoring commas inside quotes."""
    items: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in inner:
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail or items:
        items.append(tail)
    return items


def _parse_value(s: str) -> Any:
    s = s.strip()
    if s.startswith("["):
        if not s.endswith("]"):
            raise YamlError(f"unterminated flow sequence: {s!r}")
        return [_scalar(x) for x in _split_flow(s[1:-1].strip())]
    if s.startswith("{"):
        raise YamlError("flow mappings ({...}) are not supported by this loader")
    return _scalar(s)


# ─── block parsing ───────────────────────────────────────────────────────────

def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Return (indent, content) for each significant line, comments/blanks removed."""
    result: list[tuple[int, str]] = []
    for raw in text.splitlines():
        body = raw.rstrip()
        stripped = body.lstrip(" ")
        if "\t" in body[: len(body) - len(stripped)]:
            raise YamlError("tab in indentation is not allowed")
        indent = len(body) - len(stripped)
        content = _strip_inline_comment(stripped)
        if content == "":
            continue
        result.append((indent, content))
    return result


def _is_list_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _parse_block(lines: list[tuple[int, str]], idx: int, indent: int) -> tuple[Any, int]:
    if idx >= len(lines):
        return None, idx
    if _is_list_item(lines[idx][1]):
        return _parse_list(lines, idx, indent)
    return _parse_map(lines, idx, indent)


def _parse_map(lines: list[tuple[int, str]], idx: int, indent: int) -> tuple[dict, int]:
    result: dict[str, Any] = {}
    while idx < len(lines):
        cur_indent, content = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise YamlError(f"unexpected indent in mapping near {content!r}")
        key, sep, rest = content.partition(":")
        if not sep:
            raise YamlError(f"expected 'key: value', got {content!r}")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            nxt = lines[idx + 1] if idx + 1 < len(lines) else None
            if nxt is not None and (
                nxt[0] > indent or (nxt[0] == indent and _is_list_item(nxt[1]))
            ):
                value, idx = _parse_block(lines, idx + 1, nxt[0])
                result[key] = value
                continue
            result[key] = None
            idx += 1
        else:
            result[key] = _parse_value(rest)
            idx += 1
    return result, idx


def _parse_list(lines: list[tuple[int, str]], idx: int, indent: int) -> tuple[list, int]:
    result: list[Any] = []
    while idx < len(lines):
        cur_indent, content = lines[idx]
        if cur_indent < indent or not _is_list_item(content):
            break
        if cur_indent > indent:
            raise YamlError(f"unexpected indent in sequence near {content!r}")
        item = content[1:].strip()
        if item == "":
            nxt = lines[idx + 1] if idx + 1 < len(lines) else None
            if nxt is not None and nxt[0] > indent:
                value, idx = _parse_block(lines, idx + 1, nxt[0])
                result.append(value)
                continue
            result.append(None)
            idx += 1
        else:
            result.append(_parse_value(item))
            idx += 1
    return result, idx


def _load_subset(text: str) -> Any:
    lines = _logical_lines(text)
    if not lines:
        return None
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value
