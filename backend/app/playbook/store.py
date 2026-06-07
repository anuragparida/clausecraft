"""Postgres + pgvector storage layer for the playbook.

Tables
------
``playbook_versions``
    One row per active playbook. Identified by
    ``(contract_type, language, version)`` — these three together
    are the "playbook identity" the seed script pins and the
    deviation spotter consults.

``playbook_clauses``
    One row per baseline clause. Primary key
    ``(playbook_id, clause_id)``. The ``embedding`` column is a
    ``vector(embedding_dim)`` (pgvector type) that the top-k
    helper uses for cosine similarity.

Design choices
--------------
- Idempotent upsert keyed on ``(playbook_id, clause_id)``. Re-
  seeding a playbook REPLACES the row (title, text, embedding,
  provenance) — there is no soft-delete or version-on-version
  history. The "playbook version" lives at the playbook level
  (the version string) and the audit trail lives in the
  Langfuse traces.
- We do NOT use SQLAlchemy ORM models for the playbook. The
  raw SQL is short, the migration is explicit, and going through
  ORM adds an import-time dependency on a future Mapped class
  that doesn't exist yet. Phase 3 (audit log) will introduce the
  first ORM model in a dedicated ``app.audit`` package.
- The session is the existing async session from
  :mod:`app.db`. The store is a thin wrapper that takes a
  session in its constructor; ``get_store()`` returns a
  convenience singleton that uses the process-wide factory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session_factory
from app.playbook.embeddings import EmbeddingResult

logger = logging.getLogger(__name__)


# --- Result types -------------------------------------------------------

@dataclass
class PlaybookTopKHit:
    """One row of a top-k query result.

    Attributes
    ----------
    clause_id
        The baseline's clause id.
    type
        ClauseType enum value (lowercase snake_case string).
    title
        Human-readable title.
    text
        The baseline text.
    source_url
        Provenance URL.
    distance
        The raw distance returned by pgvector's ``<=>`` cosine
        operator. Range: 0 (identical direction) to 2 (opposite
        direction). Most similar pairs are close to 0.
    similarity
        Convenience: ``1.0 - distance`` (cosine similarity in
        ``[-1, 1]``). Most similar pairs are close to 1.
    provider
        Embedding provider used for the QUERY (the probe clause)
        — not for the stored baseline. Useful for the smoke
        test to confirm the right path ran.
    """

    clause_id: str
    type: str
    title: str
    text: str
    source_url: str
    distance: float
    similarity: float
    provider: str


# --- Store --------------------------------------------------------------

class PlaybookStore:
    """Postgres + pgvector storage for playbook clauses.

    The store is created without a session; methods take a session
    or open one with the default factory. The intent is that the
    FastAPI dependency-injected session works in the request path
    and the ``__main__`` smoke test opens its own.
    """

    # SQL fragments kept as class-level strings so the migration
    # and the runtime SQL stay in sync (one source of truth).
    _EMBEDDING_DIM = settings.embedding_dim

    def __init__(self, embedding_dim: Optional[int] = None) -> None:
        self.embedding_dim = embedding_dim or self._EMBEDDING_DIM
        if self.embedding_dim <= 0:
            raise ValueError(
                f"embedding_dim must be positive, got {self.embedding_dim}"
            )

    # -- schema management ----------------------------------------------

    async def ensure_schema(self, session: AsyncSession) -> None:
        """Create the two playbook tables if they do not exist.

        Idempotent: safe to call on every boot, every seed, every
        test. The ``vector`` extension is created with
        ``IF NOT EXISTS`` so we don't race the migration script.

        The migration directory (``backend/alembic/versions/``) is
        the source of truth for the schema in production. This
        function is the "fresh DB" path used by tests and the
        smoke test — the migration runs first in production
        (via ``alembic upgrade head``) and this function is then
        a no-op.
        """
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS playbook_versions (
                    id              BIGSERIAL PRIMARY KEY,
                    contract_type   TEXT NOT NULL,
                    language        TEXT NOT NULL,
                    version         TEXT NOT NULL,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    description     TEXT,
                    UNIQUE (contract_type, language, version)
                )
                """
            )
        )
        await session.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS playbook_clauses (
                    playbook_id          BIGINT NOT NULL
                                            REFERENCES playbook_versions(id)
                                            ON DELETE CASCADE,
                    clause_id            TEXT NOT NULL,
                    type                 TEXT NOT NULL,
                    language             TEXT NOT NULL,
                    title                TEXT NOT NULL,
                    text                 TEXT NOT NULL,
                    source_url           TEXT NOT NULL,
                    retrieval_date       DATE NOT NULL,
                    license              TEXT NOT NULL,
                    embedding            vector({self.embedding_dim}),
                    embedding_provider   TEXT,
                    embedding_model      TEXT,
                    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (playbook_id, clause_id)
                )
                """
            )
        )
        # An HNSW index makes top-k fast. With 5 baselines it's
        # overkill, but the index is the right shape for Phase 5's
        # 30+ contracts. ``vector_cosine_ops`` matches the
        # ``<=>`` operator we use below.
        await session.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS playbook_clauses_embedding_idx
                ON playbook_clauses
                USING hnsw (embedding vector_cosine_ops)
                """
            )
        )
        await session.commit()

    # -- playbook version management ------------------------------------

    async def upsert_playbook_version(
        self,
        session: AsyncSession,
        *,
        contract_type: str,
        language: str,
        version: str,
        description: Optional[str] = None,
    ) -> int:
        """Insert (or reuse) the playbook version row.

        Returns the row's ``id`` — the foreign key used by
        :meth:`upsert_clause`.
        """
        result = await session.execute(
            text(
                """
                INSERT INTO playbook_versions
                    (contract_type, language, version, description)
                VALUES
                    (:contract_type, :language, :version, :description)
                ON CONFLICT (contract_type, language, version) DO UPDATE
                SET description = COALESCE(
                    EXCLUDED.description, playbook_versions.description
                )
                RETURNING id
                """
            ),
            {
                "contract_type": contract_type,
                "language": language,
                "version": version,
                "description": description,
            },
        )
        row = result.first()
        await session.commit()
        if row is None:
            raise RuntimeError(
                "upsert_playbook_version returned no row — should never happen"
            )
        return int(row[0])

    # -- clause upsert ---------------------------------------------------

    async def upsert_clause(
        self,
        session: AsyncSession,
        *,
        playbook_id: int,
        clause_id: str,
        type: str,
        language: str,
        title: str,
        text_body: str,
        source_url: str,
        retrieval_date,
        license: str,
        embedding: EmbeddingResult,
    ) -> int:
        """Insert or update a single baseline clause.

        Idempotent: re-running with the same ``(playbook_id, clause_id)``
        replaces the row's text, embedding, and provenance. This is
        the behaviour the CI seed re-run relies on — every test run
        re-seeds from the same YAML, and the table converges to the
        YAML state.

        Returns the number of rows affected (1 on insert, 1 on update,
        0 if the data was identical and the trigger-style ON CONFLICT
        path skipped — which doesn't actually happen with our SQL, but
        the contract is "always returns 1").
        """
        vec_literal = _numpy_vec_to_pgvector(embedding.embedding)
        await session.execute(
            text(
                """
                INSERT INTO playbook_clauses
                    (playbook_id, clause_id, type, language, title,
                     text, source_url, retrieval_date, license,
                     embedding, embedding_provider, embedding_model)
                VALUES
                    (:playbook_id, :clause_id, :type, :language, :title,
                     :text_body, :source_url, :retrieval_date, :license,
                     :embedding, :embedding_provider, :embedding_model)
                ON CONFLICT (playbook_id, clause_id) DO UPDATE SET
                    type = EXCLUDED.type,
                    language = EXCLUDED.language,
                    title = EXCLUDED.title,
                    text = EXCLUDED.text,
                    source_url = EXCLUDED.source_url,
                    retrieval_date = EXCLUDED.retrieval_date,
                    license = EXCLUDED.license,
                    embedding = EXCLUDED.embedding,
                    embedding_provider = EXCLUDED.embedding_provider,
                    embedding_model = EXCLUDED.embedding_model
                """
            ),
            {
                "playbook_id": playbook_id,
                "clause_id": clause_id,
                "type": type,
                "language": language,
                "title": title,
                "text_body": text_body,
                "source_url": source_url,
                "retrieval_date": retrieval_date,
                "license": license,
                "embedding": vec_literal,
                "embedding_provider": embedding.provider,
                "embedding_model": embedding.model,
            },
        )
        await session.commit()
        return 1

    # -- top-k retrieval -------------------------------------------------

    async def topk(
        self,
        session: AsyncSession,
        *,
        query_embedding: EmbeddingResult,
        k: int = 3,
        contract_type: Optional[str] = None,
        language: Optional[str] = None,
    ) -> list[PlaybookTopKHit]:
        """Return the ``k`` most similar baselines by cosine distance.

        The query is filtered by ``contract_type`` and ``language``
        when provided. Without a filter the query returns the
        top-k across every playbook in the table — useful for the
        smoke test, undesirable in production (the spotter should
        always pass both filters).
        """
        if k <= 0:
            return []
        vec_literal = _numpy_vec_to_pgvector(query_embedding.embedding)
        params: dict[str, object] = {
            "embedding": vec_literal,
            "k": int(k),
        }
        where_parts: list[str] = []
        if contract_type is not None:
            where_parts.append("v.contract_type = :contract_type")
            params["contract_type"] = contract_type
        if language is not None:
            where_parts.append("v.language = :language")
            params["language"] = language
        where_clause = ""
        if where_parts:
            where_clause = "WHERE " + " AND ".join(where_parts)
        sql = text(
            f"""
            SELECT
                c.clause_id,
                c.type,
                c.title,
                c.text,
                c.source_url,
                (c.embedding <=> :embedding) AS distance
            FROM playbook_clauses AS c
            JOIN playbook_versions AS v
              ON v.id = c.playbook_id
            {where_clause}
            ORDER BY c.embedding <=> :embedding ASC
            LIMIT :k
            """
        )
        result = await session.execute(sql, params)
        hits: list[PlaybookTopKHit] = []
        for row in result.mappings():
            distance = float(row["distance"])
            hits.append(
                PlaybookTopKHit(
                    clause_id=str(row["clause_id"]),
                    type=str(row["type"]),
                    title=str(row["title"]),
                    text=str(row["text"]),
                    source_url=str(row["source_url"]),
                    distance=distance,
                    similarity=1.0 - distance,
                    provider=query_embedding.provider,
                )
            )
        return hits

    # -- count + diagnostics --------------------------------------------

    async def clause_count(
        self,
        session: AsyncSession,
        *,
        playbook_id: Optional[int] = None,
    ) -> int:
        """Total number of clauses in the table, optionally scoped to a playbook."""
        if playbook_id is None:
            result = await session.execute(
                text("SELECT COUNT(*) FROM playbook_clauses")
            )
        else:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM playbook_clauses "
                    "WHERE playbook_id = :playbook_id"
                ),
                {"playbook_id": playbook_id},
            )
        return int(result.scalar_one())


