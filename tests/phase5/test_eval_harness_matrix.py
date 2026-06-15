"""Phase 5 v3 — matrix-aware spotter eval-harness integration tests.

Card: ``t_0186cabd`` (Phase 5 v3 — Matrix-aware spotter:
eval harness integration + leaderboard row + matrix_verdict
column).

These unit tests exercise the eval-harness surface that the
matrix-aware spotter landed in Phase 5 v1 (card t_40b61e98)
and v2 (card t_7c0ca277) without running the full pipeline
on a real contract. The full integration is
``test_eval_set_runs_end_to_end`` in ``evals/harness.py``.

What the v3 surface is
----------------------
The matrix verdict column itself is already end-to-end after
v1 + v2: ``DeviationFlag.matrix_verdict`` /
``matrix_sources`` / ``matrix_counterparty_type`` are
populated by ``_stamp_matrix_audit_fields`` in
``backend/app/agents/deviation_spotter/spotter.py``, and the
orchestrator wires the matrix verdict into the spotter's
three paths. v3 is the *eval-harness* side: roll the
per-flag ``matrix_verdict`` values up into:

- per-contract 5-bucket histogram on
  :class:`evals.harness.ContractMetrics` (``matrix_aggregate``)
  + a per-contract ``matrix_verdict_changed_count`` /
  ``matrix_changed`` boolean
- per-subset rollup on
  :func:`evals.harness._aggregate_subset` /
  :func:`evals.harness._build_aggregate_by_language`
- run-wide 5-bucket histogram on
  :class:`evals.harness.RunReport` (``matrix_aggregate``) +
  ``matrix_changed_contracts_count``
- ``evals/leaderboard.csv`` schema v1.1.0 with per-language
  matrix buckets + a run-wide
  ``matrix_changed_contracts_count`` column

Why unit tests, not just the integration test
---------------------------------------------
The integration test runs the full pipeline against the
real eval set. The unit tests here prove the
rollup-to-histogram and changed-count logic in isolation —
the cases that drive the Phase 5 exit-gate signal
(``>= 3 of 30 eval contracts must have a changed verdict``).
A regression in the per-flag rollup would not be caught by
the integration test alone (the integration test's
histogram assertions are weak by design — they assert the
shape, not the values).

Test layout
-----------
1. :class:`TestContractMetricsShape` — the new fields and
   the ``matrix_changed`` property on ``ContractMetrics``.
2. :class:`TestAggregateSubsetMatrix` — the per-subset
   5-bucket histogram rollup + the changed-count rollup.
3. :class:`TestMatrixChangedDetection` — the per-flag
   ``matrix_sources[0] != "flat"`` change detection
   (the exit-gate signal building block).
4. :class:`TestLeaderboardSchemaV110` — the
   ``LEADERBOARD_FIELDS`` schema bump and the per-language
   matrix cell population.
5. :class:`TestWriteRunReportMatrix` — the run-wide
   ``matrix_aggregate`` and
   ``matrix_changed_contracts_count`` on the JSON report.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make ``evals.harness`` importable from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO_ROOT / "evals"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ``evals/conftest.py`` is the eval-harness's own conftest and
# is NOT auto-loaded by pytest when running from the repo root
# (the conftest scopes to its own ``evals/`` pytest.ini). The
# harness module imports are safe without it because
# ``evals/harness.py`` only depends on the backend ``app``
# package, which is added by ``tests/conftest.py``.
from evals.harness import (  # noqa: E402
    LEADERBOARD_FIELDS,
    LEADERBOARD_SCHEMA_VERSION,
    MATRIX_VERDICT_VALUES,  # type: ignore[attr-defined]
    ContractMetrics,
    _aggregate_subset,
    _append_leaderboard_row,
    _build_aggregate_by_language,
    _compute_gap_assertions,
    _write_run_report,
)


# --- Helpers ------------------------------------------------------------


def _make_metrics(
    *,
    contract: str = "examples/contracts/test/nda.pdf",
    language: str = "en",
    contract_type: str = "nda",
    expected_clause_count: int = 5,
    actual_clause_count: int = 5,
    expected_deviation_count: int = 1,
    actual_flag_count: int = 1,
    classification_tp: int = 5,
    classification_fp: int = 0,
    classification_fn: int = 0,
    deviation_tp: int = 1,
    deviation_fp: int = 0,
    deviation_fn: int = 0,
    severity_mismatch_count: int = 0,
    flags_with_citation: int = 1,
    retrieval_f1: float = 1.0,
    matrix_aggregate: dict[str, int] | None = None,
    matrix_verdict_changed_count: int = 0,
) -> ContractMetrics:
    """Build a ``ContractMetrics`` with sensible defaults.

    Defaults produce a perfect score: 5/5 classification,
    1/1 deviation, 1/1 citation, 0 changed. The matrix
    aggregate defaults to the spec's 5-bucket shape
    (4 spec values + ``no_stamp``) all at 0.

    The matrix_aggregate kwarg lets tests directly assert
    the histogram rollup logic without going through the
    flag loop in ``_run_one_contract`` (which requires a
    full pipeline run).
    """
    if flags_with_citation > actual_flag_count:
        flags_with_citation = actual_flag_count
    if matrix_aggregate is None:
        matrix_aggregate = {v: 0 for v in MATRIX_VERDICT_VALUES} | {"no_stamp": 0}
    return ContractMetrics(
        contract=contract,
        contract_type=contract_type,
        language=language,
        expected_clause_count=expected_clause_count,
        actual_clause_count=actual_clause_count,
        expected_deviation_count=expected_deviation_count,
        actual_flag_count=actual_flag_count,
        classification_tp=classification_tp,
        classification_fp=classification_fp,
        classification_fn=classification_fn,
        deviation_tp=deviation_tp,
        deviation_fp=deviation_fp,
        deviation_fn=deviation_fn,
        severity_mismatch_count=severity_mismatch_count,
        flags_with_citation=flags_with_citation,
        retrieval_f1=retrieval_f1,
        matrix_aggregate=matrix_aggregate,
        matrix_verdict_changed_count=matrix_verdict_changed_count,
    )


def _flag(
    *,
    score: int = 1,
    matrix_verdict: str | None = "material",
    matrix_sources: list[str] | None = None,
) -> SimpleNamespace:
    """Build a minimal flag-like object for the per-flag rollup tests.

    Returns a ``SimpleNamespace`` because the rollup loop in
    ``_run_one_contract`` only reads three attributes:
    ``score``, ``matrix_verdict``, and ``matrix_sources``.
    ``DeviationFlag`` requires more fields (clause_id,
    rationale, citation) that are not relevant for the
    histogram logic.
    """
    return SimpleNamespace(
        score=score,
        matrix_verdict=matrix_verdict,
        matrix_sources=matrix_sources,
    )


# --- TestContractMetricsShape ------------------------------------------


class TestContractMetricsShape:
    """The new ``ContractMetrics`` fields exist with the right shape."""

    def test_matrix_aggregate_field_present(self) -> None:
        """The dataclass has a ``matrix_aggregate`` field."""
        names = {f.name for f in dataclass_fields(ContractMetrics)}
        assert "matrix_aggregate" in names, (
            f"ContractMetrics missing matrix_aggregate; got {sorted(names)}"
        )

    def test_matrix_verdict_changed_count_field_present(self) -> None:
        """The dataclass has a ``matrix_verdict_changed_count`` field."""
        names = {f.name for f in dataclass_fields(ContractMetrics)}
        assert "matrix_verdict_changed_count" in names

    def test_default_matrix_aggregate_has_all_five_buckets(self) -> None:
        """A fresh ContractMetrics has all 5 buckets at 0."""
        m = _make_metrics()
        assert set(m.matrix_aggregate.keys()) == {
            "acceptable",
            "material",
            "unacceptable",
            "unverified",
            "no_stamp",
        }
        assert all(v == 0 for v in m.matrix_aggregate.values()), (
            f"Expected all 0 defaults, got {m.matrix_aggregate}"
        )

    def test_default_matrix_verdict_changed_count_is_zero(self) -> None:
        """A fresh ContractMetrics has ``matrix_verdict_changed_count = 0``."""
        m = _make_metrics()
        assert m.matrix_verdict_changed_count == 0

    def test_matrix_changed_false_when_no_changes(self) -> None:
        """``matrix_changed`` is False when ``matrix_verdict_changed_count = 0``."""
        m = _make_metrics(matrix_verdict_changed_count=0)
        assert m.matrix_changed is False

    def test_matrix_changed_true_when_at_least_one_change(self) -> None:
        """``matrix_changed`` is True when ``matrix_verdict_changed_count > 0``."""
        m = _make_metrics(matrix_verdict_changed_count=1)
        assert m.matrix_changed is True


# --- TestAggregateSubsetMatrix -----------------------------------------


class TestAggregateSubsetMatrix:
    """``_aggregate_subset`` rolls up the matrix histogram + changed count."""

    def test_empty_subset_matrix_aggregate_is_well_defined(self) -> None:
        """An empty subset has the spec's 5-bucket histogram at 0."""
        agg = _aggregate_subset([])
        assert set(agg["matrix_aggregate"].keys()) == {
            "acceptable",
            "material",
            "unacceptable",
            "unverified",
            "no_stamp",
        }
        assert all(v == 0 for v in agg["matrix_aggregate"].values())
        assert agg["matrix_verdict_changed_count"] == 0

    def test_subset_rolls_up_matrix_aggregate_across_contracts(self) -> None:
        """The subset histogram sums each contract's bucket values."""
        m1 = _make_metrics(
            matrix_aggregate={
                "acceptable": 1,
                "material": 2,
                "unacceptable": 0,
                "unverified": 0,
                "no_stamp": 0,
            },
        )
        m2 = _make_metrics(
            matrix_aggregate={
                "acceptable": 0,
                "material": 1,
                "unacceptable": 1,
                "unverified": 0,
                "no_stamp": 0,
            },
        )
        agg = _aggregate_subset([m1, m2])
        assert agg["matrix_aggregate"] == {
            "acceptable": 1,
            "material": 3,
            "unacceptable": 1,
            "unverified": 0,
            "no_stamp": 0,
        }

    def test_subset_sums_changed_count(self) -> None:
        """The subset ``matrix_verdict_changed_count`` is the sum."""
        m1 = _make_metrics(matrix_verdict_changed_count=2)
        m2 = _make_metrics(matrix_verdict_changed_count=3)
        m3 = _make_metrics(matrix_verdict_changed_count=0)
        agg = _aggregate_subset([m1, m2, m3])
        assert agg["matrix_verdict_changed_count"] == 5

    def test_aggregate_keys_include_matrix_fields(self) -> None:
        """``_aggregate_subset`` returns dicts with the 2 new matrix keys."""
        agg = _aggregate_subset([_make_metrics()])
        assert "matrix_aggregate" in agg
        assert "matrix_verdict_changed_count" in agg

    def test_build_aggregate_by_language_preserves_matrix_rollup(self) -> None:
        """The per-language split preserves the matrix rollup shape."""
        m_en = _make_metrics(
            language="en",
            matrix_aggregate={
                "acceptable": 5,
                "material": 3,
                "unacceptable": 0,
                "unverified": 1,
                "no_stamp": 0,
            },
            matrix_verdict_changed_count=4,
        )
        m_de = _make_metrics(
            language="de",
            matrix_aggregate={
                "acceptable": 2,
                "material": 1,
                "unacceptable": 1,
                "unverified": 0,
                "no_stamp": 0,
            },
            matrix_verdict_changed_count=2,
        )
        by_lang = _build_aggregate_by_language([m_en, m_de])
        assert by_lang["en"]["matrix_aggregate"]["material"] == 3
        assert by_lang["en"]["matrix_verdict_changed_count"] == 4
        assert by_lang["de"]["matrix_aggregate"]["unacceptable"] == 1
        assert by_lang["de"]["matrix_verdict_changed_count"] == 2


