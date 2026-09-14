"""The page — Steve's surface on the tailnet. [st-p8k8]

Stage 3 of the live execution service (epic st-5qjq, design §3–§5). The API in
``execd.api`` is the door the trading code and the agents use; it has no way
to arm the service, clear the STOP, or touch a credential, and a test asserts
that against its URL map. Everything it deliberately lacks lives here instead,
on a second loopback port that only ``tailscale serve`` publishes — tailnet
only, funnel never — at ``https://mydesk-1.tail89f676.ts.net/exec/``.

**The rule this module holds:** every action that *adds* capability takes the
passphrase; every action that *reduces* it does not.

- **Unlock** (passphrase): opens the vault, hands the trading credential to
  the arming state until today's close. The passphrase never leaves the
  request — it is not stored, logged, journaled or echoed.
- **Resume** (passphrase): clears the STOP file. Turning STOP *on* is a bare
  button — from a phone, one tap — because the switch that stops new risk
  must never be the one that is hard to reach.
- **Re-authorise** (passphrase): the weekly ritual for each of the two Schwab
  apps. The page shows the login link, Steve pastes the address the browser
  lands on, the service exchanges the code, proves the grant against the
  family it is for, and only then stores it — the trading grant back into the
  vault under the same passphrase, the market grant to its file. If the
  service is armed at the time, the credential in memory is swapped for the
  new one so the new refresh token is the one in use.
- **STOP, STAND DOWN, LOCK, FLATTEN**: bare buttons. FLATTEN asks once more
  on its own page with a single-use nonce (the fire server's rail, carried
  here), because it transmits.

Why the passphrase and not a login: the page is reachable only from Steve's
tailnet devices, and on this box every agent shell is root and can reach the
loopback port directly. A cookie or a header is something a root process can
forge; the passphrase is the one thing no agent has. So the port is not the
boundary — the passphrase is, and the hook change presented with this stage
denies agent shells the port as a second layer, not the first.

What this module never does: import a transport (``execd.schwab.new_client``
hands it one), name a plaintext credential file, or put a token, key or
passphrase in a message, a log line or a journal entry.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from flask import Blueprint, Flask, redirect, request, url_for
from markupsafe import escape as _escape

from .arming import ArmState, Locked
from .bounds import CT
from .broker import BrokerError
from .schwab import (VAULT_VERSION, App, Credential, authorize_url, code_from_received_url,
                     exchange, new_client, trading_payload, verify_grant)
from .service import ExecService, Refused
from .vault import BadPassphrase, Vault, VaultError, VaultMissing

#: The page's loopback port. ``tailscale serve --bg --set-path /exec
#: http://127.0.0.1:8779/exec`` publishes it; nothing else should.
PAGE_HOST = "127.0.0.1"
PAGE_PORT = 8779

#: The public address, for the words on the page and in the install output.
PAGE_URL = "https://mydesk-1.tail89f676.ts.net/exec/"

#: The callback both Schwab apps are registered with. The one the repo's
#: ``.env.template`` carries; the service cannot read ``.env`` (it runs as its
#: own user), so the install passes it as a flag and this is the default.
DEFAULT_CALLBACK_URL = "https://127.0.0.1:8182"

#: A FLATTEN confirm and a re-auth link each live this long, single use.
CONFIRM_TTL_S = 60.0
REAUTH_TTL_S = 10 * 60.0

#: A wrong passphrase costs this long before the answer, on top of scrypt.
WRONG_PASSPHRASE_DELAY_S = 1.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def esc(value: Any) -> str:
    """HTML-escape to a plain ``str``. ``markupsafe.escape`` returns a
    ``Markup``, and ``str + Markup`` escapes the *str* operand — a ``<pre>``
    tag concatenated onto one arrives on the page as ``&lt;pre&gt;``."""
    return str(_escape("" if value is None else str(value)))


# ── the market credential file ────────────────────────────────────────────


class CredentialFile:
    """The market-data app's credential on disk, and its in-memory copy.

    Loaded once at start (``python -m execd --market-credential FILE``) and
    handed to the transport as a callable, so a re-authorisation on the page
    can replace both the file and what the transport sees, atomically, without
    a restart. Plain JSON, mode 0600, owned by the service user — outside the
    vault by design (st-p9mx: this app cannot trade, so a credential that must
    load before Steve types anything costs nothing to hold that way)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._payload: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        Credential.from_payload(raw)      # shape-checked here, not on the first quote
        with self._lock:
            self._payload = raw
        return raw

    def current(self) -> dict[str, Any]:
        """What the transport calls on every market read."""
        with self._lock:
            if self._payload is None:
                raise BrokerError("no market credential is loaded")
            return self._payload

    def save(self, payload: Mapping[str, Any]) -> None:
        """Write, fsync, rename, 0600 — the vault's discipline, for the same
        reason: a half-written credential is one the service will not start
        with, and this box has been OOM-killed mid-run before."""
        Credential.from_payload(payload)
        blob = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            os.chmod(self.path, 0o600)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        with self._lock:
            self._payload = dict(payload)


