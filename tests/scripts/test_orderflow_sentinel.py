"""Sentinel day boundary, vendor first-row skips, health file, replay runner.
[st-n0qm.1 — Watcher V2 Phase 0, plan §5]

What these cover, and why each is a test rather than a note:

* The old loop reset only `path, offset` at the CT day boundary, so day 1's
  identity window judged day 2's first rows. On 2026-08-14 that produced an
  `approach` at 13:30:04Z — four seconds after the open, before the window
  could hold MIN_ROWS rows. `SentinelState.rollover` rebuilds the watches.
* The vendor's first rows of a day are not market rows: 08-14 row 1 carried a
  `timestamp` 17.5 h behind its `ts_pull_utc` (the prior close snapshot) and
  row 2 was a zeroed reset (`z_mlgamma == z_msgamma == 7535`, `agg_dex == 0`);
  08-13 row 1 was the zeroed reset. `row_verdict` names both shapes.
* Replayed over 08-10..14 the two rules skipped exactly those three rows and
  nothing else (0/0/0/1/2 per day) — the Risk 11 measurement, repeated here on
  a synthetic two-day tape so the rule cannot widen unnoticed.
* The health file is the sentinel's own liveness evidence; it must be atomic
  and carry the counters.

No sleeping loop, no network: `SentinelState` and `replay_file` are driven
directly, `_emit` is captured.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.orderflow_sentinel as ofs


# --- fixtures ---------------------------------------------------------------

@pytest.fixture
def emitted(monkeypatch):
    """Capture every alert instead of appending to the live file."""
    out: list[dict] = []
    monkeypatch.setattr(ofs, "_emit", lambda a: out.append(a))
    return out


def _row(pull: str, ts: int, spot: float, ml: float, ms: float, dex: float = -100.0,
         **extra) -> dict:
    r = {"ts_pull_utc": pull, "timestamp": ts, "spot": spot,
         "z_mlgamma": ml, "z_msgamma": ms, "agg_dex": dex}
    r.update(extra)
    return r


# 2026-08-14 13:30:02Z as an epoch second — the vendor timestamps are epoch s.
T0 = 1_786_714_202


def _market_rows(n: int, *, day: str, start_s: int, spot: float, ml: float, ms: float):
    """n well-formed rows one second apart."""
    for i in range(n):
        s = start_s + i
        hh, mm, ss = 13, 30 + (i + 2) // 60, (i + 2) % 60
        yield _row(f"{day}T{hh:02d}:{mm:02d}:{ss:02d}Z", s, spot, ml, ms)


# --- row_verdict ------------------------------------------------------------

def test_reset_row_is_skipped_as_reset():
    # 08-14 row 2, verbatim shape: both majors on the same 5-pt strike, DEX 0.
    r = _row("2026-08-14T13:30:04Z", T0 + 2, 7806.6, 7535, 7535, dex=0)
    assert ofs.row_verdict(r) == "reset"


def test_stale_row_is_skipped_as_stale():
    # 08-14 row 1: vendor timestamp is 08-13T19:59:59Z, pulled 08-14T13:30:02Z.
    r = _row("2026-08-14T13:30:02Z", 1_786_651_199, 7798.86, 7806.13, 7799.77, dex=400.08)
    assert ofs.row_verdict(r) == "stale"


def test_market_row_is_not_skipped():
    r = _row("2026-08-14T13:30:05Z", T0 + 3, 7805.29, 7759.64, 7835.78, dex=-51.68)
    assert ofs.row_verdict(r) is None


def test_stale_and_zeroed_reads_as_reset_and_anomaly_wins():
    both = _row("2026-08-14T13:30:04Z", 1_786_651_199, 7806.6, 7535, 7535, dex=0)
    assert ofs.row_verdict(both) == "reset"
    assert ofs.row_verdict({**both, "anomaly": "http 502"}) == "anomaly"


def test_equal_levels_alone_are_not_a_reset():
    """The reset signature needs BOTH halves; two coincident levels with real
    DEX are a market row (rare, but the rule must not eat it)."""
    r = _row("2026-08-14T13:40:00Z", T0 + 600, 7800.0, 7800.0, 7800.0, dex=-12.5)
    assert ofs.row_verdict(r) is None


def test_slightly_late_vendor_timestamp_is_fine():
    """Normal rows trail the pull by a second or two; only STALE_ROW_S+ is stale."""
    pull = "2026-08-14T13:40:00Z"
    pull_s = int(ofs._pull_epoch(pull))
    r = _row(pull, pull_s - 3, 7800.0, 7790.0, 7810.0)
    assert ofs.row_verdict(r) is None
    r2 = _row(pull, pull_s - ofs.STALE_ROW_S, 7800.0, 7790.0, 7810.0)
    assert ofs.row_verdict(r2) is None, "exactly STALE_ROW_S behind is still a market row"
    r3 = _row(pull, pull_s - ofs.STALE_ROW_S - 1, 7800.0, 7790.0, 7810.0)
    assert ofs.row_verdict(r3) == "stale"


# --- SentinelState ----------------------------------------------------------

def test_feed_row_counts_and_skips(emitted):
    st = ofs.SentinelState(2.5, 5.0, 5.0)
    st.rollover("2026-08-14")
    assert st.feed_row(_row("2026-08-14T13:30:02Z", 1_786_651_199, 7798.86, 7806.13, 7799.77)) == "stale"
    assert st.feed_row(_row("2026-08-14T13:30:04Z", T0 + 2, 7806.6, 7535, 7535, dex=0)) == "reset"
    assert st.feed_row(_row("2026-08-14T13:30:05Z", T0 + 3, 7805.29, 7759.64, 7835.78)) is None
    assert st.rows == 1 and st.rows_today == 1
    assert st.skipped == {"stale": 1, "reset": 1}
    assert st.last_row_pull_utc == "2026-08-14T13:30:05Z"
    # skipped rows never touched a watch
    assert st.watches["z_mlgamma"].value == 7759.64


def test_rollover_rebuilds_watches_and_resets_day_counters(emitted):
    st = ofs.SentinelState(2.5, 5.0, 5.0)
    st.rollover("2026-08-13")
    for r in _market_rows(30, day="2026-08-13", start_s=T0 - 86_400, spot=7690, ml=7700, ms=7720):
        st.feed_row(r)
    old = dict(st.watches)
    assert st.watches["z_mlgamma"].value == 7700 and len(st.watches["z_mlgamma"].window) == 30
    st.rollover("2026-08-14")
    assert st.day == "2026-08-14" and st.rollovers == 1
    assert st.rows_today == 0 and st.skipped == {} and st.alerts_today == 0
    assert st.rows == 30, "lifetime row count survives; per-day counters do not"
    for k, w in st.watches.items():
        assert w is not old[k]
        assert w.value is None and len(w.window) == 0 and w.armed


def test_day_two_first_rows_never_judged_by_day_one_window(emitted):
    """The 08-14 13:30:04Z artifact. Day 1 parks the ladder at 7700; day 2
    opens with it at 7750. Carried state saw a contest between two clusters and
    fired inside the first minute. Fresh watches see one cluster and are silent
    until something actually happens."""
    st = ofs.SentinelState(2.5, 5.0, 5.0)
    st.rollover("2026-08-13")
    for r in _market_rows(60, day="2026-08-13", start_s=T0 - 86_400, spot=7690, ml=7700, ms=7720):
        st.feed_row(r)
    emitted.clear()
    st.rollover("2026-08-14")
    for r in _market_rows(ofs.LevelWatch.MIN_ROWS + 5, day="2026-08-14", start_s=T0,
                          spot=7740, ml=7750, ms=7770):
        st.feed_row(r)
    assert emitted == [], f"day-2 opening rows fired {[(a['kind'], a['level']) for a in emitted]}"


def test_without_rollover_the_carried_window_does_fire(emitted):
    """Documents the defect the rollover fixes: the same two days through ONE
    set of watches produce an alert inside day 2's first minute."""
    st = ofs.SentinelState(2.5, 5.0, 5.0)
    st.rollover("2026-08-13")
    for r in _market_rows(60, day="2026-08-13", start_s=T0 - 86_400, spot=7690, ml=7700, ms=7720):
        st.feed_row(r)
    emitted.clear()
    for r in _market_rows(ofs.LevelWatch.MIN_ROWS + 5, day="2026-08-14", start_s=T0,
                          spot=7740, ml=7750, ms=7770):
        st.feed_row(r)   # no rollover call
    assert emitted, "carried window should have fired — if it no longer does, the rollover test above is vacuous"


