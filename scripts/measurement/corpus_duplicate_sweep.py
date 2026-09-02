"""Sweep the ES trades corpus for duplicate rows. [st-c078]

st-c078 measured 2026-07-20 at 51% duplicates against a 1.4-3.0% normal band
and asked whether other days carry it. This is that sweep, and it answers the
question.

RESULT, 2026-09-02 over 291 days: **2026-07-20 is the only affected day**, at
50.4% (332,768 of 660,208 rows). Every other day sits in a 0.7-1.7% band —
median 0.73%, mean 0.90%, exactly one day over 5%. So the contamination is
isolated, not systemic, and no other day needs re-cutting.

A "row" is keyed on the fields that make a print unique: event timestamp,
price, size and sequence. Two rows sharing all four are the same print
delivered twice — a collector restart replaying, or a backfill appended over
live capture. The ~1% baseline is genuine: distinct prints do legitimately
collide on all four at high message rates, which is why the normal band is a
band and not zero.

Re-run: .venv/bin/python3 scripts/measurement/corpus_duplicate_sweep.py
"""
import gzip, json, sys
from pathlib import Path

CORPUS = Path("data/corpus")
rows = []
days = sorted(d for d in CORPUS.iterdir() if d.is_dir() and d.name[:2] == "20")
for d in days:
    f = d / "databento_glbx_es.jsonl.gz"
    if not f.exists():
        f2 = d / "databento_glbx_es.jsonl"
        if not f2.exists():
            continue
        f = f2
    seen = set()
    n = dup = 0
    opener = gzip.open if f.suffix == ".gz" else open
    try:
        with opener(f, "rt") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                data = r.get("data") or {}
                prov = r.get("provenance") or {}
                key = (prov.get("ts_event"), data.get("price"),
                       data.get("size"), data.get("sequence"))
                if key == (None, None, None, None):
                    continue
                n += 1
                if key in seen:
                    dup += 1
                else:
                    seen.add(key)
    except (OSError, EOFError) as e:
        print(f"{d.name}  READ ERROR {type(e).__name__}: {e}", flush=True)
        continue
    if n:
        pct = 100.0 * dup / n
        rows.append((d.name, n, dup, pct))
        if pct > 5.0:
            print(f"{d.name}  rows={n:>9,}  dup={dup:>9,}  {pct:5.1f}%   <<< HIGH", flush=True)

rows.sort(key=lambda r: -r[3])
print()
print("=== TOP 15 BY DUPLICATE RATE ===")
for name, n, dup, pct in rows[:15]:
    print(f"{name}  rows={n:>9,}  dup={dup:>9,}  {pct:5.1f}%")
print()
import statistics
pcts = [r[3] for r in rows]
print(f"days scanned: {len(rows)}")
if pcts:
    print(f"median {statistics.median(pcts):.2f}%  mean {statistics.fmean(pcts):.2f}%  max {max(pcts):.1f}%")
    print(f"days over 5%: {sum(1 for p in pcts if p > 5)}")
    print(f"days over 10%: {sum(1 for p in pcts if p > 10)}")
