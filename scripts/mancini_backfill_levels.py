#!/usr/bin/env python3
"""Mancini levels backfill — a parse artifact for every letter in the cache. [co-vp45h]

WHY
    The recognizer, the post-mortem and the acuity studies take the day's
    Mancini levels from runbook/mancini/parsed/<day>.json, and those
    artifacts are written by the in-session parse — which started 2026-05-19
    and ran on 27 days. The letter cache (data/mancini-letters/, the Azure
    blob mirrored) goes back to 2025-06-24: ~350 letters whose levels nobody
    extracted. The post-mortem backfill found Mancini anchors on 88 of its
    279 tape days for exactly this reason.

WHAT
    For every letter in the cache: clean the HTML, confirm it is a Trade
    Companion letter, resolve the session it plans (title, then the "Trade
    Plan <Weekday>" header, then the first session after the send —
    runbook.mancini.listlevels.resolve_plan_day_full), pull the levels from
    the "Supports are:" / "Resistances are:" sentences (the deterministic
    extractor, listlevels.extract_list_levels — no model, no API), run the
    anti-hallucination validator over the result, and write the artifact
    with model "listlevels-backfill".

    Resends are identical copies of one letter: letters with the same level
    set are one cluster, and the cluster's day is the member whose rule is
    most confident (title > weekday header > next session), earliest send
    breaking ties. Two different letters for one day: the later send wins
    (an evening update supersedes an early release) and the manifest says so.

    An existing artifact is NEVER overwritten unless it is itself a backfill
    artifact and --force is given. The in-session parse is the richer thing
    (bias, commentary, callouts) and always wins. Nor is today's or a later
    session ever written (--until, default yesterday CT): the 08:15 prepare
    treats a levels-only artifact as "not parsed yet" (schema.is_levels_only),
    but the morning belongs to the in-session parse and this tool stays out
    of its way.

    Letters with no list sentences (Substack cut the email off: "Continue
    reading" — the 2025-12-04 … 12-11 run) get no artifact; the manifest
    names them.

USAGE
    .venv/bin/python scripts/mancini_backfill_levels.py --dry-run
    .venv/bin/python scripts/mancini_backfill_levels.py
    .venv/bin/python scripts/mancini_backfill_levels.py --force    # rewrite backfill artifacts only

WHERE IT WRITES
    runbook/mancini/parsed/<day>.json             (one per resolved session)
    data/measurement/mancini-backfill-manifest.jsonl   (one row per letter, rewritten each run)

EXIT CODES
    0 ran;  1 a letter failed validation or an unexpected error (the rest
    still written; the manifest carries the failure).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from runbook.mancini import validate                                   # noqa: E402
from runbook.mancini.clean import clean_newsletter                     # noqa: E402
from runbook.mancini.listlevels import (                               # noqa: E402
    PlanDay, extract_list_levels, resolve_plan_day_full)
from runbook.mancini.listlevels import CENTRAL                         # noqa: E402
from runbook.mancini.schema import BACKFILL_MODEL, Level, ParseResult  # noqa: E402

logger = logging.getLogger("mancini_backfill")

LETTERS_DIR = REPO_ROOT / "data" / "mancini-letters"
PARSED_DIR = REPO_ROOT / "runbook" / "mancini" / "parsed"
MANIFEST = REPO_ROOT / "data" / "measurement" / "mancini-backfill-manifest.jsonl"
SIGNATURE = "tradecompanion"          # the substack link every letter carries
RAW_EXCERPT_CHARS = 2000              # what the in-session parse keeps too


# ------------------------------------------------------------------ one letter

@dataclass
class Letter:
    blob: str
    sent_at: datetime                 # from the blob name (UTC)
    text: str = field(repr=False, default="")
    mancini: bool = False
    plan: PlanDay | None = None
    levels: list = field(default_factory=list)
    status: str = ""                  # set as the run decides
    note: str = ""

    @property
    def fingerprint(self) -> tuple:
        return tuple(sorted((lv.price, lv.kind) for lv in self.levels))

    def manifest_row(self) -> dict:
        return {
            "blob": self.blob,
            "sent_at": self.sent_at.isoformat(),
            "mancini": self.mancini,
            "day": self.plan.day.isoformat() if self.plan else None,
            "rule": self.plan.rule if self.plan else None,
            "title": self.plan.title if self.plan else "",
            "n_levels": len(self.levels),
            "status": self.status,
            "note": self.note,
        }


def sent_at_from_blob_name(name: str) -> datetime:
    """data/mancini-letters/2025-06-24-202425.txt -> 2025-06-24T20:24:25Z.
    The email-ingress function names blobs by UTC receipt time."""
    stem = name[:-4] if name.endswith(".txt") else name
    return datetime.strptime(stem, "%Y-%m-%d-%H%M%S").replace(tzinfo=timezone.utc)


def is_mancini(raw: str, text: str) -> bool:
    """A Trade Companion letter carries the substack link in its HTML (the
    cleaner strips hrefs, so look in the raw) and the two list sentences in
    its text; either marks it. The container also holds other newsletters
    (no sender filter at ingestion) and receipts that name the publication
    without being a letter — those have no list sentences and no
    publication link."""
    if "substack.com/pub/" + SIGNATURE in raw.lower() or SIGNATURE + ".substack.com" in raw.lower():
        return True
    return "Supports are" in text and "Resistances are" in text


def read_letter(path: Path, has_session=None) -> Letter:
    raw = path.read_text(encoding="utf-8", errors="replace")
    letter = Letter(blob=path.name, sent_at=sent_at_from_blob_name(path.name))
    letter.text = clean_newsletter(raw)
    letter.mancini = is_mancini(raw, letter.text)
    if not letter.mancini:
        letter.status, letter.note = "skipped", "not a Trade Companion letter"
        return letter
    letter.plan = resolve_plan_day_full(letter.text, letter.sent_at, has_session)
    letter.levels = extract_list_levels(letter.text)
    if not letter.levels:
        letter.status, letter.note = "no-levels", "no Supports/Resistances sentences (truncated email?)"
    return letter


# ------------------------------------------------------------------ choosing

def choose_per_day(letters: list[Letter]) -> dict[_date, Letter]:
    """Resolve resends and updates to one letter per session.

    Same level set = same letter (a resend): the cluster takes the day of its
    most confident member (earliest send on a tie) and every member is
    re-labelled to it. Different letters on one day: the later send wins.
    """
    clusters: dict[tuple, list[Letter]] = defaultdict(list)
    for lt in letters:
        if lt.mancini and lt.levels:
            clusters[lt.fingerprint].append(lt)

    for members in clusters.values():
        lead = max(members, key=lambda m: (m.plan.confidence, -m.sent_at.timestamp()))
        for m in members:
            if m.plan.day != lead.plan.day:
                m.note = (f"resend of {lead.blob}: day {m.plan.day} ({m.plan.rule}) "
                          f"re-labelled to {lead.plan.day} ({lead.plan.rule})")
                m.plan = PlanDay(lead.plan.day, f"resend→{lead.plan.rule}",
                                 m.plan.title, lead.plan.confidence)

    by_day: dict[_date, list[Letter]] = defaultdict(list)
    for members in clusters.values():
        for m in members:
            by_day[m.plan.day].append(m)
            if m.plan.also is not None:
                # "July 3rd/6th Plan": the same letter filed for the second
                # day at confidence 0, so any letter of that day's own wins.
                shadow = replace(m, plan=PlanDay(m.plan.also, "title-pair-second",
                                                 m.plan.title, 0), status="", note="")
                by_day[m.plan.also].append(shadow)

    chosen: dict[_date, Letter] = {}
    for day, cands in by_day.items():
        winner = max(cands, key=lambda m: (m.plan.confidence > 0, m.sent_at))
        for m in cands:
            if m is winner:
                continue
            if m.plan.rule == "title-pair-second":
                continue                     # a shadow that lost says nothing
            if m.fingerprint == winner.fingerprint:
                m.status, m.note = "duplicate", (m.note or f"same levels as {winner.blob}")
            else:
                m.status = "superseded"
                m.note = (f"{winner.blob} (sent later) has a different level set "
                          f"({len(m.levels)} vs {len(winner.levels)} levels); it wins")
        chosen[day] = winner
    return chosen


# ------------------------------------------------------------------ writing

def artifact_for(letter: Letter, now: datetime) -> dict:
    result = ParseResult(
        date=letter.plan.day.isoformat(), instrument="ES", session_bias="",
        levels=[Level(price=lv.price, kind=lv.kind, label=lv.label, source_quote=lv.source_quote)
                for lv in letter.levels],
        commentary=[], raw_excerpt=letter.text[:RAW_EXCERPT_CHARS],
        model=BACKFILL_MODEL, parsed_at=now.isoformat())
    check = validate.check(letter.text, result)
    if not check.ok:
        raise ValueError(f"validation failed: {check.errors[:3]}")
    doc = result.to_dict()
    doc["backfill"] = {"source_blob": letter.blob, "sent_at": letter.sent_at.isoformat(),
                       "plan_day_rule": letter.plan.rule, "title": letter.plan.title,
                       "n_levels": len(letter.levels)}
    return doc


def existing_artifact(path: Path) -> tuple[str | None, dict | None]:
    """(model, document) of the artifact at ``path``; (None, None) when there
    is none. An unreadable file reads as a foreign model with no document —
    never overwritten."""
    if not path.exists():
        return None, None
    try:
        doc = json.loads(path.read_text())
        return str(doc.get("model", "")), doc
    except (OSError, json.JSONDecodeError):
        return "<unreadable>", None


def filled_artifact(existing: dict, letter: Letter, now: datetime) -> dict:
    """An in-session parse that recorded NO levels (2026-06-29: bias and
    excerpt present, levels []) keeps everything it has and takes the list
    levels; its model stands (it is still that parse) and the backfill block
    says what was filled. The original is kept beside it as .pre-backfill."""
    fresh = artifact_for(letter, now)
    doc = dict(existing)
    doc["levels"] = fresh["levels"]
    doc["backfill"] = {**fresh["backfill"], "filled_empty_levels_of": existing.get("model", "")}
    return doc


def write_artifact(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------------ the run

def run(*, letters_dir: Path, parsed_dir: Path, manifest: Path | None,
        force: bool, dry_run: bool, has_session=None,
        now: datetime | None = None, until: _date | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    until = until or (now.astimezone(CENTRAL).date() - timedelta(days=1))
    paths = sorted(letters_dir.glob("*.txt"))
    letters = [read_letter(p, has_session) for p in paths]
    chosen = choose_per_day(letters)

    counts = defaultdict(int)
    errors = 0
    parsed_dir.mkdir(parents=True, exist_ok=True)
    for day in sorted(chosen):
        lt = chosen[day]
        path = parsed_dir / f"{day.isoformat()}.json"
        prior, prior_doc = existing_artifact(path)
        empty_prior = prior_doc is not None and not prior_doc.get("levels")
        if day > until:
            lt.status, lt.note = "not-yet", f"{day} is after --until {until}; the live parse owns it"
        elif prior is not None and prior != BACKFILL_MODEL and not empty_prior:
            lt.status, lt.note = "kept-existing", f"{path.name} already written by {prior!r}"
        elif prior == BACKFILL_MODEL and not force:
            lt.status, lt.note = "kept-backfill", f"{path.name} already backfilled (--force rewrites)"
        else:
            try:
                if empty_prior and prior != BACKFILL_MODEL:
                    doc, status = filled_artifact(prior_doc, lt, now), "filled-empty"
                    lt.note = f"{path.name} by {prior!r} had no levels; filled from the list"
                else:
                    doc, status = artifact_for(lt, now), ("written" if prior is None else "rewritten")
            except ValueError as e:
                lt.status, lt.note = "error", str(e)
                errors += 1
                logger.error("%s -> %s: %s", lt.blob, day, e)
                continue
            if dry_run:
                lt.status = {"written": "would-write", "rewritten": "would-rewrite",
                             "filled-empty": "would-fill-empty"}[status]
            else:
                if status == "filled-empty":
                    path.with_suffix(".json.pre-backfill").write_text(
                        json.dumps(prior_doc, indent=2), encoding="utf-8")
                write_artifact(path, doc)
                lt.status = status
    for lt in letters:
        counts[lt.status or "unresolved"] += 1

    if manifest is not None and not dry_run:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("w", encoding="utf-8") as fh:
            for lt in letters:
                fh.write(json.dumps(lt.manifest_row()) + "\n")

    rules = defaultdict(int)
    for lt in chosen.values():
        rules[lt.plan.rule] += 1
    days = sorted(chosen)
    return {"letters": len(letters), "mancini": sum(1 for lt in letters if lt.mancini),
            "sessions": len(chosen),
            "first_day": days[0].isoformat() if days else None,
            "last_day": days[-1].isoformat() if days else None,
            "by_status": dict(counts), "by_rule": dict(rules), "errors": errors,
            "letters_detail": letters}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--letters-dir", type=Path, default=LETTERS_DIR)
    ap.add_argument("--parsed-dir", type=Path, default=PARSED_DIR)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--force", action="store_true",
                    help="rewrite artifacts this tool wrote before (never an in-session parse)")
    ap.add_argument("--dry-run", action="store_true", help="resolve and report; write nothing")
    ap.add_argument("--until", type=_date.fromisoformat, default=None,
                    help="last session to write (default: yesterday CT; never today or later)")
    ap.add_argument("--no-tape", action="store_true",
                    help="do not consult the tape corpus when a title names two days")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    has_session = None
    if not args.no_tape:
        try:
            from market.orderflow.replay import has_es_day
            has_session = has_es_day
        except Exception as e:  # pragma: no cover - corpus module absent
            logger.warning("tape corpus unavailable (%s); a two-day title takes the later day", e)

    summary = run(letters_dir=args.letters_dir, parsed_dir=args.parsed_dir,
                  manifest=args.manifest, force=args.force, dry_run=args.dry_run,
                  has_session=has_session, until=args.until)
    detail = summary.pop("letters_detail")
    for lt in detail:
        if (lt.status in ("error", "superseded", "no-levels") or lt.status.endswith("filled-empty")
                or (lt.note and "re-labelled" in lt.note)):
            logger.info("%-26s %-10s %-12s %s", lt.blob, lt.plan.day if lt.plan else "-", lt.status, lt.note)
    print(json.dumps(summary, indent=2))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
