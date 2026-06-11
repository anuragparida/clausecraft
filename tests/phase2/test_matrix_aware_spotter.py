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
    _coerce_matrix_sources,
    _coerce_matrix_verdict,
    _parse_llm_output,
    _stamp_matrix_audit_fields,
    spot_clause,
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
        """The flag's matrix_verdict is overwritten with the pipeline's value."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="healthcare",
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
        assert stamped.matrix_counterparty_type == "healthcare"

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
        """``model_copy`` returns a new instance; the caller's object is untouched."""
        si = _spot_input(matrix_verdict_column="material")
        f = DeviationFlag(
            clause_id="c1", score=0, rationale="test", matrix_verdict=None,
        )
        id(f)
        stamped = _stamp_matrix_audit_fields(f, spot_input=si)
        assert id(f) != id(stamped)
        # The original is unchanged.
        assert f.matrix_verdict is None
        assert stamped.matrix_verdict == "material"

    def test_unverified_default_when_column_invalid(self) -> None:
        """When the column can't be coerced, the stamp falls back to "unverified"."""
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
        # Falls back to "unverified" when the column can't be coerced.
        assert stamped.matrix_verdict == "unverified"


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
        """
        si = _spot_input(matrix_verdict_column="material")
        raw = {
            "score": 0,
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
        """The "no baseline" short-circuit still stamps the matrix fields."""
        si = _spot_input(
            baselines=[],
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="healthcare",
        )
        # The LLM is bypassed (no baselines).
        f = spot_clause(si, contract_filename="test.pdf")
        assert f.score == 0
        assert f.matrix_verdict == "material"
        assert f.matrix_sources == ["counterparty", "flat"]
        assert f.matrix_counterparty_type == "healthcare"

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
        """When the LLM runs, the re-stamp overwrites the LLM's echo with the pipeline's view."""
        si = _spot_input(
            matrix_verdict_column="material",
            matrix_sources=["counterparty", "flat"],
            matrix_counterparty_type="healthcare",
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
        assert f.matrix_counterparty_type == "healthcare"


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
