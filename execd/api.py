"""The narrow door — HTTP on the loopback, and nothing else. [st-eznu]

Fourteen routes, no policy. Every one of them is a translation of an
:class:`~execd.service.ExecService` method into JSON and back; the bounds, the
arming state and the journal all live behind it. That is deliberate: a rule
that lives in a request handler is a rule that a second entry point can miss,
and stage 5 adds a second caller (the intent desk) to this same service.

**What is not here is the design.** There is no ``/unlock``, no ``/resume``, no
re-auth route, and ``tests/execd/test_api.py`` asserts their absence rather
than trusting this docstring. Arming the service is Steve typing a passphrase
into its tailnet page; an agent that can reach this API can ask it to trade
within his bounds, and cannot arm it, cannot clear his STOP, and never sees the
credential.

Status codes carry meaning:

``200``  the service acted, or answered a read.
``400``  the request was not a valid intent — malformed, not refused.
``409``  a bound refused it. The body carries ``{"refused": {"bound", "reason"}}``.
``502``  the broker could not be reached. Nothing was sent that we know of.
``404``  no such route — including the ones deliberately absent.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from .broker import BrokerError
from .intent import OrderIntent
from .service import ExecService, Refused

#: The loopback, and only the loopback. The page that Steve unlocks from is a
#: separate surface on the tailnet (stage 3); this one never leaves the box.
BIND_HOST = "127.0.0.1"
BIND_PORT = 8778


def create_app(service: ExecService) -> Flask:
    app = Flask("execd")
    app.config["EXEC_SERVICE"] = service

    # ── errors ───────────────────────────────────────────────────────────
    @app.errorhandler(Refused)
    def _refused(exc: Refused):
        return jsonify({"refused": exc.refusal.to_dict()}), 409

    @app.errorhandler(BrokerError)
    def _broker_down(exc: BrokerError):
        return jsonify({"error": "broker", "detail": str(exc)}), 502

    @app.errorhandler(ValueError)
    def _bad_request(exc: ValueError):
        return jsonify({"error": "bad_request", "detail": str(exc)}), 400

    # ── reads ────────────────────────────────────────────────────────────
    @app.get("/status")
    def status():
        return jsonify(service.status())

    @app.get("/quote")
    def quote():
        symbol = _required_arg("symbol")
        return jsonify(service.quote(symbol).to_dict())

    @app.get("/chain")
    def chain():
        root = _required_arg("root")
        return jsonify(service.chain(root, request.args.get("expiry")))

    @app.get("/orders")
    def orders():
        return jsonify({"orders": [o.to_dict() for o in service.orders()]})

    @app.get("/positions")
    def positions():
        return jsonify({
            "broker": [p.to_dict() for p in service.positions()],
            "tracked": service.status()["positions"],
        })

    @app.get("/journal")
    def journal():
        n = request.args.get("n", default=50, type=int)
        return jsonify({"entries": service.journal.tail(max(1, min(n, 1000)))})

    # ── writes ───────────────────────────────────────────────────────────
    @app.post("/preview")
    def preview():
        return _answer(service.preview(_intent()))

    @app.post("/place")
    def place():
        return _answer(service.place(_intent()))

    @app.post("/cancel")
    def cancel():
        body = _body()
        order_id = body.get("order_id")
        if not order_id:
            raise ValueError("cancel needs an order_id")
        return _answer(service.cancel(str(order_id)))

    @app.post("/flatten")
    def flatten():
        _require_json()
        return _answer(service.flatten(reason=str(_body().get("reason", "flatten"))))

    @app.post("/stand-down")
    def stand_down():
        _require_json()
        return jsonify(service.stand_down())

    @app.post("/stop")
    def stop():
        """STOP on. Ungated on purpose — the switch that stops new risk must
        never be the one that is hard to reach. Clearing it is page-only.

        Deliberately exempt from ``_require_json``: a hostile page firing this
        route can only stop new risk, and Steve's phone reaching it must not
        depend on getting a header right (finding 15 records the trade)."""
        return jsonify(service.stop())

    @app.post("/observe")
    def observe():
        body = _body()
        if "spx" not in body:
            raise ValueError("observe needs an spx mark")
        return jsonify(service.observe(float(body["spx"])))

    @app.post("/poll-fills")
    def poll_fills():
        _require_json()
        return jsonify(service.poll_fills())

    return app


# ── helpers ───────────────────────────────────────────────────────────────

def _require_json() -> None:
    """Refuse a state-changing request that did not arrive as JSON.

    Finding 15 of the 2026-08-30 audit: four POST routes acted on a body-less
    request, and a cross-origin HTML form post — which needs no CORS preflight
    — could therefore fire them from any page a browser on this box rendered,
    ``/flatten`` among them. A form cannot send ``application/json`` without
    triggering a preflight the loopback server never answers, so requiring the
    JSON content type closes the form-post path. Routes that carry a required
    JSON body (``/place``, ``/observe``, …) were never reachable this way;
    ``/stop`` is exempt on purpose — see its docstring."""
    if not request.is_json:
        raise ValueError(
            "this route changes state and acts only on a JSON request — "
            "send Content-Type: application/json (an empty {} body is fine)")


def _body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    return data


def _intent() -> OrderIntent:
    body = _body()
    if not body:
        raise ValueError("expected an intent as a JSON object")
    return OrderIntent.from_dict(body).validated()


def _required_arg(name: str) -> str:
    value = request.args.get(name)
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _answer(result: dict[str, Any]):
    """A refusal is a 409 with the bound named, not a 200 with a sad field.

    The caller in stage 5 is code; the difference between "the service declined"
    and "the service acted" has to be legible without reading the body."""
    if result.get("refused"):
        return jsonify(result), 409
    return jsonify(result), 200
