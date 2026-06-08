"""Audit log — Phase 3 demo-credibility build.

This package is the **only** API surface for writing to the
``audit_events`` table. Direct SQL ``INSERT`` from anywhere else
(FastAPI routes, agent code, ad-hoc scripts) is forbidden by the
Phase 3 spec.

Public surface
--------------

- :class:`AuditEvent` — Pydantic input shape for a single event.
  Callers build one, then call :func:`record_event`.
- :class:`AuditEventRow` — the SQLAlchemy row (read-only; never
  used for UPDATE).
- :func:`record_event` — the writer. Single ``INSERT``. Sets
  ``decided_at`` server-side via ``NOW()`` regardless of what
  the caller passed. Sets ``decided_by`` from
  ``settings.audit_decided_by`` (the single-operator config).

DB-level enforcement
--------------------

The ``audit_events`` table is enforced as append-only at the
**Postgres trigger** level (not in code). The migration that
creates the table also installs:

- :func:`reject_audit_mutation` (PL/pgSQL) — raises an exception
  on any UPDATE or DELETE.
- ``audit_events_no_update`` and ``audit_events_no_delete``
  triggers — bind the function to UPDATE and DELETE events.

The trigger is the spec's hard requirement. A reviewer who tries
``UPDATE audit_events SET ...`` must get an exception from the DB,
not from the writer code.

See :mod:`app.audit.migrations` for the migration that wires this
up, and ``tests/phase3/test_audit_log.py`` for the test that
proves the trigger rejects UPDATE/DELETE.
"""

from __future__ import annotations

from app.audit.schema import (
    AuditEvent,
    AuditEventRow,
    DecisionType,
)
from app.audit.log import record_event

__all__ = [
    "AuditEvent",
    "AuditEventRow",
    "DecisionType",
    "record_event",
]
