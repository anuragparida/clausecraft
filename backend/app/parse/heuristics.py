"""Parse heuristics — clause-boundary detection.

These are deliberately conservative. The shape we want to recognise:

- ``1. Title``           — top-level numbered section (``^\\d+``)
- ``1.1 Title``          — second-level
- ``1.1.1 Title``        — third-level and beyond
- ``SECTION 1. TITLE``   — the older "Section N." convention
- ``ARTICLE I. TITLE``   — Roman-numeral articles, common in some NDAs
- ``CONFIDENTIALITY.``   — ALL-CAPS, often unnumbered (this is the
  "weird-format" case in the Phase 1 test set)

Anything else is treated as body text. Conservative = prefer one
clause that spans multiple paragraphs over two clauses that split
mid-sentence. The risk we're managing is "type=definition_confidential_info
on a half-sentence that says 'Confidential Information shall mean...'".
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# --- Regex patterns -----------------------------------------------------

# Numbered section: "1.", "1.2", "12.3.4", optionally followed by space + Title.
# Also matches a bare "1." (no title) when the line is < 6 chars — this
# handles the "1.\n" heading shape common in NDAs where the section
# number is on its own line and the title is on the next.
RE_NUMBERED = re.compile(
    r"^(?P<num>\d+(?:\.\d+)*)[\.\)]?\s*(?P<title>[A-Z][^\n]{2,200})?$"
)

# "Section 1." / "Section 12." / "Section 1.2"
RE_SECTION = re.compile(
    r"^(?:Section|SECTION|Article|ARTICLE)\s+"
    r"(?P<num>[IVXLCDM\d]+(?:\.\d+)*)\.?\s*"
    r"(?P<title>[A-Z][^\n]{0,200})?$"
)

# ALL-CAPS header line: "CONFIDENTIALITY." / "DEFINITIONS"
# The line must be ≥3 chars, ≤80 chars, only letters/spaces, and
# end with optional punctuation.
RE_ALLCAPS = re.compile(
    r"^(?P<title>[A-Z][A-Z\s]{2,78}[A-Z])[\.:]?$"
)

# A heading line is "short" when it fits in a single line and the
# next non-empty line either starts a body paragraph (longer than
# the heading) or is blank. We don't enforce that here; the chunker
# applies the heuristic.


@dataclass(frozen=True)
class HeadingMatch:
    """The result of a successful heading match.

    ``section_id`` is a string like ``"1"``, ``"1.2"``, ``"3.1.4"``,
    or ``"ALL_CAPS:CONFIDENTIALITY"`` for unnumbered ALL-CAPS headers.
    It is the value that lands in ``Clause.position.section``.
    """

    section_id: str
    title: str
    level: int  # 1 for top-level, 2 for "1.2", 3 for "1.2.3", 0 for ALL-CAPS


def looks_like_heading(line: str) -> HeadingMatch | None:
    """Return a :class:`HeadingMatch` if ``line`` looks like a clause heading.

    The check is line-based; the caller is expected to pre-split the
    text on newlines. Whitespace is stripped before matching.
    """
    text = line.strip()
    if not text:
        return None

    # Numbered section: prefer the most specific match.
    m = RE_NUMBERED.match(text)
    if m:
        num = m.group("num")
        title = (m.group("title") or "").strip()
        depth = num.count(".") + 1
        return HeadingMatch(section_id=num, title=title, level=depth)

    # "Section N." or "Article N." style.
    m = RE_SECTION.match(text)
    if m:
        num = m.group("num")
        title = (m.group("title") or "").strip()
        # Normalise Roman-numeral sections to the same shape as numeric
        # ones so downstream code doesn't need to special-case them.
        section_id = num
        depth = num.count(".") + 1 if num.count(".") > 0 else 1
        return HeadingMatch(section_id=section_id, title=title, level=depth)

    # ALL-CAPS header (the "weird-format" case).
    m = RE_ALLCAPS.match(text)
    if m:
        title = m.group("title").strip()
        # Mark ALL-CAPS headers with a prefix so the section_id is
        # always distinguishable from a numeric one.
        return HeadingMatch(
            section_id=f"ALL_CAPS:{title}",
            title=title,
            level=0,
        )

    return None
