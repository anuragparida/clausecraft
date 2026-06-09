"""Test the counterparty matrix loader (flat lookup, Phase 2) + Phase 4 DE column."""

from __future__ import annotations

from app.playbook import (
    CounterpartyMatrix,
    MatrixVerdict,
    Verdict,
    load_matrix,
    lookup_verdict,
    lookup_verdict_with_language,
)


def test_load_real_matrix():
    """The committed counterparty_matrix.yaml parses into a typed matrix."""
    m = load_matrix()
    assert isinstance(m, CounterpartyMatrix)
    assert m.contract_type == "nda"
    assert m.language == "en"
    # Bumped to 0.1.0-de with the Phase 4 DE column addition.
    assert m.version == "0.1.0-de"
    # All 15 Phase 1 + the unknown clause type are listed.
    assert "definition_confidential_info" in m.clause_verdicts
    assert "term" in m.clause_verdicts
    assert "residual_knowledge" in m.clause_verdicts
    assert "governing_law" in m.clause_verdicts
    assert "injunctive_relief" in m.clause_verdicts
    assert "unknown" in m.clause_verdicts
    # Every committed value is "aligned" in Phase 2.
    for verdict in m.clause_verdicts.values():
        assert verdict == Verdict.ALIGNED


def test_default_verdict_fallback():
    """Unknown clause types fall back to the default verdict."""
    # The YAML has every known type listed, so construct a fresh
    # matrix with a missing override to test the fallback path.
    m2 = CounterpartyMatrix(
        version="0.0.0-dev",
        contract_type="nda",
        language="en",
        default_counterparty_type="any",
        default_verdict=Verdict.MATERIAL,
        clause_verdicts={"term": Verdict.MINOR},
        counterparty_overrides={},
        language_overrides={},
        raw={},
    )
    v_known = lookup_verdict(m2, "term")
    assert v_known.verdict == Verdict.MINOR
    assert v_known.is_default is False
    v_unknown = lookup_verdict(m2, "non_existent_clause_type")
    assert v_unknown.verdict == Verdict.MATERIAL
    assert v_unknown.is_default is True


def test_verdict_from_score():
    """Verdict.from_score coerces the spotter's 0-3 score into a verdict."""
    assert Verdict.from_score(0) == Verdict.ALIGNED
    assert Verdict.from_score(1) == Verdict.MINOR
    assert Verdict.from_score(2) == Verdict.MATERIAL
    assert Verdict.from_score(3) == Verdict.UNACCEPTABLE
    # Clamping: out-of-range is a no-op, not a crash.
    assert Verdict.from_score(-1) == Verdict.ALIGNED
    assert Verdict.from_score(99) == Verdict.UNACCEPTABLE


def test_matrix_verdict_typed():
    """MatrixVerdict is a proper dataclass with the expected fields."""
    v = MatrixVerdict(
        verdict=Verdict.ALIGNED,
        clause_type="term",
        counterparty_type="any",
        is_default=False,
    )
    assert v.verdict.label() == "aligned"
    assert v.counterparty_type == "any"


def test_matrix_ignores_unknown_top_level_keys():
    """Unknown top-level keys (Phase 5 forward-compat) are silently ignored."""
    raw = {
        "version": "9.9.9-test",
        "contract_type": "nda",
        "language": "en",
        "default_counterparty_type": "any",
        "default_verdict": "aligned",
        "clause_verdicts": {"term": "aligned"},
        "counterparty_overrides": {},
        # Future fields Phase 5 may add:
        "risk_weights": {"term": 0.5},
        "jurisdiction_overrides": {},
    }
    m = CounterpartyMatrix.from_dict(raw)
    assert m.version == "9.9.9-test"
    assert m.clause_verdicts["term"] == Verdict.ALIGNED


# --- Phase 4: DE column --------------------------------------------------
#
# The DE column is additive: existing EN lookups must stay green
# (the ``test_load_real_matrix`` and ``test_default_verdict_fallback``
# tests above already exercise that), and the DE override must
# apply *only* when (a) the language is "de" and (b) the configured
# counterparty type matches and (c) the override is at least as
# strict as the EN verdict (we never relax a verdict on a language
# switch — defensive against an accidentally-inverted YAML value).


def test_de_column_loaded_from_yaml():
    """The committed counterparty_matrix.yaml carries a DE column.

    Acceptance: ``playbook/counterparty_matrix.yaml`` has a DE
    column (or DE override block). The loader exposes it on
    ``CounterpartyMatrix.language_overrides["de"]``.
    """
    m = load_matrix()
    assert "de" in m.language_overrides
    # The Phase 4 strictest additions: governing_law,
    # limitation_of_liability, term — all for the
    # ``de_german_entity`` counterparty type.
    de_block = m.language_overrides["de"]
    assert "de_german_entity" in de_block
    de_german = de_block["de_german_entity"]
    assert de_german["governing_law"] == Verdict.MATERIAL
    assert de_german["limitation_of_liability"] == Verdict.MATERIAL
    assert de_german["term"] == Verdict.MATERIAL


