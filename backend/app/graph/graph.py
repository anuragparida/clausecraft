"""LangGraph compiled graph — Phase 0 echo.

A real implementation in Phase 2+ will add edges for ingest,
classify, deviation-spot, aggregate, redline, and HITL. The
``compiled_graph`` object is the public surface used by the API
layer; everything else in this module is internal.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langgraph.graph import END, StateGraph

from app.graph.nodes import echo_node
from app.graph.state import EchoState

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_compiled_graph() -> Any:
    """Build + return the compiled graph. Cached for the process lifetime.

    The graph has exactly one node in Phase 0: ``echo``. Later phases
    will rebuild this in a more structured way (node-registration
    map, separate state schemas per pipeline stage). For v0 the
    literal one-node construction is the clearest demonstration that
    LangGraph is actually wired in.
    """
    builder = StateGraph(EchoState)
    builder.add_node("echo", echo_node)
    builder.set_entry_point("echo")
    builder.add_edge("echo", END)
    compiled = builder.compile()
    logger.info("Compiled LangGraph echo pipeline (1 node)")
    return compiled


def run_echo(text: str) -> str:
    """Invoke the graph synchronously and return the echoed text.

    Used by the FastAPI endpoint in Phase 0. Wraps the LangGraph
    ``invoke`` so callers don't have to know about the state schema.
    """
    graph = get_compiled_graph()
    result = graph.invoke({"text": text})
    return result.get("echoed", "")
