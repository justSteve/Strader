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
from datetime import date as _date, datetime, timedelta, timezone
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


def test_idle_tail_raises_when_the_ct_date_rolls_past_the_pinned_day(tmp_path, monkeypatch):
    """The 2026-08-13 failure, pinned. [st-h510]

    A followed file that stops growing across midnight must fail loudly. The
    real incident ran 21.5 hours in this exact state: the feeder followed the
    previous day's finished file, produced nothing, and the bridge kept serving
    that day's bars behind a page showing the current date.
    """
    rows = _synthetic_rows(10)
    p = _write_day(tmp_path, rows)
    pinned = _date(2026, 8, 12)
    monkeypatch.setattr(feed, "central_date", lambda: _date(2026, 8, 13))

    it = feed.tail_rows(p, follow=True, poll_s=0.01, pinned_day=pinned)
    got = []
    with pytest.raises(feed.DayRolledOver) as e:
        for r in it:
            got.append(r)
    # The tape it already had is delivered first — the guard fires on IDLE, not
    # on open, so a real session's bars are never dropped by it.
    assert len(got) == len(rows)
    assert "2026-08-12" in str(e.value) and "2026-08-13" in str(e.value)


def test_pinned_day_guard_is_silent_while_the_date_still_matches(tmp_path, monkeypatch):
    """The control case: same idle file, same guard, date unchanged -> no raise.

    Without this, a guard that raised unconditionally would pass the test above
    and take the live surface down every session.
    """
    rows = _synthetic_rows(10)
    p = _write_day(tmp_path, rows)
    same = _date(2026, 8, 13)
    monkeypatch.setattr(feed, "central_date", lambda: same)
    # stop_after_idle_s gives the loop a way out that is NOT the rollover guard
    got = list(feed.tail_rows(p, follow=True, poll_s=0.01,
                              stop_after_idle_s=0.05, pinned_day=same))
    assert len(got) == len(rows)


def test_bar_payload_shape_matches_the_drill_column(tmp_path):
    live = _run_feeder(_write_day(tmp_path, _synthetic_rows()), 200)
    # Key-for-key the drill column, "ev" included [st-b0n9]: the emissions
    # panel reads the same field on both surfaces, so a rep drilled on a replay
    # reads the identical thing live. Drifting these apart is the whole failure
    # this assertion exists to catch.
    assert set(live[0]) == {
        "t0", "t1", "o", "h", "l", "c", "v", "d", "nv", "dur", "poc",
        "cells", "steps", "ev",
    }
    assert len(live[0]["steps"]) == 8          # FILL_STEPS
    assert all(len(c) == 3 for c in live[0]["cells"])
    assert isinstance(live[0]["ev"], list)


# --- emissions parity [st-b0n9] --------------------------------------------
# The live surface now carries what the stack emitted, not just bars. The bar
# parity above is only half the guarantee: if the live drive and the batch
# pipeline can disagree about WHAT FIRED, the panel Steve reads mid-session
# stops matching the record he reviews after the close.

def _even_rows(n=600, size=5):
    """Constant-size rows so the tape divides exactly into bars — no trailing
    partial bar, which is the one place live and batch differ by design."""
    rows, price = [], 7500.0
    for i in range(n):
        price += (0.25 if i % 3 else -0.25)
        rows.append(_row(i, round(price, 2), size,
                         "B" if i % 2 else ("A" if i % 5 else "N")))
    return rows


def _anchors():
    from market.orderflow.recognizer import Anchor
    return [Anchor(7500.0, "support", "test-support"),
            Anchor(7520.0, "resistance", "test-resistance")]


