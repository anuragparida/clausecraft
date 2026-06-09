"""Phase 3 HITL pipeline — the decisions + redline + audit-log orchestrator.

The Phase 3 build (Build 3) is the first phase where the user
makes per-flag decisions and the system turns them into a
real .docx with tracked changes. The pipeline is the API
layer's view of the build, not the LangGraph runtime
(``app.pipeline.graph``). The graph runtime is built and
exercised by the build's HITL ``interrupt()`` node, but the
API surface (Build 6's e2e test) drives a simpler sequential
flow::

    POST /contracts/ingest       (sets clauses in state)
        |
    POST /contracts/spot         (sets flags in state)
        |
    POST /contracts/{id}/decisions  (this module's job)
        |
    GET  /contracts/{id}/redline.docx  (read state, return bytes)
        |
    GET  /api/contracts/{id}/audit-log.json   (already works)
    GET  /api/contracts/{id}/audit-log.pdf    (already works)

Why a separate module
---------------------
The API layer (in ``app.main``) is a thin HTTP shell. The
decisions-to-docx flow is non-trivial (run the drafter per
accepted flag, run the self-check, write per-decision audit
events, write per-redline audit events, render the .docx)
and wants its own tests + module. Keeping it out of
``main.py`` means the route handlers stay small and the
pipeline is reusable (the future ``/graph/echo`` style
endpoints can call into here).

Why not the LangGraph runtime
-----------------------------
The graph is built (Build 3's ``_build_graph`` +
``graph_runtime``) and is the right tool when the caller is
the sync UI driving the ``interrupt()`` pause/resume
mechanism. The API layer doesn't need the pause — the
decisions come in one HTTP call, not as a series of UI
events — so calling the node functions directly is simpler
and faster. The graph is left in place for the future
"long-running workflow" use cases; the API doesn't use it.

State storage
-------------
A module-level dict, keyed by ``contract_id``, holds the
intermediate state (clauses, flags, the rendered .docx
bytes). Process-local, not persistent across restarts — the
spec's exit gate runs in CI, not across a container
restart. Production would swap this for a Postgres-backed
store (the table shape is documented in the
:class:`PipelineState` docstring).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.agents.deviation_spotter.schema import DeviationFlag
from app.agents.redline_drafter.drafter import DrafterUnavailable
from app.agents.redline_drafter.schema import (
    BaselineForSpotter,
    DrafterInput,
    RedlineConflict,
    RedlineProposal,
)
from app.agents.redline_drafter.self_check import run_with_self_check
from app.audit import AuditEvent, DecisionType, record_event
from app.classify.schema import Clause

logger = logging.getLogger(__name__)


# --- Per-contract state ------------------------------------------------


class PipelineRunState:
    """The in-memory state for one contract's Phase 3 run.

    Attributes
    ----------
    contract_id
        The stable key. For the e2e test, this is the
        upload filename (e.g. ``hand-curated/nda-001.pdf``);
        for production it would be a UUID.
    filename
        Echoed for the audit log.
    content_type
        The upload's MIME type. Stored so a re-render
        doesn't need to re-ingest from disk.
    file_bytes
        The original upload bytes.
    clauses
        The list of classified clauses from stage 1. Set
        after the ``/contracts/ingest`` endpoint runs.
    flags
        The list of deviation flags from stage 3. Set
        after the ``/contracts/spot`` endpoint runs.
    decisions
        The user's per-flag decisions. Set by the
        ``/contracts/{id}/decisions`` endpoint.
    redlines
        The redline drafter's outputs, keyed by
        clause_id. The shape is the drafter's three-way
        outcome (``{"outcome": "ok", "proposal": ...}`` /
        ``"conflict"`` / ``"unavailable"``). Set by
        :func:`process_decisions`.
    output_docx_bytes
        The rendered .docx. Set by
        :func:`process_decisions` after the redlines
        are computed.
    output_markdown_bytes
        The rendered markdown diff. Set by
        :func:`process_decisions` alongside the .docx
        as a v0 escape hatch (the markdown path is the
        "tracked changes are visible in Word but not in
        a browser preview" fallback; it is the same
        contract text + accepted proposals, expressed
        as a unified diff). Empty if no redlines.
    """

    __slots__ = (
        "contract_id",
        "filename",
        "content_type",
        "file_bytes",
        "clauses",
        "flags",
        "decisions",
        "redlines",
        "output_docx_bytes",
        "output_markdown_bytes",
    )

    def __init__(
        self,
        *,
        contract_id: str,
        filename: str,
        content_type: str = "application/octet-stream",
        file_bytes: bytes = b"",
    ) -> None:
        self.contract_id = contract_id
        self.filename = filename
        self.content_type = content_type
        self.file_bytes = file_bytes
        self.clauses: list[dict[str, Any]] = []
        self.flags: list[dict[str, Any]] = []
        self.decisions: dict[str, dict[str, Any]] = {}
        self.redlines: dict[str, dict[str, Any]] = {}
        self.output_docx_bytes: bytes = b""
        self.output_markdown_bytes: bytes = b""

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "filename": self.filename,
            "content_type": self.content_type,
            "file_bytes": self.file_bytes,
            "clauses": self.clauses,
            "flags": self.flags,
            "decisions": self.decisions,
            "redlines": self.redlines,
            "output_docx_bytes": self.output_docx_bytes,
            "output_markdown_bytes": self.output_markdown_bytes,
        }


#: Process-local state store. The e2e test exercises a
#: single in-process FastAPI app, so a module-level dict
#: is enough. Production swaps this for a Postgres-backed
#: store (the table schema mirrors the dataclass).
_STATE: dict[str, PipelineRunState] = {}


def get_state(contract_id: str) -> PipelineRunState:
    """Return the state for a contract, creating an empty one if needed."""
    if contract_id not in _STATE:
        _STATE[contract_id] = PipelineRunState(
            contract_id=contract_id,
            filename=contract_id,
        )
    return _STATE[contract_id]


def has_state(contract_id: str) -> bool:
    """``True`` when there's any state recorded for a contract."""
    return contract_id in _STATE