def test_health_payload_shape():
    st = ofs.SentinelState(2.5, 5.0, 5.0)
    st.rollover("2026-08-14")
    st.feed_row(_row("2026-08-14T13:30:05Z", T0 + 3, 7805.29, 7759.64, 7835.78))
    st.note_alert("2026-08-14T13:31:00Z")
    h = st.health(path=Path("/x/gexbot_orderflow_1s.jsonl"), offset=123)
    for k in ("written_utc", "pid", "day", "feed", "feed_offset", "rows", "rows_today",
              "skipped", "last_row_pull_utc", "alerts_today", "last_alert_utc",
              "rollovers", "watches"):
        assert k in h, k
    assert h["day"] == "2026-08-14" and h["feed_offset"] == 123
    assert h["alerts_today"] == 1 and h["last_alert_utc"] == "2026-08-14T13:31:00Z"
    assert set(h["watches"]) == set(ofs.LEVELS)
    assert set(h["watches"]["z_mlgamma"]) == {"value", "armed", "contested", "zone"}


def test_write_health_is_atomic_and_readable(tmp_path):
    p = tmp_path / "corpus" / "2026-08-14" / "_sentinel_health.json"
    ofs.write_health(p, {"rows": 1})
    assert json.loads(p.read_text()) == {"rows": 1}
    assert not p.with_suffix(".json.tmp").exists()
    ofs.write_health(p, {"rows": 2})
    assert json.loads(p.read_text()) == {"rows": 2}


