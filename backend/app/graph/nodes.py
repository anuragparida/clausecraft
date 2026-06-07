"""Node definitions for the LangGraph pipeline.

Phase 0 ships a single ``echo_node`` that returns the input text
verbatim. Later phases will replace this with the real ingest →
classify → spot → aggregate → redline → HITL chain. Keeping the
``echo_node`` as the v0 graph lets the rest of the wiring (compile,
invoke, FastAPI endpoint) get exercised end-to-end before the real
agent logic lands.
"""

from __future__ import annotations

import logging

from app.graph.state import EchoState
from app.observability import _NoopLangfuse, is_tracing_enabled

logger = logging.getLogger(__name__)


def echo_node(state: EchoState) -> EchoState:
    """Trivial single-node graph: take ``text`` in, echo it back.

    This is the Phase 0 placeholder. It exercises the LangGraph
    runtime + FastAPI integration so later phases can swap node
    implementations without changing the surrounding plumbing.
    """
    text = state.get("text", "")
    logger.info("echo_node received %d characters", len(text))
    return {"text": text, "echoed": text}
