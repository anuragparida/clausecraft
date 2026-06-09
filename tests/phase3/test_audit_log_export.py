"""Phase 3 Build 4 — audit log export tests.

The spec's Build 4 acceptance criteria are the spine:

- "A test that runs the full Phase 3 flow on a fixture,
  then calls both export endpoints, validates:
  - JSON has ≥1 row per stage (spot / approve / reject /
    edit / redline)
  - PDF opens (check with ``pypdf`` or a similar
    validator) and has a non-empty body
  - PDF footer contains the disclaimer string"

This file covers the export layer in three layers:

1. :func:`test_export_json_via_inprocess_function` —
   calls :func:`app.audit.export.export_audit_log_json`
   directly with a fresh async session. Verifies the
   bytes are valid JSON, the schema is stable, and the
   rows match the rows we just wrote. No HTTP. The
   "exercise the function" path.

2. :func:`test_export_pdf_via_inprocess_function` —
   calls :func:`app.audit.export.export_audit_log_pdf`
   directly. Verifies the PDF opens (``pypdf`` parses it
   without raising), has a non-empty body (≥1 page of
   text), and the disclaimer text appears on every page.

3. :func:`test_get_audit_log_json_endpoint`,
   :func:`test_get_audit_log_pdf_endpoint`,
   :func:`test_export_endpoints_return_404_for_unknown_contract` —
   exercise the FastAPI routes via :class:`httpx.AsyncClient`
   + :class:`httpx.ASGITransport` (an in-process ASGI
   client driven from the same event loop as the
   seeded fixture, so the SQLAlchemy engine's connection
   pool doesn't trip the asyncpg "different event loop"
   error that the sync ``TestClient`` hits). The route
   layer is mostly a passthrough, but the 404 path and
   the ``Content-Type`` / ``Content-Disposition`` headers
   live there, so we cover them too.

Why in-process + HTTP both
--------------------------

The unit tests in 1 + 2 are fast and reliable — they
don't depend on the route wiring or the ASGI
transport's loop semantics. The HTTP tests in 3 are the
integration layer: they confirm the endpoints are wired
and the headers are right. The spec's "calls both export
endpoints" wording suggests HTTP, but the export itself
is the unit; the HTTP is the wiring.

How the tests stay isolated
---------------------------

The audit_events table is **append-only** (Build 3
installed the trigger; Build 6 reviews it). Tests cannot
clean up after themselves. We work around this by giving
every test run a unique ``contract_id`` (a uuid4 hex
prefix), so concurrent test runs and re-runs do not
collide. The assertions are scoped to the rows written
under that test's ``contract_id``.

Decision-type coverage
----------------------

The spec asks for "≥1 row per stage (spot / approve /
reject / edit / redline)". The :class:`DecisionType`
enum does not have explicit "spot" / "approve" /
"reject" / "edit" / "redline" values — the spec
language maps onto the enum roughly as:

- "spot" → ``flag_accepted`` / ``flag_rejected`` (the
  spotter's flag is what the user approves/rejects).
- "approve" → ``flag_accepted``.
- "reject" → ``flag_rejected``.
- "edit" → ``severity_edited`` / ``context_added``.
- "redline" → ``redline_generated`` / ``redline_downloaded``.

We write one row per type under the test's
``contract_id`` so the JSON has all of them and the PDF
body has all of them. The mapping is documented here so
a future reader of the test can see why every enum
value is exercised.
"""

from __future__ import annotations

import json
import uuid
from io import BytesIO
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pypdf import PdfReader
from sqlalchemy import select

from app.audit.export import (
    ContractNotFound,
    export_audit_log_json,
    export_audit_log_pdf,
)
from app.audit.log import record_event
from app.audit.schema import AuditEvent, AuditEventRow, DecisionType
from app.db import get_session_factory
from app.main import app


# --- Fixtures ----------------------------------------------------------


