"""The order form's HTML — server-rendered, one small inline script. [st-k6gl]

Every element on ``/exec/order`` is here; the numbers come from
``execd.orderform`` and the money card from the same status body the
operations page reads. Works with no script at all (every control is a link
or a form); the script only keeps the quote, the FD0 block and the position
fresh without reloading a page that may have a number half-typed on it, and
works the padlock beside the price (st-2s4u): unlocked, the ticket's price
follows the live ask; locked, it is frozen at his number and SEND sends
that. Without a script the ticket is priced at the ask when the page loads,
as before, and there is no lock.

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
from .panel import COLORS, PANEL_SCRIPT, PANEL_STYLE, WORDS, contract_name, panel_html, stage_of as panel_stage_of
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
 button.send{background:#dc2626}button.send:disabled{opacity:.6}
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
 .dl{display:flex;align-items:center;gap:.4em}.dl.stopl input{width:6.2em}.dl input{width:5em;height:44px;box-sizing:border-box;font-size:1.15em;text-align:center;
       padding:0 .5em;border-radius:8px;border:1px solid #374151;background:#0b1020;color:#e5e7eb}
 .side a{outline:0}.side a.on{outline:3px solid #e5e7eb}.side a.bear.off{background:#7f1d1d;color:#fca5a5}.side a.bull.off{background:#064e3b;color:#6ee7b7}
 .trow{display:flex;align-items:baseline;justify-content:space-between;gap:.75em;margin:.25em 0}
 .tbig{font-size:1.5em;font-weight:700}.neg{color:#f87171;font-weight:700}.pos{color:#34d399;font-weight:700}
 button.lock{background:transparent;border:1px solid #374151;border-radius:8px;min-width:44px;height:44px;font-size:1.1em;
       cursor:pointer;vertical-align:middle;color:#9ca3af;padding:0 .4em;font-family:inherit}
 button.lock.on{background:#1f2937;border-color:#fbbf24;color:#fbbf24}
 .tbig #live{font-size:.6em;font-weight:400;vertical-align:middle}
 details.more summary{color:#60a5fa;cursor:pointer;list-style:none}details.more summary::-webkit-details-marker{display:none}
 .detail{display:none;margin-top:.5em}.card:has(details.more[open]) .detail{display:block}
 details.inputs2{margin-top:.5em}details.inputs2 summary{color:#9ca3af;cursor:pointer;font-size:.9em}
 .foot{display:flex;justify-content:space-between;gap:.75em;color:#9ca3af;font-size:.9em;margin-top:.4em}
 .money{display:flex;justify-content:space-between;align-items:baseline;gap:.75em;margin:0 0 .6em;font-size:1.05em}
 .money b{font-size:1.2em}
 details.journalbox{margin-top:.6em}details.journalbox summary{list-style:none;display:inline-flex}
 details.journalbox summary::-webkit-details-marker{display:none}
 #journal pre{white-space:pre-wrap;word-break:break-all;font-size:.8em;color:#cbd5e1;margin:0}
"""