def reset_state(contract_id: str) -> None:
    """Remove a contract's state. Used by tests that want a clean slate."""
    _STATE.pop(contract_id, None)


# --- State snapshot (Build 7 — resume-after-pause UI hydration) --------


def snapshot_state(contract_id: str) -> dict[str, Any]:
    """Return a JSON-safe snapshot of a contract's resume-relevant state.

    Built for the ``GET /contracts/{contract_id}/state`` endpoint
    that the connected review page fetches on mount. The page
    uses it to re-hydrate the clauses, flags, and prior
    decisions when the user refreshes the URL mid-review (the
    pipeline layer's state machine round-trips fine, but the
    React page was rendering empty because the parent did not
    pass the clauses prop).

    Returned shape (stable; the frontend reads these keys)::

        {
          "contract_id": str,
          "filename": str,
          "has_state": bool,
          "has_ingest": bool,        # clauses populated
          "has_spot": bool,          # flags populated
          "has_decisions": bool,     # decisions posted
          "has_redline": bool,       # docx bytes rendered
          "clauses": list[dict],
          "flags": list[dict],
          "decisions": list[dict],   # list, not dict — friendly
                                     # for DeviationReview's
                                     # ``initialDecisions`` prop
          "redlines": list[dict],    # one entry per clause_id
        }

    ``has_state`` is the single boolean the UI checks to decide
    whether to render the review surface or the "this contract
    was not found" empty state. The narrower booleans
    (``has_ingest`` etc.) are convenience flags the UI can use
    for skeletons / error messages.

    The endpoint returns 200 with this payload even when the
    contract was never ingested — the page renders a friendly
    "no contract found at this URL" state instead of a hard 404.
    A 404 would force the user to navigate back to triage on a
    refresh, which is exactly the broken behaviour F3 is meant
    to fix.
    """
    if contract_id not in _STATE:
        return {
            "contract_id": contract_id,
            "filename": contract_id,
            "has_state": False,
            "has_ingest": False,
            "has_spot": False,
            "has_decisions": False,
            "has_redline": False,
            "clauses": [],
            "flags": [],
            "decisions": [],
            "redlines": [],
        }
    s = _STATE[contract_id]
    return {
        "contract_id": s.contract_id,
        "filename": s.filename,
        "has_state": True,
        "has_ingest": bool(s.clauses),
        "has_spot": bool(s.flags),
        "has_decisions": bool(s.decisions),
        "has_redline": bool(s.output_docx_bytes),
        "clauses": list(s.clauses),
        "flags": list(s.flags),
        "decisions": [
            {"clause_id": cid, **dec} for cid, dec in s.decisions.items()
        ],
        "redlines": [
            {"clause_id": cid, **out} for cid, out in s.redlines.items()
        ],
    }


# --- Decision validation ------------------------------------------------


#: The set of decision actions the API accepts in the
#: request body. Maps 1:1 to the graph node's
#: ``_VALID_DECISION_ACTIONS`` (we don't import from
#: ``graph_nodes`` to keep this module free of the
#: graph's internal naming).
_VALID_DECISION_ACTIONS: frozenset[str] = frozenset(
    {"accepted", "rejected", "edited", "context_added"}
)


