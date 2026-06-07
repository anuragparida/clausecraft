# 07 — Eval Strategy

> Golden set, deterministic vs LLM-as-judge, regression strategy, CI integration.

**Status:** stub. The eval story is the spec's core claim, not a footnote.

## Eval layers

1. **Retrieval F1** — did we get the right playbook clauses? Deterministic.
2. **Classification F1** — did we label clauses correctly? Deterministic.
3. **Deviation set match** — precision, recall, F1 on flagged clauses; severity-mismatch count. Deterministic.
4. **Citation completeness** — % of flags with a playbook citation. Deterministic, simple.
5. **Redline quality** (v2) — LLM-as-judge via Langfuse's eval features. Optional in v1.
6. **End-to-end** — does the full pipeline produce a useful deliverable on a held-out contract? Manual + LLM-judge.

## v1 harness

A custom pytest harness (~150 lines target). Each test:

1. Loads a contract from `examples/contracts/{name}.{pdf|docx}`
2. Runs the full pipeline (ingest → parse → classify → dev-spot)
3. Loads the expected deviation set from `examples/expected/{name}.yaml`
4. Compares and reports:
   - Retrieval F1 (top-k playbook clauses)
   - Classification F1 (per clause type)
   - Deviation F1 (set match)
   - Severity-mismatch count (within ±1 tolerance)
   - Citation completeness (% of flags with citation)
5. Writes run report to `evals/runs/{timestamp}.json`
6. Posts aggregate metrics to Langfuse as a dataset run

## Golden set format

YAML per contract. Example shape:

```yaml
contract: examples/contracts/nda-001.pdf
type: nda
language: en
expected_clauses:
  - id: c1
    type: definition_confidential_info
    text_excerpt: "..."
  - id: c2
    type: term
    text_excerpt: "..."
expected_deviations:
  - clause_id: c2
    severity: 2
    category: term_too_long
    rationale: "Term of 7 years exceeds the playbook's 3-year maximum for NDAs involving trade secrets"
    citation:
      playbook_clause_id: nda-term-baseline
      source_url: "https://www.americanbar.org/..."
```

## Regression strategy

- Eval set is checked in. Every PR runs the full eval.
- Eval results are versioned (commit SHA + timestamp).
- A red CI fails the PR. Threshold: F1 drop > 5% on any metric.
- Langfuse dataset versioning handles the prompt-template side.

## LLM-as-judge (v2, optional)

Use Langfuse's built-in eval features with a different model than the drafter. Score redline quality on a rubric (1-5):

- Does the proposed text address the deviation?
- Does it introduce new deviations? (self-check pass = good)
- Is the language level appropriate for the contract?
- Is the rationale clear?

Disagreement report: run twice with different temperatures, surface cases where the LLM judge scores differ by ≥2. These are the cases worth a human review.

## Open questions for this doc

- What's the F1 drop threshold that fails CI? 5%? 10%? (My take: 5% on classification or deviation F1 is a hard fail. Retrieval F1 is softer.)
- Do we run the full eval on every PR or on merge to main only? (My take: every PR, but with a small smoke set (5 contracts) on PR and the full set (20) on main. Cost vs coverage tradeoff.)
- LLM-as-judge model — same family as the drafter or different? (My take: different. Anthropic family if drafter is Sonnet, use Opus for judging. Or vice versa.)
