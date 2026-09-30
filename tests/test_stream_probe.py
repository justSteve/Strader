"""The account-stream probe's pure parts: scrubbing and frame shape. [st-8bls]"""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "schwab_stream_probe.py"
_spec = importlib.util.spec_from_file_location("stream_probe", _PATH)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

INFO = {"schwabClientCustomerId": "cust", "schwabClientCorrelId": "corr",
        "schwabClientChannel": "N9", "schwabClientFunctionId": "APIAPP"}


def test_scrub_removes_account_numbers_nested_in_strings():
    frame = {"data": [{"service": "ACCT_ACTIVITY", "content": [
        {"1": "12345678", "2": "OrderFill",
         "3": '{"AccountNumber":"87654321","Qty":1}'}]}]}
    out = str(probe.scrub(frame))
    assert "12345678" not in out and "87654321" not in out
    assert "OrderFill" in out and '"Qty":1' in out


def test_scrub_removes_named_secrets():
    assert probe.scrub({"a": "Bearer tok-xyz"}, ("tok-xyz",)) == {"a": "Bearer <secret>"}


def test_request_shape_matches_the_streamer_contract():
    r = probe.request(INFO, 1, "ACCT_ACTIVITY", "SUBS", {"keys": "corr", "fields": "0,1,2,3"})
    (req,) = r["requests"]
    assert req == {"service": "ACCT_ACTIVITY", "requestid": "1", "command": "SUBS",
                   "SchwabClientCustomerId": "cust", "SchwabClientCorrelId": "corr",
                   "parameters": {"keys": "corr", "fields": "0,1,2,3"}}


def test_response_code_and_heartbeat():
    assert probe.response_code(
        {"response": [{"command": "LOGIN", "content": {"code": 0}}]}, "LOGIN") == 0
    assert probe.response_code({"response": [{"command": "SUBS"}]}, "LOGIN") is None
    assert probe.is_heartbeat({"notify": [{"heartbeat": "1727712345000"}]})
    assert not probe.is_heartbeat({"data": []})


def test_the_probe_sends_no_order_call():
    src = _PATH.read_text()
    for word in ("place_order", "/orders", "preview"):
        assert word not in src
