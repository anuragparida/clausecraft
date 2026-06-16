# Playbook

The clausecraft playbook is a YAML store of **baseline clauses** (NDA, DPA, Employment) used by the deviation spotter to score user-uploaded contracts. Each baseline is a short legal text (one clause) drawn from a real, public source — a statute, regulator guidance, an official model contract, or a government template.

The deviation spotter compares a user clause's embedding (bge-m3, 1024-d) against the playbook via pgvector cosine similarity (HNSW index, `<=>` operator). The closest baselines are returned as evidence; the spotter then scores the user's clause 0–3 against that evidence.

This doc is for **developers adding a new baseline source or a new clause type**. The taxonomy itself is documented in `docs/15-clause-taxonomy-phase5.md`; the conceptual overview is in `docs/01-feature-spec.md`; the architecture is in `docs/02-architecture.md`.

## Layout

The playbook root is `playbook/` at the repo root. Two top-level entries:

```
playbook/
├── counterparty_matrix.yaml            # verdict escalations per (clause_type, counterparty_type)
└── baselines/
    ├── nda-en/                         # one dir per (contract_type, language) pair
    │   ├── definition_confidential_info.yaml
    │   ├── governing_law.yaml
    │   ├── injunctive_relief.yaml
    │   ├── residual_knowledge.yaml
    │   ├── term.yaml
    │   └── SOURCES.md                  # provenance for the 5 YAMLs in this dir
    ├── nda-de/                         # German NDA baselines
    ├── dpa-en/                         # English DPA baselines
    ├── dpa-de/                         # German DPA baselines
    ├── employment-en/                  # English Employment baselines
    └── employment-de/                  # German Employment baselines
```

The directory name convention is **`playbook/baselines/<contract-type>-<lang>/<clause-type>.yaml`** (e.g. `playbook/baselines/dpa-de/dpa_breach_notification.yaml`). The seeder (`backend/app/playbook/seed.py`) splits the leaf directory on the last dash: `nda-en` → `("nda", "en")`. Both parts are validated: the language suffix is exactly 2 lowercase letters; the contract-type prefix is one of `nda`, `dpa`, `employment` (and any future contract types you add — see "How to add a new clause type" below).

## YAML shape

Each file is **one clause** with a flat schema. The seeder parses it into a `PlaybookBaseline` with a single `BaselineClause`. There is no nesting; the file is the unit of work.

```yaml
# playbook/baselines/nda-en/term.yaml
clause_id: term-of-confidentiality
type: term
language: en
title: Term of Confidentiality Obligations
text: >-
  This Agreement shall commence on the Effective Date and shall
  continue for a period of two (2) years thereafter, unless earlier
  terminated in accordance with its terms. The obligations of
  confidentiality and non-use set forth in this Agreement shall
  survive the termination or expiration of this Agreement for an
  additional period of three (3) years; provided, however, that
  with respect to any Confidential Information that constitutes a
  trade secret under applicable law, such obligations shall survive
  for so long as such information remains a trade secret.
source_url: https://nondisclosureagreement.com/wp-content/uploads/2018/03/Mutual-Non-Disclosure-Agreement.pdf
retrieval_date: 2026-06-07
license: public template, free to download, no copyright notice on the source page
notes: >-
  Indefinite terms ("perpetual confidentiality") and one-sided
  short-form terms (<1 year) are flagged as deviations. Trade-secret
  carve-outs are preserved across all common NDA variants.
```

Field reference:

| Field | Required | Notes |
|---|---|---|
| `clause_id` | yes | Unique within the playbook. Snake-case, descriptive. The DB primary key. |
| `type` | yes | Must be a valid `ClauseType` enum value from `backend/app/classify/schema.py`. |
| `language` | yes | `en` or `de` (matches the parent dir). |
| `title` | yes | Human-readable. Shown in the dev UI's evidence panel. |
| `text` | yes | The clause body. Embedded by the seeder. |
| `source_url` | yes | Real public source. Card rule: "No 'looks plausible' templates from random websites." |
| `retrieval_date` | yes | ISO date (YYYY-MM-DD). When the source was fetched. |
| `license` | yes | One short line describing the source's license / reusability. |
| `notes` | no | Free-form; clarifies what counts as a deviation against this baseline. |

