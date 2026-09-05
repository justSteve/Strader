"""Tests for strader.settings — the concrete Schwab / Databento / GexBot field-specs.

Secrets are written to a vault file the .env points at, never into .env itself
(strader/config.py defense 3, 2026-09-05).
"""

from __future__ import annotations

import pytest

from strader import config, settings
from strader.config import DEFAULT_ENV_PATH, SECRETS_POINTER, ConfigError, load, resolve_secrets_path


@pytest.fixture(autouse=True)
def _no_default_vault(request, tmp_path, monkeypatch):
    """Unit tests never read the box's real vault through the default path;
    only the real-env integration test below is allowed to."""
    if request.node.name == "test_real_env_passes_strict_loader":
        return
    monkeypatch.setattr(config, "DEFAULT_SECRETS_PATH", tmp_path / "no-default-vault")


def _vault(tmp_path, text):
    p = tmp_path / "vault" / "env"
    p.parent.mkdir(exist_ok=True)
    p.write_text(text)
    p.chmod(0o600)
    return p


def _env(tmp_path, secrets: str, settings_text: str = ""):
    """An in-tree .env holding the pointer and any non-secret settings, with
    ``secrets`` written to the vault file it names."""
    vault = _vault(tmp_path, secrets)
    p = tmp_path / ".env"
    p.write_text(f"{SECRETS_POINTER}={vault}\n{settings_text}")
    return p


def test_schwab_core_clean_from_vault_overrides_pollution(tmp_path):
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


def test_schwab_callback_is_a_setting_and_lives_in_env(tmp_path):
    env = _env(tmp_path, "SCHWAB_API_KEY=k\nSCHWAB_APP_SECRET=s\n",
               "SCHWAB_CALLBACK_URL=https://127.0.0.1:8182\n")
    cfg = load(settings.SCHWAB_AUTH_FIELDS, env_path=env, environ={})
    assert cfg["SCHWAB_CALLBACK_URL"] == "https://127.0.0.1:8182"


def test_schwab_api_key_rejects_whitespace(tmp_path):
    env = _env(tmp_path, 'SCHWAB_API_KEY="a b"\nSCHWAB_APP_SECRET=s\n')
    with pytest.raises(ConfigError) as ei:
        load(settings.SCHWAB_FIELDS, env_path=env, environ={})
    assert "SCHWAB_API_KEY" in str(ei.value)


def test_schwab_secret_in_tree_is_refused(tmp_path):
    """The 2026-08-25 convention, at the field level Strader actually uses."""
    env = _env(tmp_path, "SCHWAB_APP_SECRET=s\n", "SCHWAB_API_KEY=k\n")
    with pytest.raises(ConfigError) as ei:
        load(settings.SCHWAB_FIELDS, env_path=env, environ={})
    assert "SCHWAB_API_KEY: secret value found in .env" in str(ei.value)


def test_callback_must_be_https(tmp_path):
    env = _env(tmp_path, "SCHWAB_API_KEY=k\nSCHWAB_APP_SECRET=s\n",
               "SCHWAB_CALLBACK_URL=http://127.0.0.1:8182\n")
    with pytest.raises(ConfigError) as ei:
        load(settings.SCHWAB_AUTH_FIELDS, env_path=env, environ={})
    assert "https://" in str(ei.value)


def test_databento_clean_from_vault_overrides_pollution(tmp_path):
    env = _env(tmp_path, "DATABENTO_API_KEY=db-abc123\n")
    polluted = {"DATABENTO_API_KEY": "db-abc123  # metered — bounds the bill"}
    cfg = load(settings.DATABENTO_FIELDS, env_path=env, environ=polluted)
    assert cfg["DATABENTO_API_KEY"] == "db-abc123"


def test_databento_missing_fails(tmp_path):
    env = _env(tmp_path, "")
    with pytest.raises(ConfigError) as ei:
        load(settings.DATABENTO_FIELDS, env_path=env, environ={})
    assert "DATABENTO_API_KEY" in str(ei.value)


def test_gexbot_from_vault(tmp_path):
    env = _env(tmp_path, "GEXBOT_API_KEY=gexbot_custom_abc\n")
    assert settings.load_gexbot(env)["GEXBOT_API_KEY"] == "gexbot_custom_abc"


def test_gexbot_rejects_whitespace_and_tree_copies(tmp_path):
    env = _env(tmp_path, 'GEXBOT_API_KEY="a b"\n')
    with pytest.raises(ConfigError):
        settings.load_gexbot(env)
    env = _env(tmp_path, "", "GEXBOT_API_KEY=abc\n")
    with pytest.raises(ConfigError) as ei:
        settings.load_gexbot(env)
    assert "GEXBOT_API_KEY: secret value found in .env" in str(ei.value)


@pytest.mark.skipif(not DEFAULT_ENV_PATH.exists(), reason="no real .env in this environment")
def test_real_env_passes_strict_loader():
    """Integration: the repo's actual .env plus the vault it points at must
    satisfy the strict auth spec, and the secrets must not be in the tree.

    This is the guard that would have flagged the 2026-06-30 malformed
    SCHWAB_API_KEY at startup instead of as an opaque invalid_client from Schwab,
    and since 2026-09-05 the guard that a secret has not crept back into .env.
    """
    cfg = settings.load_schwab_auth()
    for key in ("SCHWAB_API_KEY", "SCHWAB_APP_SECRET", "SCHWAB_CALLBACK_URL"):
        assert cfg[key] and "#" not in cfg[key]
    path, _ = resolve_secrets_path({}, {}, DEFAULT_ENV_PATH)
    assert path is not None and path.exists(), "the real .env must resolve to a vault file"
