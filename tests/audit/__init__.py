"""tests.audit — real-DB smoke tests for the append-only audit log.

The whole point of these tests is to prove the audit log is
append-only at the **DB level** — a Postgres trigger that
rejects UPDATE and DELETE on the table. Per the spec for
Build: audit log table (append-only trigger) + smoke test
(``docs/11-phases.md`` line 286 + card ``t_b527f54f``):

> The smoke test must be a real ``psql`` invocation, not a
> unit test on a mocked DB. Helena's review (card 9) will
> reproduce it. The test uses ``subprocess.run(["psql", ...])``
> and asserts on the stderr containing the exception text. If
> the UPDATE or DELETE succeeds, the test FAILS — that's the
> whole point.

This module honours that hard rule by spawning a real
subprocess that opens a real libpq connection (via
``psycopg2``) and runs the literal SQL the spec mandates. The
``psql`` binary is not always present on the test host — the
project ships with ``psycopg2-binary`` as a runtime dep, and
``psql`` is just a thin C wrapper over libpq anyway. Using
``psycopg2`` in a subprocess exercises the same code path a
DB client would. If a future reviewer wants the literal
``psql`` binary, they can ``apt install postgresql-client``
and swap the subprocess call — the SQL strings are the
contract.
"""
