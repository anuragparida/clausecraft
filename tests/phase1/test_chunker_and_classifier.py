"""Unit tests for the chunker and the rule-based classifier fallback.

The contract tests in ``test_ingest_contracts.py`` exercise the full
pipeline. These tests target the chunker and classifier in isolation
so a regression in either can be localised quickly.
"""

from __future__ import annotations

import pytest

from app.classify import ClauseType, classify_clause
from app.classify.classifier import _rule_based_classify
from app.parse import chunk_text, looks_like_heading
from app.parse.heuristics import HeadingMatch


# --- Chunker tests ------------------------------------------------------


def test_chunker_handles_numbered_sections():
    """The classic NDA shape: '1. Confidentiality', '2. Term', etc."""
    text = (
        "MUTUAL NDA\n"
        "\n"
        "1. Confidentiality. Confidential Information means any non-public "
        "information disclosed by one party to the other.\n"
        "\n"
        "2. Term. This Agreement shall remain in effect for three (3) years.\n"
        "\n"
        "3. Governing Law. This Agreement shall be governed by the laws of "
        "the State of New York.\n"
    )
    clauses = chunk_text(text)
    assert len(clauses) == 3, f"Expected 3 clauses, got {len(clauses)}: {clauses}"
    # Sections should be detected.
    assert clauses[0].section == "1"
    assert clauses[1].section == "2"
    assert clauses[2].section == "3"


def test_chunker_handles_allcaps_headers():
    """Weird-format: ALL-CAPS section headers, no numbers."""
    text = (
        "AGREEMENT\n"
        "\n"
        "CONFIDENTIALITY.\n"
        "Confidential Information means any non-public information.\n"
        "\n"
        "TERM.\n"
        "This Agreement shall remain in effect for two (2) years.\n"
    )
    clauses = chunk_text(text)
    assert len(clauses) == 2
    assert clauses[0].section.startswith("ALL_CAPS:")
    assert "CONFIDENTIALITY" in clauses[0].section


def test_chunker_handles_no_headings_short():
    """A short contract with no detectable headings falls back to per-paragraph."""
    text = (
        "NDA between Acme and Beta.\n"
        "\n"
        "Confidential Information means any non-public information.\n"
        "\n"
        "This Agreement is governed by Delaware law.\n"
    )
    clauses = chunk_text(text)
    # The first paragraph is a short preamble (skipped), the next two
    # are the body — we expect 2 real clauses.
    assert len(clauses) == 2
    for c in clauses:
        assert c.section == ""


def test_chunker_preserves_deep_section_ids():
    """Deep section IDs (1.1.1) survive the chunker."""
    text = (
        "1.1.1 This sub-subsection is the deepest level.\n"
        "\n"
        "1.1.2 Another deep sub-subsection follows.\n"
    )
    clauses = chunk_text(text)
    assert len(clauses) >= 1
    # At least one clause should carry a deep section ID.
    sections = [c.section for c in clauses]
    assert any("." in s for s in sections), f"No dotted sections in {sections}"


def test_looks_like_heading_numbered():
    h = looks_like_heading("1. Confidentiality")
    assert h is not None
    assert h.section_id == "1"
    assert h.level == 1


def test_looks_like_heading_section_kw():
    h = looks_like_heading("Section 5. Notices")
    assert h is not None
    assert h.section_id == "5"


def test_looks_like_heading_article_kw():
    h = looks_like_heading("ARTICLE I. PURPOSE")
    assert h is not None
    assert h.section_id == "I"
    assert h.level == 1


def test_looks_like_heading_allcaps():
    h = looks_like_heading("CONFIDENTIALITY.")
    assert h is not None
    assert h.section_id.startswith("ALL_CAPS:")


def test_looks_like_heading_negative():
    # A regular body paragraph should not match.
    assert looks_like_heading("The receiving party shall hold all confidential information in strict confidence.") is None


# --- Rule-based classifier fallback tests ------------------------------


@pytest.mark.parametrize(
    "text, expected_type",
    [
        (
            "Confidential Information means any non-public information "
            "disclosed by one party to the other.",
            ClauseType.DEFINITION_CONFIDENTIAL_INFO,
        ),
        (
            "This Agreement shall be governed by the laws of the State of "
            "New York.",
            ClauseType.GOVERNING_LAW,
        ),
        (
            "This Agreement shall remain in effect for a period of three "
            "(3) years from the Effective Date.",
            ClauseType.TERM,
        ),
        (
            "Upon termination, each party shall return or destroy all "
            "Confidential Information in its possession.",
            ClauseType.RETURN_OF_MATERIALS,
        ),
        (
            "This Agreement constitutes the entire agreement between the "
            "parties and supersedes all prior agreements.",
            ClauseType.ENTIRE_AGREEMENT,
        ),
        (
            "For a period of twelve months, neither party shall solicit the "
            "other party's employees.",
            ClauseType.NON_SOLICIT,
        ),
        (
            "The parties acknowledge that monetary damages may be inadequate "
            "and that injunctive relief shall be available.",
            ClauseType.INJUNCTIVE_RELIEF,
        ),
        (
            "Nothing herein shall restrict the use of residual knowledge "
            "retained in the memory of personnel.",
            ClauseType.RESIDUAL_KNOWLEDGE,
        ),
        (
            "Neither party may assign this Agreement without the prior "
            "written consent of the other party.",
            ClauseType.ASSIGNMENT,
        ),
    ],
)
def test_rule_based_classify_keywords(text, expected_type):
    ctype, conf = _rule_based_classify(text)
    assert ctype == expected_type, (
        f"Expected {expected_type.value}, got {ctype.value} for: {text[:60]}"
    )
    assert conf > 0.0


def test_rule_based_classify_unknown_fallback():
    """A clause with no matching keywords falls back to 'unknown'."""
    ctype, conf = _rule_based_classify(
        "The quick brown fox jumps over the lazy dog."
    )
    assert ctype == ClauseType.UNKNOWN
    assert conf == 0.0


def test_classify_clause_uses_fallback_with_placeholder_key(monkeypatch):
    """When LLM_API_KEY is a placeholder, classify_clause uses the rule-based path."""
    from app import config

    monkeypatch.setattr(config.settings, "llm_api_key", "placeholder-not-a-real-key")
    clause = classify_clause(
        raw_id="c1",
        raw_text=(
            "Confidential Information means any non-public information "
            "disclosed by one party to the other."
        ),
        section="1",
        section_title="Confidentiality",
        paragraph_index=[0],
        contract_filename="synthetic.pdf",
    )
    assert clause.type == ClauseType.DEFINITION_CONFIDENTIAL_INFO
    assert clause.confidence > 0.0
    assert clause.id == "c1"
    assert clause.position.section == "1"
    assert clause.language == "en"
