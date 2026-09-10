"""corpus_duplicate_sweep: keyed duplicate detection across trades, depth and
opra, one clean day and one doubled day per stream. [st-c078]

The depth key exists because mbp-1 rows are NOT trades-shaped: roughly half
are quote-only book snapshots with price/size/sequence all null (measured
2026-09-07), so a trades-style key would silently bucket every quote-only row
sharing a ts_event together. This fixture builds one of each row shape.
"""
import json
from pathlib import Path

import scripts.measurement.corpus_duplicate_sweep as cds

CLEAN_DAY = "2026-01-05"
DOUBLED_DAY = "2026-01-06"


def _trades_row(sec: int, *, seq: int) -> str:
    return json.dumps({
        "ts_pull_utc": "2026-01-05T20:00:00Z",
        "stream": "databento_glbx_es",
        "provenance": {"dataset": "GLBX.MDP3", "schema": "trades",
                       "ts_event": f"2026-01-05T18:00:{sec:02d}.000000000+00:00",
                       "source": "live"},
        "data": {"symbol": "ESH6", "instrument_id": 1, "price": 5000.0 + sec,
                 "size": 1, "side": "A", "action": "T", "sequence": seq, "flags": None},
    })


def _opra_row(sec: int, *, seq: int, instrument_id: int = 100) -> str:
    return json.dumps({
        "ts_pull_utc": "2026-01-05T20:00:00Z",
        "stream": "databento_opra",
        "provenance": {"dataset": "OPRA.PILLAR", "schema": "trades",
                       "ts_event": f"2026-01-05T18:00:{sec:02d}.000000000+00:00"},
        "data": {"symbol": "SPXW  260105P05000000", "instrument_id": instrument_id,
                 "price": 12.0 + sec, "size": 2, "side": "N", "action": "T",
                 "sequence": seq, "flags": 192},
    })


def _depth_quote_row(sec: int, *, bid: float) -> str:
    """A quote-only mbp-1 row: price/size/sequence/action/side all null, only
    the book fields set — this is the row shape a trades-style key cannot
    distinguish (every one shares a null sequence)."""
    return json.dumps({
        "ts_pull_utc": "2026-01-05T20:00:00Z",
        "stream": "databento_glbx_es_mbp1",
        "provenance": {"dataset": "GLBX.MDP3", "schema": "mbp-1",
                       "ts_event": f"2026-01-05T18:00:{sec:02d}.000000000+00:00",
                       "source": "live"},
        "data": {"symbol": "ES.c.0", "instrument_id": 1, "action": None, "side": None,
                 "price": None, "size": None, "bid_px": bid, "ask_px": bid + 0.25,
                 "bid_sz": 10, "ask_sz": 12, "bid_ct": None, "ask_ct": None,
                 "sequence": None, "flags": None},
    })


def _depth_trade_row(sec: int, *, seq: int) -> str:
    """A trade-tagged mbp-1 row: the other half of the real shape, full
    fields including sequence."""
    return json.dumps({
        "ts_pull_utc": "2026-01-05T20:00:00Z",
        "stream": "databento_glbx_es_mbp1",
        "provenance": {"dataset": "GLBX.MDP3", "schema": "mbp-1",
                       "ts_event": f"2026-01-05T18:01:{sec:02d}.000000000+00:00",
                       "source": "live"},
        "data": {"symbol": "ESH6", "instrument_id": 1, "action": "T", "side": "A",
                 "price": 5000.0 + sec, "size": 1, "bid_px": 5000.0, "ask_px": 5000.25,
                 "bid_sz": 9, "ask_sz": 11, "bid_ct": 3, "ask_ct": 4,
                 "sequence": seq, "flags": None},
    })


def _write(day_dir: Path, stem: str, lines: list[str]) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"{stem}.jsonl").write_text("".join(l + "\n" for l in lines))