# The full set of decision-type values we want to exercise
# in the export. The spec's "≥1 row per stage" maps onto
# these enum values (see the module docstring for the
# mapping). We include the lifecycle events too —
# ``graph_started`` / ``graph_resumed`` are the first /
# last rows in a real export, so the export should
# include them.
_DECISION_TYPE_FIXTURES: tuple[tuple[DecisionType, str, dict], ...] = (
    (DecisionType.GRAPH_STARTED, "", {"clause_count": 4}),
    (DecisionType.FLAG_ACCEPTED, "c1", {"flag_id": "f1", "score": 1}),
    (DecisionType.FLAG_REJECTED, "c2", {"flag_id": "f2", "score": 2}),
    (DecisionType.SEVERITY_EDITED, "c3", {"old_score": 2, "new_score": 1}),
    (DecisionType.CONTEXT_ADDED, "c3", {"rationale": "acceptable for our use case"}),
    (DecisionType.REDLINE_GENERATED, "c1", {"proposed_text": "mock text", "rationale": "mock"}),
    (DecisionType.REDLINE_DOWNLOADED, "c1", {"filename": "redline.docx"}),
    (DecisionType.GRAPH_RESUMED, "", {"thread_id": "t"}),
)


def _unique_contract_id() -> str:
    """A unique contract id per test invocation.

    Append-only table → no cleanup. We give every test
    invocation a unique contract id so concurrent runs
    and re-runs never collide on the JSON / PDF
    assertions.
    """
    return f"test-export-{uuid.uuid4().hex[:12]}"


@pytest_asyncio.fixture()
async def seeded_contract() -> AsyncIterator[str]:
    """Insert one row of every DecisionType, yield the contract id.

    Uses :func:`app.audit.log.record_event` so the writes
    go through the same writer the graph runtime uses
    (single INSERT, no UPDATE/DELETE — the trigger
    rejection is the Build 3 / Review 2 invariant, and
    the export test never tries to mutate).
    """
    contract_id = _unique_contract_id()
    for decision_type, clause_id, payload in _DECISION_TYPE_FIXTURES:
        ev = AuditEvent(
            contract_id=contract_id,
            clause_id=clause_id,
            decision_type=decision_type,
            payload_json=payload,
        )
        await record_event(ev)
    yield contract_id


# --- 1. In-process JSON export -----------------------------------------


async def test_export_json_via_inprocess_function(seeded_contract: str) -> None:
    """The in-process JSON export returns valid JSON with all the rows.

    Asserts the schema (top-level keys), the row count,
    and that every :class:`DecisionType` is represented
    in the events list (the spec's "≥1 row per stage"
    rule, mapped onto the enum).
    """
    factory = get_session_factory()
    async with factory() as session:
        blob = await export_audit_log_json(session, seeded_contract)

    # 1. bytes -> dict
    payload = json.loads(blob)
    assert payload["contract_id"] == seeded_contract
    assert payload["row_count"] == len(_DECISION_TYPE_FIXTURES)
    assert isinstance(payload["exported_at"], str)
    assert "T" in payload["exported_at"]  # ISO-8601 separator
    assert len(payload["events"]) == payload["row_count"]

    # 2. schema stability: every event has the expected keys
    expected_keys = {
        "id",
        "contract_id",
        "clause_id",
        "decision_type",
        "payload_json",
        "decided_by",
        "decided_at",
    }
    for event in payload["events"]:
        assert set(event.keys()) == expected_keys, (
            f"event {event} missing keys: {expected_keys - set(event.keys())}"
        )

    # 3. every decision type we wrote is present
    seen_types = {event["decision_type"] for event in payload["events"]}
    for decision_type, _, _ in _DECISION_TYPE_FIXTURES:
        # ``use_enum_values=True`` in the Pydantic model
        # serialises the enum to its string value.
        assert decision_type.value in seen_types, (
            f"decision type {decision_type.value} missing from export"
        )

    # 4. ordering: events are ascending by decided_at, with id
    # as the tie-breaker
    sorted_events = sorted(
        payload["events"], key=lambda e: (e["decided_at"], e["id"])
    )
    assert [e["id"] for e in payload["events"]] == [
        e["id"] for e in sorted_events
    ]


async def test_export_json_raises_for_unknown_contract() -> None:
    """The in-process JSON export raises ContractNotFound on a missing id.

    The route layer maps this to a 404 (see
    :func:`test_export_endpoints_return_404_for_unknown_contract`).
    """
    factory = get_session_factory()
    async with factory() as session:
        with pytest.raises(ContractNotFound):
            await export_audit_log_json(
                session, f"definitely-does-not-exist-{uuid.uuid4().hex}"
            )


