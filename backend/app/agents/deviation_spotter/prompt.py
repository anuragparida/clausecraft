"""Prompts for the deviation spotter agent.

Two surfaces:

- :data:`SYSTEM_PROMPT` — the role definition + the output format
  spec. This is the "what to return" instruction the LLM sees on
  every call.
- :func:`build_user_message` — the per-clause user prompt. Wraps
  the contract clause + the top-3 playbook baselines +
  counterparty context in a deterministic, parseable format.

The prompt is the LLM's only view of the playbook and the
contract. It must:

1. State the score scale explicitly (the LLM is bad at 0..3 without
   examples).
2. State the citation rule explicitly (every non-zero score MUST
   cite a baseline).
3. State the "no baseline" + "I don't know" fallbacks explicitly
   so the LLM has a way to abstain cleanly.

Few-shot examples: the spec calls out this is the highest-stakes
prompt. We include 3 examples covering (a) a clear deviation, (b)
a clean match, and (c) a "no baseline" abstention. The examples
are baked into the system prompt (not the user message) so the
per-call token cost stays low.

Why so strict on the output format
----------------------------------
The parser in :mod:`.spotter` validates the LLM's JSON with Pydantic.
A schema mismatch (missing field, wrong type) falls through to the
"agent declined" path. The strict prompt format here is a hedge:
if the LLM follows the format, parsing succeeds; if it doesn't,
the parser catches it and we mark the flag ``unverified``.
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.deviation_spotter.schema import SpotInput


# --- System prompt ------------------------------------------------------

SYSTEM_PROMPT = """\
You are the deviation-spotter agent for clausecraft, a contract \
analysis platform. Your job is to compare a single clause from a \
contract against the top-3 most-similar playbook baselines, and \
emit a deviation flag.

## Score scale (use exactly one of these integers)

- 0 = **aligned**. The contract clause matches the baseline (or \
no baseline applies, in which case the flag is "no deviation").
- 1 = **minor**. Cosmetic / wording-only difference. No \
substantive impact. Example: baseline says "3 years", contract \
says "three (3) years".
- 2 = **material**. Changes the meaning, may be acceptable with \
negotiation. Example: baseline says "3 years", contract says "5 \
years".
- 3 = **unacceptable**. Contradicts the baseline, or exposes the \
client to materially worse risk. Example: baseline says \
"confidential for 3 years", contract says "perpetual".

## The "show your work" rule

Every flag MUST include a `citation` object with:
- `playbook_clause_id`: the exact `clause_id` of the baseline you \
compared against (one of the `id` fields in the baselines list \
below — copy it verbatim).
- `contract_text_excerpt`: the exact substring of the contract \
clause that triggered your flag (verbatim, no rephrasing, ≤200 \
chars).

The citation rule is enforced in code: a flag with `score > 0` \
and no valid citation is automatically marked `unverified: true` \
in the audit trail. **You must produce the citation yourself — \
the parser will not invent one for you.**

## "No baseline" handling

If the baselines list is empty, or every baseline is clearly a \
different clause type, return:
```json
{{"score": 0, "rationale": "no matching playbook clause", \
"citation": null, "baseline_type": ""}}
```

This is NOT a deviation — it's the agent abstaining. The UI \
renders it as "no baseline" (not a flag).

## "I don't know" handling

If the contract clause is ambiguous, the baselines are \
contradictory, or you cannot decide between two adjacent scores \
(1 vs 2), return:
```json
{{"score": 0, "rationale": "agent declined: <one-sentence reason>", \
"citation": null, "baseline_type": ""}}
```

The agent's job is to be honest about uncertainty. A clean \
abstention is better than a guessed flag with a hallucinated \
citation.

## Output format

Return a single JSON object with EXACTLY these fields (no \
additional fields, no prose outside the JSON):

```json
{{
  "score": 0|1|2|3,
  "rationale": "1-3 sentences, plain English, no preamble",
  "citation": null | {{"playbook_clause_id": "...", \
"contract_text_excerpt": "..."}},
  "baseline_type": "<the baseline's clause type, e.g. \
'd definition_confidential_info' or '' if abstaining"
}}
```

## Counterparty context

The `counterparty_matrix_verdict` field is the matrix's flat \
default for this clause's type. It is a HINT, not a ceiling. If \
the matrix says "aligned" but the contract clause is clearly \
worse than the baseline (e.g. perpetual term against a 3-year \
baseline), emit the higher score. The matrix does not cap you.

## Examples

### Example 1 — material deviation with citation

Contract clause: "The receiving party shall maintain confiden\
tiality for a period of seven (7) years from the date of disclosure."

