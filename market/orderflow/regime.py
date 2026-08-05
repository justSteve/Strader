"""Meltdown-regime read from the live recognizer stream. [st-kos7 · Run You Fools]

THE INSIGHT IS STEVE'S (2026-08-05). Asked to wire a flush alert, the first
build invented a point threshold over Schwab minute closes. He pushed back:
the footprint Watcher is already engaged in these readings — is this not just
recognizing the *scale* of the flush? He was right, and the answer turned out
better than scale.

The Run You Fools playbook asks one regime question:

    "Are failed breakdowns springing today, or are breakdowns just working?"

`orderflow.recognizer` already answers it, live, per anchor level, on real
tape — and has been all along:

    failed_breakdown -> CONFIRMED    the trap sprang; price reclaimed the level.
                                     Steve's S2. A normal volatile day; his
                                     butterfly playbook applies and this one
                                     does NOT.
    failed_breakdown -> INVALIDATED  the break kept going; no reclaim came.
                                     Steve's S4. Breakdowns are working.

So the meltdown read is not a magnitude at all. It is **the balance of those
two outcomes across the session's levels**, plus the ladder property the
playbook describes: breaks happening at successively lower anchors, with
bounces dying under levels already broken.

WHAT IS MEASURED AND WHAT IS NOT. The mapping above is structural — it comes
from the recognizer's own definitions, not from a number anyone picked. The
*thresholds* below (how many invalidations, over what window, how many
distinct levels) are conventional starting points and are marked as such.
Obvious Line Formalization (st-rtuu) is the lane that measures them; until it
does, callers must treat a MELTDOWN verdict as a shadow-mode signal.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# --- PROVISIONAL thresholds — await st-rtuu --------------------------------
MIN_INVALIDATED = 3        # failed breakdowns that never reclaimed
MIN_DISTINCT_LEVELS = 2    # ...spread across at least this many anchors
MAX_CONFIRM_RATIO = 0.40   # confirmed/(confirmed+invalidated) below this
# ---------------------------------------------------------------------------

CALM, MELTDOWN, TRAPS_SPRINGING = "calm", "meltdown", "traps-springing"


@dataclass
class RegimeRead:
    """A regime verdict plus the evidence that produced it.

    The evidence is not decoration. A verdict a human cannot audit is the
    artifact class the 2026-08-04 audit warned about, and this one is meant to
    justify waking Steve up.
    """
    regime: str
    confirmed: int = 0
    invalidated: int = 0
    distinct_broken_levels: tuple[float, ...] = ()
    lowest_broken: float | None = None
    highest_broken: float | None = None
    reason: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def is_meltdown(self) -> bool:
        return self.regime == MELTDOWN


def _terminal(recognitions):
    """Only settled outcomes count. `forming` is an open question, not evidence."""
    return [r for r in recognitions
            if r.get("type") == "SetupRecognition"
            and r.get("state") in ("confirmed", "invalidated")]


def read_regime(recognitions, *, min_invalidated: int = MIN_INVALIDATED,
                min_levels: int = MIN_DISTINCT_LEVELS,
                max_confirm_ratio: float = MAX_CONFIRM_RATIO) -> RegimeRead:
    """Classify the session from settled recognizer outcomes.

    ``recognitions`` is any iterable of the dicts the live feed rides on each
    bar (``bar['ev']``). Order does not matter; this is a tally, not a
    sequence check.
    """
    settled = _terminal(recognitions)
    breaks = [r for r in settled if r.get("setup") == "failed_breakdown"]
    confirmed = [r for r in breaks if r["state"] == "confirmed"]
    invalidated = [r for r in breaks if r["state"] == "invalidated"]

    broken_levels = tuple(sorted({float(r["anchor_price"]) for r in invalidated
                                  if r.get("anchor_price") is not None}))
    n_c, n_i = len(confirmed), len(invalidated)
    ratio = n_c / (n_c + n_i) if (n_c + n_i) else 0.0

    ev = [f"{n_i} failed breakdown(s) never reclaimed",
          f"{n_c} reclaimed (trap sprang)",
          f"broken anchors: {', '.join(f'{p:g}' for p in broken_levels) or 'none'}"]

    if not breaks:
        return RegimeRead(CALM, n_c, n_i, broken_levels, reason=
                          "no settled failed-breakdown outcomes yet", evidence=ev)

    if (n_i >= min_invalidated
            and len(broken_levels) >= min_levels
            and ratio <= max_confirm_ratio):
        return RegimeRead(
            MELTDOWN, n_c, n_i, broken_levels,
            lowest_broken=broken_levels[0] if broken_levels else None,
            highest_broken=broken_levels[-1] if broken_levels else None,
            reason=(f"breakdowns are working: {n_i} unreclaimed across "
                    f"{len(broken_levels)} levels, only {n_c} trap(s) sprang"),
            evidence=ev)

    if n_c > n_i:
        return RegimeRead(TRAPS_SPRINGING, n_c, n_i, broken_levels, reason=
                          f"traps springing ({n_c} reclaimed vs {n_i} not) — "
                          f"the butterfly day, not the meltdown day",
                          evidence=ev)

    return RegimeRead(CALM, n_c, n_i, broken_levels, reason=
                      f"inconclusive: {n_i} unreclaimed across "
                      f"{len(broken_levels)} level(s), below the line",
                      evidence=ev)


def recognitions_from_bars(bars) -> list[dict]:
    """Pull every recognition off a bridge /bars payload."""
    out: list[dict] = []
    for b in bars or ():
        out.extend(e for e in (b.get("ev") or [])
                   if isinstance(e, dict) and e.get("type") == "SetupRecognition")
    return out


def summarize(recognitions) -> dict:
    """Counts by (setup, state) — for journals and for eyeballing a day."""
    c = Counter((r.get("setup"), r.get("state")) for r in recognitions
                if r.get("type") == "SetupRecognition")
    return {f"{k[0]}:{k[1]}": v for k, v in sorted(c.items(), key=lambda x: -x[1])}
