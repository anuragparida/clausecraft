"""Smoke test for the Phase 5 v1 Employment eval set (card t_5400fec1).

For each of the 3 v1 Employment eval contracts (2 EN + 1 DE
synthetic stress contracts), verify that:

  1. The contract PDF is text-extractable (pymupdf can read
     it without OCR).
  2. The corresponding ``examples/expected/synthetic-employment-*``
     YAML file parses cleanly and has the right shape
     (contract, type, language, expected_clauses,
     expected_deviations).
  3. Every ``text_excerpt`` in the YAML's ``expected_clauses``
     appears in the contract's extracted text
     (whitespace-normalized).
  4. Each contract has exactly 3 expected deviations, and
     every deviation's ``clause_id`` points to a real
     clause in the same contract.
  5. Each deviation has a valid severity (1, 2, or 3) and
     a citation with an http(s) source_url and a
     playbook_clause_id.

Coverage check (separate from the per-contract loop): across
the 3 v1 contracts, the 8 employment_* Phase 5 taxonomy
values that v1 commits to covering
(notice_period, remuneration, leave_entitlements,
termination_for_cause, non_solicitation, working_hours,
probation, confidentiality_survival) should all be
exercised at least once. The remaining 3 employment_*
values (garden_leave, non_compete, ip_assignment) are
out of v1 scope and ship in v2's public clean baselines.

This is a manual smoke test (not part of the pytest suite)
— it does not need a live DB or embeddings provider. Run
from the repo root via:

  .eval-venv/bin/python scripts/smoke_employment_eval_set.py

If any contract fails text extraction, the contract text
is non-deterministic (e.g. a fonts/encoding issue) and the
golden YAMLs' ``text_excerpt`` matches will drift across
re-runs. If the YAML shape fails, the eval harness will
crash on load.

The v1 scope is 3 contracts + 3 expected-deviation YAMLs.
The v2 expansion (gated on v1 F1 being acceptable) grows
the set to 10 contracts (3 EN public + 2 EN synthetic + 3
DE public + 2 DE synthetic) with a separate smoke test.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz  # type: ignore[import-not-found]
import yaml  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"

# (yaml_path_relative_to_repo, contract_path_relative_to_repo)
# v1 scope: 2 EN synthetic + 1 DE synthetic stress contracts.
CONTRACTS: list[tuple[str, str]] = [
    (
        "examples/expected/synthetic-employment-001.yaml",
        "examples/contracts/synthetic/employment-001.pdf",
    ),
    (
        "examples/expected/synthetic-employment-002.yaml",
        "examples/contracts/synthetic/employment-002.pdf",
    ),
    (
        "examples/expected/synthetic-employment-de-001.yaml",
        "examples/contracts/synthetic-de/employment-001.pdf",
    ),
]

# The 8 employment_* Phase 5 taxonomy values that v1 commits
# to covering.
V1_EMPLOYMENT_TYPES: set[str] = {
    "employment_notice_period",
    "employment_remuneration",
    "employment_leave_entitlements",
    "employment_termination_for_cause",
    "employment_non_solicitation",
    "employment_working_hours",
    "employment_probation",
    "employment_confidentiality_survival",
}

REQUIRED_EMPLOYMENT_TYPES: set[str] = V1_EMPLOYMENT_TYPES


def _normalize(s: str) -> str:
    """Collapse all runs of whitespace to a single space (PDF wraps mid-paragraph)."""
    return re.sub(r"\s+", " ", s).strip()


def _check_contract(yaml_path: Path, contract_path: Path) -> tuple[int, int, set[str]]:
    """Run all 5 checks on one contract. Returns (n_clauses, n_devs, types_seen)."""
    if not contract_path.exists():
        raise FileNotFoundError(f"contract PDF missing: {contract_path}")
    doc = fitz.open(contract_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    if not text.strip():
        raise ValueError(f"contract PDF has no extractable text: {contract_path}")
    norm_text = _normalize(text)

    if not yaml_path.exists():
        raise FileNotFoundError(f"golden YAML missing: {yaml_path}")
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    for required in ("contract", "type", "language", "expected_clauses", "expected_deviations"):
        if required not in data:
            raise ValueError(f"golden YAML missing {required!r}: {yaml_path}")
    if data["type"] != "employment":
        raise ValueError(f"golden YAML type != 'employment': {yaml_path}")
    if data["language"] not in ("en", "de"):
        raise ValueError(f"golden YAML language not in ('en', 'de'): {yaml_path}")
    expected_clauses = data["expected_clauses"]
    expected_deviations = data["expected_deviations"]
    if not isinstance(expected_clauses, list) or not expected_clauses:
        raise ValueError(f"golden YAML expected_clauses empty: {yaml_path}")
    if not isinstance(expected_deviations, list):
        raise ValueError(f"golden YAML expected_deviations not a list: {yaml_path}")

    types_seen: set[str] = set()
    clause_ids: set[str] = set()

    for clause in expected_clauses:
        cid = clause.get("id")
        ctype = clause.get("type")
        excerpt = clause.get("text_excerpt", "")
        if not cid or not ctype or not excerpt:
            raise ValueError(f"clause missing id/type/text_excerpt: {yaml_path}")
        if cid in clause_ids:
            raise ValueError(f"duplicate clause id {cid!r}: {yaml_path}")
        clause_ids.add(cid)
        types_seen.add(ctype)
        if _normalize(excerpt) not in norm_text:
            raise ValueError(
                f"clause {cid} text_excerpt not found in {contract_path.name}: {excerpt[:80]!r}"
            )

    if len(expected_deviations) != 3:
        raise ValueError(
            f"v1 contract must have exactly 3 expected_deviations, got "
            f"{len(expected_deviations)}: {yaml_path}"
        )

    for dev in expected_deviations:
        for required in ("clause_id", "severity", "category", "rationale", "citation"):
            if required not in dev:
                raise ValueError(
                    f"deviation missing {required!r} in {yaml_path}: {dev}"
                )
        if dev["clause_id"] not in clause_ids:
            raise ValueError(
                f"deviation clause_id {dev['clause_id']!r} not in clauses {clause_ids}: {yaml_path}"
            )
        if dev["severity"] not in (1, 2, 3):
            raise ValueError(
                f"deviation severity {dev['severity']!r} not in (1, 2, 3): {yaml_path}"
            )
        if "playbook_clause_id" not in dev["citation"]:
            raise ValueError(
                f"deviation citation missing playbook_clause_id: {yaml_path}"
            )
        if "source_url" not in dev["citation"]:
            raise ValueError(
                f"deviation citation missing source_url: {yaml_path}"
            )
        if not dev["citation"]["source_url"].startswith("http"):
            raise ValueError(
                f"deviation citation source_url not an http(s) URL: {yaml_path}: "
                f"{dev['citation']['source_url']!r}"
            )

    return len(expected_clauses), len(expected_deviations), types_seen


def main() -> int:
    print(f"=== Phase 5 v1 Employment eval set smoke test ===")
    print(f"Verifying {len(CONTRACTS)} contracts + golden YAMLs...")
    print()

    total_clauses = 0
    total_devs = 0
    all_types: set[str] = set()
    failed: list[tuple[str, str]] = []

    for yaml_rel, contract_rel in CONTRACTS:
        yaml_path = REPO_ROOT / yaml_rel
        contract_path = REPO_ROOT / contract_rel
        try:
            n_clauses, n_devs, types = _check_contract(yaml_path, contract_path)
            total_clauses += n_clauses
            total_devs += n_devs
            all_types |= types
            language = "DE" if "/de/" in contract_rel or "synthetic-employment-de" in yaml_rel else "EN"
            print(
                f"  [OK]   [{language}]  {yaml_rel}  ({n_clauses} clauses, {n_devs} deviations)"
            )
        except (FileNotFoundError, ValueError) as e:
            failed.append((yaml_rel, str(e)))
            print(f"  [FAIL] {yaml_rel}: {e}")

    missing = REQUIRED_EMPLOYMENT_TYPES - all_types
    extra = all_types - V1_EMPLOYMENT_TYPES

    print()
    print("=== Summary ===")
    print(f"Contracts verified: {len(CONTRACTS) - len(failed)}/{len(CONTRACTS)}")
    print(f"Total clauses: {total_clauses}")
    print(f"Total expected deviations: {total_devs}")
    print(f"Distinct employment_* values exercised: {len(all_types)}/{len(V1_EMPLOYMENT_TYPES)}")
    if missing:
        print(f"  MISSING values: {sorted(missing)}")
    if extra:
        print(f"  EXTRA values: {sorted(extra)}")

    if failed:
        print()
        print("FAILURES:")
        for yaml_rel, msg in failed:
            print(f"  - {yaml_rel}: {msg}")
        return 1
    if missing:
        print()
        print(f"Coverage gap: {len(missing)} employment_* values not exercised.")
        return 1
    if extra:
        print()
        print(f"Unknown employment_* values: {extra}")
        return 1

    print()
    print("=== All 3 v1 contracts pass smoke test ===")
    print(
        f"All 8 employment_* Phase 5 taxonomy values committed to v1 are exercised across the 3 v1 contracts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