# ── single-use tokens ─────────────────────────────────────────────────────


@dataclass
class _Pending:
    kind: str
    expires: float
    app: App | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class _Nonces:
    """FLATTEN confirms and re-auth links: issued once, spent once, dead after
    their TTL. In memory only — a restart forgets them, which is right."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._items: dict[str, _Pending] = {}
        self._lock = threading.Lock()

    def issue(self, kind: str, ttl: float, **extra: Any) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._sweep()
            self._items[token] = _Pending(kind, self.clock() + ttl,
                                          extra.pop("app", None), extra)
        return token

    def spend(self, token: str, kind: str) -> _Pending | None:
        with self._lock:
            self._sweep()
            item = self._items.pop(token, None)
        if item is None or item.kind != kind:
            return None
        return item

    def _sweep(self) -> None:
        now = self.clock()
        for k in [k for k, v in self._items.items() if v.expires <= now]:
            del self._items[k]


# ── the page ──────────────────────────────────────────────────────────────


def create_page(service: ExecService, *, vault: Vault | str | Path,
                market: CredentialFile | None = None,
                callback_url: str = DEFAULT_CALLBACK_URL,
                http_client: Any | None = None,
                clock: Callable[[], datetime] = _utcnow,
                monotonic: Callable[[], float] = time.monotonic) -> Flask:
    """Build the page app. ``vault`` is the path (or a :class:`Vault`) the
    trading credential lives in; ``market`` the market credential file, if
    the service holds one; ``http_client`` is for tests (an ``httpx.Client``
    over a mock transport) — production builds its own from the transport
    module."""
    vault = vault if isinstance(vault, Vault) else Vault(vault)
    nonces = _Nonces(monotonic)
    app = Flask("execd-page")
    bp = Blueprint("exec", __name__, url_prefix="/exec")

    def client():
        return http_client if http_client is not None else new_client()

    # ── helpers ───────────────────────────────────────────────────────
    def home(msg: str | None = None, *, bad: bool = False):
        if not msg:
            return redirect(url_for("exec.index"), code=303)
        return redirect(url_for("exec.index", **{"bad" if bad else "msg": msg}), code=303)

    def passphrase() -> str:
        return request.form.get("passphrase", "")

    def open_vault(pw: str) -> dict[str, Any]:
        """Open the vault or raise a :class:`PageRefused` with plain words.
        A wrong passphrase and a tampered file are the same error by the
        vault's design; the page says so in one sentence and waits a second."""
        try:
            return vault.load(pw)
        except VaultMissing:
            raise PageRefused(f"There is no vault at {vault.path}. Run "
                              f"scripts/execd_vault_init.py --vault {vault.path} first.")
        except BadPassphrase:
            service.journal.record("refused", kind="passphrase",
                                   refused={"bound": "passphrase",
                                            "reason": "the vault did not open"})
            time.sleep(WRONG_PASSPHRASE_DELAY_S)
            raise PageRefused("The vault did not open. Nothing changed.")
        except VaultError as exc:
            raise PageRefused(f"The vault is not readable: {exc}")

    # ── routes ────────────────────────────────────────────────────────
    @app.get("/")
    def root():
        return redirect(url_for("exec.index"), code=302)

    @bp.get("/")
    def index():
        return _render_index(service, vault, market, clock, _actions(),
                             msg=request.args.get("msg"), bad=request.args.get("bad"))

    @bp.post("/unlock")
    def unlock():
        pw = passphrase()
        try:
            payload = trading_payload(open_vault(pw))
            Credential.from_payload(payload)
            status = service.unlock(payload)
        except PageRefused as exc:
            return home(str(exc), bad=True)
        except ValueError as exc:
            return home(f"The vault opened but its contents are not a credential: {exc}",
                        bad=True)
        except Refused as exc:
            return home(f"Unlock refused: {exc.refusal.reason}", bad=True)
        finally:
            del pw
        until = status["arming"].get("expires_at_ct") or "the close"
        return home(f"Armed until {until}.")

    @bp.post("/stop")
    def stop():
        service.stop()
        return home("STOP is on. No new positions. Getting out still works.")

    @bp.post("/resume")
    def resume():
        pw = passphrase()
        try:
            if not vault.exists:
                raise PageRefused(f"There is no vault at {vault.path}; STOP stays on.")
            if not vault.verify(pw):
                service.journal.record("refused", kind="passphrase",
                                       refused={"bound": "passphrase",
                                                "reason": "the vault did not open"})
                time.sleep(WRONG_PASSPHRASE_DELAY_S)
                raise PageRefused("The vault did not open. STOP stays on.")
        except PageRefused as exc:
            return home(str(exc), bad=True)
        except VaultError as exc:
            return home(f"The vault is not readable: {exc}. STOP stays on.", bad=True)
        finally:
            del pw
        service.resume()
        return home("STOP is off.")

    @bp.post("/stand-down")
    def stand_down():
        service.stand_down()
        return home("Stood down for the day. Nothing new opens; exits still work.")

    @bp.post("/lock")
    def lock():
        service.lock()
        return home("Locked. The credential is out of memory; the passphrase brings it back.")

    @bp.post("/flatten")
    def flatten():
        n = nonces.issue("flatten", CONFIRM_TTL_S)
        return _render_confirm_flatten(service, n, _actions())

    @bp.post("/flatten/confirm")
    def flatten_confirm():
        if nonces.spend(request.form.get("nonce", ""), "flatten") is None:
            return home(f"That FLATTEN confirm was used already or is older than "
                        f"{int(CONFIRM_TTL_S)} seconds. Nothing was sent.", bad=True)
        try:
            result = service.flatten(reason="page")
        except Refused as exc:
            return home(f"Flatten refused: {exc.refusal.reason}", bad=True)
        except BrokerError as exc:
            return home(f"Flatten could not reach the broker: {exc}", bad=True)
        closed = result.get("closed") or result.get("flattened") or []
        n_closed = len(closed) if isinstance(closed, list) else closed
        return home(f"Flatten sent. {n_closed} position(s) closed; "
                    f"read the journal below.")

    # ── re-authorisation ──────────────────────────────────────────────
    @bp.post("/reauth/link")
    def reauth_link():
        which = request.form.get("app", "")
        try:
            target = App(which)
        except ValueError:
            return home("Choose which app to re-authorise.", bad=True)
        pw = passphrase()
        try:
            source = _app_credential(target, open_vault(pw), market)
        except PageRefused as exc:
            return home(str(exc), bad=True)
        finally:
            del pw
        state = nonces.issue("reauth", REAUTH_TTL_S, app=target)
        link = authorize_url(source.app_key, _callback(source, callback_url), state)
        return _render_reauth(target, link, state, _actions())

    @bp.post("/reauth/store")
    def reauth_store():
        state = request.form.get("state", "")
        pw = passphrase()
        try:
            # The passphrase is proved BEFORE the single-use state is spent,
            # so a mistyped passphrase costs a retry, not a second Schwab login.
            payload = open_vault(pw)
            pending = nonces.spend(state, "reauth")
            if pending is None or pending.app is None:
                raise PageRefused(f"That login link is older than {int(REAUTH_TTL_S // 60)} "
                                  f"minutes or was used already. Ask for a new one.")
            target = pending.app
            source = _app_credential(target, payload, market)
            code = code_from_received_url(request.form.get("received_url", ""), state)
            with client() as c:
                wrapped = exchange(c, source.app_key, source.secret,
                                   _callback(source, callback_url), code)
                verify_grant(c, target, wrapped)
            wall = _store_grant(service, vault, market, target, payload, wrapped, pw)
        except PageRefused as exc:
            return home(str(exc), bad=True)
        except ValueError as exc:
            return home(f"The pasted address was not usable: {exc}. Nothing stored.", bad=True)
        except BrokerError as exc:
            return home(f"Re-authorisation of the {target.value} app failed: {exc}", bad=True)
        finally:
            del pw
        return home(f"The {target.value} app is re-authorised. Its new wall is "
                    f"{wall.astimezone(CT).strftime('%a %Y-%m-%d %H:%M CT')}. "
                    f"Do the other app in this sitting.")

    def _actions() -> dict[str, str]:
        """Absolute paths for every form, so a page served at ``/exec/flatten``
        posts its confirm to ``/exec/flatten/confirm`` and not to a sibling."""
        return {name: url_for(f"exec.{name}") for name in (
            "index", "unlock", "stop", "resume", "stand_down", "lock", "flatten",
            "flatten_confirm", "reauth_link", "reauth_store")}

    app.register_blueprint(bp)
    return app


