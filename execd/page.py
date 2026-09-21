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
from .orderform import (SEND_NONCE_TTL_S, Selection, intent_for, limit_at, parse_leg_text, price,
                        stamp)
from .orderpage import (balances_html, journal_html, position_html, send_fields_html,
                        quote_html, render_order, state_html, strikes_html, ticket_html)
from .service import CONTRACT_MULTIPLIER, ExecService, Refused
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
        self._stamp: tuple[int, int, int] | None = None

    def _stamp_now(self) -> tuple[int, int, int] | None:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    def load(self) -> dict[str, Any]:
        stamp = self._stamp_now()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        Credential.from_payload(raw)      # shape-checked here, not on the first quote
        with self._lock:
            self._payload = raw
            self._stamp = stamp
        return raw

    def current(self) -> dict[str, Any]:
        """What the transport calls on every market read.

        Re-read when the file has moved underneath us. Holding the credential
        in memory is the point — the transport asks on every call and must not
        touch disk for the value — but a process that could not notice the file
        had changed went on presenting a grant that was seven days dead while
        ``reauthData`` reported success, and only a restart cleared it
        (2026-09-21). One ``stat`` per market call; the file is parsed again
        only when the stamp moves, and a file caught mid-replace leaves the
        working copy in place rather than taking the service down. [st-bd2g]"""
        with self._lock:
            stamp = self._stamp_now()
            if stamp is not None and stamp != self._stamp:
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    Credential.from_payload(raw)
                except (OSError, ValueError):
                    pass              # keep what works; the stamp stays unclaimed
                else:
                    self._payload, self._stamp = raw, stamp
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
                state_dir: str | Path | None = None,
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

    @bp.before_request
    def from_this_page_only():
        """Every state-changing post must come from this page. The API's rule
        (``_require_json``, finding 15 of the 2026-08-30 audit) applied to the
        page, whose routes are form posts by design: a form auto-submitted by
        any other page rendered in a browser on the tailnet reached
        ``/exec/order/adjust`` and moved the protective stop with no
        passphrase, no nonce and no origin check (audit finding 36, st-sk9r).
        ``Sec-Fetch-Site: same-origin`` is what every browser he uses sends
        with a form posted from this page; a browser that does not send it
        must say the same with ``Origin``. STOP is exempt, as on the API: a
        hostile page firing it can only stop new risk, and his phone reaching
        it must not depend on a header."""
        if request.method != "POST" or request.endpoint == "exec.stop":
            return None
        why = _not_from_this_page(request)
        if why is None:
            return None
        service.journal.record("refused", kind="cross-site", path=request.path,
                               refused={"bound": "origin", "reason": why})
        return _page("Not from this page",
                     f"<div class=card><div class=bad>{esc(why)}</div>"
                     "<div class=k>Nothing changed.</div></div>"), 403

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
            payload = trading_payload(open_vault(pw), state_dir)
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
        # LOCKED refuses exits and the watcher skips: with a position live,
        # one tap here would strand him with only the broker's stop until he
        # types the passphrase. So while anything is held or working, LOCK
        # confirms the way FLATTEN does (audit finding 36, st-sk9r); flat, it
        # is the one tap it always was.
        if service.has_exposure():
            n = nonces.issue("lock", CONFIRM_TTL_S)
            return _render_confirm_lock(service, n, _actions(),
                                        back=request.form.get("back", ""))
        service.lock()
        return home("Locked. The credential is out of memory; the passphrase brings it back.")

    @bp.post("/lock/confirm")
    def lock_confirm():
        if nonces.spend(request.form.get("nonce", ""), "lock") is None:
            return home(f"That LOCK confirm was used already or is older than "
                        f"{int(CONFIRM_TTL_S)} seconds. Still armed.", bad=True)
        service.lock()
        return home("Locked with a position live. The SPX-mark exit is off until you "
                    "unlock; the stop resting at the broker is the protection.")

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
        # the SEND token rides with the ticket, single use (st-igw0)
        send_nonce = (nonces.issue("send", SEND_NONCE_TTL_S)
                      if priced is not None and priced.ready else None)
        return render_order(service, _actions(), sel, priced, today=_today(),
                            embed=embed, fresh=fresh, send_nonce=send_nonce, **kw)

    @bp.get("/order")
    def order():
        return _order_page(_selection(request.args), msg=request.args.get("msg"),
                           bad=request.args.get("bad"))

    @bp.get("/order/price")
    def order_price():
        sel = _selection(request.args)
        priced = price(service, sel)
        body = priced.to_dict()
        balances = service.status().get("balances")
        body["fd0_html"] = ticket_html(priced, service.bounds, balances)
        # the strikes the account can pay for, the same filter the poll uses
        body["strikes_html"] = strikes_html(priced, url_for("exec.order"), balances)
        body["send_fields_html"] = send_fields_html(sel)
        return body

    @bp.get("/order/state")
    def order_state():
        sel = _selection(request.args)
        return _state_payload(request.args.get("symbol") or "", request.args.get("lots"),
                              sel=sel if sel.side else None)

    def _state_payload(symbol: str, lots_arg: Any, *, refused: str | None = None,
                       sel: Selection | None = None) -> dict[str, Any]:
        """The status body's live half plus the chosen contract's quote, with
        the HTML fragments the page's script paints — what the poll reads,
        and what an in-place adjust answers with (st-bmaz).

        When the caller carries a selection (the trading page's poll does,
        st-644f), the ticket is priced here from one bounded chain read and
        the answer carries the whole ticket, the strikes and SEND's hidden
        fields. That is what makes the loaded strike follow the market
        without a tap — Steve, 2026-09-18, "include real-time price updates
        on the strike that is loaded (auto-reprice)" — and it costs one
        market read where the quote-only answer cost two, because the chain
        body carries the underlying's price with it. Without a selection
        (the operations page) nothing changes.

        **While an entry is working the broker is asked first** (st-jdg5).
        The status body is what this service BELIEVES, and belief lags: the
        watcher reconciles every 5 s and this poll paints every 3 s, so a fill
        Schwab made can sit unseen for about eight seconds — during which the
        screen says "not filled yet" and CANCEL is a tap aimed at an order
        that is already gone. The paper book hides this completely, because it
        has no clock and only fills when it is read. One reconcile per poll,
        and only while something is actually working, buys the screen the
        broker's own truth for the seconds when it decides what he taps."""
        if service.has_working():
            service.reconcile()          # reports a broker failure, never raises
        st = service.status()
        quote = None
        error = None
        spx = None
        limit_now = None
        cost_now = None
        extra: dict[str, Any] = {}
        priced = price(service, sel) if sel is not None and sel.side else None
        if priced is not None:
            spx = priced.spx or None
            c = priced.contract
            if c is not None:
                quote = {"symbol": c.symbol, "bid": c.bid_pts, "ask": c.ask_pts,
                         "mid": round((c.bid_pts + c.ask_pts) / 2, 4), "last": None,
                         "age_s": 0.0}
                limit_now = limit_at(c.ask_pts)
                cost_now = _money(-(limit_now * CONTRACT_MULTIPLIER * priced.lots)).lstrip("-")
            error = priced.error
            extra = {
                "fd0_html": ticket_html(priced, service.bounds, st.get("balances")),
                "strikes_html": strikes_html(priced, url_for("exec.order"),
                                             st.get("balances")),
                "send_fields_html": send_fields_html(sel),
                "contract": priced.to_dict().get("contract"),
                "stop_price": priced.stop_price,
            }
        elif symbol:
            try:
                q = service.quote(symbol)
                quote = q.to_dict()
                spx = service.spx_mark()
                # the number the ticket's head follows while unlocked (st-2s4u):
                # the ask on the tick grid, and what that costs — Python's
                # arithmetic, the script only writes the text
                if q.ask:
                    lots = Selection.from_args({"lots": lots_arg},
                                               today=_today(), lots_cap=service.bounds.qty_cap).lots
                    limit_now = limit_at(q.ask)
                    cost_now = _money(-(limit_now * CONTRACT_MULTIPLIER * lots)).lstrip("-")
            except BrokerError as exc:
                error = str(exc)
        from .panel import journal_facts, panel_body
        stage, body = panel_body(service, st, _actions(), now=clock(),
                                 order_path=url_for("exec.order"), refused=refused)
        last_close = journal_facts(service).get("last_close") or {}
        return {"mode": st["mode"], "arming": st["arming"], "day": st["day"],
                # the stamp of the day's last close, so a card NEW ORDER
                # dismissed stays dismissed under the poll (st-igw0)
                "last_close_ts": last_close.get("ts"),
                "pnl": st.get("pnl"), "positions": st["positions"],
                "working": st["working"],
                "quote": quote, "spx": spx,
                "limit_now": limit_now, "cost_now": cost_now,
                "quote_html": quote_html(quote, spx, error),
                "position_html": position_html(st, _actions()),
                "state_html": state_html(st, _actions(), now=clock()),
                "journal_html": journal_html(service),
                "balances_html": balances_html(st.get("balances")),
                # the status panel (st-4ezg): the stage and the card's body
                "panel_stage": stage, "panel_body_html": body,
                # the ticket, the strikes and SEND's fields when the caller
                # carried a selection to price (st-644f)
                **extra}

    #: The outcome of every SEND this process has answered, by its token —
    #: so a replay of a spent token (the browser or the proxy re-sending
    #: after a lost response, seen 2026-09-15 14:07 CT on an adjust) is
    #: answered with what happened, never sent twice (st-igw0).
    sent_outcomes: dict[str, dict[str, Any]] = {}

    @bp.post("/order/send")
    def order_send():
        """SEND — the ticket's one action (Steve, 2026-09-16: "I want to
        remove the preview step as well. anything we can do to shorten the
        submission after the decision has been made"). The form carries the
        selection and a single-use token issued with the page; the ticket is
        priced at this moment (the locked price or the ask) and placed; the
        service runs the broker's own preview inside the place. Answers JSON
        in place when asked (``ajax=1`` / Accept), else redirects."""
        wants_json = (request.form.get("ajax") == "1"
                      or "application/json" in (request.headers.get("Accept") or ""))
        token = request.form.get("nonce", "")
        sel = _selection(request.form)

        def answer(msg: str | None, bad: str | None, *, replayed: bool = False):
            if wants_json:
                return {"ok": bad is None, "msg": msg, "bad": bad, "replayed": replayed,
                        "send_nonce": nonces.issue("send", SEND_NONCE_TTL_S),
                        **_state_payload(sel_symbol(sel), request.form.get("lots"),
                                         refused=bad, sel=sel if sel.side else None)}
            if bad:
                return redirect(url_for("exec.order", bad=bad), code=303)
            return redirect(url_for("exec.order", msg=msg), code=303)

        if nonces.spend(token, "send") is None:
            done = sent_outcomes.get(token)
            if done is not None:
                return answer(done.get("msg"), done.get("bad"), replayed=True)
            return answer(None, f"That SEND was used already or is older than "
                                f"{int(SEND_NONCE_TTL_S // 3600)} h — reload the page and send again.")
        msg = bad = None
        try:
            priced = price(service, sel)
            intent = intent_for(priced, intent_id=f"page-{stamp(clock())}-{token[:6]}",
                                engine_sha=service.config.sha)
            out = service.place(OrderIntent.from_dict(intent), page_query=sel.as_query())
            if out.get("refused"):
                # A refusal the service answered (a bound, or the broker's own
                # preview saying no) is the red box and the REFUSED stage — not a
                # green message. 2026-09-15 09:54 CT: Schwab refused a send for
                # buying power and the page showed Steve nothing.
                bad = _describe_place(out)
            else:
                msg = _describe_place(out)
        except Refused as exc:
            bad = f"Refused ({exc.refusal.bound}): {exc.refusal.reason}. Nothing sent."
        except BrokerError as exc:
            bad = (f"The broker could not be reached: {exc}. Nothing was sent that the "
                   f"service knows of — check the orders before sending again.")
        except ValueError as exc:
            bad = f"Not sent: {exc}"
        sent_outcomes[token] = {"msg": msg, "bad": bad}
        if len(sent_outcomes) > 500:
            for k in list(sent_outcomes)[:-250]:
                sent_outcomes.pop(k, None)
        return answer(msg, bad)

    def sel_symbol(sel: Selection) -> str:
        """The chosen contract's symbol for the state payload's quote, or
        nothing — a send that refused before pricing has none."""
        try:
            priced = price(service, sel) if sel.side else None
        except Exception:  # pricing is for the quote line only here
            return ""
        return priced.contract.symbol if priced is not None and priced.contract is not None else ""

    # ── the bracket's live editor and the working entry's cancel (st-fn5y) ──
    @bp.post("/order/adjust")
    def order_adjust():
        """SET on the position card: the stop or the target, one leg per
        form, Enter sends it (Steve, 2026-09-15: "It'll be one or the other
        … just hit enter to submit", st-bmaz; before that one UPDATE for
        both, 2026-09-14). Answers JSON — the outcome in words plus the
        state payload the poll paints — when the form says ``ajax=1`` or the
        request accepts JSON; otherwise the redirect the plain form needs."""
        symbol = request.form.get("symbol", "")
        wants_json = (request.form.get("ajax") == "1"
                      or "application/json" in (request.headers.get("Accept") or ""))
        msg = bad = None
        try:
            # The box takes either form (st-2j3m). Steve's rule, 2026-09-16:
            # a value with a '.' is a dollar price (10.30); one without is an
            # SPX level (7585). ``stop_price`` / ``target_price`` stay dollars
            # for a caller that names the form.
            legs: dict[str, float | None] = {"stop_price": _form_price("stop_price"),
                                             "target_price": _form_price("target_price"),
                                             "stop_spx": None, "target_spx": None}
            for leg in ("stop", "target"):
                parsed = _form_leg(leg)
                if parsed is not None:
                    legs[f"{leg}_{parsed[0]}"] = parsed[1]
            if all(v is None for v in legs.values()):
                bad = "Nothing to update: enter a stop or a target."
            else:
                out = service.adjust(symbol, **legs)
                if out.get("refused"):
                    r = out["refused"]
                    bad = f"Refused ({r.get('bound')}): {r.get('reason')}."
                else:
                    msg = _describe_adjust(out)
        except Refused as exc:
            bad = f"Refused ({exc.refusal.bound}): {exc.refusal.reason}. Nothing changed."
        except BrokerError as exc:
            bad = (f"The broker could not be reached: {exc}. Read the position card "
                   f"before trying again.")
        except ValueError as exc:
            bad = f"Not updated: {exc}"
        if wants_json:
            return {"ok": bad is None, "msg": msg, "bad": bad,
                    **_state_payload(symbol, request.form.get("lots"))}
        if bad:
            return redirect(url_for("exec.order", bad=bad), code=303)
        return redirect(url_for("exec.order", msg=msg), code=303)

    @bp.post("/order/cancel")
    def order_cancel():
        """CANCEL AND RE-PRICE on the working-entry card. Steve, 2026-09-14:
        "assume the canceled order will be re-priced and re-armed" — so the
        form comes back with the selection the entry was priced from."""
        order_id = request.form.get("order_id", "")
        query: dict[str, str] = {}
        for w in service.status()["working"]:
            if w.get("order_id") == order_id and isinstance(w.get("page_query"), dict):
                # the form comes back at the market, not at the price that
                # did not fill: a lock never rides on a cancel (st-2s4u)
                query = {str(k): str(v) for k, v in w["page_query"].items() if k != "limit"}
        try:
            out = service.cancel(order_id)
        except Refused as exc:
            return redirect(url_for("exec.order", bad=f"Refused ({exc.refusal.bound}): "
                                    f"{exc.refusal.reason}. Nothing changed."), code=303)
        except BrokerError as exc:
            return redirect(url_for("exec.order", bad=f"The broker could not be reached: {exc}. "
                                    f"Nothing cancelled that the service knows of."), code=303)
        except ValueError as exc:
            return redirect(url_for("exec.order", bad=f"Not cancelled: {exc}"), code=303)
        # Only a cancel the broker CONFIRMED brings the form back priced for
        # another go. The other two answers leave the selection alone, because
        # re-priming the form beside an order that can still fill is how one
        # order becomes two (st-jdg5).
        if out.get("filled"):
            return redirect(url_for("exec.order", bad=(
                f"Too late — {order_id} filled before the cancel reached the broker. "
                f"The position is open and its stop and target are resting. "
                f"Use the card to get out.")), code=303)
        if not out.get("confirmed", True):
            status = str((out.get("order") or {}).get("status", "working"))
            return redirect(url_for("exec.order", bad=(
                f"Not confirmed — the broker took the cancel and still holds {order_id} "
                f"({status}). It can still fill. Nothing was re-priced; watch the card "
                f"and ask again if it is still there.")), code=303)
        return redirect(url_for("exec.order", **query, msg=f"Cancelled {order_id}."), code=303)

    def _form_price(name: str) -> float | None:
        raw = (request.form.get(name) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"{name.replace('_', ' ')} must be a number, not {raw!r}") from None

    def _form_leg(leg: str) -> tuple[str, float] | None:
        """The ``stop`` / ``target`` box, read by Steve's rule (st-2j3m): a
        '.' in it makes it a dollar price, none makes it an SPX level.
        ``("price", 10.30)`` or ``("spx", 7585.0)``; nothing for an empty box."""
        raw = (request.form.get(leg) or "").strip()
        if not raw:
            return None
        return parse_leg_text(raw, leg)

    def _actions() -> dict[str, str]:
        """Absolute paths for every form, so a page served at ``/exec/flatten``
        posts its confirm to ``/exec/flatten/confirm`` and not to a sibling."""
        return {name: url_for(f"exec.{name}") for name in (
            "index", "account", "unlock", "stop", "resume", "stand_down", "lock", "lock_confirm",
            "flatten", "flatten_confirm", "reauth_link", "reauth_store",
            "order", "order_price", "order_state", "order_send",
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
 .staterow{display:flex;align-items:center;gap:.6em}
 .badge{font-weight:700;font-size:.8em;padding:4px 8px;border-radius:6px;letter-spacing:.04em}
 .badge.paper{background:#fbbf24;color:#111}.badge.live{background:#dc2626;color:#fff}
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
    # passphrase being typed on a quiet page is never wiped. On a live page
    # the reload waits while a box has focus (a passphrase half-typed, a
    # value changed) and goes the second it is left — the meta refresh it
    # replaced wiped the passphrase field mid-word (audit note 37, st-sk9r).
    reload = (f"<script>(function(){{var s={int(refresh_s)};function go(){{var a=document.activeElement;"
              "if(a&&a.tagName==='INPUT'&&(a.type==='password'||a.value!==a.defaultValue))"
              "{setTimeout(go,1000);return;}location.reload();}setTimeout(go,s*1000);})();</script>"
              if refresh_s else "")
    return (f"<!doctype html><html><head><meta charset=utf-8><title>{esc(title)}</title>"
            f"{_STYLE}</head><body><h1>{esc(title)}</h1>{body}{reload}</body></html>")


def _not_from_this_page(req: Any) -> str | None:
    """Why a post is refused as not from this page, or ``None`` when it is.
    ``Sec-Fetch-Site`` decides when present (every current browser sends
    it); without it, ``Origin`` must name this host — the host the request
    reached, or the one the tailnet proxy says it was addressed to."""
    site = req.headers.get("Sec-Fetch-Site")
    if site is not None:
        if site == "same-origin":
            return None
        where = {"cross-site": "another site", "same-site": "another page on this site",
                 "none": "outside any page"}.get(site, site)
        return f"this request came from {where}, not from this page — refused"
    origin = req.headers.get("Origin")
    if not origin:
        return ("this request says neither where it came from (Sec-Fetch-Site) nor "
                "what page sent it (Origin) — refused")
    sent_from = origin.split('://', 1)[-1].split('/', 1)[0].lower()   # the host[:port]
    hosts = {h.lower() for h in (req.host, req.headers.get("X-Forwarded-Host", "")) if h}
    hosts |= {h.split(":", 1)[0] for h in hosts}
    if sent_from in hosts or sent_from.split(":", 1)[0] in hosts:
        return None
    return f"this request was sent by {esc(sent_from) or 'an unnamed page'}, not by this page — refused"


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


#: The trading grant's wall is worth a line from this many days out — the
#: seven-day token lifecycle is the live feed's failure point, and the grants
#: card that used to show it is gone (st-2hei).
WALL_ALERT_DAYS = 2.0


def wall_alert_html(st: dict[str, Any], now: datetime) -> str:
    """One red line when the trading grant's refresh wall is inside
    ``WALL_ALERT_DAYS`` or past — read from the armed credential, or from
    the wall the journal last saw while LOCKED. Nothing otherwise. On the
    account page, above the re-authorisation it asks for; it left the order
    form on Steve's word (2026-09-17, st-bafu)."""
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


def unlock_form(action: str, back: str | None = None) -> str:
    """The passphrase box and UNLOCK — on the account page, and on the
    trading page whenever the service is LOCKED (Steve, 2026-09-15: "if panel
    is locked the Passphrase should be displayed"). ``back=order`` brings the
    answer to the trading page."""
    back_field = f"<input type=hidden name=back value='{esc(back)}'>" if back else ""
    return (f"<form method=post action='{action}'>{back_field}"
            "<input type=password name=passphrase placeholder='passphrase' "
            "autocomplete=current-password required>"
            "<button class='big arm'>UNLOCK</button></form>")


def _render_index(service: ExecService, vault: Vault, market: CredentialFile | None,
                  clock: Callable[[], datetime], a: dict[str, str], *,
                  msg: str | None, bad: str | None) -> str:
    st = service.status()
    arming = st["arming"]
    state = arming["state"]
    day = st["day"]
    parts: list[str] = []

    if msg:
        parts.append(f"<div class=msg>{esc(msg)}</div>")
    if bad:
        parts.append(f"<div class=bad>{esc(bad)}</div>")
    parts.append(f"<form method=get action='{a['order']}'>"
                 "<button class='big quiet'>← trade</button></form>")

    # ── state ── (Steve, 2026-09-15: "way too many words in execd screen …
    # no need to define PAPER" — the badge is the word, the state is the
    # word, and the only sentence left is STOP when it is on)
    stop_line = ("<div class=stop-on>STOP IS ON</div>" if arming["killed"] else "")
    until = arming.get("expires_at_ct")
    sub = {"LOCKED": "", "ARMED": f"until {until}" if until else "",
           "STOOD_DOWN": "exits only"}[state]
    mode = str(st.get("mode", "live"))
    mode_badge = ("<span class='badge paper'>PAPER</span>" if mode == "paper"
                  else "<span class='badge live'>LIVE</span>")
    parts.append(f"<div class=card><div class=staterow>{mode_badge}"
                 f"<span class='state {state}'>{state.replace('_', ' ')}</span>"
                 f"<span class=k>{esc(sub)}</span></div>{stop_line}"
                 f"<div class=k>service {esc(st['sha'])}</div></div>")

    # ── controls ──
    if state == "LOCKED":
        parts.append(unlock_form(a["unlock"]))
    if not arming["killed"]:
        parts.append(f"<form method=post action='{a['stop']}'><button class='big stop'>STOP</button></form>")
    else:
        parts.append(f"<form method=post action='{a['resume']}'>"
                     "<input type=password name=passphrase placeholder='passphrase' "
                     "autocomplete=current-password required>"
                     "<button class='big quiet'>clear STOP</button></form>")
    if state != "LOCKED":
        parts.append(f"<form method=post action='{a['flatten']}'>"
                     "<button class='big exit'>FLATTEN</button></form>")
        if state == "ARMED":
            parts.append(f"<form method=post action='{a['stand_down']}'>"
                         "<button class='big quiet'>stand down</button></form>")
        parts.append(f"<form method=post action='{a['lock']}'>"
                     "<button class='big cancel'>lock</button></form>")

    # ── the position, with its money ──
    for p in st["positions"]:
        parts.append(_render_position(p))
    parts.append(_render_not_this_services(st))
    # the day's close-out, when it is past due and has not taken (st-9j8e)
    from .panel import flat_by_close_alert
    if (alert := flat_by_close_alert(st)):
        parts.append(f"<div class=card>{alert}</div>")

    # ── the day ──
    pnl = st.get("pnl") or {}
    rows = [
        ("open", day["open_positions"]),
        ("realized", f"{_money(pnl.get('realized_usd'))} over {pnl.get('closes', 0)} close(s)"),
        ("unrealized, net", _money(pnl.get("unrealized_net_usd"))),
        ("day", _money(pnl.get("day_usd"))),
    ]
    # No ceiling, no headroom, no attempts. Steve, 2026-09-18: "you are
    # _still showing headroom and attempts. remove all aspects of that"
    # (st-644f), after st-bafu removed the order form's own copy — "I don't
    # need that level of hand holding". The bounds still refuse an entry past
    # the day's ceiling or its attempt count, and /status still reports both
    # for the heartbeats; they are simply not on a page he reads.
    parts.append("<h2>Today</h2><div class=card><table>" + "".join(
        f"<tr><td>{esc(k)}</td><td{_money_class(v)}>{esc(str(v))}</td></tr>" for k, v in rows)
        + "</table></div>")
    if st["working"]:
        lines = ["working " + json.dumps(w, separators=(",", ":")) for w in st["working"]]
        parts.append("<div class=card><pre>" + esc("\n".join(lines)) + "</pre></div>")

    # ── re-authorisation ── (the grants card is gone — Steve, 2026-09-15:
    # "Still don't need 'GRANTS' section"; the walls are the service's to
    # alert on, [ALERT] one line, not a table for him to read)
    parts.append(wall_alert_html(st, service.clock()))
    parts.append(
        "<details><summary>re-authorise (weekly)</summary>"
        f"<div class=card><form method=post action='{a['reauth_link']}'>"
        "<label><input type=radio name=app value=trading checked> trading</label> &nbsp; "
        "<label><input type=radio name=app value=market> market data</label>"
        "<input type=password name=passphrase placeholder='passphrase' "
        "autocomplete=current-password required style='margin-top:.5em'>"
        "<button class='big quiet'>login link</button></form></div></details>")

    # ── journal ──
    tail = service.journal.tail(12)
    if tail:
        lines = [f"{e.get('ts_ct', '')[11:19]} {e.get('event', '')} "
                 + " ".join(f"{k}={_short(v)}" for k, v in e.items()
                            if k not in ("ts", "ts_ct", "event", "sha"))
                 for e in reversed(tail)]
        parts.append("<h2>Journal</h2><div class=card><pre>"
                     + esc("\n".join(lines)) + "</pre></div>")
    live_money = bool(st["positions"] or st["working"])
    return _page("execd", "".join(parts), refresh_s=5 if live_money else None)


def _describe_place(out: dict[str, Any]) -> str:
    """The service's answer to a send, in plain words — the desk's wording,
    kept here because the installed service has no ``strader/``."""
    word = ""   # the strip's badge says PAPER; no prefix (Steve, 2026-09-15, st-2hei)
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
    word = ""   # the strip's badge says PAPER; no prefix (Steve, 2026-09-15, st-2hei)
    parts: list[str] = []
    for leg, name in (("stop", "Stop"), ("target", "Target")):
        r = out.get(leg)
        if not isinstance(r, dict):
            continue
        level = r.get(f"{leg}_spx")
        if r.get("unchanged"):
            # "Stop moved from 10.30 to 10.30" (2026-09-15 14:07 CT) — say it
            # stayed, and the service left the leg resting (st-ff5j)
            line = f"{name} unchanged at {float(r.get('old_price') or 0):.2f}"
            if level is not None and r.get("given") == "spx":
                line += f" (SPX {float(level):.2f})"
            parts.append(line + ".")
        elif r.get("level_only"):
            # the level moved, the resting leg did not (st-2j3m)
            if level is None:
                parts.append(f"{name} is now the resting {float(r['new_price']):.2f} alone — "
                             f"nothing fires on the SPX mark for it.")
            else:
                parts.append(f"{name} SPX level set to {float(level):.2f}; the resting "
                             f"{float(r['new_price']):.2f} {leg} is unchanged.")
        elif r.get("moved"):
            # the answer says which form set it (st-2j3m)
            if r.get("given") == "spx" and level is not None:
                line = (f"{name} set by SPX {float(level):.2f} → rests at "
                        f"{float(r['new_price']):.2f} (was {float(r.get('old_price') or 0):.2f})")
            else:
                line = f"{name} moved from {float(r.get('old_price') or 0):.2f} to {float(r['new_price']):.2f}"
                if leg == "stop" and level is not None:
                    line += f" (SPX cut level now {float(level):.2f})"
                elif leg == "target" and r.get("old_target_spx") is not None:
                    line += " (a price: nothing fires on the SPX mark for it now)"
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
                     + (f" (order {p['stop_order_id']} — NOT IN THE BROKER'S LISTING)"
                        if p.get("stop_state") == "unaccounted" else
                        f" (order {p['stop_order_id']})" if p.get("stop_state") else
                        " (NO STOP RESTING)")))
    else:
        rows.append(("at the stop", "NO STOP — the position is unprotected"))
    if p.get("target_price") is not None:
        rows.append(("at the target", f"target {p['target_price']:.2f} → net {_money(v.get('at_target_usd'))}"
                     + (f" (order {p['target_order_id']})" if p.get("target_order_id") else " (NO TARGET RESTING)")))
    else:
        rows.append(("at the target", "NO TARGET — the journal says why"))
    if p.get("stop_spx") is not None:
        rows.append(("SPX cut level", f"{p['stop_spx']:.2f}"))
    if p.get("target_spx") is not None:
        rows.append(("SPX target level", f"{p['target_spx']:.2f}"))
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
                 f"<label>stop<input name=stop inputmode=decimal value='{stop_val}'></label>"
                 f"<label>target<input name=target inputmode=decimal value='{target_val}'></label>"
                 "</div><button class='big quiet'>UPDATE</button>"
                 "<div class=k>a number with a '.' is a price (10.30); without one it is an "
                 "SPX level (7585)</div></form>")
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


