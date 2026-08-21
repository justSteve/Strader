"""corpus_repair_doubled_day: drop a duplicate batch pull, but only when the
live tape provably covers it. [co-j5qzq]

Measured 2026-08-19: the MBP-1 depth tape closed at 12,377,582 rows against a
6,250,382 median across 28 days, because the T+1 batch pull ran onto a live
tape that already held 08:30-15:00 CT. The write-side guard is fixed; these
tests pin the read-side repair, and above all the REFUSALS — a repair that
drops a batch pull covering a genuine hole leaves a hole no consumer can see.
"""
import gzip
import json
from datetime import date
from pathlib import Path

import pytest

import scripts.corpus_repair_doubled_day as rp

DAY = date(2026, 8, 19)


# ── fixtures ───────────────────────────────────────────────────────────────

def _row(ts: str, *, live: bool) -> str:
    """One corpus row shaped like the real tape.

    Live rows carry provenance.source and the resolved contract; batch rows
    carry neither and name the continuous symbol. Key ORDER matters to the
    byte-level scanner, so it matches what corpus_stream_databento.py writes.
    """
    prov = {
        "dataset": "GLBX.MDP3",
        "schema": "mbp-1",
        "continuous_symbol": "ES.c.0",
        "ts_event": ts,
    }
    if live:
        prov["stype_in"] = "continuous"
        prov["ts_event"] = ts
        prov["source"] = "live"
    return json.dumps({
        "ts_pull_utc": "2026-08-19T05:00:03Z" if live else "2026-08-20T11:31:52Z",
        "stream": "databento_glbx_es_mbp1",
        "provenance": prov,
        "data": {"symbol": "ESU6" if live else "ES.c.0", "price": 7731.25},
    })


def _ts(second: int, *, nanos: int | None = None) -> str:
    """13:30:00 UTC + `second`, optionally with nanosecond precision."""
    h, rem = divmod(13 * 3600 + 30 * 60 + second, 3600)
    m, s = divmod(rem, 60)
    stamp = f"2026-08-19T{h:02d}:{m:02d}:{s:02d}"
    if nanos is None:
        return stamp + "+00:00"
    return f"{stamp}.{nanos:09d}+00:00"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """A corpus root the repair module reads, with day/manifest helpers bound."""
    root = tmp_path / "corpus"
    (root / DAY.isoformat()).mkdir(parents=True)
    monkeypatch.setattr(rp, "day_dir", lambda d: root / d.isoformat())
    monkeypatch.setattr(rp, "manifest_path", lambda d: root / d.isoformat() / "manifest.json")
    return root


def _write_tape(corpus: Path, rows: list[str], *, gz: bool = False) -> Path:
    name = "databento_glbx_es_mbp1.jsonl" + (".gz" if gz else "")
    p = corpus / DAY.isoformat() / name
    body = "".join(r + "\n" for r in rows)
    if gz:
        p.write_bytes(gzip.compress(body.encode()))
    else:
        p.write_text(body, encoding="utf-8")
    return p


def _write_manifest(corpus: Path, cycles: int) -> Path:
    p = corpus / DAY.isoformat() / "manifest.json"
    p.write_text(json.dumps({
        "date": DAY.isoformat(),
        "streams": {"databento_glbx_es_mbp1": {"cycles": cycles, "errors": []}},
        "notes": [],
    }))
    return p


def _doubled(n: int = 60) -> list[str]:
    """`n` live rows one second apart, then the same window pulled as batch."""
    return ([_row(_ts(i), live=True) for i in range(n)] +
            [_row(_ts(i), live=False) for i in range(n)])


def _holed() -> list[str]:
    """A live tape dense on both sides of a 302 s outage, plus a batch pull
    spanning the whole window.

    Sized so the RATIO guard passes (299 live rows against 300 batch rows) and
    only the GAP guard can refuse — otherwise the test proves nothing about
    which guard fired.
    """
    live = ([_row(_ts(i), live=True) for i in range(0, 150)] +
            [_row(_ts(i), live=True) for i in range(451, 601)])
    batch = [_row(_ts(i), live=False) for i in range(0, 600, 2)]
    return live + batch


def _run(*args) -> int:
    return rp.main(["--date", DAY.isoformat(),
                    "--stream", "databento_glbx_es_mbp1", *args])


