"""Entitlements registry + probe. [st-g0or]

Three things are worth testing here and they are not the usual ones.

1. **The real registry must stay readable by the stdlib-only loader.** Strader's
   core carries no third-party runtime dependency, so `config/entitlements.yaml`
   is authored in the subset `strader/_yaml.py` parses. PyYAML is installed in
   this venv, which means a file using syntax only PyYAML understands would pass
   every local run and fail on a clean install — at tap-in, in the morning. The
   first test parses the live file with the subset loader explicitly.

2. **The registry must never carry a credential.** It records WHAT we are
   entitled to, never HOW to authenticate (`.claude/rules/schwab-api-gate.md`).
   That is a property of the file's content, so it is asserted against the file.

3. **A dated fact must never be able to render as an observation.** The probe's
   whole purpose is the distinction, so the report's two sections and their
   verdicts are asserted directly, against a fake registry and a fake corpus —
   no live state file is read and no vendor API exists to be called.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from strader import _yaml, entitlements as ent
import scripts.entitlements_probe as ep

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_REGISTRY = REPO_ROOT / "config" / "entitlements.yaml"
NOW = datetime(2026, 8, 13, 14, 0, tzinfo=timezone.utc)


# ─── the live registry ───────────────────────────────────────────────────────

def test_live_registry_parses_with_the_dependency_free_loader():
    """No PyYAML-only syntax: block scalars, anchors, flow mappings, `- key:`."""
    data = _yaml._load_subset(LIVE_REGISTRY.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["probed"] and data["dated"]
    # And PyYAML (when present) must agree on the shape, not just parse it.
    both = _yaml.safe_load(LIVE_REGISTRY.read_text(encoding="utf-8"))
    for section in ("probed", "dated"):
        assert [e["id"] for e in ent.entries(both, section)] == \
               [e["id"] for e in ent.entries(data, section)]


def test_live_registry_entries_carry_their_required_fields():
    reg = ent.load_registry(LIVE_REGISTRY)
    probed_ids = {e["id"] for e in ent.entries(reg, "probed")}
    for e in ent.entries(reg, "probed"):
        assert e.get("kind") in ent._PROBES, f"{e['id']}: unknown probe kind"
        assert e.get("label") and e.get("what"), f"{e['id']}: needs label + what"
    for e in ent.entries(reg, "dated"):
        for f in ("id", "label", "vendor", "state", "source", "what"):
            assert e.get(f), f"{e.get('id')}: missing {f}"
        # confirmed_on/by may be null (never confirmed) but the KEYS must exist —
        # a missing key would silently render as never-confirmed.
        assert "confirmed_on" in e and "confirmed_by" in e, f"{e['id']}: date keys required"
        for ev in e.get("evidence") or []:
            assert ev in probed_ids, f"{e['id']}: evidence {ev!r} names no probed entry"


def test_live_registry_holds_no_credentials():
    """WHAT we are entitled to, never HOW to authenticate.

    Two passes. The raw pass hunts an assignment carrying a long opaque value —
    the shape an actual leaked key takes — rather than banning English words,
    because the file's own header has to be able to SAY 'no keys, no secrets'.
    The value pass then walks every parsed string for credential-store paths.
    """
    raw = LIVE_REGISTRY.read_text(encoding="utf-8")
    leak = re.compile(r"(?i)(api[_-]?key|secret|password|passwd|bearer|token)"
                      r"\s*[:=]\s*[\"']?[A-Za-z0-9/+._-]{16,}")
    assert not leak.search(raw), f"registry looks like it carries a credential: {leak.search(raw)}"

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
        elif isinstance(node, str):
            yield node

    for value in walk(ent.load_registry(LIVE_REGISTRY)):
        low = value.lower()
        for forbidden in ("tokens/", ".env", "schwab_gate_key", "authorization:", "client_secret"):
            assert forbidden not in low, f"registry value points at a credential store: {value!r}"


def test_live_registry_probes_read_local_paths_only():
    """Nothing in the registry points a probe at a URL — the probe is local-only."""
    reg = ent.load_registry(LIVE_REGISTRY)
    for e in ent.entries(reg, "probed"):
        target = str(e.get("path") or e.get("filename") or "")
        assert "://" not in target and not target.startswith("/"), \
            f"{e['id']}: probe target {target!r} is not a repo-relative local path"


# ─── fixtures for the behavioural tests ──────────────────────────────────────

def write_registry(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "entitlements.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def health(tmp_path: Path, name: str, *, status="ok", checked_at="2026-08-13T13:30:00Z",
           message="all good") -> None:
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / name).write_text(
        json.dumps({"status": status, "checked_at": checked_at, "message": message}))


def corpus_day(corpus: Path, day: str, filename: str) -> None:
    d = corpus / day
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text("{}\n")


# Fixtures are authored in the same subset the live file uses, so a clean
# install without PyYAML exercises the same parse path these assertions do.
PROBED_ONLY = """
probed:
  tok:
    label: Token health
    vendor: Schwab
    what: heartbeat
    kind: json_file
    path: state/_tok.json
    status_field: status
    ok_values: [ok]
    fields: [message]
    checked_at_field: checked_at
    stale_after_hours: 30
