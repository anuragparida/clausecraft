# 10 — Decisions (ADR log)

> Architecture Decision Records. Each entry: date, context, decision, consequences.

**Status:** stub. Fill as we lock decisions.

## Format

```
## YYYY-MM-DD — <short title>

**Context:** what forced the decision

**Decision:** what we chose

**Consequences:** what this means downstream
```

## Entries

### 2026-06-07 — Default to user's stack (Vite/shadcn dark mode + FastAPI/SQLAlchemy)

**Context:** Seed spec said Streamlit for the HITL UI ("the audience doesn't care about pixel polish").

**Decision:** Use the user's default stack (Vite + TS + React + Tailwind + shadcn dark mode) instead of Streamlit. The HITL page is the main work surface; the user finds shadcn dark mode dramatically more pleasant to use at length, and the default stack is faster to extend.

**Consequences:** +½ weekend for setup vs Streamlit. Better long-term extensibility. The legal-tech audience gets a more polished demo, which actually helps the signal.

### 2026-06-07 — LangGraph + Langfuse for orchestration + observability

**Context:** Seed spec didn't name an orchestrator. The pipeline has 6 stages with 3 real agents, parallel per-clause processing, and a pauseable HITL checkpoint.

**Decision:** Use LangGraph for orchestration (stateful, checkpointable, parallel node execution) and Langfuse for LLM observability.

**Consequences:** +½ weekend for the framework. The regulated-work pitch now has proper audit primitives (LangGraph state + Langfuse traces). The Postgres audit log is a separate, app-owned layer that Langfuse doesn't replace.

### 2026-06-07 — 3 real agents, not 6

**Context:** Seed describes 6 stages of "multi-agent." Stretching the word dilutes the signal.

**Decision:** The deviation spotter, redline drafter, and HITL review are the real agents. Classifier, playbook lookup, and summary memo writer are mechanical steps (or one-shot LLM calls) — not agents.

**Consequences:** README and pitch say "3-agent pipeline" honestly. The 3-agent framing is defensible. Mechanical steps get simpler code (no agent boilerplate).

### 2026-06-07 — NDA + DPA + Employment as the 3 v1 contract types

**Context:** Seed said 3 contract types (NDA, SaaS MSA, DPA) but didn't justify the choice against a rubric.

**Decision:** v1 = NDA + DPA + Employment. Drop SaaS MSA to v2. Reasoning: all three are public-templated, EN+DE well-supported, deviations are common and visible, and they showcase the most legally meaningful patterns (mutual obligations, regulatory baselines, asymmetric power).

**Consequences:** v2 work adds SaaS MSA, vendor, license. The eval set is anchored on these 3.

### 2026-06-07 — EN + DE bilingual from v1

**Context:** Seed said English-only in v1, DE/FR as "can be."

**Decision:** EN + DE in v1. Bilingual is a real differentiator (few legal-tech demos do DE seriously), the user lives and works in a DE legal context, and the marginal cost is ~30% more playbook work, not a doubling.

**Consequences:** Playbook sourced in both EN and DE. Eval set includes DE contracts. Embeddings via bge-m3 (multilingual). LLM handles both via the same model.

### 2026-06-07 — Custom pytest eval harness in v1, not deepeval

**Context:** User asked about deepeval for evals.

**Decision:** v1 uses a custom pytest harness (~150 lines) + a YAML golden set (10-20 contracts). DeepEval is the wrong abstraction for "did we flag the right clauses with the right severity." Langfuse's built-in eval features handle the LLM-as-judge layer in v2.

**Consequences:** No new dependencies for v1. The harness is a single file, easy to maintain. The eval set IS the eval — quality of the set is the gating decision.

### 2026-06-07 — "Show your work" + counterparty matrix as the v1 wow moments

**Context:** Multiple candidate wow moments proposed in scope discussion (deviation table, side-by-side redline, disagreement report, pre-merge playbook regression test, counterparty matrix, show-your-work citations).

**Decision:** v1 wow moments are: (1) "show your work" — every flag cites the playbook clause AND the contract text, with unverified flags downgraded; (2) counterparty matrix — severity × counterparty-type → acceptable / material / unacceptable verdict. These are the two moves that turn "demo" into "claim."

**Consequences:** Counterparty context is a required form field on upload. The matrix lives as a versioned config in the playbook. Citations are mandatory in the dev agent's output (Pydantic-enforced).

## Pending decisions

(Add to this section as they come up. Move to "Entries" once locked.)

### 2026-06-07 — Project name: `clausecraft`

**Context:** Working name was `contract-triage/`. Repo name is part of the pitch for a portfolio piece.

**Decision:** `clausecraft`. Reads as craft, signals the domain (clauses), not a generic "agent" suffix.

**Consequences:** Repo renamed. Python package name = `clausecraft`. PyPI reserved (TBD). Domain `clausecraft.dev` or similar (TBD).

### 2026-06-07 — Golden eval set: public templates + selective synthetic in v1

**Context:** Three options on the table: (a) public templates only, (b) real anonymized public contracts, (c) LLM-generated synthetic.

**Decision:** v1 = (a) for the bulk + (c) used selectively for coverage of niche clause combinations and adversarial cases. v2 = add (b) for the real-world signal bump. Rationale: (a) is honest and reviewable; (c) is fast for filling gaps in (a); (b) costs +2 weekends for sourcing + redaction and is better spent on the v1 build itself.

**Consequences:** Eval set has two clearly-labeled components: `examples/contracts/public/` and `examples/contracts/synthetic/`. README explains the sourcing mix. Synthetic contracts are explicitly marked so reviewers don't mistake them for real.

### 2026-06-07 — HITL fidelity: state machine + two-view UI (option c)

**Context:** Three HITL options: (a) Approve/Reject/Edit per flag, (b) state machine with replay, (c) both.

**Decision:** (c) both. The state machine is the same code path; the UI exposes two views: initial review (live, pauseable) and audit replay (scrub through decisions, re-run redline). The replay view doubles as the audit log demo for the live walkthrough.

**Consequences:** LangGraph state object is the source of truth for both views. The "audit replay" view is shipped in v1 because it is the audit log the regulated-work pitch is built on. Cost: +1 day of UI work, paid back by the demo's wow moment.
