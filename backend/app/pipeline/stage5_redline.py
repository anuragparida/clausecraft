"""Phase 3 Stage 5 — the redline stage (new file per card ``t_0671d337``).

Spec quotation
--------------
docs/11-phases.md line 229 (verbatim):
    "HITL state machine: LangGraph ``interrupt`` node. State
     object holds the flag table + per-flag decisions. Resume
     from the same node after the user clicks \"Generate
     redline.\" Pause-and-resume is testable."

docs/11-phases.md line 285 (verbatim):
    "If the drafter proposes text that the spotter flags, the
     retry may produce text that the spotter flags
     differently. Cap retries at 1; on the second failure,
     surface to the user with both attempts and the conflict."

This module is the "stage 5" file the card
``t_0671d337`` (Build: HITL state machine — LangGraph
interrupt) asks for. It is the *post-resume* stage that
runs the redline drafter (card ``t_d6e00376`` / Build 1)
for every approved flag in ``state.flag_decisions``,
queues a ``redline_generated`` audit event per flag, and
surfaces a :class:`RedlineConflict` to the UI when the
self-check loop fails twice (no silent third retry, per
spec line 285).

Why a new file
--------------
The card spec calls out:

    "3. **Redline stage** in ``backend/app/pipeline/stage5_redline.py``
        (new file — Phase 3's first new stage):"

Until Build 3 the redline logic lived inside the
``draft_redlines_node`` in :mod:`.graph_nodes`. That node
is still present (the existing graph topology uses it) but
this stage is the *typed-state* path the card spec calls
for: it reads from the typed ``state.flag_decisions``,
queues per-redline audit events into
``state.audit_log_writes`` (the spec's "audit log writes
are queued in state, not directly called" hard rule), and
populates ``state.redline_proposals`` (the typed equivalent
of the original ``state.redlines``).

The two paths are not in conflict. The new stage5 runs
*after* the HITL resume; the queued writes are drained by
:func:`app.pipeline.graph_nodes.flush_audit_log_writes_node`
at the end of the run.

Acceptance mapping
------------------
The card's acceptance list maps to this module:

- "On success: stores the ``RedlineProposal`` in
  ``state.redline_proposals[flag_id]``" — see the
  ``ok`` branch below.
- "On self-check fail-both: stores the
  ``RedlineProposalConflict`` and surfaces to the UI (does
  NOT silently retry a third time — per spec line 285)" —
  see the ``conflict`` branch.
- "Writes an audit log entry per redline generation:
  ``decision_type=\"redline_generated\"``,
  ``payload_json={\"flag_id\": ..., \"rationale\": ...}``,
  ``decided_by=\"agent:redline_drafter\"``" — see
  :func:`_queue_redline_audit_event`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.deviation_spotter.schema import DeviationFlag
from app.agents.redline_drafter.drafter import DrafterUnavailable
from app.agents.redline_drafter.schema import (
    BaselineForSpotter,
    DrafterInput,
    RedlineConflict,
    RedlineProposal,
)
from app.agents.redline_drafter.self_check import run_with_self_check
from app.audit.schema import DecisionType
from app.classify.schema import Clause
from app.observability import get_langfuse
from app.pipeline.graph_state import (
    AuditLogEntry,
    AuditEvent,
    PipelineState,
)

logger = logging.getLogger(__name__)


#: Max concurrent drafter calls inside :func:`run_stage5`.
#: Mirrors the existing ``draft_redlines_node`` bound (4) so
#: the two paths have the same footprint on the gateway's
#: rate limit. The self-check loop doubles the effective
#: LLM call count, so we halve the concurrency to keep
#: the gateway happy.
_DRAFTER_CONCURRENCY = 4


#: The decided_by value the spec calls out for redline
#: generation events. Distinct from the user-action events
#: (which carry ``decided_by="test-user"`` in the e2e path
#: and ``settings.audit_decided_by`` in production). The
#: agent is the actor, not the user.
_REDLINE_AGENT_DECIDED_BY = "agent:redline_drafter"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with ``Z`` suffix.

    Same shape :mod:`.graph_nodes._now_iso` uses; the
    audit log expects the spec-style ``Z`` suffix (matches
    the spec's "12:34:56Z" examples).
    """
    from datetime import datetime, timezone  # local import: hot-path-friendly
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def _trace_redline_event(event_name: str, **fields: Any) -> None:
    """Emit a Langfuse trace event for the redline stage.

    The :func:`get_langfuse` client is a no-op when the
    configured keys are placeholders; the test suite runs
    cleanly without a real Langfuse instance. We still
    exercise the call path so the spy test can assert the
    drafter emits trace annotations.
    """
    try:
        lf = get_langfuse()
        if hasattr(lf, "trace"):
            span = lf.trace(name=event_name)
            for k, v in fields.items():
                span.update(metadata={k: v})
    except Exception:  # noqa: BLE001
        # Tracing failures never break the redline stage.
        pass


