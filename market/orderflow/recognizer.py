"""Four-beat SetupRecognizer — Carmine setups from the bar stream (st-2kf, spec §3).

One parameterized state machine, not four bespoke detectors. Every setup is
the same rhythm relative to an anchor level L:

  beat 1 ``flush``   — a bar trades ≥ ENGAGE_PENETRATION_TICKS beyond L with
                       aggression in the break direction. Intensity names the
                       setup at support/resistance anchors: |Δ| ≥ FLUSH_DELTA_MIN
                       is a violent break; |Δ| ≤ QUIET_DELTA_MAX is a quiet one;
                       in between counts as violent. At a SUPPORT (break is
                       down) that is failed_breakdown / level_reclaim, the long;
                       at a RESISTANCE (break is up) it is the mirror,
                       failed_breakout / level_reject, the short [st-q5xu] —
                       the same four beats read upward: push above, stall,
                       delta flips down, close back beneath. Range edges are
                       range_trap; LVN anchors are return_to_lvn regardless of
                       intensity.
  beat 2 ``stall``   — aggression continues in the break direction but the
                       extreme extends ≤ STALL_EXTENSION_TICKS: force without
                       effect (the trades-only absorption proxy).
  beat 3 ``flip``    — a bar's Δ turns against the break by ≥ FLIP_DELTA_MIN.
  beat 4 ``confirm`` — a bar closes back across L in the resolution direction
                       with an opposite-direction ImbalanceStack, or (stacks
                       are structurally rare at N=2000 — see config note)
                       opposite Δ ≥ CONFIRM_DELTA_MIN.  → state ``confirmed``.

Lifecycle per (anchor, engagement): forming → confirmed | invalidated
(INVALIDATE_TICKS beyond L, or ENGAGEMENT_WINDOW_BARS without confirm).
Score-don't-gate: every new beat emits a ``forming`` recognition with the
beats so far; nothing is suppressed. Confirmed requires flush+flip+confirm;
stall raises confidence but is not required (its absence is the weaker-
instance case, not a non-event).

``return_to_lvn`` additionally has the ACCEPT branch — delta *extends*
through the node instead of stalling — emitted with "proposed" in the reason:
the two-branch read is the research doc's synthesis, not established
practice, and is validated empirically, not experientially.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Iterable, Literal

from market.entities.footprint import FootprintBar
from market.entities.level import Level as EntityLevel
from strader.entities.singleton import SingletonSetup
from market.orderflow.imbalance import find_stacks
from market.signals.orderflow import SetupRecognition
from market.signals.orderflow_config import (
    CONFIRM_DELTA_MIN,
    CONFLUENCE_TOLERANCE_PTS,
    ENGAGE_PENETRATION_TICKS,
    ENGAGEMENT_WINDOW_BARS,
    FLIP_DELTA_MIN,
    FLUSH_DELTA_MIN,
    INVALIDATE_TICKS,
    QUIET_DELTA_MAX,
    STALL_EXTENSION_TICKS,
    TICK,
)

logger = logging.getLogger(__name__)

AnchorKind = Literal["support", "resistance", "range_high", "range_low", "lvn"]

# which way each anchor kind gets engaged (break direction): -1 down, +1 up.
# LVN is direction-neutral — engagement direction comes from the approach.
_ENGAGE_DIR: dict[str, int] = {
    "support": -1, "range_low": -1,
    "resistance": +1, "range_high": +1,
}


@dataclass(frozen=True)
class Anchor:
    price: float
    kind: AnchorKind
    label: str = ""            # e.g. "mancini 7541" / "profile LVN"
    mancini: bool = False      # set by the caller, or via mancini_prices below


class _Engagement:
    __slots__ = ("anchor", "direction", "setup", "beats", "extreme", "age", "done")

    def __init__(self, anchor: Anchor, direction: int, setup: str, extreme: float):
        self.anchor = anchor
        self.direction = direction      # break direction: -1 down, +1 up
        self.setup = setup
        self.beats: list[str] = ["flush"]
        self.extreme = extreme          # most-adverse price reached beyond L
        self.age = 0
        self.done = False


class SetupRecognizer:
    """Feed completed bars in order; collect SetupRecognition signals.

    ``mancini_prices``: any anchor within CONFLUENCE_TOLERANCE_PTS of one of
    these carries ``mancini_confluence=True`` on every emission — the input
    the day-classifier's highest-weighted tag consumes.
    """

    def __init__(self, anchors: Iterable[Anchor], mancini_prices: Iterable[float] = ()):
        self.anchors = list(anchors)
        mp = list(mancini_prices)
        self._confluent = {
            id(a): a.mancini or any(abs(a.price - m) <= CONFLUENCE_TOLERANCE_PTS for m in mp)
            for a in self.anchors
        }
        self._active: dict[int, _Engagement] = {}   # id(anchor) -> engagement
        # after an engagement closes, the anchor is blocked until price
        # returns whole-bar to the pre-break side — no instant re-engagement
        # while price still sits beyond the level (value = break direction)
        self._blocked: dict[int, int] = {}
        self._prev_close: float | None = None
        # per-anchor confirmed-fire counter [st-98z item 2] — keyed like
        # _active/_blocked on id(anchor). Deliberately NEVER cleared: the
        # count survives block/re-engage cycles because it is the anchor's
        # session-long fire history, and it feeds ``fire_index`` (spoken and
        # displayed — the 4th call at a level is a different call from the
        # 1st). It no longer damps confidence: st-98z's 31%-vs-48% fi≥4
        # cliff (p=.019 on the old 65-day body) does not generalize — on the
        # enriched corpus no fire threshold shows a supported step on either
        # side (bullish fi≥4 42% vs 47%, p=.275; bearish 52% vs 48%, p=.448)
        # [st-7kmt, docs/measurement/fire-index-rederivation-2026-08-19.md].
        self._fires: dict[int, int] = {}

    # ── per-bar drive ───────────────────────────────────────────────────────
    def on_bar(self, bar: FootprintBar) -> list[SetupRecognition]:
        out: list[SetupRecognition] = []
        for a in self.anchors:
            key = id(a)
            if key in self._blocked:
                d = self._blocked[key]
                cleared = bar.low >= a.price if d < 0 else bar.high <= a.price
                if not cleared:
                    continue
                del self._blocked[key]
            eng = self._active.get(key)
            if eng is None:
                eng = self._try_engage(a, bar)
                if eng is not None:
                    self._active[key] = eng
                    out.append(self._emit(eng, bar, "forming"))
                continue
            out.extend(self._advance(eng, bar))
            if eng.done:
                del self._active[key]
                self._blocked[key] = eng.direction
        self._prev_close = bar.close
        return out

    def is_idle(self, anchor: Anchor) -> bool:
        """True when ``anchor`` has no engagement forming and is not blocked.

        Anchors carry their state in ``_active``/``_blocked`` keyed on ``id``,
        so an idle anchor is one with no state to lose. [st-b0n9]
        """
        key = id(anchor)
        return key not in self._active and key not in self._blocked

    def retarget(self, anchor: Anchor, price: float) -> Anchor | None:
        """Move an IDLE anchor to a new price; return the replacement, or None.

        A live session's range edges develop with the tape, so the recognizer
        has to be able to move a level it is watching (see
        market.orderflow.anchors.LiveAnchors). ``Anchor`` is frozen, so the
        move is a swap, not a mutation — and because engagement state is keyed
        on ``id(anchor)``, a swap of an ENGAGED anchor would silently orphan
        that state. Hence the guard lives here, with the state, rather than in
        the caller: an engaged or blocked anchor refuses to move and the caller
        gets None.
        """
        if not self.is_idle(anchor):
            return None
        # Identity, not equality: Anchor has dataclass value semantics, and
        # index() would happily find a different anchor that merely compares
        # equal.
        i = next((k for k, a in enumerate(self.anchors) if a is anchor), None)
        if i is None:
            return None
        new = replace(anchor, price=price)
        self.anchors[i] = new
        self._confluent[id(new)] = self._confluent.pop(id(anchor), new.mancini)
        # Carry the fire history: this is the SAME anchor ("day high") at a new
        # price, not a new one. Dropping it would quietly re-arm the >= 4th-fire
        # damping every time the session made a new extreme.
        if id(anchor) in self._fires:
            self._fires[id(new)] = self._fires.pop(id(anchor))
        return new

    def run(self, bars: Iterable[FootprintBar]) -> list[SetupRecognition]:
        sigs: list[SetupRecognition] = []
        for b in bars:
            sigs.extend(self.on_bar(b))
        return sigs

    # ── beat 1 ──────────────────────────────────────────────────────────────
    def _try_engage(self, a: Anchor, bar: FootprintBar) -> _Engagement | None:
        pen = ENGAGE_PENETRATION_TICKS * TICK
        if a.kind == "lvn":
            if self._prev_close is None:
                return None
            direction = -1 if self._prev_close > a.price else +1
        else:
            direction = _ENGAGE_DIR[a.kind]
        beyond = (a.price - bar.low) if direction < 0 else (bar.high - a.price)
        if beyond < pen:
            return None
        # proximity gate [st-98z item 4]: an engagement born at/beyond
        # invalidation depth is provably unconfirmable — _advance checks
        # invalidation first, from an extreme already ≥ INVALIDATE_TICKS, so
        # the engagement dies before the confirm branch can ever run. This is
        # noise elimination (a far-off anchor engaging on the first with-break
        # bar of the session), not scoring suppression: genuine flushes engage
        # within a few ticks of the level.
        if beyond >= INVALIDATE_TICKS * TICK:
            logger.debug("no engage @ %.2f: first bar already %.1f ticks beyond "
                         "(>= INVALIDATE_TICKS=%d)", a.price, beyond / TICK,
                         INVALIDATE_TICKS)
            return None
        # aggression must point with the break; a drift-through is no beat 1
        if direction * bar.delta < 0:
            return None
        mag = abs(bar.delta)
        if a.kind in ("range_high", "range_low"):
            setup = "range_trap"
        elif a.kind == "lvn":
            setup = "return_to_lvn"
        elif a.kind == "resistance":
            # the upside mirror [st-q5xu]: the name says which way the break
            # went, because "failed_breakdown @ 7815 (resistance)" on a push
            # ABOVE 7815 is unreadable — Mancini's Failed Breakdown is the
            # long; this is the bull trap, the short.
            setup = "level_reject" if mag <= QUIET_DELTA_MAX else "failed_breakout"
        else:
            setup = "level_reclaim" if mag <= QUIET_DELTA_MAX else "failed_breakdown"
        extreme = bar.low if direction < 0 else bar.high
        logger.debug("engage %s @ %.2f (%s, |Δ|=%d)", setup, a.price, a.kind, mag)
        return _Engagement(a, direction, setup, extreme)

    # ── beats 2-4, invalidation, LVN accept branch ─────────────────────────
    def _advance(self, eng: _Engagement, bar: FootprintBar) -> list[SetupRecognition]:
        out: list[SetupRecognition] = []
        d, L = eng.direction, eng.anchor.price
        eng.age += 1
        new_extreme = min(eng.extreme, bar.low) if d < 0 else max(eng.extreme, bar.high)
        extended = abs(new_extreme - eng.extreme) / TICK

        # invalidation: acceptance beyond the level — the break was real
        beyond = (L - new_extreme) if d < 0 else (new_extreme - L)
        if beyond / TICK >= INVALIDATE_TICKS:
            eng.extreme = new_extreme
            # LVN accept branch: the node offered no resistance (proposed read)
            if eng.setup == "return_to_lvn" and d * bar.delta >= FLIP_DELTA_MIN:
                eng.beats.append("extend")
                eng.done = True
                key = id(eng.anchor)
                self._fires[key] = self._fires.get(key, 0) + 1
                out.append(self._emit(eng, bar, "confirmed", accept_branch=True))
                return out
            eng.done = True
            out.append(self._emit(eng, bar, "invalidated"))
            return out

        # beat 2 — stall: aggression continues, extreme barely extends
        if "stall" not in eng.beats and d * bar.delta > 0 and extended <= STALL_EXTENSION_TICKS:
            eng.beats.append("stall")
            out.append(self._emit(eng, bar, "forming"))

        # beat 3 — flip: delta turns against the break
        if "flip" not in eng.beats and -d * bar.delta >= FLIP_DELTA_MIN:
            eng.beats.append("flip")
            out.append(self._emit(eng, bar, "forming"))

        # beat 4 — confirm: close back across L with opposite evidence
        if "flip" in eng.beats and "confirm" not in eng.beats:
            reclosed = bar.close > L if d < 0 else bar.close < L
            if reclosed:
                want = "buy" if d < 0 else "sell"
                stacked = any(s.direction == want for s in find_stacks(bar))
                if stacked or -d * bar.delta >= CONFIRM_DELTA_MIN:
                    eng.beats.append("confirm")
                    eng.done = True
                    key = id(eng.anchor)
                    self._fires[key] = self._fires.get(key, 0) + 1
                    out.append(self._emit(eng, bar, "confirmed", stacked=stacked))

        eng.extreme = new_extreme
        if not eng.done and eng.age >= ENGAGEMENT_WINDOW_BARS:
            eng.done = True
            out.append(self._emit(eng, bar, "invalidated"))
        return out

    # ── emission ────────────────────────────────────────────────────────────
    def _emit(self, eng: _Engagement, bar: FootprintBar, state: str,
              stacked: bool = False, accept_branch: bool = False) -> SetupRecognition:
        bias = "bullish" if eng.direction < 0 else "bearish"
        if accept_branch:  # node accepted the move: bias follows the break
            bias = "bearish" if eng.direction < 0 else "bullish"
        # fire_index: which confirmed fire this engagement is (1-based) for its
        # anchor. On a confirmed emission the counter was just incremented, so
        # it IS this fire's number; on forming/invalidated the counter holds
        # prior confirms, so this engagement would be fire prior+1.
        fired = self._fires.get(id(eng.anchor), 0)
        fire_index = fired if state == "confirmed" else fired + 1
        # confirmed confidence: base 0.8, 0.9 with stacked imbalance. The
        # st-98z fi>=4 step-damp (0.8→0.6) was removed 2026-08-19 [st-7kmt]:
        # its cliff does not reproduce on the enriched corpus on either side
        # (see the _fires note above). fire_index still rides every emission
        # for consumers to weigh — score-don't-gate cuts both ways: a score
        # must not encode evidence the corpus no longer supports.
        conf = {"forming": min(0.75, 0.2 + 0.15 * len(eng.beats)),
                "confirmed": 0.9 if stacked else 0.8,
                "invalidated": 0.0}[state]
        # "stages", never "beats" — the four-part sequence collides with the
        # musical sense and Steve reads this string directly in the emissions
        # panel's "why the stack said it" column. The internal field is still
        # named `beats`; renaming it touches the replay records, the anatomy
        # payload and the template together, which is st-g9y's job. [st-emy5]
        # "no reclaim" is the downside word (price never came back over a
        # lost support); the mirror at a resistance is price holding above it.
        never_back = "no reclaim" if eng.direction < 0 else "held above, no reject"
        words = {
            "forming": f"stages so far: {'+'.join(eng.beats)}",
            "confirmed": ("confirmed with stacked imbalance" if stacked
                          else "confirmed on opposite delta"),
            "invalidated": f"{never_back} (stages: {'+'.join(eng.beats)})",
        }[state]
        proposed = " [proposed two-branch LVN read — validate empirically]" \
            if eng.setup == "return_to_lvn" else ""
        if accept_branch:
            words = "ACCEPT branch: delta extended through the node, no stall-stage"
        return SetupRecognition(
            timestamp=bar.end_ts, source="orderflow.recognizer",
            confidence=conf,
            reason=(f"{eng.setup} {state} @ {eng.anchor.price:.2f} "
                    f"({eng.anchor.kind}{' ∩ mancini' if self._confluent[id(eng.anchor)] else ''}): "
                    f"{words}{proposed}"),
            setup=eng.setup, bias=bias,
            anchor_price=eng.anchor.price, anchor_kind=eng.anchor.kind,
            state=state, beats=tuple(eng.beats),
            mancini_confluence=self._confluent[id(eng.anchor)],
            fire_index=fire_index,
        )


# ── consumer wiring (spec §6) ───────────────────────────────────────────────
def to_singleton_setup(rec: SetupRecognition) -> SingletonSetup:
    """A confirmed recognition carries exactly what the trade idea needs."""
    if rec.state != "confirmed":
        raise ValueError(f"only confirmed recognitions become setups (got {rec.state})")
    anchor = EntityLevel(
        price=rec.anchor_price,
        label="support" if rec.bias == "bullish" else "resistance",
        source="mancini" if rec.mancini_confluence else "manual",
        annotation=rec.anchor_kind,
    )
    return SingletonSetup(bias=rec.bias, trigger=rec.setup, anchor=anchor,  # type: ignore[arg-type]
                          mancini_confluence=rec.mancini_confluence)


def orderflow_confirm(recs: Iterable[SetupRecognition], bias: str) -> bool:
    """The conditions.yaml Tier-2 ``orderflow-confirm`` tag: a confirmed
    recognition agreeing with the entry direction."""
    return any(r.state == "confirmed" and r.bias == bias for r in recs)
