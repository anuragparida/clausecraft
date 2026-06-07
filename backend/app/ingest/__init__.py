"""Ingest layer — public surface.

Re-exports the per-format extractors and the dataclass result types so
callers can do ``from app.ingest import extract_pdf, PdfDocument``.
"""

from app.ingest.docx import (
    DocxDocument,
    DocxParagraph,
    extract_docx,
)
from app.ingest.pdf import PdfDocument, PdfPage, extract_pdf
from app.ingest.scan_detect import SCAN_CHAR_THRESHOLD, is_scanned_pdf

__all__ = [
    "DocxDocument",
    "DocxParagraph",
    "PdfDocument",
    "PdfPage",
    "SCAN_CHAR_THRESHOLD",
    "extract_docx",
    "extract_pdf",
    "is_scanned_pdf",
]
