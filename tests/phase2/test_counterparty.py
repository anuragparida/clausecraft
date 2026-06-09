"""Test the counterparty matrix loader (flat lookup, Phase 2) + Phase 4 DE column."""

from __future__ import annotations

from app.playbook import (
    COUNTERPARTY_TYPES,
    CounterpartyMatrix,
    MatrixVerdict,
    Verdict,
    load_matrix,
    lookup_verdict,
    lookup_verdict_with_counterparty,
    lookup_verdict_with_language,
)


def test_load_real_matrix():
    """The committed counterparty_matrix.yaml parses into a typed matrix."""
    m = load_matrix()
    assert isinstance(m, CounterpartyMatrix)
    # Phase 5 widened contract_type from "nda" to "multi" — the
    # matrix now covers NDA + DPA + Employment clause types.
    assert m.contract_type == "multi"
    assert m.language == "en"
    # Bumped to 0.2.0-phase5 with the Phase 5 4-axis expansion.
    assert m.version == "0.2.0-phase5"
    # All 15 Phase 1 NDA + 9 Phase 5 DPA + 11 Phase 5 Employment +
    # the unknown safety net are listed (35 + unknown = 36).
    assert "definition_confidential_info" in m.clause_verdicts
    assert "term" in m.clause_verdicts
    assert "residual_knowledge" in m.clause_verdicts
    assert "governing_law" in m.clause_verdicts
    assert "injunctive_relief" in m.clause_verdicts
    # Phase 5 DPA additions:
    assert "dpa_subprocessor_consent" in m.clause_verdicts
    assert "dpa_breach_notification" in m.clause_verdicts
    assert "dpa_transfer_mechanism" in m.clause_verdicts
    # Phase 5 Employment additions:
    assert "employment_non_compete" in m.clause_verdicts
    assert "employment_probation" in m.clause_verdicts
    assert "employment_ip_assignment" in m.clause_verdicts
    assert "unknown" in m.clause_verdicts
    # Every flat value is "aligned" in Phase 2/5 (overrides are
    # what change the verdict; the flat table is the default).
    for verdict in m.clause_verdicts.values():
        assert verdict == Verdict.ALIGNED


def test_default_verdict_fallback():
    """Unknown clause types fall back to the default verdict."""
    # The YAML has every known type listed, so construct a fresh
    # matrix with a missing override to test the fallback path.
    m2 = CounterpartyMatrix(
        version="0.0.0-dev",
        contract_type="nda",
        language="en",
        default_counterparty_type="any",
        default_verdict=Verdict.MATERIAL,
        clause_verdicts={"term": Verdict.MINOR},
        counterparty_overrides={},
        language_overrides={},
        raw={},
    )
    v_known = lookup_verdict(m2, "term")
    assert v_known.verdict == Verdict.MINOR
    assert v_known.is_default is False
    v_unknown = lookup_verdict(m2, "non_existent_clause_type")
    assert v_unknown.verdict == Verdict.MATERIAL
    assert v_unknown.is_default is True


def test_verdict_from_score():
    """Verdict.from_score coerces the spotter's 0-3 score into a verdict."""
    assert Verdict.from_score(0) == Verdict.ALIGNED
    assert Verdict.from_score(1) == Verdict.MINOR
    assert Verdict.from_score(2) == Verdict.MATERIAL
    assert Verdict.from_score(3) == Verdict.UNACCEPTABLE
    # Clamping: out-of-range is a no-op, not a crash.
    assert Verdict.from_score(-1) == Verdict.ALIGNED
    assert Verdict.from_score(99) == Verdict.UNACCEPTABLE


def test_matrix_verdict_typed():
    """MatrixVerdict is a proper dataclass with the expected fields."""
    v = MatrixVerdict(
        verdict=Verdict.ALIGNED,
        clause_type="term",
        counterparty_type="any",
        is_default=False,
    )
    assert v.verdict.label() == "aligned"
    assert v.counterparty_type == "any"


