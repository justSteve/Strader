"""The order form's HTML — server-rendered, one small inline script. [st-k6gl]

Every element on ``/exec/order`` is here; the numbers come from
``execd.orderform`` and the money card from the same status body the
operations page reads. Works with no script at all (every control is a link
or a form); the script only keeps the quote, the ticket and the position
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

from .orderform import POLL_S, Priced, Selection
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
 .warn{color:#fbbf24}.cost{font-size:1.15em;font-weight:700}
 button.send{background:#dc2626}button.send:disabled{opacity:.6}
 .embed body{padding:.5em}
 .strip{display:flex;align-items:center;justify-content:space-between;gap:.75em;margin:.2em 0 .6em}
 .strip .l,.strip .r{display:flex;align-items:center;gap:.6em;min-width:0}
 .strip .badge{font-weight:700;font-size:.8em;padding:4px 8px;border-radius:6px;letter-spacing:.04em}
 .strip .badge.paper{background:#fbbf24;color:#111}.strip .badge.live{background:#dc2626;color:#fff}
 .strip .word{font-size:1.15em;font-weight:700}
 .strip form.inline{margin:0;display:inline}
 .chip{display:inline-flex;align-items:center;height:44px;padding:0 14px;border-radius:8px;font-weight:700;
       border:0;font-size:1em;font-family:inherit;text-decoration:none;cursor:pointer}
 .chip.stopbtn{background:#dc2626;color:#fff}.chip.quiet{background:#1f2937;color:#9ca3af}
 .chip.stop-on{background:#7f1d1d;color:#fca5a5}
 .row{display:flex;align-items:center;gap:.6em;flex-wrap:wrap}
 .row .grow{flex-grow:1}
 .exp2 a.chip{color:#9ca3af;background:transparent;border:1px solid #374151}.exp2 a.chip.on{background:#1f2937;color:#fff;border-color:#1f2937}
 .dl{display:flex;align-items:center;gap:.4em}.dl.stopl input{width:6.2em}.dl input{width:5em;height:44px;box-sizing:border-box;font-size:1.15em;text-align:center;
       padding:0 .5em;border-radius:8px;border:2px solid #9ca3af;background:#111827;color:#e5e7eb}
 .side a{outline:0}.side a.on{outline:3px solid #e5e7eb}.side a.bear.off{background:#7f1d1d;color:#fca5a5}.side a.bull.off{background:#064e3b;color:#6ee7b7}
 .trow{display:flex;align-items:baseline;justify-content:space-between;gap:.75em;margin:.25em 0}
 .tbig{font-size:1.5em;font-weight:700}.neg{color:#f87171;font-weight:700}.pos{color:#34d399;font-weight:700}
 button.lock{background:transparent;border:1px solid #374151;border-radius:8px;min-width:44px;height:44px;font-size:1.1em;
       cursor:pointer;vertical-align:middle;color:#9ca3af;padding:0 .4em;font-family:inherit}
 button.lock.on{background:#1f2937;border-color:#fbbf24;color:#fbbf24}
 .tbig #live{font-size:.6em;font-weight:400;vertical-align:middle}
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
  // Every reprice is numbered and only the newest answer paints (st-hzr6):
  // on a slow link two answers a second apart arrived out of order and the
  // ticket showed one state while the form held the other.
  var seq = 0; window.__lastReprice = 0; var outstanding = 0;
  // Paint the ticket, the strikes and SEND's hidden fields as ONE piece.
  // Shared by the explicit reprice below and by the poll (st-644f), because
  // a head rewritten over a stale body is the st-hzr6 bug: the price said
  // 0.60 while the stop, the net and the cost under it still stood on 0.70.
  window.__paintTicket = function(j){ if (!j) return;
    var f = document.getElementById('fd0'); if (f && j.fd0_html) f.innerHTML = j.fd0_html;
    var s = document.getElementById('strikes'); if (s && j.strikes_html) s.innerHTML = j.strikes_html;
    var p = document.getElementById('sendfields'); if (p && j.send_fields_html) p.innerHTML = j.send_fields_html;
    if (j.contract) window.__sym = j.contract.symbol;
    if (window.__followStop) window.__followStop(j); };
  function reprice(){ if(!form) return; var mine = ++seq; window.__lastReprice = Date.now();
    outstanding++;
    fetch(PRICE + '?' + q(), {headers:{'Accept':'application/json'}}).then(function(r){return r.json();}).then(function(j){
      outstanding--;
      if (mine !== seq) return;
      window.__paintTicket(j);
    }).catch(function(){ outstanding--; }); }
  // What the poll sends so its answer is priced from this selection, and
  // when it must keep its hands off the ticket: a box with something typed
  // in it, or a reprice of his own still on its way back.
  window.__pollQuery = function(){ return form ? q() : ''; };
  window.__formBusy = function(){ return outstanding > 0 || editing(); };
  // A poll answer older than the newest explicit reprice must not paint.
  window.__pollSeq = function(){ return seq; };
  // a new delta is a new contract: the lock goes with the old one
  function unlockThenReprice(){ var lf = lockField(); if (lf) lf.value = ''; reprice(); }
  if (form) { ['delta'].forEach(function(n){ var el = form.elements[n];
    var fn = (n === 'delta') ? unlockThenReprice : reprice;
    if (el) { el.addEventListener('change', fn); el.addEventListener('input', function(){ clearTimeout(window.__t); window.__t = setTimeout(fn, 600); }); } }); }
  // the stop box (st-m3bl): the visible box follows the flat-loss stop
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
  // The tap answers at once — the icon flips before the server is asked —
  // and a second tap inside half a second is the same tap (st-hzr6: on a
  // slow link the chain read took a second, nothing changed, he tapped
  // again, and the pair toggled the lock off again).
  document.addEventListener('click', function(e){ var b = e.target && e.target.closest ? e.target.closest('#lock') : null;
    if (!b) return; e.preventDefault(); var lf = lockField(); if (!lf) return;
    var now = Date.now(); if (now - (window.__lockTap || 0) < 500) return; window.__lockTap = now;
    lf.value = lf.value ? '' : (b.getAttribute('data-limit') || '');
    b.classList.toggle('on', !!lf.value); b.innerHTML = lf.value ? '&#128274;' : '&#128275;';
    reprice(); });
  // The loaded strike is repriced by the poll itself now (st-644f; Steve,
  // 2026-09-18: "include real-time price updates on the strike that is
  // loaded (auto-reprice)"). The poll carries this form's selection, the
  // service prices it from the same chain read the quote comes from, and
  // the answer paints the whole ticket. That is one market read every poll
  // where the old path took two — a quote and an index quote — and then a
  // third when the ask moved far enough to trigger a reprice of its own.
  // Locked, the server renders the live ask beside the locked price, so the
  // padlock needs nothing here either.
  function editing(){ var a = document.activeElement; return !!(a && a.tagName === 'INPUT' && form && form.contains(a)); }
  window.__lots = form && form.elements['lots'] ? (form.elements['lots'].value || '1') : '1';
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

def broker_badge(st: Mapping[str, Any]) -> str:
    """The broker this page sends to, as a large badge beside PAPER/LIVE.
    Steve runs one page per broker side by side (co-8mb1z, 2026-09-24: "I
    need sep forms for Alpaca and Schwab"), so the page must say which one
    it is before anything else. Nothing for a service that does not say."""
    broker = str(st.get("broker") or "").lower()
    if not broker:
        return ""
    return f"<span class='badge broker {esc(broker)}'>{esc(broker.upper())}</span>"


def state_html(st: dict[str, Any], actions: Mapping[str, str] | None = None,
               now: datetime | None = None) -> str:
    """The strip: the mode badge, the arming word, and STOP — the same on
    every stage (design docs/design/order-page, st-shhi). STOP posts back to
    this page; clearing it needs the passphrase and lives on the account
    page, one tap away.

    No clock. The ticking time used to sit beside the arming word, where it
    read as the moment the service was armed; Steve, 2026-09-18: "remove the
    timestamp the order was armed" (st-644f). The one time still on this page
    is the ticket's own ``priced HH:MM:SS``, which says when the number he is
    about to send was read — that one he asked to keep (st-bafu)."""
    a = st["arming"]
    mode = str(st.get("mode", "live"))
    badge = ("<span class='badge paper'>PAPER</span>" if mode == "paper"
             else "<span class='badge live'>LIVE</span>")
    state = a["state"]
    word = f"<span class='word {state}'>{state.replace('_', ' ')}</span>"
    right = ""
    if actions:
        if a["killed"]:
            right = (f"<a class='chip stop-on' href='{actions['account']}'>STOP ON · clear</a>")
        else:
            right = (f"<form method=post action='{actions['stop']}' class=inline>"
                     "<input type=hidden name=back value='order'>"
                     "<button class='chip stopbtn'>STOP</button></form>")
        right += f"<a class='chip quiet' href='{actions['account']}'>account</a>"
    return (f"<div class=strip><div class=l>{broker_badge(st)}{badge}{word}</div>"
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


def usd(v: Any) -> str:
    """An unsigned dollar figure — a balance, a cost — never the signed P&L
    form ``money`` gives."""
    return f"${float(v):,.2f}" if isinstance(v, (int, float)) else "—"


def balances_html(b: dict[str, Any] | None) -> str:
    """The account's money as one figure: option buying power, in Schwab's
    own words (Steve, 2026-09-17: "option buying power and available is
    redundant", st-bafu). An unreadable account says so."""
    if not b:
        return "<span class=k>account not read</span>"
    if b.get("error"):
        return f"<span class=k>account: {esc(b['error'])}</span>"
    return f"<span>option buying power <b>{usd(b.get('option_buying_power'))}</b></span>"


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
    """The ticket, stripped to the decision (st-bafu; Steve, 2026-09-17):
    what will be sent and its cost, the stop as the dollars it loses — or
    his level, when he typed one — and the take-profit. No derivation, no
    budget, no *more*."""
    if priced.error and priced.contract is None:
        return f"<div class=bad>{esc(priced.error)}</div>"
    c = priced.contract
    name = contract_name(c.symbol)
    # The price and its padlock (st-2s4u). Unlocked, a moved ask reprices the
    # whole ticket; locked, the number is his and the poll writes the ask
    # beside it into #live so the drift is visible. The chip's data-limit is
    # what a tap locks: the number on the screen at that moment.
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
    # One stop line (Steve, 2026-09-17: "keep amount of loss unless i
    # override with a strike"): the dollars the resting stop loses, or the
    # level he typed. A long call is cut when SPX falls to the level, a long
    # put when it rises to it.
    if priced.stop_set_by == "spx":
        verb = "falls to" if c.right == "CALL" else "rises to"
        stop_line = f"<span id=stopline>stop if SPX {verb} <b>{priced.stop_spx:g}</b></span>"
    else:
        stop_line = (f"<span id=stopline>stop loss "
                     f"<b class=neg>{usd(priced.stop_loss_usd)}</b></span>")
    line2 = f"<div class=trow>{stop_line}</div>"
    for w in priced.warnings:
        line2 += f"<div class=warn>{esc(w)}</div>"
    target_txt = ""
    try:
        multiple = float(getattr(bounds, "take_profit_multiple", 0) or 0)
        basis = str(getattr(bounds, "take_profit_basis", "premium") or "premium")
        if multiple > 1 and priced.limit:
            tp = take_profit_price(priced.limit, multiple, basis, stop_price=priced.stop_price)
            net = round((tp - priced.limit) * CONTRACT_MULTIPLIER * priced.lots
                        - priced.commissions_usd, 2)
            target_txt = (f"take-profit rests at {tp:.2f} <span class=k>({multiple:g}× the fill)</span> → "
                          f"<span class=pos>{money(net)}</span> <span class=k>if it fills there</span>")
    except (ValueError, TypeError):
        target_txt = ""
    line3 = f"<div class='trow k'><span>{target_txt}</span></div>" if target_txt else ""
    # Said only when the account cannot pay for it — the refusal of
    # 2026-09-15 09:54 CT was exactly this arithmetic. When it can, the
    # ticket says nothing about the account: the one money figure is under
    # the strip (st-bafu).
    short = ""
    avail = (balances or {}).get("available_funds")
    if isinstance(avail, (int, float)) and priced.cost_usd is not None and priced.cost_usd > avail:
        short = (f"<div class=bad>this needs {usd(priced.cost_usd)} and the "
                 f"account has {usd(avail)} available — Schwab will refuse it</div>")
    return f"<div class=card>{head}{line2}{line3}{short}</div>"


def spendable(balances: dict[str, Any] | None) -> float | None:
    """What the account can put into a new long option right now, in Schwab's
    own words: ``available_funds``, or option buying power when the account
    body carries no available figure. ``None`` means the account could not be
    read — and an unread account hides nothing, because a page that quietly
    dropped every strike because it could not reach Schwab would be worse
    than one that shows them all."""
    if not balances or balances.get("error"):
        return None
    for key in ("available_funds", "option_buying_power"):
        v = balances.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def affordable(c: Any, lots: int, funds: float | None) -> bool:
    """Can the account buy ``lots`` of this contract at its ask? The ask, not
    the mid: the ask is what the form sends as the limit."""
    if funds is None:
        return True
    return c.ask_pts * CONTRACT_MULTIPLIER * max(1, lots) <= funds


def strikes_html(priced: Priced, order_path: str,
                 balances: dict[str, Any] | None = None) -> str:
    """The strikes around spot — only the ones the account can pay for.

    Steve, 2026-09-18: "in the list of strike you offer, exclude any that
    exceed limit of the available funds" (st-644f). A strike whose ask times
    a hundred times the lots is more than the account has is not an offer,
    it is a refusal waiting at Schwab; the ticket already says so for the one
    that is loaded, and now the list does not lead him there at all. The
    loaded strike always stays in the list even when it is too dear, so
    tapping a row never makes the row he is on disappear. An account that
    could not be read filters nothing."""
    sel = priced.selection
    if not priced.contracts:
        return "<div class=k>no strikes to show</div>"
    funds = spendable(balances)
    chosen_sym = priced.contract.symbol if priced.contract is not None else None
    shown = [c for c in priced.contracts
             if affordable(c, priced.lots, funds) or c.symbol == chosen_sym]
    head = f"<div class=k>SPX {priced.spx:.2f} · tap a strike</div>"
    if not shown:
        return (head + f"<div class=k>no strike here costs less than the "
                f"{usd(funds)} the account has</div>")
    rows = []
    for c in shown:
        chosen = chosen_sym is not None and c.symbol == chosen_sym
        dear = not affordable(c, priced.lots, funds)
        # a new strike is a new price: the lock does not travel with it
        href = _link(order_path, sel.as_query(strike=f"{c.strike:g}", delta=None, limit=None, stop=None))
        rows.append(
            f"<tr class='{'chosen' if chosen else ''}'>"
            f"<td><a href='{href}'>{c.strike:g}</a></td>"
            f"<td><a href='{href}'>{c.bid_pts:.2f} / {c.ask_pts:.2f}</a></td>"
            f"<td><a href='{href}'>δ {abs(c.delta):.2f}"
            + ("<span class=warn> · over the account</span>" if dear else "")
            + "</a></td></tr>")
    left_out = len(priced.contracts) - len(shown)
    tail = (f"<div class=k>{left_out} strike{'' if left_out == 1 else 's'} "
            f"above the {usd(funds)} the account has, not shown</div>"
            if left_out > 0 else "")
    return head + "<table class=strikes>" + "".join(rows) + "</table>" + tail


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
    adjust = actions.get("order_adjust") if actions else None
    cancel = actions.get("order_cancel") if actions else None
    html = "".join(_render_position(p, adjust) for p in st["positions"])
    for w in st["working"]:
        html += working_html(w, cancel)
    # Money only. No attempts, no headroom: Steve, 2026-09-18, "you are
    # _still showing headroom and attempts. remove all aspects of that"
    # (st-644f) — the second time he has asked (st-bafu took the form's own
    # copy of the calculation out; these were the service's). The bounds
    # still refuse an entry past the ceiling or the attempt count; narrating
    # them is not this page's job.
    html += (f"<div class=k>today: realized {money(pnl.get('realized_usd'))} over "
             f"{pnl.get('closes', 0)} close(s) · unrealized {money(pnl.get('unrealized_net_usd'))} · "
             f"day {money(pnl.get('day_usd'))}</div>")
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
    # in the foot (st-2hei). The trading grant's wall is not on this page
    # (Steve, 2026-09-17: "there is still no reason to display trading grant
    # on the order form", st-bafu); it is on the account page, beside the
    # re-authorisation it asks for.
    top = [state_html(st, actions, now=service.clock())]
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
        # — and the strikes. The ticket — what is sent, the stop, the take-profit
        parts.append(f"<div id=fd0>{ticket_html(priced, service.bounds, st.get('balances'))}</div>")
        # the one action on this stage: SEND, one tap from the decision
        # (st-igw0 — the PREVIEW step is gone; the service runs the broker's
        # own preview inside every place). The script sends it by fetch and
        # paints the answer; the plain form redirects.
        if priced.ready and send_nonce:
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
        # more than one lot rides the form so a reprice keeps it
        lots_field = f"<input type=hidden name=lots value='{sel.lots}'>" if sel.lots != 1 else ""
        limit_val = f"{sel.limit:.2f}" if sel.limit is not None else ""
        # the stop box (st-m3bl): pre-filled with the flat-loss stop's price
        # (st-bafu) and following it until touched; touched, the hidden `stop` carries
        # the text as typed and the rule is applied when the ticket is priced
        # — a '.' is dollars, none is an SPX level. The visible box has no
        # name of its own, so an untouched box never overrides anything.
        derived = f"{priced.stop_price:.2f}" if priced.stop_price is not None else ""
        stop_val = sel.stop if sel.stop else derived
        parts.append(
            f"<form id=sel method=get action='{order}'>"
            f"<input type=hidden name=side value='{sel.side}'>"
            f"<input type=hidden name=expiry value='{exp.isoformat()}'>"
            f"{strike_field}{lots_field}"
            f"<input type=hidden name=limit value='{limit_val}'>"
            f"<input type=hidden name=stop value='{esc(sel.stop or '')}'>"
            # The expiry is the day, said once, not a button. There is no
            # 'next' chip: Steve, 2026-09-18, "remove the 'next' button"
            # (st-644f) — he trades the session he is in. A URL that carries
            # another expiry is still priced and still shown here, so
            # nothing is lost but the tap that offered it.
            "<div class='row exp2'>"
            f"<span class='chip on'>{exp.strftime('%m-%d')}</span>"
            "<span class=grow></span>"
            f"<label class=dl><span class=k>δ</span><input name=delta inputmode=decimal value='{delta_val}' placeholder='spot'></label>"
            f"<label class='dl stopl' title=\"a '.' makes it a price (8.30); none makes it an SPX level (7610)\">"
            f"<span class=k>stop: strike or price</span><input id=stopbox inputmode=decimal enterkeyhint=done autocomplete=off "
            f"value='{esc(stop_val)}' data-derived='{derived}'></label>"
            "<button class='chip quiet' name=reprice value=1>RE-PRICE</button></div>"
            "</form>")
        # strikes around spot — only the ones the account can pay for (st-644f)
        parts.append("<div class=card><div id=strikes>"
                     f"{strikes_html(priced, order, st.get('balances'))}</div></div>")
    elif not sel.side:
        parts.append("<div class=k style='text-align:center'>pick a side to see the strikes</div>")

    # the day, one line: the money and nothing else (st-644f — no attempts,
    # no headroom; see position_html)
    pnl = st.get("pnl") or {}
    parts.append(f"<div class=foot><span>today {money(pnl.get('day_usd'))}</span></div>")
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