def _render_confirm_lock(service: ExecService, nonce: str, a: dict[str, str],
                         back: str = "") -> str:
    st = service.status()
    rows = "".join(f"<div class=row><b>{esc(p['symbol'].strip())} × {p['qty']}</b>"
                   f" — in at {float(p['entry_price']):.2f}</div>" for p in st["positions"])
    rows += "".join(f"<div class=row><b>{esc(w['symbol'].strip())} × {w['qty']}</b> working</div>"
                    for w in st.get("working") or [])
    listing = (f"<div class=k>you are holding</div>{rows}"
               "<div class=k>LOCKED takes the credential out of memory: the SPX-mark exit "
               "does not fire, FLATTEN and the bracket's UPDATE are dead, and the stop "
               "resting at the broker is the only protection until you unlock. To get "
               "flat first, cancel and FLATTEN.</div>")
    back_field = "<input type=hidden name=back value='order'>" if back == "order" else ""
    body = (f"<div class=card>{listing}</div>"
            f"<form method=post action='{a['lock_confirm']}'>"
            f"<input type=hidden name=nonce value='{nonce}'>{back_field}"
            f"<button class='big cancel'>CONFIRM — LOCK</button></form>"
            f"<form method=get action='{a['order'] if back == 'order' else a['account']}'>"
            "<button class='big quiet'>cancel</button></form>"
            f"<div class=k>confirm window {int(CONFIRM_TTL_S)}s, single use</div>")
    return _page("LOCK with a position live — are you sure", body)


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
