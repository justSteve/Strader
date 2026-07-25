"""Day-browser payload tests against the golden fixture. [st-vrs]"""
from pathlib import Path

from scripts.day_browser import build_payload, day_entry

FIXTURE = Path(__file__).resolve().parent.parent \
    / "market/fixtures/es_ticks_golden_20260702.jsonl"


def test_day_entry_shape_and_consistency():
    e = day_entry(FIXTURE)
    assert e["date"] == "2026-07-02"
    assert e["l"] <= e["o"] <= e["h"] and e["l"] <= e["c"] <= e["h"]
    assert e["n_trades"] > 0 and e["contracts"] > 0
    assert isinstance(e["full_rth"], bool)
    assert isinstance(e["mbp1"], bool)
    # candles: [minuteISO, o, h, l, c, v], chronological, high >= low
    assert e["candles"], "no candles built"
    for iso, o, h, l, c, v in e["candles"]:
        assert h >= l and h >= max(o, c) and l <= min(o, c) and v >= 0
    isos = [k[0] for k in e["candles"]]
    assert isos == sorted(isos)


def test_build_payload_scans_and_sorts(tmp_path):
    for name in ("2026-07-02", "2026-07-01"):
        d = tmp_path / name
        d.mkdir()
        (d / "databento_glbx_es.jsonl").write_bytes(FIXTURE.read_bytes())
    (tmp_path / "not-a-date").mkdir()  # must be skipped, not fatal
    payload = build_payload(root=tmp_path)
    assert [d["date"] for d in payload["days"]] == ["2026-07-02", "2026-07-02"]
