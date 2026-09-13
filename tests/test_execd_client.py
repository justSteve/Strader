"""The readers' path through the service. [st-p8k8]

Drives ``broker_schwab.execd_client.ExecdClient`` against the real ``execd``
API app (mock broker, Flask test client standing in for the loopback), so
what is asserted is the whole seam: the ``schwab-py`` call a reader makes →
the query the service accepts → the body the reader parses. And that
``create_client`` picks the service when it answers and the token file when
it does not, without either path importing the other's dependencies.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from broker_schwab import client as factory
from broker_schwab.execd_client import ExecdClient, ExecdError, service_status
from execd.api import create_app
from execd.bounds import Bounds
from execd.broker import MockBroker
from execd.service import ExecService, ServiceConfig


@pytest.fixture
def api(tmp_path):
    broker = MockBroker()
    broker.set_quote("$SPX", bid=6379.75, ask=6380.25, last=6380.0)
    broker.set_quote("/ESU26", bid=6400.0, ask=6400.25, last=6400.25)
    broker.set_chain("SPX", {"calls": {"2026-08-26:0": {"6400.0": [{"bid": 2.0}]}},
                            "puts": {}})
    broker.set_history("/ES", [{"open": 1, "high": 2, "low": 0.5, "close": 1.5,
                                "volume": 10, "datetime": 1_756_000_000_000}])
    service = ExecService(broker, ServiceConfig(state_dir=tmp_path, bounds=Bounds(),
                                                sha="t"))
    app = create_app(service)
    app.config["TESTING"] = True
    return app.test_client(), broker


@pytest.fixture
def fetch(api):
    """A ``fetch`` that routes the client's URL into the Flask test client."""
    tc, _ = api
    calls: list[str] = []

    def _fetch(url: str, timeout: float) -> tuple[int, bytes]:
        calls.append(url)
        path = url.split("127.0.0.1:8778", 1)[1]
        r = tc.get(path)
        return r.status_code, r.get_data()

    _fetch.calls = calls  # type: ignore[attr-defined]
    return _fetch


@pytest.fixture
def client(fetch):
    return ExecdClient("http://127.0.0.1:8778", fetch=fetch)


class TestTheFourCalls:
    def test_get_quotes_reads_like_schwab_py(self, client):
        r = client.get_quotes(["$SPX", "/ESU26"])
        r.raise_for_status()
        data = r.json()
        assert r.status_code == 200
        assert data["$SPX"]["quote"]["lastPrice"] == 6380.0
        assert data["/ESU26"]["quote"]["askPrice"] == 6400.25

    def test_get_quotes_takes_a_bare_string(self, client, fetch):
        client.get_quotes("$SPX")
        assert fetch.calls[-1].endswith("/marketdata/quotes?symbols=%24SPX")

    def test_get_option_chain_maps_the_keyword_names(self, client, fetch):
        class ContractType:                    # schwab-py hands an enum
            value = "PUT"

        r = client.get_option_chain("$SPX", contract_type=ContractType(), strike_count=20,
                                    from_date=date(2026, 8, 26), to_date=date(2026, 8, 26),
                                    include_underlying_quote=True)
        assert r.status_code == 200
        url = fetch.calls[-1]
        assert "contractType=PUT" in url and "strikeCount=20" in url
        assert "fromDate=2026-08-26" in url and "includeUnderlyingQuote=true" in url
        assert "callExpDateMap" in r.json()

    def test_price_history_every_minute_sends_epoch_millis(self, client, fetch):
        start = datetime(2026, 8, 26, 13, 30, tzinfo=timezone.utc)
        end = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
        r = client.get_price_history_every_minute("/ES", start_datetime=start,
                                                  end_datetime=end,
                                                  need_extended_hours_data=False)
        assert r.status_code == 200 and r.json()["candles"][0]["close"] == 1.5
        url = fetch.calls[-1]
        assert "frequencyType=minute" in url and "frequency=1" in url
        assert f"startDate={int(start.timestamp() * 1000)}" in url
        assert "needExtendedHoursData=false" in url

    def test_five_minutes_is_frequency_five(self, client, fetch):
        client.get_price_history_every_five_minutes("/ES")
        assert "frequency=5" in fetch.calls[-1] and "periodType=day" in fetch.calls[-1]

    def test_a_service_refusal_is_a_status_the_reader_can_see(self, client):
        r = client.get_price_history("/ES", period_type="day", frequency_type="minute",
                                     frequency=1, need_previous_close=True)
        assert r.status_code == 200
        bad = client._get("quotes", {"symbols": "$SPX", "accountNumber": "1"})
        assert bad.status_code == 400
        with pytest.raises(ExecdError):
            bad.raise_for_status()

    def test_unreachable_is_an_execd_error(self):
        def down(url, timeout):
            raise OSError("connection refused")

        with pytest.raises(ExecdError):
            ExecdClient(fetch=down).get_quotes("$SPX")


