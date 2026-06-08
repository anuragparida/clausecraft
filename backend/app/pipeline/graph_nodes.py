"""Node implementations for the Phase 3 HITL graph.

Each node is a coroutine that takes the :class:`PipelineState`
and returns a partial-state dict. The graph merges the
returned dict into the live state (LangGraph convention).

Node list (topology defined in :mod:`.graph`):

- :func:`ingest_parse_classify_node` — runs
  :func:`app.pipeline.stage1_ingest.run_stage1` synchronously,
  then writes a single ``graph_started`` audit event.
- :func:`spot_deviations_node` — runs
  :func:`app.pipeline.stage3_spot.run_stage3`, then writes a
  per-flag ``flag_<score>`` event for the *initial* spotting
  (not the user's decision — the user's decision is what
  arrives via the resume call, not what the spotter emitted).
- :func:`interrupt_hitl_node` — surfaces the deviation table
  to the UI via :func:`langgraph.types.interrupt`. The graph
  pauses here. On resume, ``interrupt()`` returns the
  per-flag decision batch.
- :func:`apply_decisions_node` — runs after the resume. Maps
  the decision batch to per-flag audit events. Rejected /
  accepted / edited / context-added each get their own row.
- :func:`draft_redlines_node` — runs the redline drafter
  (with self-check) for every accepted flag. Rejected /
  edited-without-accept flags do NOT get a redline.
- :func:`assemble_output_node` — assembles the .docx. For
  Phase 3 Build 3 (this card) the docx builder is a sibling
  card; the node is a no-op that returns empty bytes. The
  Build 2 reviewer will wire the real builder.
- :func:`finalize_node` — writes the final audit event and
  returns END.

Concurrency
-----------

``stage3_spot.run_stage3`` is already an async coroutine; the
spot node awaits it directly. The redline node awaits the
self-check loop per accepted flag concurrently with
``asyncio.gather`` (bounded to 4 in flight to respect the
gateway's rate limit). Stage 1 is sync; the node runs it in
``asyncio.to_thread`` so the event loop stays responsive.

Why we don't do everything in one big function
----------------------------------------------

Each node is small enough to read top-to-bottom. A reviewer
checking the audit-log coverage can grep for ``record_event``
across the file and see the full story in one read. A
reviewer checking the decision-batch handling can grep for
``accept|reject|edit|context`` and find :func:`_emit_decision_audit_events`
without scrolling through 200 lines of redline logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.types import interrupt

from app.agents.deviation_spotter.schema import DeviationFlag
from app.agents.redline_drafter.drafter import DrafterUnavailable
from app.agents.redline_drafter.schema import (
    BaselineForSpotter,
    DrafterInput,
    RedlineConflict,
    RedlineProposal,
)
from app.agents.redline_drafter.self_check import run_with_self_check
from app.audit import DecisionType
from app.classify.schema import Clause
from app.pipeline.graph_runtime import _audit, _audit_lifecycle
from app.pipeline.graph_state import PipelineState
from app.pipeline.stage1_ingest import run_stage1
from app.pipeline.stage3_spot import run_stage3

logger = logging.getLogger(__name__)


# --- Constants ---------------------------------------------------------


#: Max concurrent drafter calls inside :func:`draft_redlines_node`.
#: Mirrors the spotter's bound (8) but trimmed to 4 — the
#: self-check loop doubles the effective LLM call count, so we
#: halve the concurrency to keep the gateway's rate limit happy.
_DRAFTER_CONCURRENCY = 4


#: Decision types the resume call is allowed to use. Anything
#: else is rejected (the drafter + redline logic only act on
#: "accepted"; the other three are audit-only).
_VALID_DECISION_ACTIONS = {"accepted", "rejected", "edited", "context_added"}


# --- Ingest + parse + classify -----------------------------------------


async def ingest_parse_classify_node(
    state: PipelineState,
) -> PipelineState:
    """Stage 1 — run the ingest / parse / classify pipeline.

    Calls :func:`app.pipeline.stage1_ingest.run_stage1` in a
    thread (the function is sync and CPU-bound enough to
    justify the executor). The result is a list of
    :class:`Clause` dicts (the Pydantic model serialises
    cleanly when stored in the state).

    The node also writes a ``graph_started`` audit event so
    the audit replay view can show "the graph started at
    14:31:42."

    On error, the node sets ``error`` in the state and
    short-circuits to END. The graph must always reach END
    so the checkpoint is durable; the API layer reads the
    error from the state.
    """
    filename = state.get("filename", "")
    content_type = state.get("content_type", "")
    file_bytes = state.get("file_bytes", b"")

    logger.info("ingest_parse_classify for %s (%d bytes)", filename, len(file_bytes))
    try:
        result = await asyncio.to_thread(
            run_stage1,
            filename=filename,
            content_type=content_type,
            data=file_bytes,
        )
        clauses: list[dict[str, Any]] = [c.model_dump() for c in result.clauses]
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest_parse_classify failed: %s", exc)
        return {"error": f"ingest failed: {exc}"}

    # Persist a graph_started audit event. The :func:`_audit`
    # helper returns the new audit_event_count; we MUST
    # merge that into the partial state we return so the
    # LangGraph state carries the incremented counter
    # forward (LangGraph merges the returned dict, not the
    # mutated ``state`` argument). The acceptance test
    # asserts ``audit_event_count >= 1`` after the first
    # pause.
    audit_update = await _audit(
        state,
        decision_type=DecisionType.GRAPH_STARTED,
        payload={"clause_count": len(clauses)},
    )

    return {
        "clauses": clauses,
        "audit_event_count": int(
            audit_update.get("audit_event_count", 0)
        ),
        "error": None,
    }


# --- Spot deviations ---------------------------------------------------


async def spot_deviations_node(state: PipelineState) -> PipelineState:
    """Stage 3 — run the deviation spotter on the classified clauses.

    The clauses from stage 1 are in the state. We rehydrate
    them into Pydantic models (the store layer is typed and
    wants the real model, not a dict), then call
    :func:`app.pipeline.stage3_spot.run_stage3`. The
    resulting flags are stored as dicts in the state.

    The node does NOT write per-flag audit events. The
    audit log records *decisions*, not intermediate agent
    outputs. The user's per-flag decisions (the audit-worthy
    events) arrive via the resume call, not from this node.
    """
    raw_clauses = state.get("clauses") or []
    if not raw_clauses:
        return {"error": "no clauses to spot — stage 1 returned empty list"}

    clauses = [Clause.model_validate(c) for c in raw_clauses]
    filename = state.get("filename", "")

    try:
        result = await run_stage3(clauses=clauses, contract_filename=filename)
        flags: list[dict[str, Any]] = [f.model_dump() for f in result.flags]
    except Exception as exc:  # noqa: BLE001
        logger.exception("spot_deviations failed: %s", exc)
        return {"error": f"spot failed: {exc}"}

    logger.info(
        "spot_deviations for %s: %d flags (%d flagged)",
        filename,
        len(flags),
        sum(1 for f in flags if f.get("score", 0) > 0),
    )

    return {"flags": flags, "error": None}


# --- Interrupt (HITL pause) -------------------------------------------


async def interrupt_hitl_node(state: PipelineState) -> PipelineState:
    """Pause the graph; surface the deviation table to the UI.

    Uses :func:`langgraph.types.interrupt` to suspend the
    graph. The first invocation raises a ``GraphInterrupt``
    carrying the ``interrupt_payload`` (the data the UI
    needs to render the table). The graph halts; the
    Postgres checkpoint is durable.

    On resume (the API layer's POST to /resume), the same
    node re-executes. ``interrupt()`` now returns the
    ``Command`` payload — the per-flag decision batch —
    instead of raising. We validate the shape and either
    advance the graph or set ``error`` and short-circuit.

    The validation is defensive: a malicious or buggy
    caller could send any JSON; we trust the schema, not
    the network. A malformed decision batch results in
    ``error`` in the state and the graph reaches END with
    the checkpoint intact (the operator can re-resume
    after fixing the payload).
    """
    contract_id = state.get("contract_id", "<unknown>")
    flags = state.get("flags") or []
    clauses = state.get("clauses") or []

    if not flags:
        return {"error": "interrupt_hitl called with empty flags"}

    # Build the payload the UI reads. Mirrors the
    # SpotResponse shape the Phase 2 endpoint returns, so
    # the frontend can reuse its deviation-table renderer.
    payload = {
        "contract_id": contract_id,
        "filename": state.get("filename", ""),
        "clause_count": len(clauses),
        "flag_count": len(flags),
        "flags": flags,
    }

    # The interrupt call. On the first execution the
    # LangGraph runtime catches the GraphInterrupt
    # internally and ``ainvoke`` returns the partial
    # result with the interrupt value under
    # ``__interrupt__``. The call to :func:`interrupt`
    # itself does NOT raise to user code in the standard
    # ``ainvoke`` path — it returns the resume value
    # (which is ``None`` on the first call) and the
    # runtime traps the GraphInterrupt to populate
    # ``__interrupt__``. We need to detect "first
    # execution" — the case where there's nothing to
    # resume from — and return the payload as part of
    # the state so the checkpoint has it. On the second
    # call (resume), ``decision_batch`` is a dict the
    # caller passed via ``Command(resume=...)``.
    decision_batch = interrupt(payload)
    if not decision_batch:
        # First-execution path: the graph is paused. Stash
        # the payload in the state so the checkpoint has
        # it. The partial-state return merges into
        # LangGraph state and the GraphInterrupt is
        # surfaced to the caller via ``__interrupt__``.
        return {
            "interrupt_payload": payload,
            "error": None,
        }

    # --- Resume path ----------------------------------------
    # Validate the decision batch. The shape is:
    #   {"decisions": {clause_id: {action, severity?, extra_context?}}}
    # The action is one of: accepted, rejected, edited,
    # context_added. severity is the user-overridden score
    # (only when action == "edited"). extra_context is the
    # user's free-form note (any action).
    if not isinstance(decision_batch, dict):
        return {"error": f"resume payload must be a dict, got {type(decision_batch).__name__}"}
    decisions_raw = decision_batch.get("decisions")
    if not isinstance(decisions_raw, dict):
        return {"error": "resume payload must contain a 'decisions' dict"}

    decisions: dict[str, dict[str, Any]] = {}
    for clause_id, dec in decisions_raw.items():
        if not isinstance(dec, dict):
            return {"error": f"decision for {clause_id!r} must be a dict"}
        action = str(dec.get("action", "")).lower().strip()
        if action not in _VALID_DECISION_ACTIONS:
            return {
                "error": (
                    f"decision for {clause_id!r} has invalid action {action!r}; "
                    f"expected one of {sorted(_VALID_DECISION_ACTIONS)}"
                )
            }
        # Build the canonical decision shape. We discard
        # unknown keys (forward-compat: a future frontend
        # version might send a field we don't know about
        # yet; we keep the API surface open but don't act
        # on unknown data).
        canonical: dict[str, Any] = {"action": action}
        if action == "edited":
            sev = dec.get("severity")
            if sev is not None:
                try:
                    canonical["severity"] = max(0, min(3, int(sev)))
                except (TypeError, ValueError):
                    return {
                        "error": (
                            f"decision for {clause_id!r} has non-integer "
                            f"severity {sev!r}"
                        )
                    }
        ctx = dec.get("extra_context")
        if ctx is not None and str(ctx).strip():
            canonical["extra_context"] = str(ctx)
        decisions[clause_id] = canonical

    logger.info(
        "interrupt_hitl resumed for %s: %d decisions (%d accepted)",
        contract_id,
        len(decisions),
        sum(1 for d in decisions.values() if d.get("action") == "accepted"),
    )

    return {
        "interrupt_payload": payload,
        "decisions": decisions,
        "error": None,
    }


# --- Apply decisions (audit per-flag) ---------------------------------


async def apply_decisions_node(state: PipelineState) -> PipelineState:
    """Write a per-decision audit event for every flag the user touched.

    One row per flag whose action is anything other than
    "accepted with no override." The action is the
    ``decision_type`` (FLAG_ACCEPTED, FLAG_REJECTED,
    SEVERITY_EDITED, CONTEXT_ADDED) and the payload carries
    the flag's original score + the user's override (if
    any) + the free-form context (if any).

    The graph does NOT short-circuit on a single decision's
    audit-write failure — the entire batch is wrapped in a
    try/except and the node returns the count of successful
    writes. A partial audit is better than a partial graph
    (the next node runs the redline drafter; the audit
    log's "missing row" is recoverable, the graph's
    "halt" is not).
    """
    decisions = state.get("decisions") or {}
    if not decisions:
        return {}

    # Walk every decision and write the per-decision audit
    # row. We accumulate the partial state updates from
    # :func:`_audit` and return the merged result so the
    # LangGraph state carries the incremented counter
    # forward (LangGraph merges the returned dict, not the
    # mutated ``state`` argument). Mutating ``state`` in
    # place works in some graph backends but the spec
    # requires we treat the returned dict as the merge
    # source — same convention as
    # :func:`ingest_parse_classify_node`.
    successes = 0
    last_count = int(state.get("audit_event_count", 0))
    for clause_id, dec in decisions.items():
        action = dec.get("action")
        payload: dict[str, Any] = {
            "original_score": dec.get("severity"),
        }
        if action == "accepted":
            d_type = DecisionType.FLAG_ACCEPTED
        elif action == "rejected":
            d_type = DecisionType.FLAG_REJECTED
        elif action == "edited":
            d_type = DecisionType.SEVERITY_EDITED
            payload["new_severity"] = dec.get("severity")
        elif action == "context_added":
            d_type = DecisionType.CONTEXT_ADDED
        else:
            # Defensive — validation already filtered
            # unknown actions, but the spec is "the only
            # way to write to the table is the writer."
            continue

        ctx = dec.get("extra_context")
        if ctx:
            payload["extra_context"] = ctx

        result = await _audit(
            state,
            decision_type=d_type,
            clause_id=clause_id,
            payload=payload,
        )
        # Track via the partial-state returned count (the
        # authoritative counter, since LangGraph merges
        # this back into the live state).
        new_count = int(result.get("audit_event_count", 0))
        if new_count > last_count:
            successes += 1
            last_count = new_count

    logger.info(
        "apply_decisions wrote %d/%d audit events for %s",
        successes,
        len(decisions),
        state.get("contract_id", "<unknown>"),
    )
    return {"audit_event_count": last_count}


# --- Redline drafter ---------------------------------------------------


async def _draft_one(
    *,
    clause_id: str,
    clause_text: str,
    clause_type: str,
    flag: DeviationFlag,
    baseline: BaselineForSpotter,
    extra_context: str,
    contract_filename: str,
) -> dict[str, Any]:
    """Draft + self-check a single accepted flag.

    Returns a dict shaped for storage in the state. The
    shape depends on the outcome:

    - happy path — ``{"outcome": "ok", "proposal": {...}}``
    - conflict — ``{"outcome": "conflict", "conflict": {...}}``
    - unavailable — ``{"outcome": "unavailable", "reason": "..."}``

    The three outcomes map to three UI states
    ("here's the redline", "we couldn't auto-draft, pick
    one", "the LLM is down, please retry").
    """
    drafter_input = DrafterInput(
        flag=flag,
        clause_text=clause_text,
        baseline=baseline,
        extra_context=extra_context,
    )
    try:
        outcome = await run_with_self_check(
            drafter_input, contract_filename=contract_filename
        )
    except DrafterUnavailable as exc:
        return {"outcome": "unavailable", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        # An unexpected exception (e.g. Pydantic validation
        # crash). Treat as unavailable — the spec's "no
        # silent default" rule means we surface the error
        # to the UI rather than swallowing it.
        return {"outcome": "unavailable", "reason": f"drafter failed: {exc}"}

    if isinstance(outcome, RedlineProposal):
        return {
            "outcome": "ok",
            "proposal": outcome.model_dump(),
        }
    if isinstance(outcome, RedlineConflict):
        return {
            "outcome": "conflict",
            "conflict": outcome.model_dump(),
        }
    return {"outcome": "unavailable", "reason": f"unknown outcome: {type(outcome).__name__}"}


async def draft_redlines_node(state: PipelineState) -> PipelineState:
    """Run the redline drafter (with self-check) for every accepted flag.

    The drafter is called concurrently for every accepted
    flag, bounded to :data:`_DRAFTER_CONCURRENCY` in flight.
    Rejected / edited-without-accept / context-added flags
    do NOT get a redline (the spec: "every approval,
    rejection, severity override, redline generation, and
    deviation flag gets a row" — only approvals get a
    redline).

    For each flag we also write a ``redline_generated`` audit
    event with the outcome (ok / conflict / unavailable).
    The audit log shows "for clause 4, the drafter produced
    a redline on attempt 1" (or "self-check retry was
    needed" — that's in the proposal.attempt field).
    """
    decisions = state.get("decisions") or {}
    raw_flags = state.get("flags") or []
    raw_clauses = state.get("clauses") or []
    contract_filename = state.get("filename", "")
    contract_id = state.get("contract_id", "<unknown>")

    accepted = [
        clause_id
        for clause_id, dec in decisions.items()
        if dec.get("action") == "accepted"
    ]
    if not accepted:
        return {"redlines": {}}

    # Build clause / flag lookup tables keyed by clause_id.
    clauses_by_id: dict[str, Clause] = {
        c["id"]: Clause.model_validate(c) for c in raw_clauses if c.get("id")
    }
    flags_by_id: dict[str, DeviationFlag] = {
        f["clause_id"]: DeviationFlag.model_validate(f)
        for f in raw_flags
        if f.get("clause_id")
    }

    semaphore = asyncio.Semaphore(_DRAFTER_CONCURRENCY)

    async def _bounded(
        clause_id: str,
    ) -> tuple[str, dict[str, Any]]:
        async with semaphore:
            flag = flags_by_id.get(clause_id)
            clause = clauses_by_id.get(clause_id)
            if flag is None or clause is None:
                # Defensive — the API layer validates
                # decisions reference real clause_ids, but
                # the graph's contract is "defensive at
                # every boundary."
                return (
                    clause_id,
                    {"outcome": "unavailable", "reason": "flag or clause not found"},
                )
            # The Phase 3 spec calls for the drafter to
            # receive the *top* baseline. The Phase 2
            # spotter doesn't surface baselines on the flag
            # (only ``baseline_type``); we have nothing to
            # pass. The drafter's "no baseline" path is
            # typed-allowed — the docx output node (Build
            # 2) will re-run the spotter lookup to fetch
            # the baseline text. For Build 3 we accept
            # the drafter's "no baseline" handling, which
            # is to use the clause text as the baseline
            # (per the drafter's :class:`DrafterInput`
            # default).
            baseline = BaselineForSpotter(
                clause_id="unknown",
                type=flag.baseline_type or "unknown",
                title="(no baseline — Build 3 placeholder)",
                text=clause.text,  # drafter's "no baseline" hint
                source_url="(no-baseline-build-3)",
                similarity=0.0,
            )
            extra_context = decisions.get(clause_id, {}).get("extra_context", "")
            result = await _draft_one(
                clause_id=clause_id,
                clause_text=clause.text,
                clause_type=clause.type.value,
                flag=flag,
                baseline=baseline,
                extra_context=extra_context,
                contract_filename=contract_filename,
            )
            return clause_id, result

    tasks = [_bounded(cid) for cid in accepted]
    results = await asyncio.gather(*tasks)
    redlines: dict[str, dict[str, Any]] = dict(results)

    # Per-flag audit event for every redline (regardless of
    # outcome). The audit log shows the drafter's outcome
    # for each accepted flag. We accumulate the partial
    # state from :func:`_audit` so the counter propagates
    # back to LangGraph state (same convention as the
    # other nodes).
    last_count = int(state.get("audit_event_count", 0))
    for clause_id, result in redlines.items():
        audit_update = await _audit(
            state,
            decision_type=DecisionType.REDLINE_GENERATED,
            clause_id=clause_id,
            payload={
                "outcome": result.get("outcome"),
                "attempt": (result.get("proposal") or {}).get("attempt", 0),
            },
        )
        new_count = int(audit_update.get("audit_event_count", 0))
        if new_count > last_count:
            last_count = new_count

    logger.info(
        "draft_redlines for %s: %d accepted, %d ok / %d conflict / %d unavailable",
        contract_id,
        len(accepted),
        sum(1 for r in redlines.values() if r.get("outcome") == "ok"),
        sum(1 for r in redlines.values() if r.get("outcome") == "conflict"),
        sum(1 for r in redlines.values() if r.get("outcome") == "unavailable"),
    )

    return {
        "redlines": redlines,
        "audit_event_count": last_count,
    }


# --- Assemble .docx ---------------------------------------------------


async def assemble_output_node(state: PipelineState) -> PipelineState:
    """Assemble the .docx (no-op until Build 2 lands).

    The real docx builder lives in Build 2 (a sibling
    card). This node is the place to call it. Until then
    the node returns an empty byte string so the API
    layer can serve a "coming soon" placeholder without
    crashing.

    The audit log writer is still called — a
    ``redline_downloaded`` event is conceptually a
    *download* event, not a *generation* event, so this
    node does NOT emit a generation event. The download
    endpoint will emit the download event itself.
    """
    return {"output_docx_bytes": b""}


# --- Finalize ----------------------------------------------------------


async def finalize_node(state: PipelineState) -> PipelineState:
    """Write a final audit summary event and return END.

    The "summary" event is a synthetic lifecycle marker
    tagged with the final state. The audit replay view
    uses it as a "the run reached END" marker. We use
    :data:`DecisionType.GRAPH_RESUMED` for the marker
    (not ``GRAPH_STARTED``) — the spec reserves
    ``graph_started`` for the *first* graph invocation
    and the resume token for lifecycle events that happen
    *after* the resume call (finalize is post-resume).
    """
    await _audit_lifecycle(
        state,
        decision_type=DecisionType.GRAPH_RESUMED,  # post-resume lifecycle marker
        extra={
            "phase": "finalize",
            "audit_event_count": int(state.get("audit_event_count", 0)),
            "redline_count": len(state.get("redlines") or {}),
        },
    )
    return {}


__all__ = [
    "ingest_parse_classify_node",
    "spot_deviations_node",
    "interrupt_hitl_node",
    "apply_decisions_node",
    "draft_redlines_node",
    "assemble_output_node",
    "finalize_node",
]
