"""Emission Review packet tool [st-rf95]."""
from __future__ import annotations

import json
from datetime import date

import pytest

import tools.emission_review as er


def _bar(i, c, d=0, t="2026-10-06T09:00:00-05:00"):
    return {"k": "bar", "i": i, "t0": t, "t1": t, "o": c, "h": c + 1, "l": c - 1,
            "c": c, "v": 2000, "d": d, "nv": 0}


@pytest.fixture
def run_log(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "REPO", tmp_path)
    log = tmp_path / "data" / "derived" / "live-parity"
    log.mkdir(parents=True)
    rows = [
        {"k": "run", "started": "first"},
        _bar(0, 100.0), {"k": "ev", "type": "Old", "reason": "first run", "bar_i": 0},
        {"k": "run", "started": "second"},          # restart replays the day
        *[_bar(i, 100.0 + i, d=10) for i in range(25)],
        {"k": "ev", "type": "SweepPrint", "reason": "buy sweep", "bar_i": 3},
        {"k": "ev", "type": "DeltaDivergence", "reason": "later", "bar_i": 6},
    ]
    (log / "2026-10-01.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    return tmp_path


def test_label_is_index_plus_one_and_last_run_wins(run_log):
    p = er.build(date(2026, 10, 1), 4)          # page "Bar 4" == index 3
    assert p["bar_index"] == 3
    assert [e["type"] for e in p["emissions"]] == ["SweepPrint"]
    assert p["source"] == "run-log" and "NOT in this record" in p["source_note"]


def test_hindsight_measures_from_the_close_and_fences_later_emissions(run_log):
    p = er.build(date(2026, 10, 1), 4)
    h = p["hindsight"]["+5"]
    assert h["close_chg"] == 5.0 and h["max_up"] == 6.0 and h["max_down"] == 0.0
    assert p["hindsight"]["+20"]["close_chg"] == 20.0
    assert [e["bar_label"] for e in p["later_emissions"]] == [7]


def test_short_hindsight_reports_what_is_available(run_log):
    p = er.build(date(2026, 10, 1), 22)
    assert p["hindsight"]["+5"] == {"available": 3}


def test_out_of_range_bar_exits(run_log):
    with pytest.raises(SystemExit):
        er.build(date(2026, 10, 1), 99)


def test_unfilled_card_is_refused_and_filled_one_delivered(run_log, tmp_path):
    p = er.build(date(2026, 10, 1), 4)
    card = tmp_path / "2026-10-01" / "bar-004.md"
    card.parent.mkdir()
    card.write_text(er.card(p))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    with pytest.raises(SystemExit):
        er.deliver(card, inbox)
    assert not list(inbox.iterdir())
    card.write_text(er.card(p).replace(er.UNFILLED, "done"))
    out = er.deliver(card, inbox)
    text = out.read_text()
    assert out.name.endswith("__Strader__emission-review-2026-10-01-bar-004.md")
    assert text.startswith("---\nfrom: Strader\nto: Desk\n")
    assert "expects_reply: false" in text
