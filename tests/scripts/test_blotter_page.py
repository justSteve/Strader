"""The blotter page: rows and manifest in, one self-contained page out, the
Statement verbatim, estimated rows labelled, registration through the desk
seam. [st-08ru]"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import blotter_page as bp  # noqa: E402

ROW = {
    "id": "2026-02-10-footprint-up-1445-1", "lane": "replay", "day": "2026-02-10", "rule_id": "footprint-up-1445",
    "registered": "ac02296", "call": "up", "sources": [], "instrument": "itm-single-10",
    "occ_symbol": "SPXW  260210C06420000", "right": "C", "strike": 6420.0, "lots": 1, "fire_ct": "14:45",
    "entry_ts": "14:45:08", "entry_premium_pts": 10.0, "spx_at_entry": 6431.7, "es_at_entry": 6451.7,
    "exit_ts": "14:59:59", "exit_premium_pts": 9.1, "exit_reason": "time", "pnl_pts": -0.9, "pnl_usd": -90.0,
    "mfe_pts": 0.4, "mae_pts": -1.2, "mark_path": "estimated", "estimated": True, "n_marks": 15,
    "state": {"T": "1445", "pT": 6451.0, "fp": {"pos": 0.9, "l30_chg": 2.0, "l30_delta": 300, "call": "up"}, "mc": None, "gx": None},
    "events": [{"line": "14:30 CT  EVENT PLAN-LEVEL TOUCH  sig=note  level=6450", "path": "tape"}],
    "excerpts": ["footprint-up-1445"], "replay": "2026-02-10 14:15 to 15:00", "grid": None,
    "estimated_exit": {"would_exit_reason_extreme": "stop", "would_exit_reason_close": "time",
                       "stop_minute_adverse": "14:47", "target_minute_favourable": None,
                       "stop_minute_close": None, "target_minute_close": None, "proxy_close_pts": 9.1},
    "extrapolated": False, "notes": ["entry = Schwab close-watch ask at 14:45:08 CT; marks = ES->premium proxy"],
}


@pytest.fixture
def rows_dir(tmp_path: Path) -> Path:
    d = tmp_path / "blotter"
    d.mkdir()
    printed = {**ROW, "id": "2025-11-03-launch-into-no-lid-1445-1", "day": "2025-11-03", "rule_id": "launch-into-no-lid-1445",
               "registered": "9df6a9c", "mark_path": "prints", "estimated": False, "exit_reason": "stop",
               "exit_premium_pts": 9.7, "pnl_pts": -0.3, "pnl_usd": -30.0, "estimated_exit": None, "notes": [],
               "grid": {"0.30x25": {"exit_reason": "stop", "exit_ts": "14:46:00", "exit_premium_pts": 9.7, "pnl_pts": -0.3}},
               "excerpts": ["launch-into-no-lid-1445"], "replay": "2025-11-03 14:15 to 15:00"}
    (d / "replay-2025-11-03.jsonl").write_text(json.dumps(printed, sort_keys=True) + "\n")
    (d / "replay-2026-02-10.jsonl").write_text(json.dumps(ROW, sort_keys=True) + "\n")
    (d / "replay-run-2025-11-01-2026-02-28.json").write_text(json.dumps({
        "range": ["2025-11-01", "2026-02-28"], "n_days": 4, "n_rows": 2, "n_unpriced": 1,
        "calibration": "data/measurement/cal.json", "events": True,
        "days": [{"day": "2026-02-11", "unpriced": [{"rule_id": "footprint-up-1445", "fire_ct": "14:45", "call": "up",
                                                     "reason": "no-entry-source", "detail": "no OPRA prints and no Schwab chain"}]}],
    }))
    (d / "replay-run-2025-01-01-2025-06-30.json").write_text(json.dumps({"range": ["2025-01-01", "2025-06-30"], "n_days": 1, "days": []}))
    return d


def test_build_reads_rows_manifest_and_rules(rows_dir):
    payload = bp.build(rows_dir, built="2026-09-11 12:00 CT")
    assert [r["id"] for r in payload["rows"]] == ["2025-11-03-launch-into-no-lid-1445-1", "2026-02-10-footprint-up-1445-1"]
    assert payload["manifest"]["range"] == ["2025-11-01", "2026-02-28"]        # the later manifest wins
    assert payload["unpriced"] == [{"day": "2026-02-11", "rule_id": "footprint-up-1445", "fire_ct": "14:45", "call": "up",
                                    "reason": "no-entry-source", "detail": "no OPRA prints and no Schwab chain"}]
    assert set(payload["rules"]) == {"footprint-up-1445", "launch-into-no-lid-1445"}
    fp = payload["rules"]["footprint-up-1445"]
    assert fp["statement"].startswith("At 14:45 CT, with the 13:00 to 14:45 box")
    assert fp["path"] == "knowledge/footprint-up-1445.md" and fp["registered"] == "ac02296"
    assert fp["exit"] == {"stop_pts": 0.3, "target_pct": 25.0, "time": "15:00 CT"}
    assert payload["aggregate"]["footprint-up-1445"]["estimated"]["all"]["n"] == 1
    assert payload["aggregate"]["launch-into-no-lid-1445"]["prints"]["all"]["n"] == 1
    assert "0.30x25" in payload["grid"]["launch-into-no-lid-1445"]
    assert payload["built"] == "2026-09-11 12:00 CT"


def test_render_embeds_the_payload_verbatim_and_self_contained(rows_dir):
    payload = bp.build(rows_dir, built="2026-09-11 12:00 CT")
    html = bp.render_html(payload)
    assert bp.MARKER not in html
    blob = re.search(r"const DATA = (\{.*?\});\n", html, re.S).group(1)
    back = json.loads(blob.replace("<\\/", "</"))
    assert back["rows"] == payload["rows"] and back["rules"] == payload["rules"]
    assert "http" not in html.split("<script>")[0].split("<body>")[0]         # no external stylesheet or font
    assert "<link" not in html and 'src="http' not in html
    assert "__BLOTTER_DATA__" not in html


def test_statement_is_verbatim_from_the_bundle():
    from strader.entities.canon import load_entity
    meta = bp.rules_meta(with_commit=False)
    for rid, m in meta.items():
        assert m["statement"] == load_entity(ROOT / "knowledge" / f"{rid}.md").statement()
        assert m["commit"] is None


def test_script_writes_the_page_and_registers_through_the_seam(rows_dir, tmp_path):
    out = tmp_path / "blotter.html"
    manifest = tmp_path / "StevesDocs.json"
    manifest.write_text(json.dumps({"Trading": [], "System": [], "Beads": [], "Specs": [], "Plans": [], "Reviews": [], "Logs": []}))
    env = {**os.environ, "DESK_MANIFEST": str(manifest)}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "blotter_page.py"), "--rows-dir", str(rows_dir),
                        "--out", str(out), "--built", "2026-09-11 12:00 CT", "--no-commit", "--register"],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "2 rows (1 printed, 1 estimated), 1 unpriced, 2 rules" in r.stdout
    assert out.exists() and "Blotter" in out.read_text()
    if bp.DESK_REGISTER.exists():
        reg = json.loads(manifest.read_text())
        assert reg["Trading"] == ["myDesk/trading/blotter.html"]
    r2 = subprocess.run([sys.executable, str(ROOT / "scripts" / "blotter_page.py"), "--rows-dir", str(rows_dir),
                        "--out", str(out), "--built", "2026-09-11 12:00 CT", "--no-commit"],
                        cwd=ROOT, capture_output=True, text=True)
    assert r2.returncode == 0
    assert out.read_bytes() == out.read_bytes()   # same inputs, same page


def test_script_refuses_a_missing_rows_dir(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "blotter_page.py"), "--rows-dir", str(tmp_path / "nope"),
                        "--out", str(tmp_path / "x.html")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 1 and "not found" in r.stderr
    (tmp_path / "empty").mkdir()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "blotter_page.py"), "--rows-dir", str(tmp_path / "empty"),
                        "--out", str(tmp_path / "x.html"), "--no-commit"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 1 and "no replay-<day>.jsonl rows" in r.stderr
