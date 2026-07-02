"""Day-type classifier: compute a DayContext from a day's market read.

The playbook evaluator (``playbook_evaluator.py``) ranks strategies against a
``DayContext`` — the set of condition tags true for the day. Until now that
context was hand-declared; this module computes it, closing the loop
`market read -> DayContext -> ranked playbook`.

Design stance (co-wh19 §10 item 1, brainstormed 2026-06, implemented under
st-nk0): an **objective baseline** computed from primitives, with a **logged
subjective override** for the reads that aren't fully computable; coarse,
well-separated buckets over fine gradations; every tag assignment auditable
(provenance recorded); determinism preferred over precision.

The objective/subjective split is taken straight from ``conditions.yaml``'s
``objective:`` flags:

  - ``objective: true``    -> derived here from :class:`MarketPrimitives`
    (vol, ivr, gex, gap, magnet/room, level room, key level, confluence,
    news-scheduled).
  - ``objective: partial`` -> ``trend-up`` / ``trend-down`` / ``range-chop``:
    a subjective read, with an optional objective *baseline* from a trend slope
    when no subjective read is supplied.
  - ``objective: false``   -> ``news-adhoc``: subjective only.

Live/historical market-data binding is deferred (co-wh19 §10 item 2): the
classifier takes a declared :class:`MarketPrimitives`, not live feeds, mirroring
how the entity took declared inputs. Each primitive's docstring names the market
entity it will later be populated from (``Session``, ``GexProfile``, ``Level``).

**Thresholds are provisional.** The defaults in :class:`ClassifierConfig` are
reasonable starting points — documented, fully overridable, and awaiting Steve's
domain validation. Determinism holds regardless: the same primitives + config
always produce the same DayContext.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from strader.entities.playbook import PlaybookError, Vocabulary
from strader.evaluate.playbook_evaluator import DayContext

TrendRead = Literal["up", "down", "range"]
Provenance = Literal["objective", "objective-baseline", "subjective"]

_TREND_TAG: dict[TrendRead, str] = {
    "up": "trend-up",
    "down": "trend-down",
    "range": "range-chop",
}


@dataclass(frozen=True)
class MarketPrimitives:
    """Objective measurements for one day.

    Every field is optional; ``None`` means *not measured*, and a tag that needs
    a missing input is simply not emitted — never guessed. Field notes name the
    future source entity so the deferred live-binding layer has an obvious target.
    """

    # Volatility — future: Session.high/low range vs a typical-range history / VIX.
    realized_range: float | None = None   # today's high-low, underlying points
    typical_range: float | None = None    # recent typical high-low (ATR-like)

    # Implied-vol rank — future: options-chain IV history.
    iv_rank: float | None = None           # 0-100

    # Dealer gamma — future: Session.gex_posture / GexProfile.net_gex.
    gex_sign: Literal["neg", "pos", "neutral"] | None = None

    # Proximity to magnets/levels — future: Session.mancini_supports/resistances, Level.price.
    points_to_nearest_magnet: float | None = None  # abs points to nearest wall/magnet
    points_to_next_level: float | None = None      # clear points to the next Mancini level
    on_key_level: bool = False                     # price sitting on a Mancini level

    # Gap — future: Session.open vs prior close.
    gap_pct: float | None = None           # signed % vs prior close (+ up / - down)

    # Confluence + calendar — future: Mancini corpus x Carmine zones / econ calendar.
    mancini_carmine_confluence: bool = False
    news_scheduled: bool = False

    # Optional objective trend baseline — the read stays subjective by default.
    trend_slope: float | None = None       # normalized directional slope, ~[-1, 1]


@dataclass(frozen=True)
class ClassifierConfig:
    """Provisional, overridable thresholds. Defaults are starting points pending
    Steve's domain validation — expect them to move. Boundaries are inclusive on
    the side that fires the tag (``>=`` for high, ``<=`` for low)."""

    vol_high_ratio: float = 1.3       # realized/typical >= -> vol-high
    vol_low_ratio: float = 0.7        # realized/typical <= -> vol-low
    ivr_high: float = 50.0            # iv_rank >= -> ivr-high
    ivr_low: float = 20.0             # iv_rank <= -> ivr-low
    near_magnet_pts: float = 3.0      # points_to_nearest_magnet <= -> near-magnet
    room_to_travel_pts: float = 10.0  # points_to_nearest_magnet >= -> room-to-travel
    level_room_pts: float = 8.0       # points_to_next_level >= -> level-to-level-room
    gap_min_pct: float = 0.3          # |gap_pct| >= -> gap-up / gap-down
    trend_slope_min: float = 0.3      # |trend_slope| >= -> objective trend baseline


@dataclass(frozen=True)
class SubjectiveRead:
    """Steve's logged read for the tags that aren't fully computable."""

    trend: TrendRead | None = None    # up | down | range -> trend-up / -down / range-chop
    news_adhoc: bool = False          # unscheduled headline vol -> news-adhoc


@dataclass(frozen=True)
class Classification:
    """The computed DayContext plus per-tag provenance (auditable by design)."""

    context: DayContext
    provenance: Mapping[str, Provenance]

    @property
    def tags(self) -> frozenset[str]:
        return self.context.tags


class DayTypeClassifier:
    """Turns a day's :class:`MarketPrimitives` (+ optional :class:`SubjectiveRead`)
    into a validated :class:`Classification`."""

    def __init__(self, vocab: Vocabulary | None = None, config: ClassifierConfig | None = None):
        self.vocab = vocab if vocab is not None else Vocabulary.load()
        self.config = config if config is not None else ClassifierConfig()

    def classify(
        self,
        primitives: MarketPrimitives,
        subjective: SubjectiveRead | None = None,
    ) -> Classification:
        cfg = self.config
        p = primitives
        prov: dict[str, Provenance] = {}

        # ── objective:true tags, computed from primitives ────────────────────
        if p.realized_range is not None and p.typical_range not in (None, 0):
            ratio = p.realized_range / p.typical_range
            if ratio >= cfg.vol_high_ratio:
                prov["vol-high"] = "objective"
            elif ratio <= cfg.vol_low_ratio:
                prov["vol-low"] = "objective"

        if p.iv_rank is not None:
            if p.iv_rank >= cfg.ivr_high:
                prov["ivr-high"] = "objective"
            elif p.iv_rank <= cfg.ivr_low:
                prov["ivr-low"] = "objective"

        if p.gex_sign == "neg":
            prov["gex-neg"] = "objective"
        elif p.gex_sign == "pos":
            prov["gex-pos"] = "objective"

        if p.points_to_nearest_magnet is not None:
            if p.points_to_nearest_magnet <= cfg.near_magnet_pts:
                prov["near-magnet"] = "objective"
            elif p.points_to_nearest_magnet >= cfg.room_to_travel_pts:
                prov["room-to-travel"] = "objective"

        if p.points_to_next_level is not None and p.points_to_next_level >= cfg.level_room_pts:
            prov["level-to-level-room"] = "objective"

        if p.on_key_level:
            prov["at-key-level"] = "objective"

        if p.gap_pct is not None:
            if p.gap_pct >= cfg.gap_min_pct:
                prov["gap-up"] = "objective"
            elif p.gap_pct <= -cfg.gap_min_pct:
                prov["gap-down"] = "objective"

        if p.mancini_carmine_confluence:
            prov["mancini-carmine-confluence"] = "objective"

        if p.news_scheduled:
            prov["news-scheduled"] = "objective"

        # ── trend: subjective wins; else optional objective baseline ─────────
        if subjective is not None and subjective.trend is not None:
            prov[_TREND_TAG[subjective.trend]] = "subjective"
        elif p.trend_slope is not None:
            if p.trend_slope >= cfg.trend_slope_min:
                prov["trend-up"] = "objective-baseline"
            elif p.trend_slope <= -cfg.trend_slope_min:
                prov["trend-down"] = "objective-baseline"
            else:
                prov["range-chop"] = "objective-baseline"

        # ── news-adhoc: subjective only (objective:false) ────────────────────
        if subjective is not None and subjective.news_adhoc:
            prov["news-adhoc"] = "subjective"

        # ── integrity: every emitted tag must be a legal day_context tag ─────
        unknown = sorted(set(prov) - self.vocab.day_context)
        if unknown:
            raise PlaybookError(
                f"day classifier emitted tag(s) absent from the conditions vocabulary: "
                f"{unknown} — the classifier and conditions.yaml have drifted"
            )

        return Classification(DayContext(frozenset(prov)), dict(prov))