"""


def test_probe_reports_ok_and_ages_the_evidence(tmp_path):
    health(tmp_path, "_tok.json")
    reg = ent.load_registry(write_registry(tmp_path, PROBED_ONLY))
    (line,) = ent.run_probes(reg, repo_root=tmp_path, now=NOW)
    assert line.state == "OK" and line.ok
    assert line.age == "30m"


def test_a_stale_heartbeat_is_not_reported_as_healthy(tmp_path):
    """The checker stopped running: yesterday's 'ok' is not today's answer."""
    health(tmp_path, "_tok.json", checked_at="2026-08-11T13:30:00Z")
    reg = ent.load_registry(write_registry(tmp_path, PROBED_ONLY))
    (line,) = ent.run_probes(reg, repo_root=tmp_path, now=NOW)
    assert line.state == "STALE" and not line.ok
    assert "OLD" in line.detail


def test_a_missing_state_file_is_missing_not_ok(tmp_path):
    reg = ent.load_registry(write_registry(tmp_path, PROBED_ONLY))
    (line,) = ent.run_probes(reg, repo_root=tmp_path, now=NOW)
    assert line.state == "MISSING" and not line.ok


STREAMS = """
probed:
  live:
    label: ES tape
    vendor: Databento
    what: live entitlement delivering
    kind: corpus_stream
    filename: es.jsonl
    expect: present
    expect_within_days: 4
  halted:
    label: OPRA tape
    vendor: Databento
    what: halted stream
    kind: corpus_stream
    filename: opra.jsonl
    expect: absent
    expect_within_days: 4