def test_live_drive_emits_exactly_what_the_batch_pipeline_emits(tmp_path):
    """StackDriver fed bar-by-bar (the live path) == full_stack_events over the
    same tape (the batch path the replay recorder runs)."""
    from market.orderflow.parity import StackDriver, full_stack_events

    rows = _even_rows(600, size=5)          # 3000 contracts
    bar_n = 100                             # -> 30 exact bars, no partial
    path = _write_day(tmp_path, rows)
    trades = read_corpus_day(path)
    assert sum(t.size for t in trades) % bar_n == 0, "tape must divide evenly"

    batch = full_stack_events(trades, bar_n=bar_n, anchors=_anchors())

    driver = StackDriver(anchors=_anchors())
    live: list = []
    buf: list = []

    def tee(it):
        for t in it:
            buf.append(t)
            yield t

    for bar_i, bar in enumerate(build_bars(tee(iter(trades)), n=bar_n)):
        live += driver.on_bar(bar_i, bar, feed.take_bar_trades(bar, buf))
    live += driver.finish(buf)

    assert live == batch
    assert any(e["bar_i"] is not None for e in live), "tape emitted nothing on bars"


def test_feeder_attaches_emissions_to_the_bar_that_produced_them(tmp_path):
    """`ev` rides ON the bar, and every event in it is stamped with that bar."""
    from market.orderflow.parity import StackDriver

    rows = _even_rows(600, size=5)
    bar_n = 100
    path = _write_day(tmp_path, rows)
    driver = StackDriver(anchors=_anchors())
    trades = read_corpus_day(path)
    buf: list = []

    def tee(it):
        for t in it:
            buf.append(t)
            yield t

    payloads = []
    for bar_i, bar in enumerate(build_bars(tee(iter(trades)), n=bar_n)):
        bt = feed.take_bar_trades(bar, buf)
        payloads.append(feed.bar_payload(bar, bt, driver.on_bar(bar_i, bar, bt)))

    for i, p in enumerate(payloads):
        for e in p["ev"]:
            assert e["bar_i"] == i, f"bar {i} carries an event stamped {e['bar_i']}"
    assert sum(len(p["ev"]) for p in payloads) > 0


def test_end_of_stream_emissions_belong_to_no_bar(tmp_path):
    """finish() carries flush + profile levels, all bar_i=None — the `final`
    channel exists because these cannot be attached to a column."""
    from market.orderflow.parity import StackDriver

    trades = read_corpus_day(_write_day(tmp_path, _even_rows(600, size=5)))
    driver = StackDriver(anchors=_anchors())
    buf: list = []

    def tee(it):
        for t in it:
            buf.append(t)
            yield t

    for bar_i, bar in enumerate(build_bars(tee(iter(trades)), n=100)):
        driver.on_bar(bar_i, bar, feed.take_bar_trades(bar, buf))
    final = driver.finish(buf)

    assert final, "a real tape must yield profile levels at least"
    assert all(e["bar_i"] is None for e in final)
    assert any(e["type"] == "Level" for e in final)


def test_driver_finish_on_an_empty_stream_does_not_raise():
    """A live page can boot, connect, and see no trade at all (pre-open, or a
    dead tape). build_profile raises on zero trades; finish() must not."""
    from market.orderflow.parity import StackDriver

    assert StackDriver(anchors=_anchors()).finish([]) == []


# --- drive_and_publish: `final` lands however the stream ends [st-n0qm.1] ---

class _RecRunLog:
    path = None
    live = False

    def __init__(self):
        self.bars, self.final, self.closed = [], None, False

    def on_bar(self, bar_i, bar, events):
        self.bars.append(bar_i)

    def on_final(self, final):
        self.final = final

    def close(self, **k):
        self.closed = True


def _drive_fixture(tmp_path, n_rows=600, n=100):
    from market.orderflow.parity import StackDriver, live_drive

    trades = read_corpus_day(_write_day(tmp_path, _even_rows(n_rows, size=5)))
    driver = StackDriver(anchors=_anchors())
    pending: list = []

    def tee(it):
        for t in it:
            pending.append(t)
            yield t

    def closed():
        for bar in build_bars(tee(iter(trades)), n=n):
            yield bar, feed.take_bar_trades(bar, pending)

    return driver, pending, live_drive(closed(), driver, None)