# ── timestamp parsing ──────────────────────────────────────────────────────

def test_parses_both_timestamp_shapes_and_keeps_nanoseconds():
    """Databento emits nanoseconds; two rows can share a microsecond, so a
    parser that truncates would merge them and understate a gap."""
    plain = rp.parse_ts_event(_row("2026-08-19T13:30:00+00:00", live=True).encode())
    nano = rp.parse_ts_event(_row("2026-08-19T13:30:00.000000001+00:00", live=True).encode())
    assert nano - plain == 1
    micro = rp.parse_ts_event(_row("2026-08-19T13:30:00.123456+00:00", live=True).encode())
    assert micro - plain == 123_456_000


def test_unparsable_rows_are_counted_not_crashed(corpus):
    _write_tape(corpus, [_row(_ts(0), live=True), "{}", "not json at all"])
    s = rp.survey(corpus / DAY.isoformat() / "databento_glbx_es_mbp1.jsonl")
    assert (s.n_live, s.n_batch, s.n_unparsed) == (1, 0, 2)


# ── survey ─────────────────────────────────────────────────────────────────

def test_survey_separates_live_from_batch_and_finds_the_span(corpus):
    _write_tape(corpus, _doubled(10))
    s = rp.survey(corpus / DAY.isoformat() / "databento_glbx_es_mbp1.jsonl")
    assert s.n_live == 10 and s.n_batch == 10 and s.total == 20
    assert rp.fmt_ns(s.batch_first).startswith("2026-08-19T13:30:00")
    assert rp.fmt_ns(s.batch_last).startswith("2026-08-19T13:30:09")
    assert s.live_in_span == 10
    assert s.max_gap_seconds == pytest.approx(1.0)


def test_survey_scopes_the_gap_measure_to_the_batch_span(corpus):
    """A long silence OUTSIDE the batch window is none of this repair's
    business — only coverage of what would be dropped matters."""
    rows = ([_row(_ts(0), live=True)] +                      # a lone early row
            [_row(_ts(i), live=True) for i in range(600, 610)] +
            [_row(_ts(i), live=False) for i in range(600, 610)])
    _write_tape(corpus, rows)
    s = rp.survey(corpus / DAY.isoformat() / "databento_glbx_es_mbp1.jsonl")
    assert s.max_gap_seconds == pytest.approx(1.0)   # not the 600 s silence


# ── refusals: the guard is the point ───────────────────────────────────────

def test_refuses_when_the_live_tape_has_a_hole_inside_the_batch_span(corpus, capsys):
    """The batch pull was covering a real outage. Dropping it would trade a
    visible duplicate for an invisible hole."""
    _write_tape(corpus, _holed())
    _write_manifest(corpus, 600)
    assert _run("--apply") == 1
    err = capsys.readouterr().err
    assert "REFUSED" in err and "302.000 s gap" in err
    assert "of the batch row count" not in err          # the GAP guard, not the ratio
    assert "windowed --force re-pull" in err


def test_refuses_when_live_rows_are_too_thin_against_the_batch(corpus, capsys):
    """No single long gap, but the live tape is a sparse shadow of the batch —
    many small holes are a hole too."""
    live = [_row(_ts(i), live=True) for i in range(0, 60, 10)]   # 6 rows
    batch = [_row(_ts(i), live=False) for i in range(0, 60)]     # 60 rows
    _write_tape(corpus, live + batch)
    _write_manifest(corpus, 66)
    assert _run("--apply") == 1
    err = capsys.readouterr().err
    assert "REFUSED" in err and "10.00% of the batch row count" in err


def test_refuses_a_batch_only_tape(corpus, capsys):
    """These rows are the day's only record; there is nothing to fall back to."""
    _write_tape(corpus, [_row(_ts(i), live=False) for i in range(10)])
    _write_manifest(corpus, 10)
    assert _run("--apply") == 1
    assert "batch-only" in capsys.readouterr().err


def test_a_refusal_leaves_the_tape_byte_identical(corpus):
    p = _write_tape(corpus, _holed())
    _write_manifest(corpus, 600)
    before = p.read_bytes()
    assert _run("--apply") == 1
    assert p.read_bytes() == before
    assert not list(p.parent.glob("*.repair-tmp"))


