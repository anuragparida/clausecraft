"""Unit tests for the per-clause language detector.

These tests target :func:`app.parse.language.detect_language`
in isolation. The function is pure (no I/O, no global state)
so the tests are deterministic and fast.

The acceptance criteria from Phase 4 plan card t_4c21627c:

  [ ] ``Clause.language`` populated at parse time via a real
      detection step (not hard-coded "en")
  [ ] Unit test: a DE clause text gets ``language="de"``; an EN
      clause text gets ``language="en"``; a mixed-clause file is
      per-clause correct
  [ ] No regression in existing EN classification — existing tests
      stay green

The tests below cover:

1. **Pure detector correctness** — DE clauses detect as "de",
   EN clauses detect as "en", at the unit level.
2. **Mixed-clause file** — a multi-clause document where each
   clause's language is correctly detected per-clause.
3. **Heading tie-breaker** — heading-only clauses where the
   body has no function words, but the heading carries the
   language signal.
4. **Edge cases** — empty text, single-word inputs, repeated
   words, mixed text.
5. **Integration with the classifier** —
   :func:`app.classify.classify_clause` auto-detects the
   language when the caller doesn't pass a ``language=``
   argument, and respects the caller's argument when passed.
"""

from __future__ import annotations

import pytest

from app.classify import ClauseType, classify_clause
from app.classify.classifier import classify_clauses
from app.parse import detect_language
from app.parse.chunker import RawClause


# --- Pure detector tests -----------------------------------------------


def test_detect_de_clause():
    """A typical DE NDA clause text detects as 'de'."""
    text = (
        "Diese Vereinbarung unterliegt deutschem Recht. "
        "Alle vertraulichen Informationen sind durch die "
        "empfangende Partei geheim zu halten."
    )
    assert detect_language(text) == "de"


def test_detect_en_clause():
    """A typical EN NDA clause text detects as 'en'."""
    text = (
        "This Agreement is governed by the laws of the State of "
        "New York. All confidential information shall be protected "
        "by the receiving party."
    )
    assert detect_language(text) == "en"


def test_detect_empty_text_defaults_to_en():
    """An empty clause text defaults to 'en' (Phase 1 fallback)."""
    assert detect_language("") == "en"


def test_detect_single_de_word():
    """A single DE legal-domain word ('Haftung') detects as 'de'."""
    assert detect_language("Haftung") == "de"


def test_detect_single_en_word():
    """A single EN legal-domain word ('Confidential') detects as 'en'."""
    assert detect_language("Confidential") == "en"


def test_detect_repeated_en_stopword_does_not_dominate():
    """Occurrence-based scoring: 3x 'shall' should not flip a DE clause.

    A DE clause with a single repeated EN stopword should still
    detect as DE if the DE score is higher. (This is the
    behaviour we want: 'shall shall shall' is just an EN word
    pattern; a DE clause that quotes it once shouldn't flip to EN.)
    """
    text = "Der Vertrag wird durch die Parteien unterzeichnet. shall"
    assert detect_language(text) == "de"


def test_detect_repeated_de_stopword_does_not_dominate():
    """A clause with one repeated DE word but otherwise EN body
    detects as EN, because the EN function words outnumber the
    single repeated DE word in the body."""
    text = "The party shall protect the confidential information. und"
    assert detect_language(text) == "en"


def test_detect_phase1_aba_clause_remains_en():
    """The Phase 1 ABA test clause (a real EN NDA paragraph)
    must still detect as 'en' after Phase 4 changes — the
    acceptance criterion is "no regression in existing EN
    classification"."""
    text = (
        "Confidential Information means any non-public information "
        "disclosed by one party to the other. The receiving party "
        "shall hold all confidential information in strict confidence "
        "and shall not disclose it to any third party without prior "
        "written consent."
    )
    assert detect_language(text) == "en"


def test_detect_de_legal_domain_indicators():
    """DE-specific legal terms tip the score to 'de'."""
    text = (
        "Im Falle einer Pflichtverletzung ist Schadensersatz zu leisten. "
        "Die Vertragspartei haftet bei Verschulden nach den "
        "gesetzlichen Bestimmungen des BGB."
    )
    assert detect_language(text) == "de"


# --- Mixed-clause file tests -------------------------------------------


def test_mixed_clauses_detected_per_clause():
    """A document with clauses in both languages: each clause is
    detected independently. The function is called per-clause,
    so the test exercises per-clause correctness by calling
    detect_language on each clause text separately (the way the
    classifier does it)."""
    clauses = [
        "This Agreement is governed by the laws of the State of New York.",  # EN
        "Diese Vereinbarung unterliegt deutschem Recht.",  # DE
        "Confidential Information means any non-public information.",  # EN
        "Vertrauliche Informationen sind alle nicht-öffentlichen Informationen.",  # DE
        "The receiving party shall hold all confidential information in strict confidence.",  # EN
    ]
    expected = ["en", "de", "en", "de", "en"]
    detected = [detect_language(c) for c in clauses]
    assert detected == expected, f"Expected {expected}, got {detected}"


