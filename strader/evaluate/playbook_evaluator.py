"""The playbook fit evaluator: score the catalog against a declared day-context.

Given a :class:`DayContext` (the condition tags true for the day), the evaluator
scores every ``worthy``/``active`` playbook with transparent arithmetic —

    score = Σ weight(favored tag present) − Σ weight(avoid tag present)

— ranks them (highest first, ties broken deterministically by code), and can
emit the top pick's indicators + entry/management checklists, instrumented for
the session. Every score reports *why* it scored (``matched_favored`` /
``matched_avoid``) so the recommendation is auditable, never a black box.

Scope (per co-wh19 §2): this does not classify the day (producing a DayContext is
a deferred brainstorm) and does not bind to live market data — it consumes a
*declared* context and recommends. Steve decides and acts.
"""

from __future__ import annotations

from dataclasses import dataclass

from strader.entities.playbook import (
    Playbook,
    PlaybookCatalog,
    PlaybookError,
    Vocabulary,
)


@dataclass(frozen=True)
class DayContext:
    """The set of day-context condition tags currently true.

    How this is produced is the deferred day-type classifier; here it is a
    declared input. Tags are validated against the vocabulary by the evaluator.
    """

    tags: frozenset[str]

    @classmethod
    def of(cls, *tags: str) -> "DayContext":
        return cls(frozenset(tags))


@dataclass(frozen=True)
class PlaybookScore:
    """One playbook's fit against a day-context, with the drivers made explicit."""

    playbook: Playbook
    score: float
    matched_favored: tuple[str, ...]
    matched_avoid: tuple[str, ...]


class PlaybookEvaluator:
    """Scores and ranks the worthy playbooks in a catalog against a day-context."""

    def __init__(self, catalog: PlaybookCatalog, vocab: Vocabulary | None = None):
        self.catalog = catalog
        self.vocab = vocab if vocab is not None else catalog.vocab

    # ── scoring ──────────────────────────────────────────────────────────────

    def _validate(self, ctx: DayContext) -> None:
        unknown = sorted(ctx.tags - self.vocab.day_context)
        if unknown:
            raise PlaybookError(
                f"unknown day-context tag(s) {unknown}; "
                f"legal tags are defined in the conditions vocabulary"
            )

    def _score(self, playbook: Playbook, ctx: DayContext) -> PlaybookScore:
        matched_favored = tuple(t for t in playbook.favored_conditions if t in ctx.tags)
        matched_avoid = tuple(t for t in playbook.avoid_conditions if t in ctx.tags)
        score = sum(self.vocab.weight(t) for t in matched_favored) - sum(
            self.vocab.weight(t) for t in matched_avoid
        )
        return PlaybookScore(playbook, score, matched_favored, matched_avoid)

    def rank(self, ctx: DayContext) -> list[PlaybookScore]:
        """All worthy playbooks scored, highest first; ties broken by code."""
        self._validate(ctx)
        scores = [self._score(pb, ctx) for pb in self.catalog.worthy()]
        # Deterministic: primary key score descending, tie-break code ascending.
        scores.sort(key=lambda s: (-s.score, s.playbook.code))
        return scores

    def surface(self, ctx: DayContext) -> PlaybookScore | None:
        """The top-ranked playbook, or None if the catalog has none worthy."""
        ranked = self.rank(ctx)
        return ranked[0] if ranked else None

    # ── instrumenting the pick ───────────────────────────────────────────────

    def instrument(self, score: PlaybookScore) -> dict:
        """The pick's indicators + checklists, ready to drive the session."""
        pb = score.playbook
        return {
            "code": pb.code,
            "name": pb.name,
            "score": score.score,
            "matched_favored": list(score.matched_favored),
            "matched_avoid": list(score.matched_avoid),
            "indicators": list(pb.indicators),
            "entry_checklist": _extract_checklist(pb.body, "Entry checklist"),
            "management_checklist": _extract_checklist(pb.body, "Management checklist"),
        }


def _extract_checklist(body: str, heading: str) -> list[str]:
    """Pull the ``- [ ]`` items under a ``## <heading>`` section of the body."""
    items: list[str] = []
    capturing = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            capturing = stripped[3:].strip().lower() == heading.lower()
            continue
        if capturing and stripped.startswith("- ["):
            # drop the leading "- [ ] " / "- [x] " checkbox marker
            _, _, text = stripped.partition("]")
            items.append(text.strip())
    return items
