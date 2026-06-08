"""Unit tests for :mod:`app.output.markdown_diff` — the v0 escape-hatch renderer.

The spec's acceptance criteria for the markdown fallback:

- The function is implemented and returns a string with
  at least one ``+`` and one ``-`` line for a one-word
  insertion.
- The unit test for the diff computation: same input →
  no changes; one-word insertion → one ``+``, one ``-``.

These tests are pure-function tests — they don't depend
on the FastAPI app, the audit log, the LLM, or any other
moving part. They exercise :func:`render_markdown_diff`
directly with hand-crafted
:class:`~app.agents.redline_drafter.RedlineProposal` inputs
and assert on the returned Markdown string.

Why we test :func:`render_markdown_diff` (not the
docx renderer)
------------------------------------------------------------
The Build 2 task body lists the markdown-diff as the v0
fallback. The acceptance criteria are explicit about
"one ``+``, one ``-``" and "same input → no changes". The
docx renderer's equivalent tests live in
:mod:`tests.phase3.test_docx_output` (different file).

Test layout
-----------
- :func:`test_empty_proposals_returns_empty_string` —
  the "no proposal → empty output" rule.
- :func:`test_same_input_produces_no_diff_lines` — the
  "same input → no changes" acceptance criterion.
- :func:`test_one_word_insertion_produces_plus_and_minus` —
  the "one-word insertion → one ``+``, one ``-``"
  acceptance criterion.
- :func:`test_section_heading_uses_clause_id` — the
  reviewer-facing convention that each clause gets a
  ``## Clause X`` heading.
- :func:`test_rationale_rendered_as_blockquote` — the
  drafter's rationale is surfaced as a Markdown blockquote
  so the reviewer sees the *why* before the *what*.
- :func:`test_diff_summary_falls_back_to_proposed_text`
  — when the drafter's ``diff_summary`` is malformed, the
  renderer still produces a well-formed diff (the
  proposed_text is the "after", the diff_summary is the
  "before").
- :func:`test_sentence_level_diff_granularity` — the diff
  is at the sentence level, not character level (a
  single-word change in a long clause shows up as one
  ``-`` line + one ``+`` line, not as a forest of
  per-character diffs).
- :func:`test_multiple_proposals_rendered_in_order` —
  the output preserves the input order (the HITL state
  machine passes clauses in clause-table order).
"""

from __future__ import annotations

# pytest's rootdir mechanism adds the repo root to
# sys.path, so `from app...` and `from tests.phase3...`
# both resolve. We don't need explicit sys.path inserts
# here — that's what the top-level tests/conftest.py and
# tests/phase3/conftest.py are for.

from app.agents.redline_drafter.schema import RedlineProposal
from app.output.markdown_diff import (
    _diff_lines,
    _format_proposal_diff,
    _parse_diff_summary,
    _split_sentences,
    render_markdown_diff,
)


# --- Helpers -----------------------------------------------------------------


def _make_proposal(
    *,
    proposed_text: str,
    rationale: str = "the rationale",
    diff_summary: str = "",
) -> RedlineProposal:
    """Build a minimal :class:`RedlineProposal` for the tests.

    The Pydantic schema's defaults are fine for the
    fields we don't set (``attempt=1``). Returns a
    validated instance.
    """
    return RedlineProposal(
        proposed_text=proposed_text,
        rationale=rationale,
        diff_summary=diff_summary,
    )


# --- Sentence-split helper tests ---------------------------------------------


def test_split_sentences_basic():
    """``_split_sentences`` breaks on ``.`` / ``?`` / ``!`` + whitespace."""
    sentences = _split_sentences("First sentence. Second sentence? Third!")
    assert sentences == ["First sentence.", "Second sentence?", "Third!"]


def test_split_sentences_empty_input():
    """Empty / whitespace-only input returns an empty list."""
    assert _split_sentences("") == []
    assert _split_sentences("   \n\n  ") == []


def test_split_sentences_collapses_whitespace():
    """Internal whitespace is collapsed to single spaces."""
    sentences = _split_sentences("First  sentence.\n\n   Second   sentence.")
    assert sentences == ["First sentence.", "Second sentence."]


# --- diff_summary parser tests -----------------------------------------------


def test_parse_diff_summary_standard_form():
    """The drafter's standard ``Original: X. New: Y.`` shape parses cleanly."""
    parsed = _parse_diff_summary("Original: The quick brown fox. New: The quick brown fox jumps.")
    assert parsed == ("The quick brown fox", "The quick brown fox jumps")


def test_parse_diff_summary_with_newlines():
    """The parser accepts newlines between the markers and the bodies."""
    parsed = _parse_diff_summary("Original:\n  The quick brown fox.\nNew:\n  The quick brown fox jumps.")
    assert parsed == ("The quick brown fox", "The quick brown fox jumps")


def test_parse_diff_summary_dash_separator():
    """The parser accepts ``-`` as the separator (a common drafter variation)."""
    parsed = _parse_diff_summary("Original - The quick brown fox. New - The quick brown fox jumps.")
    assert parsed == ("The quick brown fox", "The quick brown fox jumps")


