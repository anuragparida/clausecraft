"""Pure-function utilities for inspecting a redline .docx.

The Phase 3 e2e test (Build 6) downloads a tracked-changes
``.docx`` and asserts the file is well-formed Word XML with
the right tracked-change attributes. This module is the
**single source of truth** for those assertions — every e2e
test calls into here so the validation logic is in one place
and easy to unit-test against a hand-crafted docx.

Why a separate module (not a private helper in the test file)
------------------------------------------------------------
The validation logic is non-trivial (namespaces, attribute
parsing, ISO-8601 timestamp validation) and we want both:

1. **Unit tests** that exercise it against a hand-crafted
   ``.docx`` with known attributes, so the logic itself is
   tested in isolation.
2. **E2E tests** that use the same code path to validate the
   real Build 2 output.

Putting the logic in a private test helper means the unit
tests would have to import test internals from the e2e file —
uglier than just exposing a normal module.

What the utilities support
--------------------------

- :func:`iter_tracked_changes` — yield every ``w:ins`` and
  ``w:del`` element in the document body, with its
  ``w:author`` and ``w:date`` attributes.
- :func:`count_insertions` / :func:`count_deletions` — the
  e2e assertion "≥1 w:ins and ≥1 w:del per accepted
  proposal".
- :func:`extract_change_authors` — the set of distinct
  authors; the e2e asserts every change is attributed to
  ``"clausecraft"``.
- :func:`extract_change_dates` — the ISO-8601 dates; the
  e2e asserts every one parses.
- :func:`is_valid_iso8601` — helper, exposed for the
  hand-crafted-docx unit test.

The utilities do **not** depend on the FastAPI app, the
audit log, the LLM, or any other moving part. They take a
``bytes`` blob (or a :class:`docx.document.Document` for the
already-parsed case) and return Python primitives.

"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Iterable, Iterator, Union

from docx import Document
from docx.oxml.ns import qn

#: The well-known author the e2e test asserts every tracked
#: change is attributed to. Build 2 (the .docx output) takes
#: this as a config value; the test pins it to keep the
#: assertion tight.
EXPECTED_AUTHOR: str = "clausecraft"

#: The WordprocessingML namespace prefix used throughout
#: this module. ``qn("w:ins")`` resolves to the full Clark
#: notation ``{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ins``.
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@dataclass(frozen=True)
class TrackedChange:
    """One ``w:ins`` or ``w:del`` element in the document body.

    The dataclass is immutable so it's hashable + safe to
    cache in test fixtures without worrying about downstream
    mutation.
    """

    kind: str  # "ins" or "del"
    author: str
    date: str  # raw w:date attribute, before validation
    change_id: str  # the w:id attribute (sequential integer per change)

    def parsed_date(self) -> datetime:
        """Parse :attr:`date` as ISO-8601 UTC. Raises ``ValueError`` on bad input."""
        return _parse_iso8601(self.date)


def _parse_iso8601(s: str) -> datetime:
    """Parse an ISO-8601 string. Accepts the ``Z`` suffix.

    Python's :func:`datetime.fromisoformat` does not accept
    ``Z`` (it requires ``+00:00``) until 3.11; this helper
    normalises the suffix for cross-version compatibility.
    """
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def is_valid_iso8601(s: str) -> bool:
    """``True`` when ``s`` parses as ISO-8601 UTC, ``False`` otherwise."""
    try:
        _parse_iso8601(s)
        return True
    except (ValueError, TypeError):
        return False


def load_document(source: Union[bytes, BinaryIO, str]) -> Document:
    """Open a ``.docx`` from bytes / a file handle / a path.

    The e2e test gets a ``bytes`` blob back from the
    ``GET /contracts/{id}/redline.docx`` endpoint; this
    helper wraps python-docx's :class:`Document` constructor
    so the e2e code stays clean.
    """
    if isinstance(source, (bytes, bytearray)):
        import io

        return Document(io.BytesIO(source))
    return Document(source)


def iter_tracked_changes(doc: Document) -> Iterator[TrackedChange]:
    """Yield every tracked-change element in the document body.

    Walks the body XML looking for ``w:ins`` (insertions) and
    ``w:del`` (deletions). Nested changes (a deletion inside
    an insertion) are returned in document order. The
    ``w:author``, ``w:date``, and ``w:id`` attributes are
    read off the change element itself, not its children —
    that's the Word/LibreOffice rendering rule.
    """
    body = doc.element.body
    for el in body.iter():
        if el.tag == qn("w:ins"):
            yield TrackedChange(
                kind="ins",
                author=el.get(qn("w:author")) or "",
                date=el.get(qn("w:date")) or "",
                change_id=el.get(qn("w:id")) or "",
            )
        elif el.tag == qn("w:del"):
            yield TrackedChange(
                kind="del",
                author=el.get(qn("w:author")) or "",
                date=el.get(qn("w:date")) or "",
                change_id=el.get(qn("w:id")) or "",
            )


def count_insertions(changes: Iterable[TrackedChange]) -> int:
    """Number of ``w:ins`` elements."""
    return sum(1 for c in changes if c.kind == "ins")


def count_deletions(changes: Iterable[TrackedChange]) -> int:
    """Number of ``w:del`` elements."""
    return sum(1 for c in changes if c.kind == "del")


def extract_change_authors(changes: Iterable[TrackedChange]) -> set[str]:
    """The distinct set of authors. Empty when the doc has no tracked changes."""
    return {c.author for c in changes}


def extract_change_dates(changes: Iterable[TrackedChange]) -> list[str]:
    """The raw ``w:date`` attribute values, in document order."""
    return [c.date for c in changes]


def assert_changes_have_expected_author(
    changes: Iterable[TrackedChange],
    *,
    expected: str = EXPECTED_AUTHOR,
) -> None:
    """Raise ``AssertionError`` if any change's author != expected.

    Exposed as a separate helper so the e2e test's failure
    message can name the specific mis-attributed change,
    rather than the generic "wrong author" a list-comprehension
    check would produce.
    """
    for c in changes:
        if c.author != expected:
            raise AssertionError(
                f"tracked change id={c.change_id!r} has author {c.author!r}, "
                f"expected {expected!r}"
            )


def assert_all_dates_valid(changes: Iterable[TrackedChange]) -> None:
    """Raise ``AssertionError`` if any change's ``w:date`` is not ISO-8601."""
    for c in changes:
        if not c.date:
            raise AssertionError(
                f"tracked change id={c.change_id!r} is missing the w:date attribute"
            )
        if not is_valid_iso8601(c.date):
            raise AssertionError(
                f"tracked change id={c.change_id!r} has invalid w:date {c.date!r} "
                f"(expected ISO-8601 UTC)"
            )


__all__ = [
    "EXPECTED_AUTHOR",
    "TrackedChange",
    "is_valid_iso8601",
    "load_document",
    "iter_tracked_changes",
    "count_insertions",
    "count_deletions",
    "extract_change_authors",
    "extract_change_dates",
    "assert_changes_have_expected_author",
    "assert_all_dates_valid",
]
