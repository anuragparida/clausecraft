"""LangGraph topology for the Phase 3 HITL pipeline.

Defines the graph's nodes and edges. The actual node bodies
live in :mod:`.graph_nodes`; the runtime + audit helpers in
:mod:`.graph_runtime`. This module is purely structural.

Topology
--------

::

  START
    -> ingest_parse_classify
    -> spot_deviations
    -> hitl_review              (new in card t_0671d337 — typed interrupt)
    -> apply_decisions          (legacy: dict-keyed)
    -> draft_redlines           (legacy: dict-keyed)
    -> stage5_redline           (new in card t_0671d337 — typed state path)
    -> assemble_output
    -> flush_audit_log_writes   (new in card t_0671d337 — drain queue)
    -> finalize
    -> END

The :func:`_build_graph` function returns a fresh
``StateGraph`` (uncompiled). The :mod:`.graph_runtime`
module compiles it with the Postgres checkpointer and
caches the compiled object.

Why the topology grew from 7 to 9 nodes
---------------------------------------
The card ``t_0671d337`` (Build: HITL state machine —
LangGraph interrupt) re-decomposes Build 3 to add a typed
HITL state path. The original 7-node graph (Build 3) is
the "thin" implementation: ``interrupt_hitl_node`` is a
raw LangGraph ``interrupt()`` call + a hand-rolled dict
validation. The new ``hitl_review_node`` (Build 3
re-decomposition) is the typed implementation:

- Decision batch is Pydantic-validated into
  :class:`FlagDecision` instances.
- ``flag_decisions`` / ``severity_overrides`` /
  ``redline_proposals`` typed state fields are populated.
- Audit log writes are QUEUED in
  ``state.audit_log_writes`` (the spec's "audit log writes
  are queued in state, not directly called" hard rule) and
  drained at the END of the run by
  :func:`app.pipeline.graph_nodes.flush_audit_log_writes_node`.

The two paths are not in conflict. ``hitl_review_node``
runs first (it owns the typed state). The legacy
``apply_decisions_node`` + ``draft_redlines_node`` read
from the backward-compat ``state.decisions`` /
``state.redlines`` fields that ``hitl_review_node``
populates alongside the typed fields. The new
``stage5_redline`` runs *after* the legacy redline node
and populates ``state.redline_proposals`` (the typed
equivalent of ``state.redlines``).

Error routing
-------------
If a node sets ``error`` in the state, the graph still
reaches END — the checkpoint is durable. The graph does
NOT short-circuit on error (LangGraph doesn't have a
"fail-fast" edge; the convention is to put the error in
the state and let the API layer render it). The
``finalize`` node writes the audit summary even when
``error`` is set so the audit replay view shows "the graph
reached END, here is what happened."
"""

from __future__ import annotations


from langgraph.graph import END, START, StateGraph

from app.pipeline.graph_nodes import (
    apply_decisions_node,
    assemble_output_node,
    draft_redlines_node,
    finalize_node,
    flush_audit_log_writes_node,
    hitl_review_node,
    ingest_parse_classify_node,
    spot_deviations_node,
)
from app.pipeline.graph_state import PipelineState
from app.pipeline.stage5_redline import run_stage5


def _build_graph() -> StateGraph:
    """Build a fresh, uncompiled StateGraph.

    Each call returns a NEW ``StateGraph`` object — the
    runtime module compiles the result with a
    checkpointer, and we don't want to share a compiled
    graph across processes (the checkpointer holds a
    Postgres connection). The compiled graph is cached at
    module level in :mod:`.graph_runtime`.
    """
    builder: StateGraph = StateGraph(PipelineState)

    # Nodes
    builder.add_node("ingest_parse_classify", ingest_parse_classify_node)
    builder.add_node("spot_deviations", spot_deviations_node)
    # The new typed HITL node. Runs AFTER the spot stage
    # and BEFORE the redline stage (per the card spec:
    # "wired into graph.py between the spot stage (stage3)
    # and the redline stage (stage5)"). The legacy
    # ``interrupt_hitl_node`` is NOT in the topology
    # (the typed node supersedes it for new runs); the
    # legacy node still exists for backward compat with
    # existing call sites + tests.
    builder.add_node("hitl_review", hitl_review_node)
    # Legacy nodes. The card explicitly says: "The new
    # node ``hitl_review_node`` is wired into ``graph.py``
    # between the spot stage (stage3) and the redline
    # stage (stage5)" — the legacy ``interrupt_hitl`` is
    # replaced by ``hitl_review``. The legacy apply /
    # draft are kept because they read from the
    # backward-compat ``state.decisions`` /
    # ``state.redlines`` fields that ``hitl_review``
    # populates. The new stage5_redline node is the
    # typed-state path that reads from
    # ``state.flag_decisions`` and writes to
    # ``state.redline_proposals``.
    builder.add_node("apply_decisions", apply_decisions_node)
    builder.add_node("draft_redlines", draft_redlines_node)
    builder.add_node("stage5_redline", _stage5_node)
    builder.add_node("assemble_output", assemble_output_node)
    # The new flush node drains the queued audit log
    # writes (the spec's "audit log writes are queued in
    # state, not directly called" hard rule). Runs
    # IMMEDIATELY BEFORE the finalize node so the queue
    # is drained before the graph reaches END.
    builder.add_node("flush_audit_log_writes", flush_audit_log_writes_node)
    builder.add_node("finalize", finalize_node)

    # Edges — strictly linear. The interrupt node uses
    # ``langgraph.types.interrupt`` to pause; the resume
    # is via a separate ``Command(resume=...)`` call.
    builder.add_edge(START, "ingest_parse_classify")
    builder.add_edge("ingest_parse_classify", "spot_deviations")
    builder.add_edge("spot_deviations", "hitl_review")
    builder.add_edge("hitl_review", "apply_decisions")
    builder.add_edge("apply_decisions", "draft_redlines")
    builder.add_edge("draft_redlines", "stage5_redline")
    builder.add_edge("stage5_redline", "assemble_output")
    builder.add_edge("assemble_output", "flush_audit_log_writes")
    builder.add_edge("flush_audit_log_writes", "finalize")
    builder.add_edge("finalize", END)

    return builder


async def _stage5_node(state: PipelineState) -> PipelineState:
    """Thin LangGraph wrapper around :func:`stage5_redline.run_stage5`.

    LangGraph's :class:`StateGraph` expects a coroutine
    that takes + returns a state dict. The stage function
    is already that shape; this wrapper is a single-line
    pass-through to keep the topology file as the single
    source of truth for node wiring (a reviewer checking
    the graph can read this file in one pass).
    """
    return await run_stage5(state)


__all__ = ["_build_graph"]
