"""Strader strategy evaluators.

The fit evaluator that consumes the playbook catalog. Separate from the entities
(``strader.entities``) by design: the entities represent and validate strategies;
the evaluator scores them against a day-context and emits an instrumented pick.
"""

from strader.evaluate.playbook_evaluator import (
    DayContext,
    PlaybookEvaluator,
    PlaybookScore,
)
from strader.evaluate.day_classifier import (
    Classification,
    ClassifierConfig,
    DayTypeClassifier,
    MarketPrimitives,
    SubjectiveRead,
)

__all__ = [
    "DayContext",
    "PlaybookEvaluator",
    "PlaybookScore",
    "Classification",
    "ClassifierConfig",
    "DayTypeClassifier",
    "MarketPrimitives",
    "SubjectiveRead",
]
