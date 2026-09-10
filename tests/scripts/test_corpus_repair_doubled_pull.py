"""corpus_repair_doubled_pull: drop the copies a batch pull that ran twice left
behind — and refuse everything that is not provably the same pull. [st-c078]

Measured 2026-07-20: `databento_glbx_es.jsonl` carries two ts_pull_utc stamps
(11:30:59Z, 11:31:14Z) of 330,104 rows each whose content hashes to one digest,
and `databento_opra.jsonl` two of 512,151. The runs interleave on disk because
`append_jsonl` opens and closes per row, so the copies are not two halves.
"""
import gzip
import json
from datetime import date
from pathlib import Path

import pytest

import scripts.corpus_repair_doubled_pull as rp
from market.corpus import paths

DAY = date(2026, 7, 20)
STREAM = "databento_glbx_es"
PULL_A = "2026-07-21T11:30:59Z"
PULL_B = "2026-07-21T11:31:14Z"
PULL_C = "2026-07-21T11:32:00Z"


def _row(seq: int, *, pull: str, price: float | None = None) -> str:
    """One batch trades row. No `source: live` — a batch pull stamps none."""
    return json.dumps({
        "ts_pull_utc": pull,
        "stream": STREAM,
        "provenance": {"dataset": "GLBX.MDP3", "schema": "trades",
                       "continuous_symbol": "ES.c.0",
                       "ts_event": f"2026-07-20T13:30:{seq // 100:02d}.{seq % 100:09d}+00:00"},
        "data": {"symbol": "ES.c.0", "instrument_id": 42140870,
                 "price": 7534.5 + (seq % 7) if price is None else price,
                 "size": 1 + seq % 3, "side": "B", "action": "T",
                 "sequence": 3944516 + seq // 2, "flags": 0},
    })


def _one_run(pull: str, n: int = 40) -> list[str]:
    """A run's own output: n rows, including a pair that agrees on every
    published field — the aggressor-fills-two-resting-orders shape a keyed
    dedup would destroy."""
    rows = [_row(i, pull=pull) for i in range(n)]
    rows.insert(11, rows[10])
    return rows


def _interleaved(n: int = 40, *, second_starts_at: int = 17) -> list[str]:
    """Two runs appending to one file, the second starting mid-way through the
    first — the 2026-07-20 shape, not two contiguous halves."""
    a, b = _one_run(PULL_A, n), _one_run(PULL_B, n)
    out = a[:second_starts_at]
    ai, bi = second_starts_at, 0
    while ai < len(a) or bi < len(b):
        if ai < len(a):
            out.append(a[ai]); ai += 1
        if bi < len(b):
            out.append(b[bi]); bi += 1
    return out


def _prefix_tape(n: int = 40, cut: int = 25, second_starts_at: int = 8):
    """A run cut off after ``cut`` rows and re-run in full 25 minutes later —
    the 2026-07-14 depth shape. The short run is stamped EARLIER, so keeping
    it would be the default choice and must be overridden. Returns
    (tape, short_rows, long_rows)."""
    long_rows = _one_run(PULL_B, n)
    short_rows = [r.replace(PULL_B, PULL_A) for r in long_rows[:cut]]
    out = short_rows[:second_starts_at]
    si, li = second_starts_at, 0
    while si < len(short_rows) or li < len(long_rows):
        if si < len(short_rows):
            out.append(short_rows[si]); si += 1
        if li < len(long_rows):
            out.append(long_rows[li]); li += 1
    return out, short_rows, long_rows


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    (root / DAY.isoformat()).mkdir(parents=True)
    monkeypatch.setattr(rp, "day_dir", lambda d: root / d.isoformat())
    monkeypatch.setattr(rp, "manifest_path", lambda d: root / d.isoformat() / "manifest.json")
    monkeypatch.setattr(paths, "CORPUS_ROOT", root)  # nothing reaches the real corpus
    return root


def _write(corpus: Path, rows: list[str], *, gz: bool = False) -> Path:
    p = corpus / DAY.isoformat() / (f"{STREAM}.jsonl" + (".gz" if gz else ""))
    body = "".join(r + "\n" for r in rows).encode()
    p.write_bytes(gzip.compress(body) if gz else body)
    return p


def _read(p: Path) -> list[bytes]:
    raw = gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
    return raw.splitlines()


class TestSurvey:
    def test_separates_the_runs_and_proves_them_identical(self, corpus):
        s = rp.survey(_write(corpus, _interleaved()))
        assert [r.stamp for r in s.sorted_runs] == [PULL_A, PULL_B]
        assert [r.rows for r in s.sorted_runs] == [41, 41]
        assert s.counts_agree and s.content_agrees
        assert s.total == 82 and s.n_unattributable == 0

    def test_one_run_is_one_run(self, corpus):
        s = rp.survey(_write(corpus, _one_run(PULL_A)))
        assert len(s.runs) == 1 and s.content_agrees

    def test_a_changed_row_breaks_the_content_guard(self, corpus):
        rows = _interleaved()
        rows[-1] = _row(39, pull=PULL_B, price=1.0)
        s = rp.survey(_write(corpus, rows))
        assert s.counts_agree and not s.content_agrees

    def test_nul_and_unclosed_lines_are_unattributable(self, corpus):
        rows = _interleaved()
        rows.insert(5, "\x00" * 40 + rows[5])
        rows.insert(9, rows[9][:-5])
        s = rp.survey(_write(corpus, rows))
        assert s.n_unattributable == 2


class TestVerdicts:
    def test_dry_run_reports_and_writes_nothing(self, corpus, capsys):
        p = _write(corpus, _interleaved())
        before = p.read_bytes()
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM]) == 0
        out = capsys.readouterr().out
        assert "pull runs   : 2" in out and "dry run" in out
        assert p.read_bytes() == before
        assert not (corpus / DAY.isoformat() / "manifest.json").exists()
        assert not list((corpus / DAY.isoformat()).glob("*.pre-repair-*"))

    def test_a_single_run_is_nothing_to_repair(self, corpus):
        _write(corpus, _one_run(PULL_A))
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"]) == 2

    def test_a_shorter_run_that_is_not_a_prefix_is_refused(self, corpus, capsys):
        """Different lengths and the short run holds rows the long one does
        not: a windowed re-pull, and dropping it would leave a hole."""
        short = [_row(i, pull=PULL_A, price=1.0) for i in range(20)]
        p = _write(corpus, short + _one_run(PULL_B))
        rc = rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"])
        assert rc == 1 and "not an exact prefix" in capsys.readouterr().err
        assert len(_read(p)) == 20 + 41

    def test_a_tie_for_longest_is_refused(self, corpus, capsys):
        """Two runs of equal length and a third short one: no single complete
        run to keep, even though the long pair may well be identical."""
        rows = _one_run(PULL_A) + _one_run(PULL_B) + [_row(98, pull=PULL_C)]
        p = _write(corpus, rows)
        rc = rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"])
        assert rc == 1 and "tied for longest" in capsys.readouterr().err
        assert len(_read(p)) == len(rows)

    def test_runs_that_disagree_on_content_are_refused(self, corpus, capsys):
        rows = _interleaved()
        rows[-1] = _row(39, pull=PULL_B, price=1.0)
        p = _write(corpus, rows)
        rc = rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"])
        assert rc == 1 and "disagree on content or order" in capsys.readouterr().err
        assert len(_read(p)) == len(rows)

    def test_runs_that_disagree_on_order_are_refused(self, corpus, capsys):
        """Same rows, different order: a re-pull, not a re-run."""
        a, b = _one_run(PULL_A), _one_run(PULL_B)
        p = _write(corpus, a + b[::-1])
        rc = rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"])
        assert rc == 1 and "disagree on content or order" in capsys.readouterr().err
        assert len(_read(p)) == 82

    def test_unattributable_rows_refuse_until_allowed(self, corpus, capsys):
        rows = _interleaved()
        rows.insert(5, "\x00" * 40 + rows[5])
        p = _write(corpus, rows)
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"]) == 1
        assert "no usable ts_pull_utc" in capsys.readouterr().err
        assert len(_read(p)) == 83
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply",
                        "--drop-unattributable"]) == 0
        assert _read(p) == [r.encode() for r in _one_run(PULL_A)]

    def test_missing_tape_and_bad_date_are_usage_errors(self, corpus):
        assert rp.main(["--date", DAY.isoformat(), "--stream", "nope"]) == 3
        assert rp.main(["--date", "not-a-date", "--stream", STREAM]) == 3

    def test_unknown_keep_pull_is_a_usage_error(self, corpus):
        _write(corpus, _interleaved())
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM,
                        "--keep-pull", "2026-01-01T00:00:00Z"]) == 3


