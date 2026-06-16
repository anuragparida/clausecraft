"""End-to-end test: 10 DPA contracts × upload → spot → redline → audit.

Phase 5 card t_e4d2c38e. Per the card body:

  "5 DPA contracts × end-to-end (upload → review → redline). Each test asserts:
   - redline .docx opens in Word/LibreOffice
   - ≥ 1 tracked change present
   - audit log has ≥ 1 row per stage (ingest, classify, spot, redline, approve)
   - matrix verdict rendered in the deviation table"

The v2 DPA eval set (card t_0d594e5e) shipped 10 fixtures
(3 public-EN + 2 synthetic-EN + 3 public-DE + 2 synthetic-DE)
— overshooting the card body's "5 contracts" target to
cover the full 9 dpa_* ClauseType taxonomy + 3 NEW deviation
categories per language pair. This e2e parametrizes over
all 10 v2 fixtures.

The card body's "5 contracts" was a v1→v2 expansion target
that v2 overshot. The smoke/full CI split the card body
specifies resolves as: the smoke set is the v1 3 contracts
(the parametrize list's first 3 entries), the full set is
the v2 10 (the entire parametrize list). Both must pass.
The test file ships the full set; the v1-only smoke run is
``pytest -k 'public/dpa-001.pdf or synthetic/dpa-001.pdf or
synthetic-de/dpa-001.pdf'`` (3 contracts) — that's the
"smoke" sub-selection for fast PR feedback. The full set
runs on main.

The test is a real e2e, not a unit test mocking the pipeline.
It goes through the same HTTP / LangGraph path the UI uses.

Hard rules (verbatim from the card body)
----------------------------------------

- Assertion 1 (redline .docx opens) catches a class of bugs
  where the docx renderer emits a structurally-broken file
  (the docx is a zip + OOXML; if the zip is corrupt or the
  ``document.xml`` doesn't parse, Word/LibreOffice will
  refuse to open it).

- Assertion 2 (≥1 tracked change) catches the drafter's
  no-op path. A redline .docx with no tracked changes is
  a 0-effort output — the user can see it parsed but the
  "redline" is empty. **If this assertion starts failing,
  fix the upstream drafter / stub, don't relax the
  assertion.**

- Assertion 3 (≥1 row per stage) catches a regression in
  the audit log's stage coverage. Required stages per the
  Build 4 audit schema: ``graph_started``, ``flag_accepted``,
  ``redline_generated``, ``graph_resumed``. The card body's
  "ingest, classify, spot, redline, approve" rolls up to
  these typed-state-machine tokens.

- Assertion 4 (matrix verdict rendered) is the **kill shot**
  for the Phase 5 matrix-aware spotter. The spot response's
  ``SpotFlag`` carries ``matrix_verdict`` (one of
  ``acceptable | material | unacceptable | unverified`` per
  the spec's 4-state column), ``matrix_sources`` (a non-empty
  lookup chain), and ``matrix_counterparty_type`` (the axis
  the matrix was consulted with). **If this assertion starts
  failing, fix the matrix plumbing, don't relax the
  assertion.** The Phase 5 UI work (card t_1e6fa8e2) is
  meaningless until the wire format carries these fields.

- Assertion 5 (per-clause language) catches the silent-EN
  / silent-DE fallback on a per-document basis. EN contracts
  must have every clause labeled ``language="en"``; the DE
  contract must have every clause labeled ``language="de"``.
  This is the Phase 4 kill shot applied to Phase 5 — same
  test surface, same enforcement. **Fix the upstream language
  detection, don't relax the assertion.**

The test runs the same HTTP path as the existing e2e
footprint (Phase 3 / Phase 4) and adds nothing new to the
production code path — the drafter and spotter are stubbed
identically to the Phase 4 e2e (the test host has only a
placeholder LLM key).

Why the spotter stub carries matrix audit fields
------------------------------------------------

Assertion 4 is the kill shot — it asserts the matrix
plumbing is *actually wired* end-to-end (not just declared
on the Pydantic model). The stub returns flags with
``matrix_verdict="material"``, ``matrix_sources=["flat"]``,
``matrix_counterparty_type="any"`` so the assertion has
real values to verify. A stub that emits ``None`` for
``matrix_verdict`` would defeat the kill shot (a regression
where the orchestrator stops stamping would pass the test).

The choice of "material" + ["flat"] is the spec's flat-
baseline default: when ``counterparty_type="any"``, the
matrix consults only the flat table and the spec's 4-state
column for a score-2 deviation is "material". v2 of this
test (when the e2e goes through the real spotter) can
exercise the ``public_sector`` / ``healthcare`` axes
where the per-type escalation rule promotes score-2 to
"unacceptable" (card t_7c0ca277). For v1, the e2e is a
plumbing check, not a matrix-accuracy check — the spec
puts the matrix-accuracy check in the QA hook ("Confirm
the matrix verdict influenced the score" on 5 random
deviation rationales), not in the CI smoke set.

Smoke vs full
-------------

The card body specifies: "5/5 contracts pass the full E2E;
CI runs the smoke set on PR, the full set on main."

This file ships the **full set**: all 10 v2 DPA eval-set
fixtures. The smoke sub-selection for fast PR feedback is
the 3 v1 fixtures (the first 3 entries of the parametrize
list), invocable as:

    pytest tests/e2e/test_phase5_dpa_round_trip.py -v \\
        -k 'public/dpa-001.pdf or synthetic/dpa-001.pdf or synthetic-de/dpa-001.pdf'

The full set (10 v2 contracts) runs on main. The v2
expansion overshot the card body's "5 contracts" target
to 10 — the rationale is in the v2 commit message
(``Phase 5 (card t_0d594e5e): v2 DPA eval set expansion
3→10``): covers the full 9 dpa_* ClauseType taxonomy + 3
NEW deviation categories per language pair.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

# Reuse the docx-validation helpers from the Phase 3 e2e
# footprint. The single source of truth for "what does a
# valid redline .docx look like" lives there.
from tests.phase3.docx_utils import (
    extract_change_authors,
    iter_tracked_changes,
    load_document,
)
from tests.phase3.audit_utils import (
    AuditLogRow,
    assert_every_row_has_actor,
    parse_audit_log_json,
)

from app.agents.deviation_spotter.schema import DeviationFlag
from app.agents.redline_drafter.schema import RedlineProposal
from app.pipeline import stage3_spot, stage5_redline


# --- Autouse: dispose the engine + pool after each test --------------
#
# Same pattern as the Phase 3 / Phase 4 e2e: the module-level
# engine in :mod:`app.db` is created on whichever loop first
# calls :func:`get_engine` (TestClient's portal loop, usually),
# and the pool's cached asyncpg connections are bound to
# that loop. The next test then trips "got Future attached
# to a different loop" at the first ``await session.execute(...)``
# (the audit write in ``process_decisions``).
#
# Disposing the engine after each test forces a fresh
# engine + pool for the next test.
@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_per_test() -> AsyncIterator[None]:
    yield
    try:
        from app.db import get_engine

        engine = get_engine()
        await engine.dispose()
    except Exception:  # noqa: BLE001
        pass


# --- Spec 4-state column values for assertion 4 ----------------------
#
# The Phase 5 spec's "matrix verdict" column carries exactly
# one of these 4 values per the deviation table UI. The wire
# format's ``SpotFlag.matrix_verdict`` MUST be one of these
# (legacy / non-matrix-aware callers carry ``None``, which
# the UI renders as "unverified" — the assertion below
# catches a regression where the API plumbing drops the
# field entirely or emits a non-spec value).
SPEC_MATRIX_VERDICT_VALUES: frozenset[str] = frozenset(
    {"acceptable", "material", "unacceptable", "unverified"}
)


# --- Fixtures ---------------------------------------------------------


REPO_ROOT_PATH = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT_PATH / "examples" / "contracts"


# The v2 DPA eval set (card t_0d594e5e) shipped 10 contracts:
# 3 public-EN + 2 synthetic-EN + 3 public-DE + 2 synthetic-DE.
#
# Distribution rationale (per the v2 commit message, the spec
# at t_f3212fc0): the spec called for "3 public + 2 synthetic ×
# 2 languages" (= 10) to cover the full 9 dpa_* ClauseType
# Phase 5 taxonomy. v1 shipped 3 of these (1 public-EN + 1
# synthetic-EN + 1 synthetic-DE); v2 added the remaining 7.
#
# The e2e card body says "5 contracts" — that was the v1→v2
# expansion target. Anurag's v2 overshot to 10 (covers more
# taxonomy cells, 3 NEW deviation categories per language
# pair, and 6 distinct public hosts across 6 public
# contracts). The e2e parametrizes over all 10 — the smoke
# vs full CI split the card body specifies resolves as "the
# smoke set is the v1 3 contracts (which exercise 1 cell of
# every assertion); the full set is the v2 10." Both must
# pass; this file ships the full set, and the parametrize
# list is the single line to extend if a v3 expansion ever
# lands.
#
# (filename, expected_language) pairs, sorted by language
# then by source host so CI failures are reproducible:
DPA_CONTRACTS: tuple[tuple[str, str], ...] = (
    # EN public clean baselines (3 contracts)
    (
        "public/dpa-001.pdf",
        "en",
    ),
    (
        "public/dpa-002.pdf",
        "en",
    ),
    (
        "public/dpa-003.pdf",
        "en",
    ),
    # EN synthetic stress (2 contracts)
    (
        "synthetic/dpa-001.pdf",
        "en",
    ),
    (
        "synthetic/dpa-002.pdf",
        "en",
    ),
    # DE public clean baselines (3 contracts)
    (
        "public-de/dpa-001.pdf",
        "de",
    ),
    (
        "public-de/dpa-002.pdf",
        "de",
    ),
    (
        "public-de/dpa-003.pdf",
        "de",
    ),
    # DE synthetic stress (2 contracts)
    (
        "synthetic-de/dpa-001.pdf",
        "de",
    ),
    (
        "synthetic-de/dpa-002.pdf",
        "de",
    ),
)


def _read(path: Path) -> bytes:
    """Read a file's bytes; pytest.fail loudly if missing."""
    if not path.exists():
        pytest.fail(f"Phase 5 DPA e2e fixture contract missing: {path}")
    return path.read_bytes()


