"""The order form's HTML — server-rendered, one small inline script. [st-k6gl]

Every element on ``/exec/order`` is here; the numbers come from
``execd.orderform`` and the money card from the same status body the
operations page reads. Works with no script at all (every control is a link
or a form); the script only keeps the quote, the FD0 block and the position
fresh without reloading a page that may have a number half-typed on it.

Built for the iPad first: full-width buttons, tap-sized rows, numeric
keyboards, nothing that needs a hover or a key.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from .orderform import (
    DEFAULT_ATTEMPTS, DEFAULT_BUDGET_USD, POLL_S, Priced, Selection, next_weekday,
)
from .panel import COLORS, PANEL_SCRIPT, PANEL_STYLE, WORDS, contract_name, panel_html
from .service import CONTRACT_MULTIPLIER, CT, ExecService
from .stops import take_profit_price

_ORDER_STYLE = """
 .side{display:flex;gap:.6em}.side a{flex:1;text-align:center;text-decoration:none}
 .side a.on{outline:3px solid #e5e7eb}
 a.big{display:block;padding:.9em;font-size:1.25em;border-radius:8px;color:#fff;text-align:center;text-decoration:none}
 a.bull{background:#059669}a.bear{background:#dc2626}
 .exp a{color:#e5e7eb;margin-right:1em}.exp a.on{font-weight:700;text-decoration:underline}
 table.strikes{width:100%;border-collapse:collapse}table.strikes td{padding:.55em .4em;border-bottom:1px solid #1f2937;color:#e5e7eb}
 table.strikes tr.chosen td{background:#1f2937;font-weight:700}
 table.strikes a{color:#e5e7eb;text-decoration:none;display:block}
 .inputs{display:grid;grid-template-columns:1fr 1fr 1fr;gap:.6em;margin:.6em 0}
 .inputs label{display:block;color:#9ca3af;font-size:.9em}
 .warn{color:#fbbf24}.cost{font-size:1.15em;font-weight:700}
 .fd0 td:first-child{color:#9ca3af;width:55%}
 button.send{background:#dc2626}button.preview{background:#2563eb}
 .embed body{padding:.5em}
 .strip{display:flex;align-items:center;justify-content:space-between;gap:.75em;margin:.2em 0 .6em}
 .strip .l,.strip .r{display:flex;align-items:center;gap:.6em;min-width:0}
 .strip .badge{font-weight:700;font-size:.8em;padding:4px 8px;border-radius:6px;letter-spacing:.04em}
 .strip .badge.paper{background:#fbbf24;color:#111}.strip .badge.live{background:#dc2626;color:#fff}
 .strip .word{font-size:1.15em;font-weight:700}
 .strip .clock{font-size:1.05em;font-weight:600;color:#9ca3af;font-variant-numeric:tabular-nums}
 .strip form.inline{margin:0;display:inline}
 .chip{display:inline-flex;align-items:center;height:44px;padding:0 14px;border-radius:8px;font-weight:700;
       border:0;font-size:1em;font-family:inherit;text-decoration:none;cursor:pointer}
 .chip.stopbtn{background:#dc2626;color:#fff}.chip.quiet{background:#1f2937;color:#9ca3af}
 .chip.stop-on{background:#7f1d1d;color:#fca5a5}
 .row{display:flex;align-items:center;gap:.6em;flex-wrap:wrap}
 .row .grow{flex-grow:1}
 .exp2 a.chip{color:#9ca3af;background:transparent;border:1px solid #374151}.exp2 a.chip.on{background:#1f2937;color:#fff;border-color:#1f2937}
 .dl{display:flex;align-items:center;gap:.4em}.dl input{width:5em;height:44px;box-sizing:border-box;font-size:1.15em;text-align:center;
       padding:0 .5em;border-radius:8px;border:1px solid #374151;background:#0b1020;color:#e5e7eb}
 .side a{outline:0}.side a.on{outline:3px solid #e5e7eb}.side a.bear.off{background:#7f1d1d;color:#fca5a5}.side a.bull.off{background:#064e3b;color:#6ee7b7}
 .trow{display:flex;align-items:baseline;justify-content:space-between;gap:.75em;margin:.25em 0}
 .tbig{font-size:1.5em;font-weight:700}.neg{color:#f87171;font-weight:700}.pos{color:#34d399;font-weight:700}
 details.more summary{color:#60a5fa;cursor:pointer;list-style:none}details.more summary::-webkit-details-marker{display:none}
 .detail{display:none;margin-top:.5em}.card:has(details.more[open]) .detail{display:block}
 details.inputs2{margin-top:.5em}details.inputs2 summary{color:#9ca3af;cursor:pointer;font-size:.9em}
 .foot{display:flex;justify-content:space-between;gap:.75em;color:#9ca3af;font-size:.9em;margin-top:.4em}
"""

_SCRIPT = """
<script>
(function(){
  var PRICE = %(price)s;
  var form = document.getElementById('sel');
  window.__sym = %(symbol)s;
  function q(extra){ var d = new FormData(form); var o = {}; d.forEach(function(v,k){ if(v!=='') o[k]=v; });
    for (var k in (extra||{})) o[k]=extra[k]; return new URLSearchParams(o).toString(); }
  function reprice(){ if(!form) return;
    fetch(PRICE + '?' + q(), {headers:{'Accept':'application/json'}}).then(function(r){return r.json();}).then(function(j){
      var f = document.getElementById('fd0'); if (f && j.fd0_html) f.innerHTML = j.fd0_html;
      var s = document.getElementById('strikes'); if (s && j.strikes_html) s.innerHTML = j.strikes_html;
      var p = document.getElementById('previewform'); if (p && j.preview_fields_html) p.innerHTML = j.preview_fields_html;
      if (j.contract) window.__sym = j.contract.symbol;
    }).catch(function(){}); }
  if (form) { ['delta','budget','attempts','lots'].forEach(function(n){ var el = form.elements[n];
    if (el) { el.addEventListener('change', reprice); el.addEventListener('input', function(){ clearTimeout(window.__t); window.__t = setTimeout(reprice, 600); }); } }); }
})();
</script>
"""


_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._")


def _q(value: str) -> str:
    """Percent-encode a query value. Hand-rolled because ``urllib`` is a
    transport root the wall test forbids in every execd module but the
    transport's own (tests/execd/test_wall.py)."""
    return "".join(ch if ch in _SAFE else "".join(f"%{b:02X}" for b in ch.encode("utf-8"))
                   for ch in value)


def _link(path: str, params: Mapping[str, str]) -> str:
    return path + ("?" + "&".join(f"{_q(k)}={_q(v)}" for k, v in params.items()) if params else "")


def money(v: Any) -> str:
    from .page import _money
    return _money(v)


def esc(v: Any) -> str:
    from .page import esc as _esc
    return _esc(v)


# ── fragments (each also served as JSON for the script) ──────────────────

def state_html(st: dict[str, Any], actions: Mapping[str, str] | None = None,
               now: datetime | None = None) -> str:
    """The strip: the mode badge, the arming word, the one ticking clock, and
    STOP — the same on every stage (design docs/design/order-page, st-shhi).
    STOP posts back to this page; clearing it needs the passphrase and lives
    on the account page, one tap away."""
    a = st["arming"]
    mode = str(st.get("mode", "live"))
    badge = ("<span class='badge paper'>PAPER</span>" if mode == "paper"
             else "<span class='badge live'>LIVE</span>")
    state = a["state"]
    word = f"<span class='word {state}'>{state.replace('_', ' ')}</span>"
    clock = (now.astimezone(CT) if now else datetime.now(CT)).strftime("%H:%M:%S")
    right = ""
    if actions:
        if a["killed"]:
            right = (f"<a class='chip stop-on' href='{actions['account']}'>STOP ON · clear</a>")
        else:
            right = (f"<form method=post action='{actions['stop']}' class=inline>"
                     "<input type=hidden name=back value='order'>"
                     "<button class='chip stopbtn'>STOP</button></form>")
        right += f"<a class='chip quiet' href='{actions['account']}'>account</a>"
    return (f"<div class=strip><div class=l>{badge}{word}"
            f"<span id=clock class=clock>{clock}</span></div>"
            f"<div class=r>{right}</div></div>")


def ticket_html(priced: Priced, bounds: Any) -> str:
    """The ticket in three lines — what will be sent, the cut, the two legs
    and what each nets — with the derivation behind *more*. Replaces the
    FD0 table as the thing Steve reads before PREVIEW (st-shhi)."""
    if priced.error and priced.contract is None:
        return f"<div class=bad>{esc(priced.error)}</div>"
    c = priced.contract
    name = contract_name(c.symbol)
    head = (f"<div class=trow><div class=tbig>{esc(name)} × {priced.lots} at {priced.limit:.2f}</div>"
            f"<div class=tbig>{money(-(priced.cost_usd or 0)).lstrip('-')}</div></div>")
    if priced.error:
        return f"<div class=card>{head}<div class=bad>{esc(priced.error)}</div></div>"
    t = priced.ticket
    d = t.derivation
    side = "below" if t.right == "CALL" else "above"
    sign = "≤" if t.right == "CALL" else "≥"
    if priced.stop_price is not None:
        stop_txt = (f"stop rests at <b>{priced.stop_price:.2f}</b> → "
                    f"<span class=neg>{money(priced.net_at_stop_usd)}</span>")
    else:
        stop_txt = f"<span class=neg>no resting stop — {esc(priced.stop_note or 'none')}</span>"
    line2 = (f"<div class=trow><span>cut if SPX {sign} <b>{t.stop_trigger_spx:.2f}</b> "
             f"<span class=k>({d.stop_distance_spx:.2f} {side})</span></span><span>{stop_txt}</span></div>")
    target_txt = ""
    try:
        multiple = float(getattr(bounds, "take_profit_multiple", 0) or 0)
        basis = str(getattr(bounds, "take_profit_basis", "premium") or "premium")
        if multiple > 1 and priced.limit:
            tp = take_profit_price(priced.limit, multiple, basis, stop_price=priced.stop_price)
            net = round((tp - priced.limit) * CONTRACT_MULTIPLIER * priced.lots
                        - priced.commissions_usd, 2)
            target_txt = (f"target rests at {tp:.2f} <span class=k>({multiple:g}× the fill)</span> → "
                          f"<span class=pos>{money(net)}</span>")
    except (ValueError, TypeError):
        target_txt = ""
    line3 = (f"<div class='trow k'><span>{target_txt}</span>"
             "<details class=more><summary>more</summary></details></div>")
    rows = [
        ("most this costs", money(-t.max_loss_usd)),
        ("budget", f"${d.budget_remaining_usd:.2f} / {d.attempts_left} attempt(s) → "
                   f"${d.budget_remaining_usd / d.attempts_left:.2f} for this one"),
        ("less friction", f"${d.spread_usd:.2f} spread + ${d.fees_rt_usd:.2f} fees = "
                          f"${d.attempt_risk_usd:.2f} to risk"),
        ("in premium", f"{d.stop_premium_pts:.2f} at δ {d.delta_live:.2f} = "
                       f"{d.stop_distance_spx:.2f} SPX pts"),
        ("tape noise", f"about {d.noise_floor_spx:.2f} pts"),
        ("quote", f"{c.bid_pts:.2f} / {c.ask_pts:.2f}, δ {c.abs_delta:.2f}"),
        ("commissions", f"${priced.commissions_usd:.2f} in and out"),
    ]
    detail = "<table class=fd0>" + "".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>" for k, v in rows) + "</table>"
    for w in t.warnings:
        detail += f"<div class=warn>{esc(w)}</div>"
    return (f"<div class=card>{head}{line2}{line3}"
            f"<div class='full detail'>{detail}</div></div>")


def strikes_html(priced: Priced, order_path: str) -> str:
    sel = priced.selection
    if not priced.contracts:
        return "<div class=k>no strikes to show</div>"
    rows = []
    for c in priced.contracts:
        chosen = priced.contract is not None and c.symbol == priced.contract.symbol
        href = _link(order_path, sel.as_query(strike=f"{c.strike:g}", delta=None))
        rows.append(
            f"<tr class='{'chosen' if chosen else ''}'>"
            f"<td><a href='{href}'>{c.strike:g}</a></td>"
            f"<td><a href='{href}'>{c.bid_pts:.2f} / {c.ask_pts:.2f}</a></td>"
            f"<td><a href='{href}'>δ {abs(c.delta):.2f}</a></td></tr>")
    return (f"<div class=k>SPX {priced.spx:.2f} · tap a strike</div>"
            "<table class=strikes>" + "".join(rows) + "</table>")


def fd0_html(priced: Priced) -> str:
    if priced.error and priced.contract is None:
        return f"<div class=bad>{esc(priced.error)}</div>"
    c = priced.contract
    parts = [f"<div class=cost>{esc(c.symbol.strip())} × {priced.lots} — "
             f"limit {priced.limit:.2f} = {money(-(priced.cost_usd or 0)).lstrip('-')} "
             f"({c.bid_pts:.2f} / {c.ask_pts:.2f}, δ {c.abs_delta:.2f})</div>"]
    if priced.error:
        parts.append(f"<div class=bad>{esc(priced.error)}</div>")
        return "".join(parts)
    t = priced.ticket
    d = t.derivation
    side = "below" if t.right == "CALL" else "above"
    rows = [
        ("cut if SPX reaches", f"{t.stop_trigger_spx:.2f} — {d.stop_distance_spx:.2f} pts {side} {t.spx_at_compose:.2f}"),
        ("most this costs", money(-t.max_loss_usd)),
        ("budget", f"${d.budget_remaining_usd:.2f} / {d.attempts_left} attempt(s) → ${d.budget_remaining_usd / d.attempts_left:.2f} for this one"),
        ("less friction", f"${d.spread_usd:.2f} spread + ${d.fees_rt_usd:.2f} fees = ${d.attempt_risk_usd:.2f} to risk"),
        ("in premium", f"{d.stop_premium_pts:.2f} at δ {d.delta_live:.2f} = {d.stop_distance_spx:.2f} SPX pts"),
        ("tape noise", f"about {d.noise_floor_spx:.2f} pts"),
    ]
    if priced.stop_price is not None:
        rows.append(("resting stop the service places",
                     f"{priced.stop_price:.2f} → net {money(priced.net_at_stop_usd)} "
                     f"(commissions ${priced.commissions_usd:.2f} in and out)"))
    else:
        rows.append(("resting stop", esc(priced.stop_note or "none")))
    html = "<table class=fd0>" + "".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>" for k, v in rows) + "</table>"
    for w in t.warnings:
        html += f"<div class=warn>{esc(w)}</div>"
    return "".join(parts) + html


def quote_html(q: dict[str, Any] | None, spx: float | None, error: str | None) -> str:
    if error:
        return f"<div class=k>quote: {esc(error)}</div>"
    if not q:
        return "<div class=k>no contract chosen</div>"
    return (f"<div class=k>{esc(str(q['symbol']).strip())} bid {q['bid']:.2f} / ask {q['ask']:.2f}"
            + (f" · SPX {spx:.2f}" if spx else "") + "</div>")


def position_html(st: dict[str, Any], actions: Mapping[str, str] | None = None) -> str:
    """The open position with its bracket editor, the working entry with its
    CANCEL AND RE-PRICE, and the day's line. ``actions`` carries the page's
    ``order_adjust`` and ``order_cancel`` paths; without them the cards
    render with no controls (a read-only surface)."""
    from .page import _render_position
    pnl = st.get("pnl") or {}
    day = st["day"]
    adjust = actions.get("order_adjust") if actions else None
    cancel = actions.get("order_cancel") if actions else None
    html = "".join(_render_position(p, adjust) for p in st["positions"])
    for w in st["working"]:
        html += working_html(w, cancel)
    html += (f"<div class=k>today: realized {money(pnl.get('realized_usd'))} over "
             f"{pnl.get('closes', 0)} close(s) · unrealized {money(pnl.get('unrealized_net_usd'))} · "
             f"day {money(pnl.get('day_usd'))} · attempts {day['attempts_used']} used, "
             f"{day['attempts_left']} left · headroom ${day['loss_headroom_usd']:.2f}</div>")
    return html


def working_html(w: dict[str, Any], cancel_action: str | None) -> str:
    """One entry the broker holds and has not filled: what it is, and one
    button — CANCEL AND RE-PRICE — that pulls it and brings the form back
    priced fresh from the selection it was sent from (st-fn5y)."""
    sym = str(w.get("symbol", "")).strip()
    rows = [("working entry", f"{sym} × {w.get('qty')}"),
            ("limit", f"{float(w['limit']):.2f}" if w.get("limit") is not None else "—"),
            ("order", str(w.get("order_id", "")))]
    if w.get("stop_spx") is not None:
        rows.append(("SPX cut level", f"{float(w['stop_spx']):.2f}"))
    html = ("<h2>Working entry</h2><div class=card><table>" + "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in rows) + "</table>")
    if cancel_action:
        html += (f"<form method=post action='{cancel_action}'>"
                 f"<input type=hidden name=order_id value='{esc(w.get('order_id', ''))}'>"
                 "<button class='big exit'>CANCEL AND RE-PRICE</button></form>")
    return html + "</div>"


def preview_fields_html(sel: Selection) -> str:
    return "".join(f"<input type=hidden name='{k}' value='{esc(v)}'>"
                   for k, v in sel.as_query().items())


# ── the page ─────────────────────────────────────────────────────────────

def render_order(service: ExecService, actions: Mapping[str, str], sel: Selection,
                 priced: Priced | None, *, today, nonce: str | None = None,
                 preview: dict[str, Any] | None = None, preview_text: str | None = None,
                 msg: str | None = None, bad: str | None = None,
                 embed: bool = False) -> str:
    from .page import _STYLE, esc as _esc  # noqa: F401 — the shell's style
    st = service.status()
    order = actions["order"]
    parts: list[str] = []
    if msg:
        parts.append(f"<div class=msg>{esc(msg)}</div>")

    # the status panel — one card, the stage the order is in, its controls
    # (st-4ezg; design docs/design/order-status-panel). A refusal with
    # nothing live is the card's REFUSED stage; with money live it is the
    # red box above the card, and the card keeps its controls.
    ticket = None
    if priced is not None and priced.ticket is not None:
        ticket = {"stop_trigger_spx": priced.ticket.stop_trigger_spx,
                  "max_loss_usd": priced.ticket.max_loss_usd,
                  "stop_price": priced.stop_price}
    live_preview = preview if (nonce and preview is not None and not preview.get("refused")) else None
    panel = panel_html(service, st, actions, now=service.clock(), order_path=order,
                       sel_query=sel.as_query(), preview=live_preview,
                       nonce=nonce if live_preview else None, ticket=ticket, refused=bad)
    if bad and "data-stage=refused" not in panel:
        parts.append(f"<div class=bad>{esc(bad)}</div>")
    # the strip first — the same on every stage (st-shhi)
    parts.insert(0, state_html(st, actions, now=service.clock()))
    # The stage card only when there is a stage to show: with nothing held,
    # nothing working and no preview, the page opens on the side buttons.
    if live_preview is not None or st["positions"] or st["working"] or bad \
            or "data-stage=none" not in panel:
        parts.append(panel)

    # side — one tap
    tomorrow = next_weekday(today)
    def side_link(side: str, word: str, cls: str) -> str:
        on = " on" if sel.side == side else (" off" if sel.side else "")
        return (f"<a class='big {cls}{on}' href='{_link(order, sel.as_query(side=side, strike=None))}'>"
                f"{word}</a>")
    parts.append("<div class=side>" + side_link("call", "BULLISH", "bull")
                 + side_link("put", "BEARISH", "bear") + "</div>")

    exp = sel.expiry or today
    if priced is not None and sel.side:
        # the decision first (Steve, 2026-09-15: PREVIEW in the upper portion):
        # the ticket and PREVIEW, then the tuning — expiry, δ, RE-PRICE — and the strikes
        # the ticket — three lines, the derivation behind more
        parts.append(f"<div id=fd0>{ticket_html(priced, service.bounds)}</div>")
        # the one action on this stage
        if priced.contract is not None and priced.ticket is not None:
            if live_preview is not None and preview_text:
                parts.append(f"<div class=card><div class=k>{esc(preview_text)}</div></div>")
            parts.append(
                f"<form method=post action='{actions['order_preview']}'>"
                f"<span id=previewform>{preview_fields_html(sel)}</span>"
                f"<button class='big preview'>PREVIEW</button></form>")
        # expiry, δ target and RE-PRICE on one row — one GET form, no script needed
        delta_val = f"{sel.delta:g}" if sel.delta is not None else ""
        parts.append(
            f"<form id=sel method=get action='{order}'>"
            f"<input type=hidden name=side value='{sel.side}'>"
            f"<input type=hidden name=expiry value='{exp.isoformat()}'>"
            "<div class='row exp2'>"
            f"<a class='chip {'on' if exp == today else ''}' href='{_link(order, sel.as_query(expiry=today.isoformat(), strike=None))}'>today {today.strftime('%m-%d')}</a>"
            f"<a class='chip {'on' if exp == tomorrow else ''}' href='{_link(order, sel.as_query(expiry=tomorrow.isoformat(), strike=None))}'>next {tomorrow.strftime('%m-%d')}</a>"
            "<span class=grow></span>"
            f"<label class=dl><span class=k>δ</span><input name=delta inputmode=decimal value='{delta_val}' placeholder='spot'></label>"
            "<button class='chip quiet'>RE-PRICE</button></div>"
            "<details class=inputs2><summary>budget and attempts</summary><div class=inputs>"
            f"<label>FD0 budget $<input name=budget inputmode=decimal value='{sel.budget_usd:g}'></label>"
            f"<label>attempts<input name=attempts inputmode=numeric value='{sel.attempts}'></label>"
            f"<label>lots<input name=lots inputmode=numeric value='{sel.lots}' disabled></label>"
            "</div></details></form>")
        # strikes around spot
        parts.append(f"<div class=card><div id=strikes>{strikes_html(priced, order)}</div></div>")
    elif not sel.side:
        parts.append("<div class=k style='text-align:center'>pick a side to see the strikes</div>")

    # the day, one line
    pnl = st.get("pnl") or {}
    day = st["day"]
    parts.append(f"<div class=foot><span>today {money(pnl.get('day_usd'))} · "
                 f"{day['attempts_used']} of {day['attempts_used'] + day['attempts_left']} attempts</span>"
                 f"<span>headroom ${day['loss_headroom_usd']:.2f}</span></div>")

    symbol = (priced.contract.symbol if priced is not None and priced.contract is not None
              else None)
    script = (_SCRIPT % {"price": json.dumps(actions["order_price"]),
                         "symbol": json.dumps(symbol)}
              + PANEL_SCRIPT % {"state": json.dumps(actions["order_state"]), "poll": POLL_S,
                                "words": json.dumps(WORDS), "colors": json.dumps(COLORS)})
    return _order_page("trade", "".join(parts) + script, embed=embed)


def _order_page(title: str, body: str, *, embed: bool) -> str:
    from .page import _STYLE
    head = ("<!doctype html><html><head><meta charset=utf-8>"
            f"<title>{esc(title)}</title>"
            "<meta name=apple-mobile-web-app-capable content=yes>"
            "<meta name=apple-mobile-web-app-status-bar-style content=black>"
            f"{_STYLE}<style>{_ORDER_STYLE}{PANEL_STYLE}</style></head>")
    if embed:
        return head + f"<body class=embed>{body}</body></html>"
    return head + f"<body>{body}</body></html>"
