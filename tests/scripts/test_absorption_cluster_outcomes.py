"""Absorption-cluster outcomes (co-qp8cn): the log parser and the price path."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market.entities.trade import Trade
from scripts.measurement import absorption_cluster_outcomes as aco

CENTRAL = ZoneInfo("America/Chicago")
LINE = ("10:25 CT  EVENT ABSORPTION-CLUSTER START sig=alert bars=2 from=10:24 to=10:25 "
        "vol=2782 delta=-168 effort_pct=82+ effect_pct=7-\n")


def test_parser_reads_one_firing_per_day_and_minute(tmp_path):
    a = tmp_path / "2026-08-25.log"
    a.write_text("noise\n" + LINE + LINE)
    b = tmp_path / "2026-08-25-again" / "log.txt"
    b.parent.mkdir()
    b.write_text(LINE)
    (f,) = aco.firings([a, b])
    assert (f["date"], f["from"], f["to"], f["vol"], f["delta"]) == ("2026-08-25", "10:24", "10:25", 2782, -168)


def _t(day, hh, mm, ss, px):
    return Trade(ts=datetime(2026, 8, 25, hh, mm, ss, tzinfo=CENTRAL), symbol="ESU6",
                 instrument_id=1, price=px, size=1, side="N")


def test_outcome_marks_broke_on_the_attacked_side_only():
    f = {"date": "2026-08-25", "fired_at": "10:25", "bars": 2, "from": "10:24", "to": "10:25",
         "vol": 100, "delta": -50, "effort_pct": 90, "effect_pct": 5, "log": "x"}
    trades = [_t(0, 10, 24, 5, 7680.0), _t(0, 10, 25, 30, 7681.0),      # cluster: 7680-7681
              _t(0, 10, 27, 0, 7683.0), _t(0, 10, 40, 0, 7690.0),      # above: not a break of the bid
              _t(0, 10, 50, 0, 7679.75)]                               # below the low: broke
    r = aco.outcome(f, trades)
    assert (r["cluster_low"], r["cluster_high"], r["attacked_side"]) == (7680.0, 7681.0, "bid")
    assert r["path"]["5"]["change_pts"] == 2.0 and r["path"]["15"]["change_pts"] == 9.0
    assert r["path"]["30"]["change_pts"] == -1.25
    assert (r["result_30m"], r["broke_at"], r["broke_by_pts"]) == ("broke", "10:50:00", 0.25)

    r2 = aco.outcome(f, trades[:4])
    assert r2["result_30m"] == "held" and r2["broke_by_pts"] == 0.0


def test_outcome_without_trades_in_the_window_is_an_error():
    f = {"date": "2026-08-25", "fired_at": "10:25", "bars": 2, "from": "10:24", "to": "10:25",
         "vol": 100, "delta": -50, "effort_pct": 90, "effect_pct": 5, "log": "x"}
    assert "error" in aco.outcome(f, [_t(0, 11, 0, 0, 7680.0)])
