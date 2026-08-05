#!/usr/bin/env python3
"""Fire server — the single execution surface for staged tickets. [st-1o47]

Phase 1 is DRY-RUN ONLY. There is no order client in this process, in this
repo's agent-reachable tooling, or anywhere else: the schwab-py fork is
hobbled (lib/schwab-py ce2ccd9) and stays that way. FIRE in Phase 1 journals
the intent and reports "nothing transmitted". The future order client
(st-bxls) will live behind ~/.schwab_fire_key — a file only Steve creates —
and be importable only from here.

Architecture of record (R3 verdict, st-1tgh; Steve approved 2026-08-05):
  - Agents stage a ticket as DATA: they write data/exec/fire-ticket.json.
    They never call this server. One ticket at a time, whole-file replace.
  - This server binds ONLY to the box's Tailscale address — the form is
    reachable from Steve's devices and from nothing else on any network.
  - Steve alone fires: ARM -> single-use nonce -> FIRE, all from his screen.

Rails (all enforced server-side, none bypassable from the form):
  - QTY_CAP:      a ticket asking for more than QTY_CAP contracts cannot ARM.
  - STALE_MIN:    a ticket staged more than STALE_MIN minutes ago cannot ARM
                  or FIRE — the market has moved; restage.
  - Kill switch:  data/exec/FIRE_DISABLED existing disables ARM/FIRE. Remove
                  the file to re-enable. Creating it takes one `touch`.
  - Nonce:        FIRE requires the single-use nonce minted by ARM, expiring
                  NONCE_TTL_S after mint. Reload the form and re-ARM if it
                  lapses.
  - Journal:      every stage-view/arm/fire/refusal appends to
                  data/exec/fire-journal-<day>.jsonl. Append-only.

Run:    .venv/bin/python3 scripts/fire_server.py           # binds tailscale IP :8777
Test:   .venv/bin/python3 -m pytest tests/scripts/test_fire_server.py
Stage a ticket (agents do exactly this, nothing else):
        write JSON to data/exec/fire-ticket.json — schema in load_ticket().
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, redirect, render_template_string, request
from markupsafe import escape

ROOT = Path(__file__).resolve().parent.parent

PORT = 8777
TICKET_PATH = ROOT / "data" / "exec" / "fire-ticket.json"
KILL_PATH = ROOT / "data" / "exec" / "FIRE_DISABLED"
JOURNAL_DIR = ROOT / "data" / "exec"
FIRE_KEY = Path.home() / ".schwab_fire_key"   # Phase 2 gate; informational here

QTY_CAP = 1          # SPX singletons — one contract per ticket, hard stop
STALE_MIN = 10       # minutes; older tickets must be restaged
NONCE_TTL_S = 60     # ARM -> FIRE window

SIDES = ("BUY_TO_OPEN", "SELL_TO_CLOSE", "BUY_TO_CLOSE", "SELL_TO_OPEN")

app = Flask(__name__)
_nonces: dict[str, float] = {}   # nonce -> expiry epoch; single-use


def tailscale_ip() -> str:
    """The box's tailnet IPv4. Loud failure — never fall back to 0.0.0.0."""
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"tailscale ip failed: {e}") from e
    ip = (out.stdout or "").strip().splitlines()
    if out.returncode != 0 or not ip:
        raise RuntimeError(
            "No tailscale address (is tailscaled up?). Refusing to bind — "
            "this server must never listen on a non-tailnet interface.")
    return ip[0]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def journal(event: dict) -> None:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    day = now_utc().astimezone().strftime("%Y-%m-%d")
    path = JOURNAL_DIR / f"fire-journal-{day}.jsonl"
    event = {"ts": now_utc().isoformat(), "mode": "dry-run", **event}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def load_ticket() -> tuple[dict | None, list[str]]:
    """Read the staged ticket. Returns (ticket|None, problems).

    Schema: {"id": str, "ts_staged": iso8601, "symbol": OSI str,
             "side": one of SIDES, "qty": int, "limit": float,
             "note": str (optional), "staged_by": str}
    A malformed file is a ticket that cannot ARM — shown with its problems,
    never silently ignored.
    """
    if not TICKET_PATH.exists():
        return None, []
    problems: list[str] = []
    try:
        t = json.loads(TICKET_PATH.read_text(encoding="utf-8"))
    except ValueError as e:
        return {"raw_error": str(e)}, [f"ticket file is not valid JSON: {e}"]
    for field in ("id", "ts_staged", "symbol", "side", "qty", "limit", "staged_by"):
        if field not in t:
            problems.append(f"missing field: {field}")
    if t.get("side") and t["side"] not in SIDES:
        problems.append(f"side {t['side']!r} not in {SIDES}")
    if isinstance(t.get("qty"), int):
        if t["qty"] < 1:
            problems.append("qty < 1")
        elif t["qty"] > QTY_CAP:
            problems.append(f"qty {t['qty']} exceeds hard cap {QTY_CAP}")
    elif "qty" in t:
        problems.append("qty is not an integer")
    if "limit" in t and (not isinstance(t.get("limit"), (int, float)) or t["limit"] <= 0):
        problems.append("limit is not a positive number")
    return t, problems