"""


def test_stream_probes_read_presence_and_absence(tmp_path):
    corpus = tmp_path / "corpus"
    corpus_day(corpus, "2026-08-13", "es.jsonl")
    corpus_day(corpus, "2026-08-01", "opra.jsonl")     # old, outside the window
    reg = ent.load_registry(write_registry(tmp_path, STREAMS))
    live, halted = ent.run_probes(reg, repo_root=tmp_path, corpus_root=corpus, now=NOW)
    assert (live.state, live.ok) == ("OK", True)
    assert (halted.state, halted.ok) == ("ABSENT", True)


def test_a_halted_usage_billed_stream_reappearing_is_an_alarm(tmp_path):
    """Absence was the correct state — its return means something is billing."""
    corpus = tmp_path / "corpus"
    corpus_day(corpus, "2026-08-13", "es.jsonl")
    corpus_day(corpus, "2026-08-12", "opra.jsonl")
    reg = ent.load_registry(write_registry(tmp_path, STREAMS))
    _, halted = ent.run_probes(reg, repo_root=tmp_path, corpus_root=corpus, now=NOW)
    assert halted.state == "ALARM" and not halted.ok
    assert "REAPPEARED" in halted.detail


def test_a_present_stream_gone_quiet_is_stale(tmp_path):
    corpus = tmp_path / "corpus"
    corpus_day(corpus, "2026-08-01", "es.jsonl")
    reg = ent.load_registry(write_registry(tmp_path, STREAMS))
    live, _ = ent.run_probes(reg, repo_root=tmp_path, corpus_root=corpus, now=NOW)
    assert live.state == "STALE" and not live.ok


# ─── compaction: the packed sibling is the same evidence [st-5wk8] ───────────


def test_a_compacted_day_is_evidence_the_stream_landed(tmp_path):
    """The 07:30 compaction packs .jsonl -> .jsonl.gz. Before this fix every
    finished session read STALE, and on a Saturday the whole week did."""
    corpus = tmp_path / "corpus"
    corpus_day(corpus, "2026-08-13", "es.jsonl.gz")
    reg = ent.load_registry(write_registry(tmp_path, STREAMS))
    live, _ = ent.run_probes(reg, repo_root=tmp_path, corpus_root=corpus, now=NOW)
    assert (live.state, live.ok) == ("OK", True)
    assert ".gz" in live.detail, "the packed form must be named — gzipped MB read differently"


def test_a_zstd_capture_part_also_counts(tmp_path):
    corpus = tmp_path / "corpus"
    corpus_day(corpus, "2026-08-13", "es.jsonl.zst")
    reg = ent.load_registry(write_registry(tmp_path, STREAMS))
    live, _ = ent.run_probes(reg, repo_root=tmp_path, corpus_root=corpus, now=NOW)
    assert (live.state, live.ok) == ("OK", True)


def test_an_empty_raw_file_does_not_mask_a_packed_day(tmp_path):
    """2026-08-30 left a 0-byte databento_glbx_es.jsonl. It is a handle that
    opened and delivered nothing — it must not out-rank five healthy packed
    days behind it, and it must not itself read as evidence."""
    corpus = tmp_path / "corpus"
    corpus_day(corpus, "2026-08-13", "es.jsonl.gz")
    empty = corpus / "2026-08-14"
    empty.mkdir(parents=True, exist_ok=True)
    (empty / "es.jsonl").write_text("")
    reg = ent.load_registry(write_registry(tmp_path, STREAMS))
    live, _ = ent.run_probes(reg, repo_root=tmp_path, corpus_root=corpus, now=NOW)
    assert (live.state, live.ok) == ("OK", True)
    assert "2026-08-13" in live.detail, "the empty newer day must not win"


def test_a_halted_stream_stays_absent_when_only_old_packed_days_exist(tmp_path):
    """Widening to .gz must not resurrect a halted stream: the packed OPRA days
    are real, but they are outside the window and absence stays correct."""
    corpus = tmp_path / "corpus"
    corpus_day(corpus, "2026-08-13", "es.jsonl")
    corpus_day(corpus, "2026-08-01", "opra.jsonl.gz")
    reg = ent.load_registry(write_registry(tmp_path, STREAMS))
    _, halted = ent.run_probes(reg, repo_root=tmp_path, corpus_root=corpus, now=NOW)
    assert (halted.state, halted.ok) == ("ABSENT", True)


# ─── closed archives: a feed that ended is not a feed gone stale [st-qcj3] ───

CLOSED = """
probed:
  archive:
    label: GexBot /hist archive
    vendor: GexBot
    what: closed after the tier drop
    kind: path_present
    path: hist
    expect: present
    expect_within_days: 4
    final_day: "2026-08-01"
"""


def test_a_closed_archive_ending_on_its_final_day_is_ok_not_stale(tmp_path):
    (tmp_path / "hist" / "2026-07-31").mkdir(parents=True)
    (tmp_path / "hist" / "2026-08-01").mkdir(parents=True)
    reg = ent.load_registry(write_registry(tmp_path, CLOSED))
    line, = ent.run_probes(reg, repo_root=tmp_path, corpus_root=tmp_path, now=NOW)
    assert (line.state, line.ok) == ("OK", True)
    assert "closed" in line.detail and "2026-08-01" in line.detail


def test_a_closed_archive_that_moved_past_its_final_day_alarms(tmp_path):
    """The registry and the disk disagreeing is the fact worth seeing — either
    the entitlement did not really end or someone wrote into the record."""
    (tmp_path / "hist" / "2026-08-01").mkdir(parents=True)
    (tmp_path / "hist" / "2026-08-05").mkdir(parents=True)
    reg = ent.load_registry(write_registry(tmp_path, CLOSED))
    line, = ent.run_probes(reg, repo_root=tmp_path, corpus_root=tmp_path, now=NOW)
    assert line.state == "ALARM" and not line.ok
    assert "GREW" in line.detail


def test_the_live_registry_closes_the_hist_archive_on_the_day_we_swept(tmp_path):
    """Pins the registry itself: /hist is Quant-only and Quant ended, so the
    archive must be declared closed or it alarms every day forever."""
    reg = ent.load_registry()
    entry, = [e for e in ent.entries(reg, "probed") if e["id"] == "gexbot_hist_archive"]
    assert entry["final_day"] == "2026-09-04"


# ─── dated assertions ────────────────────────────────────────────────────────

DATED = """
meta:
  dated_stale_after_days: 30
