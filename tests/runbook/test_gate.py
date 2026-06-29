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
    del m["streams"]["databento_opra"]
    res = gate.evaluate(m, now=NOW)
    assert not res.ok
    assert any("databento_opra" in r and "missing" in r for r in res.reasons)


def test_zero_cycles_fails():
    res = gate.evaluate(_manifest(es_cycles=0), now=NOW)
    assert not res.ok
    assert any("no cycles" in r for r in res.reasons)


def test_errors_present_fails():
    res = gate.evaluate(_manifest(opra_errors=["429 from gexbot"]), now=NOW)
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
