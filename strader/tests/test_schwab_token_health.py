"""Unit tests for the pure Schwab token-age assessor. [st-e2f]

Every status branch is exercised with an injected ``now`` and a temp token file,
so the age logic is deterministic and needs no live token or clock.
"""
from __future__ import annotations

import json
from pathlib import Path

from strader.schwab_token import (
    REFRESH_TOKEN_LIFETIME_S,
    STATUS_OK,
    STATUS_WARN,
    STATUS_CRITICAL,
    STATUS_EXPIRED,
    STATUS_DEFECTIVE,
    STATUS_MISSING,
    STATUS_MALFORMED,
    assess_token,
)

DAY = 86400
MINT = 1_784_315_602  # arbitrary fixed epoch (2026-07-17); tests are relative to it


def _write_token(tmp_path: Path, creation_ts, *, refresh: bool = True) -> Path:
    inner = {"access_token": "a" * 76, "token_type": "Bearer",
             "scope": "api", "expires_in": 1800}
    if refresh:
        inner["refresh_token"] = "r" * 140
        inner["id_token"] = "i" * 383
    doc = {"creation_timestamp": creation_ts, "token": inner}
    p = tmp_path / "schwab_token.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_ok_fresh_token(tmp_path):
    p = _write_token(tmp_path, MINT)
    h = assess_token(p, now=MINT + 1 * DAY)  # 6 days left
    assert h.status == STATUS_OK
    assert h.ok and not h.actionable
    assert h.has_refresh_token
    assert 5.9 < h.days_left < 6.1
    assert h.reauth_by_ts == MINT + REFRESH_TOKEN_LIFETIME_S


def test_warn_two_days_left(tmp_path):
    p = _write_token(tmp_path, MINT)
    h = assess_token(p, now=MINT + 5 * DAY + 1)  # just under 2 days left
    assert h.status == STATUS_WARN
    assert h.actionable and not h.ok


def test_warn_boundary_exactly_two_days(tmp_path):
    p = _write_token(tmp_path, MINT)
    h = assess_token(p, now=MINT + 5 * DAY)  # exactly 2.0 days left -> warn (<=)
    assert h.status == STATUS_WARN


def test_critical_one_day_left(tmp_path):
    p = _write_token(tmp_path, MINT)
    h = assess_token(p, now=MINT + 6 * DAY)  # exactly 1.0 day left -> critical (<=)
    assert h.status == STATUS_CRITICAL


def test_expired(tmp_path):
    p = _write_token(tmp_path, MINT)
    h = assess_token(p, now=MINT + 8 * DAY)  # 1 day past the wall
    assert h.status == STATUS_EXPIRED
    assert h.days_left < 0


def test_expired_exactly_at_wall(tmp_path):
    p = _write_token(tmp_path, MINT)
    h = assess_token(p, now=MINT + REFRESH_TOKEN_LIFETIME_S)  # days_left == 0 -> expired
    assert h.status == STATUS_EXPIRED


def test_defective_no_refresh_token_even_when_young(tmp_path):
    # The 181-byte failure: young by age, but no refresh_token -> dies within the hour.
    p = _write_token(tmp_path, MINT, refresh=False)
    h = assess_token(p, now=MINT + 60)  # one minute old
    assert h.status == STATUS_DEFECTIVE
    assert h.actionable and not h.has_refresh_token


def test_missing_file(tmp_path):
    h = assess_token(tmp_path / "nope.json", now=MINT)
    assert h.status == STATUS_MISSING
    assert h.actionable
    assert h.creation_ts is None and h.days_left is None


def test_malformed_json(tmp_path):
    p = tmp_path / "schwab_token.json"
    p.write_text("{not json", encoding="utf-8")
    h = assess_token(p, now=MINT)
    assert h.status == STATUS_MALFORMED
    assert h.actionable


def test_malformed_missing_creation_timestamp(tmp_path):
    p = tmp_path / "schwab_token.json"
    p.write_text(json.dumps({"token": {"refresh_token": "r"}}), encoding="utf-8")
    h = assess_token(p, now=MINT)
    assert h.status == STATUS_MALFORMED


def test_custom_thresholds(tmp_path):
    p = _write_token(tmp_path, MINT)
    # With a 3-day warn window, 2.5 days left should warn.
    h = assess_token(p, now=MINT + 4 * DAY + DAY // 2, warn_days_left=3.0)
    assert h.status == STATUS_WARN


def test_to_dict_is_serializable(tmp_path):
    p = _write_token(tmp_path, MINT)
    h = assess_token(p, now=MINT + 1 * DAY)
    d = h.to_dict()
    assert d["status"] == STATUS_OK
    assert d["actionable"] is False
    json.dumps(d)  # must not raise
