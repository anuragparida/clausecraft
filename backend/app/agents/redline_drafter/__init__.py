"""Redline drafter — the second real agent (Phase 3).

The drafter rewrites a single accepted-deviation clause so it
aligns with the matched playbook baseline. It takes a
:class:`DrafterInput` (an accepted :class:`DeviationFlag` plus
the clause text and the baseline clause) and returns a
:class:`RedlineProposal` (``proposed_text``, ``rationale``,
``diff_summary``).

The agent ships a self-check loop (:mod:`.self_check`) that
re-runs the deviation spotter on the proposed text. If the
spotter flags a new deviation, the drafter retries **once**
with an explicit constraint injected into the prompt. If the
second attempt also fails the spotter, the loop returns a
:class:`RedlineConflict` carrying both attempts' text and the
conflicting spotter flags — the HITL UI (Build 5) renders this
as a "this redline couldn't be auto-drafted — pick one" view.

Why this is a separate agent (not a stage in the pipeline)
----------------------------------------------------------
The redline drafter is a per-flag action, not a per-contract
one. The HITL state machine (Build 3) calls
:func:`self_check.run_with_self_check` once per accepted flag.
Keeping the agent decoupled from the pipeline lets the HITL
state machine reason about individual redline attempts without
coupling to the stage orchestration.

Public surface
--------------
- :class:`RedlineProposal` — the drafter's happy-path output.
- :class:`RedlineConflict` — the "couldn't auto-draft" output
  carrying both attempts and the conflicting spotter flags.
- :class:`DrafterInput` — the agent's typed input.
- :func:`drafter.draft_redline` — the single-call LLM entry
  point (returns :class:`RedlineProposal` only; no self-check).
- :func:`self_check.run_with_self_check` — the self-check loop
  wrapping :func:`drafter.draft_redline`.
"""

from app.agents.redline_drafter.drafter import (
    DrafterUnavailable,
    draft_redline,
)
from app.agents.redline_drafter.schema import (
    DrafterInput,
    RedlineConflict,
    RedlineProposal,
    SelfCheckConstraint,
)
from app.agents.redline_drafter.self_check import run_with_self_check

__all__ = [
    "DrafterInput",
    "DrafterUnavailable",
    "RedlineConflict",
    "RedlineProposal",
    "SelfCheckConstraint",
    "draft_redline",
    "run_with_self_check",
]