def ticket_age_min(t: dict) -> float | None:
    try:
        staged = datetime.fromisoformat(t["ts_staged"])
        if staged.tzinfo is None:
            staged = staged.replace(tzinfo=timezone.utc)
        return (now_utc() - staged).total_seconds() / 60.0
    except (KeyError, ValueError):
        return None


def killed() -> bool:
    return KILL_PATH.exists()


def mint_nonce() -> str:
    n = secrets.token_urlsafe(16)
    _nonces[n] = _time.time() + NONCE_TTL_S
    return n


def burn_nonce(n: str) -> bool:
    """True iff the nonce exists, is unexpired, and has not been used."""
    exp = _nonces.pop(n, None)
    return exp is not None and _time.time() <= exp


PAGE = """<!doctype html><html><head>
<meta name=viewport content="width=device-width, initial-scale=1">
{% if refresh %}<meta http-equiv=refresh content=10>{% endif %}
<title>FIRE — dry run</title><style>
 body{background:#111;color:#eee;font:18px/1.5 -apple-system,system-ui,sans-serif;
      max-width:34em;margin:2em auto;padding:0 1em}
 .card{background:#1b1b1b;border:1px solid #333;border-radius:12px;padding:1.2em;margin:1em 0}
 .k{color:#888} .warn{color:#fbbf24} .bad{color:#f87171} .ok{color:#34d399}
 .big{display:block;width:100%;padding:1em;font-size:1.4em;border-radius:12px;
      border:0;margin:.6em 0;cursor:pointer}
 .arm{background:#b45309;color:#fff} .fire{background:#b91c1c;color:#fff}
 .cancel{background:#333;color:#eee}
 .exit{background:#7f1d1d;color:#fff;border:2px solid #f87171}
 h1{font-size:1.2em;letter-spacing:.08em} .mode{color:#60a5fa}
</style></head><body>
<h1>FIRE SERVER <span class=mode>· DRY RUN — no order client exists</span></h1>
{{ body|safe }}
</body></html>"""


def render(body: str, *, refresh: bool = False) -> str:
    """Auto-refresh belongs ONLY on the idle page.

    Two reasons, both learned live 2026-08-05: a refresh of a POST response
    re-requests /arm as a GET and 405s, and — worse — a page that reloads
    itself during the confirm window would yank the FIRE button out from
    under Steve mid-decision. The armed page holds still.
    """
    return render_template_string(PAGE, body=body, refresh=refresh)


def _ticket_card(t: dict, problems: list[str], age: float | None) -> str:
    # Ticket values come from a file agents write — escape them; only this
    # module's own chrome goes through |safe.
    rows = "".join(
        f"<div><span class=k>{k}</span> {escape(t.get(k, '—'))}</div>"
        for k in ("id", "symbol", "side", "qty", "limit", "note", "staged_by"))
    age_s = ("<div class=k>staged " + (f"{age:.1f} min ago" if age is not None
             else "at unparseable time") + "</div>")
    probs = "".join(f"<div class=bad>✗ {escape(p)}</div>" for p in problems)
    return f"<div class=card>{rows}{age_s}{probs}</div>"


@app.get("/health")
def health():
    return {"ok": True, "mode": "dry-run", "killed": killed(),
            "ticket_staged": TICKET_PATH.exists()}


EXIT_BLOCK = """<hr style="border:0;border-top:1px solid #333;margin:2.5em 0">
<form method=post action=/exit-all>
<button class='big exit'>EXIT ALL POSITIONS</button></form>
<div class=k>Always available — including when the kill switch is on.</div>"""


@app.get("/")
def index():
    if killed():
        return render("<div class='card bad'>KILL SWITCH ON — entries "
                      "disabled. Remove data/exec/FIRE_DISABLED to re-enable."
                      "</div>" + EXIT_BLOCK, refresh=True)
    t, problems = load_ticket()
    if t is None:
        return render("<div class=card><span class=k>No ticket staged.</span>"
                      "<br>Agents stage by writing data/exec/fire-ticket.json."
                      "</div>" + EXIT_BLOCK, refresh=True)
    age = ticket_age_min(t)
    stale = age is None or age > STALE_MIN
    body = _ticket_card(t, problems, age)
    if stale:
        body += ("<div class='card warn'>STALE — staged over "
                 f"{STALE_MIN} min ago. Restage to act.</div>")
    elif problems:
        body += "<div class='card bad'>Ticket cannot ARM with problems above.</div>"
    else:
        body += ("<form method=post action=/arm>"
                 "<button class='big arm'>ARM</button></form>")
    return render(body + EXIT_BLOCK, refresh=True)


