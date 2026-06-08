"""Phase 2 test suite — playbook store + seed + counterparty loader.

These tests run against the live Postgres container (the same one
Phase 1 uses). The fixtures reuse the connection setup the seed
script uses (process-wide engine from ``app.db``).

What this suite covers
----------------------

- ``test_schema.py``    — schema creation is idempotent, embedding
                          column is the right pgvector type.
- ``test_seed.py``      — YAML parse, idempotent upsert, re-seed
                          produces no duplicate rows.
- ``test_topk.py``      — topk returns 3 nearest baselines with
                          cosine scores, the offline path works
                          when the gateway is unavailable, the
                          real path works when it is (skipped if
                          the gateway guardrails block).
- ``test_counterparty.py`` — flat matrix loader, default verdict
                          fallback, verdict enum maps to spotter
                          scores.

The tests do NOT touch the Phase 1 contract fixtures. Hard rule
from the kanban card: "Do NOT touch ``examples/expected/*.yaml``".

Async fixture / test support
----------------------------
We declare async fixtures with ``@pytest_asyncio.fixture`` and
mark async tests with ``@pytest.mark.asyncio``. The phase1 tests
are all sync (they use the sync LangGraph path) so this file
exists specifically to register the async pattern.

The shared event-loop scope is "session" — see the
``pytest_collection_modifyitems`` hook below. The reason: the
SQLAlchemy async engine in ``app.db`` is process-wide and binds
to the first event loop it sees. With pytest-asyncio's default
"function" loop scope, every test would try to use an engine
bound to a closed loop. Session-scope shares the loop and
keeps the engine happy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio

# Same convention as tests/conftest.py: ensure the backend
# package is importable when pytest is run from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def pytest_collection_modifyitems(config, items):
    """Auto-mark every async test in this directory with asyncio.

    Plus: rewrite the asyncio mode for the session to "auto" so
    the async fixtures declared in this file (and the tests that
    use them) don't need explicit per-test decoration.
    """
    config.option.asyncio_mode = "auto"
    for item in items:
        if isinstance(item, pytest.Function) and item.get_closest_marker("asyncio") is None:
            if item.obj.__code__.co_flags & 0x100:  # CO_COROUTINE
                item.add_marker(pytest.mark.asyncio)
