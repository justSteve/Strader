"""Concrete Strader config field-specs + convenience loaders.

``config.py`` is the generic engine (parse, validate, fail fast). This module
declares *what* Strader actually needs and *how strictly* to validate it, so
every entry point loads config the same authoritative, comment-immune way
instead of ad-hoc ``os.getenv`` / ``load_dotenv``.
"""

from __future__ import annotations

import os

from strader.config import (
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

# The SECOND Schwab app (st-p9mx). Steve has two registrations: the one above
# carries market data and cannot trade — developer.schwab.com refuses to add the
# Accounts and Trading product to it, so every /trader/v1 call on it answers 401
# "no apiproduct match found", permanently — and this one carries Accounts and
# Trading. The unlabelled pair above is the market app and stays unlabelled on
# purpose: renaming it would touch both readers, the four schwab-stages crons,
# the corpus token check, the gate hook and the vault file, to buy symmetry. The
# asymmetry is closed in code instead, by the two explicitly named loaders below,
# so nothing that picks an app ever reads an unlabelled name.
SCHWAB_TRADING_FIELDS: tuple[Field, ...] = (
    Field("SCHWAB_TRADING_API_KEY", secret=True,
          validators=(non_empty, no_comment_residue, no_whitespace)),
    Field("SCHWAB_TRADING_APP_SECRET", secret=True,
          validators=(non_empty, no_comment_residue)),
    Field("SCHWAB_TRADING_TOKEN_PATH", required=False, validators=(no_comment_residue,)),
)

# The trading app's own OAuth registration. The callback is optional: app 2 may
# be registered with the same callback URL as app 1, and requiring it would make
# Steve answer a question he may not need to. When it differs and is unset,
# Schwab's own ``invalid_client`` says so unambiguously — see
# ``load_schwab_trading_auth`` for the fallback.
SCHWAB_TRADING_AUTH_FIELDS: tuple[Field, ...] = SCHWAB_TRADING_FIELDS + (
    Field("SCHWAB_TRADING_CALLBACK_URL", required=False,
          validators=(no_comment_residue, is_https_url)),
    Field("SCHWAB_CALLBACK_URL", validators=(non_empty, no_comment_residue, is_https_url)),
)


def load_schwab(env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Validated config for the broker client (api key, app secret, token path).

    Kept as the name every existing caller uses; it is the *market-data* app.
    New code should say which app it means — :func:`load_schwab_market` or
    :func:`load_schwab_trading`."""
    return load(SCHWAB_FIELDS, env_path=env_path)


def load_schwab_market(env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> dict[str, str]:
    """The market-data app (app 1): quotes, chains, history. This credential
    cannot place an order — Schwab refuses the endpoint family, not us — which is
    why it is the one the service may hold outside the arming lock (st-p9mx §1)."""
    return load(SCHWAB_FIELDS, env_path=env_path)


def load_schwab_auth(env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Validated config for the OAuth refresh flow (adds the callback URL)."""
    return load(SCHWAB_AUTH_FIELDS, env_path=env_path)


def load_schwab_trading(env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> dict[str, str]:
    """The Accounts and Trading app (app 2): every ``/trader/v1`` call.

    Only ``execd`` uses this, and only when Steve has armed the service."""
    return load(SCHWAB_TRADING_FIELDS, env_path=env_path)


def load_schwab_trading_auth(
    env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH,
) -> dict[str, str]:
    """The trading app's OAuth config, with the callback resolved.

    ``SCHWAB_TRADING_CALLBACK_URL`` wins when it is set; otherwise app 1's
    ``SCHWAB_CALLBACK_URL`` is used, because the common case is one callback URL
    registered on both apps. The resolved value is returned under
    ``SCHWAB_TRADING_CALLBACK_URL`` so the caller never has to know which of the
    two it got."""
    cfg = load(SCHWAB_TRADING_AUTH_FIELDS, env_path=env_path)
    if not cfg.get("SCHWAB_TRADING_CALLBACK_URL"):
        cfg["SCHWAB_TRADING_CALLBACK_URL"] = cfg["SCHWAB_CALLBACK_URL"]
    return cfg


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


# GexBot bearer for the GEX / orderflow feeds. Every reader comes through here
# (st-cir's rule for Databento, extended to GexBot 2026-09-05 when the value
# moved to the vault): no private ``.env`` parse anywhere in market/ or scripts/.
# tests/scripts/test_gexbot_env_routing.py pins that.
GEXBOT_FIELDS: tuple[Field, ...] = (
    Field("GEXBOT_API_KEY", secret=True, validators=(non_empty, no_comment_residue, no_whitespace)),
)


def load_gexbot(env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Validated config for GexBot access (the raw key; readers add the
    ``gexbot_custom_`` prefix if it is not already there)."""
    return load(GEXBOT_FIELDS, env_path=env_path)
