"""Idempotent seeder: read every YAML under ``playbook/baselines/`` and
upsert into the playbook store.

Invocation
----------
``python -m backend.app.playbook.seed`` is the canonical smoke test.
The module is also imported by tests (``tests/phase2/test_seed.py``)
which call :func:`seed_all` directly with a custom playbook path.

Behaviour
---------
1. Ensure the schema exists (:meth:`PlaybookStore.ensure_schema`).
2. Walk ``playbook/baselines/`` recursively. Each leaf directory is
   treated as a ``(contract_type, language)`` pair, derived from the
   directory name (``"nda-en"`` → ``contract_type="nda"``,
   ``language="en"``). This convention is set by the spec:
   ``playbook/baselines/<contract-type>-<language>/``.
3. For each YAML file, parse into a :class:`PlaybookBaseline` and
   upsert every clause.
4. Print a one-line summary per playbook with the clause count and
   the embedding provider used (so the operator sees whether the
   real bge-m3 was reached or the offline path ran).

Idempotency
-----------
Re-running on the same data is a no-op at the row level (the upsert
overwrites identical content). Re-running on changed YAML data
updates the existing rows. The function does NOT delete rows that
are no longer present in the YAMLs — that would be a destructive
operation the operator should do explicitly. A future "playbook
diff" tool can do that, but it's out of scope for Phase 2.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.classify.schema import ClauseType
from app.config import settings
from app.db import get_session_factory
from app.playbook.embeddings import (
    embed_texts,
    is_real_provider_available,
)
from app.playbook.schema import BaselineClause, PlaybookBaseline
from app.playbook.store import PlaybookStore

logger = logging.getLogger(__name__)


# --- Result type --------------------------------------------------------

@dataclass
class SeedSummary:
    """One row of the seed report.

    Attributes
    ----------
    contract_type
        e.g. ``"nda"``.
    language
        e.g. ``"en"``.
    version
        The playbook version string (from settings or arg).
    clause_count
        Number of clauses successfully upserted.
    embedding_provider
        ``"openai-compatible"`` (real bge-m3) or
        ``"offline-hash"`` (deterministic fallback).
    """

    contract_type: str
    language: str
    version: str
    clause_count: int
    embedding_provider: str


# --- Public API ---------------------------------------------------------

async def seed_all(
    *,
    playbook_root: Optional[Path] = None,
    version: Optional[str] = None,
    contract_type: Optional[str] = None,
    language: Optional[str] = None,
) -> list[SeedSummary]:
    """Seed every YAML under ``playbook_root/baselines/``.

    Parameters
    ----------
    playbook_root
        Root of the playbook directory (the one that contains
        ``baselines/`` and ``counterparty_matrix.yaml``). Defaults
        to the repo root computed from this file's path. The
        default works for both ``python -m backend.app.playbook.seed``
        (run from anywhere) and for tests that ``cd backend`` first.
    version
        Playbook version string. Defaults to ``settings.playbook_version``.
    contract_type, language
        When provided, restrict the seed to one
        ``(contract_type, language)`` pair. Used by tests and by
        the ``--contract-type`` / ``--language`` CLI flags.

    Returns
    -------
    list[SeedSummary]
        One entry per playbook that was seeded. The CLI prints
        these as a table.
    """
    root = _resolve_playbook_root(playbook_root)
    version = version or settings.playbook_version
    baselines_dir = root / "baselines"
    if not baselines_dir.is_dir():
        raise FileNotFoundError(
            f"playbook baselines directory not found: {baselines_dir}"
        )

    store = PlaybookStore()
    factory = get_session_factory()
    summaries: list[SeedSummary] = []
    async with factory() as session:
        await store.ensure_schema(session)
        # Note: ensure_schema commits its own transaction. The
        # next session.execute() opens a new transaction.

        for leaf in sorted(baselines_dir.iterdir()):
            if not leaf.is_dir():
                continue
            leaf_name = leaf.name
            parsed_contract, parsed_language = _split_dir_name(leaf_name)
            if parsed_contract is None or parsed_language is None:
                logger.warning(
                    "skipping playbook directory %s: name does not match "
                    "<contract-type>-<language> pattern",
                    leaf_name,
                )
                continue
            if contract_type and parsed_contract != contract_type:
                continue
            if language and parsed_language != language:
                continue

            summary = await _seed_one(
                session=session,
                store=store,
                directory=leaf,
                contract_type=parsed_contract,
                language=parsed_language,
                version=version,
            )
            summaries.append(summary)
    return summaries


# --- Internals ----------------------------------------------------------

async def _seed_one(
    *,
    session: AsyncSession,
    store: PlaybookStore,
    directory: Path,
    contract_type: str,
    language: str,
    version: str,
) -> SeedSummary:
    """Seed all YAMLs in a single ``(contract_type, language)`` directory."""
    playbook_id = await store.upsert_playbook_version(
        session,
        contract_type=contract_type,
        language=language,
        version=version,
        description=(
            f"Auto-seeded from {directory.relative_to(_resolve_playbook_root())}"
            if _is_relative_to(directory, _resolve_playbook_root())
            else f"Auto-seeded from {directory}"
        ),
    )
    yaml_files = sorted(directory.glob("*.yaml")) + sorted(
        directory.glob("*.yml")
    )
    if not yaml_files:
        logger.warning("no YAML files in %s", directory)
        return SeedSummary(
            contract_type=contract_type,
            language=language,
            version=version,
            clause_count=0,
            embedding_provider="(none)",
        )

    # Collect all clauses across all YAML files in this directory.
    # We embed in a single batch so the embedding call (when using
    # the real provider) hits the gateway once per directory.
    parsed: list[tuple[BaselineClause, Path]] = []
    for path in yaml_files:
        try:
            baseline = PlaybookBaseline.from_yaml(str(path))
        except Exception as exc:
            raise ValueError(
                f"failed to parse playbook YAML {path}: {exc}"
            ) from exc
        for clause in baseline.clauses:
            _validate_clause_type(clause)
            parsed.append((clause, path))

    if not parsed:
        return SeedSummary(
            contract_type=contract_type,
            language=language,
            version=version,
            clause_count=0,
            embedding_provider="(none)",
        )

    texts = [c.text for c, _ in parsed]
    embeddings = embed_texts(texts)

    for (clause, _path), emb in zip(parsed, embeddings):
        await store.upsert_clause(
            session,
            playbook_id=playbook_id,
            clause_id=clause.clause_id,
            type=clause.type,
            language=clause.language,
            title=clause.title,
            text_body=clause.text,
            source_url=clause.source_url,
            retrieval_date=clause.retrieval_date,
            license=clause.license,
            embedding=emb,
        )

    # All clauses in a directory share the same embedding provider
    # (embed_texts is a single batch). Pick the first non-null one.
    providers = {e.provider for e in embeddings}
    embedding_provider = (
        next(iter(providers)) if len(providers) == 1 else ",".join(sorted(providers))
    )

    return SeedSummary(
        contract_type=contract_type,
        language=language,
        version=version,
        clause_count=len(parsed),
        embedding_provider=embedding_provider,
    )


def _validate_clause_type(clause: BaselineClause) -> None:
    """Confirm ``clause.type`` is a real :class:`ClauseType` enum value.

    Done at seed time (not at YAML parse time) so the error message
    can name the YAML file and the offending value. Raises
    :class:`ValueError` on a mismatch.
    """
    try:
        ClauseType(clause.type)
    except ValueError as exc:
        raise ValueError(
            f"clause type {clause.type!r} in baseline {clause.clause_id!r} "
            f"is not a valid ClauseType enum value; valid values: "
            f"{sorted(ClauseType.non_unknown_values())}"
        ) from exc


def _split_dir_name(name: str) -> tuple[Optional[str], Optional[str]]:
    """``"nda-en"`` → ``("nda", "en")``. Returns ``(None, None)`` on miss.

    The split rule is "last dash": the suffix is the language
    (always exactly 2 lowercase letters) and the prefix is the
    contract type. This is forward-compatible with
    ``"dpa-de"``, ``"employment-en"``, etc.
    """
    m = re.fullmatch(r"([a-z0-9-]+)-([a-z]{2})", name)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _resolve_playbook_root(playbook_root: Optional[Path] = None) -> Path:
    """Locate the playbook root, defaulting to the configured setting.

    Resolution order:

    1. Explicit ``playbook_root`` argument (used by tests).
    2. ``settings.playbook_baselines_root`` env var
       (``PLAYBOOK_BASELINES_ROOT``). In the docker container
       this is set to ``/playbook`` (the bind-mount of the repo's
       ``playbook/`` directory).
    3. The repo root computed from this file's path. Works for
       ``python -m backend.app.playbook.seed`` run from the repo
       root and for tests that have the backend on sys.path.
    """
    if playbook_root is not None:
        return Path(playbook_root).resolve()
    if settings.playbook_baselines_root:
        configured = Path(settings.playbook_baselines_root)
        if configured.is_absolute():
            return configured.resolve()
        # Relative path — resolve against the file's repo root
        # (3 levels up from this file). This is the dev/CI case.
        return (Path(__file__).resolve().parents[3] / configured).resolve()
    # No setting — fall back to the historical default.
    return Path(__file__).resolve().parents[3] / "playbook"


def _is_relative_to(child: Path, parent: Path) -> bool:
    """``Path.is_relative_to`` is 3.9+; this is a defensive wrapper."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


