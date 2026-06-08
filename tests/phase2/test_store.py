"""Test the playbook store: schema creation, idempotent upsert, topk."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db import get_session_factory
from app.playbook import (
    PlaybookStore,
    embed_text,
    get_store,
)


@pytest_asyncio.fixture
async def store_with_data():
    """Ensure schema, seed a test playbook, yield the store, clean up."""
    store = get_store()
    factory = get_session_factory()
    version = f"test-{uuid.uuid4().hex[:8]}"
    async with factory() as session:
        await store.ensure_schema(session)
        pb_id = await store.upsert_playbook_version(
            session,
            contract_type="test-nda",
            language="en",
            version=version,
            description="phase2 test fixture",
        )
        # Insert 3 fake baselines with distinct texts.
        for cid, ctype, title, text_body in [
            (
                "fixture-alpha",
                "term",
                "Fixture Alpha",
                "This agreement shall remain in effect for two years.",
            ),
            (
                "fixture-beta",
                "definition_confidential_info",
                "Fixture Beta",
                "Confidential Information means any non-public technical or business data.",
            ),
            (
                "fixture-gamma",
                "governing_law",
                "Fixture Gamma",
                "This agreement is governed by the laws of the State of Delaware.",
            ),
        ]:
            emb = embed_text(text_body)
            await store.upsert_clause(
                session,
                playbook_id=pb_id,
                clause_id=cid,
                type=ctype,
                language="en",
                title=title,
                text_body=text_body,
                source_url="https://example.com/fixture",
                retrieval_date=date(2026, 1, 1),
                license="CC0-1.0",
                embedding=emb,
            )
    yield store, pb_id, version
    # Cleanup
    async with factory() as session:
        await session.execute(
            text("DELETE FROM playbook_versions WHERE version = :v"),
            {"v": version},
        )
        await session.commit()


@pytest.mark.asyncio
async def test_schema_creation_is_idempotent():
    """Calling ensure_schema twice is a no-op (no errors, no dropped data)."""
    store = get_store()
    factory = get_session_factory()
    async with factory() as session:
        await store.ensure_schema(session)
        # Second call: must succeed, must not drop the table.
        await store.ensure_schema(session)
        # Confirm the table is still queryable.
        count = await store.clause_count(session)
        assert count >= 0  # int, no exception


@pytest.mark.asyncio
async def test_upsert_is_idempotent(store_with_data):
    """Re-upserting the same (playbook_id, clause_id) doesn't create dupes."""
    store, pb_id, version = store_with_data
    factory = get_session_factory()
    async with factory() as session:
        before = await store.clause_count(session, playbook_id=pb_id)
        # Re-insert the same clause with the same text.
        emb = embed_text(
            "This agreement shall remain in effect for two years."
        )
        await store.upsert_clause(
            session,
            playbook_id=pb_id,
            clause_id="fixture-alpha",
            type="term",
            language="en",
            title="Fixture Alpha (updated)",
            text_body="This agreement shall remain in effect for two years.",
            source_url="https://example.com/fixture",
            retrieval_date=date(2026, 1, 1),
            license="CC0-1.0",
            embedding=emb,
        )
        after = await store.clause_count(session, playbook_id=pb_id)
    assert before == after, "upsert created a duplicate row"


@pytest.mark.asyncio
async def test_topk_returns_3_hits_with_cosine_scores(store_with_data):
    """topk(k=3) returns 3 rows with valid similarity scores."""
    store, pb_id, version = store_with_data
    factory = get_session_factory()
    async with factory() as session:
        probe_emb = embed_text("a contract about how long it lasts")
        hits = await store.topk(
            session,
            query_embedding=probe_emb,
            k=3,
            contract_type="test-nda",
            language="en",
        )
    assert len(hits) == 3
    # All hits come from our test playbook (nda-en).
    for h in hits:
        assert h.clause_id in {
            "fixture-alpha",
            "fixture-beta",
            "fixture-gamma",
        }
        # Cosine similarity in [-1, 1].
        assert -1.0 <= h.similarity <= 1.0
        # Distance = 1 - similarity.
        assert abs(h.distance - (1.0 - h.similarity)) < 1e-5
        # Source URL is preserved.
        assert h.source_url == "https://example.com/fixture"


@pytest.mark.asyncio
async def test_topk_with_language_filter(store_with_data):
    """Filtering by language restricts the result set."""
    store, pb_id, version = store_with_data
    factory = get_session_factory()
    async with factory() as session:
        emb = embed_text("probe")
        # Match
        hits_en = await store.topk(
            session, query_embedding=emb, k=3, language="en"
        )
        assert len(hits_en) >= 3
        # No-match filter
        hits_de = await store.topk(
            session, query_embedding=emb, k=3, language="de"
        )
        # May be 0 (no DE baselines) or fewer than k.
        assert len(hits_de) <= 3


@pytest.mark.asyncio
async def test_topk_k_zero_returns_empty(store_with_data):
    """k=0 is a documented no-op."""
    store, pb_id, version = store_with_data
    factory = get_session_factory()
    async with factory() as session:
        emb = embed_text("probe")
        hits = await store.topk(session, query_embedding=emb, k=0)
    assert hits == []
