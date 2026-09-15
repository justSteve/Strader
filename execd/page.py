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
from .intent import OrderIntent
from .orderform import PREVIEW_TTL_S, Selection, intent_for, price, stamp
from .orderpage import (fd0_html, journal_html, position_html, preview_fields_html, quote_html,
                        render_order, state_html, strikes_html, ticket_html)
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
    def home(msg: str | None = None, *, bad: bool = False, back: str | None = None):
        """After an account action: back to the account page — or to the
        trading page when the form said ``back=order`` (the strip's STOP and
        the panel's FLATTEN live there; st-shhi)."""
        target = "exec.order" if (back or request.form.get("back", "")) == "order" else "exec.account"
        if not msg:
            return redirect(url_for(target), code=303)
        return redirect(url_for(target, **{"bad" if bad else "msg": msg}), code=303)

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
        """The trading page (st-shhi, Steve 2026-09-15: stage and send with no
        agent in the loop; the account controls do not belong here)."""
        return _order_page(_selection(request.args), msg=request.args.get("msg"),
                           bad=request.args.get("bad"))

    @bp.get("/account")
    def account():
        """Arming, STOP/clear, stand down, lock, the weekly re-authorisation,
        the grants, the journal tail — everything that is not placing an order."""
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
        return _render_confirm_flatten(service, n, _actions(),
                                       back=request.form.get("back", ""))

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

    # ── the order form (stage 4, st-k6gl) — by code alone ─────────────
    def _today():
        return clock().astimezone(CT).date()

    def _selection(args) -> Selection:
        return Selection.from_args(args, today=_today(),
                                   lots_cap=service.bounds.qty_cap)

    def _order_page(sel: Selection, **kw):
        priced = price(service, sel) if sel.side else None
        embed = request.args.get("embed") == "1" or request.form.get("embed") == "1"
        fresh = request.args.get("new") == "1"
        return render_order(service, _actions(), sel, priced, today=_today(),
                            embed=embed, fresh=fresh, **kw)

    @bp.get("/order")
    def order():
        return _order_page(_selection(request.args), msg=request.args.get("msg"),
                           bad=request.args.get("bad"))

    @bp.get("/order/price")
    def order_price():
        sel = _selection(request.args)
        priced = price(service, sel)
        body = priced.to_dict()
        body["fd0_html"] = ticket_html(priced, service.bounds)
        body["strikes_html"] = strikes_html(priced, url_for("exec.order"))
        body["preview_fields_html"] = preview_fields_html(sel)
        return body

    @bp.get("/order/state")
    def order_state():
        st = service.status()
        symbol = request.args.get("symbol") or ""
        quote = None
        error = None
        spx = None
        if symbol:
            try:
                quote = service.quote(symbol).to_dict()
                spx = service.spx_mark()
            except BrokerError as exc:
                error = str(exc)
        from .panel import panel_body
        stage, body = panel_body(service, st, _actions(), now=clock(),
                                 order_path=url_for("exec.order"))
        return {"mode": st["mode"], "arming": st["arming"], "day": st["day"],
                "pnl": st.get("pnl"), "positions": st["positions"],
                "working": st["working"],
                "quote": quote, "spx": spx,
                "quote_html": quote_html(quote, spx, error),
                "position_html": position_html(st, _actions()),
                "state_html": state_html(st, _actions(), now=clock()),
                "journal_html": journal_html(service),
                # the status panel (st-4ezg): the stage and the card's body
                "panel_stage": stage, "panel_body_html": body}

    @bp.post("/order/preview")
    def order_preview():
        sel = _selection(request.form)
        priced = price(service, sel)
        try:
            intent = intent_for(priced, intent_id=f"page-{stamp(clock())}",
                                engine_sha=service.config.sha)
        except ValueError as exc:
            return _order_page(sel, bad=f"Not previewed: {exc}")
        try:
            out = service.preview(OrderIntent.from_dict(intent))
        except Refused as exc:
            return _order_page(sel, bad=f"Refused ({exc.refusal.bound}): {exc.refusal.reason}. Nothing sent.")
        except BrokerError as exc:
            return _order_page(sel, bad=f"The broker could not be reached: {exc}. Nothing sent.")
        except ValueError as exc:
            return _order_page(sel, bad=f"Not previewed: {exc}")
        if out.get("refused"):
            r = out["refused"]
            text = f"Refused ({r.get('bound')}): {r.get('reason')}. Nothing sent."
            return _order_page(sel, bad=text)
        p = out["preview"]
        word = "PAPER (simulated) — " if out.get("mode") == "paper" else ""
        text = (f"{word}Preview from Schwab: {str(p.get('symbol', '')).strip()} x{p.get('qty')} "
                f"at {float(p.get('price') or 0):.2f} — cost ${float(p.get('cost_usd') or 0):.2f}, "
                f"commission ${float(p.get('commission_usd') or 0):.2f}, total "
                f"${float(p.get('total_usd') or 0):.2f}; "
                + ("the broker accepts it." if p.get("accepted") else "the broker would REJECT it: "
                   + "; ".join(p.get("messages") or [])))
        nonce = nonces.issue("send", PREVIEW_TTL_S, intent=intent, query=sel.as_query())
        return _order_page(sel, nonce=nonce, preview=out, preview_text=text)

    @bp.post("/order/send")
    def order_send():
        item = nonces.spend(request.form.get("nonce", ""), "send")
        if item is None:
            return redirect(url_for("exec.order", bad=f"That SEND was used already or is older "
                                    f"than {int(PREVIEW_TTL_S)} s — preview again."), code=303)
        intent = item.extra.get("intent") or {}
        try:
            out = service.place(OrderIntent.from_dict(intent),
                                page_query=item.extra.get("query") or None)
        except Refused as exc:
            return redirect(url_for("exec.order", bad=f"Refused ({exc.refusal.bound}): "
                                    f"{exc.refusal.reason}. Nothing sent."), code=303)
        except BrokerError as exc:
            return redirect(url_for("exec.order", bad=f"The broker could not be reached: {exc}. "
                                    f"Nothing was sent that the service knows of — check the "
                                    f"orders before sending again."), code=303)
        except ValueError as exc:
            return redirect(url_for("exec.order", bad=f"Not sent: {exc}"), code=303)
        if out.get("refused"):
            # A refusal the service answered (a bound, or the broker's own
            # preview saying no) is the red box and the REFUSED stage — not a
            # green message. 2026-09-15 09:54 CT: Schwab refused a send for
            # buying power and the page showed Steve nothing.
            return redirect(url_for("exec.order", bad=_describe_place(out)), code=303)
        return redirect(url_for("exec.order", msg=_describe_place(out)), code=303)

    # ── the bracket's live editor and the working entry's cancel (st-fn5y) ──
    @bp.post("/order/adjust")
    def order_adjust():
        """UPDATE on the position card: both trigger conditions, one button.
        Steve, 2026-09-14: "a live editor allowing an update to both"."""
        symbol = request.form.get("symbol", "")
        try:
            stop = _form_price("stop_price")
            target = _form_price("target_price")
            if stop is None and target is None:
                return redirect(url_for("exec.order", bad="Nothing to update: enter a stop, "
                                        "a target, or both."), code=303)
            out = service.adjust(symbol, stop_price=stop, target_price=target)
        except Refused as exc:
            return redirect(url_for("exec.order", bad=f"Refused ({exc.refusal.bound}): "
                                    f"{exc.refusal.reason}. Nothing changed."), code=303)
        except BrokerError as exc:
            return redirect(url_for("exec.order", bad=f"The broker could not be reached: {exc}. "
                                    f"Read the position card before trying again."), code=303)
        except ValueError as exc:
            return redirect(url_for("exec.order", bad=f"Not updated: {exc}"), code=303)
        if out.get("refused"):
            r = out["refused"]
            return redirect(url_for("exec.order", bad=f"Refused ({r.get('bound')}): "
                                    f"{r.get('reason')}."), code=303)
        return redirect(url_for("exec.order", msg=_describe_adjust(out)), code=303)

    @bp.post("/order/cancel")
    def order_cancel():
        """CANCEL AND RE-PRICE on the working-entry card. Steve, 2026-09-14:
        "assume the canceled order will be re-priced and re-armed" — so the
        form comes back with the selection the entry was priced from."""
        order_id = request.form.get("order_id", "")
        query: dict[str, str] = {}
        for w in service.status()["working"]:
            if w.get("order_id") == order_id and isinstance(w.get("page_query"), dict):
                query = {str(k): str(v) for k, v in w["page_query"].items()}
        try:
            service.cancel(order_id)
        except Refused as exc:
            return redirect(url_for("exec.order", bad=f"Refused ({exc.refusal.bound}): "
                                    f"{exc.refusal.reason}. Nothing changed."), code=303)
        except BrokerError as exc:
            return redirect(url_for("exec.order", bad=f"The broker could not be reached: {exc}. "
                                    f"Nothing cancelled that the service knows of."), code=303)
        except ValueError as exc:
            return redirect(url_for("exec.order", bad=f"Not cancelled: {exc}"), code=303)
        return redirect(url_for("exec.order", **query, msg=f"Cancelled {order_id}."), code=303)

    def _form_price(name: str) -> float | None:
        raw = (request.form.get(name) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"{name.replace('_', ' ')} must be a number, not {raw!r}") from None

    def _actions() -> dict[str, str]:
        """Absolute paths for every form, so a page served at ``/exec/flatten``
        posts its confirm to ``/exec/flatten/confirm`` and not to a sibling."""
        return {name: url_for(f"exec.{name}") for name in (
            "index", "account", "unlock", "stop", "resume", "stand_down", "lock", "flatten",
            "flatten_confirm", "reauth_link", "reauth_store",
            "order", "order_price", "order_state", "order_preview", "order_send",
            "order_adjust", "order_cancel")}

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
 .pos-up{border-left:6px solid #34d399}.pos-down{border-left:6px solid #f87171}
 td.neg{color:#f87171;font-weight:700}td.pos{color:#34d399;font-weight:700}
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
 .bracket{display:grid;grid-template-columns:1fr 1fr;gap:.6em;margin:.6em 0 0}
 .bracket label{display:block;color:#9ca3af;font-size:.9em}
 .bracket input{width:100%;box-sizing:border-box;font-size:1.1em;padding:.6em;border-radius:8px;
      border:1px solid #374151;background:#0b1020;color:#e5e7eb}
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


def _page(title: str, body: str, *, refresh_s: int | None = None) -> str:
    # The page reloads itself only while there is money moving on it — a
    # position or a working entry — so the unrealized P&L is live and a
    # passphrase being typed on a quiet page is never wiped.
    meta = f"<meta http-equiv=refresh content={int(refresh_s)}>" if refresh_s else ""
    return (f"<!doctype html><html><head><meta charset=utf-8><title>{esc(title)}</title>"
            f"{meta}{_STYLE}</head><body><h1>{esc(title)}</h1>{body}</body></html>")


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
    parts.append(f"<form method=get action='{a['order']}'>"
                 "<button class='big quiet'>← trade</button></form>")

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

    # ── the position, with its money ──
    for p in st["positions"]:
        parts.append(_render_position(p))
    parts.append(_render_not_this_services(st))

    # ── the day ──
    pnl = st.get("pnl") or {}
    rows = [
        ("open positions", day["open_positions"]),
        ("realized today", f"{_money(pnl.get('realized_usd'))} over {pnl.get('closes', 0)} close(s)"),
        ("unrealized, net if closed now", _money(pnl.get("unrealized_net_usd"))),
        ("day, realized + unrealized", _money(pnl.get("day_usd"))),
        # Signed and red when there is one: "$40.00" read as a gain (Steve,
        # 2026-09-14); a loss against the ceiling is "-$40.00" in red.
        ("realized loss against the ceiling",
         _money(-day["realized_loss_usd"]) if day["realized_loss_usd"] else "$0.00"),
        ("headroom to the ceiling", f"${day['loss_headroom_usd']:.2f}"),
        ("attempts", f"{day['attempts_used']} used, {day['attempts_left']} left"),
    ]
    parts.append("<h2>Today</h2><div class=card><table>" + "".join(
        f"<tr><td>{esc(k)}</td><td{_money_class(v)}>{esc(str(v))}</td></tr>" for k, v in rows)
        + "</table></div>")
    if st["working"]:
        lines = ["working " + json.dumps(w, separators=(",", ":")) for w in st["working"]]
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
    live_money = bool(st["positions"] or st["working"])
    return _page("execd", "".join(parts), refresh_s=5 if live_money else None)


def _describe_place(out: dict[str, Any]) -> str:
    """The service's answer to a send, in plain words — the desk's wording,
    kept here because the installed service has no ``strader/``."""
    word = "PAPER (simulated) — " if out.get("mode") == "paper" else ""
    if out.get("refused"):
        r = out["refused"]
        return f"{word}Refused ({r.get('bound')}): {r.get('reason')}. Nothing sent."
    o = out.get("order") or {}
    oid = o.get("order_id")
    if out.get("replayed"):
        return f"{word}Already sent under this id — order {oid}, {o.get('status')}. Nothing new sent."
    status = str(o.get("status", ""))
    if status == "REJECTED":
        return f"{word}Sent, and the broker REJECTED it (order {oid}): {o.get('message') or 'no reason given'}."
    if status == "FILLED" or o.get("filled_qty"):
        fill = float(o.get("fill_price") or 0)
        qty = int(o.get("filled_qty") or o.get("qty") or 0)
        head = f"{word}SENT AND FILLED: order {oid}, {qty} at {fill:.2f} (${fill * 100 * qty:.2f})."
        stop = out.get("stop_order")
        target = out.get("target_order")
        if isinstance(target, dict) and target.get("closed"):
            c = target["closed"]
            tail = (f" The take-profit filled the moment it landed at "
                    f"{float(c.get('exit_price') or 0):.2f} — the position is closed "
                    f"({_money(c.get('pnl_usd'))}).")
        elif isinstance(target, dict) and target.get("order_id"):
            tail = (f" Take-profit resting: order {target['order_id']} at "
                    f"{float(target.get('price') or 0):.2f}.")
        else:
            tail = " No take-profit rested — the journal says why."
        if isinstance(stop, dict) and stop.get("order_id"):
            return head + (f" Protective stop resting: order {stop['order_id']} at "
                           f"{float(stop.get('price') or 0):.2f}.") + tail + \
                " The service watches the SPX mark."
        return head + " ** NO PROTECTIVE STOP RESTED — FLATTEN if in doubt." + tail
    return (f"{word}SENT: order {oid} is {status} at the broker, not filled yet; "
            f"the bracket rests when it fills.")


def _describe_adjust(out: dict[str, Any]) -> str:
    """The service's answer to an UPDATE, in plain words."""
    word = "PAPER (simulated) — " if out.get("mode") == "paper" else ""
    parts: list[str] = []
    for leg, name in (("stop", "Stop"), ("target", "Target")):
        r = out.get(leg)
        if not isinstance(r, dict):
            continue
        if r.get("moved"):
            line = f"{name} moved from {float(r.get('old_price') or 0):.2f} to {float(r['new_price']):.2f}"
            if leg == "stop" and r.get("stop_spx") is not None:
                line += f" (SPX cut level now {float(r['stop_spx']):.2f})"
            parts.append(line + ".")
        else:
            parts.append(f"{name} NOT moved: {r.get('error') or 'no reason given'}.")
    return word + (" ".join(parts) if parts else "Nothing changed.")


def _money_class(v: Any) -> str:
    """`` class=neg`` / `` class=pos`` for a rendered money string, so a loss
    is red and a gain green wherever one is shown; nothing for the rest."""
    s = str(v)
    if s.startswith("-$"):
        return " class=neg"
    if s.startswith("+$"):
        return " class=pos"
    return ""


def _money(v: Any) -> str:
    """``+$50.00`` / ``-$11.30`` / ``—`` when the quote could not be read."""
    if not isinstance(v, (int, float)):
        return "—"
    sign = "+" if v > 0 else ("-" if v < 0 else "")
    return f"{sign}${abs(v):,.2f}"


def _render_position(p: dict[str, Any], adjust_action: str | None = None) -> str:
    """One open position: the contract, the entry, the live bid and ask, and
    every part of the money — cost, value at the bid, unrealized, both
    commissions, the net if closed now, the net at the stop and at the
    target. With ``adjust_action``, the bracket's live editor: two inputs
    pre-filled with the resting prices and one UPDATE button (st-fn5y)."""
    v = p.get("valuation") or {}
    qty = p["qty"]
    sym = str(p["symbol"]).strip()
    rows = [
        ("contract", f"{sym} × {qty}"),
        ("entry", f"{p['entry_price']:.2f} → cost ${v.get('cost_usd', 0):,.2f}"),
    ]
    if v.get("bid") is not None:
        rows.append(("now", f"bid {v['bid']:.2f} / ask {v['ask']:.2f} "
                            f"(quote {v.get('quote_age_s', 0):.0f}s old)"))
        rows.append(("value at the bid", f"${v['value_usd']:,.2f}"))
        rows.append(("unrealized, before commissions", _money(v["unrealized_usd"])))
    else:
        rows.append(("now", f"no quote — {v.get('error') or 'unknown'}"))
    rows.append(("commissions, in and out",
                 f"${v.get('commissions_usd', 0):.2f} "
                 f"(entry ${v.get('entry_commission_usd', 0):.2f}, "
                 f"exit ${v.get('exit_commission_usd', 0):.2f})"))
    rows.append(("NET IF CLOSED NOW", _money(v.get("net_if_closed_usd"))))
    if p.get("stop_price") is not None:
        rows.append(("at the stop", f"stop {p['stop_price']:.2f} → net {_money(v.get('at_stop_usd'))}"
                     + (f" (order {p['stop_order_id']})" if p.get("stop_order_id") else " (NO STOP RESTING)")))
    else:
        rows.append(("at the stop", "NO STOP — the position is unprotected"))
    if p.get("target_price") is not None:
        rows.append(("at the target", f"target {p['target_price']:.2f} → net {_money(v.get('at_target_usd'))}"
                     + (f" (order {p['target_order_id']})" if p.get("target_order_id") else " (NO TARGET RESTING)")))
    else:
        rows.append(("at the target", "NO TARGET — the journal says why"))
    if p.get("stop_spx") is not None:
        rows.append(("SPX cut level", f"{p['stop_spx']:.2f}"))
    if p.get("exit_order_id"):
        rows.append(("exit in flight", f"order {p['exit_order_id']} ({p.get('exit_reason')})"))
    cls = "pos-up" if isinstance(v.get("net_if_closed_usd"), (int, float)) and v["net_if_closed_usd"] >= 0 else "pos-down"
    html = (f"<h2>Open position</h2><div class='card {cls}'><table>" + "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(str(val))}</td></tr>" for k, val in rows)
        + "</table>")
    if adjust_action and not p.get("exit_order_id"):
        stop_val = f"{p['stop_price']:.2f}" if p.get("stop_price") is not None else ""
        target_val = f"{p['target_price']:.2f}" if p.get("target_price") is not None else ""
        html += (f"<form method=post action='{adjust_action}' class=adjust>"
                 f"<input type=hidden name=symbol value='{esc(p['symbol'])}'>"
                 "<div class=bracket>"
                 f"<label>stop<input name=stop_price inputmode=decimal value='{stop_val}'></label>"
                 f"<label>target<input name=target_price inputmode=decimal value='{target_val}'></label>"
                 "</div><button class='big quiet'>UPDATE</button></form>")
    return html + "</div>"


def _short(v: Any) -> str:
    s = json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else str(v)
    return s if len(s) <= 80 else s[:77] + "..."


def _render_not_this_services(st: dict[str, Any]) -> str:
    """What the account holds that this service does not own — Steve's own
    legs, a short, a bracket leg left behind, a send with no answer, a buy it
    did not place. Each is a line here until it is gone; none is a button
    (2026-09-15 audit, st-isx3 / st-7ah8 / st-xlz9)."""
    lines: list[str] = []
    for p in st.get("foreign_positions") or []:
        lines.append(f"{esc(p['symbol'].strip())} × {p['qty']} at {float(p['avg_price']):.2f} — "
                     "held in the account, not opened here; not counted, not flattened")
    for s in st.get("shorts") or []:
        lines.append(f"<b>SHORT {esc(s['symbol'].strip())} × {abs(int(s['qty']))}</b> — this "
                     "service only sells to close; buy it back by hand")
    for leg in st.get("loose_legs") or []:
        lines.append(f"{esc(leg['leg'])} {esc(leg['order_id'])} on {esc(leg['symbol'].strip())} — "
                     "its position is closed and its cancel is not confirmed; asking again")
    for s in st.get("unconfirmed_sends") or []:
        lines.append(f"send {esc(s['intent_id'])} on {esc(s['symbol'].strip())} — no answer from "
                     "the broker; nothing else goes out until the listing accounts for it")
    for o in st.get("foreign_orders") or []:
        lines.append(f"working buy {esc(o.get('order_id', ''))} on {esc(str(o.get('symbol', '')).strip())} "
                     f"× {o.get('qty')} — not sent by this service")
    excluded = st.get("excluded_positions") or {}
    if excluded:
        lines.append("also in the account, not this service's instruments: "
                     + ", ".join(f"{n} {esc(k.lower())}" for k, n in sorted(excluded.items())))
    if not lines:
        return ""
    return ("<div class=card><div class=k>in the account, not this service's</div>"
            + "".join(f"<div class=row>{ln}</div>" for ln in lines) + "</div>")


def _render_confirm_flatten(service: ExecService, nonce: str, a: dict[str, str],
                            back: str = "") -> str:
    st = service.status()
    held = st["positions"]
    if held:
        rows = "".join(f"<div class=row><b>SELL {esc(p['symbol'].strip())} × {p['qty']}</b> at market"
                       f" — in at {float(p['entry_price']):.2f}</div>" for p in held)
        listing = f"<div class=k>this will sell</div>{rows}"
    else:
        listing = ("<div class=k>the service is tracking no position of its own; flatten "
                   "asks the broker first and closes what it finds under this service's "
                   "name</div>")
    spared = [f"{esc(p['symbol'].strip())} × {p['qty']}" for p in st.get("foreign_positions") or []]
    if spared:
        listing += ("<div class=k>this will NOT sell — held in the account, not opened here: "
                    + ", ".join(spared) + "</div>")
    back_field = "<input type=hidden name=back value='order'>" if back == "order" else ""
    body = (f"<div class=card>{listing}</div>"
            f"<form method=post action='{a['flatten_confirm']}'>"
            f"<input type=hidden name=nonce value='{nonce}'>{back_field}"
            f"<button class='big exit'>CONFIRM — FLATTEN</button></form>"
            f"<form method=get action='{a['order'] if back == 'order' else a['account']}'>"
            "<button class='big cancel'>cancel</button></form>"
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
