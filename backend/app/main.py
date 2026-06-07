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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.classify import ClauseList
from app.classify.schema import Clause
from app.config import settings
from app.db import db_ping
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
    return _build_spot_response(result)