_SCRIPT = """
<script>
(function(){
  var PRICE = %(price)s;
  var form = document.getElementById('sel');
  window.__sym = %(symbol)s;
  function q(extra){ var d = new FormData(form); var o = {}; d.forEach(function(v,k){ if(v!=='') o[k]=v; });
    for (var k in (extra||{})) o[k]=extra[k]; return new URLSearchParams(o).toString(); }
  function lockField(){ return form ? form.elements['limit'] : null; }
  function reprice(){ if(!form) return;
    fetch(PRICE + '?' + q(), {headers:{'Accept':'application/json'}}).then(function(r){return r.json();}).then(function(j){
      var f = document.getElementById('fd0'); if (f && j.fd0_html) f.innerHTML = j.fd0_html;
      var s = document.getElementById('strikes'); if (s && j.strikes_html) s.innerHTML = j.strikes_html;
      var p = document.getElementById('sendfields'); if (p && j.send_fields_html) p.innerHTML = j.send_fields_html;
      if (j.contract) window.__sym = j.contract.symbol;
      if (window.__followStop) window.__followStop(j);
    }).catch(function(){}); }
  // a new delta is a new contract: the lock goes with the old one
  function unlockThenReprice(){ var lf = lockField(); if (lf) lf.value = ''; reprice(); }
  if (form) { ['delta','budget','attempts','lots'].forEach(function(n){ var el = form.elements[n];
    var fn = (n === 'delta') ? unlockThenReprice : reprice;
    if (el) { el.addEventListener('change', fn); el.addEventListener('input', function(){ clearTimeout(window.__t); window.__t = setTimeout(fn, 600); }); } }); }
  // the stop box (st-m3bl): the visible box follows FD0's derived stop
  // until he types in it; from then on the hidden `stop` on this form
  // carries his text — dollars with a '.', an SPX level without — and the
  // ticket is repriced from it. Cleared, it goes back to following.
  var stopBox = document.getElementById('stopbox');
  function stopField(){ return form ? form.elements['stop'] : null; }
  function stopTouched(){ var sf = stopField(); return !!(sf && sf.value); }
  if (stopBox) { stopBox.addEventListener('input', function(){ var sf = stopField(); if (!sf) return;
      sf.value = stopBox.value.trim(); clearTimeout(window.__t); window.__t = setTimeout(reprice, 600); });
    stopBox.addEventListener('keydown', function(e){ if (e.key === 'Enter') { e.preventDefault(); clearTimeout(window.__t); reprice(); stopBox.blur(); } }); }
  window.__followStop = function(j){ if (!stopBox || stopTouched() || !j || j.stop_price == null) return;
    if (document.activeElement === stopBox) return;
    var v = Number(j.stop_price).toFixed(2); stopBox.value = v; stopBox.setAttribute('data-derived', v); };
  // the padlock (st-2s4u): the lock is the hidden limit on the form, the
  // server renders the ticket from it, so a tap only flips the field and
  // reprices. The chip is inside #fd0 and is re-rendered, hence delegation.
  document.addEventListener('click', function(e){ var b = e.target && e.target.closest ? e.target.closest('#lock') : null;
    if (!b) return; e.preventDefault(); var lf = lockField(); if (!lf) return;
    lf.value = lf.value ? '' : (b.getAttribute('data-limit') || ''); reprice(); });
  // the poll's quote: unlocked, the head follows the ask; locked, the ask
  // shows beside the locked price
  window.__lots = form && form.elements['lots'] ? (form.elements['lots'].value || '1') : '1';
  window.__onQuote = function(j){ if (!j || !j.quote || j.limit_now == null) return;
    var lf = lockField(); var px = document.getElementById('px'); var cost = document.getElementById('cost');
    var live = document.getElementById('live'); var lk = document.getElementById('lock');
    if (lf && lf.value) { if (live) live.textContent = 'ask ' + Number(j.quote.ask).toFixed(2) + ' now'; return; }
    if (px) px.textContent = Number(j.limit_now).toFixed(2);
    if (cost && j.cost_now) cost.textContent = j.cost_now;
    var pr = document.getElementById('priced'); if (pr && j.quote.as_of) { try {
      pr.textContent = 'priced ' + new Date(j.quote.as_of).toLocaleTimeString('en-GB', {hour12: false, timeZone: 'America/Chicago'}); } catch (e) {} }
    if (lk) lk.setAttribute('data-limit', Number(j.limit_now).toFixed(2)); };
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


#: A refusal younger than this is still the page's answer, even when the
#: redirect that carried it lost its query on the way (2026-09-15 09:54 CT:
#: the service journaled the refusal, the browser arrived at /exec/order
#: with no message, and Steve saw nothing).
RECENT_ANSWER_S = 10 * 60


def last_refusal(service: ExecService, now: datetime | None = None) -> str | None:
    """The most recent journaled refusal of a send (a bound, or the broker's
    own preview inside the place), if it is the
    latest thing the service did and it is recent — so the REFUSED stage
    renders from the record, not only from the redirect's query."""
    tail = service.journal.tail(3)
    if not tail:
        return None
    last = tail[-1]
    if last.get("event") != "refused" or last.get("kind") not in ("place", "preview"):
        return None
    at = last.get("ts")
    try:
        when = datetime.fromisoformat(at) if isinstance(at, str) else None
    except ValueError:
        when = None
    now = now or datetime.now(CT)
    if when is not None and (now - when).total_seconds() > RECENT_ANSWER_S:
        return None
    r = last.get("refused") or {}
    word = ""   # the strip's badge says PAPER; no prefix (Steve, 2026-09-15, st-2hei)
    return f"{word}Refused ({r.get('bound')}): {r.get('reason')}. Nothing sent."


#: The trading grant's wall is worth a line on the trading page from this
#: many days out — the seven-day token lifecycle is the live feed's failure
#: point, and the grants card that used to show it is gone (st-2hei).
WALL_ALERT_DAYS = 2.0