class PageRefused(RuntimeError):
    """A refusal the page shows Steve in plain words. Never carries a value."""


@dataclass(frozen=True)
class _Source:
    app_key: str
    secret: str
    callback_url: str | None


def _app_credential(target: App, vault_payload: Mapping[str, Any],
                    market: CredentialFile | None) -> _Source:
    """The app key and secret the OAuth calls need, from where each lives:
    the trading app's in the vault (already open, or we would not be here);
    the market app's in its file. The passphrase gates both — a market
    re-auth cannot leak trading capability, but the page treats every
    credential write as Steve's act, and the vault opening is how it knows."""
    if target is App.TRADING:
        trading = trading_payload(vault_payload)
        try:
            cred = Credential.from_payload(trading)
        except ValueError as exc:
            raise PageRefused(f"The vault holds no usable trading credential: {exc}")
        return _Source(cred.app_key, cred.secret, trading.get("callback_url"))
    if market is None:
        raise PageRefused("This service was started without a market credential file; "
                          "there is nothing to re-authorise for the market app.")
    try:
        raw = market.current()
        cred = Credential.from_payload(raw)
    except (BrokerError, ValueError) as exc:
        raise PageRefused(f"The market credential is not usable: {exc}")
    return _Source(cred.app_key, cred.secret, raw.get("callback_url"))


