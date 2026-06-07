# 11 — Phases

> Build phases for `clausecraft`. Each phase is a vertical slice with a clear exit gate. Slices are sized for an agent team to execute, not for human weekend sprints. Phases are sequenced so that earlier phases produce something demoable that later phases extend, not something that only works at the end.

## How to read this doc

- **Phase N — name.** One-line outcome + exit gate.
- **Scope.** What gets built. What's explicitly *not* built.
- **Slice layout.** The vertical slice for this phase (e.g. "1 contract type, 1 language, no HITL" — narrow on purpose).
- **Key files / modules.** Where the work lands in the repo.
- **Agent routing.** Which sub-agent owns the bulk of the build. Default routing per the team roster: Apollo = spec decomposition + risk, Perseus = build, Helena = review, Athena = copy + diagrams, Zeus = cron (not used here).
- **QA hooks.** What Anurag checks when they want to QA side-by-side. These should be 5–10 minutes each, not "spin up the whole stack."
- **Exit gate.** The thing that has to be true before the next phase starts.
- **Risks / known sharp edges.** What's likely to bite.

## Phases at a glance

| # | Phase | Slice scope | Exit gate |
|---|---|---|---|
| 0 | Skeleton + plumbing | Empty repo, Docker Compose, "hello world" on every service | `docker compose up` → API on 8000, web on 5173, Langfuse on 3000, Postgres reachable, LangGraph hello world runs end-to-end |
| 1 | Ingest + parse + classify (NDA, EN) | 1 contract type, 1 language, no agent, no playbook | Upload a known-bad NDA → get back a list of typed clauses in JSON |
| 2 | Playbook + deviation spotter (NDA, EN) | The first "real" agent. Eval harness arrives here. | Eval set runs, F1 reported, deviation spotter cites the right playbook clause |
| 3 | Redline drafter + HITL state machine + audit log | First "wow" moment. Two real agents. Langfuse integrated. | Approve a flag → get a .docx with tracked changes; click "audit log" → see the full decision chain |
| 4 | Bilingual pass (DE) | Same as phase 3, but DE-only. | DE NDA round-trips end-to-end with the same quality bar as EN |
| 5 | Second + third contract types (DPA, Employment) + counterparty matrix | Both languages, all 3 types. Eval set grows. | All 3 contract types × 2 languages produce usable deviation tables; counterparty matrix renders |
| 6 | Polish + deploy + demo | README, asciinema, public deploy | 2-minute demo recorded, repo public, live URL works |

Total budget: ~30–40 hours of agent work, spread over however many days/weeks the user wants. **The user is QA-side, not build-side.** Phases 2, 3, 5 are the natural QA checkpoints (visible behavior changes, eval numbers move).

---

## Phase 0 — Skeleton + plumbing

**Outcome.** A repo that runs. Nothing does anything useful yet, but every service starts, every port is reachable, every framework is wired.

**Scope.**
- Repo scaffold: `pyproject.toml` (uv), `pnpm-workspace.yaml`, `docker-compose.yml`, `Makefile` (or just) with the canonical commands
- Backend: FastAPI on :18000 with `/healthz` and a stub `POST /contracts` that returns `501 Not Implemented`
- Frontend: Vite + TS + React + Tailwind + shadcn dark mode on :15173, single page that says "clausecraft" + a "Coming soon" panel + the disclaimer footer
- Database: Postgres 16 + pgvector in Docker Compose, exposed on host :15432, SQLAlchemy 2.x async session, Alembic initialized
- LangGraph: a 1-node graph that takes a string in, echoes it back. Wire it to FastAPI.
- Langfuse: self-hosted in Docker Compose (web :13000, API :13001), integration stubbed in the LangGraph code
- README: just the "what is this" one-pager from `docs/00-overview.md` + quickstart
- `.env.example` with all env vars stubbed (no real secrets)
- `DISCLAIMER.md` with the "not legal advice" text (will be lawyer-reviewed before public deploy, not in v0)

**Slice layout.** Empty everywhere. Vertical slice = "stack comes up, says hello."

**Key files / modules.**
```
clausecraft/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app
│   │   ├── db.py              # SQLAlchemy async session
│   │   ├── graph/             # LangGraph
│   │   │   ├── state.py
│   │   │   ├── nodes.py
│   │   │   └── graph.py
│   │   └── observability.py   # Langfuse init
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── DISCLAIMER.md
└── README.md
```

