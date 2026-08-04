#!/usr/bin/env python3
"""Corpus pull: NYSE market internals minute candles via Schwab. [st-3fr]

Fetches $TICK / $TRIN / $ADD / $VOLD / $VIX minute candles from Schwab price
history and writes them into the per-day corpus
(`data/corpus/YYYY-MM-DD/internals.jsonl`, one row per symbol-minute).
Schwab's minute history is a ROLLING ~47-day window — running this weekly
makes the history permanent before it rolls off.

$VIX added 2026-08-03 [st-cdwe]; $VIX9D/$VIX3M [st-40fv] and $VVIX
[st-lru8] same day; $VIX1D/$COR1M/$COR3M 2026-08-04 [st-b3jq] completing
the vol-complex roster. Probed and NOT served (do not re-probe blind):
$SKEW(+.X), put/call ($PCSP/$PCALL/$PC), $DXY(+.X). /ZN and TLT serve but
are cross-asset with different session semantics — deliberately not in
this stream. Index symbols are bare (`$VIX` —
`$VIX.X` returns EMPTY), serve ~389 RTH minute candles/day with v=0 (indices
— volume is meaningless). Rows before the add dates carry fewer symbols.

Idempotent by day: a day whose file already exists is skipped, EXCEPT the
current session day, which is always rewritten (it may have been partial on
the previous run). One API call per symbol covers the whole range.

CAPTURE VERIFICATION [st-kzhe]
------------------------------
Until 2026-08-04 `fetch_symbol` returned [] on an empty Schwab response and
wrote nothing, so a symbol that had stopped serving looked exactly like a
symbol nobody had counted. st-b3jq then closed on "zero rows lost" — a check
of the OLD symbols — while asserting a capture of the three NEW ones that was
not on disk (auditor's report §1.4/§5.4, 2026-08-04). Every run now grades
itself and says so out loud:

  * `summarize_window()` prints a per-symbol days/candles/rows-written table
    on EVERY run, pass or fail. That is an artifact property a bead close can
    quote instead of a process claim.
  * `verify_capture()` grades each symbol against SYMBOL_SPECS, which encodes
    what that symbol is documented to serve. A named symbol that owed a
    session and did not deliver it exits 1; a run that structurally cannot
    verify exits 2. Both are nonzero, so the pull-failure alerting lane
    (st-c3r) has a signal to catch, and the two are distinct so "symbol not
    serving" is never confused with "nobody checked".

Timing is load-bearing because three symbols have no history behind them.
$VIX1D/$COR1M/$COR3M serve the CURRENT session only — a 2026-08-04 08:57 CT
pull landed 27 candles each, stamped 08:31→08:57 and nothing before it,
against ~12k rolling candles for the older symbols. There is no window to
backfill from, ever, so a session missed is a session gone. The 06:30 CT
corpus cron (`scripts/corpus_daily.py`) runs two hours before the 08:30 CT
cash open and therefore cannot capture them at all; that run now exits 2
naming them, every weekday, until a post-open pull exists.

Usage:
    .venv/bin/python scripts/corpus_pull_internals.py              # last 45 days
    .venv/bin/python scripts/corpus_pull_internals.py --days 10
    .venv/bin/python scripts/corpus_pull_internals.py --force      # rewrite all

Exit codes:
    0  every symbol served the session it owed
    1  a named symbol owed a session and did not serve it (or its fetch failed)
    2  verification inconclusive — nothing available to grade against
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker_schwab.client import create_client  # noqa: E402
from market.corpus.paths import central_date, internals_path  # noqa: E402
from market.corpus.writer import append_jsonl, update_manifest, utc_now_iso  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")

#: Wall-clock CT by which the session's first minute candle is queryable —
#: cash open 08:30 plus a few minutes' grace. `need_extended_hours_data=False`
#: means nothing exists before the open, so a run earlier than this has none of
#: today's candles to grade and must say "not verified", not "verified empty".
FIRST_CANDLE_CT = time(8, 33)

ROLLING = "rolling"
SESSION_ONLY = "session_only"


@dataclass(frozen=True)
class SymbolSpec:
    """What a symbol is documented to serve, so a gap can be graded, not guessed.

    added
        Session this symbol entered SYMBOLS. Corpus days before it carry fewer
        symbols by construction — never a finding. On-disk coverage can start
        EARLIER than `added`: the original four went in on 2026-07-23 and the
        rolling window backfilled them to 2026-06-08.
    history
        ROLLING      — Schwab serves ~47 days back, so a missed run is
                       recoverable and a hole inside the window is a defect.
        SESSION_ONLY — serves the live session and nothing behind it. No
                       backfill is possible; a missed session is permanent
                       loss, which is why these are graded against the live
                       session rather than the last completed one.
    lag_sessions
        Sessions between a candle printing and Schwab serving it. $ADD and
        $VOLD publish a session late, so the current session is never
        available from them and the previous one is what gets verified. This
        is a lower bound: a symbol that turns out to be more current still
        passes.
    """

    added: date
    history: str
    lag_sessions: int = 0


#: The roster, in fetch order, paired with what each member owes a run.
SYMBOL_SPECS: dict[str, SymbolSpec] = {
    "$TICK":  SymbolSpec(date(2026, 7, 23), ROLLING),
    "$TRIN":  SymbolSpec(date(2026, 7, 23), ROLLING),
    "$ADD":   SymbolSpec(date(2026, 7, 23), ROLLING, lag_sessions=1),
    "$VOLD":  SymbolSpec(date(2026, 7, 23), ROLLING, lag_sessions=1),
    "$VIX":   SymbolSpec(date(2026, 8, 3), ROLLING),
    "$VIX9D": SymbolSpec(date(2026, 8, 3), ROLLING),
    "$VIX3M": SymbolSpec(date(2026, 8, 3), ROLLING),
    "$VVIX":  SymbolSpec(date(2026, 8, 3), ROLLING),
    "$VIX1D": SymbolSpec(date(2026, 8, 4), SESSION_ONLY),
    "$COR1M": SymbolSpec(date(2026, 8, 4), SESSION_ONLY),
    "$COR3M": SymbolSpec(date(2026, 8, 4), SESSION_ONLY),
}
SYMBOLS = tuple(SYMBOL_SPECS)

#: Longest-serving symbol. The days IT returned are the sessions this pull saw,
#: which is how the run knows what a session is without a market calendar —
#: holidays need no modelling because they simply are not in its day set. If
#: this symbol is silent there is no frame to grade anything else against.
REFERENCE_SYMBOL = "$TICK"


def fetch_symbol(client, symbol: str, days: int) -> list[dict]:
    """Fetch `days` of minute candles for one symbol.

    Returns [] when Schwab answers 200 with `empty: true` — a real answer
    ("this symbol serves nothing over that range"), announced on stderr rather
    than swallowed. Callers must NOT read [] as success: an empty list is the
    exact shape a dead symbol and an unrequested symbol share, which is the
    ambiguity `verify_capture()` exists to remove.
    """
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
    r = client.get_price_history_every_minute(
        symbol, start_datetime=start, end_datetime=end,
        need_extended_hours_data=False,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{symbol}: HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    if data.get("empty"):
        print(f"  {symbol}: Schwab returned empty=true over the {days}d window",
              file=sys.stderr)
        return []
    return data.get("candles", [])


def summarize_window(day_counts: dict[str, Counter],
                     written_rows: Counter,
                     errors: dict[str, str],
                     dupes: Counter) -> list[str]:
    """Per-symbol day and row inventory for the pulled window.

    Printed on every run, passing or failing. This is the table a human or a
    bead close quotes: it names days, candles kept, and rows actually appended
    per symbol, so "the capture landed" is a claim someone can check in one
    glance rather than a process assertion nobody can audit (report §4).
    """
    lines = ["  symbol    days   candles   written  first        last"]
    for sym in SYMBOL_SPECS:
        if sym in errors:
            lines.append(f"  {sym:7s}   ERR   {errors[sym][:64]}")
            continue
        served = day_counts.get(sym, Counter())
        if not served:
            # Zero days is a real, reportable outcome — not a row to omit.
            lines.append(f"  {sym:7s} {0:>6} {0:>9} {0:>9}  {'—':<12} —")
            continue
        days = sorted(served)
        lines.append(f"  {sym:7s} {len(days):>6} {sum(served.values()):>9,} "
                     f"{written_rows.get(sym, 0):>9,}  {days[0]}   {days[-1]}")

    session_only = [s for s, sp in SYMBOL_SPECS.items() if sp.history == SESSION_ONLY]
    late = [s for s, sp in SYMBOL_SPECS.items() if sp.lag_sessions]
    lines.append(f"  legend: session-only, no backfill possible — {' '.join(session_only)}")
    lines.append(f"          publishes a session late — {' '.join(late)}")
    if dupes:
        drops = " ".join(f"{s}={n}" for s, n in sorted(dupes.items()))
        lines.append(f"  duplicate candles dropped (healed/clamped overlap): {drops}")
    return lines


def verify_capture(day_counts: dict[str, Counter],
                   errors: dict[str, str],
                   *,
                   now_ct: datetime | None = None,
                   specs: dict[str, SymbolSpec] | None = None,
                   ) -> tuple[int, list[str]]:
    """Grade a completed pull against what each symbol is documented to serve.

    `day_counts` maps symbol -> Counter(session date -> candles kept after
    dedup). `errors` maps symbol -> failure text for symbols whose fetch raised.

    Sessions come off REFERENCE_SYMBOL rather than a market calendar this repo
    does not have: the days it served ARE the sessions this pull saw. Each
    rolling symbol owes the session at `sessions[-1 - lag_sessions]`; each
    session-only symbol owes the live session, and can only be verified while
    that session is running.

    Returns `(exit_code, report_lines)`:
        0  every symbol served the session it owed
        1  a named symbol owed a session and did not serve it, or its fetch
           failed — a real capture defect
        2  inconclusive: the run could not verify (pre-open, or the reference
           symbol itself silent). Nonzero on purpose, so "nobody checked" is
           alertable, but distinct from 1 so it is not read as "not serving".
    """
    specs = specs or SYMBOL_SPECS
    now_ct = (now_ct or datetime.now(CENTRAL)).astimezone(CENTRAL)
    today = central_date(now_ct)
    is_weekday = now_ct.weekday() < 5
    open_passed = is_weekday and now_ct.time() >= FIRST_CANDLE_CT

    lines: list[str] = [f"# capture verification ({now_ct:%Y-%m-%d %H:%M} CT)"]
    failures: list[str] = []
    unverified: list[str] = []

    sessions = sorted(day_counts.get(REFERENCE_SYMBOL, Counter()))
    if not sessions:
        why = errors.get(REFERENCE_SYMBOL, "returned no candles")
        lines.append(f"  {REFERENCE_SYMBOL:7s} DEAD  {why}")
        lines.append(f"VERIFY: INCONCLUSIVE — reference symbol {REFERENCE_SYMBOL} "
                     f"served nothing, so there is no session frame to grade the "
                     f"other {len(specs) - 1} symbols against. Nothing here says "
                     f"they are healthy.")
        return 2, lines

    today_live = today in sessions
    reference_failed = not today_live and open_passed
    if reference_failed:
        # The reference symbol is the one thing that should always be there
        # during a live session. Its absence is the "nobody checked" case
        # wearing the "not serving" costume, and it must not pass quietly.
        failures.append(REFERENCE_SYMBOL)
        lines.append(
            f"  {REFERENCE_SYMBOL:7s} FAIL  no candle for {today} though the cash "
            f"session opened at 08:30 CT — feed outage, expired Schwab token, or "
            f"a market holiday. Confirm which before treating the corpus as complete.")

    for sym, spec in specs.items():
        if sym == REFERENCE_SYMBOL and reference_failed:
            continue  # already graded above; do not also credit it for older days
        if sym in errors:
            failures.append(sym)
            lines.append(f"  {sym:7s} FAIL  fetch failed: {errors[sym]}")
            continue
        served = day_counts.get(sym, Counter())

        if spec.history == SESSION_ONLY:
            if today_live:
                n = served.get(today, 0)
                if n:
                    lines.append(f"  {sym:7s} OK    {n:>5,} candles for live session "
                                 f"{today} (session-only history)")
                else:
                    failures.append(sym)
                    lines.append(f"  {sym:7s} FAIL  no candle for live session {today}. "
                                 f"Serves ~1 session and cannot be backfilled — this "
                                 f"session is lost unless a later pull today recovers it.")
            elif open_passed:
                # The session is running but the reference symbol never saw it,
                # so there is no frame to check these against either.
                unverified.append(sym)
                lines.append(f"  {sym:7s} SKIP  session {today} should be open but "
                             f"{REFERENCE_SYMBOL} served no candle for it (above) — "
                             f"capture unverifiable, and unrecoverable if it was missed")
            elif is_weekday:
                unverified.append(sym)
                lines.append(f"  {sym:7s} SKIP  pre-open run ({now_ct:%H:%M} CT, cash "
                             f"open 08:30 CT): serves the live session only, so this "
                             f"run cannot capture it at all. A post-open pull must.")
            else:
                lines.append(f"  {sym:7s} n/a   no live session on {today}; serves the "
                             f"live session only")
            continue

        depth = 1 + spec.lag_sessions
        if len(sessions) < depth:
            unverified.append(sym)
            lines.append(f"  {sym:7s} SKIP  window holds {len(sessions)} session(s); "
                         f"needs {depth} to reach this symbol's expected day")
            continue
        target = sessions[-depth]
        n = served.get(target, 0)
        note = " (publishes a session late)" if spec.lag_sessions else ""
        if n:
            lines.append(f"  {sym:7s} OK    {n:>5,} candles for session {target}{note}")
        else:
            failures.append(sym)
            lines.append(f"  {sym:7s} FAIL  no candle for session {target}{note}; "
                         f"{len(served)} day(s) served across the window")

    if failures:
        lines.append(f"VERIFY: FAIL — {len(failures)} symbol(s) owed a session and did "
                     f"not serve it: {', '.join(failures)}")
        return 1, lines
    if unverified:
        lines.append(f"VERIFY: INCONCLUSIVE — {len(unverified)} symbol(s) this run "
                     f"could not verify: {', '.join(unverified)}. The rest passed.")
        return 2, lines
    lines.append(f"VERIFY: PASS — all {len(specs)} symbols served their expected "
                 f"session (latest session in window: {sessions[-1]})")
    return 0, lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Corpus internals pull (Schwab minute candles)")
    ap.add_argument("--days", type=int, default=45,
                    help="how far back to request (default 45; Schwab wall ~47)")
    ap.add_argument("--force", action="store_true",
                    help="rewrite existing day files instead of skipping them")
    args = ap.parse_args(argv)

    client = create_client()
    ts_pull = utc_now_iso()
    today = central_date()

    # day -> list of (symbol, candle) in fetch order
    by_day: dict = defaultdict(list)
    day_counts: dict[str, Counter] = {}
    errors: dict[str, str] = {}
    dupes: Counter = Counter()
    for sym in SYMBOLS:
        try:
            candles = fetch_symbol(client, sym, args.days)
        except Exception as e:  # noqa: BLE001
            # One dead symbol must not cost the other ten their capture: the
            # three session-only symbols cannot be re-pulled tomorrow. Record
            # it, name it on stderr now, and fail the run at verification.
            print(f"  {sym}: fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
            errors[sym] = f"{type(e).__name__}: {e}"
            day_counts[sym] = Counter()
            continue
        # Schwab serves the just-settled day TWICE in one response: the healed
        # (negative-capable) segment first, then the stale same-day clamped
        # segment (lows/closes floored at 0). First-wins dedup keeps the
        # healed series (observed 2026-07-23, st-3fr).
        seen: set = set()
        counts: Counter = Counter()
        for c in candles:
            ts = datetime.fromtimestamp(c["datetime"] / 1000,
                                        tz=timezone.utc).astimezone(CENTRAL)
            if (sym, ts) in seen:
                dupes[sym] += 1
                continue
            seen.add((sym, ts))
            by_day[ts.date()].append((sym, ts, c))
            counts[ts.date()] += 1
        day_counts[sym] = counts

    written = skipped = 0
    written_rows: Counter = Counter()
    preserved_rows: Counter = Counter()
    for day in sorted(by_day):
        out = internals_path(day)
        if out.exists() and not args.force and day != today:
            skipped += 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        # Rewriting an existing day must never lose rows the fetch can no
        # longer see: $VIX1D/$COR1M/$COR3M serve ~1 session of history and the
        # whole endpoint is a rolling ~47-day wall, so a dropped row is
        # unrecoverable. Merge instead of replace — the fresh fetch wins per
        # (symbol, candle-ts); existing rows absent from the fetch survive.
        preserved: list[str] = []
        if out.exists():
            fetched = {(s, t.isoformat()) for s, t, _ in by_day[day]}
            for raw in out.read_text(encoding="utf-8").splitlines():
                try:
                    prov = json.loads(raw)["provenance"]
                    key = (prov["symbol"], prov["ts_candle"])
                except (ValueError, KeyError, TypeError):
                    preserved.append(raw)   # unparseable row: keep, loudly below
                    continue
                if key not in fetched:
                    preserved.append(raw)
            out.unlink()
        if preserved:
            with out.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(preserved) + "\n")
            preserved_rows[day] += len(preserved)
        rows = 0
        for sym, ts, c in by_day[day]:
            append_jsonl(out, {
                "ts_pull_utc": ts_pull,
                "stream": "schwab_internals",
                "provenance": {"symbol": sym, "ts_candle": ts.isoformat()},
                "data": {
                    "symbol": sym,
                    "open": c.get("open"), "high": c.get("high"),
                    "low": c.get("low"), "close": c.get("close"),
                },
            })
            rows += 1
            written_rows[sym] += 1
        update_manifest(d=day, stream="schwab_internals", increment_cycles=rows,
                        note=f"internals minute candles ({rows} rows)")
        written += 1

    print("# internals corpus pull")
    print(f"  window: last {args.days} days · {len(by_day)} session(s) returned")
    for line in summarize_window(day_counts, written_rows, errors, dupes):
        print(line)
    print(f"  days written={written} skipped={skipped}")
    if preserved_rows:
        kept = ", ".join(f"{d}: {n}" for d, n in sorted(preserved_rows.items()))
        print(f"  rows preserved on rewrite (absent from this fetch) — {kept}")
    print()

    rc, report = verify_capture(day_counts, errors)
    for line in report:
        print(line)
    if rc:
        # Echo the verdict to stderr too. corpus_daily.py and the cron wrapper
        # capture stderr; an alerting lane (st-c3r) should get the named
        # symbols, not just a nonzero exit code it has to go digging behind.
        sys.stdout.flush()
        print(report[-1], file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