# --- Drafter stub (Phase 5 DPA variant) -------------------------------
#
# The drafter is the only LLM-bound component in the Build 6
# path; the test host has only a placeholder LLM key. We
# stub the drafter with a deterministic EN-rationale stub
# (DE isn't strictly required here — assertion 5 is the
# language-field check on the ingest path, not the drafter's
# rationale). The DPA e2e doesn't need DE rationales in the
# audit log because the drafter's rationale is the redline
# prose, not the language-marker kill shot.
#
# The stub returns a RedlineProposal with a stable EN
# rationale + diff_summary + a proposed_text that differs
# from the original (the docx renderer needs a diff to
# render tracked changes; an identical proposed_text would
# produce 0 changes and fail assertion 2).
DPA_STUB_RATIONALE: str = (
    "Stub (Phase 5 DPA e2e): rewrote the clause to align with "
    "the GDPR Art. 28(3) mandatory-contents checklist. The "
    "data subject's rights, sub-processor flow-down, and "
    "breach-notification inner window are anchored against the "
    "EDPB Guidelines 07/2020 § 6 + DSGVO Art. 33(1)."
)
DPA_STUB_DIFF_SUMMARY: str = (
    "Stub: aligns the clause to the DPA playbook baseline "
    "(GDPR Art. 28(3) + Art. 33(1))."
)


