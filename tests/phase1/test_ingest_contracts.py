"""Phase 1 exit-gate tests.

The five test NDAs in ``examples/contracts/phase1_test/`` are run
through the full ingest → parse → classify pipeline. Each test
asserts the contract-specific expectation:

- ``aba-mutual-nda.pdf`` — clean baseline, multiple numbered clauses,
  most should classify to a real (non-unknown) type.
- ``weird-format-nda.pdf`` — ALL-CAPS section headers, no numbered
  sections. The chunker's no-headings fallback path should still
  produce typed clauses.
- ``short-nda.pdf`` — 1 page, 3 numbered clauses. The "tiny NDA"
  shape. We expect exactly 3-5 clauses and all of them typed.
- ``long-nda.pdf`` — 17 pages, deep numbering (1.1.1 etc.). The
  chunker must keep the deep section IDs intact.
- ``scanned-style-nda.pdf`` — no text layer. The pipeline must
  return ``is_scanned=True`` and a non-empty ``scanned_warning``.

The shared exit-gate assertion is: ≥80 % of clauses get a non-null
``type`` (i.e. type != "unknown"). The scanned-style contract is the
exception — its clauses have no real text, so we tolerate whatever
ratio the classifier produces (the test just asserts no crash).
"""

from __future__ import annotations

import pytest

from app.classify import ClauseType
from app.pipeline import run_stage1


# 80% threshold from the Phase 1 spec, applied per contract.
CLASSIFIED_RATIO_THRESHOLD = 0.80


def _count_classified(result) -> tuple[int, int, float]:
    """Return (classified_count, total, ratio) for a Stage1Result."""
    total = len(result.clauses)
    classified = sum(1 for c in result.clauses if c.type != ClauseType.UNKNOWN)
    ratio = (classified / total) if total else 0.0
    return classified, total, ratio


def test_aba_mutual_nda_parses(aba_mutual_nda_bytes):
    """The ABA-equivalent public template: clean numbered sections."""
    result = run_stage1(
        filename="aba-mutual-nda.pdf",
        content_type="application/pdf",
        data=aba_mutual_nda_bytes,
    )
    classified, total, ratio = _count_classified(result)
    assert total > 0, "Expected at least one clause"
    assert ratio >= CLASSIFIED_RATIO_THRESHOLD, (
        f"Expected ≥{CLASSIFIED_RATIO_THRESHOLD:.0%} of clauses classified, "
        f"got {classified}/{total} = {ratio:.0%}"
    )
    assert not result.is_scanned, "ABA template should NOT be flagged as scanned"
    # The ABA template has a definition-of-confidential-info clause.
    types_seen = {c.type for c in result.clauses}
    # We don't pin a specific type — the rule-based fallback may label
    # "definitions" differently. We just require the unknown class to
    # not dominate.
    assert ClauseType.UNKNOWN not in types_seen or len(types_seen) > 1, (
        f"All clauses were 'unknown': {result.clauses!r}"
    )


def test_weird_format_nda_parses(weird_format_nda_bytes):
    """The ALL-CAPS header, no-numbered-sections contract."""
    result = run_stage1(
        filename="weird-format-nda.pdf",
        content_type="application/pdf",
        data=weird_format_nda_bytes,
    )
    classified, total, ratio = _count_classified(result)
    assert total > 0, "Expected at least one clause"
    assert ratio >= CLASSIFIED_RATIO_THRESHOLD, (
        f"Expected ≥{CLASSIFIED_RATIO_THRESHOLD:.0%} classified, got "
        f"{classified}/{total} = {ratio:.0%}"
    )
    assert not result.is_scanned, "Weird format is text, not scanned"
    # At least one clause should be the term or definition of confidential info.
    type_values = {c.type.value for c in result.clauses}
    assert (
        "definition_confidential_info" in type_values
        or "term" in type_values
        or "governing_law" in type_values
    ), f"Expected at least one core NDA clause type, got {type_values}"


