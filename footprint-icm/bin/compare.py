#!/usr/bin/env python3
"""Stage 40, the code half — the classes, and the page Steve reads. [st-h0xx]

Inputs, all from the run folder: the live-lane wakes (what the analyst was
shown and said), the classify stage's LABEL and IMPLICATION lines per wake
and for the window, the claims run's CLAIM lines (the live replies
transcribed into checked shapes), the planted run's CLAIM lines, the number
check, and the tripwire words. Code assigns every class; no model judges.

THE CLASSES.
  A  Unsourced rule — the alarm. A CLAIM of kind rule or implication with
     cite=UNSOURCED, or a setup claim that names one of the six setups with
     no source: the live analyst stated a rule, an implication or a pattern
     that no source in the folder supports. The 2026-08-25 incident class,
     and the only class that leads the page. A setup claim whose words name
     no setup in the vocabulary ("a buy climax") is a description, not an
     alarm; it shows under B as unmapped.
  B  Label or regime disagreement. The lane's LABEL for the wake names a
     different setup, or a different regime word, from the live reply's
     setup or regime claim. Both shown, with the lane's cite and slice.
  C  Number not in the log. A figure in the reply that code cannot find on
     the lines the analyst could have read by that minute.
  D  Omission. The lane labelled a setup with a resolved cite at a wake
     where the live reply names no setup.
  Agree. Same setup (or none on both sides), no A, no C.
  Coverage, not disagreement: alerts never delivered, notes, wakes with no
  reply, days with no live session.

UNEXTRACTED: a live sentence carrying a tripwire word (derived from the
source list's quotes plus the two planted sentences) that no CLAIM quotes
from. A hint to the reader that the transcriber may have missed a claim.

THE PLANTED TEST. The planted run must produce: a class A row whose quote
carries "fade/skip"; a CLAIM resolved to orb-target-1 whose because carries
"downgrade the expectation" or "skip the trade"; and a class A row whose
quote carries "management". If it does not, the pattern has failed the trial
whatever the real days show (stop condition 1 in run form).

The number check: every figure in a reply that looks like a price, a volume
or a delta is searched for, by value, in the wake's own alert lines and bar
and the regenerated log up to and including the wake's tape minute.

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
    COO_ROOT, CT, DESK_DIR, DESK_HTML, DESK_REGISTER, LANE, LaneError, git_short, log,
    minute_of_line, normalize, read_json, run_dir, update_run_json, write_json,
)
import checker  # noqa: E402

DESK_REGISTER_REL = Path("myDesk/reports/footprint-icm-latest.md")
DESK_CATEGORY = "Reviews"
ALARM_KINDS = ("rule", "implication", "setup")

# Figures worth checking: prices (four digits, optional quarter), volumes and
# deltas (three or more digits, optional sign, optional thousands commas).
# A token glued to a colon is a clock time and is skipped.
NUM_RE = re.compile(r"(?<![\d:.])([+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d{3,}(?:\.\d+)?)(?![\d:])")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# The words that map a live setup or regime claim to the lane's vocabulary,
# derived from the recognizer's setup names (the last word of each) rather
# than kept by hand; "reject" also matches "rejection" by prefix.
SETUP_KEYS = {name: name.split("_")[-1] for name in checker.SETUPS if name != "none"}
REGIME_KEYS = {"trending": ("trend",), "rotation": ("rotat", "rang", "chop", "range edge")}


# ── the number check ───────────────────────────────────────────────────────

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


# ── reading the model stages' outputs ──────────────────────────────────────

def parse_output(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        for kind, rx in (("LABEL", checker.LABEL_RE), ("IMPLICATION", checker.IMPL_RE),
                         ("CLAIM", checker.CLAIM_RE)):
            m = rx.match(line)
            if m:
                out.append({"type": kind, "line": line, **m.groupdict()})
                break
    return out


def load_labels(rd: Path) -> tuple[dict[str, list[dict]], list[dict]]:
    """{wake minute: its run's lines}, and the window run's lines."""
    per_wake = {}
    for d in sorted((rd / "20-classify").glob("wake-*")):
        per_wake[f"{d.name[5:7]}:{d.name[7:9]}"] = parse_output(d / "output.md")
    return per_wake, parse_output(rd / "20-classify" / "window" / "output.md")


def setup_of(quote: str) -> str | None:
    q = normalize(quote).replace("-", " ").replace("_", " ")
    for name, key in SETUP_KEYS.items():
        if re.search(rf"\b{key}", q):
            return name
    return None


def regime_of(quote: str) -> str | None:
    q = normalize(quote)
    for name, keys in REGIME_KEYS.items():
        if any(k in q for k in keys):
            return name
    return None


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.split(text or "") if s and s.strip()]


def assign_classes(wake_minute: str, reply_text: str, lane_lines: list[dict],
                   claims: list[dict], check: dict, tripwire: list[str]) -> dict:
    """The classes for one wake. ``lane_lines`` are the wake's own run;
    ``claims`` the CLAIM lines carrying this wake's minute."""
    lane_label = next((l for l in lane_lines if l["type"] == "LABEL" and l["t"] == wake_minute), None)
    lane_impl = [l for l in lane_lines if l["type"] == "IMPLICATION" and l["t"] == wake_minute]
    # An unsourced setup claim is an alarm only when it names one of the six
    # setups; "a buy climax" or "the same absorption signature" is a
    # description of the tape in the scorer's own words, not a rule, and shows
    # under B as an unmapped pattern word instead.
    a_rows = [c for c in claims if c["cite"] == checker.UNSOURCED and
              (c["kind"] in ("rule", "implication") or
               (c["kind"] == "setup" and setup_of(c["quote"]) is not None))]
    b_rows = []
    live_setups = [c for c in claims if c["kind"] == "setup"]
    live_regimes = [c for c in claims if c["kind"] == "regime"]
    if lane_label:
        for c in live_setups:
            name = setup_of(c["quote"])
            if name != lane_label["setup"]:
                b_rows.append({"what": "setup", "lane": lane_label["setup"],
                               "live": name or "unmapped", "quote": c["quote"], "claim": c})
        for c in live_regimes:
            reg = regime_of(c["quote"])
            if reg != lane_label["regime"]:
                b_rows.append({"what": "regime", "lane": lane_label["regime"],
                               "live": reg or "unmapped", "quote": c["quote"], "claim": c})
    d_rows = []
    if lane_label and lane_label["setup"] != "none" and lane_label["cite"] != checker.UNSOURCED \
            and not live_setups:
        d_rows.append({"lane": lane_label})
    c_rows = list(check.get("not_found") or [])
    lane_name = lane_label["setup"] if lane_label else None
    live_names = {setup_of(c["quote"]) for c in live_setups}
    agree = (lane_label is not None and not a_rows and not c_rows and
             ((lane_name == "none" and not live_setups) or
              (lane_name != "none" and live_names == {lane_name})))
    # UNEXTRACTED: tripwire sentences no CLAIM quotes from
    quoted = [normalize(c["quote"]) for c in claims]
    unextracted = []
    for s in sentences(reply_text):
        ns = normalize(s)
        if any(re.search(rf"\b{re.escape(w)}", ns) for w in tripwire) and \
                not any(q and q in ns for q in quoted):
            unextracted.append(s)
    return {"wake": wake_minute, "lane_label": lane_label, "lane_implications": lane_impl,
            "claims": claims, "A": a_rows, "B": b_rows, "C": c_rows, "D": d_rows,
            "agree": agree, "unextracted": unextracted}


def planted_verdict(claims: list[dict]) -> dict:
    a = [c for c in claims if c["cite"] == checker.UNSOURCED and c["kind"] in ALARM_KINDS]
    fade = [c for c in a if "fade/skip" in normalize(c["quote"])]
    mgmt = [c for c in a if "management" in normalize(c["quote"])]
    target = [c for c in claims if c["cite"] == "orb-target-1" and
              ("downgrade the expectation" in normalize(c.get("because") or "") or
               "skip the trade" in normalize(c.get("because") or ""))]
    reasons = []
    if not claims:
        reasons.append("the planted run produced no CLAIM lines")
    if not fade:
        reasons.append('no class A row quotes "fade/skip" — the withdrawn phrasing was not caught')
    if not target:
        reasons.append('no CLAIM resolved to orb-target-1 with "downgrade the expectation" / '
                       '"skip the trade" — the sourced half was not cited')
    if not mgmt:
        reasons.append('no class A row quotes "management" — the uncited generalisation was not caught')
    return {"passed": not reasons, "reasons": reasons, "claims": len(claims), "class_a": len(a),
            "fade_rows": [c["line"] for c in fade], "target_rows": [c["line"] for c in target],
            "management_rows": [c["line"] for c in mgmt]}


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


def _label_str(l: dict | None) -> str:
    if not l:
        return "(no LABEL for this minute)"
    s = f"{l['setup']} · regime {l['regime']} · cite {l['cite']}"
    if l.get("because"):
        s += f' · because "{l["because"]}"'
    return s


def _cost(run: dict) -> tuple[float, int]:
    cost = (run.get("classify") or {}).get("cost_usd_list", 0) or 0
    cost += (run.get("claims") or {}).get("cost_usd_list", 0) or 0
    calls = ((run.get("classify") or {}).get("calls", 0) or 0) + ((run.get("claims") or {}).get("calls", 0) or 0)
    return round(cost, 3), calls


def render_page(day: _date, run: dict, wakes: list[dict], results: list[dict],
                window_lines: list[dict], planted: dict | None, model_ran: bool) -> str:
    inp = run.get("inputs") or {}
    ll = run.get("live_lane") or {}
    ev = inp.get("events") or {}
    live_log = inp.get("live_log") or {}
    lv = inp.get("levels") or {}
    sessions = ll.get("sessions_detail") or []
    cov = run.get("coverage") or {}
    nA = sum(len(r["A"]) for r in results)
    nB = sum(len(r["B"]) for r in results)
    nC = sum(len(r["C"]) for r in results)
    nD = sum(len(r["D"]) for r in results)
    n_agree = sum(1 for r in results if r["agree"])
    n_claims = sum(len(r["claims"]) for r in results)
    n_push = sum(len(w["reply"]["pushes"]) for w in wakes)
    cost, calls = _cost(run)

    out = [f"# Footprint audit lane — {day.isoformat()}\n"]
    if sessions and model_ran:
        out.append(f"**{day.isoformat()}: {len(wakes)} wake(s), {n_claims} claim(s) transcribed — "
                   f"A (unsourced rule): {nA}, B (label or regime differs): {nB}, C (figure not in "
                   f"the log): {nC}, D (lane labelled, live did not): {nD}; agree: {n_agree}. "
                   f"Planted test: {'PASSED' if planted and planted['passed'] else 'FAILED' if planted else 'not run'}. "
                   f"{calls} model call(s), ${cost:.3f} at list prices.**\n")
    elif sessions:
        out.append(f"**{day.isoformat()}: {len(wakes)} wake(s) delivered of "
                   f"{ev.get('rth_alerts', '?')} cash-session alerts ({ev.get('alerts', '?')} in "
                   f"the whole day); {n_push} push(es); {nC} figure(s) in the replies not "
                   f"found in the log. Model stages not run.**\n")
    else:
        out.append(f"**{day.isoformat()}: no live session. {ev.get('rth_alerts', '?')} "
                   f"cash-session alerts ({ev.get('alerts', '?')} in the whole day). "
                   f"A labelling-only day"
                   + (f": {len(window_lines)} lines from the window run; planted test "
                      f"{'PASSED' if planted and planted['passed'] else 'FAILED' if planted else 'not run'}."
                      if model_ran else ".") + "**\n")

    out.append("## What this page is\n")
    out.append("Left-hand side: what the live analyst was actually shown and what it said, taken "
               "from the session transcript by code. Right-hand side: a second reading of the same "
               "alert lines by a model that could see only the files in its own folder and had to "
               "quote, word for word, the source every label rests on; a code check failed the run "
               "on any quote the cited lines do not contain. The live replies were transcribed into "
               "claims the same way. Every class below was assigned by code. Times are Central.\n")

    if planted is not None:
        out.append("## The planted test\n")
        out.append(f"The withdrawn 2026-08-25 sentence and the uncited sentence that replaced it were fed "
                   f"through the transcriber as a fake reply. **{'PASSED' if planted['passed'] else 'FAILED'}** — "
                   f"{planted['claims']} claims, {planted['class_a']} unsourced.")
        for r in planted["fade_rows"] + planted["management_rows"] + planted["target_rows"]:
            out.append(f"- `{r}`")
        for r in planted["reasons"]:
            out.append(f"- **{r}**")
        out.append("")

    working_session = [s for s in sessions if s.get("project") != "-root-projects-Strader"
                       or not s.get("runbook_read_before_first_wake")]
    if model_ran and nA:
        out.append("## Class A — rules in the live replies that no source supports (the alarm)\n")
        if working_session:
            s = working_session[0]
            out.append(f"**Read these with care: the live side that day was a session in project "
                       f"`{s.get('project')}`, not a session operating under the analyst contract. "
                       f"The rows below measure that session's prose, not the analyst path.**\n")
        for r in results:
            for c in r["A"]:
                out.append(f"- **{r['wake']}** ({c['kind']}): “{c['quote']}”")
        out.append("")
    if model_ran and nB:
        out.append("## Class B — the lane and the live analyst named it differently\n")
        for r in results:
            for b in r["B"]:
                out.append(f"- **{r['wake']}** {b['what']}: lane says `{b['lane']}` "
                           f"({_label_str(r['lane_label'])}); live said “{b['quote']}” → `{b['live']}`")
        out.append("")
    if nC:
        out.append("## Class C — figures in the replies not found in the log\n")
        for r in results:
            if r["C"]:
                out.append(f"- **{r['wake']}**: {', '.join(r['C'])} (derived sums are the usual cause; "
                           f"the wake section says which lines were searched)")
        out.append("")
    if model_ran and nD:
        out.append("## Class D — the lane labelled a setup; the live reply named none\n")
        for r in results:
            for d in r["D"]:
                out.append(f"- **{r['wake']}**: {_label_str(d['lane'])}")
        out.append("")

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
    for i, (w, r) in enumerate(zip(wakes, results), 1):
        rp = w["reply"]
        out.append(f"### Wake {i} — {r['wake']} tape time, delivered {_ct(w.get('delivered_ct'))}"
                   + (" — agree" if r["agree"] else "") + "\n")
        out.append("Alert lines the watch delivered:\n")
        out.append("```")
        out.extend(w["lines"] or ["(none parsed)"])
        if w.get("bar"):
            out.append(f"bar: {w['bar']}")
        out.append("```\n")
        if model_ran:
            out.append(f"The lane's label (from the alert lines delivered up to this wake only): "
                       f"{_label_str(r['lane_label'])}")
            for l in r["lane_implications"]:
                out.append(f"- implication: cite {l['cite']}"
                           + (f' because "{l["because"]}"' if l.get("because") else "")
                           + f' — {l["text"]}')
            out.append("")
        out.append(f"Reply ({_ct(rp.get('first_reply_ct'))} → {_ct(rp.get('last_reply_ct'))}, "
                   f"{_fmt_usage(rp.get('usage') or {})}):\n")
        text = (rp.get("text") or "").strip() or "(no prose reply in the span)"
        out.extend("> " + ln for ln in text.splitlines())
        out.append("")
        if rp.get("pushes"):
            out.append("Pushed to Steve's phone:\n")
            for p in rp["pushes"]:
                out.append(f"- {p}")
            out.append("")
        if model_ran:
            if r["claims"]:
                out.append("Claims transcribed from the reply:\n")
                for c in r["claims"]:
                    out.append(f"- {c['kind']}: “{c['quote']}” → {c['cite']}"
                               + (f' because "{c["because"]}"' if c.get("because") else ""))
                out.append("")
            else:
                out.append("No claims transcribed from the reply.\n")
            if r["unextracted"]:
                out.append("Sentences with rule-shaped words that no claim quotes from (UNEXTRACTED):\n")
                for s_ in r["unextracted"]:
                    out.append(f"- {s_}")
                out.append("")
        c = r["check"]
        if c["checked"]:
            out.append(f"Number check — {len(c['found'])} of {len(c['checked'])} figures found in "
                       f"the {c['lines_searched']} lines the analyst could read by {c['upto_minute']}"
                       + (f"; **not found: {', '.join(c['not_found'])}**" if c["not_found"] else "")
                       + ".\n")
        else:
            out.append("Number check — the reply carries no price, volume or delta figures.\n")

    out.append("## Coverage — what the live analyst was never shown\n")
    if cov:
        out.append(f"- Alerts in the day: {ev.get('alerts', '?')}; in the cash session: "
                   f"{ev.get('rth_alerts', '?')}; delivered: {cov.get('delivered', 0)}; "
                   f"never delivered (before the scorer started, before the watch was armed, or "
                   f"after it stopped): {cov.get('undelivered', 0)}; ambiguous (same minute as the "
                   f"arm or the stop): {cov.get('ambiguous', 0)}")
        if live_log.get("start_ct"):
            out.append(f"- Scorer started {_ct(live_log['start_ct'])} (its start stamp); everything "
                       f"before that minute was printed in one burst at start-up and could not wake "
                       f"anyone")
        out.append(f"- Note-grade lines ({ev.get('rth_notes', '?')} in the cash session) never wake "
                   f"the analyst; it saw them only if it read the log by hand")
    else:
        out.append(f"- No live session, so every one of the {ev.get('alerts', '?')} alerts is "
                   f"coverage for the labelling stage.")
    if model_ran and window_lines:
        labels = [l for l in window_lines if l["type"] == "LABEL"]
        named = [l for l in labels if l["setup"] != "none"]
        uns = [l for l in labels if l["cite"] == checker.UNSOURCED]
        out.append(f"- The window run (every cash-session EVENT line): {len(labels)} labels, "
                   f"{len(named)} naming a setup, {len(uns)} UNSOURCED, "
                   f"{sum(1 for l in window_lines if l['type'] == 'IMPLICATION')} implications. "
                   f"UNSOURCED means the folder held no rule for it — expected while three of the "
                   f"six setup names have no method file.")
        if named:
            out.append("\n<details><summary>Window labels naming a setup</summary>\n")
            for l in named:
                out.append(f"- {l['t']} {_label_str(l)}")
            out.append("\n</details>")
    if cov.get("undelivered_lines"):
        out.append("\n<details><summary>Undelivered alert lines</summary>\n")
        out.append("```")
        out.extend(cov["undelivered_lines"])
        out.append("```\n</details>")
    out.append("")

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
    ex = run.get("excerpts") or {}
    if ex:
        out.append(f"- Source list: {ex.get('rows')} rows, {ex.get('lines')} lines, statuses "
                   f"{ex.get('statuses')}; every pin checked against HEAD; context folder verified untouched")
    if model_ran:
        cl = run.get("classify") or {}
        cm = run.get("claims") or {}
        out.append(f"- Model calls: classify {cl.get('calls', 0)} (${cl.get('cost_usd_list', 0)}, "
                   f"{cl.get('seconds')} s), claims {cm.get('calls', 0)} (${cm.get('cost_usd_list', 0)}, "
                   f"{cm.get('seconds')} s); model `{(cl.get('slices') or [{}])[0].get('models')}`; "
                   f"no tools, no settings, run from the run folder")
    out.append(f"- Run folder: `/var/moo/state/footprint-icm/{day.isoformat()}/`; produced "
               f"{datetime.now(CT).strftime('%Y-%m-%d %H:%M CT')}")
    out.append("\nThe desk's plain-words pass ran without its model step on this page: the glossary "
               "substitutions only, so no model rewrote what is quoted above.\n")

    # The prompts and the source list, verbatim, so Steve can read and dictate edits.
    out.append("## The prompts and the source list, as run\n")
    for rel in ("20-classify/prompt.md", "40-compare/prompt.md", "20-classify/context/manifest.yaml"):
        p = LANE / rel
        if p.exists():
            try:
                sha = git_short(Path("footprint-icm") / rel)
            except Exception:  # noqa: BLE001 — a page must render even if git is unhappy
                sha = "?"
            out.append(f"<details><summary>{rel} (commit {sha})</summary>\n")
            out.append("```")
            out.append(p.read_text(encoding="utf-8").rstrip())
            out.append("```\n</details>\n")
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
    tripwire = (read_json(out / "tripwire.json").get("words") if (out / "tripwire.json").exists() else [])
    per_wake, window_lines = load_labels(rd)
    claims_all = parse_output(out / "claims" / "output.md")
    planted_lines = parse_output(out / "planted" / "output.md")
    model_ran = bool(per_wake or window_lines or claims_all)
    planted = planted_verdict(planted_lines) if (out / "planted" / "output.md").exists() else None

    results = []
    for w in wakes:
        minute = w["lines"][0][:5] if w["lines"] else "??:??"
        upto = w["lines"][-1][:5] if w["lines"] else "99:99"
        check = number_check(w["reply"].get("text") or "", w["lines"], w.get("bar"), log_lines, upto)
        r = assign_classes(minute, w["reply"].get("text") or "", per_wake.get(minute, []),
                           [c for c in claims_all if c["t"] == minute], check, tripwire)
        r["check"] = check
        results.append(r)
    write_json(out / "numbers.json", [r["check"] for r in results])
    write_json(out / "classes.json", {"wakes": [{k: v for k, v in r.items() if k != "check"}
                                                 for r in results], "planted": planted})

    # Coverage from the live-lane derivation (first session's rule result).
    sess_path = rd / "live-lane/session.json"
    coverage = {}
    if sess_path.exists():
        for s in (read_json(sess_path).get("sessions") or []):
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

    md = render_page(day, run, wakes, results, window_lines, planted, model_ran)
    page = rd / "page.md"
    page.write_text(md, encoding="utf-8")
    rec = {"produced_at": datetime.now(CT).isoformat(timespec="seconds"), "wakes": len(wakes),
           "model_ran": model_ran,
           "figures_checked": sum(len(r["check"]["checked"]) for r in results),
           "figures_not_found": sum(len(r["check"]["not_found"]) for r in results),
           "classes": {"A": sum(len(r["A"]) for r in results), "B": sum(len(r["B"]) for r in results),
                       "C": sum(len(r["C"]) for r in results), "D": sum(len(r["D"]) for r in results),
                       "agree": sum(1 for r in results if r["agree"])},
           "claims": sum(len(r["claims"]) for r in results),
           "planted_passed": planted["passed"] if planted else None,
           "page": str(page)}
    rc = 0
    if not args.no_publish:
        rc = publish(page, day)
        rec["published"] = rc == 0
    update_run_json(day, "compare", rec)
    cl = rec["classes"]
    print(f"40-compare {day}: {len(wakes)} wake(s), {rec['claims']} claims; A {cl['A']} B {cl['B']} "
          f"C {cl['C']} D {cl['D']} agree {cl['agree']}; planted "
          f"{'PASSED' if rec['planted_passed'] else 'FAILED' if rec['planted_passed'] is False else 'not run'}; "
          f"page {page}" + ("" if args.no_publish else (" → desk" if rc == 0 else " (desk render failed)")))
    if planted is not None and not planted["passed"]:
        raise LaneError("the planted test failed: " + "; ".join(planted["reasons"]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaneError as e:
        print(f"[REFUSED] 40-compare: {e}", file=sys.stderr)
        raise SystemExit(2)
