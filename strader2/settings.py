"""Concrete Strader config field-specs + convenience loaders.

``config.py`` is the generic engine (parse, validate, fail fast). This module
declares *what* Strader actually needs and *how strictly* to validate it, so
every entry point loads config the same authoritative, comment-immune way
instead of ad-hoc ``os.getenv`` / ``load_dotenv``.
"""

from __future__ import annotations

import os

from strader2.config import (
    DEFAULT_ENV_PATH,
    Field,
    is_https_url,
    load,
    no_comment_residue,
    no_whitespace,
    non_empty,
)

# Credentials the broker client needs. The API key is a single token
# (no_whitespace); every field must be free of inline-comment residue — the
# 2026-06-30 invalid_client failure mode.
SCHWAB_FIELDS: tuple[Field, ...] = (
    Field("SCHWAB_API_KEY", secret=True, validators=(non_empty, no_comment_residue, no_whitespace)),
    Field("SCHWAB_APP_SECRET", secret=True, validators=(non_empty, no_comment_residue)),
    Field("SCHWAB_TOKEN_PATH", required=False, validators=(no_comment_residue,)),
)

# The OAuth refresh flow additionally needs the callback URL.
SCHWAB_AUTH_FIELDS: tuple[Field, ...] = SCHWAB_FIELDS + (
    Field("SCHWAB_CALLBACK_URL", validators=(non_empty, no_comment_residue, is_https_url)),
)


def load_schwab(env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Validated config for the broker client (api key, app secret, token path)."""
    return load(SCHWAB_FIELDS, env_path=env_path)


def load_schwab_auth(env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Validated config for the OAuth refresh flow (adds the callback URL)."""
    return load(SCHWAB_AUTH_FIELDS, env_path=env_path)


# Databento market-data API key (single token, comment-immune).
DATABENTO_FIELDS: tuple[Field, ...] = (
    Field("DATABENTO_API_KEY", secret=True, validators=(non_empty, no_comment_residue, no_whitespace)),
)


def load_databento(env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Validated config for Databento access. ``apply_to_environ`` (on by
    default) republishes the clean key to ``os.environ`` so the ``databento``
    library — which reads ``DATABENTO_API_KEY`` from the environment — also sees
    the authoritative value."""
    return load(DATABENTO_FIELDS, env_path=env_path)
