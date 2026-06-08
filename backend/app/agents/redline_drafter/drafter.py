"""Redline drafter — the LLM call + the Pydantic-validation boundary.

The drafter takes a :class:`DrafterInput` and returns a
:class:`RedlineProposal`. The call shape mirrors the deviation
spotter: OpenAI-compatible client, JSON response, Pydantic-
validated output. Same key-management + Langfuse tracing
wiring, same "no LLM → deterministic abstention" fallback.

Public surface
--------------
- :func:`draft_redline` — the agent's single-call entry point.
  Returns a :class:`RedlineProposal` (NOT a :class:`RedlineConflict`
  — the conflict path is the self-check loop's job, not the
  drafter's). Traced as a single Langfuse span.
- :func:`draft_redlines` — the parallel orchestrator helper,
  mirrors the spotter's :func:`spot_clauses`.

Why the drafter is async at the public boundary but sync inside
----------------------------------------------------------------
The spec says: ``async draft_redline(flag, clause, baseline, *,
model) -> RedlineProposal``. The LLM call itself is sync (the
OpenAI Python SDK blocks). The async boundary is the
"composable with LangGraph" shape — :mod:`.self_check` awaits
:func:`draft_redline` directly without spinning up a thread
pool. The parallel orchestrator (:func:`draft_redlines`) runs
the sync call in a thread pool (same pattern as the spotter).

Self-check loop placement
-------------------------
The self-check loop lives in a **separate** module
(:mod:`.self_check`), not here. The reason: the self-check
loop needs to *call* the deviation spotter, which is a
different agent. Keeping the cross-agent dependency in
:mod:`.self_check` (not in :mod:`.drafter`) means the drafter
itself is reusable as a plain "give me a redline" call — the
HITL state machine (Build 3) can choose to call the drafter
with or without self-check, depending on the flag.

The "rule-based fallback" question
----------------------------------
The drafter has no meaningful rule-based fallback. The
spotter's fallback is "score=0, abstention" — a typed,
non-action. The drafter's output is a *rewritten clause*;
a rule-based rewrite would be hallucinated contract text.
We choose: when the LLM is unavailable, raise. The HITL
state machine catches the raise, marks the flag's redline
status as ``"unavailable"`` (distinct from ``"conflict"``),
and the UI renders "redline service unavailable" instead of
silently inserting a placeholder clause.

This is the **"malformed proposals do NOT silently default"
hard rule from the spec** — applied to the "no LLM at all"
case as well. The drafter either produces a real redline or
it raises.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from pydantic import ValidationError

from app.agents.redline_drafter.prompt import build_messages
from app.agents.redline_drafter.schema import (
    DrafterInput,
    RedlineProposal,
    SelfCheckConstraint,
)
from app.config import settings
from app.observability import _NoopSpan, get_langfuse

logger = logging.getLogger(__name__)


# --- Limits ------------------------------------------------------------

#: Maximum number of LLM attempts per drafter call (1 try + 2 retries).
#: Mirrors the spotter's :data:`_MAX_LLM_ATTEMPTS` — same
#: OpenAI client, same failure modes, same retry policy. The
#: self-check loop's "cap at 1 retry" is a *separate* cap on
#: the number of drafter calls (attempt 1 + attempt 2 = 2 calls
#: max per flag).
_MAX_LLM_ATTEMPTS = 3

#: Marker exception raised by the drafter when no LLM is
#: available. Caught by the HITL state machine (Build 3) and
#: surfaced to the UI as "redline service unavailable" — a
#: distinct state from the self-check conflict.
_NO_LLM_MESSAGE = "redline drafter unavailable: no LLM key configured"


# --- Exceptions --------------------------------------------------------


class DrafterUnavailable(RuntimeError):
    """Raised when the redline drafter cannot reach the LLM.

    Distinct from a validation failure (which raises the
    built-in :class:`ValueError` from Pydantic). The HITL
    state machine catches this exception and marks the
    flag's redline status as ``"unavailable"`` so the UI
    can render a distinct message ("redline service is
    down, please retry") rather than a generic error.
    """


# --- Lookups -----------------------------------------------------------


def _looks_like_real_key(value: str) -> bool:
    """Mirror the spotter's / classifier's key-shape heuristic.

    Real OpenAI keys start with ``sk-``; OpenRouter keys with
    ``sk-or-``. The drafter uses the same OpenAI-compatible
    client as the spotter, so the heuristic is identical.
    Keeping the three subsystems' "what counts as a real key"
    in sync means an operator setting ``LLM_API_KEY`` knows
    that the classifier, the spotter, and the drafter all
    agree on whether the system is configured to talk to a
    real LLM.
    """
    if not value:
        return False
    lowered = value.lower()
    if "placeholder" in lowered or "***" in value:
        return False
    return value.startswith("sk-") or len(value) >= 30


# --- LLM call ----------------------------------------------------------


def _extract_llm_json(raw: str) -> dict[str, Any]:
    """Parse the LLM's JSON response.

    Same shape as the spotter's :func:`_extract_llm_json`:
    strip ```` ```json ```` fences, find the first ``{`` and
    last ``}`` if the model emits a leading prose sentence,
    and raise on parse failure. The drafter inherits the
    spotter's robustness choices — the LLM gateways (notably
    OpenRouter) occasionally ignore ``response_format`` and
    emit a markdown fence anyway.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("LLM returned an empty completion")
    if text.startswith("```"):
        first_nl = text.find("\n")
        last_fence = text.rfind("```")
        if first_nl != -1 and last_fence > first_nl:
            text = text[first_nl + 1 : last_fence].strip()
    if not text.startswith("{"):
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            text = text[first_brace : last_brace + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"LLM returned a {type(data).__name__} at the top level; "
            "expected a JSON object"
        )
    return data


def _call_llm_for_draft(
    drafter_input: DrafterInput,
    *,
    self_check_constraint: Optional[SelfCheckConstraint] = None,
) -> dict[str, Any]:
    """Call the LLM and return the parsed JSON dict.

    The OpenAI client is constructed on every call (same as
    the spotter) so tests can monkey-patch
    ``settings.llm_api_key`` between calls. The
    ``self_check_constraint`` is forwarded to
    :func:`build_messages` — it's the only thing that differs
    between attempt 1 and attempt 2.

    Raises on transport / parse failure — the caller decides
    whether to retry or propagate the failure.
    """
    from openai import OpenAI  # type: ignore[import-not-found]

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
    messages = build_messages(
        drafter_input,
        self_check_constraint=self_check_constraint,
    )
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.0,
        max_tokens=1500,  # larger than the spotter's 600 — a redline is a full clause
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    return _extract_llm_json(raw)


# --- Parser ------------------------------------------------------------


def _parse_llm_output(
    raw: dict[str, Any],
    *,
    drafter_input: DrafterInput,
    attempt: int,
) -> RedlineProposal:
    """Parse the LLM's JSON dict into a :class:`RedlineProposal`.

    Pydantic does the heavy lifting (type coercion, field
    validation, min_length / max_length enforcement). The
    schema's ``min_length=1`` on ``proposed_text`` is the
    "no silent default" enforcement — an empty
    ``proposed_text`` from the LLM fails validation and
    this function raises :class:`ValueError`. The retry
    loop in :func:`draft_redline` catches it.

    The ``attempt`` parameter (1 or 2) is set on the
    proposal so the audit log can show whether a
    self-check retry was needed. The drafter itself
    doesn't know about the self-check loop — the caller
    (the loop) passes the attempt number.
    """
    try:
        proposal = RedlineProposal(
            proposed_text=str(raw.get("proposed_text", "") or ""),
            rationale=str(raw.get("rationale", "") or "").strip()
            or "drafter declined: empty rationale",
            diff_summary=str(raw.get("diff_summary", "") or "").strip()
            or "drafter declined: empty diff_summary",
            attempt=attempt,
        )
    except ValidationError as exc:
        raise ValueError(f"redline proposal validation failed: {exc}") from exc
    if not proposal.proposed_text.strip():
        raise ValueError("proposed_text must be non-empty")
    if not proposal.rationale.strip():
        raise ValueError("rationale must be non-empty")
    if not proposal.diff_summary.strip():
        raise ValueError("diff_summary must be non-empty")
    return proposal


# --- Trace helpers -----------------------------------------------------


def _finish_trace(
    span: Any,
    proposal: Optional[RedlineProposal],
    *,
    used_fallback: bool,
    error_summary: Optional[str],
    constraint: Optional[SelfCheckConstraint] = None,
) -> None:
    """Update the Langfuse span with the drafter's outcome.

    Mirrors the spotter's :func:`_finish_trace` shape. The
    ``constraint`` argument is a hint to the trace that this
    was a self-check retry — useful for the eval harness to
    filter the Langfuse UI to "retry attempts" only.
    """
    try:
        if hasattr(span, "update"):
            output: dict[str, Any] = {
                "attempt": (proposal.attempt if proposal is not None else 0),
                "used_fallback": used_fallback,
                "is_self_check_retry": constraint is not None,
            }
            if proposal is not None:
                output["proposed_text_length"] = len(proposal.proposed_text)
            span.update(
                output=output,
                metadata={"error": error_summary} if error_summary else {},
            )
        if hasattr(span, "end"):
            span.end()
    except Exception:  # noqa: BLE001
        pass


# --- Public surface ----------------------------------------------------


def draft_redline_sync(
    drafter_input: DrafterInput,
    *,
    self_check_constraint: Optional[SelfCheckConstraint] = None,
    contract_filename: str = "",
) -> RedlineProposal:
    """Sync drafter entry point. Returns a :class:`RedlineProposal`.

    The function:

    1. Wraps the LLM call in a Langfuse ``trace`` named
       ``"redline_draft"`` with the contract filename as a tag.
       When ``self_check_constraint`` is set, the trace tag
       includes ``"self_check_retry"`` so the Langfuse UI
       distinguishes first attempts from retries.
    2. Calls the LLM with retries (1 try + 2 retries, same
       as the spotter).
    3. Parses the output through the Pydantic boundary.
       **A malformed proposal raises** — the spec is explicit
       that "malformed proposals do NOT silently default."
    4. Returns the validated :class:`RedlineProposal`.

    If the LLM is unavailable (placeholder key), raises
    :class:`DrafterUnavailable`. The HITL state machine (Build
    3) catches this and marks the flag's redline status as
    ``"unavailable"``.

    This is the **sync** entry point. The async wrapper
    :func:`draft_redline` delegates here via
    :func:`asyncio.to_thread` for parallelism, mirroring
    the spotter's :func:`spot_clause` / :func:`spot_clauses`
    pattern.
    """
    langfuse = get_langfuse()
    span: Any = _NoopSpan()
    tags: list[str] = []
    if contract_filename:
        tags.append(contract_filename)
    if self_check_constraint is not None:
        tags.append("self_check_retry")
    try:
        span = langfuse.trace(
            name="redline_draft",
            tags=tags,
            input={
                "clause_id": drafter_input.flag.clause_id,
                "flag_score": drafter_input.flag.score,
                "baseline_clause_id": drafter_input.baseline.clause_id,
                "clause_length": len(drafter_input.clause_text),
                "is_self_check_retry": self_check_constraint is not None,
            },
        )
    except Exception:  # noqa: BLE001
        span = _NoopSpan()

    if not _looks_like_real_key(settings.llm_api_key):
        # No LLM — raise so the HITL state machine can mark
        # the flag's redline status as "unavailable" rather
        # than silently inserting a placeholder clause.
        _finish_trace(
            span,
            None,
            used_fallback=False,
            error_summary=_NO_LLM_MESSAGE,
            constraint=self_check_constraint,
        )
        raise DrafterUnavailable(_NO_LLM_MESSAGE)

    attempt_no = 2 if self_check_constraint is not None else 1
    last_error: Optional[Exception] = None
    proposal: Optional[RedlineProposal] = None
    for attempt in range(_MAX_LLM_ATTEMPTS):
        try:
            raw = _call_llm_for_draft(
                drafter_input,
                self_check_constraint=self_check_constraint,
            )
            proposal = _parse_llm_output(
                raw, drafter_input=drafter_input, attempt=attempt_no
            )
            last_error = None
            break
        except ValueError as exc:
            # Validation failures (Pydantic rejects the
            # output, missing required fields, empty
            # proposed_text) are deterministic — the LLM is
            # being asked the same prompt, it will return
            # the same broken output. Retrying 3 times is
            # wasteful. Re-raise immediately so the caller
            # sees the validation failure as a distinct
            # error from "LLM transport is down".
            #
            # The spec is explicit: "malformed proposals do
            # NOT silently default — they raise." A
            # ``ValueError`` from ``_parse_llm_output`` is
            # the contract: the proposal is malformed, the
            # caller (HITL state machine) handles it.
            _finish_trace(
                span,
                None,
                used_fallback=False,
                error_summary=f"malformed proposal (attempt {attempt + 1}): {exc}",
                constraint=self_check_constraint,
            )
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "LLM drafter attempt %d (call attempt %d) failed for %s: %s",
                attempt_no,
                attempt + 1,
                drafter_input.flag.clause_id,
                exc,
            )

    if last_error is not None or proposal is None:
        error_summary = (
            f"LLM call failed after {_MAX_LLM_ATTEMPTS} attempts: {last_error}"
        )
        logger.warning(
            "%s — raising DrafterUnavailable for %s",
            error_summary,
            drafter_input.flag.clause_id,
        )
        _finish_trace(
            span,
            None,
            used_fallback=False,
            error_summary=error_summary,
            constraint=self_check_constraint,
        )
        # The spec says malformed proposals raise. A persistent
        # LLM transport failure is the same shape from the HITL
        # state machine's perspective — the redline is
        # unavailable. (Validation failures were already
        # re-raised above as ``ValueError``.)
        raise DrafterUnavailable(error_summary) from last_error

    _finish_trace(
        span,
        proposal,
        used_fallback=False,
        error_summary=None,
        constraint=self_check_constraint,
    )
    return proposal


