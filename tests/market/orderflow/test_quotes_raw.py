"""Raw DBN MBP-1 reader (co-qp8cn) — segments built in tmp, nothing committed.

The live collector's JSONL nulls the trade columns on every book row, so the
raw ``.dbn.zst`` archive is the only forward-collected source that can drive
AbsorptionTracker. These tests write small real DBN files with the vendor
library and read them back through ``read_mbp1_raw_segment``.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

dbn = pytest.importorskip("databento_dbn")
pytest.importorskip("databento")

from market.orderflow.quotes import mbp1_raw_segments, read_mbp1_raw_segment  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
T0_NS = 1_789_739_789_000_000_000   # 2026-09-18 13:56:29 UTC = 08:56:29 CT
PX = 1_000_000_000                  # DBN fixed-point: 1e-9


def _mbp1(ns, action, side, price, size, bid, ask, iid=10252, seq=1):
    level = dbn.BidAskPair(bid_px=bid[0], ask_px=ask[0], bid_sz=bid[1], ask_sz=ask[1],
                           bid_ct=3, ask_ct=2)
    return dbn.MBP1Msg(publisher_id=1, instrument_id=iid, ts_event=ns, price=price,
                       size=size, action=action, side=side, depth=0, ts_recv=ns + 10,
                       flags=0, ts_in_delta=0, sequence=seq, levels=level)


def _write_segment(path, records):
    meta = dbn.Metadata(dataset="GLBX.MDP3", start=T0_NS, stype_in=dbn.SType.CONTINUOUS,
                        stype_out=dbn.SType.INSTRUMENT_ID, schema=dbn.Schema.MBP_1,
                        symbols=["ES.c.0"], partial=[], not_found=[], mappings=[])
    path.write_bytes(meta.encode() + b"".join(bytes(r) for r in records))


def test_trade_row_keeps_the_columns_the_jsonl_drops(tmp_path):
    seg = tmp_path / "databento_glbx_es_mbp1.0.dbn"
    _write_segment(seg, [
        _mbp1(T0_NS, dbn.Action.TRADE, dbn.Side.ASK, 7695 * PX + PX // 2, 7,
              bid=(7695 * PX + PX // 2, 26), ask=(7695 * PX + 3 * PX // 4, 18), seq=42),
    ])
    (e,) = list(read_mbp1_raw_segment(seg))
    assert (e.action, e.side, e.price, e.size) == ("T", "A", 7695.5, 7)
    assert (e.bid_px, e.bid_sz, e.ask_px, e.ask_sz) == (7695.5, 26, 7695.75, 18)
    assert (e.bid_ct, e.ask_ct, e.sequence, e.instrument_id) == (3, 2, 42, 10252)
    assert e.ts == datetime(2026, 9, 18, 8, 56, 29, tzinfo=CENTRAL)


def test_symbol_comes_from_the_in_stream_mapping(tmp_path):
    seg = tmp_path / "databento_glbx_es_mbp1.0.dbn"
    quote = dict(action=dbn.Action.MODIFY, side=dbn.Side.NONE, price=7695 * PX, size=1,
                 bid=(7695 * PX, 5), ask=(7695 * PX + PX // 4, 5))
    mapping = dbn.SymbolMappingMsg(
        publisher_id=1, instrument_id=10252, ts_event=T0_NS,
        stype_in=dbn.SType.CONTINUOUS, stype_in_symbol="ES.c.0",
        stype_out=dbn.SType.RAW_SYMBOL, stype_out_symbol="ESZ6",
        start_ts=T0_NS, end_ts=T0_NS)
    _write_segment(seg, [mapping, _mbp1(T0_NS, **quote), _mbp1(T0_NS + 1, iid=999, **quote)])
    mapped, unmapped = list(read_mbp1_raw_segment(seg))
    assert mapped.symbol == "ESZ6"
    assert unmapped.symbol == ""


def test_undefined_prices_become_none(tmp_path):
    seg = tmp_path / "databento_glbx_es_mbp1.0.dbn"
    _write_segment(seg, [
        _mbp1(T0_NS, dbn.Action.CLEAR, dbn.Side.NONE, dbn.UNDEF_PRICE, 0,
              bid=(dbn.UNDEF_PRICE, 0), ask=(7695 * PX, 5)),
    ])
    (e,) = list(read_mbp1_raw_segment(seg))
    assert e.action == "R"
    assert e.price is None and e.bid_px is None and e.ask_px == 7695.0


def test_timestamp_regression_raises(tmp_path):
    seg = tmp_path / "databento_glbx_es_mbp1.0.dbn"
    quote = dict(action=dbn.Action.MODIFY, side=dbn.Side.NONE, price=7695 * PX, size=1,
                 bid=(7695 * PX, 5), ask=(7695 * PX + PX // 4, 5))
    _write_segment(seg, [_mbp1(T0_NS + 1_000, **quote), _mbp1(T0_NS, **quote)])
    with pytest.raises(ValueError, match="regression"):
        list(read_mbp1_raw_segment(seg))


def test_missing_segment_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(read_mbp1_raw_segment(tmp_path / "databento_glbx_es_mbp1.0.dbn.zst"))


def test_empty_segment_yields_nothing(tmp_path):
    seg = tmp_path / "databento_glbx_es_mbp1.3.dbn"
    seg.touch()
    assert list(read_mbp1_raw_segment(seg)) == []


def test_segments_sort_numerically_and_ignore_other_streams(tmp_path):
    for name in ("databento_glbx_es_mbp1.10.dbn.zst", "databento_glbx_es_mbp1.2.dbn.zst",
                 "databento_glbx_es_mbp1.0.dbn.zst", "databento_glbx_es.1.dbn.zst",
                 "databento_glbx_es_mbp1.jsonl.gz"):
        (tmp_path / name).touch()
    assert [p.name for p in mbp1_raw_segments(tmp_path)] == [
        "databento_glbx_es_mbp1.0.dbn.zst",
        "databento_glbx_es_mbp1.2.dbn.zst",
        "databento_glbx_es_mbp1.10.dbn.zst",
    ]


def test_no_segments_is_an_empty_list(tmp_path):
    assert mbp1_raw_segments(tmp_path) == []
    assert mbp1_raw_segments(tmp_path / "absent") == []
