"""Datastream health gate tests. [co-i10h]

All against the pure ``evaluate`` function with a fixed ``now`` so they are
deterministic.
"""
from datetime import datetime, timezone

from runbook.datastream import gate

NOW = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)


def _manifest(es_age_h=2, opra_age_h=2, es_cycles=124928, opra_cycles=435985,
              es_errors=None, opra_errors=None):
    from datetime import timedelta

    def stamp(age_h):
        return (NOW - timedelta(hours=age_h)).isoformat().replace("+00:00", "Z")

    return {
        "date": "2026-06-29",
        "streams": {
            "databento_glbx_es": {
                "cycles": es_cycles,
                "errors": es_errors or [],
                "last_pull_utc": stamp(es_age_h),
            },
            "databento_opra": {
                "cycles": opra_cycles,
                "errors": opra_errors or [],
                "last_pull_utc": stamp(opra_age_h),
            },
        },
    }


def test_healthy_manifest_passes():
    res = gate.evaluate(_manifest(), now=NOW)
    assert res.ok, res.reasons
    assert res.checked["databento_glbx_es"]["present"] is True


def test_missing_stream_fails():
    m = _manifest()
    del m["streams"]["databento_glbx_es"]
    res = gate.evaluate(m, now=NOW)
    assert not res.ok
    assert any("databento_glbx_es" in r and "missing" in r for r in res.reasons)


def test_missing_opra_no_longer_fails():
    """Steve halted the daily OPRA import 2026-08-07; it is ad hoc now (st-7av4).

    A gate that requires a stream nobody collects fails every morning, and a
    gate that always fails gets bypassed. Absence of OPRA is a fact about the
    collection policy, not a health failure — the measurement scripts that
    actually read the OPRA tape own their own missing-file errors.
    """
    m = _manifest()
    del m["streams"]["databento_opra"]
    res = gate.evaluate(m, now=NOW)
    assert res.ok, res.reasons


def test_zero_cycles_fails():
    res = gate.evaluate(_manifest(es_cycles=0), now=NOW)
    assert not res.ok
    assert any("no cycles" in r for r in res.reasons)


def test_errors_present_fails():
    res = gate.evaluate(_manifest(es_errors=["429 from gexbot"]), now=NOW)
    assert not res.ok
    assert any("error" in r for r in res.reasons)


def test_stale_stream_fails():
    res = gate.evaluate(_manifest(es_age_h=100), now=NOW, max_age_hours=36)
    assert not res.ok
    assert any("stale" in r for r in res.reasons)


def test_no_streams_object_fails():
    res = gate.evaluate({"date": "2026-06-29"}, now=NOW)
    assert not res.ok


def test_z_suffix_timestamp_parses():
    m = _manifest(es_age_h=1)
    # Confirm the Z-suffixed stamp the manifest writer uses round-trips.
    assert m["streams"]["databento_glbx_es"]["last_pull_utc"].endswith("Z")
    res = gate.evaluate(m, now=NOW)
    assert res.ok, res.reasons


def test_check_reads_manifest_for_the_resolved_gate_day(tmp_path, monkeypatch):
    """check(day=X) inspects the corpus manifest for exactly day X — the day
    run.py resolves via most_recent_session_day. This ties the shared day
    resolution to the file the gate actually reads: pointing it at the completed
    session's manifest (not the empty plan-day dir) is the whole point of
    Decision A. [co-i10h]
    """
    import json
    from datetime import date

    import market.corpus.paths as paths

    gate_day = date(2026, 6, 29)  # most-recent-completed session as of NOW
    monkeypatch.setattr(paths, "CORPUS_ROOT", tmp_path)

    day_dir = tmp_path / gate_day.isoformat()
    day_dir.mkdir()
    (day_dir / "manifest.json").write_text(json.dumps(_manifest()))

    # Reads tmp_path/2026-06-29/manifest.json via the corpus path convention.
    res = gate.check(day=gate_day, now=NOW)
    assert res.ok, res.reasons

    # A different day has no manifest dir — the gate fails closed, not silently.
    missing = gate.check(day=date(2026, 7, 1), now=NOW)
    assert not missing.ok
    assert any("not found" in r for r in missing.reasons)