def test_parse_diff_summary_unparseable():
    """A summary without the ``Original`` / ``New`` markers returns ``None``."""
    assert _parse_diff_summary("rewrote the term to be 3 years instead of perpetual") is None
    assert _parse_diff_summary("") is None


# --- diff_lines unit tests ---------------------------------------------------


def test_diff_lines_same_input_no_changes():
    """``_diff_lines`` returns no ``-`` / ``+`` lines for identical inputs."""
    removed, added = _diff_lines("The quick brown fox.", "The quick brown fox.")
    assert removed == []
    assert added == []


def test_diff_lines_one_word_insertion():
    """``_diff_lines`` produces one ``-`` and one ``+`` for a one-word insertion."""
    removed, added = _diff_lines(
        "The quick brown fox.",
        "The quick brown fox jumps.",
    )
    # The two texts split into ["The quick brown fox."] vs
    # ["The quick brown fox jumps."] — one delete + one insert.
    assert removed == ["- The quick brown fox."]
    assert added == ["+ The quick brown fox jumps."]


def test_diff_lines_pure_insertion_no_deletion():
    """A pure insertion (extra sentence at the end) emits one ``+`` line."""
    removed, added = _diff_lines(
        "First sentence.",
        "First sentence. Second sentence.",
    )
    assert removed == []
    assert added == ["+ Second sentence."]


def test_diff_lines_pure_deletion_no_insertion():
    """A pure deletion (a sentence removed) emits one ``-`` line."""
    removed, added = _diff_lines(
        "First sentence. Second sentence.",
        "First sentence.",
    )
    assert removed == ["- Second sentence."]
    assert added == []


# --- _format_proposal_diff ---------------------------------------------------


def test_format_proposal_diff_with_parseable_summary():
    """When the diff_summary parses, the function emits a sentence-level diff."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox jumps.",
        rationale="r",
        diff_summary="Original: The quick brown fox. New: The quick brown fox jumps.",
    )
    lines = _format_proposal_diff(proposal)
    # The diff parser strips the trailing period from the
    # ``before``/``after`` bodies, so the emitted line is
    # ``- The quick brown fox`` (no trailing period). The
    # spec is the parsed-pair is the input to the diff
    # computation, not the raw ``Original: X. New: Y.``
    # string.
    assert any(
        line.startswith("- The quick brown fox") for line in lines
    ), f"expected `- The quick brown fox` line, got: {lines!r}"
    assert any(
        line.startswith("+ The quick brown fox jumps") for line in lines
    ), f"expected `+ The quick brown fox jumps` line, got: {lines!r}"


def test_format_proposal_diff_unparseable_falls_back():
    """When the diff_summary doesn't parse, the proposed_text is the "after"."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox jumps.",
        rationale="r",
        diff_summary="rewrote the term to be 3 years",
    )
    lines = _format_proposal_diff(proposal)
    # The diff_summary is the "before" (it's the closest concrete
    # text we have without the original clause), the
    # proposed_text is the "after".
    assert any(line.startswith("- ") for line in lines)
    assert any(line.startswith("+ ") for line in lines)
    # The proposed_text must appear on a `+` line.
    assert any("The quick brown fox jumps." in line for line in lines)


def test_format_proposal_diff_same_input_returns_empty():
    """``_format_proposal_diff`` returns no lines for identical before/after."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox.",
        rationale="r",
        diff_summary="Original: The quick brown fox. New: The quick brown fox.",
    )
    lines = _format_proposal_diff(proposal)
    assert lines == []


# --- render_markdown_diff acceptance criteria --------------------------------


def test_empty_proposals_returns_empty_string():
    """No proposals → empty string (no spurious ``#`` header)."""
    out = render_markdown_diff("Test contract", [])
    assert out == ""


def test_same_input_produces_no_diff_lines():
    """Spec acceptance: same input → no ``+`` / ``-`` lines."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox.",
        rationale="r",
        diff_summary="Original: The quick brown fox. New: The quick brown fox.",
    )
    out = render_markdown_diff("Test contract", [("c1", proposal)])
    # The diff body must contain no ``+`` or ``-`` lines.
    diff_lines = [
        line for line in out.splitlines()
        if line.startswith("+ ") or line.startswith("- ")
    ]
    assert diff_lines == [], f"expected no diff lines, got: {diff_lines!r}"


def test_one_word_insertion_produces_plus_and_minus():
    """Spec acceptance: one-word insertion → one ``+``, one ``-``."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox jumps.",
        rationale="r",
        diff_summary="Original: The quick brown fox. New: The quick brown fox jumps.",
    )
    out = render_markdown_diff("Test contract", [("c1", proposal)])
    plus_lines = [line for line in out.splitlines() if line.startswith("+ ")]
    minus_lines = [line for line in out.splitlines() if line.startswith("- ")]
    assert len(plus_lines) >= 1, f"expected ≥1 `+` line, got: {plus_lines!r}"
    assert len(minus_lines) >= 1, f"expected ≥1 `-` line, got: {minus_lines!r}"


