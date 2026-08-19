"""Tests for run.py --prepare-only (st-lw58) — the 08:15 cron must prepare and
alert, never publish. The hybrid publish path must be unreachable from it."""
import argparse
import json

from runbook.mancini import run as run_mod
from runbook.mancini.schema import Level, ParseResult


def _args(clip=False):
    # no_desk=True: the prepare's good case hooks the overnight refresh (st-vxbw),
    # which renders through the desk; these tests cover readiness, not rendering.
    return argparse.Namespace(clip=clip, no_clip=False, extraction_json=None, no_desk=True)


def _det_levels():
    return [
        Level(price=7458.0, kind="support", label="major", source_quote="7458 (major)"),
        Level(price=7506.0, kind="resistance", label="", source_quote="7506"),
    ]


def _stored(model):
    return ParseResult(date="2026-08-06", instrument="ES", session_bias="b",
                       levels=[], commentary=[], raw_excerpt="", model=model,
                       parsed_at="2026-08-06T13:00:00+00:00")


def test_no_parse_yet_alerts_and_publishes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path)
    sent = []
    monkeypatch.setattr("strader.alerts.send",
                        lambda title, message, **kw: sent.append((title, kw)))
    pushed = []
    monkeypatch.setattr(run_mod, "_push_payload",
                        lambda *a, **kw: pushed.append(a) or "clipboard: x")

    rc = run_mod._prepare_only(_args(clip=True), "2026-08-06", _det_levels())

    assert rc == 0
    assert list(tmp_path.iterdir()) == []          # nothing written
    assert not pushed                              # clipboard untouched
    assert sent and sent[0][0] == "Mancini ready to parse"
    assert sent[0][1].get("urgent") is False       # readiness ping, not emergency
    out = capsys.readouterr().out
    assert "awaiting parse" in out
    assert "2 levels" in out and "1 supports" in out and "1 resistances" in out


def test_richer_parse_reloads_clipboard(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path)
    (tmp_path / "2026-08-06.json").write_text(
        json.dumps(_stored("in-session:opus").to_dict()), encoding="utf-8")
    pushed = []
    monkeypatch.setattr(run_mod, "_push_payload",
                        lambda *a, **kw: pushed.append(a) or "clipboard: loaded")
    alerted = []
    monkeypatch.setattr("strader.alerts.send",
                        lambda *a, **kw: alerted.append(a))

    rc = run_mod._prepare_only(_args(clip=True), "2026-08-06", _det_levels())

    assert rc == 0
    assert len(pushed) == 1                        # the job's good-case work
    assert not alerted                             # no readiness alert needed
    assert "already parsed by 'in-session:opus'" in capsys.readouterr().out


def test_stale_hybrid_parse_does_not_block_readiness(tmp_path, monkeypatch, capsys):
    # A deterministic-lists artifact (old hybrid era, or manual smoke) is not a
    # richer parse — prepare must still say "ready to parse".
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path)
    (tmp_path / "2026-08-06.json").write_text(
        json.dumps(_stored("deterministic-lists").to_dict()), encoding="utf-8")
    monkeypatch.setattr("strader.alerts.send", lambda *a, **kw: None)
    pushed = []
    monkeypatch.setattr(run_mod, "_push_payload",
                        lambda *a, **kw: pushed.append(a))

    rc = run_mod._prepare_only(_args(clip=True), "2026-08-06", _det_levels())

    assert rc == 0
    assert not pushed
    assert "awaiting parse" in capsys.readouterr().out


def test_alert_failure_is_non_fatal(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path)

    def boom(*a, **kw):
        raise RuntimeError("no backend configured")

    monkeypatch.setattr("strader.alerts.send", boom)
    rc = run_mod._prepare_only(_args(), "2026-08-06", _det_levels())
    assert rc == 0                                 # readiness still reported
    assert "awaiting parse" in capsys.readouterr().out


def test_backfill_artifact_does_not_block_readiness(tmp_path, monkeypatch, capsys):
    # A listlevels-backfill artifact (scripts/mancini_backfill_levels.py,
    # co-vp45h) is levels-only like the old hybrid parse: the morning must
    # still ask for the real parse.
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path)
    (tmp_path / "2026-08-06.json").write_text(
        json.dumps(_stored("listlevels-backfill").to_dict()), encoding="utf-8")
    monkeypatch.setattr("strader.alerts.send", lambda *a, **kw: None)
    pushed = []
    monkeypatch.setattr(run_mod, "_push_payload",
                        lambda *a, **kw: pushed.append(a))

    rc = run_mod._prepare_only(_args(clip=True), "2026-08-06", _det_levels())

    assert rc == 0
    assert not pushed
    assert "awaiting parse" in capsys.readouterr().out
