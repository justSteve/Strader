"""Mancini Runbook pilot CLI. [co-7lyf / co-i10h]

Daily run, end to end:

    datastream gate (#1) -> parse (#2, bounded LLM call) -> validate
      -> on pass: write commentary store + last-good ParseResult + print brief
      -> on fail: alert, keep last-good, exit non-zero (never publish suspect levels)

Usage:
    # From the Strader repo root, with the venv active or via ./.venv/bin/python:
    python -m runbook.mancini.run --file /tmp/mancini-latest.txt
    cat newsletter.txt | python -m runbook.mancini.run --date 2026-06-29
    python -m runbook.mancini.run --file nl.txt --no-gate   # offline / no live feeds

The newsletter text comes from --file or stdin. In production the COO
email-ingress blob is fetched first (infra/azure/email-ingress/scripts/
read-latest.sh) and piped in; wiring that fetch into this CLI is the v2 step.

Requires ANTHROPIC_API_KEY_DIRECT for the live parse.
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
    lines.append(f"model={result.model} parsed_at={result.parsed_at}")
    return "\n".join(lines)


def _render_desk_plan(result: ParseResult, extra_sections: list[str] | None = None) -> str:
    """The prose plan-day doc for the steves-desk Trading window. [st-eo0]

    Same content contract as the hand-written myDesk/reports/mancini docs:
    bias, actionable forward notes, then the two ladders with majors bolded.
    Renders whatever the ParseResult holds — a hybrid (deterministic-lists)
    parse yields ladders with commentary marked pending."""
    try:
        weekday = datetime.strptime(result.date, "%Y-%m-%d").strftime("%A")
    except (ValueError, TypeError):
        weekday = "?"
    lines = [
        f"# Mancini — {result.instrument or 'ES'} — {result.date} ({weekday}) plan",
        "",
        f"> {len(result.levels)} levels · {len(result.commentary)} forward notes · "
        f"model `{result.model}` · parsed {result.parsed_at[:16]}Z · "
        "prices verbatim from the letter.",
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
    for kind, title in (("resistance", "Resistance ladder (high→low)"),
                        ("support", "Support ladder (high→low)")):
        lvls = sorted((l for l in result.levels if l.kind == kind),
                      key=lambda l: l.price, reverse=True)
        if not lvls:
            continue
        lines += ["", f"## {title}  ·  **bold = major**", ""]
        lines.append(" · ".join(
            f"**{l.price:g}**" if "major" in l.label.lower() else f"{l.price:g}"
            for l in lvls))
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


def _emit_desk_plan(result: ParseResult, extra_sections: list[str] | None = None) -> Path | None:
    """Write the plan-day doc and refresh the Trading window's stable title.

    Non-fatal by contract (mirrors the chart emit): the parse artifacts are the
    critical output; a desk failure logs and moves on."""
    import subprocess

    desk_root = DESK_REPORTS.parent.parent  # COO/myDesk — absent => no desk here
    if not desk_root.exists():
        logger.warning("desk publish skipped: %s not present", desk_root)
        return None
    DESK_REPORTS.mkdir(parents=True, exist_ok=True)
    doc = DESK_REPORTS / f"mancini-es-{result.date}.md"
    doc.write_text(_render_desk_plan(result, extra_sections), encoding="utf-8")
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
    ap.add_argument("--model", default=None, help="override model id")
    ap.add_argument("--extraction-json",
                    help="pre-built tool-input dict (JSON file) — bypasses the "
                         "live LLM call but NOT validation/persistence. The "
                         "in-session parse path while ANTHROPIC_API_KEY_DIRECT "
                         "is credit-blocked (co-8gp, st-ze6 hybrid mode)")
    ap.add_argument("--no-desk", action="store_true",
                    help="skip publishing the plan doc to the steves-desk "
                         "Trading window")
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

    # 2 + validate. Live LLM call.
    parsed_at = datetime.now(timezone.utc).isoformat()
    kwargs = {"parsed_at": parsed_at}
    if args.model:
        kwargs["model"] = args.model
    if args.extraction_json:
        prebuilt = json.loads(Path(args.extraction_json).read_text(encoding="utf-8"))
        kwargs["extractor"] = lambda _text: prebuilt
        kwargs["model"] = f"in-session:{args.model or 'claude-fable-5'}"
    hybrid = False
    try:
        outcome = parse_mod.parse(raw, **kwargs)
    except Exception as e:  # network, refusal, missing tool block
        logger.exception("extraction failed: %s", e)
        if args.extraction_json or not det_levels:
            print(f"FAILED: extraction error ({e}). Keeping last-good.", file=sys.stderr)
            return 3
        # Hybrid mode [st-ze6]: interpretive leg unavailable (credit block
        # co-8gp / network) — publish the deterministic list levels alone,
        # commentary flagged pending. Still validated, still gated.
        # Never clobber a richer parse already published for this plan-day
        # (e.g. cron firing after an in-session parse).
        existing = PARSED_ROOT / f"{day}.json"
        if existing.exists():
            try:
                prev_model = json.loads(existing.read_text(encoding="utf-8")).get("model", "")
            except (OSError, ValueError):
                prev_model = ""
            if prev_model and prev_model != "deterministic-lists":
                logger.info("hybrid skip: %s already parsed by %r — keeping it",
                            day, prev_model)
                print(f"OK (no-op): {day} already has a richer parse ({prev_model}).")
                return 0
        hybrid = True
        logger.warning("HYBRID MODE: publishing %d deterministic list levels; "
                       "commentary pending (interpretive leg unavailable)",
                       len(det_levels))
        result = ParseResult(
            date=day, instrument="ES",
            session_bias="(commentary pending — interpretive leg unavailable; "
                         "deterministic list levels only)",
            levels=det_levels, commentary=[],
            raw_excerpt=raw[:2000], model="deterministic-lists",
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
            chart_mod.emit_pine(result, generated_at=parsed_at), encoding="utf-8"
        )
        logger.info("chart Pine: %s", chart_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("chart emit failed (non-fatal): %s", e)
        chart_path = None

    # 3b2. Stable-renderer payload → Windows clipboard (#st-5rc). Non-fatal.
    # Parallel-run: 3b keeps emitting the per-day script during migration week.
    payload_path = None
    try:
        from . import payload_emitter

        payload = payload_emitter.build_payload(result)
        payload_path = CHARTS_ROOT / f"{result.date or day}.payload.txt"
        payload_path.write_text(payload, encoding="utf-8")
        rc = payload_emitter.push_clipboard(payload)
        logger.info("stable-renderer payload: %s (%d bytes, clip rc=%d)",
                    payload_path, len(payload.encode()), rc)
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
                result, extra_sections=[overnight.build_overnight_section(result)])
        except Exception as e:  # noqa: BLE001
            logger.warning("desk publish failed (non-fatal): %s", e)

    # 4. Brief (mini #9).
    brief = _render_brief(result)
    if chart_path is not None:
        brief += f"\nchart: {chart_path}  (apply via tradingview-mcp pine_set_source)"
    if desk_path is not None:
        brief += ("\ndesk: Trading window title mancini-latest-es-plan.md "
                  f"<- {desk_path.name}")
    print(brief)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
