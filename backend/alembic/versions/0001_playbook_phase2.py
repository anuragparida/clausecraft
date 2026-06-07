"""playbook_versions + playbook_clauses

Phase 2: the playbook store. Two tables:

- ``playbook_versions`` — one row per ``(contract_type, language,
  version)`` triple. The foreign key target for clauses.
- ``playbook_clauses`` — one row per baseline clause. Primary key
  ``(playbook_id, clause_id)``. The ``embedding`` column is
  ``vector(embedding_dim)`` — pgvector 0.5+ supports an HNSW index
  on it for fast top-k cosine queries.

The migration is the source of truth for the schema. The runtime
store also calls ``CREATE ... IF NOT EXISTS`` in
:func:`app.playbook.store.PlaybookStore.ensure_schema` so tests
on a fresh DB don't need to run alembic first. In production the
``alembic upgrade head`` step in the docker entrypoint runs this
migration before the FastAPI process starts.

Revision ID: 0001_playbook_phase2
Revises:
Create Date: 2026-06-07 22:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector  # type: ignore[import-not-found]


# revision identifiers, used by Alembic.
revision: str = "0001_playbook_phase2"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Match the runtime default in app.config.EmbeddingDim. If you
# change one, change the other; the store asserts the dimension
# against this value at query time.
EMBEDDING_DIM = 1024


def upgrade() -> None:
    # The pgvector extension is created by scripts/pgvector-init.sql
    # on first container init. CREATE EXTENSION here is a no-op when
    # it's already present, but explicit is better than implicit —
    # a dev spinning up Postgres without the init script still
    # gets the extension.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "playbook_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("contract_type", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "contract_type", "language", "version", name="playbook_versions_triple_uq"
        ),
    )

    op.create_table(
        "playbook_clauses",
        sa.Column(
            "playbook_id",
            sa.BigInteger(),
            sa.ForeignKey("playbook_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clause_id", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("retrieval_date", sa.Date(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("embedding_provider", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("playbook_id", "clause_id"),
    )
    # HNSW index for fast top-k cosine queries. ``vector_cosine_ops``
    # matches the ``<=>`` operator in
    # :func:`app.playbook.store.PlaybookStore.topk`. The index
    # requires pgvector 0.5+; the Docker image is pgvector/pgvector:pg16
    # which ships 0.8.x.
    op.execute(
        "CREATE INDEX IF NOT EXISTS playbook_clauses_embedding_idx "
        "ON playbook_clauses USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS playbook_clauses_embedding_idx")
    op.drop_table("playbook_clauses")
    op.drop_table("playbook_versions")
