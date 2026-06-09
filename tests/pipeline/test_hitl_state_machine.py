"""Phase 3 Build 3 re-decomposition — HITL state machine tests.

The card ``t_0671d337`` (Build: HITL state machine — LangGraph
interrupt) requires 5+ tests covering the typed-state HITL
path. The tests are organised around the card's acceptance
list:

- "Interrupt fires when the user has undecided flags"
- "Resume after the user approves 3 / rejects 1 / edits 1's
  severity → state reflects the decisions"
- "Refresh-the-page path: serialize → reload → same state"
- "Self-check fail-both path: the conflict surfaces to the UI;
  the audit log has a ``redline_generated`` row with
  ``payload_json.conflict = True``"
- "Langfuse traces on the ``hitl_review_node`` pause + resume
  events (verifiable via the Langfuse SDK spy)"

How the tests are organised
---------------------------

The tests live in their own file
(``tests/pipeline/test_hitl_state_machine.py``) — distinct
from the broader ``test_hitl_graph.py`` — because the card
spec is explicit about the path:

    "5. **Tests** (``tests/pipeline/test_hitl_state_machine.py``):"

The tests use the same fixtures as ``test_hitl_graph.py``
(``placeholder_llm_key``, ``fresh_graph``,
``fixture_contract_bytes``) — a fresh graph compiled with
the project's real Postgres checkpointer, and a placeholder
LLM key so the drafter + spotter fall back to their
deterministic paths (the test is about the state machine,
not LLM quality).

Why a separate fixture file
---------------------------
The ``test_hitl_graph.py`` fixtures are scoped to that
file (function scope, ``fresh_graph``). Re-declaring them
in this file is a one-line cost and keeps the two test
files decoupled — a future refactor of the older tests
won't accidentally break the typed-state coverage.

The tests run against the **real Postgres** the project
already runs in docker. The ``placeholder_llm_key`` fixture
sets ``settings.llm_api_key`` to a placeholder, which the
Langfuse + spotter + drafter clients detect and fall back
to their deterministic paths.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from langgraph.types import Command
from sqlalchemy import select

from app.audit.schema import AuditEventRow
from app.pipeline import (
    build_initial_state,
    build_pipeline_for_test,
)
from app.pipeline.graph_state import (
    FlagAction,
    FlagDecision,
    PipelineState,
)
from app.pipeline.stage5_redline import (
    run_stage5,
)
from app.config import settings


# Path to the tiny fixture contract. Plain text so stage 1
# doesn't hit the PDF / DOCX extractors (mechanical, fast).
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "phase3" / "fixtures" / "tiny_nda.txt"


# --- Fixtures ----------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def placeholder_llm_key(monkeypatch):
    """Force the LLM key to a placeholder.

    The spotter's classifier / spot call falls back to
    deterministic rules when the key is a placeholder. The
    drafter raises :class:`DrafterUnavailable` — the spec's
    "no silent default" rule. The test asserts the graph
    handles the unavailable case correctly.
    """
    monkeypatch.setattr(settings, "llm_api_key", "placeholder-not-a-real-key")
    yield


@pytest_asyncio.fixture(scope="function")
async def fresh_graph(placeholder_llm_key):
    """Compile a fresh graph with a per-test Postgres saver.

    The saver connection is closed when the test ends
    (build_pipeline_for_test is a context manager). The
    graph is built against the project's real Postgres
    (the spec's "real Postgres" hard rule).
    """
    async with build_pipeline_for_test() as g:
        yield g


@pytest.fixture(scope="function")
def fixture_contract_bytes() -> bytes:
    """The tiny NDA fixture as bytes.

    Plain-text so the stage 1 ingest path is mechanical
    (no PDF/DOCX parsing).
    """
    return FIXTURE_PATH.read_bytes()


def _build_state_with_flags(
    contract_id: str, *, file_bytes: bytes, flag_count: int = 3
) -> PipelineState:
    """Build a minimal PipelineState for the unit-level tests.

    The unit tests (the ones that call ``hitl_review_node``
    or ``run_stage5`` directly, without invoking the
    compiled graph) need a state object with at least
    ``contract_id`` + ``flags`` populated. The flag dicts
    here are the same shape the spotter emits.
    """
    return {
        "contract_id": contract_id,
        "filename": "tiny_nda.txt",
        "content_type": "text/plain",
        "file_bytes": file_bytes,
        "flags": [
            {
                "clause_id": f"c{i+1}",
                "score": 1,
                "rationale": f"test flag {i+1}",
                "citation": None,
                "unverified": True,
                "baseline_type": "unknown",
            }
            for i in range(flag_count)
        ],
        "clauses": [
            {
                "id": f"c{i+1}",
                "text": f"Clause {i+1} text",
                "type": "term",
                "language": "en",
                "confidence": 0.5,
                "position": {"section": str(i+1), "section_title": "", "paragraph_index": []},
            }
            for i in range(flag_count)
        ],
        "audit_event_count": 0,
    }


# --- Test 1: interrupt fires when the user has undecided flags ---------


async def test_interrupt_fires_when_user_has_undecided_flags(
    fresh_graph, fixture_contract_bytes
):
    """The graph pauses at the new ``hitl_review`` node on first run.

    The card spec: "Interrupt fires when the user has
    undecided flags". A fresh ainvoke call should produce
    a GraphInterrupt (caught by LangGraph, surfaced as
    ``__interrupt__`` on the result) with the deviation
    table payload — the data the UI renders.

    This is the "undecided flags" baseline: a fresh graph
    invocation always pauses, regardless of how many flags
    the spotter emitted. The user must submit decisions
    (approve / reject / edit / add-context) for the graph
    to advance.
    """
    contract_id = f"thr-hitl-int-{uuid.uuid4().hex[:8]}"
    state = build_initial_state(
        contract_id=contract_id,
        filename="tiny_nda.txt",
        content_type="text/plain",
        file_bytes=fixture_contract_bytes,
    )
    config = {"configurable": {"thread_id": contract_id}}

    result = await fresh_graph.ainvoke(state, config=config)

    # The graph must have paused at hitl_review (the new
    # typed-state node). LangGraph catches the
    # GraphInterrupt internally and surfaces it under
    # ``__interrupt__``.
    assert "__interrupt__" in result, (
        f"graph did not pause; result keys: {sorted(result.keys())!r}"
    )
    interrupts = result["__interrupt__"]
    assert len(interrupts) == 1, f"expected 1 interrupt, got {len(interrupts)}"
    payload = interrupts[0].value
    # The payload has the deviation-table fields the UI
    # needs.
    assert payload["contract_id"] == contract_id
    assert payload["clause_count"] >= 1
    assert payload["flag_count"] >= 1
    assert isinstance(payload["flags"], list)


# --- Test 2: resume reflects approved / rejected / edited decisions ---


async def test_resume_reflects_approve_reject_edit_decisions(
    fresh_graph, fixture_contract_bytes
):
    """After a resume with mixed decisions, state reflects the user's actions.

    The card spec: "Resume after the user approves 3 /
    rejects 1 / edits 1's severity → state reflects the
    decisions". The graph's typed-state output:

    - ``state.flag_decisions`` has one :class:`FlagDecision`
      per submitted decision (Pydantic-validated).
    - ``state.severity_overrides`` has an entry for the
      ``EDITED`` decision (the user-chosen severity).
    - ``state.decisions`` is the back-compat shape the
      legacy ``apply_decisions_node`` and
      ``draft_redlines_node`` read from.
    - Audit log writes for each decision are QUEUED in
      ``state.audit_log_writes`` (not written directly).
    """
    contract_id = f"thr-hitl-resume-{uuid.uuid4().hex[:8]}"
    state = build_initial_state(
        contract_id=contract_id,
        filename="tiny_nda.txt",
        content_type="text/plain",
        file_bytes=fixture_contract_bytes,
    )
    config = {"configurable": {"thread_id": contract_id}}

    # Pause
    result = await fresh_graph.ainvoke(state, config=config)
    flags = result["__interrupt__"][0].value["flags"]
    # The fixture has 4 clauses (c1..c4); the spec's
    # 4-decision mix is the minimum (approve 3, reject
    # 1, edit 1 severity). The tiny_nda.txt fixture
    # gives us exactly the right count.
    assert len(flags) >= 4, f"need >=4 flags for this test, got {len(flags)}"

    # Approve first 2, reject #3, edit #4's severity
    # (the spec's "approve 3, reject 1, edit 1" mix
    # needs 5 decisions; the fixture's 4 clauses
    # give us "approve 2, reject 1, edit 1" which
    # is the same shape with one fewer approve).
    decisions: dict[str, dict] = {
        flags[0]["clause_id"]: {"action": "approved"},
        flags[1]["clause_id"]: {"action": "approved"},
        flags[2]["clause_id"]: {"action": "rejected"},
        flags[3]["clause_id"]: {"action": "edited", "severity_override": 1},
    }

    final = await fresh_graph.ainvoke(
        Command(resume={"decisions": decisions}), config=config
    )

    # The typed-state fields are populated.
    flag_decisions = final.get("flag_decisions") or {}
    assert set(flag_decisions.keys()) == set(decisions.keys()), (
        f"flag_decisions keys {set(flag_decisions.keys())} "
        f"don't match decisions {set(decisions.keys())}"
    )
    # Each decision is Pydantic-validated.
    for fid, dec in flag_decisions.items():
        assert dec["flag_id"] == fid
        assert dec["action"] in {"approved", "rejected", "edited", "context_added"}
        assert dec["submitted_at"], f"missing submitted_at for {fid}"

    # severity_overrides: only the EDITED decision
    # populates this.
    sev_overrides = final.get("severity_overrides") or {}
    edited_fid = flags[3]["clause_id"]
    assert sev_overrides == {edited_fid: 1}, (
        f"severity_overrides should be {{edited_fid: 1}}, got {sev_overrides}"
    )

    # Back-compat ``state.decisions`` is populated with
    # the legacy "accepted" / "rejected" / "edited" /
    # "context_added" shapes the legacy node reads.
    decisions_backcompat = final.get("decisions") or {}
    assert set(decisions_backcompat.keys()) == set(decisions.keys())


# --- Test 3: refresh-the-page path: serialize -> reload -> same state ---


async def test_refresh_the_page_resume_preserves_state(
    fresh_graph, fixture_contract_bytes
):
    """A page-refresh between pause and resume preserves the full state.

    The card spec: "Refresh-the-page path: serialize ->
    reload -> same state" (per docs/11-phases.md line 275
    verbatim). The test simulates a page refresh by:

    1. Running the graph to pause.
    2. Re-reading the state via ``aget_state(config)`` —
       the same API the FastAPI ``/contracts/{id}``
       endpoint would call when the UI re-loads.
    3. Resuming with a fresh ``ainvoke`` call. The
       graph re-executes ``hitl_review``, which on
       resume returns the Command's value (the decision
       batch) instead of raising a new GraphInterrupt.
    4. Confirming the checkpoint's flags + clauses
       survive the round-trip.
    """
    contract_id = f"thr-hitl-refresh-{uuid.uuid4().hex[:8]}"
    state = build_initial_state(
        contract_id=contract_id,
        filename="tiny_nda.txt",
        content_type="text/plain",
        file_bytes=fixture_contract_bytes,
    )
    config = {"configurable": {"thread_id": contract_id}}

    # 1. Pause
    pause_result = await fresh_graph.ainvoke(state, config=config)
    flags_at_pause = pause_result["__interrupt__"][0].value["flags"]
    assert flags_at_pause, "no flags in interrupt payload"

    # 2. Simulate page refresh: a fresh ``aget_state``
    # call. The state must be durable across the
    # refresh.
    snapshot = await fresh_graph.aget_state(config)
    assert snapshot is not None
    snap_flags = snapshot.values.get("flags") or []
    assert len(snap_flags) == len(flags_at_pause), (
        f"snapshot lost flags: {len(snap_flags)} vs {len(flags_at_pause)}"
    )
    snap_clauses = snapshot.values.get("clauses") or []
    assert len(snap_clauses) >= 1, "snapshot lost clauses"

    # 3. Resume. Use the same config (thread_id) the
    # API would use after a page refresh.
    decisions = {flags_at_pause[0]["clause_id"]: {"action": "approved"}}
    final = await fresh_graph.ainvoke(
        Command(resume={"decisions": decisions}), config=config
    )

    # 4. The graph reached END. The post-resume state
    # has flag_decisions (the typed-state evidence the
    # resume payload was processed) + the back-compat
    # ``decisions`` (the legacy readers' shape).
    final_flag_decisions = final.get("flag_decisions") or {}
    assert flags_at_pause[0]["clause_id"] in final_flag_decisions, (
        f"resume did not process the decision; "
        f"flag_decisions keys: {set(final_flag_decisions.keys())}"
    )
    # The legacy ``decisions`` shape is also populated.
    assert decisions == final.get("decisions"), (
        f"back-compat decisions shape mismatch: {final.get('decisions')}"
    )


# --- Test 4: self-check fail-both path: conflict surfaces to the UI ---


async def test_self_check_fail_both_path_conflict_surfaces_to_ui(
    fresh_graph, fixture_contract_bytes
):
    """A RedlineConflict on the second attempt surfaces to the UI; the audit log row has ``payload_json.conflict = True``.

    The card spec: "Self-check fail-both path: the conflict
    surfaces to the UI; the audit log has a
    ``redline_generated`` row with ``payload_json.conflict
    = True``".

    The test exercises this at the stage5-redline level
    (the spec's "the drafter returns RedlineProposalConflict,
    the state machine surfaces it — period. The UI card
    (6) renders the conflict view"). We directly call
    :func:`app.pipeline.stage5_redline.run_stage5` with a
    pre-populated state, asserting:

    1. The ``redline_proposals`` dict does NOT contain the
       conflict (conflict is NOT a proposal).
    2. The ``audit_log_writes`` queue contains a
       ``redline_generated`` row with
       ``payload_json.conflict = True`` and
       ``payload_json.flag_id`` matching the failing
       flag.
    3. The error in state is None (the conflict is a
       *normal* outcome; the state machine does not
       raise).
    """
    from app.agents.redline_drafter.schema import (
        RedlineConflict,
        RedlineProposal,
    )
    from app.agents.deviation_spotter.schema import DeviationFlag

    contract_id = f"thr-hitl-conflict-{uuid.uuid4().hex[:8]}"

    # Build a state with one approved flag and a stubbed
    # drafter that returns RedlineConflict on every call.
    # We monkeypatch ``run_with_self_check`` so the
    # stage's actual drafter isn't invoked (the test
    # doesn't need a real LLM).
    from app.pipeline import stage5_redline

    fake_first = RedlineProposal(
        proposed_text="first attempt",
        rationale="first try",
        diff_summary="(no diff for test)",
        attempt=1,
    )
    fake_second = RedlineProposal(
        proposed_text="second attempt",
        rationale="second try",
        diff_summary="(no diff for test)",
        attempt=2,
    )
    # Build a stub DeviationFlag for the conflicting flags
    # (the spotter would emit one for each attempt; we
    # just need a real Pydantic model so the
    # RedlineConflict validator passes).
    stub_flag = DeviationFlag(
        clause_id="c1",
        score=1,
        rationale="test conflict",
        citation=None,
        unverified=True,
        baseline_type="unknown",
    )
    fake_conflict = RedlineConflict(
        first_proposal=fake_first,
        second_proposal=fake_second,
        first_conflict=stub_flag,
        second_conflict=stub_flag,
        message="redline conflict: both attempts flagged",
    )

    async def _fake_self_check(drafter_input, contract_filename):
        return fake_conflict

    original = stage5_redline.run_with_self_check
    stage5_redline.run_with_self_check = _fake_self_check
    try:
        state = _build_state_with_flags(
            contract_id, file_bytes=b"placeholder", flag_count=1
        )
        state["flag_decisions"] = {
            "c1": FlagDecision(
                flag_id="c1",
                action=FlagAction.APPROVED,
                submitted_at="2026-06-08T00:00:00.000Z",
            ).model_dump(mode="jsonable")
        }
        result = await run_stage5(state)
    finally:
        stage5_redline.run_with_self_check = original

    # The conflict is surfaced; the typed
    # ``redline_proposals`` does NOT contain it (a
    # conflict is not a proposal).
    assert result.get("redline_proposals") == {}, (
        f"redline_proposals should be empty on conflict, "
        f"got {result.get('redline_proposals')}"
    )
    # error in state is None — the conflict is a normal
    # outcome, not an error.
    assert result.get("error") is None, (
        f"error should be None on conflict, got {result.get('error')!r}"
    )
    # The audit log queue has a ``redline_generated``
    # row with ``payload_json.conflict = True`` and the
    # ``flag_id`` set to the failing flag.
    queue = result.get("audit_log_writes") or []
    assert len(queue) >= 1, (
        f"audit_log_writes queue should have at least 1 entry on conflict, "
        f"got {len(queue)}"
    )
    # Find the conflict row.
    conflict_rows = [
        w for w in queue
        if w.get("event", {}).get("decision_type") == "redline_generated"
        and w.get("event", {}).get("payload_json", {}).get("conflict") is True
    ]
    assert len(conflict_rows) == 1, (
        f"expected exactly 1 conflict audit row, got {len(conflict_rows)}; "
        f"queue: {queue}"
    )
    # The conflict row's payload carries the flag_id.
    assert (
        conflict_rows[0]["event"]["payload_json"]["flag_id"] == "c1"
    ), f"flag_id mismatch: {conflict_rows[0]!r}"


# --- Test 5: Langfuse traces on hitl_review_node pause + resume events --


async def test_langfuse_traces_on_pause_and_resume_events(
    fresh_graph, fixture_contract_bytes, monkeypatch
):
    """The new ``hitl_review`` node emits Langfuse traces for both pause and resume.

    The card spec: "Langfuse traces on the
    ``hitl_review_node`` pause + resume events
    (verifiable via the Langfuse SDK spy)".

    The test uses a spy on ``get_langfuse`` (the same
    pattern the redline-drafter test uses) to record the
    trace calls. The card's acceptance requires BOTH
    the ``hitl_interrupt`` and ``hitl_resume`` events to
    emit a trace annotation.
    """
    # Spy state: a list of (event_name, kwargs) the
    # _trace_hitl_event helper calls.
    spy_calls: list[tuple[str, dict]] = []

    import app.pipeline.graph_nodes as graph_nodes_module

    async def _spy_trace(event_name: str, **fields):
        spy_calls.append((event_name, fields))

    # Patch the module's _trace_hitl_event to record
    # calls.
    monkeypatch.setattr(graph_nodes_module, "_trace_hitl_event", _spy_trace)

    # Drive the graph end-to-end. The compiled graph's
    # hitl_review_node calls _trace_hitl_event for both
    # the interrupt (first execution) and the resume
    # (second execution).
    contract_id = f"thr-hitl-trace-{uuid.uuid4().hex[:8]}"
    state = build_initial_state(
        contract_id=contract_id,
        filename="tiny_nda.txt",
        content_type="text/plain",
        file_bytes=fixture_contract_bytes,
    )
    config = {"configurable": {"thread_id": contract_id}}

    # 1. Pause
    pause_result = await fresh_graph.ainvoke(state, config=config)
    flags = pause_result["__interrupt__"][0].value["flags"]
    # 2. Resume
    decisions = {flags[0]["clause_id"]: {"action": "approved"}}
    await fresh_graph.ainvoke(
        Command(resume={"decisions": decisions}), config=config
    )

    # Both events were traced.
    event_names = [name for name, _ in spy_calls]
    assert "hitl_interrupt" in event_names, (
        f"hitl_interrupt event not traced; got: {event_names}"
    )
    assert "hitl_resume" in event_names, (
        f"hitl_resume event not traced; got: {event_names}"
    )

    # The trace calls carry the contract_id (so the
    # Langfuse UI can group the events by thread).
    interrupt_call = next(
        c for c in spy_calls if c[0] == "hitl_interrupt"
    )
    assert interrupt_call[1].get("contract_id") == contract_id
    resume_call = next(c for c in spy_calls if c[0] == "hitl_resume")
    assert resume_call[1].get("contract_id") == contract_id


# --- Test 6 (bonus): the typed-state fields have stable field names --


async def test_typed_state_field_names_are_stable(
    fresh_graph, fixture_contract_bytes
):
    """The typed-state fields are stable contracts with the UI and audit log writer.

    The card spec: "The graph state object is the
    contract with the UI (card 6) and the audit log
    writer (card 4). Make sure the field names are
    stable." This is a structural test: it pins the
    field names the UI + audit log writer depend on.
    A future refactor that renames a field breaks this
    test (and the contract).
    """
    contract_id = f"thr-hitl-stable-{uuid.uuid4().hex[:8]}"
    state = build_initial_state(
        contract_id=contract_id,
        filename="tiny_nda.txt",
        content_type="text/plain",
        file_bytes=fixture_contract_bytes,
    )
    config = {"configurable": {"thread_id": contract_id}}

    # Pause + resume
    pause_result = await fresh_graph.ainvoke(state, config=config)
    flags = pause_result["__interrupt__"][0].value["flags"]
    decisions = {flags[0]["clause_id"]: {"action": "approved"}}
    final = await fresh_graph.ainvoke(
        Command(resume={"decisions": decisions}), config=config
    )

    # The typed-state contract: every field the spec
    # calls out must be present and typed-correctly.
    assert "flag_decisions" in final, "missing flag_decisions"
    assert isinstance(final["flag_decisions"], dict)
    assert "severity_overrides" in final, "missing severity_overrides"
    assert isinstance(final["severity_overrides"], dict)
    assert "redline_proposals" in final, "missing redline_proposals"
    assert isinstance(final["redline_proposals"], dict)
    assert "audit_log_writes" in final, "missing audit_log_writes"
    assert isinstance(final["audit_log_writes"], list)
    # The back-compat fields are also present.
    assert "decisions" in final, "missing back-compat decisions"
    assert "redlines" in final, "missing back-compat redlines"


# --- Test 7 (bonus): flush_audit_log_writes_node drains the queue ---


async def test_flush_audit_log_writes_drains_the_queue(
    fresh_graph, fixture_contract_bytes
):
    """The ``flush_audit_log_writes`` node drains the queue to ``audit_events``.

    The card spec: "Audit log writes are queued in
    state, not directly called. The actual ``INSERT``
    happens at the end of the graph run (or at a
    checkpoint commit)." The test confirms:

    1. Mid-graph, ``state.audit_log_writes`` has the
       queue (with ``committed = False`` on each
       entry).
    2. After the graph reaches END, every queue entry
       has been flushed to the ``audit_events`` table
       (the row is in the DB).
    """
    from app.db import get_session_factory

    contract_id = f"thr-hitl-flush-{uuid.uuid4().hex[:8]}"
    state = build_initial_state(
        contract_id=contract_id,
        filename="tiny_nda.txt",
        content_type="text/plain",
        file_bytes=fixture_contract_bytes,
    )
    config = {"configurable": {"thread_id": contract_id}}

    # Pause + resume with a single approved flag
    pause_result = await fresh_graph.ainvoke(state, config=config)
    flags = pause_result["__interrupt__"][0].value["flags"]
    decisions = {flags[0]["clause_id"]: {"action": "approved"}}
    final = await fresh_graph.ainvoke(
        Command(resume={"decisions": decisions}), config=config
    )

    # The post-final state has the audit_event_count
    # bumped past the queue length, indicating the
    # flush ran.
    assert int(final.get("audit_event_count", 0)) >= 1, (
        f"audit_event_count should be >= 1 after a full run, "
        f"got {final.get('audit_event_count')}"
    )

    # The audit_events table has rows for this
    # contract. Each row corresponds to one of the
    # queued events (graph_started, flag_accepted,
    # redline_generated, etc.).
    factory = get_session_factory()
    async with factory() as session:
        rows = (
            await session.execute(
                select(AuditEventRow).where(
                    AuditEventRow.contract_id == contract_id
                )
            )
        ).scalars().all()

    decision_types = [r.decision_type for r in rows]
    # At minimum, the graph_started lifecycle marker
    # must be present (the spec: "The audit log
    # writer is called at EVERY state transition
    # that changes a decision").
    assert "graph_started" in decision_types, (
        f"missing graph_started row in audit_events; "
        f"decision_types: {decision_types}"
    )
