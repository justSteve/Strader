"""Tests for strader2.settings — the concrete Schwab field-specs."""

from __future__ import annotations

import pytest

from strader2 import settings
from strader2.config import DEFAULT_ENV_PATH, ConfigError, load


def _env(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text)
    return p


def test_schwab_core_clean_from_env_overrides_pollution(tmp_path):
    env = _env(tmp_path, "SCHWAB_API_KEY=Tob52key\nSCHWAB_APP_SECRET=sek\n")
    polluted = {"SCHWAB_API_KEY": "Tob52key  # Schwab API key from https://developer.schwab.com"}
    cfg = load(settings.SCHWAB_FIELDS, env_path=env, environ=polluted)
    assert cfg["SCHWAB_API_KEY"] == "Tob52key"


def test_schwab_core_does_not_require_callback(tmp_path):
    env = _env(tmp_path, "SCHWAB_API_KEY=k\nSCHWAB_APP_SECRET=s\n")
    cfg = load(settings.SCHWAB_FIELDS, env_path=env, environ={})
    assert "SCHWAB_CALLBACK_URL" not in cfg  # broker client must not need it


def test_schwab_auth_requires_callback(tmp_path):
    env = _env(tmp_path, "SCHWAB_API_KEY=k\nSCHWAB_APP_SECRET=s\n")  # no callback
    with pytest.raises(ConfigError) as ei:
        load(settings.SCHWAB_AUTH_FIELDS, env_path=env, environ={})
    assert "SCHWAB_CALLBACK_URL" in str(ei.value)


def test_schwab_api_key_rejects_whitespace(tmp_path):
    env = _env(tmp_path, 'SCHWAB_API_KEY="a b"\nSCHWAB_APP_SECRET=s\n')
    with pytest.raises(ConfigError) as ei:
        load(settings.SCHWAB_FIELDS, env_path=env, environ={})
    assert "SCHWAB_API_KEY" in str(ei.value)


def test_callback_must_be_https(tmp_path):
    env = _env(tmp_path, "SCHWAB_API_KEY=k\nSCHWAB_APP_SECRET=s\nSCHWAB_CALLBACK_URL=http://127.0.0.1:8182\n")
    with pytest.raises(ConfigError) as ei:
        load(settings.SCHWAB_AUTH_FIELDS, env_path=env, environ={})
    assert "https://" in str(ei.value)


def test_databento_clean_from_env_overrides_pollution(tmp_path):
    env = _env(tmp_path, "DATABENTO_API_KEY=db-abc123\n")
    polluted = {"DATABENTO_API_KEY": "db-abc123  # metered — bounds the bill"}
    cfg = load(settings.DATABENTO_FIELDS, env_path=env, environ=polluted)
    assert cfg["DATABENTO_API_KEY"] == "db-abc123"


def test_databento_missing_fails(tmp_path):
    env = _env(tmp_path, "")
    with pytest.raises(ConfigError) as ei:
        load(settings.DATABENTO_FIELDS, env_path=env, environ={})
    assert "DATABENTO_API_KEY" in str(ei.value)


@pytest.mark.skipif(not DEFAULT_ENV_PATH.exists(), reason="no real .env in this environment")
def test_real_env_passes_strict_loader():
    """Integration: the repo's actual .env must satisfy the strict auth spec.

    This is the guard that would have flagged the 2026-06-30 malformed
    SCHWAB_API_KEY at startup instead of as an opaque invalid_client from Schwab.
    """
    cfg = settings.load_schwab_auth()
    for key in ("SCHWAB_API_KEY", "SCHWAB_APP_SECRET", "SCHWAB_CALLBACK_URL"):
        assert cfg[key] and "#" not in cfg[key]
