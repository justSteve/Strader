"""Golden replay test (st-uqf; spec §5 parity groundwork).

The fixture is a deliberately messy slice of the real 2026-07-02 corpus file:
900 afternoon-pull rows first, 700 morning-pull rows after (mirroring the real
append order), plus 10 injected exact-duplicate rows — and the slice carries
17 natural duplicates of its own. The pinned values below assert the full
reader + builder pipeline: dedup, canonical (ts_event, sequence) sort, and
deterministic bar construction. If an intentional engine change moves these
numbers, regenerate them deliberately and say why in the commit (the st-bw9
harness formalizes that protocol).
"""
import hashlib
from pathlib import Path

import pytest

from market.orderflow.bars import build_bars
from market.orderflow.replay import read_corpus_day

FIXTURE = Path(__file__).parent.parent / "fixtures" / "es_ticks_golden_20260702.jsonl"

# Pinned 2026-07-04 from the fixture's first build (st-uqf).
GOLDEN = {
    "trades": 1583,             # 1610 rows − 10 injected dupes − 17 natural dupes
    "contracts": 3995,
    "first_ts": "2026-07-02T08:30:00.000083-05:00",  # morning row sorts first
    "last_ts": "2026-07-02T13:00:45.976479-05:00",
    "bars": 8,                  # n=500, include_partial=True
    "bar0": dict(open=7555.25, high=7556.25, low=7553.5, close=7554.0,
                 volume=506, delta=-22, none_vol=0, n_cells=12, poc=7555.0),
    "sha256": "8e19f2f5fbba989252ffe767461b46504496752789df0af2d7a7cd2570c23ff0",
}


@pytest.fixture(scope="module")
def trades():
    return read_corpus_day(FIXTURE)


def test_reader_dedups_and_sorts(trades):
    assert len(trades) == GOLDEN["trades"]
    assert trades[0].ts.isoformat() == GOLDEN["first_ts"]
    assert trades[-1].ts.isoformat() == GOLDEN["last_ts"]
    assert sum(t.size for t in trades) == GOLDEN["contracts"]
    # canonical order: ts ascending, sequence breaks ties
    for a, b in zip(trades, trades[1:]):
        assert (a.ts, a.sequence or -1) <= (b.ts, b.sequence or -1)


def test_golden_bars(trades):
    bars = list(build_bars(trades, n=500, include_partial=True))
    assert len(bars) == GOLDEN["bars"]
    b0, g = bars[0], GOLDEN["bar0"]
    assert (b0.open, b0.high, b0.low, b0.close) == (g["open"], g["high"], g["low"], g["close"])
    assert (b0.volume, b0.delta, b0.none_vol) == (g["volume"], g["delta"], g["none_vol"])
    assert len(b0.cells) == g["n_cells"]
    assert b0.poc_price == g["poc"]

    h = hashlib.sha256()
    for b in bars:
        h.update(repr((b.start_ts.isoformat(), b.end_ts.isoformat(), b.open, b.high,
                       b.low, b.close, b.volume, b.delta, b.none_vol,
                       tuple((c.price, c.bid_vol, c.ask_vol) for c in b.cells))).encode())
    assert h.hexdigest() == GOLDEN["sha256"]


def test_straddle_overshoot_bounded(trades):
    bars = list(build_bars(trades, n=500))
    max_size = max(t.size for t in trades)
    assert all(500 <= b.volume < 500 + max_size + 1 for b in bars)


def test_missing_day_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_corpus_day(tmp_path / "nope.jsonl")


# ── engine golden (st-wnc) ───────────────────────────────────────────────────
def test_engine_golden_default_config(trades):
    """Production thresholds on the small fixture: no signals fire (the 100-
    contract floors demand institutional size), but engine state is pinned."""
    import market.orderflow.engine as eng
    e = eng.OrderflowEngine()
    sigs = e.run(trades)
    assert sigs == []
    assert (e.cvd, e.none_vol, e.large_lot_count) == (93, 0, 0)


def test_engine_golden_sensitized(trades, monkeypatch):
    """Thresholds lowered to fixture scale so the signal paths execute and the
    full output is hash-pinned. Regenerate deliberately on intentional engine
    changes (same protocol as the bar golden)."""
    import hashlib
    import market.orderflow.engine as eng
    from market.signals.orderflow import SweepPrint
    monkeypatch.setattr(eng, "SWEEP_MIN_SIZE", 30)
    monkeypatch.setattr(eng, "LARGE_LOT_MIN_SIZE", 20)
    e = eng.OrderflowEngine()
    sigs = e.run(trades)
    assert len(sigs) == 5
    assert sum(isinstance(s, SweepPrint) for s in sigs) == 5
    assert e.large_lot_count == 3
    first = next(s for s in sigs if isinstance(s, SweepPrint))
    assert (first.direction, first.ticks_swept, first.total_size) == ("buy", 3, 49)
    h = hashlib.sha256()
    for s in sigs:
        h.update(repr(s).encode())
    # Repinned 2026-08-26 [st-bkvt]: `repr` covers `reason`, and the sweep's
    # reason now renders from the lexicon — "3 levels" became "3 tick-levels".
    # No engine behaviour moved: the assertions above (count, direction,
    # ticks_swept, total_size, large-lot count) all held across the change,
    # and the regenerated parity snapshot diffs only those five strings.
    assert h.hexdigest() == "aebc15b32f9e29a410c55dcb7ab629be82e05e0019b4f745b78b2b0beba8b002"


# ── imbalance golden (st-su4) ────────────────────────────────────────────────
def test_imbalance_golden(trades):
    from market.orderflow.imbalance import find_imbalances, find_stacks
    bars = list(build_bars(trades, n=500, include_partial=True))
    singles = [(round(p, 2), d, round(r, 2)) for b in bars for p, d, r in find_imbalances(b)]
    assert singles == [(7482.75, "buy", 3.88)]
    assert [s for b in bars for s in find_stacks(b)] == []


# ── profile golden (st-7d6) ──────────────────────────────────────────────────
def test_profile_golden(trades):
    from market.orderflow.profile import build_profile, profile_levels
    prof = build_profile(trades)
    assert (len(prof.prices), prof.total, prof.poc_price) == (78, 3995, 7482.0)
    levels = [(l.reason.split(" @ ")[0], l.price, l.level_type)
              for l in profile_levels(prof, reference_price=7500.0)]
    assert levels == [("POC", 7482.0, "support"),
                      ("HVN", 7555.0, "resistance"),
                      ("LVN", 7556.0, "resistance")]
