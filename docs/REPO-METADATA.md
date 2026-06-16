# Repo metadata

> GitHub-side metadata for the `clausecraft` repo page. None of this is
> read by the application — it's a checklist + machine-readable list for
> whoever pushes the public repo to apply the metadata via the GitHub UI
> or `gh api`.

## GitHub topics

The seven topics for the repo's "About" sidebar. Apply via
`https://github.com/<owner>/clausecraft/settings` (Topics field) or via:

```bash
gh api -X PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/<owner>/clausecraft/topics \
  --input - <<'JSON'
{ "names": ["ai", "agents", "legal-tech", "contracts", "redline", "evaluation", "multi-agent"] }
JSON
```

| # | Topic | Why |
|---|-------|-----|
| 1 | `ai` | The pipeline uses LLMs (deviation spotter, classifier). |
| 2 | `agents` | Multi-agent orchestration (ingest / classify / spot / redline / HITL). |
| 3 | `legal-tech` | The application domain (contract review, deviation spotting, redlines). |
| 4 | `contracts` | The artifact being analysed. |
| 5 | `redline` | The output format (tracked-changes .docx). |
| 6 | `evaluation` | Eval-set driven quality claim; the harness is the spec. |
| 7 | `multi-agent` | The architecture (specialist roles + Langfuse-traced handoffs). |

## Repository description (1 line)

> Multi-agent EN/DE contract deviation pipeline: ingest → classify → spot → redline → HITL, with public-source citations, an eval-driven quality bar, and a counterparty matrix that encodes when a deviation is acceptable vs material.

## Homepage URL

The `clausecraft` repo has no public homepage beyond itself; leave blank
unless Anurag wires up a project page on `anuragparida.com`.

## Other checkboxes (GitHub repo settings)

- [x] **Include in the search engine** — leave default (yes).
- [x] **Releases** — no releases planned; not used.
- [ ] **Packages** — no packages published; not used.
- [x] **Issues** — on. Bug reports / spec questions welcome.
- [x] **Discussions** — optional; defer to Anurag.
- [x] **Sponsorship** — off (this is a portfolio project, not seeking funds).
- [ ] **Wiki** — off (everything lives in `docs/`).

## Why this file exists

GitHub does not store topics in a tracked file in the repo — they're
applied through the repo settings UI or the REST API. This file is the
contract between this card and the operator (Anurag) who will paste the
topic list into the GitHub UI when the repo is flipped public in
Phase 6. The spec calls out that `.github/topics.yml` is non-standard
for this purpose; `docs/REPO-METADATA.md` is the audit trail.
