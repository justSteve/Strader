"""Anchored Market Profile page — payload shape and rendered marks. [st-jz12]

The TPO math is covered in ``tests/test_anchored_tpo.py``; this file covers the
script: that ``build`` assembles the payload the HTTP server will hand around,
that ``render_html`` actually carries every mark the page claims (POC, VAH,
VAL, Initial Balance, last, single prints, the three coloured segments), that
the page is self-contained, and that a silence inside CME's maintenance hour is
named as the halt rather than banner-ed as a hole in the capture.

The synthetic tape is one print per (bracket, price row), chosen so every count
below is countable by hand:

    row    0  1  2  3  4  5  6  7  8      (7600 … 7608, 1.0-pt rows)
    TPOs   1  2  5  1  7  3  3  2  1      total 25

so the POC is row 4, the 70% value area is rows 2–6, and row 3 is the one
interior single print (rows 0 and 8 are tails, not singles).
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import anchored_market_profile as amp  # noqa: E402
from market.entities.trade import Trade  # noqa: E402
from market.orderflow.tpo import bracket_start  # noqa: E402

CT = ZoneInfo("America/Chicago")
DAY = date(2026, 9, 9)                                  # a Wednesday
ANCHOR = datetime(2026, 9, 9, 8, 30, tzinfo=CT)
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=CT)           # Thursday, mid-session
BASE = 7600.0

#: bracket index from the anchor -> price rows it printed at.
#: 0–3 are the prior cash session (A–D), 13–15 the overnight (a–c),
#: 48–51 today's cash session (A–D).
TAPE = {
    0: [0, 1, 2], 1: [1, 2], 2: [2, 4], 3: [2, 4],
    13: [4, 5], 14: [4, 5, 6], 15: [4, 5],
    48: [2, 4], 49: [4, 6, 7], 50: [6, 7], 51: [3, 8],
}
EXPECTED_COUNTS = [1, 2, 5, 1, 7, 3, 3, 2, 1]


#: What ``anchor_start`` resolves each anchor to at NOW (Thursday 12:00 CT).
ANCHOR_CT = {
    "prior": datetime(2026, 9, 9, 8, 30, tzinfo=CT),       # Wed cash open
    "overnight": datetime(2026, 9, 9, 17, 0, tzinfo=CT),   # Wed Globex open
    "today": datetime(2026, 9, 10, 8, 30, tzinfo=CT),      # Thu cash open
}


def synthetic_window(rows_by_bracket: dict[int, list[float]],
                     anchor: datetime = ANCHOR) -> list[Trade]:
    out = []
    for idx in sorted(rows_by_bracket):
        start = bracket_start(anchor, idx)
        for j, r in enumerate(rows_by_bracket[idx]):
            out.append(Trade(ts=start + timedelta(minutes=1 + j),
                             symbol="ES.c.0", instrument_id=1,
                             price=BASE + r, size=3))
    return out


def build_payload(monkeypatch, tape=None, **kw) -> dict:
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _start: iter(synthetic_window(tape or TAPE)))
    kw.setdefault("bucket_ticks", 4)
    return amp.build(now_utc=NOW, session_day=DAY, **kw)


@pytest.fixture()
def payload(monkeypatch):
    return build_payload(monkeypatch)


def row_classes(page: str) -> list[set[str]]:
    """Classes on each rendered price row, indexed low price first.

    Rows are emitted high price first (the profile reads like a chart), so the
    list is reversed to line up with ``payload["prices"]``.
    """
    found = re.findall(r'<div class="r ?([^"]*)" title=', page)
    return [set(c.split()) for c in found][::-1]


# ── payload ──────────────────────────────────────────────────────────────────

def test_payload_shape(payload):
    for key in ("v", "symbol", "session_day", "anchor_ct", "end_ct",
                "generated_ct", "bracket_min", "bucket_ticks", "row_pts",
                "n_trades", "n_brackets", "total_tpos", "prices", "counts",
                "counts_by_role", "brackets", "segments", "poc", "poc_row",
                "vah", "vah_row", "val", "val_row", "va_tpos", "va_achieved",
                "singles", "single_rows", "last", "holes"):
        assert key in payload, key
    assert payload["session_day"] == "2026-09-09"
    assert payload["row_pts"] == 1.0
    assert payload["n_brackets"] == len(TAPE)
    assert payload["n_trades"] == sum(len(v) for v in TAPE.values())


def test_payload_is_json_serialisable(payload):
    import json
    assert json.loads(json.dumps(payload))["v"] == 1


# ── the anchor switch ────────────────────────────────────────────────────────

def test_default_anchor_is_the_prior_cash_open(payload):
    assert payload["anchor"] == "prior"
    assert payload["anchor_label"] == "prior RTH open"
    assert payload["anchor_ct"].startswith("2026-09-09T08:30")


@pytest.mark.parametrize("kind", ["prior", "overnight", "today"])
def test_each_anchor_starts_its_window_where_the_shared_helper_says(
        monkeypatch, kind):
    """The timestamp is anchor_start's, not this script's — one definition
    across both profile pages and the server."""
    expected = ANCHOR_CT[kind]
    seen = {}

    def capture(start_utc):
        seen["start"] = start_utc
        return iter(synthetic_window({0: [0, 1], 1: [0, 2]}, anchor=expected))

    monkeypatch.setattr(amp, "trades_from_corpus", capture)
    payload = amp.build(now_utc=NOW, anchor=kind, bucket_ticks=4)
    assert payload["anchor"] == kind
    assert datetime.fromisoformat(payload["anchor_ct"]) == expected
    assert seen["start"] == expected


def test_session_day_pins_only_the_prior_anchor(monkeypatch):
    pin = datetime(2026, 9, 8, 8, 30, tzinfo=CT)
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window({0: [0], 1: [1]},
                                                         anchor=pin)))
    pinned = amp.build(now_utc=NOW, anchor="prior", bucket_ticks=4,
                       session_day=date(2026, 9, 8))
    assert datetime.fromisoformat(pinned["anchor_ct"]) == pin

    # With any other anchor there is no day to pin, so it is ignored.
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window(
                            {0: [0], 1: [1]}, anchor=ANCHOR_CT["today"])))
    other = amp.build(now_utc=NOW, anchor="today", bucket_ticks=4,
                      session_day=date(2026, 9, 8))
    assert datetime.fromisoformat(other["anchor_ct"]) == ANCHOR_CT["today"]


def test_unknown_anchor_is_refused_in_words():
    with pytest.raises(ValueError, match="anchor must be one of"):
        amp.build(now_utc=NOW, anchor="lunchtime")


def test_today_anchor_yields_one_cash_session(monkeypatch):
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter([
                            Trade(ts=datetime(2026, 9, 10, 8, 31, tzinfo=CT),
                                  symbol="ES.c.0", instrument_id=1,
                                  price=BASE, size=1),
                            Trade(ts=datetime(2026, 9, 10, 9, 31, tzinfo=CT),
                                  symbol="ES.c.0", instrument_id=1,
                                  price=BASE + 2, size=1)]))
    payload = amp.build(now_utc=NOW, anchor="today", bucket_ticks=4)
    assert [s["role"] for s in payload["segments"]] == ["today_rth"]
    assert [s["label"] for s in payload["segments"]] == ["A–C"]


def test_overnight_anchor_has_no_prior_cash_segment(monkeypatch):
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter([
                            Trade(ts=datetime(2026, 9, 9, 17, 1, tzinfo=CT),
                                  symbol="ES.c.0", instrument_id=1,
                                  price=BASE, size=1),
                            Trade(ts=datetime(2026, 9, 10, 8, 31, tzinfo=CT),
                                  symbol="ES.c.0", instrument_id=1,
                                  price=BASE + 2, size=1)]))
    payload = amp.build(now_utc=NOW, anchor="overnight", bucket_ticks=4)
    assert [s["role"] for s in payload["segments"]] == ["overnight", "today_rth"]
    # The overnight run opens at 17:00 CT, so its first bracket is "a".
    assert payload["segments"][0]["label"] == "a"
    assert payload["segments"][1]["label"] == "A"


@pytest.mark.parametrize("kind,label", [
    ("prior", "prior RTH open"),
    ("overnight", "overnight (Globex) open"),
    ("today", "today&#x27;s RTH open"),
])
def test_render_names_the_anchor_and_links_the_other_two(monkeypatch, kind, label):
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window({0: [0], 1: [1]},
                                                         anchor=ANCHOR_CT[kind])))
    page = amp.render_html(amp.build(now_utc=NOW, anchor=kind, bucket_ticks=4))
    plain = label.replace("&#x27;", "'")
    assert f"<title>Market Profile" in page
    assert f"({plain})" in page                     # header line names the anchor
    assert f"<b>{kind}</b>" in page                 # the one in force, not a link
    for other in ("prior", "overnight", "today"):
        if other != kind:
            assert f'<a href="?anchor={other}">{other}</a>' in page


def test_main_takes_an_anchor(monkeypatch, capsys):
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window(
                            {0: [0], 1: [1]}, anchor=ANCHOR_CT["today"])))
    assert amp.main(["--anchor", "today", "--bucket-ticks", "4",
                     "--dry-run"]) == 0
    assert "anchored TPO [today]" in capsys.readouterr().out


def test_main_refuses_an_unknown_anchor(capsys):
    with pytest.raises(SystemExit):
        amp.main(["--anchor", "lunchtime", "--dry-run"])


def test_counts_are_the_hand_computed_profile(payload):
    assert payload["prices"] == [BASE + r for r in range(9)]
    assert payload["counts"] == EXPECTED_COUNTS
    assert payload["total_tpos"] == sum(EXPECTED_COUNTS)


def test_poc_value_area_and_single_print(payload):
    assert payload["poc"] == 7604.0 and payload["poc_row"] == 4
    assert (payload["val"], payload["vah"]) == (7602.0, 7606.0)
    assert payload["va_achieved"] >= 0.70
    assert payload["va_tpos"] == sum(
        payload["counts"][payload["val_row"]:payload["vah_row"] + 1])
    # Rows 0 and 8 are single-TPO too, but they are the profile's extremes —
    # tails (excess), not single prints.
    assert payload["single_rows"] == [3]
    assert payload["singles"] == [7603.0]


def test_payload_segments_are_prior_overnight_today(payload):
    assert [s["role"] for s in payload["segments"]] == [
        "prior_rth", "overnight", "today_rth"]
    labels = {s["role"]: s["label"] for s in payload["segments"]}
    assert labels == {"prior_rth": "A–D", "overnight": "a–c", "today_rth": "A–D"}
    # Initial Balance is read per cash session, never for the overnight.
    ibs = {s["role"]: s["ib"] for s in payload["segments"]}
    assert ibs["prior_rth"] == {"low": 7600.0, "high": 7602.0}
    assert ibs["today_rth"] == {"low": 7602.0, "high": 7607.0}
    assert ibs["overnight"] is None


def test_role_counts_partition_the_profile(payload):
    by = payload["counts_by_role"]
    for i, total in enumerate(payload["counts"]):
        assert sum(by[r][i] for r in by) == total
    assert by["prior_rth"][0] == 1 and by["today_rth"][0] == 0
    assert by["overnight"][5] == 3


# ── render ───────────────────────────────────────────────────────────────────

def test_render_carries_the_header_stamps_and_legend(payload):
    page = amp.render_html(payload)
    assert page.startswith("<!doctype html>")
    for mark in ("Market Profile", "08:30 CT", "(prior RTH open)",
                 "generated", "prior cash session", "overnight (Globex)",
                 "today's cash session", "single print",
                 "1 single-print row flagged"):
        assert mark in page, mark
    for value in (payload["poc"], payload["vah"], payload["val"],
                  payload["last"]):
        assert f"{value:g}" in page


def test_render_marks_poc_va_ib_last_and_singles(payload):
    rows = row_classes(amp.render_html(payload))
    assert len(rows) == len(payload["prices"])
    assert "poc" in rows[payload["poc_row"]]
    assert "vah" in rows[payload["vah_row"]] and "val" in rows[payload["val_row"]]
    for i in range(payload["val_row"], payload["vah_row"] + 1):
        assert "va" in rows[i] or "poc" in rows[i]
    assert "sp" in rows[3] and not any("sp" in rows[i] for i in (0, 8))
    # Today's Initial Balance, 7602–7607, drawn on the profile.
    assert "ibl" in rows[2] and "ibh" in rows[7]
    # Last print of the window: bracket 51's final trade, at 7608.
    assert payload["last"] == 7608.0 and "here" in rows[8]


def test_render_stacks_the_bracket_letters_in_time_order(payload):
    page = amp.render_html(payload)
    # Row 4 (the POC) was printed by prior C and D, all three overnight
    # brackets, and today's A and B — in that order, one span per segment.
    assert ('<span class="rp">CD</span>'
            '<span class="ro">abc</span>'
            '<span class="rt">AB</span>') in page
    # Row 3 is a single print from today's D alone.
    assert '<div class="tpo"><span class="rt">D</span></div>' in page


def test_render_labels_whole_points_contiguously(payload):
    page = amp.render_html(payload)
    for price in payload["prices"]:
        assert f'<div class="px">{price:g}</div>' in page


def test_default_row_is_the_classic_one_point_es_row(monkeypatch):
    """Steve's call, 2026-09-10. One point is the row the drill teaches on and
    the only resolution at which a two-session window's letters fit the
    viewport at full size."""
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window(TAPE)))
    payload = amp.build(now_utc=NOW, session_day=DAY)
    assert payload["bucket_ticks"] == 4 and payload["row_pts"] == 1.0


def test_cli_bucket_default_matches_build(monkeypatch, capsys):
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window(TAPE)))
    assert amp.main(["--date", "2026-09-09", "--dry-run"]) == 0
    assert "1pt rows" in capsys.readouterr().out


def test_quarter_point_rows_label_only_whole_points(monkeypatch):
    payload = build_payload(monkeypatch, bucket_ticks=1)
    page = amp.render_html(payload)
    assert payload["row_pts"] == 0.25
    assert '<div class="px">7604</div>' in page
    assert '<div class="px">7604.25</div>' not in page


def test_render_is_self_contained_and_mobile_ready(payload):
    page = amp.render_html(payload)
    assert "http://" not in page and "https://" not in page
    assert "<script src" not in page and "<link " not in page
    assert 'name="viewport"' in page
    assert "@media (max-width:520px)" in page


# ── the tape-silence banner ──────────────────────────────────────────────────

def hole(a: str, b: str, secs: float, halt: bool) -> dict:
    return {"from": a, "to": b, "secs": secs, "halt_only": halt}


def test_no_banner_when_the_tape_is_whole(payload):
    page = amp.render_html(dict(payload, holes=[]))
    assert "Incomplete window" not in page and "Exchange halt" not in page


def test_render_names_the_maintenance_halt(payload):
    page = amp.render_html(dict(payload, holes=[
        hole("2026-09-09T15:59:57-05:00", "2026-09-09T17:00:00-05:00",
             3603.0, True)]))
    assert "Exchange halt" in page and "maintenance halt" in page
    assert "Incomplete window" not in page


def test_render_banners_an_unexplained_silence(payload):
    page = amp.render_html(dict(payload, holes=[
        hole("2026-09-09T10:00:00-05:00", "2026-09-09T13:00:00-05:00",
             10800.0, False)]))
    assert "Incomplete window" in page
    assert "the tape has a hole there" in page


def test_render_banners_the_widest_silence(payload):
    page = amp.render_html(dict(payload, holes=[
        hole("2026-09-09T15:59:57-05:00", "2026-09-09T17:00:00-05:00",
             3603.0, True),
        hole("2026-09-10T01:00:00-05:00", "2026-09-10T06:00:00-05:00",
             18000.0, False)]))
    assert "Incomplete window" in page and "Exchange halt" not in page


def test_build_flags_the_real_halt_boundary(monkeypatch):
    """The 2026-09-09 tape's last print before the bell was 15:59:57 CT.

    A tape this sparse has several silences; only the one that brackets the
    maintenance hour may come back flagged.
    """
    # Brackets 0/1 (cash) and 48/49 (next cash) only — nothing inside 16:00–17:00.
    tape = synthetic_window({0: [0, 1], 1: [0, 1], 48: [2], 49: [2]}) + [
        Trade(ts=datetime(2026, 9, 9, 15, 59, 57, tzinfo=CT), symbol="ES.c.0",
              instrument_id=1, price=BASE + 4, size=1),
        Trade(ts=datetime(2026, 9, 9, 17, 0, 0, tzinfo=CT), symbol="ES.c.0",
              instrument_id=1, price=BASE + 4, size=1)]
    tape.sort(key=lambda t: t.ts)
    monkeypatch.setattr(amp, "trades_from_corpus", lambda _s: iter(tape))
    payload = amp.build(now_utc=NOW, bucket_ticks=4, session_day=DAY)
    halts = [h for h in payload["holes"] if h["halt_only"]]
    assert len(payload["holes"]) > 1 and len(halts) == 1
    assert halts[0]["from"].startswith("2026-09-09T15:59:57")


@pytest.mark.parametrize("a,b,expected", [
    ((15, 59, 57), (17, 0, 0), True),           # the real 2026-09-09 halt
    ((15, 56, 0), (17, 4, 0), True),            # inside the 5-minute pad
    ((15, 30, 0), (17, 0, 0), False),           # half an hour of tape missing
    ((16, 0, 0), (17, 30, 0), False),           # capture came back late
])
def test_halt_only_window(a, b, expected):
    def mk(t):
        return datetime(2026, 9, 9, *t, tzinfo=CT)
    assert amp._halt_only(mk(a), mk(b)) is expected


def test_halt_only_never_spans_days_or_a_weekend():
    a = datetime(2026, 9, 9, 16, 0, tzinfo=CT)
    assert amp._halt_only(a, datetime(2026, 9, 10, 16, 30, tzinfo=CT)) is False
    sat = datetime(2026, 9, 12, 16, 0, tzinfo=CT)
    assert amp._halt_only(sat, datetime(2026, 9, 12, 17, 0, tzinfo=CT)) is False


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_main_dry_run_writes_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window(TAPE)))
    out = tmp_path / "mp.html"
    assert amp.main(["--date", "2026-09-09", "--bucket-ticks", "4",
                     "--dry-run", "--out", str(out)]) == 0
    assert not out.exists()
    assert "anchored TPO" in capsys.readouterr().out


def test_main_writes_the_page(monkeypatch, tmp_path):
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window(TAPE)))
    out = tmp_path / "nested" / "mp.html"
    assert amp.main(["--date", "2026-09-09", "--bucket-ticks", "4",
                     "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_main_never_registers_the_desk_page_unless_asked(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(amp, "trades_from_corpus",
                        lambda _s: iter(synthetic_window(TAPE)))
    monkeypatch.setattr(amp.subprocess, "run",
                        lambda *a, **k: calls.append(a) or pytest.fail(
                            "desk-register must be opt-in"))
    out = tmp_path / "mp.html"
    assert amp.main(["--date", "2026-09-09", "--out", str(out)]) == 0
    assert calls == []


def test_main_returns_nonzero_and_writes_nothing_when_the_source_fails(
        monkeypatch, tmp_path):
    def boom(_start):
        raise RuntimeError("tick corpus holds no ES trades in the anchor window")

    monkeypatch.setattr(amp, "trades_from_corpus", boom)
    out = tmp_path / "mp.html"
    assert amp.main(["--date", "2026-09-09", "--out", str(out)]) == 2
    assert not out.exists()
