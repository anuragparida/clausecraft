"""Test the idempotent seeder against the live Postgres container.

These tests use a dedicated playbook root and version so they
don't interfere with the Phase 2 dev data. Each test creates
its own versioned playbook (e.g. ``test-<uuid>``), seeds it,
then drops the playbook at the end.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db import get_session_factory
from app.playbook.seed import seed_all

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINES = REPO_ROOT / "playbook" / "baselines"


def _unique_version() -> str:
    """Per-test version so parallel test runs don't clobber each other."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def cleanup_playbook():
    """Drop the test playbook rows after the test, even on failure."""
    yield
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "DELETE FROM playbook_versions WHERE version LIKE 'test-%'"
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_seed_is_idempotent(cleanup_playbook):
    """Seeding the same data twice produces no duplicate rows."""
    version = _unique_version()
    # First seed
    summaries1 = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="en",
    )
    assert len(summaries1) == 1
    assert summaries1[0].clause_count == 5
    assert summaries1[0].contract_type == "nda"
    assert summaries1[0].language == "en"
    # Count rows after the first seed
    factory = get_session_factory()
    async with factory() as session:
        count1 = await session.scalar(
            text(
                "SELECT COUNT(*) FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
    assert count1 == 5
    # Second seed — same data, same version
    summaries2 = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="en",
    )
    assert summaries2[0].clause_count == 5
    async with factory() as session:
        count2 = await session.scalar(
            text(
                "SELECT COUNT(*) FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
    assert count2 == 5, "second seed created duplicate rows!"


@pytest.mark.asyncio
async def test_seed_inserts_provenance(cleanup_playbook):
    """Every clause has a source_url, retrieval_date, and license."""
    version = _unique_version()
    await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="en",
    )
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(
            text(
                "SELECT c.clause_id, c.source_url, c.retrieval_date, c.license "
                "FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
        rows = list(rows.mappings())
    assert len(rows) == 5
    for r in rows:
        assert r["source_url"].startswith("http")
        assert r["retrieval_date"] is not None
        assert r["license"]


@pytest.mark.asyncio
async def test_seed_rejects_invalid_clause_type(tmp_path, cleanup_playbook):
    """A YAML with a bad clause type fails the seed loudly."""
    bad = tmp_path / "baselines"
    bad.mkdir()
    (bad / "nda-en").mkdir()
    (bad / "nda-en" / "bad.yaml").write_text(
        """\
clause_id: bad-clause
type: nonsense_type_that_does_not_exist
language: en
title: Bad Clause
text: This is a clause with an invalid type field.
source_url: https://example.com
retrieval_date: 2026-01-01
license: CC0-1.0
"""
    )
    with pytest.raises(ValueError, match="not a valid ClauseType"):
        await seed_all(playbook_root=tmp_path, version="0.0.0-badtest")