The seeder walks `playbook/baselines/` recursively. For each `.yaml` file it (1) parses, (2) validates the `type` against the `ClauseType` enum, (3) embeds the `text` field (bge-m3, or offline-hash fallback), (4) upserts into `playbook_clauses` keyed on `(playbook_id, clause_id)`.

## How to add a new baseline source

This is **data work, not a PR-shaped code change**. Five steps:

1. **Drop the YAML** in the right directory. For an English NDA confidentiality-period baseline: `playbook/baselines/nda-en/confidentiality_period.yaml`. Use the field reference above; copy `term.yaml` as a starting point.

2. **Validate the `type`.** The seeder raises `ValueError` on an unknown clause type. If your baseline is for a clause type that doesn't exist yet, see "How to add a new clause type" below.

3. **Document the source.** Create or edit the `SOURCES.md` in the same directory. One row per YAML in the table, with: clause type, source URL, source kind, why it's a real public source. Follow the pattern in `playbook/baselines/employment-en/SOURCES.md` or `playbook/baselines/dpa-de/SOURCES.md`. (Not every directory has a `SOURCES.md` yet — `nda-en/` is the one current gap, a leftover from Phase 4. If you're adding a new NDA-EN baseline, create the `SOURCES.md` and backfill rows for the existing 5 NDA-EN YAMLs in the same commit.) Hard rule: every baseline must have a real public source; no "looks plausible" templates.

4. **Re-seed.** Run the seeder to upsert your new YAML into the DB:
   ```bash
   cd /home/ody/workspace/clausecraft
   python -m backend.app.playbook.seed
   ```
   The output table will show the new clause count for your `(contract_type, language)` row. The seeder is idempotent — re-running overwrites existing rows with the same data, so you can iterate on the `text` field and re-seed without manual cleanup.

5. **Commit.** One commit, with the card id in the subject per `AGENTS.md`:
   ```bash
   git add playbook/baselines/nda-en/confidentiality_period.yaml \
           playbook/baselines/nda-en/SOURCES.md
   git commit -m "Phase N (card t_xxx): new NDA-EN confidentiality_period baseline from <source>"
   ```

The spotter picks up the new baseline on the next request (it reads from the DB, not the YAML tree at request time). No code change, no restart.

## How to add a new clause type

This **is** a code change — the `ClauseType` enum, the classifier prompt, and the counterparty matrix all need to know the new value. The baseline YAMLs come last. Six steps:

1. **Extend the enum.** `backend/app/classify/schema.py`:
   ```python
   class ClauseType(str, Enum):
       # ... existing values ...
       new_clause_type = "new_clause_type"
   ```
   The frontend renders a colour-coded badge per value, so add a corresponding `type-<clause_type>` variant to `frontend/src/components/ui/badge.tsx` (the per-type colour map is centralised in the shadcn `Badge` component). The frontend treats the clause type as a free-form `string` — no separate TypeScript enum mirror to update.

2. **Add a prompt entry.** `backend/app/classify/prompt.py` — the system prompt lists each clause type with a one-line definition. Add a line. The few-shot examples block also needs at least one example classified as the new type; copy the pattern of an existing one.

3. **Add at least one baseline per language.** The spotter cannot do cosine-ANN retrieval against zero baselines — it will warn and the eval harness will mark the new type as a regression. For each language you want to support, drop a YAML in `playbook/baselines/<contract-type>-<lang>/<new_clause_type>.yaml` and document it in that dir's `SOURCES.md`. The card's hard rule for baseline sources applies (real public source, SOURCES.md row).

4. **(Optional) Extend the counterparty matrix.** Edit `playbook/counterparty_matrix.yaml`. The relevant section is `clause_verdicts.<contract_type>.<clause_type>` — add a default verdict if the matrix has a different default for the new type than the per-clause "all aligned" default. See `playbook/counterparty_matrix.yaml` for examples.

5. **Re-seed and smoke-test.** Run the seeder (it will validate the new enum value), then run the eval harness to confirm the new clause type is recognised end-to-end. The eval harness is `evals/harness.py`; consult `docs/EVAL_RESULTS.md` (Card 6) for the current per-language F1 numbers.

