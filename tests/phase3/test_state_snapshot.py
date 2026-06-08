"""Tests for the resume-after-pause UI hydration (F3 from the
Phase 3 review).

Closes the F3 gap: a user who navigates to
``#/contracts/{id}/review`` after a page refresh (or after
opening the URL from a teammate) used to land on a blank
page because :class:`ReviewContractPage` received no
``clauses`` prop from the hash router. The pipeline layer
round-trips fine (see :mod:`tests.pipeline.test_hitl_state_machine`),
but the React layer had no seam to read it.

Build 7 adds ``GET /contracts/{contract_id}/state`` — a
JSON-safe snapshot of the in-memory state store. The
endpoint powers the new ``useContractState`` hook the
React page consumes on mount.

Coverage
--------

1. **Snapshot for an unknown contract.** Always returns
   200 with ``has_state=false`` and empty lists. A 404
   here would force the user back to triage on a refresh
   — the exact broken behaviour F3 is meant to fix.
2. **Snapshot after ingest.** ``has_ingest=True``,
   ``has_spot=False``, clauses populated, flags empty.
3. **Snapshot after spot.** All four booleans flip
   correctly through the pipeline.
4. **Snapshot after decisions.** ``has_decisions=True``,
   decisions list carries the canonical ``action``
   strings. (Lossless round-trip — the React side
   re-derives the ``DecisionAction`` enum from these
   canonical strings.)
5. **Snapshot after redline.** ``has_redline=True``,
   redlines list populated with one entry per
   accepted clause_id.
6. **Refresh round-trip.** The e2e shape: a contract is
   ingested, spotted, decided, redlined — the state
   snapshot after every step carries the right
   combination of clauses, flags, decisions, redlines.
   This is the exact scenario F3 was raised about.

The tests run against the real FastAPI app
(:class:`app.main.app`) but do not require a
Postgres connection — the state store is in-process.
We use the same TestClient + drafter-stub pattern
:mod:`tests.e2e.test_phase3_redline` uses, with the
state reset between tests for isolation.
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Iterable

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.agents.deviation_spotter.schema import DeviationFlag
from app.agents.redline_drafter.schema import RedlineProposal
from app.pipeline import phase3_pipeline
from app.pipeline import stage3_spot
from app.pipeline import stage5_redline


def _make_synthetic_flag(clause_id: str, score: int = 2) -> DeviationFlag:
    """Build a :class:`DeviationFlag` for the spot stub."""
    return DeviationFlag(
        clause_id=clause_id,
        score=score,
        rationale=f"e2e-stub rationale for {clause_id}",
        citation=None,
        unverified=False,
        baseline_type="term",
    )


async def _spot_stub_synthetic(
    clauses: list[Any], *, contract_filename: str = ""
) -> Any:
    """Spot-stage stub: emit one ``score=2`` flag per input clause."""
    from app.pipeline.stage3_spot import Stage3Result

    flags = [_make_synthetic_flag(c.id, score=2) for c in clauses]
    return Stage3Result(
        contract_filename=contract_filename,
        flags=flags,
        flagged_count=len(flags),
        unverified_count=0,
        no_baseline_count=0,
        matrix_version="state-stub-v0",
        embedding_provider="state-stub",
    )


async def _draft_stub_proposal(
    drafter_input: Any, contract_filename: str = ""
) -> RedlineProposal:
    """Drafter stub: return a valid async proposal on first call.

    Must be ``async def`` to match the real
    :func:`app.pipeline.stage5_redline.run_with_self_check`
    signature — ``phase3_pipeline._draft_one_redline`` awaits
    the result. The proposal shape is
    :class:`RedlineProposal` (``proposed_text`` /
    ``rationale`` / ``diff_summary`` / ``attempt``); the
    ``clause_id`` lives outside the proposal, in the state
    store dict key, so we don't need to set it here.
    """
    clause_id = getattr(
        getattr(drafter_input, "flag", None), "clause_id", "c1"
    ) or "c1"
    return RedlineProposal(
        proposed_text=f"Stub: redline for {clause_id}.",
        rationale=f"Stub: rationale for {clause_id}.",
        diff_summary=f"Stub: diff summary for {clause_id}.",
        attempt=1,
    )


@pytest.fixture()
def reset_pipeline_state() -> Iterable[None]:
    """Clear the in-memory state store before and after every test.

    The store is process-local; without this fixture a stale
    contract from a prior test would leak into the snapshot
    response and break the booleans assertions.
    """
    phase3_pipeline._STATE.clear()
    yield
    phase3_pipeline._STATE.clear()


@pytest_asyncio.fixture()
async def placeholder_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the LLM key to a placeholder for the test.

    Mirrors the e2e test's pattern. With a placeholder key,
    the classifier falls back to deterministic rules instead
    of making real HTTP calls to the LLM provider. Without
    this fixture, the classifier would hang for 3 × httpx
    timeout on every clause.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "placeholder-not-a-real-key")
    yield


@pytest.fixture()
def client(
    reset_pipeline_state: None, placeholder_llm_key: None
) -> Iterable[TestClient]:
    """A FastAPI TestClient bound to the real ``app.main`` ASGI app.

    Function-scoped so the in-memory state store is fresh
    for every test (the state endpoint reads the same dict
    the spot/ingest endpoints write to).
    """
    from app.main import app

    with TestClient(app) as c:
        yield c


# --- Autouse: dispose the engine + pool after each test --------------
#
# Mirrors the e2e test's pattern: TestClient creates a fresh
# anyio portal + event loop for every function-scoped client
# fixture, and pytest-asyncio's @pytest.mark.asyncio tests
# run on their own loop. The module-level engine in
# :mod:`app.db` is created on whichever loop first calls
# :func:`get_engine` (TestClient's portal loop, usually), and
# the pool's cached asyncpg connections are bound to that
# loop. The next test then tries to use those connections
# on a different loop and fails with
# ``got Future attached to a different loop`` /
# ``Event loop is closed`` — surfacing at the first ``await
# session.execute(...)`` (the audit write in
# ``process_decisions``).
#
# Disposing the engine after each test forces a fresh
# engine + pool for the next test. The engine is cheap to
# rebuild (the connection pool is the only meaningful
# state).
@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_per_test() -> AsyncIterator[None]:
    yield
    try:
        from app.db import get_engine

        engine = get_engine()
        await engine.dispose()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture()
def spot_synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the spot stage to emit one synthetic flag per clause.

    Patches the three names Build 6's e2e patches
    (``stage3_spot.run_stage3``, ``app.pipeline.run_stage3``,
    ``app.main.run_stage3``) — the third is the import-time
    bound name in :mod:`app.main` that the route handler
    calls.
    """
    import app.main as main_mod
    import app.pipeline as pipeline_mod

    monkeypatch.setattr(stage3_spot, "run_stage3", _spot_stub_synthetic)
    monkeypatch.setattr(pipeline_mod, "run_stage3", _spot_stub_synthetic)
    monkeypatch.setattr(main_mod, "run_stage3", _spot_stub_synthetic)


