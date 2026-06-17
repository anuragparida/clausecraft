# EVAL_RESULTS

> The eval is the claim. This doc is the claim, in numbers, for a reviewer
> to read in 5 minutes. Source of truth: `evals/runs/{run_id}.json`. The
> latest run on this branch is `evals/runs/20260615T105212Z.json`.

## TL;DR

clausecraft v1 is a 25-contract, 2-language (EN/DE), 2-type (NDA, DPA)
eval. On the most recent run, classification F1 is **0.74 EN / 0.6667 DE**,
deviation F1 is **1.00 EN / 1.00 DE**, citation completeness is **1.00
EN / 1.00 DE**, and the counterparty matrix did not flip any contract's
verdict (`matrix_changed_contracts_count = 0`). The per-language gap
assertions (10% deviation F1 / 5% citation completeness) both pass. The
harness is in **smoke mode** (`real_llm_mode = False`) — these numbers
are the eval-harness mocks, not production LLM behavior. The eval set is
small (25 contracts, no Employment type in the harness yet) and the
numbers are a **directional signal, not statistical proof**.

## What we measure, and why

Computed deterministically against the golden YAMLs in
`examples/expected/`. Full definitions and the rubric philosophy live
in [`docs/07-eval-strategy.md`](./07-eval-strategy.md).

| Metric | What it answers |
|---|---|
| **Classification F1** | Did the clause-type classifier label clauses correctly? |
| **Deviation F1** | The product metric. Set match on flagged clauses vs. the golden. |
| **Retrieval F1** | Did the playbook retriever pull the right baseline clauses? |
| **Citation completeness** | What % of flags ship a playbook citation (vs. `unverified`)? |
| **Severity mismatch count** | Flags disagreeing with the golden on a 0–3 severity band (±1 tolerance). |
| **Matrix verdict integrity** | How many (clause, counterparty) cells landed in each band, plus a run-wide count of contracts where the matrix flipped a verdict. |

Two more numbers live on the run but not the per-language table:

- **Gap assertions (EN vs DE).** Hard-coded thresholds from
  `docs/11-phases.md` Phase 4: deviation F1 drop ≤ 10%, citation
  completeness drop ≤ 5%. Code assertions, not docs — a regression
  fails the run.
- **`matrix_changed_contracts_count`.** Phase 5's "matrix is enforced"
  claim is bounded by this number.

The task spec also names MRR / nDCG@K. **The v1 harness does not report
these.** Retrieval F1 is a set match; ranking-quality metrics are a v2
ask.

## Per-language F1 (latest run)

The latest run on this branch is
`evals/runs/20260615T105212Z.json` (started
`2026-06-15T10:52:12.037360+00:00`, `contract_set_version =
0.4.0-phase5-matrix`, `real_llm_mode = False`, 25 contracts,
language filter `both`).

| Language | Classification F1 | Deviation F1 | Citation completeness | Severity mismatches |
|---|---|---|---|---|
| EN | 0.74 | 1.00 | 1.00 | 0 |
| DE | 0.6667 | 1.00 | 1.00 | 0 |
| **Gap (EN vs DE)** | 0.0733 | 0.00 | 0.00 | 0 |

The 10% / 5% gap assertions are:

| Assertion | EN | DE | Drop | Threshold | Passed |
|---|---|---|---|---|---|
| Deviation F1 | 1.00 | 1.00 | 0.00 | ≤ 0.10 | ✅ |
| Citation completeness | 1.00 | 1.00 | 0.00 | ≤ 0.05 | ✅ |

`gap_passed = True`. Both pass; matrix integrity check passes.

Notes on what the table does and does not show:

- **Classification F1 = 0.74 EN / 0.6667 DE is the run-level
  micro-averaged number.** It pools NDA-EN (n=10), DPA-EN (n=5),
  NDA-DE (n=5), DPA-DE (n=5). The per-type cells are uneven — NDA-DE
  classification F1 is poor (the rule-based DE classifier confuses
  German label sets on § 2 GeschGehG clauses), and DPA-DE classification
  F1 is clean. The 25-contract micro-average is a single number; the
  per-type breakdown lives in the per-run JSON's `contracts[]`.
- **Deviation F1 = 1.00 across the board, in smoke mode.** The
  per-run aggregate reports `deviation_f1 = 1.0` run-wide and
  `deviation_f1_en = 1.0` / `deviation_f1_de = 1.0` per language. The
  11 stress contracts (synthetic + hand-curated) carry the expected
  deviations; the 14 public-source clean baselines carry 0 expected
  deviations, so on those the F1 denominator is 0 and the harness
  reports 1.00 by convention.
