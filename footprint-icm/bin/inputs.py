#!/usr/bin/env python3
"""Stage 00 — the day's inputs, written by code, never by a model. [st-h0xx]

Produces, under ``/var/moo/state/footprint-icm/<day>/00-inputs/``:

  events.jsonl       every tape-path EVENT of the day, re-emitted from the
                     archived corpus by the replay engine (one JSON record per
                     line: ts, kind, subtype, sig, fields, line)
  events.rth.jsonl   the same, cash session only (08:30-15:00 CT)
  log.txt            the full scorer log body regenerated from the corpus
                     (graded, partial and EVENT lines) — what a number check
                     reads, because the live log is a hand-piped file that no
                     backup covers and that can hold two runs joined
  levels.json        a byte copy of the Mancini parse the scorer loaded, with
                     its fingerprint — the anchor set is a regenerable file
                     with no history, so the run carries its own copy
  live_log.json      what the live log said, when one exists: its EVENT
                     lines, start stamp, knobs, levels count, last closed minute

and the ``inputs`` section of ``run.json``.

REFUSALS (exit 2, first one wins):
  * the live log's EVENT lines differ from the replay's — the emission path
    moved, or the corpus did; nothing downstream is comparable
  * the live log's thresholds differ from config/tape_events.yaml as loaded
  * the live log's "N levels loaded" differs from the count the anchor
    module loads today — the parse file was re-run since the live day

A day with no live log is not a refusal: the lane still labels it (Steve's
reframing, 2026-08-28 — days with no live session yield provenance-checked
labels). Every check that needs the live log is recorded as "no live log".

Usage: inputs.py <YYYY-MM-DD> [--no-log-body]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import (  # noqa: E402
    CT, LaneError, PARSED, ROOT, StageTimeout, git_short, hhmm, live_log_path, log,
    minute_of_line, parse_live_log, read_json, run_dir, run_stage_process, sha256_of,
    update_run_json, write_json,
)

sys.path.insert(0, str(ROOT))
from market.orderflow.anchors import (  # noqa: E402
    mancini_levels_for, mancini_source_for, parsed_mancini_levels,
)
from market.orderflow.region_replay import (  # noqa: E402
    RTH_WINDOW, Filter, Region, replay_day,
)
from market.orderflow.replay import has_es_day  # noqa: E402
from market.orderflow.tape_events import knobs_to_dict, load_knobs  # noqa: E402

PY = ROOT / ".venv/bin/python"
SCORER = ROOT / "scripts/live_effort_effect.py"
SCORER_TIMEOUT_S = 600      # a full-day catch-up ran 6-13 s on every recorded day


def replay_events(day: _date, knobs) -> tuple[list[dict], list[dict]]:
    """Full-day and RTH tape-path records. The region narrows what is
    reported, never what the detectors see (region_replay's rule), so the
    RTH set is a strict subset of the full set and both come from one run."""
    full = replay_day(day, Region(start=day, end=day), Filter(), knobs, paths=("tape",))
    rth = replay_day(day, Region(start=day, end=day, between=RTH_WINDOW), Filter(), knobs,
                     paths=("tape",))
    return full, rth


def regenerate_log_body(day: _date, out: Path) -> dict:
    """Run the scorer over the archived corpus and keep its stdout — the
    graded, partial and EVENT lines, byte for byte what the live run printed
    (proved on 08-27). Headers are dropped: the REGIME stamp is a wall-clock
    annotation and differs on every run."""
    cmd = [str(PY), str(SCORER), "--date", day.isoformat(), "--catch-up-only"]
    t0 = datetime.now(CT)
    proc = run_stage_process(cmd, timeout=SCORER_TIMEOUT_S, what="scorer --catch-up-only",
                             capture_output=True, text=True, cwd=str(ROOT))
    secs = (datetime.now(CT) - t0).total_seconds()
    if proc.returncode != 0:
        raise LaneError(f"scorer --catch-up-only rc={proc.returncode}: "
                        f"{proc.stderr.strip()[-400:]}")
    lines = [ln.rstrip() for ln in proc.stdout.splitlines()]
    body = [ln for ln in lines if not ln.startswith("#")]
    out.write_text("\n".join(body) + "\n", encoding="utf-8")
    return {"lines": len(body), "seconds": round(secs, 1), "command": " ".join(cmd)}


def snapshot_levels(day: _date, out: Path) -> dict:
    src = PARSED / f"{day.isoformat()}.json"
    rec: dict = {"source": mancini_source_for(day), "loaded": len(mancini_levels_for(day))}
    if src.exists():
        out.write_bytes(src.read_bytes())
        doc = read_json(src)
        rec.update({"path": str(src), "sha256": sha256_of(src),
                    "parsed_at": doc.get("parsed_at"), "raw_rows": len(doc.get("levels", [])),
                    "parsed_prices": len(parsed_mancini_levels(day))})
    else:
        rec.update({"path": str(src), "present": False})
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("day", type=_date.fromisoformat)
    ap.add_argument("--no-log-body", action="store_true",
                    help="skip the 9 s scorer regeneration (tests, quick checks)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    day: _date = args.day

    if not has_es_day(day):
        raise LaneError(f"no ES corpus for {day} under data/corpus — nothing to replay")

    out = run_dir(day) / "00-inputs"
    out.mkdir(parents=True, exist_ok=True)
    knobs = load_knobs()
    knobs_d = {k: str(v) for k, v in knobs_to_dict(knobs).items()}
    rec: dict = {
        "produced_at": datetime.now(CT).isoformat(timespec="seconds"),
        "strader_head": git_short(),
        "commits": {p: git_short(Path(p)) for p in (
            "market/orderflow/tape_events.py", "scripts/live_effort_effect.py",
            "config/tape_events.yaml", "market/orderflow/anchors.py",
            "market/orderflow/region_replay.py")},
        "knobs": knobs_d,
    }

    # 1. replay → events.jsonl / events.rth.jsonl
    t0 = datetime.now(CT)
    full, rth = replay_events(day, knobs)
    (out / "events.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in full), encoding="utf-8")
    (out / "events.rth.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rth), encoding="utf-8")
    alerts = [r for r in full if r["sig"] == "alert"]
    rth_alerts = [r for r in rth if r["sig"] == "alert"]
    rec["events"] = {
        "total": len(full), "alerts": len(alerts), "notes": len(full) - len(alerts),
        "rth_total": len(rth), "rth_alerts": len(rth_alerts),
        "rth_notes": len(rth) - len(rth_alerts),
        "rth_window": f"{hhmm(RTH_WINDOW[0])}-{hhmm(RTH_WINDOW[1])} CT",
        "replay_seconds": round((datetime.now(CT) - t0).total_seconds(), 1),
    }
    log.info("replay: %d events (%d alerts), RTH %d (%d alerts)",
             len(full), len(alerts), len(rth), len(rth_alerts))

    # 2. the live log, when there is one
    lp = live_log_path(day)
    if lp.exists():
        live = parse_live_log(lp)
        replayed = [r["line"].rstrip() for r in full]
        equal = replayed == live.event_lines
        live_rec = {
            "path": str(lp), "present": True, "sha256": sha256_of(lp),
            "lines": len(live.lines), "segments": len(live.segment_starts),
            "event_lines": len(live.event_lines), "alert_lines": len(live.alert_lines),
            "start_stamp_utc": live.start_stamp_utc,
            "start_ct": live.start_ct.isoformat() if live.start_ct else None,
            "knobs": live.knobs, "levels_loaded": live.levels_loaded,
            "last_closed_minute": live.last_closed_minute,
            "event_lines_equal_replay": equal,
        }
        write_json(out / "live_log.json", {**live_rec, "event_lines_text": live.event_lines})
        rec["live_log"] = live_rec
        if not equal:
            added = [ln for ln in replayed if ln not in set(live.event_lines)]
            removed = [ln for ln in live.event_lines if ln not in set(replayed)]
            update_run_json(day, "inputs", {**rec, "refused": "event lines differ"})
            raise LaneError(
                f"live log EVENT lines differ from replay: live {len(live.event_lines)}, "
                f"replay {len(replayed)}, only-in-replay {len(added)}, only-in-live "
                f"{len(removed)}. First only-in-replay: {added[:1]}; first only-in-live: "
                f"{removed[:1]}")
        if live.knobs and live.knobs != knobs_d:
            diff = {k: (live.knobs.get(k), knobs_d.get(k)) for k in set(live.knobs) | set(knobs_d)
                    if live.knobs.get(k) != knobs_d.get(k)}
            update_run_json(day, "inputs", {**rec, "refused": "knobs differ"})
            raise LaneError(f"thresholds differ from the live log's '# knobs:' line: {diff}")
    else:
        rec["live_log"] = {"path": str(lp), "present": False}
        log.info("no live log at %s — labelling-only day", lp)

    # 3. the anchor set the scorer loaded
    lv = snapshot_levels(day, out / "levels.json")
    rec["levels"] = lv
    if lp.exists() and rec["live_log"].get("levels_loaded") is not None \
            and rec["live_log"]["levels_loaded"] != lv["loaded"]:
        update_run_json(day, "inputs", {**rec, "refused": "levels differ"})
        raise LaneError(
            f"live log header says {rec['live_log']['levels_loaded']} levels loaded; the "
            f"anchor module loads {lv['loaded']} today (parse {lv.get('parsed_at')}, "
            f"sha256 {lv.get('sha256', '?')[:12]}). The parse was re-run since the live "
            f"day — pin it before comparing.")

    # 4. the full log body for number checks
    if not args.no_log_body:
        body = regenerate_log_body(day, out / "log.txt")
        rec["log_body"] = body
        if lp.exists():
            # Only scorer lines are compared: a live run also prints the
            # midnight DayRolledOver traceback and INFO lines, which are not
            # tape content (08-25 carries eleven such lines).
            seg = parse_live_log(lp).body_after_last_header
            live_body = [ln for ln in seg if minute_of_line(ln)]
            regen_all = (out / "log.txt").read_text(encoding="utf-8").splitlines()
            regen = [ln for ln in regen_all if minute_of_line(ln)]
            rec["log_body"]["equal_live_last_segment"] = regen == live_body
            rec["log_body"]["live_last_segment_lines"] = len(live_body)
            rec["log_body"]["live_non_scorer_lines"] = len(seg) - len(live_body)
            if regen != live_body:
                log.warning("regenerated scorer lines differ from the live log's last run "
                            "(%d vs %d lines) — recorded, not refused; EVENT lines were equal",
                            len(regen), len(live_body))
        log.info("log body: %d lines in %.1f s", body["lines"], body["seconds"])

    update_run_json(day, "inputs", rec)
    print(f"00-inputs {day}: {len(full)} events / {len(alerts)} alerts "
          f"(RTH {len(rth)} / {len(rth_alerts)}); live log "
          f"{'equal' if lp.exists() else 'absent'}; levels {lv['loaded']} ({lv['source']})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StageTimeout as e:
        print(f"[REFUSED] 00-inputs: {e}", file=sys.stderr)
        raise SystemExit(3)
    except LaneError as e:
        print(f"[REFUSED] 00-inputs: {e}", file=sys.stderr)
        raise SystemExit(2)
