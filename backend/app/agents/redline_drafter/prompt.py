"""Prompts for the redline drafter agent.

Two surfaces, mirroring :mod:`app.agents.deviation_spotter.prompt`:

- :data:`SYSTEM_PROMPT` — the role definition + the output format
  spec. This is the "what to return" instruction the LLM sees on
  every call.
- :func:`build_user_message` — the per-call user prompt. Wraps
  the contract clause + the matched baseline + the flag context
  in a deterministic, parseable format. On a self-check retry,
  the drafter passes the :class:`SelfCheckConstraint` to inject
  an explicit "your previous proposal introduced a new deviation"
  instruction into the user message.

Few-shot examples
-----------------
The spec calls out the drafter as a higher-stakes prompt than
the spotter (the drafter's output goes straight into the
tracked-changes .docx). We include 2 examples covering (a) a
clean rewrite (term reduction) and (b) a rewrite that handles
a counterparty carve-out. The examples are baked into the
system prompt so the per-call token cost stays low.

Why the drafter's output format is plain text, not JSON
-------------------------------------------------------
The deviation spotter's JSON output is parsed into a typed
:class:`DeviationFlag`. The drafter's output (``proposed_text``,
``rationale``, ``diff_summary``) is **not** parsed from a JSON
object — it's parsed from a JSON object via the OpenAI
``response_format=json_object`` flag. The reason for JSON over
plain text is the same as the spotter's: a misbehaving model
that emits a markdown fence or a leading prose sentence would
fail the parser, and the agent would retry. JSON is the safest
target.

The drafter's contract text **is** plain text inside the JSON
object — the drafter does NOT escape the proposed clause (the
docx writer receives the raw string from the parsed JSON and
inserts it verbatim). The system prompt is explicit: "do NOT
wrap the proposed_text in quotes, do NOT escape the text,
just emit the raw clause body."

Self-check retry prompt
-----------------------
The self-check loop (:mod:`.self_check`) injects a constraint
into the user message on the retry:

  "Your previous proposal introduced a NEW deviation:
   <score + rationale + citation from the spotter's re-run>.
   Rewrite to address the ORIGINAL flag
   (<original flag's score + rationale>) WITHOUT introducing
   this new one."

The constraint text is rendered as a dedicated section in the
user message so the LLM can't miss it. We do NOT modify the
system prompt between attempts — the system prompt is the
"how to do your job" instruction, and changing it between
attempts would invalidate the few-shot examples. The
self-check constraint is a per-call instruction, which
belongs in the user message.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.agents.deviation_spotter.schema import DeviationFlag
from app.agents.redline_drafter.schema import (
    DrafterInput,
    SelfCheckConstraint,
)


# --- System prompt ------------------------------------------------------


SYSTEM_PROMPT = """\
You are the redline-drafter agent for clausecraft, a contract \
analysis platform. Your job is to rewrite a single clause from \
a contract so that it aligns with the matched playbook baseline.

The user has ACCEPTED a deviation flag for this clause. The \
flag is the spotter's verdict that the clause differs from the \
baseline. Your job is to produce a redline (a rewritten clause \
that aligns with the baseline) — NOT to argue with the flag. \
If the user attached extra context, honor it; otherwise, the \
baseline is the target.

## Output format

Return a single JSON object with EXACTLY these fields (no \
additional fields, no prose outside the JSON):

```json
{{
  "proposed_text": "<the rewritten clause body, verbatim, \
drop-in replacement for the original>",
  "rationale": "<1-3 sentences, plain English, no preamble>",
  "diff_summary": "<plain-text before/after summary, no \
markdown, no diff syntax, suitable for an audit log>"
}}
```

Critical rules for `proposed_text`:

1. **Verbatim drop-in.** The `proposed_text` replaces the \
   original clause in the .docx output. The drafter's job is \
   to produce a single coherent edit, not a diff. Do NOT wrap \
   the text in quotes. Do NOT escape special characters. Emit \
   the raw clause body.