# --- replay_file: the fixture / Risk-11 runner ------------------------------

def test_replay_file_counts_skips_and_alerts_from_byte_zero(tmp_path, monkeypatch):
    day = tmp_path / "2026-08-14"
    day.mkdir()
    feed = day / "gexbot_orderflow_1s.jsonl"
    rows = [
        _row("2026-08-14T13:30:02Z", 1_786_651_199, 7798.86, 7806.13, 7799.77, dex=400.08),  # stale
        _row("2026-08-14T13:30:04Z", T0 + 2, 7806.6, 7535, 7535, dex=0),                    # reset
    ] + list(_market_rows(30, day="2026-08-14", start_s=T0 + 3, spot=7740, ml=7750, ms=7770))
    feed.write_text("".join(json.dumps(r) + "\n" for r in rows) + '{"partial": tr')  # torn tail
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(ofs, "_alerts_path", lambda: alerts)
    st = ofs.SentinelState(2.5, 5.0, 5.0)
    h = ofs.replay_file(feed, st)
    assert h["day"] == "2026-08-14"
    assert h["rows"] == 30 and h["skipped"] == {"stale": 1, "reset": 1}
    assert h["alerts_today"] == 0 and not alerts.exists()
    # the torn last line was not consumed
    assert h["feed_offset"] == sum(len(json.dumps(r) + "\n") for r in rows)


def test_replay_alerts_carry_the_row_time(tmp_path, monkeypatch):
    """`ts_row` names the tape second an alert is about; `ts_alert_utc` is
    when the sentinel spoke. In replay they differ by days — without ts_row a
    replayed alert file cannot be lined up against the tape at all."""
    day = tmp_path / "2026-08-14"
    day.mkdir()
    feed = day / "gexbot_orderflow_1s.jsonl"
    rows = list(_market_rows(30, day="2026-08-14", start_s=T0, spot=7740, ml=7700, ms=7770))
    # ladder jumps 40 pts and holds: a relocation, well past MIN_ROWS
    rows += list(_market_rows(60, day="2026-08-14", start_s=T0 + 30, spot=7740, ml=7740, ms=7770))
    feed.write_text("".join(json.dumps(r) + "\n" for r in rows))
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(ofs, "_alerts_path", lambda: alerts)
    h = ofs.replay_file(feed, ofs.SentinelState(2.5, 5.0, 5.0))
    assert h["alerts_today"] >= 1
    first = json.loads(alerts.read_text().splitlines()[0])
    assert first["ts_row"].startswith("2026-08-14T13:3")
    assert first["ts_alert_utc"] != first["ts_row"]
    assert h["last_alert_utc"] == json.loads(alerts.read_text().splitlines()[-1])["ts_alert_utc"]


# --- alerts reach the bridge [st-n0qm.9] --------------------------------------

def test_emit_posts_the_alert_to_the_bridge_best_effort(tmp_path, monkeypatch):
    """The durable write happens first; the bridge POST is a display and can
    fail without touching the alert, the file, or the loop."""
    import http.server
    import threading

    got: list[dict] = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            got.append(json.loads(self.rfile.read(n)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"id":1}')

        def log_message(self, *a):  # quiet
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        alerts = tmp_path / "orderflow_alerts.jsonl"
        monkeypatch.setattr(ofs, "_alerts_path", lambda: alerts)
        monkeypatch.setattr(ofs, "_BRIDGE", f"http://127.0.0.1:{srv.server_port}")
        monkeypatch.setattr(ofs, "_STATE", None)
        ofs._emit({"kind": "approach", "level": "z_mlgamma", "value": 7804.46})
        assert len(got) == 1 and got[0]["strike"] == 7805 and got[0]["kind"] == "approach"
        assert alerts.read_text().count("\n") == 1
    finally:
        srv.shutdown()


def test_emit_survives_a_dead_bridge_and_logs_sparsely(tmp_path, monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(ofs, "_LOG", type("L", (), {"write": lambda self, s: lines.append(s)})())
    monkeypatch.setattr(ofs, "_alerts_path", lambda: tmp_path / "a.jsonl")
    monkeypatch.setattr(ofs, "_BRIDGE", "http://127.0.0.1:9")   # discard port: refused
    monkeypatch.setattr(ofs, "_STATE", None)
    monkeypatch.setattr(ofs, "_bridge_failures", 0)
    for _ in range(3):
        ofs._emit({"kind": "approach", "level": "z_mlgamma", "value": 7804.46})
    assert (tmp_path / "a.jsonl").read_text().count("\n") == 3, "the file never waits on the bridge"
    fails = [l for l in lines if "bridge post failed" in l]
    assert len(fails) == 1 and "(1x)" in fails[0], "first failure logged, then quiet until the 50th"


def test_bridge_is_off_when_unset(monkeypatch):
    monkeypatch.setattr(ofs, "_BRIDGE", None)
    assert ofs._post_alert({"kind": "approach"}) is False