# --- Singleton ----------------------------------------------------------

_default_store: Optional[PlaybookStore] = None


def get_store() -> PlaybookStore:
    """Return the process-wide :class:`PlaybookStore` singleton.

    Lazy-initialised so importing this module doesn't pay the
    cost of constructing an object that depends on settings. The
    store is stateless — it's safe to share across coroutines.
    """
    global _default_store
    if _default_store is None:
        _default_store = PlaybookStore()
    return _default_store


# --- Helpers ------------------------------------------------------------

def _numpy_vec_to_pgvector(vec: np.ndarray) -> str:
    """Serialise a numpy vector to pgvector's ``'[v1,v2,...]'`` format.

    pgvector's text representation is a JSON-array of floats.
    We use the same format for both queries (parameter binding)
    and inserts. The Python ``asyncpg`` driver will serialise the
    string as text; pgvector parses it on the server.

    We don't try to use pgvector's binary protocol — it would
    require the ``pgvector`` Python library and the binary
    codec, which adds a hard dep. The text format is what
    ``psql`` users see and what every pgvector tutorial shows,
    so the surface stays simple.
    """
    if vec.ndim != 1:
        raise ValueError(
            f"expected 1-D embedding, got shape {vec.shape!r}"
        )
    # tolist() returns a Python list of floats. str() gives
    # "[0.1, 0.2, ...]". Float repr is round-trip stable for
    # the 6 significant digits pgvector keeps.
    return "[" + ",".join(repr(float(x)) for x in vec.tolist()) + "]"


__all__ = [
    "PlaybookStore",
    "PlaybookTopKHit",
    "get_store",
]
