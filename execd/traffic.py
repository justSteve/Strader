"""The SEND traffic pane — every hop of a SEND as one plain line. [st-qnbg]

Steve, 2026-10-01: *"I don't want raw json - i want that payload (in both
directions) reduced to just the essential info of the result - something was
sent - something was returned that validated or errored."*

A SEND crosses up to three hops the page can see: the page hands the
service an intent (``→ execd``); the service asks the broker for a preview
and sends the order (``→ Schwab``, or ``→ paper`` in paper mode); the broker
answers (``←``). The service writes each of its hops to the journal under
the intent's id as it makes them, so the page reads them back from there —
the service's own record of what it sent and what came back, in the order it
happened — and reduces each to one line. Nothing here talks to a broker.

Each SEND is one *transaction*: a header line, then its hops, the last one
the answer that settled it (filled, working, refused or errored). The page
keeps the transactions in a :class:`TrafficBuffer` of at most
:data:`TRAFFIC_CAP` lines for the life of the page process, newest at the
bottom, and renders it with :func:`render_html`. Lines carry their direction
as an arrow *and* a colour, and a received line that refused or errored is
the failure colour, so the meaning never rests on colour alone.
"""

from __future__ import annotations

import html
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from .bounds import CT
from .intent import parse_occ

#: lines the buffer keeps; older ones fall off the top (Steve: "a sane
#: length, e.g. the last 200 lines, and show the cap")
TRAFFIC_CAP = 200

#: the longest reason a line carries before it is cut
REASON_CHARS = 160

#: journal events that are a hop of a SEND, in the words below
_HOP_EVENTS = ("refused", "preview", "error", "sending", "placed", "rejected",
               "send_unknown", "replayed", "filled")


@dataclass(frozen=True)
class Line:
    """One line of the pane. ``kind`` is ``head`` (a transaction's
    delimiter), ``out`` (something sent) or ``in`` (something returned);
    ``ok`` is False for a returned refusal or error."""

    at: str
    kind: str
    text: str
    ok: bool = True

    def plain(self) -> str:
        if self.kind == "head":
            return f"── {self.at} {self.text} ──"
        arrow = "→" if self.kind == "out" else "←"
        return f"{self.at} {arrow} {self.text}"

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at, "kind": self.kind, "text": self.text, "ok": self.ok,
                "plain": self.plain()}


def hhmmss(ts: datetime | str | None) -> str:
    """A CT ``HH:MM:SS`` from a datetime or a journal ``ts`` (ISO)."""
    if ts is None:
        return "--:--:--"
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return ts[-8:]
    return ts.astimezone(CT).strftime("%H:%M:%S")


def contract_words(symbol: str) -> str:
    """``SPXW  261001C07720000`` → ``SPX 7720C``."""
    try:
        o = parse_occ(symbol)
    except ValueError:
        return symbol.strip()
    return f"SPX {o.strike:g}{o.right}"


def _side_word(side: Any) -> str:
    s = str(side or "")
    return "BUY" if s.startswith("BUY") else "SELL" if s.startswith("SELL") else s


def order_words(intent: Mapping[str, Any]) -> str:
    """``BUY 2 SPX 7720C LMT 10.40`` from an intent's wire form."""
    words = f"{_side_word(intent.get('side'))} {intent.get('qty')} {contract_words(str(intent.get('symbol', '')))}"
    px = intent.get("limit") if intent.get("limit") is not None else intent.get("price")
    if px is not None:
        words += f" LMT {float(px):.2f}"
    return words


def stop_dollars(limit: float | None, stop_price: float | None, qty: int | None) -> str | None:
    """The ticket's stop as the dollars it loses: ``$20``."""
    if limit is None or stop_price is None or not qty:
        return None
    usd = round((float(limit) - float(stop_price)) * 100 * int(qty), 2)
    return f"${usd:,.0f}" if usd == int(usd) else f"${usd:,.2f}"


def ticket_words(intent: Mapping[str, Any]) -> str:
    """What the page sent: ``BUY 2 SPX 7720C LMT 10.40, stop $20``."""
    words = order_words(intent)
    stop = stop_dollars(intent.get("limit"), intent.get("stop_price"), intent.get("qty"))
    return words + (f", stop {stop}" if stop else "")


def _cut(text: Any) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= REASON_CHARS else t[:REASON_CHARS - 1] + "…"


