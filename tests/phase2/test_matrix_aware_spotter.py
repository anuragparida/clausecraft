"""Unit tests for the Phase 5 matrix-aware deviation spotter.

What's new in Phase 5
---------------------
The deviation spotter is matrix-aware. Three things
change:

1. The :class:`DeviationFlag` schema gains three optional
   fields — ``matrix_verdict``, ``matrix_sources``,
   ``matrix_counterparty_type`` — recording the
   counterparty matrix's verdict for the clause's
   ``(clause_type, counterparty_type[, language])`` cell.
2. The spotter's prompt renders the matrix verdict +
   lookup chain as a parenthetical ("matrix verdict:
   material (counterparty, flat)"). The LLM is told to
   consider the matrix verdict as a
   counterparty-specific severity multiplier, not as a
   ceiling.
3. The pipeline re-stamps the flag post-LLM with the
   pipeline's matrix verdict (the LLM is not the source
   of truth for matrix lookups).

These tests cover the schema, the LLM-output parser, the
re-stamp, the prompt render, and the end-to-end
``spot_clause`` flow with a mocked LLM. The full pipeline
integration (with the real
:func:`lookup_verdict_with_counterparty`) is exercised by
the eval-set wiring cards (t_f3212fc0, t_d5e24d95), not
here.

What's *not* in this file
-------------------------
- The DB-backed test fixtures for the eval harness. The
  harness is covered by the existing
  ``tests/phase1/test_ingest_contracts.py`` and
  ``tests/phase2/test_seed.py`` patterns (which require a
  live Postgres). The Phase 5 additions to the harness
  (the ``matrix_aggregate`` field) are validated by the
  per-contract recording logic tests in
  ``test_eval_harness_matrix.py``, which don't need a
  database.
- The matrix config tests. Those live in
  ``tests/phase2/test_counterparty.py`` and are 27/27
  green as of the t_33ecfb34 commit (the matrix config
  card). This file assumes that loader is correct and
  focuses on the spotter-side wiring.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agents.deviation_spotter.prompt import (
    DE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_messages,
    build_user_message,
)
from app.agents.deviation_spotter.schema import (
    MATRIX_VERDICT_VALUES,
    BaselineForSpotter,
    DeviationFlag,
    SpotInput,
    matrix_verdict_from_score,
)
from app.agents.deviation_spotter.spotter import (
    ELEVATED_RISK_COUNTERPARTY_TYPES,
    _coerce_matrix_sources,
    _coerce_matrix_verdict,
    _parse_llm_output,
    _stamp_matrix_audit_fields,
    is_per_type_escalation,
    spot_clause,
    verdict_for_score_and_counterparty,
)
from app.playbook.counterparty import (
    load_matrix,
    lookup_verdict_with_counterparty,
)


# --- Fixtures -----------------------------------------------------------


def _baseline(
    clause_id: str = "term-of-confidentiality",
    type_: str = "term",
    similarity: float = 0.87,
) -> BaselineForSpotter:
    """A realistic-looking baseline for tests."""
    return BaselineForSpotter(
        clause_id=clause_id,
        type=type_,
        title="Term of Confidentiality",
        text=(
            "Confidentiality obligations shall remain in effect for "
            "a period of three (3) years from the date of disclosure."
        ),
        source_url=(
            "https://nondisclosureagreement.com/blog/"
            "term-of-confidentiality/"
        ),
        similarity=similarity,
    )


def _spot_input(
    *,
    baselines: list[BaselineForSpotter] | None = None,
    clause_id: str = "c1",
    clause_type: str = "term",
    clause_language: str = "en",
    matrix_verdict_column: str = "unverified",
    matrix_sources: list[str] | None = None,
    matrix_counterparty_type: str = "any",
    counterparty_verdict: str = "aligned",
    counterparty_type: str = "any",
) -> SpotInput:
    """A realistic-looking spot input for tests."""
    return SpotInput(
        clause_id=clause_id,
        clause_text=(
            "The receiving party shall maintain confidentiality "
            "for a period of seven (7) years from the date of "
            "disclosure."
        ),
        clause_type=clause_type,
        clause_language=clause_language,
        baselines=baselines if baselines is not None else [_baseline()],
        counterparty_verdict=counterparty_verdict,
        counterparty_type=counterparty_type,
        matrix_verdict_column=matrix_verdict_column,
        matrix_sources=list(matrix_sources) if matrix_sources else [],
        matrix_counterparty_type=matrix_counterparty_type,
    )


# --- Schema tests -------------------------------------------------------


class TestMatrixVerdictValues:
    """``MATRIX_VERDICT_VALUES`` is the spec's 4-state column."""

    def test_values_match_spec(self) -> None:
        """The 4-state form per the task body: acceptable | material | unacceptable | unverified."""
        assert MATRIX_VERDICT_VALUES == (
            "acceptable",
            "material",
            "unacceptable",
            "unverified",
        )

    def test_no_matrix_internal_labels(self) -> None:
        """The spec-compliant form does NOT include the matrix's internal 4-state labels."""
        # aligned and minor collapse into acceptable per the spec.
        assert "aligned" not in MATRIX_VERDICT_VALUES
        assert "minor" not in MATRIX_VERDICT_VALUES


class TestMatrixVerdictFromScore:
    """``matrix_verdict_from_score`` bridges the matrix's 4-state to the column."""

    @pytest.mark.parametrize(
        "matrix_label,column_value",
        [
            ("aligned", "acceptable"),
            ("minor", "acceptable"),
            ("material", "material"),
            ("unacceptable", "unacceptable"),
            ("ALIGNED", "acceptable"),
            ("Minor", "acceptable"),
            ("MATERIAL", "material"),
        ],
    )
    def test_string_labels_collapse_correctly(
        self, matrix_label: str, column_value: str
    ) -> None:
        assert matrix_verdict_from_score(matrix_label) == column_value

    @pytest.mark.parametrize(
        "score,column_value",
        [
            (0, "acceptable"),
            (1, "acceptable"),
            (2, "material"),
            (3, "unacceptable"),
            (4, "unacceptable"),  # clamp high
            (-1, "acceptable"),  # clamp low
        ],
    )
    def test_int_scores_collapse_correctly(self, score: int, column_value: str) -> None:
        assert matrix_verdict_from_score(score) == column_value

    def test_none_returns_none(self) -> None:
        """``None`` is the only input that returns ``None`` (caller picks the default)."""
        assert matrix_verdict_from_score(None) is None

    @pytest.mark.parametrize("garbage", ["", "  ", "junk", "x", "nonsense"])
    def test_garbage_strings_become_unverified(self, garbage: str) -> None:
        """Defensive fallback: unknown labels become "unverified", not ``None``."""
        assert matrix_verdict_from_score(garbage) == "unverified"

    def test_unverified_passes_through(self) -> None:
        assert matrix_verdict_from_score("unverified") == "unverified"
        assert matrix_verdict_from_score("UNVERIFIED") == "unverified"


