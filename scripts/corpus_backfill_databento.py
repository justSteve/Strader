#!/usr/bin/env python3
"""Backfill SPXW OPRA trades by walking backwards through trading days.

Wraps `scripts/corpus_pull_databento.py` — one date per iteration. Designed
to run unattended in the background:

  - Skips weekends and a hardcoded US market holiday list
  - Skips dates already pulled (manifest entry with cycles > 0, no errors)
  - Polite pause between successful pulls
  - Backs off on 429 rate-limit responses (sleep + retry once)
  - Stops on any other persistent error so a human can investigate
  - Stops naturally at a configurable end date (defaults to 1-year free-window
    boundary)
  - Appends a structured line to data/corpus/_backfill.log per attempt

Usage:
    .venv/bin/python scripts/corpus_backfill_databento.py
    .venv/bin/python scripts/corpus_backfill_databento.py \\
        --start 2026-05-22 --end 2025-05-24 --window 13:00-15:00

Default --end 2025-05-24 is one day past the verified free-window boundary
(probed 2026-05-23: 2025-05-23 returns \$0, 2025-03-03 returns ~\$3.60).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date as _date, datetime, timedelta
from pathlib import Path

# US equity market holidays — covers the rolling 1-year window
# starting roughly mid-2025 through 2026. Update if backfill window changes.
HOLIDAYS_2025 = {
    _date(2025, 1, 1),   # New Year
    _date(2025, 1, 9),   # Carter mourning
    _date(2025, 1, 20),  # MLK Day
    _date(2025, 2, 17),  # Presidents Day
    _date(2025, 4, 18),  # Good Friday
    _date(2025, 5, 26),  # Memorial Day
    _date(2025, 6, 19),  # Juneteenth
    _date(2025, 7, 4),   # July 4 (observed Fri)
    _date(2025, 9, 1),   # Labor Day
    _date(2025, 11, 27), # Thanksgiving
    _date(2025, 12, 25), # Christmas
}
HOLIDAYS_2026 = {
    _date(2026, 1, 1),   # New Year
    _date(2026, 1, 19),  # MLK Day
    _date(2026, 2, 16),  # Presidents Day
    _date(2026, 4, 3),   # Good Friday
    # Memorial Day 2026 = May 25; backfill ends before then
}
HOLIDAYS = HOLIDAYS_2025 | HOLIDAYS_2026


def is_trading_day(d: _date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


PULL_SCRIPT_BY_DATASET = {
    "opra": ("corpus_pull_databento.py", "databento_opra"),
    "es":   ("corpus_pull_databento_es.py", "databento_glbx_es"),
}


def already_pulled(d: _date, repo_root: Path, stream_key: str) -> bool:
    """Return True if a successful pull of stream_key exists for d."""
    mf = repo_root / "data" / "corpus" / d.isoformat() / "manifest.json"
    if not mf.exists():
        return False
    try:
        data = json.loads(mf.read_text())
    except Exception:
        return False
    s = data.get("streams", {}).get(stream_key)
    if not s:
        return False
    return s.get("cycles", 0) > 0 and not s.get("errors")


def log(msg: str, log_path: Path) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}  {msg}"
    print(line, flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(line + "\n")


def run_pull(d: _date, window: str, repo_root: Path, script_name: str) -> tuple[int, str, str]:
    """Invoke the per-date pull script for the chosen dataset.

    Returns (exit_code, last_stdout_line, full_output).
    """
    start_ct, end_ct = window.split("-")
    script = repo_root / "scripts" / script_name
    venv_py = repo_root / ".venv" / "bin" / "python"
    cmd = [
        str(venv_py),
        str(script),
        "--date", d.isoformat(),
        "--start-ct", start_ct,
        "--end-ct", end_ct,
    ]
    proc = subprocess.run(
        cmd, cwd=str(repo_root), capture_output=True, text=True, timeout=900,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    last_line = ""
    for line in output.splitlines():
        if line.strip():
            last_line = line.strip()
    return proc.returncode, last_line, output


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    log_path = repo_root / "data" / "corpus" / "_backfill.log"

    parser = argparse.ArgumentParser(description="Backwards backfill driver for Databento corpus streams")
    parser.add_argument("--dataset", default="opra", choices=list(PULL_SCRIPT_BY_DATASET.keys()),
                        help="Which dataset to backfill: opra (SPXW.OPT trades) or es (ES.c.0 trades)")
    parser.add_argument("--start", default="2026-05-22",
                        help="Most-recent date to pull (inclusive)")
    parser.add_argument("--end", default="2025-05-24",
                        help="Oldest date to pull (inclusive). Default = 1yr free-window boundary")
    parser.add_argument("--window", default="13:00-15:00",
                        help="CT window as HH:MM-HH:MM (default 13:00-15:00 — late-day 2hr)")
    parser.add_argument("--sleep-success", type=int, default=5,
                        help="Seconds to sleep after a successful pull")
    parser.add_argument("--sleep-backoff", type=int, default=120,
                        help="Seconds to sleep after a 429 rate-limit response")
    args = parser.parse_args()

    script_name, stream_key = PULL_SCRIPT_BY_DATASET[args.dataset]

    start = _date.fromisoformat(args.start)
    end = _date.fromisoformat(args.end)
    if start < end:
        log(f"START < END refused (start={start}, end={end}); this is a backwards walker", log_path)
        return 2

    log(f"=== backfill start  dataset={args.dataset}  start={start}  end={end}  window={args.window} ===", log_path)

    current = start
    pulled = 0
    skipped = 0
    while current >= end:
        if not is_trading_day(current):
            current -= timedelta(days=1)
            continue
        if already_pulled(current, repo_root, stream_key):
            log(f"SKIP  {current}  ({args.dataset}: already pulled)", log_path)
            skipped += 1
            current -= timedelta(days=1)
            continue
        log(f"PULL  {current}  ({args.dataset}) starting...", log_path)
        rc, last_line, output = run_pull(current, args.window, repo_root, script_name)
        if rc == 0:
            log(f"PULL  {current}  OK  {last_line}", log_path)
            pulled += 1
            current -= timedelta(days=1)
            time.sleep(args.sleep_success)
            continue
        # Non-zero exit: classify as transient (retry) vs persistent (bail)
        is_ratelimit = "429" in output or "rate_limit" in output.lower() or "too many requests" in output.lower()
        is_transient_5xx = any(code in output for code in ("502", "503", "504")) or "gateway timed out" in output.lower() or "service unavailable" in output.lower()
        is_transient = is_ratelimit or is_transient_5xx
        if is_transient:
            backoff = args.sleep_backoff if is_ratelimit else 30
            label = "RATE-LIMIT" if is_ratelimit else "TRANSIENT-5XX"
            log(f"{label}  {current}  backing off {backoff}s and retrying once", log_path)
            time.sleep(backoff)
            rc2, last_line2, output2 = run_pull(current, args.window, repo_root, script_name)
            if rc2 == 0:
                log(f"PULL  {current}  OK (after backoff)  {last_line2}", log_path)
                pulled += 1
                current -= timedelta(days=1)
                time.sleep(args.sleep_success)
                continue
            log(f"{label}  {current}  still failing after backoff — stopping", log_path)
            log(f"=== backfill stop  pulled={pulled}  skipped={skipped}  reason={'rate_limit' if is_ratelimit else 'transient_5xx'} ===", log_path)
            return 1
        log(f"ERROR  {current}  rc={rc}  last={last_line}", log_path)
        log(f"=== backfill stop  pulled={pulled}  skipped={skipped}  reason=error ===", log_path)
        return 1

    log(f"=== backfill complete  pulled={pulled}  skipped={skipped} ===", log_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
