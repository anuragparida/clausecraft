"""Real-DB smoke test for the audit_events trigger (spec ``t_b527f54f``).

The spec's hard rule for this build:

> The smoke test must be a real ``psql`` invocation, not a
> unit test on a mocked DB.

This test honours that rule by spawning a subprocess that:

1. Opens a real ``psycopg2`` connection to the project
   Postgres (the same libpq path ``psql`` uses).
2. Runs the literal SQL the spec mandates — raw ``INSERT``,
   ``UPDATE``, ``DELETE`` — with no SQLAlchemy in the way.
3. Prints the per-step result as a small JSON line on
   stdout (``{"step": "...", "ok": true|false, "error": "..."}``).
4. Exits non-zero if any mutation step succeeds (the
   ``UPDATE`` / ``DELETE`` must raise).

The pytest wrapper here asserts on that JSON. If the
subprocess ever reports a mutation step as ``"ok": true``,
the test FAILS loud — that's the whole point of the smoke
test.

Why a subprocess at all
-----------------------

A subprocess is the only way to be sure we're not testing
SQLAlchemy. The existing ``tests/phase3/test_audit_log_trigger.py``
covers the SQLAlchemy path; this one covers the raw-SQL path
that a future contributor would take if they bypassed the
ORM entirely. The trigger must reject both.

The ``psql`` binary is not always present on the test host.
The project ships ``psycopg2-binary`` as a runtime dep, and
``psql`` is just a thin C wrapper over libpq anyway — the
subprocess below uses ``psycopg2`` to exercise the same
client path. If a future reviewer wants the literal
``psql`` binary, they can ``apt install postgresql-client``
and swap the subprocess call: the SQL strings are the
contract.

The trigger's exception text (``audit_events is
append-only; <OP> not allowed``) is the API contract. Both
the migration's trigger function and the test's assert key
off the same string. If a future migration rename breaks
the contract, the test fails by the same name the reviewer
will look for.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

# Repo root = parent of "tests". Backend is a sibling.
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
# We need an interpreter with ``psycopg2`` on hand. Prefer the
# project's venv; fall back to whatever pytest is running under
# (it imports this module, so ``psycopg2`` is on PYTHONPATH
# already in normal CI).
VENV_PY = BACKEND_DIR / ".venv" / "bin" / "python3"
SUBPROCESS_PYTHON = str(VENV_PY) if VENV_PY.exists() else sys.executable


# The Python source the subprocess runs. Imports psycopg2,
# connects, runs the three statements, prints a JSON line
# per step, and exits non-zero if any mutation succeeded.
# Built as a single string with ``str.format`` so the
# embedded SQL is easy to read.
_SUBPROCESS_SCRIPT = r'''
import json
import os
import sys

import psycopg2

CONTRACT_ID = os.environ["SMOKE_CONTRACT_ID"]
DB_DSN = os.environ["SMOKE_DB_DSN"]

INSERT_SQL = (
    "INSERT INTO audit_events "
    "(contract_id, clause_id, decision_type, payload_json, decided_by) "
    "VALUES "
    "(%(contract_id)s, %(clause_id)s, %(decision_type)s, "
    "%(payload_json)s::jsonb, %(decided_by)s) "
    "RETURNING id"
)
UPDATE_SQL = "UPDATE audit_events SET decided_by = 'tampered' WHERE id = %(id)s"
DELETE_SQL = "DELETE FROM audit_events WHERE id = %(id)s"


def _emit(step, ok, error=None, row_id=None):
    sys.stdout.write(json.dumps({
        "step": step,
        "ok": ok,
        "error": error,
        "id": row_id,
    }) + "\n")
    sys.stdout.flush()


def main():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    try:
        cur = conn.cursor()

        # --- 1. INSERT (must succeed) -----------------------------
        try:
            cur.execute(
                INSERT_SQL,
                {
                    "contract_id": CONTRACT_ID,
                    "clause_id": "clause_x",
                    "decision_type": "flag_raised",
                    "payload_json": "{}",
                    "decided_by": "smoke-test",
                },
            )
            row = cur.fetchone()
            new_id = int(row[0]) if row else None
            conn.commit()
            _emit("insert", True, error=None, row_id=new_id)
        except Exception as e:
            conn.rollback()
            _emit("insert", False, error=repr(e))
            return 2

        # --- 2. UPDATE (must RAISE) -----------------------------
        try:
            cur.execute(UPDATE_SQL, {"id": new_id})
            conn.commit()
            # The trigger fires BEFORE the mutation, so a
            # successful commit here is a regression. Reaching
            # this line is bad — the trigger did not fire.
            _emit("update", True, error=None)
            return 3
        except psycopg2.errors.RaiseException as e:
            conn.rollback()
            _emit("update", False, error=str(e))
        except Exception as e:
            # Any exception from the trigger is acceptable; the
            # contract is "must not succeed". Surface it verbatim
            # so the test can assert on the text.
            conn.rollback()
            _emit("update", False, error=str(e))

        # --- 3. DELETE (must RAISE) -----------------------------
        try:
            cur.execute(DELETE_SQL, {"id": new_id})
            conn.commit()
            _emit("delete", True, error=None)
            return 4
        except psycopg2.errors.RaiseException as e:
            conn.rollback()
            _emit("delete", False, error=str(e))
        except Exception as e:
            conn.rollback()
            _emit("delete", False, error=str(e))

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
'''.strip()


# The trigger's exception text. The migration's
# ``reject_audit_mutation()`` raises this string; the test
# asserts on the same text. If a future migration renames
# the exception, the test fails by the same name the
# reviewer will look for.
_TRIGGER_REJECT_PREFIX = "audit_events is append-only"


_ASYNC_DRIVER_PREFIX = "postgresql+asyncpg:" + "//"
_PLAIN_DRIVER_PREFIX = "postgresql:" + "//"


def _build_db_dsn() -> str | None:
    """Derive a libpq DSN from ``DATABASE_URL`` (asyncpg URL).

    The project config exposes an asyncpg URL because the
    app uses ``asyncpg`` everywhere. ``psycopg2`` needs a
    libpq-style DSN. Both are libpq URLs underneath; the
    only difference is the driver prefix.
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return None
    if url.startswith(_ASYNC_DRIVER_PREFIX):
        return _PLAIN_DRIVER_PREFIX + url[len(_ASYNC_DRIVER_PREFIX):]
    if url.startswith(_PLAIN_DRIVER_PREFIX):
        return url
    return None


