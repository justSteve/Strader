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

from .orderform import DEFAULT_DELTA, DEFAULT_STOP_LOSS_USD, POLL_S, Priced, Selection
from .panel import (COLORS, PANEL_SCRIPT, PANEL_STYLE, WORDS, closed_html, contract_name, panel_html,
                    short_pts, stage_of as panel_stage_of)
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
 .row.stops{justify-content:center;gap:1.2em;margin:.5em 0}
 .row .grow{flex-grow:1}
 .exp2 a.chip{color:#9ca3af;background:transparent;border:1px solid #374151}.exp2 a.chip.on{background:#1f2937;color:#fff;border-color:#1f2937}
 button.step{width:44px;height:44px;border-radius:8px;border:1px solid #374151;background:#1f2937;color:#f9fafb;
   font-size:1.3em;font-weight:700;padding:0;touch-action:manipulation;cursor:pointer}
 .dl.exitl input{width:5.6em}
 .dl{display:flex;align-items:center;gap:.4em}.dl.stopl input{width:6.2em}.dl input{width:5em;height:44px;box-sizing:border-box;font-size:1.15em;text-align:center;
       padding:0 .5em;border-radius:8px;border:2px solid #9ca3af;background:#111827;color:#e5e7eb}
 .side a{outline:0}.side a.on{outline:3px solid #e5e7eb}.side a.bear.off{background:#7f1d1d;color:#fca5a5}.side a.bull.off{background:#064e3b;color:#6ee7b7}
 .trow{display:flex;align-items:baseline;justify-content:space-between;gap:.75em;margin:.25em 0}
 .tbig{font-size:1.5em;font-weight:700}.neg{color:#f87171;font-weight:700}.pos{color:#34d399;font-weight:700}
 button.lock{background:transparent;border:1px solid #374151;border-radius:8px;min-width:44px;height:44px;font-size:1.1em;
       cursor:pointer;vertical-align:middle;color:#9ca3af;padding:0 .4em;font-family:inherit}
 button.lock.on{background:#1f2937;border-color:#fbbf24;color:#fbbf24}
 .tbig #live{font-size:.6em;font-weight:400;vertical-align:middle}
 .trow.tcenter{justify-content:center}
 button.send:disabled{opacity:.35;cursor:not-allowed}
 .stepper{display:inline-flex;align-items:center;gap:4px}
 input.numbox{width:3.6em;height:44px;box-sizing:border-box;font-size:1em;font-weight:700;text-align:center;
   border:2px solid #9ca3af;border-radius:8px;background:#111827;color:#f9fafb}
 #lotsbox{width:2.2em}
 /* the ticket head on one line at iPad width (Steve, 2026-09-30: "tighten") */
 .tcenter .tbig{display:flex;align-items:center;justify-content:center;gap:4px;flex-wrap:nowrap;font-size:1.25em}
 .tcenter .stepper{gap:2px}
 .tcenter button.step{width:34px;height:40px;font-size:1.1em}
 .tcenter input.numbox{height:40px;width:3.1em;padding:0 .1em}
 .tcenter #lotsbox{width:1.7em}
 .tcenter input.pxbox{height:40px;width:3.5em;box-sizing:border-box}
 .tcenter button.lock{min-width:38px;height:40px;padding:0 4px}
 .tcenter #live:empty{display:none}
 @media (max-width:430px){.tcenter .tbig{font-size:1.05em;gap:2px}.tcenter button.step{width:28px}
   .tcenter input.numbox{width:2.9em}.tcenter #lotsbox{width:1.6em}.tcenter input.pxbox{width:3.3em}
   .tcenter button.lock{min-width:32px}}
 input.pxbox{text-align:right;width:4.2em;font-size:1em;font-weight:700;padding:.1em .25em;border:2px solid #fbbf24;border-radius:6px;background:#111827;color:#f9fafb}
 .foot{display:flex;justify-content:space-between;gap:.75em;color:#9ca3af;font-size:.9em;margin-top:.4em}
 /* div: the card's money notes are spans of class money too */
 div.money{display:flex;justify-content:space-between;align-items:baseline;gap:.75em;margin:0 0 .6em;font-size:1.05em}
 div.money b{font-size:1.2em}
 div.money .clock{font-size:1.15em;font-weight:600;color:#9ca3af;font-variant-numeric:tabular-nums;letter-spacing:.02em}
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
    // the price box lives in the ticket: a repaint while he is in it keeps
    // what he typed and where the caret was (co-8mb1z)
    // (and so do the strike and contracts boxes, st-5n3s)
    var f = document.getElementById('fd0'), ae = document.activeElement;
    var had = !!(f && ae && ae.id && f.contains(ae)), hid = had ? ae.id : null;
    var pv = had ? ae.value : null, pc = null; try { pc = had ? ae.selectionStart : null; } catch (e) {}
    if (f && j.fd0_html) f.innerHTML = j.fd0_html;
    if (had) { var nx = document.getElementById(hid); if (nx) { nx.value = pv; nx.focus();
      try { nx.setSelectionRange(pc, pc); } catch (e) {} } }
    if (j.sendable !== undefined) { var sb = document.querySelector('form.sendform button.send');
      if (sb) sb.disabled = !j.sendable; }
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
    if (el) { el.addEventListener('change', unlockThenReprice); } }); }
  // The stop box is the stop's dollar distance under the entry (".2"),
  // riding on the hidden `stopoff`. Dollars only at entry (Steve,
  // 2026-10-01, st-a54y): the close-at-SPX box is gone from the ticket.
  var stopBox = document.getElementById('stopbox');
  function stopField(){ return form ? form.elements['stop'] : null; }
  function offField(){ return form ? form.elements['stopoff'] : null; }
  function num(v){ v = (v || '').trim(); if (!v || /^na$/i.test(v)) return NaN; return parseFloat(v); }
  function soon(ms){ clearTimeout(window.__t); window.__t = setTimeout(reprice, ms); }
  function stopLive(off){ var of = offField(), sf = stopField();
    if (of) of.value = isNaN(off) ? '' : off.toFixed(2); if (sf) sf.value = ''; }
  function shortPts(n){ var t = n.toFixed(2).replace(/0+$/, '').replace(/\.$/, ''); return t.indexOf('0.') === 0 ? t.slice(1) : t; }
  if (stopBox) {
    stopBox.addEventListener('input', function(){ var v = num(stopBox.value);
      if (!isNaN(v) && v > 0) stopLive(v); soon(600); });
    stopBox.addEventListener('keydown', function(e){ if (e.key === 'Enter') { e.preventDefault(); soon(0); stopBox.blur(); } }); }
  // left empty, the stop box says the stop's distance again
  if (stopBox) stopBox.addEventListener('blur', function(){ if (!stopBox.value.trim()) {
    var of = offField(); stopBox.value = (of && of.value) ? shortPts(parseFloat(of.value))
      : (stopBox.getAttribute('data-default') || '.2'); } });
  // the entry price box (co-8mb1z): typing is locking at that price — the
  // hidden limit carries it, the server puts it on the grid and the stop
  // follows it; an empty box goes back to following the ask
  document.addEventListener('input', function(e){ if (!e.target || e.target.id !== 'pxbox') return;
    var lf = lockField(); if (!lf) return; lf.value = e.target.value.trim();
    var b = document.getElementById('lock'); if (b) { b.classList.toggle('on', !!lf.value); b.innerHTML = lf.value ? '&#128274;' : '&#128275;'; }
    clearTimeout(window.__t); window.__t = setTimeout(reprice, 600); });
  document.addEventListener('keydown', function(e){ if (!e.target || e.target.id !== 'pxbox' || e.key !== 'Enter') return;
    e.preventDefault(); clearTimeout(window.__t); reprice(); e.target.blur(); });
  // the stop steppers (Steve, 2026-09-30): + widens the stop's distance
  // under the entry by 0.10, − narrows it; a box reading NA starts from the
  // default .2.
  document.addEventListener('click', function(e){ var b = e.target && e.target.closest ? e.target.closest('button.step') : null;
    if (!b || !stopBox || !form) return;
    var fr = b.getAttribute('data-for'); if (fr && fr !== 'stop') return; e.preventDefault();
    var cur = num(stopBox.value); if (isNaN(cur) || cur <= 0) cur = num(stopBox.getAttribute('data-default') || '.2');
    var n = Math.round(cur * 100) + Number(b.getAttribute('data-step')) * 10; if (n < 5) n = 5;
    stopBox.value = shortPts(n / 100); stopLive(n / 100); soon(300); });
  // the stop box holds a distance, which does not move with the market;
  // nothing to follow (kept for the poll's call)
  window.__followStop = function(j){};
  // the strike and contracts boxes on the ticket (Steve, 2026-09-30): typed
  // or stepped, each writes its hidden field and reprices; a new strike is a
  // new contract, so the padlock's price goes with the old one. Strikes
  // step 5 points; contracts 1, never under 1. The boxes live in #fd0,
  // which the poll repaints — hence delegation.
  function setField(n, v){ var el = form ? form.elements[n] : null; if (el) el.value = v; }
  function strikeTo(v){ if (isNaN(v) || v <= 0) return; setField('strike', String(v)); setField('delta', '');
    var lf = lockField(); if (lf) lf.value = ''; }
  function lotsTo(v){ if (isNaN(v)) return; v = Math.max(1, Math.min(99, Math.round(v)));
    setField('lots', String(v)); window.__lots = String(v); return v; }
  document.addEventListener('click', function(e){ var b = e.target && e.target.closest ? e.target.closest('button.step') : null;
    if (!b || !form) return; var fr = b.getAttribute('data-for'); if (fr !== 'strike' && fr !== 'lots') return;
    e.preventDefault(); var box = document.getElementById(fr + 'box'); if (!box) return;
    var d = Number(b.getAttribute('data-step')), v = parseFloat(box.value);
    if (fr === 'strike') { if (isNaN(v)) return; v = Math.round(v / 5) * 5 + d * 5; box.value = String(v); strikeTo(v); }
    else { v = lotsTo((isNaN(v) ? 1 : v) + d); box.value = String(v); }
    soon(300); });
  document.addEventListener('input', function(e){ var t = e.target; if (!t || (t.id !== 'strikebox' && t.id !== 'lotsbox')) return;
    var v = parseFloat(t.value); if (t.id === 'strikebox') strikeTo(v); else lotsTo(v); soon(700); });
  document.addEventListener('keydown', function(e){ var t = e.target; if (!t || (t.id !== 'strikebox' && t.id !== 'lotsbox') || e.key !== 'Enter') return;
    e.preventDefault(); soon(0); t.blur(); });
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
  // Editing is typing, not holding the cursor (st-5n3s). Steve, 2026-09-28:
  // keyed a stop, hit Enter, left the caret in the box, and the ticket stopped
  // following Schwab until he clicked out. Focus alone held every poll paint
  // off; now a box holds it only while a keystroke is still unapplied.
  var typedAt = 0, TYPING_MS = 1500;
  function ours(a){ return !!(a && a.tagName === 'INPUT' && ((form && form.contains(a)) || a.id === 'pxbox')); }
  document.addEventListener('input', function(e){ if (ours(e.target)) typedAt = Date.now(); }, true);
  document.addEventListener('keydown', function(e){ if (e.key === 'Enter' && ours(e.target)) typedAt = 0; }, true);
  function ours2(a){ return ours(a) || !!(a && a.tagName === 'INPUT' && a.closest && a.closest('#fd0')); }
  document.addEventListener('input', function(e){ if (ours2(e.target)) typedAt = Date.now(); }, true);
  function editing(){ return ours2(document.activeElement) && (Date.now() - typedAt) < TYPING_MS; }
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
        # no STOP anywhere (Steve, 2026-09-30: "The 'lock' is sufficent");
        # an unlock clears one left on
        right += f"<a class='chip quiet' href='{actions['account']}'>account</a>"
    return (f"<div class=strip id=strip><div class=l>{broker_badge(st)}{badge}{word}</div>"
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
    # the figure alone, right-aligned beside the clock (Steve, 2026-09-30)
    return f"<b>{usd(b.get('option_buying_power'))}</b>"


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
    # Centred: the strike and the contracts as boxes with the + − steppers
    # (Steve, 2026-09-30: "make input controls for both the target strike ...
    # and the number of contracts ... drop the P (or C). Use the same + -
    # pattern"), then the entry price and its padlock. No 'at', no
    # priced-at time, no total, no stop-loss line and no take-profit line —
    # the take-profit is said once the broker has accepted it (st-5n3s).
    def stepper(field: str, value: str, mode: str, label: str) -> str:
        return (f"<span class=stepper><button type=button class=step data-for={field} data-step=1 "
                f"aria-label='{label} up'>+</button>"
                f"<input id={field}box class=numbox inputmode={mode} enterkeyhint=done autocomplete=off "
                f"aria-label='{label}' value='{value}'>"
                f"<button type=button class=step data-for={field} data-step=-1 "
                f"aria-label='{label} down'>&minus;</button></span>")
    head = (f"<div class='trow tcenter'><div class=tbig>"
            f"{stepper('strike', f'{c.strike:g}', 'numeric', 'strike')} × "
            f"{stepper('lots', str(priced.lots), 'numeric', 'contracts')} "
            # the entry price is a box (co-8mb1z, Steve 2026-09-25: "i want to
            # be able to set the price of my entry"): it shows the limit that
            # will be sent, on the grid; typing in it is locking at that price
            f"<input id=pxbox class=pxbox inputmode=decimal enterkeyhint=go autocomplete=off "
            f"aria-label='entry price' value='{priced.limit:.2f}'> {lock} {live}</div></div>")
    if priced.error:
        return f"<div class=card>{head}<div class=bad>{esc(priced.error)}</div></div>"
    line2 = "".join(f"<div class=warn>{esc(w)}</div>" for w in priced.warnings)
    # Said only when the account cannot pay for it — the refusal of
    # 2026-09-15 09:54 CT was exactly this arithmetic. SEND is off with it.
    short = ""
    avail = spendable(balances)
    if avail is not None and priced.cost_usd is not None and priced.cost_usd > avail:
        short = (f"<div class=bad>this needs {usd(priced.cost_usd)} and the "
                 f"account has {usd(avail)} available — Schwab will refuse it</div>")
    return f"<div class=card>{head}{line2}{short}</div>"


def sendable(priced: Priced | None, balances: dict[str, Any] | None,
             st: Mapping[str, Any] | None = None) -> bool:
    """Is the ticket an order that may go? (Steve, 2026-09-30: "SEND should
    be disabled until a valid entry is active".) A contract at a price, no
    fault on the ticket (a close-at level on the wrong side is one), an
    account that can pay for it, and a service that permits an entry."""
    if priced is None or not priced.ready or priced.error:
        return False
    avail = spendable(balances)
    if avail is not None and priced.cost_usd is not None and priced.cost_usd > avail:
        return False
    arming = (st or {}).get("arming") or {}
    return bool(arming.get("permits_entry", True))


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


def by_delta(contracts: list[Any]) -> list[Any]:
    """The strike table's order (st-rr9o; Steve, 2026-10-01): the most
    expensive strike — the highest |delta| — on top, calls and puts alike,
    on every paint. The mark breaks a tie; a strike the chain gave no delta
    sorts by its mark, after those with one."""
    def key(c: Any) -> tuple[int, float, float]:
        d = abs(c.delta) if c.delta else 0.0
        return (1 if d > 0 else 0, d, c.mid_pts)
    return sorted(contracts, key=key, reverse=True)


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
    shown = by_delta([c for c in priced.contracts
                      if affordable(c, priced.lots, funds) or c.symbol == chosen_sym])
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


def send_fields_html(sel: Selection, priced: Priced | None = None) -> str:
    """The selection as the SEND form's hidden fields — kept fresh by the
    script so SEND carries what the ticket shows (the lock included).

    The strike the ticket shows is pinned here (st-qqxj). A ticket chosen by
    δ carried no strike, so SEND chose again by δ from the chain at the send
    — 2026-09-30 13:38 CT went out as ``delta=0.8`` with no strike — and a
    market that moved between the paint and the tap could send a strike he
    was not looking at. The form keeps following δ; SEND sends the row on
    the ticket."""
    q = sel.as_query()
    if sel.strike is None and priced is not None and priced.contract is not None:
        q = sel.as_query(strike=f"{priced.contract.strike:g}", delta=None)
    return "".join(f"<input type=hidden name='{k}' value='{esc(v)}'>"
                   for k, v in q.items())


# ── the page ─────────────────────────────────────────────────────────────

def render_order(service: ExecService, actions: Mapping[str, str], sel: Selection,
                 priced: Priced | None, *, today, send_nonce: str | None = None,
                 msg: str | None = None, bad: str | None = None,
                 embed: bool = False, fresh: bool = False) -> str:
    from .page import _STYLE, esc as _esc  # noqa: F401 — the shell's style
    st = service.status()
    order = actions["order"]
    parts: list[str] = []
    # A refusal stays on the card only until the next order begins: picking
    # a side (or ?new=1) clears it (Steve, 2026-09-15: "New Order button
    # should clear prior order screen before all else"). A close is not on
    # the card at all now — it is a folded card of its own at the foot of
    # the page (st-qqxj).
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
    dismissed = starting_over and panel_stage_of(st, facts, refused=bad) == "refused"
    panel = panel_html(service, st, actions, now=service.clock(), order_path=order,
                       sel_query=sel.as_query(), refused=bad, dismissed=dismissed)
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
        # the ticking CT clock left, the buying power right (Steve,
        # 2026-09-30); the panel script paints #clock every second. The date
        # sits to the LEFT of the clock in the clock's own font (Steve,
        # 2026-09-30: "date should be positioned to left of time - use same
        # font", st-qqxj) — the session's expiry, today unless a URL says
        # otherwise
        day = (sel.expiry or today).strftime("%m-%d")
        top.append(f"<div class=money><span class=when><span id=day class=clock>{day}</span> "
                   f"<span id=clock class=clock></span></span>"
                   f"<span id=balances>{balances_html(st.get('balances'))}</span></div>")
    parts[0:0] = top
    # The stage card shows only when there is a stage to show: with nothing
    # held, nothing working and no answer to show, the page opens on the
    # side buttons. The card is still on the page, hidden, so a SEND answered
    # in place has somewhere to paint (st-igw0).
    show = (st["positions"] or st["working"] or bad or "data-stage=none" not in panel)
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
        # expiry, δ target and RE-PRICE on one row — one GET form, no script needed.
        # The form carries the chosen strike, so RE-PRICE reprices THAT strike
        # (Steve, 2026-09-15: "simply reprice existing strike" — before st-2s4u
        # the strike was not on the form and RE-PRICE re-chose by delta), and
        # the lock as a hidden field the script toggles; the RE-PRICE button's
        # own field, reprice=1, means at the market and drops the lock.
        # The form: the chosen strike, the lock, the stop's distance and the
        # close-at-SPX level — no δ box and no RE-PRICE (Steve, 2026-09-30,
        # iPad); the poll reprices it live. A δ in a URL still caps the
        # strike choice.
        # the strike and the lots ride the form always: their boxes on the
        # ticket write them (st-5n3s)
        strike_field = (f"<input type=hidden name=strike value='{sel.strike:g}'>"
                        if sel.strike is not None else "<input type=hidden name=strike value=''>")
        delta_field = (f"<input type=hidden name=delta value='{sel.delta:g}'>"
                       if sel.delta is not None and abs(sel.delta - DEFAULT_DELTA) > 1e-9 else "")
        # more than one lot rides the form so a reprice keeps it
        lots_field = f"<input type=hidden name=lots value='{sel.lots}'>"
        limit_val = f"{sel.limit:.2f}" if sel.limit is not None else ""
        # The stop as its dollar distance under the limit (".2" — the flat
        # $20 at one lot). Dollars only at entry (Steve, 2026-10-01,
        # st-a54y: "At entry, only permit a $$ SL but after a fill the level
        # should become an option again"): the close-at-SPX box is gone from
        # this row; the position card keeps its "at SPX" box.
        off = sel.stopoff if sel.stopoff is not None else DEFAULT_STOP_LOSS_USD / (CONTRACT_MULTIPLIER * sel.lots)
        stop_val = short_pts(off)
        parts.append(
            f"<form id=sel method=get action='{order}'>"
            f"<input type=hidden name=side value='{sel.side}'>"
            f"<input type=hidden name=expiry value='{exp.isoformat()}'>"
            f"{strike_field}{delta_field}{lots_field}"
            f"<input type=hidden name=limit value='{limit_val}'>"
            f"<input type=hidden name=stop value='{esc(sel.stop or '')}'>"
            f"<input type=hidden name=stopoff value='{f'{sel.stopoff:.2f}' if sel.stopoff else ''}'>"
            "<div class='row stops'>"
            "<label class='dl stopl' title='the stop, in dollars under the entry (.2)'>"
            "<span class=k>stop $</span>"
            # the steppers (Steve, 2026-09-30): + to the left of the box, −
            # to the right; each widens or narrows the stop by 0.10
            "<button type=button class=step data-step=1 aria-label='widen the stop 0.10'>+</button>"
            f"<input id=stopbox inputmode=decimal enterkeyhint=done autocomplete=off "
            f"value='{stop_val}' data-default='{short_pts(DEFAULT_STOP_LOSS_USD / (CONTRACT_MULTIPLIER * sel.lots))}'>"
            "<button type=button class=step data-step=-1 aria-label='narrow the stop 0.10'>&minus;</button></label>"
            "</div></form>")
        # the one action on this stage: SEND, one tap from the decision
        # (st-igw0 — the PREVIEW step is gone; the service runs the broker's
        # own preview inside every place). The script sends it by fetch and
        # paints the answer; the plain form redirects. It sits under the
        # stop and close-at row (Steve, 2026-09-30: "move the stop and close
        # at line to above the send button", st-qqxj), so the last thing set
        # before the tap is the stop.
        # SEND is off until the ticket is an order that may go (Steve,
        # 2026-09-30); every poll turns it on or off again (st-5n3s)
        if send_nonce:
            ok = sendable(priced, st.get("balances"), st)
            parts.append(
                f"<form method=post action='{actions['order_send']}' class=sendform>"
                f"<span id=sendfields>{send_fields_html(sel, priced)}</span>"
                f"<input type=hidden name=nonce value='{esc(send_nonce)}'>"
                "<input type=hidden name=ajax value=''>"
                f"<button class='big send'{'' if ok else ' disabled'}>SEND</button></form>")
        # strikes around spot — only the ones the account can pay for (st-644f)
        parts.append("<div class=card><div id=strikes>"
                     f"{strikes_html(priced, order, st.get('balances'))}</div></div>")
    elif not sel.side:
        parts.append("<div class=k style='text-align:center'>pick a side to see the strikes</div>")

    # the day, one line: the money and nothing else (st-644f — no attempts,
    # no headroom; see position_html)
    pnl = st.get("pnl") or {}
    # the day's closed positions, a folded card each, newest on top — the
    # foot of the page (Steve, 2026-09-30, st-qqxj); the poll keeps it fresh
    closed = closed_html(facts, service.clock())
    parts.append(f"<div id=closed>{closed}</div>")
    parts.append(f"<div class=foot><span id=today>today {money(pnl.get('day_usd'))}</span></div>")
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