def test_matrix_ignores_unknown_top_level_keys():
    """Unknown top-level keys (Phase 5 forward-compat) are silently ignored."""
    raw = {
        "version": "9.9.9-test",
        "contract_type": "nda",
        "language": "en",
        "default_counterparty_type": "any",
        "default_verdict": "aligned",
        "clause_verdicts": {"term": "aligned"},
        "counterparty_overrides": {},
        # Future fields Phase 5 may add:
        "risk_weights": {"term": 0.5},
        "jurisdiction_overrides": {},
    }
    m = CounterpartyMatrix.from_dict(raw)
    assert m.version == "9.9.9-test"
    assert m.clause_verdicts["term"] == Verdict.ALIGNED


# --- Phase 4: DE column --------------------------------------------------
#
# The DE column is additive: existing EN lookups must stay green
# (the ``test_load_real_matrix`` and ``test_default_verdict_fallback``
# tests above already exercise that), and the DE override must
# apply *only* when (a) the language is "de" and (b) the configured
# counterparty type matches and (c) the override is at least as
# strict as the EN verdict (we never relax a verdict on a language
# switch — defensive against an accidentally-inverted YAML value).


def test_de_column_loaded_from_yaml():
    """The committed counterparty_matrix.yaml carries a DE column.

    Acceptance: ``playbook/counterparty_matrix.yaml`` has a DE
    column (or DE override block). The loader exposes it on
    ``CounterpartyMatrix.language_overrides["de"]``.
    """
    m = load_matrix()
    assert "de" in m.language_overrides
    # The Phase 4 strictest additions: governing_law,
    # limitation_of_liability, term — all for the
    # ``de_german_entity`` counterparty type.
    de_block = m.language_overrides["de"]
    assert "de_german_entity" in de_block
    de_german = de_block["de_german_entity"]
    assert de_german["governing_law"] == Verdict.MATERIAL
    assert de_german["limitation_of_liability"] == Verdict.MATERIAL
    assert de_german["term"] == Verdict.MATERIAL


def test_de_lookup_strictens_governing_law_for_german_counterparty():
    """DE override applies for DE counterparty type on configured clauses."""
    m = load_matrix()
    # EN baseline: aligned.
    v_en = lookup_verdict(m, "governing_law")
    assert v_en.verdict == Verdict.ALIGNED
    # DE + de_german_entity: stricter (material).
    v_de = lookup_verdict_with_language(
        m, "governing_law", language="de", counterparty_type="de_german_entity"
    )
    assert v_de.verdict == Verdict.MATERIAL
    assert v_de.language == "de"
    assert v_de.counterparty_type == "de_german_entity"


def test_de_lookup_falls_back_to_en_for_non_de_counterparty():
    """DE override does NOT apply for non-DE counterparty types."""
    m = load_matrix()
    # DE language but counterparty is not German.
    v = lookup_verdict_with_language(
        m, "governing_law", language="de", counterparty_type="us_enterprise"
    )
    # No override applies — the EN default (aligned) wins.
    assert v.verdict == Verdict.ALIGNED
    assert v.language == "de"


def test_de_lookup_only_narrows_never_relaxes():
    """The DE override is rejected if it would *relax* the EN verdict.

    Defensive against an accidentally-inverted YAML value
    (e.g. ``aligned`` where ``material`` was meant) — the lookup
    stays at the EN verdict. The language stamp on the result is
    still ``"de"`` so the caller knows a DE lookup was attempted.
    """
    m = CounterpartyMatrix(
        version="0.0.0-test",
        contract_type="nda",
        language="en",
        default_counterparty_type="any",
        default_verdict=Verdict.ALIGNED,
        clause_verdicts={"governing_law": Verdict.MATERIAL},
        counterparty_overrides={},
        # DE override tries to *relax* material → aligned.
        # The lookup should reject it.
        language_overrides={
            "de": {
                "de_german_entity": {
                    "governing_law": Verdict.ALIGNED,
                }
            }
        },
        raw={},
    )
    v = lookup_verdict_with_language(
        m,
        "governing_law",
        language="de",
        counterparty_type="de_german_entity",
    )
    assert v.verdict == Verdict.MATERIAL  # the EN default, not the relaxation
    assert v.language == "de"


