"""Bounds — what the service refuses, whatever the caller asks. [st-eznu]

These are pure functions over frozen data. They take an intent, the day's
state, a quote and a clock reading, and return a :class:`Refusal` naming the
bound that stopped it, or ``None``. No I/O, no broker, no credential: the
service can therefore be argued with in a test rather than against a market.

The point of putting them here rather than in the caller is that the caller is
not trusted. The engine, the intent desk, an agent with a curl command and the
page all reach the same door, and the door is this module. Steve's start values
live in ``/etc/execd/bounds.yaml`` and are his to change; the *shape* of the
bounds is not configurable, because a bound you can switch off is not a bound.

Order of checks matters and is asserted in ``tests/execd/test_bounds.py``:
instrument, side, order type, quantity, the STOP file, the protective-stop
inputs, the session window, open positions, the daily ceiling, the price band.
Cheapest and most categorical first, so a refusal names the most fundamental
thing wrong rather than whichever check happened to run.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from . import CT_TZ
from .intent import OrderIntent, OrderType, Side

CT = ZoneInfo(CT_TZ)


@dataclass(frozen=True)
class Refusal:
    """A named 'no'. ``bound`` is the machine-readable rule; ``reason`` is what
    Steve reads in the journal and on the page."""

    bound: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"bound": self.bound, "reason": self.reason}

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"{self.bound}: {self.reason}"


@dataclass(frozen=True)
class QuoteView:
    """The two numbers a bound needs from a quote, and how old they are."""

    bid: float
    ask: float
    age_s: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def is_two_sided(self) -> bool:
        return self.bid > 0 and self.ask > 0 and self.ask >= self.bid


@dataclass(frozen=True)
class DayState:
    """What has already happened today, as the journal reconstructs it."""

    open_positions: int = 0
    realized_loss_usd: float = 0.0
    attempts_used: int = 0

    def with_attempt(self) -> "DayState":
        return replace(self, attempts_used=self.attempts_used + 1)


def _parse_hhmm(s: str, label: str) -> time:
    try:
        hh, mm = s.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        raise ValueError(f"{label} must be HH:MM in Central time, not {s!r}") from None


@dataclass(frozen=True)
class Bounds:
    """Steve's start values (design §3). Every one of these is his to change;
    none of them is his to remove."""

    instruments: tuple[str, ...] = ("SPX", "SPXW")
    qty_cap: int = 1
    max_open_positions: int = 1
    daily_loss_ceiling_usd: float = 100.0
    max_attempts: int = 2
    open_ct: str = "08:30"
    close_ct: str = "15:00"
    no_open_after_ct: str = "14:50"
    weekdays_only: bool = True
    price_band_pct: float = 0.10      # a BUY limit may sit this far above the ask
    max_quote_age_s: float = 30.0     # older than this is not a live quote
    preview_cost_tolerance_usd: float = 5.00
    require_protective_stop: bool = True

    # ── derived ──
    @property
    def open_time(self) -> time:
        return _parse_hhmm(self.open_ct, "open_ct")

    @property
    def close_time(self) -> time:
        return _parse_hhmm(self.close_ct, "close_ct")

    @property
    def no_open_after(self) -> time:
        return _parse_hhmm(self.no_open_after_ct, "no_open_after_ct")

    def problems(self) -> list[str]:
        out: list[str] = []
        if not self.instruments:
            out.append("instruments must name at least one root")
        if self.qty_cap < 1:
            out.append(f"qty_cap must be at least 1, not {self.qty_cap}")
        if self.max_open_positions < 1:
            out.append(f"max_open_positions must be at least 1, not {self.max_open_positions}")
        if self.daily_loss_ceiling_usd <= 0:
            out.append("daily_loss_ceiling_usd must be positive")
        if self.max_attempts < 1:
            out.append(f"max_attempts must be at least 1, not {self.max_attempts}")
        if not (0 < self.price_band_pct < 1):
            out.append(f"price_band_pct must be within (0, 1), not {self.price_band_pct}")
        if self.max_quote_age_s <= 0:
            out.append("max_quote_age_s must be positive")
        try:
            o, c, n = self.open_time, self.close_time, self.no_open_after
        except ValueError as exc:
            out.append(str(exc))
            return out
        if not o < c:
            out.append(f"open_ct {self.open_ct} must precede close_ct {self.close_ct}")
        if not o <= n <= c:
            out.append(f"no_open_after_ct {self.no_open_after_ct} must sit inside the window")
        return out

    def validated(self) -> "Bounds":
        probs = self.problems()
        if probs:
            raise ValueError("bounds: " + "; ".join(probs))
        return self

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Bounds":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        unknown = sorted(set(d) - known)
        if unknown:
            # Loud, not lenient: a typo in Steve's bounds file must not quietly
            # leave a bound at its default while he believes he changed it.
            raise ValueError(f"unknown bound(s) in config: {', '.join(unknown)}")
        kw = dict(d)
        if "instruments" in kw:
            kw["instruments"] = tuple(str(x).upper() for x in kw["instruments"])
        return cls(**kw).validated()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Bounds":
        import yaml

        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"bounds file not found: {p}")
        loaded = yaml.safe_load(p.read_text()) or {}
        if not isinstance(loaded, Mapping):
            raise ValueError(f"bounds file {p} must be a mapping, not {type(loaded).__name__}")
        return cls.from_dict(loaded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruments": list(self.instruments),
            "qty_cap": self.qty_cap,
            "max_open_positions": self.max_open_positions,
            "daily_loss_ceiling_usd": self.daily_loss_ceiling_usd,
            "max_attempts": self.max_attempts,
            "open_ct": self.open_ct,
            "close_ct": self.close_ct,
            "no_open_after_ct": self.no_open_after_ct,
            "weekdays_only": self.weekdays_only,
            "price_band_pct": self.price_band_pct,
            "max_quote_age_s": self.max_quote_age_s,
            "preview_cost_tolerance_usd": self.preview_cost_tolerance_usd,
            "require_protective_stop": self.require_protective_stop,
        }


# ── the checks ────────────────────────────────────────────────────────────

def check_instrument(intent: OrderIntent, bounds: Bounds) -> Refusal | None:
    try:
        occ = intent.occ
    except ValueError as exc:
        return Refusal("instrument", str(exc))
    if occ.root.upper() not in bounds.instruments:
        return Refusal(
            "instrument",
            f"{occ.root} is not tradeable by this service — "
            f"allowed: {', '.join(bounds.instruments)}",
        )
    return None


def check_window(now: datetime, bounds: Bounds, *, opening: bool) -> Refusal | None:
    """The session gate. ``opening`` applies the earlier no-new-entries cutoff."""
    local = now.astimezone(CT)
    if bounds.weekdays_only and local.weekday() >= 5:
        return Refusal("window", f"{local:%A} is not a trading day")
    cutoff = bounds.no_open_after if opening else bounds.close_time
    t = local.time()
    if t < bounds.open_time:
        return Refusal(
            "window",
            f"{t:%H:%M} CT is before the session opens at {bounds.open_ct}",
        )
    if t >= cutoff:
        label = "no new positions after" if opening else "the session closes at"
        return Refusal("window", f"{t:%H:%M} CT is past {label} {cutoff:%H:%M} CT")
    return None


def check_price_band(
    intent: OrderIntent, bounds: Bounds, quote: QuoteView | None
) -> Refusal | None:
    """A limit that is nowhere near the book is a fat finger, not an order."""
    if quote is None:
        return Refusal("price_band", "no quote for the contract — refusing to price blind")
    if quote.age_s > bounds.max_quote_age_s:
        return Refusal(
            "price_band",
            f"quote is {quote.age_s:.0f}s old, older than the "
            f"{bounds.max_quote_age_s:.0f}s this service will price against",
        )
    if not quote.is_two_sided:
        return Refusal("price_band", f"quote is not two-sided (bid {quote.bid}, ask {quote.ask})")
    if intent.order_type != OrderType.LIMIT or intent.limit is None:
        return None
    ceiling = quote.ask * (1 + bounds.price_band_pct)
    floor = quote.bid * (1 - bounds.price_band_pct)
    if intent.limit > ceiling:
        return Refusal(
            "price_band",
            f"limit {intent.limit:.2f} is more than "
            f"{bounds.price_band_pct:.0%} above the {quote.ask:.2f} ask",
        )
    if intent.limit < floor:
        return Refusal(
            "price_band",
            f"limit {intent.limit:.2f} is more than "
            f"{bounds.price_band_pct:.0%} below the {quote.bid:.2f} bid",
        )
    return None


def check_entry(
    intent: OrderIntent,
    bounds: Bounds,
    state: DayState,
    quote: QuoteView | None,
    now: datetime,
    killed: bool = False,
) -> Refusal | None:
    """Every bound an opening order must clear, in order. ``None`` means send."""
    if (r := check_instrument(intent, bounds)) is not None:
        return r

    if intent.side is not Side.BUY_TO_OPEN:
        return Refusal(
            "side",
            f"opens are long premium only — {intent.side.value} is not an opening side here",
        )

    if intent.order_type is not OrderType.LIMIT:
        return Refusal(
            "order_type",
            f"entries are LIMIT only — {intent.order_type.value} gives the book a blank cheque",
        )

    if intent.qty > bounds.qty_cap:
        return Refusal(
            "qty",
            f"{intent.qty} contracts is over the {bounds.qty_cap}-contract cap",
        )

    if killed:
        return Refusal("stop", "STOP is on — no new positions until it is cleared")

    if bounds.require_protective_stop and (intent.stop_spx is None or intent.delta is None):
        return Refusal(
            "protective_stop",
            "an entry must carry stop_spx and delta — the broker-resident stop "
            "is derived from them and is not optional",
        )

    if (r := check_window(now, bounds, opening=True)) is not None:
        return r

    if state.open_positions >= bounds.max_open_positions:
        return Refusal(
            "positions",
            f"{state.open_positions} position(s) already open — the limit is "
            f"{bounds.max_open_positions}",
        )

    if state.attempts_used >= bounds.max_attempts:
        return Refusal(
            "ceiling",
            f"{state.attempts_used} of {bounds.max_attempts} attempts used today",
        )

    if state.realized_loss_usd >= bounds.daily_loss_ceiling_usd:
        return Refusal(
            "ceiling",
            f"${state.realized_loss_usd:.2f} realized loss today has reached the "
            f"${bounds.daily_loss_ceiling_usd:.2f} ceiling",
        )

    if (r := check_price_band(intent, bounds, quote)) is not None:
        return r

    return None


def check_exit(intent: OrderIntent, bounds: Bounds,
               held_qty: int | None = None) -> Refusal | None:
    """Getting out clears almost nothing. Not the window, not the ceiling, not
    the STOP file — those all exist to stop Steve *entering* risk, and applying
    them to an exit would trap him in it.

    Three things are checked, and none of them can trap him: that the contract
    is one this service trades, that a 'close' is a close, and — only when the
    service knows what is held — that the close is not larger than the
    position. Selling more than you hold is an opening sale wearing an exit's
    label; it would leave a naked short on a long-premium-only account. When
    ``held_qty`` is ``None`` the service does not know the size (a position it
    did not open, or one it recovered without a quantity) and the order goes
    through, because refusing on ignorance is exactly how an exit gate traps
    someone."""
    if (r := check_instrument(intent, bounds)) is not None:
        return r
    if intent.side is not Side.SELL_TO_CLOSE:
        return Refusal(
            "side",
            f"an exit is SELL_TO_CLOSE — {intent.side.value} would open risk, not close it",
        )
    if held_qty is not None and intent.qty > held_qty:
        return Refusal(
            "qty",
            f"closing {intent.qty} against a position of {held_qty} would leave "
            f"a short — this service is long premium only",
        )
    return None


def check_preview_cost(
    intent: OrderIntent, previewed_usd: float, bounds: Bounds
) -> Refusal | None:
    """The last gate before a send: the broker's own arithmetic must agree with
    the intent's. A preview that costs more than the intent said is either a
    stale price or a misunderstanding, and both are reasons not to transmit."""
    expected = intent.max_cost_usd
    if expected is None:
        return None
    if previewed_usd > expected + bounds.preview_cost_tolerance_usd:
        return Refusal(
            "preview_cost",
            f"the broker prices this at ${previewed_usd:.2f} but the intent "
            f"allows ${expected:.2f} (+${bounds.preview_cost_tolerance_usd:.2f}) — not sending",
        )
    return None


def session_close(now: datetime, bounds: Bounds) -> datetime:
    """The datetime this session's arming expires: today's close in CT."""
    local = now.astimezone(CT)
    close = local.replace(
        hour=bounds.close_time.hour, minute=bounds.close_time.minute,
        second=0, microsecond=0,
    )
    if close <= local:
        close = close + timedelta(days=1)
    return close


DEFAULT_BOUNDS_PATH = Path("/etc/execd/bounds.yaml")


def load_bounds(path: str | Path | None = None) -> Bounds:
    """Steve's file if it is there, the start values if it is not. A file that
    exists but is wrong raises — silently falling back to defaults would mean
    running under bounds he did not choose."""
    p = Path(path) if path is not None else DEFAULT_BOUNDS_PATH
    if not p.exists():
        return Bounds().validated()
    return Bounds.from_yaml(p)
