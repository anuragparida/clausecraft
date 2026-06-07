"""Classifier schema — Phase 1.

Pydantic models for clause classification. The ``ClauseType`` enum
covers the NDA-specific values listed in the Phase 1 spec; ``unknown``
is the safety net for low-confidence outputs.

The ``Clause`` model includes everything the spec calls out:
``{id, text, position, type, language, confidence}`` — the position
is a nested ``ClausePosition`` so the JSON serialisation is stable.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ClauseType(str, Enum):
    """The NDA clause taxonomy recognised by the Phase 1 classifier.

    Values are stable, lowercase, snake_case strings. The frontend
    renders a colour-coded badge per value, so adding a new value
    requires updating both the enum and the UI.

    ``unknown`` is a real first-class value — when the classifier
    can't reach ≥40% confidence on any other label, it returns
    ``unknown`` with ``confidence=0.0``. The spec explicitly calls
    this out as the safety net for "Sonnet can confidently
    misclassify".
    """

    DEFINITION_CONFIDENTIAL_INFO = "definition_confidential_info"
    TERM = "term"
    GOVERNING_LAW = "governing_law"
    INJUNCTIVE_RELIEF = "injunctive_relief"
    RESIDUAL_KNOWLEDGE = "residual_knowledge"
    RETURN_OF_MATERIALS = "return_of_materials"
    NON_SOLICIT = "non_solicit"
    NON_COMPETE = "non_compete"
    INDEMNITY = "indemnity"
    LIMITATION_OF_LIABILITY = "limitation_of_liability"
    ASSIGNMENT = "assignment"
    ENTIRE_AGREEMENT = "entire_agreement"
    SEVERABILITY = "severability"
    NOTICES = "notices"
    COUNTERPARTS = "counterparts"
    UNKNOWN = "unknown"

    @classmethod
    def non_unknown_values(cls) -> list[str]:
        """All enum values except ``unknown`` — for prompt-construction."""
        return [v.value for v in cls if v != cls.UNKNOWN]


class ClausePosition(BaseModel):
    """Position metadata for a single clause in its source document.

    ``section`` is the section identifier from the chunker (e.g.
    ``"1.2"``, ``"ALL_CAPS:CONFIDENTIALITY"``) or empty string when
    the document had no detectable headings. ``paragraph_index`` is
    a list (not a single int) because one clause can span multiple
    paragraphs of the source — the frontend renders a range.
    """

    section: str = ""
    section_title: str = ""
    paragraph_index: list[int] = Field(default_factory=list)


class Clause(BaseModel):
    """A single classified clause.

    The ``id`` is a stable document-local identifier assigned by the
    chunker (``c1``, ``c2``, ...). Re-classifying the same input
    preserves the id so the UI can match rows.
    """

    id: str
    text: str
    position: ClausePosition
    type: ClauseType
    language: str = "en"  # Phase 1 is EN only; the field exists for Phase 4.
    confidence: float = Field(ge=0.0, le=1.0)


class ClauseList(BaseModel):
    """Wrapper for the JSON the classifier emits.

    The Pydantic-validated LLM output is parsed into this shape, so
    the ``Clause.type`` enum and ``Clause.confidence`` range are
    enforced at deserialisation time.
    """

    clauses: list[Clause]

    def model_dump_jsonable(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict (Pydantic v2 dict mode).

        Used by the FastAPI response model.
        """
        return self.model_dump(mode="json")
