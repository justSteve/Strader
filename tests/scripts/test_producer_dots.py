"""The drill/live page's producer dots: a bad verdict wins over a fresh file,
and the feed goes amber on late drops. [st-s6qj, st-epa3]

The collector assessors rewrite _capture_health.json / _gexbot_health.json
every 2 minutes whatever they find, so a DEAD capture's file is always fresh;
the old dot tested age first and painted it green. The verdict function is
lifted out of the template between its markers and run under node.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[2] / "scripts" / "orderflow_drill_template.html"
NODE = shutil.which("node")


def _verdicts(cases: dict) -> dict:
    src = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r"// PRODUCER_DOT_BEGIN.*?\n(.*?)// PRODUCER_DOT_END", src, re.S)
    assert m, "producerDot markers missing from the template"
    consts = re.search(r"const PROD_BAD_STATUS = .*?;\n", src).group(0)
    js = (consts + m.group(1)
          + f"const cases = {json.dumps(cases)};\n"
          + "const out = {}; for (const k in cases) out[k] = producerDot(cases[k]);\n"
          + "console.log(JSON.stringify(out));\n")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _p(**kw):
    base = {"present": True, "path": "/x", "age_s": 30.0, "fresh": True,
            "fresh_s": 180, "status": "ok"}
    base.update(kw)
    return base


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_verdict_order():
    v = _verdicts({
        "ok": _p(),
        "dead_fresh": _p(status="dead"),
        "stale_fresh": _p(status="stale"),
        "dup_fresh": _p(status="duplicate"),
        "idle": _p(status="idle", fresh=False, age_s=9999),
        "quiet": _p(status="quiet"),
        "old": _p(fresh=False, age_s=9999),
        "aging": _p(fresh=False, age_s=300),
        "absent": _p(present=False),
        "feed_late": _p(status=None, fresh_s=90, late=3, dupes=0, bad=0),
        "feed_clean": _p(status=None, fresh_s=90, late=0, dupes=4, bad=0),
        "feed_late_stale": _p(status=None, fresh=False, age_s=9999, fresh_s=90, late=3),
    })
    assert v["ok"][0] == "pd ok"
    for k in ("dead_fresh", "stale_fresh", "dup_fresh"):
        assert v[k][0] == "pd bad", (k, v[k])
    assert v["dead_fresh"][1].startswith("DEAD")
    assert v["idle"][0] == "pd" and v["quiet"][0] == "pd"
    assert v["old"][0] == "pd bad" and v["aging"][0] == "pd warn"
    assert v["absent"][0] == "pd bad"
    assert v["feed_late"][0] == "pd warn" and "3 late" in v["feed_late"][1]
    assert v["feed_clean"][0] == "pd ok" and "dupes 4" in v["feed_clean"][1]
    assert v["feed_late_stale"][0] == "pd bad"   # stale outranks late


def test_page_lists_the_live_producers_only():
    src = TEMPLATE.read_text(encoding="utf-8")
    order = re.search(r"const PROD_ORDER = (\[.*?\]);", src).group(1)
    keys = [k for k, _ in json.loads(order)]
    assert keys == ["tape", "gexbot", "feed"]
