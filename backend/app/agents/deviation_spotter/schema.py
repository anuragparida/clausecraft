"""Pydantic models for the deviation spotter agent.

Three models:

- :class:`Citation` — the "show your work" pointer. A spotter flag
  with a non-zero score is useless without one.
- :class:`DeviationFlag` — the spotter's output. Typed, validated,
  and the shape the eval harness (Phase 2) compares against the
  golden set.
- :class:`SpotInput` — the input the spotter takes per call. The
  contract clause, the top-3 playbook baselines, and the
  counterparty context (the counterparty matrix's flat verdict for
  the clause's type — Phase 2 ships flat, Phase 5 adds the 2D
  lookup).

Why ``citation`` is ``Optional[Citation]`` instead of a required
field
----------------------------------------------------------------
A flag with a non-zero score AND no citation is **the** error mode
the spec calls out as critical. The schema doesn't make the field
mandatory because:

1. The "I don't know" / "agent declined" path needs to return
   ``score=0, citation=None`` — that's a valid output the UI
   renders as "no deviation" (the agent abstained).
2. The "no baseline" path needs to return ``score=0, citation=None,
   unverified=True, rationale="no matching playbook clause"``.

But the **enforcement** is in :mod:`.spotter`: when the LLM emits a
non-zero score, the parser flips ``unverified=True`` if the
citation is missing or doesn't point to a real clause_id in the
top-k list. The schema is the spec; the parser is the enforcer.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --- Score scale --------------------------------------------------------


class DeviationScore:
    """Score constants — also exported as the :class:`DeviationFlag.score`
    field's allowed values (the parser coerces to int and validates 0..3).

    0 = aligned (matches the baseline, or no baseline to compare against)
    1 = minor deviation (cosmetic / one-line wording, no impact)
    2 = material deviation (changes the meaning, may be acceptable with
        negotiation)
    3 = unacceptable (contradicts the baseline, e.g. a perpetual term in
        a "3 years" baseline)
    """

    ALIGNED = 0
    MINOR = 1
    MATERIAL = 2
    UNACCEPTABLE = 3


# --- Phase 5: matrix verdict column -----------------------------------


# The spec's 4-state column for the deviation table's "matrix verdict"
# column. This is the *column* form — distinct from the matrix's
# internal 4-state labels (``aligned`` / ``minor`` / ``material`` /
# ``unacceptable``) used inside the YAML config. The bridging is in
# :func:`matrix_verdict_from_score` below.
#
# Why a separate column form
# --------------------------
# The matrix file (Phase 2 + Phase 5) records per-cell verdicts in
# the matrix's internal labels (``aligned`` for "default", ``minor``
# for "slightly narrow", ``material``, ``unacceptable``). The UI's
# deviation table, per the spec, renders a separate "matrix verdict"
# column with 4 states that the spec calls ``acceptable`` (the union
# of ``aligned`` and ``minor`` — both mean "the spotter can
# comfortably let this through"), ``material``, ``unacceptable``,
# and ``unverified`` (the pipeline couldn't reach a verdict).
#
# The LLM only ever sees the column form; the matrix file is
# internal-only. ``matrix_verdict_from_score`` is the only place the
# two label systems meet.
MATRIX_VERDICT_VALUES: tuple[str, ...] = (
    "acceptable",
    "material",
    "unacceptable",
    "unverified",
)


def matrix_verdict_from_score(
    score: Optional[int | str],
) -> Optional[str]:
    """Bridge the matrix's internal 4-state label to the spec's column form.

    The matrix emits one of four internal labels for each
    ``(clause_type, counterparty_type[, language])`` cell:

    - ``aligned`` (default — "the cell is fine as-is")
    - ``minor`` (slightly narrow — "the cell is more conservative
      than the flat default but not yet a deal-breaker")
    - ``material`` (the matrix thinks the spotter should escalate
      this cell)
    - ``unacceptable`` (the matrix's deal-breaker)

    The spec's column form is the union of ``aligned`` and
    ``minor`` collapsed into ``acceptable``, plus the
    ``material`` / ``unacceptable`` / ``unverified`` columns.

    Parameters
    ----------
    score
        A matrix label (``"aligned"`` / ``"minor"`` / ``"material"``
        / ``"unacceptable"`` / ``"unverified"``), or a numeric
        ``DeviationScore`` value (0..3 — :class:`DeviationScore`
        ordering is the same as the matrix's). ``None`` returns
        ``None`` (the caller picks the default — typically
        ``"unverified"``).

    Returns
    -------
    Optional[str]
        The spec's 4-state column form, or ``None`` when the
        caller passed ``None``. **Garbage inputs collapse to
        ``"unverified"``** — we never propagate a label the UI
        can't render.

    Examples
    --------
    >>> matrix_verdict_from_score("aligned")
    'acceptable'
    >>> matrix_verdict_from_score("minor")
    'acceptable'
    >>> matrix_verdict_from_score("material")
    'material'
    >>> matrix_verdict_from_score("unacceptable")
    'unacceptable'
    >>> matrix_verdict_from_score(0)
    'acceptable'
    >>> matrix_verdict_from_score(2)
    'material'
    >>> matrix_verdict_from_score(None) is None
    True
    >>> matrix_verdict_from_score("junk")
    'unverified'
    """
    if score is None:
        return None
    # Numeric path (DeviationScore constants 0..3): the matrix
    # uses the same scale, so the bridge is direct. Score 0/1 →
    # "acceptable" (aligned/minor), 2 → "material", 3 →
    # "unacceptable". The Pydantic field already validates 0..3
    # upstream; defensive clamp is belt-and-braces for callers
    # that pass arbitrary ints.
    if isinstance(score, int) and not isinstance(score, bool):
        if score <= 1:
            return "acceptable"
        if score == 2:
            return "material"
        return "unacceptable"
    # String path (matrix label, or spec column passthrough).
    # Case-insensitive, whitespace-trimmed.
    if isinstance(score, str):
        normalised = score.strip().lower()
        if not normalised:
            return "unverified"
        # Spec column form is a passthrough.
        if normalised in MATRIX_VERDICT_VALUES:
            return normalised
        # Matrix internal labels collapse to the spec column.
        if normalised == "aligned":
            return "acceptable"
        if normalised == "minor":
            return "acceptable"
        if normalised in ("material", "unacceptable", "unverified"):
            return normalised
    # Garbage input (unknown label, non-int non-str, etc.) →
    # "unverified", not ``None`` (the UI never sees a hole).
    return "unverified"


# --- Models -------------------------------------------------------------


class Citation(BaseModel):
    """A pointer from a flag back to the playbook it cites.

    Attributes
    ----------
    playbook_clause_id
        The ``clause_id`` of the playbook baseline the spotter is
        comparing against. **Must be one of the clause_ids in the
        top-k list passed to the spotter** — the parser verifies
        this; a citation pointing outside the top-k is treated as
        missing and the flag is marked ``unverified=True``.
    contract_text_excerpt
        The exact substring of the contract clause that triggered
        the flag. Short (≤200 chars), verbatim, no rephrasing. The
        UI renders this in a popover and the eval harness uses it
        to check that the spotter actually looked at the right
        text.
    """

    playbook_clause_id: str = Field(..., min_length=1, max_length=128)
    contract_text_excerpt: str = Field(..., min_length=1, max_length=2000)

    def is_real(self, valid_clause_ids: set[str]) -> bool:
        """``True`` when ``playbook_clause_id`` is in ``valid_clause_ids``.

        Used by the parser to enforce the "citation must point to a
        real baseline" rule. Empty / unknown ids return ``False``.
        """
        return bool(self.playbook_clause_id) and self.playbook_clause_id in valid_clause_ids


class DeviationFlag(BaseModel):
    """The spotter's output for a single clause.

    Attributes
    ----------
    clause_id
        The ``Clause.id`` of the clause being spotted. Echoed on
        the output so the caller can match flags back to the input
        list (the orchestrator in :mod:`app.pipeline.stage3_spot`
        uses this).
    score
        0..3 — see :class:`DeviationScore`. ``0`` is the default
        (aligned, or "I don't know / no baseline").
    rationale
        The spotter's reasoning. 1–3 sentences. Even at
        ``score=0`` we require a non-empty rationale so the UI can
        show *why* the spotter abstained.
    citation
        Pointer to the playbook baseline the spotter compared
        against. ``None`` is a valid value (the spotter abstained
        or no baseline matched), but a non-zero score with
        ``citation=None`` flips ``unverified=True`` (set by the
        parser, not the schema).
    unverified
        ``True`` when the parser could not verify the citation
        (missing, or pointing outside the top-k) — OR when the
        spotter explicitly declined (LLM returned a refusal or
        ambiguous output). The UI renders unverified flags with a
        warning badge and the user must manually approve.
    baseline_type
        The ``ClauseType`` of the playbook baseline the spotter
        decided was the right reference. Echoed for the UI (the
        deviation table groups flags by baseline type). ``""``
        when the spotter abstained.
    matrix_verdict
        The counterparty matrix's verdict for the clause's
        ``(clause_type, counterparty_type[, language])`` cell,
        in the spec's 4-state column form
        (see :data:`MATRIX_VERDICT_VALUES`). ``None`` when the
        flag was constructed outside the orchestrator (a Phase 2
        caller that didn't know about the matrix axis) — the
        re-stamp in :func:`app.agents.deviation_spotter.spotter._stamp_matrix_audit_fields`
        fills it in.
    matrix_sources
        The lookup chain that produced the matrix verdict, in
        strictness order (the first element is the winning
        source). Common entries: ``"counterparty"`` (an explicit
        counterparty-axis override), ``"language"`` (a language
        axis override), ``"flat"`` (the Phase 2 default).
        Capped at 8 entries; empty strings are dropped. ``None``
        when the flag was constructed outside the orchestrator.
    matrix_counterparty_type
        The counterparty type the matrix was consulted with.
        Defaults to ``"any"`` (the Phase 2 sentinel that consults
        only the flat table). Echoed for the audit trail — the
        UI's deviation table can show "material (healthcare
        override)" in a tooltip.
    """

    clause_id: str = Field(..., min_length=1, max_length=64)
    score: int = Field(..., ge=0, le=3)
    rationale: str = Field(..., min_length=1, max_length=2000)
    citation: Optional[Citation] = None
    unverified: bool = False
    baseline_type: str = Field(default="", max_length=64)
    matrix_verdict: Optional[str] = Field(
        default=None,
        max_length=16,
        description=(
            "Counterparty matrix verdict in the spec's 4-state "
            "column form (acceptable/material/unacceptable/unverified). "
            "Filled by the orchestrator's re-stamp; ``None`` when "
            "constructed outside the matrix-aware path."
        ),
    )
    matrix_sources: Optional[list[str]] = Field(
        default=None,
        description=(
            "Lookup chain that produced the matrix verdict, in "
            "strictness order. Empty strings are dropped; capped at 8."
        ),
    )
    matrix_counterparty_type: str = Field(
        default="any",
        max_length=64,
        description=(
            "Counterparty type the matrix was consulted with. "
            "Defaults to ``'any'`` (Phase 2 sentinel; consults only the "
            "flat table)."
        ),
    )

    @field_validator("score")
    @classmethod
    def _coerce_score(cls, v: int) -> int:
        """Coerce to int and clamp to 0..3.

        The Pydantic ``ge=0, le=3`` already does this, but we
        want the coercion (in case the LLM returns a float or
        a string) to happen before the validation. The LLM
        occasionally returns ``1.0`` instead of ``1``.
        """
        try:
            iv = int(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"score must be an integer, got {v!r}") from exc
        return max(0, min(3, iv))

    @field_validator("matrix_verdict")
    @classmethod
    def _validate_matrix_verdict(cls, v: Optional[str]) -> Optional[str]:
        """Validate ``matrix_verdict`` against the spec's 4-state column.

        ``None`` is preserved as the "no orchestrator stamp"
        sentinel. The re-stamp in
        :func:`app.agents.deviation_spotter.spotter._stamp_matrix_audit_fields`
        fills it in. Empty strings are coerced to ``None`` so
        an LLM that emitted ``""`` doesn't make it into the
        audit trail. Strings are lowercased for case-insensitive
        comparison; the matrix emits lowercase labels.
        """
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError(
                f"matrix_verdict must be a string, got {type(v).__name__}"
            )
        normalised = v.strip().lower()
        if not normalised:
            return None
        if normalised not in MATRIX_VERDICT_VALUES:
            raise ValueError(
                f"matrix_verdict must be one of {MATRIX_VERDICT_VALUES}, "
                f"got {v!r}"
            )
        return normalised

    @field_validator("matrix_sources")
    @classmethod
    def _validate_matrix_sources(
        cls, v: Optional[list[str]]
    ) -> Optional[list[str]]:
        """Drop empty strings from ``matrix_sources`` and cap at 8.

        ``None`` is preserved as the "no orchestrator stamp"
        sentinel. Empty / whitespace-only strings are dropped
        (defensive — the LLM might emit ``["counterparty", ""]``
        with a trailing empty). The 8-entry cap matches the
        LLM echo's cap in
        :func:`app.agents.deviation_spotter.spotter._coerce_matrix_sources`.
        """
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError(
                f"matrix_sources must be a list, got {type(v).__name__}"
            )
        cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        return cleaned[:8]


class SpotInput(BaseModel):
    """The input the spotter takes per call.

    Constructed by :mod:`app.pipeline.stage3_spot` from a
    :class:`~app.classify.Clause` plus the top-k baselines and the
    counterparty matrix's flat verdict for the clause's type.

    Attributes
    ----------
    clause_id
        Echoed on the output.
    clause_text
        The clause body the spotter reads.
    clause_type
        The classified :class:`~app.classify.ClauseType`. The
        spotter uses this as a hint for which playbook baselines
        to weight most heavily, but the top-k list is the
        authoritative reference (the classifier and the retrieval
        can disagree; the spotter trusts the retrieval, not the
        classifier).
    baselines
        The top-3 playbook baselines (or fewer when the store has
        fewer matching clauses). The spotter compares the clause
        against these in the order presented; ``baselines[0]`` is
        the most-similar baseline by cosine similarity.
    counterparty_verdict
        The counterparty matrix's flat verdict for the clause's
        type (``"aligned"`` / ``"minor"`` / ``"material"`` /
        ``"unacceptable"``). The spotter uses this as a prior:
        when the matrix says the default for this clause type is
        ``aligned`` and the spotter would otherwise emit
        ``score=1``, it still emits ``score=1`` but the rationale
        explains the matrix's "aligned" default. The matrix does
        NOT cap the spotter's score — a contract with an explicit
        "term of 7 years" against a 3-year baseline is
        unacceptable even if the matrix default for ``term`` is
        ``aligned``.
    counterparty_type
        The counterparty type that produced the matrix verdict
        (Phase 2 always ``"any"``). Echoed for the audit trail.
    matrix_verdict_column
        **Phase 5.** The matrix verdict in the spec's 4-state
        column form
        (see :data:`MATRIX_VERDICT_VALUES` — ``acceptable`` /
        ``material`` / ``unacceptable`` / ``unverified``). Set
        by the orchestrator from
        :func:`app.playbook.counterparty.lookup_verdict_with_counterparty`
        via :func:`matrix_verdict_from_score`. Defaults to
        ``"unverified"`` (the safe choice — the matrix never
        blocks a spotter call by raising, but the orchestrator
        might not have run for a Phase 2 caller that
        constructed a ``SpotInput`` directly).
    matrix_sources
        **Phase 5.** The lookup chain that produced the matrix
        verdict, in strictness order (the first element is the
        winning source). Common entries: ``"counterparty"``
        (an explicit counterparty-axis override), ``"language"``
        (a language axis override), ``"flat"`` (the Phase 2
        default). Defaults to an empty list.
    matrix_counterparty_type
        **Phase 5.** The counterparty type the matrix was
        consulted with. Defaults to ``"any"`` (the Phase 2
        sentinel that consults only the flat table).
    """

    clause_id: str = Field(..., min_length=1, max_length=64)
    clause_text: str = Field(..., min_length=1)
    clause_type: str = Field(..., min_length=1, max_length=64)
    clause_language: str = Field(
        default="en",
        max_length=8,
        description=(
            "Per-clause language code. Drives the spotter's prompt "
            "dispatch (see app.agents.deviation_spotter.prompt). "
            "Defaults to 'en' for backwards compatibility."
        ),
    )
    baselines: list["BaselineForSpotter"] = Field(..., min_length=0)
    counterparty_verdict: str = Field(default="aligned", max_length=32)
    counterparty_type: str = Field(default="any", max_length=64)
    matrix_verdict_column: str = Field(
        default="unverified",
        max_length=16,
        description=(
            "Phase 5: counterparty matrix verdict in the spec's "
            "4-state column form. Set by the orchestrator from "
            "the matrix lookup. Defaults to ``'unverified'`` (safe "
            "default for callers that haven't wired the matrix axis)."
        ),
    )
    matrix_sources: list[str] = Field(
        default_factory=list,
        description=(
            "Phase 5: lookup chain that produced the matrix verdict, "
            "in strictness order. Defaults to empty."
        ),
    )
    matrix_counterparty_type: str = Field(
        default="any",
        max_length=64,
        description=(
            "Phase 5: counterparty type the matrix was consulted with. "
            "Defaults to ``'any'`` (the Phase 2 sentinel)."
        ),
    )

    @field_validator("counterparty_verdict")
    @classmethod
    def _normalise_verdict(cls, v: str) -> str:
        """Lowercase the verdict string. The matrix emits lowercase
        labels (``"aligned"``, ``"minor"``, ...); the field is
        free-form to keep the schema decoupled from
        :class:`app.playbook.counterparty.Verdict`."""
        return (v or "aligned").strip().lower() or "aligned"

    @field_validator("matrix_verdict_column")
    @classmethod
    def _validate_matrix_verdict_column(cls, v: str) -> str:
        """Validate ``matrix_verdict_column`` against the spec's 4-state column.

        The orchestrator is the only writer; this is a guard against
        typos (e.g. the matrix's internal ``"aligned"`` label leaking
        in instead of the spec column's ``"acceptable"``). The LLM
        echo parser is lenient on the LLM's output — but the
        orchestrator's stamp must match the spec column.
        """
        if not isinstance(v, str):
            raise ValueError(
                f"matrix_verdict_column must be a string, got {type(v).__name__}"
            )
        normalised = v.strip().lower()
        if not normalised:
            return "unverified"
        if normalised not in MATRIX_VERDICT_VALUES:
            raise ValueError(
                f"matrix_verdict_column must be one of {MATRIX_VERDICT_VALUES}, "
                f"got {v!r} (matrix-internal labels like 'aligned' / 'minor' "
                f"should be bridged via matrix_verdict_from_score)"
            )
        return normalised


class BaselineForSpotter(BaseModel):
    """A serialised view of a :class:`app.playbook.store.PlaybookTopKHit`
    that the spotter receives as part of :class:`SpotInput`.

    Defined here (not imported from the playbook package) so the
    agent's I/O surface is decoupled from the store's
    representation. The pipeline orchestrator converts
    :class:`PlaybookTopKHit` to :class:`BaselineForSpotter` before
    calling the spotter.

    Attributes
    ----------
    clause_id
        The baseline's clause_id. The spotter's
        :class:`Citation.playbook_clause_id` must match one of
        these.
    type
        The baseline's clause type (e.g.
        ``"definition_confidential_info"``).
    title
        Human-readable title — the spotter's prompt renders this.
    text
        The baseline clause body. The spotter compares this
        against the contract clause.
    source_url
        Provenance URL. The spotter's prompt includes this so the
        LLM can decide whether the baseline is authoritative.
    similarity
        Cosine similarity in ``[-1, 1]`` from the top-k query.
        The spotter uses this as a tie-breaker (the highest-
        similarity baseline is the primary comparison target).
    """

    clause_id: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=512)
    text: str = Field(..., min_length=1)
    source_url: str = Field(..., min_length=1, max_length=2048)
    similarity: float = Field(..., ge=-1.0, le=1.0)


# Resolve the forward reference on SpotInput.baselines.
SpotInput.model_rebuild()


__all__ = [
    "DeviationScore",
    "Citation",
    "DeviationFlag",
    "SpotInput",
    "BaselineForSpotter",
    # Phase 5: matrix verdict column.
    "MATRIX_VERDICT_VALUES",
    "matrix_verdict_from_score",
]