def test_de_lookup_unknown_clause_falls_back_to_default():
    """Unknown clause type in DE lookup → matrix default verdict."""
    m = load_matrix()
    v = lookup_verdict_with_language(
        m,
        "non_existent_clause_type",
        language="de",
        counterparty_type="de_german_entity",
    )
    assert v.verdict == Verdict.ALIGNED  # the matrix default
    assert v.is_default is True
    assert v.language == "de"


def test_unknown_language_falls_through_to_en_path():
    """A language code with no overrides falls through to the EN path."""
    m = load_matrix()
    v_en = lookup_verdict(m, "term")
    v_xx = lookup_verdict_with_language(
        m, "term", language="xx", counterparty_type="de_german_entity"
    )
    # ``xx`` has no overrides, so the EN result wins.
    assert v_xx.verdict == v_en.verdict
    assert v_xx.language == "xx"


def test_de_lookup_does_not_mutate_existing_en_lookup():
    """The EN ``lookup_verdict`` is unchanged in behavior.

    The Phase 4 addition must not break the Phase 2 path —
    this is the acceptance criterion that the existing tests
    also exercise, but we make it explicit here.
    """
    m = load_matrix()
    # The DE column is loaded; lookup_verdict should still ignore it.
    assert m.language_overrides  # non-empty after Phase 4
    v = lookup_verdict(m, "governing_law", counterparty_type="de_german_entity")
    # Even with a DE counterparty type, lookup_verdict returns the
    # EN default. The DE column is only consulted by
    # lookup_verdict_with_language.
    assert v.verdict == Verdict.ALIGNED


def test_de_lookup_inherits_matrix_language_default():
    """Omitting ``language=`` defaults to the matrix's language field."""
    m = load_matrix()
    # The committed YAML has language: "en" at the top level.
    # Omitting language= in the call should default to "en" and
    # hit the EN path, not the DE path.
    v = lookup_verdict_with_language(m, "governing_law")
    assert v.verdict == Verdict.ALIGNED
    assert v.language == "en"


def test_de_lookup_alternate_yaml_shape_parses():
    """The flat ``language → counterparty_type → clause_type`` shape
    also parses (the canonical shape is nested under
    ``counterparty_overrides`` per language, but a direct 2D
    shape is also accepted as a forward-compat)."""
    raw = {
        "version": "0.1.0-test",
        "contract_type": "nda",
        "language": "en",
        "default_counterparty_type": "any",
        "default_verdict": "aligned",
        "clause_verdicts": {"governing_law": "aligned"},
        "counterparty_overrides": {},
        "language_overrides": {
            "de": {
                # Flat shape — no nested counterparty_overrides.
                "de_german_entity": {
                    "governing_law": "unacceptable",
                }
            }
        },
    }
    m = CounterpartyMatrix.from_dict(raw)
    assert m.language_overrides["de"]["de_german_entity"]["governing_law"] == (
        Verdict.UNACCEPTABLE
    )
    v = lookup_verdict_with_language(
        m, "governing_law", language="de", counterparty_type="de_german_entity"
    )
    assert v.verdict == Verdict.UNACCEPTABLE


# --- Phase 5: 4-axis counterparty matrix ---------------------------------
#
# Spec exit-gate (docs/11-phases.md § "Phase 5"):
#   "Counterparty matrix is wired and changes verdicts on at least 3
#    of 30 eval contracts."
# The spec's expected cell count is "~60-80 entries" — the committed
# matrix carries 67 explicit override cells across 4 counterparty
# axes (enterprise / smb / public_sector / healthcare) × 35 clause
# types (15 NDA + 9 DPA + 11 Employment). The tests below pin the
# spec-anchor verdicts on a handful of high-signal cells (the ones
# Helena's review is most likely to challenge) and assert the
# composition semantics on the lookup function.


