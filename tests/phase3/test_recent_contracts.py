"""Tests for the ``GET /api/contracts`` "recent contracts" listing.

Phase 6 adds a "Recent contracts" card to the home page. The
card is fed by ``GET /api/contracts`` — a thin listing of the
in-memory :data:`app.pipeline.phase3_pipeline._STATE` store,
sorted by ``last_touched_at`` descending. This test module
covers three surfaces:

1. **Helper unit tests** (:func:`list_recent_contracts`) — no
   HTTP, no fixtures. Verifies the sort order, the row shape,
   and the ``limit`` clamp.
2. **Endpoint round-trip** — uses a FastAPI TestClient to
   exercise ``GET /api/contracts`` after a real ingest, so
   the row the user sees in the card matches the row the
   pipeline actually wrote.
3. **Endpoint edge cases** — empty store returns ``[]``;
   ``limit`` is clamped (defensive against a bad client).

The tests run against the real FastAPI app
(:class:`app.main.app`) but do not require a Postgres
connection — the state store is in-process. We use the
``reset_pipeline_state`` + TestClient + placeholder-LLM
pattern :mod:`tests.phase3.test_state_snapshot` uses.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import pytest
from fastapi.testclient import TestClient

from app.pipeline import phase3_pipeline


# --- Fixtures ------------------------------------------------------------


@pytest.fixture()
def reset_pipeline_state() -> Iterable[None]:
    """Clear the in-memory state store before and after every test.

    Same rationale as the state-snapshot tests: the store
    is process-local, so without this fixture a stale
    contract from a prior test would leak into the listing
    response.
    """
    phase3_pipeline._STATE.clear()
    yield
    phase3_pipeline._STATE.clear()


@pytest.fixture()
def client(reset_pipeline_state: None) -> Iterable[TestClient]:
    """A FastAPI TestClient bound to the real ``app.main`` ASGI app.

    Function-scoped so the in-memory state store is fresh
    for every test.
    """
    from app.main import app

    with TestClient(app) as c:
        yield c


# --- Helper --------------------------------------------------------------


def _seed_state(
    *,
    contract_id: str,
    filename: str | None = None,
    last_touched_at: datetime | None = None,
    clauses: list[dict[str, Any]] | None = None,
    flags: list[dict[str, Any]] | None = None,
    decisions: dict[str, dict[str, Any]] | None = None,
    output_docx_bytes: bytes = b"",
) -> phase3_pipeline.PipelineRunState:
    """Seed one :class:`PipelineRunState` directly into the store.

    Bypasses the real ingest / spot / decisions endpoints so
    the helper-level tests can assert ordering without paying
    for the full pipeline. The endpoint-level tests below use
    real ingest + the listing round-trip.
    """
    state = phase3_pipeline.PipelineRunState(
        contract_id=contract_id,
        filename=filename or contract_id,
    )
    state.clauses = clauses or []
    state.flags = flags or []
    state.decisions = decisions or {}
    state.output_docx_bytes = output_docx_bytes
    if last_touched_at is not None:
        state.last_touched_at = last_touched_at
    phase3_pipeline._STATE[contract_id] = state
    return state


# --- Helper unit tests --------------------------------------------------


def test_list_recent_contracts_empty_when_store_empty() -> None:
    """A fresh store returns an empty list.

    No raises, no 5xx — the home card renders the
    "no contracts yet" empty state on top of this list.
    """
    phase3_pipeline._STATE.clear()
    rows = phase3_pipeline.list_recent_contracts()
    assert rows == []


def test_list_recent_contracts_sorted_by_last_touched_desc() -> None:
    """Newer touches rank first.

    Three seeded contracts with explicit timestamps; the
    helper must return them in descending order regardless
    of insertion order.
    """
    phase3_pipeline._STATE.clear()
    now = datetime.now(timezone.utc)
    _seed_state(
        contract_id="a-old.pdf",
        last_touched_at=now - timedelta(hours=2),
    )
    _seed_state(
        contract_id="b-newest.pdf",
        last_touched_at=now,
    )
    _seed_state(
        contract_id="c-middle.pdf",
        last_touched_at=now - timedelta(hours=1),
    )

    rows = phase3_pipeline.list_recent_contracts()
    assert [r["contract_id"] for r in rows] == [
        "b-newest.pdf",
        "c-middle.pdf",
        "a-old.pdf",
    ]


def test_list_recent_contracts_row_shape_matches_api_model() -> None:
    """The row shape is the ``ContractSummaryResponse`` API contract.

    Pinning the keys here so a future schema drift (e.g.
    adding a field the home card doesn't read) breaks the
    test loud and early, before the React side starts
    reading missing keys.
    """
    expected_keys = {
        "contract_id",
        "filename",
        "has_ingest",
        "has_spot",
        "has_decisions",
        "has_redline",
        "clause_count",
        "flag_count",
        "decision_count",
        "last_touched_at",
    }
    phase3_pipeline._STATE.clear()
    _seed_state(
        contract_id="shape.pdf",
        clauses=[{"id": "c1"}, {"id": "c2"}],
        flags=[{"id": "f1"}],
        decisions={"c1": {"action": "accepted"}},
    )
    rows = phase3_pipeline.list_recent_contracts()
    assert len(rows) == 1
    assert set(rows[0].keys()) == expected_keys
    assert rows[0]["clause_count"] == 2
    assert rows[0]["flag_count"] == 1
    assert rows[0]["decision_count"] == 1
    assert rows[0]["has_ingest"] is True
    assert rows[0]["has_spot"] is True
    assert rows[0]["has_decisions"] is True
    assert rows[0]["has_redline"] is False


def test_list_recent_contracts_limit_clamped_to_safe_range() -> None:
    """The ``limit`` kwarg is clamped to ``1..50``.

    Defensive against a malicious / buggy client sending
    ``limit=0`` (empty list — surprising), ``limit=-1``
    (Python sort would crash), or ``limit=10_000`` (memory
    exhaustion).
    """
    phase3_pipeline._STATE.clear()
    for i in range(3):
        _seed_state(contract_id=f"contract-{i}.pdf")

    # limit=0 should clamp to 1.
    assert len(phase3_pipeline.list_recent_contracts(limit=0)) == 1
    # Negative should clamp to 1.
    assert len(phase3_pipeline.list_recent_contracts(limit=-5)) == 1
    # Huge should clamp to 50 (still ≤ 3 since only 3 seeded).
    assert len(phase3_pipeline.list_recent_contracts(limit=10_000)) == 3
    # Sane default 10.
    assert len(phase3_pipeline.list_recent_contracts(limit=10)) == 3


def test_list_recent_contracts_respects_limit() -> None:
    """With more contracts than ``limit``, the helper returns
    only the top ``limit`` by last_touched_at desc."""
    phase3_pipeline._STATE.clear()
    now = datetime.now(timezone.utc)
    for i in range(5):
        _seed_state(
            contract_id=f"contract-{i}.pdf",
            last_touched_at=now - timedelta(minutes=i),
        )
    rows = phase3_pipeline.list_recent_contracts(limit=2)
    assert len(rows) == 2
    assert rows[0]["contract_id"] == "contract-0.pdf"
    assert rows[1]["contract_id"] == "contract-1.pdf"


def test_get_state_bumps_last_touched_at() -> None:
    """Calling ``get_state`` updates ``last_touched_at`` to "now".

    This is the contract the home card relies on:
    touching a contract (ingest / spot / decisions /
    redline fetch) makes it rise to the top of the recent
    list. The bump happens inside :func:`get_state`
    itself so every endpoint that calls it gets the
    ordering for free.
    """
    phase3_pipeline._STATE.clear()
    state = _seed_state(
        contract_id="bumped.pdf",
        last_touched_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert state.last_touched_at.year == 2020

    # Read-back via the public ``get_state`` choke point.
    fresh = phase3_pipeline.get_state("bumped.pdf")
    assert fresh.last_touched_at.year >= 2026


# --- Endpoint round-trip ------------------------------------------------


def test_endpoint_returns_empty_list_on_fresh_server(
    client: TestClient,
) -> None:
    """``GET /api/contracts`` on a fresh process returns ``[]``."""
    resp = client.get("/api/contracts")
    assert resp.status_code == 200, (
        f"recent contracts endpoint must return 200, "
        f"got {resp.status_code} {resp.text[:500]!r}"
    )
    assert resp.json() == []


def test_endpoint_returns_one_row_after_real_ingest(
    client: TestClient,
) -> None:
    """After a real ``POST /contracts/ingest`` the endpoint
    returns one row matching the ingested contract's id
    and filename, with ``has_ingest=True`` and the
    remaining booleans False."""
    from tests.e2e.test_phase3_redline import CONTRACT_KNOWN_BAD

    if not CONTRACT_KNOWN_BAD.exists():
        pytest.fail(f"e2e fixture missing: {CONTRACT_KNOWN_BAD}")

    contract_id = f"ingest-recent-{uuid.uuid4().hex[:12]}.pdf"
    ingest_resp = client.post(
        "/contracts/ingest",
        files={
            "file": (contract_id, CONTRACT_KNOWN_BAD.read_bytes(), "application/pdf")
        },
    )
    assert ingest_resp.status_code == 200, (
        f"ingest failed: {ingest_resp.status_code} {ingest_resp.text[:500]!r}"
    )
    clause_count = ingest_resp.json()["clause_count"]

    resp = client.get("/api/contracts")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["contract_id"] == contract_id
    assert row["filename"] == contract_id
    assert row["has_ingest"] is True
    assert row["has_spot"] is False
    assert row["has_decisions"] is False
    assert row["has_redline"] is False
    assert row["clause_count"] == clause_count
    assert row["flag_count"] == 0
    assert row["decision_count"] == 0
    # ISO-8601 UTC. The helper normalises via ``datetime.now(timezone.utc)``
    # so the trailing "Z" / "+00:00" must be present and parseable.
    assert row["last_touched_at"].endswith("+00:00") or row["last_touched_at"].endswith(
        "Z"
    )
    parsed = datetime.fromisoformat(row["last_touched_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_endpoint_respects_query_limit(
    client: TestClient,
) -> None:
    """The ``?limit=N`` query param caps the response length."""
    phase3_pipeline._STATE.clear()
    now = datetime.now(timezone.utc)
    for i in range(5):
        _seed_state(
            contract_id=f"q-{i}.pdf",
            last_touched_at=now - timedelta(seconds=i),
        )

    resp = client.get("/api/contracts?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_endpoint_clamps_oversized_limit(
    client: TestClient,
) -> None:
    """A ``limit`` greater than the safe cap is silently clamped.

    The endpoint never raises on a bad value — it just
    clamps. The client UI uses a known-good default (10)
    but a malicious or curious client probing the API
    surface shouldn't be able to crash the server.
    """
    phase3_pipeline._STATE.clear()
    now = datetime.now(timezone.utc)
    for i in range(3):
        _seed_state(
            contract_id=f"clamp-{i}.pdf",
            last_touched_at=now - timedelta(seconds=i),
        )

    resp = client.get("/api/contracts?limit=99999")
    assert resp.status_code == 200
    assert len(resp.json()) == 3  # all of them, since only 3 seeded and cap is 50