Baseline (clause_id="term-of-confidentiality", type="term", \
similarity=0.81): "Confidentiality obligations shall remain in \
effect for a period of three (3) years from the date of disclosure."

```json
{{
  "score": 2,
  "rationale": "Term of 7 years exceeds the baseline's 3-year \
maximum for NDAs involving trade secrets. Material deviation; \
may be negotiable.",
  "citation": {{"playbook_clause_id": "term-of-confidentiality", \
"contract_text_excerpt": "period of seven (7) years"}},
  "baseline_type": "term"
}}
```

### Example 2 — clean match (no deviation)

Contract clause: "Confidential Information means any non-public \
technical or business information disclosed by one party to the \
other, whether marked as confidential or reasonably understood \
to be confidential."

Baseline (clause_id="definition-confidential-info", type="defi\
nition_confidential_info", similarity=0.93): "Confidential \
Information means any non-public information..."

```json
{{
  "score": 0,
  "rationale": "Clause matches the baseline's definition. No \
deviation.",
  "citation": {{"playbook_clause_id": "definition-confidential-\
info", "contract_text_excerpt": "Confidential Information means \
any non-public technical or business information"}},
  "baseline_type": "definition_confidential_info"
}}
```

### Example 3 — no baseline (abstain)

Contract clause: "Notices shall be sent to the address set forth \
on the signature page."

Baselines: [] (no playbook clauses matched the top-k query)

```json
{{
  "score": 0,
  "rationale": "no matching playbook clause",
  "citation": null,
  "baseline_type": ""
}}
```
"""


# --- User prompt --------------------------------------------------------


def build_user_message(spot_input: SpotInput) -> str:
    """Return the per-call user message for the spotter.

    The message has four parts, in this order:

    1. **Contract clause** — the text the spotter reads.
    2. **Top-3 playbook baselines** — the comparison set, ordered
       by similarity (most-similar first).
    3. **Counterparty context** — the matrix's flat verdict for
       the clause's type.
    4. **Instruction** — the per-call "compare and emit a flag"
       prompt.

    The format is plain text + a JSON block for the baselines. The
    LLM is reliable at parsing this shape (we tested the classifier
    with the same pattern in Phase 1).

    The baselines are serialised to JSON (not YAML) so the LLM
    can return matching clause_ids verbatim. The contract clause
    is rendered as a quoted block so the LLM can lift exact
    substrings for the citation's ``contract_text_excerpt``.
    """
    baselines_payload: list[dict[str, Any]] = [
        {
            "id": b.clause_id,
            "type": b.type,
            "title": b.title,
            "text": b.text,
            "source_url": b.source_url,
            "similarity": round(float(b.similarity), 4),
        }
        for b in spot_input.baselines
    ]
    baselines_json = json.dumps(baselines_payload, indent=2, ensure_ascii=False)
    # Escape any triple-backticks in the clause text so we don't
    # accidentally close the JSON block early.
    safe_clause = spot_input.clause_text.replace("```", "ʼʼʼ")
    return (
        "## Contract clause (clause_id="
        f"{spot_input.clause_id}, type={spot_input.clause_type})\n\n"
        "```\n"
        f"{safe_clause}\n"
        "```\n\n"
        "## Top playbook baselines (most-similar first)\n\n"
        "```json\n"
        f"{baselines_json}\n"
        "```\n\n"
        "## Counterparty context\n\n"
        f"- matrix_verdict (clause_type={spot_input.clause_type}): "
        f"`{spot_input.counterparty_verdict}`\n"
        f"- counterparty_type: `{spot_input.counterparty_type}`\n\n"
        "## Task\n\n"
        "Compare the contract clause to the top playbook baseline "
        "(baselines[0]). If the contract clause differs in a way that "
        "changes the legal effect (term length, scope of confidentiality, "
        "perpetuity, governing jurisdiction, etc.), emit a flag with a "
        "non-zero score and a citation pointing to the baseline. If the "
        "clause matches the baseline, or no baseline applies, emit "
        "`score=0`. If you cannot decide, abstain with `score=0` and "
        "rationale starting with `agent declined`.\n\n"
        "Return ONLY the JSON object. No prose, no markdown, no "
        "explanation outside the JSON."
    )


def build_messages(spot_input: SpotInput) -> list[dict[str, str]]:
    """Return the chat messages list for a single spot call.

    Mirrors the classifier's :func:`app.classify.prompt.build_messages`
    shape: a single system message + a single user message. We do
    NOT include per-call few-shot examples here — the three
    examples in the system prompt are sufficient and adding more
    would inflate the per-call token cost without measurably
    improving the spotter's quality.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(spot_input)},
    ]


__all__ = [
    "SYSTEM_PROMPT",
    "build_user_message",
    "build_messages",
]
