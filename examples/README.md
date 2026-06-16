# `examples/` — eval-set fixtures and golden YAMLs

> Index of the contract PDFs and expected-deviation YAMLs that drive
> the eval harness. **Use these as test fixtures**, not as
> representative real-world contracts. The SOURCES files alongside
> the public contracts are the provenance audit trail.

## What's here

```
examples/
├── contracts/
│   ├── public/         # 11 EN contracts from public sources (NDA + DPA + Employment)
│   ├── public-de/      #  9 DE contracts from public sources (NDA + DPA + Employment)
│   ├── synthetic/      #  6 EN contracts, hand-written with known deviations
│   ├── synthetic-de/   #  6 DE contracts, hand-written with known deviations
│   ├── hand-curated/   #  3 EN NDA contracts, hand-injected deviations
│   └── phase1_test/    #  5 EN NDA contracts, the Phase 1 exit-gate fixtures
└── expected/           # 35 golden YAMLs — one per contract, minus phase1_test
```

**40 contract PDFs total**, **35 expected-deviation YAMLs**. The
phase1_test contracts are pre-Phase-2 fixtures; they don't have golden
YAMLs because the Phase 1 exit gate is "the parser doesn't crash and
clause-type F1 ≥ 0.8", not "the deviation spotter gets it right."

## Contract types covered

| Type | Languages | Count | Sourcing |
|---|---|---|---|
| **NDA** (non-disclosure agreement) | EN + DE | 5 EN public + 3 EN hand-curated + 5 EN phase1_test + 2 EN synthetic + 3 DE public + 2 DE synthetic = **20** | Public-source templates (nondisclosureagreement.com, IHK-Hessen, DIHK, BMJ juristic portal) + 2 hand-injected deviations per synthetic |
| **DPA** (data processing agreement, GDPR Art. 28) | EN + DE | 3 EN public + 2 EN synthetic + 3 DE public + 2 DE synthetic = **10** | Public: GDPR Art. 28(3), EDPB Guidelines 07/2020 §6, IAPP Model DPA. DE public: BMJ/EDPB-DE analogues |
| **Employment** (employment agreement) | EN + DE | 3 EN public + 2 EN synthetic + 3 DE public + 2 DE synthetic = **10** | Public: ABA Model Employment Agreement, GOV.UK ERA 1996 s.86/94 garden-leave. DE public: Tarifvertrag-anchored templates |

## Sourcing — read this before writing the eval

Every public contract has a `SOURCES.md`, `SOURCES.dpa.md`, or
`SOURCES.employment.md` next to it that records:

- The exact public source URL.
- The source kind (statute, professional-association model, EU open-data policy, etc.).
- Why it's a public source (no copyright, open license, statutory text).
- The retrieval date.

The hard rule is **"real public source per contract, provenance in
metadata"** (cards `t_463d603d`, `t_0d594e5e`, `t_b238eff4`,
`t_ccb0a7fd`, `t_e4d2c38e`, `t_2bda59fb`). Synthetic contracts
are explicitly labelled `synthetic-` and `synthetic-de-` so a
reviewer never mistakes one for a real signed agreement.

**Do not edit the golden YAMLs to make tests pass.** Per
`AGENTS.md`: "If a golden looks wrong, file a card, get sign-off,
then update the golden AND the rationale."

## How the eval harness uses these

`docs/07-eval-strategy.md` is the full spec. The short version:

1. Load a contract from `examples/contracts/<name>.pdf`.
2. Run the ingest → classify → spot pipeline.
3. Load the expected deviation set from
   `examples/expected/<name>.yaml` (clauses, types, expected
   deviations, severities, citations).
4. Compute classification F1, deviation F1, severity-mismatch count,
   citation completeness.
5. With the counterparty matrix in scope (Phase 5+), also compute
   matrix verdict alignment.

Run the suite:

```bash
cd clausecraft/
# Phase 2 eval harness (deviation F1, classification F1):
uv run pytest tests/phase2/test_deviation_spotter.py -q
# Phase 5 eval harness (matrix verdict alignment, EN + DE):
uv run pytest tests/phase5/test_eval_harness_matrix.py -q
```

## Pointers (don't duplicate these here)

- The deviation-spotter's F1 numbers and methodology live in
  [`evals/leaderboard.csv`](../evals/leaderboard.csv) and
  [`docs/EVAL_RESULTS.md`](../docs/EVAL_RESULTS.md) (Phase 6 deliverable).
- The playbook structure (baselines, counterparty matrix, clause
  taxonomy) lives in [`playbook/`](../playbook/) and
  [`docs/PLAYBOOK.md`](../docs/PLAYBOOK.md) (Phase 6 deliverable).
- The eval rubric philosophy lives in
  [`docs/07-eval-strategy.md`](../docs/07-eval-strategy.md).
- The Phase 5 clause taxonomy and deviation catalogue live in
  [`docs/15-clause-taxonomy-phase5.md`](../docs/15-clause-taxonomy-phase5.md).

## Adding a new contract

1. Drop the PDF in the right subdirectory:
   - Real public source with provenance → `public/` or `public-de/`.
   - Synthetic with hand-injected deviations → `synthetic/` or `synthetic-de/`.
   - Hand-curated NDA test case → `hand-curated/`.
2. Write a `SOURCES.md` (or `SOURCES.<type>.md`) for public sources.
3. Write the golden YAML in `examples/expected/<name>.yaml` matching
   the contract filename. The schema is documented in
   `docs/07-eval-strategy.md`.
4. Add a row to `evals/leaderboard.csv` once you've re-run the eval
   with the new contract in the set.
5. File the card that built it (card id in the commit subject per
   `AGENTS.md`).

## License + disclaimer

The contracts themselves are sourced from public templates and public
statutes — they carry their own licenses (or no copyright, for
statutes). The **codebase** that reads them is Apache 2.0; see
[`LICENSE`](../LICENSE). **The pipeline output is research /
portfolio, not legal advice** — see
[`DISCLAIMER.md`](../DISCLAIMER.md).
