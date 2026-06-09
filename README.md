# clausecraft

> Upload a contract, get a deviation table against a public-source playbook,
> approve the redlines you want, download a tracked-changes .docx. Every flag
> is cited. Nothing is trusted by default. Not legal advice.

A multi-agent pipeline — ingest, classify, deviation-spot, redline,
human-review, output — that takes a privacy or commercial contract in **EN
or DE**, parses it into clauses, scores each clause 0–3 against a
public-source baseline playbook (EU SCCs, IAPP, BGB, ABA, DSGVO,
Tarifvertrag), and produces a tracked-changes .docx with a deviation table
and a plain-language summary memo. The dev agent cites the specific
playbook clause AND the contract text it compared; flags without citations
are downgraded to "unverified." A counterparty matrix encodes when a
deviation is acceptable vs material (e.g. "LoL 1y cap → acceptable for
SaaS, material for healthcare vendor"). Every decision is logged to an
immutable Postgres audit table and traced through Langfuse.

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

**Phase 4 — bilingual (EN + DE) is the current build target.** The EN
pipeline runs end-to-end (Phase 3 review, audit log, redline export). The
DE pipeline (Phase 4) ships the eval set, per-clause language detection,
DE-localized prompts, and the per-language F1 + 10% / 5% gap assertions.
Subsequent phases:

1. **Phase 1** — ingest + parse + classify (NDA, EN).
2. **Phase 2** — playbook + deviation spotter (NDA, EN) + eval harness.
3. **Phase 3** — redline drafter + HITL state machine + audit log.
4. **Phase 4** — bilingual pass (DE). ← in progress
5. **Phase 5** — DPA + Employment + counterparty matrix.
6. **Phase 6** — polish + deploy + demo.

See [`docs/11-phases.md`](./docs/11-phases.md) for the full plan and
[`docs/00-overview.md`](./docs/00-overview.md) for the locked scope.

---

## Audit trail

Every decision the system makes and every action the user takes leaves a row.
The audit log is an append-only Postgres table — a trigger rejects UPDATE and
DELETE at the database level, so rows can be inserted but not edited or
removed. The trigger is a defense against accidental modification, not against
a determined adversary with shell on the box. If someone with root wants to
rewrite history, the log will not stop them. For everything short of that, the
log answers the question honestly.

What gets recorded: every approval, rejection, severity override, context
note, redline generation, and redline download — with `decided_by` (the
operator id) and `decided_at` (server-set, not caller-supplied) for each. The
schema is `(contract_id, clause_id, decision_type, payload_json, decided_by,
decided_at)`.

Who decides: the user. The system proposes; the human disposes. The HITL step
is the product's thesis, not a checkbox — see
[`docs/09-threat-model.md`](./docs/09-threat-model.md) for why this matters.

What the export looks like: JSON for re-import and machine reading, PDF for
humans. Both per-contract, both generated from the same row set, both
downloadable from the AuditReplay page. The JSON includes every decision in
chronological order with `schema_version` (a major-version string,
currently `"1"`, bumped on breaking format changes) and `exported_at`
fields at the top; the PDF is the same chain rendered for a human
reader, suitable for handing to a prospect's legal team. Files are
named `audit-{contract_id}.json` and `audit-{contract_id}.pdf`.

What the audit log is *not*: it is not a multi-tenant system, not a SOC 2
artifact, and not a substitute for the disclaimer in
[`DISCLAIMER.md`](./DISCLAIMER.md). It is a row you can point at when someone
asks why clause 7 was flagged severity 3 and what the operator did about it.
The answer is a timestamp, not a guess.

The append-only guarantee is enforced by a Postgres trigger installed in
[`backend/alembic/versions/0002_audit_log_phase3.py`](./backend/alembic/versions/0002_audit_log_phase3.py).
The spec for this phase lives in
[`docs/11-phases.md` § Phase 3](./docs/11-phases.md#phase-3-redline-drafter-hitl-state-machine-audit-log).

The string on the AuditReplay page, next to the download buttons:

> Every approval, rejection, severity override, redline generation, and
> download for this contract, with timestamps and the operator id. Not a
> substitute for the disclaimer; a record of what happened.

---

## Languages

Supports **English and German** NDAs out of the box. DE is a first-class
target, not a port: the eval set has 5 DE contracts (3 public-source
baselines + 2 hand-crafted stress contracts with known deviations), the
playbook baselines include 5 DE sources (BMJ juristic portal, DIHK,
IHK-München, IHK-Hessen, WKO FEEI Mustervertrag), and the per-clause
language detector runs on every parsed clause. The DE term for an NDA is
`Geheimhaltungsvereinbarung` (GHV) — sometimes still called
`Vertraulichkeitsvereinbarung`.

**What this isn't, for DE specifically:** Kein Ersatz für Rechtsberatung
durch einen deutschen Rechtsanwalt. A deviation table is a checklist of
things to look at, not a verdict. BGB § 305 ff. AGB-Kontrolle, BGH
Vertragsstrafen-Rechtsprechung (5 % der Auftragssumme in AGB), and § 38 ZPO
kaufmännischer Gerichtsstand are all things a real German lawyer will
read in the actual contract that this system does not. See
[`DISCLAIMER.md`](./DISCLAIMER.md) for the full "not legal advice" text
and `docs/09-threat-model.md` for why the disclaimer isn't a checkbox.

### Per-language quality bar

The eval harness reports per-language F1 + a 10 % deviation F1 / 5 %
citation completeness **gap assertion** (EN vs DE). The thresholds are
code assertions, not docs — a regression fails CI. From the most recent
run on the 15-contract eval set (`evals/runs/20260609T074418Z.json`):

| Language | Classification F1 | Deviation F1 | Citation completeness | Severity mismatches |
|---|---|---|---|---|
| EN | 0.70 | 1.00 | 1.00 | 0 |
| DE | 0.05 | 1.00 | 1.00 | 0 |
| **Gap (EN vs DE)** | **0.65** | 0.00 | 0.00 | 0 |

The deviation F1 / citation completeness gap is the spec's 10 % / 5 %
budget — both well within. The classification F1 gap is **honest and
unflattering** and is reported as-is. The DE classifier is rule-based and
fails on the German label set (e.g. `definition_confidential_info` ↔
`definition` confusion on § 2 GeschGehG clauses); the LLM-driven classifier
is gated on a follow-up card. The deviation F1 number — the one that
matters for the product — is 1.0 on DE in mock mode and matches EN
exactly.

### A real DE deviation table

From `synthetic-de/nda-001.pdf`, a 7-clause DE NDA with 3 hand-injected
deviations. The harness flagged all 3. The c4 (Ausnahmen) deviation
shows the spotter's full output: clause excerpt, the playbook baseline it
was compared against, and the German-language rationale the spotter
emits.

| Field | Value |
|---|---|
| **Clause** | c4 — `4. Ausnahmen` (residual_knowledge) |
| **Severity** | 1 (minor) |
| **Contract text** | "Von der Vertraulichkeitsverpflichtung ausgenommen sind Informationen, an denen die empfangende Partei (i) bereits vor der Offenlegung nachweislich im rechtmäßigen Besitz war, oder (ii) die ohne Verstoß gegen diese Vereinbarung unabhängig entwickelt hat, oder (iii) die von einem zur Offenlegung berechtigten Dritten erhalten hat, oder (iv) die ohne Verstoß gegen diese Vereinbarung allgemein bekannt sind. Im Gedächtnis der Mitarbeiter der empfangenden Partei verbleibende allgemeine Erfahrung darf frei verwendet werden." |
| **Citation** | `ausnahmen-von-der-vertraulichkeit` — [WKO FEEI Mustervertrag, Art. 2](https://www.wko.at/oe/agb/feei-muster-geheimhaltungsvereinbarung.pdf) |
| **Rationale (DE)** | Die vier Ausnahme-Tatbestände (i–iv) sind vollständig erhalten, aber die WKO-FEEI-Baseline (Art. 2) verlangt zusätzlich eine ausdrückliche Beweislast-Allokation: „Die Beweislast für das Vorliegen der vorgenannten Ausnahmen trägt die empfangende Partei." Diese Beweislast-Zuweisung fehlt im Vertragstext. Geringfügig, weil die substanziellen Ausnahmen vorhanden sind — nur die Beweislast-Allokation wurde weggelassen. Eine Beweislast-Verlagerung auf die offenlegende Partei ist in der Praxis kaum erfüllbar, da die empfangende Partei einen „vorherigen Besitz" geltend machen kann, ohne Belege vorzulegen. |

The full expected-deviation set for this contract is in
[`examples/expected/synthetic-de-001.yaml`](./examples/expected/synthetic-de-001.yaml);
the run report is
[`evals/runs/20260609T074418Z.json`](./evals/runs/20260609T074418Z.json).

---

## How the eval works

The eval harness is the spec's core claim, not a footnote. Four things to know
about it: what F1 means here, the contract set, the citation rule, and the
exit gate.

### What F1 means here

F1 is a deviation set match. Precision is `flagged-but-not-expected / all-flagged`.
Recall is `expected-but-not-flagged / all-expected`. The harness also reports
classification F1, retrieval F1, severity-mismatch count, and citation
completeness — see [`docs/07-eval-strategy.md`](./docs/07-eval-strategy.md) for
the full rubric philosophy.

### The contract set

15 NDA contracts (10 EN + 5 DE). The EN set: 5 from public templates
(`examples/contracts/public/`), 5 with hand-injected deviations (2 in
`synthetic/`, 3 in `hand-curated/`). The DE set: 3 public-source clean
baselines (`public-de/`, anchored to BMJ juristic portal, DIHK, IHK-Hessen)
+ 2 synthetic stress contracts (`synthetic-de/`) with 3 hand-injected
deviations each across 6 distinct deviation categories
(`term_too_long`, `missing_beweislast_allocation`,
`missing_geschaeftsgeheimnis_anchor`, `missing_exclusions_list`,
`vertragsstrafe_over_bgh_5pct_cap`, `foreign_jurisdiction`). Hand-written
expected deviations in `examples/expected/*.yaml`.

### The citation rule

The deviation spotter returns
`{score: 0|1|2|3, rationale, citation: {playbook_clause_id, contract_text_excerpt}, unverified: bool}`.
The "show your work" rule is enforced here — no citation means `unverified=True`,
and the UI renders unverified flags differently.

### The exit gate

Per the spec, Phase 2 is done when:

- Eval set runs in CI. F1 numbers are reported and saved.
- Citation completeness ≥ 95% (every flag has a citation or is marked unverified).
- Deviation spotter handles "no baseline" cases gracefully.
- The "show your work" rule is documented in the README. (This section.)

### How to run it

```bash
pytest evals/                  # run the harness
cat evals/runs/<timestamp>.json # the per-contract F1, classification, severity, citation report
```

The harness is content-addressed cached (PDF text, embeddings, golden YAMLs,
mocked LLM responses), so re-runs are sub-second once the cache is warm.

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
