"""Strict, fail-fast configuration loader for Strader.

Supersedes the per-script ``_load_dotenv`` helpers scattered through the repo.
Motivated directly by the 2026-06-30 ``.env`` → ``invalid_client`` incident: an
inline ``# comment`` on a value line bled into ``SCHWAB_API_KEY`` (VS Code's
envFile loader injects vars without stripping inline comments), and Schwab
rejected the malformed client_id. Diagnosis took an hour; a startup validator
would have turned it into a one-line error.

Three defenses live here:

1. **Authoritative parse.** ``.env`` is parsed strictly (inline comments and
   surrounding quotes stripped) and its values *override* any pre-existing —
   possibly polluted — process environment. The clean file wins.
2. **Fail-fast validation.** Every declared field is validated at load time and
   *all* problems are reported in one :class:`ConfigError`, before a single value
   can reach an external API.
3. **Secrets out of the tree.** A ``Field(secret=True)`` value comes from the
   vault file named by ``STRADER_SECRETS_FILE`` (default ``/home/vault/Strader/env``,
   mode 0600, outside every project tree), never from the in-tree ``.env`` — a
   secret found there is refused at load. Convention of 2026-08-25 (Steve to
   COO, credential estate), enforced where the value is consumed. [co-4q6cg]

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
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, MutableMapping

# A validator takes the resolved value and returns an error string, or None if OK.
Validator = Callable[[str], "str | None"]

# Repo root = parent of the strader package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

# ─── The vault: where secret values live ─────────────────────────────────────
#
# The in-tree .env holds settings and ONE pointer; the values a Field marks
# ``secret=True`` live in the file the pointer names. Precedence when a name
# appears in more than one place: vault file > .env > process environment.
# Without a pointer, the default vault path is used if it exists, so a fresh
# checkout on this box works with no .env edit; with a pointer, the file must
# exist. Either way the file must be readable by its owner only.

SECRETS_POINTER = "STRADER_SECRETS_FILE"
DEFAULT_SECRETS_PATH = Path("/home/vault/Strader/env")


def resolve_secrets_path(
    dotenv: Mapping[str, str],
    environ: Mapping[str, str],
    env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH,
) -> tuple[Path | None, bool]:
    """The secrets file to read, and whether it was named explicitly.

    Explicit (``STRADER_SECRETS_FILE`` in ``.env`` or the environment): that path,
    relative paths resolved beside ``.env``; it must exist. Implicit: the default
    vault path, only if it is present. ``(None, False)`` means no secrets file.
    """
    raw = dotenv.get(SECRETS_POINTER) or environ.get(SECRETS_POINTER)
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path(env_path).resolve().parent / p
        return p, True
    if DEFAULT_SECRETS_PATH.exists():
        return DEFAULT_SECRETS_PATH, False
    return None, False


def secrets_file_problem(path: Path) -> str | None:
    """Why a secrets file cannot be used, or None. It must exist and be mode
    0600 or tighter — a vault file readable by group or other is not a vault."""
    if not path.exists():
        return f"{SECRETS_POINTER}: {path} does not exist"
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        return (f"{SECRETS_POINTER}: {path} is mode {mode:04o}; a secrets file must be "
                f"0600 (chmod 600 it — group/other must not read it)")
    return None


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

    Precedence is vault file > ``.env`` > ``environ``: a value in a file
    overrides any pre-existing (possibly polluted) value in the process
    environment, and the vault file overrides ``.env``. A ``secret=True`` field
    found in ``.env`` is refused — secret values do not live in the tree. Every
    field is validated; all failures are collected and raised together as
    :class:`ConfigError`.
    """
    environ = os.environ if environ is None else environ
    dotenv = parse_dotenv(env_path)

    resolved: dict[str, str] = {}
    problems: list[str] = []

    secrets_path, _explicit = resolve_secrets_path(dotenv, environ, env_path)
    secrets: dict[str, str] = {}
    if secrets_path is not None:
        problem = secrets_file_problem(secrets_path)
        if problem:
            problems.append(problem)
        else:
            secrets = parse_dotenv(secrets_path)
    where = f"{Path(env_path).name}, the secrets file or environment"

    for f in fields:
        if f.secret and f.name in dotenv:
            problems.append(
                f"{f.name}: secret value found in {Path(env_path).name} — secret values live "
                f"only in the vault file named by {SECRETS_POINTER}; move it there and leave "
                f"no value in the tree (convention 2026-08-25)")
            continue
        # vault file > .env > the (possibly polluted) process environment.
        value = secrets.get(f.name, dotenv.get(f.name, environ.get(f.name)))
        if value is None:
            if f.required:
                problems.append(f"{f.name}: missing (not in {where})")
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
