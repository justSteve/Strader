"""az-binary resolution for the Mancini blob fetch. [st-i68]

The 2026-07-24 06:30 cron batch died with a bare ``FileNotFoundError: 'az'``:
on this box the Azure CLI is reachable only through the WSL interop wbin dir,
which is on the interactive PATH but not cron's. These tests pin the resolution
order and — the part that actually shortens the next outage — that a miss
raises an error naming the binary and every location searched.
"""
import os
import stat

import pytest

from runbook.mancini import fetch

#: Snapshotted at import — the autouse fixture below blanks the live constant.
SHIPPED_FALLBACKS = tuple(fetch.AZ_FALLBACK_PATHS)


def _fake_az(tmp_path, name="az", executable=True):
    p = tmp_path / name
    p.write_text("#!/bin/sh\nexit 0\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return str(p)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """No env override, empty PATH, no real fallbacks — tests opt back in."""
    monkeypatch.delenv(fetch.AZ_ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(fetch, "AZ_FALLBACK_PATHS", ())


# ── env var override ────────────────────────────────────────────────────────
def test_env_var_wins(monkeypatch, tmp_path):
    override = _fake_az(tmp_path)
    on_path_dir = tmp_path / "bin"
    on_path_dir.mkdir()
    _fake_az(on_path_dir)
    monkeypatch.setenv("PATH", str(on_path_dir))
    monkeypatch.setenv(fetch.AZ_ENV_VAR, override)

    assert fetch.resolve_az() == override


def test_env_var_pointing_at_nothing_is_a_named_error(monkeypatch, tmp_path):
    monkeypatch.setenv(fetch.AZ_ENV_VAR, str(tmp_path / "nope" / "az"))

    with pytest.raises(fetch.AzCliNotFound) as exc:
        fetch.resolve_az()
    assert fetch.AZ_ENV_VAR in str(exc.value)


def test_blank_env_var_falls_through_to_path(monkeypatch, tmp_path):
    on_path_dir = tmp_path / "bin"
    on_path_dir.mkdir()
    expected = _fake_az(on_path_dir)
    monkeypatch.setenv("PATH", str(on_path_dir))
    monkeypatch.setenv(fetch.AZ_ENV_VAR, "   ")

    assert fetch.resolve_az() == expected


# ── PATH ────────────────────────────────────────────────────────────────────
def test_found_on_path(monkeypatch, tmp_path):
    on_path_dir = tmp_path / "bin"
    on_path_dir.mkdir()
    expected = _fake_az(on_path_dir)
    monkeypatch.setenv("PATH", str(on_path_dir))

    assert fetch.resolve_az() == expected


def test_path_beats_fallback(monkeypatch, tmp_path):
    on_path_dir = tmp_path / "bin"
    on_path_dir.mkdir()
    expected = _fake_az(on_path_dir)
    monkeypatch.setenv("PATH", str(on_path_dir))
    monkeypatch.setattr(fetch, "AZ_FALLBACK_PATHS", (_fake_az(tmp_path),))

    assert fetch.resolve_az() == expected


# ── fallback paths (the cron case) ──────────────────────────────────────────
def test_fallback_used_when_path_is_bare(monkeypatch, tmp_path):
    """Cron's minimal PATH: nothing on PATH, interop binary still found."""
    fallback = _fake_az(tmp_path)
    monkeypatch.setattr(fetch, "AZ_FALLBACK_PATHS", ("/does/not/exist/az", fallback))

    assert fetch.resolve_az() == fallback


def test_non_executable_fallback_is_skipped(monkeypatch, tmp_path):
    dud = _fake_az(tmp_path, name="az-dud", executable=False)
    good = _fake_az(tmp_path, name="az-good")
    monkeypatch.setattr(fetch, "AZ_FALLBACK_PATHS", (dud, good))

    assert fetch.resolve_az() == good


def test_wsl_interop_path_is_a_shipped_fallback():
    """Regression guard: the box's real az location must stay in the list."""
    assert "/mnt/c/Program Files (x86)/Microsoft SDKs/Azure/CLI2/wbin/az" in \
        SHIPPED_FALLBACKS


# ── not found anywhere ──────────────────────────────────────────────────────
def test_missing_everywhere_names_binary_and_search_trail(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "AZ_FALLBACK_PATHS", ("/does/not/exist/az",))

    with pytest.raises(fetch.AzCliNotFound) as exc:
        fetch.resolve_az()
    msg = str(exc.value)
    assert "'az'" in msg                     # names the missing binary
    assert "/does/not/exist/az" in msg       # lists where it looked
    assert "$PATH" in msg
    assert fetch.AZ_ENV_VAR in msg           # names the escape hatch


def test_not_found_is_a_runtime_error(monkeypatch):
    """run.py catches RuntimeError to keep last-good artifacts — stay catchable."""
    monkeypatch.setattr(fetch, "AZ_FALLBACK_PATHS", ())

    with pytest.raises(RuntimeError):
        fetch.resolve_az()


def test_fetch_latest_surfaces_the_named_error(monkeypatch):
    """The public entry point must not leak a bare FileNotFoundError."""
    monkeypatch.setattr(fetch, "AZ_FALLBACK_PATHS", ())

    with pytest.raises(fetch.AzCliNotFound):
        fetch.fetch_latest()


def test_resolved_binary_is_what_gets_executed(monkeypatch, tmp_path):
    """_az must invoke the resolved path, never the bare name 'az'."""
    resolved = _fake_az(tmp_path)
    monkeypatch.setattr(fetch, "AZ_FALLBACK_PATHS", (resolved,))
    seen = {}

    class _Proc:
        returncode = 0
        stdout = "ok\r\n"
        stderr = ""

    def _run(cmd, **kw):
        seen["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(fetch.subprocess, "run", _run)

    assert fetch._az("storage", "blob", "list") == "ok\n"
    assert seen["cmd"][0] == resolved
    assert os.path.isabs(seen["cmd"][0])
