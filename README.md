# clausecraft

> Upload a contract, get a deviation table against a public-source playbook,
> approve the redlines you want, download a tracked-changes .docx. Every flag
> is cited. Nothing is trusted by default. Not legal advice.

A multi-agent pipeline — ingest, classify, deviation-spot, redline,
human-review, output — that takes a privacy or commercial contract in EN or
DE, parses it into clauses, scores each clause 0–3 against a public-source
baseline playbook (EU SCCs, IAPP, BGB, ABA, DSGVO, Tarifvertrag), and
produces a tracked-changes .docx with a deviation table and a plain-language
summary memo. The dev agent cites the specific playbook clause AND the
contract text it compared; flags without citations are downgraded to
"unverified." A counterparty matrix encodes when a deviation is acceptable
vs material (e.g. "LoL 1y cap → acceptable for SaaS, material for healthcare
vendor"). Every decision is logged to an immutable Postgres audit table and
traced through Langfuse.

> Spellbook costs $30k/year. This costs an LLM API key. The playbook is
> public. The redlines are reproducible. Read the eval set before you call
> it a toy.

**This is a research / portfolio project, not a product.** It is not legal
advice. See [`DISCLAIMER.md`](./DISCLAIMER.md).

---

## Quickstart

```bash
# 1. Copy env stubs (no real secrets in .env.example)
cp .env.example .env

# 2. Bring the stack up
docker compose up --build

# 3. Wait for the first boot (Postgres + Langfuse init take a minute)
#    Then verify every port is reachable:

curl -s -w 'status=%{http_code}\n' http://localhost:18000/healthz
curl -s http://localhost:15173/ | head -20
curl -s -o /dev/null -w 'status=%{http_code}\n' http://localhost:13000/
psql -h localhost -p 15432 -U clausecraft -d clausecraft \
  -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
```

| Service | Port | What it is |
|---|---|---|
| FastAPI backend | http://localhost:18000 | main API (Phase 0: `/healthz`, `POST /contracts` → 501, `POST /graph/echo`) |
| Vite frontend | http://localhost:15173 | single-page UI (Phase 0: "Coming soon" + disclaimer) |
| Langfuse web | http://localhost:13000 | LLM observability (login screen) |
| Langfuse API | http://localhost:13001 | Langfuse ingestion API |
| Postgres | `localhost:15432` | pgvector-enabled DB (user: `clausecraft`, db: `clausecraft`) |

Ports are high-numbered (12000+) on purpose: Honcho and the custom dashboard
already bind the conventional 3000/5432/8000/9874/9875 ranges on this host.
See `docs/08-tech-stack.md` for the full rationale.

---

## Status

**Phase 0 — skeleton + plumbing.** The stack comes up, every framework is
wired, no agent logic is implemented yet. Subsequent phases:

1. **Phase 1** — ingest + parse + classify (NDA, EN).
2. **Phase 2** — playbook + deviation spotter (NDA, EN) + eval harness.
3. **Phase 3** — redline drafter + HITL state machine + audit log.
4. **Phase 4** — bilingual pass (DE).
5. **Phase 5** — DPA + Employment + counterparty matrix.
6. **Phase 6** — polish + deploy + demo.

See [`docs/11-phases.md`](./docs/11-phases.md) for the full plan and
[`docs/00-overview.md`](./docs/00-overview.md) for the locked scope.

---

## Layout

```
clausecraft/
├── backend/            # FastAPI + SQLAlchemy + LangGraph (uv, Python 3.12)
├── frontend/           # Vite + TS + React + Tailwind + shadcn-style dark mode (pnpm)
├── docs/               # 11 spec docs (overview, features, architecture, ...)
├── docker-compose.yml  # single-host stack
├── .env.example        # all env vars stubbed, no real secrets
└── DISCLAIMER.md       # the "not legal advice" text
```

---

## License

TBD — see `docs/10-decisions.md` (open question).