# --- CLI ----------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m backend.app.playbook.seed",
        description=(
            "Idempotent seeder for the playbook. Re-runs are safe: "
            "existing rows are overwritten with the same data."
        ),
    )
    p.add_argument(
        "--playbook-root",
        type=Path,
        default=None,
        help="Path to the playbook root (default: repo root).",
    )
    p.add_argument(
        "--version",
        type=str,
        default=None,
        help="Playbook version string (default: settings.playbook_version).",
    )
    p.add_argument(
        "--contract-type",
        type=str,
        default=None,
        help="Restrict to one contract type (e.g. 'nda'). Default: all.",
    )
    p.add_argument(
        "--language",
        type=str,
        default=None,
        help="Restrict to one language (e.g. 'en'). Default: all.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-playbook output (only the summary).",
    )
    return p


async def _amain(args: argparse.Namespace) -> int:
    if not args.quiet:
        if is_real_provider_available():
            print(
                f"[seed] embedding provider: bge-m3 via "
                f"{settings.embedding_base_url} (model={settings.embedding_model})"
            )
        else:
            print(
                "[seed] WARNING: no real embedding provider configured; "
                "using offline-hash fallback (deterministic but not "
                "semantic). The store and top-k still work; the F1 numbers "
                "will not be meaningful. Set EMBEDDING_API_KEY and "
                "EMBEDDING_BASE_URL to enable real bge-m3."
            )
    summaries = await seed_all(
        playbook_root=args.playbook_root,
        version=args.version,
        contract_type=args.contract_type,
        language=args.language,
    )
    if not args.quiet:
        print()
        print(
            f"{'contract_type':<16} {'language':<10} {'version':<16} "
            f"{'clauses':>8}  {'provider':<24}"
        )
        print("-" * 80)
        for s in summaries:
            print(
                f"{s.contract_type:<16} {s.language:<10} {s.version:<16} "
                f"{s.clause_count:>8}  {s.embedding_provider:<24}"
            )
    if not summaries:
        print("[seed] no playbooks matched the filters", file=sys.stderr)
        return 1
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    args = _build_arg_parser().parse_args(argv)
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