def normalise_decision(
    *,
    clause_id: str,
    decision: str,
    new_severity: Optional[int] = None,
    old_severity: Optional[int] = None,
    extra_context: Optional[str] = None,
) -> dict[str, Any]:
    """Normalise one test-supplied decision into the canonical shape.

    The e2e test sends decisions in the shape::

        {"clause_id": "c4", "decision": "approve"}
        {"clause_id": "c6", "decision": "reject"}
        {"clause_id": "c4", "decision": "edit_severity",
         "new_severity": 1, "old_severity": 2}

    The internal graph / drafter / audit code uses the
    canonical shape::

        {"action": "accepted"|"rejected"|"edited"|"context_added",
         "severity": int, "extra_context": str}

    This function translates the test's shape to the
    canonical one. It is the only place that knows about
    the test's `decision` -> `action` mapping.
    """
    # Map the test's `decision` string to the canonical `action`.
    action_map = {
        "approve": "accepted",
        "accept": "accepted",
        "accepted": "accepted",
        "reject": "rejected",
        "rejected": "rejected",
        "edit_severity": "edited",
        "edit": "edited",
        "edited": "edited",
        "add_context": "context_added",
        "context_added": "context_added",
    }
    action = action_map.get(decision.lower().strip())
    if action is None:
        raise ValueError(
            f"unknown decision {decision!r} for clause {clause_id!r}; "
            f"expected one of {sorted(set(action_map.keys()))}"
        )

    canonical: dict[str, Any] = {"action": action}

    if action == "edited":
        if new_severity is not None:
            try:
                sev = int(new_severity)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"new_severity for clause {clause_id!r} must be int, "
                    f"got {new_severity!r}"
                ) from exc
            canonical["severity"] = max(0, min(3, sev))
        # old_severity is informational only — the audit
        # log uses it to render "2 → 1" diffs. We forward
        # it as-is when present.
        if old_severity is not None:
            canonical["old_severity"] = int(old_severity)

    if extra_context is not None and str(extra_context).strip():
        canonical["extra_context"] = str(extra_context)

    return canonical


# --- The pipeline -------------------------------------------------------


