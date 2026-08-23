"""The survey's entities as plain dataclasses, and the DayPlan that holds a day of them.
[st-79z.3; model from docs/research/2026-07-25-trade-language-entity-survey.md §3]

Two attributes travel on everything priced: the **frame** (ES or SPX — hazard #1) and,
where a claim came from, its **quote** (the speaker's words, verbatim — provenance is
load-bearing, survey §6.8). Mancini's and Carmine's vocabularies stay separate namespaces
(st-1s1): a Level records its ``source``; nothing here ever asserts two sources' levels
are the same level.

These compose with what exists rather than replacing it: ``kind`` uses
``runbook.mancini.schema.LEVEL_KINDS``; ``state`` is the renderer spec's level state
machine; a StructureTemplate resolves through ``market.resolve`` and ``market.entities``.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Literal

from runbook.mancini.schema import LEVEL_KINDS, TRIGGER_TYPES
from strader.intent.numbers import Frame

LevelKind = Literal["support", "resistance", "pivot", "target", "trigger"]
LevelState = Literal["untouched", "tested", "held", "broken", "reclaimed"]
Direction = Literal["long", "short"]
Anchor = Literal["down", "up"]            # which way the first move went (the flush)
Vehicle = Literal["fly", "single", "vertical", "condor"]
Right = Literal["CALL", "PUT"]

# Session windows bind to the trader's profile, not the method (survey §3.5). Central time.
WINDOWS: dict[str, tuple[str, str]] = {
    "window-open": ("08:30", "09:30"),
    "window-midday": ("09:30", "13:00"),
    "window-late": ("13:00", "15:00"),
}

# Setup families decide what a direction should be, given the first move's direction.
# A trap pays AGAINST the first move; a continuation pays WITH it. This is the table the
# direction-anchor echo reasons from (knowledge/direction-inversion-watch.md).
SETUP_FAMILY: dict[str, str] = {
    "failed_breakdown": "trap", "level_reclaim": "trap", "flush_and_recover": "trap",
    "v_down": "trap", "failed_breakout": "trap", "level_reject": "trap",
    "clean_reject": "trap", "clean_break": "continuation", "breakdown_short": "continuation",
}


@dataclass(frozen=True)
class Price:
    value: float
    frame: Frame
    said: str = ""                         # the words that said it, if spoken

    def __str__(self) -> str:
        v = self.value
        return f"{v:g} {self.frame}" if v == int(v) else f"{v:.2f} {self.frame}"


@dataclass
class Level:
    price: Price
    kind: LevelKind
    tier: str = ""                          # "major" / "minor" — Mancini's annotation, or ""
    source: str = "manual"                  # mancini / carmine / manual / profile / gex / luxalgo
    label: str = ""                         # the speaker's word: shelf, consolidation, magnet, low
    price2: Price | None = None             # the far edge of a zone
    state: LevelState = "untouched"
    quote: str = ""

    def __post_init__(self) -> None:
        if self.kind not in LEVEL_KINDS:
            raise ValueError(f"level kind {self.kind!r} not in {LEVEL_KINDS}")


@dataclass
class Trigger:
    type: str                               # one of TRIGGER_TYPES
    anchors: list[Price] = field(default_factory=list)
    condition_text: str = ""
    namespace: str = "steve"                # mancini / carmine / strader / steve

    def __post_init__(self) -> None:
        if self.type not in TRIGGER_TYPES:
            raise ValueError(f"trigger type {self.type!r} not in {TRIGGER_TYPES}")


@dataclass
class Setup:
    name: str                               # failed_breakdown, level_reclaim, v_down, ...
    namespace: str = "steve"
    anchor: Price | None = None
    quality: str = ""
    state: str = "forming"                  # forming / confirmed / invalidated

    @property
    def family(self) -> str:
        return SETUP_FAMILY.get(self.name, "unknown")


@dataclass
class Regime:
    day_type: str = ""                      # b-day, trend-up, trend-down, range-chop, rotation, liquidation
    control: str = ""                       # bears / bulls / ""
    pivot: Price | None = None              # the level control is keyed to
    bias: str = ""
    tags: list[str] = field(default_factory=list)   # conditions.yaml day_context tags
    quote: str = ""


@dataclass
class SessionWindow:
    name: str
    start: str
    end: str
    owner: str = "steve"


@dataclass
class Intent:
    """One if/then unit of the day plan: when this happens, I want that."""

    trigger: Trigger
    direction: Direction
    direction_anchor: Anchor | None = None  # the first move's direction, stated before the call
    setup: Setup | None = None
    quality: str = ""
    window: str = ""                        # a WINDOWS key or ""
    management_hint: str = ""
    vehicle_hint: str = ""
    confirmed: bool = False                 # the direction-anchor echo was answered yes
    quote: str = ""

    @property
    def expected_direction(self) -> Direction | None:
        """What the setup family says the direction should be, given the anchor."""
        if self.setup is None or self.direction_anchor is None:
            return None
        fam = self.setup.family
        if fam == "trap":
            return "long" if self.direction_anchor == "down" else "short"
        if fam == "continuation":
            return "short" if self.direction_anchor == "down" else "long"
        return None

    @property
    def looks_inverted(self) -> bool:
        exp = self.expected_direction
        return exp is not None and exp != self.direction


@dataclass
class StructureTemplate:
    vehicle: Vehicle
    center: str = "ATM"                     # "ATM", "ATM+5", a label (consolidation/magnet), or a price
    width: int | None = None
    expiry: str = "0DTE"
    right: Right | None = None
    lots: int = 1
    delta_hint: str = ""                    # "first-ITM", "0.6", ...
    quote: str = ""


@dataclass
class Order:
    """One executable TOS line. Greenfield in the enterprise (survey §3.8)."""

    action: str                             # BUY / SELL
    quantity: int                           # signed: +2, -1
    spread_type: str                        # SINGLE / VERTICAL / BUTTERFLY / CONDOR
    expiry: dt.date
    strikes: tuple[float, ...]
    right: Right
    price: float
    price_kind: str = "debit"               # debit / credit
    underlying: str = "SPX"
    multiplier: int = 100
    series: str = "Weeklys"
    order_type: str = "LMT"
    tif: str = ""
    position_effect: str = "TO OPEN"
    est_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if (self.action == "BUY") != (self.quantity > 0):
            raise ValueError("action and the sign of quantity must agree (survey §3.8)")


@dataclass
class DayPlan:
    date: str
    frame_default: Frame = "ES"
    basis: float | None = None              # ES minus SPX, checked once per session
    levels: list[Level] = field(default_factory=list)
    regime: Regime = field(default_factory=Regime)
    intents: list[Intent] = field(default_factory=list)
    structures: list[StructureTemplate] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    # the one intent waiting for a yes or no, and when it was staged (ISO, Central). It
    # persists so a one-line-per-process flow (a dictation pane) can say "yes" next; go
    # refuses while it waits, and a stale one is refused rather than armed.
    pending: Intent | None = None
    pending_at: str = ""
    # the FD0 bracket for a priced directional single: a compose.Ticket.to_dict()
    # (budget-derived stop + the SPX-conditional exit fields). Computed at price
    # time, when the chain is in hand, so go can render it in a later process.
    bracket: dict | None = None

    # ------------------------------------------------------------ persistence
    def to_dict(self) -> dict[str, Any]:
        return _encode(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".partial")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DayPlan":
        return cls(
            date=d["date"],
            frame_default=d.get("frame_default", "ES"),
            basis=d.get("basis"),
            levels=[_level(x) for x in d.get("levels", [])],
            regime=_regime(d.get("regime") or {}),
            intents=[_intent(x) for x in d.get("intents", [])],
            structures=[StructureTemplate(**x) for x in d.get("structures", [])],
            orders=[_order(x) for x in d.get("orders", [])],
            unparsed=list(d.get("unparsed", [])),
            log=list(d.get("log", [])),
            pending=_intent(d["pending"]) if d.get("pending") else None,
            pending_at=d.get("pending_at", ""),
            bracket=d.get("bracket"),
        )

    @classmethod
    def load(cls, path: Path) -> "DayPlan":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- encode/decode

def _encode(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _encode(v) for k, v in asdict(obj).items()} if False else \
            {f: _encode(getattr(obj, f)) for f in obj.__dataclass_fields__}
    if isinstance(obj, dt.date):
        return obj.isoformat()
    if isinstance(obj, (list, tuple)):
        return [_encode(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    return obj


def _price(d: dict | None) -> Price | None:
    return None if d is None else Price(value=float(d["value"]), frame=d["frame"], said=d.get("said", ""))


def _level(d: dict) -> Level:
    return Level(price=_price(d["price"]), kind=d["kind"], tier=d.get("tier", ""),
                 source=d.get("source", "manual"), label=d.get("label", ""),
                 price2=_price(d.get("price2")), state=d.get("state", "untouched"),
                 quote=d.get("quote", ""))


def _regime(d: dict) -> Regime:
    return Regime(day_type=d.get("day_type", ""), control=d.get("control", ""),
                  pivot=_price(d.get("pivot")), bias=d.get("bias", ""),
                  tags=list(d.get("tags", [])), quote=d.get("quote", ""))


def _intent(d: dict) -> Intent:
    t = d["trigger"]
    s = d.get("setup")
    return Intent(
        trigger=Trigger(type=t["type"], anchors=[_price(p) for p in t.get("anchors", [])],
                        condition_text=t.get("condition_text", ""), namespace=t.get("namespace", "steve")),
        direction=d["direction"], direction_anchor=d.get("direction_anchor"),
        setup=None if s is None else Setup(name=s["name"], namespace=s.get("namespace", "steve"),
                                           anchor=_price(s.get("anchor")), quality=s.get("quality", ""),
                                           state=s.get("state", "forming")),
        quality=d.get("quality", ""), window=d.get("window", ""),
        management_hint=d.get("management_hint", ""), vehicle_hint=d.get("vehicle_hint", ""),
        confirmed=bool(d.get("confirmed", False)), quote=d.get("quote", ""),
    )


def _order(d: dict) -> Order:
    return Order(action=d["action"], quantity=int(d["quantity"]), spread_type=d["spread_type"],
                 expiry=dt.date.fromisoformat(d["expiry"]), strikes=tuple(float(s) for s in d["strikes"]),
                 right=d["right"], price=float(d["price"]), price_kind=d.get("price_kind", "debit"),
                 underlying=d.get("underlying", "SPX"), multiplier=int(d.get("multiplier", 100)),
                 series=d.get("series", "Weeklys"), order_type=d.get("order_type", "LMT"),
                 tif=d.get("tif", ""), position_effect=d.get("position_effect", "TO OPEN"),
                 est_cost_usd=float(d.get("est_cost_usd", 0.0)))