2. **Preserve structure.** If the original clause has numbered \
   list items, "provided that" carve-outs, or definitions of \
   terms used elsewhere in the contract, preserve them. The \
   redline is a single edit, not a fragment swap.
3. **Stay close to the baseline.** The baseline is the target. \
   If the user attached extra context (e.g. "limit to 5 years, \
   not the baseline's 3"), the user context overrides the \
   baseline's exact text. Otherwise, the baseline's text is \
   authoritative.

Critical rules for `rationale`:

1. **Plain English.** The audit log renders this verbatim. A \
   human reviewer reads it to understand *what you changed* and \
   *why*. No marketing language, no "as per the user's \
   request" boilerplate.
2. **1-3 sentences.** If your rationale is longer than that, \
   you're explaining, not redlining.
3. **Name the deviation you're fixing.** Example: "Term of 7 \
   years reduced to the baseline's 3-year maximum. Carve-out \
   for trade secrets preserved from the original."

Critical rules for `diff_summary`:

1. **Plain text.** The audit log + JSON export render this \
   verbatim. No markdown, no diff syntax (no `+` / `-` lines, \
   no unified-diff markers). A single short paragraph.
2. **Before / after.** Example: "Term: 7 years → 3 years. \
   Carve-out for trade secrets: preserved. Governing law \
   reference: unchanged."

## When the clause is unfixable

If the deviation is structural (e.g. the contract is a \
perpetual NDA and the baseline is a 3-year term, and the \
"perpetuity" is the entire deal), do NOT try to rewrite the \
clause into something the counterparty will never accept. \
Return your best attempt anyway — the self-check loop will \
catch it and the HITL UI will surface the conflict to the \
user. **The drafter always returns a redline; the self-check \
loop decides whether to ship it.**

## Examples

### Example 1 — clean rewrite (term reduction)

Contract clause: "The receiving party shall maintain confiden\
tiality for a period of seven (7) years from the date of \
disclosure."

Flag (score=2, rationale="Term of 7 years exceeds the \
baseline's 3-year maximum for NDAs involving trade secrets."): \
material deviation.

Baseline (clause_id="term-of-confidentiality", type="term"): \
"Confidentiality obligations shall remain in effect for a \
period of three (3) years from the date of disclosure."

```json
{{
  "proposed_text": "Confidentiality obligations shall remain \
in effect for a period of three (3) years from the date of \
disclosure.",
  "rationale": "Term of 7 years reduced to the baseline's 3-\
year maximum. The original clause's 'receiving party' is \
preserved as 'obligations' (the baseline's neutral framing \
matches our standard NDA form).",
  "diff_summary": "Term: 7 years → 3 years. Subject: 'receiv\
ing party' → 'obligations' (neutral framing per baseline). \
Other: unchanged."
}}
```

### Example 2 — rewrite honoring user context (term override)

Contract clause: "Confidentiality obligations shall remain in \
effect for a period of three (3) years from the date of \
disclosure, except for trade secrets, which shall remain \
confidential for a period of seven (7) years from the date of \
disclosure."

Flag (score=2): material deviation (carve-out for trade \
secrets exceeds the 3-year term).

Baseline: "Confidentiality obligations shall remain in \
effect for a period of three (3) years from the date of \
disclosure."

Extra context from user: "Acceptable for our use case if the \
trade-secrets carve-out is limited to 5 years."