def test_section_heading_uses_clause_id():
    """Each clause gets a ``## Clause X`` section heading."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox jumps.",
        rationale="r",
        diff_summary="Original: The quick brown fox. New: The quick brown fox jumps.",
    )
    out = render_markdown_diff("Test contract", [("c-abc-123", proposal)])
    assert "## Clause c-abc-123" in out


def test_rationale_rendered_as_blockquote():
    """The drafter's rationale is rendered as a Markdown blockquote."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox jumps.",
        rationale="the term was perpetual, must be 3 years",
        diff_summary="Original: The quick brown fox. New: The quick brown fox jumps.",
    )
    out = render_markdown_diff("Test contract", [("c1", proposal)])
    assert "> the term was perpetual, must be 3 years" in out


def test_contract_name_in_header():
    """The first non-blank line of the baseline is used as the contract name."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox jumps.",
        rationale="r",
        diff_summary="Original: The quick brown fox. New: The quick brown fox jumps.",
    )
    out = render_markdown_diff(
        "MUTUAL NON-DISCLOSURE AGREEMENT\n\nThis Agreement is entered into...",
        [("c1", proposal)],
    )
    assert "# Redline: MUTUAL NON-DISCLOSURE AGREEMENT" in out


def test_multiple_proposals_rendered_in_order():
    """Proposals render in input order — the reviewer reads top-to-bottom."""
    p1 = _make_proposal(
        proposed_text="Term is 3 years.",
        rationale="r1",
        diff_summary="Original: Term is perpetual. New: Term is 3 years.",
    )
    p2 = _make_proposal(
        proposed_text="Governing law is Delaware.",
        rationale="r2",
        diff_summary="Original: Governing law is Texas. New: Governing law is Delaware.",
    )
    p3 = _make_proposal(
        proposed_text="Return materials within 30 days.",
        rationale="r3",
        diff_summary="Original: Return materials within 60 days. New: Return materials within 30 days.",
    )
    out = render_markdown_diff("Test contract", [("c1", p1), ("c2", p2), ("c3", p3)])
    # The three section headings must appear in the input order.
    c1_idx = out.find("## Clause c1")
    c2_idx = out.find("## Clause c2")
    c3_idx = out.find("## Clause c3")
    assert c1_idx != -1 and c2_idx != -1 and c3_idx != -1
    assert c1_idx < c2_idx < c3_idx


def test_sentence_level_diff_granularity():
    """The diff is at the sentence level, not character level.

    A 5-word change in a 50-word clause should produce
    exactly one ``-`` line and one ``+`` line, not a
    forest of per-character diffs.
    """
    long_before = (
        "The Receiving Party shall hold the Confidential Information in strict confidence. "
        "The Receiving Party shall not disclose the Confidential Information to any third party. "
        "The Receiving Party shall use the Confidential Information solely for the Permitted Purpose. "
        "The Receiving Party shall return all Confidential Information within 30 days of termination."
    )
    long_after = long_before.replace("30 days", "60 days")
    proposal = _make_proposal(
        proposed_text=long_after,
        rationale="r",
        diff_summary=f"Original: {long_before} New: {long_after}",
    )
    out = render_markdown_diff("Test contract", [("c1", proposal)])
    plus_lines = [line for line in out.splitlines() if line.startswith("+ ")]
    minus_lines = [line for line in out.splitlines() if line.startswith("- ")]
    # 50 words with one 2-word change should produce exactly
    # one ``+`` line + one ``-`` line at the sentence level.
    assert len(plus_lines) == 1, f"expected 1 `+` line, got {len(plus_lines)}: {plus_lines!r}"
    assert len(minus_lines) == 1, f"expected 1 `-` line, got {len(minus_lines)}: {minus_lines!r}"


def test_output_is_valid_markdown_no_trailing_blank_lines():
    """The output has no trailing blank lines (the file ends with one ``\\n``)."""
    proposal = _make_proposal(
        proposed_text="The quick brown fox jumps.",
        rationale="r",
        diff_summary="Original: The quick brown fox. New: The quick brown fox jumps.",
    )
    out = render_markdown_diff("Test contract", [("c1", proposal)])
    # The output ends with exactly one ``\n`` — not zero, not
    # two or more. POSIX-correct line endings.
    assert not out.endswith("\n\n"), "output should not have trailing blank lines"
    assert out.endswith("\n"), "output should end with exactly one newline"


def test_diff_summary_unparseable_does_not_raise():
    """A malformed diff_summary falls back gracefully — no exception."""
    proposal = _make_proposal(
        proposed_text="Term is 3 years.",
        rationale="r",
        diff_summary="I changed the term.",
    )
    # Must not raise.
    out = render_markdown_diff("Test contract", [("c1", proposal)])
    # Must still produce a well-formed doc with ≥1 of each kind.
    plus_lines = [line for line in out.splitlines() if line.startswith("+ ")]
    minus_lines = [line for line in out.splitlines() if line.startswith("- ")]
    assert len(plus_lines) >= 1
    assert len(minus_lines) >= 1