# --- TestMatrixChangedDetection ----------------------------------------


class TestMatrixChangedDetection:
    """The per-flag change detection in ``_run_one_contract``.

    These tests re-implement the rollup loop on synthetic
    flag lists so the changed-detection rule is covered
    without needing a real contract. The rule is: a flag's
    matrix verdict is "changed" iff its ``matrix_sources``
    first entry is not ``"flat"``. The test asserts:

    - ``score = 0`` flags are skipped (no matrix signal)
    - ``matrix_verdict is None`` flags go to the
      ``no_stamp`` bucket
    - ``matrix_verdict in MATRIX_VERDICT_VALUES`` flags go
      to the matching bucket
    - Garbage ``matrix_verdict`` values fall to
      ``unverified`` (the same fail-safe the spotter uses
    - ``matrix_sources = []`` or ``None`` defaults to
      ``"flat"`` (no change)
    - ``matrix_sources[0] = "flat"`` is no change
    - ``matrix_sources[0] = "counterparty"`` is a change
    """

    @staticmethod
    def _rollup(flags: list[SimpleNamespace]) -> tuple[dict[str, int], int]:
        """Re-implement the per-flag rollup from ``_run_one_contract``.

        Kept in sync with the harness's loop (lines 567-601 of
        ``evals/harness.py`` at the time of writing). If the
        harness loop changes, this helper MUST be updated.
        """
        matrix_aggregate: dict[str, int] = {
            v: 0 for v in MATRIX_VERDICT_VALUES
        } | {"no_stamp": 0}
        changed = 0
        for f in flags:
            if f.score <= 0:
                continue
            verdict = f.matrix_verdict
            if verdict is None:
                bucket = "no_stamp"
            elif verdict in MATRIX_VERDICT_VALUES:
                bucket = verdict
            else:
                bucket = "unverified"  # garbage → fail-safe
            matrix_aggregate[bucket] = matrix_aggregate.get(bucket, 0) + 1
            sources = list(f.matrix_sources or [])
            winning = sources[0] if sources else "flat"
            if winning != "flat":
                changed += 1
        return matrix_aggregate, changed

    def test_score_zero_flags_are_excluded(self) -> None:
        """``score = 0`` flags don't contribute to the histogram."""
        flags = [
            _flag(score=0, matrix_verdict="material"),
            _flag(score=0, matrix_verdict="acceptable"),
        ]
        agg, changed = self._rollup(flags)
        assert agg == {
            "acceptable": 0,
            "material": 0,
            "unacceptable": 0,
            "unverified": 0,
            "no_stamp": 0,
        }
        assert changed == 0

    def test_none_verdict_goes_to_no_stamp_bucket(self) -> None:
        """``matrix_verdict = None`` is the ``no_stamp`` bucket."""
        flags = [
            _flag(score=1, matrix_verdict=None, matrix_sources=["flat"]),
        ]
        agg, _ = self._rollup(flags)
        assert agg["no_stamp"] == 1
        assert agg["material"] == 0

    def test_known_verdict_goes_to_matching_bucket(self) -> None:
        """A flag with ``matrix_verdict = 'unacceptable'`` is bucketed correctly."""
        flags = [
            _flag(score=2, matrix_verdict="unacceptable", matrix_sources=["flat"]),
            _flag(score=1, matrix_verdict="acceptable", matrix_sources=["flat"]),
            _flag(score=3, matrix_verdict="unacceptable", matrix_sources=["flat"]),
        ]
        agg, _ = self._rollup(flags)
        assert agg["unacceptable"] == 2
        assert agg["acceptable"] == 1

    def test_garbage_verdict_falls_to_unverified(self) -> None:
        """An unknown ``matrix_verdict`` value fails safe to ``unverified``."""
        flags = [
            _flag(score=1, matrix_verdict="garbage", matrix_sources=["flat"]),
            _flag(score=1, matrix_verdict="DELETED_LEGACY_VALUE", matrix_sources=["flat"]),
        ]
        agg, _ = self._rollup(flags)
        assert agg["unverified"] == 2
        # Garbage does NOT also increment a spec bucket.
        assert agg["acceptable"] == 0
        assert agg["material"] == 0

    def test_empty_sources_means_no_change(self) -> None:
        """``matrix_sources = []`` is treated as ``['flat']`` (no change)."""
        flags = [
            _flag(score=1, matrix_verdict="material", matrix_sources=[]),
            _flag(score=1, matrix_verdict="material", matrix_sources=None),
        ]
        _, changed = self._rollup(flags)
        assert changed == 0

    def test_first_source_flat_means_no_change(self) -> None:
        """``matrix_sources = ['flat']`` is no change."""
        flags = [
            _flag(score=1, matrix_verdict="material", matrix_sources=["flat"]),
            _flag(score=1, matrix_verdict="material", matrix_sources=["flat", "counterparty"]),
        ]
        _, changed = self._rollup(flags)
        assert changed == 0

    def test_first_source_non_flat_is_a_change(self) -> None:
        """``matrix_sources = ['counterparty', ...]`` is a change."""
        flags = [
            _flag(score=1, matrix_verdict="material", matrix_sources=["counterparty"]),
            _flag(score=1, matrix_verdict="material", matrix_sources=["language"]),
            _flag(
                score=1,
                matrix_verdict="unacceptable",
                matrix_sources=["per_type_escalation"],
            ),
        ]
        _, changed = self._rollup(flags)
        assert changed == 3

    def test_mixed_score_and_sources_rolls_up_correctly(self) -> None:
        """A realistic flag mix: 3 score>0, 1 score=0, mixed sources."""
        flags = [
            _flag(score=0, matrix_verdict="material", matrix_sources=["flat"]),  # skipped
            _flag(score=2, matrix_verdict="material", matrix_sources=["flat"]),  # no change
            _flag(score=2, matrix_verdict="unacceptable", matrix_sources=["counterparty", "flat"]),  # change
            _flag(score=1, matrix_verdict="acceptable", matrix_sources=["flat", "counterparty"]),  # no change
            _flag(score=3, matrix_verdict="unacceptable", matrix_sources=["per_type_escalation"]),  # change
        ]
        agg, changed = self._rollup(flags)
        assert agg == {
            "acceptable": 1,
            "material": 1,
            "unacceptable": 2,
            "unverified": 0,
            "no_stamp": 0,
        }
        assert changed == 2


