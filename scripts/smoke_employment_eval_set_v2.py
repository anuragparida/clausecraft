"""Smoke test for the Phase 5 v2 Employment eval set (card t_ccb0a7fd).

This is the v2 expansion smoke test. It covers the full
v1 + v2 set (10 contracts: 3 EN public + 2 EN synthetic + 3 DE
public + 2 DE synthetic) and all 11 employment_* Phase 5
taxonomy values. v1 covered 8 of 11 values; v2 adds the
remaining 3 (garden_leave, non_compete, ip_assignment).

For each of the 10 Employment eval contracts (3 v1 + 7 v2),
verify that:

  1. The contract PDF is text-extractable (pymupdf can read
     it without OCR).
  2. The corresponding ``examples/expected/...employment-*.yaml``
     file parses cleanly and has the right shape
     (contract, type, language, expected_clauses,
     expected_deviations).
  3. Every ``text_excerpt`` in the YAML's ``expected_clauses``
     appears in the contract's extracted text
     (whitespace-normalized).
  4. Each contract has exactly 8 expected clauses, and every
     clause's ``id`` is c1..c8 and ``type`` is one of the
     11 employment_* Phase 5 taxonomy values.
  5. Synthetic stress contracts have exactly 3 expected
     deviations; public clean baselines have exactly 0.
  6. Every deviation's ``clause_id`` points to a real
     clause in the same contract, has a valid severity
     (1, 2, or 3), and a citation with an http(s)
     source_url and a playbook_clause_id.

Aggregate coverage check (separate from the per-contract
loop): across all 10 contracts, all 11 employment_* Phase 5
taxonomy values should be exercised at least once.

This is a manual smoke test (not part of the pytest suite)
— it does not need a live DB or embeddings provider. Run
from the repo root via:

  .eval-venv/bin/python scripts/smoke_employment_eval_set_v2.py

If any contract fails text extraction, the contract text
is non-deterministic (e.g. a fonts/encoding issue) and the
golden YAMLs' ``text_excerpt`` matches will drift across
re-runs. If the YAML shape fails, the eval harness will
crash on load.

The 10 contracts (v1 + v2 expansion):
  v1 (3 contracts, FROZEN, see card t_5400fec1):
    - synthetic/employment-001.pdf        (EN ABA-anchored stress)
    - synthetic/employment-002.pdf        (EN GOV.UK-anchored stress)
    - synthetic-de/employment-001.pdf     (DE IHK + BGB stress)
  v2 (7 contracts, see card t_ccb0a7fd):
    - public/employment-001.pdf            (EN ABA model + garden_leave + non_compete)
    - public/employment-002.pdf            (EN US tech startup + ip_assignment)
    - public/employment-003.pdf            (EN GOV.UK + garden_leave)
    - public-de/employment-001.pdf         (DE IHK Mustervertrag + non_compete + garden_leave)
    - public-de/employment-002.pdf         (DE BGB § 74 HGB + non_compete)
    - public-de/employment-003.pdf         (DE ArbEG + ip_assignment)
    - synthetic-de/employment-002.pdf      (DE BGB stress, different deviations)
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
# v1+v2: 10 contracts total (3 v1 + 7 v2), 3 EN public + 2 EN synthetic + 3 DE public + 2 DE synthetic.
CONTRACTS: list[tuple[str, str]] = [
    # --- v1 (frozen) ---
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
    # --- v2 (new, this card t_ccb0a7fd) ---
    (
        "examples/expected/public-employment-001.yaml",
        "examples/contracts/public/employment-001.pdf",
    ),
    (
        "examples/expected/public-employment-002.yaml",
        "examples/contracts/public/employment-002.pdf",
    ),
    (
        "examples/expected/public-employment-003.yaml",
        "examples/contracts/public/employment-003.pdf",
    ),
    (
        "examples/expected/public-de-employment-001.yaml",
        "examples/contracts/public-de/employment-001.pdf",
    ),
    (
        "examples/expected/public-de-employment-002.yaml",
        "examples/contracts/public-de/employment-002.pdf",
    ),
    (
        "examples/expected/public-de-employment-003.yaml",
        "examples/contracts/public-de/employment-003.pdf",
    ),
    (
        "examples/expected/synthetic-de-employment-002.yaml",
        "examples/contracts/synthetic-de/employment-002.pdf",
    ),
]

# The 11 employment_* Phase 5 taxonomy values.
ALL_TAXONOMY_VALUES: list[str] = [
    "employment_notice_period",
    "employment_remuneration",
    "employment_leave_entitlements",
    "employment_termination_for_cause",
    "employment_non_solicitation",
    "employment_working_hours",
    "employment_probation",
    "employment_confidentiality_survival",
    "employment_garden_leave",
    "employment_non_compete",
    "employment_ip_assignment",
]

# v1 commits to covering 8 of these (notice_period,
# remuneration, leave_entitlements, termination_for_cause,
# non_solicitation, working_hours, probation,
# confidentiality_survival). v2 adds the remaining 3
# (garden_leave, non_compete, ip_assignment).
V1_TAXONOMY_VALUES: list[str] = [
    "employment_notice_period",
    "employment_remuneration",
    "employment_leave_entitlements",
    "employment_termination_for_cause",
    "employment_non_solicitation",
    "employment_working_hours",
    "employment_probation",
    "employment_confidentiality_survival",
]
V2_NEW_TAXONOMY_VALUES: list[str] = [
    "employment_garden_leave",
    "employment_non_compete",
    "employment_ip_assignment",
]

# v1 contracts: synthetic stress with 3 deviations each.
# v2 contracts: public clean baselines (0 deviations) + 1 DE synthetic stress (3 deviations).
V1_YAML_PATHS: set[str] = {
    "examples/expected/synthetic-employment-001.yaml",
    "examples/expected/synthetic-employment-002.yaml",
    "examples/expected/synthetic-employment-de-001.yaml",
}
SYNTHETIC_DE_V2_YAML_PATH: str = "examples/expected/synthetic-de-employment-002.yaml"


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _check_contract(yml_path: Path, pdf_path: Path) -> tuple[bool, list[str]]:
    """Return (ok, errors) for a single (yaml, pdf) pair."""
    errors: list[str] = []
    yml_rel = yml_path.relative_to(REPO_ROOT).as_posix()
    pdf_rel = pdf_path.relative_to(REPO_ROOT).as_posix()

    # 1. PDF text-extractable
    if not pdf_path.exists():
        return False, [f"{pdf_rel}: missing PDF"]
    try:
        doc = fitz.open(pdf_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
    except Exception as exc:
        return False, [f"{pdf_rel}: pymupdf open failed: {exc}"]
    if len(text) < 200:
        errors.append(f"{pdf_rel}: extracted text is suspiciously short ({len(text)} chars)")

    # 2. YAML parses cleanly with the right shape
    if not yml_path.exists():
        return False, [f"{yml_rel}: missing YAML"]
    try:
        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return False, [f"{yml_rel}: YAML parse failed: {exc}"]
    for required_key in ("contract", "type", "language", "expected_clauses", "expected_deviations"):
        if required_key not in data:
            errors.append(f"{yml_rel}: missing key {required_key!r}")
    if errors:
        return False, errors
    if data["type"] != "employment":
        errors.append(f"{yml_rel}: type={data['type']!r} expected 'employment'")

    # 3. Every text_excerpt appears in the contract text (whitespace-normalized)
    norm_text = _normalize(text)
    clause_ids: set[str] = set()
    clause_types_seen: list[str] = []
    for clause in data["expected_clauses"]:
        cid = clause.get("id")
        ctype = clause.get("type")
        exc = clause.get("text_excerpt")
        if cid is None or ctype is None or exc is None:
            errors.append(f"{yml_rel}: clause missing id/type/text_excerpt: {clause!r}")
            continue
        clause_ids.add(cid)
        clause_types_seen.append(ctype)
        if _normalize(exc) not in norm_text:
            errors.append(
                f"{yml_rel}: c{cid} ({ctype}) text_excerpt not found in PDF text. "
                f"excerpt[:80]={_normalize(exc)[:80]!r}"
            )

    # 4. Exactly 8 expected_clauses, ids c1..c8, types from the 11-value taxonomy
    if len(data["expected_clauses"]) != 8:
        errors.append(
            f"{yml_rel}: expected 8 expected_clauses, got {len(data['expected_clauses'])}"
        )
    expected_ids = {f"c{i}" for i in range(1, 9)}
    if clause_ids != expected_ids:
        errors.append(
            f"{yml_rel}: clause ids {clause_ids} != expected {expected_ids}"
        )
    for ctype in clause_types_seen:
        if ctype not in ALL_TAXONOMY_VALUES:
            errors.append(f"{yml_rel}: unknown taxonomy value {ctype!r}")

    # 5. Synthetic stress: 3 deviations; public clean baseline: 0 deviations
    deviations = data.get("expected_deviations") or []
    is_synthetic = yml_rel in V1_YAML_PATHS or yml_rel == SYNTHETIC_DE_V2_YAML_PATH
    if is_synthetic:
        if len(deviations) != 3:
            errors.append(
                f"{yml_rel}: synthetic stress contract should have 3 deviations, got {len(deviations)}"
            )
    else:
        if len(deviations) != 0:
            errors.append(
                f"{yml_rel}: public clean baseline should have 0 deviations, got {len(deviations)}"
            )

    # 6. Every deviation's clause_id points to a real clause; severity 1/2/3; citation complete
    for dev in deviations:
        if dev.get("clause_id") not in clause_ids:
            errors.append(
                f"{yml_rel}: deviation references unknown clause_id {dev.get('clause_id')!r}"
            )
        sev = dev.get("severity")
        if sev not in (1, 2, 3):
            errors.append(
                f"{yml_rel}: deviation severity={sev!r} not in (1, 2, 3)"
            )
        cit = dev.get("citation") or {}
        url = cit.get("source_url", "")
        pid = cit.get("playbook_clause_id", "")
        if not url.startswith("http://") and not url.startswith("https://"):
            errors.append(
                f"{yml_rel}: deviation citation source_url is not http(s): {url!r}"
            )
        if not pid:
            errors.append(
                f"{yml_rel}: deviation citation playbook_clause_id is empty"
            )

    return (len(errors) == 0), errors


def main() -> int:
    all_ok = True
    all_types_seen: set[str] = set()
    v1_types_seen: set[str] = set()
    v2_new_types_seen: set[str] = set()
    n_contracts = 0
    n_deviations = 0
    n_clean_baselines = 0

    for yml_rel, pdf_rel in CONTRACTS:
        yml_path = REPO_ROOT / yml_rel
        pdf_path = REPO_ROOT / pdf_rel
        ok, errors = _check_contract(yml_path, pdf_path)
        n_contracts += 1
        if not ok:
            all_ok = False
            for e in errors:
                print(f"FAIL: {e}")
            continue
        # Accumulate aggregate stats
        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        for clause in data["expected_clauses"]:
            t = clause["type"]
            all_types_seen.add(t)
            if yml_rel in V1_YAML_PATHS:
                v1_types_seen.add(t)
            else:
                if t in V2_NEW_TAXONOMY_VALUES:
                    v2_new_types_seen.add(t)
        n_deviations += len(data.get("expected_deviations") or [])
        if not (data.get("expected_deviations") or []):
            n_clean_baselines += 1
        print(f"OK: {pdf_rel} <-> {yml_rel}")

    # Aggregate coverage
    print()
    print(f"Contracts: {n_contracts}/10")
    print(f"Clean baselines (0 deviations): {n_clean_baselines}")
    print(f"Stress contracts (3 deviations each): {n_contracts - n_clean_baselines}")
    print(f"Total expected deviations: {n_deviations}")
    print(f"v1 taxonomy values seen (target 8): {len(v1_types_seen)}/8")
    print(f"v2 NEW taxonomy values seen (target 3): {len(v2_new_types_seen)}/3")
    print(f"All 11 employment_* values seen: {len(all_types_seen)}/11")

    missing_v1 = set(V1_TAXONOMY_VALUES) - v1_types_seen
    missing_v2 = set(V2_NEW_TAXONOMY_VALUES) - v2_new_types_seen
    if missing_v1:
        print(f"FAIL: v1 taxonomy values missing: {sorted(missing_v1)}")
        all_ok = False
    if missing_v2:
        print(f"FAIL: v2 NEW taxonomy values missing: {sorted(missing_v2)}")
        all_ok = False
    if len(all_types_seen) < len(ALL_TAXONOMY_VALUES):
        missing = set(ALL_TAXONOMY_VALUES) - all_types_seen
        print(f"FAIL: taxonomy values missing: {sorted(missing)}")
        all_ok = False
    if n_contracts != 10:
        print(f"FAIL: contract count is {n_contracts}, expected 10")
        all_ok = False
    if n_clean_baselines != 6:
        print(f"FAIL: clean baseline count is {n_clean_baselines}, expected 6")
        all_ok = False
    if n_deviations != 12:  # 3 v1 (3) + 1 v2 DE synthetic (3) = 12
        print(f"FAIL: total deviations is {n_deviations}, expected 12")
        all_ok = False

    print()
    print("V2 SMOKE TEST PASS" if all_ok else "V2 SMOKE TEST FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
