"""Canon — the OKF knowledge bundle read as data. [st-k5a8]

``knowledge/`` is an OKF v0.1 bundle (``knowledge/index.md``: one concept per
file, typed front matter, ``index.md`` and ``log.md`` reserved) and
``strader/playbooks/`` holds the nine strategy records. Until this module
existed nothing in the code read either as data: the audit lane's source list
(``footprint-icm/20-classify/context/manifest.yaml``) was eight hand rows, one
file's tabled state was kept in three places by hand, and the two status
vocabularies (the lane's ``trusted | exploratory | …`` and the records'
``candidate | worthy | …``) shared no words. The refactor-and-blotter plan
(``docs/a2a/2026-08-29-coo-to-strader-refactor-and-blotter-plan.md`` §2–§3)
gives every file one header and this loader reads it.

The header is OKF's front matter extended, not replaced (Steve, 2026-08-29:
``type`` stays OKF's field, its vocabulary grows; nothing is added beside it
that OKF already names)::

    id: orb-target-1                 # stable, kebab, equals the file stem
    type: management-rule            # OKF's field; vocabulary in VALID_TYPES
    status: trusted                  # FILE_STATUSES
    owner: Steve
    provenance:
      origin: steve-dictation        # ORIGINS
      ref: "master reference §Risk rules, June 2026"
    sources: [OFB-31]                # optional: register ids this entity converges with
    lineage:
      supersedes: orb-playbook#Target 1   # an entity id, "path#heading", or null
      since: 2026-09-02
      commit: <sha or null>
    cite: ["## Statement"]           # required on method types, no default (Strader
                                     # counter 2026-08-30 §6b: zero files carry a
                                     # Statement heading, 22 have no ## heading at all).
                                     # Each entry is one citable excerpt = one generated
                                     # row: "## Heading" | "body" (the whole body) |
                                     # "L23-36" (whole-file lines) | {cite: ..., id: slug}
    triggers: []                     # optional: EVENT kinds / emission types
    rule: null                       # optional predictive block (plan §5)
    title: …                         # kept from OKF
    description: …
    timestamp: …

This module holds *form*, in the shape of :mod:`strader.entities.playbook`:
``Entity`` is one validated file, ``Canon`` the catalog. Every problem in a
file is reported together, naming the path, so a fresh agent can open the file
and fix it. ``Canon.load(strict=False)`` collects problems per file instead of
raising — the migration's review sheet and ``python -m strader.entities.canon
--report`` use that.

What consumes it: the generated source list (``footprint-icm/bin/manifest_gen.py``,
st-apxk) takes ``Canon.lane_sources()`` and ``Entity.cites()`` — one manifest row
per cite, id ``<entity-id>-<slug>`` (counter §6c), and only entities under
``knowledge/`` are lane sources; the nine playbook records are registry entities
and not citable by the lane until one is promoted (counter §6g). The stub
entities (st-4l6e), the rule registry (st-djb9) and the regenerated
``index.md`` read the same catalog. A test loads the real bundle and fails on
any file that does not validate — the discipline
``test_the_real_manifest_builds_and_its_pins_hold`` gives the manifest today.

Decision (a), Steve's YES relayed by Desk 2026-08-29 14:40 CT: one status
vocabulary across method files and playbook records. ``letter`` is a
generated-only status (st-jep1's per-day Mancini rows) and is refused in a
file. ``source`` is a refusal word: a register is a claim about what someone
said, never a rule.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator, Mapping

from strader._yaml import safe_load as _safe_load

# strader/entities/canon.py -> strader/entities -> strader -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
PLAYBOOKS_DIR = REPO_ROOT / "strader" / "playbooks"
BUNDLE_DIRS: tuple[Path, ...] = (KNOWLEDGE_DIR, PLAYBOOKS_DIR)

# OKF reserves these two names; they are the bundle's entry point and history,
# not entities, and the registry regenerates index.md from the headers.
RESERVED_FILES = frozenset({"index.md", "log.md"})

# ─── vocabularies (plan §2) ──────────────────────────────────────────────────

METHOD_TYPES = frozenset({"setup", "management-rule", "regime-rule", "concept", "strategy"})
OKF_TYPES = frozenset({"convention", "decision", "operator-profile", "reference", "runbook", "rule"})
LEGACY_TYPES = frozenset({"playbook"})  # the nine knowledge/ files retyped in curation (stage 2)
REGISTER_TYPE = "register"
VALID_TYPES = METHOD_TYPES | OKF_TYPES | LEGACY_TYPES | {REGISTER_TYPE}

FILE_STATUSES = frozenset({"trusted", "exploratory", "under-review", "tabled", "withdrawn", "source"})
GENERATED_STATUSES = frozenset({"letter"})           # written by code per day, never in a file
ADMISSIBLE_STATUSES = frozenset({"trusted", "exploratory"})  # a file the lane may cite
# The closed status vocabulary as the lane sees it: file statuses that admit,
# plus the generated-only `letter` rows (st-jep1). manifest_gen validates its
# rows against this, the file loader against FILE_STATUSES (counter §6a).
LANE_STATUSES = ADMISSIBLE_STATUSES | GENERATED_STATUSES
SOURCE_TYPES = frozenset({REGISTER_TYPE, "reference"})  # the only types that may carry status: source

ORIGINS = frozenset({"steve-dictation", "third-party-source", "empirical-observation", "code"})

REQUIRED_FIELDS = ("id", "type", "status", "owner", "provenance", "lineage",
                   "title", "description", "timestamp")
RULE_FIELDS = ("registered", "module", "entry", "exit", "instrument")
BODY_CITE = "body"

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LINES_CITE_RE = re.compile(r"^L(\d+)-(\d+)$")


class CanonError(Exception):
    """Raised when a bundle file or the catalog is malformed.

    The message names every offending path with every problem found in it.
    """


# ─── cites ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CiteSpec:
    """One ``cite`` entry as written: a heading, the whole body, or a line range.

    ``slug`` names the generated manifest row (``<entity-id>-<slug>``): the
    heading text in kebab case, ``body``, or ``l<start>-<end>`` unless the
    entry gave an explicit ``id``. The line-range form is pinned to the file
    as it is; a header rewrite moves it (counter §6f), so the migration writes
    it only where no heading exists.
    """

    kind: str            # "heading" | "body" | "lines"
    value: str           # heading text, "", or "<start>-<end>"
    level: int | None    # heading level, or None
    slug: str
    spec: str            # the entry as written


@dataclass(frozen=True)
class Cite:
    """One resolved citable excerpt: whole-file, 1-indexed, inclusive lines."""

    spec: CiteSpec
    start: int
    end: int

    @property
    def slug(self) -> str:
        return self.spec.slug


# ─── the entity ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Entity:
    """One validated bundle file: the extended OKF header plus the body."""

    id: str
    type: str
    status: str
    owner: str
    origin: str
    ref: str
    sources: tuple[str, ...]
    supersedes: str | None
    since: date
    commit: str | None
    cite: tuple[CiteSpec, ...]
    triggers: tuple[str, ...]
    rule: Mapping | None
    rules: tuple[str, ...]          # strategy only: the rule entities it lists
    title: str
    description: str
    timestamp: str
    body: str
    path: Path
    lines: tuple[str, ...]          # the whole file, for line-numbered excerpts
    body_start: int                 # 1-indexed line number of the first body line
    extra: Mapping                  # every other front-matter key, untouched

    @property
    def is_method(self) -> bool:
        return self.type in METHOD_TYPES

    @property
    def admissible(self) -> bool:
        """May the audit lane cite this entity? Method type and an admitting status."""
        return self.is_method and self.status in ADMISSIBLE_STATUSES

    def headings(self) -> list[tuple[int, int, str]]:
        """Every body heading as (1-indexed line, level, text)."""
        out = []
        for i in range(self.body_start - 1, len(self.lines)):
            m = _HEADING_RE.match(self.lines[i])
            if m:
                out.append((i + 1, len(m.group(1)), m.group(2).strip()))
        return out

    def cites(self) -> list[Cite]:
        """Every cite entry resolved to whole-file lines — one generated row each.

        A heading's range runs from the line after it to the line before the
        next heading of the same or a higher level (or the end of the file);
        ``body`` is everything after the front matter; ``L<a>-<b>`` is taken as
        written. Blank lines are trimmed from both ends. Line numbers are of
        the whole file, front matter included, so they match ``git show`` and
        the manifest. Entries that do not resolve are omitted here and reported
        as problems by the loader.
        """
        out: list[Cite] = []
        for spec in self.cite:
            resolved = self.resolve(spec)
            if resolved is not None:
                out.append(Cite(spec, *resolved))
        return out

    def resolve(self, spec: CiteSpec) -> tuple[int, int] | None:
        """(start, end) for one cite entry, or None when it does not resolve."""
        total = len(self.lines)
        if spec.kind == BODY_CITE:
            start, end = self.body_start, total
        elif spec.kind == "lines":
            a, b = (int(x) for x in spec.value.split("-"))
            if a < self.body_start or b > total or a > b:
                return None
            start, end = a, b
        else:
            heads = self.headings()
            hit = next((i for i, (_, lvl, txt) in enumerate(heads)
                        if txt == spec.value and (spec.level is None or lvl == spec.level)), None)
            if hit is None:
                return None
            line, level, _ = heads[hit]
            end = total
            for nline, nlevel, _ in heads[hit + 1:]:
                if nlevel <= level:
                    end = nline - 1
                    break
            start = line + 1
        while start <= end and not self.lines[start - 1].strip():
            start += 1
        while end >= start and not self.lines[end - 1].strip():
            end -= 1
        return (start, end) if start <= end else None

    def excerpt(self, cite: Cite) -> str:
        """The excerpt's lines, verbatim."""
        return "\n".join(self.lines[cite.start - 1:cite.end])

    def statement(self) -> str:
        """The first cite's excerpt, verbatim (empty when nothing resolves)."""
        cites = self.cites()
        return self.excerpt(cites[0]) if cites else ""

    def quote(self, cite: Cite | None = None) -> str:
        """The first sentence of an excerpt — the manifest row's ``quote``."""
        if cite is None:
            cites = self.cites()
            if not cites:
                return ""
            cite = cites[0]
        text = " ".join(self.excerpt(cite).split())
        m = re.match(r"(.+?[.!?])(?:\s|$)", text)
        return (m.group(1) if m else text).strip()


