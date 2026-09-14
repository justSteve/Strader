"""The desk's door to the execution service — preview only. [st-k6gl, stage 4]

Stage 4's rehearsal: the intent desk's ``go`` hands the priced ticket to execd
as an intent and asks for a **preview** — the service runs it through every
bound and, if the bounds pass, asks the broker what it would cost. Nothing is
sent. The service journals the request and the answer under the intent's id,
so the rehearsal leaves the same audit trail the live ticket will, and the
live ticket (one 1-lot, Steve at the STOP button) reuses the id it previewed
under.

Then ``send`` (Steve's word, 2026-09-14: "i want to see the full life cycle
now"): the same intent, same id, to ``POST /place``. The service previews it
again, applies its rules again, sends the one order, and on the fill rests the
protective stop at the broker and watches the SPX mark (``execd.watch``). A
repeat of an id the service already sent is answered from its journal, never
re-sent.

What this module does not do, on purpose:

- It imports neither ``schwab`` nor ``broker_schwab`` — plain HTTP to the
  loopback with the standard library, the same as the readers' client. The
  gate hook that keeps agent code away from the live API stays exactly as it
  is; the service is the one credential holder and the one judge.
- It never carries a credential, an account, or a bound. The intent is the
  order as data; the service decides.

The chain the desk prices against comes through the same door
(``/marketdata/chains``), so ``price`` no longer needs a hand-made file.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from execd.intent import OrderIntent
from market.entities.chain import Chain
from market.ingest.schwab import chain_from_schwab
from strader.execution.compose import Ticket
from strader.intent.entities import Order
from strader.intent.tos import occ_symbols

log = logging.getLogger(__name__)

#: The service's narrow door. Loopback only; the port is ``execd.api.BIND_PORT``.
DEFAULT_URL = os.environ.get("EXECD_URL", "http://127.0.0.1:8778")

#: Schwab gets 15 s inside the service; this covers that plus the hop.
TIMEOUT_S = float(os.environ.get("EXECD_TIMEOUT_S", "20"))

#: How many strikes either side of spot the live chain carries. Enough for a
#: first-ITM single and a twenty-wide fly around a marked level.
CHAIN_STRIKES = 40

#: The source word the service journals for a desk intent (``execd.intent``).
SOURCE = "intent-desk"

REPO = Path(__file__).resolve().parents[2]

Transport = Callable[[str, str, bytes | None, float], tuple[int, bytes]]


class ExecdUnreachable(RuntimeError):
    """The service did not answer. Staging still happened; nothing was sent."""


@dataclass(frozen=True)
class Answer:
    """One HTTP answer from the service: the status, and the JSON body."""

    status: int
    body: dict[str, Any]

    @property
    def refused(self) -> dict[str, Any] | None:
        r = self.body.get("refused")
        return r if isinstance(r, dict) else None

    @property
    def preview(self) -> dict[str, Any] | None:
        p = self.body.get("preview")
        return p if isinstance(p, dict) else None


def _transport(method: str, url: str, body: bytes | None, timeout: float) -> tuple[int, bytes]:
    """One request. A non-2xx comes back as its status, not raised — a 409 is
    the service's answer, not a transport failure."""
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as r:  # noqa: S310 — loopback, fixed host
            return r.status, r.read()
    except HTTPError as exc:
        return exc.code, exc.read()