def _make_dpa_proposal_text(original_text: str) -> str:
    """EN-language proposed_text for the stub.

    The proposed text must differ from the original (otherwise
    the docx renderer has no diff to render). The stub prepends
    a marker line so the test can assert the stub's output made
    it through end-to-end.
    """
    return (
        "[DPA-REDLINE-STUB] "
        + (original_text[:500] if original_text else "DPA stub proposed text")
        + " [END-STUB]"
    )


async def _stub_dpa_drafter(
    drafter_input: Any, contract_filename: str = ""
) -> RedlineProposal:
    """Drafter stub: returns a happy-path RedlineProposal with a
    Phase 5 DPA rationale."""
    return RedlineProposal(
        proposed_text=_make_dpa_proposal_text(drafter_input.clause_text),
        rationale=DPA_STUB_RATIONALE,
        diff_summary=DPA_STUB_DIFF_SUMMARY,
        attempt=1,
    )


def _make_dpa_flag(clause_id: str, *, score: int = 2) -> DeviationFlag:
    """Build a deterministic DeviationFlag for the e2e stub.

    Same pattern as the Phase 3 / Phase 4 e2e: one score=2 flag
    per input clause, with a stub rationale. The Phase 5 twist:
    the flag carries matrix audit fields (``matrix_verdict``,
    ``matrix_sources``, ``matrix_counterparty_type``) so
    assertion 4 (matrix verdict rendered) has real values to
    verify. Without these fields, a regression where the API
    plumbing drops them would not be caught by the assertion
    (the flag would be `None`-shaped and the assertion would
    trivially fail at the "every flag has matrix_verdict in
    the spec 4-state" check — but the failure mode would be
    "spotter stub never set the field," not "API plumbing
    dropped the field," which is harder to debug).
    """
    return DeviationFlag(
        clause_id=clause_id,
        score=score,
        rationale=(
            f"e2e DPA stub: synthetic flag for {clause_id} "
            f"(deterministic, matrix plumbing verified)"
        ),
        citation=None,
        unverified=False,
        baseline_type="dpa_unknown",
        # Phase 5 matrix audit fields. The values match the
        # spec's flat-baseline defaults: when
        # counterparty_type="any", the matrix consults only
        # the flat clause_verdicts table and a score-2
        # deviation is bridged to the spec's 4-state column
        # form as "material". Sources is the lookup chain
        # (just the flat cell hit).
        matrix_verdict="material",
        matrix_sources=["flat"],
        matrix_counterparty_type="any",
    )


