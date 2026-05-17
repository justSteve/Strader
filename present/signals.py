"""Format the signal feed for the tmux Signals pane."""
from __future__ import annotations
from market.signals.types import Signal, Bias, Alert, Action, Regime, InferenceRequest

_LABELS = {Bias: "BIAS", Regime: "REGIME", Alert: "ALERT", Action: "ACTION", InferenceRequest: "INFER"}


def format_signals(signals: list[Signal]) -> str:
    if not signals:
        return "  (no signals)"
    lines = ["─" * 60, "  SIGNALS"]
    for sig in signals:
        label = _LABELS.get(type(sig), "SIG")
        ts    = sig.timestamp.strftime("%H:%M:%S")
        conf  = f"{sig.confidence:.0%}"
        lines.append(f"  {ts}  [{label:<6}] {conf}  {sig.source}  {_detail(sig)}")
    lines.append("─" * 60)
    return "\n".join(lines)


def _detail(sig: Signal) -> str:
    if isinstance(sig, Bias):             return f"{sig.direction.upper()}  {sig.reason}"
    if isinstance(sig, Alert):            return f"{sig.severity.upper()}  {sig.message}"
    if isinstance(sig, Action):           return f"{sig.verb}  {sig.params}"
    if isinstance(sig, Regime):           return f"{sig.state.upper()}  {sig.reason}"
    if isinstance(sig, InferenceRequest): return f"→ {sig.question}"
    return sig.reason
