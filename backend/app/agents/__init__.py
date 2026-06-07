"""Agents package — Phase 2 introduces the first real agent.

Phase 2 ships one agent: :mod:`app.agents.deviation_spotter`. Phase 3
adds the redline drafter, Phase 5 adds the counterparty-aware router.

Agents are *not* pipeline stages — they take a typed input (a
:class:`~app.classify.Clause` plus context) and return a typed
output (here, a :class:`~app.agents.deviation_spotter.DeviationFlag`).
The pipeline (``app.pipeline.stage3_spot``) is the orchestrator that
calls the agent per clause.

Why a separate ``agents/`` directory and not ``agents/deviation_spotter``
sitting under ``pipeline/``: the spec calls out the spotter as the
"first real agent" — the code shape should reflect that. Each agent
is a self-contained package with ``schema`` (typed I/O), ``prompt``
(system + per-call messages), and ``spotter`` (the LLM call +
parsing). The eval harness compares the agent's output against the
golden set; Helena reviews the prompt and the citation-enforcement
logic.
"""

from app.agents.deviation_spotter.schema import (
    Citation,
    DeviationFlag,
    SpotInput,
)

__all__ = [
    "Citation",
    "DeviationFlag",
    "SpotInput",
]
