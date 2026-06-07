# 02 — Architecture

> System diagram, agent roles, data flow.

**Status:** stub. To be filled once the pipeline spec is locked.

## Components (proposed)

- **Ingest service** — PDF/DOCX → text + section metadata. `pymupdf`, `python-docx`.
- **Parser** — semantic chunking by section headers + numbered clause detection.
- **Classifier** — per-clause type. Open question: prompted LLM vs small fine-tuned classifier (DeBERTa-v3).
- **Playbook store** — Postgres table, versioned, seeded from public sources. Embeddings in pgvector (bge-m3).
- **Deviation spotter (agent)** — reads clause + baseline + counterparty context, scores 0–3 with citation.
- **Redline drafter (agent)** — for accepted flags, proposes specific alternative language with rationale.
- **HITL review (agent + UI)** — pause graph, surface flag table, accept/reject/edit per flag.
- **Summary memo writer** — 1-page plain-language summary of the full deviation table.
- **Audit log** — Postgres append-only, owned by the app. INSERT-only, no UPDATE.
- **LangGraph orchestrator** — wires it all together, stateful, checkpointable.
- **Langfuse** — LLM call observability, eval annotations, disagreement reports.

## Data flow (high level)

1. Upload contract (PDF or DOCX, EN or DE)
2. Ingest → Parse → Classify (per clause)
3. Parallel per-clause: Playbook lookup → Deviation spotter (with counterparty context)
4. Aggregate deviation table
5. **HITL checkpoint** — user reviews each flag
6. Redline drafter runs on accepted flags
7. Generate tracked-changes .docx + summary memo + audit log export
8. Audit log persisted; Langfuse traces persisted

## Open questions for this doc

- Are the classifier and playbook lookup "agents" or mechanical steps? (My take: not agents. Deviation spotter and redline drafter are the only real agents.)
- Counterparty context — does the user provide it (form: "I am a SaaS vendor selling to enterprise in DE") or does the system infer it from the contract? (My take: explicit form field. Inference is brittle.)
- Where does the language detection happen — at upload or at parse?
- Is the "summary memo writer" a separate agent or a side-effect of the redline drafter? (My take: same prompt, different output mode. Not a separate agent.)
