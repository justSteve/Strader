#!/usr/bin/env python3
"""Pre-open heartbeat — did pull / parse / gate run before the open. [st-66u]

Runbook #11 (COO design co-6wts), minimal version: one deterministic check,
fired pre-open, answering yes/no — with an alert on no — to the question that
guards the ugliest live failure mode: a silently dead feed producing
confident-looking artifacts.

Hard checks (any failure → exit 1 + alert to data/corpus/_health.jsonl):
  corpus   — datastream gate passes for the most recent completed session
             (same gate.check the 06:30 batch and the Mancini parse use;
             single source of truth, not a reimplementation)
  mancini  — today's parse artifact exists (runbook/mancini/parsed/<today>.json,
             written by the 08:15 CT pre-open cron)

Soft checks (reported, never fail the run):
  schwab   — today's manifest carries a schwab snapshot (the 07:00 premarket
             stage fire, st-096). Not gate-required, so not a hard stop —
             but a missing premarket snapshot on a live morning is worth a line.
  capture  — the live Databento streamer survived the night (st-6qx4). Read from
             the supervisor's state file, not re-derived: the supervisor fires
             every two minutes and this runs once, so its accumulated view is
             what matters at 08:25. Soft because a lost night of ES tape does not
             make TODAY's plan unsafe — but it is unrecoverable data, so it must
             appear on a surface someone actually reads. This is that surface.

Scheduling: 08:25 CT weekdays via scripts/cron/preopen-heartbeat-wrapper.sh —
after the 08:15 parse has had its window, five minutes before the bell.

Usage:
    .venv/bin/python -m runbook.heartbeat          # human-readable + exit code
    .venv/bin/python -m runbook.heartbeat --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.corpus.paths import (  # noqa: E402
    CORPUS_ROOT,
    central_date,
    manifest_path,
    most_recent_session_day,
)
from runbook.datastream import gate  # noqa: E402

PARSED_ROOT = REPO_ROOT / "runbook" / "mancini" / "parsed"

# Live-capture supervisor state [st-6qx4] — written every run by
# scripts/capture_health.py, which scripts/cron/capture-supervisor-wrapper.sh
# fires every two minutes.
CAPTURE_STATE = CORPUS_ROOT / "_capture_health.json"
# A state file older than this means the SUPERVISOR stopped, which is a silent
# failure of the guard itself. Generous against a 2-minute cadence.
CAPTURE_STATE_MAX_AGE_MIN = 30.0


def check_corpus() -> dict:
    """Datastream gate over the most recent completed session."""
    day = most_recent_session_day()
    result = gate.check(day=day)
    return {"name": "corpus", "hard": True, "ok": result.ok,
            "day": day.isoformat(), "reasons": list(result.reasons)}


def check_mancini() -> dict:
    """Today's parse artifact — the 08:15 cron's output."""
    today = central_date()
    path = PARSED_ROOT / f"{today.isoformat()}.json"
    ok = path.exists()
    reasons = [] if ok else [f"missing {path.name} — 08:15 parse did not land"]
    return {"name": "mancini", "hard": True, "ok": ok,
            "day": today.isoformat(), "reasons": reasons}


def check_schwab() -> dict:
    """Premarket schwab snapshot in today's manifest (soft — never a hard stop)."""
    today = central_date()
    reasons: list[str] = []
    ok = False
    path = manifest_path(today)
    if not path.exists():
        reasons.append("no manifest for today yet")
    else:
        try:
            streams = json.loads(path.read_text(encoding="utf-8")).get("streams", {})
        except (json.JSONDecodeError, OSError) as e:
            streams = {}
            reasons.append(f"manifest unreadable: {e}")
        st = streams.get("schwab") or {}
        ok = (st.get("cycles", 0) or 0) > 0 and not st.get("errors")
        if not ok and not reasons:
            reasons.append("no clean schwab snapshot — 07:00 premarket stage did not land")
    return {"name": "schwab", "hard": False, "ok": ok,
            "day": today.isoformat(), "reasons": reasons}


