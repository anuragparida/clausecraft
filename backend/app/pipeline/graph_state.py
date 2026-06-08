"""LangGraph state shape for the Phase 3 HITL pipeline.

The state is a TypedDict (LangGraph's preferred shape - keeps
serialisation trivial and works with the Postgres checkpoint
saver out of the box). Every field is ``total=False`` so the
graph can build it up incrementally across nodes.

State lifecycle
---------------

1. **Start** - caller invokes the graph with ``contract_id``,
   ``filename``, ``file_bytes``, ``content_type``. The
   ``ingest`` node fills in ``clauses`` from
   :func:`app.pipeline.stage1_ingest.run_stage1`.

2. **Spot** - :func:`app.pipeline.stage3_spot.run_stage3`
   fills in ``flags`` (one per clause). The graph pauses here
   in the demo flow, but in this Phase 3 build we don't pause
   between spot and interrupt - the interrupt is dedicated to
   the human review step.

3. **Interrupt** - :func:`langgraph.types.interrupt` surfaces
   the flag table to the caller. The graph state holds
   ``flags`` + ``interrupt_payload`` (the data the UI needs to
   render the table). The graph blocks here until the caller
   resumes with a :class:`Command` whose ``resume`` value is
   the per-flag decision batch.

4. **Redline** - the drafter runs against every accepted flag.
   Results land in ``redlines`` (one per accepted flag, or a
   ``RedlineConflict`` marker when both attempts failed).
   Rejected / edited flags get audit rows but no redline.

5. **Output** - the docx builder assembles the contract with
   tracked changes. Output lives in ``output_docx_bytes`` (the
   in-memory .docx; the FastAPI layer streams it from the
   graph state on download). For Phase 3 Build 3, this node is
   a no-op that returns an empty byte string when the
   ``output.docx`` module is not yet present (Build 2 is a
   sibling card).

6. **Finalize** - END.

Concurrency note
----------------
The state is JSON-serialised on every checkpoint. The file
bytes are base64-encoded by the ``StateGraph`` machinery; for a
multi-megabyte PDF this is wasteful but acceptable for Phase 3
(NDA contracts are typically <200KB; we have headroom). If a
future build needs to handle larger contracts, the file bytes
can be moved out-of-band (S3, filesystem) with only a
``file_uri`` string in the state.

The ``flags`` and ``redlines`` lists are Pydantic models at
runtime but serialise as plain dicts. The Postgres saver
json-serialises them automatically via its default serde.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.audit.schema import AuditEvent


# --- Typed state models (Phase 3 Build 3 re-decomposition) ---------------
#
# These are the Pydantic models the new ``hitl_review_node`` writes into
# state. The card spec (``t_0671d337``) calls for a typed-state layer in
# addition to the existing dict-keyed fields:
#
# - ``flag_decisions: dict[flag_id -> FlagDecision]`` (was: ``decisions:
#   dict[clause_id -> dict]``)
# - ``severity_overrides: dict[flag_id -> int]`` (new)
# - ``redline_proposals: dict[flag_id -> RedlineProposal]`` (was: ``redlines:
#   dict[clause_id -> dict]``)
# - ``audit_log_writes: list[AuditLogEntry]`` - the queued writes the graph
#   accumulates; the actual ``INSERT`` happens at the END of the run
#   (or at a checkpoint commit) so a mid-graph crash doesn't leave
#   half-written audit state.
#
# The ``flag_id`` keying is finer-grained than the existing ``clause_id``
# keying: in the current implementation the *clause* is the unit (one
# flag per clause), so in practice ``flag_id == clause_id``. The
# separation is forward-compat: a future build may emit multiple flags
# per clause (e.g. one per deviation type) and the typed state is ready
# for that without a refactor.
#
# Why Pydantic models in a TypedDict state
# ----------------------------------------
# LangGraph's StateGraph serialises state to JSON for the Postgres
# checkpoint. Pydantic v2's ``model_dump(mode="json")`` roundtrips
# cleanly; the runtime treats the model as a dict at the boundary
# (the saver's default serde). The Pydantic validation catches
# malformed decisions at resume time (a malicious or buggy caller
# could send any JSON; the schema is the trust boundary).


class FlagAction(str, Enum):
    """The four per-flag actions the HITL UI can submit.

    The values are persisted verbatim in the audit log's
    ``decision_type`` (the spec's audit log table records every
    action as its own row). The UI sends the string form
    (``"approved"`` / ``"rejected"`` / ``"edited"`` /
    ``"context_added"``); the Pydantic enum coerces and rejects
    anything else.

    Why four actions, not two
    -------------------------
    The Phase 2 UI shipped Approve / Reject (two buttons). The
    Phase 3 HITL spec (card body) calls for four: Approve,
    Reject, Edit (severity override), Add-context. The extra
    two are audit-worthy: a severity override IS a decision
    (the spotter's score is wrong) and an added context IS a
    decision (the user is saying "I know, accept it"). A
    two-action model would lose the audit signal.
    """

    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    CONTEXT_ADDED = "context_added"


class FlagDecision(BaseModel):
    """One user's decision for one flag.

    The contract between the UI (card 6) and the drafter (card 2).
    The HITL node validates and persists one of these per flag_id
    the user touched. The fields are the same shape the UI
    submits; the Pydantic model adds a Pydantic-typed
    ``flag_id`` and a ``submitted_at`` timestamp the API layer
    stamps (so a UI double-click is distinguishable in the
    audit log).

    Attributes
    ----------
    flag_id
        Stable per-flag identifier. In Phase 3 a flag is keyed
        by its clause_id (one flag per clause); the field is
        named ``flag_id`` (not ``clause_id``) per the card spec.
    action
        One of :class:`FlagAction`. Pydantic enforces the enum.
    severity_override
        Optional 0-3 severity override. Required when
        ``action == EDITED``; ignored otherwise (the audit log
        still records it as a no-op if it's set on a non-EDIT
        action - the spec wants the field present so the
        export view can render "approved at severity 2" without
        a join).
    extra_context
        Optional free-form note. Common examples: "acceptable
        for our use case if limited to 5 years" or
        "counterparty's standard form, non-negotiable".
    submitted_at
        The wall-clock the UI recorded the action. Stamped
        server-side at the resume call (not client-supplied)
        to defeat clock skew. ISO-8601 string.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    flag_id: str = Field(..., min_length=1, max_length=64)
    action: FlagAction
    severity_override: Optional[int] = Field(default=None, ge=0, le=3)
    extra_context: str = Field(default="", max_length=2_000)
    submitted_at: str = Field(..., min_length=1, max_length=64)


class AuditLogEntry(BaseModel):
    """A queued audit log write.

    The graph accumulates one of these per state transition
    that changes a decision (per the spec - "The audit log
    writer is called at EVERY state transition that changes
    a decision"). The actual ``INSERT`` to ``audit_events``
    happens at the end of the graph run (or at a checkpoint
    commit) - never mid-graph. This is the spec's "audit log
    writes are queued in state, not directly called" hard
    rule: a mid-graph crash doesn't leave half-written audit
    state.

    The model wraps :class:`app.audit.schema.AuditEvent` (the
    Pydantic shape the writer accepts) plus a ``committed``
    flag the runner flips after the INSERT. Tests assert the
    flag is ``False`` mid-graph and ``True`` after
    :func:`flush_audit_log` runs.
    """

    model_config = ConfigDict(extra="forbid")

    event: AuditEvent
    committed: bool = False
    flushed_at: Optional[str] = None


class PipelineState(TypedDict, total=False):
    """Phase 3 HITL pipeline state - the single source of truth for the graph.

    Fields are written by the corresponding node. The
    ``interrupt_payload`` field is what the UI reads on pause
    (and what the resume call's batch of decisions is
    validated against).

    The Build 3 re-decomposition (card ``t_0671d337``) adds
    four typed-state fields alongside the original dict-keyed
    ones:

    - ``flag_decisions`` - ``dict[flag_id -> FlagDecision]``.
      Written by :func:`hitl_review_node` on resume. The
      canonical "what did the user decide" store. The original
      ``decisions`` field is kept for backward compat with the
      existing node bodies (the existing :func:`apply_decisions_node`
      and :func:`draft_redlines_node` read from ``decisions``;
      the new :func:`hitl_review_node` populates both shapes
      from a single Pydantic-validated source).
    - ``severity_overrides`` - ``dict[flag_id -> int]`` (0-3).
      Written by :func:`hitl_review_node` for every ``EDITED``
      decision. The drafter uses this to replace the spotter's
      score in the :class:`RedlineProposal` rationale.
    - ``redline_proposals`` - ``dict[flag_id -> RedlineProposal]``.
      Written by :func:`stage5_redline.run_stage5` for every
      approved flag whose drafter returned a proposal
      (skipping the ``RedlineConflict`` path; the conflict
      goes to the audit log instead). The original ``redlines``
      field is kept for backward compat.
    - ``audit_log_writes`` - ``list[AuditLogEntry]``. The
      accumulated queue of audit events. The actual
      ``INSERT`` to ``audit_events`` happens in
      :func:`flush_audit_log` at the end of the run (or at a
      checkpoint commit) - never mid-graph. The spec's "no
      half-written audit state" hard rule.

    Attributes
    ----------
    contract_id
        The thread id. Generated at upload time, used as the
        LangGraph checkpoint key. Stable across pause / resume.
    filename
        Echoed for the API response / audit log. Stable across
        pause / resume.
    content_type
        The upload's MIME type. Used by the ingest node to
        dispatch on the right extractor.
    file_bytes
        The raw upload bytes. ``StateGraph`` base64-encodes
        them on checkpoint. See the "Concurrency note" in the
        module docstring for the multi-MB caveat.
    clauses
        Filled in by the ``ingest`` node. List of Pydantic
        ``Clause`` dicts (serialised form).
    flags
        Filled in by the ``spot`` node. List of Pydantic
        ``DeviationFlag`` dicts (serialised form). One per
        clause, in the same order.
    interrupt_payload
        Filled in by the ``interrupt_hitl`` node right before
        the pause. Dict with the data the UI needs to render
        the deviation table (``{"flags": [...], "contract_id":
        ...}``). Echoed back to the caller on resume.
    decisions
        Filled in by the resume call. Dict ``{clause_id:
        decision}`` where ``decision`` is one of ``"accepted"``,
        ``"rejected"``, ``"edited"``, ``"context_added"``, plus
        optional ``{"severity": int, "extra_context": str}``.
        The full set of decisions lands in one batch (spec
        line: "The HITL node returns ALL flags' decisions in
        one batch"). Backward-compat with the existing
        :func:`apply_decisions_node` and
        :func:`draft_redlines_node` readers.
    flag_decisions
        Typed equivalent of ``decisions``. ``dict[flag_id ->
        FlagDecision]``. Pydantic-validated. The canonical
        store going forward.
    severity_overrides
        ``dict[flag_id -> int]`` (0-3). Only ``EDITED`` actions
        populate this.
    redlines
        Filled in by the ``redline`` node. Dict ``{clause_id:
        proposal_dict}`` for accepted flags. Rejected / edited
        flags do NOT get a redline.
    redline_proposals
        Typed equivalent of ``redlines``. ``dict[flag_id ->
        RedlineProposal]``. Pydantic-validated.
    audit_log_writes
        The queued writes. ``list[AuditLogEntry]``. The
        ``commit`` happens at END of the run.
    output_docx_bytes
        Filled in by the ``output`` node. The .docx byte
        stream. Empty string when the docx builder is not
        available (Build 2 sibling card).
    audit_event_count
        Counter - number of audit events written so far. The
        finalize node reads this to assert "the graph wrote at
        least one audit event per state transition" (the
        acceptance criterion).
    error
        Filled in by any node that catches an exception. The
        graph still reaches END so the checkpoint is durable;
        the API layer renders the error to the user.
    """

    contract_id: str
    filename: str
    content_type: str
    file_bytes: bytes
    clauses: list[dict[str, Any]]
    flags: list[dict[str, Any]]
    interrupt_payload: dict[str, Any]
    decisions: dict[str, dict[str, Any]]
    flag_decisions: dict[str, dict[str, Any]]
    severity_overrides: dict[str, int]
    redlines: dict[str, dict[str, Any]]
    redline_proposals: dict[str, dict[str, Any]]
    audit_log_writes: list[dict[str, Any]]
    output_docx_bytes: bytes
    audit_event_count: int
    error: Optional[str]


__all__ = [
    "AuditLogEntry",
    "FlagAction",
    "FlagDecision",
    "PipelineState",
]