def wall_alert_html(st: dict[str, Any], now: datetime) -> str:
    """One red line when the trading grant's refresh wall is inside
    ``WALL_ALERT_DAYS`` or past — read from the armed credential, or from
    the wall the journal last saw while LOCKED. Nothing otherwise."""
    from .page import _fmt_wall
    cred = st.get("credential") or {}
    wall = cred.get("refresh_wall") if cred.get("armed") else cred.get("last_known_trading_wall")
    if not wall:
        return ""
    try:
        left = (datetime.fromisoformat(str(wall)) - now).total_seconds() / 86400
    except ValueError:
        return ""
    if left > WALL_ALERT_DAYS:
        return ""
    return f"<div class=bad>trading grant: {_fmt_wall(str(wall), now)}</div>"


def usd(v: Any) -> str:
    """An unsigned dollar figure — a balance, a cost — never the signed P&L
    form ``money`` gives."""
    return f"${float(v):,.2f}" if isinstance(v, (int, float)) else "—"


def balances_html(b: dict[str, Any] | None) -> str:
    """The account's money in Schwab's own words: available funds (what its
    preview checks an option buy against) and option buying power (the
    non-marginable figure). One line; an unreadable account says so."""
    if not b:
        return "<span class=k>account not read</span>"
    if b.get("error"):
        return f"<span class=k>account: {esc(b['error'])}</span>"
    return (f"<span>option buying power <b>{usd(b.get('option_buying_power'))}</b></span>"
            f"<span class=k>available {usd(b.get('available_funds'))}</span>")


def journal_html(service: ExecService, n: int = 20) -> str:
    """The day's journal, latest first, in one line per event — the same
    rendering as the account page's tail. On the trading page it sits behind
    one tap (Steve, 2026-09-15: "i should have a button that expands
    journal") and the poll keeps it fresh."""
    from .page import _short
    tail = service.journal.tail(n)
    if not tail:
        return "<div class=k>nothing journaled today</div>"
    lines = []
    for e in reversed(tail):
        fields = " ".join(f"{k}={_short(v)}" for k, v in e.items()
                          if k not in ("ts", "ts_ct", "event", "sha", "mode", "preview_raw", "body"))
        lines.append(f"{e.get('ts_ct', '')[11:19]} {e.get('event', '')} {fields}")
    return "<pre>" + esc("\n".join(lines)) + "</pre>"


def ticket_html(priced: Priced, bounds: Any, balances: dict[str, Any] | None = None) -> str:
    """The ticket in three lines — what will be sent, the cut, the two legs
    and what each nets — with the derivation behind *more*. Replaces the
    FD0 table as the thing Steve reads before SEND (st-shhi)."""
    if priced.error and priced.contract is None:
        return f"<div class=bad>{esc(priced.error)}</div>"
    c = priced.contract
    name = contract_name(c.symbol)
    # The price and its padlock (st-2s4u). Unlocked, the poll writes the live
    # limit into #px and #cost; locked, the number is his and the poll writes
    # the ask beside it into #live so the drift is visible. The chip's
    # data-limit is what a tap locks: the number on the screen at that moment.
    locked = priced.selection.locked
    lock = (f"<button type=button id=lock class='lock{' on' if locked else ''}' "
            f"data-limit='{priced.limit:.2f}' aria-label='{'unlock' if locked else 'lock'} the price' "
            f"title='{'locked — tap to follow the ask' if locked else 'following the ask — tap to lock'}'>"
            f"{'&#128274;' if locked else '&#128275;'}</button>")
    live = (f"<span id=live class=k>ask {c.ask_pts:.2f} now</span>" if locked else "<span id=live class=k></span>")
    # when the number on the screen was read (st-sk9r): the ask's time while
    # following, the moment of the lock while locked; the poll keeps it current
    when = (f"priced {priced.priced_at.astimezone(CT).strftime('%H:%M:%S')}"
            if priced.priced_at is not None else "")
    head = (f"<div class=trow><div class=tbig>{esc(name)} × {priced.lots} at "
            f"<span id=px>{priced.limit:.2f}</span> {lock} {live} "
            f"<span id=priced class=k>{when}</span></div>"
            f"<div class=tbig id=cost>{money(-(priced.cost_usd or 0)).lstrip('-')}</div></div>")
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
    # a stop of his own is marked as his, and by which form (st-m3bl)
    own = ""
    if priced.stop_set_by == "price":
        own = " <span class=k id=ownstop>· your price</span>"
    elif priced.stop_set_by == "spx":
        own = " <span class=k id=ownstop>· your level</span>"
    line2 = (f"<div class=trow><span>cut if SPX {sign} <b>{t.stop_trigger_spx:.2f}</b> "
             f"<span class=k>({d.stop_distance_spx:.2f} {side})</span>{own}</span><span>{stop_txt}</span></div>")
    for w in t.warnings:
        if w.startswith("YOUR STOP RISKS"):
            line2 += f"<div class=warn>{esc(w)}</div>"
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
    # The account's money against this ticket, before SEND asks Schwab —
    # the refusal of 2026-09-15 09:54 CT was exactly this arithmetic.
    money_line = ""
    avail = (balances or {}).get("available_funds")
    if isinstance(avail, (int, float)) and priced.cost_usd is not None:
        if priced.cost_usd > avail:
            money_line = (f"<div class=bad>this needs {usd(priced.cost_usd)} and the "
                          f"account has {usd(avail)} available — Schwab will refuse it</div>")
        else:
            money_line = (f"<div class=k>available funds {usd(avail)} — "
                          f"{usd(avail - priced.cost_usd)} after this</div>")
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
    return (f"<div class=card>{head}{line2}{line3}{money_line}"
            f"<div class='full detail'>{detail}</div></div>")


