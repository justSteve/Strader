import json
from pathlib import Path
from datetime import date
from zoneinfo import ZoneInfo
from market.ingest import chain_from_schwab, session_from_mancini
from market.entities.session import Session
from market.signals.types import Regime
from market.indicators.gex import gex_regime
from mancini.parser import ManciniEmail, Level as ManciniLevel

FIXTURE = Path(__file__).parent.parent / "fixtures" / "schwab_chain_spx.json"
CENTRAL = ZoneInfo("America/Chicago")

def _chain():
    return chain_from_schwab(json.loads(FIXTURE.read_text()), expiry=date(2026, 5, 17))

def _session(gex_posture: str, vix: float = 14.8) -> Session:
    email = ManciniEmail(
        date="2026-05-17", subject="test",
        support_levels=[ManciniLevel(price=5780.0, annotation="")],
        resistance_levels=[ManciniLevel(price=5850.0, annotation="")],
    )
    quote = {"mark": 5820.5, "openPrice": 5800.0, "highPrice": 5840.0, "lowPrice": 5795.0}
    return session_from_mancini(email, quote, date(2026, 5, 17), vix=vix, gex_posture=gex_posture)

def test_returns_regime():
    assert isinstance(gex_regime(_chain(), _session("negative")), Regime)

def test_source_is_gex_regime():
    assert gex_regime(_chain(), _session("negative")).source == "gex_regime"

def test_confidence_in_range():
    r = gex_regime(_chain(), _session("negative"))
    assert 0.0 <= r.confidence <= 1.0

def test_reason_nonempty():
    assert gex_regime(_chain(), _session("negative")).reason

def test_positive_gex_low_vix_is_compressed():
    assert gex_regime(_chain(), _session("positive", vix=11.0)).state == "compressed"

def test_positive_gex_normal_vix_is_ranging():
    assert gex_regime(_chain(), _session("positive", vix=15.0)).state == "ranging"

def test_negative_gex_high_vix_is_volatile():
    assert gex_regime(_chain(), _session("negative", vix=22.0)).state == "volatile"

def test_negative_gex_normal_vix_is_trending():
    assert gex_regime(_chain(), _session("negative", vix=15.0)).state == "trending"

def test_timestamp_is_central():
    r = gex_regime(_chain(), _session("neutral"))
    assert r.timestamp.tzinfo == CENTRAL

def test_full_pipeline():
    chain = _chain()
    session = _session("negative")
    result = gex_regime(chain, session)
    assert isinstance(result, Regime)
    assert result.state in ("trending", "ranging", "volatile", "compressed")
