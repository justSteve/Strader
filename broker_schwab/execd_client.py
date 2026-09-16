"""The readers' client to the execution service's market-data door. [st-p8k8]

Stage 3 of the live execution service moves the market token out of the repo
tree: the one credential holder on this box is ``execd``, and the repo's
readers — the schwab-stages snapshots, the premarket profile, the Mancini
overnight section, the MI gauge, the continuation meter, the FD0 feed — ask it
for what they used to fetch with their own copy of the token.

This class answers the four ``schwab-py`` calls those readers make, with the
same names and keyword arguments, and returns an object with the three things
they read off a response — ``status_code``, ``json()``, ``raise_for_status()``
— so no consumer changes. What it does NOT offer is anything the door does
not: the service passes through exactly three market-data resources (quotes,
chains, price history), GET only, and nothing under ``/trader``.

No credential, no gate key, no ``schwab`` import: this module speaks plain
HTTP to ``127.0.0.1:8778`` with the standard library. ``create_client`` in
``broker_schwab.client`` picks it when the service answers and falls back to
the token-file path when it does not, so the morning jobs keep running across
the migration and the plaintext token is retired only once the service has
been seen answering them.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger("broker_schwab.execd")

#: The service's narrow door. Loopback only; the port is ``execd.api.BIND_PORT``.
EXECD_URL = os.environ.get("EXECD_URL", "http://127.0.0.1:8778")

#: How long a reader waits for the service. Schwab itself gets 15 s inside
#: the service; this covers that plus the hop.
TIMEOUT_S = float(os.environ.get("EXECD_TIMEOUT_S", "20"))

#: What ``create_client`` spends deciding whether the service is up.
PROBE_TIMEOUT_S = 1.5

#: The second look when the first one found nothing. The service answers one
#: request at a time, so a probe can queue behind a Schwab call that a slow
#: link is stretching to several seconds — 2026-09-16, 2 to 5 s per call, and
#: the level tracker fell to a token file that had moved into the service,
#: then paged Steve about a token that was fine [st-5fs4]. A refused connection
#: still comes back at once; only a queued probe spends this budget.
PATIENT_PROBE_TIMEOUT_S = float(os.environ.get("EXECD_PATIENT_PROBE_S", "12"))

Fetch = Callable[[str, float], tuple[int, bytes]]


def _fetch(url: str, timeout: float) -> tuple[int, bytes]:
    """One GET. A non-2xx is returned as its status, not raised, so a reader
    sees the same ``status_code`` it saw from ``schwab-py``."""
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:  # noqa: S310 — loopback, fixed host
            return r.status, r.read()
    except HTTPError as exc:
        return exc.code, exc.read()


class ExecdError(RuntimeError):
    """The service could not be reached, or answered with an error status."""


class ExecdResponse:
    """The three things every reader touches on a ``schwab-py`` response."""

    def __init__(self, status_code: int, body: bytes, url: str) -> None:
        self.status_code = status_code
        self._body = body
        self.url = url

    @property
    def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self._body or b"null")

    def raise_for_status(self) -> None:
        if not 200 <= self.status_code < 300:
            raise ExecdError(f"execd answered HTTP {self.status_code} for "
                             f"{self.url.split('?')[0]}: {self.text[:200]}")

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"<ExecdResponse {self.status_code}>"


def _ms(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _plain(value: Any) -> Any:
    """``schwab-py`` takes enums for a few arguments (``Client.Options.
    ContractType.PUT``); Schwab takes their values. Dates become ISO days,
    booleans the lowercase words the API wants."""
    if value is None:
        return None
    if hasattr(value, "value") and not isinstance(value, (str, int, float)):
        value = value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class ExecdClient:
    """A ``schwab-py``-shaped read client over the service's door."""

    def __init__(self, base_url: str = EXECD_URL, *, timeout_s: float = TIMEOUT_S,
                 fetch: Fetch | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        # Resolved at call time, not bound at definition: a test that patches
        # the module's ``_fetch`` must see its patch here.
        self._fetch = fetch or (lambda url, timeout: _fetch(url, timeout))

    # ── plumbing ─────────────────────────────────────────────────────────
    def _get(self, kind: str, params: Mapping[str, Any]) -> ExecdResponse:
        clean = {k: _plain(v) for k, v in params.items() if v is not None}
        url = f"{self.base_url}/marketdata/{kind}"
        if clean:
            url += "?" + urlencode(clean)
        try:
            status, body = self._fetch(url, self.timeout_s)
        except (URLError, OSError, TimeoutError) as exc:
            raise ExecdError(f"execd unreachable at {self.base_url}: "
                             f"{type(exc).__name__}: {exc}") from None
        return ExecdResponse(status, body, url)

    # ── the four calls the readers make ──────────────────────────────────
    def get_quotes(self, symbols, *, fields=None, indicative=None) -> ExecdResponse:
        if isinstance(symbols, str):
            symbols = [symbols]
        return self._get("quotes", {"symbols": ",".join(symbols), "fields": fields,
                                    "indicative": indicative})

    def get_option_chain(self, symbol, *, contract_type=None, strike_count=None,
                         include_underlying_quote=None, strategy=None, interval=None,
                         strike=None, strike_range=None, from_date=None, to_date=None,
                         volatility=None, underlying_price=None, interest_rate=None,
                         days_to_expiration=None, exp_month=None, option_type=None,
                         entitlement=None) -> ExecdResponse:
        return self._get("chains", {
            "symbol": symbol, "contractType": contract_type, "strikeCount": strike_count,
            "includeUnderlyingQuote": include_underlying_quote, "strategy": strategy,
            "interval": interval, "strike": strike, "range": strike_range,
            "fromDate": from_date, "toDate": to_date, "volatility": volatility,
            "underlyingPrice": underlying_price, "interestRate": interest_rate,
            "daysToExpiration": days_to_expiration, "expMonth": exp_month,
            "optionType": option_type, "entitlement": entitlement})

    def get_price_history(self, symbol, *, period_type=None, period=None,
                          frequency_type=None, frequency=None, start_datetime=None,
                          end_datetime=None, need_extended_hours_data=None,
                          need_previous_close=None) -> ExecdResponse:
        return self._get("pricehistory", {
            "symbol": symbol, "periodType": period_type, "period": period,
            "frequencyType": frequency_type, "frequency": frequency,
            "startDate": _ms(start_datetime), "endDate": _ms(end_datetime),
            "needExtendedHoursData": need_extended_hours_data,
            "needPreviousClose": need_previous_close})

    def _minutes(self, symbol, every: int, start_datetime, end_datetime,
                 need_extended_hours_data, need_previous_close) -> ExecdResponse:
        # schwab-py's normalisation, kept so a reader that passed no window
        # gets the same window it always got: the epoch to a week from now.
        if start_datetime is None:
            start_datetime = datetime(1971, 1, 1, tzinfo=timezone.utc)
        if end_datetime is None:
            end_datetime = datetime.now(tz=timezone.utc).replace(microsecond=0)
            end_datetime = end_datetime.fromtimestamp(end_datetime.timestamp() + 7 * 86400,
                                                      tz=timezone.utc)
        return self.get_price_history(
            symbol, period_type="day", frequency_type="minute", frequency=every,
            start_datetime=start_datetime, end_datetime=end_datetime,
            need_extended_hours_data=need_extended_hours_data,
            need_previous_close=need_previous_close)

    def get_price_history_every_minute(self, symbol, *, start_datetime=None,
                                       end_datetime=None, need_extended_hours_data=None,
                                       need_previous_close=None) -> ExecdResponse:
        return self._minutes(symbol, 1, start_datetime, end_datetime,
                             need_extended_hours_data, need_previous_close)

    def get_price_history_every_five_minutes(self, symbol, *, start_datetime=None,
                                             end_datetime=None,
                                             need_extended_hours_data=None,
                                             need_previous_close=None) -> ExecdResponse:
        return self._minutes(symbol, 5, start_datetime, end_datetime,
                             need_extended_hours_data, need_previous_close)


def service_status(base_url: str = EXECD_URL, *, timeout_s: float = PROBE_TIMEOUT_S,
                   fetch: Fetch | None = None) -> dict[str, Any] | None:
    """The service's ``/status`` body, or ``None`` when it does not answer.
    What ``create_client`` and the token-age heartbeat both ask first."""
    fetch = fetch or _fetch
    try:
        status, body = fetch(f"{base_url.rstrip('/')}/status", timeout_s)
    except (URLError, OSError, TimeoutError):
        return None
    if status != 200:
        return None
    try:
        parsed = json.loads(body)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None
