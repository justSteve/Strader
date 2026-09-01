"""Pins for the GexBot WebSocket probe's pure functions. [st-8qqw]

The socket half cannot be tested without a live Quant key inside RTH, and the
entitlement lapses 2026-09-06 — so everything that CAN be pinned is pinned here,
because after that date a regression in this file could never be caught by
running it.

Two of these guard real hazards rather than arithmetic:

  - `redact` runs on every path to disk. The negotiate response embeds a bearer
    token in six hub URLs; an artifact directory is not a secret store.
  - `hub_for_group` splits group names. Tickers themselves contain underscores
    (`ES_SPX_orderflow_orderflow`), so the obvious `split("_")` index arithmetic
    is wrong and silently picks the wrong hub.
"""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone

import pytest

from scripts.gexbot_ws_probe import (
    CT,
    _histogram,
    bearer,
    hub_for_group,
    in_rth,
    read_varint,
    redact,
    spacings,
    walk_protobuf,
)

HUBS = {
    "classic": "wss://ws.gex.bot:443/client/hubs/classic?access_token=AAA",
    "state_gex": "wss://ws.gex.bot:443/client/hubs/state_gex?access_token=BBB",
    "state_greeks_zero": "wss://ws.gex.bot:443/client/hubs/state_greeks_zero?access_token=CCC",
    "state_greeks": "wss://ws.gex.bot:443/client/hubs/state_greeks?access_token=DDD",
    "state_greeks_one": "wss://ws.gex.bot:443/client/hubs/state_greeks_one?access_token=EEE",
    "orderflow": "wss://ws.gex.bot:443/client/hubs/orderflow?access_token=FFF",
}


# ------------------------------------------------------------- redaction ----

def test_redact_strips_token_from_hub_url():
    out = redact(HUBS["classic"])
    assert "AAA" not in out
    assert out.endswith("access_token=<REDACTED>")
    # The URL itself is worth keeping — only the credential goes.
    assert "wss://ws.gex.bot:443/client/hubs/classic" in out


def test_redact_handles_every_url_in_one_blob():
    import json

    blob = json.dumps({"websocket_urls": HUBS})
    out = redact(blob)
    for secret in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
        assert f"access_token={secret}" not in out
    assert out.count("<REDACTED>") == 6


def test_redact_stops_at_the_delimiter_not_the_end_of_string():
    out = redact("wss://h?access_token=SECRET&hub=classic")
    assert "SECRET" not in out
    assert "&hub=classic" in out


def test_redact_is_a_noop_on_clean_text():
    assert redact("no credential here") == "no credential here"


# ------------------------------------------------------------------ auth ----

def test_bearer_adds_the_vendor_prefix():
    assert bearer("abc123") == "Bearer gexbot_custom_abc123"


def test_bearer_does_not_double_an_already_prefixed_key():
    assert bearer("gexbot_custom_abc123") == "Bearer gexbot_custom_abc123"


# -------------------------------------------------------- hub resolution ----

@pytest.mark.parametrize(
    "group,expected",
    [
        ("SPX_state_gamma_zero", "state_greeks_zero"),
        ("SPX_state_gamma_one", "state_greeks_one"),
        ("SPX_state_vanna_zero", "state_greeks_zero"),
        ("SPX_state_charm_one", "state_greeks_one"),
        ("SPX_classic_gex_full", "classic"),
        ("SPX_classic_gex_zero", "classic"),
        ("SPX_state_gex_full", "state_gex"),
    ],
)
def test_hub_for_group_maps_categories(group, expected):
    hub, url = hub_for_group(group, HUBS)
    assert hub == expected
    assert url == HUBS[expected]


def test_hub_for_group_survives_an_underscored_ticker():
    """ES_SPX is one ticker. Index arithmetic on split('_') gets this wrong."""
    hub, url = hub_for_group("ES_SPX_orderflow_orderflow", HUBS)
    assert hub == "orderflow"
    assert url == HUBS["orderflow"]


def test_hub_for_group_rejects_a_group_naming_no_package():
    with pytest.raises(ValueError, match="names no package"):
        hub_for_group("SPX_nonsense_thing", HUBS)


