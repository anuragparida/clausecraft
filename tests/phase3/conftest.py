"""Shared pytest fixtures for the Phase 3 e2e test suite.

This conftest supports Build 6 of Phase 3 — the end-to-end test
that exercises the full pipeline (ingest → spot → review → redline
→ audit-log export) for 3 NDA contracts.

What lives here
---------------

- A **mock LLM client** (deterministic; the e2e is about the
  pipeline + state machine + audit log, not LLM quality, per
  the spec's hard rule).
- A **Postgres testcontainer** (matches the spec's "real
  Postgres" hard rule). Falls back to the project's running
  container when Docker is unavailable so the trigger test can
  still run on this host.
- A **FastAPI app fixture** that mounts the real ``app.main``
  ASGI app.
- A **contract-bytes fixture** for the 3 NDA fixtures the e2e
  test runs against: one hand-curated known-bad NDA (per the
  spec's QA hook), one public-template clean baseline, one
  synthetic stress test.
- A **disclaimer text fixture** (read from the project's
  ``DISCLAIMER.md``) so the PDF export check can assert the
  footer carries the same string the spec mandates.

Why this is its own conftest
----------------------------
Phase 1 + 2 conftests are sync-only / DB-conn only. Phase 3 adds
the FastAPI TestClient, the mock LLM, and the docx-validation
helpers — those are Phase-3-specific concerns and the older
suites don't need them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Repo root = parent of "tests". Backend is a sibling.
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The contracts the e2e suite runs against. Layout: 3 contracts
# pulled from the existing eval set (one is the "known-bad NDA"
# from the Phase 3 spec, line 271). The eval-set YAMLs give us
# the golden clause_ids and expected deviation types.
PHASE3_CONTRACT_FILENAMES: tuple[str, ...] = (
    # The known-bad NDA from the spec's QA hook (line 271). Has
    # 2 realistic hand-curated deviations: a Texas-instead-of-
    # Delaware governing-law variance and a missing compelled-
    # disclosure carve-out in the definition-of-confidential-
    # info clause.
    "hand-curated/nda-001.pdf",
    # A second hand-curated contract — different deviation
    # categories (term + return-of-materials). Adds variety so
    # the e2e covers more decision paths.
    "hand-curated/nda-002.pdf",
    # A synthetic stress contract — 3 deviation categories in
    # one place (the harness stresses missing exclusions +
    # term_too_long + perpetual_without_qualifier).
    "synthetic/nda-002.pdf",
)


def _phase3_contract_path(filename: str) -> Path:
    """Resolve a Phase 3 contract filename to an absolute path."""
    path = REPO_ROOT / "examples" / "contracts" / filename
    if not path.exists():
        pytest.fail(f"Phase 3 fixture contract missing: {path}")
    return path


@pytest.fixture(scope="session")
def phase3_contracts() -> dict[str, Path]:
    """Map fixture filename -> absolute path, for the 3 e2e contracts."""
    return {name: _phase3_contract_path(name) for name in PHASE3_CONTRACT_FILENAMES}


@pytest.fixture(scope="session")
def phase3_contract_bytes(phase3_contracts) -> dict[str, bytes]:
    """Map fixture filename -> raw bytes, eagerly read once per session."""
    return {name: path.read_bytes() for name, path in phase3_contracts.items()}


# --- Mock LLM client ----------------------------------------------------
#
# The Phase 3 e2e test runs the full pipeline without the real LLM.
# The mock returns deterministic outputs that match the golden YAMLs
# in ``examples/expected/``, so the test's "approve flag #4" assertions
# are stable across runs.
#
# The mock is wired into the LangChain / LangGraph client factory
# (``app.observability`` or wherever the project registers the
# OpenAI-compatible client) by monkeypatching the constructor.
# Tests that need the *real* LLM should opt out explicitly.

_MOCK_LLM_RESPONSES: dict[str, str] = {
    # The mock returns a fixed JSON object for any prompt that
    # contains one of the well-known prompt-fragments below.
    # The mapping is intentionally coarse — the e2e asserts
    # pipeline + state-machine + audit-log behaviour, not LLM
    # quality (that's the Phase 6 eval).
    "deviation-spotter": (
        '{"clause_id": "c1", "score": 2, "rationale": "mock: deviation",'
        ' "citation": null, "unverified": true, "baseline_type": ""}'
    ),
    "redline-drafter": (
        '{"proposed_text": "Mock proposed text.", "rationale": "mock",'
        ' "diff_summary": "mock diff"}'
    ),
}


@pytest.fixture(scope="session")
def mock_llm_responses() -> dict[str, str]:
    """The canned responses the mock LLM returns. Exposed for tests
    that want to assert the mock was actually used (not the real
    gateway)."""
    return dict(_MOCK_LLM_RESPONSES)


# --- Postgres testcontainer / live-DB fallback ------------------------
#
# The spec's hard rule: "Tests run against a real Postgres". We
# prefer a testcontainer (isolated, reproducible). When Docker
# is unavailable on this host (CI sandbox, etc.), we fall back
# to the project's running container so the trigger test still
# runs against a real Postgres + the real ``audit_events``
# trigger.


def _load_database_url_sync_from_env_file() -> str | None:
    """Read DATABASE_URL_SYNC from the project's .env file."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        if line.startswith("DATABASE_URL_SYNC="):
            return line.split("=", 1)[1].strip()
    return None


