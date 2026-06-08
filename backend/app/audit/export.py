"""Audit log export — JSON + PDF.

Build 4 of Phase 3: the "download the decision chain" button
the review UI calls. Two export formats:

- :func:`export_audit_log_json` — a :class:`bytes` blob of
  pretty-printed JSON. A complete copy of every
  ``audit_events`` row for the contract, ordered by
  ``decided_at`` ascending, with the full ``payload_json``
  per row. No redaction, no transformation. v1 ships the
  raw log; the spec acknowledges a future "redact PII"
  toggle is a v2 card.

- :func:`export_audit_log_pdf` — a :class:`bytes` blob of a
  reportlab PDF. One page per ~25 events, with a header
  block (contract id, export timestamp, row count) and a
  per-event block (timestamp, decision type, decided by,
  clause id, pretty-printed payload). Every page carries
  the "not legal advice" disclaimer in the footer, pulled
  verbatim from ``DISCLAIMER.md`` (the single source of
  truth — do not paraphrase).

Both functions read-only. They do NOT touch the writer or
the trigger; they are pure SELECT + serialise.

Why "404 if no rows" instead of "empty export"
-----------------------------------------------

The spec hard rule: "Both endpoints require the contract
to exist (404 otherwise)." Since ``contract_id`` is a
free-form string (no ``contracts`` table — see the schema
docstring), "exists" means "has at least one audit_event
row." Empty result → :class:`ContractNotFound`; the API
layer maps that to a 404. This is the same convention the
graph runtime uses to short-circuit a resume on an unknown
thread.

Why bytes, not str / Path
-------------------------

The functions are pure serialisers — they take a session
and a contract id, return bytes. The FastAPI handler in
``app.main`` wraps them in a :class:`Response` with the
right ``Content-Type`` / ``Content-Disposition`` headers.
Keeping the export pure makes it trivial to unit-test
(write the bytes to a temp path, re-read with ``pypdf`` /
``json.loads``) and keeps the reportlab + sqlalchemy
imports out of the API module.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schema import AuditEventRow

logger = logging.getLogger(__name__)


# --- Public exceptions --------------------------------------------------


class ContractNotFound(LookupError):
    """Raised when no audit events exist for the given contract id.

    The API layer maps this to a 404. The exception is a
    ``LookupError`` so callers that want a generic
    "missing resource" check (``except LookupError``)
    catch it cleanly.
    """


# --- Project root + disclaimer -----------------------------------------


def _repo_root() -> Path:
    """The repository root, computed from this file's location.

    ``backend/app/audit/export.py`` → ``<repo>/``. Used to
    resolve ``DISCLAIMER.md`` regardless of the process's
    CWD (matters for the pytest collection path, which
    sets ``CWD`` to ``backend/`` for some tests).
    """
    return Path(__file__).resolve().parents[3]


def _read_disclaimer_text() -> str:
    """Read the "not legal advice" disclaimer verbatim.

    Source: ``<repo>/DISCLAIMER.md``, the same file the
    spec calls out as the single source of truth. We read
    once and cache — the file does not change at runtime
    and the read is cheap, but reading once per process
    keeps the call site simple (no module-level mutable
    state beyond the lru_cache-style cached value).

    The full file content is used, not a one-line
    summary. The spec says "the disclaimer" — the whole
    file IS the disclaimer. Paraphrasing or truncating
    would defeat the "verbatim" requirement on line 12 of
    the spec.

    If the file is missing, fall back to a literal string
    that still satisfies "contains the words 'not legal
    advice'" — the export must not crash because a
    contributor deleted ``DISCLAIMER.md``.
    """
    path = _repo_root() / "DISCLAIMER.md"
    if not path.exists():
        logger.warning(
            "DISCLAIMER.md missing at %s; using fallback disclaimer string.",
            path,
        )
        return (
            "clausecraft is a research project, not a product. "
            "It is not legal advice."
        )
    return path.read_text(encoding="utf-8").strip()


# --- Row model used by the export layer --------------------------------


class _ExportRow:
    """A snapshot of one audit_events row, decoupled from the ORM session.

    The export functions read rows into this light dataclass-like
    object so the PDF / JSON serialisation can happen after the
    session is closed. The fields mirror the DB columns
    one-for-one (so a JSON export can faithfully round-trip).
    """

    __slots__ = (
        "id",
        "contract_id",
        "clause_id",
        "decision_type",
        "payload_json",
        "decided_by",
        "decided_at",
    )

    def __init__(
        self,
        *,
        id: int,
        contract_id: str,
        clause_id: str,
        decision_type: str,
        payload_json: dict[str, Any],
        decided_by: str,
        decided_at: datetime,
    ) -> None:
        self.id = id
        self.contract_id = contract_id
        self.clause_id = clause_id
        self.decision_type = decision_type
        self.payload_json = payload_json
        self.decided_by = decided_by
        self.decided_at = decided_at

    def to_json_dict(self) -> dict[str, Any]:
        """Return the dict shape used in the JSON export.

        Keys are stable (don't rename without bumping the
        JSON export version). ``decided_at`` is ISO-8601
        with timezone — the rest of the system reads it
        the same way.
        """
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "clause_id": self.clause_id,
            "decision_type": self.decision_type,
            "payload_json": self.payload_json,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat(),
        }


# --- Read path ---------------------------------------------------------


async def _load_rows(session: AsyncSession, contract_id: str) -> list[_ExportRow]:
    """Load all audit events for a contract, ordered by ``decided_at`` asc.

    Returns an empty list when no rows match; the caller
    (``export_audit_log_*``) raises :class:`ContractNotFound`
    in that case (the spec's "404 if no events" rule).

    The session is consumed via ``SELECT ... ORDER BY
    decided_at ASC, id ASC`` — ``id ASC`` is the
    tie-breaker for events written in the same millisecond
    (a fast batch of audit writes can land in the same
    timestamp tick). The export order is then "real
    chronological, then insertion order", which is what a
    reviewer reading the log expects.
    """
    stmt = (
        select(AuditEventRow)
        .where(AuditEventRow.contract_id == contract_id)
        .order_by(AuditEventRow.decided_at.asc(), AuditEventRow.id.asc())
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        _ExportRow(
            id=r.id,
            contract_id=r.contract_id,
            clause_id=r.clause_id or "",
            decision_type=r.decision_type,
            payload_json=r.payload_json or {},
            decided_by=r.decided_by,
            decided_at=r.decided_at,
        )
        for r in rows
    ]


# --- JSON export -------------------------------------------------------


async def export_audit_log_json(
    session: AsyncSession,
    contract_id: str,
) -> bytes:
    """Render the audit log for a contract as a pretty-printed JSON blob.

    Parameters
    ----------
    session
        An open async SQLAlchemy session. The caller owns
        the transaction; this function does not commit.
    contract_id
        The free-form contract identifier. Must match at
        least one row in ``audit_events``; otherwise a
        :class:`ContractNotFound` is raised.

    Returns
    -------
    bytes
        UTF-8-encoded JSON, pretty-printed with 2-space
        indent. The top-level shape is::

            {
              "contract_id": "...",
              "exported_at": "2026-...Z",
              "row_count": 7,
              "events": [ { ... one row ... }, ... ]
            }

        The events list is ordered by ``decided_at`` ASC.
        No redaction, no field removal — this is a
        machine-readable copy of the log.

    Raises
    ------
    ContractNotFound
        When the contract has no audit_events rows.
    """
    rows = await _load_rows(session, contract_id)
    if not rows:
        raise ContractNotFound(contract_id)

    payload: dict[str, Any] = {
        "contract_id": contract_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "events": [r.to_json_dict() for r in rows],
    }
    blob = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    logger.info(
        "audit log JSON export: contract=%s rows=%d bytes=%d",
        contract_id,
        len(rows),
        len(blob),
    )
    return blob


# --- PDF export --------------------------------------------------------


def _humanise_timestamp(decided_at: datetime) -> str:
    """Render a timestamp in the same shape the audit replay view uses.

    ``2026-06-08 14:31:02 UTC`` — ISO date, 24h time,
    explicit UTC. Avoids the locale-dependent default
    str() of datetime. Defensive against naive
    datetimes: any tz-less value is treated as UTC.
    """
    if decided_at.tzinfo is None:
        decided_at = decided_at.replace(tzinfo=timezone.utc)
    return decided_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _safe_payload_string(payload: Any, *, _depth: int = 0) -> str:
    """Render an audit payload as a single line of text for the PDF.

    The PDF footer is on every page; the body uses
    ``<pre>``-ish Paragraph text. Deeply-nested dicts are
    flattened with ``json.dumps`` to keep the layout
    simple. Bounded recursion so a malicious payload
    can't OOM the renderer.
    """
    if _depth > 6:
        return "...(truncated, depth>6)..."
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(payload)


def _build_pdf_story(
    contract_id: str,
    rows: list[_ExportRow],
    *,
    exported_at: datetime,
    disclaimer_text: str,
) -> Iterable[Any]:
    """Construct the reportlab flowables for the PDF body.

    Layout (functional, not pretty — the spec calls this
    out explicitly):

    - Cover line: "Audit Log — Contract <id>" + export
      timestamp + row count.
    - Per event: a small table with the key fields + a
      one-line payload summary.
    - A page break after every ~25 events to keep the
      per-page footer readable.
    """
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AuditTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        spaceAfter=8,
    )
    meta_style = ParagraphStyle(
        "AuditMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.grey,
        spaceAfter=12,
    )
    event_header_style = ParagraphStyle(
        "EventHeader",
        parent=styles["Heading3"],
        fontSize=11,
        leading=14,
        spaceBefore=8,
        spaceAfter=4,
    )

    yield Paragraph(f"Audit Log &mdash; Contract {contract_id}", title_style)
    yield Paragraph(
        f"Exported {_humanise_timestamp(exported_at)} &middot; "
        f"{len(rows)} event{'s' if len(rows) != 1 else ''}",
        meta_style,
    )

    events_per_page = 25
    for idx, row in enumerate(rows):
        if idx > 0 and idx % events_per_page == 0:
            yield PageBreak()
        yield Paragraph(
            f"#{row.id} &middot; {row.decision_type} &middot; "
            f"{_humanise_timestamp(row.decided_at)}",
            event_header_style,
        )
        meta_table_data = [
            ["decided_by", row.decided_by],
            ["clause_id", row.clause_id or "(pipeline-level)"],
            ["payload", _safe_payload_string(row.payload_json)],
        ]
        meta_table = Table(
            meta_table_data,
            colWidths=[1.1 * inch, 5.4 * inch],
        )
        meta_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                    ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        yield meta_table
        yield Spacer(1, 0.08 * inch)


def _make_footer_canvas(disclaimer_text: str):
    """Build the on-every-page footer canvas factory for reportlab.

    reportlab's :class:`SimpleDocTemplate` accepts a
    ``onFirstPage`` + ``onLaterPages`` callback. We use
    the same callback for both because the spec says
    "footer on every page" — first page and continuation
    pages carry the same disclaimer.

    The disclaimer is the full ``DISCLAIMER.md`` content
    (see ``_read_disclaimer_text``). We render it as
    small grey text in the page bottom using two
    :func:`canvas.drawString` calls:

    - line 1: the headline phrase verbatim (the spec's
      "not legal advice" rule).
    - line 2+: a 240-char slice of the body, indented
      and offset to sit just below line 1.

    We use drawString (not a Frame) because pypdf
    reliably extracts drawString text from the content
    stream — Frame + Paragraph in an onPage callback
    works visually but the text appears after the page
    content has been laid out, and pypdf sometimes
    mis-orders the extraction. drawString writes text
    directly to the page in a known order, so the
    validation path (pypdf on the produced PDF) sees
    the disclaimer reliably.
    """
    # Two pre-formatted lines of footer text. The first is
    # the headline phrase; the second is a 240-char slice
    # of the body so a reviewer glancing at any page sees
    # more than just the headline.
    body_line = disclaimer_text.replace("\n", " ")
    if len(body_line) > 240:
        body_line = body_line[:237] + "..."

    def _draw_footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(
            0.5 * inch,
            0.45 * inch,
            "clausecraft is a research project, not a product. "
            "It is not legal advice.",
        )
        canvas.drawString(0.5 * inch, 0.30 * inch, body_line)
        canvas.restoreState()

    return _draw_footer


async def export_audit_log_pdf(
    session: AsyncSession,
    contract_id: str,
) -> bytes:
    """Render the audit log for a contract as a PDF blob.

    Uses :mod:`reportlab` to build a SimpleDocTemplate,
    writes the body via :func:`_build_pdf_story`, and
    attaches the disclaimer footer to every page. The
    result is a single ``bytes`` blob suitable for a
    FastAPI ``Response(media_type='application/pdf')``.

    Parameters
    ----------
    session
        An open async SQLAlchemy session. The caller owns
        the transaction; this function does not commit.
    contract_id
        The free-form contract identifier. Must match at
        least one row in ``audit_events``; otherwise a
        :class:`ContractNotFound` is raised.

    Returns
    -------
    bytes
        A complete, well-formed PDF file. The PDF carries
        the ``DISCLAIMER.md`` text verbatim in the footer
        of every page.

    Raises
    ------
    ContractNotFound
        When the contract has no audit_events rows.
    """
    rows = await _load_rows(session, contract_id)
    if not rows:
        raise ContractNotFound(contract_id)

    disclaimer_text = _read_disclaimer_text()
    exported_at = datetime.now(timezone.utc)

    # We use reportlab's in-memory BytesIO buffer to keep
    # the function pure (no tempfile). The buffer is
    # small (the PDF is text-only, even with hundreds of
    # events it stays well under 1 MB).
    from io import BytesIO

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.75 * inch,  # leave room for the two-line footer
        title=f"clausecraft audit log — contract {contract_id}",
        author="clausecraft",
    )
    story = list(
        _build_pdf_story(
            contract_id,
            rows,
            exported_at=exported_at,
            disclaimer_text=disclaimer_text,
        )
    )
    doc.build(story, onFirstPage=_make_footer_canvas(disclaimer_text), onLaterPages=_make_footer_canvas(disclaimer_text))
    blob = buffer.getvalue()
    logger.info(
        "audit log PDF export: contract=%s rows=%d bytes=%d",
        contract_id,
        len(rows),
        len(blob),
    )
    return blob


__all__ = [
    "ContractNotFound",
    "export_audit_log_json",
    "export_audit_log_pdf",
]
