"""PDF ingest — Phase 1.

Uses pymupdf (the modern PyMuPDF binding) to extract text from native
PDFs that have a text layer. Scanned PDFs (no text layer) are detected
via ``scan_detect.is_scanned_pdf``; we log a warning and return the
empty / near-empty text. OCR is explicitly out of scope for Phase 1.

The function returns a :class:`PdfDocument` — a thin dataclass that
captures both the extracted text and the per-page offset (so downstream
chunker can recover positions). The pymupdf version is intentionally
pinned in pyproject.toml; older pymupdf had a different ``get_text``
signature.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pymupdf  # type: ignore[import-not-found]

from app.ingest.scan_detect import SCAN_CHAR_THRESHOLD, is_scanned_pdf

logger = logging.getLogger(__name__)


@dataclass
class PdfPage:
    """A single page's worth of extracted text + 1-based page number."""

    page_number: int
    text: str


@dataclass
class PdfDocument:
    """The result of opening + extracting from a PDF.

    Attributes
    ----------
    pages
        Per-page text, in document order. ``pages[i].page_number`` is
        1-based (matches the PDF reader convention).
    full_text
        Concatenation of every page's text, separated by ``\\n\\n``.
    is_scanned
        True when the total extractable text is below the scan
        threshold. The caller should warn the user but is allowed
        to continue — Phase 1 returns whatever partial text we have.
    scanned_warning
        Human-readable warning when ``is_scanned`` is True. Empty
        otherwise. The orchestrator surfaces this to the API client
        so the UI can render a "scanned PDF" banner.
    char_count
        Total number of extractable characters. Useful for telemetry
        and for the test assertions.
    """

    pages: list[PdfPage] = field(default_factory=list)
    full_text: str = ""
    is_scanned: bool = False
    scanned_warning: str = ""
    char_count: int = 0


def extract_pdf(data: bytes) -> PdfDocument:
    """Open ``data`` (a PDF byte string) and return its extracted text.

    The function is synchronous because pymupdf is a C extension and
    releases the GIL — running it inline in a thread pool is
    sufficient for the contract-size documents we deal with (typically
    < 1 MB, < 100 pages).
    """
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — pymupdf raises bare Exception
        # A malformed PDF is a Phase-1 unrecoverable error: the contract
        # can't be ingested. The orchestrator turns this into a 400.
        raise ValueError(f"PDF could not be opened: {exc}") from exc

    pages: list[PdfPage] = []
    try:
        for idx in range(len(doc)):
            page = doc.load_page(idx)
            text = page.get_text("text") or ""
            pages.append(PdfPage(page_number=idx + 1, text=text))
    finally:
        doc.close()

    full_text = "\n\n".join(p.text for p in pages)
    char_count = len(full_text)
    scanned = is_scanned_pdf(full_text)

    if scanned:
        warning = (
            f"PDF appears to be scanned (only {char_count} extractable chars; "
            f"threshold is {SCAN_CHAR_THRESHOLD}). OCR is not implemented in "
            f"Phase 1 — the contract will be returned with minimal or empty "
            f"clause text."
        )
        logger.warning(warning)
    else:
        warning = ""

    return PdfDocument(
        pages=pages,
        full_text=full_text,
        is_scanned=scanned,
        scanned_warning=warning,
        char_count=char_count,
    )
