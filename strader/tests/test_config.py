"""Tests for strader.config — the fail-fast configuration layer.

Includes the direct regression for the 2026-06-30 .env → invalid_client bug and,
since 2026-09-05, the credential-estate rule: secret values come from the vault
file the pointer names, never from the in-tree .env.
"""

from __future__ import annotations

import pytest

from strader import config
from strader.config import (
    SECRETS_POINTER,
    ConfigError,
    Field,
    is_https_url,
    load,
    no_comment_residue,
    no_whitespace,
    non_empty,
    parse_dotenv,
    resolve_secrets_path,
    secrets_file_problem,
)


# ─── helpers ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_default_vault(tmp_path, monkeypatch):
    """Unit tests must never read the box's real vault. Without this, a test
    that relies on the environment fallback would silently pick up the live
    /home/vault/Strader/env through the default path (it happened 2026-09-05,
    the day the vault appeared)."""
    monkeypatch.setattr(config, "DEFAULT_SECRETS_PATH", tmp_path / "no-default-vault")


def _write_env(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text)
    return p


def _write_vault(tmp_path, text, mode=0o600):
    """A secrets file the way the vault holds it: KEY=VALUE, owner-only."""
    p = tmp_path / "vault" / "env"
    p.parent.mkdir(exist_ok=True)
    p.write_text(text)
    p.chmod(mode)
    return p


def _env_pointing_at(tmp_path, vault, extra=""):
    return _write_env(tmp_path, f"{SECRETS_POINTER}={vault}\n{extra}")


# ─── parsing ─────────────────────────────────────────────────────────────────

def test_strips_inline_comment(tmp_path):
    env = _write_env(tmp_path, "SCHWAB_API_KEY=Tob52key  # Schwab API key from https://developer.schwab.com\n")
    parsed = parse_dotenv(env)
    assert parsed["SCHWAB_API_KEY"] == "Tob52key"


def test_keeps_hash_without_preceding_space(tmp_path):
    # A '#' that is part of the value (no whitespace before it) is preserved.
    env = _write_env(tmp_path, "TOKEN=abc#def\n")
    assert parse_dotenv(env)["TOKEN"] == "abc#def"


def test_strips_quotes_and_trailing_comment(tmp_path):
    env = _write_env(tmp_path, 'CALLBACK="https://127.0.0.1:8182"  # configured in app\n')
    assert parse_dotenv(env)["CALLBACK"] == "https://127.0.0.1:8182"


def test_tolerates_export_prefix_and_blanks(tmp_path):
    env = _write_env(tmp_path, "\n# a comment line\nexport FOO=bar\n")
    assert parse_dotenv(env) == {"FOO": "bar"}


def test_missing_file_is_empty(tmp_path):
    assert parse_dotenv(tmp_path / "nope.env") == {}


# ─── the 2026-06-30 regression, now through the vault ────────────────────────

def test_vault_overrides_polluted_environment(tmp_path):
    """The exact failure mode: the process env carries a comment-polluted
    SCHWAB_API_KEY (VS Code envFile), but the clean file value must win — and
    since 2026-09-05 the clean file is the vault, not .env."""
    vault = _write_vault(tmp_path, "SCHWAB_API_KEY=Tob52key\n")
    env = _env_pointing_at(tmp_path, vault)
    polluted = {"SCHWAB_API_KEY": "Tob52key  # Schwab API key from https://developer.schwab.com (required)"}
    cfg = load([Field("SCHWAB_API_KEY", secret=True)], env_path=env, environ=polluted)
    assert cfg["SCHWAB_API_KEY"] == "Tob52key"
    assert polluted["SCHWAB_API_KEY"] == "Tob52key"  # environ republished clean