def test_hub_for_group_reports_an_unauthorized_hub_rather_than_keyerror_noise():
    """After 2026-09-06 the State key authorizes nothing; the message must say so."""
    with pytest.raises(KeyError, match="outside the entitlement"):
        hub_for_group("SPX_state_gamma_zero", {"classic": HUBS["classic"]})


# ---------------------------------------------------------- RTH gatekeeper ----

def _ct(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=CT)


@pytest.mark.parametrize(
    "when,expected",
    [
        (_ct(2026, 9, 1, 8, 30), True),    # exactly the open
        (_ct(2026, 9, 1, 15, 0), True),    # exactly the close
        (_ct(2026, 9, 1, 8, 29), False),   # one minute early
        (_ct(2026, 9, 1, 15, 1), False),   # one minute late
        (_ct(2026, 9, 1, 12, 0), True),    # Tuesday midday
        (_ct(2026, 9, 5, 12, 0), False),   # Saturday
        (_ct(2026, 9, 6, 12, 0), False),   # Sunday
    ],
)
def test_in_rth_window(when, expected):
    assert in_rth(when) is expected


def test_in_rth_converts_from_utc_rather_than_reading_the_clock_naively():
    """14:00 UTC is 09:00 CT — inside. The same wall number in CT is not."""
    assert in_rth(datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)) is True
    assert in_rth(datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)) is False


# ------------------------------------------------------------ wire format ----

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(num: int, wire: int) -> bytes:
    return _varint((num << 3) | wire)


def test_read_varint_single_and_multibyte():
    assert read_varint(b"\x01", 0) == (1, 1)
    assert read_varint(_varint(300), 0) == (300, 2)
    assert read_varint(_varint(2**35), 0)[0] == 2**35


def test_read_varint_refuses_truncation():
    with pytest.raises(ValueError, match="truncated varint"):
        read_varint(b"\x80\x80", 0)


def test_read_varint_refuses_an_overlong_encoding():
    with pytest.raises(ValueError, match="longer than 64 bits"):
        read_varint(b"\x80" * 12 + b"\x01", 0)


def test_walk_protobuf_recovers_field_numbers_and_types():
    msg = (
        _field(1, 0) + _varint(1777492800)          # timestamp
        + _field(2, 2) + _varint(3) + b"SPX"        # ticker
        + _field(3, 1) + struct.pack("<d", 6890.5)  # spot
        + _field(4, 5) + struct.pack("<f", 1.25)
    )
    out = walk_protobuf(msg)
    assert out["ok"] is True
    assert out["consumed"] == len(msg)
    assert set(out["fields"]) == {1, 2, 3, 4}
    assert out["fields"][1]["wire_type"] == 0
    assert out["fields"][1]["sample"] == 1777492800
    assert out["fields"][2]["sample_len"] == 3
    assert out["fields"][3]["sample"] == pytest.approx(6890.5)
    assert out["fields"][4]["sample"] == pytest.approx(1.25)


def test_walk_protobuf_counts_repeated_fields():
    msg = (_field(7, 0) + _varint(1)) * 5
    out = walk_protobuf(msg)
    assert out["ok"] is True
    assert out["fields"][7]["count"] == 5


def test_walk_protobuf_rejects_a_length_that_overruns():
    msg = _field(1, 2) + _varint(50) + b"short"
    out = walk_protobuf(msg)
    assert out["ok"] is False
    assert "overruns" in out["error"]


def test_walk_protobuf_rejects_deprecated_group_wire_types():
    out = walk_protobuf(_field(1, 3))
    assert out["ok"] is False
    assert "unsupported wire type 3" in out["error"]


def test_walk_protobuf_rejects_field_number_zero():
    out = walk_protobuf(_varint(0) + b"\x01")
    assert out["ok"] is False
    assert "field number 0" in out["error"]


def test_walk_protobuf_rejects_random_bytes():
    """The detector half: noise must not read as a well-formed message.

    This is what makes 'N of M payloads walk cleanly' evidence rather than
    coincidence, so it is worth pinning that noise fails.
    """
    noise = bytes(range(256)) * 4
    assert walk_protobuf(noise)["ok"] is False


