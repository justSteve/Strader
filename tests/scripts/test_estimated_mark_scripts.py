"""estimated_mark_calibrate.py / estimated_mark_validate.py — the acceptance
gate in miniature: two runs over one date range with unchanged code are
byte-identical, on a synthetic two-day corpus. [st-9hhc]

Deterministic, no network, no real corpus. One summer and one winter day so
the DST offset is exercised end to end.
"""
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent


def load_script(name: str):
    # The scripts' pools run with the spawn start method and their workers
    # live in strader.marks.jobs (importable), so nothing here needs to be
    # picklable by module name — fork was rejected because a fork under a
    # multi-threaded pytest parent can deadlock the child, order-dependently.
    spec = importlib.util.spec_from_file_location(
        name, REPO / "scripts" / "measurement" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def opra_line(ts_utc: str, symbol: str, price: float) -> str:
    return json.dumps({
        "stream": "databento_opra",
        "provenance": {"dataset": "OPRA.PILLAR", "schema": "trades",
                       "parent_symbol": "SPXW.OPT", "ts_event": ts_utc},
        "data": {"symbol": symbol, "instrument_id": 1, "price": round(price, 2),
                 "size": 1, "side": "N", "action": "T"},
    })


def es_line(ts_utc: str, price: float) -> str:
    return json.dumps({
        "stream": "databento_glbx_es",
        "provenance": {"dataset": "GLBX.MDP3", "schema": "trades",
                       "ts_event": ts_utc},
        "data": {"symbol": "ES", "price": round(price, 2), "size": 1, "side": "B"},
    })


def write_day(root: Path, day: str, off_hours: int, spx: float) -> None:
    """One synthetic corpus day: prints for 5 strikes x C/P every 30s and an
    ES trade every 30s, 13:00-15:00 CT, prices drifting deterministically."""
    y, m, d = day.split("-")
    exp = f"{y[2:]}{m}{d}"
    ddir = root / "data" / "corpus" / day
    ddir.mkdir(parents=True)
    opra, es = [], []
    for i in range(241):  # every 30s over two hours
        ct_s = 13 * 3600 + 30 * i
        utc_s = ct_s - off_hours * 3600
        ts = f"{day}T{utc_s // 3600:02d}:{utc_s % 3600 // 60:02d}:{utc_s % 60:02d}.000000000+00:00"
        drift = ((i * 13) % 41 - 20) * 0.25   # deterministic wobble, +-5 pts
        es.append(es_line(ts, spx + 15.0 + drift))
        for k in range(int(spx) - 10, int(spx) + 11, 5):
            c_val = max(spx + drift - k, 0.0) + 1.0
            p_val = max(k - spx - drift, 0.0) + 1.0
            opra.append(opra_line(ts, f"SPXW  {exp}C{k * 1000:08d}", c_val))
            opra.append(opra_line(ts, f"SPXW  {exp}P{k * 1000:08d}", p_val))
    # one day plain, gzip the other via suffix choice on day parity
    if day.endswith("5"):
        with gzip.open(ddir / "databento_opra.jsonl.gz", "wt") as f:
            f.write("\n".join(opra) + "\n")
    else:
        (ddir / "databento_opra.jsonl").write_text("\n".join(opra) + "\n")
    (ddir / "databento_glbx_es.jsonl").write_text("\n".join(es) + "\n")


@pytest.fixture()
def fixture_corpus(tmp_path, monkeypatch):
    write_day(tmp_path, "2025-06-02", -5, 6000.0)   # summer
    write_day(tmp_path, "2026-01-05", -6, 6900.0)   # winter
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_calibrate_then_validate_byte_identical(fixture_corpus, tmp_path, capsys):
    cal_mod = load_script("estimated_mark_calibrate")
    val_mod = load_script("estimated_mark_validate")
    out = tmp_path / "out"
    out.mkdir()

    for tag in ("a", "b"):
        rc = cal_mod.main(["x", str(out / f"legdays-{tag}.jsonl"),
                           str(out / f"cal-{tag}.json")])
        assert rc == 0
    assert (out / "legdays-a.jsonl").read_bytes() == (out / "legdays-b.jsonl").read_bytes()
    assert (out / "cal-a.json").read_bytes() == (out / "cal-b.json").read_bytes()

    for tag in ("a", "b"):
        rc = val_mod.main(["x", str(out / "cal-a.json"),
                           str(out / f"val-{tag}.jsonl")])
        assert rc == 0
    assert (out / "val-a.jsonl").read_bytes() == (out / "val-b.jsonl").read_bytes()

    rows = [json.loads(l) for l in (out / "val-a.jsonl").read_text().splitlines()]
    scored = [r for r in rows if r.get("skip") is None]
    assert len(rows) == 2 * 4 * 6          # 2 days x 4 entries x 6 legs
    assert scored, "fixture produced no scoreable leg-days"
    for r in scored:
        assert r["close_print"] >= 0 and r["close_proxy"] >= 0
        assert r["cut030"]["level"] == pytest.approx(r["entry"] - 0.30)
        assert r["tgt25"]["level"] == pytest.approx(r["entry"] * 1.25)
    # both days present: the winter offset produced usable CT windows too
    assert {r["day"] for r in rows} == {"2025-06-02", "2026-01-05"}


def test_fit_through_bounds_the_fit(fixture_corpus, tmp_path, capsys):
    cal_mod = load_script("estimated_mark_calibrate")
    out = tmp_path / "out2"
    out.mkdir()
    rc = cal_mod.main(["x", str(out / "legdays.jsonl"), str(out / "cal.json"),
                       "--fit-through", "2025-12-31"])
    assert rc == 0
    cal = json.loads((out / "cal.json").read_text())
    assert cal["fit_days"] == "2025-06-02..2025-06-02"
    rows = [json.loads(l) for l in (out / "legdays.jsonl").read_text().splitlines()]
    by_day = {r["day"]: r["in_fit"] for r in rows}
    assert by_day == {"2025-06-02": True, "2026-01-05": False}