async def _draft_one_redline(
    *,
    clause_id: str,
    clause_text: str,
    flag: DeviationFlag,
    extra_context: str,
    contract_filename: str,
    clause_language: str = "en",
) -> dict[str, Any]:
    """Run the drafter + self-check for one accepted flag.

    Returns the result dict the state stores. Three
    outcomes:

    - ``{"outcome": "ok", "proposal": {...}}``
    - ``{"outcome": "conflict", "conflict": {...}}``
    - ``{"outcome": "unavailable", "reason": "..."}``
    """
    # The drafter needs a BaselineForSpotter. The Phase 2
    # spotter doesn't surface baselines on the flag
    # (only ``baseline_type``); we have nothing better to
    # pass. The drafter's "no baseline" path uses the
    # clause text as the baseline hint (matches the
    # graph node's Build 3 placeholder).
    baseline = BaselineForSpotter(
        clause_id="unknown",
        type=flag.baseline_type or "unknown",
        title="(no baseline — Phase 3 placeholder)",
        text=clause_text,
        source_url="(no-baseline-phase-3)",
        similarity=0.0,
    )
    drafter_input = DrafterInput(
        flag=flag,
        clause_text=clause_text,
        baseline=baseline,
        extra_context=extra_context,
        clause_language=clause_language,
    )
    try:
        outcome = await run_with_self_check(
            drafter_input, contract_filename=contract_filename
        )
    except DrafterUnavailable as exc:
        return {"outcome": "unavailable", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        # Unexpected — surface to the user, not silent.
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


async def _audit_event(
    *,
    contract_id: str,
    clause_id: str,
    decision_type: DecisionType,
    payload: dict[str, Any],
) -> None:
    """Append one audit event to the log.

    Helper around :func:`app.audit.log.record_event` that
    also logs failures (the spec is "the only way to write
    to the table is the writer" — the writer never raises
    on transport failure, it logs and moves on).
    """
    try:
        await record_event(
            AuditEvent(
                contract_id=contract_id,
                clause_id=clause_id,
                decision_type=decision_type,
                payload_json=payload,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "audit write failed for contract=%s clause=%s type=%s: %s",
            contract_id,
            clause_id or "<pipeline>",
            decision_type,
            exc,
        )


async def process_decisions(
    *,
    contract_id: str,
    decisions: list[dict[str, Any]],
    decided_by: str = "test-user",
) -> dict[str, Any]:
    """The main entry point: process the user's per-flag decisions.

    Steps:

    1. Normalise the test's decision list into the
       canonical shape.
    2. Write a ``graph_started`` lifecycle event (the
       test asserts ≥1 row per stage; the resume after
       ingest/spot also gets a ``graph_resumed`` event).
    3. Write one per-decision audit row.
    4. For each accepted flag, run the drafter (with
       self-check) and write a ``redline_generated``
       row.
    5. Render the .docx from the successful proposals.
    6. Write a ``graph_resumed`` lifecycle event.

    The state (clauses, flags, decisions, redlines, docx
    bytes) is updated in-place on the
    :class:`PipelineRunState` so the
    ``/contracts/{id}/redline.docx`` endpoint can serve
    it.
    """
    state = get_state(contract_id)

    # --- Step 1: normalise decisions ---------------------------
    canonical: dict[str, dict[str, Any]] = {}
    for raw in decisions:
        clause_id = str(raw.get("clause_id", "")).strip()
        decision = str(raw.get("decision", "")).strip()
        if not clause_id:
            raise ValueError("decision missing 'clause_id'")
        if not decision:
            raise ValueError(f"decision for {clause_id!r} missing 'decision'")
        try:
            canonical[clause_id] = normalise_decision(
                clause_id=clause_id,
                decision=decision,
                new_severity=raw.get("new_severity"),
                old_severity=raw.get("old_severity"),
                extra_context=raw.get("extra_context"),
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    state.decisions = canonical

    # --- Step 2: graph_started lifecycle -----------------------
    await _audit_event(
        contract_id=contract_id,
        clause_id="",
        decision_type=DecisionType.GRAPH_STARTED,
        payload={"thread_id": contract_id, "stage": "decisions"},
    )

    # --- Step 3: per-decision audit ----------------------------
    for clause_id, dec in canonical.items():
        action = dec["action"]
        payload: dict[str, Any] = {"action": action}
        if action == "edited":
            payload["new_severity"] = dec.get("severity")
            if "old_severity" in dec:
                payload["old_severity"] = dec["old_severity"]
        if "extra_context" in dec:
            payload["extra_context"] = dec["extra_context"]

        d_type = {
            "accepted": DecisionType.FLAG_ACCEPTED,
            "rejected": DecisionType.FLAG_REJECTED,
            "edited": DecisionType.SEVERITY_EDITED,
            "context_added": DecisionType.CONTEXT_ADDED,
        }.get(action)
        if d_type is None:
            continue
        await _audit_event(
            contract_id=contract_id,
            clause_id=clause_id,
            decision_type=d_type,
            payload=payload,
        )

    # --- Step 4: per-accepted redline --------------------------
    clauses_by_id: dict[str, Clause] = {
        c.get("id"): Clause.model_validate(c)
        for c in state.clauses
        if isinstance(c, dict) and c.get("id")
    }
    flags_by_id: dict[str, DeviationFlag] = {
        f.get("clause_id"): DeviationFlag.model_validate(f)
        for f in state.flags
        if isinstance(f, dict) and f.get("clause_id")
    }

    accepted_ids = [
        cid for cid, dec in canonical.items() if dec.get("action") == "accepted"
    ]
    redlines: dict[str, dict[str, Any]] = {}
    for cid in accepted_ids:
        flag = flags_by_id.get(cid)
        clause = clauses_by_id.get(cid)
        if flag is None or clause is None:
            redlines[cid] = {
                "outcome": "unavailable",
                "reason": f"flag or clause {cid!r} not in state",
            }
            continue
        extra_context = canonical.get(cid, {}).get("extra_context", "")
        result = await _draft_one_redline(
            clause_id=cid,
            clause_text=clause.text,
            flag=flag,
            extra_context=extra_context,
            contract_filename=state.filename,
            clause_language=clause.language,
        )
        redlines[cid] = result

        # Per-redline audit event. Per spec line 285, the
        # self-check conflict case writes a ``redline_generated``
        # row with ``payload_json.conflict = True`` and both
        # attempts recorded. We honour that contract here:
        # - on the ``ok`` path, we record ``attempt`` (1 or 2,
        #   the drafter's cap-at-1-retry).
        # - on the ``conflict`` path, we set ``conflict=True``
        #   and copy the two attempt proposals into the payload
        #   so the audit log is self-describing (the row alone
        #   is enough to reconstruct what happened).
        attempt = 0
        payload: dict[str, Any] = {"outcome": result.get("outcome")}
        if result.get("outcome") == "ok" and isinstance(result.get("proposal"), dict):
            proposal_dict = result["proposal"]
            attempt = int(proposal_dict.get("attempt", 0))
            payload["attempt"] = attempt
            # Phase 4 (card t_3597a13b) — the redline_generated
            # audit row must carry the drafter's rationale
            # verbatim, so the audit log is the source of
            # truth for "the DE LLM reasoned in DE, not in EN"
            # (the per-language F1 eval queries the rationale
            # prose directly). The conflict path below already
            # copies both attempts' rationales; the ok path
            # was missing this and the Phase 3 e2e never
            # asserted on it. The Phase 4 DE e2e enforces it.
            payload["rationale"] = proposal_dict.get("rationale", "")
        elif result.get("outcome") == "conflict":
            payload["conflict"] = True
            payload["attempt"] = attempt
            conflict = result.get("conflict") or {}
            if isinstance(conflict, dict):
                first = conflict.get("first_proposal") or {}
                second = conflict.get("second_proposal") or {}
                if isinstance(first, dict):
                    payload["first_attempt"] = {
                        "proposed_text": first.get("proposed_text"),
                        "rationale": first.get("rationale"),
                        "attempt": first.get("attempt"),
                    }
                if isinstance(second, dict):
                    payload["second_attempt"] = {
                        "proposed_text": second.get("proposed_text"),
                        "rationale": second.get("rationale"),
                        "attempt": second.get("attempt"),
                    }
        await _audit_event(
            contract_id=contract_id,
            clause_id=cid,
            decision_type=DecisionType.REDLINE_GENERATED,
            payload=payload,
        )

    state.redlines = redlines

    # --- Step 5: render .docx ---------------------------------
    await _render_docx_into_state(state)

    # --- Step 6: graph_resumed lifecycle -----------------------
    await _audit_event(
        contract_id=contract_id,
        clause_id="",
        decision_type=DecisionType.GRAPH_RESUMED,
        payload={
            "thread_id": contract_id,
            "decisions_count": len(canonical),
            "redlines_count": sum(
                1 for r in redlines.values() if r.get("outcome") == "ok"
            ),
        },
    )

    return {
        "contract_id": contract_id,
        "decisions_count": len(canonical),
        "redlines_count": sum(
            1 for r in redlines.values() if r.get("outcome") == "ok"
        ),
        "docx_bytes": len(state.output_docx_bytes),
    }


async def _render_docx_into_state(state: PipelineRunState) -> None:
    """Render the .docx from the redlines and store the bytes.

    Mirrors the graph's ``assemble_output_node`` but
    without the LangGraph state plumbing. Reads
    ``state.clauses`` (text) and ``state.redlines``
    (proposals) and writes ``state.output_docx_bytes``.
    """
    accepted: list[tuple[str, RedlineProposal]] = []
    for cid, result in state.redlines.items():
        if not isinstance(result, dict):
            continue
        if result.get("outcome") != "ok":
            continue
        proposal_data = result.get("proposal") or {}
        try:
            proposal = RedlineProposal.model_validate(proposal_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "render_docx: dropping clause %s — malformed proposal: %s",
                cid,
                exc,
            )
            continue
        accepted.append((cid, proposal))

    if not accepted:
        state.output_docx_bytes = b""
        state.output_markdown_bytes = b""
        return

    clause_texts = [
        str(c.get("text", ""))
        for c in state.clauses
        if isinstance(c, dict) and c.get("text")
    ]
    baseline = "\n\n".join(clause_texts).strip()
    if not baseline:
        state.output_docx_bytes = b""
        state.output_markdown_bytes = b""
        return

    # The markdown path is the v0 escape hatch: same input
    # (contract baseline + accepted proposals), different
    # output format. We render it before the .docx so a
    # docx-render failure still leaves the markdown
    # available for download.
    try:
        from app.output.markdown_diff import render_markdown_diff

        md_text = await asyncio.to_thread(
            render_markdown_diff,
            baseline,
            accepted,
        )
        state.output_markdown_bytes = md_text.encode("utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "render_docx: markdown render failed for %s: %s",
            state.filename,
            exc,
        )
        state.output_markdown_bytes = b""

    try:
        from app.output.docx import render_redline_docx

        blob = await asyncio.to_thread(
            render_redline_docx,
            baseline,
            accepted,
            author="clausecraft",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_docx: docx render failed for %s: %s", state.filename, exc)
        state.output_docx_bytes = b""
        return

    state.output_docx_bytes = blob


__all__ = [
    "PipelineRunState",
    "get_state",
    "has_state",
    "reset_state",
    "snapshot_state",
    "normalise_decision",
    "process_decisions",
]