def test_a_clean_tape_reports_nothing_to_repair(corpus):
    _write_tape(corpus, [_row(_ts(i), live=True) for i in range(10)])
    _write_manifest(corpus, 10)
    assert _run("--apply") == 2


def test_thresholds_are_operator_overridable(corpus):
    """A 302 s hole refuses by default and passes when the operator widens the
    limit — the knob exists so a judged case need not bypass the tool."""
    _write_tape(corpus, _holed())
    _write_manifest(corpus, 600)
    assert _run() == 1
    assert _run("--max-gap-seconds", "600") == 0


# ── the repair itself ──────────────────────────────────────────────────────

def test_dry_run_is_the_default_and_writes_nothing(corpus, capsys):
    p = _write_tape(corpus, _doubled(30))
    mf = _write_manifest(corpus, 60)
    before, before_mf = p.read_bytes(), mf.read_text()
    assert _run() == 0
    out = capsys.readouterr().out
    assert "GUARDS PASS" in out and "DRY RUN" in out
    assert p.read_bytes() == before and mf.read_text() == before_mf


def test_apply_keeps_every_live_row_and_drops_every_batch_row(corpus):
    p = _write_tape(corpus, _doubled(30))
    _write_manifest(corpus, 60)
    assert _run("--apply") == 0
    kept = [json.loads(ln) for ln in p.read_text().splitlines()]
    assert len(kept) == 30
    assert all(r["provenance"].get("source") == "live" for r in kept)
    assert [r["provenance"]["ts_event"] for r in kept] == [_ts(i) for i in range(30)]


def test_apply_sets_the_manifest_count_and_records_why(corpus):
    """A SET, not an increment — the count was wrong, and an increment cannot
    say that. The note has to leave the event legible to a later reader."""
    _write_tape(corpus, _doubled(30))
    mf = _write_manifest(corpus, 60)
    assert _run("--apply") == 0
    m = json.loads(mf.read_text())
    s = m["streams"]["databento_glbx_es_mbp1"]
    assert s["cycles"] == 30
    assert s["repair"] == {"dropped_batch_rows": 30, "kept_live_rows": 30}
    assert "repaired_utc" in s
    note = m["notes"][-1]
    assert note["stream"] == "databento_glbx_es_mbp1"
    assert "REPAIR [co-j5qzq]" in note["note"] and "dropped 30" in note["note"]


def test_repair_is_idempotent(corpus):
    """Running it twice must not be a second, silent edit."""
    p = _write_tape(corpus, _doubled(30))
    _write_manifest(corpus, 60)
    assert _run("--apply") == 0
    after = p.read_bytes()
    assert _run("--apply") == 2          # nothing left to repair
    assert p.read_bytes() == after


def test_a_compacted_day_is_repaired_in_place_as_gzip(corpus):
    """corpus_compact_databento.py packs finished days and removes the source,
    so a repair that only knew .jsonl would report a doubled day as missing."""
    _write_tape(corpus, _doubled(30), gz=True)
    _write_manifest(corpus, 60)
    assert _run("--apply") == 0
    p = corpus / DAY.isoformat() / "databento_glbx_es_mbp1.jsonl.gz"
    rows = gzip.decompress(p.read_bytes()).decode().splitlines()
    assert len(rows) == 30
    assert all(json.loads(r)["provenance"].get("source") == "live" for r in rows)


def test_rewrite_refuses_to_land_when_the_count_disagrees(corpus):
    """The one thing that must never happen quietly: a rewrite that kept a
    different number of rows than the survey measured means the file moved
    under the repair."""
    p = _write_tape(corpus, _doubled(30))
    with pytest.raises(rp.RepairError, match="the file changed under the repair"):
        rp.rewrite_without_batch(p, expect_keep=999)
    assert len(p.read_text().splitlines()) == 60      # original intact
    assert not list(p.parent.glob("*.repair-tmp"))


def test_missing_day_is_a_usage_error_not_a_crash(corpus, capsys):
    assert rp.main(["--date", "2026-08-18",
                    "--stream", "databento_glbx_es_mbp1"]) == 3
    assert "no corpus file at" in capsys.readouterr().err


def test_bad_date_is_rejected(corpus, capsys):
    assert rp.main(["--date", "19-08-2026",
                    "--stream", "databento_glbx_es_mbp1"]) == 3
    assert "must be YYYY-MM-DD" in capsys.readouterr().err