def _venue(e: Mapping[str, Any]) -> str:
    """Who the service spoke to: the paper book in paper mode, else the
    broker the journal names."""
    if e.get("mode") == "paper":
        return "paper"
    b = str(e.get("broker") or "Schwab")
    return {"schwab": "Schwab", "alpaca": "Alpaca", "mock": "mock"}.get(b.lower(), b)


def _hop(e: Mapping[str, Any]) -> list[Line]:
    """One journal line of a SEND as the pane's line or lines."""
    at = hhmmss(e.get("ts"))
    ev = e.get("event")
    venue = _venue(e)
    if ev == "refused":
        r = e.get("refused") or {}
        return [Line(at, "in", f"REFUSED by execd ({r.get('bound')}): {_cut(r.get('reason'))}",
                     ok=False)]
    if ev == "preview":
        p = e.get("preview") or {}
        sent = Line(at, "out", f"{venue}: preview {order_words(p)}")
        if p.get("accepted", True):
            total = p.get("total_usd")
            got = Line(at, "in", f"{venue}: preview ok"
                       + (f", ${float(total):,.2f} with fees" if total is not None else ""))
        else:
            got = Line(at, "in", f"{venue}: preview REFUSED: "
                       + _cut("; ".join(p.get("messages") or ()) or "no reason given"), ok=False)
        return [sent, got]
    if ev == "error":
        return [Line(at, "in", f"{venue}: error ({e.get('kind', '')}): {_cut(e.get('detail'))}",
                     ok=False)]
    if ev == "sending":
        words = order_words({"side": "BUY_TO_OPEN", "qty": e.get("qty"),
                             "symbol": e.get("symbol", ""), "limit": e.get("limit")})
        if e.get("stop_price") is not None:
            words += f" + STOP {float(e['stop_price']):.2f}"
        if e.get("target_price") is not None:
            words += f" + TARGET {float(e['target_price']):.2f}"
        return [Line(at, "out", f"{venue}: {words}")]
    if ev == "placed":
        o = e.get("order") or {}
        status = str(o.get("status", ""))
        oid = o.get("order_id")
        if status == "REJECTED":
            return [Line(at, "in", f"{venue}: REJECTED, order {oid}: "
                         + _cut(o.get("message") or "no reason given"), ok=False)]
        if status == "FILLED" or o.get("filled_qty"):
            # the fill itself is its own line, from the ``filled`` event
            return [Line(at, "in", f"{venue}: accepted, order {oid}")]
        return [Line(at, "in", f"{venue}: accepted, order {oid}, {status or 'WORKING'}")]
    if ev == "filled":
        return [fill_line(e, e.get("qty"), e.get("_of"))]
    if ev == "send_unknown":
        return [Line(at, "in", f"{venue}: no answer: {_cut(e.get('detail'))}", ok=False)]
    if ev == "replayed":
        return [Line(at, "in", f"execd: already sent under this id, order {e.get('order_id')}")]
    return []


def fill_line(e: Mapping[str, Any], qty: Any, of: Any) -> Line:
    """``← FILLED 2 @ 10.35``, or ``← FILLED 1/2 @ 10.35`` for a part
    (Steve, 2026-10-01): the count filled so far over the order's size."""
    count = f"{qty}/{of}" if of and qty and int(qty) < int(of) else f"{qty}"
    px = e.get("price")
    return Line(hhmmss(e.get("ts")), "in",
                f"FILLED {count}" + (f" @ {float(px):.2f}" if px is not None else ""))


def _with_fill_counts(hops: list[Mapping[str, Any]], total: Any) -> list[dict[str, Any]]:
    """Each ``filled`` event carries its own part; the line says the count
    filled so far over the order's size."""
    out, so_far = [], 0
    for e in hops:
        if e.get("event") == "filled":
            so_far += int(e.get("qty") or 0)
            e = {**e, "qty": so_far, "_of": total}
        out.append(dict(e))
    return out


