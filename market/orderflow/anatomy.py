"""Setup anatomy — group the recognizer's flat emission stream into concrete
four-beat instances for the drill's anatomy mode (st-yfn).

The SetupRecognizer (st-2kf) emits one ``SetupRecognition`` each time a beat
fires (``state="forming"``) plus a terminal emission (``confirmed`` |
``invalidated``). For a *walkthrough* the trainee needs the opposite shape:
one record per engagement, carrying which bar each beat fired on so the drill
can annotate the replay beat-by-beat.

Reconstruction is exact, not heuristic. Per anchor the recognizer keeps at
most one live engagement (``_active`` keyed by anchor identity) and blocks
re-engagement until price crosses back — so for a fixed ``(anchor_price,
anchor_kind)`` the emissions are strictly ordered ``flush → … → terminal``,
and a terminal closes one instance. A beat's firing bar is the bar of the
emission that first introduced it into ``beats``; ``timestamp == bar.end_ts``
maps back to the bar index (bars here are the *same* FootprintBar list the
drill serializes, so the index is identical to ``DATA.bars``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from market.entities.footprint import FootprintBar
from market.signals.orderflow import SetupRecognition

# Canonical beat order + a one-line teaching gloss the drill shows as each
# beat is reached. Kept here (not the template) so the vocabulary has one home.
BEAT_ORDER = ("flush", "stall", "flip", "confirm", "extend")
BEAT_GLOSS = {
    "flush":   "Aggression breaks past the level — the trap is set.",
    "stall":   "The break stops being rewarded: force without effect (absorption).",
    "flip":    "Delta turns against the break — the other side seizes control.",
    "confirm": "Price re-takes the level with opposite evidence — reversal confirmed.",
    "extend":  "Delta extended through the node instead of stalling — acceptance (proposed read).",
}


@dataclass(frozen=True)
class BeatFire:
    beat: str
    bar: int          # index into the bar list (== DATA.bars index)
    clock: str        # HH:MM:SS CT, the bar's end time
    reason: str       # the recognizer's own words for this emission


@dataclass
class SetupInstance:
    setup: str
    bias: str
    anchor_price: float
    anchor_kind: str
    mancini: bool
    state: str                       # confirmed | invalidated | forming (EOD-open)
    start_bar: int                   # the flush bar
    end_bar: int                     # the terminal bar
    confidence: float
    headline: str                    # terminal emission's reason
    beats: list[BeatFire] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "setup": self.setup, "bias": self.bias,
            "anchor_price": self.anchor_price, "anchor_kind": self.anchor_kind,
            "mancini": self.mancini, "state": self.state,
            "start_bar": self.start_bar, "end_bar": self.end_bar,
            "confidence": round(self.confidence, 3), "headline": self.headline,
            "beats": [{"beat": b.beat, "bar": b.bar, "clock": b.clock,
                       "reason": b.reason, "gloss": BEAT_GLOSS.get(b.beat, "")}
                      for b in self.beats],
        }


def _clock(bar: FootprintBar) -> str:
    return bar.end_ts.isoformat()[11:19]


def build_instances(
    recs: Sequence[SetupRecognition], bars: Sequence[FootprintBar]
) -> list[SetupInstance]:
    """Fold a recognizer emission stream into completed engagement instances.

    ``bars`` must be the exact list the recognitions were produced from.
    """
    ts_to_idx = {b.end_ts: i for i, b in enumerate(bars)}
    # group emissions per anchor, preserving stream order
    per_anchor: dict[tuple[float, str], list[SetupRecognition]] = {}
    for r in recs:
        per_anchor.setdefault((round(r.anchor_price, 4), r.anchor_kind), []).append(r)

    instances: list[SetupInstance] = []
    for stream in per_anchor.values():
        seen: set[str] = set()
        cur: SetupInstance | None = None
        for r in stream:
            idx = ts_to_idx.get(r.timestamp, -1)
            if cur is None:
                cur = SetupInstance(
                    setup=r.setup, bias=r.bias, anchor_price=r.anchor_price,
                    anchor_kind=r.anchor_kind, mancini=r.mancini_confluence,
                    state=r.state, start_bar=idx, end_bar=idx,
                    confidence=r.confidence, headline=r.reason,
                )
                seen = set()
            # a later emission may refine setup/bias (e.g. LVN accept branch)
            cur.setup, cur.bias = r.setup, r.bias
            cur.state, cur.end_bar = r.state, idx
            cur.confidence, cur.headline = r.confidence, r.reason
            for beat in r.beats:
                if beat not in seen:
                    seen.add(beat)
                    clock = _clock(bars[idx]) if 0 <= idx < len(bars) else ""
                    cur.beats.append(BeatFire(beat, idx, clock, r.reason))
            if r.state in ("confirmed", "invalidated"):
                instances.append(cur)
                cur = None
        if cur is not None:      # engagement still open at end of day
            instances.append(cur)
    instances.sort(key=lambda x: (x.start_bar, x.anchor_price))
    return instances


# ranking for the walkthrough list: confirmed first (best teaching material),
# then richer invalidated instances; forming-at-EOD last.
_STATE_RANK = {"confirmed": 0, "invalidated": 1, "forming": 2}


def anatomy_payload(
    instances: Iterable[SetupInstance], top: int | None = 12, min_beats: int = 1
) -> list[dict]:
    """JSON-friendly, ranked, capped list for embedding in the drill.

    Bare flush→invalidate (the level simply broke) is kept but ranks below
    anything that reached a flip; confirmed instances always lead.
    """
    kept = [i for i in instances if len(i.beats) >= min_beats]
    kept.sort(key=lambda x: (
        _STATE_RANK.get(x.state, 3),
        -len(x.beats),
        -x.confidence,
        x.start_bar,
    ))
    if top is not None:
        kept = kept[:top]
    return [i.to_payload() for i in kept]
