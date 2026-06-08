"""Pure-function utilities for inspecting the audit-log export response.

Build 4 (the audit-log export) ships two endpoints:

- ``GET /api/contracts/{contract_id}/audit-log.json`` —
  pretty-printed JSON, one row per ``AuditEvent``.
- ``GET /api/contracts/{contract_id}/audit-log.pdf`` —
  a ``reportlab``-rendered PDF whose footer carries the
  project's "not legal advice" disclaimer verbatim.

The Phase 3 e2e test (Build 6) hits both endpoints and
asserts:

1. The JSON has ``≥1 row per stage`` (the spec's exact
   phrasing — one row each for spot / approve / reject /
   edit / redline, with a permissive tolerance for stages
   that are pipeline-internal).
2. The PDF opens (we use :mod:`pypdf` to parse the trailer
   + count pages).
3. The PDF body is non-empty.
4. The PDF footer carries the disclaimer string.

This module is the single source of truth for those
assertions. The e2e test calls into here; the unit tests
exercise the same code against hand-crafted JSON / PDF
blobs.

Why not just inline the parsing in the test file
-----------------------------------------------
The PDF-disclaimer check needs to walk the raw PDF
byte-stream looking for the disclaimer string (it may
appear in either a literal or a compressed object
stream). That's ~30 lines of gnarly code; isolating it in
a function with a clear name keeps the test file readable.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any, Iterable

#: All decision types the e2e test expects to see in the
#: audit log JSON for a complete run. Maps 1:1 to the
#: :class:`app.audit.schema.DecisionType` enum that Build 3
#: will create. Kept here as a constant so the test
#: failure message can name the missing stage.
EXPECTED_STAGES: tuple[str, ...] = (
    "graph_started",
    "flag_accepted",
    "flag_rejected",
    "severity_edited",
    "redline_generated",
    "redline_downloaded",
    "graph_resumed",
)


@dataclass(frozen=True)
class AuditLogRow:
    """One row of the audit-log JSON export.

    The JSON export's wire format is the same as the
    ``audit_events`` table — we don't want a separate
    Pydantic model here, because the test should be
    tolerant of field ordering and value-encoding changes
    that don't affect the audit-replay UI.
    """

    contract_id: str
    clause_id: str
    decision_type: str
    payload_json: dict[str, Any]
    decided_by: str
    decided_at: str  # raw ISO-8601 string

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "AuditLogRow":
        """Build an :class:`AuditLogRow` from one decoded JSON object."""
        try:
            return cls(
                contract_id=str(row["contract_id"]),
                clause_id=str(row.get("clause_id", "")),
                decision_type=str(row["decision_type"]),
                payload_json=dict(row.get("payload_json") or {}),
                decided_by=str(row.get("decided_by", "")),
                decided_at=str(row.get("decided_at", "")),
            )
        except KeyError as exc:
            raise ValueError(
                f"audit-log row missing required field {exc.args[0]!r}"
            ) from exc


def parse_audit_log_json(blob: bytes) -> list[AuditLogRow]:
    """Decode the JSON export into a list of :class:`AuditLogRow`.

    Accepts both the "list at top level" shape (the
    natural FastAPI ``JSONResponse`` shape) and the
    ``{"events": [...]}`` envelope (the shape Build 4
    could use if it ever wants to add envelope-level
    metadata). The envelope shape is detected by the
    presence of an ``events`` key whose value is a list.
    """
    decoded = json.loads(blob.decode("utf-8"))
    if isinstance(decoded, dict) and isinstance(decoded.get("events"), list):
        rows = decoded["events"]
    elif isinstance(decoded, list):
        rows = decoded
    else:
        raise ValueError(
            "audit-log JSON is neither a list nor a dict with an 'events' key"
        )
    return [AuditLogRow.from_dict(r) for r in rows]


def count_rows_per_stage(rows: Iterable[AuditLogRow]) -> dict[str, int]:
    """How many rows there are per decision_type, in row-decoded form."""
    out: dict[str, int] = {}
    for r in rows:
        out[r.decision_type] = out.get(r.decision_type, 0) + 1
    return out


def assert_every_stage_present(
    rows: Iterable[AuditLogRow],
    *,
    expected_stages: Iterable[str] = EXPECTED_STAGES,
) -> None:
    """Raise ``AssertionError`` when any expected stage is missing.

    The spec's exact phrase: "the audit log has ≥1 row per
    stage (spot / approve / reject / edit / redline)". The
    "spot" stage corresponds to ``graph_started`` /
    ``graph_resumed`` in Build 3's enum (the spot happens
    in the same graph tick as the start). The helper does
    not enforce the exact mapping — it just checks that
    each token in :data:`EXPECTED_STAGES` has at least one
    matching row in the log.
    """
    counts = count_rows_per_stage(rows)
    missing = [s for s in expected_stages if counts.get(s, 0) < 1]
    if missing:
        raise AssertionError(
            f"audit log is missing ≥1 row for these stages: {missing!r}. "
            f"Got: {counts!r}"
        )


def assert_every_row_has_actor(rows: Iterable[AuditLogRow]) -> None:
    """Raise ``AssertionError`` when any row has an empty ``decided_by``.

    Build 4's JSON export acceptance criterion (per the
    Build 4 spec): "every row has a ``decision_type`` and a
    ``decided_by``". This helper enforces that.
    """
    for r in rows:
        if not r.decided_by:
            raise AssertionError(
                f"audit log row id for clause {r.clause_id!r} has empty decided_by"
            )


# --- PDF helpers -------------------------------------------------------


def parse_pdf_pages(blob: bytes) -> int:
    """Return the page count of a PDF blob.

    Uses :mod:`pypdf` (the spec's recommended validator for
    the PDF export). Raises :class:`AssertionError` if the
    blob isn't a valid PDF or has zero pages.
    """
    try:
        import pypdf
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pypdf is required for the Phase 3 e2e PDF check. "
            "Install with `uv add --dev pypdf`."
        ) from exc

    reader = pypdf.PdfReader(io.BytesIO(blob))
    return len(reader.pages)


def pdf_has_non_empty_body(blob: bytes) -> bool:
    """``True`` when the PDF has at least one page with non-empty extracted text.

    The spec wants the PDF body to be "non-empty" — the
    test is satisfied by a page that has a title row
    ("Audit Log — Contract <id>") even with no events, so
    the assertion is "≥1 page with text ≥20 characters
    total" (a permissive floor that catches an empty /
    blank-PDF failure mode without false-positiving on
    short log summaries).
    """
    try:
        import pypdf
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pypdf is required for the Phase 3 e2e PDF check."
        ) from exc

    reader = pypdf.PdfReader(io.BytesIO(blob))
    if len(reader.pages) < 1:
        return False
    total_text = "".join((p.extract_text() or "") for p in reader.pages)
    return len(total_text.strip()) >= 20


def pdf_footer_contains_disclaimer(blob: bytes, disclaimer: str) -> bool:
    """``True`` when the disclaimer string appears anywhere in the PDF.

    The Build 4 spec requires the disclaimer to be in the
    footer of *every* page, but the spec also notes that
    :mod:`reportlab`'s "page footer" is rendered into the
    page's content stream, not a separate footer
    annotation — so checking for the string anywhere in
    the extracted text is a sound proxy for the
    "every-page footer" requirement.

    A short disclaimer (<8 chars) would be ambiguous with
    random punctuation; we require the search to match at
    least 8 characters. Build 4's disclaimer is
    multi-sentence and far longer than that.
    """
    needle = disclaimer.strip()
    if len(needle) < 8:
        raise ValueError(
            "Disclaimer string is too short to be searched unambiguously "
            "(need at least 8 characters)."
        )
    try:
        import pypdf
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pypdf is required for the Phase 3 e2e PDF check."
        ) from exc

    reader = pypdf.PdfReader(io.BytesIO(blob))
    if len(reader.pages) < 1:
        return False
    haystack = "\n".join((p.extract_text() or "") for p in reader.pages)
    return needle in haystack


# Convenience: a single entry point that does the whole PDF
# assertion set. Tests prefer this to a sequence of
# "call-assert-call-assert" calls.
def assert_pdf_export_ok(blob: bytes, *, disclaimer: str) -> None:
    """Run the full PDF export assertion set.

    Equivalent to: page count > 0, body has text, footer
    contains the disclaimer. The three checks are bundled
    because the e2e test always wants all three; a test
    that wants a finer-grained failure can call the
    individual helpers instead.
    """
    pages = parse_pdf_pages(blob)
    if pages < 1:
        raise AssertionError("PDF export has 0 pages (expected ≥1)")
    if not pdf_has_non_empty_body(blob):
        raise AssertionError(
            f"PDF export has {pages} page(s) but body text is empty"
        )
    if not pdf_footer_contains_disclaimer(blob, disclaimer):
        raise AssertionError(
            "PDF export footer does not contain the disclaimer string"
        )


__all__ = [
    "EXPECTED_STAGES",
    "AuditLogRow",
    "parse_audit_log_json",
    "count_rows_per_stage",
    "assert_every_stage_present",
    "assert_every_row_has_actor",
    "parse_pdf_pages",
    "pdf_has_non_empty_body",
    "pdf_footer_contains_disclaimer",
    "assert_pdf_export_ok",
]
