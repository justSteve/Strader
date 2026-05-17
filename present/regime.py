"""Format regime and session context for the tmux Regime pane."""
from __future__ import annotations
from market.entities.session import Session
from market.signals.types import Regime

_STATE_LABELS = {
    "compressed": "COMPRESSED  ■ low vol expected",
    "ranging":    "RANGING     ↔ mean-reverting",
    "trending":   "TRENDING    → follow-through",
    "volatile":   "VOLATILE    ⚡ amplified moves",
}


def format_regime(regime: Regime, session: Session) -> str:
    lines = [
        "─" * 50,
        f"  REGIME  {_STATE_LABELS.get(regime.state, regime.state.upper())}",
        f"  Confidence: {regime.confidence:.0%}   GEX: {session.gex_posture.upper()}   VIX: {session.vix:.1f}",
        f"  {regime.reason}",
        "─" * 50,
        f"  SPX {session.underlying_price:.2f}   O {session.open:.0f}  H {session.high:.0f}  L {session.low:.0f}",
        "",
        "  SUPPORTS",
    ]
    for lev in sorted(session.mancini_supports, key=lambda l: l.price, reverse=True):
        tag = f" [{lev.annotation}]" if lev.annotation else ""
        lines.append(f"    {lev.price:>8.1f}{tag}")
    lines += ["", "  RESISTANCES"]
    for lev in sorted(session.mancini_resistances, key=lambda l: l.price):
        tag = f" [{lev.annotation}]" if lev.annotation else ""
        lines.append(f"    {lev.price:>8.1f}{tag}")
    lines.append("─" * 50)
    return "\n".join(lines)