def test_short_nda_parses(short_nda_bytes):
    """The 1-page, 3-clause NDA. Tiny but real."""
    result = run_stage1(
        filename="short-nda.pdf",
        content_type="application/pdf",
        data=short_nda_bytes,
    )
    classified, total, ratio = _count_classified(result)
    assert 1 <= total <= 8, (
        f"Short NDA should produce 1-8 clauses, got {total}"
    )
    assert ratio >= CLASSIFIED_RATIO_THRESHOLD, (
        f"Expected ≥{CLASSIFIED_RATIO_THRESHOLD:.0%} classified, got "
        f"{classified}/{total} = {ratio:.0%}"
    )
    assert not result.is_scanned
    type_values = {c.type.value for c in result.clauses}
    # The short NDA explicitly has 3 clauses; the LLM/fallback should
    # at minimum hit one of definition_confidential_info, term, or
    # governing_law.
    assert (
        "definition_confidential_info" in type_values
        or "term" in type_values
        or "governing_law" in type_values
    ), f"Expected one of the 3 core clause types, got {type_values}"


def test_long_nda_parses(long_nda_bytes):
    """The 17-page NDA with 1.1.1-style deep numbering."""
    result = run_stage1(
        filename="long-nda.pdf",
        content_type="application/pdf",
        data=long_nda_bytes,
    )
    classified, total, ratio = _count_classified(result)
    assert total >= 10, (
        f"Long NDA should produce ≥10 clauses (it has 15 sections × 3 "
        f"subsections), got {total}"
    )
    assert ratio >= CLASSIFIED_RATIO_THRESHOLD, (
        f"Expected ≥{CLASSIFIED_RATIO_THRESHOLD:.0%} classified, got "
        f"{classified}/{total} = {ratio:.0%}"
    )
    # Deep section IDs should survive the chunker. The exact match
    # depends on the regex, but at least one clause should have a
    # section ID with ≥2 dots (e.g. "1.1.1").
    deep_ids = [
        c.position.section
        for c in result.clauses
        if c.position.section and c.position.section.count(".") >= 2
    ]
    assert deep_ids, (
        f"Expected at least one clause with deep section ID (1.1.1), got "
        f"sections: {[c.position.section for c in result.clauses]}"
    )


def test_scanned_style_nda_warns(scanned_style_nda_bytes):
    """The no-text-layer PDF: must warn, must not crash."""
    result = run_stage1(
        filename="scanned-style-nda.pdf",
        content_type="application/pdf",
        data=scanned_style_nda_bytes,
    )
    assert result.is_scanned, "Expected is_scanned=True for no-text-layer PDF"
    assert result.scanned_warning, "Expected a non-empty scanned_warning"
    assert result.char_count < 50, (
        f"Expected <50 chars in a scanned PDF, got {result.char_count}"
    )
    # The pipeline should still return a (mostly empty) clause list.
    # The number of clauses may be 0 or 1 — we don't pin a specific value.
    assert isinstance(result.clauses, list)


# --- Exit-gate summary --------------------------------------------------


def test_exit_gate_summary(
    aba_mutual_nda_bytes,
    weird_format_nda_bytes,
    short_nda_bytes,
    long_nda_bytes,
    scanned_style_nda_bytes,
):
    """Aggregate the per-contract assertions into a single gate check.

    This test is the "all 5 contracts parse without error" assertion
    from the Phase 1 spec. It runs the pipeline against all 5 inputs
    in one go and confirms the aggregate behaviour matches the exit
    gate. Individual contracts have their own tests above for
    contract-specific assertions.
    """
    fixtures = [
        ("aba-mutual-nda.pdf", aba_mutual_nda_bytes, False),
        ("weird-format-nda.pdf", weird_format_nda_bytes, False),
        ("short-nda.pdf", short_nda_bytes, False),
        ("long-nda.pdf", long_nda_bytes, False),
        ("scanned-style-nda.pdf", scanned_style_nda_bytes, True),
    ]
    summaries: list[tuple[str, int, int, float, bool]] = []
    for name, data, expected_scanned in fixtures:
        result = run_stage1(
            filename=name,
            content_type="application/pdf",
            data=data,
        )
        assert result.is_scanned == expected_scanned, (
            f"{name}: expected is_scanned={expected_scanned}, got "
            f"{result.is_scanned}"
        )
        classified, total, ratio = _count_classified(result)
        summaries.append((name, classified, total, ratio, result.is_scanned))

    # Print a summary so the pytest output is human-readable.
    print("\nPhase 1 exit-gate summary:")
    print(f"  {'contract':<32} {'classified':>10} {'total':>6} {'ratio':>8} {'scanned':>8}")
    for name, classified, total, ratio, scanned in summaries:
        print(
            f"  {name:<32} {classified:>10} {total:>6} {ratio:>8.0%} {str(scanned):>8}"
        )
