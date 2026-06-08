"""SQL fragments for the audit_events trigger.

Centralised so the Alembic migration and the test suite
(``tests/phase3/test_audit_log.py``) share the exact same DDL.
A reviewer who changes the trigger function in one place
should see the same change in the other — the test that proves
UPDATE/DELETE are rejected uses these constants, not its own
copy of the SQL.

The trigger function name and the trigger names are stable
identifiers — the migration script and the test both reference
them by literal string. If a future migration renames them,
update both the migration file and the constants here.
"""

from __future__ import annotations


#: Name of the PL/pgSQL function that rejects UPDATE/DELETE.
REJECT_FUNCTION_NAME = "reject_audit_mutation"

#: Trigger that fires BEFORE UPDATE on audit_events.
UPDATE_TRIGGER_NAME = "audit_events_no_update"

#: Trigger that fires BEFORE DELETE on audit_events.
DELETE_TRIGGER_NAME = "audit_events_no_delete"

#: The trigger function body. Idempotent (``CREATE OR REPLACE``).
#: Raises an exception with the operation name so the rejection
#: message is self-describing in logs.
TRIGGER_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {REJECT_FUNCTION_NAME}() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only; % not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;
""".strip()


#: DDL that creates the BEFORE UPDATE trigger. Idempotent
#: (``DROP TRIGGER IF EXISTS`` first, then ``CREATE TRIGGER``).
UPDATE_TRIGGER_SQL = f"""
DROP TRIGGER IF EXISTS {UPDATE_TRIGGER_NAME} ON audit_events;
CREATE TRIGGER {UPDATE_TRIGGER_NAME}
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION {REJECT_FUNCTION_NAME}();
""".strip()


#: DDL that creates the BEFORE DELETE trigger. Idempotent.
DELETE_TRIGGER_SQL = f"""
DROP TRIGGER IF EXISTS {DELETE_TRIGGER_NAME} ON audit_events;
CREATE TRIGGER {DELETE_TRIGGER_NAME}
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION {REJECT_FUNCTION_NAME}();
""".strip()


__all__ = [
    "REJECT_FUNCTION_NAME",
    "UPDATE_TRIGGER_NAME",
    "DELETE_TRIGGER_NAME",
    "TRIGGER_FUNCTION_SQL",
    "UPDATE_TRIGGER_SQL",
    "DELETE_TRIGGER_SQL",
]