# ─── loading one file ────────────────────────────────────────────────────────

def load_entity(path: str | Path) -> Entity:
    """Parse and validate one bundle file; raise :class:`CanonError` naming it."""
    entity, problems = _load(Path(path))
    if problems:
        raise CanonError(f"{path}: " + "; ".join(problems))
    assert entity is not None
    return entity


def _load(path: Path) -> tuple[Entity | None, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, ["file not found"]

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, ["file must open with a '---' front-matter fence"]
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, ["unterminated front matter (no closing '---')"]
    try:
        fm = _safe_load("\n".join(lines[1:end]))
    except Exception as exc:  # the subset loader raises its own error type
        return None, [f"front matter does not parse: {exc}"]
    if not isinstance(fm, dict):
        return None, ["front matter did not parse to a mapping"]

    problems: list[str] = []
    missing = [k for k in REQUIRED_FIELDS if fm.get(k) in (None, "")]
    if missing:
        problems.append(f"missing header field(s): {', '.join(missing)}")

    ident = str(fm.get("id", "")).strip()
    if ident:
        if ident != path.stem:
            problems.append(f"id {ident!r} does not equal the file stem {path.stem!r}")
        if not _ID_RE.match(ident):
            problems.append(f"id {ident!r} is not kebab-case")

    etype = str(fm.get("type", "")).strip()
    if etype and etype not in VALID_TYPES:
        problems.append(f"type {etype!r} not one of {sorted(VALID_TYPES)}")

    status = str(fm.get("status", "")).strip()
    if status:
        if status in GENERATED_STATUSES:
            problems.append(f"status {status!r} is generated-only and may not be written in a file")
        elif status not in FILE_STATUSES:
            problems.append(f"status {status!r} not one of {sorted(FILE_STATUSES)}")
    if etype == REGISTER_TYPE and status and status != "source":
        problems.append("a register carries status 'source' (it is a claim about what someone said, never a rule)")
    if status == "source" and etype and etype not in SOURCE_TYPES:
        problems.append(f"status 'source' is only for types {sorted(SOURCE_TYPES)}, not {etype!r}")

    prov = fm.get("provenance")
    origin = ref = ""
    if prov is not None and not isinstance(prov, dict):
        problems.append("provenance must be a mapping with origin and ref")
    elif isinstance(prov, dict):
        origin = str(prov.get("origin", "")).strip()
        ref = str(prov.get("ref", "")).strip()
        if origin not in ORIGINS:
            problems.append(f"provenance.origin {origin!r} not one of {sorted(ORIGINS)}")
        if not ref:
            problems.append("provenance.ref is empty (a bead, memo, session, file:line or register id)")

    lin = fm.get("lineage")
    supersedes: str | None = None
    since: date | None = None
    commit: str | None = None
    if lin is not None and not isinstance(lin, dict):
        problems.append("lineage must be a mapping with supersedes, since and commit")
    elif isinstance(lin, dict):
        if "supersedes" not in lin:
            problems.append("lineage.supersedes is missing (write null when nothing was replaced)")
        raw_sup = lin.get("supersedes")
        supersedes = None if raw_sup in (None, "", "null", "~") else str(raw_sup).strip()
        raw_since = lin.get("since")
        if isinstance(raw_since, date):
            since = raw_since
        else:
            try:
                since = date.fromisoformat(str(raw_since).strip())
            except (TypeError, ValueError):
                problems.append(f"lineage.since {raw_since!r} is not an ISO date (YYYY-MM-DD)")
        raw_commit = lin.get("commit")
        if raw_commit not in (None, "", "null", "~"):
            commit = str(raw_commit).strip()
            if not _SHA_RE.match(commit):
                problems.append(f"lineage.commit {commit!r} is not a git sha")

    sources = _as_tuple(fm.get("sources"))
    triggers = _as_tuple(fm.get("triggers"))
    rules = _as_tuple(fm.get("rules"))
    if rules and etype != "strategy":
        problems.append(f"rules: is only for type 'strategy', not {etype!r}")

    rule = fm.get("rule")
    if rule is not None:
        if not isinstance(rule, dict):
            problems.append("rule must be a mapping (registered, module, entry, exit, instrument) or null")
            rule = None
        else:
            lacking = [k for k in RULE_FIELDS if rule.get(k) in (None, "")]
            if lacking:
                problems.append(f"rule block missing {', '.join(lacking)}")

    cite, cite_problems = _parse_cites(fm.get("cite"))
    problems += cite_problems
    if etype in METHOD_TYPES and not cite and not cite_problems:
        problems.append("cite is required on a method entity — a heading, 'body', or "
                        "'L<start>-<end>'; there is no default")
    body_start = end + 2
    body = "\n".join(lines[end + 1:]).strip()
    entity = Entity(
        id=ident, type=etype, status=status, owner=str(fm.get("owner", "")).strip(),
        origin=origin, ref=ref, sources=sources, supersedes=supersedes,
        since=since or date.min, commit=commit, cite=cite, triggers=triggers,
        rule=rule, rules=rules, title=str(fm.get("title", "")).strip(),
        description=str(fm.get("description", "")).strip(),
        timestamp=str(fm.get("timestamp", "")).strip(), body=body, path=path,
        lines=tuple(lines), body_start=body_start,
        extra={k: v for k, v in fm.items() if k not in _HEADER_KEYS},
    )

    # Every cite entry must resolve to a non-empty excerpt, and every entry
    # names a distinct generated row.
    seen: set[str] = set()
    for spec in cite:
        if spec.slug in seen:
            problems.append(f"cite slug {spec.slug!r} is used twice; give one entry an explicit id")
        seen.add(spec.slug)
        if entity.resolve(spec) is None:
            what = {"heading": "heading not found in the body",
                    "lines": "lines outside the body or reversed",
                    BODY_CITE: "the body is empty"}[spec.kind]
            problems.append(f"cite {spec.spec!r} does not resolve: {what}")

    return (entity if not problems else None), problems


_HEADER_KEYS = frozenset(REQUIRED_FIELDS) | {"sources", "cite", "triggers", "rule", "rules"}


# ─── the catalog ─────────────────────────────────────────────────────────────

class Canon:
    """The bundle loaded and validated once: entities by id, problems by path."""

    def __init__(self, entities: tuple[Entity, ...], problems: Mapping[Path, list[str]],
                 reserved: tuple[Path, ...]):
        self._entities = entities
        self._by_id: dict[str, Entity] = {e.id: e for e in entities}
        self.problems: dict[Path, list[str]] = dict(problems)
        self.reserved = reserved

    @classmethod
    def load(cls, dirs: tuple[Path, ...] | list[Path] = BUNDLE_DIRS, *,
             strict: bool = True, repo_root: Path | None = None) -> "Canon":
        """Load every ``*.md`` under *dirs* (recursively; reserved files skipped).

        ``strict=True`` raises :class:`CanonError` listing every file's problems
        and every catalog-level problem. ``strict=False`` returns the catalog of
        the files that validated with ``problems`` filled in for the rest.
        """
        root = repo_root if repo_root is not None else REPO_ROOT
        problems: dict[Path, list[str]] = {}
        entities: list[Entity] = []
        reserved: list[Path] = []
        for d in dirs:
            d = Path(d)
            if not d.is_dir():
                problems[d] = ["bundle directory not found"]
                continue
            for p in sorted(d.rglob("*.md")):
                if p.name in RESERVED_FILES and p.parent == d:
                    reserved.append(p)
                    continue
                entity, probs = _load(p)
                if probs:
                    problems[p] = probs
                elif entity is not None:
                    entities.append(entity)

        # catalog-level checks: duplicates, then references that must resolve
        by_id: dict[str, Entity] = {}
        for e in entities:
            if e.id in by_id:
                problems.setdefault(e.path, []).append(
                    f"duplicate id {e.id!r}: also {by_id[e.id].path}")
            else:
                by_id[e.id] = e
        for e in entities:
            for rid in e.rules:
                if rid not in by_id:
                    problems.setdefault(e.path, []).append(f"rules entry {rid!r} is not an entity id")
            if e.supersedes is not None:
                msg = _check_supersedes(e.supersedes, by_id, root)
                if msg:
                    problems.setdefault(e.path, []).append(msg)

        if strict and problems:
            raise CanonError(_format_problems(problems))
        bad = set(problems)
        kept = tuple(e for e in entities if e.path not in bad)
        return cls(kept, problems, tuple(reserved))

    # ── queries ──
    def all(self) -> list[Entity]:
        return list(self._entities)

    def method(self) -> list[Entity]:
        return [e for e in self._entities if e.is_method]

    def admissible(self) -> list[Entity]:
        """Method entities with an admitting status, wherever they live."""
        return [e for e in self._entities if e.admissible]

    def lane_sources(self, roots: tuple[Path, ...] | list[Path] = (KNOWLEDGE_DIR,)) -> list[Entity]:
        """What the audit lane may cite: admissible AND under an allowed root.

        The nine playbook records are registry entities but not lane sources
        until one is promoted (counter §6g) — ``allowed_paths`` keeps
        ``knowledge/`` only, so an exploratory short-premium record can never
        reach the classify stage's context folder.
        """
        resolved = tuple(Path(r).resolve() for r in roots)
        return [e for e in self.admissible()
                if any(e.path.resolve().is_relative_to(r) for r in resolved)]

    def by_type(self, etype: str) -> list[Entity]:
        return [e for e in self._entities if e.type == etype]

    def by_status(self, status: str) -> list[Entity]:
        return [e for e in self._entities if e.status == status]

    def by_id(self, ident: str) -> Entity:
        try:
            return self._by_id[ident]
        except KeyError:
            raise KeyError(f"no entity with id {ident!r}") from None

    def __contains__(self, ident: object) -> bool:
        return ident in self._by_id

    def __len__(self) -> int:
        return len(self._entities)

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._entities)