async def test_export_json_includes_schema_version(seeded_contract: str) -> None:
    """The JSON export carries a top-level ``schema_version`` field.

    Fix F2 from the Phase 3 review. Downstream consumers
    (regulated-work pitches, re-importers, validators)
    need a machine-checkable handle to know whether
    their parser matches the producer's format. The
    field is a string of the form ``"<major>"`` — the
    first versioned export is ``"1"``; any future
    breaking change must bump it and document the diff
    in the README's audit-log section.

    Asserts:

    1. ``schema_version`` is present at the top level.
    2. It is a non-empty string.
    3. It is the expected current value (``"1"``), so a
       regression that drops the field back out is
       caught by the test rather than by a downstream
       consumer.

    The test is intentionally separate from
    :func:`test_export_json_via_inprocess_function`
    so that a regression on this single field gives a
    direct pointer to the fix card.
    """
    factory = get_session_factory()
    async with factory() as session:
        blob = await export_audit_log_json(session, seeded_contract)

    payload = json.loads(blob)
    assert "schema_version" in payload, (
        "F2 regression: JSON export is missing the top-level "
        "`schema_version` field. See t_ccdb1b96 for context."
    )
    assert isinstance(payload["schema_version"], str)
    assert payload["schema_version"] != ""
    # Pin the current version. When this changes, update
    # this assertion AND the README audit-log section.
    assert payload["schema_version"] == "1"


# --- 2. In-process PDF export ------------------------------------------


