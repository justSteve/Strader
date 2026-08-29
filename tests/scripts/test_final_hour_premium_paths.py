"""The premium scoreboard sees gzipped OPRA days. [co-8p9nn]

On 2026-08-29 the corpus held 276 OPRA day-files, 7 of them gzipped by the
compactor (five in August 2026), and ``final_hour_premium.py`` globbed the
plain form only — so the August days existed on disk and were invisible to
the one scorer that prices a rule in premium. ``final_hour_lens.py`` and
``final_hour_base.py`` already read both forms; this pins the third script
to the same behaviour.
"""
import gzip
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "measurement" / "final_hour_premium.py"


def _load(monkeypatch, tmp_path):
    # The script reads its two positional args at import; give it harmless ones.
    monkeypatch.setattr(sys, "argv", ["final_hour_premium.py", str(tmp_path / "base.jsonl"), str(tmp_path / "out.jsonl")])
    spec = importlib.util.spec_from_file_location("final_hour_premium_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _corpus_day(root, day, gz):
    d = root / "data" / "corpus" / day
    d.mkdir(parents=True)
    line = json.dumps({"provenance": {"ts_event": f"{day}T19:00:00.000000000+00:00"},
                       "data": {"symbol": "SPXW  250807C06345000", "price": 1.0, "size": 1}}) + "\n"
    if gz:
        p = d / "databento_opra.jsonl.gz"
        with gzip.open(p, "wt") as f:
            f.write(line)
    else:
        p = d / "databento_opra.jsonl"
        p.write_text(line)
    return p


def test_opra_paths_include_gzipped_days_and_honour_the_base_skip(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    plain = _corpus_day(tmp_path, "2026-07-30", gz=False)
    gzd = _corpus_day(tmp_path, "2026-08-03", gz=True)
    _corpus_day(tmp_path, "2026-08-04", gz=True)          # skipped by the base file
    _corpus_day(tmp_path, "2026-08-05", gz=True)          # absent from the base file
    base = {"2026-07-30": {"day": "2026-07-30"}, "2026-08-03": {"day": "2026-08-03"},
            "2026-08-04": {"day": "2026-08-04", "skip": "thin"}}
    monkeypatch.chdir(tmp_path)
    got = mod.opra_paths(base)
    assert [os.path.relpath(p, tmp_path) for p in got] == [
        os.path.relpath(plain, tmp_path), os.path.relpath(gzd, tmp_path)]


def test_open_reads_gzipped_and_plain_alike(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    plain = _corpus_day(tmp_path, "2026-07-30", gz=False)
    gzd = _corpus_day(tmp_path, "2026-08-03", gz=True)
    with mod._open(str(plain)) as f:
        a = f.read()
    with mod._open(str(gzd)) as f:
        b = f.read()
    assert "SPXW  250807C06345000" in a and "SPXW  250807C06345000" in b
