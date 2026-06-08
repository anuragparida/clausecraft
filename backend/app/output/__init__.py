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
- :func:`app.output.markdown_diff.render_markdown_diff` —
  returns ``str``, the Markdown document. Same endpoint
  shape but ``text/markdown``.

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

from app.output.docx import DocxRenderError, render_redline_docx
from app.output.markdown_diff import render_markdown_diff

__all__ = [
    "DocxRenderError",
    "render_markdown_diff",
    "render_redline_docx",
]