def test_walk_protobuf_accepts_an_empty_message():
    out = walk_protobuf(b"")
    assert out["ok"] is True
    assert out["fields"] == {}


# --------------------------------------------------------------- spacing ----

def test_spacings_are_differences_not_absolutes():
    rows = [{"t_mono": 0.0}, {"t_mono": 1.0}, {"t_mono": 3.5}]
    assert spacings(rows) == [1.0, 2.5]


def test_spacings_of_a_single_frame_is_empty():
    assert spacings([{"t_mono": 0.0}]) == []


def test_histogram_buckets_to_whole_seconds_with_sub_second_first():
    hist = _histogram([0.4, 0.9, 1.2, 1.8, 2.1, 3.0])
    assert hist["<1s"] == 2
    assert hist["1s"] == 2
    assert hist["2s"] == 1
    assert hist["3s"] == 1
    assert list(hist)[0] == "<1s"


# ------------------------------------------------------- envelope unwrap ----
# Added 2026-09-01 after the first two sessions reported every frame
# "uncompressed", which read as falsifying the vendor's documented
# "Zstandard-compressed Protocol Buffers". The vendor was right: the frame is a
# plain protobuf envelope and the zstd sits one level in, where a frame-level
# magic check cannot see it. These pin the corrected shape.

def _zstd(blob: bytes) -> bytes:
    import zstandard
    return zstandard.ZstdCompressor().compress(blob)


def _envelope(type_name: bytes, inner: bytes) -> bytes:
    return (_field(1, 2) + _varint(len(type_name)) + type_name
            + _field(2, 2) + _varint(len(inner)) + inner)


def test_unwrap_reads_the_envelope_and_decompresses_the_inner_message():
    from scripts.gexbot_ws_probe import unwrap

    message = _field(1, 0) + _varint(1788269524) + _field(2, 2) + _varint(3) + b"SPX"
    frame = _envelope(b"proto.greek", _zstd(message))
    raw, how, name = unwrap(frame)
    assert how == "envelope+zstd"
    assert name == "proto.greek"
    assert raw == message


def test_unwrap_does_not_call_an_envelope_uncompressed():
    """The exact regression: a frame whose zstd is one level in."""
    from scripts.gexbot_ws_probe import unwrap

    frame = _envelope(b"proto.greek", _zstd(b"\x08\x01"))
    assert unwrap(frame)[1] != "uncompressed"


def test_unwrap_still_handles_a_bare_zstd_frame():
    from scripts.gexbot_ws_probe import unwrap

    raw, how, name = unwrap(_zstd(b"\x08\x01"))
    assert how == "zstd-frame"
    assert raw == b"\x08\x01"
    assert name is None


def test_unwrap_leaves_a_plain_message_alone():
    from scripts.gexbot_ws_probe import unwrap

    plain = _field(1, 0) + _varint(7)
    assert unwrap(plain) == (plain, "uncompressed", None)


def test_walk_recurses_into_a_nested_message():
    inner = _field(1, 0) + _varint(42)
    outer = _field(3, 2) + _varint(len(inner)) + inner
    out = walk_protobuf(outer)
    assert out["ok"] is True
    assert out["fields"][3]["message"][1]["sample"] == 42


def test_walk_reports_ascii_payloads_as_text():
    msg = _field(1, 2) + _varint(11) + b"proto.greek"
    out = walk_protobuf(msg)
    assert out["fields"][1]["sample_text"] == "proto.greek"


def test_walk_recursion_is_depth_capped():
    """A long ASCII string can parse as a plausible message by chance."""
    inner = _field(1, 0) + _varint(1)
    nested = inner
    for _ in range(6):
        nested = _field(1, 2) + _varint(len(nested)) + nested
    out = walk_protobuf(nested, max_depth=2)
    assert out["ok"] is True
    depth = 0
    node = out["fields"][1]
    while "message" in node:
        depth += 1
        node = node["message"][1]
    assert depth <= 2