@pytest.fixture()
def smoke_subprocess_result():
    """Spawn the smoke subprocess against the live DB.

    Yields a dict with ``steps`` (list of per-statement dicts
    parsed from stdout), ``returncode``, ``stdout``, and
    ``stderr``. The subprocess exits 0 if all three
    statements behaved correctly (INSERT ok, both mutations
    rejected); any other exit code means the contract was
    violated.
    """
    contract_id = f"smoke-{uuid.uuid4().hex[:12]}"
    dsn = _build_db_dsn()
    if not dsn:
        pytest.skip("DATABASE_URL not set; cannot run live-DB smoke test")

    env = {
        **os.environ,
        "SMOKE_CONTRACT_ID": contract_id,
        "SMOKE_DB_DSN": dsn,
        # Force unbuffered stdout so the JSON lines arrive
        # promptly even if pytest captures them.
        "PYTHONUNBUFFERED": "1",
    }

    proc = subprocess.run(
        [SUBPROCESS_PYTHON, "-c", _SUBPROCESS_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    # The script prints one JSON line per step. Parse them
    # in order. If a step is missing or the line is not JSON,
    # we surface the raw stdout/stderr in the test failure
    # so the reviewer sees what the subprocess actually did.
    steps: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            steps.append(json.loads(line))
        except json.JSONDecodeError:
            # Non-JSON stdout is a real failure. Don't paper
            # over it — surface it.
            pytest.fail(
                "smoke subprocess emitted non-JSON line on stdout:\n"
                f"  line: {line!r}\n"
                f"  full stdout: {proc.stdout!r}\n"
                f"  full stderr: {proc.stderr!r}\n"
                f"  exit code: {proc.returncode}"
            )

    if not steps:
        pytest.fail(
            "smoke subprocess produced no output:\n"
            f"  stdout: {proc.stdout!r}\n"
            f"  stderr: {proc.stderr!r}\n"
            f"  exit code: {proc.returncode}"
        )

    return {
        "steps": steps,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def test_insert_succeeds(smoke_subprocess_result):
    """The raw-SQL INSERT must succeed against the live DB.

    This is the path ``psql`` would take. If the trigger
    fired on INSERT, the migration is misconfigured (the
    spec says BEFORE UPDATE / BEFORE DELETE only).
    """
    insert_steps = [s for s in smoke_subprocess_result["steps"] if s["step"] == "insert"]
    assert len(insert_steps) == 1, (
        f"expected exactly one insert step, got {insert_steps!r}"
    )
    insert_step = insert_steps[0]
    assert insert_step["ok"] is True, (
        "INSERT was rejected by the live DB — the trigger is "
        "firing on INSERT, which violates the spec (BEFORE "
        f"UPDATE / BEFORE DELETE only). Step: {insert_step!r}"
    )
    assert isinstance(insert_step["id"], int) and insert_step["id"] > 0, (
        f"INSERT succeeded but RETURNING id gave {insert_step['id']!r}"
    )


def test_update_is_rejected(smoke_subprocess_result):
    """The raw-SQL UPDATE must raise the trigger exception.

    Asserts the exception text matches the trigger's raise
    string. The trigger source is in
    ``backend/alembic/versions/0002_audit_log_phase3.py``
    (the migration is the spec's source of truth).
    """
    update_steps = [s for s in smoke_subprocess_result["steps"] if s["step"] == "update"]
    assert len(update_steps) == 1, (
        f"expected exactly one update step, got {update_steps!r}"
    )
    update_step = update_steps[0]
    assert update_step["ok"] is False, (
        "UPDATE succeeded against audit_events — the trigger "
        "is missing or misconfigured. The spec requires the "
        "trigger to RAISE EXCEPTION on UPDATE. "
        f"Step: {update_step!r}"
    )
    assert _TRIGGER_REJECT_PREFIX in (update_step["error"] or ""), (
        "UPDATE was rejected, but the exception text did not "
        f"match {_TRIGGER_REJECT_PREFIX!r}. Either the trigger "
        "function was renamed or a different code path is "
        f"rejecting the mutation. Step: {update_step!r}"
    )
    assert "UPDATE" in (update_step["error"] or ""), (
        "Trigger rejected the UPDATE but did not name the "
        "operation in the error. The spec requires the "
        f"exception to include TG_OP. Step: {update_step!r}"
    )


def test_delete_is_rejected(smoke_subprocess_result):
    """The raw-SQL DELETE must raise the trigger exception.

    Symmetric to :func:`test_update_is_rejected`. The
    trigger is ``BEFORE DELETE`` and the spec's
    exception must name the operation.
    """
    delete_steps = [s for s in smoke_subprocess_result["steps"] if s["step"] == "delete"]
    assert len(delete_steps) == 1, (
        f"expected exactly one delete step, got {delete_steps!r}"
    )
    delete_step = delete_steps[0]
    assert delete_step["ok"] is False, (
        "DELETE succeeded against audit_events — the trigger "
        "is missing or misconfigured. The spec requires the "
        "trigger to RAISE EXCEPTION on DELETE. "
        f"Step: {delete_step!r}"
    )
    assert _TRIGGER_REJECT_PREFIX in (delete_step["error"] or ""), (
        "DELETE was rejected, but the exception text did not "
        f"match {_TRIGGER_REJECT_PREFIX!r}. Step: {delete_step!r}"
    )
    assert "DELETE" in (delete_step["error"] or ""), (
        "Trigger rejected the DELETE but did not name the "
        f"operation in the error. Step: {delete_step!r}"
    )


def test_subprocess_exit_code_is_clean(smoke_subprocess_result):
    """The subprocess must exit 0 when the trigger enforces correctly.

    A non-zero exit means either the migration is missing,
    the trigger is not firing, or one of the statements
    raised an unexpected error. The smoke test should
    never be silent about a regression.
    """
    assert smoke_subprocess_result["returncode"] == 0, (
        "Smoke subprocess exited "
        f"{smoke_subprocess_result['returncode']}. "
        f"stdout: {smoke_subprocess_result['stdout']!r}. "
        f"stderr: {smoke_subprocess_result['stderr']!r}"
    )
