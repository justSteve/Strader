"""Tests for the live footprint feeder. [st-re1o]

The headline test is parity: bars built by tailing rows must equal bars built
by read_corpus_day over the same rows. That is the visible half of the spec §5
guarantee — if the live surface and the drill surface can disagree, every rep
Steve has banked against replay stops transferring.

The rest cover the feed edge, which is where live differs from replay at all:
reconnect-boundary disorder and redelivered rows.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market.orderflow.bars import build_bars
from market.orderflow.fill import bar_fill_steps
from market.orderflow.replay import read_corpus_day

CENTRAL = ZoneInfo("America/Chicago")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    path = REPO_ROOT / "scripts" / "live_footprint_feed.py"
    spec = importlib.util.spec_from_file_location("live_footprint_feed", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


feed = _load()
T0 = datetime(2026, 7, 31, 8, 30, 0, tzinfo=CENTRAL)


def _row(i: int, price: float, size: int, side: str = "B", *, ts=None, seq=None):
    ts = ts if ts is not None else T0 + timedelta(milliseconds=100 * i)
    return {
        "ts_pull_utc": "2026-07-31T13:30:00+00:00",
        "stream": "databento_glbx_es",
        "provenance": {"dataset": "GLBX.MDP3", "schema": "trades",
                       "continuous_symbol": "ES.c.0",
                       "ts_event": ts.isoformat(), "source": "live"},
        "data": {"symbol": "ESU6", "instrument_id": 7, "price": price,
                 "size": size, "side": side, "action": "T",
                 "sequence": i if seq is None else seq, "flags": None},
    }


def _synthetic_rows(n=600):
    rows, price = [], 7500.0
    for i in range(n):
        price += (0.25 if i % 3 else -0.25)
        rows.append(_row(i, round(price, 2), 5 + (i % 7),
                         "B" if i % 2 else ("A" if i % 5 else "N")))
    return rows


def _write_day(tmp_path, rows, name="databento_glbx_es.jsonl"):
    p = tmp_path / name
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


# --- parity ----------------------------------------------------------------

def test_feeder_bars_equal_replay_bars(tmp_path):
    rows = _synthetic_rows()
    path = _write_day(tmp_path, rows)
    bar_n = 200

    # Reference: the drill's own path.
    ref_trades = read_corpus_day(path)
    ref_bars = list(build_bars(ref_trades, n=bar_n))
    ref_fill = bar_fill_steps(ref_trades, ref_bars)
    reference = [feed.bar_payload(b, None) | {"steps": s}
                 for b, s in zip(ref_bars, ref_fill)]

    # Live: through the tail + reorder buffer.
    live = _run_feeder(path, bar_n)

    assert len(live) == len(reference) > 3
    assert live == reference


def _run_feeder(path, bar_n, reorder_lag=2.0):
    rows = feed.tail_rows(path, follow=False)
    trades = feed.ordered_trades(rows, reorder_lag_s=reorder_lag)
    buf: list = []

    def tee(it):
        for t in it:
            buf.append(t)
            yield t

    return [feed.bar_payload(b, feed.take_bar_trades(b, buf))
            for b in build_bars(tee(trades), n=bar_n)]


# --- the feed edge ---------------------------------------------------------

def test_reorder_buffer_absorbs_out_of_order_delivery(tmp_path):
    """A reconnect can interleave. build_bars raises on disorder, so the buffer
    must sort it out before the engine ever sees it."""
    rows = _synthetic_rows(400)
    scrambled = list(rows)
    # Swap neighbours across several points, as a redelivery would.
    for i in (50, 120, 250, 310):
        scrambled[i], scrambled[i + 1] = scrambled[i + 1], scrambled[i]
    path = _write_day(tmp_path, scrambled)

    ordered_path = _write_day(tmp_path / "sub", rows) if False else None  # noqa
    live = _run_feeder(path, 200)

    # Same bars as the in-order file — disorder absorbed, nothing raised.
    clean = _write_day(tmp_path, rows, name="clean.jsonl")
    assert live == _run_feeder(clean, 200)


def test_out_of_order_beyond_the_lag_would_raise_without_the_buffer(tmp_path):
    """Guards the guard: with the buffer disabled, the same input raises —
    so the passing test above is not passing by accident."""
    rows = _synthetic_rows(200)
    scrambled = list(rows)
    scrambled[50], scrambled[51] = scrambled[51], scrambled[50]
    path = _write_day(tmp_path, scrambled)

    with pytest.raises(ValueError, match="out-of-order"):
        raw = (feed.trade_from_row(r)[2]
               for r in feed.tail_rows(path, follow=False))
        list(build_bars(raw, n=200))


def test_redelivered_rows_are_deduped(tmp_path):
    rows = _synthetic_rows(400)
    path = _write_day(tmp_path, rows)
    baseline = _run_feeder(path, 200)

    # A reconnect redelivers the last stretch verbatim.
    with_dupes = rows + rows[-60:]
    dup_path = _write_day(tmp_path, with_dupes, name="dupes.jsonl")
    assert _run_feeder(dup_path, 200) == baseline


def test_partial_trailing_line_is_not_parsed_until_complete(tmp_path):
    rows = _synthetic_rows(50)
    p = tmp_path / "partial.jsonl"
    text = "".join(json.dumps(r) + "\n" for r in rows)
    p.write_text(text + '{"data": {"pri', encoding="utf-8")  # mid-write row
    got = list(feed.tail_rows(p, follow=False))
    assert len(got) == len(rows)  # the torn row is held, not mangled


def test_compacted_day_is_read_and_not_followed(tmp_path):
    """The compaction cron will pack days out from under a replay. A .gz cannot
    grow, so following it would spin forever."""
    rows = _synthetic_rows(100)
    raw = "".join(json.dumps(r) + "\n" for r in rows).encode()
    p = tmp_path / "databento_glbx_es.jsonl.gz"
    p.write_bytes(gzip.compress(raw))
    got = list(feed.tail_rows(p, follow=True))  # follow=True must be overridden
    assert len(got) == len(rows)


def test_bar_payload_shape_matches_the_drill_column(tmp_path):
    live = _run_feeder(_write_day(tmp_path, _synthetic_rows()), 200)
    assert set(live[0]) == {
        "t0", "t1", "o", "h", "l", "c", "v", "d", "nv", "dur", "poc",
        "cells", "steps",
    }
    assert len(live[0]["steps"]) == 8          # FILL_STEPS
    assert all(len(c) == 3 for c in live[0]["cells"])
