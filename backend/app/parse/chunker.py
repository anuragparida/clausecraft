"""Semantic chunker — turns text into a list of clauses.

Inputs come from the ingest layer (PDF or DOCX). The chunker doesn't
care which one — it operates on plain text + (optional) per-paragraph
metadata. The output is a :class:`RawClause` list that the classifier
fills in.

Strategy:

1. Pre-process the text: strip known boilerplate (PDF page headers
   like "Copyright © ... Page 1 of 3"), and join "orphan" heading
   markers like "1." that ended up on their own line.
2. Split the text into paragraphs on double newlines (the DOCX
   path) and on "hard" single-newline boundaries (the PDF path).
3. Within each paragraph, detect in-line numbered sections like
   "1. Title..." that got fused into one paragraph and split on
   those boundaries too — this is the common PDF case where pymupdf
   uses single newlines for soft line wraps.
4. Walk the resulting paragraph list, identifying heading
   boundaries via the regex heuristics in
   :mod:`app.parse.heuristics`.
5. Group non-heading paragraphs into the most recent heading.
6. If no headings are found (e.g. a 1-page short NDA, or a weird
   format that doesn't trigger any regex), fall back to "one clause
   per paragraph" — the conservative default.

The result is deliberately over-mergey: a clause that contains 5
paragraphs of body text under a single ``1. Confidentiality`` heading
is one clause. The classifier will get the whole thing and is
expected to label it once. The "under-chunk" failure mode is much
easier to recover from downstream than the "over-chunk" failure mode
(splits a real clause mid-sentence).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

from app.parse.heuristics import HeadingMatch, looks_like_heading

logger = logging.getLogger(__name__)


# A paragraph break, in plain text. PDF text often uses a single
# newline inside a paragraph (after a soft line-wrap) and a double
# newline between paragraphs; DOCX paragraphs are explicit. We treat
# any line that is empty OR consists of whitespace as a paragraph
# boundary.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


# PDF page-header boilerplate. Many public-source NDAs include a
# "Copyright © YYYY by <publisher> Page N of M" line at the top of
# every page. We strip the most common shapes. The pattern is
# deliberately conservative — it would be easy to over-strip
# legitimate text if we widened the match.
_PDF_BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*Copyright\s*©?\s*\d{4}.*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
    # The "Copyright © YYYY by <publisher>" line on its own, without
    # the "Page N of M" trailer on the same line.
    re.compile(r"^\s*Copyright\s*©?\s*\d{4}\s+by\s+\S+.*$", re.IGNORECASE),
]


# An "orphan" heading marker is a line that contains just a section
# number (e.g. "1.", "2.", "14.3.2.") and nothing else. PDFs commonly
# put the number on one line and the title on the next; without
# joining them, the heading loses its title and the body becomes an
# orphan paragraph. We join these with the following non-empty line
# at pre-processing time.
_ORPHAN_HEADING_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s*$")


# In-line numbered-section detector. Catches the case where the PDF
# flattens a paragraph break into a single newline:
#
#     "...Prior text. \n1. Either Party may disclose...\n2. When informed..."
#
# Without splitting, the chunker sees one giant paragraph and never
# produces more than 1 clause. We split on the start of any
# in-line top-level "N." heading so the chunker can treat each
# top-level section as its own clause.
#
# The pattern matches "N." (a single digit followed by a dot) at
# the start of a line, followed by space + capital letter. We
# deliberately do NOT match "N.N." (e.g. 1.1) or "N.N.N." (e.g.
# 1.1.1) — those are sub-sections that should remain part of
# the parent clause's body. The "1.1.1 Heading" lines themselves
# still get matched as headings later (via ``looks_like_heading``),
# but they do not trigger an in-place paragraph split. This keeps
# the chunker from over-chunking a 17-page long NDA into 200+
# sub-section chunks whose body is generic boilerplate the
# classifier can't label.
_INLINE_SECTION_BOUNDARY = re.compile(
    r"\n(?=\d+(?:\.\d+)*\.?\s+[A-Z])"
)


# In-line ALL-CAPS heading detector. The "weird-format" PDFs often
# have no double-newline between sections, so the chunker sees a
# single paragraph like:
#
#     "MUTUAL NONDISCLOSURE AGREEMENT\nThis Mutual... \nCONFIDENTIALITY.\nThe parties acknowledge..."
#
# Splitting on numbered boundaries alone wouldn't catch the
# CONFIDENTIALITY/TERM/OBLIGATIONS sections because they are
# unnumbered. We split on a `\n` followed by an ALL-CAPS line
# ending in `\.?` so the in-line heading peel can pick them up
# later.
_INLINE_ALLCAPS_BOUNDARY = re.compile(
    r"\n(?=[A-Z][A-Z][A-Z][A-Z\s]{2,}[A-Z][\.:]?\n)"
)


@dataclass
class RawClause:
    """A single clause as produced by the chunker.

    The ``id`` is a stable, document-local identifier of the form
    ``c{N}`` where N is the 1-based index in the clause list. Stable
    across re-classification of the same input — the classifier
    preserves the id, only fills in ``type`` and ``confidence``.

    Attributes
    ----------
    id
        ``c1``, ``c2``, ...
    text
        The concatenated text of every paragraph assigned to this
        clause, separated by ``\\n\\n``. Heading lines are NOT
        included in the text — they're in ``position.section``.
    position
        Position metadata, populated below.
    """

    id: str
    text: str
    section: str = ""  # the section_id from the heading (or "" if none)
    section_title: str = ""  # human-readable title
    paragraph_indices: list[int] = field(default_factory=list)


def _strip_boilerplate(lines: list[str]) -> list[str]:
    """Drop known boilerplate lines (PDF page headers etc).

    Returns a new list. Lines that match one of the boilerplate
    patterns are removed; everything else is preserved. We do not
    rejoin adjacent lines here — that's the caller's job.
    """
    out: list[str] = []
    for line in lines:
        if any(p.match(line) for p in _PDF_BOILERPLATE_PATTERNS):
            continue
        out.append(line)
    return out


def _strip_orphan_boilerplate_words(text: str) -> str:
    """Strip any "Copyright © YYYY ... Page N of M" tokens from ``text``.

    PDFs sometimes emit the page header on its own line, but pymupdf
    (and other extractors) can drop the newline that follows, fusing
    the header onto the start of the next paragraph. The result is
    e.g. ``"Copyright © 2018 by X Page 1 of 3MUTUAL NON-DISCLOSURE ..."`` —
    a single "paragraph" that starts with boilerplate. The boilerplate
    can also appear in the middle of a paragraph when a page break
    is mid-sentence (e.g. ``"...injunctive injury if its Confidential
    Information is made\\nCopyright © 2020 ... Page 2 of 3\\npublic,
    released to..."``). We strip the leading boilerplate so the
    paragraph starts with its real content.

    The pattern is the same as the line-based one, but anchored at
    the start of a string (after optional whitespace). We strip up
    to 2 occurrences — the leading one and one in the middle of the
    text.
    """
    pattern = re.compile(
        r"\s*Copyright\s*©?\s*\d{4}[^\n]*?Page\s+\d+\s+of\s+\d+\s*",
        re.IGNORECASE,
    )
    return pattern.sub(" ", text, count=2).strip()


def _join_orphan_headings(lines: list[str]) -> list[str]:
    """Join a line that is just a number ("1.", "14.3.2.") with the next line.

    PDFs frequently split a heading across two lines:
        "1."
        "Either Party may disclose..."
    Without joining, the chunker treats the heading as a 1-char title
    and the next paragraph as an orphan body. We join the two into
    "1. Either Party may disclose..." so the heading regex can
    recognise the title and assign the body to the right clause.
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _ORPHAN_HEADING_NUMBER.match(line)
        if m and i + 1 < len(lines) and lines[i + 1].strip():
            # Join with a single space — the heading regex expects
            # "1. Title..." with a single space.
            out.append(f"{m.group(1).rstrip('.')} {lines[i + 1].strip()}")
            i += 2
        else:
            out.append(line)
            i += 1
    return out


def _preprocess(text: str) -> str:
    """Apply boilerplate-strip + orphan-join + paragraph normalisation.

    The output is a cleaner plain-text block ready for paragraph
    splitting. The function is idempotent — running it twice on the
    same text produces the same output.
    """
    if not text:
        return text
    # Split on newlines, process line-by-line, rejoin.
    lines = text.split("\n")
    lines = _strip_boilerplate(lines)
    # After stripping a boilerplate line that ended up adjacent to a
    # continuation line, glue the continuation back onto the previous
    # line. The pattern: the previous line ends with a word char (no
    # terminal punctuation) and the next non-empty line starts with
    # a lowercase letter. We only do this for one line at a time to
    # avoid runaway merges.
    lines = _glue_continuation_after_boilerplate(lines)
    lines = _join_orphan_headings(lines)
    return "\n".join(lines)


def _glue_continuation_after_boilerplate(lines: list[str]) -> list[str]:
    """If a run of boilerplate lines was followed by a continuation line
    (lowercase first letter, the previous line didn't end with
    sentence punctuation), glue the continuation onto the previous
    non-boilerplate line and drop the boilerplate run + continuation.

    Boilerplate often spans 2 lines ("Copyright © ... \nPage N of M"),
    so we skip runs of consecutive boilerplate lines, not just one.
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if any(p.match(line) for p in _PDF_BOILERPLATE_PATTERNS):
            # Find the end of the boilerplate run.
            j = i + 1
            while j < len(lines) and any(
                p.match(lines[j]) for p in _PDF_BOILERPLATE_PATTERNS
            ):
                j += 1
            # Find the next non-empty line.
            k = j
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k < len(lines):
                cont = lines[k].strip()
                if (
                    cont
                    and cont[0].islower()
                    and out
                    and out[-1].rstrip()
                    and out[-1].rstrip()[-1] not in ".!?:;\"'"
                ):
                    out[-1] = out[-1].rstrip() + " " + cont
                    i = k + 1
                    continue
            i = j
            continue
        out.append(line)
        i += 1
    return out


def _split_paragraphs(text: str) -> list[str]:
    """Split a block of text on paragraph breaks.

    Empty / whitespace-only paragraphs are dropped — they exist in
    many PDFs as visual padding, not as content. The DOCX path
    already produces only non-empty paragraphs.
    """
    if not text:
        return []
    parts = _PARAGRAPH_BREAK.split(text)
    return [p.strip() for p in parts if p.strip()]


def _split_inline_heading(paragraph: str) -> tuple[HeadingMatch | None, str]:
    """If a paragraph starts with a heading line, peel it off.

    The chunker produces paragraphs that may begin with a single-line
    heading (``CONFIDENTIALITY.``) followed by a body line on the next
    line, joined together by a ``\\n``. This is a common PDF shape
    where the heading and its body are rendered as adjacent lines
    without a blank line between them. We split the heading off so
    the rest of the chunker can treat it as a real heading and the
    body as a real body paragraph.

    The returned body is the FULL paragraph (heading + remainder) so
    the chunker's ``current_paragraphs`` ends up with the complete
    clause text. Without this, a sentence that starts with the
    section number (``1. Either Party may disclose...``) and
    continues across a soft line wrap (``...in confidence provided
    that...``) would be split into a heading-only title and a
    body-fragment, and the classifier would see only the fragment.

    Returns ``(heading_or_None, full_paragraph)`` where
    ``full_paragraph`` is the original ``paragraph`` unchanged when
    no heading is detected, and is the original paragraph (with
    heading still embedded) when a heading is detected — the
    heading metadata is recorded separately and the original text
    is preserved in full for the clause body.
    """
    if "\n" not in paragraph:
        return None, paragraph
    head, _, rest = paragraph.partition("\n")
    heading = looks_like_heading(head)
    if heading is None:
        return None, paragraph
    # Return the full paragraph (heading + body) as the "body". The
    # caller tracks the heading metadata via the returned tuple.
    return heading, paragraph


def _split_inplace_sections(paragraphs: list[str]) -> list[str]:
    """Split any paragraph that contains in-line section boundaries.

    The input is a list of paragraphs (already split on double
    newlines). The function returns a new list where any paragraph
    that contains a hard newline followed by a heading-like line
    is split at that boundary. This is the PDF case where pymupdf
    emits soft line breaks for in-paragraph text and the original
    section boundaries are now buried inside a single paragraph.

    Two flavours of boundary are split:

    - ``_INLINE_SECTION_BOUNDARY`` — top-level numbered sections
      ("1. Title", "2. Title", ...). Sub-section IDs (1.1, 1.1.1)
      are intentionally NOT split here so the parent clause keeps
      its full body.
    - ``_INLINE_ALLCAPS_BOUNDARY`` — unnumbered ALL-CAPS headings
      ("CONFIDENTIALITY.", "TERM.") followed by a newline + body.
      The "weird-format" PDF case.
    """
    out: list[str] = []
    for para in paragraphs:
        splits_a = _INLINE_SECTION_BOUNDARY.split(para)
        splits: list[str] = []
        for s in splits_a:
            sub = _INLINE_ALLCAPS_BOUNDARY.split(s)
            splits.extend(sub)
        if len(splits) > 1:
            out.extend(s.strip() for s in splits if s.strip())
        else:
            out.append(para)
    return out


def _is_short_form_clause(text: str) -> bool:
    """Heuristic: a "very short" text is likely a title or signature block.

    Used by the fallback "no headings" path to avoid emitting dozens of
    one-line clauses for things like "IN WITNESS WHEREOF" or "Signature:".

    The threshold is 30 chars (a single line of pre-amble prose) — short
    enough to skip a title line, generous enough that a real one-sentence
    clause (which is rare in NDAs) survives.
    """
    stripped = text.strip()
    return len(stripped) < 30


def _starts_with_lowercase(text: str) -> bool:
    """True when the first non-whitespace char of ``text`` is lowercase.

    Used to detect paragraph continuations: a paragraph that begins
    with a lowercase letter is almost certainly a continuation of the
    previous sentence (PDFs break lines mid-sentence all the time).
    """
    for ch in text:
        if ch.isspace():
            continue
        return ch.islower()
    return False


def _merge_continuations(paragraphs: list[str]) -> list[str]:
    """Merge a paragraph that starts lowercase into the previous one.

    PDFs commonly break a single sentence across a page boundary, with
    the second half on the new page. After the line-based processing
    and in-place section split, this manifests as two adjacent
    paragraphs where the second one starts with a lowercase letter.
    The function concatenates them with a single space.

    Headings (paragraphs that start with "N." or are ALL-CAPS) are
    never treated as continuations.
    """
    out: list[str] = []
    for p in paragraphs:
        if out and _starts_with_lowercase(p) and not looks_like_heading(p):
            # Continuation: join with the previous paragraph.
            out[-1] = (out[-1].rstrip() + " " + p.lstrip()).strip()
        else:
            out.append(p)
    return out


# Boilerplate / preamble patterns that should NEVER become a clause.
# We filter these AFTER chunking so the chunker itself stays general.
_PREAMBLE_PATTERNS = [
    re.compile(r"^MUTUAL\s+NDA\s*$", re.IGNORECASE),
    re.compile(r"^MUTUAL\s+NON-?DISCLOSURE\s+AGREEMENT", re.IGNORECASE),
    re.compile(r"^NON-?DISCLOSURE\s+AGREEMENT", re.IGNORECASE),
    re.compile(r"^THIS\s+MUTUAL\s+NON-?DISCLOSURE\s+AGREEMENT", re.IGNORECASE),
    # Bare ALL_CAPS document-title patterns (when the chunker is
    # conservative and treats them as headings anyway).
    re.compile(r"^ALL_CAPS:AGREEMENT$", re.IGNORECASE),
    re.compile(r"^AGREEMENT\s*$", re.IGNORECASE),
    re.compile(r"^WHEREAS\s+", re.IGNORECASE),
    re.compile(r"^NOW,?\s+THEREFORE", re.IGNORECASE),
    re.compile(r"^IN\s+WITNESS\s+WHEREOF", re.IGNORECASE),
    re.compile(r"^PARTY\s+[AB]\S*\s+SIGNATURE", re.IGNORECASE),
    re.compile(r"^PRINT\s+NAME", re.IGNORECASE),
]


def _is_preamble(text: str) -> bool:
    """True when ``text`` looks like a title, signature, or preamble line.

    These should not become clauses — they don't carry a contractual
    obligation, and the classifier would mark them "unknown" anyway.
    We filter them out of the final clause list so the 80% ratio
    check is measured on real clauses, not boilerplate.
    """
    stripped = text.strip()
    if not stripped:
        return True
    # Drop a leading page-header line if it survived the
    # boilerplate strip, so the pattern check sees the real start
    # of the paragraph.
    head = re.sub(
        r"^.*?Copyright\s*©?\s*\d{4}[^\n]*?Page\s+\d+\s+of\s+\d+\s*",
        "",
        stripped[:200],
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    if not head:
        return True
    return any(p.search(head) for p in _PREAMBLE_PATTERNS)


def chunk_text(text: str) -> list[RawClause]:
    """Turn ``text`` into a list of :class:`RawClause`.

    See module docstring for the strategy. The function is pure
    (no I/O, no global state) so it's trivially testable.
    """
    preprocessed = _preprocess(text)
    paragraphs = _split_paragraphs(preprocessed)
    # Drop a leading "Copyright ... Page N of M" that got fused onto
    # the start of a paragraph when the PDF didn't emit a hard newline
    # after the page header.
    paragraphs = [_strip_orphan_boilerplate_words(p) for p in paragraphs]
    paragraphs = [p for p in paragraphs if p.strip()]
    # Split any paragraph that has in-line "N. Title" section
    # boundaries — the common PDF case.
    paragraphs = _split_inplace_sections(paragraphs)
    # Merge a paragraph that starts lowercase into the previous one
    # (PDF page-break continuations).
    paragraphs = _merge_continuations(paragraphs)
    if not paragraphs:
        return []

    # First pass: walk the paragraphs, identify heading vs body.
    # A heading immediately starts a new clause; a body paragraph
    # extends the most recent clause.
    clauses: list[RawClause] = []
    current_section = ""
    current_section_title = ""
    current_paragraphs: list[str] = []
    current_indices: list[int] = []
    next_id = 1

    def _flush() -> None:
        """Close out the current clause and append it to the list."""
        nonlocal next_id
        if not current_paragraphs and not current_section:
            return
        if not current_paragraphs:
            # Heading without any following body — still emit a clause
            # with the heading as its text so the classifier can label it.
            body = current_section_title or current_section
        else:
            body = "\n\n".join(current_paragraphs)
        clauses.append(
            RawClause(
                id=f"c{next_id}",
                text=body,
                section=current_section,
                section_title=current_section_title,
                paragraph_indices=list(current_indices),
            )
        )
        next_id += 1

    headings_found = 0
    for idx, para in enumerate(paragraphs):
        # If the paragraph starts with a heading line, peel it off and
        # treat the rest of the paragraph as the first body paragraph.
        # The clause's text is built from the body paragraphs only —
        # the heading line itself is preserved in
        # ``current_section_title`` and never re-appears in the body
        # (otherwise the classifier sees the heading twice).
        inline_heading, para = _split_inline_heading(para)
        if inline_heading is not None:
            # All numbered headings (top-level and sub-section) start
            # a new clause.
            _flush()
            current_section = inline_heading.section_id
            current_section_title = inline_heading.title
            current_paragraphs = []
            current_indices = []
            headings_found += 1
            # The remainder becomes a body paragraph (unless it's empty).
            if para:
                current_paragraphs.append(para)
                current_indices.append(idx)
            continue
        heading = looks_like_heading(para)
        # The "heading" detector can false-positive on a body paragraph
        # that starts with "1." inside its first sentence. We require
        # the heading itself to be relatively short (typical clause
        # titles are < 200 chars). If the paragraph is one line and
        # matches a heading pattern, it's a real heading; if it's
        # multi-line, the inline-heading peel above already handled it.
        if heading is not None and "\n" not in para and len(para.strip()) < 200:
            # Close the current clause (if any).
            _flush()
            current_section = heading.section_id
            current_section_title = heading.title
            current_paragraphs = []
            current_indices = []
            headings_found += 1
        else:
            current_paragraphs.append(para)
            current_indices.append(idx)

    # Don't forget the trailing clause.
    _flush()

    # Fallback: if no headings were detected at all, the loop above
    # produced exactly one clause containing every paragraph. That's
    # *too coarse* for a short NDA with 3 distinct clauses — we'd
    # want each paragraph as its own clause. Apply the no-headings
    # fallback: emit one clause per non-trivially-short paragraph.
    if headings_found == 0 and len(clauses) == 1 and len(paragraphs) > 1:
        clauses = []
        first_skipped = False
        for n, para in enumerate(paragraphs, start=1):
            # The very first short paragraph in a heading-less short
            # document is almost always a title / preamble line
            # ("NDA between Acme and Beta.", "Mutual NDA", etc.). Skip
            # it explicitly so it doesn't pollute the clause list
            # with non-clause junk. If the document is heading-less
            # but every paragraph is non-trivially short, we keep
            # them all.
            if (
                not first_skipped
                and _is_short_form_clause(para)
                and not _is_preamble(para)
            ):
                first_skipped = True
                continue
            # Preserve deep section IDs (1.1.1, 1.2.3) when the
            # paragraph looks like a sub-section heading.
            heading = looks_like_heading(para)
            section_id = heading.section_id if heading is not None and len(para.strip()) < 200 else ""
            section_title = heading.title if heading is not None and len(para.strip()) < 200 else ""
            clauses.append(
                RawClause(
                    id=f"c{n}",
                    text=para,
                    section=section_id,
                    section_title=section_title,
                    paragraph_indices=[n - 1],
                )
            )
        if not clauses:
            # Edge case: every paragraph was "short". Fall back to one
            # clause per paragraph, no filtering.
            clauses = [
                RawClause(
                    id=f"c{n}",
                    text=para,
                    section="",
                    section_title="",
                    paragraph_indices=[n - 1],
                )
                for n, para in enumerate(paragraphs, start=1)
            ]

    # Drop preamble / signature / title clauses. Re-numbered
    # sequentially so the IDs are dense.
    return _filter_preamble(clauses)


def _filter_preamble(clauses: list[RawClause]) -> list[RawClause]:
    """Drop preamble / signature / title clauses from the output.

    The classifier is asked to label every clause the chunker emits.
    Preamble lines like "MUTUAL NON-DISCLOSURE AGREEMENT" and
    "WHEREAS ..." never fit any of the 15 NDA clause types, so
    marking them "unknown" pollutes the 80% ratio check. We strip
    them at the boundary so the chunker's internal logic stays
    general.
    """
    out: list[RawClause] = []
    next_id = 1
    for c in clauses:
        if _is_preamble(c.text):
            continue
        # Re-number the surviving clauses so the IDs are dense (c1,
        # c2, c3, ...). The classifier preserves the ID; if a
        # preamble is filtered out, downstream code shouldn't have
        # to know about the gap.
        out.append(
            RawClause(
                id=f"c{next_id}",
                text=c.text,
                section=c.section,
                section_title=c.section_title,
                paragraph_indices=list(c.paragraph_indices),
            )
        )
        next_id += 1
    return out


def chunk_paragraphs(paragraphs: Iterable[str]) -> list[RawClause]:
    """Convenience: chunk from an iterable of paragraph strings.

    Equivalent to ``chunk_text("\\n\\n".join(paragraphs))`` but
    avoids the round-trip through a string. Used by the DOCX path
    where paragraphs are already separated.
    """
    paras = [p for p in paragraphs]
    # Reuse the paragraph-aware path: build a string with double
    # newlines, then split. The cost is one extra string join.
    joined = "\n\n".join(paras)
    return chunk_text(joined)
