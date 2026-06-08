"""Phase 3 — audit log trigger enforcement test.

This is the spine of Review 2 (Helena's highest-priority
review of the phase). The spec calls for the audit log to
be append-only at the **DB level** — a Postgres trigger
that rejects UPDATE / DELETE on the table. The hard rule
from Build 3: "If the trigger is missing, the build is not
done."

The two tests in this file exercise the trigger end-to-end:

- :func:`test_update_is_rejected` — INSERT a row, then try
  to UPDATE it. The trigger must raise.
- :func:`test_delete_is_rejected` — INSERT a row, then try
  to DELETE it. The trigger must raise.

We use the project's existing ``app.audit.log`` module —
the writer + the :func:`is_audit_mutation_error` helper —
rather than raw SQL. The helper's contract is the same
"audit_events is append-only" string the trigger raises,
so the test will fail loudly if a future migration rename
breaks the contract.

The tests are **not** e2e in the "hit the API" sense —
they exercise the audit log writer + the trigger directly.
The reason: the spec's hard rule for Build 6 is "tests run
against a real Postgres (the append-only trigger is
exercised by these tests, which is the only thing that
makes Review 2's claim credible)". So this is the test
that backs the review.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

from app.audit.log import is_audit_mutation_error, record_event
from app.audit.schema import AuditEvent, AuditEventRow, DecisionType
from app.db import get_session_factory


# Unique contract_id per test run so concurrent test sessions
# don't trip on each other. The audit_events table is append-only,
# so we cannot clean up — but each test inserts under its own
# contract_id and asserts on that row only.
_RUN_ID = uuid.uuid4().hex[:12]


@pytest_asyncio.fixture()
async def inserted_row_id():
    """Insert one audit row, yield its id, leave the row in place
    (the trigger forbids DELETE)."""
    ev = AuditEvent(
        contract_id=f"test-trigger-{_RUN_ID}",
        clause_id="c1",
        decision_type=DecisionType.GRAPH_STARTED,
        payload_json={"trigger": "build-6-test"},
    )
    row_id = await record_event(ev, decided_by="trigger-test")
    return row_id


async def test_update_is_rejected(inserted_row_id):
    """The trigger must raise when a row is UPDATEd.

    Uses the SQLAlchemy ``update()`` construct (not raw
    SQL) because that's the path a future contributor
    would naturally take. The trigger fires regardless
    of the client, so this catches the "rogue writer"
    failure mode the spec calls out.
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            with pytest.raises(DBAPIError) as exc_info:
                stmt = (
                    update(AuditEventRow)
                    .where(AuditEventRow.id == inserted_row_id)
                    .values(decision_type="x")
                )
                await session.execute(stmt)
                await session.commit()
            assert is_audit_mutation_error(exc_info.value), (
                "DBAPIError was raised but is_audit_mutation_error() returned False. "
                f"Exception: {exc_info.value!r}"
            )
    finally:
        await factory().close()


async def test_delete_is_rejected(inserted_row_id):
    """The trigger must raise when a row is DELETEd.

    Same pattern as :func:`test_update_is_rejected`. The
    "append-only" rule is two-sided: no UPDATE *and* no
    DELETE. Review 2 will check both.
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            with pytest.raises(DBAPIError) as exc_info:
                stmt = delete(AuditEventRow).where(AuditEventRow.id == inserted_row_id)
                await session.execute(stmt)
                await session.commit()
            assert is_audit_mutation_error(exc_info.value), (
                "DBAPIError was raised but is_audit_mutation_error() returned False. "
                f"Exception: {exc_info.value!r}"
            )
    finally:
        await factory().close()


async def test_writer_only_inserts():
    """The :func:`app.audit.log.record_event` writer must accept a
    fresh insert under a unique contract_id without raising.

    Sanity check that the writer is wired to the right
    table. If the migration wasn't applied, this test
    fails with ``ProgrammingError: relation does not
    exist`` — which is the right failure mode (the spec
    mandates the migration run before the API can be
    exercised).
    """
    contract_id = f"test-insert-{_RUN_ID}-{uuid.uuid4().hex[:6]}"
    ev = AuditEvent(
        contract_id=contract_id,
        clause_id="c2",
        decision_type=DecisionType.FLAG_ACCEPTED,
        payload_json={"flag_id": "c2", "score": 1},
    )
    new_id = await record_event(ev, decided_by="insert-test")
    assert isinstance(new_id, int) and new_id > 0, (
        f"record_event returned {new_id!r}, expected a positive int"
    )