# --- TestLeaderboardSchemaV110 -----------------------------------------


class TestLeaderboardSchemaV110:
    """The leaderboard CSV schema bumps to v1.1.0 with the 13 new matrix columns."""

    REQUIRED_MATRIX_FIELDS = (
        "matrix_acceptable_en",
        "matrix_material_en",
        "matrix_unacceptable_en",
        "matrix_unverified_en",
        "matrix_no_stamp_en",
        "matrix_verdict_changed_count_en",
        "matrix_acceptable_de",
        "matrix_material_de",
        "matrix_unacceptable_de",
        "matrix_unverified_de",
        "matrix_no_stamp_de",
        "matrix_verdict_changed_count_de",
        "matrix_changed_contracts_count",
    )

    def test_leaderboard_schema_version_is_phase5(self) -> None:
        """The schema version string mentions phase 5 / matrix."""
        assert "phase5" in LEADERBOARD_SCHEMA_VERSION or "1.1" in LEADERBOARD_SCHEMA_VERSION, (
            f"LEADERBOARD_SCHEMA_VERSION should reflect the v1.1.0 bump; got {LEADERBOARD_SCHEMA_VERSION!r}"
        )

    def test_leaderboard_fields_includes_all_matrix_columns(self) -> None:
        """All 13 matrix columns are present in ``LEADERBOARD_FIELDS``."""
        for f in self.REQUIRED_MATRIX_FIELDS:
            assert f in LEADERBOARD_FIELDS, (
                f"LEADERBOARD_FIELDS missing {f!r}; got {LEADERBOARD_FIELDS}"
            )

    def test_append_leaderboard_row_writes_matrix_cells(
        self, tmp_path: Path
    ) -> None:
        """A row on a fresh leaderboard has the 13 new matrix cells."""
        csv_path = tmp_path / "leaderboard.csv"
        agg_en = {
            "retrieval_f1": 1.0,
            "classification_f1": 0.9,
            "deviation_f1": 0.9,
            "severity_mismatch_count": 0,
            "citation_completeness": 0.95,
            "matrix_aggregate": {
                "acceptable": 4,
                "material": 3,
                "unacceptable": 0,
                "unverified": 0,
                "no_stamp": 0,
            },
            "matrix_verdict_changed_count": 2,
        }
        agg_de = {
            "retrieval_f1": 1.0,
            "classification_f1": 0.85,
            "deviation_f1": 0.85,
            "severity_mismatch_count": 1,
            "citation_completeness": 0.92,
            "matrix_aggregate": {
                "acceptable": 2,
                "material": 1,
                "unacceptable": 1,
                "unverified": 0,
                "no_stamp": 0,
            },
            "matrix_verdict_changed_count": 1,
        }
        agg_by_lang = {"en": agg_en, "de": agg_de}
        gap = _compute_gap_assertions(agg_by_lang)
        gap_with_matrix = {**gap, "matrix_changed_contracts_count": 3}
        _append_leaderboard_row(
            csv_path,
            run_id="matrix-row",
            started_at="2026-06-15T00:00:00+00:00",
            ended_at="2026-06-15T00:00:01+00:00",
            real_llm_mode=False,
            contract_set_version="0.4.0-phase5-matrix",
            language_filter="both",
            n_contracts=10,
            aggregate_by_language=agg_by_lang,
            gap_assertions_=gap_with_matrix,
        )
        with csv_path.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        row = rows[0]
        # EN matrix cells.
        assert row["matrix_acceptable_en"] == "4"
        assert row["matrix_material_en"] == "3"
        assert row["matrix_unacceptable_en"] == "0"
        assert row["matrix_unverified_en"] == "0"
        assert row["matrix_no_stamp_en"] == "0"
        assert row["matrix_verdict_changed_count_en"] == "2"
        # DE matrix cells.
        assert row["matrix_acceptable_de"] == "2"
        assert row["matrix_material_de"] == "1"
        assert row["matrix_unacceptable_de"] == "1"
        assert row["matrix_unverified_de"] == "0"
        assert row["matrix_no_stamp_de"] == "0"
        assert row["matrix_verdict_changed_count_de"] == "1"
        # Run-wide.
        assert row["matrix_changed_contracts_count"] == "3"

    def test_append_leaderboard_row_empty_cells_for_missing_languages(
        self, tmp_path: Path
    ) -> None:
        """``--language=en`` runs have empty DE matrix cells."""
        csv_path = tmp_path / "leaderboard.csv"
        agg_en = {
            "retrieval_f1": 1.0,
            "classification_f1": 0.9,
            "deviation_f1": 0.9,
            "severity_mismatch_count": 0,
            "citation_completeness": 0.95,
            "matrix_aggregate": {
                "acceptable": 4,
                "material": 0,
                "unacceptable": 0,
                "unverified": 0,
                "no_stamp": 0,
            },
            "matrix_verdict_changed_count": 0,
        }
        agg_by_lang = {"en": agg_en}
        gap = _compute_gap_assertions(agg_by_lang)
        gap_with_matrix = {**gap, "matrix_changed_contracts_count": 0}
        _append_leaderboard_row(
            csv_path,
            run_id="en-only",
            started_at="t",
            ended_at="t",
            real_llm_mode=False,
            contract_set_version="v",
            language_filter="en",
            n_contracts=5,
            aggregate_by_language=agg_by_lang,
            gap_assertions_=gap_with_matrix,
        )
        with csv_path.open() as f:
            rows = list(csv.DictReader(f))
        row = rows[0]
        assert row["matrix_acceptable_en"] == "4"
        # DE matrix cells are empty (the run didn't process DE).
        assert row["matrix_acceptable_de"] == ""
        assert row["matrix_material_de"] == ""
        assert row["matrix_unacceptable_de"] == ""
        assert row["matrix_unverified_de"] == ""
        assert row["matrix_no_stamp_de"] == ""
        assert row["matrix_verdict_changed_count_de"] == ""
        # Run-wide is still populated (exit-gate signal is run-level).
        assert row["matrix_changed_contracts_count"] == "0"


