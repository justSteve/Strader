"""The verbs over a DayPlan: read, mark, call, arm, yes, no, fly, single, price, go,
stand down, show. [st-79z.3 — grammar sketch, survey §5]

Each verb takes free dictation after it and answers with a read-back. ``arm`` never arms
by itself: it stages the intent and returns the direction-anchor echo; only ``yes`` arms
it. ``go`` emits the paste string only when an order has been priced and every intent on
the plan is confirmed — and it never routes: the ticket is written as data under
``data/intent/staged/`` and the string is handed back for Steve's own hands.

The plan persists after every verb (JSON, one file per day) so a session restart, a
crash, or a second pane picks up where the last word left off.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from market.entities.chain import Chain
from market.entities.spread import ButterflyTemplate
from market.resolve import ResolutionError, resolve_butterfly
from strader.intent import grammar
from strader.intent.entities import DayPlan, Intent, Order, StructureTemplate
from strader.intent.readback import anchor_echo, order_line, read_back
from strader.intent.tos import occ_symbols, render

log = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")
DEFAULT_PLAN_DIR = Path(__file__).resolve().parents[2] / "data" / "intent"
# a staged intent older than this is refused by "yes" — say it again; the tape has moved
PENDING_MAX_MINUTES = 10
VERBS = ("read", "mark", "call", "arm", "yes", "no", "fly", "single", "price", "go",
         "stand down", "show", "frame", "basis")


class Session:
    def __init__(self, plan: DayPlan | None = None, plan_dir: Path | None = None,
                 day: dt.date | None = None, speak: bool = False) -> None:
        self.plan_dir = plan_dir or DEFAULT_PLAN_DIR
        self.day = day or dt.datetime.now(CT).date()
        self.path = self.plan_dir / f"{self.day.isoformat()}.json"
        self.speak = speak
        if plan is not None:
            self.plan = plan
        elif self.path.is_file():
            self.plan = DayPlan.load(self.path)
            log.info("intent: loaded %s", self.path)
        else:
            self.plan = DayPlan(date=self.day.isoformat())
        self._last_notes: list[str] = []

    # ---------------------------------------------------------------- plumbing
    def _save(self) -> None:
        try:
            self.plan.save(self.path)
        except OSError as e:
            log.error("intent: could not save %s: %s", self.path, e)

    def _log(self, line: str) -> None:
        stamp = dt.datetime.now(CT).strftime("%H:%M:%S")
        self.plan.log.append(f"{stamp} {line}")

    def _absorb(self, ex: grammar.Extraction) -> None:
        self.plan.levels += [lv for lv in ex.levels if not grammar._dup(lv, self.plan.levels)]
        if ex.regime:
            self.plan.regime = grammar._merge_regime(self.plan.regime if
                                                    (self.plan.regime.day_type or self.plan.regime.control)
                                                    else None, ex.regime)
        self.plan.structures += ex.structures
        self.plan.unparsed += ex.unparsed
        self._last_notes = ex.frame_notes

    @property
    def pending(self) -> Intent | None:
        return self.plan.pending

    def _stage(self, intent: Intent) -> None:
        self.plan.pending = intent
        self.plan.pending_at = dt.datetime.now(CT).isoformat(timespec="seconds")

    def _clear_pending(self) -> None:
        self.plan.pending = None
        self.plan.pending_at = ""

    def _pending_age_minutes(self) -> float | None:
        if not self.plan.pending or not self.plan.pending_at:
            return None
        try:
            staged = dt.datetime.fromisoformat(self.plan.pending_at)
        except ValueError:
            return None
        return (dt.datetime.now(CT) - staged).total_seconds() / 60

    def show(self) -> str:
        out = read_back(self.plan, speak=self.speak, notes=self._last_notes or None)
        if self.plan.pending:
            out += "\nWaiting for a yes or no: " + anchor_echo(self.plan.pending, self.speak)
        return out

    # ---------------------------------------------------------------- verbs
    def handle(self, line: str) -> str:
        """One line: a verb and its words. Unknown first word → the whole line is ``read``."""
        text = line.strip()
        if not text:
            return self.show()
        low = text.lower()
        if low.startswith("stand down"):
            return self.stand_down()
        verb, _, rest = text.partition(" ")
        verb = verb.lower().rstrip(":,")
        fn = {"read": self.read, "mark": self.mark, "call": self.call, "arm": self.arm,
              "yes": lambda _r: self.yes(), "no": lambda _r: self.no(), "fly": self.fly,
              "single": self.single, "show": lambda _r: self.show(), "go": lambda _r: self.go(),
              "frame": self.frame, "basis": self.basis}.get(verb)
        if fn is None:
            return self.read(text)
        return fn(rest)

    def read(self, text: str) -> str:
        ex = grammar.extract(text, self.plan.frame_default)
        self._absorb(ex)
        for intent in ex.intents:
            self._stage(intent)          # the last branch read is the one waiting; the
            # read-back shows it with its echo
        self._log(f"read: {text}")
        self._save()
        return self.show()

    def mark(self, text: str) -> str:
        levels, notes = grammar.extract_levels(text, self.plan.frame_default)
        if not levels:
            regime, pivots, notes = grammar.extract_regime(text, self.plan.frame_default)
            levels = pivots
        if not levels:
            self.plan.unparsed.append(text)
            self._save()
            return f"No level in: \"{text}\". Say the price and what it is — support, resistance, pivot, target."
        self.plan.levels += [lv for lv in levels if not grammar._dup(lv, self.plan.levels)]
        self._last_notes = notes
        self._log(f"mark: {text}")
        self._save()
        return self.show()

    def call(self, text: str) -> str:
        regime, pivots, notes = grammar.extract_regime(text, self.plan.frame_default)
        if regime is None:
            self.plan.unparsed.append(text)
            self._save()
            return f"No day type or control in: \"{text}\"."
        self.plan.regime = grammar._merge_regime(
            self.plan.regime if (self.plan.regime.day_type or self.plan.regime.control) else None, regime)
        self.plan.levels += [p for p in pivots if not grammar._dup(p, self.plan.levels)]
        self._last_notes = notes
        self._log(f"call: {text}")
        self._save()
        return self.show()

    def arm(self, text: str) -> str:
        intent, notes = grammar.extract_intent("arm " + text, self.plan.frame_default)
        if intent is None:
            self.plan.unparsed.append(text)
            self._save()
            return (f"No branch in: \"{text}\". Say what has to happen and which way you go — "
                    f"for example: arm the failed breakdown at sixty-four twelve, long on the reclaim.")
        self._stage(intent)
        self._last_notes = notes
        self._log(f"arm (pending): {text}")
        self._save()
        return anchor_echo(intent, self.speak)

    def yes(self) -> str:
        if self.pending is None:
            return "Nothing is waiting for a yes."
        age = self._pending_age_minutes()
        if age is not None and age > PENDING_MAX_MINUTES:
            quote = self.pending.quote
            self._clear_pending()
            self._log(f"stale pending refused ({age:.0f} min): {quote}")
            self._save()
            return (f"That was staged {age:.0f} minutes ago and the tape has moved. "
                    f"Say it again if you still want it.")
        intent = self.pending
        intent.confirmed = True
        self.plan.intents.append(intent)
        self._log(f"armed: {intent.quote} ({intent.direction}, first move {intent.direction_anchor})")
        self._clear_pending()
        self._save()
        return self.show()

    def no(self) -> str:
        if self.pending is None:
            return "Nothing is waiting for a no."
        self._log(f"dropped: {self.pending.quote}")
        self._clear_pending()
        self._save()
        return "Dropped. Say it again with the flush direction first if you want it."

    def fly(self, text: str) -> str:
        return self._structure("fly " + text)

    def single(self, text: str) -> str:
        return self._structure("single " + text)

    def _structure(self, text: str) -> str:
        s, notes = grammar.extract_structure(text, self.plan.frame_default)
        if s is None:
            self.plan.unparsed.append(text)
            self._save()
            return f"No vehicle in: \"{text}\"."
        self.plan.structures.append(s)
        self._last_notes = notes
        self._log(f"structure: {text}")
        self._save()
        return self.show()

    def frame(self, text: str) -> str:
        f = text.strip().upper()
        if f not in ("ES", "SPX"):
            return "Frame is ES or SPX."
        self.plan.frame_default = f
        self._log(f"frame default: {f}")
        self._save()
        return f"Bare prices are {f} from here on."

    def basis(self, text: str) -> str:
        try:
            self.plan.basis = float(text.strip().split()[0])
        except (ValueError, IndexError):
            return "Say the basis as a number: ES minus SPX, in points."
        self._log(f"basis: {self.plan.basis}")
        self._save()
        return f"Basis {self.plan.basis:g}: an ES price less {self.plan.basis:g} is the SPX price."

    # ---------------------------------------------------------------- pricing and go
    def price(self, chain: Chain) -> str:
        """Resolve the latest structure against a chain snapshot into an Order."""
        if not self.plan.structures:
            return "No vehicle to price. Say fly or single first."
        s = self.plan.structures[-1]
        try:
            order = self._resolve(s, chain)
        except (ResolutionError, ValueError) as e:
            self._log(f"price refused: {e}")
            return f"Could not price the {s.vehicle}: {e}"
        self.plan.orders = [order]
        self._log(f"priced: {order_line(order, False)}")
        self._save()
        string, status = render(order)
        return (f"{order_line(order, self.speak)}.\n"
                f"Paste line ({status}): {string}\n"
                f"Say go to stage it, or stand down.")

    def _resolve(self, s: StructureTemplate, chain: Chain) -> Order:
        right = s.right or "CALL"
        if s.vehicle == "fly":
            if not s.width:
                raise ValueError("a fly needs a width — say 'twenty wide'")
            center = self._center_spec(s, chain)
            inst = resolve_butterfly(ButterflyTemplate(center=center, width=s.width, expiry=s.expiry,
                                                       contract_type=right), chain)
            debit = round(inst.net_debit, 2)
            return Order(action="BUY", quantity=+s.lots, spread_type="BUTTERFLY", expiry=chain.expiry,
                         strikes=(inst.lower.strike, inst.center.strike, inst.upper.strike), right=right,
                         price=debit, price_kind="debit", est_cost_usd=debit * 100 * s.lots)
        if s.vehicle == "single":
            source = chain.calls if right == "CALL" else chain.puts
            if s.delta_hint == "first-ITM":
                # first strike in the money: calls below spot, puts above
                cands = [c for c in source.values() if (c.strike <= chain.underlying_price) == (right == "CALL")]
                if not cands:
                    raise ValueError("no in-the-money strike in the chain")
                contract = min(cands, key=lambda c: abs(c.strike - chain.underlying_price))
            else:
                contract = chain.nearest_call(chain.underlying_price) if right == "CALL" \
                    else chain.nearest_put(chain.underlying_price)
            px = round(contract.ask, 2)          # marketable limit, as FD0 does
            return Order(action="BUY", quantity=+s.lots, spread_type="SINGLE", expiry=chain.expiry,
                         strikes=(contract.strike,), right=right, price=px, price_kind="debit",
                         est_cost_usd=px * 100 * s.lots)
        raise ValueError(f"{s.vehicle} pricing is not built yet")

    def _center_spec(self, s: StructureTemplate, chain: Chain) -> str:
        c = s.center
        if c == "ATM" or c.startswith("ATM"):
            return c
        if c.replace(".", "").isdigit():
            return c
        # a label: the level on the plan that carries it, else the nearest target/pivot
        for lv in self.plan.levels:
            if lv.label == c or lv.kind == c:
                return f"{self._to_spx(lv.price):g}"
        targets = [lv for lv in self.plan.levels if lv.kind in ("target", "pivot")]
        if targets:
            return f"{self._to_spx(targets[-1].price):g}"
        raise ValueError(f"no level on the plan called '{c}' — mark it first")

    def _to_spx(self, p) -> float:
        if p.frame == "SPX":
            return p.value
        if self.plan.basis is None:
            raise ValueError(f"{p.value:g} is an ES price and no basis is set — say 'basis <points>'")
        return p.value - self.plan.basis

    def go(self) -> str:
        if self.pending is not None or any(not i.confirmed for i in self.plan.intents):
            return "An intent is waiting for a yes or no. Answer it before go."
        if not self.plan.orders:
            return "Nothing priced. Say price first."
        order = self.plan.orders[-1]
        string, status = render(order)
        stamp = dt.datetime.now(CT).strftime("%Y%m%dT%H%M%S")
        staged = self.plan_dir / "staged" / f"{stamp}-{order.spread_type.lower()}.json"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(json.dumps({
            "staged_at": dt.datetime.now(CT).isoformat(), "order": self.plan.to_dict()["orders"][-1],
            "tos": string, "tos_status": status, "occ": occ_symbols(order), "plan": self.path.name,
        }, indent=2), encoding="utf-8")
        self._log(f"go: staged {staged.name} — {string}")
        self._save()
        return (f"Staged, nothing sent. Paste this into thinkorswim ({status} shape):\n{string}\n"
                f"Legs: {', '.join(occ_symbols(order))}")

    def stand_down(self) -> str:
        self.plan.orders = []
        self._clear_pending()
        self._log("stand down")
        self._save()
        return "Standing down. Nothing priced, nothing pending."
