"""Shared pytest fixtures for the Phase 1 test suite.

The fixtures here make the 5 test contracts available to every test
function in ``tests/phase1/`` by absolute path. The path is computed
relative to the repo root so the tests work both inside and outside
the backend Docker container.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# Repo root = parent of the "tests" directory.
# Path: tests/phase1/conftest.py -> parents[0]=phase1, parents[1]=tests, parents[2]=repo
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "examples" / "contracts" / "phase1_test"


def _contract(name: str) -> bytes:
    """Read a contract file by name and return its raw bytes."""
    path = CONTRACTS_DIR / name
    if not path.exists():
        pytest.fail(f"Missing test contract: {path}")
    return path.read_bytes()


@pytest.fixture(scope="session")
def aba_mutual_nda_bytes() -> bytes:
    return _contract("aba-mutual-nda.pdf")


@pytest.fixture(scope="session")
def weird_format_nda_bytes() -> bytes:
    return _contract("weird-format-nda.pdf")


@pytest.fixture(scope="session")
def short_nda_bytes() -> bytes:
    return _contract("short-nda.pdf")


@pytest.fixture(scope="session")
def long_nda_bytes() -> bytes:
    return _contract("long-nda.pdf")


@pytest.fixture(scope="session")
def scanned_style_nda_bytes() -> bytes:
    return _contract("scanned-style-nda.pdf")