**Agent routing.** Perseus builds. Helena reviews the docker-compose health check. Athena drafts the README one-pager from `docs/00-overview.md`.

**QA hook (5 min).**
1. `docker compose up` from a clean clone
2. Hit `http://localhost:18000/healthz` → 200
3. Open `http://localhost:15173` → see "clausecraft" + disclaimer
4. Open `http://localhost:13000` → see Langfuse login
5. `psql` into the Postgres container (port 15432) → confirm `pgvector` extension is installed

**Exit gate.** All four URLs work from a clean clone. README's quickstart command works. Disclaimer is visible in the UI footer.

**Risks / sharp edges.**
- Langfuse self-hosting has its own gotchas (Postgres + Redis + worker + ClickHouse in some configs). **Use the Langfuse "all-in-one" Docker image for v0**, switch to a production config in v1 of polish (Phase 6).
- **Port collisions.** The host already binds 8000 (Honcho API) and 5432 (Honcho Postgres); the custom dashboard is on 9874/9875. Use only high-numbered ports (12000+) — defaults listed in the Scope block. **If a chosen port is rejected at runtime, pick another high port and log the change in the reporting checklist — do not crash silently.**
- **Skill names must exist.** Verify with `skills_list` before referencing. `fullstack-docker-compose-stack` and `docker-management` are both real (in the `devops/` category); prefer `fullstack-docker-compose-stack` for Phase 0 — it has the canonical recipe including port-collision checks, the favicon-600 nginx trap, and a verify.sh template.
- The first `uv sync` will pull a lot. Don't try to optimize the dependency tree in Phase 0.

---

## Phase 1 — Ingest + parse + classify (NDA, EN)

**Outcome.** Upload a PDF/DOCX NDA in English, get back a JSON list of typed clauses. No agents, no playbook, no redline — just the mechanical pipeline.