class TestServiceStatus:
    def test_answers_the_status_body(self, fetch):
        st = service_status("http://127.0.0.1:8778", fetch=fetch)
        assert st is not None and st["arming"]["state"] == "LOCKED"

    def test_none_when_down(self):
        def down(url, timeout):
            raise OSError("refused")

        assert service_status(fetch=down) is None


class TestCreateClient:
    def test_picks_the_service_when_it_answers(self, monkeypatch, fetch):
        monkeypatch.setattr("broker_schwab.execd_client._fetch", fetch)
        monkeypatch.delenv(factory.MODE_ENV, raising=False)
        # The token-file path must not be reached in a test, ever: it would
        # build a live client from the real token file on this box.
        monkeypatch.setattr(factory, "_legacy_client",
                            lambda: (_ for _ in ()).throw(AssertionError("legacy path")))
        c = factory.create_client()
        assert isinstance(c, ExecdClient)
        assert fetch.calls and fetch.calls[0].endswith("/status")

    def test_falls_back_to_the_token_file_when_it_does_not(self, monkeypatch):
        def down(url, timeout):
            raise OSError("refused")

        monkeypatch.setattr("broker_schwab.execd_client._fetch", down)
        monkeypatch.delenv(factory.MODE_ENV, raising=False)
        sentinel = object()
        monkeypatch.setattr(factory, "_legacy_client", lambda: sentinel)
        assert factory.create_client() is sentinel

    def test_execd_mode_refuses_to_fall_back(self, monkeypatch):
        def down(url, timeout):
            raise OSError("refused")

        monkeypatch.setattr("broker_schwab.execd_client._fetch", down)
        monkeypatch.setenv(factory.MODE_ENV, "execd")
        with pytest.raises(RuntimeError, match="does not answer"):
            factory.create_client()

    def test_legacy_mode_never_probes(self, monkeypatch):
        def boom(url, timeout):
            raise AssertionError("probed")

        monkeypatch.setattr("broker_schwab.execd_client._fetch", boom)
        monkeypatch.setenv(factory.MODE_ENV, "legacy")
        sentinel = object()
        monkeypatch.setattr(factory, "_legacy_client", lambda: sentinel)
        assert factory.create_client() is sentinel

    def test_an_unknown_mode_is_refused(self, monkeypatch):
        monkeypatch.setenv(factory.MODE_ENV, "maybe")
        with pytest.raises(RuntimeError, match="not one of"):
            factory.create_client()

    def test_the_service_path_imports_no_broker_library(self):
        import sys
        import importlib
        for name in list(sys.modules):
            if name == "schwab" or name.startswith("schwab."):
                del sys.modules[name]
        importlib.reload(__import__("broker_schwab.execd_client", fromlist=["x"]))
        assert not any(m == "schwab" or m.startswith("schwab.") for m in sys.modules)
