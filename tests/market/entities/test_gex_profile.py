import pytest

from market.entities.gex_profile import GexProfile


def _profile(**overrides) -> GexProfile:
    defaults = dict(
        spot=5820.5,
        net_gex=2.6e11,
        net_gex_calls=1.1e12,
        net_gex_puts=-8.5e11,
        by_strike={5800.0: 6.5e10, 5810.0: 6.4e10},
    )
    defaults.update(overrides)
    return GexProfile(**defaults)


def test_profile_construction():
    p = _profile()
    assert p.spot == 5820.5
    assert p.net_gex == pytest.approx(2.6e11)
    assert 5800.0 in p.by_strike


def test_profile_is_frozen():
    p = _profile()
    with pytest.raises((AttributeError, TypeError)):
        p.net_gex = 0.0  # type: ignore
