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


# ── the second Schwab app (st-p9mx) ──────────────────────────────────────
#
# App 1 (the unlabelled SCHWAB_* pair) carries market data and cannot trade;
# app 2 (SCHWAB_TRADING_*) carries Accounts and Trading. The env names stay
# asymmetric on purpose — renaming app 1's pair would touch both readers, four
# crons, the corpus token check, the gate hook and the vault file — so the
# disambiguation lives in these loaders instead, and nothing that picks an app
# ever reads an unlabelled name.

@pytest.fixture
def _no_schwab_in_environ(monkeypatch):
    """The convenience loaders read the process environment; a real
    SCHWAB_TRADING_* on this box would otherwise mask a missing vault entry."""
    for key in ("SCHWAB_API_KEY", "SCHWAB_APP_SECRET", "SCHWAB_CALLBACK_URL",
                "SCHWAB_TOKEN_PATH", "SCHWAB_TRADING_API_KEY",
                "SCHWAB_TRADING_APP_SECRET", "SCHWAB_TRADING_CALLBACK_URL",
                "SCHWAB_TRADING_TOKEN_PATH"):
        monkeypatch.delenv(key, raising=False)


def test_trading_pair_loads_from_the_vault(tmp_path):
    env = _env(tmp_path, "SCHWAB_TRADING_API_KEY=t-key\nSCHWAB_TRADING_APP_SECRET=t-sek\n")
    cfg = load(settings.SCHWAB_TRADING_FIELDS, env_path=env, environ={})
    assert cfg["SCHWAB_TRADING_API_KEY"] == "t-key"
    assert cfg["SCHWAB_TRADING_APP_SECRET"] == "t-sek"


def test_the_two_pairs_are_independent(tmp_path):
    """Loading one app must never fall back to the other's key. A cross-read
    here would send orders through the app that cannot trade, or market reads
    through the one that can."""
    env = _env(tmp_path, "SCHWAB_API_KEY=m-key\nSCHWAB_APP_SECRET=m-sek\n"
                         "SCHWAB_TRADING_API_KEY=t-key\nSCHWAB_TRADING_APP_SECRET=t-sek\n")
    market = load(settings.SCHWAB_FIELDS, env_path=env, environ={})
    trading = load(settings.SCHWAB_TRADING_FIELDS, env_path=env, environ={})
    assert market["SCHWAB_API_KEY"] == "m-key"
    assert trading["SCHWAB_TRADING_API_KEY"] == "t-key"
    assert "SCHWAB_API_KEY" not in trading
    assert "SCHWAB_TRADING_API_KEY" not in market


def test_a_missing_trading_pair_is_refused_not_silently_the_market_one(tmp_path):
    env = _env(tmp_path, "SCHWAB_API_KEY=m-key\nSCHWAB_APP_SECRET=m-sek\n")
    with pytest.raises(ConfigError) as ei:
        load(settings.SCHWAB_TRADING_FIELDS, env_path=env, environ={})
    assert "SCHWAB_TRADING_API_KEY" in str(ei.value)


def test_trading_secrets_in_the_tree_are_refused(tmp_path):
    """The same defence the market pair has: a secret pasted into .env fails at
    start-up naming the field, rather than later as a broker error."""
    vault = _vault(tmp_path, "SCHWAB_TRADING_API_KEY=t-key\n")
    p = tmp_path / ".env"
    p.write_text(f"{SECRETS_POINTER}={vault}\nSCHWAB_TRADING_APP_SECRET=in-the-tree\n")
    with pytest.raises(ConfigError) as ei:
        load(settings.SCHWAB_TRADING_FIELDS, env_path=p, environ={})
    assert "SCHWAB_TRADING_APP_SECRET" in str(ei.value)


def test_market_loader_is_the_unlabelled_pair(tmp_path, _no_schwab_in_environ):
    env = _env(tmp_path, "SCHWAB_API_KEY=m-key\nSCHWAB_APP_SECRET=m-sek\n")
    cfg = settings.load_schwab_market(env_path=env)
    assert cfg["SCHWAB_API_KEY"] == "m-key"
    assert settings.load_schwab(env_path=env) == cfg, "load_schwab is the market app"


def test_trading_auth_falls_back_to_the_shared_callback(tmp_path, _no_schwab_in_environ):
    """The common case: one callback URL registered on both apps. The resolved
    value comes back under the trading name so no caller has to know which of
    the two it got."""
    env = _env(tmp_path,
               "SCHWAB_TRADING_API_KEY=t-key\nSCHWAB_TRADING_APP_SECRET=t-sek\n",
               "SCHWAB_CALLBACK_URL=https://127.0.0.1:8182\n")
    cfg = settings.load_schwab_trading_auth(env_path=env)
    assert cfg["SCHWAB_TRADING_CALLBACK_URL"] == "https://127.0.0.1:8182"


def test_trading_auth_prefers_its_own_callback_when_set(tmp_path, _no_schwab_in_environ):
    env = _env(tmp_path,
               "SCHWAB_TRADING_API_KEY=t-key\nSCHWAB_TRADING_APP_SECRET=t-sek\n",
               "SCHWAB_CALLBACK_URL=https://127.0.0.1:8182\n"
               "SCHWAB_TRADING_CALLBACK_URL=https://127.0.0.1:8183\n")
    cfg = settings.load_schwab_trading_auth(env_path=env)
    assert cfg["SCHWAB_TRADING_CALLBACK_URL"] == "https://127.0.0.1:8183"


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
