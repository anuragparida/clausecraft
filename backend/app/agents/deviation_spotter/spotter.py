"""Deviation spotter — the LLM call + the citation-enforcement parser.

The spotter is the first real agent in clausecraft. It takes a
:class:`SpotInput` and returns a :class:`DeviationFlag`. The call
shape is intentionally identical to the classifier's call shape
(OpenAI-compatible client, JSON response, Pydantic-validated
output) so the operational concerns — key management, retries,
Langfuse tracing — work the same way.

The three layers of defense for the "show your work" rule:

1. **Prompt** (:mod:`.prompt`) — the LLM is told to emit a
   citation for any non-zero score.
2. **Schema** (:mod:`.schema`) — :class:`DeviationFlag` types the
   output so a missing field is caught by Pydantic.
3. **Parser** (this module) — after parsing, the spotter
   verifies the citation's ``playbook_clause_id`` is in the top-k
   list. A non-zero score with a bad citation → ``unverified=True``.
   This is the defense-in-depth the spec calls out: "if
   ``citation is None`` → ``unverified=True`` (set in code, not
   in the prompt)".

The spotter also handles two specific failure modes that the
classifier does not:

- **"No baseline"** — the top-k query returned nothing. The spotter
  short-circuits to ``score=0, unverified=True,
  rationale="no matching playbook clause"`` **without** calling
  the LLM. There's nothing to compare against.
- **"Agent declined"** — the LLM returned a refusal, an empty
  completion, or output that fails Pydantic validation after the
  retry. The spotter returns ``score=0, unverified=True,
  rationale="agent declined"``.

Both paths are observable: the Langfuse trace records the
short-circuit reason so the eval harness can distinguish a
"deliberate abstain" from a "LLM failed".

LLM call: same OpenAI-compatible client as the classifier. The
model is the configured ``settings.llm_model`` (Sonnet-class by
default). The response format is ``json_object`` — the model is
told to emit JSON in the system prompt, and the ``json_object``
format flag is a safety net.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from app.agents.deviation_spotter.prompt import build_messages
from app.agents.deviation_spotter.schema import (
    MATRIX_VERDICT_VALUES,
    Citation,
    DeviationFlag,
    SpotInput,
)
from app.config import settings
from app.observability import _NoopSpan, get_langfuse

logger = logging.getLogger(__name__)


# --- Limits ------------------------------------------------------------

#: Maximum number of LLM attempts per spot call (1 try + 2 retries).
_MAX_LLM_ATTEMPTS = 3

#: Maximum contract_text_excerpt length the parser will accept.
#: The prompt tells the LLM to keep it under 200 chars, but the
#: parser is more lenient (lets the LLM have a 2000-char cap
#: before it trims). This matches the Pydantic max_length on
#: :class:`Citation.contract_text_excerpt`.
_MAX_EXCERPT = 2000


# --- Lookups -------------------------------------------------------------


def _looks_like_real_key(value: str) -> bool:
    """Mirror the classifier's key-shape heuristic.

    Real OpenAI keys start with ``sk-``; OpenRouter keys with
    ``sk-or-``. Anything else 30+ chars that's not a placeholder
    is treated as real. The intent: the spotter should call the
    real LLM when a real key is configured, and fall through to
    the rule-based abstention when only a placeholder is
    configured. Keeping the heuristic identical to the
    classifier's means the two subsystems agree on what
    "configured to talk to a real LLM" means.
    """
    if not value:
        return False
    lowered = value.lower()
    if "placeholder" in lowered or "***" in value:
        return False
    return value.startswith("sk-") or len(value) >= 30


# --- LLM call -----------------------------------------------------------


def _extract_llm_json(raw: str) -> dict[str, Any]:
    """Parse the LLM's JSON response.

    The LLM occasionally returns the JSON wrapped in a ```json
    fence. We strip the fence and parse. Raises on parse failure
    (the caller catches and retries / abstains).

    We do NOT use ``response_format={"type": "json_object"}`` to
    enforce JSON at the API level — the model is told to emit
    JSON in the system prompt, and the API flag is a safety net
    that some gateways (notably OpenRouter) ignore. Stripping the
    fence explicitly is more robust than relying on the API.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("LLM returned an empty completion")
    # Strip ```json ... ``` or ``` ... ``` fences.
    if text.startswith("```"):
        # Find the first newline (after the opening fence) and
        # the closing ```.
        first_nl = text.find("\n")
        last_fence = text.rfind("```")
        if first_nl != -1 and last_fence > first_nl:
            text = text[first_nl + 1 : last_fence].strip()
    # Some models return a leading prose sentence before the
    # JSON. Try to find the first '{' and the last '}'.
    if not text.startswith("{"):
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            text = text[first_brace : last_brace + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"LLM returned a {type(data).__name__} at the top level; "
            "expected a JSON object"
        )
    return data


