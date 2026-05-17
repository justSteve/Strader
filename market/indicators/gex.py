from datetime import datetime
from zoneinfo import ZoneInfo

from market.entities.chain import Chain
from market.entities.session import Session
from market.indicators.registry import indicator
from market.signals.types import Regime

CENTRAL = ZoneInfo("America/Chicago")


@indicator(inputs=["Chain", "Session"], output="Regime", name="gex_regime")
def gex_regime(chain: Chain, session: Session) -> Regime:
    """Translate GEX posture + VIX into a market Regime signal.

    Positive GEX: dealers are long gamma. They sell rallies, buy dips,
    suppressing volatility. Result: compressed or ranging conditions.

    Negative GEX: dealers are short gamma. They buy rallies, sell dips,
    amplifying directional moves. Result: trending or volatile conditions.

    GEX posture is set externally on Session. Real GEX calculation from
    chain data (gamma exposure by strike) is deferred to a future revision.
    """
    now     = datetime.now(tz=CENTRAL)
    posture = session.gex_posture
    vix     = session.vix

    if posture == "positive":
        if vix < 13:
            return Regime(
                timestamp=now, source="gex_regime", confidence=0.8,
                reason=f"Positive GEX + low VIX ({vix:.1f}): dealers suppressing moves",
                state="compressed",
            )
        return Regime(
            timestamp=now, source="gex_regime", confidence=0.7,
            reason=f"Positive GEX + VIX {vix:.1f}: mean-reverting conditions",
            state="ranging",
        )

    if posture == "negative":
        if vix > 20:
            return Regime(
                timestamp=now, source="gex_regime", confidence=0.8,
                reason=f"Negative GEX + elevated VIX ({vix:.1f}): amplified moves expected",
                state="volatile",
            )
        return Regime(
            timestamp=now, source="gex_regime", confidence=0.65,
            reason=f"Negative GEX + VIX {vix:.1f}: directional bias, watch for follow-through",
            state="trending",
        )

    return Regime(
        timestamp=now, source="gex_regime", confidence=0.4,
        reason=f"Neutral GEX + VIX {vix:.1f}: no strong regime bias",
        state="ranging",
    )
