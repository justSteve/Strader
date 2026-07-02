"""Strict, fail-fast configuration loader for Strader.

Supersedes the per-script ``_load_dotenv`` helpers scattered through the repo.
Motivated directly by the 2026-06-30 ``.env`` → ``invalid_client`` incident: an
inline ``# comment`` on a value line bled into ``SCHWAB_API_KEY`` (VS Code's
envFile loader injects vars without stripping inline comments), and Schwab
rejected the malformed client_id. Diagnosis took an hour; a startup validator
would have turned it into a one-line error.

Two defenses live here:

1. **Authoritative parse.** ``.env`` is parsed strictly (inline comments and
   surrounding quotes stripped) and its values *override* any pre-existing —
   possibly polluted — process environment. The clean file wins.
2. **Fail-fast validation.** Every declared field is validated at load time and
   *all* problems are reported in one :class:`ConfigError`, before a single value
   can reach an external API.

Usage::

    from strader.config import Field, load, non_empty, no_comment_residue, is_https_url

    SCHWAB = [
        Field("SCHWAB_API_KEY", secret=True, validators=[non_empty, no_comment_residue, no_whitespace]),
        Field("SCHWAB_APP_SECRET", secret=True, validators=[non_empty, no_comment_residue]),
        Field("SCHWAB_CALLBACK_URL", validators=[non_empty, no_comment_residue, is_https_url]),
        Field("SCHWAB_TOKEN_PATH", required=False),
    ]
    cfg = load(SCHWAB)              # raises ConfigError listing every problem
    key = cfg["SCHWAB_API_KEY"]
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, MutableMapping

# A validator takes the resolved value and returns an error string, or None if OK.
Validator = Callable[[str], "str | None"]

# Repo root = parent of the strader package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


class ConfigError(Exception):
    """Raised when one or more configuration fields fail to load or validate.

    Aggregates *all* problems so the operator fixes them in one pass rather than
    rediscovering them one API call at a time.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        body = "\n".join(f"  - {p}" for p in problems)
        super().__init__(
            f"Strader config invalid ({len(problems)} problem(s)):\n{body}"
        )


# ─── .env parsing ────────────────────────────────────────────────────────────

def _strip_inline_comment(raw: str) -> str:
    """Return the value with a dotenv-style inline comment and quotes removed.

    Rules (matching python-dotenv semantics closely enough for our files):
      - A quoted value (``"..."`` or ``'...'``) yields the quoted content; any
        trailing ``# comment`` after the closing quote is dropped.
      - An unquoted value has an inline comment stripped only when the ``#`` is
        preceded by whitespace, so ``abc#def`` keeps its ``#`` but
        ``abc  # note`` becomes ``abc``.
    """
    raw = raw.strip()
    if not raw:
        return raw
    if raw[0] in ("'", '"'):
        quote = raw[0]
        end = raw.find(quote, 1)
        if end != -1:
            return raw[1:end]
        # Unbalanced quote: fall through and treat literally.
    out: list[str] = []
    for i, ch in enumerate(raw):
        if ch == "#" and i > 0 and raw[i - 1] in " \t":
            break
        out.append(ch)
    return "".join(out).rstrip()


def parse_dotenv(path: str | os.PathLike[str]) -> dict[str, str]:
    """Parse a ``.env`` file into a dict, stripping inline comments and quotes.

    Missing file → empty dict (fields are then validated against the process
    environment alone). ``export KEY=...`` prefixes are tolerated.
    """
    p = Path(path)
    if not p.exists():
        return {}
    result: dict[str, str] = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, raw_val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        result[key] = _strip_inline_comment(raw_val)
    return result


# ─── Field spec + built-in validators ────────────────────────────────────────

@dataclass(frozen=True)
class Field:
    """One configuration variable and how to validate it."""

    name: str
    required: bool = True
    secret: bool = False  # mask the value in error messages
    validators: tuple[Validator, ...] = field(default_factory=tuple)

    def masked(self, value: str) -> str:
        if not self.secret or not value:
            return value
        return f"<{self.name} set, {len(value)} chars>"


def non_empty(value: str) -> str | None:
    return "is empty" if value.strip() == "" else None


def no_comment_residue(value: str) -> str | None:
    """Catch the exact 2026-06-30 failure: an inline comment that survived
    a naive loader, e.g. ``Tob52...  # Schwab API key ...``."""
    if "#" in value and any(sep + "#" in value for sep in (" ", "\t")):
        return "contains an inline '# comment' — clean the .env value line"
    return None


def no_whitespace(value: str) -> str | None:
    """API keys / client ids must be a single token."""
    return "contains whitespace" if any(c.isspace() for c in value) else None


def is_https_url(value: str) -> str | None:
    return None if value.startswith("https://") else "is not an https:// URL"


# ─── Loader ──────────────────────────────────────────────────────────────────

def load(
    fields: Iterable[Field],
    env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH,
    environ: MutableMapping[str, str] | None = None,
    apply_to_environ: bool = True,
) -> dict[str, str]:
    """Load and validate configuration, returning a name→value dict.

    ``.env`` is authoritative: a value present in the file overrides any
    pre-existing (possibly polluted) value in ``environ``. Fields absent from
    the file fall back to ``environ``. Every field is validated; any failures
    are collected and raised together as :class:`ConfigError`.
    """
    environ = os.environ if environ is None else environ
    dotenv = parse_dotenv(env_path)

    resolved: dict[str, str] = {}
    problems: list[str] = []

    for f in fields:
        # .env wins over the (possibly polluted) process environment.
        value = dotenv.get(f.name, environ.get(f.name))
        if value is None:
            if f.required:
                problems.append(f"{f.name}: missing (not in {Path(env_path).name} or environment)")
            continue
        field_problems = [msg for v in f.validators if (msg := v(value))]
        for msg in field_problems:
            problems.append(f"{f.name}: {msg} (got {f.masked(value)!r})")
        resolved[f.name] = value
        if apply_to_environ and not field_problems:
            environ[f.name] = value  # publish the clean value

    if problems:
        raise ConfigError(problems)
    return resolved