def test_drive_and_publish_finalises_on_a_clean_end(tmp_path):
    driver, pending, it = _drive_fixture(tmp_path)
    runlog, pubs = _RecRunLog(), []
    out = feed.drive_and_publish(it, driver, pending, runlog,
                                 lambda b, m, f: pubs.append((len(b), m is not None, f)),
                                 meta={"day": "x"}, push_every_n=2)
    assert out["stopped_by"] == "end-of-stream"
    assert runlog.closed and runlog.final is not None
    assert pubs[0][1] is True, "meta rides on the first push"
    assert pubs[-1][2], "the last publish carries final"
    assert any(e["type"] == "Level" for e in pubs[-1][2])
    assert sum(p[0] for p in pubs) == len(runlog.bars) == out["sent"]


def test_drive_and_publish_finalises_when_the_stream_is_killed_mid_day(tmp_path):
    """The whole Phase-0 point: a SIGTERM (StopFeed) three bars in must still
    flush the engine, write the run-log end, and push `final` — the profile
    levels reach the page even when the process, not the tape, ended the day."""
    driver, pending, it = _drive_fixture(tmp_path)

    def killed():
        for i, item in enumerate(it):
            if i == 3:
                raise feed.StopFeed("signal 15")
            yield item

    runlog, pubs = _RecRunLog(), []
    out = feed.drive_and_publish(killed(), driver, pending, runlog,
                                 lambda b, m, f: pubs.append((len(b), m is not None, f)),
                                 push_every_n=1)
    assert out["stopped_by"] == "StopFeed"
    assert runlog.closed and runlog.final is not None
    assert len(runlog.bars) == 3
    assert pubs[-1][2] is not None and any(e["type"] == "Level" for e in pubs[-1][2])
    assert all(e["bar_i"] is None for e in pubs[-1][2])


def test_drive_and_publish_finalises_then_reraises_day_rollover(tmp_path):
    """Midnight: finalise the old day, then let the exception out so the exit
    is non-zero and the unit's Restart=on-failure starts the new day."""
    driver, pending, it = _drive_fixture(tmp_path)

    def rolled():
        for i, item in enumerate(it):
            if i == 2:
                raise feed.DayRolledOver("CT date moved")
            yield item

    runlog, pubs = _RecRunLog(), []
    with pytest.raises(feed.DayRolledOver):
        feed.drive_and_publish(rolled(), driver, pending, runlog,
                               lambda b, m, f: pubs.append((len(b), m is not None, f)),
                               push_every_n=1)
    assert runlog.closed and runlog.final is not None
    assert pubs[-1][2] is not None, "final published before the re-raise"


def test_drive_and_publish_survives_a_finish_error(tmp_path):
    """driver.finish blowing up must not eat the run log or the batch."""
    driver, pending, it = _drive_fixture(tmp_path)
    driver.finish = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom"))
    runlog, pubs = _RecRunLog(), []
    out = feed.drive_and_publish(it, driver, pending, runlog,
                                 lambda b, m, f: pubs.append((len(b), m is not None, f)),
                                 push_every_n=1000)
    assert runlog.closed and runlog.final == []
    assert out["final"] == [] and pubs and pubs[-1][2] is None
    assert pubs[-1][0] == len(runlog.bars), "the coalesced batch still shipped"


def test_waiting_for_a_missing_file_also_raises_when_the_day_rolls(tmp_path, monkeypatch):
    """A feeder under a unit can start on a day with no corpus file at all
    (weekend, or before capture opens). The wait-for-file branch must honour
    the pinned day too, or it waits forever for a file that will never exist
    while the calendar moves on. [st-n0qm.3]"""
    missing = tmp_path / "databento_glbx_es.jsonl"
    days = iter([_date(2026, 8, 16)] * 3 + [_date(2026, 8, 17)] * 50)
    monkeypatch.setattr(feed, "central_date", lambda: next(days))
    gen = feed.tail_rows(missing, follow=True, poll_s=0.001, pinned_day=_date(2026, 8, 16))
    with pytest.raises(feed.DayRolledOver):
        next(gen)


