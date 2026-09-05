"""Entitlements registry — load it, probe what is probeable, keep the rest dated. [st-g0or]

The registry (``config/entitlements.yaml``) is the single home for subscription
and entitlement state. This module is its pure reader: it loads the file, runs
the probeable checks against LOCAL state only, ages the dated assertions, and
renders the observation report. ``scripts/entitlements_probe.py`` is the thin
CLI over it — same split as ``strader/schwab_token.py`` / ``scripts/schwab_token_health.py``.

Two kinds of line, and the distinction is the entire point:

    PROBED   Re-derived every run from a local JSON state file or a corpus
             directory listing. An observation. Proves the DATA IS LANDING —
             never that the contract is paid, because a cancelled plan keeps
             delivering until the billing period ends.

    DATED    What Steve reported from a billing portal on a date. Not verified
             since. Rendered with its date and its age, always, so no reader can
             mistake it for a measurement.

**This module calls no vendor API.** Not Schwab, not Databento, not GexBot. It
opens local files and stats directories, nothing else — the agent is barred from
executing live-API code (``.claude/rules/schwab-api-gate.md``) and a probe that
needed credentials to answer "what are we entitled to" would be unrunnable at the
moment the answer matters. It also means the probe cannot itself be the thing
that is down.
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strader import _yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / "config" / "entitlements.yaml"
DEFAULT_CORPUS_ROOT = REPO_ROOT / "data" / "corpus"

# A dated fact older than this (and with no explicit stale_after_days) stops
# being merely dated and starts being AGED — still true as far as we know, but
# old enough that quoting it without re-checking is how the OPRA week happened.
DEFAULT_DATED_STALE_DAYS = 30


# ─── results ─────────────────────────────────────────────────────────────────

@dataclass
class ProbedLine:
    """One observation. `state` is what we measured; `ok` is whether that is fine."""
    id: str
    label: str
    vendor: str
    state: str                 # OK | IDLE | ABSENT | MISSING | STALE | ALARM | ERROR
    age: str                   # human age of the evidence ("21.4h", "1d", "-")
    detail: str
    ok: bool = True
    what: str = ""

    def to_dict(self) -> dict:
        return {"kind": "probed", "id": self.id, "label": self.label, "vendor": self.vendor,
                "state": self.state, "age": self.age, "detail": self.detail, "ok": self.ok,
                "what": self.what}


@dataclass
class DatedLine:
    """One assertion of Steve's, with the date attached — never without it."""
    id: str
    label: str
    vendor: str
    state: str
    cost: str
    confirmed_on: str | None
    confirmed_by: str | None
    source: str
    age_days: float | None
    verdict: str               # DATED | AGED | REVIEW DUE | NEVER
    what: str = ""
    note: str = ""
    cost_note: str = ""
    review_by: str | None = None
    bead: str = ""
    evidence: list[str] = field(default_factory=list)
    question: str = ""         # `needs_steve:` — an open gap inside an otherwise dated entry

    @property
    def actionable(self) -> bool:
        return self.verdict in ("AGED", "REVIEW DUE")

    def to_dict(self) -> dict:
        return {"kind": "dated", "id": self.id, "label": self.label, "vendor": self.vendor,
                "state": self.state, "cost": self.cost, "confirmed_on": self.confirmed_on,
                "confirmed_by": self.confirmed_by, "source": self.source,
                "age_days": self.age_days, "verdict": self.verdict, "review_by": self.review_by,
                "what": self.what, "note": self.note, "cost_note": self.cost_note,
                "bead": self.bead, "evidence": self.evidence, "needs_steve": self.question}


@dataclass
class Report:
    checked_at: datetime
    registry_path: Path
    probed: list[ProbedLine]
    dated: list[DatedLine]

    @property
    def needs_steve(self) -> list[DatedLine]:
        """Facts no probe can settle: never confirmed, aged out, past review, or
        carrying an explicit open question inside an otherwise dated entry."""
        return [d for d in self.dated
                if d.verdict in ("NEVER", "AGED", "REVIEW DUE") or d.question]

    def actionable(self, strict: bool = False) -> bool:
        """True when something needs a human TODAY. Standing never-confirmed gaps
        are listed every run but do not flip this — a check that always fails is
        a check nobody reads — unless `strict`."""
        if any(not p.ok for p in self.probed):
            return True
        if any(d.actionable for d in self.dated):
            return True
        return strict and any(d.verdict == "NEVER" for d in self.dated)

    def to_dict(self, strict: bool = False) -> dict:
        return {"checked_at": _iso(self.checked_at),
                "registry": str(self.registry_path),
                "actionable": self.actionable(strict),
                "probed": [p.to_dict() for p in self.probed],
                "dated": [d.to_dict() for d in self.dated]}