def test_comment_residue_is_rejected_fail_fast(tmp_path):
    """If a malformed value somehow reaches validation (e.g. only present in the
    environment, not in any file), fail fast with a clear message."""
    env = _write_env(tmp_path, "")  # no files → value comes from environ
    polluted = {"SCHWAB_API_KEY": "Tob52key  # comment"}
    with pytest.raises(ConfigError) as ei:
        load(
            [Field("SCHWAB_API_KEY", secret=True, validators=(no_comment_residue,))],
            env_path=env,
            environ=polluted,
        )
    assert "inline '# comment'" in str(ei.value)


# ─── the credential estate rule (2026-08-25 convention) ──────────────────────

def test_secret_in_tree_is_refused(tmp_path):
    """A secret value in .env is the thing the convention forbids. Refuse it by
    name, even when the vault also has it, so the tree copy gets removed."""
    vault = _write_vault(tmp_path, "SCHWAB_API_KEY=Tob52key\n")
    env = _env_pointing_at(tmp_path, vault, extra="SCHWAB_API_KEY=Tob52key\n")
    with pytest.raises(ConfigError) as ei:
        load([Field("SCHWAB_API_KEY", secret=True)], env_path=env, environ={})
    msg = str(ei.value)
    assert "SCHWAB_API_KEY: secret value found in .env" in msg
    assert SECRETS_POINTER in msg
    assert "Tob52key" not in msg  # never echo the value


def test_non_secret_may_live_in_env(tmp_path):
    vault = _write_vault(tmp_path, "SCHWAB_API_KEY=k\n")
    env = _env_pointing_at(tmp_path, vault, extra="SCHWAB_TOKEN_PATH=./tokens/t.json\n")
    cfg = load([Field("SCHWAB_API_KEY", secret=True), Field("SCHWAB_TOKEN_PATH")],
               env_path=env, environ={})
    assert cfg == {"SCHWAB_API_KEY": "k", "SCHWAB_TOKEN_PATH": "./tokens/t.json"}


def test_vault_wins_over_env_for_non_secrets_too(tmp_path):
    vault = _write_vault(tmp_path, "REGION=vault\n")
    env = _env_pointing_at(tmp_path, vault, extra="REGION=tree\n")
    cfg = load([Field("REGION")], env_path=env, environ={"REGION": "process"})
    assert cfg["REGION"] == "vault"


def test_secret_may_come_from_environment_when_no_file_has_it(tmp_path):
    """The process environment stays a legal source (the databento library
    reads it); only the in-tree .env is forbidden."""
    env = _write_env(tmp_path, "")
    cfg = load([Field("DATABENTO_API_KEY", secret=True)], env_path=env,
               environ={"DATABENTO_API_KEY": "db-x"})
    assert cfg["DATABENTO_API_KEY"] == "db-x"


def test_explicit_pointer_to_missing_file_is_a_problem(tmp_path):
    env = _write_env(tmp_path, f"{SECRETS_POINTER}={tmp_path / 'nowhere'}\n")
    with pytest.raises(ConfigError) as ei:
        load([Field("SCHWAB_API_KEY", secret=True)], env_path=env, environ={})
    msg = str(ei.value)
    assert "does not exist" in msg and "SCHWAB_API_KEY: missing" in msg


def test_loose_mode_vault_is_refused(tmp_path):
    """A vault file group- or world-readable is not a vault."""
    vault = _write_vault(tmp_path, "SCHWAB_API_KEY=k\n", mode=0o644)
    env = _env_pointing_at(tmp_path, vault)
    with pytest.raises(ConfigError) as ei:
        load([Field("SCHWAB_API_KEY", secret=True)], env_path=env, environ={})
    assert "mode 0644" in str(ei.value) and "0600" in str(ei.value)


def test_secrets_file_problem_accepts_0600_and_tighter(tmp_path):
    ok = _write_vault(tmp_path, "A=b\n", mode=0o600)
    assert secrets_file_problem(ok) is None
    ok.chmod(0o400)
    assert secrets_file_problem(ok) is None


