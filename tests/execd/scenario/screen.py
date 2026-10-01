"""The order screen, driven the way the browser drives it. [st-ug1h]

``OrderScreen`` keeps the form's state — the selection form (``#sel``: side,
strike, delta, lots, the price box, the stop box ``stopoff``, the close-at
box ``exitspx``) and the SEND form's hidden fields — and moves it with the
same requests the page's script makes:

* picking a side or tapping a strike, typing in a box, or a stepper tap:
  ``GET /order/price?<selection>``, which answers the ticket as JSON and
  SEND's hidden fields (``send_fields_html``, the strike on the ticket
  pinned, st-qqxj);
* SEND: ``POST /order/send`` with the hidden fields, then every box of the
  selection form as it stands (``['stop', 'stopoff', 'exitspx', 'limit',
  'lots']``) and the strike box when it holds one (``delta`` dropped), the
  single-use token, ``ajax=1`` — what ``PANEL_SCRIPT``'s submit handler
  builds (execd/panel.py);
* the poll: ``GET /order/state?<selection>``, the payload the page paints.

What the screen SHOWED is kept (``shown``: the last ticket the page
painted) so a test can compare it with what the service RECEIVED.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

#: what the stop steppers move the stop box by (orderpage: 0.10 a tap)
STEP = 0.10
DEFAULT_STOPOFF = 0.30
_HIDDEN = re.compile(r"name='([^']+)' value='([^']*)'")
_NONCE = re.compile(r"name=nonce value='([^']+)'")
_CPNL = re.compile(r"<span class='cpnl [a-z]+'>([^<]+)</span>")


def dollars(text: str) -> float:
    """``-$1,234.50`` / ``+$20.00`` / ``$0.00`` → a number."""
    t = text.strip().replace(",", "").replace("$", "")
    return float(t)


class OrderScreen:
    def __init__(self, scn) -> None:
        self.scn = scn
        self.client = scn.page()
        self.prefix = "/exec"
        #: the selection form's fields, as its inputs hold them
        self.sel: dict[str, str] = {"side": "", "strike": "", "delta": "", "lots": "1",
                                    "limit": "", "stop": "", "stopoff": "", "exitspx": ""}
        self.hidden: dict[str, str] = {}
        self.shown: dict[str, Any] = {}
        self.answers: list[dict[str, Any]] = []

    # ── the selection ────────────────────────────────────────────────────
    def query(self) -> dict[str, str]:
        return {k: v for k, v in self.sel.items() if v not in ("", None)}

    def reprice(self) -> dict[str, Any]:
        r = self.client.get(f"{self.prefix}/order/price?{urlencode(self.query())}")
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        self.shown = r.json
        self.hidden = dict(_HIDDEN.findall(self.shown.get("send_fields_html") or ""))
        return self.shown

    def pick(self, side: str, delta: float | None = None) -> dict[str, Any]:
        self.sel.update(side=side, strike="", delta="" if delta is None else f"{delta:g}",
                        limit="")
        body = self.client.get(f"{self.prefix}/order?{urlencode(self.query())}"
                               ).get_data(as_text=True)
        assert "id=fd0" in body
        return self.reprice()

    def tap(self, strike: float) -> dict[str, Any]:
        self.sel.update(strike=f"{strike:g}", delta="", limit="")
        return self.reprice()

    def step_stop(self, taps: int) -> dict[str, Any]:
        """``+`` widens the stop box by 0.10 a tap, ``−`` narrows it."""
        now = float(self.sel["stopoff"] or DEFAULT_STOPOFF)
        self.sel.update(stopoff=f"{max(0.05, round(now + taps * STEP, 2)):.2f}", exitspx="")
        return self.reprice()

    def type_stop(self, text: str) -> dict[str, Any]:
        self.sel.update(stopoff=text, exitspx="")
        return self.reprice()

    def type_exit(self, level: float) -> dict[str, Any]:
        """The close-at-SPX box: typing in it writes NA in the stop box."""
        self.sel.update(exitspx=f"{level:g}", stopoff="")
        return self.reprice()

    def lock(self, price: float | None = None) -> dict[str, Any]:
        """The padlock: the price box holds the limit (the ticket's own, or one
        he typed)."""
        self.sel["limit"] = f"{(price if price is not None else self.shown['limit']):.2f}"
        return self.reprice()

    def lots(self, n: int) -> dict[str, Any]:
        self.sel["lots"] = str(n)
        return self.reprice()

    # ── SEND ─────────────────────────────────────────────────────────────
    def nonce(self) -> str:
        body = self.client.get(f"{self.prefix}/order?{urlencode(self.query())}"
                               ).get_data(as_text=True)
        m = _NONCE.search(body)
        assert m, "the page carried no SEND token"
        return m.group(1)

    def send(self, nonce: str | None = None) -> dict[str, Any]:
        """Tap SEND, as the script builds the post."""
        token = nonce or self.nonce()
        fd = dict(self.hidden)
        for n in ("stop", "stopoff", "exitspx", "limit", "lots"):
            fd[n] = self.sel.get(n, "")
        if self.sel.get("strike"):
            fd["strike"] = self.sel["strike"]
            fd.pop("delta", None)
        fd.update(nonce=token, ajax="1")
        n_before = len(self.scn.events("request"))

        def post():
            r = self.client.post(f"{self.prefix}/order/send", data=fd,
                                 headers={"Accept": "application/json"})
            assert r.status_code == 200, r.get_data(as_text=True)[:400]
            return r.json
        answer = self.scn.step(f"SEND {fd.get('side')} {fd.get('strike')} "
                               f"stopoff={fd.get('stopoff')} exitspx={fd.get('exitspx')} "
                               f"limit={fd.get('limit')}", post)
        self.answers.append(answer)
        sent = [e for e in self.scn.events("request")[n_before:] if e.get("kind") == "place"]
        answer["_received"] = sent[-1]["intent"] if sent else None
        return answer

    # ── the poll ─────────────────────────────────────────────────────────
    def poll(self) -> dict[str, Any]:
        q = urlencode(self.query()) if self.sel.get("side") else ""
        return self.scn.step("poll", lambda: self.client.get(
            f"{self.prefix}/order/state?{q}").json)

    @staticmethod
    def closed_cards(state: dict[str, Any]) -> list[float]:
        return [dollars(t) for t in _CPNL.findall(state.get("closed_html") or "")]

    @staticmethod
    def today(state: dict[str, Any]) -> float | None:
        text = state.get("today_text")
        if not text:
            return None
        word = text.split()[-1]
        return None if word in ("—", "-", "None") else dollars(word)