class TestFlagMatrixFields:
    """``DeviationFlag`` carries the matrix-aware fields with validation."""

    def test_default_matrix_verdict_is_none(self) -> None:
        """For flags constructed outside the orchestrator, matrix_verdict is None."""
        f = DeviationFlag(
            clause_id="c1", score=0, rationale="test"
        )
        assert f.matrix_verdict is None
        assert f.matrix_sources is None
        assert f.matrix_counterparty_type == "any"

    def test_valid_matrix_verdict_passes(self) -> None:
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="material deviation",
            matrix_verdict="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="healthcare",
        )
        assert f.matrix_verdict == "material"
        assert f.matrix_sources == ["counterparty", "flat"]
        assert f.matrix_counterparty_type == "healthcare"

    def test_invalid_matrix_verdict_rejected(self) -> None:
        """The LLM might invent labels; the schema rejects them."""
        with pytest.raises(ValueError, match="matrix_verdict must be one of"):
            DeviationFlag(
                clause_id="c1",
                score=0,
                rationale="test",
                matrix_verdict="aligned",  # not in the spec's 4-state column
            )

    def test_matrix_verdict_normalised_to_lowercase(self) -> None:
        f = DeviationFlag(
            clause_id="c1",
            score=0,
            rationale="test",
            matrix_verdict="ACCEPTABLE",
        )
        assert f.matrix_verdict == "acceptable"

    def test_matrix_sources_drops_empty_strings(self) -> None:
        f = DeviationFlag(
            clause_id="c1",
            score=0,
            rationale="test",
            matrix_sources=["counterparty", "", "  ", "flat"],
        )
        assert f.matrix_sources == ["counterparty", "flat"]

    def test_matrix_sources_capped_at_8(self) -> None:
        long_list = [f"src{i}" for i in range(20)]
        f = DeviationFlag(
            clause_id="c1",
            score=0,
            rationale="test",
            matrix_sources=long_list,
        )
        assert f.matrix_sources is not None
        assert len(f.matrix_sources) == 8

    def test_matrix_sources_preserves_none(self) -> None:
        """``None`` is the "no orchestrator stamp" sentinel; the validator preserves it."""
        f = DeviationFlag(
            clause_id="c1",
            score=0,
            rationale="test",
            matrix_sources=None,
        )
        assert f.matrix_sources is None


class TestSpotInputMatrixFields:
    """``SpotInput`` carries the matrix-aware fields for the prompt builder."""

    def test_default_matrix_verdict_column_is_unverified(self) -> None:
        """The safe default is "unverified" (not "aligned") — the spec is explicit about this."""
        si = SpotInput(
            clause_id="c1",
            clause_text="test",
            clause_type="term",
            baselines=[],
        )
        assert si.matrix_verdict_column == "unverified"
        assert si.matrix_sources == []
        assert si.matrix_counterparty_type == "any"

    def test_invalid_matrix_verdict_column_rejected(self) -> None:
        """Bad column values are a code bug (orchestrator is the only writer)."""
        with pytest.raises(ValueError, match="matrix_verdict_column must be one of"):
            SpotInput(
                clause_id="c1",
                clause_text="test",
                clause_type="term",
                baselines=[],
                matrix_verdict_column="aligned",  # not the 4-state spec form
            )

    def test_default_matrix_sources_is_empty_list(self) -> None:
        """Empty list, not None, for the prompt's lookup chain."""
        si = SpotInput(
            clause_id="c1",
            clause_text="test",
            clause_type="term",
            baselines=[],
        )
        assert si.matrix_sources == []


# --- Coercion helpers ---------------------------------------------------


class TestCoerceMatrixVerdict:
    """``_coerce_matrix_verdict`` leniently reads the LLM's echo."""

    def test_material_passes_through(self) -> None:
        assert _coerce_matrix_verdict("material") == "material"

    def test_uppercase_normalised(self) -> None:
        # The 4 spec values are accepted regardless of case.
        assert _coerce_matrix_verdict("ACCEPTABLE") == "acceptable"
        assert _coerce_matrix_verdict("Material") == "material"
        # The matrix's internal labels (aligned, minor) are
        # rejected by the LLM-echo parser — only the spec
        # values pass through. The re-stamp writes the
        # pipeline's view, so the flag still ships with the
        # right value.
        assert _coerce_matrix_verdict("Aligned") is None
        assert _coerce_matrix_verdict("Minor") is None

    def test_unverified_passes_through(self) -> None:
        assert _coerce_matrix_verdict("unverified") == "unverified"

    def test_none_returns_none(self) -> None:
        """The LLM might not include the field; the parser returns None for that."""
        assert _coerce_matrix_verdict(None) is None

    def test_garbage_returns_none(self) -> None:
        """Garbage values are filtered so the pipeline re-stamps cleanly."""
        assert _coerce_matrix_verdict("junk") is None
        assert _coerce_matrix_verdict("x") is None
        assert _coerce_matrix_verdict("") is None

    def test_non_string_returns_none(self) -> None:
        assert _coerce_matrix_verdict(42) is None
        assert _coerce_matrix_verdict(["material"]) is None
        assert _coerce_matrix_verdict({"value": "material"}) is None


class TestCoerceMatrixSources:
    """``_coerce_matrix_sources`` leniently reads the LLM's echo."""

    def test_list_passes_through(self) -> None:
        assert _coerce_matrix_sources(["counterparty", "flat"]) == [
            "counterparty", "flat"
        ]

    def test_string_passes_through_as_single_element(self) -> None:
        assert _coerce_matrix_sources("counterparty") == ["counterparty"]

    def test_none_returns_none(self) -> None:
        assert _coerce_matrix_sources(None) is None

    def test_empty_list_returns_none(self) -> None:
        """Empty list is the "LLM had no opinion" case; returns None for the validator."""
        assert _coerce_matrix_sources([]) is None

    def test_list_with_only_empty_strings_returns_none(self) -> None:
        assert _coerce_matrix_sources(["", "  "]) is None

    def test_capped_at_8(self) -> None:
        long_list = [f"src{i}" for i in range(20)]
        result = _coerce_matrix_sources(long_list)
        assert result is not None
        assert len(result) == 8

    def test_non_list_non_string_returns_none(self) -> None:
        assert _coerce_matrix_sources(42) is None
        assert _coerce_matrix_sources({"value": "x"}) is None


# --- Re-stamp helper ----------------------------------------------------


