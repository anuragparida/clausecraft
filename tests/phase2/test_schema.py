"""Test the playbook schema (YAML parsing + Pydantic validation)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.playbook import BaselineClause, PlaybookBaseline


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINES = REPO_ROOT / "playbook" / "baselines" / "nda-en"


def test_baseline_dir_has_five_files():
    """The committed EN NDA baselines are exactly the 5 the spec calls for."""
    files = sorted(p.name for p in BASELINES.glob("*.yaml"))
    assert files == [
        "definition_confidential_info.yaml",
        "governing_law.yaml",
        "injunctive_relief.yaml",
        "residual_knowledge.yaml",
        "term.yaml",
    ]


@pytest.mark.parametrize(
    "filename,clause_id,clause_type",
    [
        ("definition_confidential_info.yaml", "definition-of-confidential-information", "definition_confidential_info"),
        ("term.yaml", "term-of-confidentiality", "term"),
        ("residual_knowledge.yaml", "residual-knowledge", "residual_knowledge"),
        ("governing_law.yaml", "governing-law", "governing_law"),
        ("injunctive_relief.yaml", "injunctive-relief", "injunctive_relief"),
    ],
)
def test_each_baseline_parses_and_validates(
    filename: str, clause_id: str, clause_type: str
):
    """Each baseline YAML parses, has provenance, and matches a ClauseType."""
    p = BASELINES / filename
    assert p.exists(), f"missing baseline: {p}"
    b = PlaybookBaseline.from_yaml(str(p))
    assert len(b.clauses) == 1
    c = b.clauses[0]
    assert c.clause_id == clause_id
    assert c.type == clause_type
    assert c.language == "en"
    # Provenance required by the spec — every baseline has it.
    assert c.source_url.startswith("http")
    assert isinstance(c.retrieval_date, date)
    assert c.license  # non-empty
    # The text body is non-trivial (>= 50 chars).
    assert len(c.text) >= 50


def test_invalid_clause_type_rejected():
    """A baseline with a non-enum type is rejected at parse time."""
    with pytest.raises(ValueError, match="lowercase snake_case"):
        BaselineClause(
            clause_id="x",
            type="InvalidType",  # not lowercase snake_case
            language="en",
            title="t",
            text="body",
            source_url="https://example.com",
            retrieval_date=date(2026, 1, 1),
            license="x",
        )


def test_missing_source_url_rejected():
    """Provenance is required. Empty source_url fails validation."""
    with pytest.raises(ValueError):
        BaselineClause(
            clause_id="x",
            type="term",
            language="en",
            title="t",
            text="body",
            source_url="",
            retrieval_date=date(2026, 1, 1),
            license="x",
        )


def test_top_level_mapping_parses_as_single_clause():
    """A bare mapping (not wrapped in ``clauses:``) parses as a one-clause file."""
    # The committed files use the bare-mapping shape. Verify it works.
    p = BASELINES / "term.yaml"
    b = PlaybookBaseline.from_yaml(str(p))
    assert len(b.clauses) == 1
    assert b.clauses[0].clause_id == "term-of-confidentiality"