- **Citation completeness = 1.00 everywhere.** Every flag the spotter
  raised had a citation. The "show your work" rule has not been
  stressed under real LLM behavior.
- **Severity mismatches = 0.** The spotter agreed with the golden
  severity on every flagged clause.
- **Matrix verdict counts (run-wide).** 29 acceptable, 0 of any other
  band, 0 verdict-changed. All 29 acceptable verdicts land on stress
  contracts. The 14 public baselines carry 0 flags, so they
  contribute 0 verdicts to any band.
  `matrix_changed_contracts_count = 0` because the spotter output and
  the matrix-stamped output agree on every (clause, counterparty) cell.

## What the numbers mean

`Deviation F1 = 1.00` is the product metric: every expected deviation
was flagged and no extra deviations were flagged. That's the spotter
working as designed. `Classification F1 = 0.74 EN / 0.6667 DE` is a
classifier quality number — the run-level micro-average across all
contract types and languages. It's lower than deviation F1 because
classification and deviation are different problems: deviation F1 cares
about *whether* a flag was raised, classification F1 cares about *what
label* the clause got. The classifier is allowed to mis-label clauses
that the spotter would still flag for the right reason. The gap
between 0.74 and 0.6667 is the cost of a rule-based DE classifier that
needs a German-trained LLM behind it. Until that lands, the per-type
breakdown lives in the per-run JSON, not the README.

## Limitations (be honest)

- **Smoke mode, not live LLM.** `real_llm_mode = False` on the latest
  run. The harness mocks the LLM with deterministic responses from the
  golden YAMLs. The production model's deviation F1 is **not** in this
  report — wiring `real_llm_mode = True` and re-running is a follow-up
  card. The numbers are real on the frozen golden set, not on customer
  traffic.
- **25 contracts is small.** The set grew 15 → 25 across Phase 4
  (DPA-DE expansion 3→5) and Phase 5 (matrix-aware spotter on the
  full set). 25 is still small. The DE set is smaller than the EN set.
  Stress contracts dominate the recall signal (public contracts
  contribute 0 to recall by construction). The 3-vs-5 baseline hedge
  from Phase 5 still applies on the DPA-DE public side. **Directional
  signal, not statistical proof.** The harness catches regressions; it
  does not prove generalization.
- **Employment is not in the harness.** The expected-YAML set has
  Employment contracts, but `EVAL_CONTRACTS` in `evals/conftest.py`
  doesn't register them. The matrix and classifier enum are wired;
  harness integration is a follow-up card. The Employment cell is
  **omitted on purpose** — writing "not yet measured" instead of "0.0"
  is the rule.
- **NDA-DE classification F1 is bad, on purpose, reported as is.** The
  rule-based DE classifier in Phase 4 confuses German label sets on
  § 2 GeschGehG clauses. The product metric (deviation F1 = 1.00) is
  unaffected because the deviation set is computed against the golden
  YAML, not the classifier output. The LLM-driven DE classifier is a
  follow-up card.
- **Leaderboard CSV on this branch is stale.** The on-disk
  `evals/runs/` directory has the 2026-06-15 runs but
  `evals/leaderboard.csv` was last appended on 2026-06-09. The
  per-run JSONs are the source of truth for the numbers quoted here;
  the leaderboard is an append-only history that gets re-synced when
  Phase 6 lands. (Out of scope for this card; flagged as a workflow
  smell.)
- **No ranking metrics.** MRR / nDCG@K are not in the v1 harness.
- **No model-vs-model comparison.** That is a separate experiment,
  not Phase 6 scope.

## How to reproduce

```bash
cd clausecraft
pytest evals/                     # run the harness
cat evals/runs/<timestamp>.json   # the per-contract report
cat evals/leaderboard.csv         # append-only history of every run
```

The harness is content-addressed cached (PDF text, embeddings, golden
YAMLs, mocked LLM responses), so re-runs are sub-second once the cache
is warm. No Docker, Postgres, or external service required — pure
Python pytest. To force a fresh run (after a prompt or taxonomy
change), delete `evals/.cache/` and re-run; a new row lands in
`evals/leaderboard.csv` on the same commit.

## See also

- [`docs/07-eval-strategy.md`](./07-eval-strategy.md) — the deep dive
  on what F1 means, the eval layers, and the LLM-as-judge plan.
- [`docs/11-phases.md` § Phase 4](./11-phases.md) — the spec the eval
  set grows out of.
- [`README.md` § Per-language quality bar](../README.md) — the
  README's per-language F1 table; this doc is the 5-minute version.
- [`evals/runs/20260615T105212Z.json`](../evals/runs/20260615T105212Z.json)
  — the source of truth for the numbers in this doc. If the numbers
  in this doc disagree with the per-run JSON, the per-run JSON wins.
