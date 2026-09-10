"""corpus_repair_doubled_span: drop the second live writer's rows from the span
two streamers wrote at once — and refuse everything else. [st-7kwg]

Measured 2026-09-08: strader-capture-evening started at the 03:06 boot beside
strader-capture and both appended to one file until 06:45 CT. Trades and depth
were 49-50% duplicate per half hour inside that span and 0.1-0.8% outside it.
"""
import gzip
import json
from datetime import date
from pathlib import Path

import pytest

import scripts.corpus_repair_doubled_span as rp
from market.corpus import paths

DAY = date(2026, 9, 8)
STREAM = "databento_glbx_es"


def _row(hh: int, mm: int, ss: int, seq: int, *, pull: str = "2026-09-08T08:00:00Z") -> str:
    """One live trades row at hh:mm:ss UTC (CT = UTC-5 on this day)."""
    return json.dumps({
        "ts_pull_utc": pull,
        "stream": STREAM,
        "provenance": {"dataset": "GLBX.MDP3", "schema": "trades", "continuous_symbol": "ES.c.0",
                       "stype_in": "continuous",
                       "ts_event": f"2026-09-08T{hh:02d}:{mm:02d}:{ss:02d}.000000{seq % 1000:03d}+00:00",
                       "source": "live"},
        "data": {"symbol": "ESU6", "instrument_id": 1, "price": 7690.0 + seq % 7, "size": 1,
                 "side": "A", "action": "T", "sequence": seq, "flags": None},
    })


def _tape(doubled_utc: tuple[int, int] | None, *, rows_per_minute: int = 4) -> list[str]:
    """08:00-13:00 UTC (03:00-08:00 CT), one writer; a second writer's copy of
    every row inside ``doubled_utc`` (hours, inclusive-exclusive) with its own
    ts_pull_utc, interleaved the way two appenders leave it."""
    out = []
    seq = 0
    for hh in range(8, 13):
        for mm in range(60):
            for k in range(rows_per_minute):
                seq += 1
                r = _row(hh, mm, k * 10, seq)
                out.append(r)
                if doubled_utc and doubled_utc[0] <= hh < doubled_utc[1]:
                    out.append(_row(hh, mm, k * 10, seq, pull="2026-09-08T08:00:01Z"))
    return out


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    (root / DAY.isoformat()).mkdir(parents=True)
    monkeypatch.setattr(rp, "day_dir", lambda d: root / d.isoformat())
    monkeypatch.setattr(rp, "manifest_path", lambda d: root / d.isoformat() / "manifest.json")
    monkeypatch.setattr(paths, "CORPUS_ROOT", root)  # belt and braces: nothing reaches the real corpus
    return root


def _write(corpus: Path, rows: list[str], *, gz: bool = True) -> Path:
    p = corpus / DAY.isoformat() / (f"{STREAM}.jsonl" + (".gz" if gz else ""))
    body = "".join(r + "\n" for r in rows).encode()
    p.write_bytes(gzip.compress(body) if gz else body)
    return p


def _read(p: Path) -> list[bytes]:
    raw = gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
    return raw.splitlines()


class TestSurvey:
    def test_finds_the_doubled_run_in_ct_minutes(self, corpus):
        p = _write(corpus, _tape((9, 11)))  # 09:00-10:59 UTC = 04:00-05:59 CT
        s = rp.survey(p, None, min_share=0.35)
        assert s.span == (4 * 60, 5 * 60 + 59)
        assert s.span_share == pytest.approx(0.5)
        assert s.outside_dups == 0

    def test_a_given_span_is_used_as_is(self, corpus):
        p = _write(corpus, _tape((9, 11)))
        s = rp.survey(p, (4 * 60, 4 * 60 + 59), min_share=0.35)
        assert s.span == (240, 299)
        assert s.span_dups == 60 * 4

    def test_nul_and_unclosed_lines_are_not_rows(self, corpus):
        rows = _tape(None)
        rows.insert(50, "\x00" * 40 + rows[50])
        rows.insert(70, rows[70][:-5])
        p = _write(corpus, rows)
        s = rp.survey(p, None, min_share=0.35)
        assert s.n_unparsed == 2
        assert s.span is None


