"""Phase 3 — unit tests for the audit-log response utilities.

The audit-log response comes back from Build 4's endpoints
in two flavours:

- **JSON**: a list (or a ``{"events": [...]}`` envelope) of
  audit rows. The unit tests below exercise the parser
  against hand-built JSON blobs to confirm the field
  decoding + the per-stage counting + the per-row actor
  assertion work as advertised.

- **PDF**: a ``reportlab``-rendered PDF. We do not unit-test
  the PDF parser here because (a) the spec does not require
  the unit-test layer to exercise the PDF path — that's the
  e2e test's job, against real Build 4 output — and
  (b) ``pypdf`` is not a v0 dependency (the project will
  add it as a dev dep when Build 4 lands). The unit test
  for the PDF helpers is intentionally omitted to avoid
  adding a dep just to test the dep.

What the unit tests cover
-------------------------

- :func:`parse_audit_log_json` — accepts both list and
  envelope shapes, raises on a malformed payload, decodes
  every field into a typed :class:`AuditLogRow`.
- :func:`count_rows_per_stage` — counts per decision_type.
- :func:`assert_every_stage_present` — passes when every
  expected stage is present, raises (with a clear message)
  when one is missing.
- :func:`assert_every_row_has_actor` — passes when every
  row has a non-empty ``decided_by``, raises (with the
  clause_id) when one doesn't.
"""

from __future__ import annotations

import json

import pytest

from tests.phase3.audit_utils import (  # noqa: F401
    EXPECTED_STAGES,
    AuditLogRow,
    assert_every_row_has_actor,
    assert_every_stage_present,
    count_rows_per_stage,
    parse_audit_log_json,
)


def _row(
    *,
    contract_id: str = "c-1",
    clause_id: str = "c1",
    decision_type: str = "flag_accepted",
    decided_by: str = "clausecraft-operator",
    payload: dict | None = None,
    decided_at: str = "2026-06-08T10:15:30Z",
) -> dict:
    """A canonical audit row for tests."""
    return {
        "contract_id": contract_id,
        "clause_id": clause_id,
        "decision_type": decision_type,
        "payload_json": payload or {},
        "decided_by": decided_by,
        "decided_at": decided_at,
    }


def test_parse_audit_log_json_accepts_list_shape():
    """Top-level list of rows."""
    blob = json.dumps([_row(), _row(clause_id="c2")]).encode("utf-8")
    rows = parse_audit_log_json(blob)
    assert len(rows) == 2
    assert rows[0].clause_id == "c1"
    assert rows[1].clause_id == "c2"


def test_parse_audit_log_json_accepts_envelope_shape():
    """The ``{"events": [...]}`` envelope shape."""
    blob = json.dumps({"events": [_row(), _row(clause_id="c2")]}).encode("utf-8")
    rows = parse_audit_log_json(blob)
    assert len(rows) == 2


def test_parse_audit_log_json_rejects_malformed_payload():
    """Anything that's neither a list nor an ``{"events": [...]}`` raises."""
    blob = json.dumps({"contract_id": "c-1"}).encode("utf-8")
    with pytest.raises(ValueError, match="neither a list nor a dict"):
        parse_audit_log_json(blob)


def test_parse_audit_log_json_rejects_missing_field():
    """A row missing ``decision_type`` raises with a clear message."""
    bad = {"contract_id": "c-1", "clause_id": "c1", "decided_by": "x", "decided_at": "2026-06-08T10:15:30Z"}
    blob = json.dumps([bad]).encode("utf-8")
    with pytest.raises(ValueError, match="missing required field 'decision_type'"):
        parse_audit_log_json(blob)


def test_count_rows_per_stage():
    """Per-stage counts sum to total row count."""
    rows = [
        AuditLogRow.from_dict(_row(decision_type="flag_accepted", clause_id="c1")),
        AuditLogRow.from_dict(_row(decision_type="flag_accepted", clause_id="c2")),
        AuditLogRow.from_dict(_row(decision_type="flag_rejected", clause_id="c3")),
    ]
    counts = count_rows_per_stage(rows)
    assert counts == {"flag_accepted": 2, "flag_rejected": 1}


def test_assert_every_stage_present_passes_for_complete_log():
    """A row per expected stage is enough to pass."""
    rows = [
        AuditLogRow.from_dict(_row(decision_type=stage, clause_id=f"c-{i}"))
        for i, stage in enumerate(EXPECTED_STAGES)
    ]
    assert_every_stage_present(rows)  # must not raise


def test_assert_every_stage_present_fails_with_clear_message():
    """A missing stage raises with a list of the missing tokens."""
    rows = [
        AuditLogRow.from_dict(_row(decision_type="flag_accepted", clause_id="c1")),
        AuditLogRow.from_dict(_row(decision_type="flag_rejected", clause_id="c2")),
        # Missing: graph_started, severity_edited, redline_generated,
        # redline_downloaded, graph_resumed.
    ]
    with pytest.raises(AssertionError, match="missing ≥1 row for these stages"):
        assert_every_stage_present(rows)


def test_assert_every_row_has_actor_passes_when_filled():
    """Every row's ``decided_by`` is non-empty."""
    rows = [AuditLogRow.from_dict(_row(decided_by="alice"))]
    assert_every_row_has_actor(rows)


def test_assert_every_row_has_actor_fails_when_empty():
    """A row with empty ``decided_by`` is flagged with its clause_id."""
    rows = [AuditLogRow.from_dict(_row(decided_by="", clause_id="c-bad"))]
    with pytest.raises(AssertionError, match="clause 'c-bad'"):
        assert_every_row_has_actor(rows)
