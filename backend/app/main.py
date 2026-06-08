"""FastAPI entrypoint for clausecraft backend.

Phase 0 endpoints:

- ``GET  /healthz``           — liveness + DB connectivity check
- ``GET  /``                  — service banner
- ``POST /contracts``         — stub, returns 501 Not Implemented
- ``POST /graph/echo``        — exercise the LangGraph echo graph

The 501 on /contracts is intentional: the real ingest pipeline lands
in Phase 1, and we want a clear contract for clients (404 vs 501)
rather than a silent 200.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.audit.export import (
    ContractNotFound,
    export_audit_log_json,
    export_audit_log_pdf,
)
from app.classify import ClauseList
from app.classify.schema import Clause
from app.config import settings
from app.db import db_ping, get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.graph import run_echo
from app.observability import init_langfuse
from app.pipeline import Stage1Result, Stage3Result, run_stage1, run_stage3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Langfuse at import time so the rest of the app can use it
# synchronously. Falls back to no-op when keys are placeholders.
init_langfuse(
    host=settings.langfuse_host,
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
)

app = FastAPI(
    title="clausecraft backend",
    version="0.1.0-dev",
    description=(
        "Multi-agent contract triage pipeline. Phase 1+2: ingest → "
        "parse → classify an uploaded NDA, look up matching playbook "
        "baselines via bge-m3 cosine similarity over pgvector, and "
        "spot deviations per clause using a prompted Sonnet agent. "
        "Phase 2 adds the playbook store, the top-k retrieval helper, "
        "and the deviation spotter (the first real agent)."
    ),
)


class EchoRequest(BaseModel):
    """Body for the Phase 0 echo endpoint."""

    text: str = Field(..., min_length=1, max_length=10_000)


class EchoResponse(BaseModel):
    """Echo response — the LangGraph graph's verbatim output."""

    echoed: str