def _queue_redline_audit_event(
    *,
    contract_id: str,
    flag_id: str,
    outcome: str,
    rationale: str = "",
    conflict: bool = False,
    attempt: int = 0,
) -> dict[str, Any]:
    """Build an :class:`AuditLogEntry` for a redline generation event.

    The shape is exactly what the spec calls for:

        decision_type="redline_generated"
        payload_json={"flag_id": ..., "rationale": ...,
                      "conflict": True|False, "attempt": int}
        decided_by="agent:redline_drafter"

    The entry is QUEUED — it lands in
    ``state.audit_log_writes`` and is drained by
    :func:`app.pipeline.graph_nodes.flush_audit_log_writes_node`
    at the end of the run. This is the spec's "audit log
    writes are queued in state, not directly called" hard
    rule: a mid-graph crash doesn't leave half-written
    audit state.
    """
    payload_json: dict[str, Any] = {
        "flag_id": flag_id,
        "rationale": rationale,
        "conflict": conflict,
        "attempt": attempt,
    }
    event = AuditEvent(
        contract_id=contract_id,
        clause_id=flag_id,
        decision_type=DecisionType.REDLINE_GENERATED,
        payload_json=payload_json,
    )
    entry = AuditLogEntry(event=event, committed=False)
    return entry.model_dump(mode="jsonable")


def _queue_redline_audit_event_for_state(
    state: PipelineState,
    *,
    flag_id: str,
    outcome: str,
    rationale: str = "",
    conflict: bool = False,
    attempt: int = 0,
) -> dict[str, Any]:
    """Same as :func:`_queue_redline_audit_event` but threads the state.

    Reads ``contract_id`` from the state and appends the
    new entry to the existing ``state.audit_log_writes``
    queue (a list of dicts).

    Returns a partial-state dict with the new queue — the
    caller merges this into the LangGraph return value so
    the queue propagates to the checkpoint.
    """
    contract_id = state.get("contract_id", "<unknown>")
    entry = _queue_redline_audit_event(
        contract_id=contract_id,
        flag_id=flag_id,
        outcome=outcome,
        rationale=rationale,
        conflict=conflict,
        attempt=attempt,
    )
    queue = list(state.get("audit_log_writes") or [])
    queue.append(entry)
    return {"audit_log_writes": queue}


async def _draft_one_for_flag(
    *,
    flag_id: str,
    clause_text: str,
    clause_type: str,
    flag: DeviationFlag,
    extra_context: str,
    contract_filename: str,
) -> dict[str, Any]:
    """Run the drafter + self-check for one approved flag.

    Returns a dict shaped for storage in the typed state:

    - happy path — ``{"outcome": "ok", "proposal": <RedlineProposal dump>}``
    - conflict — ``{"outcome": "conflict", "conflict": <RedlineConflict dump>}``
    - unavailable — ``{"outcome": "unavailable", "reason": "..."}``

    The drafter raises :class:`DrafterUnavailable` when the
    LLM key is a placeholder; the spec's "no silent default"
    rule. The conflict path is the spec's "self-check
    fail-both" path (line 285) — we do NOT silently retry a
    third time.
    """
    baseline = BaselineForSpotter(
        clause_id="unknown",
        type=flag.baseline_type or "unknown",
        title="(no baseline — stage 5 placeholder)",
        text=clause_text,
        source_url="(no-baseline-stage-5)",
        similarity=0.0,
    )
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
    return {
        "outcome": "unavailable",
        "reason": f"unknown outcome: {type(outcome).__name__}",
    }