def _callback(source: _Source, default: str) -> str:
    return source.callback_url or default


def _store_grant(service: ExecService, vault: Vault, market: CredentialFile | None,
                 target: App, vault_payload: Mapping[str, Any], wrapped: Mapping[str, Any],
                 pw: str) -> datetime:
    """Store a verified grant where its app's credential lives, and if the
    service is armed, put the new trading credential into memory too. Journals
    the event with the app and its new wall — never a value."""
    if target is App.TRADING:
        trading = dict(trading_payload(vault_payload))
        trading["token"] = dict(wrapped)
        envelope: dict[str, Any] = dict(vault_payload) if "trading" in vault_payload else {}
        envelope["version"] = VAULT_VERSION
        envelope["trading"] = trading
        vault.store(envelope, pw)
        wall = Credential.from_payload(trading).refresh_wall
        if service.arming.state is not ArmState.LOCKED:
            try:
                service.arming.replace_credential(trading)
            except Locked:
                pass
        service.journal.record("reauth", app=target.value, refresh_wall=wall,
                               in_memory=service.arming.state is not ArmState.LOCKED)
        return wall
    assert market is not None
    payload = dict(market.current())
    payload["token"] = dict(wrapped)
    market.save(payload)
    wall = Credential.from_payload(payload).refresh_wall
    service.journal.record("reauth", app=target.value, refresh_wall=wall, in_memory=True)
    return wall


