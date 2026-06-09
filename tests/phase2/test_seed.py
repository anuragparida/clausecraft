"""Test the idempotent seeder against the live Postgres container.

These tests use a dedicated playbook root and version so they
don't interfere with the Phase 2 dev data. Each test creates
its own versioned playbook (e.g. ``test-<uuid>``), seeds it,
then drops the playbook at the end.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db import get_session_factory
from app.playbook.seed import seed_all

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINES = REPO_ROOT / "playbook" / "baselines"


def _unique_version() -> str:
    """Per-test version so parallel test runs don't clobber each other."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def cleanup_playbook():
    """Drop the test playbook rows after the test, even on failure.

    Also disposes the asyncpg connection pool so the next test gets a
    fresh session factory. Without this, the pytest-asyncio session
    loop reuses a connection that has seen the previous test's
    transaction state and the next ``factory()`` call can attach to
    a connection that has been reset mid-flight, surfacing a
    ``PoolError``/``InterfaceError`` from asyncpg. The pool dispose
    is a no-op when the pool is already empty, so it is safe to
    call after every test.
    """
    yield

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "DELETE FROM playbook_versions WHERE version LIKE 'test-%'"
            )
        )
        await session.commit()
    # Force a fresh pool for the next test. The session factory is
    # cached at import time, so we dispose the underlying engine
    # directly; the next ``get_session_factory()`` rebuilds the pool.
    from app.db import get_engine
    await get_engine().dispose()


@pytest.mark.asyncio
async def test_seed_is_idempotent(cleanup_playbook):
    """Seeding the same data twice produces no duplicate rows."""
    version = _unique_version()
    # First seed
    summaries1 = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="en",
    )
    assert len(summaries1) == 1
    assert summaries1[0].clause_count == 5
    assert summaries1[0].contract_type == "nda"
    assert summaries1[0].language == "en"
    # Count rows after the first seed
    factory = get_session_factory()
    async with factory() as session:
        count1 = await session.scalar(
            text(
                "SELECT COUNT(*) FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
    assert count1 == 5
    # Second seed — same data, same version
    summaries2 = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="en",
    )
    assert summaries2[0].clause_count == 5
    async with factory() as session:
        count2 = await session.scalar(
            text(
                "SELECT COUNT(*) FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
    assert count2 == 5, "second seed created duplicate rows!"


@pytest.mark.asyncio
async def test_seed_inserts_provenance(cleanup_playbook):
    """Every clause has a source_url, retrieval_date, and license."""
    version = _unique_version()
    await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="en",
    )
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(
            text(
                "SELECT c.clause_id, c.source_url, c.retrieval_date, c.license "
                "FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
        rows = list(rows.mappings())
    assert len(rows) == 5
    for r in rows:
        assert r["source_url"].startswith("http")
        assert r["retrieval_date"] is not None
        assert r["license"]


@pytest.mark.asyncio
async def test_seed_rejects_invalid_clause_type(tmp_path, cleanup_playbook):
    """A YAML with a bad clause type fails the seed loudly."""
    bad = tmp_path / "baselines"
    bad.mkdir()
    (bad / "nda-en").mkdir()
    (bad / "nda-en" / "bad.yaml").write_text(
        """\
clause_id: bad-clause
type: nonsense_type_that_does_not_exist
language: en
title: Bad Clause
text: This is a clause with an invalid type field.
source_url: https://example.com
retrieval_date: 2026-01-01
license: CC0-1.0
"""
    )
    with pytest.raises(ValueError, match="not a valid ClauseType"):
        await seed_all(playbook_root=tmp_path, version="0.0.0-badtest")


# ---------------------------------------------------------------------------
# DE baselines (Phase 4 trunk card t_c714cf94) — lock the DE coverage in CI.
# ---------------------------------------------------------------------------

DE_EXPECTED_TYPES = {
    "definition_confidential_info",
    "term",
    "governing_law",
    "injunctive_relief",
    "residual_knowledge",
}

# Expected source-URL host per clause_type. Each baseline must come
# from a real public German (or, for the residual-knowledge carve-out
# which is structurally identical under § 3 GeschGehG, Austrian)
# source, and the set of hosts must be diverse enough that no single
# document is doing the work of two clause types. The diversity
# requirement is the card's "5 real-public-source DE baselines" rule
# implemented as a hard assertion.
DE_EXPECTED_HOSTS = {
    "definition_confidential_info": "www.gesetze-im-internet.de",  # GeschGehG § 2 Nr. 1 (BMJ/BfJ)
    "term": "www.dihk.de",                                          # DIHK-Muster Ziff. 8
    "governing_law": "www.ihk-muenchen.de",                         # IHK-München-Muster Ziff. 8
    "injunctive_relief": "www.ihk.de",                             # IHK-Hessen-Muster Ziff. 6
    "residual_knowledge": "www.wko.at",                            # WKO-FEEI-Muster Art. 2
}


@pytest.mark.asyncio
async def test_seed_de_baselines_load(cleanup_playbook):
    """All 5 DE baselines parse and seed into the store with real provenance.

    This locks the Phase 4 DE trunk card (t_c714cf94) so a future
    change to ``playbook/baselines/nda-de/`` cannot silently drop a
    clause type, swap a source for a non-public one, or collapse the
    source spread back to a single document.
    """
    version = _unique_version()
    summaries = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="de",
    )
    assert len(summaries) == 1
    assert summaries[0].contract_type == "nda"
    assert summaries[0].language == "de"
    assert summaries[0].clause_count == 5

    factory = get_session_factory()
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT c.clause_id, c.type, c.source_url, "
                        "c.retrieval_date, c.license, c.language "
                        "FROM playbook_clauses c "
                        "JOIN playbook_versions v ON v.id = c.playbook_id "
                        "WHERE v.version = :v"
                    ),
                    {"v": version},
                )
            ).mappings()
        )
    assert len(rows) == 5, f"expected 5 DE baselines, got {len(rows)}"
    seen_types: set[str] = set()
    seen_hosts: set[str] = set()
    for r in rows:
        # Every row must be a DE baseline with a valid type and a real URL.
        assert r["language"] == "de"
        assert r["type"] in DE_EXPECTED_TYPES
        assert r["source_url"].startswith("http")
        assert r["retrieval_date"] is not None
        assert r["license"]
        seen_types.add(r["type"])
        # Track the source host so we can assert provenance is spread
        # across multiple distinct public sources (the card's
        # "5 real-public-source DE baselines" rule).
        host = r["source_url"].split("/")[2] if "/" in r["source_url"] else ""
        seen_hosts.add(host)
        # Per-clause-type host check: the expected host map pins each
        # baseline to a specific public source. Any change to a host
        # must be a conscious decision, not a silent swap.
        expected_host = DE_EXPECTED_HOSTS[r["type"]]
        assert host == expected_host, (
            f"DE baseline {r['clause_id']} (type={r['type']}) is hosted at "
            f"{host!r}, expected {expected_host!r}. Update DE_EXPECTED_HOSTS "
            f"if the source change is intentional."
        )
    assert seen_types == DE_EXPECTED_TYPES
    # The 5 baselines must come from 5 distinct public sources — no
    # single document covers more than one clause type.
    assert len({r["source_url"] for r in rows}) == 5
    assert len(seen_hosts) == 5, (
        f"DE baselines should come from 5 distinct hosts (one per "
        f"clause type); got {len(seen_hosts)}: {seen_hosts}"
    )


