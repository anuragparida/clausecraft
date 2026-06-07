# 00 — Overview

**Name:** `clausecraft` (locked 2026-06-07)

**One-liner:** Upload a contract, get a deviation table against a public-source playbook, approve the redlines you want, download a tracked-changes .docx. Every flag is cited. Nothing is trusted by default. Not legal advice.

## Pitch (cold-technical, 1 paragraph)

A multi-agent pipeline — ingest, classify, deviation-spot, redline, human-review, output — that takes a privacy or commercial contract in EN or DE, parses it into clauses, scores each clause 0–3 against a public-source baseline playbook (EU SCCs, IAPP, BGB, ABA, DSGVO, Tarifvertrag), and produces a tracked-changes .docx with a deviation table and a plain-language summary memo. The dev agent cites the specific playbook clause AND the contract text it compared; flags without citations are downgraded to "unverified." A counterparty matrix encodes when a deviation is acceptable vs material (e.g. "LoL 1y cap → acceptable for SaaS, material for healthcare vendor"). Every decision is logged to an immutable Postgres audit table and traced through Langfuse.

## Pitch (provocative, 1 sentence)

Spellbook costs $30k/year. This costs an LLM API key. The playbook is public. The redlines are reproducible. Read the eval set before you call it a toy.

## Scope (locked 2026-06-07)

- **Languages:** EN + DE, both from v1.
- **Contract types in v1:** NDA (mutual), DPA (Art 28 GDPR), Employment (Arbeitsvertrag / at-will).
- **Stack:** FastAPI + SQLAlchemy + Postgres + pgvector (backend), Vite + TS + React + Tailwind + shadcn dark mode (frontend), LangGraph (orchestration), Langfuse (LLM observability), pytest (evals).
- **Audit story:** 3 layers — Langfuse (LLM), LangGraph state (agents), Postgres append-only audit log (business).
- **Marketing tone:** cold-technical default; provocative alt for the README hook.
- **Wow moments for live demo:** "Show your work" (citations on every flag) + counterparty matrix (severity × counterparty).
- **Evals in v1:** Yes. Custom pytest harness + YAML golden set (10-20 contracts, hand-labeled). No LLM-as-judge in v1.

## Open questions (still being decided)

See [README.md § Open scope questions](../README.md#open-scope-questions-2026-06-07) and the questions in the active planning conversation.

## Status

Phase 0 — scope, no code yet. See [docs/11-phases.md](docs/11-phases.md) for the build plan (7 phases, vertical slices, agent-routed). First kanban dispatch (`t_aa030f09`) crashed 2026-06-07 17:58 because the spec used host-bound ports (8000, 5432); spec + tech-stack doc updated to high ports (18000 / 15173 / 13000 / 13001 / 15432), re-dispatch pending.