6. **Commit.** Likely multiple files; one commit per card per `AGENTS.md`:
   ```bash
   git add backend/app/classify/schema.py \
           backend/app/classify/prompt.py \
           playbook/counterparty_matrix.yaml \
           playbook/baselines/<contract-type>-en/<new_clause_type>.yaml \
           playbook/baselines/<contract-type>-de/<new_clause_type>.yaml \
           playbook/baselines/<contract-type>-en/SOURCES.md \
           playbook/baselines/<contract-type>-de/SOURCES.md
   git commit -m "Phase N (card t_xxx): new clause type <new_clause_type> (enum + prompt + baselines)"
   ```

## How to extend the counterparty matrix

The counterparty matrix maps `(clause_type, counterparty_type)` tuples to verdicts (`aligned` / `minor` / `material` / `unacceptable`) that the spotter uses to escalate deviations. The 4 counterparty axes are: business size, data sensitivity, regulatory exposure, and contract value (see `playbook/counterparty_matrix.yaml` header for definitions).

To add or change a verdict:

1. **Edit `playbook/counterparty_matrix.yaml`.** Bump the `version` field at the top (semver — major for breaking shape changes, minor for new verdicts/axes, patch for typo fixes). Edit the relevant `clause_verdicts` or `counterparty_overrides` block. Schema is validated by `backend/app/playbook/counterparty.py::load_matrix`; malformed entries are dropped with a logged warning rather than failing the parse.

2. **No code change.** The matrix is re-read from the YAML on every spot call (`run_stage3` → `_load_matrix_or_default`), so the next request picks up the new verdict. No restart, no seeder run.

3. **Commit.** Card id in the subject:
   ```bash
   git add playbook/counterparty_matrix.yaml
   git commit -m "Phase N (card t_xxx): counterparty matrix — <one-line description of change>"
   ```

The `language_overrides.<lang>.counterparty_overrides` block lets a language-specific override *escalate* an English-aligned verdict to a stricter one (e.g. DE NDA `term` from `aligned` to `material` under German commercial practice). Overrides cannot *relax* a verdict — `lookup_verdict_with_language` rejects a DE override that would be more lenient than the EN default.

## Data vs. code — the sharp distinction

The playbook YAMLs are **data**. The directory tree, the file naming convention, the SOURCES.md pattern — none of it is in source control of the spotter or the API. The seeder walks the directory, embeds each YAML's `text`, and stores it in PostgreSQL. The spotter reads the DB.

This means:
- **Adding a baseline source** is data work: drop a YAML, document the source, re-seed, commit. No code review needed beyond a sanity check on the source URL and license.
- **Editing an existing baseline's text** is data work: change the YAML, re-seed. The seeder upserts; the next spot call uses the new embedding.
- **Adding a clause type** is a code change: the enum, the prompt, the counterparty matrix, and at least one baseline per language. Review it like any other code change.
- **Editing the counterparty matrix** is data work: the matrix is re-read on every request, so a YAML edit is the entire change. Schema validation happens at load time, so a malformed matrix is caught before it affects a spot result.

The `playbook/` directory is bind-mounted read-only inside the docker container (`docker-compose.yml` mounts it as `:ro`); the in-container copy is never edited. To add a new baseline in the running stack, drop the YAML in the repo on the host and re-seed.

## Cross-links

- `docs/01-feature-spec.md` — what the playbook covers conceptually (the "what").
- `docs/02-architecture.md` — how the playbook fits the architecture (the "where").
- `docs/15-clause-taxonomy-phase5.md` — the clause-type taxonomy itself (the values you add to when introducing a new type).
- `docs/EVAL_RESULTS.md` (Card 6, pending) — the per-language F1 numbers that measure whether a new baseline or clause type is helping.
- `backend/app/playbook/seed.py` — the seeder; the canonical source of truth on file layout and validation.
- `backend/app/playbook/store.py` — the pgvector-backed store; the spotter reads from here at request time.
- `backend/app/playbook/counterparty.py` — the counterparty matrix loader and verdict-lookup chain.
