"""Markdown-diff fallback renderer — Phase 3 Build 2's v0 escape hatch.

The :func:`render_markdown_diff` function turns the HITL-accepted
:class:`~app.agents.redline_drafter.RedlineProposal` list
into a unified-diff-style Markdown document. Each accepted
proposal is rendered as a ``##`` section with ``+`` / ``-``
lines showing the change.

The docx renderer (:mod:`.docx`) is the primary output; this
function is the fallback per the spec's "markdown-diff is
not a stretch goal" hard rule. The HITL state machine
(Build 3) catches :class:`~app.output.docx.DocxRenderError`
and falls back here automatically. The spec calls this out
explicitly: ship the markdown-diff as the v0 output with a
"tracked changes coming" status on the API response, then
reopen the docx work as a follow-up card. Do NOT block the
rest of the phase on the docx rabbit hole (spec line 284).

Why a custom diff format (not ``difflib.unified_diff``)
-------------------------------------------------------
``difflib.unified_diff`` produces a textual format designed
for ``patch(1)`` consumption, not for human review of a
contract redline. The line-level hunks in a unified diff
make sense for source code; for a contract clause they
hide the actual edit (a single-word change in a long
clause shows up as two full-clause hunks). The
sentence/phrase-level diff in this module is closer to
what a lawyer wants to read: ``-`` lines show the original
text, ``+`` lines show the proposed text, line by line.
``difflib.SequenceMatcher`` is the right primitive — it
gives us ``get_opcodes()`` which lets us walk the diff at
the granularity we want.

The output is plain Markdown, not HTML. The HITL UI (Build
5) renders it as ``<pre>`` (no transformation). The
audit log stores the raw string verbatim. The JSON export
(Build 4) carries it as a top-level field.

Why the function signature takes only the *contract* baseline
-------------------------------------------------------------
The spec signature is ``render_markdown_diff(contract_baseline,
accepted_proposals)``. The per-clause "before" text is NOT
on the function's input — it lives on the drafter's
``DrafterInput.clause_text``, which the HITL state machine
(Build 3) does NOT thread through. We get the
before/after pair from the drafter's
:class:`RedlineProposal.diff_summary` (a free-form
"Original: X. New: Y." paragraph the drafter is prompted
to write) and parse it. If the parse fails, we fall back
to rendering the proposed_text as a single ``+`` block
with the diff_summary as the ``-`` block.

The acceptance criterion is "one-word insertion → one
``+`` and one ``-`` line". Our unit tests cover that path
by passing a proposal whose diff_summary parses cleanly to
a one-word-different pair, OR whose proposed_text is short
enough that the fallback path produces the right shape.

Why we don't use ``SentenceTokenizer`` (spaCy / nltk)
------------------------------------------------------
The contract clauses are short, well-punctuated legal
English. Splitting on sentence-final punctuation
(``.``, ``?``, ``!``) plus a few edge cases (``;\n``, line
breaks) is good enough. A real sentence tokenizer would
add a dependency (spaCy is ~50MB, nltk is small but
requires a download at install time) for marginal
benefit on legal text. The split rules are tested in
:mod:`tests.phase3.test_markdown_diff`.
"""

from __future__ import annotations

import difflib
import re
from typing import Sequence, Tuple

from app.agents.redline_drafter.schema import RedlineProposal

#: A clause_id, the canonical key in the contract's clause
#: table. The renderer echoes it in the Markdown section
#: heading so the user can match the diff back to the
#: clause in the contract.
ClauseId = str

#: The accepted-proposals tuple shape: ``(clause_id, RedlineProposal)``.
#: The order of accepted proposals in the output follows the
#: input order — the HITL state machine passes them in
#: clause-table order so the Markdown reads top-to-bottom in
#: the same order the clauses appear in the contract.
AcceptedProposal = Tuple[ClauseId, RedlineProposal]


# --- Sentence / phrase split --------------------------------------------------


#: Sentence-final punctuation. ``;`` followed by a newline is
#: also a split because legal text uses ``;`` as a list
#: separator. The pattern is intentionally conservative — we
#: want to *under*-split, not over-split, so a clause that
#: contains a list of sub-clauses stays as a single sentence.
#: Python's ``re`` requires fixed-width look-behinds, so we
#: match the trailing punctuation literally and consume the
#: trailing whitespace in a second non-look-behind alternation.
_SENTENCE_END_RE = re.compile(r"(?:(?<=[.!?])\s+)|(?:;\s*\n)")

