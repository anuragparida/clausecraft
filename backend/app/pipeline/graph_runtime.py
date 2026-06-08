"""Runtime + audit helpers for the Phase 3 HITL graph.

Owns the connection-string translation, the per-test saver
context manager, the audit-event helper, and the public driver
(compile-once compiled graph + per-test compile helper).

The actual node implementations live in :mod:`.graph_nodes`,
the graph topology in :mod:`.graph`. Splitting the three
concerns keeps the node bodies short and the test fixtures
easy to swap.

Why the runtime is async
------------------------

The pipeline's LLM-bound nodes (spot, redline) make
concurrent calls. The Postgres checkpoint saver must be
async too -- ``AsyncPostgresSaver`` is the only Postgres
saver that integrates cleanly with an async graph. The
sync ``PostgresSaver`` would block the event loop on every
checkpoint write and serialise the LLM calls.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.audit import AuditEvent, DecisionType, record_event
from app.config import settings
from app.pipeline.graph_state import PipelineState

logger = logging.getLogger(__name__)


# --- Connection helpers ------------------------------------------------


def _psycopg_conn_string() -> str:
    """Translate the async SQLAlchemy URL into a psycopg string.

    LangGraph's :class:`AsyncPostgresSaver` uses ``psycopg``
    (v3) natively. Our settings are async-SQLAlchemy
    (``asyncpg``); we just swap the driver prefix.

    If the env provides a literal
    ``LANGGRAPH_CHECKPOINT_URL`` we use that as-is -- it's
    an escape hatch for "I want the checkpointer to talk
    to a different Postgres than the app's data" use cases
    (e.g. a separate metrics DB).
    """
    override = os.environ.get("LANGGRAPH_CHECKPOINT_URL")
    if override:
        return override
    return settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql://"
    )


@asynccontextmanager
async def _saver() -> AsyncIterator[AsyncPostgresSaver]:
    """Yield a connected :class:`AsyncPostgresSaver`.

    Sets up the checkpoint tables on first use (idempotent
    -- see ``PostgresSaver.setup``). The context manager
    holds the connection open for the lifetime of the
    graph; closing it ends the process's ability to
    resume.
    """
    async with AsyncPostgresSaver.from_conn_string(
        _psycopg_conn_string()
    ) as saver:
        await saver.setup()
        yield saver


# --- Audit helpers -----------------------------------------------------


async def _audit(
    state: PipelineState,
    *,
    decision_type: DecisionType,
    clause_id: str = "",
    payload: Optional[dict[str, Any]] = None,
) -> PipelineState:
    """Append a single audit event AND bump the in-state counter.

    Returns a new state dict with ``audit_event_count``
    incremented and the rest of the state unchanged. Nodes
    use the return value when constructing the LangGraph
    state update (the convention is "return a partial
    dict, the graph merges").

    The ``payload`` argument is forwarded verbatim into
    ``AuditEvent.payload_json`` -- a node-specific dict
    (e.g. ``{"score": 2, "rationale": "..."}``). When
    ``payload`` is None we serialise an empty dict.
    """
    contract_id = state.get("contract_id", "<unknown>")
    event = AuditEvent(
        contract_id=contract_id,
        clause_id=clause_id,
        decision_type=decision_type,
        payload_json=payload or {},
    )
    try:
        await record_event(event)
        incremented = int(state.get("audit_event_count", 0)) + 1
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "audit write failed for contract=%s clause=%s type=%s: %s",
            contract_id,
            clause_id or "<pipeline>",
            decision_type,
            exc,
        )
        incremented = int(state.get("audit_event_count", 0))
    return {"audit_event_count": incremented}


async def _audit_lifecycle(
    state: PipelineState,
    *,
    decision_type: DecisionType,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Audit-event helper for the graph's lifecycle markers.

    Used by the resume path (``GRAPH_RESUMED``) and the
    initial-start path (``GRAPH_STARTED``). Unlike
    :func:`_audit`, this helper does NOT update the state --
    the lifecycle markers do not need to be reflected in
    the counter, only in the audit table.

    The ``extra`` dict is merged into the payload (the
    ``thread_id`` is always included).
    """
    contract_id = state.get("contract_id", "<unknown>")
    payload = {"thread_id": contract_id}
    if extra:
        payload.update(extra)
    try:
        await record_event(
            AuditEvent(
                contract_id=contract_id,
                decision_type=decision_type,
                payload_json=payload,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "lifecycle audit write failed for contract=%s type=%s: %s",
            contract_id,
            decision_type,
            exc,
        )


# --- Public driver -----------------------------------------------------


_compiled_pipeline: Optional[Any] = None
_compiled_pipeline_lock = asyncio.Lock()


async def get_compiled_pipeline() -> Any:
    """Return the compiled graph (compiled once per process).

    The compiled graph holds a reference to the
    AsyncPostgresSaver context manager. Closing the saver
    would orphan the compiled graph's checkpointer, so we
    keep it open for the process lifetime. Tests that need
    a fresh saver call :func:`build_pipeline_for_test`
    instead.
    """
    global _compiled_pipeline
    if _compiled_pipeline is not None:
        return _compiled_pipeline
    async with _compiled_pipeline_lock:
        if _compiled_pipeline is not None:
            return _compiled_pipeline
        from app.pipeline.graph import _build_graph

        builder = _build_graph()
        async with _saver() as saver:
            _compiled_pipeline = builder.compile(checkpointer=saver)
        logger.info(
            "Compiled Phase 3 HITL pipeline (6 nodes, Postgres checkpointer)"
        )
        return _compiled_pipeline


@asynccontextmanager
async def build_pipeline_for_test() -> AsyncIterator[Any]:
    """Compile a fresh graph for a single test.

    Each test gets its own context manager so the saver
    connection is closed when the test ends (no leaks
    between pytest-asyncio tests).
    """
    from app.pipeline.graph import _build_graph

    builder = _build_graph()
    async with _saver() as saver:
        compiled = builder.compile(checkpointer=saver)
        yield compiled


def new_thread_id() -> str:
    """Generate a stable thread id for a new contract."""
    return f"thr-{uuid.uuid4()}"


def build_initial_state(
    *,
    contract_id: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> PipelineState:
    """Build the initial state for a new pipeline invocation."""
    return {
        "contract_id": contract_id,
        "filename": filename,
        "content_type": content_type,
        "file_bytes": file_bytes,
        "audit_event_count": 0,
    }


__all__ = [
    "get_compiled_pipeline",
    "build_pipeline_for_test",
    "build_initial_state",
    "new_thread_id",
    "_audit",
    "_audit_lifecycle",
]