def check_risk() -> dict:
    """Today's risk state exists — the day-start reset ran [st-958]. Hard:
    live trading without the day's budgets on disk is the exact failure this
    heartbeat exists to catch."""
    today = central_date()
    from runbook.risk_state import state_path
    path = state_path(today.isoformat())
    ok = path.exists()
    reasons = [] if ok else ["no risk state — run: python -m runbook.risk_state reset"]
    return {"name": "risk", "hard": True, "ok": ok,
            "day": today.isoformat(), "reasons": reasons}


def check_capture() -> dict:
    """Did the live Databento capture survive the night (soft) [st-6qx4].

    Reports the supervisor's own verdict rather than re-deriving liveness — and
    reports the supervisor's ABSENCE too. An alert nobody reads is not a guard:
    the health log is durable but unread, so the overnight capture story is
    surfaced here, on the one thing already looked at before every open.
    """
    from datetime import datetime, timezone

    reasons: list[str] = []
    today = central_date()
    if not CAPTURE_STATE.exists():
        return {"name": "capture", "hard": False, "ok": False,
                "day": today.isoformat(),
                "reasons": [f"no capture watcher state ({CAPTURE_STATE.name}) — "
                            "is capture-supervisor-wrapper.sh in cron?"]}
    try:
        state = json.loads(CAPTURE_STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"name": "capture", "hard": False, "ok": False,
                "day": today.isoformat(),
                "reasons": [f"capture watcher state unreadable: {e}"]}

    status = state.get("status", "unknown")
    checked = state.get("checked_at")
    age_min = None
    try:
        seen = datetime.strptime(checked, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - seen).total_seconds() / 60
    except (TypeError, ValueError):
        reasons.append(f"capture watcher state has no usable checked_at ({checked!r})")

    ok = status in ("ok", "starting", "quiet", "idle")
    if age_min is not None and age_min > CAPTURE_STATE_MAX_AGE_MIN:
        ok = False
        reasons.append(f"capture watcher last ran {age_min:.0f} min ago — the "
                       f"supervisor itself has stopped; liveness is UNKNOWN")
    if not ok and status not in ("ok", "starting", "quiet", "idle"):
        reasons.append(f"{status}: {state.get('message', '')}".strip())

    restarts = int(state.get("restarts") or 0)
    if restarts:
        reasons.append(f"{restarts} supervisor restart(s) today (last "
                       f"{state.get('last_restart_utc', '?')}) — expect gaps in "
                       f"the tape around those times")
    return {"name": "capture", "hard": False, "ok": ok,
            "day": state.get("day", today.isoformat()), "reasons": reasons}


def run_checks() -> list[dict]:
    return [check_corpus(), check_mancini(), check_risk(), check_schwab(),
            check_capture()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-open heartbeat [st-66u]")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        checks = run_checks()
    except Exception as e:  # rc 2 = the check itself broke, distinct from "failed"
        print(f"pre-open heartbeat: INTERNAL ERROR — {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    hard_failures = [c for c in checks if c["hard"] and not c["ok"]]
    ok = not hard_failures

    # Durable record + alert ride the same health log the corpus batch and the
    # Mancini wrapper write — one log, read by one morning surface.
    from scripts.corpus_daily import _append_health, _utc_now_iso, emit_alert
    _append_health({"ts": _utc_now_iso(), "level": "heartbeat", "ok": ok,
                    "checks": checks})
    if not ok:
        detail = "; ".join(r for c in hard_failures for r in c["reasons"])
        emit_alert("preopen_heartbeat",
                   f"Pre-open heartbeat FAILED — {detail}. The open is minutes "
                   "out; artifacts on the desk may be stale.",
                   {"checks": checks})

    if args.json:
        print(json.dumps({"ok": ok, "checks": checks}, indent=2))
    else:
        print(f"pre-open heartbeat: {'OK' if ok else 'FAILED'}")
        for c in checks:
            tier = "hard" if c["hard"] else "soft"
            state = "ok" if c["ok"] else "MISSING"
            line = f"  {c['name']:<8} [{tier}] {state}"
            if c["reasons"]:
                line += " — " + "; ".join(c["reasons"])
            print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
