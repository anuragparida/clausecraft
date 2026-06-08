"""Tests for the redline drafter agent.

Three acceptance-criteria tests, mirroring the structure of
``tests/phase2/test_deviation_spotter.py``:

1. **Clean case.** ``draft_redline`` returns a
   :class:`RedlineProposal` with ``attempt=1`` for an
   LLM-stub that emits a well-formed JSON dict.
2. **Retry-once-then-succeed.** ``run_with_self_check``
   returns a :class:`RedlineProposal` with ``attempt=2`` when
   the first attempt fails the spotter's re-run and the
   second attempt passes. The drafter's two LLM calls are
   visible as distinct Langfuse spans (the second carries
   the ``"self_check_retry"`` tag).
3. **Retry-twice-fail (conflict).** ``run_with_self_check``
   returns a :class:`RedlineConflict` carrying both attempts
   when the first attempt fails the spotter and the second
   attempt also fails. The loop does **not** silently return
   one of the two — the conflict surfaces both.

Plus three extra coverage tests:

4. **Pydantic boundary.** The schema rejects a malformed
   proposal (empty ``proposed_text``) — the drafter raises,
   it does NOT silently default.
5. **No LLM → :class:`DrafterUnavailable`.** When the key is
   a placeholder, the drafter raises (it does not insert a
   hallucinated clause into the docx output).
6. **Cap-at-1 enforcement.** The loop does not call the
   drafter a third time. We assert the call count via the
   LLM stub's side-effect list.

Mocking strategy
----------------
We patch the LLM call with a controllable stub. For the
self-check loop tests, we patch BOTH the drafter's LLM call
and the spotter's LLM call (the self-check loop re-runs the
spotter). The spotter's stub returns different
:class:`DeviationFlag` values depending on which proposed
text it sees — that's how the test simulates "first attempt
failed, second passed" vs. "both failed".

Why async tests
---------------
The self-check loop is async (the spec says so, and the
drafter is async). The deviation-spotter tests in
``tests/phase2`` are sync because the spotter's public
surface is sync. We declare the async tests with
``@pytest.mark.asyncio`` and let ``pytest-asyncio``'s
session-scoped event loop handle the rest.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Ensure the backend package is importable when pytest is run
# from the repo root (same convention as tests/conftest.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.deviation_spotter.schema import (  # noqa: E402
    BaselineForSpotter,
    Citation,
    DeviationFlag,
)
from app.agents.redline_drafter import (  # noqa: E402
    DrafterInput,
    DrafterUnavailable,
    RedlineConflict,
    RedlineProposal,
    run_with_self_check,
)
from app.agents.redline_drafter.drafter import (  # noqa: E402
    draft_redline,
    draft_redline_sync,
)


# --- Fixtures -----------------------------------------------------------


def _baseline(
    clause_id: str = "term-of-confidentiality",
    type_: str = "term",
    similarity: float = 0.87,
) -> BaselineForSpotter:
    """A realistic-looking baseline for tests.

    Mirrors the shape of the Phase 2 NDA-EN
    ``term-of-confidentiality`` baseline so the spotter's
    citation-enforcement logic has a real clause_id to
    verify against.
    """
    return BaselineForSpotter(
        clause_id=clause_id,
        type=type_,
        title="Term of Confidentiality",
        text=(
            "Confidentiality obligations shall remain in effect for "
            "a period of three (3) years from the date of disclosure."
        ),
        source_url=(
            "https://nondisclosureagreement.com/blog/"
            "term-of-confidentiality/"
        ),
        similarity=similarity,
    )


def _flag(
    *,
    score: int = 2,
    clause_id: str = "c1",
    rationale: str = "Term of 7 years exceeds the baseline's 3-year maximum.",
) -> DeviationFlag:
    """A realistic-looking accepted flag for tests."""
    return DeviationFlag(
        clause_id=clause_id,
        score=score,
        rationale=rationale,
        citation=Citation(
            playbook_clause_id="term-of-confidentiality",
            contract_text_excerpt="period of seven (7) years",
        ),
        unverified=False,
        baseline_type="term",
    )


def _drafter_input(
    *,
    clause_text: str | None = None,
    baselines: BaselineForSpotter | None = None,
    flag: DeviationFlag | None = None,
) -> DrafterInput:
    """A realistic-looking drafter input for tests."""
    return DrafterInput(
        flag=flag or _flag(),
        clause_text=clause_text
        or (
            "The receiving party shall maintain confidentiality for a "
            "period of seven (7) years from the date of disclosure."
        ),
        baseline=baselines or _baseline(),
    )


def _stub_draft_payload(
    *,
    proposed_text: str = (
        "Confidentiality obligations shall remain in effect for a period "
        "of three (3) years from the date of disclosure."
    ),
    rationale: str = "Term of 7 years reduced to the baseline's 3-year maximum.",
    diff_summary: str = "Term: 7 years → 3 years. Other: unchanged.",
) -> dict[str, Any]:
    """Build a realistic LLM-output dict for the drafter stub."""
    return {
        "proposed_text": proposed_text,
        "rationale": rationale,
        "diff_summary": diff_summary,
    }


def _stub_spot_payload(
    *,
    score: int = 0,
    rationale: str = "Clause matches the baseline's term. No deviation.",
) -> dict[str, Any]:
    """Build a realistic LLM-output dict for the spotter stub.

    ``score=0`` is the "self-check passes" case. Tests that
    need "self-check fails" set ``score > 0`` and a real
    citation (so the spotter's enforcement does not flip
    ``unverified=True``).
    """
    return {
        "score": score,
        "rationale": rationale,
        "citation": (
            {
                "playbook_clause_id": "term-of-confidentiality",
                "contract_text_excerpt": "excerpt",
            }
            if score > 0
            else None
        ),
        "baseline_type": "term",
    }


# --- Test 1: clean case ------------------------------------------------


def test_draft_redline_returns_proposal_for_clean_case():
    """``draft_redline`` returns a ``RedlineProposal`` with ``attempt=1``.

    The LLM stub emits a well-formed JSON dict; the parser
    produces a :class:`RedlineProposal`; the async wrapper
    returns it. This is the "no self-check, no retry" happy
    path — what Build 5 (the HITL state machine) will call
    when it wants a plain "give me a redline" output.
    """
    di = _drafter_input()
    raw = _stub_draft_payload()

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        return_value=raw,
    ):
        proposal = draft_redline_sync(di, contract_filename="test.pdf")

    assert isinstance(proposal, RedlineProposal)
    assert proposal.attempt == 1
    assert "three (3) years" in proposal.proposed_text
    assert proposal.rationale
    assert proposal.diff_summary


# --- Test 2: retry-once-then-succeed -----------------------------------


@pytest.mark.asyncio
async def test_run_with_self_check_succeeds_on_first_attempt():
    """``run_with_self_check`` returns a ``RedlineProposal``
    on the first attempt when the spotter's re-run says "clean".

    The drafter stub returns the same well-formed JSON for
    both attempts (we only need one call here). The spotter
    stub returns ``score=0`` (aligned) — the self-check
    passes, the loop returns the first proposal.
    """
    di = _drafter_input()
    draft_raw = _stub_draft_payload()

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        return_value=draft_raw,
    ), patch(
        "app.agents.redline_drafter.self_check._run_spotter_on_proposed_text",
        return_value=DeviationFlag(
            clause_id=di.flag.clause_id,
            score=0,
            rationale="aligned",
            citation=None,
            unverified=False,
            baseline_type="term",
        ),
    ):
        result = await run_with_self_check(di, contract_filename="test.pdf")

    assert isinstance(result, RedlineProposal)
    assert result.attempt == 1
    assert "three (3) years" in result.proposed_text


@pytest.mark.asyncio
async def test_run_with_self_check_succeeds_on_retry():
    """First attempt fails the spotter; second attempt passes.

    The drafter is called twice (two LLM calls, two Langfuse
    spans). The spotter's re-run on attempt 1's output
    returns ``score=2, unverified=False`` (real deviation).
    The spotter's re-run on attempt 2's output returns
    ``score=0`` (clean). The loop returns attempt 2's
    proposal with ``attempt=2``.
    """
    di = _drafter_input()
    draft_raw_1 = _stub_draft_payload(
        proposed_text="first attempt — too aggressive",
        rationale="first try",
    )
    draft_raw_2 = _stub_draft_payload(
        proposed_text="second attempt — closer to baseline",
        rationale="second try",
    )
    spot_clean = DeviationFlag(
        clause_id=di.flag.clause_id,
        score=0,
        rationale="aligned",
        citation=None,
        unverified=False,
        baseline_type="term",
    )
    spot_dirty = DeviationFlag(
        clause_id=di.flag.clause_id,
        score=2,
        rationale="still deviates",
        citation=Citation(
            playbook_clause_id="term-of-confidentiality",
            contract_text_excerpt="still too long",
        ),
        unverified=False,
        baseline_type="term",
    )

    # The drafter's LLM stub returns different payloads on
    # successive calls — that's how we simulate the retry
    # producing different output.
    draft_call_log: list[int] = []

    def _draft_side_effect(*_args, **_kwargs):
        draft_call_log.append(len(draft_call_log) + 1)
        if len(draft_call_log) == 1:
            return draft_raw_1
        return draft_raw_2

    # The spotter's re-run stub returns "dirty" on the first
    # call (attempt 1's text) and "clean" on the second call
    # (attempt 2's text).
    spot_call_log: list[int] = []

    async def _spot_side_effect(**_kwargs):
        spot_call_log.append(len(spot_call_log) + 1)
        if len(spot_call_log) == 1:
            return spot_dirty
        return spot_clean

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        side_effect=_draft_side_effect,
    ), patch(
        "app.agents.redline_drafter.self_check._run_spotter_on_proposed_text",
        side_effect=_spot_side_effect,
    ):
        result = await run_with_self_check(di, contract_filename="test.pdf")

    # The loop called the drafter exactly twice (cap-at-1
    # enforcement) and the spotter exactly twice (once per
    # drafter output).
    assert len(draft_call_log) == 2, (
        f"Self-check loop should call the drafter exactly twice on a "
        f"first-attempt-fail path. Got {len(draft_call_log)} calls."
    )
    assert len(spot_call_log) == 2

    # The returned proposal is attempt 2 (the one that passed).
    assert isinstance(result, RedlineProposal)
    assert result.attempt == 2
    assert "second attempt" in result.proposed_text


# --- Test 3: retry-twice-fail (conflict) --------------------------------


@pytest.mark.asyncio
async def test_run_with_self_check_returns_conflict_when_both_attempts_fail():
    """Both drafter attempts fail the spotter → ``RedlineConflict``.

    The spec is explicit: the second-failure path returns a
    :class:`RedlineConflict` carrying BOTH attempts. We do
    NOT silently return one. The HITL UI consumes this
    conflict in Build 5.
    """
    di = _drafter_input()
    draft_raw_1 = _stub_draft_payload(
        proposed_text="first attempt — also bad",
        rationale="first try",
    )
    draft_raw_2 = _stub_draft_payload(
        proposed_text="second attempt — also bad",
        rationale="second try",
    )
    spot_dirty = DeviationFlag(
        clause_id=di.flag.clause_id,
        score=2,
        rationale="still deviates from the baseline",
        citation=Citation(
            playbook_clause_id="term-of-confidentiality",
            contract_text_excerpt="excerpt",
        ),
        unverified=False,
        baseline_type="term",
    )

    draft_call_log: list[int] = []

    def _draft_side_effect(*_args, **_kwargs):
        draft_call_log.append(len(draft_call_log) + 1)
        if len(draft_call_log) == 1:
            return draft_raw_1
        return draft_raw_2

    async def _spot_side_effect(**_kwargs):
        return spot_dirty

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        side_effect=_draft_side_effect,
    ), patch(
        "app.agents.redline_drafter.self_check._run_spotter_on_proposed_text",
        side_effect=_spot_side_effect,
    ):
        result = await run_with_self_check(di, contract_filename="test.pdf")

    # Cap-at-1: the drafter is called exactly twice. NEVER a third.
    assert len(draft_call_log) == 2, (
        f"Self-check loop should cap retries at 1 (max 2 drafter calls). "
        f"Got {len(draft_call_log)} calls."
    )

    # The result is a RedlineConflict, not a RedlineProposal.
    assert isinstance(result, RedlineConflict)
    assert not isinstance(result, RedlineProposal), (
        "The second-failure path MUST return a RedlineConflict, "
        "NOT a RedlineProposal. The HITL UI needs the conflict "
        "shape to render the 'pick one' view."
    )

    # The conflict carries both attempts and both conflicting flags.
    assert result.first_proposal.attempt == 1
    assert result.second_proposal.attempt == 2
    assert "first attempt" in result.first_proposal.proposed_text
    assert "second attempt" in result.second_proposal.proposed_text
    assert result.first_conflict.score == 2
    assert result.second_conflict.score == 2
    assert result.message.startswith("redline conflict:")


# --- Test 4: Pydantic boundary (malformed proposal → raise) -----------


def test_draft_redline_raises_on_malformed_proposal():
    """A malformed proposal (empty ``proposed_text``) raises
    ``ValueError`` — the drafter does NOT silently default.

    The spec is explicit: "Pydantic validation runs at the
    LLM boundary. Malformed proposals do NOT silently
    default — they raise." This is the defense-in-depth
    hedge: the LLM might emit ``{"proposed_text": ""}`` or
    forget the field, and the drafter must catch it.
    """
    di = _drafter_input()
    raw = _stub_draft_payload(proposed_text="")  # empty — schema rejects

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        return_value=raw,
    ):
        with pytest.raises(ValueError, match="proposed_text"):
            draft_redline_sync(di, contract_filename="test.pdf")


def test_draft_redline_raises_on_missing_proposed_text_field():
    """An LLM output missing the ``proposed_text`` field
    also raises — the parser coerces the missing field to
    ``""`` and the empty-string guard rejects it.
    """
    di = _drafter_input()
    raw = {"rationale": "no proposed_text", "diff_summary": "no diff"}

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        return_value=raw,
    ):
        with pytest.raises(ValueError, match="proposed_text"):
            draft_redline_sync(di, contract_filename="test.pdf")


# --- Test 5: no LLM → DrafterUnavailable -------------------------------


def test_draft_redline_raises_drafter_unavailable_when_no_llm_key():
    """When the LLM key is a placeholder, the drafter raises
    :class:`DrafterUnavailable` — it does NOT insert a
    hallucinated clause into the docx output.

    The HITL state machine (Build 3) catches this and marks
    the flag's redline status as ``"unavailable"``. The
    fallback is the same shape as the spec's "no silent
    default" rule.
    """
    di = _drafter_input()

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=False,
    ):
        with pytest.raises(DrafterUnavailable):
            draft_redline_sync(di, contract_filename="test.pdf")


# --- Test 6: unverified spotter flag does NOT trigger retry ------------


@pytest.mark.asyncio
async def test_unverified_spotter_flag_does_not_trigger_retry():
    """A spotter flag with ``unverified=True`` is treated as
    "self-check passed" — the loop does NOT retry.

    Rationale: an unverified flag means the spotter wasn't
    sure, not that the drafter broke something. The HITL
    reviewer is the right place to resolve uncertainty, not
    a third drafter attempt.
    """
    di = _drafter_input()
    draft_raw = _stub_draft_payload()
    unverified_flag = DeviationFlag(
        clause_id=di.flag.clause_id,
        score=2,
        rationale="spotter wasn't sure",
        citation=None,  # missing citation → unverified
        unverified=True,
        baseline_type="term",
    )

    draft_call_log: list[int] = []

    def _draft_side_effect(*_args, **_kwargs):
        draft_call_log.append(len(draft_call_log) + 1)
        return draft_raw

    async def _spot_side_effect(**_kwargs):
        return unverified_flag

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        side_effect=_draft_side_effect,
    ), patch(
        "app.agents.redline_drafter.self_check._run_spotter_on_proposed_text",
        side_effect=_spot_side_effect,
    ):
        result = await run_with_self_check(di, contract_filename="test.pdf")

    # Only one drafter call — the unverified flag did not
    # trigger a retry.
    assert len(draft_call_log) == 1
    assert isinstance(result, RedlineProposal)
    assert result.attempt == 1


# --- Test 7: the async wrapper returns what the sync one does ---------


@pytest.mark.asyncio
async def test_async_draft_redline_matches_sync():
    """The async ``draft_redline`` is the async boundary over
    the sync ``draft_redline_sync``. They return equivalent
    proposals for the same input.
    """
    di = _drafter_input()
    raw = _stub_draft_payload()

    with patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        return_value=raw,
    ):
        async_proposal = await draft_redline(di, contract_filename="test.pdf")
        # The sync path also exists and is used by the
        # parallel orchestrator; verify it returns the
        # same shape.
        sync_proposal = draft_redline_sync(di, contract_filename="test.pdf")

    assert async_proposal.proposed_text == sync_proposal.proposed_text
    assert async_proposal.rationale == sync_proposal.rationale
    assert async_proposal.diff_summary == sync_proposal.diff_summary
    assert async_proposal.attempt == 1


# --- Test 8: Langfuse traces on every LLM call ------------------------


@pytest.mark.asyncio
async def test_langfuse_trace_annotated_for_drafter_and_self_check():
    """Spy on ``get_langfuse().trace()`` and confirm both the
    drafter and the self-check loop emit annotations.

    Per the spec: "Langfuse trace annotations on every LLM
    call (drafter call + spotter self-check call)." The
    self-check loop wraps the spotter's re-run on the
    drafter's output, so both agents need to surface their
    work to Langfuse. We patch ``get_langfuse`` to return a
    fake client that records every ``trace()`` call, then
    assert both names appear.
    """
    from app.observability import _NoopSpan

    class _RecordingLangfuse:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def trace(self, *, name: str = "", tags=None, input=None, **_kwargs):
            self.calls.append({"name": name, "tags": tags, "input": input})
            return _NoopSpan()

        def span(self, *_args, **_kwargs):
            return _NoopSpan()

        def generation(self, *_args, **_kwargs):
            return _NoopSpan()

        def flush(self) -> None:
            return None

    recorder = _RecordingLangfuse()

    di = _drafter_input()
    draft_raw_1 = _stub_draft_payload(
        proposed_text="first attempt — too aggressive",
        rationale="first try",
    )
    draft_raw_2 = _stub_draft_payload(
        proposed_text="second attempt — closer to baseline",
        rationale="second try",
    )
    spot_clean = DeviationFlag(
        clause_id=di.flag.clause_id,
        score=0,
        rationale="aligned",
        citation=None,
        unverified=False,
        baseline_type="term",
    )
    spot_dirty = DeviationFlag(
        clause_id=di.flag.clause_id,
        score=2,
        rationale="still deviates",
        citation=Citation(
            playbook_clause_id="term-of-confidentiality",
            contract_text_excerpt="still too long",
        ),
        unverified=False,
        baseline_type="term",
    )

    draft_call_log: list[int] = []

    def _draft_side_effect(*_args, **_kwargs):
        draft_call_log.append(len(draft_call_log) + 1)
        if len(draft_call_log) == 1:
            return draft_raw_1
        return draft_raw_2

    spot_call_log: list[int] = []

    async def _spot_side_effect(**_kwargs):
        spot_call_log.append(len(spot_call_log) + 1)
        if len(spot_call_log) == 1:
            return spot_dirty
        return spot_clean

    with patch(
        "app.agents.redline_drafter.drafter.get_langfuse", return_value=recorder
    ), patch(
        "app.agents.redline_drafter.self_check.get_langfuse", return_value=recorder
    ), patch(
        "app.agents.redline_drafter.drafter._looks_like_real_key",
        return_value=True,
    ), patch(
        "app.agents.redline_drafter.drafter._call_llm_for_draft",
        side_effect=_draft_side_effect,
    ), patch(
        "app.agents.redline_drafter.self_check._run_spotter_on_proposed_text",
        side_effect=_spot_side_effect,
    ):
        result = await run_with_self_check(di, contract_filename="test.pdf")

    assert isinstance(result, RedlineProposal)
    assert result.attempt == 2

    # 1 trace for the self-check loop wrapper, 2 traces for
    # the drafter calls (one per attempt), 2 traces for the
    # spotter re-runs (one per attempt). At minimum we need
    # the drafter + self-check-loop names.
    names = [c["name"] for c in recorder.calls]
    assert names.count("redline_draft") == 2, (
        f"Expected 2 drafter traces (one per attempt). Got: {names}"
    )
    assert "redline_draft_with_self_check" in names, (
        f"Self-check loop wrapper trace missing. Got: {names}"
    )
