"""Top-level test conftest — ensures the backend ``app`` package is importable.

The Phase 1 tests live under ``tests/phase1/`` but the backend package
they import is at ``backend/app/``. Without this conftest, running
``pytest tests/`` from the repo root would fail with
``ModuleNotFoundError: No module named 'app'``.

The cleanest fix is to insert the backend directory into ``sys.path``
before any test module is imported. This is the standard pattern when
the test tree sits outside the package being tested.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root = parent of "tests". Backend is a sibling.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