dated:
  fresh:
    label: Fresh plan
    vendor: V
    state: active
    what: w
    cost: $1/mo
    confirmed_on: "2026-08-05"
    confirmed_by: Steve
    source: portal
  old:
    label: Old plan
    vendor: V
    state: active
    what: w
    cost: $2/mo
    confirmed_on: "2026-01-01"
    confirmed_by: Steve
    source: portal
  due:
    label: Review plan
    vendor: V
    state: active
    what: w
    cost: $3/mo
    confirmed_on: "2026-08-05"
    confirmed_by: Steve
    source: portal
    review_by: "2026-08-12"
  never:
    label: Unknown plan
    vendor: V
    state: unconfirmed
    what: w
    cost: unconfirmed
    confirmed_on: null
    confirmed_by: null
    source: portal
"""


def test_a_list_shaped_section_still_carries_its_ids():
    """The file is id-keyed today; the reader must not break if it is ever
    re-shaped into a list of entries carrying their own id."""
    as_list = {"dated": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}
    assert [e["id"] for e in ent.entries(as_list, "dated")] == ["a", "b"]
    assert ent.entries({}, "probed") == []


def test_dated_verdicts_age_confirm_and_review(tmp_path):
    reg = ent.load_registry(write_registry(tmp_path, DATED))
    verdicts = {d.id: d.verdict for d in ent.read_dated(reg, now=NOW)}
    assert verdicts == {"fresh": "DATED", "old": "AGED", "due": "REVIEW DUE", "never": "NEVER"}


def test_never_confirmed_is_listed_but_does_not_alarm_daily(tmp_path):
    """A standing gap must stay visible without making the check cry wolf every
    session — unless the caller asks for strict."""
    reg_path = write_registry(tmp_path, DATED.replace('confirmed_on: "2026-01-01"',
                                                      'confirmed_on: "2026-08-05"')
                                             .replace('review_by: "2026-08-12"',
                                                      'review_by: "2026-09-30"'))
    report = ent.build_report(reg_path, repo_root=tmp_path, now=NOW)
    assert [d.id for d in report.needs_steve] == ["never"]
    assert report.actionable() is False
    assert report.actionable(strict=True) is True


def test_an_open_question_inside_a_dated_entry_surfaces(tmp_path):
    reg_path = write_registry(tmp_path, DATED + "    needs_steve: what does it cost?\n")
    report = ent.build_report(reg_path, repo_root=tmp_path, now=NOW)
    assert "never" in [d.id for d in report.needs_steve]
    assert any(d.question for d in report.dated)


# ─── the report itself ───────────────────────────────────────────────────────

def test_report_separates_observations_from_dated_assertions(tmp_path):
    health(tmp_path, "_tok.json")
    reg_path = write_registry(tmp_path, PROBED_ONLY + DATED)
    text = ent.render(ent.build_report(reg_path, repo_root=tmp_path, now=NOW))
    observed, _, dated = text.partition("DATED — NOT observations")
    assert "OBSERVED" in observed and dated
    # Every dated line carries its date or an explicit NEVER — never bare.
    assert "2026-08-05" in dated and "NEVER" in dated
    # The probed surface appears above the divider, not among the assertions.
    assert "Token health" in observed and "Token health" not in dated


def test_cli_exit_codes_and_json(tmp_path, capsys):
    health(tmp_path, "_tok.json", checked_at="2026-08-11T13:30:00Z")  # stale -> actionable
    reg_path = write_registry(tmp_path, PROBED_ONLY)
    rc = ep.main(["--registry", str(reg_path), "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1 and payload["actionable"] is True
    assert payload["probed"][0]["kind"] == "probed"


def test_cli_reports_a_missing_registry_loudly(tmp_path, capsys):
    rc = ep.main(["--registry", str(tmp_path / "nope.yaml")])
    err = capsys.readouterr().err
    assert rc == 2 and "INTERNAL ERROR" in err


def test_the_probe_touches_no_network(monkeypatch, tmp_path):
    """Belt and braces: the probe must not open a socket, ever."""
    import socket

    def boom(*a, **k):  # pragma: no cover - only runs if the probe regresses
        raise AssertionError("entitlements probe attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    ent.render(ent.build_report(LIVE_REGISTRY, now=NOW))


def test_live_report_renders_end_to_end():
    """The real registry against the real repo — no fixtures, no network."""
    text = ent.render(ent.build_report(LIVE_REGISTRY), verbose=True)
    assert "ENTITLEMENTS" in text and "OBSERVED" in text and "DATED" in text
    assert "GexBot" in text and "Databento" in text and "Schwab" in text


@pytest.mark.parametrize("field_", ["confirmed_on", "confirmed_by", "source"])
def test_dated_entries_never_lose_their_provenance_fields(field_):
    reg = ent.load_registry(LIVE_REGISTRY)
    assert all(field_ in e for e in ent.entries(reg, "dated"))
