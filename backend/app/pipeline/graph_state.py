"""LangGraph state shape for the Phase 3 HITL pipeline.

The state is a TypedDict (LangGraph's preferred shape — keeps
serialisation trivial and works with the Postgres checkpoint
saver out of the box). Every field is ``total=False`` so the
graph can build it up incrementally across nodes.

State lifecycle
---------------

1. **Start** — caller invokes the graph with ``contract_id``,
   ``filename``, ``file_bytes``, ``content_type``. The
   ``ingest`` node fills in ``clauses`` from
   :func:`app.pipeline.stage1_ingest.run_stage1`.

2. **Spot** — :func:`app.pipeline.stage3_spot.run_stage3`
   fills in ``flags`` (one per clause). The graph pauses here
   in the demo flow, but in this Phase 3 build we don't pause
   between spot and interrupt — the interrupt is dedicated to
   the human review step.

3. **Interrupt** — :func:`langgraph.types.interrupt` surfaces
   the flag table to the caller. The graph state holds
   ``flags`` + ``interrupt_payload`` (the data the UI needs to
   render the table). The graph blocks here until the caller
   resumes with a :class:`Command` whose ``resume`` value is
   the per-flag decision batch.

4. **Redline** — the drafter runs against every accepted flag.
   Results land in ``redlines`` (one per accepted flag, or a
   ``RedlineConflict`` marker when both attempts failed).
   Rejected / edited flags get audit rows but no redline.

5. **Output** — the docx builder assembles the contract with
   tracked changes. Output lives in ``output_docx_bytes`` (the
   in-memory .docx; the FastAPI layer streams it from the
   graph state on download). For Phase 3 Build 3, this node is
   a no-op that returns an empty byte string when the
   ``output.docx`` module is not yet present (Build 2 is a
   sibling card).

6. **Finalize** — END.

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

from typing import Any, Optional, TypedDict


class PipelineState(TypedDict, total=False):
    """Phase 3 HITL pipeline state — the single source of truth for the graph.

    Fields are written by the corresponding node. The
    ``interrupt_payload`` field is what the UI reads on pause
    (and what the resume call's batch of decisions is
    validated against).

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
        one batch").
    redlines
        Filled in by the ``redline`` node. Dict ``{clause_id:
        proposal_dict}`` for accepted flags. Rejected / edited
        flags do NOT get a redline.
    output_docx_bytes
        Filled in by the ``output`` node. The .docx byte
        stream. Empty string when the docx builder is not
        available (Build 2 sibling card).
    audit_event_count
        Counter — number of audit events written so far. The
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
    redlines: dict[str, dict[str, Any]]
    output_docx_bytes: bytes
    audit_event_count: int
    error: Optional[str]


__all__ = ["PipelineState"]
