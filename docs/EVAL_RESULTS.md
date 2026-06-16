# EVAL_RESULTS

> The eval is the claim. This doc is the claim, in numbers, for a reviewer
> to read in 5 minutes. Source of truth: `evals/leaderboard.csv`. Most
> recent run: `evals/runs/20260615T105212Z.json`.

## TL;DR

clausecraft v1 is a 25-contract, 2-language (EN/DE), 2-type (NDA, DPA)
eval. On the most recent run, classification F1 is **0.74 EN / 0.67 DE**,
deviation F1 is **1.00 EN / 1.00 DE**, citation completeness is **1.00
EN / 1.00 DE**, and the counterparty matrix did not flip any contract's
verdict (`matrix_changed_contracts_count = 0`). The per-language gap
assertions (10% deviation F1 / 5% citation completeness) both pass. The
harness is in **smoke mode** (`real_llm_mode = False`) — these numbers
are the eval-harness mocks, not production LLM behavior. Per-type:
NDA-EN is the strongest (10 contracts, dev F1 = 1.00); DPA-EN and
DPA-DE match (5 each, dev F1 = 1.00); NDA-DE is the weakest on
classification (5 contracts, F1 = 0.05; the rule-based DE classifier
mis-labels German clause types; the LLM-driven classifier is a
follow-up). The eval set is small (25 contracts, no Employment type in
the harness yet) and the numbers are a **directional signal, not
statistical proof**.

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

Two more numbers live on the run but not the per-type table:

- **Gap assertions (EN vs DE).** Hard-coded thresholds from
  `docs/11-phases.md` Phase 4: deviation F1 drop ≤ 10%, citation
  completeness drop ≤ 5%. Code assertions, not docs — a regression
  fails the run.
- **`matrix_changed_contracts_count`.** Phase 5's "matrix is enforced"
  claim is bounded by this number.

The task spec also names MRR / nDCG@K. **The v1 harness does not report
these.** Retrieval F1 is a set match; ranking-quality metrics are a v2
ask.

## Per-type × per-language F1

The leaderboard row for the most recent run
(`evals/leaderboard.csv`, `run_id = 20260615T105212Z`). Per-type
classification F1 is **micro-averaged** (sum TP/FP/FN across the
contracts in the cell, then compute F1) — same methodology as the
run-level leaderboard aggregates.

| Type × Lang | n | Classification F1 | Deviation F1 | Citation completeness | Severity mismatches |
|---|---|---|---|---|---|
| NDA × EN | 10 | 0.70 | 1.00 | 1.00 | 0 |
| NDA × DE | 5 | 0.05 | 1.00 | 1.00 | 0 |
| DPA × EN | 5 | 0.83 | 1.00 | 1.00 | 0 |
| DPA × DE | 5 | 1.00 | 1.00 | 1.00 | 0 |
| **Run total** | **25** | **0.74 EN / 0.67 DE** | **1.00 / 1.00** | **1.00 / 1.00** | **0 / 0** |

Notes on what the table does and does not show:

- **NDA-DE classification F1 = 0.05 is bad, on purpose, reported as
  is.** The rule-based DE classifier in Phase 4 confuses German label
  sets on § 2 GeschGehG clauses. The product metric (deviation F1 =
  1.00) is unaffected because the deviation set is computed against the
  golden YAML, not the classifier output.
- **DPA-DE classification F1 = 1.00 is a clean pass.** The 5 DPA-DE
  contracts (3 public + 2 synthetic) exercise 7 dpa_* taxonomy values
  (controller/processor designation, sub-processor consent + flowdown,
  transfer mechanism, breach notification, audit rights, data
  return/deletion).
- **Deviation F1 = 1.00 across the board, in smoke mode.** The 11
  stress contracts (synthetic + hand-curated) carry the expected
  deviations; the 14 public-source clean baselines carry 0 expected
  deviations, so on those the F1 denominator is 0 and the harness
  reports 1.00 by convention.
- **Citation completeness = 1.00 everywhere.** Every flag the spotter
  raised had a citation. The "show your work" rule has not been
  stressed under real LLM behavior.
- **Severity mismatches = 0.** The spotter agreed with the golden
  severity on every flagged clause.
- **Matrix verdict counts (run-wide):** EN = 17 acceptable, DE = 12
  acceptable, 0 of any other band on either side, 0 verdict-changed.
  All 29 acceptable verdicts land on stress contracts. The 14 public
  baselines carry 0 flags, so they contribute 0 verdicts to any band.
  `matrix_changed_contracts_count = 0` because the spotter output and
  the matrix-stamped output agree on every (clause, counterparty) cell.