def test_de_lookup_strictens_governing_law_for_german_counterparty():
    """DE override applies for DE counterparty type on configured clauses."""
    m = load_matrix()
    # EN baseline: aligned.
    v_en = lookup_verdict(m, "governing_law")
    assert v_en.verdict == Verdict.ALIGNED
    # DE + de_german_entity: stricter (material).
    v_de = lookup_verdict_with_language(
        m, "governing_law", language="de", counterparty_type="de_german_entity"
    )
    assert v_de.verdict == Verdict.MATERIAL
    assert v_de.language == "de"
    assert v_de.counterparty_type == "de_german_entity"


def test_de_lookup_falls_back_to_en_for_non_de_counterparty():
    """DE override does NOT apply for non-DE counterparty types."""
    m = load_matrix()
    # DE language but counterparty is not German.
    v = lookup_verdict_with_language(
        m, "governing_law", language="de", counterparty_type="us_enterprise"
    )
    # No override applies — the EN default (aligned) wins.
    assert v.verdict == Verdict.ALIGNED
    assert v.language == "de"


def test_de_lookup_only_narrows_never_relaxes():
    """The DE override is rejected if it would *relax* the EN verdict.

    Defensive against an accidentally-inverted YAML value
    (e.g. ``aligned`` where ``material`` was meant) — the lookup
    stays at the EN verdict. The language stamp on the result is
    still ``"de"`` so the caller knows a DE lookup was attempted.
    """
    m = CounterpartyMatrix(
        version="0.0.0-test",
        contract_type="nda",
        language="en",
        default_counterparty_type="any",
        default_verdict=Verdict.ALIGNED,
        clause_verdicts={"governing_law": Verdict.MATERIAL},
        counterparty_overrides={},
        # DE override tries to *relax* material → aligned.
        # The lookup should reject it.
        language_overrides={
            "de": {
                "de_german_entity": {
                    "governing_law": Verdict.ALIGNED,
                }
            }
        },
        raw={},
    )
    v = lookup_verdict_with_language(
        m,
        "governing_law",
        language="de",
        counterparty_type="de_german_entity",
    )
    assert v.verdict == Verdict.MATERIAL  # the EN default, not the relaxation
    assert v.language == "de"


def test_de_lookup_unknown_clause_falls_back_to_default():
    """Unknown clause type in DE lookup → matrix default verdict."""
    m = load_matrix()
    v = lookup_verdict_with_language(
        m,
        "non_existent_clause_type",
        language="de",
        counterparty_type="de_german_entity",
    )
    assert v.verdict == Verdict.ALIGNED  # the matrix default
    assert v.is_default is True
    assert v.language == "de"


def test_unknown_language_falls_through_to_en_path():
    """A language code with no overrides falls through to the EN path."""
    m = load_matrix()
    v_en = lookup_verdict(m, "term")
    v_xx = lookup_verdict_with_language(
        m, "term", language="xx", counterparty_type="de_german_entity"
    )
    # ``xx`` has no overrides, so the EN result wins.
    assert v_xx.verdict == v_en.verdict
    assert v_xx.language == "xx"


def test_de_lookup_does_not_mutate_existing_en_lookup():
    """The EN ``lookup_verdict`` is unchanged in behavior.

    The Phase 4 addition must not break the Phase 2 path —
    this is the acceptance criterion that the existing tests
    also exercise, but we make it explicit here.
    """
    m = load_matrix()
    # The DE column is loaded; lookup_verdict should still ignore it.
    assert m.language_overrides  # non-empty after Phase 4
    v = lookup_verdict(m, "governing_law", counterparty_type="de_german_entity")
    # Even with a DE counterparty type, lookup_verdict returns the
    # EN default. The DE column is only consulted by
    # lookup_verdict_with_language.
    assert v.verdict == Verdict.ALIGNED


def test_de_lookup_inherits_matrix_language_default():
    """Omitting ``language=`` defaults to the matrix's language field."""
    m = load_matrix()
    # The committed YAML has language: "en" at the top level.
    # Omitting language= in the call should default to "en" and
    # hit the EN path, not the DE path.
    v = lookup_verdict_with_language(m, "governing_law")
    assert v.verdict == Verdict.ALIGNED
    assert v.language == "en"


def test_de_lookup_alternate_yaml_shape_parses():
    """The flat ``language → counterparty_type → clause_type`` shape
    also parses (the canonical shape is nested under
    ``counterparty_overrides`` per language, but a direct 2D
    shape is also accepted as a forward-compat)."""
    raw = {
        "version": "0.1.0-test",
        "contract_type": "nda",
        "language": "en",
        "default_counterparty_type": "any",
        "default_verdict": "aligned",
        "clause_verdicts": {"governing_law": "aligned"},
        "counterparty_overrides": {},
        "language_overrides": {
            "de": {
                # Flat shape — no nested counterparty_overrides.
                "de_german_entity": {
                    "governing_law": "unacceptable",
                }
            }
        },
    }
    m = CounterpartyMatrix.from_dict(raw)
    assert m.language_overrides["de"]["de_german_entity"]["governing_law"] == (
        Verdict.UNACCEPTABLE
    )
    v = lookup_verdict_with_language(
        m, "governing_law", language="de", counterparty_type="de_german_entity"
    )
    assert v.verdict == Verdict.UNACCEPTABLE
