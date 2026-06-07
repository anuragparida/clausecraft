"""Classifier — public surface."""

from app.classify.classifier import (
    classify_clause,
    classify_clauses,
)
from app.classify.schema import Clause, ClauseList, ClausePosition, ClauseType

__all__ = [
    "Clause",
    "ClauseList",
    "ClausePosition",
    "ClauseType",
    "classify_clause",
    "classify_clauses",
]
