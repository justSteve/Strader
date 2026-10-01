"""The view log's mechanics: display-precision change detection, the 1/s
coalesce, the bounded queue, errors counted not raised, 14-day prune, the
flag, and its health on /status. [st-6pfc]"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from execd.viewlog import ViewLog, viewer_tag

T0 = datetime(2026, 10, 1, 17, 0, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


def rec(limit: float, page: str = "order") -> tuple[dict, tuple]:
    return ({"page": page, "ticket": {"limit": limit}}, (f"{limit:.2f}",))


def lines(vl: ViewLog) -> list[dict]:
    return [json.loads(x) for f in sorted(vl.dir.glob("*.jsonl")) for x in f.read_text().splitlines()]


def test_only_a_displayed_change_is_a_line(tmp_path):
    vl = ViewLog(tmp_path, clock=Clock(), start=False)
    vl.offer("desktop-1", *rec(2.10))
    vl.offer("desktop-1", {"page": "order", "ticket": {"limit": 2.1000004}}, ("2.10",))   # jitter
    vl.offer("desktop-1", *rec(2.10))
    vl.drain(force=True)
    assert len(lines(vl)) == 1 and vl.counts["unchanged"] == 2
    vl.offer("ipad-2", *rec(2.10))                      # another viewer is its own key
    vl.offer("desktop-1", *rec(2.20))
    vl.drain(force=True)
    assert sorted((ln["viewer"], ln["ticket"]["limit"]) for ln in lines(vl)[1:]) == \
        [("desktop-1", 2.2), ("ipad-2", 2.1)]


def test_a_burst_inside_a_second_is_one_line_with_the_latest(tmp_path):
    vl = ViewLog(tmp_path, clock=Clock(), start=False)
    vl.offer("d", *rec(2.10))
    assert vl.drain(now_s=100.0) == 1
    for px in (2.20, 2.30, 2.40):
        vl.offer("d", *rec(px))
        assert vl.drain(now_s=100.5) == 0              # inside the second: held
    assert vl.drain(now_s=101.1) == 1
    assert vl.drain(now_s=103.2) == 0                  # the ~2 s flush
    assert [ln["ticket"]["limit"] for ln in lines(vl)] == [2.10, 2.40]


def test_the_queue_drops_its_oldest_and_counts(tmp_path):
    vl = ViewLog(tmp_path, clock=Clock(), start=False, queue_max=3)
    for i in range(5):
        vl.offer(f"v{i}", *rec(1.0 + i))
    assert vl.counts["dropped"] == 2
    vl.drain(force=True)
    assert sorted(ln["viewer"] for ln in lines(vl)) == ["v2", "v3", "v4"]


def test_a_write_error_is_counted_never_raised(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    vl = ViewLog(blocker / "sub", clock=Clock(), start=False)    # cannot be a directory
    vl.offer("d", *rec(2.10))
    vl.drain(force=True)
    assert vl.counts["write_errors"] >= 1 and vl.health()["lines"] == 0


def test_off_is_off(tmp_path):
    vl = ViewLog(tmp_path / "x", enabled=False, clock=Clock())
    vl.offer("d", *rec(2.10))
    assert vl.health()["enabled"] is False and not (tmp_path / "x").exists()


def test_files_older_than_fourteen_days_are_pruned_at_the_roll(tmp_path):
    for d in (1, 13, 14, 15, 40):
        (tmp_path / f"{(T0 - timedelta(days=d)).date().isoformat()}.jsonl").write_text("{}\n")
    vl = ViewLog(tmp_path, clock=Clock(), start=False)
    vl.offer("d", *rec(2.10))
    vl.drain(force=True)
    left = sorted(p.stem for p in Path(tmp_path).glob("*.jsonl"))
    assert left == sorted((T0 - timedelta(days=d)).date().isoformat() for d in (0, 1, 13, 14))
    assert vl.counts["pruned"] == 2


def test_the_writer_thread_writes_and_stops(tmp_path):
    vl = ViewLog(tmp_path, clock=Clock())
    vl.offer("d", *rec(2.10))
    vl.stop()
    assert len(lines(vl)) == 1 and vl.health()["writer_alive"] is False


def test_viewer_tags():
    assert viewer_tag("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)").startswith("ipad-")
    assert viewer_tag("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1").startswith("ipad-")
    assert viewer_tag("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129").startswith("desktop-")
    assert viewer_tag(None).startswith("desktop-")


def test_the_page_offers_and_status_carries_the_health(armed, broker, clock, mono, tmp_path):
    from execd.page import create_page
    from .conftest import same_origin, schwab_chain_maps
    from .test_page import CALLBACK, PASS, market_payload, vault_payload
    from execd.page import CredentialFile
    from execd.vault import Vault
    broker.set_chain("SPXW", schwab_chain_maps())
    vault = Vault(tmp_path / "vault.json")
    vault.store(vault_payload(), PASS)
    (tmp_path / "market.json").write_text(json.dumps(market_payload()))
    market = CredentialFile(tmp_path / "market.json")
    market.load()
    vl = ViewLog(tmp_path / "surface", clock=clock, start=False)
    armed.view_log = vl
    app = create_page(armed, vault=vault, market=market, callback_url=CALLBACK, clock=clock,
                      monotonic=mono, view_log=vl)
    app.config["TESTING"] = True
    c = same_origin(app.test_client())
    for _ in range(3):
        c.get("/exec/order/state?side=call", headers={"User-Agent": "Mozilla/5.0 (iPad)"})
    vl.drain(force=True)
    got = lines(vl)
    assert len(got) == 1 and got[0]["viewer"].startswith("ipad-") and got[0]["chosen"]["strike"]
    assert armed.status()["view_log"]["lines"] == 1


from .test_orderform import mono  # noqa: E402,F401 — fixture
