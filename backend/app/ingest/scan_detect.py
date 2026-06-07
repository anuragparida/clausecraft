"""Scanned-PDF detection — Phase 1.

A PDF is considered "scanned" when the text layer is empty or near-empty
(no real characters extracted from any page). The exact threshold is
opinionated — we use 50 chars total, which catches true image-only
scans while tolerating tiny metadata noise (PDF version strings,
form-feed artefacts).

The caller decides what to do with a scanned PDF. Phase 1 = warn and
return whatever text we have; OCR is deferred to a later phase.
"""

from __future__ import annotations

from typing import Iterable

# A PDF with fewer than this many extractable characters across all
# pages is treated as scanned. Tuned empirically against the 5 test
# contracts in examples/contracts/phase1_test/.
SCAN_CHAR_THRESHOLD = 50


def is_scanned_pdf(text_chars: Iterable[str]) -> bool:
    """Return True when the extractable text is below the scan threshold.

    Accepts any iterable of single-character strings (the output of
    ``pymupdf.Page.get_text("text")`` joined across pages). Using
    ``len()`` directly on a concatenated string is equivalent, but
    the iterable form lets callers stream pages without buffering.
    """
    total = sum(1 for _ in text_chars)
    return total < SCAN_CHAR_THRESHOLD