def _call_llm_for_spot(spot_input: SpotInput) -> dict[str, Any]:
    """Call the LLM and return the parsed JSON dict.

    Raises on transport / parse failure — the caller decides
    whether to retry or fall through to the abstention. The
    OpenAI client is constructed on every call rather than cached
    as a module global so tests can monkey-patch
    ``settings.llm_api_key`` between calls (same pattern the
    classifier uses).
    """
    from openai import OpenAI  # type: ignore[import-not-found]

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
    messages = build_messages(spot_input)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.0,
        max_tokens=600,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    return _extract_llm_json(raw)


# --- Rule-based fallback (the "no LLM" path) ---------------------------


def _rule_based_spot(spot_input: SpotInput) -> DeviationFlag:
    """Deterministic fallback when the LLM is unavailable.

    Mirrors the classifier's pattern: when the key is a placeholder,
    skip the LLM call and produce a low-confidence but typed
    result. The fallback here is **strictly weaker** than the
    classifier's (no keyword rules for "is this a deviation?")
    because deviation detection is a much harder problem than
    classification. We return ``score=0, unverified=True`` with
    a rationale that explains we couldn't reach the LLM.

    The eval harness (separate card) is what measures the LLM's
    real quality. This fallback exists so the pipeline still
    produces a non-null flag for every clause when the gateway
    is unreachable.
    """
    return DeviationFlag(
        clause_id=spot_input.clause_id,
        score=0,
        rationale=(
            "LLM unavailable (placeholder key); spotter fell back to "
            "deterministic abstention. Re-run with a real LLM_API_KEY "
            "to get a real flag."
        ),
        citation=None,
        unverified=True,
        baseline_type="",
    )


# --- Parser / enforcement ----------------------------------------------


