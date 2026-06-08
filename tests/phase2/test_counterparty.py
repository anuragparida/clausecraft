"""Test the counterparty matrix loader (flat lookup, Phase 2)."""

from __future__ import annotations

import pytest

from app.playbook import (
    CounterpartyMatrix,
    MatrixVerdict,
    Verdict,
    load_matrix,
    lookup_verdict,
)


def test_load_real_matrix():
    """The committed counterparty_matrix.yaml parses into a typed matrix."""
    m = load_matrix()
    assert isinstance(m, CounterpartyMatrix)
    assert m.contract_type == "nda"
    assert m.language == "en"
    assert m.version == "0.0.0-dev"
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
    m = load_matrix()
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