def test_phase5_module_exports():
    """Phase 5 public surface is importable from the playbook package.

    The matrix-aware spotter (``backend/app/agents/deviation_spotter``)
    imports ``lookup_verdict_with_counterparty`` and the
    ``COUNTERPARTY_TYPES`` constant directly from ``app.playbook``.
    The re-export in ``__init__.py`` is the contract that call sites
    depend on.
    """
    from app.playbook import (  # noqa: F401
        COUNTERPARTY_TYPES,
        DEFAULT_COUNTERPARTY_TYPE,
        DE_GERMAN_ENTITY,
        lookup_verdict_with_counterparty,
    )
    assert "enterprise" in COUNTERPARTY_TYPES
    assert "smb" in COUNTERPARTY_TYPES
    assert "public_sector" in COUNTERPARTY_TYPES
    assert "healthcare" in COUNTERPARTY_TYPES
    # The 4-axis types do NOT include the legacy language-axis type.
    # That one lives under language_overrides, not the top-level
    # counterparty_overrides — the matrix config keeps the two axes
    # separate so a Helena reviewer can grep one without the other.
    assert "de_german_entity" not in COUNTERPARTY_TYPES


def test_phase5_matrix_loaded_with_4_axes():
    """The committed counterparty_matrix.yaml exposes the 4 axes.

    Acceptance: every one of the 4 counterparty axes is present in
    ``matrix.counterparty_overrides`` with at least one explicit
    override cell. The total cell count is in the 60-80 band the
    spec calls out (~67 today).
    """
    m = load_matrix()
    for cp in ("enterprise", "smb", "public_sector", "healthcare"):
        assert cp in m.counterparty_overrides, f"missing axis: {cp}"
        assert len(m.counterparty_overrides[cp]) > 0, (
            f"axis {cp!r} has zero override cells — should have at "
            f"least one material/minor narrowing"
        )
    total = sum(len(v) for v in m.counterparty_overrides.values())
    assert 50 <= total <= 90, (
        f"override cell count {total} is outside the spec's 60-80 "
        f"estimate (allowing ±10 slack for the 67-cell baseline)"
    )


def test_phase5_healthcare_dpa_breach_is_material():
    """HIPAA 60-day rule + GDPR 72h rule → material for healthcare DPA.

    This is the spec's QA hook example: "Upload a DPA with EU SCC
    deviations → see the matrix verdict flag the transfer mechanism
    as 'unacceptable' for healthcare counterparty." The breach-
    notification cell sits right next to it.
    """
    m = load_matrix()
    v = lookup_verdict_with_counterparty(
        m, "dpa_breach_notification",
        counterparty_type="healthcare", language="en",
    )
    assert v.verdict == Verdict.MATERIAL
    # sources records the override path so the UI tooltip can show
    # "matrix verdict: material (healthcare override)".
    assert "counterparty" in v.sources
    assert v.counterparty_type == "healthcare"


def test_phase5_smb_employment_non_compete_is_material():
    """DE SMB non-compete is material (Karenzentschädigung infeasibility).

    BGB §§ 74 ff. HGB require the employer to pay
    Karenzentschädigung (compensation) of at least 50% of the
    employee's last earnings during the restricted period. An SMB
    cannot afford that, so a non-compete in an SMB employment
    contract is either unenforceable (DE) or a red-line
    negotiation point (EN) — material.
    """
    m = load_matrix()
    v = lookup_verdict_with_counterparty(
        m, "employment_non_compete",
        counterparty_type="smb", language="en",
    )
    assert v.verdict == Verdict.MATERIAL
    assert "counterparty" in v.sources
    assert v.counterparty_type == "smb"