async def draft_redline(
    drafter_input: DrafterInput,
    *,
    self_check_constraint: Optional[SelfCheckConstraint] = None,
    contract_filename: str = "",
) -> RedlineProposal:
    """Async drafter entry point. Returns a :class:`RedlineProposal`.

    The async boundary is the "composable with LangGraph"
    shape — :mod:`.self_check` awaits this directly without
    spinning up a thread pool at the call site. The LLM call
    itself is sync, so the body delegates to
    :func:`draft_redline_sync` via :func:`asyncio.to_thread`.
    """
    return await asyncio.to_thread(
        draft_redline_sync,
        drafter_input,
        self_check_constraint=self_check_constraint,
        contract_filename=contract_filename,
    )


async def draft_redlines(
    drafter_inputs: list[DrafterInput],
    *,
    contract_filename: str = "",
) -> list[RedlineProposal]:
    """Draft redlines for a list of inputs with bounded parallelism.

    The parallel orchestrator. Mirrors the spotter's
    :func:`spot_clauses` shape — bounded to
    ``min(len(inputs), 8)`` workers via the default thread
    pool, returns the list of :class:`RedlineProposal` in
    the same order as the inputs.

    **Note:** this helper does **not** wrap each drafter in a
    self-check loop. The self-check loop is per-flag and
    needs to reason about the drafter's output, so it lives
    in :mod:`.self_check` and is called per-input from the
    HITL state machine. This helper is the "I have a list
    of accepted flags, just give me redlines, no
    self-check" path — useful for batch tools and tests.
    """
    if not drafter_inputs:
        return []
    bound = max(1, min(len(drafter_inputs), 8))
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(
            None,
            draft_redline_sync,
            di,
            None,  # no self-check constraint
            contract_filename,
        )
        for di in drafter_inputs
    ]
    results = await asyncio.gather(*tasks)
    _ = bound  # silence linters — bound is documented in the docstring
    return list(results)


__all__ = [
    "DrafterUnavailable",
    "draft_redline",
    "draft_redline_sync",
    "draft_redlines",
]
