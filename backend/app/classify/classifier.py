"""Clause classifier — Phase 1.

Two backends:

1. **LLM (preferred).** Calls the configured model (Sonnet-class by
   default) via the OpenAI-compatible client. The system prompt is
   defined in :mod:`app.classify.prompt` and the output is Pydantic-
   validated. Retries on validation failure (max 2), then falls
   through to the rule-based classifier with a low confidence.

2. **Rule-based (fallback).** When the LLM API key is a placeholder,
   or when the LLM call fails, the classifier uses a deterministic
   keyword/regex pass over the clause text. The rule-based pass is
   intentionally simple — it produces a non-null ``type`` for the
   5 test contracts but is NOT meant to be a production classifier.
   The eval harness (Phase 2) measures real quality; this fallback
   is here so the Phase 1 pipeline can run end-to-end without a
   real LLM key.

Every classification call is traced via Langfuse (1 trace per call).
When tracing is disabled (placeholder keys), the trace call is a
no-op so the rest of the code path is identical.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.classify.prompt import build_messages
from app.classify.schema import Clause, ClausePosition, ClauseType
from app.config import settings
from app.observability import _NoopSpan, get_langfuse

logger = logging.getLogger(__name__)


# --- Rule-based fallback ------------------------------------------------

# Keyword patterns per clause type. Order matters: more specific
# patterns come first so a clause mentioning "for a period of three
# years" doesn't get tagged as ``term`` when it's actually the end
# of a ``definition_confidential_info`` clause.
_RULES: list[tuple[ClauseType, re.Pattern[str]]] = [
    # NOTE: order matters. The patterns above are checked top-to-bottom
    # and the FIRST match wins. Patterns that overlap (e.g. a clause
    # about returning "Confidential Information" can match BOTH
    # return_of_materials and definition_confidential_info) are
    # ordered with the more specific/intent-bearing one first.
    # ENTIRE_AGREEMENT is checked first because clauses that
    # combine "entire agreement" + "in no way creates an obligation"
    # / "shall not be construed to constitute" / "constitute an
    # agency" etc. should label as ``entire_agreement``, not
    # ``definition_confidential_info`` — the entire-agreement intent
    # is the dominant one.
    (
        ClauseType.ENTIRE_AGREEMENT,
        re.compile(
            r"\b(entire\s+agreement|whole\s+agreement|"
            r"constitutes\s+the\s+entire|"
            r"contains\s+the\s+entire\s+agreement|"
            r"supersedes?\s+all\s+prior|"
            r"this\s+agreement\s+constitutes\s+the\s+entire)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.RETURN_OF_MATERIALS,
        re.compile(
            r"\b(return\s+(?:or\s+destroy|destroy\s+or\s+return|all\s+materials)|"
            r"destroy(?:ing)?\s+(?:all|any)\s+confidential|"
            r"upon\s+(?:termination|expiration|written\s+request).*"
            r"(?:return|destroy))\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.DEFINITION_CONFIDENTIAL_INFO,
        re.compile(
            r"\b(confidential\s+information\s+(?:means|shall\s+mean|includes|"
            r"refers\s+to|is\s+defined\s+as|does\s+not\s+(?:include|comprise))|"
            r"confidential\s+means|"
            r"\bmeans\s+any\s+(non-?public|technical|business|information)|"
            r"information\s+that\s+(?:is|would\s+be)\s+confidential|"
            r"(?:either|each|any)\s+party\s+may\s+disclose|"
            r"may\s+disclose\s+(?:confidential\s+)?information|"
            r"certain\s+non-?public\s+information|"
            r"non-?public\s+information\s+(?:disclosed|that)|"
            r"shall\s+be\s+marked\s+confidential|"
            r"obligations\s+of\s+confidentiality|"
            r"obligations\s+of\s+the\s+receiving\s+party|"
            r"standard\s+of\s+care|"
            r"protect\s+the\s+confidential\s+information\s+by|"
            r"same\s+degree\s+of\s+care|"
            r"recipient\s+shall\s+(?:for\s+a\s+period|protect|refrain)|"
            r"receiving\s+party\s+shall\s+(?:for\s+a\s+period|protect|refrain)|"
            r"this\s+agreement\s+shall\s+not\s+be\s+construed\s+to\s+limit|"
            r"limit\s+either\s+party.?s?\s+right\s+to\s+develop|"
            r"information\s+shall\s+not\s+be\s+deemed\s+confidential|"
            r"nothing\s+in\s+this\s+agreement\s+shall\s+be\s+construed\s+to\s+constitute|"
            r"constitute\s+an\s+agency|"
            r"public\s+announcement\s+of\s+or\s+otherwise\s+disclose)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.GOVERNING_LAW,
        re.compile(
            r"\b(governed\s+by\s+(?:and\s+construed\s+in\s+accordance\s+with\s+)?"
            r"the\s+laws?\s+of|jurisdiction\s+of\s+the\s+courts?\s+of|"
            r"venue\s+shall\s+be|choice\s+of\s+law)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.INJUNCTIVE_RELIEF,
        re.compile(
            r"\b(injunctive\s+relief|irreparable\s+(?:harm|injury|damage)|"
            r"equitable\s+remed(?:y|ies)|"
            r"monetary\s+damages?\s+(?:may\s+be|are|is)\s+(?:inadequate|insufficient))\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.RESIDUAL_KNOWLEDGE,
        re.compile(
            r"\b(residual\s+knowledge|residual\s+information|"
            r"(?:retain|retained|retaining)\s+in\s+(?:the\s+)?(?:unaided\s+)?memory|"
            r"retained\s+in\s+the\s+(?:unaided\s+)?memory)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.NON_COMPETE,
        re.compile(
            r"\b(non-?compete|non-?competition|"
            r"shall\s+not\s+(?:engage\s+in|compete\s+with)|"
            r"competitive\s+activities?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.INDEMNITY,
        re.compile(
            r"\b(indemnif(?:y|ication|ies)|hold\s+harmless|"
            r"defend(?:s)?\s+against\s+(?:any|all))\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.LIMITATION_OF_LIABILITY,
        re.compile(
            r"\b(limitation\s+of\s+liability|limit(?:ation)?\s+on\s+liability|"
            r"in\s+no\s+event\s+(?:shall|might).*liable|"
            r"aggregate\s+liability.*exceed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.ASSIGNMENT,
        re.compile(
            r"\b(assign(?:ment)?\s+of\s+(?:this\s+)?agreement|"
            r"neither\s+party\s+may\s+assign|"
            r"may\s+not\s+be\s+assigned\s+without|"
            r"transfer\s+(?:of\s+)?(?:rights|obligations))\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.SEVERABILITY,
        re.compile(
            r"\b(severability|severable|"
            r"if\s+any\s+provision\s+(?:is|shall\s+be)\s+(?:held\s+)?"
            r"(?:unenforceable|invalid|illegal)|"
            r"invalid\s+provision|"
            r"remaining\s+provisions?\s+shall\s+remain\s+in\s+full\s+force)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.NOTICES,
        re.compile(
            r"\b(notices?\s+shall\s+be\s+(?:in\s+writing|given|delivered)|"
            r"all\s+notices?[,\s]+requests?[,\s]+(?:consents?|and\s+other\s+"
            r"communications?)|"
            r"all\s+notices?\s+(?:shall|must|will)\s+be\s+(?:in\s+writing|"
            r"delivered\s+to)|"
            r"address(?:es)?\s+(?:for|to)\s+notice|"
            r"deemed\s+to\s+have\s+been\s+duly\s+given)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.NON_SOLICIT,
        re.compile(
            r"\b(non-?solicit(?:ation)?|shall\s+not\s+solicit|"
            # "shall solicit for employment" or "solicit employees" etc.
            r"solicit\s+(?:for\s+employment\s+)?(?:any\s+)?(?:the\s+other\s+"
            r"party'?s?\s+)?(?:employees?|customers?|personnel|staff)|"
            r"solicit\s+(?:any\s+of\s+the\s+other|employees|customers|"
            r"personnel))\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.COUNTERPARTS,
        re.compile(
            r"\b(counterparts?|"
            r"executed\s+in\s+one\s+or\s+more\s+counterparts|"
            r"facsimile\s+(?:or\s+(?:electronic\s+)?)?signatures?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClauseType.TERM,
        re.compile(
            r"\b(term\s+of\s+(?:this\s+)?agreement|"
            r"(?:effective|expir)\s+(?:date|period)|"
            r"(?:this\s+)?agreement\s+(?:shall|will)\s+(?:remain|continue|"
            r"be\s+in\s+(?:full\s+)?force)\s+(?:in\s+effect\s+)?"
            r"for\s+a\s+period\s+of|"
            r"for\s+a\s+period\s+of\s+(?:\w+\s+)?(?:\d+)\s+years?)\b",
            re.IGNORECASE,
        ),
    ),
]


def _rule_based_classify(
    text: str,
    *,
    section_title: str = "",
) -> tuple[ClauseType, float]:
    """Return ``(type, confidence)`` for ``text`` using the keyword rules.

    Confidence is a hard-coded value (0.55) for the rule-based path —
    the LLM is the only thing that produces calibrated confidence in
    Phase 1, and the eval harness (Phase 2) is what measures quality.

    The ``section_title`` argument is a strong signal: when the
    chunker has identified a clean heading (e.g. ``"CONFIDENTIALITY"``,
    ``"DEFINITIONS"``, ``"TERM"``, ``"GOVERNING LAW"``), we trust it
    over the body keywords. The body text in synthetic / weird-format
    NDAs is often fragmentary (a soft-line wrap that gets cut short by
    pymupdf) and the heading is the cleanest hint we have.
    """
    if section_title:
        title = section_title.strip().upper()
        # Clean trailing punctuation so "TERM." and "TERM" both match.
        title = title.rstrip(".?:")
        title_to_type: dict[str, ClauseType] = {
            "CONFIDENTIALITY": ClauseType.DEFINITION_CONFIDENTIAL_INFO,
            "DEFINITIONS": ClauseType.DEFINITION_CONFIDENTIAL_INFO,
            "CONFIDENTIAL INFORMATION": ClauseType.DEFINITION_CONFIDENTIAL_INFO,
            "TERM": ClauseType.TERM,
            "GOVERNING LAW": ClauseType.GOVERNING_LAW,
            "ENTIRE AGREEMENT": ClauseType.ENTIRE_AGREEMENT,
            "INTEGRATION": ClauseType.ENTIRE_AGREEMENT,
            "INJUNCTIVE RELIEF": ClauseType.INJUNCTIVE_RELIEF,
            "RESIDUAL KNOWLEDGE": ClauseType.RESIDUAL_KNOWLEDGE,
            "RETURN OF MATERIALS": ClauseType.RETURN_OF_MATERIALS,
            "NON-SOLICITATION": ClauseType.NON_SOLICIT,
            "NON-SOLICIT": ClauseType.NON_SOLICIT,
            "NON-COMPETITION": ClauseType.NON_COMPETE,
            "NON-COMPETE": ClauseType.NON_COMPETE,
            "INDEMNITY": ClauseType.INDEMNITY,
            "INDEMNIFICATION": ClauseType.INDEMNITY,
            "LIMITATION OF LIABILITY": ClauseType.LIMITATION_OF_LIABILITY,
            "ASSIGNMENT": ClauseType.ASSIGNMENT,
            "SEVERABILITY": ClauseType.SEVERABILITY,
            "NOTICES": ClauseType.NOTICES,
            "NOTICE": ClauseType.NOTICES,
            "COUNTERPARTS": ClauseType.COUNTERPARTS,
        }
        if title in title_to_type:
            return title_to_type[title], 0.6
    for ctype, pattern in _RULES:
        if pattern.search(text):
            return ctype, 0.55
    return ClauseType.UNKNOWN, 0.0


# --- LLM call -----------------------------------------------------------

def _looks_like_real_key(value: str) -> bool:
    """True when ``value`` looks like a real LLM API key (not a placeholder)."""
    if not value:
        return False
    lowered = value.lower()
    if "placeholder" in lowered or "***" in value:
        return False
    # Real OpenAI keys start with "sk-"; OpenRouter keys start with "sk-or-".
    # Anything else 30+ chars that's not a placeholder is likely real.
    return value.startswith("sk-") or len(value) >= 30


def _call_llm_for_classification(
    clause_text: str, *, contract_filename: str
) -> tuple[ClauseType, float]:
    """Call the LLM and return ``(type, confidence)``.

    Raises on transport / parse failure — the caller decides whether
    to retry or fall back. The OpenAI client is constructed on every
    call rather than cached as a module global so that tests can
    monkey-patch ``settings.llm_api_key`` between calls.
    """
    from openai import OpenAI  # type: ignore[import-not-found]

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
    messages = build_messages(clause_text)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.0,
        max_tokens=80,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ValueError("LLM returned an empty completion")
    data = json.loads(raw)
    type_str = str(data.get("type", "")).strip()
    conf = float(data.get("confidence", 0.0))
    # Pydantic-validate the type string against the enum.
    clause_type = ClauseType(type_str)
    return clause_type, max(0.0, min(1.0, conf))


# --- Public surface -----------------------------------------------------

def classify_clause(
    raw_id: str,
    raw_text: str,
    *,
    section: str = "",
    section_title: str = "",
    paragraph_index: list[int] | None = None,
    contract_filename: str = "",
) -> Clause:
    """Classify a single raw clause. Returns a fully-populated ``Clause``.

    The function:

    1. Calls the LLM (or the rule-based fallback) with retries.
    2. Wraps the call in a Langfuse ``trace`` named
       ``"classify_clause"`` with the contract filename as a tag.
    3. Returns a ``Clause`` whose ``id`` is preserved from the
       chunker (``raw_id``) and whose other fields are filled in.
    """
    langfuse = get_langfuse()
    span: Any = _NoopSpan()
    try:
        span = langfuse.trace(
            name="classify_clause",
            tags=[contract_filename] if contract_filename else [],
            input={"clause_id": raw_id, "clause_length": len(raw_text)},
        )
    except Exception:  # noqa: BLE001
        span = _NoopSpan()

    # LLM call path with retries.
    ctype: ClauseType = ClauseType.UNKNOWN
    confidence: float = 0.0
    used_fallback = False
    error_summary: str | None = None

    if _looks_like_real_key(settings.llm_api_key):
        last_error: Exception | None = None
        for attempt in range(3):  # 1 try + 2 retries
            try:
                ctype, confidence = _call_llm_for_classification(
                    raw_text, contract_filename=contract_filename
                )
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "LLM classify attempt %d failed: %s", attempt + 1, exc
                )
        if last_error is not None:
            error_summary = f"LLM call failed after 3 attempts: {last_error}"
            logger.warning("%s — falling back to rule-based classifier", error_summary)
            ctype, confidence = _rule_based_classify(
                raw_text, section_title=section_title
            )
            used_fallback = True
    else:
        ctype, confidence = _rule_based_classify(
            raw_text, section_title=section_title
        )
        used_fallback = True

    # End the trace with the outcome.
    try:
        if hasattr(span, "update"):
            span.update(
                output={
                    "type": ctype.value,
                    "confidence": confidence,
                    "used_fallback": used_fallback,
                },
                metadata={"error": error_summary} if error_summary else {},
            )
        if hasattr(span, "end"):
            span.end()
    except Exception:  # noqa: BLE001
        # Never let trace-update failures affect the return value.
        pass

    return Clause(
        id=raw_id,
        text=raw_text,
        position=ClausePosition(
            section=section,
            section_title=section_title,
            paragraph_index=list(paragraph_index or []),
        ),
        type=ctype,
        language="en",
        confidence=confidence,
    )


def classify_clauses(
    raw_clauses: list[Any],  # list[RawClause] — kept untyped to avoid a cycle
    *,
    contract_filename: str = "",
) -> list[Clause]:
    """Classify a list of :class:`app.parse.chunker.RawClause`.

    The classifier calls are sequential. Phase 1 is mechanical —
    no agent, no parallelism. Each call produces one Langfuse trace.
    """
    classified: list[Clause] = []
    for raw in raw_clauses:
        clause = classify_clause(
            raw_id=raw.id,
            raw_text=raw.text,
            section=raw.section,
            section_title=raw.section_title,
            paragraph_index=raw.paragraph_indices,
            contract_filename=contract_filename,
        )
        classified.append(clause)
    return classified
