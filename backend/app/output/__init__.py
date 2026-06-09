"""Output renderers — Phase 3 Build 2.

The :mod:`app.output` package turns the HITL-accepted
:class:`~app.agents.redline_drafter.RedlineProposal` list
into a deliverable the user can hand back to the
counterparty. Two renderers ship:

- :mod:`.markdown_diff` — the v0 escape hatch. A
  unified-diff-style Markdown document with ``+`` / ``-``
  per change. Always available; never breaks; this is the
  fallback per the spec's "markdown-diff is not a stretch
  goal" hard rule.
- :mod:`.docx` — the primary renderer. A
  Word/LibreOffice-readable ``.docx`` with proper
  ``w:ins`` / ``w:del`` tracked-changes elements. Uses
  ``python-docx`` for the body + raw ``lxml`` for the
  tracked-change XML (python-docx has no first-class API
  for revision marks).

API surface (Build 3 wraps both as HTTP responses)
-------------------------------------------------

- :func:`app.output.docx.render_redline_docx` — returns
  ``bytes``, the OOXML blob. Build 3's FastAPI endpoint
  wraps it as a ``Response(media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")``.
- :func:`app.output.markdown_diff.render_markdown_diff` — returns
  ``str``, the Markdown document. Same endpoint shape but
  ``text/markdown``.
- :func:`render_redline` — the single entry point Build 3 /
  Build 6 call. The caller picks the format (``"docx"`` or
  ``"markdown"``) and the function returns ``(bytes,
  filename_hint)``. The docx path's bytes are wrapped as a
  file download with the matching ``.docx`` filename; the
  markdown path is UTF-8 encoded and saved with a ``.md``
  filename.

Why a separate ``output/`` package (not under ``pipeline/``)
-------------------------------------------------------------
The output renderers are pure functions of their inputs —
they have no I/O, no database, no LLM, no observability.
Putting them in ``pipeline/`` would lump them in with the
LangGraph state machine (Build 3) and the audit log
(Build 4), which have very different concerns. A
self-contained package makes the renderers trivially
unit-testable and lets Build 3 import them by name.

The "fallback to markdown-diff" rule
------------------------------------
The docx renderer raises :class:`DocxRenderError` (a typed
exception) on a non-recoverable error. The HITL state
machine (Build 3) catches that exception and falls back to
:meth:`render_markdown_diff` automatically. The "tracked
changes coming" status on the API response is the build's
escape hatch per the spec — the docx path's known rabbit
hole (per spec line 284) does not block the phase.

PDF round-trip is **out of scope** per the spec, line 228.
"""

from __future__ import annotations

from typing import Literal, Sequence, Tuple

from app.agents.redline_drafter.schema import RedlineProposal
from app.output.docx import DocxRenderError, render_redline_docx
from app.output.markdown_diff import render_markdown_diff

#: The accepted-proposals tuple shape used by both
#: renderers. Re-declared here so the entry point's
#: signature is self-contained (callers don't need to
#: import from the leaf modules).
AcceptedProposal = Tuple[str, RedlineProposal]

#: Literal for the ``format`` kwarg of :func:`render_redline`.
RenderFormat = Literal["docx", "markdown"]

#: Filename hints for the download button on the UI. The
#: caller (Build 6) sets the ``Content-Disposition`` header
#: to ``attachment; filename="<this>"`` so the browser saves
#: the file with the right extension. ``.docx`` triggers
#: Word/LibreOffice; ``.md`` opens in any text editor.
FILENAME_DOCX = "contract_redline.docx"
FILENAME_MARKDOWN = "contract_redline.md"


def render_redline(
    contract_baseline: str,
    accepted_proposals: Sequence[AcceptedProposal],
    *,
    format: RenderFormat = "docx",
    author: str = "clausecraft",
) -> Tuple[bytes, str]:
    """Render the redline in the caller\'s chosen format.

    This is the single entry point the HITL state machine
    (Build 3) and the redline output UI (Build 6) call.
    The caller picks ``format="docx"`` for the primary
    tracked-changes Word file or ``format="markdown"`` for
    the v0 fallback. The function returns ``(bytes,
    filename_hint)`` so the API layer can wrap the bytes
    as an HTTP response and set the ``Content-Disposition``
    header from ``filename_hint``.

    Parameters
    ----------
    contract_baseline
        The full contract text. Used by the docx renderer
        to derive the document title and by the markdown
        renderer for the header line. Not diffed against
        — the per-clause diffs are local to each proposal.
    accepted_proposals
        The list of ``(clause_id, RedlineProposal)``
        tuples the HITL state machine accepted. Order is
        preserved in the output.
    format
        ``"docx"`` (default) — return the OOXML blob
        (Word/LibreOffice). ``"markdown"`` — return a
        UTF-8-encoded unified-diff-style Markdown doc.
    author
        The ``w:author`` attribute on every tracked
        change in the docx path. Ignored for the markdown
        path (Markdown has no concept of authorship).
        Defaults to ``"clausecraft"`` (the system
        identity, hardcoded per the card\'s hard rules).

    Returns
    -------
    tuple[bytes, str]
        ``(blob, filename_hint)`` where ``blob`` is the
        file bytes (always ``bytes``, not ``str``) and
        ``filename_hint`` is either
        :data:`FILENAME_DOCX` or :data:`FILENAME_MARKDOWN`
        depending on the format.

    Raises
    ------
    DocxRenderError
        When ``format="docx"`` and the docx renderer
        cannot produce a valid blob (empty baseline,
        empty proposals, blank author). The HITL state
        machine catches this and falls back to
        ``format="markdown"`` automatically — the
        fallback is the spec\'s exit criterion, not an
        error path the user sees.
    ValueError
        When ``format`` is anything other than
        ``"docx"`` or ``"markdown"``.

    Notes
    -----
    The docx path and the markdown path are
    *semantically equivalent* — for a given input, the
    same set of clauses change, the same rationale is
    surfaced, and the same ``(before, after)`` text is
    emitted (the docx path runs the same ``diff_summary``
    parser as the markdown path; the only difference is
    the output container). The cross-check is pinned in
    :mod:`tests.phase3.test_docx_entrypoint`.
    """
    if format == "docx":
        blob = render_redline_docx(
            contract_baseline,
            accepted_proposals,
            author=author,
        )
        return blob, FILENAME_DOCX
    if format == "markdown":
        text = render_markdown_diff(contract_baseline, accepted_proposals)
        return text.encode("utf-8"), FILENAME_MARKDOWN
    raise ValueError(
        f"unknown render format: {format!r} (expected \'docx\' or \'markdown\')"
    )


__all__ = [
    "AcceptedProposal",
    "DocxRenderError",
    "FILENAME_DOCX",
    "FILENAME_MARKDOWN",
    "RenderFormat",
    "render_markdown_diff",
    "render_redline",
    "render_redline_docx",
]
