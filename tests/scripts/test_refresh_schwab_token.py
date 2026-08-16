"""Re-auth script guards — the grant gate and backup hygiene. [st-r1b5]

The age logic itself is covered in strader/tests/test_schwab_token_health.py.
What is tested here is the thing that actually failed on 2026-08-12: the re-auth
script accepted a grant that could never be refreshed, because its only check
was a live API call and that call *succeeds* on a defective token.

The defective fixture below is the real one, byte-shape for byte-shape: a
28-char access token, expires_in 1800, no refresh_token, no id_token — the
"181-byte file" that `strader/schwab_token.py` already names. Reproducing its
shape rather than inventing one keeps this test honest about what Schwab
actually returned.

No network, no OAuth, no real token: every case runs against a tmp file.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import scripts.refresh_schwab_token as rst
from strader.schwab_token import STATUS_DEFECTIVE, STATUS_EXPIRED, STATUS_MISSING

DAY = 86400


def _write(path: Path, doc: dict) -> Path:
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _healthy(creation_ts: int | None = None) -> dict:
    return {
        "creation_timestamp": int(time.time()) if creation_ts is None else creation_ts,
        "token": {
            "expires_in": 1800,
            "token_type": "Bearer",
            "scope": "api",
            "refresh_token": "r" * 140,
            "access_token": "a" * 76,
            "id_token": "i" * 383,
        },
    }


def _defective(creation_ts: int | None = None) -> dict:
    """The 2026-08-12 grant. Note it is *young* and its access token *works* —
    that is exactly why the live probe waved it through."""
    return {
        "creation_timestamp": int(time.time()) if creation_ts is None else creation_ts,
        "token": {
            "expires_in": 1800,
            "token_type": "Bearer",
            "scope": "api",
            "access_token": "a" * 28,
        },
    }


# --------------------------------------------------------------------------
# The gate


def test_gate_accepts_a_complete_fresh_grant(tmp_path):
    p = _write(tmp_path / "schwab_token.json", _healthy())
    health = rst._grant_gate(p)
    assert health.ok
    assert health.has_refresh_token
    assert 6.9 < health.days_left <= 7.0


def test_gate_rejects_defective_grant_despite_being_young(tmp_path):
    """The regression. A 200 from the API would not have caught this."""
    p = _write(tmp_path / "schwab_token.json", _defective())
    with pytest.raises(rst.DefectiveGrant) as exc:
        rst._grant_gate(p)
    assert exc.value.health.status == STATUS_DEFECTIVE
    assert exc.value.health.has_refresh_token is False
    # The operator has to be able to read why, not just that.
    assert "refresh_token" in str(exc.value)


def test_gate_rejects_a_token_already_past_the_wall(tmp_path):
    p = _write(tmp_path / "schwab_token.json", _healthy(int(time.time()) - 8 * DAY))
    with pytest.raises(rst.DefectiveGrant) as exc:
        rst._grant_gate(p)
    assert exc.value.health.status == STATUS_EXPIRED


def test_gate_rejects_a_missing_file(tmp_path):
    """A flow that silently wrote nothing must not read as success."""
    with pytest.raises(rst.DefectiveGrant) as exc:
        rst._grant_gate(tmp_path / "schwab_token.json")
    assert exc.value.health.status == STATUS_MISSING


# --------------------------------------------------------------------------
# Backup hygiene — a bad run must not be able to destroy the last good token


def test_backup_is_timestamped_not_a_single_slot(tmp_path):
    p = _write(tmp_path / "schwab_token.json", _healthy())
    first = rst._backup(p)
    assert first is not None
    assert ".bak-" in first.name
    # A second run writes a *different* file even when the source changed.
    _write(p, _defective())
    second = rst._backup(p)
    assert second is not None and second != first
    # The original good token is still on disk, unmodified.
    assert json.loads(first.read_text())["token"]["refresh_token"] == "r" * 140


def test_backup_returns_none_when_there_is_nothing_to_back_up(tmp_path):
    assert rst._backup(tmp_path / "schwab_token.json") is None


def test_prune_keeps_the_newest_n(tmp_path):
    p = tmp_path / "schwab_token.json"
    stamps = [f"2026080{i}T120000Z" for i in range(1, 8)]
    for s in stamps:
        _write(p.with_suffix(p.suffix + f".bak-{s}"), _healthy())
    rst._prune_backups(p, keep=3)
    left = sorted(q.name for q in tmp_path.glob("schwab_token.json.bak-*"))
    assert len(left) == 3
    assert left == [f"schwab_token.json.bak-{s}" for s in stamps[-3:]]


def test_prune_is_a_no_op_below_the_limit(tmp_path):
    p = tmp_path / "schwab_token.json"
    _write(p.with_suffix(p.suffix + ".bak-20260801T120000Z"), _healthy())
    rst._prune_backups(p, keep=10)
    assert len(list(tmp_path.glob("schwab_token.json.bak-*"))) == 1


def test_prune_ignores_the_live_token_and_other_siblings(tmp_path):
    """Globbing must not sweep up the token itself or the .rejected evidence."""
    p = _write(tmp_path / "schwab_token.json", _healthy())
    _write(p.with_suffix(p.suffix + ".rejected"), _defective())
    for i in range(1, 5):
        _write(p.with_suffix(p.suffix + f".bak-2026080{i}T120000Z"), _healthy())
    rst._prune_backups(p, keep=1)
    assert p.exists()
    assert p.with_suffix(p.suffix + ".rejected").exists()
    assert len(list(tmp_path.glob("schwab_token.json.bak-*"))) == 1


# --------------------------------------------------------------------------
# Evidence stashing


def test_stash_copies_without_moving_the_original(tmp_path):
    p = _write(tmp_path / "schwab_token.json", _defective())
    dest = rst._stash(p, ".rejected")
    assert dest is not None and dest.exists()
    assert p.exists()
    assert json.loads(dest.read_text()) == json.loads(p.read_text())


def test_stash_returns_none_when_the_source_is_absent(tmp_path):
    assert rst._stash(tmp_path / "schwab_token.json", ".rejected") is None


def test_stash_is_timestamped_so_a_second_failure_keeps_the_first(tmp_path):
    """A bare `.new` / `.rejected` is one slot; the second failure would erase
    the first attempt's evidence. Same hazard `_backup` was fixed for [st-r1b5],
    and the reason a `.new` sat unnoticed for three months (co-03ojd.7 J-F10)."""
    p = _write(tmp_path / "schwab_token.json", _healthy())
    first = rst._stash(p, ".new")
    assert first is not None and ".new-" in first.name
    _write(p, _defective())
    second = rst._stash(p, ".new")
    assert second is not None and second != first
    assert first.exists() and second.exists()
    # The first rescue still holds the first grant, untouched.
    assert json.loads(first.read_text())["token"]["refresh_token"] == "r" * 140


# --------------------------------------------------------------------------
# Rescue sweeping — success is the only moment a rescue copy is provably stale


def test_sweep_removes_rescue_copies_including_the_legacy_bare_name(tmp_path):
    p = _write(tmp_path / "schwab_token.json", _healthy())
    legacy = _write(p.with_suffix(p.suffix + ".new"), _healthy())          # pre-2026-08-16
    stamped = _write(p.with_suffix(p.suffix + ".new-20260520T185744Z"), _healthy())
    removed = rst._sweep_rescues(p)
    assert set(removed) == {legacy, stamped}
    assert not legacy.exists() and not stamped.exists()
    assert p.exists()


def test_sweep_keeps_rejected_evidence_and_backups(tmp_path):
    """Rejected copies are forensic evidence of a defective mint, not a stale
    credential — sweeping them would delete the only record of what Schwab
    returned. Backups are the restore path and are pruned by count, not here."""
    p = _write(tmp_path / "schwab_token.json", _healthy())
    rejected = _write(p.with_suffix(p.suffix + ".rejected-20260812T100120Z"), _defective())
    bak = _write(p.with_suffix(p.suffix + ".bak-20260812T100000Z"), _healthy())
    assert rst._sweep_rescues(p) == []
    assert rejected.exists() and bak.exists() and p.exists()


def test_prune_copies_is_anchored_per_kind(tmp_path):
    """Pruning one kind must not see another kind's copies."""
    p = _write(tmp_path / "schwab_token.json", _healthy())
    for i in range(1, 5):
        _write(p.with_suffix(p.suffix + f".new-2026080{i}T120000Z"), _healthy())
    _write(p.with_suffix(p.suffix + ".bak-20260801T120000Z"), _healthy())
    rst._prune_copies(p, "new", keep=2)
    assert len(list(tmp_path.glob("schwab_token.json.new-*"))) == 2
    assert len(list(tmp_path.glob("schwab_token.json.bak-*"))) == 1
    assert p.exists()
