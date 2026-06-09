# clausecraft — AGENTS.md

> Project-level onboarding for AI agents (and humans) working in `clausecraft/`.
> The cross-project baseline lives at `../AGENTS.md`; this file overrides it for
> clausecraft-specific rules.

## What this is

Multi-agent contract deviation pipeline (ingest → classify → deviation-spot →
redline → human-review → output) for EN/DE NDAs and commercial contracts. See
`README.md` for the one-paragraph version and `DISCLAIMER.md` for the legal
disclaimer (this is **research / portfolio, not legal advice**).

**Current phase:** Phase 4 (DE language support). Phase 3 (the audit-log +
HITL state machine + redline drafter) is on `main`. Phase 4 work has been
done on a `phase4/*` branch and is mid-merge.

## Hard rules for this repo

### Commit cadence (overrides the cross-project default with project-specific)

- **One commit per kanban card, at minimum.** The repo's commit log is the
  only auditable artifact. Card IDs (`t_xxxxxxxx`) MUST be in the commit
  subject. Format: `Phase N (card t_xxx): <what changed>` or
  `fix(<area>): <what changed>` for non-card fixes.
- **Commit before yielding the working tree.** If a coder agent (Perseus)
  finishes a card, the commit happens *before* marking the card done in the
  kanban. Reviewers read `git log`, not working-tree state.
- **Phase-end = merge to `main` + push.** When a phase wraps, all `phaseN/*`
  branches get merged to `main` and pushed. The current main is at "Phase 3
  Build 1" while `phase4/per-language-f1-eval-harness` is ~10 commits ahead —
  that's a bug in the previous workflow, not the new rule. Stale phase
  branches rot and confuse the next agent.
- **No `--force` against `main`.** Fast-forward only. If `main` has moved,
  rebase or merge — never rewrite.
- **No `--allow-empty` filler.** If a card didn't change any tracked file,
  update a doc, the leaderboard, or the eval results instead. Empty cards
  are a process smell.

### Work on `main` after each phase

- In-flight: `phase4/<slug>` is OK while Phase 4 is still being built.
- End of phase: merge to `main` (no fast-forward squashing, preserve card IDs),
  push, delete the phase branch locally (`git branch -d phase4/...`).

### Local-only / never-commit

- `.env`, `.env.local`, any file containing API keys (Langfuse, MiniMax,
  OpenRouter). `.env.example` is the placeholder template; that one is fine.
- `node_modules/`, `.venv*/`, `dist/`, `.vite/`, `__pycache__/`,
  `.pytest_cache/`, `.ruff_cache/`, `.harness-venv/`, `.eval-venv/` — all in
  `.gitignore` already. Don't fight it.
- The `playbook/` directory is read-only inside the container (bind-mount `:ro`).
  If a new public-source baseline is needed, add it under `playbook/` and
  commit the YAML, but never edit the in-container copy.

### Eval-set discipline (Phase 4 lesson learned)

- The eval set (3 public + 2 synthetic DE NDAs + golden YAMLs, plus the EN
  set) is **frozen**. Do not edit golden YAMLs to "make tests pass." If a
  golden looks wrong, file a card, get sign-off, then update the golden AND
  the rationale.
- Eval results go in `evals/leaderboard.csv` (committed). When you change a
  prompt, model, or threshold, that file gets a new row.

### Project rule: spec-287 disclaimer

- The UI surfaces a "Not legal advice" banner (spec line 287). Don't remove
  it. If a redesign loses it, that's a regression.

## Tech stack (project-specific)

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, asyncpg.
  Embeddings via OpenRouter `qwen/qwen3-embedding-8b` (1024-dim, pgvector).
  LLM via `MiniMax-M3` (configured in docker-compose.yml).
- **Frontend:** Vite + React 18 + Tailwind + shadcn/ui (dark mode by default).
  pnpm 9.7.0 (corepack-pinned in the Dockerfile). See `frontend/pnpm-workspace.yaml`
  for the workspace declaration.
- **Infra:** Docker Compose. Four services: `postgres` (pgvector), `backend`
  (FastAPI, port 18000), `frontend` (Vite, port 15173), `langfuse-web`
  (Langfuse v2, ports 13000/13001). High-numbered ports — host already binds
  8000/5432 (Honcho) and 9874/9875 (custom dashboard).
- **No CI / no deploy pipeline.** The host's `gh` is authenticated, but
  Actions and Cloud Run / Coolify deploys are intentionally absent for
  portfolio reasons. Push to GitHub is enough.

## Quick verification (run-it-for-Anurag rule)

After any meaningful change:

```bash
cd /home/ody/workspace/clausecraft
sg docker -c "docker compose up -d --build"
# Wait ~10s for healthchecks
curl -s -w 'frontend=%{http_code}\n' -o /dev/null http://localhost:15173/
curl -s -w 'backend=%{http_code}\n'  -o /dev/null http://localhost:18000/healthz
curl -s -w 'langfuse=%{http_code}\n' -o /dev/null http://localhost:13000/
```

Frontend HTTP 200, backend `/healthz` 200, Langfuse 200 → green.

## Things that look like bugs but aren't

| Looks like… | Reality |
|---|---|
| `pnpm-workspace.yaml` should be deleted since this is a single-package app | It's a pnpm 9.7+ requirement. `packages: []` must be present or pnpm errors. |
| Main branch is way behind phase branches | Legacy of the old workflow. Active migration: merge `phase4/*` to `main` at end of Phase 4. |
| SpotifyCard.astro is missing from the homepage | N/A here, that was the portfolio site. |
| Langfuse is on v2 not v3 | v2 is the deliberate choice (v3 needs ClickHouse + Redis + worker container). See `docker-compose.yml` comment. |

## When in doubt

- Read `README.md` for the project pitch and quickstart.
- Read `../AGENTS.md` for cross-project rules (commit cadence, stack defaults, no-HDI-internal-data).
- Read `../project_ideas/11_legal_contract_triage.md` for the original spec.
- Check `evals/leaderboard.csv` for the current quality bar.
