import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market.entities.trade import Trade
from market.orderflow.profile import build_profile, profile_levels
from market.signals.orderflow_config import PROFILE_BUCKET_TICKS, TICK

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 7, 1, 8, 30, 0, tzinfo=CENTRAL)
BUCKET = PROFILE_BUCKET_TICKS * TICK  # 1.0 pt


def _trades(spec):
    """spec: list of (price, size). Timestamps ascend deterministically."""
    return [Trade(ts=T0 + timedelta(seconds=i), symbol="ES.c.0", instrument_id=1,
                  price=p, size=v, side="B", sequence=i)
            for i, (p, v) in enumerate(spec)]


def _bimodal():
    """Two nodes at 7500 (vol 1000 - POC) and 7510 (vol 800 - HVN) with a thin
    valley at 7505 (vol 100 - LVN); shoulders taper so extrema are clean."""
    spec = [(7500.0, 1000), (7501.0, 600), (7502.0, 400), (7503.0, 300),
            (7504.0, 200), (7505.0, 100), (7506.0, 250), (7507.0, 350),
            (7508.0, 450), (7509.0, 600), (7510.0, 800)]
    return _trades(spec)


def test_profile_histogram_and_poc():
    prof = build_profile(_bimodal())
    assert prof.bucket_pts == BUCKET
    assert prof.total == 5050
    assert prof.poc_price == 7500.0
    assert prof.prices[0] == 7500.0 and prof.prices[-1] == 7510.0
    assert len(prof.prices) == 11  # contiguous


def test_poc_tie_lower_price_wins():
    prof = build_profile(_trades([(7500.0, 500), (7501.0, 500), (7502.0, 100)]))
    assert prof.poc_price == 7500.0


def test_nodes_extracted_at_known_placements():
    levels = profile_levels(build_profile(_bimodal()), reference_price=7505.0)
    nodes = {(l.reason.split(" @ ")[0], l.price) for l in levels}
    assert ("POC", 7500.0) in nodes
    assert ("HVN", 7510.0) in nodes
    assert ("LVN", 7505.0) in nodes


def test_support_resistance_split_on_reference():
    levels = profile_levels(build_profile(_bimodal()), reference_price=7505.0)
    by = {l.price: l.level_type for l in levels}
    assert by[7500.0] == "support"        # below reference
    assert by[7510.0] == "resistance"     # above reference
    assert by[7505.0] == "resistance"     # at reference -> resistance side


def test_zero_volume_gap_buckets_are_not_lvns():
    # price jumps 7500 -> 7508: interior zero buckets must not emit LVNs
    levels = profile_levels(build_profile(_trades([(7500.0, 500), (7508.0, 400)])),
                            reference_price=7504.0)
    assert all("LVN" not in l.reason for l in levels)


def test_empty_window_raises():
    with pytest.raises(ValueError, match="zero trades"):
        build_profile([])


def test_double_build_identical():
    a = build_profile(_bimodal())
    b = build_profile(_bimodal())
    assert a == b
    assert profile_levels(a, 7505.0) == profile_levels(b, 7505.0)