class TestVerdicts:
    def test_dry_run_reports_and_writes_nothing(self, corpus, capsys):
        p = _write(corpus, _tape((9, 11)))
        before = p.read_bytes()
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM]) == 0
        out = capsys.readouterr().out
        assert "doubled span: 04:00-05:59 CT" in out and "dry run" in out
        assert p.read_bytes() == before
        assert not (corpus / DAY.isoformat() / "manifest.json").exists()

    def test_clean_tape_is_nothing_to_repair(self, corpus):
        _write(corpus, _tape(None))
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"]) == 2

    def test_a_span_that_is_not_doubled_is_refused(self, corpus, capsys):
        p = _write(corpus, _tape(None))
        rc = rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply",
                      "--from-ct", "04:00", "--to-ct", "05:59"])
        assert rc == 2  # zero duplicates in the span: nothing to do
        rows = _tape(None)
        rows.append(rows[100])  # one stray duplicate inside the span
        p = _write(corpus, rows)
        rc = rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply",
                      "--from-ct", "03:00", "--to-ct", "07:59"])
        assert rc == 1 and "REFUSED" in capsys.readouterr().out
        assert len(_read(p)) == len(rows)

    def test_doubling_outside_the_span_is_refused(self, corpus, capsys):
        p = _write(corpus, _tape((8, 13)))  # doubled everywhere
        rc = rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply",
                      "--from-ct", "04:00", "--to-ct", "05:59"])
        assert rc == 1
        assert "outside the span" in capsys.readouterr().out
        assert len(_read(p)) == len(_tape((8, 13)))

    def test_missing_tape_is_a_usage_error(self, corpus):
        assert rp.main(["--date", DAY.isoformat(), "--stream", "nope"]) == 3
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--from-ct", "04:00"]) == 3


class TestApply:
    @pytest.mark.parametrize("gz", [True, False])
    def test_drops_second_copies_in_the_span_and_nothing_else(self, corpus, gz, capsys):
        rows = _tape((9, 11))
        rows.insert(3, "\x00" * 40 + rows[3])  # the scrambled line, outside the span
        p = _write(corpus, rows, gz=gz)
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"]) == 0
        kept = _read(p)
        clean = [r.encode() for r in _tape(None)]
        assert kept == clean  # first copies survive in order; the NUL line is gone
        assert not list((corpus / DAY.isoformat()).glob("*.repair-tmp"))
        m = json.loads((corpus / DAY.isoformat() / "manifest.json").read_text())
        s = m["streams"][STREAM]
        assert s["cycles"] == len(clean)
        assert s["repair"] == {"dropped_duplicate_rows": 480, "dropped_unparseable_rows": 1,
                               "kept_rows": len(clean), "span_ct": "04:00-05:59"}
        assert "repaired [st-7kwg]" in m["notes"][-1]["note"]
        assert (corpus / DAY.isoformat() / "manifest.lock").exists()
        assert "REPAIRED" in capsys.readouterr().out

    def test_legitimate_collisions_outside_the_span_are_kept(self, corpus):
        rows = _tape((9, 11))
        rows.append(rows[10])  # a baseline collision at 03:00 CT, outside the span
        p = _write(corpus, rows)
        assert rp.main(["--date", DAY.isoformat(), "--stream", STREAM, "--apply"]) == 0
        assert len(_read(p)) == len(_tape(None)) + 1

    def test_a_changed_file_aborts_the_rewrite(self, corpus, monkeypatch):
        p = _write(corpus, _tape((9, 11)))
        with pytest.raises(rp.RepairError):
            rp.rewrite_without_span_duplicates(p, (240, 359), expect_keep=1)
        assert len(_read(p)) == len(_tape((9, 11)))
        assert not list((corpus / DAY.isoformat()).glob("*.repair-tmp"))
