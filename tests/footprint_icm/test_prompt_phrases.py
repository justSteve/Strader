"""No prompt in the lane may carry the withdrawn sentences. [st-h0xx]

The classify prompt is lifted from the runbook; a paste that brought the
2026-08-25 phrasing (or the uncited sentence that replaced it) back in would
seed the very claim the lane exists to catch. The planted sentences live in
``excerpts.PLANTED`` and in the checker's tests, never in a prompt or a rubric.
"""
from pathlib import Path

import excerpts

LANE = Path(__file__).resolve().parents[2] / "footprint-icm"
PROMPT_FILES = [p for p in LANE.rglob("*.md")
                if p.name in ("prompt.md", "rubric.md") or "fixtures" in p.parts]


def test_no_prompt_or_rubric_carries_a_planted_sentence():
    offenders = []
    for p in PROMPT_FILES:
        if "fixtures" in p.parts:
            continue           # the planted fixture is meant to carry them
        text = p.read_text(encoding="utf-8").lower()
        for s in excerpts.PLANTED:
            if s.lower() in text or "fade/skip" in text:
                offenders.append((str(p.relative_to(LANE)), s))
    assert offenders == []


def test_the_planted_sentences_are_the_two_the_plan_names():
    assert excerpts.PLANTED == (
        "fade/skip context per the playbook",
        "regime changes a setup's management and expectancy, not its validity",
    )