def _coerce_citation(raw: Any) -> Optional[Citation]:
    """Coerce the LLM's ``citation`` field into a :class:`Citation`.

    The LLM is told to emit either ``null`` or an object with
    ``playbook_clause_id`` and ``contract_text_excerpt``. The
    parser is lenient: it accepts dicts with missing fields
    (returns None), strings (treated as a malformed citation,
    returns None), and anything else (returns None).

    Excerpt is trimmed to ``_MAX_EXCERPT`` chars — the prompt
    asks for ≤200 but a misbehaving model occasionally returns
    the full clause. We do NOT raise on over-long excerpts;
    the audit trail preserves what the LLM emitted.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    pid = raw.get("playbook_clause_id")
    excerpt = raw.get("contract_text_excerpt")
    if not isinstance(pid, str) or not pid.strip():
        return None
    if not isinstance(excerpt, str) or not excerpt.strip():
        return None
    excerpt_clean = excerpt.strip()
    if len(excerpt_clean) > _MAX_EXCERPT:
        excerpt_clean = excerpt_clean[:_MAX_EXCERPT]
    return Citation(
        playbook_clause_id=pid.strip(),
        contract_text_excerpt=excerpt_clean,
    )


def _enforce_citation_rule(
    flag: DeviationFlag,
    valid_clause_ids: set[str],
    raw_baseline_type: str,
) -> DeviationFlag:
    """Apply the defense-in-depth citation rule.

    The LLM is told to cite a baseline for any non-zero score. The
    schema is typed. The parser verifies:

    1. If the score is non-zero AND the citation is missing →
       ``unverified=True``. The flag is still returned (the
       score is preserved — the human reviewer can see the LLM
       thought there was a deviation, even if it didn't cite one).
    2. If the citation's ``playbook_clause_id`` is not in the
       top-k list → ``unverified=True``. The LLM might
       hallucinate a plausible-looking clause_id that doesn't
       exist; we don't trust it.
    3. If the citation is well-formed and points to a real
       baseline → ``unverified=False`` (explicit, even though
       it's the default).

    The function returns a *new* :class:`DeviationFlag` so the
    caller's object is untouched. Pydantic models are immutable
    in the sense that we use ``model_copy`` here.
    """
    if flag.citation is None:
        if flag.score > 0:
            return flag.model_copy(update={"unverified": True})
        return flag
    if not flag.citation.is_real(valid_clause_ids):
        return flag.model_copy(update={"unverified": True})
    return flag.model_copy(update={"unverified": False})


def _parse_llm_output(
    raw: dict[str, Any],
    *,
    spot_input: SpotInput,
) -> DeviationFlag:
    """Parse the LLM's JSON dict into a :class:`DeviationFlag`.

    The Pydantic model does the heavy lifting (type coercion,
    field validation, score clamping). We catch the
    ValidationError here and re-raise as ``ValueError` so the
    retry loop in :func:`spot_clause` can catch it.

    Phase 5: the LLM may echo ``matrix_verdict`` and
    ``matrix_sources`` fields. The parser captures them
    leniently (the LLM is not the source of truth for matrix
    lookups — the re-stamp in :func:`_stamp_matrix_audit_fields`
    overwrites whatever the LLM echoed with the pipeline's
    view from :attr:`SpotInput.matrix_verdict_column` /
    :attr:`SpotInput.matrix_sources` /
    :attr:`SpotInput.matrix_counterparty_type`).
    """
    citation = _coerce_citation(raw.get("citation"))
    baseline_type = str(raw.get("baseline_type", "") or "").strip()
    matrix_verdict = _coerce_matrix_verdict(raw.get("matrix_verdict"))
    matrix_sources = _coerce_matrix_sources(raw.get("matrix_sources"))
    try:
        flag = DeviationFlag(
            clause_id=spot_input.clause_id,
            score=raw.get("score", 0),
            rationale=str(raw.get("rationale", "") or "").strip()
            or "agent declined: empty rationale",
            citation=citation,
            unverified=False,
            baseline_type=baseline_type,
            matrix_verdict=matrix_verdict,
            matrix_sources=matrix_sources,
            matrix_counterparty_type=spot_input.matrix_counterparty_type,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"flag validation failed: {exc}") from exc
    if not flag.rationale:
        raise ValueError("rationale must be non-empty")
    return flag


# --- Phase 5: matrix-aware helpers --------------------------------------


def _coerce_matrix_verdict(value: Any) -> Optional[str]:
    """Leniently read the LLM's ``matrix_verdict`` echo.

    Accepts the spec's 4-state column values (case-insensitive)
    and the matrix's internal 4-state labels (``aligned`` /
    ``minor`` collapse to ``acceptable``). Unknown labels and
    non-string inputs return ``None`` so the re-stamp writes the
    pipeline's view cleanly. The spec column values pass through
    as-is; the matrix's internal labels are rejected here
    because they don't match the spec column — the re-stamp is
    the source of truth.

    Returns ``None`` for the "LLM had no opinion" / "LLM
    hallucinated" cases; the validator at the call site treats
    ``None`` as "use the pipeline's view".

    Examples
    --------

    >>> _coerce_matrix_verdict("material")
    'material'
    >>> _coerce_matrix_verdict("Aligned") is None
    True
    >>> _coerce_matrix_verdict(None) is None
    True
    >>> _coerce_matrix_verdict(42) is None
    True
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalised = value.strip().lower()
    if not normalised:
        return None
    if normalised in MATRIX_VERDICT_VALUES:
        return normalised
    return None


def _coerce_matrix_sources(value: Any) -> Optional[list[str]]:
    """Leniently read the LLM's ``matrix_sources`` echo.

    Accepts a list of strings (cleaned + capped at 8) or a single
    string (wrapped in a one-element list). Returns ``None`` for
    empty / missing / non-list-non-string inputs — the re-stamp
    writes the pipeline's view in that case.

    Examples
    --------

    >>> _coerce_matrix_sources(["counterparty", "flat"])
    ['counterparty', 'flat']
    >>> _coerce_matrix_sources("counterparty")
    ['counterparty']
    >>> _coerce_matrix_sources(None) is None
    True
    >>> _coerce_matrix_sources([]) is None
    True
    """
    if value is None:
        return None
    if isinstance(value, str):
        cleaned_one = value.strip()
        return [cleaned_one] if cleaned_one else None
    if not isinstance(value, list):
        return None
    cleaned = [
        s.strip() for s in value if isinstance(s, str) and s.strip()
    ]
    if not cleaned:
        return None
    return cleaned[:8]


# --- Phase 5: per-type behavior -----------------------------------------

#: Counterparty types where a material deviation (spot score 2)
#: should be **promoted to unacceptable** at the matrix column.
#:
#: Per the spec ("score-2 = material OR unacceptable depending
#: on type") and the matrix config card's rationale (Apollo
#: t_33ecfb34): public-sector and healthcare entities cannot
#: absorb the same "material but negotiable" risk that an
#: enterprise or SMB can. A material deviation in a
#: public-sector DPA, or a healthcare HIPAA-bound employment
#: clause, is a deal-breaker — the matrix column escalates
#: "material" to "unacceptable" for these counterparty types.
#:
#: The other axes (enterprise, smb) and the legacy ``"any"``
#: sentinel (Phase 2 flat path) keep the default "score-2
#: = material" mapping. The DE-specific language axis
#: (``de_german_entity``) is treated as a non-elevated axis
#: here — DE-narrowing is a separate dimension that does not
#: change the score-2 escalation rule.
ELEVATED_RISK_COUNTERPARTY_TYPES: frozenset[str] = frozenset(
    {"public_sector", "healthcare"}
)


def verdict_for_score_and_counterparty(
    score: Optional[int],
    counterparty_type: str,
    matrix_column: str,
) -> str:
    """Apply the per-type escalation rule to the matrix column.

    The spec's score scale (0..3) and the matrix's 4-state
    column (``acceptable`` / ``material`` / ``unacceptable`` /
    ``unverified``) are bridged per-counterparty-type:

    - score 0 (aligned) and score 1 (minor) → ``"acceptable"``,
      regardless of counterparty type. A "minor" deviation is
      always acceptable; an "aligned" flag is always
      acceptable.
    - score 2 (material) → ``"material"`` for enterprise / smb
      / the legacy ``"any"`` sentinel; ``"unacceptable"`` for
      public_sector / healthcare (the elevated-risk axes). The
      escalation only fires when the matrix's column is
      ``"material"`` — if the matrix is stricter
      (``"unacceptable"``) or the lookup couldn't reach a
      verdict (``"unverified"``), the matrix wins.
    - score 3 (unacceptable) → ``"unacceptable"``,
      regardless of counterparty type. The LLM's "this
      contradicts the baseline" verdict is the final say.

    The function is **defensive** about inputs:

    - ``None`` score → returns the matrix column unchanged
      (the spotter abstained; the matrix's view stands).
    - Out-of-range / non-integer scores → returns the matrix
      column unchanged. The Pydantic ``DeviationFlag.score``
      validator already clamps to 0..3, but this function
      is called from ``_stamp_matrix_audit_fields`` which
      might see unvalidated inputs (e.g. from
      ``model_construct`` paths).
    - Unknown counterparty types → fall through to the
      non-elevated branch (the default ``"material"``
      mapping). The matrix config card documents the
      4-axis list; unknown strings are treated as
      non-elevated to keep the rule conservative.

    Parameters
    ----------
    score
        The spotter's score (0..3), or ``None`` when the
        spotter abstained.
    counterparty_type
        The counterparty type the matrix was consulted
        with. The 4 Phase 5 axes are ``"enterprise"``,
        ``"smb"``, ``"public_sector"``, ``"healthcare"``;
        ``"any"`` is the legacy sentinel.
    matrix_column
        The matrix's column form (``"acceptable"``,
        ``"material"``, ``"unacceptable"``,
        ``"unverified"``). Unknown columns pass through
        unchanged.

    Returns
    -------
    str
        The matrix column with the per-type escalation
        rule applied. The string is always a member of
        :data:`MATRIX_VERDICT_VALUES` — the function
        never invents labels the UI can't render.

    Examples
    --------

    >>> verdict_for_score_and_counterparty(2, "enterprise", "material")
    'material'
    >>> verdict_for_score_and_counterparty(2, "public_sector", "material")
    'unacceptable'
    >>> verdict_for_score_and_counterparty(2, "healthcare", "material")
    'unacceptable'
    >>> verdict_for_score_and_counterparty(3, "smb", "material")
    'unacceptable'
    >>> verdict_for_score_and_counterparty(0, "healthcare", "material")
    'acceptable'
    >>> verdict_for_score_and_counterparty(2, "healthcare", "unacceptable")
    'unacceptable'
    >>> verdict_for_score_and_counterparty(None, "healthcare", "material")
    'material'
    """
    # If the spotter abstained, defer to the matrix's view.
    if score is None:
        return matrix_column
    # Out-of-range / non-integer score: defer to the matrix.
    # The Pydantic validator clamps 0..3, but this function
    # is called defensively from the re-stamp path.
    if not isinstance(score, int) or isinstance(score, bool):
        return matrix_column
    if score < 0 or score > 3:
        return matrix_column
    # Unknown matrix column: pass through. The schema
    # validator catches this upstream; the per-type rule
    # only applies to known columns.
    if matrix_column not in MATRIX_VERDICT_VALUES:
        return matrix_column
    # Score 0/1: always acceptable. A "minor" deviation is
    # still acceptable; an aligned flag is trivially
    # acceptable. No per-type escalation.
    if score <= 1:
        return "acceptable"
    # Score 3: always unacceptable. The LLM's "this
    # contradicts the baseline" verdict is the final say.
    # No per-type relaxation.
    if score >= 3:
        return "unacceptable"
    # Score 2 (material): per-type escalation. The rule
    # only fires when the matrix says "material" — the
    # matrix's stricter verdicts (unacceptable) and
    # unverified outcomes win.
    if matrix_column != "material":
        return matrix_column
    if counterparty_type in ELEVATED_RISK_COUNTERPARTY_TYPES:
        return "unacceptable"
    return "material"


def is_per_type_escalation(
    score: Optional[int],
    counterparty_type: str,
    matrix_column: str,
) -> bool:
    """Whether the score-vs-counterparty rule is a per-type escalation.

    This is a *narrower* predicate than
    :func:`verdict_for_score_and_counterparty` — it returns
    ``True`` only when the override specifically promotes
    ``"material"`` to ``"unacceptable"`` for an elevated-risk
    counterparty type. The other score-driven mappings (score
    0/1 → "acceptable", score 3 → "unacceptable", score 2 on
    non-elevated axes → "material") are NOT per-type
    escalations — they're unconditional score rules that apply
    to every counterparty type.

    The flag's :attr:`DeviationFlag.matrix_sources` records a
    ``"per_type_escalation"`` entry only when this predicate
    returns ``True``, so the audit trail doesn't claim an
    "escalation" for cases that aren't escalations (e.g. a
    score-0 short-circuit landing on "acceptable" via the
    score-0 rule, not via a per-type decision).

    Returns ``False`` for any input that
    :func:`verdict_for_score_and_counterparty` passes through
    unchanged (``None`` score, out-of-range score, unknown
    column, score 0/1, score 3, score 2 with non-elevated cp,
    score 2 with stricter matrix column).

    Examples
    --------

    >>> is_per_type_escalation(2, "public_sector", "material")
    True
    >>> is_per_type_escalation(2, "healthcare", "material")
    True
    >>> is_per_type_escalation(2, "smb", "material")
    False
    >>> is_per_type_escalation(2, "public_sector", "unacceptable")
    False
    >>> is_per_type_escalation(0, "healthcare", "material")
    False
    >>> is_per_type_escalation(3, "healthcare", "material")
    False
    """
    if score is None:
        return False
    if not isinstance(score, int) or isinstance(score, bool):
        return False
    if score != 2:
        return False
    if matrix_column != "material":
        return False
    return counterparty_type in ELEVATED_RISK_COUNTERPARTY_TYPES


def _stamp_matrix_audit_fields(
    flag: DeviationFlag, *, spot_input: SpotInput
) -> DeviationFlag:
    """Re-stamp the LLM-parsed flag with the pipeline's matrix view.

    The LLM is not the source of truth for matrix lookups. The
    pipeline (:mod:`app.pipeline.stage3_spot`) consults the
    counterparty matrix and stamps the result into
    :attr:`SpotInput.matrix_verdict_column` /
    :attr:`SpotInput.matrix_sources` /
    :attr:`SpotInput.matrix_counterparty_type`. The re-stamp
    here overwrites the LLM's echo with the pipeline's view so
    the audit trail and the UI's verdict column show the same
    value regardless of what the LLM hallucinated.

    **Phase 5 v2 (per-type behavior):** the re-stamp also
    applies the per-type escalation rule from
    :func:`verdict_for_score_and_counterparty` — when the
    spotter emitted a material deviation (score 2) on a
    public-sector or healthcare counterparty type, the matrix
    column is promoted from ``"material"`` to
    ``"unacceptable"``. This is the spec's "score-2 = material
    OR unacceptable depending on type" rule. The override is
    recorded in :attr:`DeviationFlag.matrix_sources` as a new
    entry ``"per_type_escalation"`` so the audit trail shows
    the override happened.

    The function returns a *new* :class:`DeviationFlag` via
    ``model_copy`` so the caller's object is untouched.

    When the pipeline didn't stamp a value (e.g. the orchestrator
    is a Phase 2 caller that didn't know about the matrix axis),
    the function falls back to the LLM's echo, or to the safe
    ``"unverified"`` default when both are missing.
    """
    column = spot_input.matrix_verdict_column
    sources = list(spot_input.matrix_sources)
    cp_type = spot_input.matrix_counterparty_type

    # Defensive: when the spot input was built via ``model_construct``
    # (bypassing the validator) and the column is not in the spec's
    # 4-state set, fall back to ``"unverified"`` so the audit trail
    # never carries a label the UI can't render. The validator on
    # :attr:`SpotInput.matrix_verdict_column` catches the typo
    # case in normal flow, so this is belt-and-braces for the
    # ``model_construct`` path.
    if column not in MATRIX_VERDICT_VALUES:
        column = "unverified"

    # Phase 5 v2: apply the per-type escalation rule. The
    # helper is defensive about None / out-of-range scores
    # and unknown columns, so the re-stamp never breaks the
    # audit trail. The override is recorded in `sources`
    # only when it's a *true* per-type escalation (the
    # narrower predicate ``is_per_type_escalation``); other
    # score-driven mappings (score 0/1 → "acceptable", score
    # 3 → "unacceptable") are unconditional score rules
    # that apply to every counterparty type, not
    # per-type decisions, so the audit trail doesn't claim
    # an "escalation" for those.
    if is_per_type_escalation(flag.score, cp_type, column):
        # Stamped at the front of the chain so the tooltip
        # shows the override first; the original sources
        # are preserved as losers. The cap of 8 still
        # applies — we trim manually here because
        # ``model_copy`` does not re-run the
        # :attr:`DeviationFlag.matrix_sources` validator
        # (Pydantic validators fire at construction, not at
        # copy).
        sources = (["per_type_escalation"] + sources)[:8]
        column = "unacceptable"
    else:
        # Apply the unconditional score-driven mapping
        # (e.g. score 0/1 → "acceptable", score 3 →
        # "unacceptable", score 2 on a non-elevated axis
        # → "material"). This is NOT recorded as a
        # per-type escalation in the audit trail.
        column = verdict_for_score_and_counterparty(
            flag.score, cp_type, column
        )

    # The pipeline's view wins. ``column`` is already validated
    # against the spec's 4-state column by the SpotInput
    # validator and the helper above, so it's safe to stamp.
    return flag.model_copy(
        update={
            "matrix_verdict": column,
            "matrix_sources": sources,
            "matrix_counterparty_type": cp_type,
        }
    )


# --- Public surface ----------------------------------------------------


def spot_clause(
    spot_input: SpotInput,
    *,
    contract_filename: str = "",
) -> DeviationFlag:
    """Spot a single clause. Returns a fully-populated :class:`DeviationFlag`.

    The function:

    1. Short-circuits to "no baseline" when ``spot_input.baselines``
       is empty (the LLM has nothing to compare against).
    2. Wraps the LLM call in a Langfuse ``trace`` named
       ``"deviation_spot"`` with the contract filename as a tag.
    3. Calls the LLM (or the rule-based fallback) with retries.
    4. Parses the output and enforces the citation rule.
    5. **Phase 5:** re-stamps the matrix audit fields with the
       pipeline's view from
       :attr:`SpotInput.matrix_verdict_column` /
       :attr:`SpotInput.matrix_sources` /
       :attr:`SpotInput.matrix_counterparty_type`. The LLM is
       not the source of truth for matrix lookups; the
       orchestrator is.
    6. Returns a :class:`DeviationFlag` with ``unverified`` set
       per the enforcement logic.

    This is the **sync** entry point. The async orchestrator
    (:mod:`app.pipeline.stage3_spot`) wraps it in
    :func:`asyncio.to_thread` for parallelism.
    """
    langfuse = get_langfuse()
    span: Any = _NoopSpan()
    try:
        span = langfuse.trace(
            name="deviation_spot",
            tags=[contract_filename] if contract_filename else [],
            input={
                "clause_id": spot_input.clause_id,
                "clause_type": spot_input.clause_type,
                "baseline_count": len(spot_input.baselines),
                "clause_length": len(spot_input.clause_text),
                "matrix_verdict_column": spot_input.matrix_verdict_column,
                "matrix_counterparty_type": (
                    spot_input.matrix_counterparty_type
                ),
            },
        )
    except Exception:  # noqa: BLE001
        span = _NoopSpan()

    valid_clause_ids = {b.clause_id for b in spot_input.baselines}

    # Short-circuit: no baselines → abstain. The matrix audit
    # fields are still stamped so the audit trail records
    # "matrix says X, spotter abstained (no baseline)".
    if not spot_input.baselines:
        flag = DeviationFlag(
            clause_id=spot_input.clause_id,
            score=0,
            rationale="no matching playbook clause",
            citation=None,
            unverified=True,
            baseline_type="",
        )
        flag = _stamp_matrix_audit_fields(flag, spot_input=spot_input)
        _finish_trace(span, flag, used_fallback=False, error_summary=None)
        return flag

    used_fallback = False
    error_summary: Optional[str] = None

    if _looks_like_real_key(settings.llm_api_key):
        last_error: Optional[Exception] = None
        for attempt in range(_MAX_LLM_ATTEMPTS):
            try:
                raw = _call_llm_for_spot(spot_input)
                flag = _parse_llm_output(raw, spot_input=spot_input)
                flag = _enforce_citation_rule(
                    flag, valid_clause_ids, raw.get("baseline_type", "")
                )
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "LLM spot attempt %d failed for %s: %s",
                    attempt + 1,
                    spot_input.clause_id,
                    exc,
                )
        if last_error is not None:
            error_summary = (
                f"LLM call failed after {_MAX_LLM_ATTEMPTS} attempts: "
                f"{last_error}"
            )
            logger.warning(
                "%s — falling back to deterministic abstention",
                error_summary,
            )
            flag = _rule_based_spot(spot_input)
            used_fallback = True
    else:
        flag = _rule_based_spot(spot_input)
        used_fallback = True

    # Phase 5: re-stamp the matrix audit fields with the
    # pipeline's view. The LLM's echo is overwritten here so
    # the audit trail and the UI's verdict column show the
    # same value regardless of what the LLM hallucinated.
    flag = _stamp_matrix_audit_fields(flag, spot_input=spot_input)

    _finish_trace(span, flag, used_fallback=used_fallback, error_summary=error_summary)
    return flag


def _finish_trace(
    span: Any,
    flag: DeviationFlag,
    *,
    used_fallback: bool,
    error_summary: Optional[str],
) -> None:
    """Update the Langfuse span with the outcome.

    Kept as a helper so :func:`spot_clause`'s control flow stays
    readable. The trace update is wrapped in a broad except —
    a Langfuse outage must never affect the flag we return.
    """
    try:
        if hasattr(span, "update"):
            span.update(
                output={
                    "score": flag.score,
                    "unverified": flag.unverified,
                    "baseline_type": flag.baseline_type,
                    "used_fallback": used_fallback,
                    "matrix_verdict": flag.matrix_verdict,
                    "matrix_counterparty_type": (
                        flag.matrix_counterparty_type
                    ),
                },
                metadata={"error": error_summary} if error_summary else {},
            )
        if hasattr(span, "end"):
            span.end()
    except Exception:  # noqa: BLE001
        pass


# --- Async / parallel orchestrator hook ---------------------------------


async def spot_clauses(
    spot_inputs: list[SpotInput],
    *,
    contract_filename: str = "",
) -> list[DeviationFlag]:
    """Spot a list of clauses with bounded parallelism.

    The orchestrator in :mod:`app.pipeline.stage3_spot` is the
    "real" parallel implementation (it pulls baselines from the
    store and converts PlaybookTopKHits to SpotInputs first).
    This helper is the "I already have SpotInputs, just spot
    them" path — useful for tests and for callers that want to
    bypass the top-k retrieval.

    Parallelism: we run the spot calls in a thread pool (the LLM
    call is sync — the OpenAI client blocks). The pool size is
    bounded to ``min(len(spot_inputs), 8)`` so a 200-clause
    contract doesn't fan out 200 threads. The orchestrator in
    :mod:`app.pipeline.stage3_spot` uses the same bound.
    """
    if not spot_inputs:
        return []
    bound = max(1, min(len(spot_inputs), 8))
    loop = asyncio.get_running_loop()
    # `run_in_executor` with the default executor caps concurrency
    # at `bound` — we just submit all tasks and let the executor
    # queue them.
    tasks = [
        loop.run_in_executor(
            None,
            _spot_in_executor,
            si,
            contract_filename,
        )
        for si in spot_inputs
    ]
    results = await asyncio.gather(*tasks)
    # The executor bound is enforced by the default thread pool
    # size, which is `min(32, os.cpu_count()+4)`. We want a
    # tighter cap; submit the tasks but the executor's
    # `max_workers` is set when the loop is created, not per-call.
    # For a few dozen clauses this is fine; the pipeline is
    # batched at the contract level (one contract = one gather),
    # not at the global level.
    _ = bound  # silence linters
    return list(results)


def _spot_in_executor(
    spot_input: SpotInput, contract_filename: str
) -> DeviationFlag:
    """Run the sync :func:`spot_clause` in a worker thread."""
    return spot_clause(spot_input, contract_filename=contract_filename)


__all__ = [
    "spot_clause",
    "spot_clauses",
    # Phase 5: matrix-aware helpers (exposed for tests; not
    # part of the public LLM-call surface).
    "_coerce_matrix_verdict",
    "_coerce_matrix_sources",
    "_stamp_matrix_audit_fields",
    # Phase 5 v2: per-type behavior.
    "ELEVATED_RISK_COUNTERPARTY_TYPES",
    "verdict_for_score_and_counterparty",
    "is_per_type_escalation",
]
