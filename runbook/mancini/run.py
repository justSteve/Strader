"""Mancini Runbook pilot CLI. [co-7lyf / co-i10h]

Daily run, end to end:

    datastream gate (#1) -> parse (#2, in-session extraction) -> validate
      -> on pass: write commentary store + last-good ParseResult + print brief
      -> on fail: alert, keep last-good, exit non-zero (never publish suspect levels)

Usage:
    # From the Strader repo root, with the venv active or via ./.venv/bin/python:
    python -m runbook.mancini.run --from-blob --extraction-json /tmp/x.json
    python -m runbook.mancini.run --file /tmp/mancini-latest.txt
    cat newsletter.txt | python -m runbook.mancini.run --date 2026-06-29
    python -m runbook.mancini.run --file nl.txt --no-gate   # offline / no live feeds

The newsletter text comes from --from-blob, --file, or stdin.

This CLI calls no model. The deterministic list scrape (listlevels.py) runs on
every pass and needs no judgment. The interpretive leg is an in-session prompt
parse: an agent reads the letter, writes the extraction JSON, and passes it via
--extraction-json — see extraction-contract.md for the instructions and the JSON
shape. Without --extraction-json the run publishes deterministic levels alone
with commentary flagged pending (hybrid mode). No credential is required.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as date_cls, datetime, timezone
from pathlib import Path

from . import clean
from . import listlevels
from . import parse as parse_mod
from . import schema
from . import store as store_mod
from . import validate as validate_mod
from .schema import ParseResult

logger = logging.getLogger("runbook.mancini")

# Last-good full ParseResult lands here, for intraday re-emit and recovery.
PARSED_ROOT = Path(__file__).resolve().parent / "parsed"
# Generated daily Pine overlay (#3 deterministic chart).
CHARTS_ROOT = Path(__file__).resolve().parent / "charts"
# steves-desk Trading window publication [st-eo0]: the plan-day doc lands in
# COO's mancini reports dir, and COO's refresh script copies the newest one to
# the stable Trading-window address (myDesk/trading/mancini-latest-es-plan.md).
# Cross-repo write sanctioned by the shared-executable-space convention.
DESK_REPORTS = Path("/root/projects/COO/myDesk/reports/mancini")
DESK_REFRESH = Path("/root/projects/COO/myDesk/trading/trading-desk-refresh.sh")
# Browser view of the same plan [st-lo2]. Steve keeps a tab parked on this
# address and refreshes it in place, so the parse re-renders it rather than
# opening anything. COO affirmed the /tmp/desk-<slug>.html mapping as contract
# in reply to st-qx4 — moving it breaks a bookmark no error will explain.
DESK_HTML = Path("/tmp/desk-mancini-latest-es-plan.html")
DESK_HTML_SCRIPT = Path("/root/projects/COO/tmuxMOO/bin/desk-html.sh")


def _read_newsletter(file_arg: str | None) -> str:
    if file_arg:
        raw = Path(file_arg).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raise SystemExit("ERROR: provide newsletter text via --file or stdin")
    # Blobs arrive as raw HTML email; convert to the plain visible-text format
    # the parser + prompt expect. Plain-text input passes through. (co-ylhf)
    return clean.clean_newsletter(raw)


def _resolve_day(date_arg: str | None) -> str:
    """The parse *plan-day*: the trading session the newsletter plans for.

    This dates the emitted levels/commentary. It is deliberately NOT the day the
    gate checks — see _resolve_gate_day. [co-i10h]
    """
    if date_arg:
        return date_arg
    try:
        from market.corpus.paths import central_date

        return central_date().isoformat()
    except Exception:
        return date_cls.today().isoformat()


def _resolve_gate_day() -> date_cls:
    """The gate *data-day*: the most-recent-completed session (prev weekday).

    Decoupled from the parse plan-day by Decision A (Steve, 2026-07-01):
    Databento is T+1, so the upcoming session the letter plans for has no
    manifest yet — gating on it would spuriously halt every pre-close run.
    The gate instead checks the last finished session, resolved identically to
    scripts/corpus_daily.py's ingestion target via the shared helper so the two
    cannot drift onto different days. [co-i10h]
    """
    from market.corpus.paths import most_recent_session_day

    return most_recent_session_day()


def _run_gate(args, gate_day: date_cls | None) -> bool:
    """Return True if the Runbook may proceed.

    ``gate_day`` is the most-recent-completed session (see _resolve_gate_day),
    NOT the parse plan-day. An explicit --manifest short-circuits day
    resolution (the path is used verbatim). [co-i10h]
    """
    if args.no_gate:
        logger.warning("datastream gate SKIPPED (--no-gate)")
        return True
    from runbook.datastream import gate

    res = gate.check(manifest_path=args.manifest, day=gate_day)
    where = "explicit manifest" if args.manifest else f"data-day {gate_day}"
    if res.ok:
        logger.info("datastream gate OK (%s): %s", where, res.checked)
        return True
    logger.error("datastream gate FAILED (%s) — halting. reasons: %s",
                 where, res.reasons)
    return False


def _clip_wanted(args) -> bool:
    """Should this run conclude by loading the Daily Payload? [st-llor]

    A completed interpretive parse is the Mancini Parse procedure and owns the
    clipboard by default. Hybrid/diagnostic runs do not, unless --clip forces
    it (the pre-open wrapper, which never has an extraction). --no-clip opts an
    interpretive run out for backfill or a renderer check.
    """
    if args.no_clip:
        return False
    if args.clip:
        return True
    return bool(args.extraction_json)


def _prepare_only(args, day: str, det_levels: list) -> int:
    """08:15 pre-open mode [st-lw58]: every no-judgment step, then stop.

    Under the 2026-08-06 ruling Steve triggers every parse, so the old hybrid
    publish put a lesser, commentary-free plan on the desk 15 minutes before
    the open — exactly when he'd read it. This mode fetches, cleans, and
    scrapes the deterministic lists (all done by the time we're called), then
    ALERTS readiness instead of publishing. The desk and parsed/<day>.json are
    only ever written by a real parse.

    The one thing it still owns in the good case: when an in-session parse
    already ran overnight, the clipboard payload is hours stale by 08:15, so
    reload the richer stored parse — the morning routine must find the best
    payload waiting. [st-llor]
    """
    existing = PARSED_ROOT / f"{day}.json"
    prev_model = ""
    if existing.exists():
        try:
            prev_model = json.loads(existing.read_text(encoding="utf-8")).get("model", "")
        except (OSError, ValueError):
            prev_model = ""
    if prev_model and not schema.is_levels_only(prev_model):
        msg = f"OK (prepared): {day} already parsed by {prev_model!r}."
        if _clip_wanted(args):
            try:
                prev = ParseResult.from_dict(
                    json.loads(existing.read_text(encoding="utf-8")))
                msg += " " + _push_payload(prev, existing)
            except Exception as e:  # noqa: BLE001
                logger.warning("payload reload failed (non-fatal): %s", e)
                msg += f" clipboard: RELOAD FAILED ({e})"
        # Overnight refresh [st-vxbw]: the parse that exists ran whenever Steve
        # ran it — 01:28 CT today — so its interaction section covers a slice
        # of the overnight. Re-render the SAME plan doc from the full
        # letter-time → now window. Levels untouched; no browser window from
        # cron (the parked tab refreshes in place). Non-fatal.
        if not args.no_desk:
            try:
                from . import refresh as refresh_mod

                outcome = refresh_mod.refresh(day, open_browser=False, quiet=True)
                msg += " " + outcome.summary
            except Exception as e:  # noqa: BLE001
                logger.warning("overnight refresh failed (non-fatal): %s", e)
                msg += f" overnight refresh: FAILED ({e})"
        print(msg)
        return 0

    n_sup = sum(1 for lv in det_levels if lv.kind == "support")
    n_res = sum(1 for lv in det_levels if lv.kind == "resistance")
    summary = (f"Mancini letter fetched for {day}: {len(det_levels)} levels "
               f"scraped ({n_sup} supports, {n_res} resistances). "
               "Ready to parse — run /mancini-parse.")
    logger.info("prepare-only: %s", summary)
    # Readiness ping, not an emergency: no session is in the loop at 08:15, so
    # the signal goes code-to-phone. Failure to alert must not fail the run —
    # the health log and cron log still carry the readiness line.
    try:
        from strader.alerts import send as alert_send
        alert_send("Mancini ready to parse", summary, urgent=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("ready-alert failed (non-fatal): %s", e)
    print(f"OK (prepared, awaiting parse): {summary}")
    return 0


def _push_payload(result: ParseResult, payload_path: Path | None = None) -> str:
    """Build the Daily Payload from ``result`` and load it. Returns a brief note."""
    from . import payload_emitter
    from .validate import split_out_of_band

    payload = payload_emitter.build_payload(result)
    size = len(payload.encode())
    # A dropped level means the LETTER likely has a typo — that is a finding
    # the brief must carry, not bury in a log file. [st-wqr]
    _, dropped = split_out_of_band(result.levels)
    sanity = ""
    if dropped:
        listed = ", ".join(f"{lv.price:g} ({lv.kind})" for lv in dropped)
        sanity = (f"\nSANITY: {len(dropped)} out-of-band level(s) dropped from "
                  f"emit — {listed}. Check the letter for typos.")
    rc = payload_emitter.push_clipboard(payload)
    if rc == 0:
        logger.info("Daily Payload -> clipboard (%d bytes)", size)
        return (f"clipboard: Daily Payload loaded ({size} bytes) — "
                "Ctrl+V onto the indicator" + sanity)
    logger.warning("clipboard push returned rc=%d", rc)
    where = payload_path or "the payload file"
    return f"clipboard: PUSH FAILED (rc={rc}) — paste from {where}" + sanity


def _render_brief(result: ParseResult) -> str:
    lines = [
        f"=== MANCINI MORNING BRIEF — {result.instrument or '?'} {result.date or ''} ===",
        f"Bias: {result.session_bias or '(none)'}",
        "",
        "Levels:",
    ]
    for lvl in sorted(result.levels, key=lambda l: l.price, reverse=True):
        label = f" — {lvl.label}" if lvl.label else ""
        lines.append(f"  {lvl.price:>9}  {lvl.kind:<11}{label}")
    if not result.levels:
        lines.append("  (none)")
    lines += ["", "Forward-looking commentary:"]
    for c in result.commentary:
        anchors = ", ".join(str(p) for p in c.trigger.anchor_prices)
        anchor_str = f" [{c.trigger.type}: {anchors}]" if anchors else f" [{c.trigger.type}]"
        lines.append(f"  • {c.text}{anchor_str}")
    if not result.commentary:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"model={result.model} parsed {_ct(result.parsed_at)}")
    return "\n".join(lines)


def _ct(iso_ts: str) -> str:
    """An ISO timestamp (UTC or offset-aware) as 'YYYY-MM-DD HH:MM CT'.

    Steve, 2026-08-18: "anytime we come across a timestamp written in UTC we
    need to update it to CT" — every human-facing surface (desk doc header,
    terminal brief, Pine 'Generated:' line) shows Central. Stored/JSON
    timestamps stay ISO UTC; only the rendering converts. Unparseable input is
    returned unchanged rather than dropped."""
    from zoneinfo import ZoneInfo

    if not iso_ts:
        return ""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return iso_ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M CT")


def _render_desk_plan(result: ParseResult, extra_sections: list[str] | None = None,
                      overnight_section: str | None = None,
                      header_note: str | None = None) -> str:
    """The prose plan-day doc for the steves-desk Trading window. [st-eo0]

    Same content contract as the hand-written myDesk/reports/mancini docs:
    bias, actionable forward notes, then the two ladders with majors bolded.
    Renders whatever the ParseResult holds — a hybrid (deterministic-lists)
    parse yields ladders with commentary marked pending.

    Steve's 2026-08-11 refinements:
    - ``overnight_section`` folds INTO the forward-looking notes rather than
      standing as its own section further down. What price has already done to a
      level is forward-looking information — it belongs beside the note it
      qualifies, not in an appendix he has to scroll to.
    - Ladders carry Mancini's own callouts for the levels he singles out. The
      compact price run stays (it is what makes a 46-level ladder scannable) and
      the annotated subset is listed under it. Earlier versions collapsed every
      callout to `major`/`minor`; that over-corrected a narrow instruction to
      drop his RUNNER/position talk, and threw away the level colour with it.
    """
    try:
        weekday = datetime.strptime(result.date, "%Y-%m-%d").strftime("%A")
    except (ValueError, TypeError):
        weekday = "?"
    lines = [
        f"# Mancini — {result.instrument or 'ES'} — {result.date} ({weekday}) plan",
        "",
        f"> {len(result.levels)} levels · {len(result.commentary)} forward notes · "
        f"model `{result.model}` · parsed {_ct(result.parsed_at)} · "
        "prices verbatim from the letter."
        + (f" {header_note}" if header_note else ""),
        "",
        "## Bias",
        "",
        result.session_bias or "(none)",
        "",
        "## Actionable — forward-looking notes",
        "",
    ]
    for c in result.commentary:
        anchors = ", ".join(str(p) for p in c.trigger.anchor_prices)
        suffix = f"  _[{c.trigger.type}: {anchors}]_" if anchors else f"  _[{c.trigger.type}]_"
        lines.append(f"- {c.text}{suffix}")
    if not result.commentary:
        lines.append("_(commentary pending — interpretive leg unavailable; "
                     "ladders below are the deterministic list levels)_")
    # Overnight interaction lands inside this section, demoted to a sub-head so
    # it reads as part of the forward picture rather than a separate appendix.
    if overnight_section:
        lines += ["", _demote_headings(overnight_section)]
    for kind, title in (("resistance", "Resistance ladder (high→low)"),
                        ("support", "Support ladder (high→low)")):
        lvls = sorted((l for l in result.levels if l.kind == kind),
                      key=lambda l: l.price, reverse=True)
        if not lvls:
            continue
        lines += ["", f"## {title}  ·  **bold = major**", ""]
        lines.append(" · ".join(
            f"**{l.price:g}**" if schema.is_major(l.label) else f"{l.price:g}"
            for l in lvls))
        annotated = [l for l in lvls if schema.callout(l.label)]
        if annotated:
            lines += ["", "_Mancini's callouts:_", ""]
            for l in annotated:
                marker = f"**{l.price:g}**" if schema.is_major(l.label) else f"{l.price:g}"
                lines.append(f"- {marker} — {schema.callout(l.label)}")
    extras = [l for l in result.levels if l.kind not in ("resistance", "support")]
    if extras:
        lines += ["", "## Other named levels", ""]
        for l in sorted(extras, key=lambda l: l.price, reverse=True):
            label = f" — {l.label}" if l.label else ""
            lines.append(f"- {l.price:g} ({l.kind}){label}")
    for section in (extra_sections or []):
        lines += ["", section]
    lines.append("")
    return "\n".join(lines)


def _demote_headings(section: str) -> str:
    """Push a section's markdown headings down one level. [st-eo0]

    Used to fold the overnight brief into the forward-looking notes: it is
    authored as a top-level `##` section and becomes a `###` sub-head there.
    Fenced code is not a concern — these sections carry none."""
    return "\n".join(
        ("#" + line) if line.startswith("## ") else line
        for line in section.splitlines()
    )


def _render_desk_html(doc: Path) -> Path | None:
    """Re-render the plan doc as the desk browser page at DESK_HTML. [st-lo2]

    Delegates to COO's desk-html.sh (co-wp0db), which owns the desk stylesheet.
    Strader deliberately keeps no fallback renderer: an inline copy is exactly
    the duplication the extraction removed, and a stale-but-consistent page beats
    a second stylesheet drifting out of sync with every other desk page.

    Renders the doc this run just wrote rather than the stable-title copy: same
    content on the normal path (ours is the newest), but the page still lands on
    today's plan if COO's refresh script is missing or fails.

    Passes DESK_HTML explicitly. Left to itself the script derives
    /tmp/desk-<basename>.html, which for mancini-es-<date>.md would mint a new
    address every day instead of the one Steve's tab is parked on.

    Non-fatal by contract — a parse must never die over a browser page.
    """
    import subprocess

    if not DESK_HTML_SCRIPT.exists():
        logger.warning("desk html skipped: renderer absent (%s)", DESK_HTML_SCRIPT)
        return None
    try:
        proc = subprocess.run([str(DESK_HTML_SCRIPT), str(doc), str(DESK_HTML)],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("desk html skipped: renderer failed to run (%s)", e)
        return None
    if proc.returncode == 3:
        # Documented as "marked not on PATH" — routine under a bare cron, since
        # marked lives in the Windows npm install. Logged at info, not warning.
        # Carries stderr because desk-html.sh also exits 3 when marked runs and
        # fails, so the text is the only thing separating the two. [st-qx4]
        logger.info("desk html skipped: %s", proc.stderr.strip()[:300])
        return None
    if proc.returncode != 0:
        logger.warning("desk-html.sh failed (rc=%d): %s",
                       proc.returncode, proc.stderr.strip()[:300])
        return None
    logger.info("desk html: %s — refresh the open tab to see it", DESK_HTML)
    return DESK_HTML


def _emit_desk_plan(result: ParseResult, extra_sections: list[str] | None = None,
                    overnight_section: str | None = None,
                    header_note: str | None = None) -> Path | None:
    """Write the plan-day doc and refresh the Trading window's stable title.

    Non-fatal by contract (mirrors the chart emit): the parse artifacts are the
    critical output; a desk failure logs and moves on. Also the re-render path
    of the overnight refresh [st-vxbw] — same doc, same title, same html; only
    the interaction section and ``header_note`` differ."""
    import subprocess

    desk_root = DESK_REPORTS.parent.parent  # COO/myDesk — absent => no desk here
    if not desk_root.exists():
        logger.warning("desk publish skipped: %s not present", desk_root)
        return None
    DESK_REPORTS.mkdir(parents=True, exist_ok=True)
    doc = DESK_REPORTS / f"mancini-es-{result.date}.md"
    doc.write_text(_render_desk_plan(result, extra_sections, overnight_section,
                                     header_note),
                   encoding="utf-8")
    logger.info("desk plan doc: %s", doc)
    if DESK_REFRESH.exists():
        proc = subprocess.run(["bash", str(DESK_REFRESH)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            logger.warning("trading-desk-refresh failed (rc=%d): %s",
                           proc.returncode, proc.stderr.strip()[:300])
        else:
            logger.info("Trading window refreshed — stable title "
                        "mancini-latest-es-plan.md now serves %s", doc.name)
    else:
        logger.warning("refresh script missing (%s) — doc written but the "
                       "stable title was not updated", DESK_REFRESH)
    _render_desk_html(doc)
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mancini Runbook pilot")
    ap.add_argument("--show", metavar="YYYY-MM-DD", nargs="?", const="today",
                    help="re-emit the stored brief for a plan-day (default "
                         "today) — no gate, no fetch, no parse")
    ap.add_argument("--file", help="newsletter text file (default: stdin)")
    ap.add_argument("--from-blob", action="store_true",
                    help="fetch the newest letter from the email-ingress blob "
                         "container instead of --file/stdin [st-ze6]")
    ap.add_argument("--date", help="trading day YYYY-MM-DD (default: today US/Central)")
    ap.add_argument("--no-gate", action="store_true", help="skip the datastream gate")
    ap.add_argument("--manifest", help="explicit manifest.json path for the gate")
    ap.add_argument("--store-root", help="override commentary store root (testing)")
    ap.add_argument("--model", default=None,
                    help="label recorded alongside the in-session parse, e.g. "
                         "the agent/model that read the letter (default: the "
                         "generic 'in-session')")
    ap.add_argument("--extraction-json",
                    help="the in-session extraction (JSON file) — THE "
                         "interpretive leg [st-26q5]. Written by an agent that "
                         "read the letter; see extraction-contract.md. Skips no "
                         "validation or persistence. Omit it and the run "
                         "publishes deterministic list levels alone with "
                         "commentary pending (st-ze6 hybrid mode)")
    ap.add_argument("--prepare-only", action="store_true",
                    help="fetch/clean/scrape then stop and alert readiness; "
                         "never publish. The 08:15 cron mode [st-lw58]. "
                         "Reloads the clipboard from an existing richer parse.")
    ap.add_argument("--no-desk", action="store_true",
                    help="skip publishing the plan doc to the steves-desk "
                         "Trading window")
    # Clipboard policy [st-llor, refining st-0x9]. A COMPLETED interpretive
    # parse — the Mancini Parse procedure — concludes by loading the Daily
    # Payload, because that run IS the pre-open routine. Hybrid, diagnostic and
    # backfill runs still leave the clipboard alone: it is Steve's live desktop,
    # and whatever sits there at 08:29 is what lands on the chart.
    clip_group = ap.add_mutually_exclusive_group()
    clip_group.add_argument("--clip", action="store_true",
                            help="force the Daily Payload push even when the run "
                                 "is hybrid/diagnostic. Set by the 08:15 CT "
                                 "pre-open wrapper, which has no agent in the "
                                 "loop and so never has an extraction to trigger "
                                 "the default.")
    clip_group.add_argument("--no-clip", action="store_true",
                            help="suppress the push on an interpretive parse — "
                                 "for backfilling an old day or checking a "
                                 "renderer change without seizing the clipboard.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.show:
        show_day = _resolve_day(None if args.show == "today" else args.show)
        path = PARSED_ROOT / f"{show_day}.json"
        if not path.exists():
            print(f"no stored parse for {show_day} ({path})", file=sys.stderr)
            return 1
        result = ParseResult.from_dict(json.loads(path.read_text(encoding="utf-8")))
        print(_render_brief(result))
        if not args.no_desk:
            _emit_desk_plan(result)
        return 0

    gate_day = _resolve_gate_day()         # gate data-day (last completed session)

    # 1. Datastream gate — checks the last completed session, decoupled from the
    #    plan-day because Databento is T+1 (the plan-day has no data yet). [co-i10h]
    if not _run_gate(args, gate_day):
        print("HALTED: datastream gate failed. Keeping last-good artifacts.",
              file=sys.stderr)
        return 2

    if args.from_blob:
        from . import fetch as fetch_mod
        try:
            blob_name, blob_raw = fetch_mod.fetch_latest()
        except RuntimeError as e:
            logger.error("blob fetch failed: %s", e)
            print(f"FAILED: blob fetch ({e}). Keeping last-good.", file=sys.stderr)
            return 2
        logger.info("letter source: blob %s", blob_name)
        raw = clean.clean_newsletter(blob_raw)
    else:
        raw = _read_newsletter(args.file)
    if not raw.strip():
        logger.error("empty newsletter input")
        return 2

    # Plan-day: explicit --date wins; else the letter's own title ("July 23
    # Plan") is authoritative; today is the last resort. [st-ze6]
    if args.date:
        day = _resolve_day(args.date)
    else:
        title_day = listlevels.resolve_plan_day(raw, _resolve_gate_day())
        day = title_day.isoformat() if title_day else _resolve_day(None)
        logger.info("plan-day from %s: %s",
                    "letter title" if title_day else "fallback (today)", day)
    logger.info("Mancini Runbook run — parse plan-day %s, gate data-day %s",
                day, gate_day.isoformat())

    # Deterministic list extraction runs on EVERY pass — cross-check when the
    # interpretive leg runs, sole level source in hybrid mode. [st-ze6]
    det_levels = listlevels.extract_list_levels(raw)
    logger.info("deterministic lists: %d levels (%d supports, %d resistances)",
                len(det_levels),
                sum(1 for l in det_levels if l.kind == "support"),
                sum(1 for l in det_levels if l.kind == "resistance"))

    # Pre-open prepare mode stops here: everything above needed no judgment,
    # everything below builds a publishable plan. [st-lw58]
    if args.prepare_only:
        return _prepare_only(args, day, det_levels)

    # 2 + validate. The interpretive leg is an in-session prompt parse supplied
    # via --extraction-json (extraction-contract.md) — this CLI calls no model
    # and needs no credential. [st-26q5]
    parsed_at = datetime.now(timezone.utc).isoformat()
    hybrid = False

    if args.extraction_json:
        prebuilt = json.loads(Path(args.extraction_json).read_text(encoding="utf-8"))
        try:
            outcome = parse_mod.parse(
                raw,
                extractor=lambda _text: prebuilt,
                model=f"in-session:{args.model}" if args.model else "in-session",
                parsed_at=parsed_at,
            )
        except Exception as e:  # malformed extraction, shape mismatch
            logger.exception("extraction failed: %s", e)
            print(f"FAILED: extraction error ({e}). Keeping last-good.", file=sys.stderr)
            return 3
    else:
        # Hybrid mode [st-ze6]: no in-session extraction was supplied — publish
        # the deterministic list levels alone, commentary flagged pending.
        # Still validated, still gated.
        if not det_levels:
            print("FAILED: no --extraction-json, and no Supports/Resistances "
                  "lists to fall back on. Keeping last-good.", file=sys.stderr)
            return 3
        # Never clobber a richer parse already published for this plan-day
        # (e.g. cron firing after an in-session parse).
        existing = PARSED_ROOT / f"{day}.json"
        if existing.exists():
            try:
                prev_model = json.loads(existing.read_text(encoding="utf-8")).get("model", "")
            except (OSError, ValueError):
                prev_model = ""
            if prev_model and not schema.is_levels_only(prev_model):
                logger.info("hybrid skip: %s already parsed by %r — keeping it",
                            day, prev_model)
                msg = f"OK (no-op): {day} already has a richer parse ({prev_model})."
                # The parse is a no-op, but the CLIPBOARD is not. [st-llor]
                # This is the 08:15 pre-open job's real work when an in-session
                # parse already ran overnight: the payload it would have loaded
                # is hours stale by now, so reload the RICHER stored parse. The
                # morning routine must find the best available payload waiting,
                # not whatever Steve last copied.
                if _clip_wanted(args):
                    try:
                        prev = ParseResult.from_dict(
                            json.loads(existing.read_text(encoding="utf-8")))
                        msg += " " + _push_payload(prev, existing)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("payload reload failed (non-fatal): %s", e)
                        msg += f" clipboard: RELOAD FAILED ({e})"
                print(msg)
                return 0
        hybrid = True
        logger.warning("HYBRID MODE: publishing %d deterministic list levels; "
                       "commentary pending (no in-session extraction supplied)",
                       len(det_levels))
        result = ParseResult(
            date=day, instrument="ES",
            session_bias="(commentary pending — no in-session extraction; "
                         "deterministic list levels only)",
            levels=det_levels, commentary=[],
            raw_excerpt=raw[:2000], model=schema.DETERMINISTIC_LISTS_MODEL,
            parsed_at=parsed_at,
        )
        outcome = parse_mod.ParseOutcome(
            result=result, validation=validate_mod.check(raw, result))

    if not outcome.ok:
        logger.error("validation FAILED — not publishing. errors: %s",
                     outcome.validation.errors)
        print("FAILED: validation rejected the parse (possible hallucinated "
              f"levels). Keeping last-good.\n  {outcome.validation.errors}",
              file=sys.stderr)
        return 4

    result = outcome.result
    if not result.date:
        result.date = day

    # Count-parity cross-check [st-ze6]: when the interpretive leg ran, every
    # deterministically-listed level must appear in its output — a missing one
    # is an omission (the quiet failure mode validation can't otherwise see).
    if not hybrid and det_levels:
        missing = listlevels.parity_check(
            det_levels, {lv.price for lv in result.levels})
        if missing:
            miss_str = ", ".join(f"{lv.price:.0f} ({lv.kind})" for lv in missing)
            logger.error("list-parity FAILED — interpretive parse omitted: %s", miss_str)
            print(f"FAILED: interpretive parse omitted {len(missing)} listed "
                  f"level(s): {miss_str}. Keeping last-good.", file=sys.stderr)
            return 4

    # 3. Persist: commentary store + last-good full result.
    store_path = store_mod.append(
        result.commentary, result.date or day,
        instrument=result.instrument, ingested_at=parsed_at,
        store_root=args.store_root,
    )
    PARSED_ROOT.mkdir(parents=True, exist_ok=True)
    parsed_path = PARSED_ROOT / f"{result.date or day}.json"
    parsed_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    logger.info("commentary store: %s", store_path)
    logger.info("last-good parse: %s", parsed_path)

    # 3b. Deterministic daily chart Pine (#3). Non-fatal: the levels/commentary
    # are the critical output; a chart-emit failure must not sink the run.
    chart_path = None
    try:
        from . import chart as chart_mod

        CHARTS_ROOT.mkdir(parents=True, exist_ok=True)
        chart_path = CHARTS_ROOT / f"{result.date or day}.pine"
        chart_path.write_text(
            chart_mod.emit_pine(result, generated_at=_ct(parsed_at)), encoding="utf-8"
        )
        logger.info("chart Pine: %s", chart_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("chart emit failed (non-fatal): %s", e)
        chart_path = None

    # 3b2. Daily Payload for the stable renderer (#st-5rc). Non-fatal.
    # Parallel-run: 3b keeps emitting the per-day script during migration week.
    #
    # The FILE is written here; the CLIPBOARD push is deferred to the end of the
    # run [st-llor] so the payload only lands once the whole procedure has
    # actually succeeded — a half-finished parse must never leave Steve holding
    # a payload that looks authoritative.
    payload_path = None
    payload = None
    try:
        from . import payload_emitter

        payload = payload_emitter.build_payload(result)
        payload_path = CHARTS_ROOT / f"{result.date or day}.payload.txt"
        payload_path.write_text(payload, encoding="utf-8")
        logger.info("Daily Payload: %s (%d bytes)",
                    payload_path, len(payload.encode()))
    except Exception as e:  # noqa: BLE001
        logger.warning("payload emit failed (non-fatal): %s", e)

    # 3c. steves-desk Trading window: plan-day doc under the stable title
    # mancini-latest-es-plan.md. Non-fatal, same contract as the chart. [st-eo0]
    desk_path = None
    if not args.no_desk:
        try:
            # Overnight interaction supplement (st-doz): what price has already
            # done to the letter's levels since it was written. Never blocks —
            # build_overnight_section degrades to a one-line note internally.
            from . import overnight

            desk_path = _emit_desk_plan(
                result,
                overnight_section=overnight.build_overnight_section(result))
        except Exception as e:  # noqa: BLE001
            logger.warning("desk publish failed (non-fatal): %s", e)

    # 4. Conclude by loading the Daily Payload. [st-llor]
    # Default ON for an interpretive parse — that run is the Mancini Parse
    # procedure and the clipboard is its last step, so the morning routine is
    # double-click the indicator, Ctrl+A, Ctrl+V with nothing in between.
    # Hybrid/diagnostic runs stay off unless --clip forces it; --no-clip opts
    # an interpretive run out (backfill, renderer check).
    should_clip = _clip_wanted(args)

    clip_note = None
    if payload is None:
        if should_clip:
            logger.warning("no payload built — clipboard left untouched")
    elif should_clip:
        try:
            clip_note = _push_payload(result, payload_path)
        except Exception as e:  # noqa: BLE001
            logger.warning("clipboard push failed (non-fatal): %s", e)
            clip_note = f"clipboard: PUSH FAILED ({e}) — paste from {payload_path}"
    else:
        clip_note = f"clipboard: untouched — payload at {payload_path}"

    # 5. Brief (mini #9).
    brief = _render_brief(result)
    if chart_path is not None:
        brief += f"\nchart: {chart_path}  (apply via tradingview-mcp pine_set_source)"
    if desk_path is not None:
        brief += ("\ndesk: Trading window title mancini-latest-es-plan.md "
                  f"<- {desk_path.name}")
    if clip_note is not None:
        brief += f"\n{clip_note}"
    print(brief)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
