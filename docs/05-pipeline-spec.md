# 05 — Pipeline Spec

> Per-agent inputs, outputs, model, prompt strategy, error handling.

**Status:** stub.

## Agents (real ones, not theatre)

The seed describes 6 stages; I argue 3 of them are real agents and 3 are mechanical. The agents earn the multi-agent framing; the mechanical steps don't.

| Stage | Real agent? | Model | Inputs | Outputs |
|---|---|---|---|---|
| Ingest | No | n/a | PDF/DOCX | text + section metadata |
| Parse | No | n/a | text | clause list (id, text, position) |
| Classify | Maybe (DeBERTa) | small classifier or prompted LLM | clause | clause_type enum |
| Playbook lookup | No (vector retrieval) | embeddings | clause_type, clause_text | top-k baseline clauses |
| **Deviation spotter** | **YES** | LLM (Sonnet-class) | clause + baseline + counterparty | score 0–3 + rationale + citation |
| **Redline drafter** | **YES** | LLM (Sonnet-class) | accepted flag + clause + baseline | proposed alternative text + rationale |
| HITL review | **YES** (real pause) | n/a (user) | flag table | per-flag decisions |
| Summary memo | No (one-shot LLM) | LLM | flag table + contract meta | 1-page memo |

## Deviation spotter (the core agent)

- **Inputs:** `{clause_text, clause_type, baseline_clause, baseline_provenance, counterparty_context, language}`
- **Output (Pydantic):** `{score: 0|1|2|3, rationale: str, citation: {playbook_clause_id, contract_text_excerpt}, unverified: bool}`
- **Prompt strategy:** system prompt with the playbook schema + a worked example per severity level; few-shot with 2-3 examples in the target language
- **Failure mode:** if the model returns no citation, mark `unverified=True` and downgrade the score by 1 (or refuse to flag)
- **Retries:** max 2 on Pydantic validation failure, then escalate to user

## Redline drafter

- **Inputs:** `{clause_text, baseline_clause, deviation_rationale, accepted_severity, language}`
- **Output (Pydantic):** `{proposed_text: str, rationale: str, diff_summary: str}`
- **Constraint:** proposed text must NOT introduce new deviations against the baseline. Verified by re-running the deviation spotter on the proposed text (a self-check loop).
- **Failure mode:** if the self-check flags a new deviation, retry once with an explicit constraint; if it still fails, surface to user with the conflict.

## HITL review

- **State:** LangGraph state holds the flag table + per-flag decision
- **Decisions per flag:** `accept` (proceed to redline), `reject` (drop the flag), `edit_severity` (override score), `add_context` (free text fed to the redline drafter)
- **Resume:** graph resumes from the human-review node after the final "Generate redline" click

## Open questions for this doc

- Sonnet vs MiniMax-M3 vs ensemble? (My take: Sonnet for the dev agent and redline drafter (reasoning quality matters), Haiku-class or smaller for the classifier and summary memo. The LLM-as-judge layer in v2 should use a different model from the drafter for honest disagreement.)
- Do we use LangGraph's prebuilt agents or build nodes from scratch? (My take: from scratch. The pipeline is too domain-specific for prebuilts.)
- Where does the counterparty matrix live — in the playbook store or as a separate config? (My take: separate config, versioned, with the playbook store referencing it. Easier to update without re-seeding the playbook.)
