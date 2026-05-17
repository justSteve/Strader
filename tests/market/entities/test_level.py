import pytest
from market.entities.level import Level

def test_level_construction():
    lev = Level(price=5780.0, label="support", source="mancini")
    assert lev.price == 5780.0
    assert lev.label == "support"
    assert lev.source == "mancini"

def test_level_is_frozen():
    lev = Level(price=5780.0, label="support", source="mancini")
    with pytest.raises((AttributeError, TypeError)):
        lev.price = 5790.0  # type: ignore

def test_level_with_annotation():
    lev = Level(price=5800.0, label="resistance", source="mancini", annotation="major")
    assert lev.annotation == "major"

def test_level_default_annotation():
    lev = Level(price=5800.0, label="resistance", source="mancini")
    assert lev.annotation == ""