# ─── loading ─────────────────────────────────────────────────────────────────

def load_registry(path: str | Path | None = None) -> dict:
    """Parse the registry. Raises FileNotFoundError if it is missing — an absent
    registry must be loud, never an empty report that reads like 'all clear'."""
    p = Path(path) if path else DEFAULT_REGISTRY
    data = _yaml.load_file(p)
    if not isinstance(data, dict):
        raise ValueError(f"{p}: expected a mapping at the top level")
    return data


def entries(registry: dict, section: str) -> list[dict]:
    """Yield a section's entries with their `id` filled in.

    The file authors each section as an id-keyed mapping — the form
    ``strader/_yaml.py`` parses without PyYAML, and the form that makes the id
    unmissable when a human edits it. A list of entries carrying their own `id`
    is accepted too, so a future re-shape of the file does not break the probe.
    """
    section_data = registry.get(section) or {}
    if isinstance(section_data, dict):
        return [{"id": key, **(val or {})} for key, val in section_data.items()]
    return [dict(e) for e in section_data]


def dated_state(entry_id: str, registry_path: str | Path | None = None) -> str | None:
    """The ``state:`` Steve last asserted for one dated entry, or None when the
    entry is not in the registry. Propagates the load error when the registry
    itself is missing or unparseable — a caller gating work on an entitlement
    must fail loudly there, never read the failure as "not held". [st-xxo0]
    """
    for entry in entries(load_registry(registry_path), "dated"):
        if str(entry.get("id")) == entry_id:
            state = entry.get("state")
            return None if state is None else str(state)
    return None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_date(raw: Any) -> datetime | None:
    """Registry dates are authored as quoted YYYY-MM-DD; PyYAML may hand back a
    date object instead, so normalise both."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _ct_date(dt: datetime):
    """Corpus day-dirs are named in Central Time; UTC's date runs ahead of CT
    after 19:00 CT, which would age today's file by a day."""
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/Chicago")).date()
    except Exception:  # pragma: no cover - tz database absent
        return dt.date()