@app.get("/")
async def root() -> dict[str, str]:
    """Lightweight banner endpoint — useful for sanity-checking the API."""
    return {
        "service": "clausecraft-backend",
        "version": "0.1.0-dev",
        "phase": "2 — playbook store + bge-m3 retrieval + deviation spotter (NDA EN)",
    }


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness + DB connectivity probe.

    Returns 200 when the DB is reachable. Returns 503 when it isn't
    (e.g. Postgres is still starting, or the network between
    containers hasn't come up yet). Container healthchecks hit this
    URL.
    """
    db_ok = await db_ping()
    body: dict[str, Any] = {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
    }
    code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=body)


@app.post(
    "/contracts",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def post_contract(payload: dict[str, Any]) -> dict[str, str]:
    """Stub for the contract-ingest pipeline.

    Returns 501 to make the "not implemented yet" status explicit to
    clients. Will be replaced in Phase 1 with the real ingest →
    parse → classify stage that returns a clause list.
    """
    # We accept the payload (and deliberately ignore it) so clients
    # that send a JSON body don't get a 422 from FastAPI's body
    # parsing. The 501 carries the real signal.
    _ = payload
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "POST /contracts is a Phase 0 stub. The real ingest → "
            "parse → classify pipeline lands in Phase 1."
        ),
    )


@app.post("/graph/echo", response_model=EchoResponse)
async def graph_echo(req: EchoRequest) -> EchoResponse:
    """Drive the Phase 0 LangGraph echo graph end-to-end.

    Replaces the v0 contract endpoint's emptiness with a real signal:
    "yes, the LangGraph runtime is loaded, compiled, and invokable."
    """
    echoed = run_echo(req.text)
    return EchoResponse(echoed=echoed)


# --- Phase 1: real ingest endpoint --------------------------------------


class IngestResponse(BaseModel):
    """Response body for ``POST /contracts/ingest``.

    The JSON schema is stable across Phase 1 — the frontend renders
    the ``clauses`` list in a DataTable, the ``scanned_warning`` as a
    banner, and the ``summary`` fields as headline chips.
    """

    filename: str
    format: str
    clause_count: int
    classified_count: int
    classified_ratio: float
    char_count: int
    is_scanned: bool
    scanned_warning: str
    clauses: list[dict[str, Any]]


def _build_ingest_response(result: Stage1Result) -> IngestResponse:
    """Convert a :class:`Stage1Result` into the API response model."""
    clauses_dump = ClauseList(clauses=result.clauses).model_dump_jsonable()["clauses"]
    classified = sum(1 for c in result.clauses if c.type.value != "unknown")
    total = len(result.clauses)
    ratio = (classified / total) if total else 0.0
    return IngestResponse(
        filename=result.filename,
        format=result.detected_format,
        clause_count=total,
        classified_count=classified,
        classified_ratio=ratio,
        char_count=result.char_count,
        is_scanned=result.is_scanned,
        scanned_warning=result.scanned_warning,
        clauses=clauses_dump,
    )


@app.post(
    "/contracts/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
)
async def post_contracts_ingest(
    file: UploadFile = File(..., description="PDF or DOCX NDA contract"),
    language: str = Form(
        default="en",
        description='Contract language. Phase 1 supports "en" only.',
    ),
) -> IngestResponse:
    """Phase 1 — ingest + parse + classify an uploaded NDA.

    Accepts a multipart upload (``file=@contract.pdf``) and an optional
    ``language`` form field. The pipeline returns the typed clause list
    in a stable JSON schema; the frontend renders it in the Triage page.

    Failure modes:

    - Unsupported content type → 415.
    - File could not be parsed → 400 with the parser error.
    - Pydantic validation error in the classifier → already swallowed
      by the classifier (it falls back to ``type=unknown``); the
      endpoint still returns 200 with the partially-classified list.
    """
    if language not in ("en", "de"):
        # Phase 1 = en only. We accept "de" as a form value so the
        # field is forward-compatible, but the classifier still treats
        # it as English for now.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported language {language!r}. Phase 1 supports 'en' "
                f"only. The 'de' value is accepted as a forward-compatible "
                f"placeholder but is classified as English."
            ),
        )

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file upload.",
        )

    try:
        result = run_stage1(
            filename=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
    except ValueError as exc:
        # Unsupported format / parse failure — return 400.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Phase 3 Build 6: stash the ingest result in the
    # in-memory state store so the downstream
    # ``/contracts/{id}/decisions`` endpoint can find it
    # without re-ingesting. The ``contract_id`` is the
    # filename (the e2e test's contract_id == filename
    # convention). Production swaps the dict for a
    # Postgres-backed store.
    try:
        from app.pipeline.phase3_pipeline import get_state

        state = get_state(file.filename or "upload.bin")
        state.filename = result.filename
        state.content_type = file.content_type or "application/octet-stream"
        state.file_bytes = data
        state.clauses = ClauseList(
            clauses=result.clauses
        ).model_dump(mode="jsonable")["clauses"]
    except Exception as exc:  # noqa: BLE001
        # State-store failure is non-fatal for the
        # ingest itself — the response is still
        # accurate. The /decisions endpoint will surface
        # a clear error if state is missing.
        logger.warning(
            "ingest: failed to stash clauses in state store: %s", exc
        )

    return _build_ingest_response(result)


# --- Phase 2: deviation spotter endpoint --------------------------------


class SpotRequest(BaseModel):
    """Body for ``POST /contracts/spot``.

    The spotter takes *already-classified* clauses (the output of
    stage 1, or a re-classify from the UI). The body is the same
    shape as the ``clauses`` field of :class:`IngestResponse` —
    the frontend can round-trip the ingest response straight into
    a spot request.

    Attributes
    ----------
    filename
        The contract filename. Echoed on the response and used as
        a Langfuse tag so per-contract traces are easy to filter.
    clauses
        The classified clauses. Each clause has ``id``, ``text``,
        ``type`` (a :class:`~app.classify.ClauseType` value),
        ``language``, ``confidence``, and a ``position`` block.
    """

    filename: str = Field(..., min_length=1, max_length=512)
    clauses: list[dict[str, Any]] = Field(..., min_length=1)


class SpotFlag(BaseModel):
    """Response-side view of a :class:`DeviationFlag`.

    The pipeline returns the raw flag dataclass; the API response
    is a Pydantic model so the JSON schema is stable. Fields:

    - ``clause_id`` — the input clause's id
    - ``score`` — 0..3
    - ``rationale`` — the spotter's reasoning
    - ``citation`` — the citation object (or null)
    - ``unverified`` — true when the parser couldn't verify the
      citation or the LLM declined
    - ``baseline_type`` — the baseline's clause type
    """

    clause_id: str
    score: int
    rationale: str
    citation: dict[str, Any] | None = None
    unverified: bool
    baseline_type: str = ""


class SpotResponse(BaseModel):
    """Response body for ``POST /contracts/spot``."""

    filename: str
    flag_count: int
    flagged_count: int
    unverified_count: int
    no_baseline_count: int
    matrix_version: str
    embedding_provider: str
    flags: list[SpotFlag]


def _parse_clauses_from_spot_request(
    payload_clauses: list[dict[str, Any]],
) -> list[Clause]:
    """Convert the API payload's clause dicts into :class:`Clause` objects.

    The frontend sends a JSON-friendly shape (enums as strings,
    nested position as a dict). We rebuild the typed Pydantic
    model here so the pipeline gets the same input shape that
    :func:`app.pipeline.stage1_ingest.run_stage1` would have
    produced. A malformed clause (missing fields, bad enum
    value) is rejected with a 400 — the spotter is not a
    repair-shop for bad upstream data.
    """
    rebuilt: list[Clause] = []
    for c in payload_clauses:
        try:
            rebuilt.append(Clause.model_validate(c))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid clause payload at index {len(rebuilt)}: {exc}"
                ),
            ) from exc
    return rebuilt


def _build_spot_response(result: Stage3Result) -> SpotResponse:
    """Convert a :class:`Stage3Result` into the API response model."""
    flags: list[SpotFlag] = []
    for f in result.flags:
        citation: dict[str, Any] | None = None
        if f.citation is not None:
            citation = {
                "playbook_clause_id": f.citation.playbook_clause_id,
                "contract_text_excerpt": f.citation.contract_text_excerpt,
            }
        flags.append(
            SpotFlag(
                clause_id=f.clause_id,
                score=f.score,
                rationale=f.rationale,
                citation=citation,
                unverified=f.unverified,
                baseline_type=f.baseline_type,
            )
        )
    return SpotResponse(
        filename=result.contract_filename,
        flag_count=len(result.flags),
        flagged_count=result.flagged_count,
        unverified_count=result.unverified_count,
        no_baseline_count=result.no_baseline_count,
        matrix_version=result.matrix_version,
        embedding_provider=result.embedding_provider,
        flags=flags,
    )


@app.post(
    "/contracts/spot",
    response_model=SpotResponse,
    status_code=status.HTTP_200_OK,
)
async def post_contracts_spot(payload: SpotRequest) -> SpotResponse:
    """Phase 2 — spot deviations on a list of classified clauses.

    Takes the output of ``POST /contracts/ingest`` (or any other
    source of classified clauses) and runs the deviation spotter
    per clause. The response is a flag list with the citation
    pointer the UI needs to render the deviation table.

    The endpoint is independent of the upload pipeline: the
    frontend can re-spot after a re-classify without re-uploading
    the file. The Phase 3 / Phase 4 eval harness drives the same
    orchestrator (``app.pipeline.stage3_spot.run_stage3``)
    directly with its own clause list.

    Failure modes:

    - Empty clauses list → 400.
    - Malformed clause payload (missing fields, bad enum) → 400
      with the validator's error message.
    - Per-clause spot failures (LLM unreachable, parse error) →
      a flag with ``unverified=True`` and a rationale that names
      the failure. The endpoint still returns 200 — the pipeline
      contract is "a flag for every clause, no matter what".
    - No matching playbook clauses for any clause → every flag
      has ``rationale="no matching playbook clause"`` and
      ``unverified=True``. The endpoint still returns 200.
    """
    if not payload.clauses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SpotRequest.clauses must contain at least one clause.",
        )
    clauses = _parse_clauses_from_spot_request(payload.clauses)
    try:
        result = await run_stage3(
            clauses=clauses,
            contract_filename=payload.filename,
        )
    except Exception as exc:  # noqa: BLE001
        # The orchestrator is supposed to swallow per-clause
        # failures; a top-level exception is a real bug. Return
        # 500 so the operator sees it on the Langfuse error
        # dashboard.
        logger.exception("run_stage3 failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Spot stage failed: {exc}",
        ) from exc

    # Phase 3 Build 6: stash the spot flags in the
    # in-memory state store so the downstream
    # ``/contracts/{id}/decisions`` endpoint can find them
    # when the user clicks "Generate redline". The state
    # was created by the prior ``/contracts/ingest`` call —
    # we look it up by the same ``filename`` key.
    try:
        from app.pipeline.phase3_pipeline import get_state

        state = get_state(payload.filename)
        # ``result.flags`` is a list of ``DeviationFlag``
        # Pydantic models; the pipeline module only consumes
        # the dict shape (``clause_id``, ``score``, etc.).
        # ``model_dump`` is the cleanest serialiser — it
        # handles the nested ``Citation`` (also a Pydantic
        # model) recursively.
        state.flags = [
            f.model_dump() if hasattr(f, "model_dump") else dict(f)
            for f in (result.flags or [])
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "spot: failed to stash flags in state store: %s", exc
        )

    return _build_spot_response(result)


# --- Phase 3 Build 4: audit log export ---------------------------------


def _safe_filename_segment(contract_id: str) -> str:
    """Sanitise ``contract_id`` for use in a Content-Disposition filename.

    The contract_id is operator-supplied free-form text, so
    we strip path-traversal characters and whitespace
    before embedding it in the ``filename=`` field of the
    response. The result is a single filename stem with
    ``-`` replacing any non-alphanumeric / non-underscore
    character.
    """
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "-" for c in contract_id)


@app.get(
    "/api/contracts/{contract_id}/audit-log.json",
    response_class=Response,
)
async def get_audit_log_json(
    contract_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Phase 3 Build 4 — download the audit log as JSON.

    Returns the full chain of decisions for a single
    contract as a pretty-printed JSON blob. The schema
    is stable:

    ::

        {
          "schema_version": "1",
          "contract_id": "...",
          "exported_at": "<ISO-8601 UTC>",
          "row_count": N,
          "events": [ {id, contract_id, clause_id, decision_type,
                       payload_json, decided_by, decided_at}, ... ]
        }

    Status codes:

    - ``200`` — at least one audit event exists for the
      contract; the body is the JSON.
    - ``404`` — no audit events for the contract (the
      spec's "contract must exist" rule, mapped from
      :class:`ContractNotFound`).
    """
    try:
        blob = await export_audit_log_json(session, contract_id)
    except ContractNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No audit log found for contract_id={contract_id!r}. "
                f"The export endpoint requires the contract to have at "
                f"least one audit event."
            ),
        )
    safe = _safe_filename_segment(contract_id) or "contract"
    return Response(
        content=blob,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit-log-{safe}.json"'
            ),
        },
    )