def lines_for_send(*, at: datetime, title: str, intent: Mapping[str, Any] | None,
                   journal: Iterable[Mapping[str, Any]] = (), page_refusal: str | None = None,
                   error: str | None = None, mode: str | None = None) -> list[Line]:
    """One SEND as the pane's lines: its header, the page's hop to execd,
    the service's hops under the intent's id, and — when the page itself
    refused it or the call raised — that answer.

    ``title`` is the ticket in words (``BUY 2 SPX 7720C``) for the header
    and for a SEND the page refused before an intent existed; ``journal``
    is the service's journal lines written during the call."""
    when = hhmmss(at)
    # the header names the side the SEND went to (st-n4tr)
    out = [Line(when, "head", f"{mode.upper()} {title}" if mode else title)]
    if intent is None:
        out.append(Line(when, "out", f"SEND {title}"))
        out.append(Line(when, "in", f"REFUSED at the page: {_cut(page_refusal or error)}", ok=False))
        return out
    out.append(Line(when, "out", f"execd: {ticket_words(intent)}"))
    iid = intent.get("intent_id")
    hops = [e for e in journal if e.get("intent_id") == iid and e.get("event") in _HOP_EVENTS
            and not (e.get("event") in ("refused", "error") and e.get("kind") not in (None, "place", "preview"))
            and not (e.get("event") == "filled" and e.get("kind") != "entry")]
    for e in _with_fill_counts(hops, intent.get("qty")):
        out.extend(_hop(e))
    if page_refusal:
        out.append(Line(when, "in", f"REFUSED at the page: {_cut(page_refusal)}", ok=False))
    elif error and not any(not ln.ok for ln in out):
        out.append(Line(when, "in", f"error: {_cut(error)}", ok=False))
    elif len(out) == 2:
        out.append(Line(when, "in", "execd: no answer recorded", ok=False))
    return out


class TrafficBuffer:
    """The page's session buffer: every SEND a transaction — its header and
    hops — oldest first, at most ``cap`` lines across them; the oldest
    transactions fall off the top. A transaction whose order is still
    working is *pending*: its fill, when it comes later (a reconcile, the
    account stream, a poll), is added inside its own block by
    :meth:`note_fills`. Thread-safe — the page serves on several threads."""

    def __init__(self, cap: int = TRAFFIC_CAP) -> None:
        self.cap = cap
        #: the side these lines belong to; a switch clears them (st-n4tr)
        self.mode: str | None = None
        self._tx: list[tuple[str, list[Line]]] = []
        #: intent id -> (the order's size, the ``filled`` events already said)
        self._pending: dict[str, tuple[int, int]] = {}
        #: re-arms already said (st-d7nt)
        self._rearms: set[str] = set()
        self._lock = threading.Lock()
        self.dropped = 0

    def add(self, lines: Iterable[Line], *, key: str | None = None,
            pending_qty: int | None = None, fills_said: int = 0) -> None:
        with self._lock:
            k = key or f"tx-{len(self._tx)}-{id(lines)}"
            self._tx.append((k, list(lines)))
            if key and pending_qty:
                self._pending[key] = (int(pending_qty), fills_said)
            self._trim()

    def _trim(self) -> None:
        n = sum(len(ls) for _, ls in self._tx)
        while n > self.cap and self._tx:
            k, ls = self._tx[0]
            drop = min(len(ls), n - self.cap)
            del ls[:drop]
            self.dropped += drop
            n -= drop
            if not ls:
                self._tx.pop(0)
                self._pending.pop(k, None)

    @property
    def pending(self) -> set[str]:
        with self._lock:
            return set(self._pending)

    def note_fills(self, journal: Iterable[Mapping[str, Any]]) -> int:
        """Add the fill lines of every pending SEND that the journal now
        shows, inside that SEND's block; a SEND filled in full stops being
        pending. Returns how many lines were added."""
        with self._lock:
            if not self._pending:
                return 0
            fills: dict[str, list[Mapping[str, Any]]] = {}
            for e in journal:
                if e.get("event") == "filled" and e.get("kind") == "entry" \
                        and e.get("intent_id") in self._pending:
                    fills.setdefault(str(e["intent_id"]), []).append(e)
            added = 0
            for key, events in fills.items():
                total, said = self._pending[key]
                counted = _with_fill_counts(events, total)
                new = counted[said:]
                if not new:
                    continue
                block = next((ls for k, ls in self._tx if k == key), None)
                if block is None:
                    self._pending.pop(key, None)
                    continue
                block.extend(fill_line(e, e["qty"], total) for e in new)
                added += len(new)
                if counted[-1]["qty"] >= total:
                    self._pending.pop(key, None)
                else:
                    self._pending[key] = (total, len(counted))
            self._trim()
            return added

    def for_mode(self, mode: str) -> bool:
        """Hold only ``mode``'s lines: a switch of side clears the buffer
        (Steve, 2026-10-01, st-n4tr: "Live should never see paper's trades
        and vice versa"). Returns True when it cleared."""
        with self._lock:
            if self.mode == mode:
                return False
            cleared = self.mode is not None
            self.mode = mode
            self._tx.clear()
            self._pending.clear()
            return cleared

    def note_rearm(self, rearm: Mapping[str, Any]) -> bool:
        """The stop-out that re-armed the form, inside its SEND's block when
        this page sent it, else a block of its own (st-d7nt):
        ``← STOP FILLED 2 @ 9.80 — form re-armed: CALL 7720 @ mid``.
        Once per re-arm. Returns True when it added the line."""
        with self._lock:
            rid = str(rearm.get("id"))
            if rid in self._rearms:
                return False
            self._rearms.add(rid)
            px = rearm.get("fill_price")
            line = Line(hhmmss(rearm.get("at")), "in",
                        f"STOP FILLED {rearm.get('lots')}"
                        + (f" @ {float(px):.2f}" if px is not None else "")
                        + f" — form re-armed: {str(rearm.get('side', '')).upper()} "
                          f"{float(rearm.get('strike') or 0):g} @ mid")
            key = rearm.get("intent_id")
            block = next((ls for k, ls in self._tx if k == key), None) if key else None
            if block is not None:
                block.append(line)
            else:
                self._tx.append((f"rearm-{rid}", [Line(line.at, "head", f"{(self.mode or '').upper()} STOP-OUT".strip()), line]))
            self._trim()
            return True

    def forget(self, keys: Iterable[str]) -> None:
        """Stop waiting on SENDs that are no longer working and never
        filled (cancelled, rejected later)."""
        with self._lock:
            for k in keys:
                self._pending.pop(k, None)

    def lines(self) -> list[Line]:
        with self._lock:
            return [ln for _, ls in self._tx for ln in ls]

    def __len__(self) -> int:
        with self._lock:
            return sum(len(ls) for _, ls in self._tx)


