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
# DE Employment baselines (Phase 5 card t_84896561) — lock the 5-baseline
# DE Employment coverage in CI. Mirrors the EN Employment pattern
# (5 baselines) but pivots to the DE source spread (4 × gesetze-im-
# internet.de + 1 × ihk.de).
#
# Source spread (2 distinct hosts, 5 distinct URLs):
#   - www.gesetze-im-internet.de (4 × Bundesgesetzestexte, each
#     pinned to a different statute: BGB § 622 notice, BGB § 611a
#     Abs. 2 remuneration, BUrlG § 3 leave, BGB § 626 termination
#     for cause)
#   - www.ihk.de (1 × IHK Musterarbeitsvertrag, § 12/§ 13 post-
#     employment confidentiality + secondary-employment restriction
#     as the DE non-solicitation anchor)
#
# The "no single document covers more than one clause type" rule
# holds: the four gesetze-im-internet.de pages are four different
# statutes (BGB § 622 ≠ BGB § 611a ≠ BUrlG § 3 ≠ BGB § 626), even
# though they share the same amtliche domain. The IHK Mustervertrag
# is a different host, different document kind. This mirrors the
# EN Employment card's "4 × GOV.UK + 1 × ABA" pattern and the
# DE DPA card's "EUR-Lex co-host + multiple statutes" pattern.
# ---------------------------------------------------------------------------

EMPLOYMENT_DE_EXPECTED_TYPES = {
    "employment_notice_period",
    "employment_remuneration",
    "employment_leave_entitlements",
    "employment_termination_for_cause",
    "employment_non_solicitation",
}

# Expected source-URL host per clause_type. The four gesetze-im-
# internet.de pages all share the www.gesetze-im-internet.de
# host because they are four distinct Bundesgesetzestexte (the
# same way the DE DPA spread uses 3 distinct EUR-Lex documents).
# The spec's diversity rule is "no single document covers more
# than one clause type", which is satisfied (4 different statutes,
# 4 different clause types).
EMPLOYMENT_DE_EXPECTED_HOSTS = {
    "employment_notice_period": "www.gesetze-im-internet.de",              # § 622 BGB — Kündigungsfristen
    "employment_remuneration": "www.gesetze-im-internet.de",               # § 611a Abs. 2 BGB — Vergütungspflicht
    "employment_leave_entitlements": "www.gesetze-im-internet.de",         # § 3 BUrlG — Dauer des Urlaubs
    "employment_termination_for_cause": "www.gesetze-im-internet.de",      # § 626 BGB — Fristlose Kündigung
    "employment_non_solicitation": "www.ihk.de",                           # IHK Musterarbeitsvertrag § 12/§ 13
}


@pytest.mark.asyncio
async def test_seed_employment_de_baselines_load(cleanup_playbook):
    """All 5 DE Employment baselines parse and seed into the store with real provenance.

    This locks the Phase 5 card t_84896561 so a future change to
    ``playbook/baselines/employment-de/`` cannot silently drop a
    clause type, swap a source for a non-public one, or collapse
    the source spread back to a single document.
    """
    version = _unique_version()
    summaries = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="employment",
        language="de",
    )
    assert len(summaries) == 1
    assert summaries[0].contract_type == "employment"
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
    assert len(rows) == 5, f"expected 5 DE Employment baselines, got {len(rows)}"
    seen_types: set[str] = set()
    seen_hosts: set[str] = set()
    for r in rows:
        # Every row must be a DE Employment baseline with a valid type and a real URL.
        assert r["language"] == "de"
        assert r["type"] in EMPLOYMENT_DE_EXPECTED_TYPES, (
            f"unexpected Employment-DE type {r['type']!r}; expected one of "
            f"{sorted(EMPLOYMENT_DE_EXPECTED_TYPES)}"
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
        expected_host = EMPLOYMENT_DE_EXPECTED_HOSTS[r["type"]]
        assert host == expected_host, (
            f"DE Employment baseline {r['clause_id']} (type={r['type']}) is "
            f"hosted at {host!r}, expected {expected_host!r}. Update "
            f"EMPLOYMENT_DE_EXPECTED_HOSTS if the source change is intentional."
        )
    assert seen_types == EMPLOYMENT_DE_EXPECTED_TYPES
    # The 5 baselines must come from 5 distinct source URLs — no
    # single document covers more than one clause type. (Hosts may
    # repeat: the 4 gesetze-im-internet.de pages all share the
    # www.gesetze-im-internet.de host; the spec's diversity rule
    # is "no single document covers more than one clause type",
    # satisfied by the 4 different Bundesgesetzestexte.)
    assert len({r["source_url"] for r in rows}) == 5
    # Source-spread cross-check: the union of hosts covers the
    # 2-source spread (gesetze-im-internet.de + ihk.de). A weaker
    # assertion is appropriate here than for the DE NDA (5 distinct
    # hosts) or the DE DPA (≥ 4 distinct hosts): the DE Employment
    # set is anchored to German federal statutory floors which
    # legitimately collapse to a single amtliche host across 4
    # distinct statutes, plus the IHK Mustervertrag for the
    # non-solicitation anchor.
    assert len(seen_hosts) >= 2, (
        f"DE Employment baselines should come from at least 2 distinct "
        f"hosts (gesetze-im-internet.de + ihk.de); got {len(seen_hosts)}: "
        f"{seen_hosts}"
    )


@pytest.mark.asyncio
async def test_seed_employment_de_baselines_idempotent(cleanup_playbook):
    """Re-seeding the DE Employment baselines produces no duplicate rows.

    The seeder is documented as idempotent at the row level; the
    DE Employment coverage is no exception. The (playbook_id, clause_id)
    PK should reject any second insert.
    """
    version = _unique_version()
    first = await seed_all(
        playbook_root=BASELINES.parent,
        version=version,
        contract_type="employment",
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
        contract_type="employment",
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
    assert count2 == 5, "second DE Employment seed created duplicate rows!"