def _check_supersedes(spec: str, by_id: Mapping[str, Entity], root: Path) -> str | None:
    """An entity id, or ``path#heading`` where the path exists under the repo."""
    if "#" not in spec:
        if spec in by_id:
            return None
        return f"lineage.supersedes {spec!r} is neither an entity id nor 'path#heading'"
    rel, _, heading = spec.partition("#")
    target = root / rel
    if not target.is_file():
        return f"lineage.supersedes {spec!r}: {rel} does not exist under {root}"
    want = heading.strip().lstrip("#").strip()
    for line in target.read_text(encoding="utf-8").splitlines():
        m = _HEADING_RE.match(line)
        if m and m.group(2).strip() == want:
            return None
    return f"lineage.supersedes {spec!r}: heading {want!r} not found in {rel}"


def _format_problems(problems: Mapping[Path, list[str]]) -> str:
    out = [f"{len(problems)} bundle file(s) do not validate:"]
    for p in sorted(problems, key=str):
        out.append(f"  {p}:")
        out.extend(f"    - {msg}" for msg in problems[p])
    return "\n".join(out)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _parse_heading_spec(spec: str) -> tuple[int | None, str]:
    """'## Statement' -> (2, 'Statement'); 'Statement' -> (None, 'Statement')."""
    m = re.match(r"^(#+)\s*(.*)$", spec.strip())
    if m:
        return len(m.group(1)), m.group(2).strip()
    return None, spec.strip()