def _pdf_has_disclaimer_on_every_page(pdf_bytes: bytes, *, phrase: str) -> bool:
    """Check the disclaimer phrase appears in pypdf-extracted text on every page.

    The footer is rendered with ``canvas.drawString`` (not
    a Frame/Paragraph), and pypdf reliably extracts
    drawString text from the content stream — that's the
    reason for the drawString choice (the Frame/Paragraph
    alternative had flaky pypdf extraction). The body of
    every page should contain the phrase.

    The phrase is the first 84 chars of the project's
    ``DISCLAIMER.md``: "clausecraft is a research project,
    not a product. It is not legal advice." The full
    text is the spec's verbatim source, but pypdf's
    extraction of the second-line body slice is
    inconsistent across reportlab versions; the
    high-signal phrase is the spec's actual rule.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    for page in reader.pages:
        text = page.extract_text() or ""
        if phrase not in text:
            return False
    return True


async def test_export_pdf_via_inprocess_function(
    seeded_contract: str,
    disclaimer_text: str,
) -> None:
    """The in-process PDF export returns a valid PDF with the disclaimer.

    Asserts:

    1. The PDF opens with ``pypdf`` (a corrupt PDF would
       raise on ``PdfReader``).
    2. The PDF has at least one page and each page has
       a non-empty body.
    3. The "not legal advice" phrase appears on every
       page (the spec's hard rule for the footer).
    4. The body contains the decision types we wrote
       (sanity check that the export is not blank).
    """
    factory = get_session_factory()
    async with factory() as session:
        pdf_bytes = await export_audit_log_pdf(session, seeded_contract)

    # 1. opens
    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    # 2. non-empty body
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        assert text.strip(), f"page {i+1} has empty body"

    # 3. disclaimer on every page
    phrase = "clausecraft is a research project, not a product. It is not legal advice."
    assert _pdf_has_disclaimer_on_every_page(pdf_bytes, phrase=phrase), (
        f"disclaimer phrase not found on every page; "
        f"first-page text: {(reader.pages[0].extract_text() or '')[:300]!r}"
    )

    # 4. the body's first page contains the title and a
    # couple of the decision types we wrote (sanity).
    first_page = reader.pages[0].extract_text() or ""
    assert seeded_contract in first_page, "contract id missing from PDF body"
    assert "graph_started" in first_page, "graph_started row missing from PDF body"
    assert "redline_generated" in first_page, "redline_generated row missing from PDF body"


async def test_export_pdf_raises_for_unknown_contract() -> None:
    """The in-process PDF export raises ContractNotFound on a missing id."""
    factory = get_session_factory()
    async with factory() as session:
        with pytest.raises(ContractNotFound):
            await export_audit_log_pdf(
                session, f"definitely-does-not-exist-{uuid.uuid4().hex}"
            )


# --- 3. HTTP endpoint tests --------------------------------------------


@pytest_asyncio.fixture()
async def async_client() -> AsyncIterator[httpx.AsyncClient]:
    """An in-process ASGI client driven from the same loop as the fixtures.

    Why not the project's sync :func:`TestClient` fixture?

    The sync TestClient drives the ASGI app in a separate
    anyio portal, so the request handler runs in a
    different event loop than the
    :func:`seeded_contract` fixture's loop. The project's
    module-level SQLAlchemy engine is shared across
    loops, and asyncpg refuses to hand a connection from
    one loop's pool to another — the request raises
    ``RuntimeError: got Future ... attached to a
    different loop`` during the response body read.

    :class:`httpx.AsyncClient` + :class:`ASGITransport`
    runs the ASGI app in the *current* loop (the test's
    own loop), so the engine's connection pool stays
    consistent between the seeded fixture's writes and
    the export endpoint's reads. Same test code shape as
    a TestClient (``async_client.get(...)``); different
    transport.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


async def test_get_audit_log_json_endpoint(
    async_client: httpx.AsyncClient, seeded_contract: str
) -> None:
    """The /audit-log.json endpoint returns the JSON export with the right headers.

    Asserts:

    - 200 status
    - ``application/json`` content type
    - ``Content-Disposition: attachment; filename=...``
    - Body parses as JSON and contains the contract id
    """
    response = await async_client.get(
        f"/api/contracts/{seeded_contract}/audit-log.json"
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".json" in cd

    payload = response.json()
    assert payload["contract_id"] == seeded_contract
    assert payload["row_count"] == len(_DECISION_TYPE_FIXTURES)
    assert len(payload["events"]) == len(_DECISION_TYPE_FIXTURES)
    # F2 from the Phase 3 review: the JSON must advertise
    # its schema_version at the top level. Caught at the
    # route layer (not just the in-process function) so a
    # regression in the response wrapper is caught too.
    assert "schema_version" in payload
    assert isinstance(payload["schema_version"], str)
    assert payload["schema_version"] == "1"


async def test_get_audit_log_pdf_endpoint(
    async_client: httpx.AsyncClient, seeded_contract: str
) -> None:
    """The /audit-log.pdf endpoint returns a valid PDF with the right headers.

    Asserts:

    - 200 status
    - ``application/pdf`` content type
    - ``Content-Disposition: attachment; filename=...``
    - Body is a valid PDF (pypdf parses it)
    - Disclaimer appears on every page
    """
    response = await async_client.get(
        f"/api/contracts/{seeded_contract}/audit-log.pdf"
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".pdf" in cd

    # Magic bytes: a valid PDF starts with %PDF-
    assert response.content[:5] == b"%PDF-", (
        f"response is not a valid PDF (magic={response.content[:8]!r})"
    )

    # pypdf round-trip
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) >= 1
    phrase = "clausecraft is a research project, not a product. It is not legal advice."
    assert _pdf_has_disclaimer_on_every_page(response.content, phrase=phrase), (
        "disclaimer missing from at least one page of the HTTP-returned PDF"
    )


async def test_export_endpoints_return_404_for_unknown_contract(
    async_client: httpx.AsyncClient,
) -> None:
    """Both export endpoints return 404 when the contract has no events.

    The spec's hard rule: "Both endpoints require the
    contract to exist (404 otherwise)."
    """
    unknown = f"definitely-does-not-exist-{uuid.uuid4().hex}"
    r_json = await async_client.get(f"/api/contracts/{unknown}/audit-log.json")
    assert r_json.status_code == 404
    assert "audit log" in r_json.json().get("detail", "").lower()

    r_pdf = await async_client.get(f"/api/contracts/{unknown}/audit-log.pdf")
    assert r_pdf.status_code == 404
    assert "audit log" in r_pdf.json().get("detail", "").lower()


# --- 4. Append-only invariant (sanity for this build) ------------------


async def test_seeded_rows_survive_in_db(seeded_contract: str) -> None:
    """Sanity: the seeded rows are present in the DB after the test.

    The trigger forbids UPDATE/DELETE, so the rows the
    test wrote should still be there with the same
    decided_by / decided_at. This is a 1-line sanity
    check that the export was actually reading what we
    wrote (and that no concurrent test has clobbered the
    rows, which it can't, because the trigger forbids
    it).
    """
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(AuditEventRow).where(
            AuditEventRow.contract_id == seeded_contract
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    assert len(rows) == len(_DECISION_TYPE_FIXTURES)
    seen_types = {r.decision_type for r in rows}
    for decision_type, _, _ in _DECISION_TYPE_FIXTURES:
        assert decision_type.value in seen_types
