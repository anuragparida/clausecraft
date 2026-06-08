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
    -> interrupt_hitl
    -> apply_decisions
    -> draft_redlines
    -> assemble_output
    -> finalize
    -> END

The :func:`_build_graph` function returns a fresh
``StateGraph`` (uncompiled). The :mod:`.graph_runtime`
module compiles it with the Postgres checkpointer and
caches the compiled object.

Why a separate topology file
----------------------------

A reviewer verifying the graph structure (the spec's
"ingest -> parse -> classify -> spot -> interrupt -> redline
-> output -> audit" chain) can read this file in one pass.
The node bodies are deferred to :mod:`.graph_nodes` so the
topology stays a single screenful.

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
    ingest_parse_classify_node,
    interrupt_hitl_node,
    spot_deviations_node,
)
from app.pipeline.graph_state import PipelineState


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
    builder.add_node("interrupt_hitl", interrupt_hitl_node)
    builder.add_node("apply_decisions", apply_decisions_node)
    builder.add_node("draft_redlines", draft_redlines_node)
    builder.add_node("assemble_output", assemble_output_node)
    builder.add_node("finalize", finalize_node)

    # Edges — strictly linear. The interrupt node uses
    # ``langgraph.types.interrupt`` to pause; the resume
    # is via a separate ``Command(resume=...)`` call.
    builder.add_edge(START, "ingest_parse_classify")
    builder.add_edge("ingest_parse_classify", "spot_deviations")
    builder.add_edge("spot_deviations", "interrupt_hitl")
    builder.add_edge("interrupt_hitl", "apply_decisions")
    builder.add_edge("apply_decisions", "draft_redlines")
    builder.add_edge("draft_redlines", "assemble_output")
    builder.add_edge("assemble_output", "finalize")
    builder.add_edge("finalize", END)

    return builder


__all__ = ["_build_graph"]
