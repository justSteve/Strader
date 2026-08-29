#!/usr/bin/env python3
"""Stage 40, the code half — the page Steve reads. [st-h0xx]

Day 1 form (no model in the loop yet): for each wake the live analyst was
shown, the page carries the alert lines, the graded bar the watch attached,
the reply verbatim, any push, the number check, and the tokens the reply
cost. Then coverage — the alerts never delivered and why — and the run's
provenance (commits, thresholds, anchor fingerprint).

THE NUMBER CHECK. Every figure in a reply that looks like a price, a volume
or a delta is searched for in the lines the analyst could have read by that
minute: the wake's own alert lines and bar, and the regenerated log up to and
including the wake's tape minute. A figure not found is listed — it may be
derived (a difference, a sum) or a slip; the page says which lines were
searched so a reader can decide. Nothing here judges the prose.

When the model stages exist (Day 3) this file also reads their LABEL and
CLAIM lines and assigns the comparison classes; the page shape stays.

Usage: compare.py <YYYY-MM-DD> [--no-publish]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import date as _date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import (  # noqa: E402
    COO_ROOT, CT, DESK_DIR, DESK_HTML, DESK_REGISTER, LaneError, log, minute_of_line,
    read_json, run_dir, update_run_json, write_json,
)

DESK_REGISTER_REL = Path("myDesk/reports/footprint-icm-latest.md")
DESK_CATEGORY = "Reviews"

# Figures worth checking: prices (four digits, optional quarter), volumes and
# deltas (three or more digits, optional sign, optional thousands commas).
# A token glued to a colon is a clock time and is skipped.
NUM_RE = re.compile(r"(?<![\d:.])([+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d{3,}(?:\.\d+)?)(?![\d:])")


def numbers_in(text: str) -> list[str]:
    seen, out = set(), []
    for m in NUM_RE.finditer(text):
        tok = m.group(1)
        norm = tok.replace(",", "").lstrip("+")
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _values_in_lines(lines: list[str]) -> set[float]:
    """Every number on the lines, by value — so ``7687.50`` in a reply matches
    the log's ``7687.5`` and ``-317`` matches ``d-317``. Sign is kept and also
    dropped, since a reply may quote a sell delta as 866 or -866."""
    vals: set[float] = set()
    for ln in lines:
        for m in re.finditer(r"[+-]?\d+(?:\.\d+)?", ln):
            v = float(m.group(0))
            vals.add(v)
            vals.add(abs(v))
    return vals


def number_check(reply: str, wake_lines: list[str], bar: str | None,
                 log_lines: list[str], upto_minute: str) -> dict:
    """Which figures in the reply appear in what the analyst could read."""
    nums = numbers_in(reply)
    context = list(wake_lines) + ([bar] if bar else [])
    searched = [ln for ln in log_lines if (minute_of_line(ln) or "99:99") <= upto_minute]
    have = _values_in_lines(context + searched)
    found = [n for n in nums if float(n) in have or abs(float(n)) in have]
    missing = [n for n in nums if n not in found]
    return {"checked": nums, "found": found, "not_found": missing,
            "lines_searched": len(searched) + len(context), "upto_minute": upto_minute}


# ── the page ───────────────────────────────────────────────────────────────

def _fmt_usage(u: dict) -> str:
    return (f"out {u.get('output_tokens', 0):,} · cache read {u.get('cache_read_input_tokens', 0):,} "
            f"· cache write {u.get('cache_creation_input_tokens', 0):,} · in {u.get('input_tokens', 0):,}")


def _ct(s) -> str:
    if not s:
        return "?"
    try:
        return datetime.fromisoformat(str(s)).astimezone(CT).strftime("%H:%M:%S")
    except ValueError:
        return str(s)


def render_page(day: _date, run: dict, wakes: list[dict], checks: list[dict]) -> str:
    inp = run.get("inputs") or {}
    ll = run.get("live_lane") or {}
    ev = inp.get("events") or {}
    live_log = inp.get("live_log") or {}
    lv = inp.get("levels") or {}
    sessions = ll.get("sessions_detail") or []
    n_missing = sum(len(c["not_found"]) for c in checks)
    n_push = sum(len(w["reply"]["pushes"]) for w in wakes)

    out = [f"# Footprint audit lane — {day.isoformat()} (live side, no model)\n"]
    if sessions:
        out.append(f"**{day.isoformat()}: {len(wakes)} wake(s) delivered of "
                   f"{ev.get('rth_alerts', '?')} cash-session alerts ({ev.get('alerts', '?')} in "
                   f"the whole day); {n_push} push(es); {n_missing} figure(s) in the replies not "
                   f"found in the log.**\n")
    else:
        out.append(f"**{day.isoformat()}: no live session. {ev.get('rth_alerts', '?')} "
                   f"cash-session alerts ({ev.get('alerts', '?')} in the whole day). "
                   f"A labelling-only day.**\n")

    out.append("## What this page is\n")
    out.append("The left-hand side of the audit lane: what the live analyst was actually shown, "
               "and what it said, taken from the session transcript by code. Nothing on this "
               "page was written by a model except the quoted replies themselves. Times are "
               "Central. A wake is one delivery from the watch script; the alert lines in it are "
               "the scorer's own words.\n")

    for s in sessions:
        out.append("## The live session\n")
        out.append(f"- Session: project `{s.get('project')}`, working directory `{s.get('cwd')}`, "
                   f"model `{s.get('model')}`, task `{s.get('task_id')}`")
        out.append(f"- Watch armed {_ct(s.get('armed_ct'))}; stopped {_ct(s.get('stopped_ct'))} "
                   f"({s.get('stopped_how')})")
        out.append(f"- Runbook (`emitter-two-tier.md`) read before the first wake: "
                   f"**{'yes' if s.get('runbook_read_before_first_wake') else 'no'}**"
                   + ("" if s.get('runbook_read_before_first_wake') else
                      " — this session was not operating under the analyst contract; read its "
                      "replies as a working session's, not the analyst's"))
        out.append(f"- Wake sets: transcript and rule "
                   f"{'agree' if s.get('wake_sets_match') else 'DIFFER'}")
        u = s.get("usage_from_arm") or {}
        out.append(f"- Tokens from the arm to the stop (all the session's work in that span, not only wakes): "
                   f"{_fmt_usage(u)}; {u.get('assistant_rows', 0)} assistant turns\n")

    if wakes:
        out.append("## The wakes\n")
    for i, (w, c) in enumerate(zip(wakes, checks), 1):
        r = w["reply"]
        first = w["lines"][0][:5] if w["lines"] else "?"
        out.append(f"### Wake {i} — {first} tape time, delivered {_ct(w.get('delivered_ct'))}\n")
        out.append("Alert lines the watch delivered:\n")
        out.append("```")
        out.extend(w["lines"] or ["(none parsed)"])
        if w.get("bar"):
            out.append(f"bar: {w['bar']}")
        out.append("```\n")
        out.append(f"Reply ({_ct(r.get('first_reply_ct'))} → {_ct(r.get('last_reply_ct'))}, "
                   f"{_fmt_usage(r.get('usage') or {})}):\n")
        text = (r.get("text") or "").strip() or "(no prose reply in the span)"
        out.extend("> " + ln for ln in text.splitlines())
        out.append("")
        if r.get("pushes"):
            out.append("Pushed to Steve's phone:\n")
            for p in r["pushes"]:
                out.append(f"- {p}")
            out.append("")
        if c["checked"]:
            out.append(f"Number check — {len(c['found'])} of {len(c['checked'])} figures found in "
                       f"the {c['lines_searched']} lines the analyst could read by {c['upto_minute']}"
                       + (f"; **not found: {', '.join(c['not_found'])}**" if c["not_found"] else "")
                       + ".\n")
        else:
            out.append("Number check — the reply carries no price, volume or delta figures.\n")

    # Coverage
    out.append("## Coverage — alerts the live analyst was never shown\n")
    cov = run.get("coverage") or {}
    if cov:
        out.append(f"- Alerts in the day: {ev.get('alerts', '?')}; in the cash session: "
                   f"{ev.get('rth_alerts', '?')}; delivered: {cov.get('delivered', 0)}; "
                   f"never delivered (before the scorer started, before the watch was armed, or "
                   f"after it stopped): {cov.get('undelivered', 0)}; ambiguous (same minute as the "
                   f"arm or the stop): "
                   f"{cov.get('ambiguous', 0)}")
        if live_log.get("start_ct"):
            out.append(f"- Scorer started {_ct(live_log['start_ct'])} (its start stamp); everything "
                       f"before that minute was printed in one burst at start-up and could not wake "
                       f"anyone")
        out.append(f"- Note-grade lines ({ev.get('rth_notes', '?')} in the cash session) never wake "
                   f"the analyst; it saw them only if it read the log by hand\n")
        if cov.get("undelivered_lines"):
            out.append("<details><summary>Undelivered alert lines</summary>\n")
            out.append("```")
            out.extend(cov["undelivered_lines"])
            out.append("```\n</details>\n")
    else:
        out.append(f"- No live session, so every one of the {ev.get('alerts', '?')} alerts is "
                   f"coverage for the labelling stage.\n")

    # Provenance
    out.append("## Provenance of this run\n")
    out.append(f"- Strader `{inp.get('strader_head')}`; scorer `"
               f"{(inp.get('commits') or {}).get('scripts/live_effort_effect.py')}`, detector `"
               f"{(inp.get('commits') or {}).get('market/orderflow/tape_events.py')}`, thresholds `"
               f"{(inp.get('commits') or {}).get('config/tape_events.yaml')}`")
    if live_log.get("present"):
        out.append(f"- Live log: {live_log.get('event_lines')} EVENT lines, "
                   f"{'equal to' if live_log.get('event_lines_equal_replay') else 'DIFFERENT from'} "
                   f"the replay; thresholds equal; last closed minute {live_log.get('last_closed_minute')}; "
                   f"{live_log.get('segments')} scorer run(s) in the file")
    else:
        out.append("- No live log for this day; inputs come from the replay alone")
    lb = inp.get("log_body") or {}
    if lb:
        out.append(f"- Regenerated log body: {lb.get('lines')} lines in {lb.get('seconds')} s"
                   + (f", {'identical to' if lb.get('equal_live_last_segment') else 'differs from'} "
                      f"the live log's last run" if "equal_live_last_segment" in lb else ""))
    out.append(f"- Anchor set: {lv.get('loaded')} levels loaded from the {lv.get('source')} "
               f"(parse {lv.get('parsed_at')}, fingerprint `{str(lv.get('sha256', ''))[:12]}`, "
               f"{lv.get('raw_rows')} raw rows)")
    out.append(f"- Thresholds in force: " + ", ".join(f"{k}={v}" for k, v in
                                                        sorted((inp.get('knobs') or {}).items())))
    out.append(f"- Run folder: `/var/moo/state/footprint-icm/{day.isoformat()}/`; produced "
               f"{datetime.now(CT).strftime('%Y-%m-%d %H:%M CT')}")
    out.append("\nThe desk's plain-words pass ran without its model step on this page: the glossary "
               "substitutions only, so no model rewrote what is quoted above.\n")
    return "\n".join(out)


def publish(md: Path, day: _date) -> int:
    if not DESK_HTML.exists():
        log.warning("desk-html.sh absent at %s — page not rendered", DESK_HTML)
        return 3
    target = DESK_DIR / f"desk-footprint-icm-{day.isoformat()}.html"
    # The renderer's glossary pass runs; its model step does not, so no model
    # rewrites the quoted replies. Everything else in the environment is
    # inherited — the renderer finds node and marked through it.
    env = {**os.environ, "DESK_TRANSLATE_NO_MODEL": "1"}
    proc = subprocess.run([str(DESK_HTML), str(md), str(target)], capture_output=True,
                          text=True, timeout=900, env=env)
    if proc.returncode != 0:
        log.warning("desk-html.sh rc=%d: %s", proc.returncode, proc.stderr.strip()[-300:])
        return 3
    shutil.copyfile(target, DESK_DIR / "desk-footprint-icm-latest.html")
    log.info("page: %s (and desk-footprint-icm-latest.html)", target)
    desk_md = COO_ROOT / DESK_REGISTER_REL
    try:
        desk_md.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(md, desk_md)
        out = subprocess.run([str(DESK_REGISTER), DESK_CATEGORY, str(DESK_REGISTER_REL)],
                             capture_output=True, text=True, timeout=30)
        if out.returncode:
            log.warning("desk-register rc=%d: %s", out.returncode, out.stderr.strip()[-200:])
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("desk copy/register skipped: %s", e)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("day", type=_date.fromisoformat)
    ap.add_argument("--no-publish", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    day: _date = args.day
    rd = run_dir(day, create=False)
    if not (rd / "run.json").exists():
        raise LaneError(f"no run.json under {rd} — run inputs.py first")
    run = read_json(rd / "run.json")
    if "inputs" not in run:
        raise LaneError("run.json has no inputs section — run inputs.py first")
    out = rd / "40-compare"
    out.mkdir(exist_ok=True)

    wakes: list[dict] = []
    wp = rd / "live-lane/wakes.jsonl"
    if wp.exists():
        wakes = [json.loads(l) for l in wp.read_text(encoding="utf-8").splitlines() if l]
    log_lines = (rd / "00-inputs/log.txt").read_text(encoding="utf-8").splitlines() \
        if (rd / "00-inputs/log.txt").exists() else []

    checks = []
    for w in wakes:
        upto = w["lines"][-1][:5] if w["lines"] else "99:99"
        checks.append(number_check(w["reply"].get("text") or "", w["lines"], w.get("bar"),
                                   log_lines, upto))
    write_json(out / "numbers.json", checks)

    # Coverage from the live-lane derivation (first session's rule result).
    sess_path = rd / "live-lane/session.json"
    coverage = {}
    if sess_path.exists():
        sdoc = read_json(sess_path)
        for s in sdoc.get("sessions") or []:
            d = s.get("derived") or {}
            coverage = {"delivered": len(d.get("wakes") or []),
                        "undelivered": len(d.get("undelivered") or []),
                        "ambiguous": len(d.get("ambiguous") or []),
                        "undelivered_lines": d.get("undelivered") or [],
                        "ambiguous_lines": d.get("ambiguous") or []}
            break
    run["coverage"] = coverage
    if coverage:
        update_run_json(day, "coverage", {k: v for k, v in coverage.items()
                                          if not k.endswith("_lines")})

    md = render_page(day, run, wakes, checks)
    page = rd / "page.md"
    page.write_text(md, encoding="utf-8")
    rec = {"produced_at": datetime.now(CT).isoformat(timespec="seconds"), "wakes": len(wakes),
           "figures_checked": sum(len(c["checked"]) for c in checks),
           "figures_not_found": sum(len(c["not_found"]) for c in checks), "page": str(page)}
    rc = 0
    if not args.no_publish:
        rc = publish(page, day)
        rec["published"] = rc == 0
    update_run_json(day, "compare", rec)
    print(f"40-compare {day}: {len(wakes)} wake(s); figures checked {rec['figures_checked']}, "
          f"not found {rec['figures_not_found']}; page {page}"
          + ("" if args.no_publish else (" → desk" if rc == 0 else " (desk render failed)")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaneError as e:
        print(f"[REFUSED] 40-compare: {e}", file=sys.stderr)
        raise SystemExit(2)
