"""Sweep a corpus stream for duplicate rows. [st-c078]

st-c078 measured 2026-07-20 ES trades at 51% duplicates against a 1.4-3.0%
normal band and asked whether other days carry it. The first pass (below,
2026-09-02) answered that for trades. On 2026-09-10 Strader found a second
defect shape the trades-only sweep could not see — two live writers running
after a reboot (09-08 03:06-06:44 CT and 08-28 03:31-03:48 CT), both repaired
by scripts/corpus_repair_doubled_span.py, and on 09-08 the DEPTH stream held
660k duplicate rows on its own. This sweep now covers all three corpus
streams via ``--stream {trades,depth,opra}``.

TRADES RESULT, 2026-09-02 over 291 days: **2026-07-20 is the only affected
day**, at 50.4% (332,768 of 660,208 rows). Every other day sits in a
0.7-1.7% band — median 0.73%, mean 0.90%, exactly one day over 5%. So the
contamination is isolated, not systemic, and no other day needs re-cutting.
Trades behaviour (row schema, file resolution, skip-on-missing, output
shape) is unchanged by the depth/opra extension — verified byte-for-byte
against this history.

DUPLICATE KEYS, one per stream, chosen from the row shape each schema
actually writes (checked by reading sample rows and counting field
population, st-c078):

  trades (databento_glbx_es, databento_opra "trades" schema): a print is
  identified by (ts_event, price, size, sequence). OPRA adds instrument_id —
  a single ES front-month has one symbol per file, but OPRA is a multi-
  thousand-instrument feed, so instrument_id guards against two different
  option prints that happen to collide on the other four fields. (Measured:
  zero such collisions in a 21k-row sample, but the feed doesn't promise
  that holds everywhere.)

  depth (databento_glbx_es_mbp1, "mbp-1" schema): price/size/sequence are
  NOT reliably populated the way they are for trades — measured on
  2026-09-07 (486,760 rows), 209,557 rows are quote-only book snapshots
  (only bid_px/ask_px/bid_sz/ask_sz set, everything else None) and 277,203
  are trade-tagged mbp-1 messages (action/side/price/size/sequence/bid_ct/
  ask_ct all set). A trades-shaped key would collapse every quote-only row
  sharing a ts_event to one bucket — wrong. So the depth key is effectively
  the whole row: (ts_event, instrument_id, sequence, action, side, price,
  size, bid_px, ask_px, bid_sz, ask_sz, bid_ct, ask_ct, flags) — the same
  "everything but ts_pull_utc" duplicate definition
  corpus_repair_doubled_span.py already validated for this stream, just as
  a field tuple instead of a line hash (the fields left out — dataset,
  schema, continuous_symbol, stype_in, source, symbol — are constant within
  a stream file or redundant with instrument_id, so omitting them doesn't
  change what counts as a duplicate).

A day whose file for the requested stream is absent is skipped. For
``--stream trades`` that skip is silent, matching the original script (no
day in the corpus is actually missing an ES trades file today, so this
never fires in practice, but the behaviour is preserved on principle). For
``--stream depth`` and ``--stream opra`` — new capability, no byte-identical
promise to keep — the skip prints a line, because depth in particular is
absent for most of the corpus (the collector is recent) and a silent skip
would look like a near-empty sweep rather than "not collected yet."

Re-run: .venv/bin/python3 scripts/measurement/corpus_duplicate_sweep.py
    [--stream trades|depth|opra] [--since YYYY-MM-DD] [--corpus PATH]
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from market.corpus.opra import opra_key_fields  # noqa: E402

CORPUS = Path("data/corpus")

# stream name -> file stem under a day directory
STREAMS = {
    "trades": "databento_glbx_es",
    "depth": "databento_glbx_es_mbp1",
    "opra": "databento_opra",
}


def resolve_file(d: Path, stem: str) -> Path | None:
    """The readable file for ``stem`` under day dir ``d``: .gz preferred (this
    sweep's own long-standing convention for the trades stream), else plain
    .jsonl, else None."""
    f = d / f"{stem}.jsonl.gz"
    if f.exists():
        return f
    f2 = d / f"{stem}.jsonl"
    return f2 if f2.exists() else None


def row_key(stream: str, r: dict) -> tuple:
    """The fields that make one row of ``stream`` unique. See module docstring
    for why each stream gets a different key."""
    data = r.get("data") or {}
    prov = r.get("provenance") or {}
    ts = prov.get("ts_event")
    if stream == "trades":
        return (ts, data.get("price"), data.get("size"), data.get("sequence"))
    if stream == "opra":
        return opra_key_fields(r)      # ONE definition: market/corpus/opra.py (the read guard's)
    if stream == "depth":
        return (ts, data.get("instrument_id"), data.get("sequence"), data.get("action"),
                 data.get("side"), data.get("price"), data.get("size"), data.get("bid_px"),
                 data.get("ask_px"), data.get("bid_sz"), data.get("ask_sz"),
                 data.get("bid_ct"), data.get("ask_ct"), data.get("flags"))
    raise ValueError(f"unknown stream {stream!r}")


def sweep_file(f: Path, stream: str) -> tuple[int, int]:
    """One streaming pass over ``f``: return (rows, duplicates). A row whose
    key is entirely None (unparseable / no identifying fields at all) is
    skipped and not counted — for trades this is exactly the original
    script's ``key == (None, None, None, None)`` guard, generalized to any
    key width."""
    seen: set[tuple] = set()
    n = dup = 0
    opener = gzip.open if f.suffix == ".gz" else open
    with opener(f, "rt") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            key = row_key(stream, r)
            if all(v is None for v in key):
                continue
            n += 1
            if key in seen:
                dup += 1
            else:
                seen.add(key)
    return n, dup


def sweep(stream: str, *, corpus: Path = CORPUS, since: str | None = None) -> list[tuple]:
    """Sweep every day directory in ``corpus`` for ``stream``. Prints progress
    exactly as the original trades-only script did (HIGH lines and read
    errors), plus a skip line for depth/opra when a day has no file for the
    stream. Returns the collected (day, rows, dup, pct) rows."""
    stem = STREAMS[stream]
    days = sorted(d for d in corpus.iterdir() if d.is_dir() and d.name[:2] == "20")
    if since:
        days = [d for d in days if d.name >= since]
    rows = []
    for d in days:
        f = resolve_file(d, stem)
        if f is None:
            if stream != "trades":
                print(f"{d.name}  SKIP no {stem} file", flush=True)
            continue
        try:
            n, dup = sweep_file(f, stream)
        except (OSError, EOFError) as e:
            print(f"{d.name}  READ ERROR {type(e).__name__}: {e}", flush=True)
            continue
        if n:
            pct = 100.0 * dup / n
            rows.append((d.name, n, dup, pct))
            if pct > 5.0:
                print(f"{d.name}  rows={n:>9,}  dup={dup:>9,}  {pct:5.1f}%   <<< HIGH", flush=True)
    return rows


def report(rows: list[tuple]) -> None:
    rows = sorted(rows, key=lambda r: -r[3])
    print()
    print("=== TOP 15 BY DUPLICATE RATE ===")
    for name, n, dup, pct in rows[:15]:
        print(f"{name}  rows={n:>9,}  dup={dup:>9,}  {pct:5.1f}%")
    print()
    print(f"days scanned: {len(rows)}")
    pcts = [r[3] for r in rows]
    if pcts:
        print(f"median {statistics.median(pcts):.2f}%  mean {statistics.fmean(pcts):.2f}%  max {max(pcts):.1f}%")
        print(f"days over 5%: {sum(1 for p in pcts if p > 5)}")
        print(f"days over 10%: {sum(1 for p in pcts if p > 10)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stream", choices=sorted(STREAMS), default="trades")
    ap.add_argument("--since", help="only sweep days >= this YYYY-MM-DD (US/Central)")
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    args = ap.parse_args(argv)
    rows = sweep(args.stream, corpus=args.corpus, since=args.since)
    report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