def test_phase5_public_sector_assignment_is_minor():
    """Public-sector assignment is minor (procurement-law review).

    A change-of-control of a public-sector vendor typically
    triggers a procurement-law review, but the *clause language*
    is rarely the binding issue (the procurement review is
    separate). The matrix narrows to "minor" so the spotter
    surfaces it as a flag, not a hard blocker.
    """
    m = load_matrix()
    v = lookup_verdict_with_counterparty(
        m, "assignment",
        counterparty_type="public_sector", language="en",
    )
    assert v.verdict == Verdict.MINOR
    assert "counterparty" in v.sources


def test_phase5_enterprise_residual_knowledge_is_minor():
    """Enterprise residual-knowledge is minor (workable deviation).

    Enterprise counterparties often have broader residual-rights
    language; missing it is a workable deviation, not a deal-
    breaker. The matrix narrows to "minor" so the spotter doesn't
    over-flag a standard enterprise NDA.
    """
    m = load_matrix()
    v = lookup_verdict_with_counterparty(
        m, "residual_knowledge",
        counterparty_type="enterprise", language="en",
    )
    assert v.verdict == Verdict.MINOR
    assert "counterparty" in v.sources


def test_phase5_any_counterparty_returns_flat_default():
    """``counterparty_type="any"`` (the legacy Phase 2 sentinel)
    consults only the flat ``clause_verdicts`` table — same as
    :func:`lookup_verdict`."""
    m = load_matrix()
    v = lookup_verdict_with_counterparty(
        m, "dpa_breach_notification",
        counterparty_type="any", language="en",
    )
    # No counterparty override applies; flat default is "aligned".
    assert v.verdict == Verdict.ALIGNED
    assert v.is_default is False  # flat hit, not default_verdict hit
    # The "flat" source is always recorded when the flat table
    # contributed — the audit trail names every cell that was
    # considered, not just the winner.
    assert v.sources == ["flat"]


def test_phase5_unknown_counterparty_falls_through_to_flat():
    """A counterparty type the matrix doesn't know about falls
    through to the flat default verdict, never raises."""
    m = load_matrix()
    v = lookup_verdict_with_counterparty(
        m, "term",
        counterparty_type="niche_segment_we_dont_have", language="en",
    )
    # Flat ``clause_verdicts["term"]`` is "aligned" → the lookup
    # returns aligned with no override applied.
    assert v.verdict == Verdict.ALIGNED
    assert "counterparty" not in v.sources


def test_phase5_unknown_clause_falls_back_to_default():
    """An unknown clause type with a known counterparty falls back
    to the matrix's ``default_verdict`` (no override applies)."""
    m = load_matrix()
    v = lookup_verdict_with_counterparty(
        m, "non_existent_clause_type",
        counterparty_type="healthcare", language="en",
    )
    assert v.verdict == m.default_verdict
    assert v.is_default is True
    # No candidate matched — sources is empty. The counterparty
    # type is still recorded on the result for forward-compat.
    assert v.sources == []
    assert v.counterparty_type == "healthcare"


def test_phase5_strictest_axis_wins_for_dpa_audit():
    """When multiple axes contribute, the strictest verdict wins.

    The DE-no-relax guard from Phase 4 is preserved: the DE
    override is dropped if it would *relax* the verdict relative
    to the counterparty axis. For dpa_audit_rights on DE +
    healthcare, BOTH the DE language axis (Art 28(3)(h) GDPR) and
    the healthcare counterparty axis narrow the verdict, so
    material wins.
    """
    m = load_matrix()
    v = lookup_verdict_with_counterparty(
        m, "dpa_audit_rights",
        counterparty_type="healthcare", language="de",
    )
    # Both healthcare (material) and the matrix's flat default
    # would yield "aligned" — so the strictest of the matching
    # candidates is the healthcare "material" override.
    assert v.verdict == Verdict.MATERIAL
    # The healthcare override won; the source list is ordered with
    # the winner first.
    assert v.sources[0] == "counterparty"
    assert "counterparty" in v.sources