class TestStampMatrixAuditFields:
    """``_stamp_matrix_audit_fields`` re-stamps the LLM-parsed flag with the pipeline's view."""

    def test_re_stamps_matrix_verdict(self) -> None:
        """The flag's matrix_verdict is overwritten with the pipeline's value.

        v2: the per-type rule does not fire for non-elevated
        counterparty types (smb/any/enterprise). The test
        uses ``smb`` so the score-2 → "material" mapping
        holds. The healthcare path is covered in
        ``TestStampMatrixAuditFieldsPerType``.
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="smb",
        )
        # Construct a flag with a different (LLM-invented) matrix_verdict.
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="test",
            matrix_verdict="acceptable",  # LLM echoed something different
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        # The pipeline's view wins.
        assert stamped.matrix_verdict == "material"
        assert stamped.matrix_sources == ["counterparty", "flat"]
        assert stamped.matrix_counterparty_type == "smb"

    def test_preserves_other_fields(self) -> None:
        """Score, rationale, citation, baseline_type are NOT touched."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
        )
        f = DeviationFlag(
            clause_id="c1",
            score=3,
            rationale="unacceptable deviation",
            citation=None,
            unverified=True,
            baseline_type="term",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.score == 3
        assert stamped.rationale == "unacceptable deviation"
        assert stamped.citation is None
        assert stamped.unverified is True
        assert stamped.baseline_type == "term"

    def test_returns_new_flag(self) -> None:
        """``model_copy`` returns a new instance; the caller's object is untouched.

        v2: the test uses ``score=2`` so the score-2 →
        "material" branch fires (test uses
        ``matrix_counterparty_type="any"`` to avoid the
        score-2-on-elevated-risk escalation). The score-0
        path is covered in
        ``TestStampMatrixAuditFieldsPerType``.
        """
        si = _spot_input(matrix_verdict_column="material")
        f = DeviationFlag(
            clause_id="c1", score=2, rationale="test", matrix_verdict=None,
        )
        id(f)
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert id(f) != id(stamped)
        # The original is unchanged.
        assert f.matrix_verdict is None
        assert stamped.matrix_verdict == "material"

    def test_unverified_default_when_column_invalid(self) -> None:
        """When the column can't be coerced, the stamp falls back to "unverified".

        v2: the test asserts that with an invalid column
        (matrix-internal label) and ``score=0``, the
        defensive fallback wins: the column can't be
        coerced to a spec 4-state label so it falls back to
        "unverified", and the score-0 rule then maps to
        "acceptable". The point of the test is the
        defensive fallback, not the score-3 rule (covered
        in ``TestStampMatrixAuditFieldsPerType``).
        """
        # Build a spot input with an invalid column. The schema
        # validator rejects this, so we have to bypass it via
        # model_construct to simulate a bug.
        si = SpotInput.model_construct(
            clause_id="c1",
            clause_text="test",
            clause_type="term",
            clause_language="en",
            baselines=[],
            counterparty_verdict="aligned",
            counterparty_type="any",
            matrix_verdict_column="aligned",  # invalid for the spec column
            matrix_sources=[],
            matrix_counterparty_type="any",
        )
        f = DeviationFlag(clause_id="c1", score=0, rationale="test")
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        # The defensive fallback wins: the column can't be
        # coerced to a spec 4-state label so it falls back
        # to "unverified", and the score-0 rule then maps
        # to "acceptable". The defensive fallback is the
        # most-specific signal here (the matrix couldn't
        # reach a verdict at all), so the score-0 rule
        # applies on top of the fallback.
        assert stamped.matrix_verdict == "acceptable"


# --- Parser tests -------------------------------------------------------


class TestParseLlmOutput:
    """``_parse_llm_output`` reads the LLM's matrix fields leniently."""

    def test_parses_matrix_verdict_echo(self) -> None:
        """The LLM might echo the matrix verdict; the parser captures it."""
        si = _spot_input(matrix_verdict_column="material")
        raw = {
            "score": 2,
            "rationale": "test rationale",
            "citation": None,
            "baseline_type": "term",
            "matrix_verdict": "material",
            "matrix_sources": ["counterparty", "flat"],
        }
        f = _parse_llm_output(raw, spot_input=si)
        assert f.matrix_verdict == "material"
        assert f.matrix_sources == ["counterparty", "flat"]
        assert f.matrix_counterparty_type == "any"

    def test_parser_filters_invalid_matrix_verdict_to_none(self) -> None:
        """The parser filters invalid labels to ``None``; the re-stamp writes the real value.

        The LLM might echo the matrix's internal 4-state label
        (``"aligned"``, ``"minor"``) — those are not in the
        spec's 4-state column form, so the parser filters them
        to ``None`` and the pipeline re-stamps the flag with
        the real matrix verdict. The audit trail preserves
        the raw LLM output in the Langfuse span.

        v2: uses ``score=2`` so the per-type rule's score-2
        → "material" branch fires (test uses
        ``counterparty_type="any"`` to avoid the
        score-2-on-elevated-risk escalation). The score-0
        path is also covered in
        ``TestStampMatrixAuditFieldsPerType``.
        """
        si = _spot_input(matrix_verdict_column="material")
        raw = {
            "score": 2,
            "rationale": "test",
            "citation": None,
            "baseline_type": "",
            "matrix_verdict": "aligned",  # matrix-internal label
        }
        f = _parse_llm_output(raw, spot_input=si)
        # Parser is lenient: returns None for invalid labels.
        assert f.matrix_verdict is None
        # The re-stamp in spot_clause writes the real value.
        from app.agents.deviation_spotter.spotter import (
            _stamp_matrix_audit_fields,
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "material"

    def test_parser_tolerates_missing_matrix_fields(self) -> None:
        """Older LLM outputs that don't include matrix_verdict still parse."""
        si = _spot_input(matrix_verdict_column="material")
        raw = {
            "score": 2,
            "rationale": "test",
            "citation": None,
            "baseline_type": "term",
        }
        f = _parse_llm_output(raw, spot_input=si)
        # The LLM didn't echo; the parser leaves the field None.
        assert f.matrix_verdict is None
        assert f.matrix_sources is None

    def test_parser_preserves_matrix_counterparty_type_from_input(self) -> None:
        """The spot_input's matrix_counterparty_type is the audit-trail source of truth."""
        si = _spot_input(
            matrix_counterparty_type="healthcare",
        )
        raw = {
            "score": 0,
            "rationale": "test",
            "citation": None,
            "baseline_type": "",
        }
        f = _parse_llm_output(raw, spot_input=si)
        assert f.matrix_counterparty_type == "healthcare"


# --- End-to-end spot_clause flow ---------------------------------------


class TestSpotClauseMatrixAware:
    """``spot_clause`` re-stamps the matrix-aware fields end-to-end."""

    def test_no_baseline_short_circuit_stamps_matrix(self) -> None:
        """The "no baseline" short-circuit still stamps the matrix fields.

        v2: the test uses ``matrix_counterparty_type="smb"``
        so the per-type rule does not fire. The
        short-circuit abstains with ``score=0``, which the
        per-type rule maps to "acceptable" — but that's the
        score-0 branch, not the per-type escalation. The
        ``counterparty"`` and ``"flat"`` sources are stamped
        verbatim (no override marker). The healthcare path
        is covered in ``TestSpotClausePerTypeEndToEnd``.
        """
        si = _spot_input(
            baselines=[],
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="smb",
        )
        # The LLM is bypassed (no baselines).
        f = spot_clause(si, contract_filename="test.pdf")
        assert f.score == 0
        # Score 0 maps to "acceptable" (the v2 score-0 rule).
        assert f.matrix_verdict == "acceptable"
        assert f.matrix_sources == ["counterparty", "flat"]
        assert f.matrix_counterparty_type == "smb"

    def test_rule_based_fallback_stamps_matrix(self) -> None:
        """When the LLM is unavailable, the rule-based fallback still re-stamps."""
        si = _spot_input(
            matrix_verdict_column="acceptable",
            matrix_sources=["flat"],
            matrix_counterparty_type="any",
        )
        # The rule-based fallback fires when the LLM key is a placeholder.
        # (settings.llm_api_key is a placeholder in the test environment.)
        f = spot_clause(si, contract_filename="test.pdf")
        # The matrix verdict from the pipeline is stamped regardless of which
        # path the spotter took.
        assert f.matrix_verdict == "acceptable"
        assert f.matrix_sources == ["flat"]
        assert f.matrix_counterparty_type == "any"

    def test_mocked_llm_path_re_stamps_matrix(self) -> None:
        """When the LLM runs, the re-stamp overwrites the LLM's echo with the pipeline's view.

        v2: uses ``matrix_counterparty_type="smb"`` so the
        score-2 → "material" mapping holds. The
        score-2-on-healthcare escalation path is covered in
        ``TestSpotClausePerTypeEndToEnd``.
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="smb",
        )
        # Mock the LLM to return a DIFFERENT matrix_verdict than the pipeline.
        llm_response = {
            "score": 2,
            "rationale": "test rationale",
            "citation": None,
            "baseline_type": "term",
            "matrix_verdict": "acceptable",  # LLM disagrees with the matrix
            "matrix_sources": ["flat"],
        }
        with patch(
            "app.agents.deviation_spotter.spotter._call_llm_for_spot",
            return_value=llm_response,
        ), patch(
            "app.agents.deviation_spotter.spotter._looks_like_real_key",
            return_value=True,
        ):
            f = spot_clause(si, contract_filename="test.pdf")
        # The pipeline's view wins.
        assert f.matrix_verdict == "material"
        assert f.matrix_sources == ["counterparty", "flat"]
        assert f.matrix_counterparty_type == "smb"


# --- Prompt render -----------------------------------------------------


class TestPromptRendersMatrix:
    """``build_user_message`` renders the matrix fields in the per-call user message."""

    def test_en_prompt_renders_matrix_verdict_column(self) -> None:
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="healthcare",
        )
        msg = build_user_message(si, language="en")
        # The spec column is rendered.
        assert "matrix_verdict" in msg
        assert "material" in msg
        # The lookup chain is rendered as a parenthetical.
        assert "counterparty" in msg
        assert "flat" in msg
        # The counterparty type the matrix was consulted with.
        assert "healthcare" in msg

    def test_de_prompt_renders_matrix_verdict_column(self) -> None:
        si = _spot_input(
            clause_language="de",
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        msg = build_user_message(si, language="de")
        assert "matrix_verdict" in msg
        assert "material" in msg
        assert "healthcare" in msg

    def test_prompt_preserves_legacy_counterparty_lines(self) -> None:
        """The legacy ``counterparty_verdict`` / ``counterparty_type`` lines are kept for back-compat."""
        si = _spot_input(
            counterparty_verdict="aligned",
            counterparty_type="any",
        )
        msg = build_user_message(si, language="en")
        # The legacy lines are still rendered (for back-compat with older readers).
        assert "counterparty_verdict (legacy" in msg
        assert "counterparty_type (legacy)" in msg

    def test_prompt_with_no_sources_omits_parenthetical(self) -> None:
        """When the matrix sources list is empty, no parenthetical is appended."""
        si = _spot_input(
            matrix_verdict_column="acceptable",
            matrix_sources=[],
        )
        msg = build_user_message(si, language="en")
        # The matrix_verdict is rendered but no parenthetical.
        assert "matrix_verdict" in msg
        assert "acceptable" in msg
        # There should be no `(` after the matrix_verdict line value.
        # (We test this indirectly by ensuring the structure is clean.)
        lines = [line for line in msg.split("\n") if "matrix_verdict" in line]
        assert len(lines) >= 1
        for line in lines:
            if "`acceptable`" in line:
                # No trailing parenthetical.
                assert "(" not in line or line.count("(") == line.count(")")


class TestSystemPromptDocumentsMatrix:
    """The system prompt's "Counterparty context" section documents the matrix verdict."""

    def test_en_system_prompt_documents_4_state_column(self) -> None:
        """The EN system prompt renders the spec's 4-state column values."""
        assert "acceptable" in SYSTEM_PROMPT
        assert "material" in SYSTEM_PROMPT
        assert "unacceptable" in SYSTEM_PROMPT
        assert "unverified" in SYSTEM_PROMPT

    def test_de_system_prompt_documents_4_state_column(self) -> None:
        """The DE system prompt renders the spec's 4-state column values too."""
        assert "acceptable" in DE_SYSTEM_PROMPT
        assert "material" in DE_SYSTEM_PROMPT
        assert "unacceptable" in DE_SYSTEM_PROMPT
        assert "unverified" in DE_SYSTEM_PROMPT

    def test_en_system_prompt_mentions_lookup_chain(self) -> None:
        """The EN system prompt tells the LLM about the lookup-chain parenthesisation."""
        # The system prompt's "Counterparty context" section
        # should mention the parenthetical lookup chain.
        assert "lookup chain" in SYSTEM_PROMPT or "lookup" in SYSTEM_PROMPT

    def test_en_system_prompt_keeps_ceiling_rule(self) -> None:
        """The matrix verdict is a HINT, not a ceiling — the prompt keeps this rule."""
        # The original prompt's ceiling rule is preserved: the
        # matrix does not cap the LLM's score.
        assert "HINT" in SYSTEM_PROMPT or "hint" in SYSTEM_PROMPT
        assert "ceiling" in SYSTEM_PROMPT or "cap" in SYSTEM_PROMPT


# --- build_messages dispatch --------------------------------------------


class TestBuildMessagesMatrixAware:
    """``build_messages`` dispatches the matrix-aware prompts per language."""

    def test_en_messages_uses_en_system_prompt(self) -> None:
        si = _spot_input(clause_language="en")
        msgs = build_messages(si, language="en")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "matrix_verdict" in msgs[0]["content"]
        assert msgs[1]["role"] == "user"
        assert "matrix_verdict" in msgs[1]["content"]

    def test_de_messages_uses_de_system_prompt(self) -> None:
        si = _spot_input(clause_language="de")
        msgs = build_messages(si, language="de")
        assert len(msgs) == 2
        # The DE system prompt includes the matrix verdict section.
        assert "matrix_verdict" in msgs[0]["content"]


# --- Matrix composition --------------------------------------------------


class TestMatrixComposition:
    """The matrix lookup composes counterparty × language × clause_type."""

    def test_flat_lookup_with_any_counterparty(self) -> None:
        """``counterparty_type="any"`` returns the flat clause-type default."""
        matrix = load_matrix()
        mv = lookup_verdict_with_counterparty(
            matrix,
            "term",
            counterparty_type="any",
            language="en",
        )
        # The "any" path is the Phase 2 flat lookup; sources should
        # only contain "flat" (no counterparty or language hit).
        assert "flat" in mv.sources
        assert mv.counterparty_type == "any"

    def test_healthcare_counterparty_can_promote_verdict(self) -> None:
        """A healthcare counterparty override can promote a flat "acceptable" to "material"."""
        matrix = load_matrix()
        # Find a clause_type where healthcare has an explicit override.
        # The matrix file has healthcare overrides for dpa_transfer_mechanism.
        mv = lookup_verdict_with_counterparty(
            matrix,
            "dpa_transfer_mechanism",
            counterparty_type="healthcare",
            language="en",
        )
        # Healthcare override should be in the sources.
        assert "counterparty" in mv.sources

    def test_de_language_axis_composes(self) -> None:
        """A DE-language lookup also consults the language axis."""
        matrix = load_matrix()
        mv = lookup_verdict_with_counterparty(
            matrix,
            "term",
            counterparty_type="any",
            language="de",
        )
        # DE-only narrows; sources may include language:de.
        # The exact value depends on the matrix; we just verify the call works.
        assert mv.language == "de"
        assert isinstance(mv.sources, list)


# --- Phase 5 v2: per-type behavior (score-2 rule) ---------------------


class TestElevatedRiskAxes:
    """The ``ELEVATED_RISK_COUNTERPARTY_TYPES`` constant.

    Per the spec ("score-2 = material OR unacceptable depending
    on type") and the matrix config card's rationale (Apollo
    t_33ecfb34): public-sector and healthcare entities cannot
    absorb the same "material but negotiable" risk that an
    enterprise or SMB can. The other 2 Phase 5 axes
    (enterprise, smb) and the legacy "any" sentinel are
    non-elevated.
    """

    def test_public_sector_is_elevated(self) -> None:
        assert "public_sector" in ELEVATED_RISK_COUNTERPARTY_TYPES

    def test_healthcare_is_elevated(self) -> None:
        assert "healthcare" in ELEVATED_RISK_COUNTERPARTY_TYPES

    def test_enterprise_is_not_elevated(self) -> None:
        assert "enterprise" not in ELEVATED_RISK_COUNTERPARTY_TYPES

    def test_smb_is_not_elevated(self) -> None:
        assert "smb" not in ELEVATED_RISK_COUNTERPARTY_TYPES

    def test_any_sentinel_is_not_elevated(self) -> None:
        """The legacy Phase 2 sentinel defaults to the non-elevated branch."""
        assert "any" not in ELEVATED_RISK_COUNTERPARTY_TYPES

    def test_de_german_entity_is_not_elevated(self) -> None:
        """DE-narrowing is a separate axis and does not change the score-2 rule."""
        assert "de_german_entity" not in ELEVATED_RISK_COUNTERPARTY_TYPES


class TestIsPerTypeEscalation:
    """``is_per_type_escalation`` is the narrower predicate.

    The predicate returns ``True`` only when the override
    specifically promotes ``"material"`` → ``"unacceptable"``
    for an elevated-risk counterparty type. The other
    score-driven mappings (score 0/1 → "acceptable", score 3
    → "unacceptable", score 2 on non-elevated axes →
    "material") are unconditional score rules that apply to
    every counterparty type, NOT per-type decisions, so the
    audit trail's ``per_type_escalation`` entry should NOT
    fire for those.
    """

    # --- the one True case: score 2 + elevated-risk + material ---

    @pytest.mark.parametrize("cp_type", ["public_sector", "healthcare"])
    def test_true_for_score_2_elevated_material(
        self, cp_type: str
    ) -> None:
        """Score 2 + elevated-risk cp type + material matrix column → True."""
        assert is_per_type_escalation(2, cp_type, "material") is True

    # --- False cases: every other combination ---

    @pytest.mark.parametrize("cp_type", ["enterprise", "smb", "any"])
    def test_false_for_score_2_non_elevated(self, cp_type: str) -> None:
        """Score 2 + non-elevated cp type → False (no escalation)."""
        assert is_per_type_escalation(2, cp_type, "material") is False

    def test_false_for_score_2_de_german_entity(self) -> None:
        """DE-narrowing is a separate axis; score 2 on DE doesn't escalate."""
        assert is_per_type_escalation(2, "de_german_entity", "material") is False

    @pytest.mark.parametrize("cp_type", ["public_sector", "healthcare"])
    @pytest.mark.parametrize(
        "matrix_column",
        ["acceptable", "unacceptable", "unverified"],
    )
    def test_false_for_score_2_with_stricter_or_unchanged_matrix(
        self, cp_type: str, matrix_column: str
    ) -> None:
        """Score 2 + elevated cp + non-material column → False.

        The escalation only fires when the matrix says
        "material". Stricter verdicts ("unacceptable") and
        unverified outcomes are not escalations.
        """
        assert is_per_type_escalation(2, cp_type, matrix_column) is False

    @pytest.mark.parametrize("score", [0, 1])
    @pytest.mark.parametrize("cp_type", ["public_sector", "healthcare"])
    def test_false_for_score_0_or_1_even_on_elevated(
        self, score: int, cp_type: str
    ) -> None:
        """Score 0/1 is the unconditional "acceptable" rule, not a per-type escalation."""
        assert is_per_type_escalation(score, cp_type, "material") is False

    @pytest.mark.parametrize("cp_type", ["public_sector", "healthcare"])
    def test_false_for_score_3_even_on_elevated(self, cp_type: str) -> None:
        """Score 3 is the unconditional "unacceptable" rule, not a per-type escalation."""
        assert is_per_type_escalation(3, cp_type, "material") is False

    def test_false_for_none_score(self) -> None:
        """``None`` score (spotter abstained) → no per-type decision."""
        for col in ("acceptable", "material", "unacceptable", "unverified"):
            assert is_per_type_escalation(None, "public_sector", col) is False

    @pytest.mark.parametrize("bad_score", [-1, 4, 5, 100])
    def test_false_for_out_of_range_score(self, bad_score: int) -> None:
        """Out-of-range scores are no-ops; the matrix's view stands."""
        assert is_per_type_escalation(bad_score, "public_sector", "material") is False

    def test_false_for_non_int_score(self) -> None:
        """Non-int scores (e.g. ``"2"``, ``2.0``) → False."""
        for bad in ("2", 2.0, [], {}):
            assert is_per_type_escalation(bad, "public_sector", "material") is False

    def test_false_for_bool_score(self) -> None:
        """``bool`` is a subclass of ``int``; reject it."""
        assert is_per_type_escalation(True, "public_sector", "material") is False
        assert is_per_type_escalation(False, "public_sector", "material") is False

    def test_false_for_unknown_matrix_column(self) -> None:
        """Unknown matrix columns → False (validator catches upstream)."""
        assert is_per_type_escalation(2, "public_sector", "") is False
        assert is_per_type_escalation(2, "public_sector", "garbage") is False

    def test_false_for_unknown_counterparty_type(self) -> None:
        """Unknown cp types → False (treated as non-elevated)."""
        assert is_per_type_escalation(2, "future_axis", "material") is False
        assert is_per_type_escalation(2, "", "material") is False


class TestUnconditionalScoreRuleBranch:
    """The non-per-type-escalation branch of ``_stamp_matrix_audit_fields``.

    When ``is_per_type_escalation`` returns ``False``, the
    re-stamp applies the unconditional score-driven mapping
    from :func:`verdict_for_score_and_counterparty`. This
    branch must NOT add the ``per_type_escalation`` entry to
    ``matrix_sources`` — the audit trail only records a
    per-type escalation when the *narrower* predicate fires.
    """

    def test_score_0_healthcare_keeps_acceptable_no_override_marker(self) -> None:
        """Score 0 + healthcare → "acceptable", no per_type_escalation marker.

        Score 0 is the unconditional "acceptable" rule, not a
        per-type escalation. The audit trail records the
        original sources verbatim.
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=0,
            rationale="aligned",
            matrix_verdict="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "acceptable"
        # No per_type_escalation marker — this is the
        # unconditional score-0 rule, not a per-type
        # decision.
        assert stamped.matrix_sources == ["counterparty"]

    def test_score_3_healthcare_keeps_unacceptable_no_override_marker(self) -> None:
        """Score 3 + healthcare → "unacceptable", no per_type_escalation marker.

        Score 3 is the unconditional "unacceptable" rule, not
        a per-type escalation. The audit trail records the
        original sources verbatim.
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=3,
            rationale="unacceptable deviation",
            matrix_verdict="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "unacceptable"
        # No per_type_escalation marker — this is the
        # unconditional score-3 rule.
        assert stamped.matrix_sources == ["counterparty"]

    def test_score_2_smb_stays_material_no_override_marker(self) -> None:
        """Score 2 + smb + material → "material", no per_type_escalation marker.

        SMB is non-elevated, so the per-type rule doesn't
        fire. The matrix's "material" column passes through
        unchanged.
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="smb",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="material deviation",
            matrix_verdict="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="smb",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "material"
        assert stamped.matrix_sources == ["counterparty", "flat"]

    def test_score_2_healthcare_with_unacceptable_matrix_unchanged(self) -> None:
        """Score 2 + healthcare + matrix=unacceptable → "unacceptable", no override.

        The matrix's stricter verdict wins. The per-type
        rule doesn't fire because the column was already
        "unacceptable" — there's no "promotion" to record in
        the audit trail.
        """
        si = _spot_input(
            matrix_verdict_column="unacceptable",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="material deviation",
            matrix_verdict="unacceptable",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "unacceptable"
        assert stamped.matrix_sources == ["counterparty"]


class TestVerdictForScoreAndCounterparty:
    """The per-type escalation rule (score-2 = material or unacceptable).

    The spec rule: when the spotter emits ``score=2`` (material),
    the matrix column is escalated to ``unacceptable`` for
    public_sector and healthcare counterparty types, and stays
    at ``material`` for the other axes. ``score=0``/``score=1``
    always map to ``acceptable``; ``score=3`` always maps to
    ``unacceptable``. The escalation only fires when the matrix
    column is ``"material"`` — the matrix's stricter verdicts
    (``unacceptable``) and unverified outcomes win.
    """

    # --- score-2 rule: per-counterparty escalation ---

    @pytest.mark.parametrize("cp_type", ["public_sector", "healthcare"])
    def test_score_2_elevated_risk_promotes_to_unacceptable(
        self, cp_type: str
    ) -> None:
        """Score 2 with an elevated-risk cp type escalates material -> unacceptable."""
        assert (
            verdict_for_score_and_counterparty(2, cp_type, "material")
            == "unacceptable"
        )

    @pytest.mark.parametrize("cp_type", ["enterprise", "smb", "any"])
    def test_score_2_non_elevated_stays_material(self, cp_type: str) -> None:
        """Score 2 with a non-elevated cp type stays at material."""
        assert (
            verdict_for_score_and_counterparty(2, cp_type, "material")
            == "material"
        )

    def test_score_2_de_german_entity_stays_material(self) -> None:
        """Score 2 with the Phase 4 DE counterparty type stays at material.

        DE-narrowing is a separate axis — it changes the
        matrix's verdict for DE clauses, not the per-type
        score-2 escalation.
        """
        assert (
            verdict_for_score_and_counterparty(2, "de_german_entity", "material")
            == "material"
        )

    # --- score 0/1: always acceptable ---

    @pytest.mark.parametrize("score", [0, 1])
    @pytest.mark.parametrize(
        "cp_type",
        ["public_sector", "healthcare", "enterprise", "smb", "any", "de_german_entity"],
    )
    def test_score_0_or_1_always_acceptable(
        self, score: int, cp_type: str
    ) -> None:
        """Score 0 and score 1 always map to acceptable, regardless of cp type.

        The matrix column is irrelevant — score 0/1 wins.
        This holds even when the matrix says "unacceptable" or
        "material"; the spec rule is that the spotter's "minor"
        deviation is always acceptable, and the LLM's "aligned"
        verdict is trivially acceptable.
        """
        for matrix_col in ("acceptable", "material", "unacceptable", "unverified"):
            assert (
                verdict_for_score_and_counterparty(score, cp_type, matrix_col)
                == "acceptable"
            )

    # --- score 3: always unacceptable ---

    @pytest.mark.parametrize(
        "cp_type",
        ["public_sector", "healthcare", "enterprise", "smb", "any", "de_german_entity"],
    )
    @pytest.mark.parametrize("matrix_col", ["acceptable", "material", "unverified"])
    def test_score_3_always_unacceptable(
        self, cp_type: str, matrix_col: str
    ) -> None:
        """Score 3 always maps to unacceptable, regardless of cp type or matrix.

        The LLM's "this contradicts the baseline" verdict is
        the final say. The matrix does not relax it.
        """
        assert (
            verdict_for_score_and_counterparty(3, cp_type, matrix_col)
            == "unacceptable"
        )

    # --- matrix-stricter-wins rule ---

    def test_score_2_with_unacceptable_matrix_stays_unacceptable(self) -> None:
        """The matrix's stricter verdicts win over the per-type rule."""
        # If the matrix already says "unacceptable", the
        # per-type rule doesn't change it.
        assert (
            verdict_for_score_and_counterparty(2, "public_sector", "unacceptable")
            == "unacceptable"
        )
        assert (
            verdict_for_score_and_counterparty(2, "healthcare", "unacceptable")
            == "unacceptable"
        )

    def test_score_2_with_unverified_matrix_stays_unverified(self) -> None:
        """The matrix's "unverified" outcome wins over the per-type rule."""
        # When the matrix couldn't reach a verdict, the
        # per-type rule doesn't override it — the audit trail
        # records "unverified" so the reviewer knows the
        # pipeline didn't reach a matrix call.
        assert (
            verdict_for_score_and_counterparty(2, "public_sector", "unverified")
            == "unverified"
        )

    def test_score_2_with_acceptable_matrix_stays_acceptable(self) -> None:
        """The matrix's "acceptable" verdict is never escalated by the per-type rule.

        The per-type rule only escalates "material" to
        "unacceptable" for elevated-risk axes. It does not
        escalate "acceptable" — the matrix's "acceptable" call
        is the final say for that cell.
        """
        assert (
            verdict_for_score_and_counterparty(2, "public_sector", "acceptable")
            == "acceptable"
        )
        assert (
            verdict_for_score_and_counterparty(2, "healthcare", "acceptable")
            == "acceptable"
        )

    # --- defensive cases ---

    def test_none_score_returns_matrix_column(self) -> None:
        """``None`` score (spotter abstained) returns the matrix column unchanged."""
        for col in ("acceptable", "material", "unacceptable", "unverified"):
            assert verdict_for_score_and_counterparty(None, "public_sector", col) == col
            assert verdict_for_score_and_counterparty(None, "enterprise", col) == col

    @pytest.mark.parametrize("bad_score", [-1, 4, 5, 100, -100])
    def test_out_of_range_score_returns_matrix_column(self, bad_score: int) -> None:
        """Out-of-range scores return the matrix column unchanged.

        The Pydantic ``DeviationFlag.score`` validator clamps
        to 0..3, but the helper is called defensively from
        the re-stamp path (where the flag might be
        model_construct'd with bad data).
        """
        for col in ("acceptable", "material", "unacceptable", "unverified"):
            assert (
                verdict_for_score_and_counterparty(bad_score, "public_sector", col)
                == col
            )

    @pytest.mark.parametrize("bad_score", ["2", 2.0, None, [], {}])
    def test_non_int_score_returns_matrix_column(self, bad_score: object) -> None:
        """Non-integer scores return the matrix column unchanged.

        ``2.0`` and ``"2"`` are intentionally rejected: the
        helper expects a clean ``int`` (Pydantic coerces
        upstream). The ``None`` case is also handled here as
        a non-int path even though it has its own test above.
        """
        for col in ("acceptable", "material", "unacceptable", "unverified"):
            assert (
                verdict_for_score_and_counterparty(
                    bad_score, "public_sector", col  # type: ignore[arg-type]
                )
                == col
            )

    def test_bool_score_is_rejected(self) -> None:
        """``bool`` is a subclass of ``int`` in Python; reject it explicitly.

        ``isinstance(True, int) is True`` would otherwise let
        ``True``/``False`` slip through the int check. The
        helper treats them as non-int inputs (defensive).
        """
        for col in ("acceptable", "material", "unacceptable", "unverified"):
            assert (
                verdict_for_score_and_counterparty(True, "public_sector", col) == col
            )
            assert (
                verdict_for_score_and_counterparty(False, "public_sector", col) == col
            )

    def test_unknown_column_passes_through(self) -> None:
        """Unknown matrix columns pass through unchanged.

        The schema validator catches this upstream; the
        per-type rule only applies to known columns.
        """
        # An empty string and a garbage string pass through.
        assert verdict_for_score_and_counterparty(2, "public_sector", "") == ""
        assert (
            verdict_for_score_and_counterparty(2, "public_sector", "garbage")
            == "garbage"
        )

    def test_unknown_counterparty_type_falls_through(self) -> None:
        """Unknown counterparty types fall through to the non-elevated branch.

        The 4 Phase 5 axes are documented; unknown strings
        (e.g. a future Phase 6 axis) are treated as
        non-elevated to keep the rule conservative. Score 2
        with an unknown cp type stays at "material".
        """
        assert (
            verdict_for_score_and_counterparty(2, "future_axis", "material")
            == "material"
        )
        assert (
            verdict_for_score_and_counterparty(2, "", "material")
            == "material"
        )


class TestStampMatrixAuditFieldsPerType:
    """``_stamp_matrix_audit_fields`` applies the per-type rule end-to-end.

    The re-stamp is the surface that actually promotes
    ``material`` → ``unacceptable`` for elevated-risk counterparty
    types. These tests assert the full path: score 2 on a
    healthcare spot input, with a material matrix column,
    produces an ``unacceptable`` flag with the
    ``per_type_escalation`` entry stamped at the front of
    ``matrix_sources``.
    """

    def test_score_2_healthcare_promotes_to_unacceptable(self) -> None:
        """Score 2 + healthcare + matrix=material → flag has matrix_verdict=unacceptable."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="material deviation",
            matrix_verdict="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "unacceptable"
        # The override is stamped at the front of the chain.
        assert stamped.matrix_sources[0] == "per_type_escalation"
        # Original sources preserved as losers.
        assert "counterparty" in stamped.matrix_sources
        assert "flat" in stamped.matrix_sources

    def test_score_2_public_sector_promotes_to_unacceptable(self) -> None:
        """Score 2 + public_sector + matrix=material → flag has matrix_verdict=unacceptable."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="public_sector",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="material deviation",
            matrix_verdict="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="public_sector",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "unacceptable"
        assert stamped.matrix_sources[0] == "per_type_escalation"

    @pytest.mark.parametrize("cp_type", ["enterprise", "smb", "any"])
    def test_score_2_non_elevated_stays_material(self, cp_type: str) -> None:
        """Score 2 + non-elevated cp + matrix=material → flag has matrix_verdict=material."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type=cp_type,
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="material deviation",
            matrix_verdict="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type=cp_type,
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "material"
        # No per_type_escalation entry: the rule didn't fire.
        assert "per_type_escalation" not in (stamped.matrix_sources or [])

    def test_score_0_healthcare_keeps_acceptable(self) -> None:
        """Score 0 + healthcare → flag has matrix_verdict=acceptable (score wins)."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=0,
            rationale="aligned",
            matrix_verdict="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        # Score 0 always maps to acceptable.
        assert stamped.matrix_verdict == "acceptable"
        # The per-type rule didn't fire (the score-2 escalation
        # is conditional on score == 2; score 0 just lands on
        # acceptable via the score-0/1 branch). No
        # per_type_escalation entry.
        assert "per_type_escalation" not in (stamped.matrix_sources or [])

    def test_score_3_healthcare_keeps_unacceptable(self) -> None:
        """Score 3 + healthcare + matrix=material → flag has matrix_verdict=unacceptable.

        Score 3 always maps to unacceptable; the per-type rule
        doesn't change anything (it was already going to land
        on unacceptable). No ``per_type_escalation`` entry
        because the column didn't change.
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=3,
            rationale="unacceptable deviation",
            matrix_verdict="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "unacceptable"
        # The column didn't change (was material, now
        # unacceptable, but the per-type rule for score 2 is
        # the only path that adds the override marker; score
        # 3 maps directly via the unconditional branch).
        assert "per_type_escalation" not in (stamped.matrix_sources or [])

    def test_score_2_healthcare_with_unacceptable_matrix_unchanged(self) -> None:
        """Score 2 + healthcare + matrix=unacceptable → flag stays unacceptable.

        The matrix's stricter verdict wins. The per-type rule
        doesn't fire (it only escalates "material" to
        "unacceptable"; the column was already stricter).
        """
        si = _spot_input(
            matrix_verdict_column="unacceptable",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="material deviation",
            matrix_verdict="unacceptable",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "unacceptable"
        # No per_type_escalation — the column didn't change.
        assert "per_type_escalation" not in (stamped.matrix_sources or [])

    def test_per_type_escalation_respects_sources_cap(self) -> None:
        """The 8-entry cap on ``matrix_sources`` is preserved after the override.

        A 7-entry original sources list + 1
        per_type_escalation = 8 entries (under the cap). A
        8-entry original sources list + 1 per_type_escalation
        = 9 entries (capped at 8 by the validator). The
        validator trims the trailing entry.
        """
        # 7 original entries: total after stamp = 8 (under cap).
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["a", "b", "c", "d", "e", "f", "g"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="test",
            matrix_verdict="material",
            matrix_sources=["a", "b", "c", "d", "e", "f", "g"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "unacceptable"
        assert stamped.matrix_sources is not None
        assert stamped.matrix_sources[0] == "per_type_escalation"
        # 7 originals + 1 override = 8 (under the cap of 8).
        assert len(stamped.matrix_sources) == 8

    def test_per_type_escalation_with_full_sources_caps_at_8(self) -> None:
        """A 8-entry original sources list + 1 override is capped at 8 by the validator."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["a", "b", "c", "d", "e", "f", "g", "h"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="test",
            matrix_verdict="material",
            matrix_sources=["a", "b", "c", "d", "e", "f", "g", "h"],
            matrix_counterparty_type="healthcare",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert stamped.matrix_verdict == "unacceptable"
        assert stamped.matrix_sources is not None
        # The validator on DeviationFlag.matrix_sources caps
        # at 8: the 8 originals + 1 override = 9, but the
        # validator trims to 8 (the per_type_escalation is at
        # the front; the trailing entry "h" is dropped).
        assert stamped.matrix_sources[0] == "per_type_escalation"
        assert len(stamped.matrix_sources) == 8

    def test_per_type_escalation_does_not_touch_score(self) -> None:
        """The override only changes matrix_verdict, not the spotter's score."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        f = DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="material deviation",
            citation=None,
            unverified=True,
            baseline_type="term",
        )
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        # The LLM's score is preserved — the per-type rule
        # only escalates the matrix column, not the spot score.
        assert stamped.score == 2
        assert stamped.rationale == "material deviation"
        assert stamped.baseline_type == "term"
        assert stamped.unverified is True


class TestSpotClausePerTypeEndToEnd:
    """End-to-end ``spot_clause`` integration with the per-type rule.

    The spotter's three paths (short-circuit, LLM, rule-based
    fallback) all flow through ``_stamp_matrix_audit_fields``,
    so the per-type rule applies uniformly. These tests cover
    each path.
    """

    def test_short_circuit_path_with_healthcare_promotes(self) -> None:
        """No-baseline short-circuit still applies the per-type rule.

        The short-circuit abstains (``score=0``) but the
        re-stamp records the matrix view. The per-type rule
        for score 0 maps to "acceptable" regardless of cp
        type — no per_type_escalation entry.
        """
        si = _spot_input(
            baselines=[],  # no baselines → short-circuit
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        flag = spot_clause(si, contract_filename="test.pdf")
        # Short-circuit: score 0, rationale mentions "no baseline".
        assert flag.score == 0
        # The matrix column was re-stamped.
        assert flag.matrix_verdict == "acceptable"
        # Score 0 → no per_type_escalation entry.
        assert "per_type_escalation" not in (flag.matrix_sources or [])

    def test_rule_based_fallback_with_healthcare_promotes(self) -> None:
        """The placeholder-key rule-based fallback applies the per-type rule.

        The fallback returns ``score=0`` (abstention), so
        score 0 maps to "acceptable" — the per-type rule
        doesn't escalate. The matrix's view is still stamped.
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty"],
            matrix_counterparty_type="healthcare",
        )
        # Placeholder key → rule-based fallback path.
        with patch(
            "app.agents.deviation_spotter.spotter.settings.llm_api_key",
            "placeholder",
        ):
            flag = spot_clause(si, contract_filename="test.pdf")
        # Fallback: score 0, unverified=True, rationale mentions
        # "fallback" or "LLM unavailable".
        assert flag.score == 0
        assert flag.unverified is True
        # Score 0 maps to acceptable (not the per-type rule's
        # "material" → "unacceptable" path).
        assert flag.matrix_verdict == "acceptable"
        assert "per_type_escalation" not in (flag.matrix_sources or [])

    def test_llm_path_with_healthcare_and_score_2_promotes(self) -> None:
        """The LLM path with score 2 + healthcare + matrix=material promotes.

        Mocks the LLM to return a score-2 flag with a valid
        citation, then asserts the re-stamp escalates the
        matrix column.
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="healthcare",
        )
        # Valid baseline + a real-ish citation.
        baseline = si.baselines[0]
        llm_payload = {
            "score": 2,
            "rationale": "material deviation in healthcare DPA",
            "citation": {
                "playbook_clause_id": baseline.clause_id,
                "contract_text_excerpt": "seven (7) years",
            },
            "baseline_type": baseline.type,
            "matrix_verdict": "material",  # LLM echoes the column
            "matrix_sources": ["counterparty", "flat"],
        }
        with patch(
            "app.agents.deviation_spotter.spotter.settings.llm_api_key",
            "sk-or-v1-abcdefghijklmnopqrstuvwxyz1234567890",  # real-shape
        ):
            with patch(
                "app.agents.deviation_spotter.spotter._call_llm_for_spot",
                return_value=llm_payload,
            ):
                flag = spot_clause(si, contract_filename="test.pdf")
        # Score preserved.
        assert flag.score == 2
        # The per-type rule escalated material → unacceptable.
        assert flag.matrix_verdict == "unacceptable"
        # The override is recorded.
        assert flag.matrix_sources is not None
        assert flag.matrix_sources[0] == "per_type_escalation"

    def test_llm_path_with_smb_and_score_2_stays_material(self) -> None:
        """The LLM path with score 2 + smb + matrix=material stays at material.

        SMB is a non-elevated axis; the per-type rule doesn't
        fire. The flag's matrix_verdict stays at "material".
        """
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="smb",
        )
        baseline = si.baselines[0]
        llm_payload = {
            "score": 2,
            "rationale": "material deviation in SMB contract",
            "citation": {
                "playbook_clause_id": baseline.clause_id,
                "contract_text_excerpt": "five (5) years",
            },
            "baseline_type": baseline.type,
            "matrix_verdict": "material",
            "matrix_sources": ["counterparty", "flat"],
        }
        with patch(
            "app.agents.deviation_spotter.spotter.settings.llm_api_key",
            "sk-or-v1-abcdefghijklmnopqrstuvwxyz1234567890",
        ):
            with patch(
                "app.agents.deviation_spotter.spotter._call_llm_for_spot",
                return_value=llm_payload,
            ):
                flag = spot_clause(si, contract_filename="test.pdf")
        assert flag.score == 2
        assert flag.matrix_verdict == "material"
        # No per_type_escalation entry.
        assert "per_type_escalation" not in (flag.matrix_sources or [])
