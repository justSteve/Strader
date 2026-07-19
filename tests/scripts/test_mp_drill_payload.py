"""Market Profile drill payload assembly (st-3zh)."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import market_profile_drill as mpd  # noqa: E402
from market.entities.trade import Trade  # noqa: E402

DAY = date(2026, 7, 2)


def synthetic_day() -> list[Trade]:
    """Six brackets (A–F), a P-ish day: fast run up in A, acceptance on top.
    Row r = 7400 + r with 1.0-pt rows."""
    rows_per_bracket = [[0, 1, 2, 3, 4, 5], [5, 6, 7], [6, 7, 8],
                        [6, 7, 8], [6, 7], [6, 7, 8]]
    out = []
    for k, rows in enumerate(rows_per_bracket):
        h, m = divmod(8 * 60 + 30 + k * 30, 60)
        for r in rows:
            out.append(Trade(ts=datetime(2026, 7, 2, h, m + 1), symbol="ES.c.0",
                             instrument_id=1, price=7400.0 + r, size=2))
    return out


@pytest.fixture()
def payload(monkeypatch):
    monkeypatch.setattr(mpd, "read_corpus_day", lambda d: synthetic_day())
    return mpd.payload_for(DAY)


def test_payload_shape(payload):
    assert payload["meta"]["n_brackets"] == 6
    assert len(payload["snapshots"]) == 6
    assert len(payload["volume"]) == len(payload["rows"])
    assert payload["rows"] == sorted(payload["rows"])
    letters = [b["letter"] for b in payload["brackets"]]
    assert letters == ["A", "B", "C", "D", "E", "F"]


def test_checkpoints_end_at_last_bracket(payload):
    # C is present, F is the last bracket; I/M don't exist on a 6-bracket day
    assert payload["checkpoints"] == ["C", "F"]


def test_ib_and_truth(payload):
    assert payload["ib"] == {"low": 7400.0, "high": 7407.0}   # A+B rows 0..7
    assert payload["truth"]["day_type"] == "P"
    assert payload["truth"]["why"]


def test_day_type_override(monkeypatch):
    monkeypatch.setattr(mpd, "read_corpus_day", lambda d: synthetic_day())
    p = mpd.payload_for(DAY, day_type="trend")
    assert p["truth"]["day_type"] == "trend"
    assert "heuristic read" in p["truth"]["why"]


def test_snapshots_are_developing(payload):
    # after A the range is rows 0–5; by close the high is row 8
    assert payload["snapshots"][0]["hi"] == 5
    assert payload["snapshots"][-1]["hi"] == 8
    # every snapshot's VA sits inside its range
    for s in payload["snapshots"]:
        assert s["lo"] <= s["val"] <= s["poc"] <= s["vah"] <= s["hi"]


def test_render_injects_marker(tmp_path, payload, monkeypatch):
    tpl = tmp_path / "tpl.html"
    tpl.write_text("<script>const DATA = /*__MP_DRILL_DATA__*/null;</script>")
    monkeypatch.setattr(mpd, "TEMPLATE", tpl)
    out = tmp_path / "out.html"
    mpd.render(payload, out)
    html = out.read_text()
    assert "/*__MP_DRILL_DATA__*/null" not in html
    assert '"n_brackets":6' in html


def test_template_has_marker():
    tpl = ROOT / "scripts/market_profile_drill_template.html"
    if not tpl.exists():
        pytest.skip("template not yet delivered")
    assert mpd.MARKER in tpl.read_text()
