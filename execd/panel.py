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

* one ticking clock, in the header, Central time; every other time on the
  card is *x ago* and ticks too;
* a contract is named ``C7630`` / ``P7600`` — right and strike, nothing else;
* one net number, commissions included (``NET NOW`` is what a market sell
  nets after both commissions, the same arithmetic as the position row);
* the filled stage is the live editor for the stop and the take-profit;
* a working entry has one control, CANCEL AND RE-PRICE, and no STOP;
* no footers — the card is as tall as its stage and no taller. ``more`` /
  ``less`` folds the detail rows away.

Server-rendered, so it works with no script; the script only ticks the
clocks, polls the body, and folds the detail.
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
 .panel .ctl{background:transparent;color:#9ca3af;border:1px solid #374151;border-radius:8px;min-height:36px;padding:0 12px;font-size:.9em;cursor:pointer;font-family:inherit}
 .panel .ico{display:flex;align-items:center;justify-content:center;width:44px;height:44px;background:#1f2937;color:#e5e7eb;border:0;border-radius:8px;cursor:pointer}
 .panel .row2{display:flex;align-items:center;justify-content:space-between;gap:.75em;margin-top:8px}
 .panel .row2 .l{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
 .panel .title{margin-top:12px;font-size:1.15em;font-weight:700}
 .panel .hero{display:flex;align-items:baseline;justify-content:space-between;gap:.75em;margin-top:8px}
 .panel .hero .n{font-size:2em;font-weight:700}
 .panel .neg{color:#f87171}.panel .pos{color:#34d399}.panel .amber{color:#fbbf24}.panel .plain{color:#e5e7eb}
 .panel table{margin-top:8px}
 .panel .actions{display:flex;flex-direction:column;gap:8px;margin-top:12px}
 .panel .actions form{margin:0}.panel .actions .big{margin:0}
 .panel .editor{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
 .panel .editor label{display:flex;flex-direction:column;gap:4px;color:#9ca3af;font-size:.9em}
 .panel .editor input{width:100%;box-sizing:border-box;font-size:1.1em;padding:.6em;border-radius:8px;border:1px solid #374151;background:#0b1020;color:#e5e7eb}
 .panel .editor .money{font-size:.9em;font-weight:700}
 .panel .editor .level{font-size:.85em;color:#9ca3af;margin-left:.6em}
 .panel .hint{margin-top:6px;font-size:.8em;color:#6b7280}
 .panel .editor form{margin:0}.panel .legrow{display:flex;gap:6px;align-items:stretch}
 .panel .editor button.set{min-height:44px;padding:0 12px;border-radius:8px;border:1px solid #374151;font-weight:700;cursor:pointer;background:#1f2937;color:#e5e7eb;font-family:inherit}
 .panel .editor button.set:disabled{opacity:.5}
 .panel #adjustnote{margin-top:8px;min-height:1.2em}.panel #adjustnote.bad{background:#7f1d1d;border:1px solid #ef4444;border-radius:8px;padding:.4em .7em;color:#fecaca}
 .panel #adjustnote.ok{color:#34d399}
 .panel .refusal{margin-top:12px;background:#7f1d1d;border:1px solid #ef4444;border-radius:10px;padding:.7em 1em}
 .panel.compact .full{display:none}
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
    for e in service.journal.read():
        ev = e.get("event")
        ts = _parse_ts(e.get("ts"))
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
    return {"sent": sent, "exit_sent": exit_sent, "filled": filled, "last_close": last_close}


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
    day = st["day"]
    pnl = st.get("pnl") or {}
    used = day["attempts_used"]
    total = used + day["attempts_left"]
    parts = []
    if pnl.get("closes"):
        parts.append(f"realized {money(pnl.get('realized_usd'))} over {pnl['closes']} close(s)")
    parts.append(f"attempts {used} of {total} used")
    parts.append(f"headroom ${day['loss_headroom_usd']:,.2f}")
    return f"<tr><td>today</td><td>{esc(' · '.join(parts))}</td></tr>"


def _last_row(facts: Mapping[str, Any], now: datetime) -> str:
    c = facts.get("last_close")
    if not c:
        return ""
    name = contract_name(str(c.get("symbol", "")))
    pnl = c.get("pnl_usd")
    return (f"<tr><td>last</td><td>{esc(name)} closed {ago_span(_parse_ts(c.get('ts')), now)}, "
            f"<span class='{money_class(pnl)}'>{money(pnl)}</span></td></tr>")


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
        return "<div class='k stop-on' style='margin-top:8px'>STOP IS ON — no new positions</div>"
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
    html += f"<table class=full>{_last_row(facts, now)}{_today_row(st)}</table>"
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
            on_fill.append(f"target {float(mult):g}× the fill")
        if on_fill:
            rows.append(f"<tr><td>on fill</td><td>{' · '.join(on_fill)}</td></tr>")
        if w.get("order_id"):
            rows.append(f"<tr><td>order</td><td>{esc(w['order_id'])}</td></tr>")
        rows.append(_today_row(st))
        html += "<table class=full>" + "".join(rows) + "</table>"
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
        # the live editor (st-fn5y) — both trigger conditions, one button
        stop_val = f"{p['stop_price']:.2f}" if p.get("stop_price") is not None else ""
        target_val = f"{p['target_price']:.2f}" if p.get("target_price") is not None else ""
        # each leg shows both forms — the resting price in the box, the SPX
        # level beside the money: "stop 10.30 · SPX 7585.03" (st-2j3m)
        stop_note = (f"<span class='money {money_class(v.get('at_stop_usd'))}'>{money(v.get('at_stop_usd'))}</span>"
                     if p.get("stop_price") is not None else "<span class='money neg'>NO STOP RESTING</span>")
        if p.get("stop_spx") is not None:
            stop_note += f"<span class=level>SPX {float(p['stop_spx']):.2f}</span>"
        target_note = (f"<span class='money {money_class(v.get('at_target_usd'))}'>{money(v.get('at_target_usd'))}</span>"
                       if p.get("target_price") is not None else "<span class='money amber'>NO TARGET RESTING</span>")
        if p.get("target_spx") is not None:
            target_note += f"<span class=level>SPX {float(p['target_spx']):.2f}</span>"
        # One leg at a time (Steve, 2026-09-15: "It'll be one or the other.
        # I'd like to be able to enter the value in either and just hit
        # enter to submit … make this as instant as possible", st-bmaz):
        # each leg is its own form, Enter sends it, SET is the tap target;
        # the script posts it by fetch and paints the answer into the card.
        # The box takes a price or an SPX level, told apart by the '.'
        # (Steve, 2026-09-16, st-2j3m); the route reads it by that rule.
        def leg_form(leg: str, val: str, note: str) -> str:
            return (f"<form method=post action='{actions['order_adjust']}' class='adjust leg' data-leg={leg}>"
                    f"<input type=hidden name=symbol value='{esc(sym)}'>"
                    "<input type=hidden name=ajax value=''>"
                    f"<label>{leg}<span class=legrow>"
                    f"<input name={leg} inputmode=decimal enterkeyhint=go autocomplete=off value='{val}'>"
                    f"<button class=set aria-label='set the {leg}'>SET</button></span>{note}</label></form>")
        html += ("<div id=adjustnote class=k></div><div class=editor>"
                 + leg_form("stop", stop_val, stop_note)
                 + leg_form("target", target_val, target_note) + "</div>"
                 "<div class='k hint'>a number with a '.' is a price (10.30); without one it "
                 "is an SPX level (7585)</div>")
        html += f"<table class=full>{_today_row(st)}</table>"
    html += "<div class=actions>"
    if st["arming"]["state"] != "LOCKED":
        html += _big_button(actions["flatten"], "FLATTEN", "exit", {"back": "order"})
    if not st["arming"]["killed"]:
        html += _big_button(actions["stop"], "STOP", "stop", {"back": "order"})
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
        html += "<table class=full>" + "".join(rows) + "</table>"
    html += "<div class=actions>"
    if st["arming"]["state"] != "LOCKED":
        html += _big_button(actions["flatten"], "FLATTEN AGAIN", "exit", {"back": "order"})
    html += "</div>"
    return html


def body_closed(st, facts, actions, now, order_path) -> str:
    c = facts["last_close"]
    name = contract_name(str(c.get("symbol", "")))
    closed_at = _parse_ts(c.get("ts"))
    pnl = c.get("pnl_usd")
    html = f"<div class=title>{esc(name)} × {c.get('qty')} · closed {ago_span(closed_at, now)}</div>"
    html += (f"<div class=hero><div class=k>P&amp;L</div>"
             f"<div class='n {money_class(pnl)}'>{money(pnl)}</div></div>")
    entry = c.get("entry_price")
    exit_px = c.get("exit_price")
    io = ""
    if isinstance(entry, (int, float)) and isinstance(exit_px, (int, float)):
        io = f"{entry:.2f} → {exit_px:.2f}"
    opened = facts["filled"].get(str(c.get("intent_id"))) or facts["filled"].get(str(c.get("symbol")))
    if opened and closed_at:
        io += f" · held {ago((closed_at - opened).total_seconds())}"
    rows = []
    if io:
        rows.append(f"<tr><td>in → out</td><td>{esc(io)}</td></tr>")
    rows.append(f"<tr><td>reason</td><td>{esc(c.get('kind') or c.get('reason') or '—')}</td></tr>")
    water = _water_line(c, now, row=True)
    if water:
        rows.append(water)
    rows.append(_today_row(st))
    html += "<table class=full>" + "".join(rows) + "</table>"
    html += "<div class=actions>" + _link_button(order_path + "?new=1", "NEW ORDER", "quiet") + "</div>"
    return html


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
    if refused and live in ("none", "closed"):
        stage = "refused"
    else:
        stage = live
    if dismissed and stage in ("closed", "refused"):
        # NEW ORDER, or a side picked: the finished card is over (Steve,
        # 2026-09-15); the card renders as no order and the page marks the
        # close it dismissed so the poll does not bring it back (st-igw0)
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
    elif stage == "closed":
        body += body_closed(st, facts, actions, now, order_path)
    elif stage == "none":
        body += body_none(st, facts, actions, now)
    return stage, f"<div class=body data-stage={stage}>{body}</div>"


def panel_html(service: ExecService, st: Mapping[str, Any], actions: Mapping[str, str], *,
               now: datetime, order_path: str, **kw: Any) -> str:
    """The whole card: the header the script owns (stage word, badge, clock,
    refresh, updated, pause, more/less) around the body it polls."""
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
        "<div class=row2><div class=l><span class=k>updated "
        f"<span id=updated class=ago data-at={int(now.timestamp() * 1000)}>just now</span></span>"
        "<button type=button id=pause class=ctl>pause</button></div>"
        "<button type=button id=more class=ctl>less</button></div>"
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
  var paused = false, WORDS = %(words)s, COLORS = %(colors)s;
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
    // the card is on the page hidden while there is nothing to show; a stage
    // arriving from the poll or from a SEND answered in place unhides it (st-igw0)
    var pn = document.getElementById('panel');
    // a close he dismissed with NEW ORDER stays dismissed: the page carries its stamp
    var dismissed = !!(pn && j.panel_stage === 'closed' && pn.getAttribute('data-dismissed')
                       && pn.getAttribute('data-dismissed') === String(j.last_close_ts || ''));
    if (pn && j.panel_stage && j.panel_stage !== 'none' && !dismissed) pn.hidden = false;
    if (body && j.panel_body_html && !dismissed && !inflight && (changed || !editing())) { var kept = keepTyped(body); body.innerHTML = j.panel_body_html; restoreTyped(body, kept); }
    if (changed) { var m = document.querySelector('.msg'); if (m) m.parentNode.removeChild(m); }
    var w = document.getElementById('stageword'); if (w && j.panel_stage && !dismissed) { w.textContent = WORDS[j.panel_stage] || j.panel_stage; w.style.color = COLORS[j.panel_stage] || '#e5e7eb'; }
    var u = document.getElementById('updated'); if (u) { u.setAttribute('data-at', String(Date.now())); u.textContent = 'just now'; }
    var qd = document.getElementById('quote'); if (qd && j.quote_html) qd.innerHTML = j.quote_html;
    var pc = document.getElementById('position'); if (pc && j.position_html !== undefined && !editing()) { var keptp = keepTyped(pc); pc.innerHTML = j.position_html || ''; restoreTyped(pc, keptp); }
    var jn = document.getElementById('journal'); if (jn && j.journal_html) jn.innerHTML = j.journal_html;
    var bl = document.getElementById('balances'); if (bl && j.balances_html) bl.innerHTML = j.balances_html;
    if (window.__onQuote) { try { window.__onQuote(j); } catch (e) {} } }
  function poll(force){ if (!force && (paused || document.visibilityState === 'hidden' || requestScoped())) return;
    var u = STATE + (window.__sym ? ('?symbol=' + encodeURIComponent(window.__sym)
      + (window.__lots ? '&lots=' + encodeURIComponent(window.__lots) : '')) : '');
    fetch(u, {headers:{'Accept':'application/json'}}).then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then(apply)
      .catch(function(e){ var up = document.getElementById('updated'); if (up) { up.removeAttribute('data-at'); up.textContent = 'poll failed: ' + (e && e.message ? e.message : e); } }); }
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
  function answerBox(text, bad){ var a = document.getElementById('answer'); if (!a) return;
    a.innerHTML = ''; if (!text) return; var d = document.createElement('div'); d.className = bad ? 'bad' : 'msg';
    d.textContent = text; a.appendChild(d); var old = document.querySelector('.msg:not(#answer .msg)'); if (old && !bad) old.parentNode.removeChild(old); }
  document.addEventListener('submit', function(e){ var f = e.target; if (!f || !f.classList || !f.classList.contains('sendform')) return;
    var b = f.querySelector('button'); if (b && b.disabled) { e.preventDefault(); return; }
    if (!window.fetch || !window.FormData) { if (b) { b.disabled = true; b.textContent = 'SENDING…'; } return; }
    e.preventDefault();
    var fd = new FormData(f); fd.set('ajax', '1');
    // the stop box's text rides every SEND as typed, even if the reprice
    // that refreshes the hidden fields has not come back yet (st-m3bl)
    var sf = document.getElementById('sel'); if (sf && sf.elements['stop']) fd.set('stop', sf.elements['stop'].value || '');
    if (b) { b.disabled = true; b.textContent = 'SENDING…'; }
    fetch(f.getAttribute('action'), {method: 'POST', body: fd, headers: {'Accept': 'application/json'}})
      .then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(j){ apply(j); answerBox(j.bad || j.msg || '', !!j.bad);
        var n = f.querySelector('input[name=nonce]'); if (n && j.send_nonce) n.value = j.send_nonce;
        if (b) { b.disabled = false; b.textContent = 'SEND'; }
        if (window.__panelPoll) window.__panelPoll(true); })
      .catch(function(err){ if (b) { b.disabled = false; b.textContent = 'SEND'; }
        answerBox('not sent, or not answered — ' + (err && err.message ? err.message : err) + '. Read the card before sending again.', true); }); });
  document.addEventListener('submit', function(e){ var f = e.target; if (!f || !f.classList || !f.classList.contains('adjust')) return;
    var b = f.querySelector('button'); if (b && b.disabled) { e.preventDefault(); return; }
    if (!window.fetch || !window.FormData) { if (b) { b.disabled = true; b.textContent = '…'; } inflight = true; return; }
    e.preventDefault();
    var fd = new FormData(f); fd.set('ajax', '1');
    var inputs = f.querySelectorAll('input,button'); for (var i = 0; i < inputs.length; i++) inputs[i].disabled = true;
    if (b) b.textContent = '…';
    inflight = true; note('sending…', false);
    fetch(f.getAttribute('action'), {method: 'POST', body: fd, headers: {'Accept': 'application/json'}})
      .then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(j){ inflight = false; apply(j); note(j.bad || j.msg || '', !!j.bad); })
      .catch(function(err){ inflight = false;
        for (var i = 0; i < inputs.length; i++) inputs[i].disabled = false; if (b) b.textContent = 'SET';
        note('not sent — ' + (err && err.message ? err.message : err) + '; the card may be stale, refresh', true); }); });
  var pauseBtn = document.getElementById('pause');
  if (pauseBtn) pauseBtn.addEventListener('click', function(){ paused = !paused; pauseBtn.textContent = paused ? 'resume' : 'pause';
    var u = document.getElementById('updated'); if (u) { if (paused) { u.removeAttribute('data-at'); u.textContent = 'paused'; } else poll(true); } });
  var refreshBtn = document.getElementById('refresh');
  if (refreshBtn) refreshBtn.addEventListener('click', function(){ poll(true); });
  var moreBtn = document.getElementById('more');
  function setCompact(on){ if (on) panel.classList.add('compact'); else panel.classList.remove('compact');
    if (moreBtn) moreBtn.textContent = on ? 'more' : 'less'; try { localStorage.setItem('execd.panel.compact', on ? '1' : '0'); } catch (e) {} }
  if (moreBtn) moreBtn.addEventListener('click', function(){ setCompact(!panel.classList.contains('compact')); });
  try { if (localStorage.getItem('execd.panel.compact') === '1') setCompact(true); } catch (e) {}
  tick(); setInterval(tick, 1000); setInterval(function(){ poll(false); }, POLL * 1000);
  window.__panelPoll = poll;
})();
</script>
"""