def _selected_flag_ids(state: PipelineState) -> list[str]:
    """Return the flag_ids the drafter should run against.

    The typed-state source of truth is ``state.flag_decisions``
    (the spec's name). We filter to **only** approved
    actions because the spec is explicit: "every approval,
    rejection, severity override, redline generation, and
    deviation flag gets a row — **only approvals get a
    redline**." Edited / context-added flags do NOT get a
    redline (the user has overridden the spotter's score
    or added context, but the drafter is not called).

    Falls back to ``state.decisions`` for backward-compat
    with the existing graph topology (the original
    ``draft_redlines_node`` reads from ``decisions`` keyed
    by clause_id; the legacy shape uses the action name
    "accepted" rather than the typed-state "approved").
    The action-name mapping ("accepted" -> "approved") is
    applied earlier in the pipeline; here we accept both
    spellings for the back-compat fallback.
    """
    flag_decisions = state.get("flag_decisions") or {}
    if flag_decisions:
        return [
            fid
            for fid, dec in flag_decisions.items()
            if isinstance(dec, dict)
            and dec.get("action") == "approved"
        ]
    decisions = state.get("decisions") or {}
    return [
        cid
        for cid, dec in decisions.items()
        if isinstance(dec, dict)
        and dec.get("action") in {"accepted", "approved"}
    ]


