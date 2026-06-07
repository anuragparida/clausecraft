"""Classifier prompt — Phase 1.

The system prompt + 2 few-shot examples the classifier sends to the
LLM. Kept in a module (not a YAML or DB) because Phase 1 has no
prompt-management infrastructure; Phase 2 (eval harness) will grow
one.

The few-shot examples cover two distinct cases:

1. A "definition of confidential information" clause — the most
   common NDA clause, and the one the LLM most reliably mislabels
   as ``term`` when the clause body mentions a "period of N years".
2. A "governing law" clause — short, jurisdiction-named, easy to
   confuse with ``notices`` or ``entire_agreement``.
"""

from __future__ import annotations

from app.classify.schema import ClauseType

# Keep the system prompt short but specific. We name every valid
# enum value (excluding ``unknown``) and explain the confidence rule.
SYSTEM_PROMPT = """You are a contract-clause classifier for English-language \
Non-Disclosure Agreements (NDAs). You will be given the text of a single \
clause extracted from a larger NDA. Your job is to assign it exactly one \
clause type from the following taxonomy:

{definition_confidential_info} — defines what counts as "Confidential \
Information" (e.g. "Confidential Information means any non-public \
information disclosed by one party to the other...")

{term} — specifies how long the obligation lasts (e.g. "This Agreement \
shall remain in effect for a period of three (3) years...")

{governing_law} — names the jurisdiction whose laws govern the \
agreement (e.g. "This Agreement shall be governed by the laws of the \
State of New York...")

{injunctive_relief} — acknowledges that breach may cause irreparable \
harm warranting injunction (e.g. "The parties acknowledge that monetary \
damages may be inadequate and that injunctive relief shall be available...")

{residual_knowledge} — permits retention of information in unaided \
memory (e.g. "Nothing herein shall restrict the use of residual \
knowledge retained in the memory of personnel...")

{return_of_materials} — requires return or destruction of confidential \
materials on request (e.g. "Upon termination, each party shall return or \
destroy all Confidential Information...")

{non_solicit} — restricts solicitation of employees or customers \
(e.g. "For a period of twelve months, neither party shall solicit the \
other's employees...")

{non_compete} — restricts competing business activity (rare in NDAs, \
but possible)

{indemnity} — shifts liability for breach (e.g. "The disclosing party \
shall indemnify the receiving party for any losses...")

{limitation_of_liability} — caps or excludes damages

{assignment} — governs transfer of rights (e.g. "Neither party may \
assign this Agreement without prior written consent...")

{entire_agreement} — declares the document the complete agreement \
between the parties

{severability} — addresses the effect of an unenforceable provision

{notices} — sets the channel/address for formal notices

{counterparts} — permits execution in counterparts (e.g. "This \
Agreement may be executed in counterparts...")

Return a JSON object with:
- "type": one of the values above (or "unknown" if none fit ≥40% confidence)
- "confidence": a float between 0.0 and 1.0

Rules:
- The "type" field must be exactly one of the values listed.
- "confidence" is your own estimate of how certain you are. 0.0 means \
you're guessing; 1.0 means the clause text is a textbook example of \
the type. Never return a value outside [0.0, 1.0].
- Do NOT include the text of the clause in your response. Only the \
"type" and "confidence" fields.
""".format(
    definition_confidential_info=ClauseType.DEFINITION_CONFIDENTIAL_INFO.value,
    term=ClauseType.TERM.value,
    governing_law=ClauseType.GOVERNING_LAW.value,
    injunctive_relief=ClauseType.INJUNCTIVE_RELIEF.value,
    residual_knowledge=ClauseType.RESIDUAL_KNOWLEDGE.value,
    return_of_materials=ClauseType.RETURN_OF_MATERIALS.value,
    non_solicit=ClauseType.NON_SOLICIT.value,
    non_compete=ClauseType.NON_COMPETE.value,
    indemnity=ClauseType.INDEMNITY.value,
    limitation_of_liability=ClauseType.LIMITATION_OF_LIABILITY.value,
    assignment=ClauseType.ASSIGNMENT.value,
    entire_agreement=ClauseType.ENTIRE_AGREEMENT.value,
    severability=ClauseType.SEVERABILITY.value,
    notices=ClauseType.NOTICES.value,
    counterparts=ClauseType.COUNTERPARTS.value,
)


# Two few-shot examples. Each is (clause_text, expected_type).
FEW_SHOT_EXAMPLES: list[dict[str, str]] = [
    {
        "role": "user",
        "content": (
            "Clause: \"Confidential Information means any non-public "
            "technical, business, or financial information disclosed by "
            "one party to the other, whether orally or in writing, that "
            "is marked as confidential or that a reasonable person "
            "would understand to be confidential.\""
        ),
    },
    {
        "role": "assistant",
        "content": '{"type": "definition_confidential_info", "confidence": 0.97}',
    },
    {
        "role": "user",
        "content": (
            "Clause: \"This Agreement shall be governed by and "
            "construed in accordance with the laws of the State of "
            "California, without regard to its conflict of laws "
            "principles.\""
        ),
    },
    {
        "role": "assistant",
        "content": '{"type": "governing_law", "confidence": 0.98}',
    },
]


def build_messages(clause_text: str) -> list[dict[str, str]]:
    """Return the chat messages list for a single classification call.

    The shape is OpenAI-compatible: ``[{"role": "system", ...}, ...]``.
    The caller adds the user message containing the clause text.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT_EXAMPLES,
        {"role": "user", "content": f"Clause: \"{clause_text}\""},
    ]