def _build_corpus(root: Path) -> None:
    """Clean day: 50 distinct rows per stream (no duplicates). Doubled day:
    every row appended a second time (different ts_pull_utc, same identity) —
    a 50% duplicate rate, the same shape st-c078 measured on the real
    defects."""
    clean = root / CLEAN_DAY
    doubled = root / DOUBLED_DAY

    trades_clean = [_trades_row(s, seq=s) for s in range(50)]
    _write(clean, "databento_glbx_es", trades_clean)
    trades_doubled = []
    for s in range(50):
        trades_doubled.append(_trades_row(s, seq=s))
        trades_doubled.append(_trades_row(s, seq=s))
    _write(doubled, "databento_glbx_es", trades_doubled)

    opra_clean = [_opra_row(s, seq=s) for s in range(50)]
    _write(clean, "databento_opra", opra_clean)
    opra_doubled = []
    for s in range(50):
        opra_doubled.append(_opra_row(s, seq=s))
        opra_doubled.append(_opra_row(s, seq=s))
    _write(doubled, "databento_opra", opra_doubled)

    depth_clean = ([_depth_quote_row(s, bid=5000.0 + s) for s in range(25)]
                   + [_depth_trade_row(s, seq=s) for s in range(25)])
    _write(clean, "databento_glbx_es_mbp1", depth_clean)
    depth_doubled = []
    for s in range(25):
        depth_doubled.append(_depth_quote_row(s, bid=5000.0 + s))
        depth_doubled.append(_depth_quote_row(s, bid=5000.0 + s))
    for s in range(25):
        depth_doubled.append(_depth_trade_row(s, seq=s))
        depth_doubled.append(_depth_trade_row(s, seq=s))
    _write(doubled, "databento_glbx_es_mbp1", depth_doubled)


def test_trades_percentages(tmp_path):
    _build_corpus(tmp_path)
    rows = cds.sweep("trades", corpus=tmp_path)
    by_day = {r[0]: r for r in rows}
    assert by_day[CLEAN_DAY][3] == 0.0
    assert by_day[DOUBLED_DAY][1:4] == (100, 50, 50.0)


def test_opra_percentages(tmp_path):
    _build_corpus(tmp_path)
    rows = cds.sweep("opra", corpus=tmp_path)
    by_day = {r[0]: r for r in rows}
    assert by_day[CLEAN_DAY][3] == 0.0
    assert by_day[DOUBLED_DAY][1:4] == (100, 50, 50.0)


def test_depth_percentages_cover_both_row_shapes(tmp_path):
    """The doubled day's quote-only rows (null sequence) and trade-tagged
    rows (real sequence) must BOTH be counted as duplicates — proof the key
    isn't silently trades-shaped."""
    _build_corpus(tmp_path)
    rows = cds.sweep("depth", corpus=tmp_path)
    by_day = {r[0]: r for r in rows}
    assert by_day[CLEAN_DAY][3] == 0.0
    assert by_day[DOUBLED_DAY][1:4] == (100, 50, 50.0)


def test_depth_quote_only_rows_are_not_one_bucket(tmp_path):
    """A trades-shaped key (ts_event, price, size, sequence) would see every
    quote-only row as (ts, None, None, None) — all equal — and call 24 of 25
    of them duplicates. The real key must not do that on a CLEAN day."""
    root = tmp_path
    clean = root / CLEAN_DAY
    _write(clean, "databento_glbx_es_mbp1", [_depth_quote_row(s, bid=5000.0 + s) for s in range(25)])
    rows = cds.sweep("depth", corpus=root)
    day, n, dup, pct = rows[0]
    assert n == 25 and dup == 0


def test_missing_file_is_skipped_and_reported_for_depth_not_trades(tmp_path, capsys):
    root = tmp_path
    only_trades = root / "2026-02-02"
    _write(only_trades, "databento_glbx_es", [_trades_row(0, seq=0)])

    cds.sweep("trades", corpus=root)
    assert "SKIP" not in capsys.readouterr().out

    rows = cds.sweep("depth", corpus=root)
    out = capsys.readouterr().out
    assert rows == []
    assert "2026-02-02  SKIP no databento_glbx_es_mbp1 file" in out


def test_since_filters_days(tmp_path):
    _build_corpus(tmp_path)
    rows = cds.sweep("trades", corpus=tmp_path, since="2026-01-06")
    assert [r[0] for r in rows] == [DOUBLED_DAY]


def test_report_prints_stats(tmp_path, capsys):
    _build_corpus(tmp_path)
    rows = cds.sweep("trades", corpus=tmp_path)
    cds.report(rows)
    out = capsys.readouterr().out
    assert "days scanned: 2" in out
    assert "days over 5%: 1" in out
    assert f"{DOUBLED_DAY}  rows=" in out and "50.0%" in out
