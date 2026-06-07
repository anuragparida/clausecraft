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
from app.config import settings
from app.db import db_ping
from app.graph.graph import run_echo
from app.observability import init_langfuse
from app.pipeline import Stage1Result, run_stage1

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
        "Multi-agent contract triage pipeline. Phase 1: ingest → "
        "parse → classify an uploaded NDA. Returns a typed clause list "
        "in a stable JSON schema."
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
        "phase": "1 — ingest + parse + classify (NDA EN)",
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
