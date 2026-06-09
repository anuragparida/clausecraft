"""Phase 4 — per-language F1 + gap-assertion unit tests.

These tests exercise the Phase 4 eval-harness surface
*without* running the full pipeline on a real contract. The
full integration is the ``test_eval_set_runs_end_to_end``
test in ``evals/harness.py``; the unit tests here prove the
behaviour of the new pieces in isolation:

- ``_build_aggregate_by_language`` — groups per-contract
  metrics by language and computes the per-language F1
  split.
- ``_compute_gap_assertions`` + ``assert_gap_assertions`` —
  hard-coded 10% deviation F1 / 5% citation completeness
  thresholds, fail CI on regression.
- ``_append_leaderboard_row`` — the per-run leaderboard
  CSV writer.
- The JSON report shape — the per-language split, gap
  assertions, and ``language_filter`` fields appear with
  the right structure.
- ``--language`` filter — the CLI option filters the
  active eval set to a single language.

Why unit tests, not just the integration test
---------------------------------------------
The integration test (``test_eval_set_runs_end_to_end``)
runs the full pipeline against the real eval set, which
is EN-only at the time of writing — so it can never
exercise the gap-assertion logic (the gap is undefined
with one language). These unit tests construct synthetic
two-language aggregates so we can prove the 10% / 5%
thresholds work, the skip-on-one-language logic works,
and the EN-vs-other comparison picks the right pair.
The moment the DE eval set lands, the integration test
will start exercising the gap assertion too — but until
then, this file is the only test that proves the gap
logic.

What these tests are NOT
-------------------------
They are not a substitute for the integration test on
real contracts. The integration test exercises the full
ingest → parse → classify → spot pipeline and the
golden-YAML-driven mock. These unit tests only prove
that the new code paths are correct in isolation; a
golden-set bug would not be caught here.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from evals.harness import (
    CITATION_COMPLETENESS_GAP_THRESHOLD,
    CONTRACT_TYPE,
    DEVIATION_F1_GAP_THRESHOLD,
    LANGUAGE_FILTER_CHOICES,
    LEADERBOARD_FIELDS,
    LEADERBOARD_PATH,
    LEADERBOARD_SCHEMA_VERSION,
    ContractMetrics,
    _aggregate_subset,
    _append_leaderboard_row,
    _build_aggregate,
    _build_aggregate_by_language,
    _compute_gap_assertions,
    _write_run_report,
    assert_gap_assertions,
)


# --- Helpers ------------------------------------------------------------


def _make_metrics(
    *,
    contract: str = "examples/contracts/test/nda.pdf",
    language: str = "en",
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
) -> ContractMetrics:
    """Build a ContractMetrics with sensible defaults for unit tests.

    Defaults produce a perfect score: 5/5 classification,
    1/1 deviation, 1/1 citation. Tests that exercise a
    regression override the relevant fields.

    Note: ``flags_with_citation`` is capped at
    ``actual_flag_count`` so the default-citation rate is
    well-defined (can't have more citations than flags).
    The dataclass doesn't enforce this invariant; it's
    on the caller.
    """
    if flags_with_citation > actual_flag_count:
        flags_with_citation = actual_flag_count
    return ContractMetrics(
        contract=contract,
        contract_type=CONTRACT_TYPE,
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
    )


def _make_aggregate(
    *,
    en_f1: float,
    de_f1: float,
    en_citation: float = 1.0,
    de_citation: float = 1.0,
) -> dict[str, dict[str, float]]:
    """Build a synthetic per-language aggregate for gap-assertion tests.

    Only the deviation F1 and citation completeness are
    relevant for the gap assertion — the other fields are
    filled with neutral defaults.
    """
    def _agg(dev_f1: float, citation: float) -> dict[str, float]:
        return {
            "retrieval_f1": 1.0,
            "classification_f1": dev_f1,
            "deviation_f1": dev_f1,
            "severity_mismatch_count": 0,
            "citation_completeness": citation,
        }

    return {
        "en": _agg(en_f1, en_citation),
        "de": _agg(de_f1, de_citation),
    }


# --- _aggregate_subset --------------------------------------------------


def test_aggregate_subset_perfect_classification_and_deviation() -> None:
    """Perfect inputs: all 5 contracts classify + spot correctly."""
    metrics = [
        _make_metrics(classification_tp=10, classification_fp=0, classification_fn=0,
                      deviation_tp=2, deviation_fp=0, deviation_fn=0,
                      flags_with_citation=2)
        for _ in range(5)
    ]
    agg = _aggregate_subset(metrics)
    assert agg["classification_f1"] == 1.0
    assert agg["deviation_f1"] == 1.0
    assert agg["citation_completeness"] == 1.0
    assert agg["severity_mismatch_count"] == 0


def test_aggregate_subset_micro_averaged_classification() -> None:
    """Classification F1 is micro-averaged, not macro-averaged.

    Two contracts: contract A has 9 TP + 1 FP, contract B
    has 1 TP + 9 FP. Per-contract F1s are 0.947 and 0.10.
    Macro would give ~0.524; micro gives 10/20 = 0.50.
    """
    a = _make_metrics(classification_tp=9, classification_fp=1, classification_fn=0)
    b = _make_metrics(classification_tp=1, classification_fp=9, classification_fn=0)
    agg = _aggregate_subset([a, b])
    p = 10 / 20  # micro precision
    r = 10 / 10  # micro recall
    expected = 2 * p * r / (p + r)
    assert agg["classification_f1"] == pytest.approx(round(expected, 4), rel=1e-3)


def test_aggregate_subset_empty_subset_is_well_defined() -> None:
    """An empty subset returns the same 5 keys with neutral defaults.

    This is the edge case for ``--language=de`` on an
    EN-only eval set: the active subset is empty, but the
    shape must still be valid so the report JSON is
    well-formed.
    """
    agg = _aggregate_subset([])
    assert set(agg.keys()) == {
        "retrieval_f1",
        "classification_f1",
        "deviation_f1",
        "severity_mismatch_count",
        "citation_completeness",
    }
    assert agg["retrieval_f1"] == 0.0
    assert agg["classification_f1"] == 0.0
    assert agg["deviation_f1"] == 1.0  # trivially aligned
    assert agg["severity_mismatch_count"] == 0
    assert agg["citation_completeness"] == 1.0  # vacuously complete


# --- _build_aggregate (legacy entry) -----------------------------------


def test_build_aggregate_matches_aggregate_subset_for_mixed_languages() -> None:
    """``_build_aggregate`` returns the same shape as ``_aggregate_subset``.

    Phase 4 keeps ``_build_aggregate`` as a thin wrapper
    over ``_aggregate_subset`` for backwards compat with
    the Phase 2 report shape. The new ``aggregate_by_language``
    is the primary view.
    """
    metrics = [
        _make_metrics(language="en", classification_tp=5),
        _make_metrics(language="de", classification_tp=3, classification_fp=2),
    ]
    full = _build_aggregate(metrics)
    subset = _aggregate_subset(metrics)
    assert full == subset


# --- _build_aggregate_by_language --------------------------------------


def test_build_aggregate_by_language_groups_by_lang() -> None:
    """Per-language split: EN and DE get separate aggregate dicts."""
    en = _make_metrics(language="en", contract="nda-001.pdf",
                       classification_tp=5, classification_fp=0)
    de = _make_metrics(language="de", contract="nda-002.pdf",
                       classification_tp=3, classification_fp=2)
    agg = _build_aggregate_by_language([en, de])
    assert set(agg.keys()) == {"en", "de"}
    assert agg["en"]["classification_f1"] == 1.0
    # DE: 3 tp, 2 fp → p = 0.6, r = 1.0 → f1 = 0.75.
    assert agg["de"]["classification_f1"] == pytest.approx(0.75, rel=1e-2)


def test_build_aggregate_by_language_omits_empty_languages() -> None:
    """A run that produced no contracts has an empty per-language split.

    This is the ``--language=de`` on the EN-only eval set
    case: no contracts were processed, so the per-language
    split is the empty dict.
    """
    agg = _build_aggregate_by_language([])
    assert agg == {}


def test_build_aggregate_by_language_treats_blank_language_as_unknown() -> None:
    """A contract with ``language=""`` is bucketed under ``"unknown"``."""
    blank = _make_metrics(language="", contract="nda-blank.pdf")
    agg = _build_aggregate_by_language([blank])
    assert "unknown" in agg
    assert agg["unknown"]["classification_f1"] == 1.0


# --- _compute_gap_assertions + assert_gap_assertions -------------------


def test_gap_assertions_both_languages_pass() -> None:
    """Both languages within budget → ``all_passed=True``."""
    agg = _make_aggregate(en_f1=0.9, de_f1=0.85, en_citation=0.95, de_citation=0.92)
    # Drops: deviation 0.05 (< 0.10), citation 0.03 (< 0.05).
    gap = _compute_gap_assertions(agg)
    # ``languages_compared`` is the EN-vs-other pair (always
    # EN first), not the sorted-keys list.
    assert gap["languages_compared"] == ["en", "de"]
    assert gap["deviation_f1"]["drop"] == pytest.approx(0.05, abs=1e-3)
    assert gap["deviation_f1"]["passed"] is True
    assert gap["citation_completeness"]["drop"] == pytest.approx(0.03, abs=1e-3)
    assert gap["citation_completeness"]["passed"] is True
    assert gap["all_passed"] is True


def test_gap_assertions_deviation_drop_at_threshold_passes() -> None:
    """Drop exactly equal to the threshold is treated as a pass (drop ≤ threshold)."""
    agg = _make_aggregate(en_f1=0.9, de_f1=0.8)  # 0.10 drop, exactly the threshold
    gap = _compute_gap_assertions(agg)
    assert gap["deviation_f1"]["drop"] == pytest.approx(0.10, abs=1e-3)
    assert gap["deviation_f1"]["threshold"] == DEVIATION_F1_GAP_THRESHOLD
    assert gap["deviation_f1"]["passed"] is True


def test_gap_assertions_deviation_drop_above_threshold_fails() -> None:
    """A 12% DE F1 drop is the spec's "red flag" example — must fail."""
    agg = _make_aggregate(en_f1=0.92, de_f1=0.80)  # 0.12 drop, exceeds threshold
    gap = _compute_gap_assertions(agg)
    assert gap["deviation_f1"]["drop"] == pytest.approx(0.12, abs=1e-3)
    assert gap["deviation_f1"]["passed"] is False
    assert gap["all_passed"] is False


def test_gap_assertions_citation_drop_above_threshold_fails() -> None:
    """A 6% citation completeness drop exceeds the 5% threshold."""
    agg = _make_aggregate(en_f1=0.9, de_f1=0.85, en_citation=0.96, de_citation=0.90)
    gap = _compute_gap_assertions(agg)
    assert gap["citation_completeness"]["drop"] == pytest.approx(0.06, abs=1e-3)
    assert gap["citation_completeness"]["passed"] is False
    assert gap["all_passed"] is False


def test_gap_assertions_only_one_language_skips() -> None:
    """One language → gap is undefined, assertion is skipped (not failed)."""
    agg = {"en": _make_aggregate(en_f1=0.9, de_f1=0.0)["en"]}
    gap = _compute_gap_assertions(agg)
    assert gap["skipped"] is True
    assert gap["languages_compared"] == ["en"]
    assert "skip_reason" in gap
    assert "Re-run with --language=both" in gap["skip_reason"]
    # The hard assertion function is a no-op when the gap is skipped.
    assert_gap_assertions(gap)  # must not raise


def test_gap_assertions_no_languages_skips() -> None:
    """Zero languages (empty active set) → skipped with a clear reason."""
    gap = _compute_gap_assertions({})
    assert gap["skipped"] is True
    assert gap["languages_compared"] == []
    assert_gap_assertions(gap)  # no-op


def test_gap_assertions_no_en_skips_with_specific_reason() -> None:
    """Both FR and DE present, no EN → skip because EN is the reference."""
    agg = {
        "fr": _make_aggregate(en_f1=0.9, de_f1=0.85)["en"],
        "de": _make_aggregate(en_f1=0.9, de_f1=0.85)["de"],
    }
    gap = _compute_gap_assertions(agg)
    assert gap["skipped"] is True
    assert "EN aggregate is the reference" in gap["skip_reason"]


def test_assert_gap_assertions_raises_on_deviation_regression() -> None:
    """``assert_gap_assertions`` raises ``AssertionError`` on a 12% drop.

    This is the "code assertion, not report line" guarantee
    the spec requires. A 12% drop is a real regression —
    the function must raise.
    """
    agg = _make_aggregate(en_f1=0.92, de_f1=0.80)
    gap = _compute_gap_assertions(agg)
    with pytest.raises(AssertionError) as excinfo:
        assert_gap_assertions(gap)
    assert "DEVIATION F1 GAP" in str(excinfo.value)
    assert "10%" in str(excinfo.value)


def test_assert_gap_assertions_raises_on_citation_regression() -> None:
    """A citation completeness drop above 5% also raises."""
    agg = _make_aggregate(en_f1=0.9, de_f1=0.85, en_citation=0.96, de_citation=0.88)
    gap = _compute_gap_assertions(agg)
    with pytest.raises(AssertionError) as excinfo:
        assert_gap_assertions(gap)
    assert "CITATION COMPLETENESS GAP" in str(excinfo.value)
    assert "5%" in str(excinfo.value)


def test_assert_gap_assertions_raises_with_both_failures() -> None:
    """Both metrics failing surfaces both in the AssertionError message."""
    agg = _make_aggregate(
        en_f1=0.95, de_f1=0.80,  # 0.15 deviation drop
        en_citation=0.99, de_citation=0.90,  # 0.09 citation drop
    )
    gap = _compute_gap_assertions(agg)
    with pytest.raises(AssertionError) as excinfo:
        assert_gap_assertions(gap)
    msg = str(excinfo.value)
    assert "DEVIATION F1 GAP" in msg
    assert "CITATION COMPLETENESS GAP" in msg


def test_gap_assertions_use_module_constants_for_thresholds() -> None:
    """The thresholds in the report match the module-level constants.

    Guards against the constant-and-the-assertion drifting
    out of sync (the "comment vs code" anti-pattern the
    spec calls out).
    """
    agg = _make_aggregate(en_f1=0.9, de_f1=0.85)
    gap = _compute_gap_assertions(agg)
    assert gap["deviation_f1"]["threshold"] == DEVIATION_F1_GAP_THRESHOLD
    assert gap["citation_completeness"]["threshold"] == CITATION_COMPLETENESS_GAP_THRESHOLD
    # And the constants themselves match the spec's 10% / 5%.
    assert DEVIATION_F1_GAP_THRESHOLD == 0.10
    assert CITATION_COMPLETENESS_GAP_THRESHOLD == 0.05


# --- Leaderboard CSV ----------------------------------------------------


def test_append_leaderboard_row_writes_header_on_new_file(tmp_path: Path) -> None:
    """First append to a fresh path writes the header row."""
    csv_path = tmp_path / "leaderboard.csv"
    agg_by_lang = _make_aggregate(en_f1=0.9, de_f1=0.85)
    gap = _compute_gap_assertions(agg_by_lang)
    _append_leaderboard_row(
        csv_path,
        run_id="r1",
        started_at="2026-06-09T00:00:00+00:00",
        ended_at="2026-06-09T00:00:01+00:00",
        real_llm_mode=False,
        contract_set_version="0.3.0-test",
        language_filter="both",
        n_contracts=10,
        aggregate_by_language=agg_by_lang,
        gap_assertions_=gap,
    )
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["run_id"] == "r1"
    assert rows[0]["language_filter"] == "both"
    assert rows[0]["n_contracts"] == "10"
    assert float(rows[0]["deviation_f1_en"]) == 0.9
    assert float(rows[0]["deviation_f1_de"]) == 0.85
    assert rows[0]["gap_passed"] == "True"


def test_append_leaderboard_row_appends_without_header(tmp_path: Path) -> None:
    """A second append does not write a duplicate header."""
    csv_path = tmp_path / "leaderboard.csv"
    csv_path.write_text(
        "run_id,started_at,ended_at,real_llm_mode,contract_set_version,language_filter,n_contracts,classification_f1_en,classification_f1_de,deviation_f1_en,deviation_f1_de,citation_completeness_en,citation_completeness_de,severity_mismatch_count_en,severity_mismatch_count_de,gap_deviation_f1,gap_citation_completeness,gap_passed\n"
        "old,ts,ts,False,v,en,5,,,,,,,,,,,\n"
    )
    agg = {"en": _make_aggregate(en_f1=0.9, de_f1=0.0)["en"]}
    gap = _compute_gap_assertions(agg)
    _append_leaderboard_row(
        csv_path,
        run_id="new",
        started_at="t", ended_at="t", real_llm_mode=False,
        contract_set_version="v", language_filter="en",
        n_contracts=5, aggregate_by_language=agg, gap_assertions_=gap,
    )
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["run_id"] == "old"
    assert rows[1]["run_id"] == "new"


def test_append_leaderboard_row_empty_cells_for_missing_languages(tmp_path: Path) -> None:
    """A ``--language=en`` run has empty DE columns (no DE was processed)."""
    csv_path = tmp_path / "leaderboard.csv"
    agg = {"en": _make_aggregate(en_f1=0.9, de_f1=0.0)["en"]}
    gap = _compute_gap_assertions(agg)
    _append_leaderboard_row(
        csv_path,
        run_id="en-only", started_at="t", ended_at="t",
        real_llm_mode=False, contract_set_version="v",
        language_filter="en", n_contracts=5,
        aggregate_by_language=agg, gap_assertions_=gap,
    )
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    row = rows[0]
    # EN columns populated, DE columns empty.
    assert row["deviation_f1_en"] == "0.9"
    assert row["deviation_f1_de"] == ""
    assert row["citation_completeness_de"] == ""
    # Gap columns empty (skipped — only one language).
    assert row["gap_deviation_f1"] == ""
    assert row["gap_citation_completeness"] == ""
    assert row["gap_passed"] == ""


def test_leaderboard_path_and_fields_match_module_constants() -> None:
    """The module-level constants for the leaderboard are self-consistent."""
    assert LEADERBOARD_PATH.is_absolute()
    assert LEADERBOARD_PATH.parent.name == "evals"
    # The fields list is the schema — the writer uses it
    # as the DictWriter fieldnames.
    assert isinstance(LEADERBOARD_FIELDS, list)
    assert len(LEADERBOARD_FIELDS) >= 12  # per-language + gap columns
    # Schema version is a string for downstream readers to detect mismatches.
    assert isinstance(LEADERBOARD_SCHEMA_VERSION, str)
    assert LEADERBOARD_SCHEMA_VERSION  # non-empty


# --- _write_run_report (JSON shape) ------------------------------------


def test_write_run_report_includes_phase4_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The JSON report carries ``aggregate_by_language`` + ``gap_assertions``
    + ``language_filter`` (the Phase 4 additions), in
    addition to the legacy ``aggregate`` field.
    """
    # Redirect the leaderboard writer to a tmp file so
    # the unit test doesn't pollute the real
    # ``evals/leaderboard.csv`` with synthetic run_ids.
    fake_leaderboard = tmp_path / "leaderboard.csv"
    monkeypatch.setattr(
        "evals.harness.LEADERBOARD_PATH", fake_leaderboard
    )
    metrics = [
        _make_metrics(language="en", contract="nda-001.pdf"),
        _make_metrics(language="de", contract="nda-002.pdf", classification_tp=3,
                      classification_fp=1),
    ]
    report_path = tmp_path / "report.json"
    report = _write_run_report(
        report_path,
        run_id="r1",
        started_at="t0", ended_at="t1",
        real_llm_mode=False,
        per_contract=metrics,
        language_filter="both",
    )
    with report_path.open() as f:
        data = json.load(f)
    # Legacy aggregate is preserved.
    assert "aggregate" in data
    assert set(data["aggregate"].keys()) == {
        "retrieval_f1", "classification_f1", "deviation_f1",
        "severity_mismatch_count", "citation_completeness",
    }
    # Phase 4 additions.
    assert "aggregate_by_language" in data
    assert set(data["aggregate_by_language"].keys()) == {"en", "de"}
    assert "gap_assertions" in data
    assert "language_filter" in data
    assert data["language_filter"] == "both"
    # The dataclass is consistent with the JSON.
    assert report.language_filter == "both"
    assert "en" in report.aggregate_by_language
    assert "de" in report.aggregate_by_language
    # The leaderboard was written to the tmp path, not the
    # real one (so a re-run of this test doesn't pollute
    # the production leaderboard).
    assert fake_leaderboard.is_file()
    with fake_leaderboard.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["run_id"] == "r1"


# --- --language CLI filter --------------------------------------------


def test_language_filter_choices() -> None:
    """The ``--language`` option accepts exactly ``en``, ``de``, or ``both``."""
    assert LANGUAGE_FILTER_CHOICES == ("en", "de", "both")


# --- Per-contract smoke test behaviour --------------------------------


def test_per_contract_smoke_test_skipped_for_filtered_language() -> None:
    """A per-contract smoke test on a DE contract is skipped under
    ``--language=en``.

    This is a documentation test — the actual skip
    behaviour is implemented inside the
    ``test_contract_ingests_and_classifies`` parametrised
    test, which reads the ``--language`` option at test
    time. We assert the same logic exists by inspecting
    the function's source so a future refactor that loses
    the skip behaviour is caught here.
    """
    import inspect

    from evals.harness import test_contract_ingests_and_classifies

    source = inspect.getsource(test_contract_ingests_and_classifies)
    assert "pytest.skip" in source, (
        "Per-contract smoke test no longer calls pytest.skip on "
        "language mismatch. The --language=de run on an EN-only "
        "eval set will fail (no DE contracts to iterate) instead "
        "of cleanly skipping."
    )
    assert "--language" in source, (
        "Per-contract smoke test no longer reads the --language "
        "option. The filter won't apply to the per-contract tests."
    )
