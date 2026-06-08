"""Self-check loop for the redline drafter.

Re-runs the deviation spotter on the drafter's output. If the
spotter flags a new deviation, retries the drafter **once**
with an explicit constraint. If the second attempt also fails
the spotter, surfaces a :class:`RedlineConflict` to the user
with both attempts and the conflicting flags.

Hard rules (from the spec, non-negotiable):

1. **Cap retries at 1.** Spec line 285, verbatim: "Cap retries
   at 1; on the second failure, surface to the user with both
   attempts and the conflict." No third attempt, no temperature
   swap, no escalation through the model. The loop makes at most
   2 drafter calls per accepted flag.
2. **Reuse the deviation spotter, not a separate "spotter in
   self-check mode."** Same code path, same prompt, same
   behavior. The self-check loop calls
   :func:`app.agents.deviation_spotter.spotter.spot_clause` —
   no shortcut, no relaxed parser.
3. **The second failure surfaces a :class:`RedlineConflict` —
   NOT a :class:`RedlineProposal`.** The HITL UI (Build 5)
   consumes this in a "this redline couldn't be auto-drafted
   — pick one" view. We do NOT silently return one of the
   two attempts.

Why the conflict carries both attempts
--------------------------------------
The HITL state machine's job is to give the user a real
choice. Picking one attempt silently is a worse UX than
showing both — the user can see *what went wrong* (the
conflicting flags) and *what they got anyway* (both proposed
texts). The conflict object's ``first_proposal`` and
``second_proposal`` are the inputs the user picks between.

What "fails the spotter" means
------------------------------
We re-run the spotter on the **proposed text** as if it were
a contract clause. The spotter compares it against the SAME
baseline the drafter was rewriting toward. If the spotter
emits a flag with ``score > 0`` AND that flag's citation
points to a real baseline (i.e. ``unverified=False``), the
drafter's output failed the self-check. The rationale:
``unverified`` flags are not trustworthy enough to count as
"the drafter broke something" — they're "the spotter wasn't
sure, and the human should look."

We treat ``score=0`` (aligned) and ``unverified=True`` as
"the drafter succeeded." A misbehaving spotter that emits
``unverified=True`` on a clean rewrite is not the drafter's
fault.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from app.agents.deviation_spotter.schema import (
    BaselineForSpotter,
    DeviationFlag,
    SpotInput,
)
from app.agents.deviation_spotter.spotter import spot_clause
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
from app.observability import _NoopSpan, get_langfuse

logger = logging.getLogger(__name__)


# --- Self-check "did it pass" predicate --------------------------------


def _spotter_passes(flag: DeviationFlag) -> bool:
    """``True`` when the spotter's re-run says the rewrite is clean.

    "Clean" means:

    - ``score == 0`` (aligned) — the rewrite matches the
      baseline.
    - **OR** ``unverified is True`` — the spotter wasn't sure,
      but the drafter's output is not provably wrong. The HITL
      reviewer (or the user) decides.

    "Not clean" (``False``) means ``score > 0`` AND
    ``unverified is False`` — the spotter is confident the
    rewrite introduced a new deviation. That's the retry
    trigger.
    """
    if flag.score == 0:
        return True
    if flag.unverified:
        # Spotter wasn't sure; don't trigger a retry on uncertainty.
        return True
    return False


# --- The loop ----------------------------------------------------------


async def _run_spotter_on_proposed_text(
    *,
    clause_id: str,
    clause_type: str,
    proposed_text: str,
    baseline: BaselineForSpotter,
    contract_filename: str = "",
) -> DeviationFlag:
    """Re-run the deviation spotter on the drafter's output.

    Mirrors the production spotter call shape exactly: a
    :class:`SpotInput` with the proposed text + the same
    baseline the drafter was rewriting toward. The spotter's
    citation-enforcement logic runs unchanged, so an
    unverified flag surfaces correctly.

    We run the spotter in a thread (the spotter's public
    surface is sync, same as the drafter's). The thread-pool
    is the default executor — the self-check loop is per-flag,
    so the bound of 8 concurrent spots per loop is fine.
    """
    spot_input = SpotInput(
        clause_id=clause_id,
        clause_text=proposed_text,
        clause_type=clause_type,
        baselines=[baseline],
        counterparty_verdict="aligned",
        counterparty_type="any",
    )
    import asyncio

    return await asyncio.to_thread(
        spot_clause, spot_input, contract_filename=contract_filename
    )


async def run_with_self_check(
    drafter_input: DrafterInput,
    *,
    contract_filename: str = "",
) -> Union[RedlineProposal, RedlineConflict]:
    """Draft a redline and run the self-check loop. Returns
    either a :class:`RedlineProposal` (self-check passed) or
    a :class:`RedlineConflict` (both attempts failed).

    The loop:

    1. Calls :func:`draft_redline` (attempt 1).
    2. Re-runs the deviation spotter on ``proposal.proposed_text``.
    3. If the spotter says "clean" (``_spotter_passes`` →
       ``True``), return the proposal. Done.
    4. Otherwise, build a :class:`SelfCheckConstraint` from
       the first attempt + the spotter's flag, and call
       :func:`draft_redline` again (attempt 2). The prompt
       injects the constraint; the drafter rewrites the
       clause with the conflict in mind.
    5. Re-run the spotter on attempt 2's output.
    6. If the spotter says "clean", return attempt 2. Done.
    7. Otherwise, build a :class:`RedlineConflict` carrying
       both proposals and both conflicting spotter flags.
       Return the conflict. Done.

    The Langfuse trace for the loop is a single
    ``redline_draft_with_self_check`` span with two child
    generations (one per drafter call). The retry's tag
    (``"self_check_retry"``) lets the eval harness filter
    the Langfuse UI to retry attempts only.

    The spec is explicit: the loop raises
    :class:`DrafterUnavailable` from :func:`draft_redline` if
    the LLM is unreachable. We do NOT catch that here — the
    HITL state machine (Build 3) catches it and marks the
    flag's redline status as ``"unavailable"``. The
    self-check loop is only responsible for the
    "LLM is up, but the rewrite is bad" case.
    """
    langfuse = get_langfuse()
    span: Any = _NoopSpan()
    tags: list[str] = []
    if contract_filename:
        tags.append(contract_filename)
    try:
        span = langfuse.trace(
            name="redline_draft_with_self_check",
            tags=tags,
            input={
                "clause_id": drafter_input.flag.clause_id,
                "flag_score": drafter_input.flag.score,
                "baseline_clause_id": drafter_input.baseline.clause_id,
                "clause_length": len(drafter_input.clause_text),
            },
        )
    except Exception:  # noqa: BLE001
        span = _NoopSpan()

    # --- Attempt 1 --------------------------------------------------
    first_proposal = await draft_redline(
        drafter_input, contract_filename=contract_filename
    )
    first_conflict = await _run_spotter_on_proposed_text(
        clause_id=drafter_input.flag.clause_id,
        clause_type=drafter_input.flag.baseline_type or "unknown",
        proposed_text=first_proposal.proposed_text,
        baseline=drafter_input.baseline,
        contract_filename=contract_filename,
    )
    if _spotter_passes(first_conflict):
        _finish_loop_trace(
            span,
            outcome="first_pass",
            attempts=1,
            first_proposal=first_proposal,
            second_proposal=None,
            first_conflict=first_conflict,
            second_conflict=None,
        )
        return first_proposal

    # --- Attempt 2 (the one allowed retry) --------------------------
    constraint = SelfCheckConstraint(
        previous_proposed_text=first_proposal.proposed_text,
        conflicting_flag=first_conflict,
    )
    second_proposal = await draft_redline(
        drafter_input,
        self_check_constraint=constraint,
        contract_filename=contract_filename,
    )
    # The drafter's `attempt` field is 2 by construction (we
    # passed the constraint). Pydantic enforces ge=1, le=2;
    # the drafter sets it explicitly when the constraint is
    # present. Defensive assertion in case the drafter's
    # contract changes.
    if second_proposal.attempt != 2:
        # Should never happen; keep the invariant honest.
        second_proposal = second_proposal.model_copy(update={"attempt": 2})

    second_conflict = await _run_spotter_on_proposed_text(
        clause_id=drafter_input.flag.clause_id,
        clause_type=drafter_input.flag.baseline_type or "unknown",
        proposed_text=second_proposal.proposed_text,
        baseline=drafter_input.baseline,
        contract_filename=contract_filename,
    )
    if _spotter_passes(second_conflict):
        _finish_loop_trace(
            span,
            outcome="second_pass",
            attempts=2,
            first_proposal=first_proposal,
            second_proposal=second_proposal,
            first_conflict=first_conflict,
            second_conflict=second_conflict,
        )
        return second_proposal

    # --- Both attempts failed — surface the conflict -----------------
    logger.info(
        "redline conflict for %s: both attempts failed the self-check "
        "(first score=%d, second score=%d)",
        drafter_input.flag.clause_id,
        first_conflict.score,
        second_conflict.score,
    )
    conflict = RedlineConflict(
        first_proposal=first_proposal,
        second_proposal=second_proposal,
        first_conflict=first_conflict,
        second_conflict=second_conflict,
    )
    _finish_loop_trace(
        span,
        outcome="conflict",
        attempts=2,
        first_proposal=first_proposal,
        second_proposal=second_proposal,
        first_conflict=first_conflict,
        second_conflict=second_conflict,
    )
    return conflict


def _finish_loop_trace(
    span: Any,
    *,
    outcome: str,
    attempts: int,
    first_proposal: RedlineProposal,
    second_proposal: Optional[RedlineProposal],
    first_conflict: DeviationFlag,
    second_conflict: Optional[DeviationFlag],
) -> None:
    """Update the Langfuse span with the loop's outcome.

    ``outcome`` is one of ``"first_pass"``, ``"second_pass"``,
    ``"conflict"``. The eval harness can filter on this to
    measure retry rate + conflict rate separately.
    """
    try:
        if hasattr(span, "update"):
            span.update(
                output={
                    "outcome": outcome,
                    "attempts": attempts,
                    "first_attempt_score": first_conflict.score,
                    "first_attempt_unverified": first_conflict.unverified,
                    "second_attempt_score": (
                        second_conflict.score if second_conflict is not None else None
                    ),
                    "second_attempt_unverified": (
                        second_conflict.unverified
                        if second_conflict is not None
                        else None
                    ),
                },
            )
        if hasattr(span, "end"):
            span.end()
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "run_with_self_check",
    # Re-exported for tests and the HITL state machine:
    "DrafterUnavailable",
]
