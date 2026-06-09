"""Pydantic models for the redline drafter agent.

Three models — plus one internal carrier for the self-check loop:

- :class:`DrafterInput` — the agent's typed input. Carries the
  accepted :class:`DeviationFlag`, the clause text, and the
  matched baseline clause. The flag carries the score / rationale
  the spotter emitted; the baseline carries the target text the
  drafter is rewriting the clause toward.
- :class:`RedlineProposal` — the happy-path output. ``proposed_text``
  is the rewritten clause (verbatim, drop-in replacement for the
  original). ``rationale`` is 1–3 sentences explaining the edit
  in plain English. ``diff_summary`` is a plain-text before/after
  summary suitable for the audit log + the JSON export.
- :class:`RedlineConflict` — the "couldn't auto-draft" output.
  Carries both attempts' ``proposed_text`` and the conflicting
  spotter flags. The HITL UI (Build 5) renders this as a
  "this redline couldn't be auto-drafted — pick one" view.
- :class:`SelfCheckConstraint` — internal: the constraint
  injected into the prompt on the retry. Carries the first
  attempt's text and the new spotter flag that triggered the
  retry, so the drafter knows what to avoid in attempt #2.

Why ``proposed_text`` is a required ``str`` (not Optional)
----------------------------------------------------------
The drafter's contract: a :class:`RedlineProposal` is a
*finished* redline. The HITL state machine (Build 3) treats
``proposed_text is not None and proposed_text != ""`` as the
"draft succeeded" signal. A drafter that returns an empty
proposal would corrupt the docx output. The schema is the
first line of defense: a missing/empty text fails validation
and the agent raises — the malformed proposal never reaches
the docx writer.

Why ``RedlineConflict`` is separate from :class:`RedlineProposal`
-----------------------------------------------------------------
A union type would force every caller to discriminate before
using either field. By making the conflict its own model, the
HITL UI can do ``if isinstance(outcome, RedlineConflict)`` and
the docx writer can do ``if isinstance(outcome, RedlineProposal)``
— clean, statically checkable, no validator gymnastics.

The ``proposed_text`` and ``rationale`` fields are short,
plain-text strings — the drafter is rewriting a single clause,
not a section. The ``diff_summary`` is also plain text (no
HTML / no diff-syntax markers) so the audit log + JSON export
can render it without a markdown processor.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.deviation_spotter.schema import (
    BaselineForSpotter,
    DeviationFlag,
)


# --- Limits -------------------------------------------------------------

#: Hard cap on the rewritten clause length. The drafter rewrites
#: a single clause, not a section; even the longest NDA clauses
#: in our test corpus are under 4KB. A 16KB cap leaves headroom
#: for unusually verbose rewrites while still bounding the docx
#: output (python-docx's run-merge can stall on multi-MB runs).
_MAX_PROPOSED_TEXT = 16_000

#: Hard cap on the rationale / diff_summary. These are *for humans*
#: in the audit log — a 4-sentence rationale is plenty. Longer
#: rationales are usually a sign the drafter is hedging, not
#: explaining.
_MAX_RATIONALE = 2_000
_MAX_DIFF_SUMMARY = 2_000


# --- Inputs -------------------------------------------------------------


class DrafterInput(BaseModel):
    """The drafter's typed input.

    Attributes
    ----------
    flag
        The accepted :class:`DeviationFlag` from the HITL review
        (Phase 2 deviation table, post-review). The drafter reads
        the flag's ``score`` and ``rationale`` to understand *why*
        the spotter flagged the clause; the drafter's job is to
        rewrite the clause so a *re-run* of the spotter would
        return ``score=0``.
    clause_text
        The verbatim text of the clause being redlined. The
        drafter echoes the surrounding clause structure
        (definitions, "provided that" carve-outs) so the
        redline reads as a single coherent edit, not a swap of
        a substring.
    baseline
        The matched playbook baseline clause (as a
        :class:`BaselineForSpotter` so the drafter sees the same
        shape the spotter saw). The drafter uses the baseline's
        ``text`` as the *target* the rewrite should align with.
    extra_context
        Optional free-form context the user attached when
        accepting the flag in the HITL review. Examples:
        ``"acceptable for our use case if limited to 5 years"``
        or ``"counterparty's standard form, non-negotiable"``.
        The drafter surfaces this in the rationale. Default
        empty string — the drafter treats "no context" as
        "use the baseline as-is".
    """

    flag: DeviationFlag = Field(...)
    clause_text: str = Field(..., min_length=1)
    baseline: BaselineForSpotter = Field(...)
    extra_context: str = Field(default="", max_length=2_000)
    clause_language: str = Field(
        default="en",
        max_length=8,
        description=(
            "Per-clause language code. Drives the drafter's prompt "
            "dispatch (see app.agents.redline_drafter.prompt). "
            "Defaults to 'en' for backwards compatibility."
        ),
    )


# --- Outputs ------------------------------------------------------------


class RedlineProposal(BaseModel):
    """The drafter's happy-path output.

    Attributes
    ----------
    proposed_text
        The rewritten clause (verbatim, drop-in replacement for
        the original). The drafter preserves the clause's
        surrounding structure (numbered list items, ``provided
        that`` carve-outs) so the redline is a single coherent
        edit. **Required, non-empty** — the drafter's contract
        is to produce a *finished* redline.
    rationale
        1–3 sentences explaining the edit in plain English. The
        audit log renders this verbatim; the HITL UI surfaces it
        in a popover when the user hovers the "view redline"
        button. Non-empty.
    diff_summary
        A plain-text before/after summary suitable for the audit
        log + JSON export. The drafter writes this as a
        free-form paragraph (not a structured diff format like
        unified diff syntax) — the format choice is documented
        in :mod:`.prompt`. Non-empty.
    attempt
        Which attempt produced this proposal: 1 (first try) or 2
        (after a self-check retry). The audit log uses this to
        show the user whether a self-check retry was needed.
        Default 1 — the typical path is a single attempt.
    """

    proposed_text: str = Field(..., min_length=1, max_length=_MAX_PROPOSED_TEXT)
    rationale: str = Field(..., min_length=1, max_length=_MAX_RATIONALE)
    diff_summary: str = Field(..., min_length=1, max_length=_MAX_DIFF_SUMMARY)
    attempt: int = Field(default=1, ge=1, le=2)


class SelfCheckConstraint(BaseModel):
    """Internal: the constraint injected into the prompt on a retry.

    Carries the first attempt's text and the new spotter flag
    that triggered the retry, so the drafter knows what to avoid
    in attempt #2. Not exported on the public surface — the
    drafter / self-check modules pass it through internally.

    Attributes
    ----------
    previous_proposed_text
        The first attempt's ``proposed_text``. The drafter uses
        this to understand *what went wrong* — the drafter
        typically rewrites this text, not the original clause,
        when the first attempt introduced a new deviation.
    conflicting_flag
        The :class:`DeviationFlag` the spotter produced when
        re-run on ``previous_proposed_text``. Carries the score
        + rationale + citation the spotter emitted, so the
        drafter can address the specific issue.
    """

    previous_proposed_text: str = Field(..., min_length=1)
    conflicting_flag: DeviationFlag = Field(...)


class RedlineConflict(BaseModel):
    """The "couldn't auto-draft" output.

    Returned by :func:`self_check.run_with_self_check` when
    **both** drafter attempts fail the spotter's re-run. The
    HITL UI (Build 5) renders this as a "this redline couldn't
    be auto-drafted — pick one" view: both proposals are shown
    side-by-side with the conflicting spotter flags, and the
    user picks one (or writes a third) manually.

    Attributes
    ----------
    first_proposal
        The first drafter attempt.
    second_proposal
        The second drafter attempt (after the self-check
        constraint was injected into the prompt).
    first_conflict
        The :class:`DeviationFlag` the spotter produced when
        re-run on ``first_proposal.proposed_text``. This is
        the conflict that triggered the retry.
    second_conflict
        The :class:`DeviationFlag` the spotter produced when
        re-run on ``second_proposal.proposed_text``. The
        presence of this flag is what surfaces the
        :class:`RedlineConflict` to the user (the second
        attempt also failed).
    message
        A short human-readable message for the audit log +
        the HITL popover. Always starts with "redline
        conflict:" so log readers can grep for it.
    """

    first_proposal: RedlineProposal = Field(...)
    second_proposal: RedlineProposal = Field(...)
    first_conflict: DeviationFlag = Field(...)
    second_conflict: DeviationFlag = Field(...)
    message: str = Field(default="redline conflict: both drafter attempts failed the spotter's self-check")

    @property
    def both_failed(self) -> bool:
        """``True`` if both attempts introduced a non-zero deviation.

        Convenience for the HITL UI: it can show the user a
        "both attempts failed the self-check" badge without
        re-deriving the condition from the two conflict flags.
        """
        return self.first_conflict.score > 0 or self.second_conflict.score > 0


# Resolve the forward references (DeviationFlag, BaselineForSpotter
# come from the deviation_spotter schema — defined first so the
# import order is correct, but Pydantic's model_rebuild keeps the
# forward-ref machinery honest in case anyone reorders the imports).
DrafterInput.model_rebuild()
RedlineProposal.model_rebuild()
SelfCheckConstraint.model_rebuild()
RedlineConflict.model_rebuild()


__all__ = [
    "DrafterInput",
    "RedlineProposal",
    "RedlineConflict",
    "SelfCheckConstraint",
]