class TestApply:
    @pytest.mark.parametrize("gz", [False, True])
    def test_keeps_the_first_run_byte_for_byte(self, corpus, gz, capsys):
        p = _write(corpus, _interleaved(), gz=gz)
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"]) == 0
        assert _read(p) == [r.encode() for r in _one_run(PULL_A)]
        assert not list((corpus / DAY.isoformat()).glob("*.repair-tmp"))
        assert "REPAIRED" in capsys.readouterr().out

    def test_the_run_s_own_repeated_row_survives(self, corpus):
        """A keyed dedup would drop it; it is a real print, not damage."""
        p = _write(corpus, _interleaved())
        rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"])
        kept = _read(p)
        assert kept[10] == kept[11]
        assert len(kept) == 41  # 40 distinct rows + the legitimate repeat

    def test_backup_is_written_before_the_rewrite(self, corpus):
        rows = _interleaved()
        p = _write(corpus, rows)
        before = p.read_bytes()
        rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"])
        backups = list((corpus / DAY.isoformat()).glob(f"{STREAM}.jsonl.pre-repair-*"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == before

    def test_no_backup_leaves_none(self, corpus):
        p = _write(corpus, _interleaved())
        rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply", "--no-backup"])
        assert not list((corpus / DAY.isoformat()).glob("*.pre-repair-*"))
        assert len(_read(p)) == 41

    def test_keep_pull_selects_the_named_run(self, corpus):
        p = _write(corpus, _interleaved())
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply",
                        "--keep-pull", PULL_B]) == 0
        assert _read(p) == [r.encode() for r in _one_run(PULL_B)]

    def test_manifest_carries_the_repair_record(self, corpus):
        _write(corpus, _interleaved())
        rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"])
        m = json.loads((corpus / DAY.isoformat() / "manifest.json").read_text())
        s = m["streams"][STREAM]
        assert s["cycles"] == 41
        assert s["repair"]["dropped_duplicate_rows"] == 41
        assert s["repair"]["dropped_unparseable_rows"] == 0
        assert s["repair"]["kept_rows"] == 41
        assert s["repair"]["kept_pull_utc"] == PULL_A
        assert s["repair"]["dropped_pull_utc"] == [PULL_B]
        assert len(s["repair"]["identical_run_digest"]) == 32
        assert s["repair"]["duplicate_shape"] == "identical"
        assert f"repaired [{rp.BEAD}]" in m["notes"][-1]["note"]
        assert (corpus / DAY.isoformat() / "manifest.lock").exists()

    def test_prefix_run_keeps_the_completed_pull(self, corpus, capsys):
        tape, short_rows, long_rows = _prefix_tape()
        p = _write(corpus, tape)
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"]) == 0
        assert _read(p) == [r.encode() for r in long_rows]
        out = capsys.readouterr().out
        assert "prefix runs" in out and f"prefix of {PULL_B}: True" in out
        m = json.loads((corpus / DAY.isoformat() / "manifest.json").read_text())
        s = m["streams"][STREAM]
        assert s["cycles"] == len(long_rows)
        assert s["repair"]["kept_pull_utc"] == PULL_B          # the LATER run
        assert s["repair"]["dropped_pull_utc"] == [PULL_A]
        assert s["repair"]["dropped_duplicate_rows"] == len(short_rows)
        assert s["repair"]["duplicate_shape"] == "prefix"
        assert "was cut off before finishing" in m["notes"][-1]["note"]

    def test_prefix_survey_sees_the_disagreement(self, corpus):
        tape, short_rows, long_rows = _prefix_tape()
        p = _write(corpus, tape)
        s = rp.survey(p)
        assert not s.counts_agree and not s.content_agrees
        keep = rp.longest_run(s)
        assert keep.stamp == PULL_B and keep.rows == len(long_rows)
        assert rp.prefix_verdicts(p, s, keep) == {PULL_A: True}

    def test_keep_pull_cannot_name_a_prefix_run(self, corpus, capsys):
        tape, _, long_rows = _prefix_tape()
        p = _write(corpus, tape)
        rc = rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply",
                      "--keep-pull", PULL_A])
        assert rc == 3 and "is a PREFIX of" in capsys.readouterr().err
        assert len(_read(p)) == len(tape)

    def test_a_changed_file_aborts_the_rewrite(self, corpus):
        p = _write(corpus, _interleaved())
        with pytest.raises(rp.RepairError):
            rp.rewrite_keeping_run(p, PULL_A, expect_keep=1)
        assert len(_read(p)) == 82
        assert not list((corpus / DAY.isoformat()).glob("*.repair-tmp"))

    def test_backup_refuses_to_overwrite(self, corpus):
        p = _write(corpus, _interleaved())
        dest = p.with_name(f"{p.name}.pre-repair-20260710T000000Z")
        dest.write_bytes(b"prior")
        with pytest.raises(rp.RepairError):
            rp.back_up(p, stamp_utc="20260710T000000Z")
        assert dest.read_bytes() == b"prior"