# ── rendering ─────────────────────────────────────────────────────────────

_STYLE = """
<meta name=viewport content="width=device-width, initial-scale=1">
<style>
 body{font-family:-apple-system,system-ui,sans-serif;background:#0b1020;color:#e5e7eb;
      margin:0;padding:1em;max-width:34em;margin-inline:auto}
 h1{font-size:1.15em;letter-spacing:.06em;margin:.2em 0 .6em}
 h2{font-size:1em;color:#9ca3af;margin:1.2em 0 .4em;text-transform:uppercase;letter-spacing:.08em}
 .card{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:.9em 1em;margin:.6em 0}
 .state{font-size:1.6em;font-weight:700}
 .LOCKED{color:#9ca3af}.ARMED{color:#34d399}.STOOD_DOWN{color:#fbbf24}
 .paper{background:#fbbf24;color:#111;font-weight:700;padding:.5em .7em;border-radius:6px;margin-bottom:.6em}
 .live{background:#dc2626;color:#fff;font-weight:700;padding:.5em .7em;border-radius:6px;margin-bottom:.6em}
 .stop-on{color:#f87171;font-weight:700}
 .k{color:#9ca3af;font-size:.9em}
 .big{display:block;width:100%;padding:.9em;font-size:1.25em;border-radius:12px;border:0;
      margin:.5em 0;font-weight:700;cursor:pointer}
 .arm{background:#059669;color:#fff}.stop{background:#dc2626;color:#fff}
 .exit{background:#b45309;color:#fff}.quiet{background:#374151;color:#e5e7eb}
 .cancel{background:#1f2937;color:#9ca3af}
 input[type=password],input[type=text],textarea{width:100%;box-sizing:border-box;font-size:1.1em;
      padding:.6em;border-radius:8px;border:1px solid #374151;background:#0b1020;color:#e5e7eb}
 .msg{background:#064e3b;border:1px solid #10b981;border-radius:10px;padding:.7em 1em}
 .bad{background:#7f1d1d;border:1px solid #ef4444;border-radius:10px;padding:.7em 1em}
 table{width:100%;border-collapse:collapse;font-size:.92em}
 td{padding:.25em .2em;border-bottom:1px solid #1f2937;vertical-align:top}
 td:first-child{color:#9ca3af;white-space:nowrap;padding-right:.8em}
 pre{white-space:pre-wrap;word-break:break-all;font-size:.8em;color:#cbd5e1;margin:0}
 details summary{cursor:pointer;color:#9ca3af}
 a{color:#60a5fa;word-break:break-all}
</style>
"""


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset=utf-8><title>{esc(title)}</title>"
            f"{_STYLE}</head><body><h1>{esc(title)}</h1>{body}</body></html>")


def _fmt_wall(iso: str | None, now: datetime) -> str:
    if not iso:
        return "unknown"
    try:
        wall = datetime.fromisoformat(iso)
    except ValueError:
        return esc(iso)
    left = wall - now
    days = left.total_seconds() / 86400
    when = wall.astimezone(CT).strftime("%a %m-%d %H:%M CT")
    if days <= 0:
        return f"<span class=stop-on>PAST THE WALL ({when}) — re-authorise now</span>"
    if days <= 1:
        return f"<span class=stop-on>{days * 24:.0f} hours left ({when})</span>"
    if days <= 2:
        return f"<span style='color:#fbbf24'>{days:.1f} days left ({when})</span>"
    return f"{days:.1f} days left ({when})"