def _kebab(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def _parse_cite_spec(text: str, slug: str | None) -> tuple[CiteSpec | None, str | None]:
    """One cite entry -> (CiteSpec, None) or (None, problem)."""
    raw = text.strip()
    if raw == BODY_CITE:
        return CiteSpec(BODY_CITE, "", None, slug or BODY_CITE, raw), None
    m = _LINES_CITE_RE.match(raw)
    if m:
        a, b = m.group(1), m.group(2)
        return CiteSpec("lines", f"{a}-{b}", None, slug or f"l{a}-{b}", raw), None
    if raw.startswith("#"):
        level, heading = _parse_heading_spec(raw)
        if heading:
            return CiteSpec("heading", heading, level, slug or _kebab(heading), raw), None
    return None, (f"cite entry {raw!r} is not a heading ('## Text'), 'body', or "
                  f"'L<start>-<end>'")


def _parse_cites(raw) -> tuple[tuple[CiteSpec, ...], list[str]]:
    """The ``cite`` key: a list of strings or ``{cite: ..., id: ...}`` mappings."""
    if raw is None:
        return (), []
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    specs: list[CiteSpec] = []
    problems: list[str] = []
    for item in items:
        slug = None
        if isinstance(item, dict):
            slug = item.get("id")
            item = item.get("cite")
            if slug is not None and not _ID_RE.match(str(slug)):
                problems.append(f"cite id {slug!r} is not kebab-case")
                continue
            slug = str(slug) if slug is not None else None
        if not isinstance(item, str) or not item.strip():
            problems.append(f"cite entry {item!r} is not a string")
            continue
        spec, problem = _parse_cite_spec(item, slug)
        if problem:
            problems.append(problem)
        else:
            specs.append(spec)  # type: ignore[arg-type]
    return tuple(specs), problems


def _as_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value)
    return (str(value).strip(),)