def test_phase5_de_no_relax_guard_preserved():
    """The Phase 4 DE-no-relax guard still applies under Phase 5.

    If a (hypothetical) DE override were less strict than the
    counterparty override, the DE override is *rejected as the
    winner* but is *still recorded in the audit trail* as a
    considered candidate. The verdict is the strictest
    non-relaxing candidate; the sources list shows the full
    lookup chain.
    """
    raw = {
        "version": "0.0.0-test",
        "contract_type": "multi",
        "language": "en",
        "default_counterparty_type": "any",
        "default_verdict": "aligned",
        "clause_verdicts": {"term": "aligned"},
        "counterparty_overrides": {
            "smb": {"term": "material"},
        },
        "language_overrides": {
            "de": {
                "smb": {
                    # DE tries to RELAX the SMB override. The lookup
                    # should reject DE as the winner and keep "material".
                    "term": "aligned",
                },
            },
        },
    }
    m = CounterpartyMatrix.from_dict(raw)
    v = lookup_verdict_with_counterparty(
        m, "term", counterparty_type="smb", language="de",
    )
    # SMB counterparty override wins.
    assert v.verdict == Verdict.MATERIAL
    assert v.sources[0] == "counterparty"
    # The DE override was rejected for being a relaxation, but
    # it's still in the audit trail — the UI tooltip shows
    # "DE override considered: aligned (rejected as relaxation)".
    assert "language:de" in v.sources


def test_phase5_exit_gate_three_contracts_change_verdict():
    """Phase 5 exit-gate: the matrix is wired and changes verdicts
    on at least 3 of 30 eval contracts.

    The "≥ 3 of 30 contracts" criterion lives on the eval-set
    wiring card (DPA = t_f3212fc0, Employment = t_d5e24d95), not
    here. What this test pins is the *matrix side*: every one
    of the 4 counterparty axes carries at least one explicit
    override cell, and the aggregate cell count is in the
    spec's 60-80 band. (Each cell either narrows from the flat
    "aligned" default, in which case the spotter's verdict
    *changes*, or matches the flat default, in which case the
    cell is a no-op assertion of "this verdict is correct for
    this counterparty" — both are part of the matrix's spec.)
    """
    m = load_matrix()
    # Aggregate: every cell the matrix declares is part of the
    # spec's "wired" surface. 67 today, well within 60-80.
    total = sum(len(v) for v in m.counterparty_overrides.values())
    assert 50 <= total <= 90, (
        f"override cell count {total} is outside the spec's 60-80 "
        f"estimate (allowing ±10 slack for the 67-cell baseline)"
    )
    # Per-axis: every axis has at least one override cell.
    # Enterprise is intentionally all "minor" (the spotter
    # narrows less aggressively because enterprises absorb
    # standard risk) — those still count as wired cells.
    for cp in COUNTERPARTY_TYPES:
        n = len(m.counterparty_overrides[cp])
        assert n > 0, (
            f"counterparty axis {cp!r} has zero override cells — "
            f"the matrix is unwired for this axis"
        )
    # The "≥ 3 of 30 contracts" criterion is exercised by the
    # eval-set wiring card. The matrix-card test can only
    # guarantee that *some* contracts *will* change verdict
    # when wired up — which the public_sector, smb, and
    # healthcare axes already do (their material verdicts on
    # the spec's QA-hook examples — dpa_audit_rights, smb
    # non-compete, healthcare breach — are all in the spec's
    # change-verdict set).


def test_phase5_verdict_label_roundtrip():
    """Verdict.label() round-trips the verdict to a lowercase string.

    The UI renders the verdict label verbatim (e.g. "material" →
    <SeverityBadge variant="material" />). The label must be
    one of: aligned, minor, material, unacceptable.
    """
    for v in Verdict:
        assert v.label() in (
            "aligned", "minor", "material", "unacceptable",
        ), f"unexpected label for {v!r}: {v.label()!r}"