def test_relative_pointer_resolves_beside_env(tmp_path):
    vault = _write_vault(tmp_path, "SCHWAB_API_KEY=k\n")
    env = _write_env(tmp_path, f"{SECRETS_POINTER}=vault/env\n")
    path, explicit = resolve_secrets_path(parse_dotenv(env), {}, env)
    assert explicit and path == vault.resolve()
    assert load([Field("SCHWAB_API_KEY", secret=True)], env_path=env, environ={})["SCHWAB_API_KEY"] == "k"


def test_pointer_from_environment_when_env_lacks_it(tmp_path):
    vault = _write_vault(tmp_path, "SCHWAB_API_KEY=k\n")
    env = _write_env(tmp_path, "")
    cfg = load([Field("SCHWAB_API_KEY", secret=True)], env_path=env,
               environ={SECRETS_POINTER: str(vault)})
    assert cfg["SCHWAB_API_KEY"] == "k"


def test_default_vault_is_used_when_present(tmp_path, monkeypatch):
    vault = _write_vault(tmp_path, "SCHWAB_API_KEY=from-default\n")
    monkeypatch.setattr(config, "DEFAULT_SECRETS_PATH", vault)
    env = _write_env(tmp_path, "")
    path, explicit = resolve_secrets_path({}, {}, env)
    assert path == vault and not explicit
    cfg = load([Field("SCHWAB_API_KEY", secret=True)], env_path=env, environ={})
    assert cfg["SCHWAB_API_KEY"] == "from-default"


def test_no_default_vault_means_no_secrets_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_SECRETS_PATH", tmp_path / "absent")
    assert resolve_secrets_path({}, {}, tmp_path / ".env") == (None, False)


# ─── validators ──────────────────────────────────────────────────────────────

def test_non_empty(tmp_path):
    env = _write_env(tmp_path, "K=\n")
    with pytest.raises(ConfigError) as ei:
        load([Field("K", validators=(non_empty,))], env_path=env, environ={})
    assert "is empty" in str(ei.value)


def test_no_whitespace(tmp_path):
    env = _write_env(tmp_path, 'K="a b"\n')
    with pytest.raises(ConfigError) as ei:
        load([Field("K", validators=(no_whitespace,))], env_path=env, environ={})
    assert "whitespace" in str(ei.value)


def test_is_https_url(tmp_path):
    env = _write_env(tmp_path, "K=http://insecure\n")
    with pytest.raises(ConfigError) as ei:
        load([Field("K", validators=(is_https_url,))], env_path=env, environ={})
    assert "https://" in str(ei.value)


def test_missing_required_key(tmp_path):
    env = _write_env(tmp_path, "")
    with pytest.raises(ConfigError) as ei:
        load([Field("NEEDED")], env_path=env, environ={})
    assert "missing" in str(ei.value)


def test_optional_key_absent_is_ok(tmp_path):
    env = _write_env(tmp_path, "")
    cfg = load([Field("MAYBE", required=False)], env_path=env, environ={})
    assert "MAYBE" not in cfg


def test_all_problems_aggregated(tmp_path):
    """Fail-fast reports every problem at once, not just the first."""
    env = _write_env(tmp_path, "A=\nB=has space\n")
    with pytest.raises(ConfigError) as ei:
        load(
            [
                Field("A", validators=(non_empty,)),
                Field("B", validators=(no_whitespace,)),
                Field("C"),  # missing
            ],
            env_path=env,
            environ={},
        )
    assert len(ei.value.problems) == 3


def test_secret_value_masked_in_error(tmp_path):
    vault = _write_vault(tmp_path, "SECRET=x y\n")
    env = _env_pointing_at(tmp_path, vault)
    with pytest.raises(ConfigError) as ei:
        load([Field("SECRET", secret=True, validators=(no_whitespace,))], env_path=env, environ={})
    # The raw secret value must not appear; the masked form does.
    assert "x y" not in str(ei.value)
    assert "SECRET set" in str(ei.value)