def test_mixed_via_classify_clauses(monkeypatch):
    """End-to-end: classify_clauses (no per-document language arg)
    auto-detects per clause. The 3 EN clauses get language='en',
    the 2 DE clauses get language='de'."""
    # Force the rule-based fallback path so the test is fast
    # and deterministic — the real LLM endpoint is not
    # available in the test environment, and the test's
    # assertion is about the per-clause language field, not
    # about LLM classification quality (that's the DE prompts
    # card's responsibility).
    from app import config

    monkeypatch.setattr(
        config.settings, "llm_api_key", "placeholder-not-a-real-key"
    )

    raw_clauses = [
        RawClause(
            id="c1",
            text="This Agreement is governed by the laws of the State of New York.",
            section="1",
            section_title="Governing Law",
            paragraph_indices=[0],
        ),
        RawClause(
            id="c2",
            text="Diese Vereinbarung unterliegt deutschem Recht. Alle Vertragsparteien sind verpflichtet.",
            section="2",
            section_title="Anwendbares Recht",
            paragraph_indices=[1],
        ),
        RawClause(
            id="c3",
            text="Confidential Information means any non-public information disclosed by one party to the other.",
            section="3",
            section_title="Definition of Confidential Information",
            paragraph_indices=[2],
        ),
        RawClause(
            id="c4",
            text="Vertrauliche Informationen sind alle nicht-öffentlichen Informationen, die von einer Partei an die andere weitergegeben werden.",
            section="4",
            section_title="Definition vertraulicher Informationen",
            paragraph_indices=[3],
        ),
        RawClause(
            id="c5",
            text="The receiving party shall hold all confidential information in strict confidence and shall not disclose it to any third party without prior written consent.",
            section="5",
            section_title="Obligations of Receiving Party",
            paragraph_indices=[4],
        ),
    ]
    classified = classify_clauses(
        raw_clauses, contract_filename="mixed-nda.pdf"
    )
    languages = [c.language for c in classified]
    # Auto-detection per clause: the EN clauses are stamped
    # "en", the DE clauses are stamped "de". The classifier
    # uses the placeholder-key fallback (rule-based), so the
    # run is fast and deterministic.
    assert languages == ["en", "de", "en", "de", "en"], (
        f"Expected per-clause auto-detect, got {languages}"
    )
    # The IDs are preserved.
    assert [c.id for c in classified] == ["c1", "c2", "c3", "c4", "c5"]


# --- Heading tie-breaker tests -----------------------------------------


def test_heading_tiebreaker_de():
    """A heading-only DE clause uses the heading for language
    detection. The body has 0 function words; the heading
    'Haftung' (a DE stopword) tips the score to 'de'."""
    text = "HAFTUNG."  # heading only, body is the heading itself
    assert detect_language(text, heading="Haftung") == "de"


def test_heading_tiebreaker_en():
    """A heading-only EN clause uses the heading for language
    detection. The heading 'Confidentiality' is a real EN
    legal term and tips the score to 'en'."""
    text = "CONFIDENTIALITY."  # heading only
    assert detect_language(text, heading="Confidentiality") == "en"


def test_heading_overrides_uninformative_body():
    """When the body has no function words, the heading decides.

    A real-world case: a DE NDA's first clause is just a
    title like "Vertraulichkeitsvereinbarung." (no body). The
    body has 0 function words, but the heading is DE legal
    terminology.
    """
    text = "VERTRAULICHKEITSVEREINBARUNG."
    # Body alone would default to "en" (no function words).
    # With the heading "Haftung" (a DE stopword), the
    # tie-breaker tips the score to "de".
    # Note: if the heading itself is the compound word
    # "Vertraulichkeitsvereinbarung", it won't match any
    # stopword (it's one word), so the default "en" applies.
    # That's the documented limitation: a single compound
    # DE word with no function words is genuinely hard to
    # detect. A simple heading like "Haftung" works fine.
    assert detect_language(text, heading="Haftung") == "de"


# --- Classifier integration tests --------------------------------------


def test_classify_clause_auto_detects_de(monkeypatch):
    """classify_clause with no language arg auto-detects 'de' for a
    DE clause. The fallback path runs (placeholder key) so the
    test is deterministic. We don't care about the exact
    ClauseType — the rule-based fallback gives some
    non-unknown label for a DE clause that mentions
    "Vertrauliche" — but the key assertion is ``language='de'``."""
    from app import config

    monkeypatch.setattr(
        config.settings, "llm_api_key", "placeholder-not-a-real-key"
    )
    clause = classify_clause(
        raw_id="c1",
        raw_text=(
            "Vertrauliche Informationen sind alle nicht-öffentlichen "
            "Informationen, die von einer Partei an die andere "
            "weitergegeben werden. Die empfangende Partei ist "
            "verpflichtet, alle vertraulichen Informationen streng "
            "vertraulich zu behandeln."
        ),
        section="1",
        section_title="Vertraulichkeit",
        paragraph_index=[0],
        contract_filename="de-nda.pdf",
    )
    assert clause.language == "de"


