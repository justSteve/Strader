"""Meltdown-regime read from recognizer outcomes. [st-kos7]

The mapping under test is structural, not numeric: a failed breakdown that
CONFIRMS is Steve's S2 (trap sprang, butterfly day); one that INVALIDATES is
S4 (the break worked). These tests pin that mapping so a later refactor of the
recognizer cannot silently invert the regime call.
"""
from market.orderflow import regime


def _r(state, price, setup="failed_breakdown"):
    return {"type": "SetupRecognition", "setup": setup, "state": state,
            "anchor_price": price, "anchor_kind": "support"}


def test_no_settled_outcomes_is_calm():
    r = regime.read_regime([_r("forming", 7700)])
    assert r.regime == regime.CALM and not r.is_meltdown
    assert "no settled" in r.reason


def test_traps_springing_is_not_a_meltdown():
    """The butterfly day. Confirmed reclaims dominate — Run You Fools stays off."""
    rec = [_r("confirmed", 7700), _r("confirmed", 7690), _r("confirmed", 7680),
           _r("invalidated", 7670)]
    r = regime.read_regime(rec)
    assert r.regime == regime.TRAPS_SPRINGING and not r.is_meltdown
    assert "butterfly" in r.reason


def test_breakdowns_working_across_levels_is_a_meltdown():
    rec = [_r("invalidated", 7700), _r("invalidated", 7680),
           _r("invalidated", 7650), _r("confirmed", 7660)]
    r = regime.read_regime(rec)
    assert r.is_meltdown
    assert r.invalidated == 3 and r.confirmed == 1
    assert r.lowest_broken == 7650 and r.highest_broken == 7700
    assert "breakdowns are working" in r.reason


def test_one_level_broken_repeatedly_is_not_a_ladder():
    """Three invalidations at ONE anchor is a level failing, not a meltdown.
    The playbook's picture is breaks marching down successive levels."""
    rec = [_r("invalidated", 7700), _r("invalidated", 7700), _r("invalidated", 7700)]
    r = regime.read_regime(rec)
    assert not r.is_meltdown


def test_enough_traps_springing_vetoes_despite_breaks():
    """Ratio gate: breaks working AND traps springing means an unsettled day,
    not a one-way meltdown."""
    rec = [_r("invalidated", 7700), _r("invalidated", 7680), _r("invalidated", 7650),
           _r("confirmed", 7690), _r("confirmed", 7670), _r("confirmed", 7660),
           _r("confirmed", 7640)]
    r = regime.read_regime(rec)
    assert not r.is_meltdown


def test_only_failed_breakdowns_drive_the_read():
    """level_reclaim / range_trap outcomes are other setups; they must not
    contaminate the regime tally."""
    rec = [_r("invalidated", 7700, setup="level_reclaim"),
           _r("invalidated", 7680, setup="range_trap"),
           _r("invalidated", 7650, setup="return_to_lvn")]
    r = regime.read_regime(rec)
    assert r.regime == regime.CALM and r.invalidated == 0


def test_forming_is_never_evidence():
    rec = [_r("forming", p) for p in (7700, 7680, 7650, 7620)]
    assert not regime.read_regime(rec).is_meltdown


def test_evidence_is_always_populated():
    r = regime.read_regime([_r("invalidated", 7700), _r("invalidated", 7680),
                            _r("invalidated", 7650)])
    assert len(r.evidence) == 3 and any("7700" in e for e in r.evidence)


def test_recognitions_from_bars_extracts_ev():
    bars = [{"i": 1, "ev": [_r("confirmed", 7700), {"type": "Other"}]},
            {"i": 2}, {"i": 3, "ev": [_r("invalidated", 7680)]}]
    rec = regime.recognitions_from_bars(bars)
    assert len(rec) == 2 and {x["state"] for x in rec} == {"confirmed", "invalidated"}


def test_summarize_counts_by_setup_and_state():
    s = regime.summarize([_r("confirmed", 1), _r("confirmed", 2), _r("invalidated", 3)])
    assert s["failed_breakdown:confirmed"] == 2
    assert s["failed_breakdown:invalidated"] == 1
