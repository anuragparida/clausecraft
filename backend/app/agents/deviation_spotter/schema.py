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
    """

    clause_id: str = Field(..., min_length=1, max_length=64)
    score: int = Field(..., ge=0, le=3)
    rationale: str = Field(..., min_length=1, max_length=2000)
    citation: Optional[Citation] = None
    unverified: bool = False
    baseline_type: str = Field(default="", max_length=64)

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

    @field_validator("counterparty_verdict")
    @classmethod
    def _normalise_verdict(cls, v: str) -> str:
        """Lowercase the verdict string. The matrix emits lowercase
        labels (``"aligned"``, ``"minor"``, ...); the field is
        free-form to keep the schema decoupled from
        :class:`app.playbook.counterparty.Verdict`."""
        return (v or "aligned").strip().lower() or "aligned"


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
]
