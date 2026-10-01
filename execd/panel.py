"""The order status panel — one card, seven stages, on ``/exec/order``. [st-4ezg]

The design is ``docs/design/order-status-panel`` (Steve's 2026-09-14 review:
*"the complete status of the order, plus controls to alter or refresh its
rendering … optimize for the obvious … the panel can re-size according to
context"*). This is that design in code: the same card changes shape as the
order moves through its life —

    none → working → filled → exiting → closed                    (refused)

— and every stage is read off the service's status body plus the day's
journal, never off a state the page keeps for itself. The rules from the
review hold in every stage:

* every time on the card is *x ago*, and it ticks. There is no clock: the
  strip's ticking wall clock sat beside the arming word and read as the
  moment the service was armed, and Steve had it removed (2026-09-18,
  st-644f). ``tick()`` still paints ``#clock`` if a page ever carries one;
* a contract is named ``C7630`` / ``P7600`` — right and strike, nothing else;
* one net number, commissions included (``NET NOW`` is what a market sell
  nets after both commissions, the same arithmetic as the position row);
* the filled stage is the live editor for the stop and the take-profit;
* a working entry has one control, CANCEL AND RE-PRICE, and no STOP;
* no footers — the card is as tall as its stage and no taller;
* a closed position leaves this card for a folded card of its own in the
  stack at the foot of the page, newest on top (st-qqxj).

Server-rendered, so it works with no script; the script only ticks the
clocks and polls the body.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .intent import parse_occ
from .service import ExecService, CT

#: Six stages since st-igw0 — PREVIEWED went with the PREVIEW step; SEND is
#: one tap from the decision and the broker's own preview runs inside the
#: service's place.
STAGES = ("none", "working", "filled", "exiting", "closed", "refused")

WORDS = {"none": "no order", "working": "WORKING",
         "filled": "FILLED", "exiting": "SELLING", "closed": "CLOSED",
         "refused": "REFUSED"}
COLORS = {"none": "#9ca3af", "working": "#fbbf24",
          "filled": "#34d399", "exiting": "#fbbf24", "closed": "#9ca3af",
          "refused": "#f87171"}

PANEL_STYLE = """
 .panel .hdr{display:flex;align-items:center;justify-content:space-between;gap:.75em}
 .panel .hdr .l,.panel .hdr .r{display:flex;align-items:center;gap:.75em;min-width:0}
 .panel .word{font-size:1.6em;font-weight:700;line-height:1.1}
 .panel .badge{font-weight:700;font-size:.8em;padding:4px 8px;border-radius:6px;letter-spacing:.04em}
 .panel .badge.paper{background:#fbbf24;color:#111;margin:0}.panel .badge.live{background:#dc2626;color:#fff;margin:0}
 .panel .clock{font-size:1.15em;font-weight:600;color:#9ca3af;font-variant-numeric:tabular-nums;letter-spacing:.02em}
 .panel .ico{display:flex;align-items:center;justify-content:center;width:44px;height:44px;background:#1f2937;color:#e5e7eb;border:0;border-radius:8px;cursor:pointer}
 .panel .title{margin-top:12px;font-size:1.15em;font-weight:700}
 .panel .hero{display:flex;align-items:baseline;justify-content:space-between;gap:.75em;margin-top:8px}
 .panel .hero .n{font-size:2em;font-weight:700}
 .panel .neg{color:#f87171}.panel .pos{color:#34d399}.panel .amber{color:#fbbf24}.panel .plain{color:#e5e7eb}
 .panel table{margin-top:8px}
 .panel .actions{display:flex;flex-direction:column;gap:8px;margin-top:12px}
 .panel .actions form{margin:0}.panel .actions .big{margin:0}
 /* each leg a row as the ticket's stop row is: a dollar box between + and
    −, an SPX box, SET (st-qqxj); the boxes take the ticket's .dl styles */
 .panel .editor{display:flex;flex-direction:column;gap:10px;margin-top:12px}
 .panel .editor form{margin:0}
 .panel .legrow{justify-content:center;gap:.5em;flex-wrap:nowrap}
 .panel .legrow .dl{gap:.3em}.panel .legrow .dl.stopl input{width:4.2em}.panel .legrow .dl.exitl input{width:5.2em}
 .panel .legrow .dl .k{white-space:nowrap}
 @media (max-width:430px){.panel .legrow{flex-wrap:wrap;gap:.4em}.panel .legrow .dl.stopl input{width:3.6em}
   .panel .legrow .dl.exitl input{width:4.8em}.panel .legrow button.step{width:38px}}
 .panel .legnote{text-align:center;margin-top:2px}
 .panel .editor .money{font-size:.9em;font-weight:700;margin:0 .4em}
 .panel .editor button.set{min-height:44px;padding:0 12px;border-radius:8px;border:1px solid #374151;font-weight:700;cursor:pointer;background:#1f2937;color:#e5e7eb;font-family:inherit}
 .panel .editor button.set:disabled{opacity:.5}
 .panel #adjustnote{margin-top:8px;min-height:1.2em}.panel #adjustnote.bad{background:#7f1d1d;border:1px solid #ef4444;border-radius:8px;padding:.4em .7em;color:#fecaca}
 .panel #adjustnote.ok{color:#34d399}
 .panel .refusal{margin-top:12px;background:#7f1d1d;border:1px solid #ef4444;border-radius:10px;padding:.7em 1em}
 .panel .pollnote{margin-top:8px;background:#7f1d1d;border:1px solid #ef4444;border-radius:8px;padding:.4em .7em;color:#fecaca;font-size:.9em}
 /* the day's closed positions, a card each, folded (st-qqxj) */
 .closedhead{margin:1em 0 .2em}
 details.closedcard{padding:0;margin:.4em 0}
 details.closedcard summary{list-style:none;display:flex;align-items:center;gap:.8em;padding:.75em 1em;min-height:44px;
   box-sizing:border-box;cursor:pointer;touch-action:manipulation}
 details.closedcard summary::-webkit-details-marker{display:none}
 details.closedcard summary::after{content:'\\25B8';margin-left:auto;color:#6b7280}
 details.closedcard[open] summary::after{content:'\\25BE'}
 details.closedcard .cname{font-weight:700;white-space:nowrap}details.closedcard .cpnl{font-weight:700;white-space:nowrap}
 details.closedcard .cwhen{white-space:nowrap}
 @media (max-width:430px){details.closedcard summary{gap:.5em;padding:.6em .8em}}
 details.closedcard .cpnl.neg{color:#f87171}details.closedcard .cpnl.pos{color:#34d399}
 details.closedcard .cwhy{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 details.closedcard table{margin:0 1em .8em;width:calc(100% - 2em)}
"""


# ── words for numbers ────────────────────────────────────────────────────

def contract_name(symbol: str) -> str:
    """``SPXW  260826C06400000`` → ``C6400``. A symbol that is not OCC comes
    back trimmed, so a page never breaks on a name."""
    try:
        occ = parse_occ(symbol)
    except ValueError:
        return str(symbol).strip()
    return f"{occ.right}{occ.strike:g}"


def ago(seconds: float | None) -> str:
    """``12 s`` / ``1 m 35 s`` / ``2 h 05 m`` — the design's unit words."""
    if seconds is None:
        return "—"
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} m {s:02d} s" if s else f"{m} m"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} m"


def short_pts(v: float) -> str:
    """An option-point distance the way Steve writes it: ".2", ".25", "1.5"."""
    t = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return t[1:] if t.startswith("0.") else t


def money(v: Any) -> str:
    from .page import _money
    return _money(v)


def money_class(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return "plain"
    return "pos" if v > 0 else ("neg" if v < 0 else "plain")


def esc(v: Any) -> str:
    from .page import esc as _esc
    return _esc(v)


def _parse_ts(s: Any) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def ago_span(at: datetime | None, now: datetime) -> str:
    """A relative time the script keeps ticking: the server's reading in the
    text, the instant in ``data-at`` (epoch milliseconds)."""
    if at is None:
        return "<span class=ago>—</span>"
    secs = (now - at).total_seconds()
    return f"<span class=ago data-at={int(at.timestamp() * 1000)}>{ago(secs)} ago</span>"


# ── what the day's journal knows that the status body does not ───────────

def journal_facts(service: ExecService) -> dict[str, Any]:
    """The times the status body does not carry: when each working entry was
    sent, when each position's close went out, when the last position filled,
    and the last ``closed`` line of the day."""
    sent: dict[str, datetime] = {}
    exit_sent: dict[str, datetime] = {}
    filled: dict[str, datetime] = {}
    last_close: dict[str, Any] | None = None
    closes: list[dict[str, Any]] = []
    #: what the broker said each order was (``order_raw``), so a close the
    #: service booked as "external" can still be named a stop or a target
    order_types: dict[str, str] = {}
    #: the stop each position last rested at, by intent — the closed card
    #: says what the stop was, so "did my .3 register?" is on the card
    stops: dict[str, float] = {}
    limits: dict[str, float] = {}
    for e in service.journal.read():
        ev = e.get("event")
        ts = _parse_ts(e.get("ts"))
        iid = str(e.get("intent_id") or "")
        if ev == "order_raw" and e.get("order_id") and isinstance(e.get("body"), dict):
            kind = e["body"].get("order_type")
            if kind:
                order_types[str(e["order_id"])] = str(kind)
        elif ev == "sending" and iid:
            if isinstance(e.get("limit"), (int, float)):
                limits[iid] = float(e["limit"])
            if isinstance(e.get("stop_price"), (int, float)):
                stops[iid] = float(e["stop_price"])
        elif ev == "stop_placed" and iid and isinstance(e.get("stop_price"), (int, float)):
            stops[iid] = float(e["stop_price"])
        elif ev == "stop_adjusted" and iid and isinstance(e.get("new_price"), (int, float)):
            stops[iid] = float(e["new_price"])
        if ev == "working" and e.get("kind") == "entry" and e.get("order_id"):
            sent[str(e["order_id"])] = ts
        elif ev == "placed" and e.get("kind") == "exit":
            # keyed by the close's own order id — that is what the position
            # carries as ``exit_order_id`` while the close works
            order = e.get("order") if isinstance(e.get("order"), dict) else {}
            if order.get("order_id"):
                exit_sent[str(order["order_id"])] = ts
        elif ev == "exit_unfilled" and e.get("order_id"):
            exit_sent.setdefault(str(e["order_id"]), ts)
        elif ev == "filled" and e.get("kind") == "entry":
            for key in (e.get("intent_id"), e.get("symbol")):
                if key:
                    filled[str(key)] = ts
        elif ev == "closed":
            last_close = e
            closes.append(e)
    return {"sent": sent, "exit_sent": exit_sent, "filled": filled, "last_close": last_close,
            "closes": closes, "order_types": order_types, "stops": stops, "limits": limits}


def stage_of(st: Mapping[str, Any], facts: Mapping[str, Any], *,
             refused: bool = False) -> str:
    """Which of the six stages the card is in. A refusal is the page's own
    (it belongs to this request); everything else is read off the service."""
    if refused:
        return "refused"
    positions = st.get("positions") or []
    if any(p.get("exit_order_id") for p in positions):
        return "exiting"
    if positions:
        return "filled"
    if st.get("working"):
        return "working"
    if facts.get("last_close"):
        return "closed"
    return "none"


# ── the card ─────────────────────────────────────────────────────────────

def _today_row(st: Mapping[str, Any]) -> str:
    """The day as money, and only money. The attempts used and the headroom
    left came off on Steve's word (2026-09-18: "you are _still showing
    headroom and attempts. remove all aspects of that", st-644f); the bounds
    still hold both, they are simply not counted at him. With no close yet
    there is nothing to say, and the row does not appear."""
    pnl = st.get("pnl") or {}
    if not pnl.get("closes"):
        return ""
    body = f"realized {money(pnl.get('realized_usd'))} over {pnl['closes']} close(s)"
    return f"<tr><td>today</td><td>{esc(body)}</td></tr>"


def _big_button(action: str, word: str, cls: str, hidden: Mapping[str, str] | None = None,
                method: str = "post") -> str:
    fields = "".join(f"<input type=hidden name={esc(k)} value='{esc(v)}'>"
                     for k, v in (hidden or {}).items())
    return f"<form method={method} action='{action}'>{fields}<button class='big {cls}'>{word}</button></form>"


def _link_button(href: str, word: str, cls: str) -> str:
    return f"<a class='big {cls}' href='{href}'>{word}</a>"


def _arming_line(st: Mapping[str, Any], actions: Mapping[str, str]) -> str:
    a = st["arming"]
    if a.get("killed"):
        return ("<div class='k stop-on' style='margin-top:8px'>STOP IS ON — no new positions; "
                "an unlock clears it</div>")
    if a["state"] == "LOCKED":
        return ""   # the passphrase box sits under the strip (st-2hei)
    if a["state"] != "ARMED":
        return f"<div class=k style='margin-top:8px'>{esc(a['state'].replace('_', ' ').lower())}</div>"
    return ""


def _quote_line(service: ExecService, symbol: str, now: datetime) -> tuple[dict[str, Any] | None, str]:
    from .broker import BrokerError
    try:
        q = service.quote(symbol)
    except BrokerError as exc:
        return None, f"no quote — {esc(str(exc))}"
    return ({"bid": q.bid, "ask": q.ask, "age": q.age_s(now)},
            f"bid {q.bid:.2f} / ask {q.ask:.2f} · quote {ago(q.age_s(now))} old")


def _spx_line(service: ExecService) -> float | None:
    from .broker import BrokerError
    try:
        return service.spx_mark()
    except BrokerError:
        return None


def body_none(st, facts, actions, now) -> str:
    html = ("<div class=k style='margin-top:12px'>nothing held, nothing working</div>"
            + _arming_line(st, actions))
    html += f"<table>{_today_row(st)}</table>"
    return html


def _at_market(sel_query: Mapping[str, str]) -> dict[str, str]:
    """The selection without its lock: RE-PRICE means at the market."""
    return {k: v for k, v in sel_query.items() if k != "limit"}


def body_working(service, st, facts, actions, now, bounds) -> str:
    html = ""
    for w in st["working"]:
        sym = str(w.get("symbol", ""))
        name = contract_name(sym)
        limit = float(w["limit"]) if w.get("limit") is not None else None
        sent = facts["sent"].get(str(w.get("order_id", "")))
        html += (f"<div class=title>{esc(name)} × {w.get('qty')} · buy limit "
                 f"{limit:.2f} · sent {ago_span(sent, now)}</div>"
                 if limit is not None else
                 f"<div class=title>{esc(name)} × {w.get('qty')} · sent {ago_span(sent, now)}</div>")
        q, qline = _quote_line(service, sym, now)
        if q and limit is not None:
            gap = round(q["ask"] - limit, 2)
            word = "ask above the limit" if gap > 0 else ("ask at the limit" if gap == 0 else "ask below the limit")
            cls = "amber" if gap > 0 else "pos"
            html += (f"<div class=hero><div class=k>{word}</div>"
                     f"<div class='n {cls}'>{gap:+.2f}</div></div>")
        html += f"<div class=k>{qline}</div>"
        rows = []
        on_fill = []
        if w.get("stop_spx") is not None:
            on_fill.append(f"cut if SPX reaches {float(w['stop_spx']):.2f}")
        mult = bounds.get("take_profit_multiple")
        if isinstance(mult, (int, float)) and bounds.get("take_profit_basis", "premium") == "premium":
            on_fill.append(f"target {float(mult):g}× the entry")
        if on_fill:
            rows.append(f"<tr><td>on fill</td><td>{' · '.join(on_fill)}</td></tr>")
        if w.get("order_id"):
            rows.append(f"<tr><td>order</td><td>{esc(w['order_id'])}</td></tr>")
        rows.append(_today_row(st))
        html += "<table>" + "".join(rows) + "</table>"
        html += ("<div class=actions>"
                 + _big_button(actions["order_cancel"], "CANCEL AND RE-PRICE", "quiet",
                               {"order_id": str(w.get("order_id", ""))})
                 + "</div>")
    return html


def _water_line(p: Mapping[str, Any], now: datetime, *, row: bool = False) -> str:
    """The best and worst net the position has shown and when — from the
    status body while it is held, from the ``closed`` line after (st-ff5j).
    Nothing until a valuation has been struck."""
    best, worst = p.get("best_net_usd"), p.get("worst_net_usd")
    if best is None and worst is None:
        return ""
    def at(key: str) -> str:
        t = _parse_ts(p.get(key))
        return f" at {t.astimezone(CT).strftime('%H:%M:%S')}" if t else ""
    text = (f"best <span class='{money_class(best)}'>{money(best)}</span>{at('best_at')} · "
            f"worst <span class='{money_class(worst)}'>{money(worst)}</span>{at('worst_at')}")
    if row:
        return f"<tr><td>best · worst</td><td>{text}</td></tr>"
    return f"<div class=k>{text}</div>"


def body_filled(service, st, facts, actions, now) -> str:
    html = ""
    spx = _spx_line(service)
    for p in st["positions"]:
        v = p.get("valuation") or {}
        sym = str(p["symbol"])
        name = contract_name(sym)
        opened = _parse_ts(p.get("opened_at")) or facts["filled"].get(str(p.get("intent_id"))) \
            or facts["filled"].get(sym)
        html += (f"<div class=title>{esc(name)} × {p['qty']} · in {p['entry_price']:.2f} · "
                 f"{ago_span(opened, now)}</div>")
        net = v.get("net_if_closed_usd")
        html += (f"<div class=hero><div class=k>NET NOW</div>"
                 f"<div class='n {money_class(net)}'>{money(net)}</div></div>")
        html += _water_line(p, now)
        if v.get("bid") is not None:
            line = f"bid {v['bid']:.2f} / ask {v['ask']:.2f} · quote {ago(v.get('quote_age_s'))} old"
        else:
            line = f"no quote — {esc(v.get('error') or 'unknown')}"
        if spx is not None:
            line += f" · SPX {spx:.2f}"
        if p.get("stop_spx") is not None:
            line += f", cut {float(p['stop_spx']):.2f}"
        html += f"<div class=k>{line}</div>"
        # the live editor (st-fn5y) — both trigger conditions, each leg
        # given both ways (st-qqxj, below)
        # Each note is the broker's answer, not the id alone: a leg the
        # listing has not reported for LEG_SETTLE_S says so, and a leg with
        # no order behind it is NO ... RESTING whatever price it was last at
        # (audit findings 39 and 41, st-vqmr).
        stop_note = (f"<span class='money {money_class(v.get('at_stop_usd'))}'>{money(v.get('at_stop_usd'))}</span>"
                     if p.get("stop_state") else "<span class='money neg'>NO STOP RESTING</span>")
        if not p.get("stop_state") and p.get("stop_off_by_hand"):
            stop_note += "<span class='money neg'>CANCELLED IN TOS — NOTHING HERE WILL CLOSE IT</span>"
        if p.get("stop_state") == "unaccounted":
            stop_note += "<span class='money neg'>NOT IN THE BROKER'S LISTING</span>"
        target_note = (f"<span class='money {money_class(v.get('at_target_usd'))}'>{money(v.get('at_target_usd'))}</span>"
                       if p.get("target_state") else "<span class='money amber'>NO TARGET RESTING</span>")
        if not p.get("target_state") and p.get("target_off_by_hand"):
            target_note += "<span class='money amber'>CANCELLED IN TOS</span>"
        if p.get("target_state") == "unaccounted":
            target_note += "<span class='money amber'>NOT IN THE BROKER'S LISTING</span>"
        # One leg at a time (Steve, 2026-09-15: "It'll be one or the other.
        # I'd like to be able to enter the value in either and just hit
        # enter to submit … make this as instant as possible", st-bmaz):
        # each leg is its own form, Enter sends it, SET is the tap target;
        # the script posts it by fetch and paints the answer into the card.
        # Each leg as the ticket's stop is (Steve, 2026-09-30: "The 'open
        # position' screen should display both SL and TP controls the same
        # way they are rendered on the pre-order screen. Offer both strike
        # and amount triggers", st-qqxj): a dollar box — the leg's distance
        # from the fill, ".3" is 0.30 under it for the stop, over it for the
        # target — with + left and − right stepping 0.10, and an SPX box, a
        # level. Typing or stepping in one writes NA in the other and marks
        # it the live one; SET sends that one.
        entry = float(p["entry_price"])
        def leg_form(leg: str, price: float | None, level: float | None, note: str) -> str:
            off = "NA"
            if price is not None:
                d = round(entry - price if leg == "stop" else price - entry, 2)
                off = short_pts(d) if d > 0 else "NA"
            spx_val = f"{float(level):g}" if level is not None else "NA"
            side = "under" if leg == "stop" else "over"
            return (f"<form method=post action='{actions['order_adjust']}' class='adjust leg' data-leg={leg}>"
                    f"<input type=hidden name=symbol value='{esc(sym)}'>"
                    "<input type=hidden name=ajax value=''>"
                    "<input type=hidden name=live value=''>"
                    "<div class='row legrow'>"
                    f"<label class='dl stopl' title='the {leg}, in dollars {side} the {entry:.2f} fill (.3)'>"
                    f"<span class=k>{leg} $</span>"
                    f"<button type=button class=step data-for=off data-step=1 aria-label='{leg} 0.10 further'>+</button>"
                    f"<input name={leg}off class=offbox inputmode=decimal enterkeyhint=go autocomplete=off "
                    f"aria-label='{leg} in dollars' value='{off}'>"
                    f"<button type=button class=step data-for=off data-step=-1 aria-label='{leg} 0.10 nearer'>&minus;</button></label>"
                    f"<label class='dl exitl' title='the {leg} as an SPX level (7610)'><span class=k>at SPX</span>"
                    f"<input name={leg}spx class=spxbox inputmode=decimal enterkeyhint=go autocomplete=off "
                    f"aria-label='{leg} as an SPX level' value='{spx_val}'></label>"
                    f"<button class=set aria-label='set the {leg}'>SET</button></div>"
                    f"<div class=legnote>{note}</div></form>")
        html += ("<div id=adjustnote class=k></div><div class=editor>"
                 + leg_form("stop", p.get("stop_price"), p.get("stop_spx"), stop_note)
                 + leg_form("target", p.get("target_price"), p.get("target_spx"), target_note)
                 + "</div>")
        html += f"<table>{_today_row(st)}</table>"
    html += "<div class=actions>"
    if st["arming"]["state"] != "LOCKED" and st["positions"]:
        html += _big_button(actions["flatten"], "FLATTEN", "exit", {"back": "order"})
    # no STOP on the card either (Steve, 2026-09-30: "i do not want a STOP
    # button to display on the trade screen"); lock is the one switch
    html += "</div>" + _arming_line(st, actions)
    return html


def body_exiting(service, st, facts, actions, now) -> str:
    html = ""
    for p in st["positions"]:
        if not p.get("exit_order_id"):
            continue
        v = p.get("valuation") or {}
        name = contract_name(str(p["symbol"]))
        sent = facts["exit_sent"].get(str(p.get("exit_order_id")))
        html += f"<div class=title>{esc(name)} × {p['qty']} · in {p['entry_price']:.2f} · selling</div>"
        html += (f"<div class=hero><div class=k>market sell sent</div>"
                 f"<div class='n amber'>{ago_span(sent, now)}</div></div>")
        if v.get("bid") is not None:
            html += (f"<div class=k>last bid {v['bid']:.2f} · about "
                     f"<span class='{money_class(v.get('net_if_closed_usd'))}'>{money(v.get('net_if_closed_usd'))}</span></div>")
        rows = [f"<tr><td>reason</td><td>{esc(p.get('exit_reason') or 'exit')}</td></tr>",
                "<tr><td>stop · target</td><td>cancelled</td></tr>",
                f"<tr><td>order</td><td>{esc(p['exit_order_id'])}</td></tr>", _today_row(st)]
        html += "<table>" + "".join(rows) + "</table>"
    html += "<div class=actions>"
    if st["arming"]["state"] != "LOCKED" and st["positions"]:
        html += _big_button(actions["flatten"], "FLATTEN AGAIN", "exit", {"back": "order"})
    html += "</div>"
    return html


#: A close's ``kind`` in the words the card uses. "external" is the
#: service's word for a sell it did not recognise as one of its own legs;
#: the card names that one from what the broker said the order was.
REASON_WORDS = {"protective-stop": "stop", "resting-stop": "stop", "target": "target",
                "take-profit": "target", "spx-stop": "stop at its SPX level",
                "spx-exit": "close-at SPX level", "spx-target": "target at its SPX level",
                "flatten": "FLATTEN"}


def reason_words(c: Mapping[str, Any], order_types: Mapping[str, str]) -> str:
    """Why a position closed, in the card's words (Steve, 2026-09-30: "why
    is 'reason' now showing 'external'?", st-qqxj). 13:38 CT that day: the
    stop sent with the entry filled while the service, not seeing the pair
    whole, was resting a second one, and booked the fill as a sale made
    outside it. The card names such a close by the order the broker says it
    was, marked untracked; a sale really made elsewhere says so."""
    kind = str(c.get("kind") or c.get("reason") or "")
    if kind == "external":
        typ = str(order_types.get(str(c.get("order_id") or "")) or "").upper()
        if typ == "STOP":
            return "stop (an order the service was not tracking)"
        if typ == "LIMIT":
            return "target (an order the service was not tracking)"
        return "closed outside this form"
    return REASON_WORDS.get(kind, kind or "—")


def closed_positions(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The day's closed positions, newest first — one per position, however
    many ``closed`` lines it took (a partial close is a line per part). A
    position still partly held is not closed and is not here."""
    groups: dict[str, dict[str, Any]] = {}
    for c in facts.get("closes") or []:
        key = str(c.get("intent_id") or c.get("order_id") or c.get("ts"))
        g = groups.setdefault(key, {"key": key, "symbol": c.get("symbol"),
                                    "intent_id": c.get("intent_id"), "qty": 0,
                                    "pnl_usd": 0.0, "net_pnl_usd": 0.0,
                                    "value_out": 0.0, "parts": []})
        qty = int(c.get("qty") or 0)
        g["qty"] += qty
        if isinstance(c.get("pnl_usd"), (int, float)):
            g["pnl_usd"] = round(g["pnl_usd"] + float(c["pnl_usd"]), 2)
            # net of fees beside the gross (st-ocnp); a line from before it
            # carried one counts gross
            net = c.get("net_pnl_usd")
            g["net_pnl_usd"] = round(g["net_pnl_usd"] + float(
                net if isinstance(net, (int, float)) else c["pnl_usd"]), 2)
        if isinstance(c.get("exit_price"), (int, float)):
            g["value_out"] += float(c["exit_price"]) * qty
        g["parts"].append(c)
    out = []
    for g in groups.values():
        last = g["parts"][-1]
        if int(last.get("remaining_qty") or 0) > 0:
            continue
        g["last"] = last
        g["closed_at"] = _parse_ts(last.get("ts"))
        g["entry_price"] = last.get("entry_price")
        g["exit_price"] = (round(g["value_out"] / g["qty"], 2) if g["qty"]
                           else last.get("exit_price"))
        out.append(g)
    out.sort(key=lambda g: g["closed_at"] or datetime.min.replace(tzinfo=timezone.utc),
             reverse=True)
    return out


def closed_card(g: Mapping[str, Any], facts: Mapping[str, Any], now: datetime) -> str:
    """One closed position, a card of its own (Steve, 2026-09-30: "after a
    position has closed for whatever reason, collapse it's details - let's
    consider each position to be a card unto itself … permit each order to
    be expanded again", st-qqxj). Collapsed it is one line — the contract,
    when it closed (CT), the money, why; a tap opens the rest and another
    folds it. A ``<details>``, so the tap needs no script; the poll's
    repaint keeps an opened card open by its ``data-key``."""
    last = g["last"]
    name = contract_name(str(g.get("symbol") or ""))
    closed_at = g.get("closed_at")
    when = closed_at.astimezone(CT).strftime("%H:%M:%S") if closed_at else "—"
    # net of both commissions, the card's own arithmetic: the open card's
    # "at stop" is net, and the closed one said the gross — the same trade
    # two numbers apart by the fees (st-ocnp)
    pnl = g.get("net_pnl_usd", g.get("pnl_usd"))
    why = reason_words(last, facts.get("order_types") or {})
    head = (f"<summary><span class=cname>{esc(name)} × {g['qty']}</span>"
            f"<span class='k cwhen'>{when}</span>"
            f"<span class='cpnl {money_class(pnl)}'>{money(pnl)}</span>"
            f"<span class='k cwhy'>{esc(why)}</span></summary>")
    rows = []
    entry, exit_px = g.get("entry_price"), g.get("exit_price")
    io = ""
    if isinstance(entry, (int, float)) and isinstance(exit_px, (int, float)):
        io = f"{entry:.2f} → {exit_px:.2f}"
    iid = str(g.get("intent_id") or "")
    opened = facts["filled"].get(iid) or facts["filled"].get(str(g.get("symbol")))
    if opened and closed_at:
        io += f" · held {ago((closed_at - opened).total_seconds())}"
    if io:
        rows.append(("in → out", io))
    gross = g.get("pnl_usd")
    if isinstance(gross, (int, float)) and isinstance(pnl, (int, float)) and gross != pnl:
        rows.append(("before fees", f"{money(gross)} (${gross - pnl:,.2f} in commissions)"))
    # the stop it last rested at, and how far under the entry's limit —
    # "I had changed the SL to .3 — did that change register?" (st-qqxj)
    stop = (facts.get("stops") or {}).get(iid)
    if stop is not None:
        line = f"{stop:.2f}"
        limit = (facts.get("limits") or {}).get(iid)
        if limit is not None and limit > stop:
            line += f" ({limit - stop:.2f} under the {limit:.2f} limit)"
        rows.append(("stop rested", line))
    rows.append(("reason", why))
    orders = ", ".join(str(p["order_id"]) for p in g["parts"] if p.get("order_id"))
    if orders:
        rows.append(("order", orders))
    body = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in rows)
    return (f"<details class='card closedcard' data-key='{esc(g['key'])}'>{head}"
            f"<table>{body}{_water_line(last, now, row=True)}</table></details>")


def closed_html(facts: Mapping[str, Any], now: datetime) -> str:
    """The day's closed positions as a stack of collapsed cards at the foot
    of the trading page, the most recent on top (st-qqxj)."""
    cards = closed_positions(facts)
    if not cards:
        return ""
    return ("<div class='k closedhead'>closed today</div>"
            + "".join(closed_card(g, facts, now) for g in cards))


def body_refused(reason: str, order_path: str, sel_query: Mapping[str, str]) -> str:
    return (f"<div class=refusal>{esc(reason)}</div>"
            "<div class=actions>" + _link_button(_href(order_path, _at_market(sel_query)), "RE-PRICE", "quiet") + "</div>")


def _href(path: str, params: Mapping[str, str] | None) -> str:
    from .orderpage import _link
    return _link(path, dict(params or {}))


# ── entry points ─────────────────────────────────────────────────────────

def panel_body(service: ExecService, st: Mapping[str, Any], actions: Mapping[str, str], *,
               now: datetime, order_path: str, sel_query: Mapping[str, str] | None = None,
               refused: str | None = None, dismissed: bool = False) -> tuple[str, str]:
    """``(stage, body_html)`` for the card, off the status body and the
    day's journal.

    A refusal belongs to this request, and the card shows it — but never at
    the price of hiding money that is live: a refusal while something is
    live is the page's red box above the card, not a stage, so the editor
    and the exit buttons stay in reach."""
    facts = journal_facts(service)
    live = stage_of(st, facts)
    # A closed position is not this card's any more: it folds into its own
    # card in the stack at the foot of the page (Steve, 2026-09-30, st-qqxj),
    # and this card goes back to no order.
    if live == "closed":
        live = "none"
    stage = "refused" if refused and live == "none" else live
    if dismissed and stage == "refused":
        # a side picked (or ?new=1): the refusal is over (Steve,
        # 2026-09-15); the card renders as no order
        stage = "none"
    bounds = st.get("bounds") or {}
    sel_query = sel_query or {}
    body = ""
    if stage == "refused":
        body = body_refused(refused or "", order_path, sel_query)
    # the live part always renders while money is live; the resting stages
    # only when nothing of this request sits in front of them
    if live == "working":
        body += body_working(service, st, facts, actions, now, bounds)
    elif live == "filled":
        body += body_filled(service, st, facts, actions, now)
    elif live == "exiting":
        body += body_exiting(service, st, facts, actions, now)
    elif stage == "none":
        body += body_none(st, facts, actions, now)
    return stage, f"<div class=body data-stage={stage}>{body}</div>"


def panel_html(service: ExecService, st: Mapping[str, Any], actions: Mapping[str, str], *,
               now: datetime, order_path: str, **kw: Any) -> str:
    """The whole card: the header the script owns (the stage word and
    refresh) around the body it polls. No 'updated', pause or less (Steve,
    2026-09-30: "you can remove the 'update [n] and pause and 'less'
    buttons", st-qqxj); a poll that fails says so in #pollnote, in red,
    until one succeeds."""
    stage, body = panel_body(service, st, actions, now=now, order_path=order_path, **kw)
    # The mode badge and the one ticking clock moved to the page's strip on
    # 2026-09-15 (st-shhi): the card no longer repeats them. The script still
    # ticks whichever element carries id=clock.
    return (
        "<div id=panel class='card panel'>"
        "<div class=hdr>"
        f"<div class=l><span id=stageword class=word style='color:{COLORS[stage]}'>{WORDS[stage]}</span></div>"
        "<div class=r>"
        "<button type=button id=refresh class=ico title='refresh now' aria-label='refresh now'>"
        "<svg width=22 height=22 viewBox='0 0 24 24' fill=none stroke=currentColor stroke-width=2 "
        "stroke-linecap=round stroke-linejoin=round><path d='M21 12a9 9 0 1 1-2.64-6.36'></path>"
        "<path d='M21 3v6h-6'></path></svg></button></div></div>"
        "<div id=pollnote class=pollnote hidden></div>"
        f"<div id=panelbody>{body}</div>"
        "</div>")


PANEL_SCRIPT = """
<script>
(function(){
  var STATE = %(state)s, POLL = %(poll)d;
  // The card is on the page only when there is a stage to show (st-shhi);
  // the clock, the quote and the balances still tick without it (st-2s4u —
  // before this the script returned here and a fresh trading page froze).
  var panel = document.getElementById('panel') || document.body;
  var WORDS = %(words)s, COLORS = %(colors)s;
  function two(n){ return (n < 10 ? '0' : '') + n; }
  function ago(ms){ var s = Math.max(0, Math.floor(ms / 1000));
    if (s < 60) return s + ' s'; var m = Math.floor(s / 60); s = s %% 60;
    if (m < 60) return s ? (m + ' m ' + two(s) + ' s') : (m + ' m');
    var h = Math.floor(m / 60); m = m %% 60; return h + ' h ' + two(m) + ' m'; }
  function clockNow(){ try { return new Date().toLocaleTimeString('en-US', {hour12:false, timeZone:'America/Chicago'}); }
    catch (e) { return new Date().toLocaleTimeString('en-US', {hour12:false}); } }
  function tick(){ var c = document.getElementById('clock'); if (c) c.textContent = clockNow();
    var now = Date.now(); var els = panel.querySelectorAll('.ago[data-at]');
    for (var i = 0; i < els.length; i++) { var at = parseInt(els[i].getAttribute('data-at'), 10);
      if (!isNaN(at)) els[i].textContent = ago(now - at) + ' ago'; } }
  // An input he is typing in is protected from the poll — but only while it
  // is DIRTY (its value differs from what the server rendered) and only while
  // the stage is the same. 2026-09-15 13:21 CT: the stop filled 31 s after
  // the entry, the poll fetched the CLOSED card every 3 s, and the page kept
  // the FILLED editor because a bracket input had focus (st-f3y3).
  function editing(){ var a = document.activeElement;
    return !!(a && a.tagName === 'INPUT' && panel.contains(a) && a.value !== a.defaultValue); }
  function stageNow(){ var b = panel.querySelector('#panelbody .body'); return b ? (b.getAttribute('data-stage') || '') : ''; }
  // A number typed into a SET box outlives the repaint. editing() holds the
  // poll off only while the box has focus; the moment focus leaves (a tap
  // elsewhere, eyes off the screen) the next repaint used to put the resting
  // price back and an Enter after that sent nothing — 2026-09-16 10:19 CT, a
  // target strike typed, Enter, "the dollar amount stayed in the input", no
  // request in the journal (st-4b0p). Typed and unsent is kept, name by name.
  function keepTyped(root){ var out = []; if (!root) return out;
    var ins = root.querySelectorAll('form.adjust input[name]');
    for (var i = 0; i < ins.length; i++) { var a = ins[i];
      if (a.type === 'hidden' || a.value === a.defaultValue) continue;
      out.push({name: a.name, value: a.value, focused: document.activeElement === a,
                start: a.selectionStart, end: a.selectionEnd}); }
    return out; }
  function restoreTyped(root, kept){ if (!root || !kept || !kept.length) return;
    for (var i = 0; i < kept.length; i++) { var k = kept[i];
      var a = root.querySelector('form.adjust input[name="' + k.name + '"]'); if (!a) continue;
      a.value = k.value;
      if (k.focused) { try { a.focus(); if (k.start !== null) a.setSelectionRange(k.start, k.end); } catch (e) {} } } }
  function requestScoped(){ return stageNow() === 'refused'; }
  function apply(j){ var body = document.getElementById('panelbody');
    var changed = !!(j.panel_stage && stageNow() && j.panel_stage !== stageNow());
    // a fill resets the order form's strike to follow the market (st-6ogv)
    if (j.panel_stage && window.__strikeResets && window.__onFilled
        && window.__strikeResets(stageNow() || 'none', j.panel_stage)) { try { window.__onFilled(); } catch (e) {} }
    // the card is on the page hidden while there is nothing to show; a stage
    // arriving from the poll or from a SEND answered in place unhides it
    // (st-igw0), and a position closing hides it again — the close is a card
    // of its own at the foot of the page now (st-qqxj)
    var pn = document.getElementById('panel');
    if (pn && pn !== document.body && j.panel_stage) pn.hidden = (j.panel_stage === 'none');
    if (body && j.panel_body_html && !inflight && (changed || !editing())) { var kept = keepTyped(body); body.innerHTML = j.panel_body_html; restoreTyped(body, kept); }
    if (changed) { var m = document.querySelector('.msg'); if (m) m.parentNode.removeChild(m); }
    // a caption tied to a stage goes when the card leaves it — "not filled
    // yet" under a FILLED card was 2026-09-30's paper-0061 (st-5n3s)
    var tied = document.querySelector('#answer [data-for-stage]');
    if (tied && stageNow() && tied.getAttribute('data-for-stage') !== stageNow()) tied.parentNode.removeChild(tied);
    var w = document.getElementById('stageword'); if (w && j.panel_stage) { w.textContent = WORDS[j.panel_stage] || j.panel_stage; w.style.color = COLORS[j.panel_stage] || '#e5e7eb'; }
    pollNote('');
    // the day's closed positions (st-qqxj): repainted only when they change,
    // and a card he opened stays open
    var cs = document.getElementById('closed');
    if (cs && j.closed_html !== undefined && cs.__html !== j.closed_html) {
      var open = {}, ds = cs.querySelectorAll('details[open]');
      for (var i = 0; i < ds.length; i++) open[ds[i].getAttribute('data-key')] = true;
      cs.innerHTML = j.closed_html; cs.__html = j.closed_html;
      ds = cs.querySelectorAll('details'); for (var i2 = 0; i2 < ds.length; i2++) if (open[ds[i2].getAttribute('data-key')]) ds[i2].open = true; }
    var td = document.getElementById('today'); if (td && j.today_text) td.textContent = j.today_text;
    // a stop fill re-armed the order form (st-d7nt): the order page loads the
    // prepopulated ticket once per re-arm. It never sends.
    if (j.rearm && window.__onRearm) { try { window.__onRearm(j.rearm); } catch (e) {} }
    // the SEND traffic buffer (st-qnbg): repainted only when it changed,
    // scrolled to its newest line at the bottom
    var tr = document.getElementById('traffic');
    if (tr && j.traffic_html !== undefined && tr.__html !== j.traffic_html) {
      tr.innerHTML = j.traffic_html; tr.__html = j.traffic_html;
      var tl = document.getElementById('traffic-lines'); if (tl) tl.scrollTop = tl.scrollHeight; }
    var qd = document.getElementById('quote'); if (qd && j.quote_html) qd.innerHTML = j.quote_html;
    var pc = document.getElementById('position'); if (pc && j.position_html !== undefined && !editing()) { var keptp = keepTyped(pc); pc.innerHTML = j.position_html || ''; restoreTyped(pc, keptp); }
    var jn = document.getElementById('journal'); if (jn && j.journal_html) jn.innerHTML = j.journal_html;
    var bl = document.getElementById('balances'); if (bl && j.balances_html) bl.innerHTML = j.balances_html;
    // the strip — PAPER or LIVE, the arming word, STOP — follows the poll, so a
    // switch made on the other page shows here without a reload (co-8mb1z)
    var sp = document.getElementById('strip'); if (sp && j.state_html) sp.outerHTML = j.state_html;
    // The order form's ticket and strikes, priced from this same answer
    // (st-644f). Held off while a box has something typed in it or a
    // reprice of his own is still out, and dropped outright when a newer
    // reprice began while the poll was away: a stale paint over a fresh
    // price is the one thing worse than a slow one.
    if (j.fd0_html && window.__paintTicket && !(window.__formBusy && window.__formBusy())
        && !(window.__pollSeq && j.__seq !== undefined && j.__seq !== window.__pollSeq())) {
      try { window.__paintTicket(j); } catch (e) {} }
    if (window.__onQuote) { try { window.__onQuote(j); } catch (e) {} } }
  // a poll that fails is said on the card, in red, until one succeeds —
  // the 'updated' line that used to carry it is gone (st-qqxj)
  function pollNote(text){ var n = document.getElementById('pollnote'); if (!n) return;
    n.textContent = text || ''; n.hidden = !text;
    if (text) { var pn = document.getElementById('panel'); if (pn) pn.hidden = false; } }
  function poll(force){ if (!force && (document.visibilityState === 'hidden' || requestScoped())) return;
    var parts = [];
    if (window.__sym) { parts.push('symbol=' + encodeURIComponent(window.__sym));
      if (window.__lots) parts.push('lots=' + encodeURIComponent(window.__lots)); }
    // the order page hands the poll its selection, so what comes back is
    // this ticket priced now, not just a quote (st-644f)
    var mine = window.__pollQuery ? window.__pollQuery() : '';
    if (mine) parts.push(mine);
    var u = STATE + (parts.length ? '?' + parts.join('&') : '');
    // the reprice counter as it stood when this poll left, so an answer that
    // crosses a reprice of his own is dropped rather than painted
    var atSeq = window.__pollSeq ? window.__pollSeq() : undefined;
    fetch(u, {headers:{'Accept':'application/json'}}).then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(j){ if (atSeq !== undefined) j.__seq = atSeq; apply(j); })
      .catch(function(e){ pollNote('poll failed: ' + (e && e.message ? e.message : e) + ' — the card is as of '
        + clockNow() + ' CT or earlier'); }); }
  // UPDATE once: the button goes dead the moment the form leaves, so a
  // second tap while the first adjust is still at the broker (four seconds
  // of cancel-and-rest, 2026-09-15 14:07 CT) is not a second adjust (st-ff5j)
  // … and from that moment the poll leaves the card body alone, so the
  // editor does not flash the server's old values while the new ones are on
  // their way (the 104 he saw twice, 2026-09-15 14:07 CT, st-gw5m)
  var inflight = false;
  // One leg, sent by fetch, painted in place: no navigation, no blink, the
  // answer at the top of the card (st-bmaz). Without a script the same form
  // posts and the page redirects as before.
  function note(text, bad){ var n = document.getElementById('adjustnote'); if (!n) return;
    n.textContent = text || ''; n.className = 'k ' + (bad ? 'bad' : 'ok'); }
  // SEND, one tap, answered in place (st-igw0): the button goes dead while
  // the order is out, the answer lands in #answer above the card, the card
  // paints from the same answer, and a fresh token arms the button again.
  function answerBox(text, bad, forStage){ var a = document.getElementById('answer'); if (!a) return;
    a.innerHTML = ''; if (!text) return;
    // an answer about a stage the card has already left is not said (st-5n3s)
    if (forStage && stageNow() && stageNow() !== forStage) return;
    var d = document.createElement('div'); d.className = bad ? 'bad' : 'msg';
    if (forStage) d.setAttribute('data-for-stage', forStage);
    d.textContent = text; a.appendChild(d); var old = document.querySelector('.msg:not(#answer .msg)'); if (old && !bad) old.parentNode.removeChild(old); }
  document.addEventListener('submit', function(e){ var f = e.target; if (!f || !f.classList || !f.classList.contains('sendform')) return;
    var b = f.querySelector('button'); if (b && b.disabled) { e.preventDefault(); return; }
    if (!window.fetch || !window.FormData) { if (b) { b.disabled = true; b.textContent = 'SENDING…'; } return; }
    e.preventDefault();
    var fd = new FormData(f); fd.set('ajax', '1');
    // what the boxes say rides every SEND as typed, even if the reprice that
    // refreshes the hidden fields has not come back yet (st-m3bl). Since
    // 2026-09-30 the stop box writes `stopoff`, the price box `limit` —
    // only `stop` was carried, so a .3 typed and SENT inside the 600 ms
    // before the reprice went out as the old stop (st-qqxj). The close-at
    // box is gone from the entry (st-a54y, 2026-10-01). The strike the
    // ticket shows is pinned in the hidden fields; a strike he typed or
    // stepped replaces it.
    var sf = document.getElementById('sel');
    if (sf) { ['stop', 'stopoff', 'limit', 'lots'].forEach(function(n){
        var el = sf.elements[n]; if (el) fd.set(n, el.value || ''); });
      var sk = sf.elements['strike']; if (sk && sk.value) { fd.set('strike', sk.value); fd.delete('delta'); } }
    if (b) { b.disabled = true; b.textContent = 'SENDING…'; }
    // a SEND shows the traffic buffer, and it stays until he taps (st-qnbg)
    if (window.__paneShow) window.__paneShow('send');
    fetch(f.getAttribute('action'), {method: 'POST', body: fd, headers: {'Accept': 'application/json'}})
      .then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(j){ apply(j); answerBox(j.bad || j.msg || '', !!j.bad, j.msg_stage || null);
        var n = f.querySelector('input[name=nonce]'); if (n && j.send_nonce) n.value = j.send_nonce;
        if (b) { b.disabled = false; b.textContent = 'SEND'; }
        if (window.__panelPoll) window.__panelPoll(true); })
      .catch(function(err){ if (b) { b.disabled = false; b.textContent = 'SEND'; }
        answerBox('not sent, or not answered — ' + (err && err.message ? err.message : err) + '. Read the card before sending again.', true); }); });
  // The open position's stop and target, each as the ticket's stop is
  // (Steve, 2026-09-30, st-qqxj): a dollar box — the leg's distance from the
  // fill — that + widens by 0.10 and − narrows, and an SPX box. Typing or
  // stepping in one writes NA in the other and marks it live; SET sends the
  // live one. The boxes keep their number until SET sends it.
  function legNum(v){ v = (v || '').trim(); if (!v || /^na$/i.test(v)) return NaN; return parseFloat(v); }
  function legPts(n){ var t = n.toFixed(2).replace(/0+$/, '').replace(/\.$/, ''); return t.indexOf('0.') === 0 ? t.slice(1) : t; }
  function legLive(f, which){ var l = f.querySelector('input[name=live]'); if (l) l.value = which;
    var other = f.querySelector(which === 'off' ? 'input.spxbox' : 'input.offbox'); if (other) other.value = 'NA'; }
  document.addEventListener('click', function(e){ var b = e.target && e.target.closest ? e.target.closest('button.step') : null;
    if (!b || b.getAttribute('data-for') !== 'off') return; e.preventDefault();
    var f = b.closest('form'), box = f ? f.querySelector('input.offbox') : null; if (!box) return;
    var v = legNum(box.value); if (isNaN(v) || v <= 0) v = legNum(box.defaultValue); if (isNaN(v) || v <= 0) v = 0.2;
    var n = Math.round(v * 100) + Number(b.getAttribute('data-step')) * 10; if (n < 5) n = 5;
    box.value = legPts(n / 100); legLive(f, 'off'); });
  document.addEventListener('input', function(e){ var t = e.target, f = t && t.closest ? t.closest('form.adjust') : null; if (!f) return;
    if (t.classList.contains('offbox')) legLive(f, 'off'); else if (t.classList.contains('spxbox')) legLive(f, 'spx'); });
  // a tap into a box that reads NA clears it for typing, as on the ticket
  document.addEventListener('focusin', function(e){ var t = e.target;
    if (t && t.closest && t.closest('form.adjust') && t.tagName === 'INPUT' && /^na$/i.test((t.value || '').trim())) t.value = ''; });
  document.addEventListener('submit', function(e){ var f = e.target; if (!f || !f.classList || !f.classList.contains('adjust')) return;
    var b = f.querySelector('button.set') || f.querySelector('button'); if (b && b.disabled) { e.preventDefault(); return; }
    if (!window.fetch || !window.FormData) { if (b) { b.disabled = true; b.textContent = '…'; } inflight = true; return; }
    e.preventDefault();
    var fd = new FormData(f); fd.set('ajax', '1');
    var inputs = f.querySelectorAll('input,button'); for (var i = 0; i < inputs.length; i++) inputs[i].disabled = true;
    if (b) b.textContent = '…';
    inflight = true; note('sending…', false);
    fetch(f.getAttribute('action'), {method: 'POST', body: fd, headers: {'Accept': 'application/json'}})
      .then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(j){ inflight = false;
        // a leg the service took is the card's own number now: what was
        // typed (and the NA in the other box) is not kept over the answer —
        // it hid the new SPX level behind NA (st-qqxj). A refusal keeps it.
        if (!j.bad) { for (var k = 0; k < inputs.length; k++) if (inputs[k].tagName === 'INPUT') inputs[k].value = inputs[k].defaultValue; }
        apply(j); note(j.bad || j.msg || '', !!j.bad); })
      .catch(function(err){ inflight = false;
        for (var i = 0; i < inputs.length; i++) inputs[i].disabled = false; if (b) b.textContent = 'SET';
        note('not sent — ' + (err && err.message ? err.message : err) + '; the card may be stale, refresh', true); }); });
  var refreshBtn = document.getElementById('refresh');
  if (refreshBtn) refreshBtn.addEventListener('click', function(){ poll(true); });
  tick(); setInterval(tick, 1000); setInterval(function(){ poll(false); }, POLL * 1000);
  window.__panelPoll = poll;
})();
</script>
"""