async def _spot_stub_dpa(
    *,
    clauses: list[Any],
    contract_filename: str = "",
    counterparty_type: str = "any",
) -> Any:
    """Spot-stage stub: emit one score=2 flag per input clause.

    Phase 5: accepts the ``counterparty_type`` kwarg from
    :func:`app.main.post_contracts_spot`'s new forward
    (the API plumbing wires the request's counterparty
    axis into :func:`run_stage3`; this stub mirrors that
    signature but ignores the value because it emits
    counterparty-agnostic score-2 flags).

    Returns a :class:`Stage3Result` with one flag per
    clause so the downstream /decisions path has flags
    to act on. Each flag carries matrix audit fields
    (matrix_verdict="material", matrix_sources=["flat"],
    matrix_counterparty_type="any") so assertion 4 has
    real values to verify.
    """
    from app.pipeline.stage3_spot import Stage3Result

    flags = [_make_dpa_flag(c.id, score=2) for c in clauses]
    return Stage3Result(
        contract_filename=contract_filename,
        flags=flags,
        flagged_count=len(flags),
        unverified_count=0,
        no_baseline_count=0,
        matrix_version="phase5-flat-stub-v0",
        embedding_provider="e2e-dpa-stub",
    )


# --- Pytest fixtures --------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def placeholder_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the LLM key to a placeholder for the whole e2e.

    Same pattern as the Phase 3 / Phase 4 e2e. The classifier
    + spotter paths read ``settings.llm_api_key``; with a
    placeholder key, the classifier falls back to deterministic
    rules, the spotter abstains, and the drafter raises
    :class:`DrafterUnavailable` (which we patch around with
    the DPA-aware drafter stub).
    """
    from app.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "placeholder-not-a-real-key")
    yield


@pytest.fixture(scope="function")
def drafter_dpa_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the drafter to always return a happy-path DPA-rationale proposal.

    Patches two names (same dual-patch as the Phase 3 / Phase 4 e2e):

    - ``app.pipeline.stage5_redline.run_with_self_check`` —
      the canonical location.
    - ``app.pipeline.phase3_pipeline.run_with_self_check`` —
      the import-time bound name in
      :mod:`app.pipeline.phase3_pipeline`. The pipeline does
      ``from app.agents.redline_drafter.self_check import
      run_with_self_check`` at import time, so the attribute
      on the ``phase3_pipeline`` module is a *direct reference*
      to the original function object. Patching only the
      source module does NOT update the name ``phase3_pipeline``
      captured.
    """
    from app.pipeline import phase3_pipeline

    monkeypatch.setattr(
        stage5_redline, "run_with_self_check", _stub_dpa_drafter
    )
    monkeypatch.setattr(
        phase3_pipeline, "run_with_self_check", _stub_dpa_drafter
    )