**Scope.**
- **Ingest:** `pymupdf` for native PDFs (text-layer), `python-docx` for `.docx`, vision-model fallback for scanned PDFs (defer to Phase 3 if it's painful)
- **Parse:** semantic chunking by section headers + numbered clause detection. Heuristic, not ML.
- **Classify:** prompted LLM (Sonnet-class) for now — returns one of ~15 clause types (`definition_confidential_info`, `term`, `governing_law`, `injunctive_relief`, `residual_knowledge`, `return_of_materials`, `non_solicit`, etc.). Pydantic-validated, retry on failure.
- **Output:** `Clause[]` with `{id, text, position, type, language}`
- **UI:** a 2nd page: upload + counterparty context form + "Triage" button. For Phase 1 the button runs only the ingest/parse/classify stage and renders the JSON in a `<pre>` block + a shadcn `DataTable` summary
- **Tests:** 5 hand-picked NDA contracts (1 from ABA, 1 with weird formatting, 1 scanned, 1 short, 1 long). Each test asserts: contract parses, ≥80% of clauses get a non-null type, no Pydantic crashes.
- **Langfuse:** every LLM call traced. No eval yet.

**Slice layout.** 1 contract type, 1 language, no playbook, no agent. Mechanical.

**Key files / modules.**
```
backend/app/
├── ingest/
│   ├── pdf.py
│   ├── docx.py
│   └── scan_detect.py
├── parse/
│   ├── chunker.py
│   └── heuristics.py
├── classify/
│   ├── prompt.py
│   ├── schema.py              # Pydantic: ClauseType enum, Clause model
│   └── classifier.py
├── pipeline/
│   └── stage1_ingest.py       # the linear stage, returns Clause[]
```

**Agent routing.** Perseus builds. Helena reviews the parse heuristics against the 5 test contracts. Athena does not own anything here.

**QA hook (10 min).**
1. Upload the 5 NDA test contracts one at a time
2. Confirm the JSON has the expected clause count and types
3. Skim the Langfuse UI — confirm 1 trace per classification call
4. Try the scanned-PDF contract — confirm graceful error, not a crash

**Exit gate.** All 5 test contracts parse, classify returns non-null types for ≥80% of clauses, no crashes. JSON output schema is locked in.

**Risks / sharp edges.**
- "Clause" is not a stable concept. Section 14.3.2 may be 3 paragraphs deep. The heuristics will be brittle. **Plan for a 1-day rabbit hole.** See `docs/02-architecture.md` open question on parse strategy.
- Sonnet can confidently misclassify. Pydantic enums + a "I don't know" fallback (`type: "unknown"`) are the safety net.
- The "scan detect" path is the highest-risk feature in this phase. **If vision-model OCR turns into a rabbit hole, defer to Phase 3** with a graceful "scanned PDF support coming soon" error.

---

## Phase 2 — Playbook + deviation spotter (NDA, EN)

**Outcome.** The first real agent runs. Eval harness arrives. We can claim the system *detects deviations against a baseline*, with measured F1.

**Scope.**
- **Playbook store:** Postgres table, versioned. Seeded with 5 NDA baselines (EN): definition of confidential info, term, residual knowledge, governing law, injunctive relief. Each baseline has provenance (URL + retrieval date + license).
- **Embeddings:** bge-m3 via the LLM gateway, pgvector. Top-k retrieval per clause.
- **Deviation spotter (the agent):** prompted Sonnet with the clause + top-3 baselines + counterparty context. Pydantic-typed output: `{score: 0|1|2|3, rationale, citation: {playbook_clause_id, contract_text_excerpt}, unverified: bool}`. **The "show your work" rule is enforced here** — no citation = `unverified=True`, and the UI renders unverified flags differently.
- **Counterparty context:** a versioned YAML config in `playbook/counterparty_matrix.yaml`. Phase 2 ships with the matrix rendering but with a **flat baseline (no matrix lookups yet)** — the matrix is wired in Phase 5.
- **Eval harness:** custom pytest, ~150 lines. Runs N contracts, compares against YAML golden set, reports retrieval F1, classification F1, deviation F1, severity-mismatch count, citation completeness. Saves run report to `evals/runs/{timestamp}.json`, posts aggregate to Langfuse.
- **Eval set:** 10 NDA contracts (EN). 5 from public templates, 5 with hand-injected deviations. 3 in `examples/contracts/public/`, 2 in `examples/contracts/synthetic/`. Hand-written expected deviations in `examples/expected/*.yaml`.
- **UI:** 3rd page: deviation table. Each row = clause + severity badge + counterparty matrix verdict (flat for now) + citation popover + "Approve / Reject / Edit" buttons. **Buttons are not wired yet** — they update local state only. Wired in Phase 3.
- **Langfuse:** every dev-spot call traced. Eval run is a separate "experiment" in Langfuse.

**Slice layout.** 1 contract type, 1 language, 1 real agent (the deviation spotter), eval harness live. No redline, no real HITL persistence.

**Key files / modules.**
```
backend/app/
├── playbook/
│   ├── store.py               # Postgres + pgvector
│   ├── seed.py                # idempotent seed from YAML
│   └── counterparty.py        # matrix config loader
├── agents/
│   └── deviation_spotter/
│       ├── prompt.py
│       ├── schema.py
│       └── spotter.py
├── pipeline/
│   ├── stage2_classify.py     # calls classifier
│   ├── stage3_spot.py         # orchestrates parallel per-clause spot
│   └── stage4_aggregate.py    # builds the flag table
evals/
├── harness.py                 # the pytest harness
├── conftest.py
└── runs/                      # gitignored except .gitkeep
examples/
├── contracts/
│   ├── public/                # 3 NDA templates
│   └── synthetic/             # 2 NDA with injected deviations
└── expected/                  # 5 YAML golden files
playbook/
├── baselines/                 # YAML per baseline, versioned
│   └── nda-en/
└── counterparty_matrix.yaml   # flat for Phase 2
frontend/src/
├── pages/
│   ├── DeviationReview.tsx
│   └── components/
│       ├── SeverityBadge.tsx
│       └── CitationPopover.tsx
```

**Agent routing.** Apollo plans the prompt strategy and the eval rubric (this is the highest-stakes prompt in the project). Perseus builds. Helena reviews for two things: (1) the eval harness actually measures what it claims, (2) the citation rule is enforced (no flagged clause without a citation). Athena drafts the README's "how the eval works" section.

**QA hook (15 min).**
1. Run `pytest evals/` — should be green or near-green. Read the F1 numbers in the run report.
2. Open the Langfuse UI — find the eval experiment, confirm 10 contracts × N clauses per contract = expected trace count.
3. Upload one of the public-template NDAs through the UI — see the deviation table populate. Click into a citation popover — confirm it points to a real baseline clause.
4. Upload a contract with no matching playbook clause — confirm graceful "no baseline" handling, not a crash.
5. Skim 5 random flags — confirm the rationales make sense and the citations are accurate.

**Exit gate.**
- Eval set runs in CI. F1 numbers are reported and saved.
- Citation completeness ≥ 95% (every flag has a citation or is marked unverified).
- Deviation spotter handles "no baseline" cases gracefully.
- The "show your work" rule is documented in the README.

**Risks / sharp edges.**
- **This is the highest-risk phase.** If the dev agent can't reliably cite baselines, the whole pitch falls apart. **Mitigation:** start with a small eval set (3 contracts), iterate on the prompt until F1 is acceptable, then grow to 10. Do not commit to 10 in one go.
- Eval set quality IS the eval. **A bad golden set will produce a green CI that lies.** Have Helena spot-check 3 of the 10 expected-deviation YAMLs against the actual contract.
- bge-m3 retrieval on 5 baselines is overkill. The retrieval F1 will likely be 100% with k=3. The real test is the LLM judgment, not the retrieval.
- The matrix config is loaded but not enforced. Don't promise counterparty-aware verdicts in this phase.

---

## Phase 3 — Redline drafter + HITL state machine + audit log

**Outcome.** The user can review flags, approve/reject, and download a real tracked-changes .docx. The audit log shows the full decision chain. **This is the first phase where the system is "demoable" in a way that lands the pitch.**

**Scope.**
- **Redline drafter (the second real agent):** prompted Sonnet, takes an accepted flag + clause + baseline, returns `{proposed_text, rationale, diff_summary}`. **Self-check loop:** re-run the deviation spotter on the proposed text; if it flags a new deviation, retry once with an explicit constraint; if it still fails, surface to the user with the conflict.
- **Tracked changes:** `python-docx` for `.docx` output. Direct redline insertion (delete + insert with `w:author` + `w:date` attributes so Word/LibreOffice render them as tracked changes). PDF round-trip is out of scope.
- **HITL state machine:** LangGraph `interrupt` node. State object holds the flag table + per-flag decisions. Resume from the same node after the user clicks "Generate redline." Pause-and-resume is testable.
- **Two-view UI:**
  - **Live review:** the deviation table from Phase 2, with real Approve / Reject / Edit / Add-context actions that mutate the LangGraph state.
  - **Audit replay:** a read-only view that scrubs through the decision chain. "At 14:32:08, the user approved flag #4 with severity override 2→1 and added context 'acceptable for our use case.'" Doubles as the audit log the regulated-work pitch is built on.
- **Audit log table:** Postgres, append-only (INSERT-only, no UPDATE). Schema: `(contract_id, clause_id, decision_type, payload_json, decided_by, decided_at)`. Every approval, rejection, severity override, redline generation, and deviation flag gets a row.
- **Audit log export:** button on the contract view → downloads a JSON + a PDF rendering of the full decision chain.
- **Langfuse:** all LLM calls traced. Eval run is a separate experiment. The "disagreement report" can land here too (run dev-spot twice with different temperatures, surface conflicts) — defer to Phase 6 if it's noisy.
- **Tests:** 3 contracts × end-to-end (upload → review → redline). Each test asserts: redline .docx opens, ≥1 tracked change present, audit log has ≥1 row per stage.

**Slice layout.** 1 contract type, 1 language, 2 real agents (deviation spotter + redline drafter) + real HITL + audit log. **The "wow" moment lives here.**

**Key files / modules.**
```
backend/app/
├── agents/
│   └── redline_drafter/
│       ├── prompt.py
│       ├── schema.py
│       ├── drafter.py
│       └── self_check.py      # re-runs spotter on proposed text
├── output/
│   ├── docx.py                # python-docx with tracked changes
│   └── summary_memo.py        # 1-page plain-language memo
├── audit/
│   ├── schema.py              # Pydantic + SQLAlchemy
│   ├── log.py                 # append-only writer
│   └── export.py              # JSON + PDF
├── pipeline/
│   ├── graph.py               # full LangGraph with interrupt
│   └── stage5_redline.py
frontend/src/
├── pages/
│   ├── DeviationReview.tsx    # wired up
│   ├── AuditReplay.tsx        # new
│   └── RedlineOutput.tsx      # new (mammoth.js preview + download)
└── components/
    └── AuditLogTimeline.tsx
```

**Agent routing.** Perseus builds the redline drafter + the audit log table + the docx output. **Helena owns the audit log review** — she's the "regulated work" eye. Athena drafts the README's "audit trail" section and the audit log export's user-facing description.

**QA hook (20 min).**
1. Upload a known-bad NDA → review flags → approve 3, reject 1, edit 1's severity → click "Generate redline."
2. Open the .docx in Word (or LibreOffice) → confirm tracked changes are visible, attributed to "clausecraft," with timestamps.
3. Click "Audit log" → confirm the full decision chain is rendered: every flag, every decision, every rationale.
4. Export the audit log as JSON → confirm every row has a `decision_type` and a `decided_by`.
5. Try the resume-after-pause path: start a review, refresh the page, confirm the state is restored.

**Exit gate.**
- Real .docx with tracked changes opens cleanly in Word and LibreOffice.
- Audit log is append-only at the DB level (try to UPDATE a row, confirm the DB rejects it).
- The two-view UI works: live review and audit replay.
- Langfuse shows traces for both agents.

**Risks / sharp edges.**
- **Tracked changes in `python-docx` is a known rabbit hole.** Direct XML manipulation for the `w:ins` / `w:del` elements. Plan 1 day. Have a fallback: render the redline as a Markdown diff and ship that as the v0 output if the docx path is broken.
- **Self-check loop can oscillate.** If the drafter proposes text that the spotter flags, the retry may produce text that the spotter flags differently. Cap retries at 1; on the second failure, surface to the user with both attempts and the conflict.
- **Append-only at the DB level needs more than a code convention.** Either use a Postgres trigger that rejects UPDATE/DELETE on the audit table, or use a separate Postgres user with INSERT-only permissions. The trigger is simpler.
- **Mammoth.js** for the .docx preview. It will not render tracked changes — it sees the "final" document. That's OK; the tracked changes are visible when the user opens the actual .docx.

---

## Phase 4 — Bilingual pass (DE)

**Outcome.** The same end-to-end experience works in German. The eval set, playbook, and prompts all have DE counterparts.

**Scope.**
- **Playbook DE:** 5 NDA baselines translated and adapted. Sources: Vertragsmuster.de (BMJ), IHK Musterverträge, BGH standard formulations. Provenance + license per baseline.
- **Eval set DE:** 5 NDA contracts (3 from public DE templates, 2 synthetic DE with injected deviations). Expected deviations in YAML.
- **Prompts DE:** system prompt in DE, few-shot examples in DE. The Pydantic schemas and English clause type enums stay the same — the language detection is a per-clause `language: "de" | "en"` field.
- **Counterparty matrix DE:** the existing matrix config gains a DE column (most verdicts are language-agnostic; a few DE-specific entries like "governing law: German courts" become stricter for DE counterparty types).
- **UI:** language picker on the upload form. Default: auto-detect, with manual override. DE UI strings via a minimal i18n (just the page titles + button labels, not a full localization).
- **Eval harness:** runs both EN and DE contracts, reports F1 separately. F1 drop > 10% on DE vs EN = red flag for the prompt work.
- **README:** updated with the DE support claim + an example DE deviation table.

**Slice layout.** 1 contract type, 2 languages. All 3 v1 contract types is Phase 5. The DE work here is *only* the NDA contract type.

**Key files / modules.**
```
playbook/baselines/nda-de/    # new
examples/contracts/public/    # +3 DE NDAs
examples/contracts/synthetic/ # +2 DE NDAs
examples/expected/            # +5 DE golden YAMLs
backend/app/classify/prompt.py        # add DE variant
backend/app/agents/deviation_spotter/prompt.py  # add DE variant
backend/app/agents/redline_drafter/prompt.py    # add DE variant
frontend/src/i18n/                    # minimal DE strings
```

**Agent routing.** Perseus builds. **Helena reviews the DE eval set** — she should not be a native DE speaker, that's the point: a non-DE reviewer checking that the system works for non-DE users is the signal. (If Helena is DE-fluent, great; if not, the eval set is the test.) Athena adds the DE i18n strings.

**QA hook (15 min).**
1. Upload a known-bad DE NDA → see the deviation table populate in DE.
2. Run `pytest evals/` — confirm DE F1 numbers are reported.
3. Compare EN vs DE F1: gap < 10% on deviation F1, gap < 5% on citation completeness.
4. Skim 3 DE rationales — confirm they make sense, not just translated but actually reasoned.

**Exit gate.**
- DE NDA round-trips end-to-end with the same quality bar as EN.
- Eval harness reports per-language F1.
- README updated.

**Risks / sharp edges.**
- **The LLM is fluent in DE, but the playbook quality is what determines the citations.** If the DE baselines are thin, the spotter will fabricate or skip. **Mitigation:** every DE baseline must have a real public source. If we can't find 5, ship 3 and document the gap.
- **DE legal terminology is its own dialect.** "Vertraulichkeitsvereinbarung" vs "NDA," "Schadensersatz" vs "Haftung," "Kündigung" vs "Termination." The classifier and spotter prompts need DE-fluent reviewers. If Perseus isn't DE-fluent (likely), this is a spot where a human in the loop helps.
- **DE contracts often have Schuldrecht / Sachenrecht distinctions** that EN contracts don't make explicit. The clause taxonomy may need a DE-specific enum value or two. Add them, don't force-fit into EN enums.

---

## Phase 5 — Second + third contract types (DPA, Employment) + counterparty matrix

**Outcome.** All 3 v1 contract types (NDA, DPA, Employment) work in both EN and DE. The counterparty matrix is actually enforced.

**Scope.**
- **DPA (Art 28 GDPR):** 5 baselines EN, 5 baselines DE. Sources: EU SCCs (2021/914, both EN and DE BAnz versions), IAPP, EDPB, DSK Kurzpapier. Eval set: 3 public + 2 synthetic per language.
- **Employment:** 5 baselines EN, 5 baselines DE. Sources: ABA at-will templates, UK gov.uk statement of particulars, BGB §§ 611a ff., KSchG, NachwG, IHK Musterarbeitsvertrag. Eval set: 3 public + 2 synthetic per language.
- **Clause taxonomy expansion:** ~15 new clause types per contract type (DPA: sub-processor consent, transfer mechanism, breach notification window, data subject rights, etc. Employment: probation, notice period, garden leave, non-compete, IP assignment, etc.). Adds to the existing classifier enum, doesn't replace.
- **Counterparty matrix:** the YAML matrix config becomes the source of truth for `(clause_type, counterparty_type) → acceptable_range` lookups. The deviation spotter's verdict is matrix-aware: a score-2 deviation is "material" or "unacceptable" depending on the counterparty type. Renders as a verdict column in the UI.
- **Counterparty types:** enterprise | SMB | public-sector | healthcare (4 axes). Matrix is a 4-column lookup per clause type.
- **Eval harness:** full set is now ~30 contracts (5 NDA + 5 DPA + 5 Employment per language). CI runs the smoke set (5 contracts) on PR, the full set on main.
- **UI:** the deviation table gains the matrix verdict column. The counterparty context form gets the 4 counterparty type options.

**Slice layout.** 3 contract types × 2 languages. **This is the full v1 scope.**

**Key files / modules.**
```
playbook/baselines/dpa-en/    # new
playbook/baselines/dpa-de/    # new
playbook/baselines/employment-en/  # new
playbook/baselines/employment-de/  # new
playbook/counterparty_matrix.yaml   # expanded
examples/contracts/            # +30 contracts, +expected/*.yaml
backend/app/agents/deviation_spotter/prompt.py  # matrix-aware variant
backend/app/classify/schema.py     # expanded ClauseType enum
frontend/src/components/CounterpartyMatrixCard.tsx  # new
```

**Agent routing.** Apollo plans the clause taxonomy expansion (the highest-risk spec call here — wrong taxonomy = retraining prompts). Perseus builds. Helena reviews the matrix config against the eval set ("does the matrix actually change a verdict on a real contract?"). Athena drafts the README's "supported contract types" section.

**QA hook (30 min).**
1. Run `pytest evals/` — full set, both languages, all 3 types. F1 numbers per type + per language.
2. Upload a DPA with EU SCC deviations → see the matrix verdict flag the transfer mechanism as "unacceptable" for healthcare counterparty.
3. Upload an employment contract with a non-compete clause → see the matrix verdict flag it as "material" for SMB counterparty (where it's often unenforceable) and "acceptable" for enterprise counterparty.
4. Cross-check 5 random deviation rationales — confirm the matrix verdict influenced the score.

**Exit gate.**
- All 3 contract types × 2 languages produce usable deviation tables.
- Counterparty matrix is wired and changes verdicts on at least 3 eval contracts.
- F1 on the full eval set is within 10% of the smoke set's F1 (no overfitting to the smoke set).
- README's "supported contract types" table is up to date.

**Risks / sharp edges.**
- **The clause taxonomy is the second-highest-risk call in the project** (after the eval set quality in Phase 2). Get Apollo to plan it; have Helena cross-check.
- **The counterparty matrix is opinionated.** Different lawyers will disagree on what's "acceptable" for an SMB vs an enterprise. The matrix is a *claim* — the README should say "this is our judgment, based on common public-source templates, you can override per-counterparty" and offer a config file for overrides.
- **The eval set jumps from 10 to ~30.** Each new contract needs an expected-deviation YAML. **Budget ½ weekend for the YAML work, not ½ day.** This is the second-bottleneck of the phase.
- **Public-source DPAs are less common than NDA templates.** IAPP, EU SCCs, and a few Big-4 law firm templates are the main sources. If we can't get 5 EN baselines from public sources, use 3 + 2 synthetic-with-clear-sourcing.

---

## Phase 6 — Polish + deploy + demo

**Outcome.** Repo is public, live URL works, 2-minute demo is recorded, README reads well, the "not legal advice" disclaimer is everywhere.

**Scope.**
- **README rewrite:** 1-paragraph pitch, 2 before/after screenshots (deviation table + redlined docx), quickstart, "what this isn't" section, threat model, "how the eval works" section, "audit trail" section, supported contract types table. **Athena owns this.** Multiple drafts, two review passes.
- **Asciinema / 2-minute demo:** upload a known-bad NDA, see the deviation table populate, approve 2 flags, generate the redline, download the .docx. ~2 minutes. Screencast, not slides.
- **Live deploy:** single host (Hetzner or Fly.io). The Docker Compose stack runs as-is; add a `docker-compose.prod.yml` with TLS termination (Caddy or Traefik) and a `prod` env file. **Langfuse stays self-hosted** in the same stack.
- **Public repo:** if the user opts for public-from-day-1, this is the moment to push. If local-only-until-demo, this is the moment to push to GitHub.
- **Polish checklist:** `LICENSE` (Apache 2.0), GitHub topics (`ai`, `agents`, `legal-tech`, `contracts`, `redline`, `evaluation`, `multi-agent`), `/examples` README, `docs/PLAYBOOK.md` (how the playbook is structured + how to extend), `docs/LEGAL.md` (the disclaimer language), GitHub Actions for the eval smoke set on PR (optional — user said no GitHub Actions on the portfolio site, but a portfolio project repo can opt in; defer to user).
- **Eval final report:** a single markdown doc with the final F1 numbers per type × per language, written for a reviewer to read in 5 minutes. The "eval is the claim" story.
- **Counterfactual demo contract:** a `demo/` folder with a known-bad NDA that has 5 hand-crafted deviations, plus the expected redline. The asciinema runs against this contract. The "wow" is reproducible.

**Slice layout.** No new functionality. All polish.

**Key files / modules.**
```
README.md                       # rewritten
LICENSE                         # Apache 2.0
docs/
├── PLAYBOOK.md                 # new
├── LEGAL.md                    # new
└── EVAL_RESULTS.md             # new
demo/
├── known-bad-nda.pdf
├── expected-redline.docx
└── asciinema.cast
.github/                        # optional, per user
```

**Agent routing.** Athena owns the README, the asciinema script, the legal disclaimer writeup. Perseus handles the deploy (Docker Compose, Caddy, env). Helena reviews the README for "would a hiring manager actually read this?" Helena is the proxy for the audience.

**QA hook (10 min).**
1. Read the README top to bottom — does it land the pitch in 30 seconds?
2. Watch the asciinema — does it show the "wow" moment?
3. Open the live URL — does it work?
4. Read the eval results doc — are the F1 numbers credible?
5. Read the disclaimer in the UI, the README, and the .docx — same language everywhere?

**Exit gate.**
- README reads well, 2-minute demo recorded, live URL works, repo public, disclaimer everywhere.

**Risks / sharp edges.**
- **The "what this isn't" section is a discipline test.** If the README oversells, reviewers will smell it. If it undersells, the wow moments get buried. Athena needs 2 drafts.
- **The asciinema is the single most-watched artifact.** Plan 3 takes; the third is usually the one.
- **Self-hosting Langfuse in prod is non-trivial.** ClickHouse + worker + Redis + Postgres + the web/API containers. The "all-in-one" Docker image is fine for v0; for prod, the user should be on a managed Langfuse or accept the operational cost.
- **The disclaimer should be lawyer-reviewed before any public deploy.** AGENTS.md says the user has HDI in their background. **Confirm with the user that they have a lawyer contact** before pushing the public deploy; if not, the deploy waits.

---

## Phase dependencies at a glance

```
Phase 0 (skeleton) ─┐
                    ├─→ Phase 1 (ingest+parse+classify, NDA EN) ─┐
                                                              ├─→ Phase 2 (playbook+dev agent+eval, NDA EN) ─┐
                                                                                                          ├─→ Phase 3 (redline+HITL+audit, NDA EN) ─┐
                                                                                                                                                       ├─→ Phase 4 (DE pass, NDA only)
                                                                                                                                                       │
                                                                                                                                                       ├─→ Phase 5 (DPA+Employment, both langs, matrix)
                                                                                                                                                       │
                                                                                                                                                       └─→ Phase 6 (polish+deploy)
```

Phases 4 and 5 are technically independent in scope (DE NDA, then DPA+Employment+matrix), but Phase 5 should not start until Phase 4's DE baselines are in place — the matrix needs the DE baselines to render its DE column.

## Risks summary (cross-phase)

| Risk | Phase | Mitigation |
|---|---|---|
| Langfuse self-host rabbit hole | 0, 3 | Use all-in-one image in v0; defer prod config to Phase 6 |
| Parse heuristics brittleness | 1 | 5 hand-picked test contracts, including 1 weird-format |
| Scanned PDF / OCR | 1 | Defer to Phase 3 if it becomes a rabbit hole |
| Bad eval set | 2 | Helena spot-checks; don't commit to 10 in one go |
| Tracked changes rabbit hole | 3 | Markdown-diff fallback if `python-docx` path is broken |
| Self-check loop oscillation | 3 | Cap retries at 1; surface conflict to user |
| DE legal terminology dialect | 4 | DE-fluent reviewer on prompt work; don't force-fit EN enums |
| Clause taxonomy expansion | 5 | Apollo plans, Helena cross-checks |
| Counterparty matrix overselling | 5 | README is honest about "our judgment, configurable" |
| Public deploy without legal review | 6 | Confirm lawyer contact before pushing |

## What this doc does NOT do

- **Estimate weekends.** Anurag is QA-side, the build is agent-side. The doc is shaped for the agent team, not a personal calendar.
- **Promise a ship date.** Phases are ordered, not dated.
- **Pick the LLM provider.** That's a Phase 0 sub-decision (Apollo plans, Perseus builds, the user signs off once). See `docs/08-tech-stack.md` open question.
- **Pick the deploy target.** Fly.io vs Hetzner vs HF Spaces is a Phase 6 decision. The seed said Fly.io / Hetzner; the user can change it.

## After Phase 6

Phase 6 is "v1 demoable." The v2 backlog (from `docs/01-feature-spec.md` "can be" tier) is unranked. Likely v2 candidates:
- Multi-contract portfolio review (upload 5, see aggregate risk)
- Negotiation email drafter
- Side-by-side HTML redline visualization
- Public benchmark with human spot-checks
- LLM-as-judge + disagreement report
- Pre-merge playbook regression test

But that's a different planning session.