def _render_index(service: ExecService, vault: Vault, market: CredentialFile | None,
                  clock: Callable[[], datetime], a: dict[str, str], *,
                  msg: str | None, bad: str | None) -> str:
    st = service.status()
    arming = st["arming"]
    state = arming["state"]
    now = clock()
    day = st["day"]
    parts: list[str] = []

    if msg:
        parts.append(f"<div class=msg>{esc(msg)}</div>")
    if bad:
        parts.append(f"<div class=bad>{esc(bad)}</div>")

    # ── state ──
    stop_line = ("<div class=stop-on>STOP IS ON — no new positions</div>"
                 if arming["killed"] else "<div class=k>STOP is off</div>")
    until = arming.get("expires_at_ct")
    sub = {"LOCKED": "no credential in memory — enter the passphrase to arm",
           "ARMED": f"armed until {until}" if until else "armed",
           "STOOD_DOWN": "stood down — nothing new opens; exits still work"}[state]
    mode = str(st.get("mode", "live"))
    mode_line = ("<div class=paper>PAPER — orders are simulated against live quotes; "
                 "nothing reaches Schwab's order book</div>" if mode == "paper"
                 else "<div class=live>LIVE — orders reach Schwab</div>")
    parts.append(f"<div class=card>{mode_line}"
                 f"<div class='state {state}'>{state.replace('_', ' ')}</div>"
                 f"<div class=k>{esc(sub)}</div>{stop_line}"
                 f"<div class=k>{esc(st['now_ct'])} · service {esc(st['sha'])} · "
                 f"mode {esc(mode)}</div></div>")

    # ── controls ──
    if state == "LOCKED":
        parts.append(f"<form method=post action='{a['unlock']}'>"
                     "<input type=password name=passphrase placeholder='vault passphrase' "
                     "autocomplete=current-password required>"
                     "<button class='big arm'>UNLOCK — arm until the close</button></form>")
    if not arming["killed"]:
        parts.append(f"<form method=post action='{a['stop']}'><button class='big stop'>STOP</button>"
                     "<div class=k>blocks new positions; never blocks getting out</div></form>")
    else:
        parts.append(f"<form method=post action='{a['resume']}'>"
                     "<input type=password name=passphrase placeholder='vault passphrase' "
                     "autocomplete=current-password required>"
                     "<button class='big quiet'>clear STOP</button></form>")
    if state != "LOCKED":
        parts.append(f"<form method=post action='{a['flatten']}'>"
                     "<button class='big exit'>FLATTEN — close everything</button>"
                     "<div class=k>asks once more on the next page</div></form>")
        if state == "ARMED":
            parts.append(f"<form method=post action='{a['stand_down']}'>"
                         "<button class='big quiet'>stand down for the day</button></form>")
        parts.append(f"<form method=post action='{a['lock']}'>"
                     "<button class='big cancel'>lock — forget the credential</button></form>")

    # ── the day ──
    rows = [
        ("open positions", day["open_positions"]),
        ("realized loss", f"${day['realized_loss_usd']:.2f}"),
        ("headroom to the ceiling", f"${day['loss_headroom_usd']:.2f}"),
        ("attempts", f"{day['attempts_used']} used, {day['attempts_left']} left"),
    ]
    parts.append("<h2>Today</h2><div class=card><table>" + "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(str(v))}</td></tr>" for k, v in rows)
        + "</table></div>")
    if st["positions"] or st["working"]:
        lines = [json.dumps(p, separators=(",", ":")) for p in st["positions"]]
        lines += ["working " + json.dumps(w, separators=(",", ":")) for w in st["working"]]
        parts.append("<div class=card><pre>" + esc("\n".join(lines)) + "</pre></div>")

    # ── credentials ──
    cred = st.get("credential") or {}
    trading_line = (_fmt_wall(cred.get("refresh_wall"), now) if cred.get("armed")
                    else esc(cred.get("detail") or "locked — unlock to see its wall"))
    mk = cred.get("market") or {}
    market_line = (_fmt_wall(mk.get("refresh_wall"), now) if mk.get("armed")
                   else esc(mk.get("detail") or "no market credential loaded"))
    parts.append("<h2>Schwab grants</h2><div class=card><table>"
                 f"<tr><td>trading app</td><td>{trading_line}</td></tr>"
                 f"<tr><td>market-data app</td><td>{market_line}</td></tr>"
                 f"<tr><td>vault</td><td>{'present' if vault.exists else 'MISSING'} — "
                 f"{esc(str(vault.path))}</td></tr></table></div>")
    parts.append(
        "<details><summary>re-authorise an app (weekly; do both in one sitting)</summary>"
        f"<div class=card><form method=post action='{a['reauth_link']}'>"
        "<label><input type=radio name=app value=trading checked> trading app</label> &nbsp; "
        "<label><input type=radio name=app value=market> market-data app</label>"
        "<input type=password name=passphrase placeholder='vault passphrase' "
        "autocomplete=current-password required style='margin-top:.5em'>"
        "<button class='big quiet'>show the login link</button></form></div></details>")

    # ── journal ──
    tail = service.journal.tail(12)
    if tail:
        lines = [f"{e.get('ts_ct', '')[11:19]} {e.get('event', '')} "
                 + " ".join(f"{k}={_short(v)}" for k, v in e.items()
                            if k not in ("ts", "ts_ct", "event", "sha"))
                 for e in reversed(tail)]
        parts.append("<h2>Journal, latest first</h2><div class=card><pre>"
                     + esc("\n".join(lines)) + "</pre></div>")
    parts.append(f"<div class=k>{esc(PAGE_URL)} · tailnet only</div>")
    return _page("execd", "".join(parts))