```json
{{
  "proposed_text": "Confidentiality obligations shall remain \
in effect for a period of three (3) years from the date of \
disclosure, except for trade secrets, which shall remain \
confidential for a period of five (5) years from the date of \
disclosure.",
  "rationale": "Trade-secrets carve-out limited to 5 years \
per the user's extra context. The 3-year base term matches \
the baseline. The carve-out structure (except-for-trade-\
secrets) is preserved from the original.",
  "diff_summary": "Term: 3 years (base, matches baseline) + \
5 years (trade-secrets carve-out, per user context) — was 3 \
+ 7. Carve-out structure: preserved."
}}
```
"""


# --- Self-check retry instruction --------------------------------------


def _format_flag_for_constraint(label: str, flag: DeviationFlag) -> str:
    """Render a :class:`DeviationFlag` for the self-check constraint.

    The constraint text appears in the user message on the retry.
    The drafter needs the spotter's score + rationale + citation
    so it can understand the new deviation and avoid it.

    The format is a labelled bullet list (not a JSON dump) so the
    LLM can parse it reliably. We avoid backticks / code fences
    here — the surrounding user message has its own code fences
    and nested fences are a parser-fragility risk.
    """
    score_label = {
        0: "aligned (0)",
        1: "minor (1)",
        2: "material (2)",
        3: "unacceptable (3)",
    }.get(flag.score, f"unknown ({flag.score})")
    parts = [
        f"{label} score: {score_label}",
        f"{label} rationale: {flag.rationale}",
    ]
    if flag.citation is not None:
        parts.append(
            f"{label} citation: clause_id={flag.citation.playbook_clause_id}, "
            f"excerpt=\"{flag.citation.contract_text_excerpt}\""
        )
    else:
        parts.append(f"{label} citation: (none)")
    if flag.baseline_type:
        parts.append(f"{label} baseline_type: {flag.baseline_type}")
    return "\n".join(parts)


# --- User prompt --------------------------------------------------------


def build_user_message(
    drafter_input: DrafterInput,
    *,
    self_check_constraint: Optional[SelfCheckConstraint] = None,
) -> str:
    """Return the per-call user message for the drafter.

    The message has five parts, in this order:

    1. **The accepted flag** — the spotter's verdict the user
       approved. The drafter reads the score + rationale to
       understand *why* the clause was flagged.
    2. **The original clause** — the text the drafter rewrites.
    3. **The matched baseline** — the target the rewrite aligns
       toward. The drafter's prompt renders the baseline as a
       JSON block (matching the spotter's format) so the LLM
       sees the same shape.
    4. **Extra context** — the user's free-form context from
       the HITL review (if any). The drafter surfaces this in
       the rationale.
    5. **Self-check constraint** — only on the retry. The
       previous attempt's text + the spotter's new flag, so
       the drafter knows what to avoid in attempt #2.

    On a self-check retry, the parts are reordered: the
    constraint moves to position 1 (after the section header)
    so the LLM can't miss it. The rest of the message is
    identical to a first-attempt call.
    """
    flag = drafter_input.flag
    baseline = drafter_input.baseline

    baseline_payload: dict[str, Any] = {
        "id": baseline.clause_id,
        "type": baseline.type,
        "title": baseline.title,
        "text": baseline.text,
        "source_url": baseline.source_url,
        "similarity": round(float(baseline.similarity), 4),
    }
    baseline_json = json.dumps(baseline_payload, indent=2, ensure_ascii=False)
    # Escape triple-backticks in the clause text to avoid closing
    # the JSON block early. Same pattern as the spotter.
    safe_clause = drafter_input.clause_text.replace("```", "ʼʼʼ")
    safe_baseline = baseline.text.replace("```", "ʼʼʼ")

    if self_check_constraint is None:
        # First attempt — standard prompt shape.
        extra_block = ""
        if drafter_input.extra_context:
            extra_block = (
                "\n## Extra context from the user\n\n"
                "The user attached the following context when "
                "accepting this flag. Honor it in the redline:\n\n"
                f"> {drafter_input.extra_context}\n"
            )
        return (
            "## Accepted deviation flag\n\n"
            f"- flag score: {flag.score} "
            f"({_score_label(flag.score)})\n"
            f"- flag rationale: {flag.rationale}\n"
            f"- baseline_type: {flag.baseline_type or '(none)'}\n"
            + (
                f"- citation: clause_id="
                f"{flag.citation.playbook_clause_id}, "
                f"excerpt=\"{flag.citation.contract_text_excerpt}\"\n"
                if flag.citation is not None
                else "- citation: (none)\n"
            )
            + extra_block
            + "\n## Original clause (to be redlined)\n\n"
            "```\n"
            f"{safe_clause}\n"
            "```\n\n"
            "## Matched playbook baseline (the target)\n\n"
            "```json\n"
            f"{baseline_json}\n"
            "```\n\n"
            "## Baseline clause text (rendered for readability)\n\n"
            "```\n"
            f"{safe_baseline}\n"
            "```\n\n"
            "## Task\n\n"
            "Rewrite the original clause so it aligns with the "
            "baseline. If extra context is attached, honor it "
            "(the user context overrides the baseline's exact "
            "text). Return ONLY the JSON object — `proposed_text`, "
            "`rationale`, `diff_summary` — with no prose, no "
            "markdown, no explanation outside the JSON."
        )

    # Self-check retry — constraint at the top so the drafter
    # can't miss it.
    conflict_text = _format_flag_for_constraint(
        "Conflicting spotter flag", self_check_constraint.conflicting_flag
    )
    original_flag_text = _format_flag_for_constraint(
        "Original accepted flag", flag
    )
    safe_previous = self_check_constraint.previous_proposed_text.replace(
        "```", "ʼʼʼ"
    )
    return (
        "## Self-check retry — your previous attempt failed the spotter\n\n"
        "Your previous proposal introduced a NEW deviation. The "
        "spotter was re-run on it and flagged the following:\n\n"
        f"{conflict_text}\n\n"
        "The ORIGINAL flag the user accepted (which you are "
        "supposed to be fixing) was:\n\n"
        f"{original_flag_text}\n\n"
        "Your previous proposal (which introduced the new "
        "deviation):\n\n"
        "```\n"
        f"{safe_previous}\n"
        "```\n\n"
        "## Matched playbook baseline (the target)\n\n"
        "```json\n"
        f"{baseline_json}\n"
        "```\n\n"
        "## Task\n\n"
        "Rewrite the original clause so it addresses the "
        "ORIGINAL flag WITHOUT introducing the new deviation "
        "above. Stay close to the baseline, but if the new "
        "deviation points to a structural conflict (e.g. the "
        "baseline requires a 3-year term and the new deviation "
        "requires a perpetual term, and the user's original "
        "context doesn't resolve it), produce your best attempt "
        "anyway — the self-check loop will surface the conflict "
        "to the user.\n\n"
        "Return ONLY the JSON object — `proposed_text`, "
        "`rationale`, `diff_summary` — with no prose, no "
        "markdown, no explanation outside the JSON."
    )


def _score_label(score: int) -> str:
    """Human-readable label for a deviation score (0..3)."""
    return {
        0: "aligned",
        1: "minor",
        2: "material",
        3: "unacceptable",
    }.get(score, f"unknown ({score})")


# --- Messages -----------------------------------------------------------


def build_messages(
    drafter_input: DrafterInput,
    *,
    self_check_constraint: Optional[SelfCheckConstraint] = None,
) -> list[dict[str, str]]:
    """Return the chat messages list for a single drafter call.

    Mirrors the spotter's :func:`app.agents.deviation_spotter.prompt.build_messages`
    shape: a single system message + a single user message. The
    system prompt is identical between attempts (the self-check
    constraint goes in the user message). The few-shot examples
    in the system prompt are calibrated for first-attempt calls
    but the retry path is rare enough (≤10% of accepted flags in
    our rough estimate) that we don't bother swapping examples.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_message(
                drafter_input,
                self_check_constraint=self_check_constraint,
            ),
        },
    ]


__all__ = [
    "SYSTEM_PROMPT",
    "build_user_message",
    "build_messages",
]