@app.post("/exit-all")
def exit_all():
    """Panic surface. Deliberately NOT gated by the kill switch.

    FIRE_DISABLED exists to stop the machine ENTERING trades. If it also
    blocked exits it would trap Steve in positions at precisely the moment
    he most needs out — backwards, and the reason this route checks nothing
    but its own confirm. Ticket state, staleness and the qty cap are equally
    irrelevant here: exit acts on live account state, not a staged ticket.
    """
    n = mint_nonce()
    journal({"event": "exit_all_armed", "nonce": n[:6] + "…"})
    return render(
        "<div class='card bad'>CLOSE EVERY OPEN POSITION.</div>"
        "<div class=card><span class=k>positions</span> unknown — the broker "
        "fork is hobbled (no account access), so this cannot enumerate them. "
        "Phase 2 lists each position here before you confirm.</div>"
        f"<form method=post action=/exit-all/confirm>"
        f"<input type=hidden name=nonce value='{n}'>"
        f"<button class='big exit'>CONFIRM — FLATTEN (dry run)</button></form>"
        "<form method=get action=/><button class='big cancel'>cancel</button></form>")


@app.post("/exit-all/confirm")
def exit_all_confirm():
    if not burn_nonce(request.form.get("nonce", "")):
        journal({"event": "exit_all_refused", "reason": "bad or expired nonce"})
        return render("<div class='card bad'>Exit refused: confirm window "
                      "lapsed. Tap EXIT ALL again.</div><a href=/>back</a>"), 409
    journal({"event": "exit_all", "transmitted": False,
             "reason_not_transmitted": "phase 1 — no order client exists"})
    return render(
        "<div class='card ok'>DRY RUN COMPLETE — nothing transmitted.<br>"
        "Intent journaled. Phase 2 (st-bxls) closes each open position with "
        "a market order.</div><a href=/>back</a>")


@app.get("/arm")
@app.get("/fire")
@app.get("/exit-all")
def _action_get_redirects_home():
    """A refresh or back-button on an action URL lands home, never a 405."""
    return redirect("/", code=303)


@app.post("/arm")
def arm():
    t, problems = load_ticket()
    age = ticket_age_min(t) if t else None
    refusal = (
        "kill switch on" if killed()
        else "no ticket staged" if t is None
        else "ticket has problems" if problems
        else "ticket stale" if (age is None or age > STALE_MIN)
        else None)
    if refusal:
        journal({"event": "arm_refused", "reason": refusal})
        return render(f"<div class='card bad'>ARM refused: {refusal}.</div>"
                      "<a href=/>back</a>"), 409
    n = mint_nonce()
    journal({"event": "armed", "ticket_id": t.get("id"), "nonce": n[:6] + "…"})
    return render(
        _ticket_card(t, [], age)
        + f"<form method=post action=/fire><input type=hidden name=nonce value='{n}'>"
          f"<button class='big fire'>FIRE (dry run)</button></form>"
          f"<form method=get action=/><button class='big cancel'>cancel</button></form>"
          f"<div class=k>confirm window {NONCE_TTL_S}s, single use</div>")


@app.post("/fire")
def fire():
    n = request.form.get("nonce", "")
    t, problems = load_ticket()
    age = ticket_age_min(t) if t else None
    refusal = (
        "kill switch on" if killed()
        else "bad, reused, or expired nonce — re-ARM" if not burn_nonce(n)
        else "no ticket staged" if t is None
        else "ticket has problems" if problems
        else "ticket stale" if (age is None or age > STALE_MIN)
        else None)
    if refusal:
        journal({"event": "fire_refused", "reason": refusal})
        return render(f"<div class='card bad'>FIRE refused: {refusal}.</div>"
                      "<a href=/>back</a>"), 409
    journal({"event": "fire", "ticket": t, "transmitted": False,
             "reason_not_transmitted": "phase 1 — no order client exists"})
    return render(
        "<div class='card ok'>DRY RUN COMPLETE — nothing transmitted.<br>"
        "Intent journaled. The order client (st-bxls) does not exist yet, "
        "by design.</div><a href=/>back</a>")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fire server (Phase 1 — dry run)")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    ip = tailscale_ip()
    print(f"fire server (DRY RUN) binding {ip}:{args.port} — tailnet only",
          flush=True)
    journal({"event": "server_start", "bind": f"{ip}:{args.port}"})
    app.run(host=ip, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
