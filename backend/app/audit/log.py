"""Append-only writer for the audit log.

The :func:`record_event` function is the **only** entry point
this package exposes for writing to ``audit_events``. It:

1. Builds a single ``INSERT INTO audit_events ...`` statement.
2. Sets ``decided_by`` from ``settings.audit_decided_by`` (the
   single-operator config; spec says "authenticated user
   identifier, single-operator for now, so this is a config
   value or a session attribute").
3. Sets ``decided_at`` via the DB default (``NOW()``) — caller-
   supplied timestamps are ignored. The Pydantic model does NOT
   carry a timestamp field; the writer cannot accept one.

The function does not commit eagerly — it returns when the
session commit succeeds, raising on any error. The caller is
responsible for the surrounding transaction (or, for the graph
node path, the implicit one-shot INSERT).

If the migration is not yet applied, the function will raise
``ProgrammingError`` ("relation audit_events does not exist").
That is the right failure mode — it forces the migration to
run before the API can be exercised.

DB-level enforcement
--------------------

The trigger installed by the migration rejects UPDATE and
DELETE. The writer has no UPDATE or DELETE methods. The trigger
is the spec's hard requirement; this file's discipline is
defensive but the trigger is the actual enforcement.

If a future contributor accidentally adds an UPDATE method to
this module, the migration trigger will still raise on the
mutation. The trigger is the safety net, not a comment in this
file.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import DBAPIError

from app.audit.schema import AuditEvent
from app.config import settings
from app.db import get_session_factory
from app.observability import _NoopSpan, get_langfuse

logger = logging.getLogger(__name__)


def _finish_audit_span(span: Any, *, new_id: int | None, error: BaseException | None) -> None:
    """Close out the Langfuse span for an audit-log write.

    The trace update is wrapped in a broad except — a Langfuse
    outage must never affect the audit log we return. The
    pattern mirrors :func:`app.agents.deviation_spotter.spotter.
    _finish_trace` so the two paths are visibly the same shape
    when a reviewer greps for ``_finish_trace``.
    """
    try:
        if hasattr(span, "update"):
            if new_id is not None:
                span.update(
                    output={"id": new_id},
                    metadata={"error": str(error)} if error else {},
                )
            else:
                span.update(
                    output={},
                    metadata={"error": str(error)} if error else {},
                )
        if hasattr(span, "end"):
            span.end()
    except Exception:  # noqa: BLE001
        # A Langfuse client failure is non-fatal for the
        # audit-log write. The DB-level trigger is the real
        # enforcement; the trace is observability only.
        pass


def _resolved_decided_by(override: str | None) -> str:
    """Pick the ``decided_by`` value for the row.

    Priority:

    1. The explicit ``override`` argument (used by tests + the
       single place where a real authenticated user id might
       come in).
    2. ``settings.audit_decided_by`` (the config value, the
       single-operator default for now).

    The spec calls for the value to be "the authenticated user
    identifier (single-operator for now, so this is a config
    value or a session attribute)". When full auth lands the
    override path will be wired to the session; until then the
    config value is authoritative.
    """
    if override:
        return override
    return settings.audit_decided_by


async def record_event(event: AuditEvent, *, decided_by: str | None = None) -> int:
    """Append a single event to the audit log. Returns the new row id.

    Parameters
    ----------
    event
        The :class:`AuditEvent` Pydantic model. Field validation
        has already run by the time we get here.
    decided_by
        Optional override for the operator id. When ``None``
        (the default), :func:`_resolved_decided_by` picks
        ``settings.audit_decided_by``.

    Returns
    -------
    int
        The newly-inserted row's primary key. Useful for tests
        ("did it actually get written?") and for the future
        export (cite ``id`` + ``decided_at`` together).

    Raises
    ------
    sqlalchemy.exc.DBAPIError
        If the INSERT fails for any reason — the most common
        one in dev is the missing ``audit_events`` table (the
        migration hasn't run). The trigger rejection of
        UPDATE/DELETE is NOT raised here because the writer
        never issues them; the trigger rejection surfaces only
        in the UPDATE/DELETE tests.
    """
    by = _resolved_decided_by(decided_by)

    # ``use_enum_values=True`` on the Pydantic model means the
    # decision_type is already a plain string ("flag_accepted",
    # etc.) at this point.
    decision_type = (
        event.decision_type
        if isinstance(event.decision_type, str)
        else str(event.decision_type)
    )

    # The payload is a free-form dict; SQLAlchemy's JSONB column
    # accepts a Python dict directly. We pass the dict, not a
    # pre-serialised string — psycopg/asyncpg will serialise it
    # for us. A caller-supplied datetime inside the payload
    # would break the JSON encoder; we do a defensive str() to
    # avoid that surprise.
    payload: dict[str, Any] = {
        k: v if not hasattr(v, "isoformat") else v.isoformat()
        for k, v in event.payload_json.items()
    }

    # --- Langfuse trace wrap ----------------------------------
    # The audit log is the "did the agent decide correctly"
    # ledger. Every write is an observable event in Langfuse
    # so the dashboard can show the decision chain alongside
    # the LLM traces. The trace is wrapped in a broad except
    # so a Langfuse outage never fails the audit-log write
    # (the trigger is the real enforcement; the trace is
    # observability only — same posture as the deviation
    # spotter's _finish_trace).
    span: Any = _NoopSpan()
    new_id: int | None = None
    error: BaseException | None = None
    try:
        langfuse = get_langfuse()
        span = langfuse.trace(
            name="audit_event_record",
            input={
                "contract_id": event.contract_id,
                "clause_id": event.clause_id or "",
                "decision_type": decision_type,
                "decided_by": by,
                "payload_keys": sorted(payload.keys()),
            },
        )
    except Exception:  # noqa: BLE001
        span = _NoopSpan()

    try:
        factory = get_session_factory()
        async with factory() as session:
            async with session.begin():
                result = await session.execute(
                    AuditEventRow.__table__.insert().values(
                        contract_id=event.contract_id,
                        clause_id=event.clause_id or "",
                        decision_type=decision_type,
                        payload_json=payload,
                        decided_by=by,
                    )
                    .returning(AuditEventRow.__table__.c.id)
                )
                row = result.first()
                if row is None:
                    # Should be impossible — the trigger rejects
                    # UPDATE/DELETE, not INSERT. Defensive raise.
                    raise RuntimeError(
                        "audit_events INSERT returned no row (DB is misconfigured?)"
                    )
                new_id = int(row[0])
    except BaseException as e:  # noqa: BLE001
        error = e
        _finish_audit_span(span, new_id=None, error=e)
        raise
    else:
        _finish_audit_span(span, new_id=new_id, error=None)

    logger.info(
        "audit event recorded id=%s contract=%s clause=%s type=%s by=%s",
        new_id,
        event.contract_id,
        event.clause_id or "<pipeline>",
        decision_type,
        by,
    )
    return new_id  # type: ignore[return-value]


def is_audit_mutation_error(exc: BaseException) -> bool:
    """``True`` when ``exc`` is the trigger raising on UPDATE/DELETE.

    The migration's :func:`reject_audit_mutation` raises
    ``audit_events is append-only; <OP> not allowed``. The DBAPI
    wraps the error in a ``DBAPIError`` whose ``orig`` carries
    the Postgres exception. This helper is for the test suite
    (and any future defensive code that needs to distinguish
    "trigger rejected the mutation" from "table doesn't exist"
    or "column doesn't exist").

    Kept in this module (not the test) because the error string
    is the API contract — a future migration rename would need
    to update the tests AND this helper together.
    """
    if not isinstance(exc, DBAPIError):
        return False
    msg = str(exc.orig) if exc.orig is not None else str(exc)
    return "audit_events is append-only" in msg


# Imported here to avoid a circular import: the writer's
# ``__table__`` reference is the schema's SQLAlchemy class, so
# the schema module must be importable before this one runs.
# Doing the import at the bottom of the schema module is the
# wrong shape (the schema module shouldn't know about the
# writer); doing it here at the bottom keeps the dependency
# one-way (writer -> schema).
from app.audit.schema import AuditEventRow  # noqa: E402


__all__ = ["record_event", "is_audit_mutation_error"]
