# 08 — Tech Stack

> Concrete libraries, services, ports, env vars, infra.

**Status:** stub.

## Confirmed (per AGENTS.md defaults + locked decisions)

### Backend
- **Package manager:** uv
- **Runtime:** Python 3.12
- **Framework:** FastAPI
- **ORM:** SQLAlchemy 2.x (async)
- **Validation:** Pydantic v2
- **Server:** uvicorn (single instance for v1; no Gunicorn workers needed)

### Frontend
- **Package manager:** pnpm
- **Build:** Vite
- **Language:** TypeScript (strict)
- **Framework:** React 18
- **Styling:** Tailwind CSS
- **Components:** shadcn/ui (dark mode default)
- **State:** TanStack Query for server state; Zustand for local UI state if needed

### Database
- **Primary:** PostgreSQL 16
- **Vector:** pgvector extension (bge-m3 embeddings, 1024-dim)

### Orchestration
- **Docker Compose** (single host for v1)
- **LangGraph** for agent orchestration
- **Langfuse** for LLM observability (self-hosted, in the same Docker Compose)

### LLM
- **Deviation spotter + redline drafter:** Sonnet-class (Anthropic or equivalent)
- **Classifier:** DeBERTa-v3 (fine-tuned) OR prompted Sonnet — TBD per cost/latency
- **Summary memo:** Haiku-class

## Infra (single host, Docker Compose)

| Service | Port (host) | Notes |
|---|---|---|
| FastAPI | 18000 | main API |
| Frontend (Vite dev) | 15173 | dev only; build for prod |
| Postgres | 15432 | pgvector enabled |
| Langfuse (web) | 13000 | self-hosted |
| Langfuse (API) | 13001 | internal |
| Langfuse worker | n/a | background |

**Why high ports:** Honcho is on 8000 and 5432 on this host; the custom dashboard is on 9874/9875. The user's standing preference is high-numbered ports (12000+) to avoid collisions. If any of these ports is rejected at runtime, pick another high port and log the change.

## Open questions for this doc

- Are we self-hosting Langfuse or using Langfuse Cloud? (My take: self-host. We already have Postgres + Docker, the marginal cost is small and the IP story is cleaner.)
- Where do the LLM API keys come from? OpenRouter for vendor portability, or direct (Anthropic, OpenAI)? (My take: OpenRouter, since the team's tool gateway already routes through it. Model choice becomes a config change.)
- For the DE NLP, are we using a separate embedding model? bge-m3 is multilingual and should work. (My take: same model, bge-m3. Confirmed handles DE well.)
- Single-machine deploy or Fly.io / Hetzner? (My take: local-first for v1, deploy later. The seed says Fly.io / Hetzner, but local is faster to iterate.)

## Env vars (to be defined)

- `DATABASE_URL` — Postgres connection
- `LLM_API_KEY`, `LLM_BASE_URL` — via OpenRouter
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- `PLAYBOOK_VERSION` — pins the active baseline (for reproducibility)
- `EVAL_SET_VERSION` — pins the active golden set
- `COUNTERPARTY_MATRIX_PATH` — path to the matrix config
- `DISCLAIMER_TEXT` — the "not legal advice" string, versioned
