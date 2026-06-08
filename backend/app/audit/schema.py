"""Audit log — Pydantic input + SQLAlchemy row.

Two models:

- :class:`AuditEvent` — what the caller constructs. Pydantic
  validation enforces the field set, the payload structure
  (``payload_json`` is a free-form dict serialised to JSONB), and
  the ``decision_type`` enum.
- :class:`AuditEventRow` — the SQLAlchemy table mapping. Used by
  the writer (:func:`app.audit.log.record_event`) to issue a
  single ``INSERT``. Never used for UPDATE or DELETE.

Why we do not model UPDATE / DELETE on the row
----------------------------------------------
The whole point of the audit log is that nothing in the
application touches the table except the writer, and the writer
only does INSERT. The SQLAlchemy mapping exposes the table
purely so :func:`app.audit.log.record_event` has a typed way to
build the INSERT statement. There is no ``update()`` or
``delete()`` method on this module — the API surface is the
:class:`AuditEvent` input plus the writer.

The DB-level enforcement is the migration's
:func:`reject_audit_mutation` PL/pgSQL trigger; that is what
actually rejects mutations if a future developer tries one.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# --- Decision types ----------------------------------------------------


class DecisionType(str, enum.Enum):
    """The set of decisions a user (or the system) can make.

    Kept narrow on purpose: the audit log is for *decisions*, not
    for telemetry. The spec calls out:

    - ``flag_accepted`` / ``flag_rejected`` — user approved or
      rejected a deviation flag.
    - ``severity_edited`` — user changed the spotter's severity
      score (e.g. 2 → 1).
    - ``context_added`` — user added a free-form rationale
      ("acceptable for our use case").
    - ``redline_generated`` — the redline drafter produced a
      proposed text.
    - ``redline_downloaded`` — the user downloaded the .docx.
    - ``graph_started`` / ``graph_resumed`` — pipeline lifecycle
      markers so the audit replay view can show "the graph
      paused at 14:31, resumed at 14:32."

    New decision types must be added here AND in the LLM prompt
    that classifies them (if any). Adding a value to this enum is
    a low-risk change — the column is just ``VARCHAR``.
    """

    FLAG_ACCEPTED = "flag_accepted"
    FLAG_REJECTED = "flag_rejected"
    SEVERITY_EDITED = "severity_edited"
    CONTEXT_ADDED = "context_added"
    REDLINE_GENERATED = "redline_generated"
    REDLINE_DOWNLOADED = "redline_downloaded"
    GRAPH_STARTED = "graph_started"
    GRAPH_RESUMED = "graph_resumed"


# --- Pydantic input ----------------------------------------------------


class AuditEvent(BaseModel):
    """The single API for writing to the audit log.

    Construct one of these and pass it to
    :func:`app.audit.log.record_event`. The writer will set
    ``decided_at`` server-side (caller-supplied timestamps are
    ignored, per the spec — defends against clock skew + replay)
    and ``decided_by`` from the configured operator id.

    Attributes
    ----------
    contract_id
        Free-form string identifying the contract being triaged.
        Typically the upload's filename, or a UUID generated at
        upload time. Indexed (the audit replay view filters by
        contract).
    clause_id
        Optional. The ``Clause.id`` the decision is about. Empty
        string for pipeline-lifecycle events (``graph_started``,
        ``graph_resumed``).
    decision_type
        One of :class:`DecisionType`. Pydantic enforces the enum.
    payload_json
        Free-form dict. The shape is ``decision_type``-specific:
        ``flag_accepted`` has ``{"flag_id": ..., "score": 1}``;
        ``redline_generated`` has ``{"proposed_text": "...",
        "rationale": "..."}``. JSONB column — indexed with a
        GIN index in the migration for the future export / replay
        use cases.
    """

    contract_id: str = Field(..., min_length=1, max_length=256)
    clause_id: str = Field(default="", max_length=64)
    decision_type: DecisionType
    payload_json: dict[str, Any] = Field(default_factory=dict)

    model_config = {"use_enum_values": True}


# --- SQLAlchemy row (read mapping only) --------------------------------


class AuditEventRow(Base):
    """The ``audit_events`` table.

    Schema (matches the spec exactly):

    - ``id`` — autoincrement BIGINT, primary key.
    - ``contract_id`` — VARCHAR(256), NOT NULL, indexed.
    - ``clause_id`` — VARCHAR(64), NOT NULL default ''.
    - ``decision_type`` — VARCHAR(64), NOT NULL, indexed.
    - ``payload_json`` — JSONB, NOT NULL default '{}'::jsonb.
      GIN-indexed so the future export / replay queries can do
      ``payload_json @> '{"flag_id": ...}'``.
    - ``decided_by`` — VARCHAR(128), NOT NULL. Set by the writer
      from the configured operator id.
    - ``decided_at`` — TIMESTAMPTZ, NOT NULL, default ``NOW()``.
      Set by the DB, not the writer, to defeat caller-supplied
      timestamps (per spec).

    No relationships, no foreign keys — the audit log is its own
    world. Even if the contract / clause tables get dropped in a
    future migration, the audit trail must survive.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[str] = mapped_column(String(256), nullable=False)
    clause_id: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("''")
    )
    decision_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    decided_by: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("audit_events_contract_id_idx", "contract_id"),
        Index("audit_events_decision_type_idx", "decision_type"),
        # GIN index for the future JSONB predicate queries
        # (``payload_json @> '{...}'``). Created in the migration
        # alongside the table; declared here as documentation for
        # ``--autogenerate`` consumers.
    )


__all__ = [
    "AuditEvent",
    "AuditEventRow",
    "DecisionType",
]
