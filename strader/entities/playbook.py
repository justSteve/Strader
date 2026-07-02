"""Playbook entity + catalog — the InvestiTrade strategies as first-class data.

A ``Playbook`` is one curated trading strategy, framed structurally the way a
Zgent is a first-class entity: queryable YAML frontmatter (the machine-readable
surface) plus a standardized markdown body (the human-oriented narrative). The
set of playbooks is a curated, version-controlled catalog under
``strader/playbooks/``; ``PlaybookCatalog`` enumerates and filters it.

Design of record: ``docs/superpowers/specs/2026-06-26-playbook-entity-design.md``
(co-wh19), implemented under st-c71. Placement was corrected from the spec's
``market/entities/`` to the ``strader`` package: the spec predated the strader2
fold-in, after which strategy entities live beside ``singleton.py``. This module
holds *form*; the ``.md`` files hold *content*; the fit evaluator
(``strader.evaluate``) is a separate unit that consumes this catalog.

It does not automate trades. It represents, validates, and organizes strategies;
Steve sets each playbook's ``status`` by hand
(``candidate -> worthy -> active -> retired``) — no backtest gates worthiness in
v1, and a ``retired`` playbook is benched but kept, never deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator, Mapping

from strader._yaml import load_file as _load_yaml_file
from strader._yaml import safe_load as _safe_load

# strader/entities/playbook.py -> strader/ -> strader/playbooks/
PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent / "playbooks"
CONDITIONS_PATH = PLAYBOOKS_DIR / "conditions.yaml"

VALID_STATUS = ("candidate", "worthy", "active", "retired")
WORTHY_STATUS = frozenset({"worthy", "active"})  # eligible for the evaluator
DEFAULT_WEIGHT = 1.0
_WEIGHT_WORDS = {"high": 2.0, "medium": 1.5, "low": 0.5}

REQUIRED_FIELDS = (
    "code",
    "name",
    "status",
    "source",
    "instruments",
    "favored_conditions",
    "avoid_conditions",
    "indicators",
    "rationale",
    "adopted",
    "updated",
)


class PlaybookError(Exception):
    """Raised when a playbook file or the conditions vocabulary is malformed.

    The message always names the offending path so a fresh agent can jump
    straight to the file and fix it.
    """


# ─── controlled vocabulary ───────────────────────────────────────────────────

@dataclass(frozen=True)
class Vocabulary:
    """The loaded ``conditions.yaml``: the set of legal tags plus promote weights."""

    day_context: frozenset[str]
    entry_confirmation: frozenset[str]
    weights: Mapping[str, float]  # day_context tag -> promote weight (default 1.0)

    def weight(self, tag: str) -> float:
        return self.weights.get(tag, DEFAULT_WEIGHT)

    @classmethod
    def load(cls, path: str | Path = CONDITIONS_PATH) -> "Vocabulary":
        path = Path(path)
        try:
            data = _load_yaml_file(path)
        except FileNotFoundError as exc:
            raise PlaybookError(f"conditions vocabulary not found: {path}") from exc
        tiers = data.get("tiers") if isinstance(data, dict) else None
        if not isinstance(tiers, dict):
            raise PlaybookError(f"{path}: expected a top-level 'tiers' mapping")
        day_context = tiers.get("day_context") or {}
        entry_confirmation = tiers.get("entry_confirmation") or {}
        if not isinstance(day_context, dict) or not isinstance(entry_confirmation, dict):
            raise PlaybookError(
                f"{path}: 'day_context' and 'entry_confirmation' must be mappings"
            )
        weights: dict[str, float] = {}
        for tag, spec in day_context.items():
            raw = spec.get("weight") if isinstance(spec, dict) else None
            if raw is None:
                continue
            weights[tag] = (
                _WEIGHT_WORDS.get(raw, DEFAULT_WEIGHT)
                if isinstance(raw, str)
                else float(raw)
            )
        return cls(frozenset(day_context), frozenset(entry_confirmation), weights)


# ─── the entity ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Playbook:
    """One curated strategy: queryable frontmatter fields + the markdown body."""

    code: str
    name: str
    status: str
    source: str
    instruments: tuple[str, ...]
    favored_conditions: tuple[str, ...]
    avoid_conditions: tuple[str, ...]
    indicators: tuple[str, ...]
    rationale: str
    adopted: date
    updated: date
    body: str
    path: Path | None = None

    @property
    def is_worthy(self) -> bool:
        """Eligible for the evaluator (curated as sound or actively traded)."""
        return self.status in WORTHY_STATUS

    @classmethod
    def load(cls, path: str | Path, vocab: Vocabulary) -> "Playbook":
        """Parse a playbook file and validate it against *vocab*.

        Raises :class:`PlaybookError` (naming the file) on: a malformed or
        missing frontmatter fence, any missing required field, an unknown
        ``status``, a non-ISO date, an unknown day-context tag, or a tag that
        appears in both ``favored`` and ``avoid``. All problems for a file are
        reported together.
        """
        path = Path(path)
        try:
            text = path.read_text()
        except FileNotFoundError as exc:
            raise PlaybookError(f"playbook file not found: {path}") from exc

        frontmatter, body = _split_frontmatter(text, path)

        missing = [k for k in REQUIRED_FIELDS if frontmatter.get(k) in (None, "")]
        if missing:
            raise PlaybookError(
                f"{path}: missing frontmatter field(s): {', '.join(missing)}"
            )

        problems: list[str] = []
        status = str(frontmatter["status"]).strip()
        if status not in VALID_STATUS:
            problems.append(f"status {status!r} not one of {VALID_STATUS}")

        favored = _as_tuple(frontmatter["favored_conditions"])
        avoid = _as_tuple(frontmatter["avoid_conditions"])
        unknown = sorted({t for t in (*favored, *avoid) if t not in vocab.day_context})
        if unknown:
            problems.append(
                f"unknown day-context tag(s) {unknown}; "
                f"legal tags are defined in {CONDITIONS_PATH.name}"
            )
        overlap = sorted(set(favored) & set(avoid))
        if overlap:
            problems.append(f"tag(s) in both favored and avoid: {overlap}")

        if problems:
            raise PlaybookError(f"{path}: " + "; ".join(problems))

        return cls(
            code=str(frontmatter["code"]).strip(),
            name=str(frontmatter["name"]).strip(),
            status=status,
            source=str(frontmatter["source"]).strip(),
            instruments=_as_tuple(frontmatter["instruments"]),
            favored_conditions=favored,
            avoid_conditions=avoid,
            indicators=_as_tuple(frontmatter["indicators"]),
            rationale=str(frontmatter["rationale"]).strip(),
            adopted=_as_date(frontmatter["adopted"], "adopted", path),
            updated=_as_date(frontmatter["updated"], "updated", path),
            body=body,
            path=path,
        )


# ─── the catalog ─────────────────────────────────────────────────────────────

class PlaybookCatalog:
    """The set of playbook files under a directory, loaded and validated once."""

    def __init__(self, directory: str | Path = PLAYBOOKS_DIR, vocab: Vocabulary | None = None):
        self.directory = Path(directory)
        self.vocab = vocab if vocab is not None else Vocabulary.load()
        self._playbooks: tuple[Playbook, ...] = tuple(
            Playbook.load(p, self.vocab)
            for p in sorted(self.directory.glob("*.md"))
        )
        self._by_code: dict[str, Playbook] = {}
        for pb in self._playbooks:
            if pb.code in self._by_code:
                raise PlaybookError(
                    f"duplicate playbook code {pb.code!r}: "
                    f"{self._by_code[pb.code].path} and {pb.path}"
                )
            self._by_code[pb.code] = pb

    def all(self) -> list[Playbook]:
        return list(self._playbooks)

    def worthy(self) -> list[Playbook]:
        """Only ``worthy``/``active`` playbooks — the set the evaluator scores."""
        return [pb for pb in self._playbooks if pb.is_worthy]

    def by_instrument(self, symbol: str) -> list[Playbook]:
        return [pb for pb in self._playbooks if symbol in pb.instruments]

    def by_code(self, code: str) -> Playbook:
        try:
            return self._by_code[code]
        except KeyError:
            raise KeyError(f"no playbook with code {code!r}") from None

    def __len__(self) -> int:
        return len(self._playbooks)

    def __iter__(self) -> Iterator[Playbook]:
        return iter(self._playbooks)


# ─── frontmatter parsing helpers ─────────────────────────────────────────────

def _split_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PlaybookError(f"{path}: file must open with a '---' frontmatter fence")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise PlaybookError(f"{path}: unterminated frontmatter (no closing '---')")
    frontmatter = _safe_load("\n".join(lines[1:end]))
    if not isinstance(frontmatter, dict):
        raise PlaybookError(f"{path}: frontmatter did not parse to a mapping")
    body = "\n".join(lines[end + 1:]).strip()
    return frontmatter, body


def _as_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value)
    return (str(value).strip(),)


def _as_date(value, field: str, path: Path) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise PlaybookError(
            f"{path}: {field} {value!r} is not an ISO date (YYYY-MM-DD)"
        ) from exc