@pytest.fixture()
def drafter_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the drafter's ``run_with_self_check`` to return a valid
    async proposal for any input.

    Patches three names, mirroring :mod:`tests.e2e.test_phase3_redline`:
    the function in :mod:`app.pipeline.stage5_redline`
    (the source), the import-time bound name on
    :mod:`app.pipeline.phase3_pipeline` (the only one the
    route handler actually calls), and the re-export on
    :mod:`app.pipeline` for safety.
    """
    monkeypatch.setattr(
        stage5_redline, "run_with_self_check", _draft_stub_proposal
    )
    monkeypatch.setattr(
        phase3_pipeline, "run_with_self_check", _draft_stub_proposal
    )


def _ingest(client: TestClient, contract_id: str) -> dict[str, Any]:
    """POST /contracts/ingest with a real (small) contract file.

    We use the known-bad NDA fixture from :mod:`tests.e2e`.
    If the fixture is missing the test fails clearly so the
    CI signal is "missing fixture", not "500 from FastAPI".
    """
    from tests.e2e.test_phase3_redline import CONTRACT_KNOWN_BAD

    if not CONTRACT_KNOWN_BAD.exists():
        pytest.fail(f"e2e fixture missing: {CONTRACT_KNOWN_BAD}")
    files = {
        "file": (contract_id, CONTRACT_KNOWN_BAD.read_bytes(), "application/pdf")
    }
    resp = client.post("/contracts/ingest", files=files)
    assert resp.status_code == 200, (
        f"ingest failed: {resp.status_code} {resp.text[:500]!r}"
    )
    return resp.json()


def _new_contract_id(prefix: str) -> str:
    """Unique contract id per test so the state store is
    isolated even when the fixture order interleaves.
    """
    return f"{prefix}-state-{uuid.uuid4().hex[:12]}.pdf"


# --- Tests ---------------------------------------------------------------


def test_state_for_unknown_contract_returns_empty_200(
    client: TestClient,
) -> None:
    """F3 contract: refresh an unknown URL → 200, not 404.

    A 404 here would force the user back to triage on a
    refresh — exactly the broken behaviour F3 was raised
    about. The endpoint must return 200 with
    ``has_state=false`` so the React page can render a
    friendly empty state.
    """
    resp = client.get(f"/contracts/{_new_contract_id('ghost')}/state")
    assert resp.status_code == 200, (
        f"state endpoint must return 200 for unknown contract, "
        f"got {resp.status_code} {resp.text[:500]!r}"
    )
    body = resp.json()
    assert body["has_state"] is False
    assert body["has_ingest"] is False
    assert body["has_spot"] is False
    assert body["has_decisions"] is False
    assert body["has_redline"] is False
    assert body["clauses"] == []
    assert body["flags"] == []
    assert body["decisions"] == []
    assert body["redlines"] == []


def test_state_after_ingest_has_clauses(
    client: TestClient, spot_synthetic: None
) -> None:
    """After ``/contracts/ingest`` the snapshot has clauses
    and ``has_ingest=True``; the spot booleans stay False.
    """
    contract_id = _new_contract_id("nda001")
    ingest_resp = _ingest(client, contract_id)
    assert ingest_resp["clause_count"] >= 1

    resp = client.get(f"/contracts/{contract_id}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_state"] is True
    assert body["has_ingest"] is True
    assert body["has_spot"] is False
    assert body["has_decisions"] is False
    assert body["has_redline"] is False
    # Clauses round-trip from the ingest response.
    assert len(body["clauses"]) == ingest_resp["clause_count"]
    assert body["flags"] == []
    assert body["decisions"] == []


def test_state_after_spot_has_flags(
    client: TestClient, spot_synthetic: None
) -> None:
    """After ``/contracts/spot`` the snapshot has flags and
    ``has_spot=True``. Clauses + flags are both populated.
    """
    contract_id = _new_contract_id("nda001")
    ingest_resp = _ingest(client, contract_id)
    clauses = ingest_resp["clauses"]

    spot_resp = client.post(
        "/contracts/spot",
        json={"filename": contract_id, "clauses": clauses},
    )
    assert spot_resp.status_code == 200
    assert len(spot_resp.json()["flags"]) >= 1

    resp = client.get(f"/contracts/{contract_id}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_ingest"] is True
    assert body["has_spot"] is True
    assert body["has_decisions"] is False
    assert body["has_redline"] is False
    # Flags round-trip with clause_ids.
    flag_ids = {f["clause_id"] for f in body["flags"]}
    assert flag_ids == {c["id"] for c in clauses if c.get("id")}


def test_state_after_decisions_has_canonical_actions(
    client: TestClient, spot_synthetic: None, drafter_happy_path: None
) -> None:
    """After ``/contracts/{id}/decisions`` the snapshot's
    decisions list carries canonical ``action`` strings the
    frontend can re-derive to its ``DecisionAction`` enum.
    """
    contract_id = _new_contract_id("nda001")
    ingest_resp = _ingest(client, contract_id)
    clauses = ingest_resp["clauses"]

    spot_resp = client.post(
        "/contracts/spot",
        json={"filename": contract_id, "clauses": clauses},
    )
    assert spot_resp.status_code == 200
    flag_ids = [f["clause_id"] for f in spot_resp.json()["flags"]]
    assert len(flag_ids) >= 2

    decisions_resp = client.post(
        f"/contracts/{contract_id}/decisions",
        json={
            "decisions": [
                {"clause_id": flag_ids[0], "decision": "approve"},
                {"clause_id": flag_ids[1], "decision": "reject"},
            ]
        },
    )
    assert decisions_resp.status_code == 200

    resp = client.get(f"/contracts/{contract_id}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_decisions"] is True
    # The two decisions are present with the canonical action names.
    by_id = {d["clause_id"]: d for d in body["decisions"]}
    assert by_id[flag_ids[0]]["action"] == "accepted"
    assert by_id[flag_ids[1]]["action"] == "rejected"


def test_state_after_redline_has_redlines(
    client: TestClient, spot_synthetic: None, drafter_happy_path: None
) -> None:
    """After ``/contracts/{id}/decisions`` produces a docx,
    the snapshot's ``has_redline`` is True and the redlines
    list has one entry per accepted clause_id.
    """
    contract_id = _new_contract_id("nda001")
    ingest_resp = _ingest(client, contract_id)
    clauses = ingest_resp["clauses"]

    spot_resp = client.post(
        "/contracts/spot",
        json={"filename": contract_id, "clauses": clauses},
    )
    assert spot_resp.status_code == 200
    flag_ids = [f["clause_id"] for f in spot_resp.json()["flags"]]
    assert len(flag_ids) >= 2

    # Approve 1, reject 1 → 1 accepted redline, 1 rejected (no redline).
    decisions_resp = client.post(
        f"/contracts/{contract_id}/decisions",
        json={
            "decisions": [
                {"clause_id": flag_ids[0], "decision": "approve"},
                {"clause_id": flag_ids[1], "decision": "reject"},
            ]
        },
    )
    assert decisions_resp.status_code == 200
    assert decisions_resp.json()["redlines_count"] >= 1

    resp = client.get(f"/contracts/{contract_id}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_redline"] is True
    redline_ids = [r["clause_id"] for r in body["redlines"]]
    assert flag_ids[0] in redline_ids
    # The accepted flag is the only one with a redline outcome
    # that is not "unavailable".
    accepted_redline = next(
        r for r in body["redlines"] if r["clause_id"] == flag_ids[0]
    )
    assert accepted_redline["outcome"] == "ok"


def test_state_refresh_after_full_flow_round_trip(
    client: TestClient, spot_synthetic: None, drafter_happy_path: None
) -> None:
    """The F3 scenario end-to-end.

    A user:
    1. Ingests a contract
    2. Spots the clauses
    3. Approves 1 flag, rejects 1
    4. Navigates to ``/contracts/{id}/review`` (the URL
       copies from the address bar into a chat, or the user
       hits refresh)
    5. The state endpoint must return everything needed to
       re-hydrate: clauses, flags, prior decisions, and the
       ``has_redline`` boolean so the page knows to show
       the redline view instead of the review view.

    This is the exact scenario F3 was raised about. If
    the snapshot is missing any of the four fields, the
    React page falls back to its broken behaviour (a blank
    page or a stuck loading state).
    """
    contract_id = _new_contract_id("nda001")
    ingest_resp = _ingest(client, contract_id)
    clauses = ingest_resp["clauses"]

    spot_resp = client.post(
        "/contracts/spot",
        json={"filename": contract_id, "clauses": clauses},
    )
    assert spot_resp.status_code == 200
    flag_ids = [f["clause_id"] for f in spot_resp.json()["flags"]]
    assert len(flag_ids) >= 2

    decisions_resp = client.post(
        f"/contracts/{contract_id}/decisions",
        json={
            "decisions": [
                {"clause_id": flag_ids[0], "decision": "approve"},
                {"clause_id": flag_ids[1], "decision": "reject"},
            ]
        },
    )
    assert decisions_resp.status_code == 200

    # The "refresh" — fresh state fetch, no in-memory
    # shortcut. The state endpoint is the only seam the
    # React page has into the backend.
    resp = client.get(f"/contracts/{contract_id}/state")
    assert resp.status_code == 200
    body = resp.json()

    # Every field the React page reads is present and
    # correctly populated.
    assert body["has_state"] is True
    assert body["has_ingest"] is True
    assert body["has_spot"] is True
    assert body["has_decisions"] is True
    assert body["has_redline"] is True
    assert body["filename"] == contract_id
    assert len(body["clauses"]) >= 1
    assert len(body["flags"]) >= 1
    assert len(body["decisions"]) == 2
    assert len(body["redlines"]) >= 1

    # The decisions are the ones the user submitted.
    by_id = {d["clause_id"]: d for d in body["decisions"]}
    assert by_id[flag_ids[0]]["action"] == "accepted"
    assert by_id[flag_ids[1]]["action"] == "rejected"


def test_state_url_uses_url_safe_contract_id(client: TestClient) -> None:
    """The endpoint URL must be safe to round-trip any
    contract id the spec's e2e flow uses (alphanumeric +
    dot + underscore + dash — the same characters the
    in-memory state store accepts as a key).
    """
    # Use a deliberately weird but URL-safe id.
    weird_id = "weird.id_with-mixed_chars-001"
    resp = client.get(f"/contracts/{weird_id}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["contract_id"] == weird_id
    assert body["has_state"] is False