# ─── command line ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Load the knowledge bundle as data and report on it.")
    ap.add_argument("--report", action="store_true",
                    help="list every file that does not validate, with its problems; exit 1 if any")
    ap.add_argument("--ids", action="store_true", help="print id, type, status per entity")
    ap.add_argument("--admissible", action="store_true",
                    help="print only the entities the audit lane may cite")
    ap.add_argument("--dir", action="append", type=Path,
                    help="bundle directory (repeatable; default knowledge/ and strader/playbooks/)")
    args = ap.parse_args(argv)

    dirs = tuple(args.dir) if args.dir else BUNDLE_DIRS
    canon = Canon.load(dirs, strict=False)
    if args.report or not (args.ids or args.admissible):
        print(f"{len(canon)} entity file(s) validate; {len(canon.problems)} do not; "
              f"{len(canon.reserved)} reserved")
        if canon.problems:
            print(_format_problems(canon.problems))
    if args.ids or args.admissible:
        rows = canon.admissible() if args.admissible else canon.all()
        for e in rows:
            print(f"{e.id}\t{e.type}\t{e.status}\t{e.path.relative_to(REPO_ROOT) if e.path.is_relative_to(REPO_ROOT) else e.path}")
    return 1 if canon.problems else 0


if __name__ == "__main__":
    sys.exit(main())