def _short(v: Any) -> str:
    s = json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else str(v)
    return s if len(s) <= 80 else s[:77] + "..."


def _render_confirm_flatten(service: ExecService, nonce: str, a: dict[str, str]) -> str:
    st = service.status()
    held = st["positions"]
    listing = ("<pre>" + esc("\n".join(json.dumps(p, separators=(",", ":")) for p in held))
               + "</pre>" if held else "<div class=k>the service is tracking no position; "
               "flatten still asks the broker and closes whatever it finds</div>")
    body = (f"<div class=card>{listing}</div>"
            f"<form method=post action='{a['flatten_confirm']}'>"
            f"<input type=hidden name=nonce value='{nonce}'>"
            f"<button class='big exit'>CONFIRM — FLATTEN</button></form>"
            f"<form method=get action='{a['index']}'><button class='big cancel'>cancel</button></form>"
            f"<div class=k>confirm window {int(CONFIRM_TTL_S)}s, single use</div>")
    return _page("FLATTEN — are you sure", body)


def _render_reauth(target: App, link: str, state: str, a: dict[str, str]) -> str:
    body = (
        f"<div class=card><div class=k>{esc(target.value)} app</div>"
        f"<ol><li>Open this link, log in to Schwab, approve the app:<br>"
        f"<a href='{esc(link)}' target=_blank rel=noopener>{esc(link)}</a></li>"
        f"<li>The page it lands on will not load — that is expected. Copy the whole "
        f"address from the address bar.</li>"
        f"<li>Paste it here <b>straight away</b> (the code dies within seconds) and enter "
        f"the passphrase again.</li></ol></div>"
        f"<form method=post action='{a['reauth_store']}'>"
        f"<input type=hidden name=state value='{state}'>"
        f"<textarea name=received_url rows=4 placeholder='https://127.0.0.1:8182/?code=...' "
        f"required></textarea>"
        f"<input type=password name=passphrase placeholder='vault passphrase' "
        f"autocomplete=current-password required style='margin-top:.5em'>"
        f"<button class='big arm'>store the new grant</button></form>"
        f"<form method=get action='{a['index']}'><button class='big cancel'>cancel</button></form>"
        f"<div class=k>link good for {int(REAUTH_TTL_S // 60)} minutes, single use</div>")
    return _page(f"re-authorise — {target.value}", body)