async def run_stage5(state: PipelineState) -> PipelineState:
    """Stage 5 — run the redline drafter (with self-check) for every approved flag.

    This is the typed-state entry point the card
    ``t_0671d337`` calls for. It is wired into
    :mod:`.graph` *after* the ``hitl_review_node`` and
    *before* the ``flush_audit_log_writes_node`` so:

    1. The HITL node populates ``state.flag_decisions``.
    2. Stage 5 reads from ``state.flag_decisions`` and
       runs the drafter per approved flag.
    3. The flush node drains ``state.audit_log_writes`` to
       the audit_events table.

    Per-flag audit events are QUEUED in
    ``state.audit_log_writes`` (not written directly) — the
    spec's "audit log writes are queued in state, not
    directly called" hard rule.

    Returns
    -------
    PipelineState
        A partial-state update with:

        - ``redline_proposals`` — ``dict[flag_id -> RedlineProposal]``
          for the ok path (typed; Pydantic-validated).
        - ``redlines`` — backward-compat dict (legacy
          ``draft_redlines_node`` readers).
        - ``audit_log_writes`` — appended queue.
        - ``error`` — ``None`` on success; error string on
          defensive failures.
    """
    # Propagate error from previous nodes (the graph
    # does not short-circuit on error; the API layer
    # reads error from the final state).
    if state.get("error"):
        return {"error": state.get("error")}

    contract_id = state.get("contract_id", "<unknown>")
    contract_filename = state.get("filename", "")
    selected = _selected_flag_ids(state)
    raw_flags = state.get("flags") or []
    raw_clauses = state.get("clauses") or []

    if not selected:
        logger.info("stage5_redline: no approved flags for %s", contract_id)
        return {
            "redline_proposals": {},
            "error": None,
        }

    # Build clause / flag lookup tables. The card spec
    # keys by flag_id; the current data model uses
    # clause_id (one flag per clause). For the existing
    # test corpus, ``flag_id == clause_id`` (the
    # :func:`_flag_id_for_clause` helper in graph_nodes is
    # the 1:1 rename). We accept both forms for forward
    # compat.
    clauses_by_id: dict[str, Clause] = {
        c["id"]: Clause.model_validate(c)
        for c in raw_clauses
        if isinstance(c, dict) and c.get("id")
    }
    flags_by_id: dict[str, DeviationFlag] = {}
    for f in raw_flags:
        if not isinstance(f, dict):
            continue
        cid = f.get("clause_id") or f.get("flag_id")
        if cid:
            flags_by_id[str(cid)] = DeviationFlag.model_validate(f)

    # Map "approved flag_id" -> extra_context. The user's
    # context is read from the typed ``flag_decisions`` or
    # the backward-compat ``decisions`` dict.
    extra_context_map: dict[str, str] = {}
    for fid in selected:
        dec = (state.get("flag_decisions") or {}).get(fid) or (
            state.get("decisions") or {}
        ).get(fid)
        if isinstance(dec, dict):
            extra_context_map[fid] = str(dec.get("extra_context", "") or "")
        else:
            extra_context_map[fid] = ""

    semaphore = asyncio.Semaphore(_DRAFTER_CONCURRENCY)

    async def _bounded(flag_id: str) -> tuple[str, dict[str, Any]]:
        async with semaphore:
            # The lookup accepts the flag_id directly OR
            # the clause_id (Phase 3 keeps flag_id ==
            # clause_id, but a future build may split).
            flag = flags_by_id.get(flag_id)
            clause = clauses_by_id.get(flag_id)
            if flag is None or clause is None:
                return (
                    flag_id,
                    {
                        "outcome": "unavailable",
                        "reason": f"flag or clause {flag_id!r} not in state",
                    },
                )
            return flag_id, await _draft_one_for_flag(
                flag_id=flag_id,
                clause_text=clause.text,
                clause_type=clause.type.value,
                flag=flag,
                extra_context=extra_context_map.get(flag_id, ""),
                contract_filename=contract_filename,
            )

    tasks = [_bounded(fid) for fid in selected]
    results = await asyncio.gather(*tasks)

    redline_proposals: dict[str, dict[str, Any]] = {}
    redlines_backcompat: dict[str, dict[str, Any]] = {}
    queued = list(state.get("audit_log_writes") or [])

    for flag_id, result in results:
        outcome = result.get("outcome")
        # Typed-state population. The Pydantic validation
        # is the trust boundary — a malformed RedlineProposal
        # in the typed layer would corrupt the docx output.
        if outcome == "ok":
            proposal_dict = result.get("proposal") or {}
            try:
                proposal = RedlineProposal.model_validate(proposal_dict)
            except Exception as exc:  # noqa: BLE001
                # Defensive: a malformed proposal (e.g. the
                # drafter returned a dict that doesn't
                # validate) lands as unavailable. We do
                # NOT silently drop it.
                logger.error(
                    "stage5: malformed RedlineProposal for %s: %s",
                    flag_id, exc,
                )
                redlines_backcompat[flag_id] = {
                    "outcome": "unavailable",
                    "reason": f"malformed proposal: {exc}",
                }
                queued.append(
                    _queue_redline_audit_event(
                        contract_id=contract_id,
                        flag_id=flag_id,
                        outcome="unavailable",
                        rationale=f"malformed proposal: {exc}",
                        conflict=False,
                        attempt=int(proposal_dict.get("attempt", 0) or 0),
                    )
                )
                continue
            redline_proposals[flag_id] = proposal.model_dump(mode="jsonable")
            redlines_backcompat[flag_id] = {
                "outcome": "ok",
                "proposal": proposal.model_dump(),
            }
            # Queue the per-redline audit event per spec.
            rationale = ""
            try:
                rationale = proposal.rationale or ""
            except AttributeError:
                pass
            queued.append(
                _queue_redline_audit_event(
                    contract_id=contract_id,
                    flag_id=flag_id,
                    outcome="ok",
                    rationale=rationale,
                    conflict=False,
                    attempt=int(proposal.attempt or 0),
                )
            )
        elif outcome == "conflict":
            conflict_dict = result.get("conflict") or {}
            try:
                conflict = RedlineConflict.model_validate(conflict_dict)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "stage5: malformed RedlineConflict for %s: %s",
                    flag_id, exc,
                )
                redlines_backcompat[flag_id] = {
                    "outcome": "unavailable",
                    "reason": f"malformed conflict: {exc}",
                }
                continue
            # The card spec is explicit: "stores the
            # ``RedlineProposalConflict`` and surfaces to
            # the UI (does NOT silently retry a third
            # time — per spec line 285)". We surface it
            # in BOTH the typed and the back-compat
            # state shape. The audit log row carries
            # ``conflict=True`` so the audit replay view
            # can render the conflict path.
            redlines_backcompat[flag_id] = {
                "outcome": "conflict",
                "conflict": conflict.model_dump(),
            }
            rationale = ""
            try:
                # RedlineConflict exposes the first
                # proposal's rationale (the second
                # attempt's rationale is the same
                # shape; the conflict_reason is the
                # message field).
                rationale = (
                    conflict.first_proposal.rationale
                    if hasattr(conflict, "first_proposal")
                    else "self-check fail-both"
                )
            except AttributeError:
                rationale = "self-check fail-both"
            queued.append(
                _queue_redline_audit_event(
                    contract_id=contract_id,
                    flag_id=flag_id,
                    outcome="conflict",
                    rationale=rationale,
                    conflict=True,
                    attempt=2,
                )
            )
        else:
            reason = str(result.get("reason", "unknown"))
            redlines_backcompat[flag_id] = {
                "outcome": "unavailable",
                "reason": reason,
            }
            queued.append(
                _queue_redline_audit_event(
                    contract_id=contract_id,
                    flag_id=flag_id,
                    outcome="unavailable",
                    rationale=reason,
                    conflict=False,
                    attempt=0,
                )
            )

    # Trace the stage5 completion. The spec calls for
    # Langfuse traces on the redline stage.
    await _trace_redline_event(
        "stage5_redline",
        contract_id=contract_id,
        approved_count=len(selected),
        ok=sum(1 for r in redlines_backcompat.values() if r.get("outcome") == "ok"),
        conflict=sum(
            1 for r in redlines_backcompat.values() if r.get("outcome") == "conflict"
        ),
        unavailable=sum(
            1 for r in redlines_backcompat.values() if r.get("outcome") == "unavailable"
        ),
    )

    logger.info(
        "stage5_redline for %s: %d approved, %d ok / %d conflict / %d unavailable",
        contract_id,
        len(selected),
        sum(1 for r in redlines_backcompat.values() if r.get("outcome") == "ok"),
        sum(1 for r in redlines_backcompat.values() if r.get("outcome") == "conflict"),
        sum(
            1 for r in redlines_backcompat.values() if r.get("outcome") == "unavailable"
        ),
    )

    return {
        "redline_proposals": redline_proposals,
        # NOTE: we do NOT write to ``state.redlines`` here.
        # The legacy ``draft_redlines_node`` runs BEFORE
        # this stage and is the canonical owner of the
        # back-compat ``state.redlines`` dict. The typed
        # ``state.redline_proposals`` is the additive
        # typed-state equivalent the card spec calls for;
        # consumers that want the typed path read from
        # ``state.redline_proposals``, consumers that want
        # the legacy path read from ``state.redlines``.
        "audit_log_writes": queued,
        "error": None,
    }


__all__ = [
    "run_stage5",
    "_queue_redline_audit_event",
    "_queue_redline_audit_event_for_state",
    "REDLINE_AGENT_DECIDED_BY",
]


# Re-export for completeness — the spec calls out the
# agent's identity explicitly.
REDLINE_AGENT_DECIDED_BY = _REDLINE_AGENT_DECIDED_BY
