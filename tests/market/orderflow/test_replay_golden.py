"""Golden replay test (st-uqf; spec §5 parity groundwork).

The fixture is a deliberately messy slice of the real 2026-07-02 corpus file:
900 afternoon-pull rows first, 700 morning-pull rows after (mirroring the real
append order), plus 10 injected re-delivered copies (written by a later pull,
11:45 vs 11:30) — and 17 rows that share a (sequence, ts_event) with a
neighbour. Those 17 are NOT duplicates: they are the other fills of one match
event, written together — one key carries 22 at 7481.00, 25 at 7481.25 and 19
at 7481.50, a sweep. Until 2026-10-01 this test pinned them as dropped
(st-exmw); the reader now keeps them and drops only the later-pulled copies. The pinned values below assert the full
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
    # Repinned 2026-10-01 [st-exmw]: 1610 rows − 10 re-delivered copies. The
    # 17 match-event fills the old key dropped are kept (+176 contracts).
    "trades": 1600,
    "contracts": 4171,
    "first_ts": "2026-07-02T08:30:00.000083-05:00",  # morning row sorts first
    "last_ts": "2026-07-02T13:00:45.976479-05:00",
    "bars": 9,                  # n=500, include_partial=True
    "bar0": dict(open=7555.25, high=7556.25, low=7554.0, close=7554.0,
                 volume=509, delta=35, none_vol=0, n_cells=10, poc=7555.0),
    "sha256": "79182e421a966be6493d9910fdf893fcbd8040fa4c680d8367af88bc894d3293",
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
    assert (e.cvd, e.none_vol, e.large_lot_count) == (163, 0, 0)


def test_engine_golden_sensitized(trades, monkeypatch):
    """Thresholds lowered to fixture scale so the signal paths execute and the
    full output is hash-pinned. Regenerate deliberately on intentional engine
    changes (same protocol as the bar golden)."""
    import hashlib
    import market.orderflow.engine as eng
    from market.signals.orderflow import SweepPrint
    monkeypatch.setattr(eng, "SWEEP_MIN_SIZE", 30)
    # fixture scale, as above — the synthetic tape has no dominant prints
    monkeypatch.setattr(eng, "SWEEP_MAX_SPAN_MS", 10**9)
    monkeypatch.setattr(eng, "SWEEP_MIN_CONCENTRATION", 0.0)
    monkeypatch.setattr(eng, "LARGE_LOT_MIN_SIZE", 20)
    e = eng.OrderflowEngine()
    sigs = e.run(trades)
    assert len(sigs) == 8
    assert sum(isinstance(s, SweepPrint) for s in sigs) == 8
    assert e.large_lot_count == 4
    first = next(s for s in sigs if isinstance(s, SweepPrint))
    assert (first.direction, first.levels_swept, first.total_size) == ("buy", 3, 49)
    # the sweep the old dedup erased: one match event's fills at three prices
    assert any(s.level_sizes == ((7481.0, 25), (7481.25, 25), (7481.5, 19))
               for s in sigs if isinstance(s, SweepPrint))
    h = hashlib.sha256()
    for s in sigs:
        h.update(repr(s).encode())
    # Repinned 2026-08-26 [st-bkvt]: `repr` covers `reason`, and the sweep's
    # reason now renders from the lexicon — "3 levels" became "3 tick-levels".
    # No engine behaviour moved: the assertions above (count, direction,
    # levels_swept, total_size, large-lot count) all held across the change,
    # and the regenerated parity snapshot diffs only those five strings.
    #
    # Repinned 2026-08-27: SweepPrint gained span_ms and concentration, the two
    # fields that make its own docstring ("one aggressor ... near-instantly")
    # checkable. PROVEN additive rather than argued: stripping those two fields
    # from each repr reproduces the 08-26 hash above byte for byte
    # (aebc15b3...), and the five behavioural assertions all still hold. The
    # production gates are relaxed to fixture scale here, so this golden pins
    # serialization, not the new rule — the rule's evidence is the re-emission
    # diff over archived tape.
    #
    # Repinned 2026-09-30 [st-r6ni, st-hnl7]: ``ticks_swept`` renamed
    # ``levels_swept``; SweepPrint gained ``level_sizes``; and a price now
    # counts only when it carries size (5 contracts and 2.5% of the run). Two
    # of the five fixture sweeps each carried a dust price (4 contracts at
    # 7555.75, 2 at 7557.75 — both under 5) and now count 3 prices,
    # not 4 — confidence 0.67 -> 0.50, reason "4" -> "3 tick-levels". The
    # other three are unchanged but for the rename and the new field. All five
    # still fire; the behavioural assertions above hold.
    #
    # Repinned 2026-10-01 [st-exmw]: the reader keeps every fill of a match
    # event (the old (sequence, ts_event) dedup dropped them). Three sweeps
    # appear that the short tape hid, asserted by name above; the five before
    # are unchanged.
    assert h.hexdigest() == "5a50c2f19b40cc90645d8fe185ab4338ab96d21453eccef4cf3bf5ab6f8c246c"


# ── imbalance golden (st-su4) ────────────────────────────────────────────────
def test_imbalance_golden(trades):
    from market.orderflow.imbalance import find_imbalances, find_stacks
    bars = list(build_bars(trades, n=500, include_partial=True))
    singles = [(round(p, 2), d, round(r, 2)) for b in bars for p, d, r in find_imbalances(b)]
    # 2026-10-01 [st-exmw]: the one imbalance pinned here (7482.75 buy 3.88)
    # was an artifact of the short tape; with the match-event fills kept the
    # ask side there is no longer >= 3x the diagonal bid.
    assert singles == []
    assert [s for b in bars for s in find_stacks(b)] == []


# ── profile golden (st-7d6) ──────────────────────────────────────────────────
def test_profile_golden(trades):
    from market.orderflow.profile import build_profile, profile_levels
    prof = build_profile(trades)
    assert (len(prof.prices), prof.total, prof.poc_price) == (78, 4171, 7482.0)
    levels = [(l.reason.split(" @ ")[0], l.price, l.level_type)
              for l in profile_levels(prof, reference_price=7500.0)]
    assert levels == [("POC", 7482.0, "support"),
                      ("HVN", 7555.0, "resistance"),
                      ("LVN", 7556.0, "resistance")]


def test_match_event_fills_are_kept_and_later_copies_dropped(tmp_path):
    """The identity rule itself [st-exmw]: rows sharing (sequence, ts_event)
    written in one pull are distinct fills; the same key written by a later
    pull is a re-delivered copy."""
    import json
    def row(price, size, pulled):
        return {"ts_pull_utc": pulled, "stream": "databento_glbx_es",
                "provenance": {"ts_event": "2026-08-21T14:05:01.900000+00:00",
                               "source": "live"},
                "data": {"symbol": "ESU6", "instrument_id": 1, "price": price,
                         "size": size, "side": "B", "action": "T", "sequence": 7}}
    rows = [row(7685.0, 5, "2026-08-21T14:05:02Z"), row(7685.25, 5, "2026-08-21T14:05:02Z"),
            row(7685.25, 2, "2026-08-21T14:05:02Z"),
            row(7685.0, 5, "2026-08-21T14:09:40Z")]     # a reconnect's replay
    p = tmp_path / "es.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    got = read_corpus_day(p)
    assert [(t.price, t.size) for t in got] == [(7685.0, 5), (7685.25, 5), (7685.25, 2)]