# --- live basis on the wire [st-n0qm.8] --------------------------------------

def test_closed_bars_carry_the_basis_and_gex_converts_through_it(tmp_path):
    """The feeder samples the basis on every closed bar, stamps `bs`, and hands
    the estimate to GexContext so `touch`/`dflip` are in ES terms."""
    from market.orderflow.basis import BasisEstimator
    from market.orderflow.gex_context import GexContext

    driver, pending, it = _drive_fixture(tmp_path)
    # 1 Hz rows: vendor spot a flat 20 points under the tape for the whole
    # fixture window (rows start at 08:30 CT and run 60 s of wall time).
    t_utc = T0.astimezone(timezone.utc)
    rows = []
    for i in range(0, 90):
        ts = t_utc + timedelta(seconds=i)
        rows.append(json.dumps({"ts_pull_utc": (ts + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
                                "timestamp": int(ts.timestamp()), "ticker": "SPX",
                                "spot": 7480.0, "z_mlgamma": 7506.0, "z_msgamma": 7499.0,
                                "agg_dex": 400.0}))
    p1s = tmp_path / "gexbot_orderflow_1s.jsonl"
    p1s.write_text("".join(r + "\n" for r in rows), encoding="utf-8")
    # one majors poll before the fixture starts, flip at SPX 7480 (= ES ~7500)
    pg = tmp_path / "gexbot.jsonl"
    pg.write_text(json.dumps({
        "ts_pull_utc": (t_utc - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "stream": "gexbot",
        "data": {"summary": {"spot_at_gamma_zero": 7480.0, "major_positive": 7530.0,
                             "major_negative": 7430.0, "major_long_gamma": 7532.0,
                             "major_short_gamma": 7428.0, "one_major_positive": 7570.0,
                             "one_major_negative": 7400.0},
                 "responses": {"/SPX/classic/gex_zero/majors": {
                     "zero_gamma": 7480.0, "net_gex_oi": 1.5e9, "net_gex_vol": 7e8,
                     "spot": 7480.0}}},
        "errors": []}) + "\n", encoding="utf-8")

    pubs: list = []
    feed.drive_and_publish(it, driver, pending, _RecRunLog(),
                           lambda b, m, f: pubs.extend(b), meta={"day": "x"},
                           gex=GexContext(pg, max_age_s=10_000),
                           basis=BasisEstimator(p1s), push_every_n=1)
    bars = [b for b in pubs if "t0" in b]
    assert bars, "fixture produced no closed bars"
    with_bs = [b for b in bars if "bs" in b]
    assert with_bs, "no bar carried a basis"
    b = with_bs[-1]
    import statistics
    # the fixture tape trends, the fake spot is flat: the estimate is the median
    # of close − spot over the last ten closed bars, exactly
    expect = round(statistics.median([x["c"] - 7480.0 for x in bars[-10:]]), 2)
    assert b["bs"]["n"] == min(10, len(bars)) and b["bs"]["pts"] == expect
    # gex on the same bar converted through that basis: flip SPX 7480 → ES ≈ 7500
    assert b["gex"]["basis"] == b["bs"]["pts"]
    assert b["gex"]["dflip"] == round(b["c"] - (7480.0 + b["bs"]["pts"]), 2)
    assert b["gex"]["flip"] == 7480.0, "levels stay SPX on the wire"


def test_bar_payload_omits_bs_when_unknown(tmp_path):
    from market.orderflow.bars import FootprintBar  # noqa: F401 — shape guard only
    bars = list(build_bars(iter(read_corpus_day(_write_day(tmp_path, _synthetic_rows(300)))), n=100))
    p = feed.bar_payload(bars[0], [], bs={"pts": None, "n": 0, "age_s": None})
    assert "bs" not in p
    p2 = feed.bar_payload(bars[0], [], bs={"pts": 20.75, "n": 10, "age_s": 0.4})
    assert p2["bs"] == {"pts": 20.75, "n": 10, "age_s": 0.4}