class DeskExecd:
    """The desk's client: ``preview`` an intent, fetch the ``chain`` it prices on."""

    def __init__(self, base_url: str = DEFAULT_URL, *, timeout_s: float = TIMEOUT_S,
                 transport: Transport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._transport = transport or _transport

    # ── plumbing ─────────────────────────────────────────────────────────
    def _call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Answer:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        try:
            status, raw = self._transport(method, url, body, self.timeout_s)
        except (URLError, OSError, TimeoutError) as exc:
            raise ExecdUnreachable(
                f"execd unreachable at {self.base_url}: {type(exc).__name__}: {exc}") from None
        try:
            parsed = json.loads(raw or b"{}")
        except ValueError:
            parsed = {"error": "not_json", "detail": raw[:200].decode("utf-8", "replace")}
        if not isinstance(parsed, dict):
            parsed = {"error": "not_an_object", "detail": str(parsed)[:200]}
        return Answer(status, parsed)

    # ── the two calls the desk makes ─────────────────────────────────────
    def preview(self, intent: dict[str, Any]) -> Answer:
        """``POST /preview``. The service journals the request under the
        intent's id, runs the bounds, and prices it with the broker if they
        pass. Sends nothing, in every branch."""
        return self._call("POST", "/preview", intent)

    def place(self, intent: dict[str, Any]) -> Answer:
        """``POST /place``. The one call that can transmit. The service runs
        its rules and the broker's preview again, sends the order, and on a
        fill rests the protective stop. Same intent, same id as the preview."""
        return self._call("POST", "/place", intent)

    def chain(self, expiry: dt.date, *, symbol: str = "$SPX",
              strike_count: int = CHAIN_STRIKES) -> dict[str, Any]:
        """The raw Schwab chain body for one expiry, through the service's
        market-data door (answers while LOCKED — the market grant is outside
        the lock)."""
        params = {"symbol": symbol, "contractType": "ALL", "strikeCount": strike_count,
                  "includeUnderlyingQuote": "true",
                  "fromDate": expiry.isoformat(), "toDate": expiry.isoformat()}
        ans = self._call("GET", "/marketdata/chains?" + urlencode(params))
        if ans.status != 200:
            raise ExecdUnreachable(
                f"execd answered HTTP {ans.status} for the chain: "
                f"{ans.body.get('detail') or ans.body}")
        return ans.body


# ── the intent, from the priced order ────────────────────────────────────

def intent_for(order: Order, bracket: dict[str, Any] | None, *, intent_id: str,
               engine_sha: str = "") -> dict[str, Any]:
    """The service's ``OrderIntent`` wire form for a priced desk order.

    One leg only — the service sends single legs (``execd.intent``), and the
    caller has already refused anything else. The bracket, when FD0 could
    build one, supplies the two numbers the broker-resident stop is derived
    from: the SPX level at which the service exits, and the leg's delta at
    compose. Without them the service refuses the entry at its own bound,
    which is the right place for that refusal to be recorded.

    Validated against the service's own rules before it leaves, so a
    malformed intent is caught here with the service's words rather than as
    a 400 on the wire.
    """
    legs = occ_symbols(order)
    if len(legs) != 1:
        raise ValueError(f"the service sends single legs only; this order has {len(legs)}")
    d: dict[str, Any] = {
        "intent_id": intent_id,
        "symbol": legs[0],
        "side": "BUY_TO_OPEN" if order.action == "BUY" else "SELL_TO_CLOSE",
        "qty": abs(int(order.quantity)),
        "order_type": "LIMIT",
        "limit": round(float(order.price), 2),
        "source": SOURCE,
        "engine_sha": engine_sha,
    }
    if bracket:
        t = Ticket.from_dict(bracket)
        d["stop_spx"] = float(t.stop_trigger_spx)
        d["delta"] = round(abs(float(t.derivation.delta_live)), 4)
    OrderIntent.from_dict(d).validated()
    return d


def repo_sha() -> str:
    """The desk's own commit, for the intent's ``engine_sha`` — the same
    ``-dirty`` rule the service applies to its own stamp. ``unknown`` when
    git cannot say."""
    try:
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain",
                                "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = (head.stdout or "").strip()
    if head.returncode != 0 or not sha:
        return "unknown"
    return sha + ("-dirty" if (dirty.stdout or "").strip() else "")


# ── the read-back ────────────────────────────────────────────────────────

def _mode_prefix(ans: Answer) -> str:
    """``PAPER `` when the service is simulating orders — on every answer that
    could otherwise read as real (st-k6gl)."""
    return "PAPER (simulated) — " if ans.body.get("mode") == "paper" else ""


def describe(ans: Answer) -> str:
    """The service's answer in the desk's words. Every branch says that
    nothing was sent, because in every branch nothing was."""
    return _mode_prefix(ans) + _describe(ans)


def _describe(ans: Answer) -> str:
    if ans.status == 200 and ans.preview is not None:
        p = ans.preview
        price = p.get("price")
        head = (f"Execd preview, nothing sent: {str(p.get('symbol', '')).strip()} "
                f"{p.get('side')} x{p.get('qty')} {p.get('order_type')}"
                + (f" at {float(price):.2f}" if price is not None else "")
                + f" — cost ${_f(p.get('cost_usd')):.2f}, commission "
                  f"${_f(p.get('commission_usd')):.2f}, total ${_f(p.get('total_usd')):.2f}; "
                + ("the broker accepts it." if p.get("accepted") else "the broker would REJECT it."))
        msgs = [str(m) for m in (p.get("messages") or [])]
        return head + ("".join(f"\n  broker: {m}" for m in msgs) if msgs else "")
    if ans.status == 409 and ans.refused is not None:
        r = ans.refused
        return f"Execd refused ({r.get('bound')}): {r.get('reason')}. Nothing sent."
    detail = ans.body.get("detail") or ans.body
    if ans.status == 400:
        return f"Execd rejected the intent as malformed: {detail}. Nothing sent."
    if ans.status == 502:
        return f"Execd could not reach the broker: {detail}. Nothing sent."
    return f"Execd answered HTTP {ans.status}: {detail}. Nothing sent."


def describe_place(ans: Answer) -> str:
    """The service's answer to a send, in the desk's words. Says SENT only
    when the service says it sent; every other branch says what happened
    instead. In paper mode every line is prefixed so a simulated fill never
    reads as a real one."""
    return _mode_prefix(ans) + _describe_place(ans)


def _describe_place(ans: Answer) -> str:
    if ans.status == 200 and isinstance(ans.body.get("order"), dict):
        o = ans.body["order"]
        oid = o.get("order_id")
        if ans.body.get("replayed"):
            return (f"Already sent earlier under this id — order {oid}, status {o.get('status')}. "
                    f"Nothing new sent.")
        status = str(o.get("status", ""))
        if status == "REJECTED":
            return (f"Sent, and the broker REJECTED it (order {oid}): "
                    f"{o.get('message') or 'no reason given'}. Nothing is open.")
        if status == "FILLED" or o.get("filled_qty"):
            fill = _f(o.get("fill_price"))
            qty = int(o.get("filled_qty") or o.get("qty") or 0)
            head = (f"SENT AND FILLED: order {oid}, {qty} at {fill:.2f} "
                    f"(${fill * 100 * qty:.2f}).")
            stop = ans.body.get("stop_order")
            if isinstance(stop, dict) and stop.get("order_id"):
                head += (f" Protective stop resting at the broker: order {stop['order_id']} "
                         f"at {_f(stop.get('price')):.2f}. The service watches the SPX mark; "
                         f"STOP and FLATTEN are on your page.")
            else:
                head += (" ** NO PROTECTIVE STOP RESTED — the position is live and "
                         "unprotected; FLATTEN on the page if in doubt.")
            return head
        work = ans.body.get("working")
        limit = _f((work or {}).get("limit") or o.get("price"))
        return (f"SENT: order {oid} is {status} at the broker at {limit:.2f}, not filled yet. "
                f"The service is watching it; the stop rests when it fills.")
    if ans.status == 409 and ans.refused is not None:
        r = ans.refused
        return f"Execd refused ({r.get('bound')}): {r.get('reason')}. Nothing sent."
    detail = ans.body.get("detail") or ans.body
    if ans.status == 400:
        return f"Execd rejected the intent as malformed: {detail}. Nothing sent."
    if ans.status == 502:
        return (f"Execd could not reach the broker: {detail}. Nothing was sent that the "
                f"service knows of — check the page's orders before sending again.")
    return f"Execd answered HTTP {ans.status}: {detail}. Check the page before sending again."


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ── the live chain ───────────────────────────────────────────────────────

def live_chain(client: DeskExecd, expiry: dt.date, *, symbol: str = "$SPX") -> Chain:
    """The chain ``price`` resolves against, fetched now through the service.

    Raises :class:`ExecdUnreachable` when the service does not answer and
    ``ValueError`` when it answers with no contracts for the expiry — a
    holiday, a wrong date, or a chain that came back empty — because pricing
    against nothing must not look like a quiet 'no strike'.
    """
    data = client.chain(expiry, symbol=symbol)
    chain = chain_from_schwab(data, expiry)
    if not chain.calls and not chain.puts:
        raise ValueError(
            f"the live chain has no {symbol} contracts expiring {expiry.isoformat()} "
            f"(status {data.get('status')!r})")
    if not chain.underlying_price:
        raise ValueError("the live chain carries no underlying price")
    return chain
