"""Classifier schema — Phase 1 + Phase 5 (DPA + Employment).

Pydantic models for clause classification. The ``ClauseType`` enum
covers the NDA-specific values from Phase 1, the bilingual language
field from Phase 4, and the DPA + Employment clause types from
Phase 5. ``unknown`` is the safety net for low-confidence outputs.

Full enum tree + per-value rationale + example clauses:
``docs/15-clause-taxonomy-phase5.md`` (locked 2026-06-09, kanban
card ``t_8337687f``). That doc is the trunk for Phase 5 — do not
add a clause type here without amending the doc first.

The ``Clause`` model includes everything the spec calls out:
``{id, text, position, type, language, confidence}`` — the position
is a nested ``ClausePosition`` so the JSON serialisation is stable.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ClauseType(str, Enum):
    """The clause taxonomy recognised by the clausecraft classifier.

    Values are stable, lowercase, snake_case strings. The frontend
    renders a colour-coded badge per value, so adding a new value
    requires updating both the enum and the UI.

    Three phases contribute to the enum:

    - **Phase 1 (NDA, 15 values):** the original NDA taxonomy
      (``definition_confidential_info`` … ``counterparts``).
    - **Phase 4 (bilingual DE):** did **not** add enum values —
      the per-clause ``language`` field on ``Clause`` carries the
      DE vs EN distinction. The spec explicitly keeps the EN enum
      values stable for DE.
    - **Phase 5 (DPA + Employment, 20 values):** the 9 ``dpa_*``
      and 11 ``employment_*`` values added for Art 28 GDPR
      data-processing agreements and BGB / ERA employment
      contracts. See ``docs/15-clause-taxonomy-phase5.md`` for
      the full tree, rationale, and example clauses.

    ``unknown`` is a real first-class value — when the classifier
    can't reach ≥40% confidence on any other label, it returns
    ``unknown`` with ``confidence=0.0``. The spec explicitly calls
    this out as the safety net for "Sonnet can confidently
    misclassify".
    """

    # === Phase 1: NDA (15 values) ====================================
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

    # === Phase 5: DPA (9 values) =====================================
    # Art 28 GDPR data-processing agreements. All prefixed ``dpa_``
    # to keep them disjoint from NDA values and from future contract-
    # type additions (e.g. ``ma_*`` for M&A). See
    # ``docs/15-clause-taxonomy-phase5.md`` § "Phase 5 — DPA" for
    # per-value rationale + public-source URLs.
    DPA_CONTROLLER_PROCESSOR_DESIGNATION = "dpa_controller_processor_designation"
    DPA_SUBPROCESSOR_CONSENT = "dpa_subprocessor_consent"
    DPA_SUBPROCESSOR_FLOWDOWN = "dpa_subprocessor_flowdown"
    DPA_TRANSFER_MECHANISM = "dpa_transfer_mechanism"
    DPA_INTERNATIONAL_TRANSFER = "dpa_international_transfer"
    DPA_BREACH_NOTIFICATION = "dpa_breach_notification"
    DPA_DATA_SUBJECT_RIGHTS = "dpa_data_subject_rights"
    DPA_AUDIT_RIGHTS = "dpa_audit_rights"
    DPA_DATA_RETURN_DELETION = "dpa_data_return_deletion"

    # === Phase 5: Employment (11 values) =============================
    # BGB / HGB / ArbZG / BUrlG / KSchG / ERA 1996 employment
    # contracts. All prefixed ``employment_`` to keep them disjoint
    # from NDA ``non_compete`` and ``non_solicit`` (which live in a
    # confidentiality-agreement context, not an employment context).
    # See ``docs/15-clause-taxonomy-phase5.md`` § "Phase 5 —
    # Employment" for per-value rationale + public-source URLs.
    EMPLOYMENT_PROBATION = "employment_probation"
    EMPLOYMENT_NOTICE_PERIOD = "employment_notice_period"
    EMPLOYMENT_GARDEN_LEAVE = "employment_garden_leave"
    EMPLOYMENT_NON_COMPETE = "employment_non_compete"
    EMPLOYMENT_NON_SOLICITATION = "employment_non_solicitation"
    EMPLOYMENT_IP_ASSIGNMENT = "employment_ip_assignment"
    EMPLOYMENT_CONFIDENTIALITY_SURVIVAL = "employment_confidentiality_survival"
    EMPLOYMENT_REMUNERATION = "employment_remuneration"
    EMPLOYMENT_WORKING_HOURS = "employment_working_hours"
    EMPLOYMENT_LEAVE_ENTITLEMENTS = "employment_leave_entitlements"
    EMPLOYMENT_TERMINATION_FOR_CAUSE = "employment_termination_for_cause"

    UNKNOWN = "unknown"

    @classmethod
    def non_unknown_values(cls) -> list[str]:
        """All enum values except ``unknown`` — for prompt-construction.

        Returns the values in declaration order (Phase 1 NDA first,
        then Phase 5 DPA, then Phase 5 Employment, then ``unknown``
        — which is filtered). Stable order matters: the DE few-shot
        examples in ``backend/app/classify/prompt.py`` reference
        values by string, not by index.
        """
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