@app.get(
    "/api/contracts/{contract_id}/audit-log.pdf",
    response_class=Response,
)
async def get_audit_log_pdf(
    contract_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Phase 3 Build 4 — download the audit log as PDF.

    Returns a reportlab-rendered PDF with one block per
    audit event (timestamp, decision type, decided by,
    clause id, payload). The ``DISCLAIMER.md`` text is
    rendered verbatim in the footer of every page (the
    spec's hard rule).

    Status codes:

    - ``200`` — at least one audit event exists for the
      contract; the body is the PDF.
    - ``404`` — no audit events for the contract.
    """
    try:
        blob = await export_audit_log_pdf(session, contract_id)
    except ContractNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No audit log found for contract_id={contract_id!r}. "
                f"The export endpoint requires the contract to have at "
                f"least one audit event."
            ),
        )
    safe = _safe_filename_segment(contract_id) or "contract"
    return Response(
        content=blob,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit-log-{safe}.pdf"'
            ),
        },
    )


# --- Phase 3 Build 6: decisions + redline download ---------------------
#
# These two routes are the spine of the e2e test. Both are
# thin HTTP shells over the ``app.pipeline.phase3_pipeline``
# module's in-memory state store, which was populated by
# the prior ``/contracts/ingest`` and ``/contracts/spot``
# calls (the same filename key).
#
# State is process-local — the spec's exit gate runs in CI,
# not across a container restart. A production deployment
# would swap the dict for a Postgres-backed store.


class DecisionItem(BaseModel):
    """One per-flag decision in the e2e request body.

    Mirrors the shape the e2e test sends — the spec
    hardcodes the test's ``decision`` strings
    (``"approve"`` / ``"reject"`` / ``"edit_severity"``) and
    the pipeline module's :func:`normalise_decision` does
    the mapping to the canonical ``accepted`` / ``rejected``
    / ``edited`` action names.
    """

    clause_id: str = Field(..., min_length=1, max_length=128)
    decision: str = Field(..., min_length=1, max_length=32)
    new_severity: int | None = None
    old_severity: int | None = None
    extra_context: str | None = None


class DecisionsRequest(BaseModel):
    """Body for ``POST /contracts/{contract_id}/decisions``.

    Wraps a list of :class:`DecisionItem`. The e2e test
    pins a deterministic set of decisions per fixture
    contract, so the request body is fully specifiable.
    """

    decisions: list[DecisionItem] = Field(..., min_length=1)


class DecisionsResponse(BaseModel):
    """Response body for ``/contracts/{id}/decisions``.

    Mirrors the pipeline's :func:`process_decisions` return
    shape — the operator / e2e test cares about the
    counts, not the inner state.
    """

    contract_id: str
    decisions_count: int
    redlines_count: int
    docx_bytes: int


@app.post(
    "/contracts/{contract_id}/decisions",
    response_model=DecisionsResponse,
    status_code=status.HTTP_200_OK,
)
async def post_contracts_decisions(
    contract_id: str,
    payload: DecisionsRequest,
) -> DecisionsResponse:
    """Phase 3 Build 6 — submit per-flag decisions and render the redline.

    The endpoint is the HITL ``resume`` point in the
    Build 3 spec: the user has reviewed the spot flags,
    approved some and rejected others, and now wants
    the redline drafter to run + the .docx to be
    rendered. The pipeline module runs:

    1. Decision normalisation (``approve`` / ``reject``
       / ``edit_severity`` → canonical actions).
    2. Per-decision audit events.
    3. Drafter + self-check for each accepted flag.
    4. ``.docx`` render (Build 2's
       :func:`app.output.docx.render_redline_docx`).
    5. ``graph_resumed`` lifecycle event.

    Failure modes:

    - No state for ``contract_id`` → 404 (the user
      hasn't run ``/contracts/ingest`` first, or the
      server restarted — the in-memory state is
      process-local).
    - Decision validation error → 422 (Pydantic does
      this for us on the body itself; a semantic
      ``ValueError`` from
      :func:`app.pipeline.phase3_pipeline.process_decisions`
      is converted to 400).
    """
    # Imported lazily so the e2e test's gating fixture
    # can introspect the app's routes without paying for
    # the import until a request actually arrives.
    from app.pipeline.phase3_pipeline import process_decisions

    decisions_payload = [d.model_dump(exclude_none=True) for d in payload.decisions]
    try:
        result = await process_decisions(
            contract_id=contract_id,
            decisions=decisions_payload,
            decided_by="api-user",
        )
    except KeyError as exc:
        # The pipeline raises KeyError-shaped errors when
        # the state was never populated. Convert to 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No in-memory state for contract_id={contract_id!r}. "
                f"Call POST /contracts/ingest first. ({exc})"
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        # Unexpected — log and 500. The audit log already
        # has the ``graph_started`` event, so the operator
        # can correlate.
        logger.exception(
            "decisions endpoint failed for contract_id=%s: %s",
            contract_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Decisions processing failed: {exc}",
        ) from exc

    return DecisionsResponse(
        contract_id=result["contract_id"],
        decisions_count=result["decisions_count"],
        redlines_count=result["redlines_count"],
        docx_bytes=result["docx_bytes"],
    )


# --- Phase 3 Build 7: state snapshot (resume-after-pause UI hydration) --


class ContractStateResponse(BaseModel):
    """Response body for ``GET /contracts/{contract_id}/state``.

    The connected review page fetches this on mount when the
    user navigates to ``#/contracts/{id}/review`` after a page
    refresh. The page uses the clauses + flags to re-hydrate
    DeviationReview, the prior decisions to restore the user's
    per-flag choices, and the booleans to render a friendly
    "contract not found" state when the URL points at a
    contract that was never ingested.

    All fields are always present (``[]`` / ``False`` when
    missing) so the React side can render the page without
    optional-chaining everywhere.
    """

    contract_id: str
    filename: str
    has_state: bool
    has_ingest: bool
    has_spot: bool
    has_decisions: bool
    has_redline: bool
    clauses: list[dict[str, Any]]
    flags: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    redlines: list[dict[str, Any]]


@app.get(
    "/contracts/{contract_id}/state",
    response_model=ContractStateResponse,
    status_code=status.HTTP_200_OK,
)
async def get_contracts_state(contract_id: str) -> ContractStateResponse:
    """Phase 3 Build 7 — snapshot of a contract's resume state.

    Closes the F3 gap from the Phase 3 review: a user who
    navigates to ``#/contracts/{id}/review`` after a page
    refresh (or after copying the URL from a teammate) used
    to land on a blank page because :class:`ReviewContractPage`
    received no ``clauses`` prop from the hash router. The
    pipeline's state machine round-trips fine (see
    :mod:`tests.pipeline.test_hitl_state_machine`), but the
    React layer could not see it. This endpoint is the seam
    the React page fetches on mount.

    Behaviour
    ---------
    - Returns 200 with a fully-populated payload when the
      contract has state in the in-memory store. The
      ``has_ingest`` / ``has_spot`` / ``has_decisions`` /
      ``has_redline`` booleans let the UI render the right
      skeleton / error message for partial progress.
    - Returns 200 with ``has_state=False`` and empty lists
      when no state exists. The UI renders a friendly
      "this contract was not found" state instead of a
      hard 404 — a 404 would force the user back to
      triage on a refresh, which is exactly the broken
      behaviour F3 is meant to fix.
    """
    from app.pipeline.phase3_pipeline import snapshot_state

    snap = snapshot_state(contract_id)
    return ContractStateResponse(**snap)


@app.get(
    "/contracts/{contract_id}/redline.docx",
    response_class=Response,
)
async def get_contracts_redline_docx(contract_id: str) -> Response:
    """Phase 3 Build 6 — download the rendered redline ``.docx``.

    Returns the blob the pipeline module rendered in
    :func:`process_decisions`. The bytes were written
    into the in-memory state store under
    ``contract_id`` by the prior ``/contracts/{id}/decisions``
    call.

    Status codes:

    - ``200`` — at least one accepted flag produced a
      redline; the body is a valid Word ``.docx`` with
      ``w:ins`` / ``w:del`` tracked changes attributed
      to ``"clausecraft"``.
    - ``404`` — no state for ``contract_id`` (the user
      didn't call ``/contracts/{id}/decisions`` first,
      or the server restarted), or all flags were
      rejected and the docx renderer had nothing to do.
    """
    from app.pipeline.phase3_pipeline import get_state

    state = get_state(contract_id)
    blob = state.output_docx_bytes
    if not blob:
        # Either no state was ever populated, or every
        # flag was rejected and the renderer produced an
        # empty blob. Distinguish in the error message.
        from app.pipeline.phase3_pipeline import has_state

        if not has_state(contract_id) or not state.decisions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No redline has been generated for "
                    f"contract_id={contract_id!r}. The flow is: "
                    f"POST /contracts/ingest → POST /contracts/spot → "
                    f"POST /contracts/{contract_id}/decisions → "
                    f"GET /contracts/{contract_id}/redline.docx."
                ),
            )
        # Decisions exist but the docx was empty — likely
        # the drafter was unavailable for every accepted
        # flag. The audit log has the per-redline rows;
        # the .docx path is genuinely empty.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No redline bytes were rendered for "
                f"contract_id={contract_id!r}. Every accepted "
                f"flag's drafter was unavailable (check the "
                f"audit log for per-redline outcome details)."
            ),
        )
    safe = _safe_filename_segment(contract_id) or "contract"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="redline-{safe}.docx"'
            ),
        },
    )


@app.get(
    "/contracts/{contract_id}/redline.md",
    response_class=Response,
)
async def get_contracts_redline_md(contract_id: str) -> Response:
    """Phase 3 Build 5 — download the redline as a markdown diff.

    The markdown path is the v0 escape hatch for the .docx
    path: same contract baseline + accepted proposals, but
    rendered as a unified diff against a single text
    document. The "tracked changes" caveat in the spec
    (line 287: "Mammoth.js… will not render tracked
    changes — it sees the 'final' document") is exactly
    the problem the .md path exists to side-step. A user
    who cannot open the .docx in Word can still see the
    redline in a plain-text viewer.

    Returns:
    - 200 — the body is a UTF-8 markdown document with a
      unified diff for every accepted flag.
    - 404 — no state for ``contract_id``, or the markdown
      render was empty (e.g. every accepted flag's
      drafter was unavailable).
    """
    from app.pipeline.phase3_pipeline import get_state, has_state

    state = get_state(contract_id)
    md = state.output_markdown_bytes
    if not md:
        if not has_state(contract_id) or not state.decisions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No redline has been generated for "
                    f"contract_id={contract_id!r}. The flow is: "
                    f"POST /contracts/ingest → POST /contracts/spot → "
                    f"POST /contracts/{contract_id}/decisions → "
                    f"GET /contracts/{contract_id}/redline.md."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No markdown redline bytes were rendered for "
                f"contract_id={contract_id!r}. Every accepted "
                f"flag's drafter was unavailable (check the "
                f"audit log for per-redline outcome details)."
            ),
        )
    safe = _safe_filename_segment(contract_id) or "contract"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="redline-{safe}.md"'
            ),
        },
    )
