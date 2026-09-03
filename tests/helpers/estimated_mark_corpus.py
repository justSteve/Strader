"""A synthetic corpus day for the estimated-mark tests. [st-9hhc]

Writes the two files strader.marks reads, in the exact shape the corpus
carries them: one JSON object per line, the usable timestamp under
``provenance.ts_event`` as ISO 8601 UTC with nanoseconds, the payload under
``data``. A decoy top-level ``ts_event`` is written on every row so a reader
that trusts the top level is caught by the tests rather than by a P&L column.

The option prices are synthetic and honest to the model's *shape* only
(intrinsic plus a time value that decays as the square root of minutes
remaining and shrinks away from the money); the tests assert structure,
determinism and guards, never a market number.
"""
from __future__ import annotations

import gzip
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
BASIS = 20.0            # ES - SPX, held constant
PRINT_EVERY_S = 10      # option prints per symbol
ES_EVERY_S = 1


def _utc_iso(day: str, sec_ct: int) -> str:
    y, m, d = (int(x) for x in day.split("-"))
    local = datetime(y, m, d, tzinfo=CT) + timedelta(seconds=sec_ct)
    u = local.astimezone(timezone.utc)
    return u.strftime("%Y-%m-%dT%H:%M:%S") + ".000000000+00:00"


def _sec(hhmm: str) -> int:
    return (int(hhmm[:2]) * 60 + int(hhmm[3:])) * 60


def synthetic_premium(right: str, strike: float, spx: float, sec_ct: int, *, close_sec: int) -> float:
    tau_min = max(0.0, (close_sec - sec_ct) / 60.0)
    intrinsic = max(0.0, (strike - spx) if right == "P" else (spx - strike))
    m = (strike - spx) if right == "P" else (spx - strike)   # ITM-positive
    tv = 3.0 * math.sqrt(tau_min / 120.0) * math.exp(-(m * m) / (2 * 12.0 ** 2))
    return round(max(0.05, intrinsic + tv) * 20) / 20   # nickel grid


def write_day(corpus: Path, day: str, *, seed: int, gz: bool = False,
              opra_from: str = "13:00", opra_to: str = "15:00",
              es_from: str = "12:00", es_to: str = "15:00",
              es_start: float = 6420.0, drift_per_min: float = 0.0,
              decoy_top_level_ts: bool = True) -> Path:
    """One corpus day. Returns the day directory."""
    rng = random.Random(seed)
    d = corpus / day
    d.mkdir(parents=True, exist_ok=True)
    close_sec = _sec("15:00")
    # ES path: a per-second random walk with a chosen drift.
    es_path: list[tuple[int, float]] = []
    es = es_start
    for s in range(_sec(es_from), _sec(es_to), ES_EVERY_S):
        es += rng.gauss(drift_per_min / 60.0, 0.12)
        es_path.append((s, round(es * 4) / 4))
    es_by_sec = dict(es_path)

    def es_at(s: int) -> float:
        while s not in es_by_sec:
            s -= 1
        return es_by_sec[s]

    def row(ts_sec: int, data: dict) -> str:
        r = {"provenance": {"ts_event": _utc_iso(day, ts_sec), "source": "synthetic"}, "data": data}
        if decoy_top_level_ts:
            r["ts_event"] = "1970-01-01T00:00:00Z"
        return json.dumps(r) + "\n"

    es_name = "databento_glbx_es.jsonl" + (".gz" if gz else "")
    with (gzip.open(d / es_name, "wt") if gz else open(d / es_name, "w")) as f:
        for s, p in es_path:
            f.write(row(s, {"symbol": "ESZ5", "price": p, "size": 1, "side": "B" if rng.random() < 0.5 else "A"}))

    # Option prints: strikes on the 5-pt grid within +-60 of the 13:00 spot.
    spx0 = es_at(_sec("13:00")) - BASIS
    base = int(round(spx0 / 5.0)) * 5
    strikes = [base + 5 * k for k in range(-12, 13)]
    y, m, dd = day.split("-")
    exp = f"{y[2:]}{m}{dd}"
    opra_name = "databento_opra.jsonl" + (".gz" if gz else "")
    with (gzip.open(d / opra_name, "wt") if gz else open(d / opra_name, "w")) as f:
        # A far-dated symbol that must be ignored (not 0DTE).
        f.write(row(_sec(opra_from) + 1, {"symbol": "SPXW  991231C06000000", "price": 1.0, "size": 1}))
        for s in range(_sec(opra_from), _sec(opra_to), PRINT_EVERY_S):
            spx = es_at(s) - BASIS
            for k in strikes:
                for right in ("P", "C"):
                    sym = f"SPXW  {exp}{right}{int(k * 1000):08d}"
                    px = synthetic_premium(right, k, spx, s, close_sec=close_sec)
                    f.write(row(s + (1 if right == "C" else 0), {"symbol": sym, "price": px, "size": 1}))
    (d / "manifest.json").write_text(json.dumps({"day": day, "synthetic": True}) + "\n")
    return d


def write_corpus(corpus: Path, days: dict[str, dict]) -> None:
    """``days`` maps day -> keyword arguments for :func:`write_day`."""
    for i, (day, kw) in enumerate(sorted(days.items())):
        write_day(corpus, day, seed=kw.pop("seed", 100 + i), **kw)
