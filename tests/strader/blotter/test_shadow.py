"""The shadow lane on a synthetic day with a driven clock: the journal at real
time, rows through the replay's composer, and the compare that is its
acceptance. [st-uaxf]"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from strader.blotter import shadow as S
from strader.blotter.replay import replay_day
from strader.blotter.rules import load_rules
from strader.marks.estimated import BinFit, Calibration
from tests.helpers.estimated_mark_corpus import write_corpus

DAY = "2026-02-10"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    c = tmp_path_factory.mktemp("corpus")
    write_corpus(c, {DAY: {"drift_per_min": +0.35, "side_bias": 0.7, "opra_from": "15:00"}})
    return c


def _write_snapshot(corpus: Path) -> None:
    cw = [{"strike": float(k), "side": side, "bid": 9.9, "ask": 10.0, "mark": 9.95}
          for k in range(6300, 6600, 5) for side in ("CALL", "PUT")]
    (corpus / DAY / "schwab.jsonl").write_text(json.dumps({
        "ts_pull_utc": "2026-02-10T20:45:05Z", "stage": "close-watch",
        "data": {"spot_spx": 6431.7, "spot_es": 6451.7, "chain_window": cw}}) + "\n")


@pytest.fixture(scope="module")
def cal() -> Calibration:
    fits = {(r, lo): BinFit(r, lo, 0.7, 0.5, 1000, 1000, 50, 0.5, 0.0) for r in ("C", "P") for lo in range(-20, 20, 5)}
    return Calibration(fits=fits, days=("2025-01-02",))


class Clock:
    """A wall clock the test advances: sleeping moves it forward."""

    def __init__(self, start: str):
        self.t = S._at(DAY, start)
        self.sleeps: list[float] = []
        self.hooks: list = []          # (when, fn) — fired once the clock passes `when`

    def now(self) -> datetime:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += timedelta(seconds=s)
        for when, fn in list(self.hooks):
            if self.t >= when:
                fn()
                self.hooks.remove((when, fn))


def test_shadow_waits_fires_records_and_prices(corpus, cal, tmp_path):
    (corpus / DAY / "schwab.jsonl").unlink(missing_ok=True)
    clock = Clock("14:40:00")
    # the close-watch snapshot lands at 14:45:05 wall clock, i.e. after the fire minute closes
    clock.hooks.append((S._at(DAY, "14:46:30"), lambda: _write_snapshot(corpus)))
    rules = load_rules()
    rep = S.run_shadow(DAY, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal, out_dir=tmp_path / "out",
                       now_fn=clock.now, sleep_fn=clock.sleep, events=False)
    phases = [j["phase"] for j in rep.journal]
    assert phases == ["fire", "entry", "close"]
    fire = rep.journal[0]
    assert fire["fire_ct"] == "14:45" and fire["seen_at"].startswith(f"{DAY}T14:46:05")
    assert {a["rule_id"]: a["call"] for a in fire["answers"]} == {"footprint-up-1445": "up", "launch-into-no-lid-1445": "up"}
    entry = rep.journal[1]
    assert entry["source"] == "schwab-snapshot" and entry["snapshot_ct"] == "14:45:05"
    assert entry["seen_at"] >= f"{DAY}T14:46:30" and len(entry["legs"]) == 2 and entry["legs"][0]["ask"] == 10.0
    close = rep.journal[2]
    assert close["seen_at"].startswith(f"{DAY}T15:00:20") and close["n_rows"] == 2
    assert len(rep.rows) == 2 and not rep.unpriced
    for r in rep.rows:
        assert r["lane"] == "shadow" and r["estimated"] and r["exit_reason"] == "time"
        assert r["shadow"]["fired_seen_at"].startswith(f"{DAY}T14:46:05")
        assert r["shadow"]["entry_seen_at"] and r["shadow"]["closed_at"].startswith(f"{DAY}T15:00:20")
        assert r["id"].startswith(f"{DAY}-") and r["entry_ts"] == "14:45:05"
    # the files
    rows_file = S.shadow_rows_path(tmp_path / "out", DAY)
    log_file = S.shadow_log_path(tmp_path / "out", DAY)
    assert len(rows_file.read_text().splitlines()) == 2
    assert [json.loads(l)["phase"] for l in log_file.read_text().splitlines()] == phases
    # the acceptance: the replay reproduces the shadow rows
    out = S.compare(DAY, rep.rows, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal)
    assert out["clean"], out
    assert out["n_shadow"] == out["n_replay"] == 2


def test_shadow_started_after_the_close_prices_at_once(corpus, cal, tmp_path):
    _write_snapshot(corpus)
    clock = Clock("16:30:00")
    rules = load_rules()
    rep = S.run_shadow(DAY, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal, out_dir=tmp_path / "out",
                       now_fn=clock.now, sleep_fn=clock.sleep, events=False)
    assert clock.sleeps == []                      # nothing to wait for
    assert len(rep.rows) == 2
    replay = replay_day(DAY, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal, events=False)
    same = ("rule_id", "fire_ct", "call", "entry_ts", "occ_symbol", "entry_premium_pts", "exit_premium_pts", "pnl_pts")
    for a, b in zip(rep.rows, replay.rows):
        assert {k: a[k] for k in same} == {k: b[k] for k in same}
        assert a["lane"] == "shadow" and b["lane"] == "replay"


def test_no_snapshot_in_time_is_journaled_and_unpriced(corpus, cal, tmp_path):
    (corpus / DAY / "schwab.jsonl").unlink(missing_ok=True)
    clock = Clock("14:46:00")
    rules = load_rules()
    rep = S.run_shadow(DAY, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal, out_dir=tmp_path / "out",
                       now_fn=clock.now, sleep_fn=clock.sleep, events=False, snapshot_wait_s=30, snapshot_poll_s=10)
    entry = next(j for j in rep.journal if j["phase"] == "entry")
    assert entry["source"] is None and "no Schwab snapshot" in entry["note"]
    assert rep.rows == [] and len(rep.unpriced) == 2 and {u["reason"] for u in rep.unpriced} == {"no-entry-source"}
    assert not S.shadow_rows_path(tmp_path / "out", DAY).exists()


def test_compare_names_the_mismatch(corpus, cal, tmp_path):
    _write_snapshot(corpus)
    clock = Clock("16:30:00")
    rules = load_rules()
    rep = S.run_shadow(DAY, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal, out_dir=tmp_path / "out",
                       now_fn=clock.now, sleep_fn=clock.sleep, events=False)
    rows = [dict(r) for r in rep.rows]
    rows[0]["entry_ts"] = "14:47:00"                                   # a shadow that saw a different entry minute
    rows[1]["occ_symbol"] = "SPXW  260210C06400000"
    out = S.compare(DAY, rows, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal)
    assert not out["clean"] and len(out["mismatches"]) == 2
    assert out["mismatches"][0]["differs"] == {"entry_minute": {"shadow": "14:47", "replay": "14:45"}}
    assert "occ_symbol" in out["mismatches"][1]["differs"]
    out2 = S.compare(DAY, rows[:1], rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal)
    assert out2["replay_only"] == [f"{DAY}-launch-into-no-lid-1445-1"]


def test_compare_holds_every_journaled_answer(corpus, cal, tmp_path):
    """The journal is the shadow's side of the compare: rows when there are
    any, and every rule's answer at the fire minute either way (2026-09-11,
    day 1, wrote no rows and the compare must still run)."""
    _write_snapshot(corpus)
    clock = Clock("16:30:00")
    rules = load_rules()
    S.run_shadow(DAY, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal, out_dir=tmp_path / "out",
                 now_fn=clock.now, sleep_fn=clock.sleep, events=False)
    rows, fires = S.read_journal(tmp_path / "out", DAY)
    assert len(rows) == 2 and {(f["rule_id"], f["call"]) for f in fires} == {("footprint-up-1445", "up"), ("launch-into-no-lid-1445", "up")}
    out = S.compare(DAY, rows, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal, shadow_fires=fires)
    assert out["clean"] and out["n_fires"] == 2 and out["fire_mismatches"] == []
    # a day that journaled "no call" for both rules and wrote no rows file
    quiet = tmp_path / "quiet"
    quiet.mkdir()
    S.shadow_log_path(quiet, DAY).write_text(
        json.dumps({"phase": "fire", "fire_ct": "14:45", "day": DAY,
                    "answers": [{"rule_id": r.id, "call": None} for r in rules]}) + "\n"
        + json.dumps({"phase": "close", "day": DAY, "n_calls": 0, "n_rows": 0, "n_unpriced": 0}) + "\n")
    assert not S.shadow_rows_path(quiet, DAY).exists()
    rows, fires = S.read_journal(quiet, DAY)
    assert rows == [] and [f["call"] for f in fires] == [None, None]
    out = S.compare(DAY, rows, rules, corpus=corpus, parsed=tmp_path / "parsed", cal=cal, shadow_fires=fires)
    assert not out["clean"] and out["n_shadow"] == 0 and out["n_replay"] == 2
    assert out["fire_mismatches"][0] == {"rule_id": "footprint-up-1445", "fire_ct": "14:45", "shadow": None, "replay": "up"}
    assert out["replay_only"] == [f"{DAY}-footprint-up-1445-1", f"{DAY}-launch-into-no-lid-1445-1"]
    # a journal that never reached the close is not a day to compare
    open_day = tmp_path / "open"
    open_day.mkdir()
    S.shadow_log_path(open_day, DAY).write_text(json.dumps({"phase": "fire", "fire_ct": "14:45", "day": DAY, "answers": []}) + "\n")
    assert S.read_journal(open_day, DAY) is None
    assert S.read_journal(tmp_path / "nowhere", DAY) is None
