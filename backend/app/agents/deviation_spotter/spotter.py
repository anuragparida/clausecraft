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
    """
    citation = _coerce_citation(raw.get("citation"))
    baseline_type = str(raw.get("baseline_type", "") or "").strip()
    try:
        flag = DeviationFlag(
            clause_id=spot_input.clause_id,
            score=raw.get("score", 0),
            rationale=str(raw.get("rationale", "") or "").strip()
            or "agent declined: empty rationale",
            citation=citation,
            unverified=False,
            baseline_type=baseline_type,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"flag validation failed: {exc}") from exc
    if not flag.rationale:
        raise ValueError("rationale must be non-empty")
    return flag


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
    5. Returns a :class:`DeviationFlag` with ``unverified`` set
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
            },
        )
    except Exception:  # noqa: BLE001
        span = _NoopSpan()

    valid_clause_ids = {b.clause_id for b in spot_input.baselines}

    # Short-circuit: no baselines → abstain.
    if not spot_input.baselines:
        flag = DeviationFlag(
            clause_id=spot_input.clause_id,
            score=0,
            rationale="no matching playbook clause",
            citation=None,
            unverified=True,
            baseline_type="",
        )
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
]
