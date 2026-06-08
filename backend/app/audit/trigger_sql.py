"""DEPRECATED — kept only for back-compat; the migration is the source of truth.

The audit_events trigger DDL lives in
``backend/alembic/versions/0002_audit_log_phase3.py`` — that
file is the spec's chosen source of truth (card ``t_b527f54f``
hard rule: "the trigger lives in the migration file, not in
trigger_sql.py at runtime").

This module is preserved because (a) downstream tools and
docs may still import the constant names, and (b) deleting
it would be a noisy git operation that obscures the more
important fact — the migration owns the schema. **Do not
add new imports from this module.** Add the DDL to the
migration instead.

If you need the trigger DDL at runtime for a one-off script,
read the migration file directly. The constants here are
NOT guaranteed to be in sync with the migration.
"""

from __future__ import annotations


#: Name of the PL/pgSQL function that rejects UPDATE/DELETE.
#: DEPRECATED: read from the migration instead.
REJECT_FUNCTION_NAME = "reject_audit_mutation"

#: Trigger that fires BEFORE UPDATE on audit_events.
#: DEPRECATED: read from the migration instead.
UPDATE_TRIGGER_NAME = "audit_events_no_update"

#: Trigger that fires BEFORE DELETE on audit_events.
#: DEPRECATED: read from the migration instead.
DELETE_TRIGGER_NAME = "audit_events_no_delete"

#: The trigger function body. DEPRECATED: read from the
#: migration (``0002_audit_log_phase3.py``) instead. The
#: string here may be out of sync with the live DDL.
TRIGGER_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {REJECT_FUNCTION_NAME}() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only; % not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;
""".strip()


#: DDL that creates the BEFORE UPDATE trigger. DEPRECATED.
UPDATE_TRIGGER_SQL = f"""
DROP TRIGGER IF EXISTS {UPDATE_TRIGGER_NAME} ON audit_events;
CREATE TRIGGER {UPDATE_TRIGGER_NAME}
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION {REJECT_FUNCTION_NAME}();
""".strip()


#: DDL that creates the BEFORE DELETE trigger. DEPRECATED.
DELETE_TRIGGER_SQL = f"""
DROP TRIGGER IF EXISTS {DELETE_TRIGGER_NAME} ON audit_events;
CREATE TRIGGER {DELETE_TRIGGER_NAME}
    BEFORE DELETE ON audit_events
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
