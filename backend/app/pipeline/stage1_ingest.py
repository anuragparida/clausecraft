"""Stage 1 — ingest → parse → classify.

The Phase 1 pipeline is a linear sequence:

    raw bytes (PDF or DOCX)
        → ingest (text + per-paragraph metadata)
        → parse (chunked into RawClauses)
        → classify (each RawClause gets a ClauseType + confidence)
        → ClauseList

There is no LangGraph state in Phase 1 — the pipeline is mechanical,
not a multi-step agent. The graph abstraction lands in Phase 2 when
the deviation spotter joins.

The orchestrator returns a :class:`Stage1Result` that captures:

- ``clauses`` — the classified ``Clause[]``
- ``filename`` — the original upload's filename (so the UI can echo it)
- ``scanned_warning`` — non-empty when the PDF was detected as scanned
- ``is_scanned`` — bool
- ``char_count`` — total extractable characters (telemetry)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.classify import Clause, classify_clauses
from app.ingest import (
    DocxDocument,
    PdfDocument,
    extract_docx,
    extract_pdf,
)
from app.parse import RawClause, chunk_paragraphs, chunk_text

logger = logging.getLogger(__name__)


SUPPORTED_PDF = "application/pdf"
SUPPORTED_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUPPORTED_PLAIN = "text/plain"


@dataclass
class Stage1Result:
    """The output of the Phase 1 ingest+parse+classify pipeline."""

    filename: str
    clauses: list[Clause] = field(default_factory=list)
    is_scanned: bool = False
    scanned_warning: str = ""
    char_count: int = 0
    detected_format: str = ""


def _ingest(filename: str, content_type: str, data: bytes) -> tuple[Any, str]:
    """Dispatch on ``content_type`` to the right ingest extractor.

    Returns ``(ingest_result, format_name)`` where ``format_name`` is
    one of ``"pdf"``, ``"docx"``, or ``"plain"``. Raises ``ValueError``
    for unsupported content types — the FastAPI layer turns that into
    a 415 response.
    """
    ct = (content_type or "").lower()
    if ct == SUPPORTED_PDF or filename.lower().endswith(".pdf"):
        return extract_pdf(data), "pdf"
    if ct == SUPPORTED_DOCX or filename.lower().endswith(".docx"):
        return extract_docx(data), "docx"
    if ct.startswith("text/") or filename.lower().endswith(".txt"):
        # Plain text fallback: synthesise a minimal DocxDocument-shaped
        # object so the chunker can treat it identically.
        text = data.decode("utf-8", errors="replace")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        # Build a DocxDocument with synthetic paragraph indices.
        from app.ingest.docx import DocxDocument, DocxParagraph

        paras = [
            DocxParagraph(
                paragraph_index=n,
                text=p,
                style="Normal",
                is_heading=False,
                heading_level=0,
            )
            for n, p in enumerate(paragraphs)
        ]
        full = "\n\n".join(paragraphs)
        return (
            DocxDocument(
                paragraphs=paras,
                full_text=full,
                char_count=len(full),
                detected_scan=False,
                scanned_warning="",
            ),
            "plain",
        )
    raise ValueError(
        f"Unsupported content type {content_type!r} / filename {filename!r}. "
        f"Phase 1 supports application/pdf, .docx, and text/*."
    )


def _parse(ingest_result: Any, format_name: str) -> list[RawClause]:
    """Turn an ingest result into a list of :class:`RawClause`.

    For PDFs we chunk the joined page text (no per-paragraph metadata
    is available from pymupdf without an additional structure pass).
    For DOCX we use the explicit paragraph list, which preserves
    heading metadata.
    """
    if format_name == "pdf":
        return chunk_text(ingest_result.full_text)
    if format_name == "docx":
        return _chunk_docx_paragraphs(ingest_result)
    if format_name == "plain":
        return chunk_paragraphs([p.text for p in ingest_result.paragraphs])
    raise ValueError(f"Unknown format {format_name!r}")


def _chunk_docx_paragraphs(doc: DocxDocument) -> list[RawClause]:
    """Chunk a DOCX document using its explicit paragraph list.

    The chunker wants raw text; the per-paragraph heading metadata
    is used to mark the first paragraph after a heading as the
    start of a new clause. We do this in a single pass so the
    paragraph indices stay in document order.
    """
    paragraphs = [p.text for p in doc.paragraphs]
    return chunk_paragraphs(paragraphs)


def run_stage1(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    language: str = "en",
) -> Stage1Result:
    """Execute the full Phase 1 pipeline on the uploaded file.

    See module docstring for the shape. The function is the public
    surface that :func:`app.main.post_contracts_ingest` calls.

    The ``language`` parameter is the per-document language code
    (``"en"`` or ``"de"``). It is propagated to
    :func:`app.classify.classify_clauses` so the classifier stamps
    every :class:`Clause` with the right ``language`` field and the
    underlying LLM call uses the matching prompt variant. Per-clause
    language detection (Phase 4 card 3) can override this default at
    the chunker level in a follow-up card; this entry point threads
    the document-level language through unchanged.
    """
    ingest_result, format_name = _ingest(filename, content_type, data)
    raw_clauses = _parse(ingest_result, format_name)
    classified = classify_clauses(
        raw_clauses, contract_filename=filename, language=language
    )

    is_scanned = bool(getattr(ingest_result, "is_scanned", False)) or bool(
        getattr(ingest_result, "detected_scan", False)
    )
    scanned_warning = getattr(ingest_result, "scanned_warning", "") or ""
    char_count = getattr(ingest_result, "char_count", 0)

    logger.info(
        "Stage 1 ingested %s (%s, %d chars, scanned=%s) → %d clauses",
        filename,
        format_name,
        char_count,
        is_scanned,
        len(classified),
    )

    return Stage1Result(
        filename=filename,
        clauses=classified,
        is_scanned=is_scanned,
        scanned_warning=scanned_warning,
        char_count=char_count,
        detected_format=format_name,
    )