def _age_str(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m"
    if seconds < 172800:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ─── probes (local state only) ───────────────────────────────────────────────

def _probe_json_file(entry: dict, root: Path, now: datetime) -> tuple[str, str, str, bool]:
    rel = str(entry.get("path", ""))
    path = root / rel
    if not path.exists():
        return "MISSING", "-", f"{rel} absent — the checker that writes it is not running", False
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return "ERROR", "-", f"unreadable ({type(e).__name__})", False

    status = str(rec.get(str(entry.get("status_field", "status")), "?"))
    ok_values = [str(v) for v in (entry.get("ok_values") or ["ok"])]
    stamp = _parse_ts(rec.get(str(entry.get("checked_at_field", "checked_at"))))
    age_secs = (now - stamp).total_seconds() if stamp else None
    limit_h = float(entry.get("stale_after_hours") or 0) or None

    bits = []
    for f in entry.get("fields") or []:
        v = rec.get(str(f))
        if v is None:
            continue
        bits.append(f"{v:.1f}" if isinstance(v, float) else str(v))
    detail = " · ".join(bits) or status

    ok = status in ok_values
    state = status.upper() if ok else "ALARM"
    if ok and limit_h and age_secs is not None and age_secs > limit_h * 3600:
        # The heartbeat itself has stopped — a healthy verdict from yesterday is
        # not a healthy verdict. Say so instead of relaying the stale status.
        return "STALE", _age_str(age_secs), f"last written {_age_str(age_secs)} ago (limit {limit_h:g}h) — verdict below is OLD: {detail}", False
    return state, _age_str(age_secs), detail, ok


def _corpus_days(corpus_root: Path) -> list[str]:
    if not corpus_root.is_dir():
        return []
    return sorted(d.name for d in corpus_root.iterdir()
                  if d.is_dir() and len(d.name) == 10 and d.name[4] == "-" and d.name[:4].isdigit())


# The 07:30 compaction packs each finished session's raw .jsonl to .jsonl.gz,
# so the bare name is evidence only until compaction runs. Accept the packed
# sibling under the same age arithmetic or every completed day reads STALE and
# the day counts downstream become floors rather than counts [st-5wk8]. The
# numbered .dbn.zst capture parts are deliberately NOT accepted: a day holding
# only those means compaction did not finish, which should still surface.
COMPACTED_SUFFIXES = (".gz", ".zst")


def _stream_forms(filename: str) -> tuple[str, ...]:
    """The bare name first, then the forms compaction leaves behind."""
    return (filename, *(filename + s for s in COMPACTED_SUFFIXES))


def _newest_stream_day(corpus_root: Path, days: list[str],
                       filename: str) -> tuple[str | None, Path | None]:
    """Newest corpus day holding a NON-EMPTY form of ``filename``.

    Size matters: a 0-byte file is a collector that opened the handle and
    delivered nothing, not evidence the entitlement is live (2026-08-30 left
    exactly that, and it masked five healthy packed days behind it).
    """
    for day in reversed(days):
        for name in _stream_forms(filename):
            candidate = corpus_root / day / name
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return day, candidate
            except OSError:      # transient DrvFs / unmounted 9p — treat as absent
                continue
    return None, None


def _probe_corpus_stream(entry: dict, corpus_root: Path, now: datetime) -> tuple[str, str, str, bool]:
    filename = str(entry.get("filename", ""))
    expect = str(entry.get("expect", "present")).lower()
    window = int(entry.get("expect_within_days") or 4)
    days = _corpus_days(corpus_root)
    today = _ct_date(now)   # corpus dirs are named in Central, not UTC

    hit_day, hit_path = _newest_stream_day(corpus_root, days, filename)

    if hit_day is None:
        if expect == "absent":
            return "ABSENT", "-", f"{filename} not present in any corpus day — as expected", True
        return "MISSING", "-", f"{filename} not found in any corpus day", False

    age_days = (today - datetime.strptime(hit_day, "%Y-%m-%d").date()).days
    size_mb = hit_path.stat().st_size / 1e6
    # Name the packed form: 3.8 MB gzipped and 3.8 MB raw are different volumes.
    form = "" if hit_path.name == filename else f" [{hit_path.name[len(filename):]}]"
    detail = f"last {hit_day} ({age_days}d ago) · {size_mb:,.1f} MB{form}"

    if expect == "absent":
        if age_days <= window:
            return "ALARM", f"{age_days}d", f"REAPPEARED — {detail}. This stream was halted; something is billing again", False
        return "ABSENT", f"{age_days}d", f"none within {window}d (newest {hit_day}) — as expected", True
    if age_days > window:
        return "STALE", f"{age_days}d", f"{detail} — older than the {window}d window", False
    return "OK", f"{age_days}d", detail, True


def _probe_path_present(entry: dict, root: Path, now: datetime) -> tuple[str, str, str, bool]:
    path = root / str(entry.get("path", ""))
    expect = str(entry.get("expect", "present")).lower()
    window = int(entry.get("expect_within_days") or 7)
    if not path.exists():
        if expect == "absent":
            return "ABSENT", "-", f"{entry.get('path')} absent — as expected", True
        return "MISSING", "-", f"{entry.get('path')} absent", False
    children = sorted(c.name for c in path.iterdir()) if path.is_dir() else []
    # Prefer day-named children — an archive's newest DAY is the fact. Its mtime
    # is not: a manifest rewrite freshens the directory while the last harvested
    # DAY sits days behind, which is exactly the gap worth seeing.
    days = [c for c in children if len(c) == 10 and c[4] == "-" and c[:4].isdigit()]
    newest = (days or children)[-1] if children else None
    unit = "days" if days else "entries"
    detail = f"{len(days or children)} {unit} · newest {newest}" if newest else "present, empty"

    # A CLOSED archive is not a stale one. When the entitlement that fed a
    # directory ends, its newest day stops advancing by design, and ageing it
    # against a freshness window turns into a permanent false alarm that costs
    # the report its meaning. `final_day` says the feed is closed and names the
    # last day it delivered; the check then becomes an integrity check — the
    # newest day must still BE that day [st-qcj3].
    final_day = str(entry.get("final_day") or "").strip()
    if final_day and days and expect != "absent":
        newest_day = days[-1]
        if newest_day == final_day:
            return ("OK", "closed",
                    f"{detail} — closed archive, complete through {final_day}", True)
        verdict = "GREW" if newest_day > final_day else "SHRANK"
        return ("ALARM", "closed",
                f"{detail} — closed archive {verdict} past its final day "
                f"{final_day}; the registry and the disk disagree", False)

    if days:
        gap = (_ct_date(now) - datetime.strptime(days[-1], "%Y-%m-%d").date()).days
        age, stale = f"{gap}d", gap > window
        detail = f"{detail} ({gap}d ago)"
    else:
        age_secs = now.timestamp() - path.stat().st_mtime
        age, stale = _age_str(age_secs), age_secs > window * 86400

    if expect == "absent":
        return "ALARM", age, f"present when it should be absent — {detail}", False
    if stale:
        return "STALE", age, f"{detail} — nothing new inside the {window}d window", False
    return "OK", age, detail, True


_PROBES = {
    "json_file": _probe_json_file,
    "corpus_stream": _probe_corpus_stream,
    "path_present": _probe_path_present,
}


def run_probes(registry: dict, *, repo_root: Path | None = None,
               corpus_root: Path | None = None, now: datetime | None = None) -> list[ProbedLine]:
    root = repo_root or REPO_ROOT
    corpus = corpus_root or (root / "data" / "corpus")
    now = now or datetime.now(timezone.utc)
    out: list[ProbedLine] = []
    for entry in entries(registry, "probed"):
        kind = str(entry.get("kind", ""))
        fn = _PROBES.get(kind)
        if fn is None:
            out.append(ProbedLine(str(entry.get("id", "?")), str(entry.get("label", "?")),
                                  str(entry.get("vendor", "")), "ERROR", "-",
                                  f"unknown probe kind {kind!r}", False,
                                  str(entry.get("what", ""))))
            continue
        base = corpus if kind == "corpus_stream" else root
        try:
            state, age, detail, ok = fn(entry, base, now)
        except Exception as e:  # a broken probe must not take the report down
            state, age, detail, ok = "ERROR", "-", f"{type(e).__name__}: {e}", False
        note = str(entry.get("note", "")).strip()
        if note and state not in ("OK",):
            detail = f"{detail} · {note}"
        out.append(ProbedLine(str(entry.get("id", "?")), str(entry.get("label", "?")),
                              str(entry.get("vendor", "")), state, age, detail, ok,
                              str(entry.get("what", ""))))
    return out


# ─── dated assertions ────────────────────────────────────────────────────────

def read_dated(registry: dict, *, now: datetime | None = None) -> list[DatedLine]:
    now = now or datetime.now(timezone.utc)
    horizon = float((registry.get("meta") or {}).get("dated_stale_after_days")
                    or DEFAULT_DATED_STALE_DAYS)
    out: list[DatedLine] = []
    for entry in entries(registry, "dated"):
        confirmed_raw = entry.get("confirmed_on")
        confirmed = _parse_date(confirmed_raw)
        age_days = (now - confirmed).total_seconds() / 86400 if confirmed else None
        review = _parse_date(entry.get("review_by"))
        limit = float(entry.get("stale_after_days") or horizon)

        if confirmed is None:
            verdict = "NEVER"
        elif review is not None and now >= review:
            verdict = "REVIEW DUE"
        elif age_days is not None and age_days > limit:
            verdict = "AGED"
        else:
            verdict = "DATED"

        out.append(DatedLine(
            id=str(entry.get("id", "?")), label=str(entry.get("label", "?")),
            vendor=str(entry.get("vendor", "")), state=str(entry.get("state", "?")),
            cost=str(entry.get("cost", "")),
            confirmed_on=(str(confirmed_raw)[:10] if confirmed_raw else None),
            confirmed_by=(str(entry["confirmed_by"]) if entry.get("confirmed_by") else None),
            source=str(entry.get("source", "")), age_days=age_days, verdict=verdict,
            what=str(entry.get("what", "")), note=str(entry.get("note", "")),
            cost_note=str(entry.get("cost_note", "")),
            review_by=(str(entry.get("review_by"))[:10] if entry.get("review_by") else None),
            bead=str(entry.get("bead", "")),
            evidence=[str(x) for x in (entry.get("evidence") or [])],
            question=str(entry.get("needs_steve", "") or "")))
    return out


def build_report(registry_path: str | Path | None = None, *, repo_root: Path | None = None,
                 corpus_root: Path | None = None, now: datetime | None = None) -> Report:
    now = now or datetime.now(timezone.utc)
    path = Path(registry_path) if registry_path else DEFAULT_REGISTRY
    reg = load_registry(path)
    return Report(checked_at=now, registry_path=path,
                  probed=run_probes(reg, repo_root=repo_root, corpus_root=corpus_root, now=now),
                  dated=read_dated(reg, now=now))


# ─── rendering (house style: surface_liveness.sh) ────────────────────────────

_RULE = "-" * 103


def render(report: Report, *, verbose: bool = False) -> str:
    """The observation report. Sections are labelled OBSERVED and DATED because a
    reader who skims must not be able to mistake one for the other."""
    try:
        from zoneinfo import ZoneInfo
        stamp = report.checked_at.astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:  # pragma: no cover - tz database absent
        stamp = _iso(report.checked_at)

    L: list[str] = []
    try:
        reg_disp = report.registry_path.relative_to(REPO_ROOT)
    except ValueError:
        reg_disp = report.registry_path
    L.append(f"ENTITLEMENTS — probed {stamp} · registry {reg_disp}")
    L.append("")
    L.append("OBSERVED — measured just now, from local state files only. No vendor API is")
    L.append("called: a green line proves the DATA IS LANDING, never that the CONTRACT is")
    L.append("paid. A cancelled plan keeps delivering until its period ends.")
    L.append("")
    L.append(f"{'SURFACE':<24} {'STATE':<9} {'AGE':<6} EVIDENCE")
    L.append(_RULE)
    for p in report.probed:
        L.append(f"{_clip(p.label, 24):<24} {p.state:<9} {p.age:<6} {_clip(p.detail, 61)}")
        if not p.ok:
            # An alarm is exactly where truncation costs the most — spell it out.
            for chunk in textwrap.wrap(" ".join(p.detail.split()), 96):
                L.append(f"    {chunk}")

    L.append("")
    L.append("DATED — NOT observations. Each line is what Steve reported from a billing")
    L.append("portal or vendor page on the date shown, unverified since. Quote these WITH")
    L.append("their date — 'as of <date>, Steve reported …' — never as current truth.")
    L.append("")
    L.append(f"{'SUBSCRIPTION':<38} {'STATE':<12} {'AS OF':<11} {'AGE':<5} CONFIRMED BY / SOURCE")
    L.append(_RULE)
    for d in report.dated:
        age = f"{d.age_days:.0f}d" if d.age_days is not None else "-"
        conf = d.confirmed_on or "NEVER"
        src = d.source if not d.confirmed_by else f"{d.confirmed_by} · {d.source}"
        flag = "" if d.verdict == "DATED" else f"  [{d.verdict}]"
        L.append(f"{_clip(d.label, 38):<38} {_clip(d.state, 12):<12} {conf:<11} {age:<5} "
                 f"{_clip(src, 32)}{flag}")
        if verbose:
            if d.cost:
                L.append(f"      cost: {d.cost}")
            for line_ in (d.what, d.cost_note, d.note):
                for chunk in textwrap.wrap(" ".join(str(line_).split()), 96) if line_ else []:
                    L.append(f"      {chunk}")

    needs = report.needs_steve
    L.append("")
    if needs:
        L.append("NEEDS STEVE — no probe can settle these. NEVER = never recorded by anyone;")
        L.append("AGED / REVIEW DUE = recorded once and now old enough to re-check; the rest are")
        L.append("dated entries carrying one open question inside them.")
        L.append("")
        for d in needs:
            if d.verdict == "NEVER":
                why = "never confirmed by anyone"
            elif d.verdict == "AGED":
                why = f"last confirmed {d.confirmed_on} ({d.age_days:.0f}d ago)"
            elif d.verdict == "REVIEW DUE":
                why = f"review date {d.review_by} reached"
            else:
                why = f"dated {d.confirmed_on}, with an open question"
            L.append(f"  · {d.label} — {why}")
            for chunk in textwrap.wrap(" ".join((d.question or d.note or "").split()), 92):
                L.append(f"      {chunk}")
            if d.source:
                L.append(f"      check: {d.source}")
    else:
        L.append("NEEDS STEVE — nothing. Every dated line is inside its confirmation window.")

    L.append("")
    L.append("Read this OVER any bundle doc, CurrentStatus line, or memory file that states")
    L.append("a plan, tier, or price: those record what was true when someone wrote them.")
    L.append("Registry edits are Steve's call — agents may add probes, never advance a date.")
    return "\n".join(L)
