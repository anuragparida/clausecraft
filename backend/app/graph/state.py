"""State shape for the LangGraph contract-triage pipeline.

In Phase 0 the graph is a single "echo" node. Later phases extend the
state with clause lists, deviation flags, citation objects, and HITL
decisions. Keeping the state TypedDict-shaped (rather than Pydantic)
keeps LangGraph happy and serialization trivial.
"""

from __future__ import annotations

from typing import TypedDict


class EchoState(TypedDict, total=False):
    """Phase 0 state: one input string, one echoed output string."""

    text: str
    echoed: str
