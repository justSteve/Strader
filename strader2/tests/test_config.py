"""Tests for strader2.config — the fail-fast configuration layer.

Includes the direct regression for the 2026-06-30 .env → invalid_client bug.
"""

from __future__ import annotations

import pytest

from strader2.config import (
    ConfigError,
    Field,
    is_https_url,
    load,
    no_comment_residue,
    no_whitespace,
    non_empty,
    parse_dotenv,
)


# ─── parsing ─────────────────────────────────────────────────────────────────

def _write_env(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text)
    return p


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


# ─── the 2026-06-30 regression ───────────────────────────────────────────────

def test_env_overrides_polluted_environment(tmp_path):
    """The exact failure mode: the process env carries a comment-polluted
    SCHWAB_API_KEY (VS Code envFile), but the clean .env value must win."""
    env = _write_env(tmp_path, "SCHWAB_API_KEY=Tob52key\n")
    polluted = {"SCHWAB_API_KEY": "Tob52key  # Schwab API key from https://developer.schwab.com (required)"}
    cfg = load([Field("SCHWAB_API_KEY", secret=True)], env_path=env, environ=polluted)
    assert cfg["SCHWAB_API_KEY"] == "Tob52key"
    assert polluted["SCHWAB_API_KEY"] == "Tob52key"  # environ republished clean


def test_comment_residue_is_rejected_fail_fast(tmp_path):
    """If a malformed value somehow reaches validation (e.g. only present in the
    environment, not the file), fail fast with a clear message."""
    env = _write_env(tmp_path, "")  # empty file → value comes from environ
    polluted = {"SCHWAB_API_KEY": "Tob52key  # comment"}
    with pytest.raises(ConfigError) as ei:
        load(
            [Field("SCHWAB_API_KEY", secret=True, validators=(no_comment_residue,))],
            env_path=env,
            environ=polluted,
        )
    assert "inline '# comment'" in str(ei.value)


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
    env = _write_env(tmp_path, "SECRET=x y\n")
    with pytest.raises(ConfigError) as ei:
        load([Field("SECRET", secret=True, validators=(no_whitespace,))], env_path=env, environ={})
    # The raw secret value must not appear; the masked form does.
    assert "x y" not in str(ei.value)
    assert "SECRET set" in str(ei.value)