# --- TestWriteRunReportMatrix ------------------------------------------


class TestWriteRunReportMatrix:
    """The JSON run report carries the run-wide matrix rollup.

    Each test in this class monkeypatches ``evals.harness.LEADERBOARD_PATH``
    to a temp file so the test does NOT pollute the real
    ``evals/leaderboard.csv``. The harness's
    ``_write_run_report`` always appends a row to the
    module-level ``LEADERBOARD_PATH`` (by design — that's the
    eval harness's durable handoff to the CI dashboard), and
    a unit test must not write to the real file. The
    ``test_eval_set_runs_end_to_end`` integration test is the
    only one that writes to the real leaderboard.
    """

    def _patched_leaderboard(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        """Point the harness's leaderboard at a temp file for this test."""
        fake = tmp_path / "leaderboard.csv"
        monkeypatch.setattr("evals.harness.LEADERBOARD_PATH", fake)
        return fake

    def test_write_run_report_includes_top_level_matrix_fields(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The JSON report has ``matrix_aggregate`` and ``matrix_changed_contracts_count``."""
        self._patched_leaderboard(monkeypatch, tmp_path)
        m1 = _make_metrics(
            matrix_aggregate={
                "acceptable": 3,
                "material": 2,
                "unacceptable": 1,
                "unverified": 0,
                "no_stamp": 0,
            },
            matrix_verdict_changed_count=3,
        )
        m2 = _make_metrics(
            matrix_aggregate={
                "acceptable": 1,
                "material": 1,
                "unacceptable": 0,
                "unverified": 0,
                "no_stamp": 0,
            },
            matrix_verdict_changed_count=0,
        )
        report_path = tmp_path / "run.json"
        report = _write_run_report(
            report_path,
            run_id="matrix-test",
            started_at="2026-06-15T00:00:00+00:00",
            ended_at="2026-06-15T00:00:01+00:00",
            real_llm_mode=False,
            per_contract=[m1, m2],
            language_filter="both",
        )
        # Dataclass surface.
        assert hasattr(report, "matrix_aggregate")
        assert hasattr(report, "matrix_changed_contracts_count")
        # Run-wide histogram is the sum of per-contract buckets.
        assert report.matrix_aggregate == {
            "acceptable": 4,
            "material": 3,
            "unacceptable": 1,
            "unverified": 0,
            "no_stamp": 0,
        }
        # Run-wide changed-count is the count of contracts with changes.
        assert report.matrix_changed_contracts_count == 1

    def test_write_run_report_json_shape_has_matrix_fields(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The serialized JSON has the new matrix fields at the top level."""
        self._patched_leaderboard(monkeypatch, tmp_path)
        m1 = _make_metrics(
            matrix_aggregate={
                "acceptable": 1,
                "material": 1,
                "unacceptable": 0,
                "unverified": 0,
                "no_stamp": 0,
            },
            matrix_verdict_changed_count=1,
        )
        report_path = tmp_path / "run.json"
        _write_run_report(
            report_path,
            run_id="json-shape",
            started_at="t",
            ended_at="t",
            real_llm_mode=False,
            per_contract=[m1],
            language_filter="en",
        )
        with report_path.open() as f:
            data = json.load(f)
        assert "matrix_aggregate" in data
        assert "matrix_changed_contracts_count" in data
        assert isinstance(data["matrix_aggregate"], dict)
        assert set(data["matrix_aggregate"].keys()) == {
            "acceptable",
            "material",
            "unacceptable",
            "unverified",
            "no_stamp",
        }
        assert data["matrix_changed_contracts_count"] == 1

    def test_write_run_report_per_contract_includes_matrix_aggregate(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The per-contract block in the JSON has the new fields too."""
        self._patched_leaderboard(monkeypatch, tmp_path)
        m1 = _make_metrics(
            matrix_aggregate={
                "acceptable": 0,
                "material": 0,
                "unacceptable": 1,
                "unverified": 0,
                "no_stamp": 0,
            },
            matrix_verdict_changed_count=1,
        )
        report_path = tmp_path / "run.json"
        _write_run_report(
            report_path,
            run_id="per-contract",
            started_at="t",
            ended_at="t",
            real_llm_mode=False,
            per_contract=[m1],
            language_filter="en",
        )
        with report_path.open() as f:
            data = json.load(f)
        contract = data["contracts"][0]
        assert "matrix_aggregate" in contract
        assert "matrix_verdict_changed_count" in contract
        assert "matrix_changed" in contract
        assert contract["matrix_aggregate"]["unacceptable"] == 1
        assert contract["matrix_verdict_changed_count"] == 1
        assert contract["matrix_changed"] is True

    def test_write_run_report_zero_changed_contracts(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """All-flat run: ``matrix_changed_contracts_count = 0``."""
        self._patched_leaderboard(monkeypatch, tmp_path)
        m1 = _make_metrics(matrix_verdict_changed_count=0)
        m2 = _make_metrics(matrix_verdict_changed_count=0)
        report_path = tmp_path / "run.json"
        report = _write_run_report(
            report_path,
            run_id="flat",
            started_at="t",
            ended_at="t",
            real_llm_mode=False,
            per_contract=[m1, m2],
            language_filter="en",
        )
        assert report.matrix_changed_contracts_count == 0
        assert all(v == 0 for v in report.matrix_aggregate.values())