### Gap assertions

| Assertion | EN | DE | Drop | Threshold | Passed |
|---|---|---|---|---|---|
| Deviation F1 | 1.00 | 1.00 | 0.00 | ≤ 0.10 | ✅ |
| Citation completeness | 1.00 | 1.00 | 0.00 | ≤ 0.05 | ✅ |

`gap_passed = True`. Both pass; matrix integrity check passes.

## The eval set

25 contracts total. Frozen per `AGENTS.md` ("the eval set... is frozen.
Do not edit golden YAMLs to 'make tests pass.'"). The harness's
`EVAL_CONTRACTS` list in `evals/conftest.py` is the canonical inventory.

| Type × Lang | Public-source | Synthetic | Hand-curated | Total |
|---|---|---|---|---|
| NDA × EN | 5 | 2 | 3 | 10 |
| NDA × DE | 3 | 2 | 0 | 5 |
| DPA × EN | 3 | 2 | 0 | 5 |
| DPA × DE | 3 | 2 | 0 | 5 |
| **Total** | **14** | **8** | **3** | **25** |

Public contracts are clean baselines (0 expected deviations); they
exercise the spotter's false-positive rate. Stress contracts
(synthetic + hand-curated) carry 3 hand-injected deviations each; they
exercise the spotter's true-positive rate. The golden YAMLs name the
deviations exactly so a regression is unambiguous.

**Per-type provenance.** NDA-EN: ABA NDA elements, US Uniform Trade
Secrets Act. NDA-DE: BMJ juristic portal, DIHK, IHK-München,
IHK-Hessen, WKO FEEI Mustervertrag. DPA-EN: EU SCCs (2021/914), IAPP,
EDPB Guidelines 07/2020 § 6. DPA-DE: Art. 28 DSGVO, DSK Kurzpapier
Nr. 13, BDSG § 62. Sources live on each golden YAML as
`expected_deviations[].citation.source_url`.

**Employment is not in this run.** The expected-YAML set has 5 EN + 5
DE Employment contracts, but `EVAL_CONTRACTS` doesn't register them.
The matrix and classifier enum are wired; harness integration is a
follow-up card. The Employment row is **omitted on purpose** — writing
"not yet measured" instead of "0.0" is the rule.

**Limits.** 25 contracts is small. The DE set is smaller than the EN
set. Stress contracts dominate the recall signal (public contracts
contribute 0 to recall by construction). The 3-vs-5 baseline hedge
from Phase 5 still applies on the DPA-DE public side. **Directional
signal, not statistical proof.** The harness catches regressions; it
does not prove generalization.

## The "eval is the claim" story

The pitch: *a multi-agent contract deviation pipeline with reproducible
evaluation.* The eval is the only artifact that backs the second half
of that sentence. Without the harness, the pipeline is a demo; with
the harness, it's a claim you can re-run.

The deliverables that constitute the claim:

1. **The eval set.** 25 contracts, golden YAMLs in
   `examples/expected/`, frozen.
2. **The eval harness.** `evals/harness.py` + `evals/conftest.py` —
   content-addressed cached, deterministic, runs in CI.
3. **The leaderboard.** `evals/leaderboard.csv` — every run appends a
   row. The most recent row is the current quality bar.
4. **The per-run report.** `evals/runs/{run_id}.json` — per-contract
   breakdown.
5. **This doc.** The 5-minute review surface.

If the numbers above hold on a re-run, the claim holds. If they
don't, the gap assertions and the per-type table tell you which cell
regressed.

## What's NOT in the eval

- **Smoke mode, not live LLM.** `real_llm_mode = False` on every
  leaderboard row. The production model's deviation F1 is **not** in
  this report — it is a follow-up card to wire `real_llm_mode = True`
  and re-run.
- **No counterfactual demo contract.** `demo/known-bad-nda.pdf` (5
  hand-crafted deviations) is a separate Phase 6 artifact for the
  asciinema.
- **No production telemetry.** The "real" numbers here are real on the
  frozen golden set, not on customer traffic.
- **No ranking metrics.** MRR / nDCG@K are not in the v1 harness.
- **No Employment type in the harness.**
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
- [`docs/11-phases.md` § Phase 5](./11-phases.md#phase-5-second-third-contract-types-dpa-employment-counterparty-matrix)
  — the spec the eval set grows out of.
- [`README.md` § How the eval works](../README.md#how-the-eval-works) —
  the README's one-paragraph version of this doc.
- [`evals/leaderboard.csv`](../evals/leaderboard.csv) — the source of
  truth. If the numbers in this doc disagree with the most recent
  leaderboard row, the leaderboard wins.