@pytest.mark.asyncio
async def test_seed_de_baselines_idempotent(cleanup_playbook):
    """Seeding the DE baselines twice produces no duplicate rows.

    The seeder is documented as idempotent at the row level; the
    DE coverage is no exception. The (playbook_id, clause_id) PK
    should reject any second insert.
    """
    version = _unique_version()
    first = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="de",
    )
    assert first[0].clause_count == 5
    factory = get_session_factory()
    async with factory() as session:
        count1 = await session.scalar(
            text(
                "SELECT COUNT(*) FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
    assert count1 == 5
    second = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="nda",
        language="de",
    )
    assert second[0].clause_count == 5
    async with factory() as session:
        count2 = await session.scalar(
            text(
                "SELECT COUNT(*) FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
    assert count2 == 5, "second DE seed created duplicate rows!"


# ---------------------------------------------------------------------------
# EN DPA baselines (Phase 5 card t_45151f58) — lock the 5-baseline EN DPA
# coverage in CI. Mirrors the DE pattern: 5 baselines, 5 distinct source
# URLs, 5 distinct clause types covering the controller/processor +
# sub-processor + transfer-mechanism + breach + audit spine of an Art 28
# GDPR DPA.
#
# Note: the "no two from the same host" rule is intentionally relaxed
# here (vs. the DE NDA test, which asserts 5 distinct hosts). The EN DPA
# spread uses 2 GDPR-statute articles (Art 28 + Art 33) which are
# legitimately hosted together on gdpr-info.eu; the spec's "no single
# document covers more than one clause type" rule still holds because
# Art 28 and Art 33 are different articles, different content. The
# DPA_EN_EXPECTED_HOSTS map below documents the canonical host per
# clause type; assertions check URL+content (per-clause-type) and
# distinct URLs (cross-clause), not distinct hosts.
# ---------------------------------------------------------------------------

DPA_EN_EXPECTED_TYPES = {
    "dpa_controller_processor_designation",
    "dpa_subprocessor_consent",
    "dpa_transfer_mechanism",
    "dpa_breach_notification",
    "dpa_audit_rights",
}

# Expected source-URL host per clause_type. Two of the five (Art 28
# GDPR and Art 33 GDPR) share the gdpr-info.eu host because the
# consolidated GDPR text is published there as a single document;
# the spec's diversity rule is "no single document covers more than
# one clause type", which is satisfied (Art 28 ≠ Art 33).
DPA_EN_EXPECTED_HOSTS = {
    "dpa_controller_processor_designation": "gdpr-info.eu",                            # Art 28 GDPR (statute)
    "dpa_subprocessor_consent": "www.edpb.europa.eu",                                 # EDPB Guidelines 07/2020 § 6
    "dpa_transfer_mechanism": "eur-lex.europa.eu",                                    # EU SCCs 2021/914 Module Two
    "dpa_breach_notification": "gdpr-info.eu",                                        # Art 33 GDPR (statute)
    "dpa_audit_rights": "www.datenschutzkonferenz-online.de",                         # DSK Kurzpapier Nr. 13
}


@pytest.mark.asyncio
async def test_seed_dpa_en_baselines_load(cleanup_playbook):
    """All 5 EN DPA baselines parse and seed into the store with real provenance.

    This locks the Phase 5 card t_45151f58 so a future change to
    ``playbook/baselines/dpa-en/`` cannot silently drop a clause
    type, swap a source for a non-public one, or collapse the
    source spread back to a single document.
    """
    version = _unique_version()
    summaries = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="dpa",
        language="en",
    )
    assert len(summaries) == 1
    assert summaries[0].contract_type == "dpa"
    assert summaries[0].language == "en"
    assert summaries[0].clause_count == 5

    factory = get_session_factory()
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT c.clause_id, c.type, c.source_url, "
                        "c.retrieval_date, c.license, c.language "
                        "FROM playbook_clauses c "
                        "JOIN playbook_versions v ON v.id = c.playbook_id "
                        "WHERE v.version = :v"
                    ),
                    {"v": version},
                )
            ).mappings()
        )
    assert len(rows) == 5, f"expected 5 EN DPA baselines, got {len(rows)}"
    seen_types: set[str] = set()
    seen_hosts: set[str] = set()
    for r in rows:
        # Every row must be an EN DPA baseline with a valid type and a real URL.
        assert r["language"] == "en"
        assert r["type"] in DPA_EN_EXPECTED_TYPES, (
            f"unexpected DPA-EN type {r['type']!r}; expected one of "
            f"{sorted(DPA_EN_EXPECTED_TYPES)}"
        )
        assert r["source_url"].startswith("http")
        assert r["retrieval_date"] is not None
        assert r["license"]
        seen_types.add(r["type"])
        # Track the source host so we can assert provenance is spread
        # across multiple distinct public sources.
        host = r["source_url"].split("/")[2] if "/" in r["source_url"] else ""
        seen_hosts.add(host)
        # Per-clause-type host check: the expected host map pins each
        # baseline to a specific public source.
        expected_host = DPA_EN_EXPECTED_HOSTS[r["type"]]
        assert host == expected_host, (
            f"EN DPA baseline {r['clause_id']} (type={r['type']}) is "
            f"hosted at {host!r}, expected {expected_host!r}. Update "
            f"DPA_EN_EXPECTED_HOSTS if the source change is intentional."
        )
    assert seen_types == DPA_EN_EXPECTED_TYPES
    # The 5 baselines must come from 5 distinct source URLs — no
    # single document covers more than one clause type. (Hosts may
    # repeat: Art 28 and Art 33 GDPR are both hosted on
    # gdpr-info.eu.)
    assert len({r["source_url"] for r in rows}) == 5
    # Source-spread cross-check: the union of clause types is the
    # full DPA-EN spine (designation + sub-processor + transfer +
    # breach + audit).
    assert len(seen_hosts) >= 4, (
        f"EN DPA baselines should come from at least 4 distinct "
        f"hosts (Art 28+33 share gdpr-info.eu); got {len(seen_hosts)}: "
        f"{seen_hosts}"
    )


@pytest.mark.asyncio
async def test_seed_dpa_en_baselines_idempotent(cleanup_playbook):
    """Re-seeding the EN DPA baselines produces no duplicate rows.

    The seeder is documented as idempotent at the row level; the
    EN DPA coverage is no exception. The (playbook_id, clause_id)
    PK should reject any second insert.
    """
    version = _unique_version()
    first = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="dpa",
        language="en",
    )
    assert first[0].clause_count == 5
    factory = get_session_factory()
    async with factory() as session:
        count1 = await session.scalar(
            text(
                "SELECT COUNT(*) FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
    assert count1 == 5
    second = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="dpa",
        language="en",
    )
    assert second[0].clause_count == 5
    async with factory() as session:
        count2 = await session.scalar(
            text(
                "SELECT COUNT(*) FROM playbook_clauses c "
                "JOIN playbook_versions v ON v.id = c.playbook_id "
                "WHERE v.version = :v"
            ),
            {"v": version},
        )
    assert count2 == 5, "second EN DPA seed created duplicate rows!"