def strikes_html(priced: Priced, order_path: str) -> str:
    sel = priced.selection
    if not priced.contracts:
        return "<div class=k>no strikes to show</div>"
    rows = []
    for c in priced.contracts:
        chosen = priced.contract is not None and c.symbol == priced.contract.symbol
        # a new strike is a new price: the lock does not travel with it
        href = _link(order_path, sel.as_query(strike=f"{c.strike:g}", delta=None, limit=None, stop=None))
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


def send_fields_html(sel: Selection) -> str:
    """The selection as the SEND form's hidden fields — kept fresh by the
    script so SEND carries what the ticket shows (the lock included)."""
    return "".join(f"<input type=hidden name='{k}' value='{esc(v)}'>"
                   for k, v in sel.as_query().items())


# ── the page ─────────────────────────────────────────────────────────────

def render_order(service: ExecService, actions: Mapping[str, str], sel: Selection,
                 priced: Priced | None, *, today, send_nonce: str | None = None,
                 msg: str | None = None, bad: str | None = None,
                 embed: bool = False, fresh: bool = False) -> str:
    from .page import _STYLE, esc as _esc  # noqa: F401 — the shell's style
    st = service.status()
    order = actions["order"]
    parts: list[str] = []
    # A finished order — closed or refused — stays on the card only until the
    # next order begins: NEW ORDER (?new=1) or picking a side clears it
    # (Steve, 2026-09-15: "New Order button should clear prior order screen
    # before all else").
    starting_over = fresh or bool(sel.side)
    if not bad and not msg and not starting_over:
        bad = last_refusal(service, now=service.clock())
    if msg:
        parts.append(f"<div class=msg>{esc(msg)}</div>")

    # the status panel — one card, the stage the order is in, its controls
    # (st-4ezg; design docs/design/order-status-panel). A refusal with
    # nothing live is the card's REFUSED stage; with money live it is the
    # red box above the card, and the card keeps its controls.
    from .panel import journal_facts
    facts = journal_facts(service)
    live_stage = panel_stage_of(st, facts, refused=bad)
    dismissed = starting_over and live_stage in ("closed", "refused")
    panel = panel_html(service, st, actions, now=service.clock(), order_path=order,
                       sel_query=sel.as_query(), refused=bad, dismissed=dismissed)
    if dismissed:
        stamp_ = str((facts.get("last_close") or {}).get("ts") or "")
        panel = panel.replace("<div id=panel ", f"<div id=panel data-dismissed='{esc(stamp_)}' ", 1)
    if bad and "data-stage=refused" not in panel:
        parts.append(f"<div class=bad>{esc(bad)}</div>")
    # the strip first — the same on every stage (st-shhi); under it, the
    # passphrase box when the service is LOCKED (Steve, 2026-09-15: "if panel
    # is locked the Passphrase should be displayed") or the account's money
    # when it can be read — the number he looks for first, at the top, not
    # in the foot (st-2hei)
    top = [state_html(st, actions, now=service.clock()),
           wall_alert_html(st, service.clock())]
    if st["arming"]["state"] == "LOCKED":
        from .page import unlock_form
        top.append(unlock_form(actions["unlock"], back="order"))
    else:
        top.append(f"<div class=money id=balances>{balances_html(st.get('balances'))}</div>")
    parts[0:0] = top
    # The stage card shows only when there is a stage to show: with nothing
    # held, nothing working and no answer to show, the page opens on the
    # side buttons. The card is still on the page, hidden, so a SEND answered
    # in place has somewhere to paint (st-igw0).
    show = (st["positions"] or st["working"] or bad or msg or "data-stage=none" not in panel)
    parts.append(panel if show else panel.replace("<div id=panel ", "<div id=panel hidden ", 1))
    parts.append("<div id=answer></div>")

    # side — one tap
    tomorrow = next_weekday(today)
    def side_link(side: str, word: str, cls: str) -> str:
        on = " on" if sel.side == side else (" off" if sel.side else "")
        return (f"<a class='big {cls}{on}' href='{_link(order, sel.as_query(side=side, strike=None, limit=None, stop=None))}'>"
                f"{word}</a>")
    parts.append("<div class=side>" + side_link("call", "BULLISH", "bull")
                 + side_link("put", "BEARISH", "bear") + "</div>")

    exp = sel.expiry or today
    if priced is not None and sel.side:
        # the decision first (Steve, 2026-09-15: the action in the upper
        # portion): the ticket and SEND, then the tuning — expiry, δ, RE-PRICE
        # — and the strikes. The ticket — three lines, the derivation behind more
        parts.append(f"<div id=fd0>{ticket_html(priced, service.bounds, st.get('balances'))}</div>")
        # the one action on this stage: SEND, one tap from the decision
        # (st-igw0 — the PREVIEW step is gone; the service runs the broker's
        # own preview inside every place). The script sends it by fetch and
        # paints the answer; the plain form redirects.
        if priced.contract is not None and priced.ticket is not None and send_nonce:
            parts.append(
                f"<form method=post action='{actions['order_send']}' class=sendform>"
                f"<span id=sendfields>{send_fields_html(sel)}</span>"
                f"<input type=hidden name=nonce value='{esc(send_nonce)}'>"
                "<input type=hidden name=ajax value=''>"
                "<button class='big send'>SEND</button></form>")
        # expiry, δ target and RE-PRICE on one row — one GET form, no script needed.
        # The form carries the chosen strike, so RE-PRICE reprices THAT strike
        # (Steve, 2026-09-15: "simply reprice existing strike" — before st-2s4u
        # the strike was not on the form and RE-PRICE re-chose by delta), and
        # the lock as a hidden field the script toggles; the RE-PRICE button's
        # own field, reprice=1, means at the market and drops the lock.
        delta_val = f"{sel.delta:g}" if sel.delta is not None else ""
        strike_field = (f"<input type=hidden name=strike value='{sel.strike:g}'>"
                        if sel.strike is not None else "")
        limit_val = f"{sel.limit:.2f}" if sel.limit is not None else ""
        # the stop box (st-m3bl): pre-filled with FD0's derived dollar stop
        # and following it until touched; touched, the hidden `stop` carries
        # the text as typed and the rule is applied when the ticket is priced
        # — a '.' is dollars, none is an SPX level. The visible box has no
        # name of its own, so an untouched box never overrides anything.
        derived = f"{priced.stop_price:.2f}" if priced.stop_price is not None else ""
        stop_val = sel.stop if sel.stop else derived
        parts.append(
            f"<form id=sel method=get action='{order}'>"
            f"<input type=hidden name=side value='{sel.side}'>"
            f"<input type=hidden name=expiry value='{exp.isoformat()}'>"
            f"{strike_field}"
            f"<input type=hidden name=limit value='{limit_val}'>"
            f"<input type=hidden name=stop value='{esc(sel.stop or '')}'>"
            "<div class='row exp2'>"
            f"<a class='chip {'on' if exp == today else ''}' href='{_link(order, sel.as_query(expiry=today.isoformat(), strike=None, limit=None, stop=None))}'>today {today.strftime('%m-%d')}</a>"
            f"<a class='chip {'on' if exp == tomorrow else ''}' href='{_link(order, sel.as_query(expiry=tomorrow.isoformat(), strike=None, limit=None, stop=None))}'>next {tomorrow.strftime('%m-%d')}</a>"
            "<span class=grow></span>"
            f"<label class=dl><span class=k>δ</span><input name=delta inputmode=decimal value='{delta_val}' placeholder='spot'></label>"
            f"<label class='dl stopl' title=\"a '.' makes it a price (8.30); none makes it an SPX level (7610)\">"
            f"<span class=k>stop</span><input id=stopbox inputmode=decimal enterkeyhint=done autocomplete=off "
            f"value='{esc(stop_val)}' data-derived='{derived}'></label>"
            "<button class='chip quiet' name=reprice value=1>RE-PRICE</button></div>"
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
    # the journal, one tap away, kept fresh by the poll
    parts.append("<details id=journalbox class=journalbox><summary class='chip quiet'>journal</summary>"
                 f"<div class=card id=journal>{journal_html(service)}</div></details>")

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