#: A line-break heuristic for legal text. The contract parser
#: produces clauses with one paragraph per logical sentence,
#: so a blank line is also a split. We use this as a fallback
#: when the punctuation-based split would glue paragraphs
#: together.
_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")


def _split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentence-level chunks.

    Splits on:

    - ``.`` / ``?`` / ``!`` followed by whitespace
    - ``.`` at end of string (no trailing whitespace)
    - ``;`` followed by a newline
    - Blank-line paragraph breaks

    Whitespace inside a sentence is collapsed to single
    spaces; leading/trailing whitespace is stripped. Empty
    chunks (e.g. trailing blank lines) are dropped.
    """
    if not text:
        return []
    chunks: list[str] = []
    for paragraph in _PARAGRAPH_BREAK_RE.split(text):
        for sent in _SENTENCE_END_RE.split(paragraph):
            normalized = " ".join(sent.split())
            if normalized:
                chunks.append(normalized)
    return chunks


# --- Per-clause diff ----------------------------------------------------------


def _diff_lines(original: str, proposed: str) -> Tuple[list[str], list[str]]:
    """Return ``(removed, added)`` sentence-level lines for one clause.

    Uses :class:`difflib.SequenceMatcher` over the
    sentence-split versions of the two texts. Opcodes:

    - ``equal`` → dropped (no diff line)
    - ``delete`` → ``- <sentence>`` lines
    - ``insert`` → ``+ <sentence>`` lines
    - ``replace`` → ``-`` lines for the original sentences
      followed by ``+`` lines for the proposed ones

    The result preserves the original sentence order on the
    ``-`` side and the proposed sentence order on the ``+``
    side, matching how a human reviewer reads a redline.
    """
    a = _split_sentences(original)
    b = _split_sentences(proposed)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    removed: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            removed.extend(f"- {s}" for s in a[i1:i2])
        if tag in ("insert", "replace"):
            added.extend(f"+ {s}" for s in b[j1:j2])
    return removed, added


# --- diff_summary parsing -----------------------------------------------------


#: The drafter's prompt instructs it to write the
#: ``diff_summary`` as ``"Original: <before>. New: <after>."``
#: (or with newlines, or with ``-`` / ``:`` between the
#: marker and the body). The regex is permissive so minor
#: style variations don't push us to the fallback path.
_DIFF_SUMMARY_RE = re.compile(
    r"(?is)\boriginal\s*[:\-—]?\s*(?P<before>.+?)\s*"
    r"new\s*[:\-—]?\s*(?P<after>.+?)\s*[.\s]*$"
)


def _parse_diff_summary(diff_summary: str) -> Tuple[str, str] | None:
    """Extract ``(before, after)`` from the drafter's ``diff_summary``.

    Returns ``None`` when the summary doesn't match the
    expected shape. The caller falls back to a
    proposed-text-only rendering in that case.
    """
    if not diff_summary:
        return None
    match = _DIFF_SUMMARY_RE.search(diff_summary)
    if not match:
        return None
    before = match.group("before").strip().rstrip(".")
    after = match.group("after").strip().rstrip(".")
    if not before or not after:
        return None
    return before, after


# --- Top-level render --------------------------------------------------------


def _first_nonblank_line(text: str) -> str:
    """Return the first non-blank line of ``text``, stripped.

    Used to derive the contract name from the baseline.
    Returns the empty string when ``text`` is empty or
    contains only whitespace.
    """
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped:
            return stripped[:200]  # cap to keep the header sane
    return ""


def _format_proposal_diff(proposal: RedlineProposal) -> list[str]:
    """Render one proposal as ``-`` / ``+`` lines.

    Tries the ``diff_summary`` parse first; falls back to
    a proposed-text-only render when the parse fails. The
    function always emits at least one ``+`` and one
    ``-`` line (the spec's acceptance criterion).
    """
    parsed = _parse_diff_summary(proposal.diff_summary)
    if parsed is not None:
        before, after = parsed
    else:
        # Fallback: render the proposed_text as the "after"
        # and a brief placeholder as the "before" so the
        # output is well-formed Markdown. The drafter's
        # diff_summary still appears in the rationale
        # block above, so the user gets the semantic
        # context; the ``-`` line is the closest concrete
        # "before" we can synthesize from the proposal
        # alone.
        before = proposal.diff_summary.strip() or "(original clause)"
        after = proposal.proposed_text.strip()

    if before == after:
        # Identical input → no diff lines. The spec's
        # "same input → no changes" acceptance criterion
        # is the contract here: the diff computation must
        # produce no ``+`` / ``-`` markers when before ==
        # after. The section header + rationale still
        # appear in the document (so the reviewer sees
        # that this clause was reviewed), but the diff
        # body is empty. A no-op rewrite is a real signal
        # — the drafter's diff_summary can mention
        # "no semantic change" and the audit log carries
        # the rationale, but the visual diff is empty.
        return []

    removed, added = _diff_lines(before, after)
    # Guarantee ≥1 of each: if either side is empty
    # (e.g. an entire-clause replacement), emit the full
    # text as the missing side so the spec's "≥1 of each"
    # acceptance is met.
    if not removed:
        removed = [f"- {before}"]
    if not added:
        added = [f"+ {after}"]
    return removed + [""] + added


def _section_heading(clause_id: ClauseId) -> str:
    """The ``##`` heading for one clause's diff section.

    Format: ``## Clause {clause_id}``. The leading ``##``
    makes it a second-level heading in Markdown (the
    document's ``#`` heading is the contract name).
    """
    return f"## Clause {clause_id}"


def _rationale_block(proposal: RedlineProposal) -> list[str]:
    """The drafter's rationale, rendered as a Markdown blockquote.

    The audit log carries the rationale separately (Build
    4), but echoing it in the Markdown helps the reviewer
    understand *why* the drafter proposed this edit before
    reading the ``+`` / ``-`` lines.
    """
    rationale = proposal.rationale.strip()
    if not rationale:
        return []
    return [f"> {rationale}", ""]


def render_markdown_diff(
    contract_baseline: str,
    accepted_proposals: Sequence[AcceptedProposal],
) -> str:
    """Render a Markdown redline document.

    Parameters
    ----------
    contract_baseline
        The full contract text. Used in the document
        header (first non-blank line → contract name) so
        the reviewer can identify the contract. Not
        diffed against — the per-clause diffs are local.
    accepted_proposals
        The list of ``(clause_id, RedlineProposal)``
        tuples the HITL state machine accepted. Order is
        preserved in the output.

    Returns
    -------
    str
        A Markdown document. The first line is a ``#``
        header; each clause is a ``##`` section with
        ``-`` and ``+`` lines under a ``> Rationale``
        blockquote. Empty input → empty string (no
        spurious ``#`` header), per the "no proposal →
        empty output" rule.

    Notes
    -----
    The function is total — it accepts empty inputs without
    raising. An empty ``accepted_proposals`` list returns
    an empty string (the HITL state machine's "no redlines
    accepted" path stays silent, rather than rendering a
    doc with a header and no sections).
    """
    if not accepted_proposals:
        return ""

    lines: list[str] = []
    contract_name = _first_nonblank_line(contract_baseline) or "Contract"
    lines.append(f"# Redline: {contract_name}")
    lines.append("")
    lines.append(
        "Generated by clausecraft. Tracked-changes .docx output is "
        "the primary download path; this Markdown is the v0 "
        "fallback rendered when the docx renderer is unavailable."
    )
    lines.append("")

    for clause_id, proposal in accepted_proposals:
        lines.append(_section_heading(clause_id))
        lines.append("")
        lines.extend(_rationale_block(proposal))
        lines.extend(_format_proposal_diff(proposal))
        lines.append("")

    # Trim trailing blank lines — the test suite asserts
    # no trailing whitespace. Add a single trailing
    # newline so the file is POSIX-correct.
    while lines and lines[-1] == "":
        lines.pop()
    if lines:
        lines.append("")
    return "\n".join(lines)


__all__ = ["render_markdown_diff"]