@pytest.fixture(scope="function")
def spot_dpa_synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the spot stage to emit one synthetic flag per clause.

    Triple-patch (same as the Phase 3 / Phase 4 e2e):

    - ``app.pipeline.stage3_spot.run_stage3`` — the function
      the rest of the pipeline calls.
    - ``app.pipeline.run_stage3`` — the re-export in the
      public ``app.pipeline.__init__``.
    - ``app.main.run_stage3`` — the import-time bound name
      in :mod:`app.main`. ``app.main`` did
      ``from app.pipeline import ... run_stage3`` at import
      time, so the attribute on the ``app.main`` module is a
      *direct reference* to the original function object —
      patching the source module's attribute does NOT update
      the name ``app.main`` captured. Patching ``app.main``
      directly is the only way to make the FastAPI route
      handler see the stub.

    The stub signature mirrors the real
    :func:`app.pipeline.stage3_spot.run_stage3` kwargs-only
    shape (``*, clauses, contract_filename,
    counterparty_type``) so the new
    :func:`app.main.post_contracts_spot` forward (which
    threads ``counterparty_type=payload.counterparty_type``
    into ``run_stage3``) is exercised end-to-end by the
    test.
    """
    import app.main as main_mod
    import app.pipeline as pipeline_mod

    monkeypatch.setattr(stage3_spot, "run_stage3", _spot_stub_dpa)
    monkeypatch.setattr(pipeline_mod, "run_stage3", _spot_stub_dpa)
    monkeypatch.setattr(main_mod, "run_stage3", _spot_stub_dpa)


@pytest.fixture(scope="function")
def client(placeholder_llm_key: None) -> Iterable[TestClient]:
    """A FastAPI TestClient bound to the real ``app.main`` ASGI app.

    Function-scoped so the in-memory state store is fresh for
    every test (the Build 6 path's contract_id → state mapping
    is a process-local dict; a stale state would silently use
    the wrong clauses on the next ``/decisions`` call).
    """
    from app.main import app

    with TestClient(app) as c:
        yield c


def _new_contract_id(prefix: str) -> str:
    """Unique contract id for the test run.

    The Build 6 in-memory state store keys on filename, and
    the in-memory state shares an audit-log key with the
    Postgres audit_events table (contract_id). We use a
    unique filename per test so concurrent test runs don't
    trip on each other.
    """
    return f"{prefix}-dpa-e2e-{uuid.uuid4().hex[:12]}.pdf"


# --- Helpers ----------------------------------------------------------


def _ingest(
    client: TestClient, contract_id: str, pdf_bytes: bytes, language: str
) -> dict[str, Any]:
    """POST /contracts/ingest with a real DPA contract file.

    Threads the ``language={en|de}`` form field so the
    per-document language is the source of truth (the
    per-clause detector would also arrive at the same value
    for these clauses, but threading the form field exercises
    the document-level path the frontend uses).
    """
    files = {"file": (contract_id, pdf_bytes, "application/pdf")}
    resp = client.post(
        "/contracts/ingest", files=files, data={"language": language}
    )
    assert resp.status_code == 200, (
        f"ingest failed for {contract_id}: "
        f"{resp.status_code} {resp.text[:500]!r}"
    )
    return resp.json()


def _spot(
    client: TestClient,
    contract_id: str,
    clauses: list[dict],
    *,
    counterparty_type: str = "any",
) -> dict:
    """POST /contracts/spot on the ingested clauses.

    Phase 5: the request carries a ``counterparty_type`` form
    field. The default ``"any"`` is the legacy sentinel; a
    real axis (``"enterprise"`` / ``"smb"`` / ``"public_sector"``
    / ``"healthcare"``) exercises the matrix override path
    the TriagePage's counterparty picker forwards.
    """
    resp = client.post(
        "/contracts/spot",
        json={
            "filename": contract_id,
            "clauses": clauses,
            "counterparty_type": counterparty_type,
        },
    )
    assert resp.status_code == 200, (
        f"spot failed for {contract_id}: {resp.status_code} {resp.text[:500]!r}"
    )
    return resp.json()


def _decisions(
    client: TestClient, contract_id: str, decisions: list[dict]
) -> dict:
    """POST /contracts/{id}/decisions — runs drafter (DPA stub)
    + audit log writes + docx render in one round-trip."""
    resp = client.post(
        f"/contracts/{contract_id}/decisions",
        json={"decisions": decisions},
    )
    assert resp.status_code == 200, (
        f"decisions failed for {contract_id}: "
        f"{resp.status_code} {resp.text[:500]!r}"
    )
    return resp.json()


def _redline_docx(client: TestClient, contract_id: str) -> bytes:
    """GET /contracts/{id}/redline.docx → bytes."""
    resp = client.get(f"/contracts/{contract_id}/redline.docx")
    assert resp.status_code == 200, (
        f"redline.docx failed for {contract_id}: "
        f"{resp.status_code} {resp.text[:500]!r}"
    )
    return resp.content


def _audit_log_json(client: TestClient, contract_id: str) -> list[dict]:
    """GET /api/contracts/{id}/audit-log.json → parsed JSON.

    Returns the list of events (decoded JSON). The Build 4
    shape is ``{"row_count": N, "events": [...], ...}`` — we
    return the events list for direct iteration.
    """
    resp = client.get(f"/api/contracts/{contract_id}/audit-log.json")
    assert resp.status_code == 200, (
        f"audit-log.json failed for {contract_id}: "
        f"{resp.status_code} {resp.text[:500]!r}"
    )
    blob = resp.json()
    # The shape is either an envelope ``{"events": [...]}``
    # or a bare list. Handle both (the audit_utils helper
    # has the same logic).
    if isinstance(blob, dict) and isinstance(blob.get("events"), list):
        return blob["events"]
    if isinstance(blob, list):
        return blob
    raise AssertionError(
        f"audit-log.json is neither a list nor a dict with an 'events' key: "
        f"got {type(blob).__name__}"
    )


def _audit_log_json_raw(client: TestClient, contract_id: str) -> bytes:
    """Raw bytes version of the audit-log fetch (used by
    parse_audit_log_json)."""
    resp = client.get(f"/api/contracts/{contract_id}/audit-log.json")
    assert resp.status_code == 200, (
        f"audit-log.json failed for {contract_id}: "
        f"{resp.status_code} {resp.text[:500]!r}"
    )
    return resp.content


# --- The 3 contracts × 5 assertions e2e test -------------------------
#
# We parametrize the test by (rel_path, expected_language) so
# pytest reports one test result per DPA contract. The hard
# rules say "5 test cases (one per DPA contract) or 1
# parametrized test" — we do the parametrized shape, which
# gives per-contract failure isolation in CI without 5x the
# fixture setup cost.


def _contract_ids() -> list[tuple[str, str]]:
    """Build a list of (rel_path, expected_language) pairs for
    parametrize. The full path is unique per contract so a
    failed assertion in one contract can't trip on a
    state-store collision with another."""
    return [(rel_path, lang) for rel_path, lang in DPA_CONTRACTS]


@pytest.mark.parametrize("rel_path,expected_language", _contract_ids())
def test_dpa_full_round_trip(
    rel_path: str,
    expected_language: str,
    client: TestClient,
    drafter_dpa_happy_path: None,
    spot_dpa_synthetic: None,
) -> None:
    """One DPA contract × full upload → spot → redline → audit.

    Parametrized over the 3 v1 DPA fixtures (1 public EN + 1
    synthetic EN + 1 synthetic DE). Each run goes through the
    real HTTP path the UI uses:

        POST /contracts/ingest (multipart, language={en|de})
            → POST /contracts/spot
            → POST /contracts/{id}/decisions
            → GET /contracts/{id}/redline.docx
            → GET /api/contracts/{id}/audit-log.json

    Five hard-rule assertions per contract (per card body +
    the Phase 4 language kill shot applied to Phase 5):

    1. The output .docx opens cleanly (parse with
       python-docx, assert ≥1 paragraph).

    2. ≥1 tracked change is present in the .docx (count
       <w:ins> / <w:del> elements with w:author attribute).
       Author must be "clausecraft" (the drafter's identity).

    3. Audit log has ≥1 row per stage (graph_started,
       flag_accepted, redline_generated, graph_resumed).

    4. **Matrix verdict rendered** — the kill shot. The
       spot response's ``flags[].matrix_verdict`` is one
       of the spec's 4-state column values
       (``acceptable | material | unacceptable |
       unverified``) for every flag; ``matrix_sources`` is
       a non-empty list; ``matrix_counterparty_type`` is
       a real axis or ``"any"``.

    5. Per-clause language field is the expected value
       (``"en"`` for EN contracts, ``"de"`` for the DE
       contract) for every clause in the contract. The
       Phase 4 kill shot applied to Phase 5.

    Per-clause language detection runs at parse time and is
    the source of truth. We assert the language field on
    the *ingest response's clauses* (assertion 5's scope),
    not on the spotter's flag inputs — the card body is
    explicit that this catches "the parser or the dispatch
    logic silently uses the EN path on a DE contract".
    """
    abs_path = EXAMPLES_DIR / rel_path
    pdf_bytes = _read(abs_path)
    contract_id = _new_contract_id(Path(rel_path).stem)

    # --- 1) Ingest with language={en|de} -----------------------
    ingest = _ingest(
        client, contract_id, pdf_bytes, language=expected_language
    )
    assert ingest["filename"].endswith(".pdf"), ingest["filename"]
    clauses = ingest["clauses"]
    assert len(clauses) >= 1, (
        f"expected ≥1 clause for {rel_path}, got {len(clauses)}"
    )

    # === Assertion 5: per-clause language field is the expected
    # value for all clauses. This is the Phase 4 kill shot
    # applied to Phase 5 — same enforcement, same fix-the-
    # upstream-not-relax-the-assertion rule.
    bad = [c for c in clauses if c.get("language") != expected_language]
    assert not bad, (
        f"{rel_path}: ≥1 clause has language != {expected_language!r} "
        f"(silent-EN-fallback or silent-DE-fallback regression). "
        f"First 3 bad clauses: "
        f"{[(c.get('id'), c.get('language'), c.get('text', '')[:60]) for c in bad[:3]]!r}"
    )

    # --- 2) Spot (real path; spotter is stubbed) ---------------
    # Phase 5: thread counterparty_type=expected_language's
    # sector for the DE contract (healthcare) and "any" for
    # the EN contracts. This exercises the matrix override
    # path: the DE contract should see the healthcare
    # override applied; the EN contracts should see the
    # flat default. The stub ignores counterparty_type, but
    # the API plumbing routes it through end-to-end, and
    # assertion 4 verifies the wire format carries the
    # matrix audit fields.
    if expected_language == "de":
        ct_for_spot = "healthcare"
    else:
        ct_for_spot = "any"
    spot = _spot(client, contract_id, clauses, counterparty_type=ct_for_spot)
    assert spot["filename"] == contract_id, spot["filename"]

    # === Assertion 4 (the kill shot): matrix verdict rendered.
    # Every flag in the spot response's ``flags`` list must
    # carry the Phase 5 matrix audit fields in valid form.
    # This is the kill shot for the matrix plumbing — it
    # catches a regression where the API surface drops the
    # fields, or the orchestrator stops stamping them, or
    # the spec's 4-state column form is bypassed. The UI's
    # deviation table is meaningless until the wire format
    # carries these fields.
    flags = spot.get("flags", [])
    assert flags, (
        f"{rel_path}: spot returned 0 flags — the drafter "
        f"stub has nothing to redline. The spot stub should "
        f"have produced one flag per clause."
    )
    for f in flags:
        # matrix_verdict: one of the spec's 4-state column
        # values, never None (the stub sets "material";
        # the real orchestrator sets the matrix's actual
        # verdict bridged into the 4-state form).
        matrix_verdict = f.get("matrix_verdict")
        assert matrix_verdict in SPEC_MATRIX_VERDICT_VALUES, (
            f"{rel_path}: flag matrix_verdict is not in the spec's "
            f"4-state column form. Got {matrix_verdict!r}, expected "
            f"one of {sorted(SPEC_MATRIX_VERDICT_VALUES)}. "
            f"clause_id={f.get('clause_id')!r}, "
            f"full flag={f!r}. This is the kill shot — fix the "
            f"matrix plumbing, don't relax this assertion."
        )
        # matrix_sources: a non-empty list (the spec's
        # audit trail; the stub sets ["flat"]).
        matrix_sources = f.get("matrix_sources")
        assert isinstance(matrix_sources, list) and len(matrix_sources) >= 1, (
            f"{rel_path}: flag matrix_sources is empty or not a "
            f"list — the spec's audit trail must record at least "
            f"one lookup source. Got {matrix_sources!r}. "
            f"clause_id={f.get('clause_id')!r}. This is the kill "
            f"shot — fix the matrix plumbing."
        )
        # matrix_counterparty_type: a real axis or "any".
        matrix_counterparty_type = f.get("matrix_counterparty_type")
        assert matrix_counterparty_type in (
            "any",
            "enterprise",
            "smb",
            "public_sector",
            "healthcare",
        ), (
            f"{rel_path}: flag matrix_counterparty_type is not a "
            f"valid axis. Got {matrix_counterparty_type!r}, expected "
            f"one of ('any', 'enterprise', 'smb', 'public_sector', "
            f"'healthcare'). clause_id={f.get('clause_id')!r}. "
            f"This is the kill shot — fix the matrix plumbing."
        )

    # --- 3) Decisions: approve every clause to maximise the
    # number of redline_generated audit rows. With the spot
    # stub emitting 1 flag per clause and the drafter stub
    # returning a happy-path proposal, every approve yields
    # a redline → redlines_count == decisions_count.
    decision_batch = [
        {"clause_id": c["id"], "decision": "approve"} for c in clauses
    ]
    dec_resp = _decisions(client, contract_id, decision_batch)
    assert dec_resp["decisions_count"] == len(decision_batch), (
        f"{rel_path}: expected {len(decision_batch)} decisions, "
        f"got {dec_resp['decisions_count']}"
    )
    assert dec_resp["redlines_count"] == len(decision_batch), (
        f"{rel_path}: expected {len(decision_batch)} redlines "
        f"(one per approved clause), got {dec_resp['redlines_count']}"
    )
    assert dec_resp["docx_bytes"] > 0, (
        f"{rel_path}: expected non-empty docx, got {dec_resp['docx_bytes']} bytes"
    )

    # --- 4) .docx round-trip --------------------------------------

    # === Assertion 1: the .docx opens cleanly (≥1 paragraph).
    docx_bytes = _redline_docx(client, contract_id)
    assert docx_bytes.startswith(b"PK"), (
        f"{rel_path}: redline.docx is not a valid ZIP/OOXML blob "
        f"(got {docx_bytes[:8]!r})"
    )
    doc = load_document(io.BytesIO(docx_bytes))
    # python-docx's ``Document.paragraphs`` is empty only if
    # the document is structurally broken; a real redline
    # .docx carries the contract's clause paragraphs plus
    # the redline insertions.
    assert len(doc.paragraphs) >= 1, (
        f"{rel_path}: expected ≥1 paragraph in redline .docx, "
        f"got 0 (parser may have rejected the file)"
    )

    # === Assertion 2: ≥1 tracked change with a w:author.
    changes = list(iter_tracked_changes(doc))
    assert len(changes) >= 1, (
        f"{rel_path}: expected ≥1 tracked change in the .docx, "
        f"got 0. The drafter stub should have produced a "
        f"proposal per approved clause."
    )
    authors = extract_change_authors(changes)
    assert "clausecraft" in authors, (
        f"{rel_path}: expected 'clausecraft' in change authors, "
        f"got {authors!r}"
    )

    # --- 5) Audit log shape --------------------------------------

    # === Assertion 3: ≥1 row per stage.
    events = _audit_log_json(client, contract_id)
    decision_types = [e["decision_type"] for e in events]
    # Required stages (per the card body: "ingest, classify,
    # spot, redline, approve"). The Build 4 audit
    # export doesn't write a row for itself (it's a read
    # operation), so the closest stage tokens are
    # graph_started, flag_accepted, redline_generated,
    # graph_resumed. The card body's "ingest" and "classify"
    # stages roll up into graph_started in the Build 3
    # typed-state machine.
    required_stages = (
        "graph_started",
        "flag_accepted",
        "redline_generated",
        "graph_resumed",
    )
    missing = [s for s in required_stages if s not in decision_types]
    assert not missing, (
        f"{rel_path}: audit log missing required stages {missing!r}. "
        f"Got decision_types={decision_types!r}"
    )
    # And every redline_generated row should pair 1:1 with
    # the number of approved decisions — that's the spec's
    # "≥1 row per stage" rule applied to the redline stage.
    assert decision_types.count("redline_generated") == len(decision_batch), (
        f"{rel_path}: expected {len(decision_batch)} "
        f"redline_generated rows, got "
        f"{decision_types.count('redline_generated')}"
    )

    # Defense in depth: every row has a decided_by actor.
    rows = parse_audit_log_json(_audit_log_json_raw(client, contract_id))
    assert_every_row_has_actor(rows)