#: colours from the page's own palette (page.py / panel.py): the muted grey
#: of a label for what was sent, the ok green for a good answer, the stop
#: red for a refusal or an error
_STYLE = (" .traffic{font-family:ui-monospace,Menlo,monospace;font-size:.82em;line-height:1.45;"
          "max-height:22em;overflow-y:auto;cursor:pointer}"
          " .traffic .tl{white-space:pre-wrap;word-break:break-word}"
          " .traffic .tl-out{color:#9ca3af}.traffic .tl-in{color:#34d399}"
          " .traffic .tl-fail{color:#f87171;font-weight:600}"
          " .traffic .tl-head{color:#e5e7eb;border-top:1px solid #374151;margin-top:.45em;"
          "padding-top:.25em;font-weight:600}"
          " .traffic .tl-head:first-child{border-top:0;margin-top:0}"
          " .panehead{display:flex;justify-content:space-between;align-items:center;gap:.5em;"
          "margin-bottom:.35em}"
          " .panehead .toggle{background:#1f2937;color:#e5e7eb;border:1px solid #4b5563;"
          "border-radius:6px;padding:.2em .7em;font-size:.85em}")


def style() -> str:
    return _STYLE


def render_html(buf: TrafficBuffer | Iterable[Line]) -> str:
    """The buffer as the pane's HTML, escaped, newest at the bottom, with
    the cap said above it. No JSON anywhere: every line is words."""
    lines = buf.lines() if isinstance(buf, TrafficBuffer) else list(buf)
    cap = buf.cap if isinstance(buf, TrafficBuffer) else TRAFFIC_CAP
    head = (f"<div class=k id=traffic-cap>{len(lines)} of the last {cap} lines kept · newest at the "
            f"bottom · tap here for the strikes</div>")
    if not lines:
        return head + "<div class=traffic id=traffic-lines><div class='tl tl-out'>no SEND yet</div></div>"
    rows = []
    for ln in lines:
        cls = ("tl-head" if ln.kind == "head" else "tl-out" if ln.kind == "out"
               else "tl-in" if ln.ok else "tl-fail")
        rows.append(f"<div class='tl {cls}'>{html.escape(ln.plain(), quote=True)}</div>")
    return head + "<div class=traffic id=traffic-lines>" + "".join(rows) + "</div>"