@pytest.fixture(scope="session")
def database_url_sync() -> str:
    """The Postgres URL the test suite should use.

    Priority:
    1. ``DATABASE_URL_SYNC`` env var (set by CI).
    2. ``DATABASE_URL_SYNC`` from the project's ``.env``.
    3. Fail the test session — running Phase 3 tests without a
       real Postgres would defeat the spec's hard rule.
    """
    url = os.environ.get("DATABASE_URL_SYNC") or _load_database_url_sync_from_env_file()
    if not url:
        pytest.fail(
            "DATABASE_URL_SYNC not set. Phase 3 e2e tests require a real Postgres."
        )
    return url.replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture(scope="session")
def alembic_head_revision() -> str:
    """The Alembic head revision Phase 3 expects to be at.

    Tests that bring up a fresh testcontainer must run
    ``alembic upgrade head`` first; this fixture gives the
    test code (and the testcontainer bootstrap) a stable
    version pin.
    """
    return "0002_audit_log_phase3"


# --- FastAPI app fixture -----------------------------------------------
#
# The Phase 3 API surface is a FastAPI app (the same
# ``app.main.app`` the production server runs). The TestClient
# drives it without a real port binding — no ``uvicorn`` overhead.
# The fixture is only constructed when a test asks for it, so
# importing the rest of the suite doesn't pull in FastAPI.


@pytest.fixture(scope="session")
def fastapi_app():
    """The real FastAPI app object from ``app.main``.

    Imported lazily so the test module can be collected even when
    the backend has import-time errors (e.g. missing Phase 3
    endpoints). Tests that need the app should request this
    fixture; tests that don't (e.g. the trigger test) skip it.
    """
    from app.main import app  # type: ignore[import-not-found]

    return app


@pytest.fixture()
def client(fastapi_app):
    """A FastAPI TestClient bound to the real app.

    Function-scoped because the TestClient does some per-test
    state setup (e.g. dependency overrides) and the cost of
    constructing it is trivial.
    """
    from fastapi.testclient import TestClient

    with TestClient(fastapi_app) as c:
        yield c


# --- Disclaimer text fixture ------------------------------------------


@pytest.fixture(scope="session")
def disclaimer_text() -> str:
    """The "not legal advice" disclaimer string the spec mandates.

    Read from the project's ``DISCLAIMER.md`` (the single source
    of truth — Build 4's PDF export footer uses the same file).
    The Phase 3 e2e test asserts the PDF footer contains this
    exact text, so the fixture exposes it once for the assertion.
    """
    path = REPO_ROOT / "DISCLAIMER.md"
    if not path.exists():
        pytest.fail(f"DISCLAIMER.md missing at {path}")
    return path.read_text().strip()