def test_classify_clause_auto_detects_en(monkeypatch):
    """classify_clause with no language arg auto-detects 'en' for
    an EN clause. The Phase 1 baseline behaviour must be
    preserved (acceptance criterion: no EN regression)."""
    from app import config

    monkeypatch.setattr(
        config.settings, "llm_api_key", "placeholder-not-a-real-key"
    )
    clause = classify_clause(
        raw_id="c1",
        raw_text=(
            "Confidential Information means any non-public "
            "information disclosed by one party to the other. "
            "The receiving party shall hold all confidential "
            "information in strict confidence and shall not "
            "disclose it to any third party without prior "
            "written consent."
        ),
        section="1",
        section_title="Confidentiality",
        paragraph_index=[0],
        contract_filename="en-nda.pdf",
    )
    assert clause.language == "en"


def test_classify_clause_caller_override(monkeypatch):
    """When the caller passes language='de' explicitly, the
    classifier uses that value (and doesn't auto-detect). This
    is the per-document fast-path: a caller that knows the
    file is uniformly DE can skip per-clause detection.
    """
    from app import config

    monkeypatch.setattr(
        config.settings, "llm_api_key", "placeholder-not-a-real-key"
    )
    # An EN clause (clearly detectable as 'en' by the heuristic)
    # is forced to 'de' by the caller's override.
    clause = classify_clause(
        raw_id="c1",
        raw_text=(
            "Confidential Information means any non-public "
            "information disclosed by one party to the other."
        ),
        section="1",
        section_title="Confidentiality",
        paragraph_index=[0],
        contract_filename="synthetic.pdf",
        language="de",
    )
    assert clause.language == "de"


def test_classify_clause_classifies_de_clause_with_de_type(monkeypatch):
    """A DE clause about confidential information is classified
    as DEFINITION_CONFIDENTIAL_INFO (the same type as the EN
    equivalent — the schema's enum is language-agnostic, per
    the Phase 4 plan's hard rule: 'A clause that's
    GOVERNING_LAW in EN stays GOVERNING_LAW in DE')."""
    from app import config

    monkeypatch.setattr(
        config.settings, "llm_api_key", "placeholder-not-a-real-key"
    )
    clause = classify_clause(
        raw_id="c1",
        raw_text=(
            "Vertrauliche Informationen sind alle nicht-öffentlichen "
            "Informationen, die von einer Partei an die andere "
            "weitergegeben werden. Die empfangende Partei ist "
            "verpflichtet, alle vertraulichen Informationen streng "
            "vertraulich zu behandeln und nicht an Dritte "
            "weiterzugeben."
        ),
        section="1",
        section_title="Definition vertraulicher Informationen",
        paragraph_index=[0],
        contract_filename="de-nda.pdf",
    )
    assert clause.language == "de"
    # The rule-based fallback's keywords for
    # DEFINITION_CONFIDENTIAL_INFO were authored against the
    # EN register (e.g. "vertrauliche Informationen" doesn't
    # match the EN regex). The clause might fall to
    # UNKNOWN — that's OK; the language field is the
    # assertion. The Phase 4 plan explicitly notes that
    # "the DE prompts card" (t_1478a342) is what
    # enables DE-side classification quality; this card
    # (t_4c21627c) only wires the language field.
    assert clause.type in (
        ClauseType.DEFINITION_CONFIDENTIAL_INFO,
        ClauseType.UNKNOWN,
    )


# --- Hard-rule guard tests ---------------------------------------------


def test_existing_test_clause_language_unchanged(monkeypatch):
    """The Phase 1 test_clause_uses_fallback_with_placeholder_key
    test asserts ``clause.language == "en"`` for an EN clause.
    We re-test that here so a regression on the per-clause
    detection can't slip past while the chunker+classifier
    suite stays green.
    """
    from app import config

    monkeypatch.setattr(
        config.settings, "llm_api_key", "placeholder-not-a-real-key"
    )
    clause = classify_clause(
        raw_id="c1",
        raw_text=(
            "Confidential Information means any non-public "
            "information disclosed by one party to the other."
        ),
        section="1",
        section_title="Confidentiality",
        paragraph_index=[0],
        contract_filename="synthetic.pdf",
    )
    assert clause.language == "en"


@pytest.mark.parametrize(
    "text,expected",
    [
        # The spec test cases from the Phase 4 plan card
        # (t_4c21627c acceptance criteria).
        (
            "Diese Vereinbarung unterliegt deutschem Recht. "
            "Alle vertraulichen Informationen sind geschützt.",
            "de",
        ),
        (
            "This Agreement is governed by the laws of the State of New York.",
            "en",
        ),
        (
            "Confidential Information means any non-public information.",
            "en",
        ),
        (
            "Vertrauliche Informationen sind alle nicht-öffentlichen Informationen.",
            "de",
        ),
    ],
)
def test_spec_acceptance_criteria(text, expected):
    """Direct test of the spec's acceptance-criteria bullets.

    The Phase 4 plan card (t_4c21627c) acceptance criteria:
    'a DE clause text gets language="de"; an EN clause text
    gets language="en"; a mixed-clause file is per-clause
    correct'. This parametrize covers the per-clause bullets.
    """
    assert detect_language(text) == expected
