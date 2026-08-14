"""MBP-1 backfill authorization tests. [st-xxo0, supersedes the st-ve6 date list]

The authorization is derived from the entitlements registry at run time:
authorized while the registry's dated `databento_plan` entry says the
CME/Futures plan (GLBX.MDP3) is held live (historical GLBX is flat-rate on a
held plan — $0.00 marginal, measured 2026-08-05), refused with a stated reason
otherwise. The defect being prevented: a hardcoded approval list that goes
stale silently and leaves live capture as the only copy of MBP-1 depth.
"""
from pathlib import Path

import pytest

from scripts.corpus_daily import MBP1_PLAN_ID, mbp1_authorization


def _registry(tmp_path: Path, plan_state: str | None) -> str:
    lines = ["meta:", "  version: 1", "probed:", "dated:"]
    if plan_state is not None:
        lines += [
            f"  {MBP1_PLAN_ID}:",
            "    label: Databento — CME/Futures plan (GLBX.MDP3)",
            "    vendor: Databento",
            f"    state: {plan_state}",
            '    confirmed_on: "2026-08-04"',
            "    confirmed_by: Steve",
            "    source: Databento billing portal",
        ]
    p = tmp_path / "entitlements.yaml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def test_authorized_while_plan_active(tmp_path):
    ok, reason = mbp1_authorization(_registry(tmp_path, "active"))
    assert ok
    assert "flat-rate" in reason


def test_refused_when_plan_not_held(tmp_path):
    ok, reason = mbp1_authorization(_registry(tmp_path, "cancelled"))
    assert not ok
    assert "cancelled" in reason
    assert "usage-billed" in reason


def test_refused_when_plan_entry_missing(tmp_path):
    ok, reason = mbp1_authorization(_registry(tmp_path, None))
    assert not ok
    assert "not held live" in reason


def test_missing_registry_fails_closed_with_reason(tmp_path):
    ok, reason = mbp1_authorization(str(tmp_path / "nope.yaml"))
    assert not ok
    assert "unreadable" in reason


def test_july_date_list_is_gone():
    """The five-date July approval set was the defect (st-xxo0) — its removal
    is load-bearing, so its absence is pinned."""
    import scripts.corpus_daily as cd

    assert not hasattr(cd, "MBP1_APPROVED_DAYS")
    assert not hasattr(cd, "mbp1_approved")


def test_real_registry_currently_authorizes():
    """Against the checked-in registry: GLBX is held live as of this writing,
    so the backfill must be available. If this fails because Steve recorded a
    plan change, the refusal is correct — update this expectation with it."""
    ok, reason = mbp1_authorization()
    assert ok, reason
