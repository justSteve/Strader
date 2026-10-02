"""The scenario harness — the real service over the real paper book on a tape. [st-ug1h]

Wired the way ``execd/__main__.py`` wires the Schwab instance in paper mode::

    ModeSwitch(PaperBroker(transport, book_path=<state>/paper-book.json), transport, "paper")

with the transport a :class:`~.market.ReplayMarket` instead of Schwab, the
clock the conftest's movable ``Clock`` instead of the wall, and the
``Watcher`` driven one pass at a time (``Watcher.once``) instead of on its
thread. Everything else is production code, unmodified: ``ExecService``,
``PaperBroker`` (whose ``_sweep`` fills stops, targets and resting entries
against the tape's quotes), the order form's pricing (``orderform.price`` /
``intent_for`` — the CLI behind the page's SEND), the page itself when a
scenario asks for it.

A scenario is a sequence of steps — ``tick`` (time passes: the watcher's
pass), ``send``, ``adjust``, ``cancel``, ``flatten``, ``lock``/``unlock``,
``restart`` — and after every step :func:`.invariants.check` runs. A
violation raises :class:`~.invariants.InvariantViolation` naming the
invariant and printing the whole sequence so far, CT-stamped, with the
index, the contract's quote and what the step did.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from execd.bounds import Bounds
from execd.broker import OrderResult, OrderStatus
from execd.intent import OrderIntent, OrderType, Side
from execd.orderform import Priced, Selection, intent_for, price
from execd.paper import ModeSwitch, PaperBroker
from execd.service import ExecService, ServiceConfig
from execd.watch import Watcher

from ..conftest import Clock
from .invariants import InvariantViolation, Memory, Violation, check
from .known_bugs import require
from .market import ReplayMarket
from .tape import CT, Tape


class Scenario:
    """One run: a tape, a state directory, the service and its paper book."""

    def __init__(self, tape: Tape, state_dir: Path, *, bounds: Bounds | None = None,
                 funds: float = 250_000.0, unlock: bool = True, strict: bool = True,
                 waive: dict[str, str] | None = None,
                 book: type[PaperBroker] = PaperBroker,
                 triggered_bracket: bool = False) -> None:
        self.tape = tape
        #: the entry sent with its bracket as one triggered order — off in
        #: production since 2026-10-02 (st-jdk7); on for a scenario of that path
        self.triggered_bracket = triggered_bracket
        #: the paper book's class — ``PaperBroker``; ``faults.FaultBook`` only
        #: for a scenario that needs a broker behaviour the book does not model
        self.book_cls = book
        self.state_dir = Path(state_dir)
        self.bounds = bounds or Bounds()          # production defaults: 5x, trailing on
        self.clock = Clock(tape.start)
        self.market = ReplayMarket(tape, self.clock, funds=funds)
        self.book_path = self.state_dir / "paper-book.json"
        self.memory = Memory()
        #: raise at the first violation (``True``), or collect them all
        self.strict = strict
        #: invariant name → the known-bug key it is set aside for. Only an
        #: open entry in ``known_bugs.KNOWN`` naming that invariant may be cited.
        self.waived: dict[str, str] = {}
        for name, key in (waive or {}).items():
            if name not in [n.strip() for n in require(key)["invariant"].split(",")]:
                raise ValueError(f"{key} is about {require(key)['invariant']}, not {name}")
            self.waived[name] = key
        self.violations: list[tuple[str, Violation]] = []
        self.log: list[str] = []
        #: has a reconcile run since the last step that lost an answer? The
        #: ``open_mismatch`` check waits for one: "after reconcile settles"
        self.reconciled = True
        self._page = None
        self._seq = 0
        self._journal_seen = 0
        self._jpath: Path | None = None
        self._jpos = 0
        self._jlines: list[dict[str, Any]] = []
        self._build()
        if unlock:
            self.unlock()

    # ── wiring (execd/__main__.py, paper mode) ───────────────────────────
    def _build(self) -> None:
        self.paper = self.book_cls(self.market, book_path=self.book_path, clock=self.clock)
        self.broker = ModeSwitch(self.paper, self.market, "paper")
        config = ServiceConfig(state_dir=self.state_dir / "execd", bounds=self.bounds,
                               sha="scenario", mode="paper", broker="schwab",
                               triggered_bracket=self.triggered_bracket)
        self.service = ExecService(self.broker, config, clock=self.clock)
        self.watcher = Watcher(self.service, sleep=lambda _s: None)
        self._page = None
        self._journal_seen = len(self.journal())

    # ── reading the scene ────────────────────────────────────────────────
    @property
    def elapsed(self) -> float:
        return (self.clock() - self.tape.start).total_seconds()

    @property
    def spx(self) -> float:
        return self.tape.spx_at(self.clock())

    def quote(self, symbol: str):
        return self.market.quote_at(symbol, self.clock())

    def position(self, symbol: str):
        return self.service._open.get(symbol)

    def working(self, symbol: str | None = None) -> list[OrderResult]:
        return [o for o in self.paper._orders.values() if o.status is OrderStatus.WORKING
                and (symbol is None or o.symbol == symbol)]

    def resting(self, symbol: str) -> dict[str, list[float]]:
        sells = [o for o in self.working(symbol) if o.side is Side.SELL_TO_CLOSE]
        return {"stop": sorted(o.price for o in sells if o.order_type is OrderType.STOP),
                "target": sorted(o.price for o in sells if o.order_type is OrderType.LIMIT)}

    def held(self) -> dict[str, int]:
        return {s: p.qty for s, p in self.paper._positions.items() if p.qty}

    def journal(self) -> list[dict[str, Any]]:
        """Today's journal, parsed — read incrementally (the harness asks
        after every step; the service's own reads are the service's)."""
        path = self.service.journal.path_for()
        if path != self._jpath:
            self._jpath, self._jpos, self._jlines = path, 0, []
        try:
            with path.open("rb") as fh:
                fh.seek(self._jpos)
                chunk = fh.read()
        except FileNotFoundError:
            return self._jlines
        end = chunk.rfind(b"\n") + 1
        for raw in chunk[:end].decode("utf-8").splitlines():
            if raw.strip():
                self._jlines.append(json.loads(raw))
        self._jpos += end
        return self._jlines

    def events(self, *names: str) -> list[dict[str, Any]]:
        wanted = set(names)
        return [e for e in self.journal() if e.get("event") in wanted]

    def closes(self) -> list[dict[str, Any]]:
        return self.events("closed")

    def realized(self) -> float:
        """The day's closes net of fees — what the day total sums (st-ocnp)."""
        return round(sum(float(e.get("net_pnl_usd", e.get("pnl_usd")) or 0)
                         for e in self.closes()), 2)

    def status_pnl(self) -> float | None:
        return self.service._day_pnl([])["realized_usd"]

    # ── the steps ────────────────────────────────────────────────────────
    def step(self, label: str, fn: Callable[[], Any] | None = None, *,
             raises: type[BaseException] | tuple[type[BaseException], ...] | None = None) -> Any:
        """Run one step and check every invariant after it. ``raises`` names
        an exception the step is expected to end in (a send whose answer is
        lost): it is caught, logged and returned, and the checks still run."""
        before = getattr(self.service, "_last_reconcile_at", None)
        try:
            out = fn() if fn is not None else None
        except Exception as exc:  # noqa: BLE001 — re-raised unless expected
            if raises is None or not isinstance(exc, raises):
                self._record(f"{label} — raised {type(exc).__name__}: {exc}", None)
                raise
            out = exc
            label = f"{label} — raised {type(exc).__name__}: {exc}"
            # an answer was lost: the book may hold what the service has not
            # been told, until a reconcile has looked
            self.reconciled = False
        else:
            if getattr(self.service, "_last_reconcile_at", None) != before:
                self.reconciled = True
        self._record(label, out)
        self.check(label)
        return out

    def tick(self, seconds: float = 3.0) -> dict[str, Any]:
        """Time passes by ``seconds`` and the watcher makes one pass: the
        reconcile (fills booked, the book's sweep run), the SPX-mark exit
        loop, the trailing stop."""
        self.clock.advance(seconds=seconds)

        return self.step("tick", self.watcher.once)

    def run(self, seconds: float, *, every: float = 3.0,
            until: Callable[["Scenario"], bool] | None = None) -> None:
        """Tick for ``seconds`` (or until ``until`` says stop)."""
        end = self.elapsed + seconds
        while self.elapsed + every <= end + 1e-9:
            self.tick(every)
            if until is not None and until(self):
                return

    def to_end(self, every: float = 3.0) -> None:
        self.run(self.tape.length_s - self.elapsed, every=every)

    def wait_until(self, t: float) -> None:
        """Move the clock to ``t`` seconds into the tape without a watcher
        pass — the box asleep, or simply between beats."""
        self.clock.set(self.tape.start + timedelta(seconds=t))

    def ticket(self, side: str = "call", **sel: Any) -> Priced:
        """The order form's priced ticket for a selection — ``strike``,
        ``delta``, ``lots``, ``limit`` (the padlock), ``stopoff`` (the stop
        box, dollars under the limit per contract), ``exitspx`` (the close-at
        box), ``stop`` (a typed stop)."""
        args = {"side": side, **{k: v for k, v in sel.items() if v is not None}}
        return price(self.service, Selection.from_args(
            {k: str(v) for k, v in args.items()}, today=self.clock().astimezone(CT).date(),
            lots_cap=99))

    def intent(self, ticket: Priced, intent_id: str | None = None) -> OrderIntent:
        self._seq += 1
        iid = intent_id or f"scn-{self._seq:03d}"
        return OrderIntent.from_dict(intent_for(ticket, intent_id=iid, engine_sha="scenario"))

    def send(self, what: Priced | OrderIntent, *, intent_id: str | None = None,
             label: str | None = None, raises: Any = None) -> dict[str, Any]:
        """SEND: the ticket's intent through ``ExecService.place``."""
        intent = what if isinstance(what, OrderIntent) else self.intent(what, intent_id)
        return self.step(label or f"send {intent.intent_id} {intent.symbol.strip()} "
                                  f"x{intent.qty} @ {intent.limit}"
                                  + (f" stop {intent.stop_price}" if intent.stop_price else "")
                                  + (f" stop_spx {intent.stop_spx}" if intent.stop_spx else ""),
                         lambda: self.service.place(intent), raises=raises)

    def adjust(self, symbol: str, **legs: float) -> dict[str, Any]:
        """Steve moves a leg on the card (price or SPX-level form)."""
        self.memory.hand_adjusted.add(symbol)
        return self.step("adjust " + " ".join(f"{k}={v}" for k, v in legs.items()),
                         lambda: self.service.adjust(symbol, **legs))

    def cancel(self, order_id: str) -> dict[str, Any]:
        return self.step(f"cancel {order_id}", lambda: self.service.cancel(order_id))

    def flatten(self) -> dict[str, Any]:
        return self.step("flatten", lambda: self.service.flatten())

    def exit(self, symbol: str, qty: int) -> dict[str, Any]:
        intent = OrderIntent(intent_id=f"scn-exit-{self.elapsed:.0f}", symbol=symbol,
                             side=Side.SELL_TO_CLOSE, qty=qty, order_type=OrderType.MARKET,
                             source="scenario")
        return self.step(f"exit {symbol.strip()} x{qty}", lambda: self.service.place(intent))

    def lock(self) -> dict[str, Any]:
        return self.step("lock", self.service.lock)

    def unlock(self) -> dict[str, Any]:
        return self.step("unlock", lambda: self.service.unlock({"token": "scenario"}))

    def restart(self, *, unlock: bool = True) -> None:
        """The process dies and comes back: a new ``PaperBroker`` loads the
        book from its file, a new ``ExecService`` replays the journal over
        the same state directory, and it starts LOCKED until unlocked."""
        self._build()
        self._record("restart", {"recovered": sorted(s.strip() for s in self.service._open),
                                 "working": sorted(self.service._working)})
        self.check("restart")
        if unlock:
            self.unlock()

    # ── the page (execd/page.py), built over this service on demand ─────
    def page(self):
        if self._page is None:
            self._page = _page_client(self)
        return self._page

    # ── checking ─────────────────────────────────────────────────────────
    def check(self, label: str) -> list[Violation]:
        found = [v for v in check(self) if v.name not in self.waived]
        self.violations.extend((label, v) for v in found)
        if found and self.strict:
            raise InvariantViolation(label, found, self.log_text())
        return found

    def _record(self, label: str, out: Any) -> None:
        now = self.clock()
        new = self.journal()[self._journal_seen:]
        self._journal_seen += len(new)
        events = [e.get("event") for e in new if e.get("event") not in (
            "order_raw", "request", "preview", "preview_raw")]
        held = ", ".join(f"{s.strip()} x{q}" for s, q in self.held().items()) or "flat"
        quotes = []
        for sym in sorted({o.symbol for o in self.paper._orders.values()} | set(self.held())):
            try:
                q = self.quote(sym)
                quotes.append(f"{sym.strip()[-9:]} {q.bid:.2f}/{q.ask:.2f}")
            except Exception:  # noqa: BLE001
                pass
        self.log.append(
            f"  t+{self.elapsed:7.1f}s {now.astimezone(CT):%H:%M:%S} CT  SPX {self.spx:8.2f}  "
            f"{label}\n      held: {held}; quotes: {'; '.join(quotes[-3:]) or '-'}\n"
            f"      journal: {', '.join(events) or '-'}")

    def log_text(self, last: int = 60) -> str:
        head = f"  tape {self.tape.name}: {self.tape.note}\n" if self.tape.note else ""
        return head + "\n".join(self.log[-last:])


def _page_client(scn: Scenario):
    """The order page over the scenario's service, as the page tests build
    it (``tests/execd/test_orderform.py``'s ``order_page``)."""
    import httpx

    from execd.page import CredentialFile, create_page
    from execd.vault import Vault

    from ..conftest import same_origin
    from ..test_page import CALLBACK, PASS, Schwab, market_payload, vault_payload

    root = scn.state_dir / "page"
    root.mkdir(parents=True, exist_ok=True)
    vault = Vault(root / "vault.json")
    if not (root / "vault.json").exists():
        vault.store(vault_payload(), PASS)
    mfile = root / "market.json"
    mfile.write_text(json.dumps(market_payload()))
    market = CredentialFile(mfile)
    market.load()

    class Mono:
        t = 1000.0

        def __call__(self):
            return self.t

    app = create_page(scn.service, vault=vault, market=market, callback_url=CALLBACK,
                      http_client=httpx.Client(base_url="https://api.schwabapi.com",
                                               transport=httpx.MockTransport(Schwab())),
                      clock=scn.clock, monotonic=Mono(),
                      view_log=getattr(scn, "view_log", None))
    app.config["TESTING"] = True
    return same_origin(app.test_client())
