"""audit_events + append-only trigger (Phase 3).

Adds the audit log table and the PL/pgSQL trigger that
enforces the "no UPDATE / no DELETE" rule. The trigger is the
spec's hard requirement — a reviewer who tries to UPDATE a row
must get an exception from the DB, not from application code.

The trigger is installed with DROP TRIGGER IF EXISTS /
CREATE TRIGGER pairs so the migration is idempotent. A
container that's been brought up, then restarted, then brought
up again, will pass ``alembic upgrade head`` cleanly.

Why the trigger is the enforcement (not a code comment)
--------------------------------------------------------
The writer in :mod:`app.audit.log` only ever issues an INSERT.
That discipline is real, but a future contributor who adds a
``update()`` or ``delete()`` method to that module would
silently mutate the audit log — the kind of failure mode the
spec explicitly calls out. The trigger makes that
impossible at the DB level: even if a future writer goes
rogue, Postgres refuses the mutation.

The trigger fires BEFORE the row is touched, so it is also
cheaper than a row-level CHECK constraint that runs after
the mutation. Review 2 (Helena) is the regulated-work eye
that verifies this; the test
``tests/phase3/test_audit_log.py::test_update_is_rejected``
and ``::test_delete_is_rejected`` exercise the trigger
end-to-end.

Schema (matches :class:`app.audit.schema.AuditEventRow`):

- ``id`` BIGSERIAL PRIMARY KEY
- ``contract_id`` VARCHAR(256) NOT NULL
- ``clause_id`` VARCHAR(64) NOT NULL DEFAULT ''
- ``decision_type`` VARCHAR(64) NOT NULL
- ``payload_json`` JSONB NOT NULL DEFAULT '{}'::jsonb
- ``decided_by`` VARCHAR(128) NOT NULL
- ``decided_at`` TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indexes:

- btree on ``contract_id`` (the audit replay view filters by
  contract)
- btree on ``decision_type`` (the audit replay view groups by
  type)
- GIN on ``payload_json`` (the future export path does
  ``payload_json @> '{...}'`` predicates)

The GIN index is the only one that uses pgvector / special
syntax; the btree indexes use the standard ``create_index``
op. The GIN index is installed with raw SQL because
SQLAlchemy's ``postgresql_using='gin'`` is verbose and we'd
rather have one place to read it.

Revision ID: 0002_audit_log_phase3
Revises: 0001_playbook_phase2
Create Date: 2026-06-08 09:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "0002_audit_log_phase3"
down_revision: Union[str, None] = "0001_playbook_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: SQL fragment for the trigger function. Matches the
#: :mod:`app.audit.trigger_sql` constants — if you change one,
#: change the other (the test suite imports the same constants).
REJECT_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only; % not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;
""".strip()


def upgrade() -> None:
    """Create the audit_events table + indexes + triggers."""
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("contract_id", sa.String(length=256), nullable=False),
        sa.Column(
            "clause_id",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("decision_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("decided_by", sa.String(length=128), nullable=False),
        sa.Column(
            "decided_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # btree indexes — written via the Alembic helper so the
    # naming convention is consistent with the rest of the
    # project's migrations.
    op.create_index(
        "audit_events_contract_id_idx",
        "audit_events",
        ["contract_id"],
        unique=False,
    )
    op.create_index(
        "audit_events_decision_type_idx",
        "audit_events",
        ["decision_type"],
        unique=False,
    )
    # GIN index on the JSONB column for the future export /
    # replay predicates. Raw SQL because the SQLAlchemy GIN
    # helper requires both a column and a ``postgresql_using``
    # kwarg, and one place is easier to read than two.
    op.execute(
        "CREATE INDEX IF NOT EXISTS audit_events_payload_json_gin "
        "ON audit_events USING GIN (payload_json)"
    )

    # --- Append-only enforcement ------------------------------
    # The function first (idempotent), then the two triggers
    # (also idempotent: DROP IF EXISTS before CREATE).
    op.execute(REJECT_FUNCTION_SQL)
    op.execute(
        "DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_update "
        "BEFORE UPDATE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_delete "
        "BEFORE DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )


def downgrade() -> None:
    """Drop the audit_events table and its triggers."""
    # Drop the triggers first so the DROP TABLE doesn't fire
    # the DELETE trigger. The function is left in place — it's
    # reusable across other append-only tables in the future
    # and is harmless without a table that uses it.
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events")
    op.execute("DROP INDEX IF EXISTS audit_events_payload_json_gin")
    op.drop_index("audit_events_decision_type_idx", table_name="audit_events")
    op.drop_index("audit_events_contract_id_idx", table_name="audit_events")
    op.drop_table("audit_events")
