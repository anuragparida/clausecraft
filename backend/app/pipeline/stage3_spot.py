"""Stage 3 — spot deviations (per-clause parallel orchestration).

The pipeline so far (Phase 1 + 2):

  raw bytes
    → ingest (text + per-paragraph metadata)        [stage1]
    → parse (chunked into RawClauses)               [stage1]
    → classify (each RawClause gets a ClauseType)    [stage1]
    → spot (each Clause gets a DeviationFlag)        [stage3]
    → aggregate (build the flag table)              [stage4 — separate card]

This module owns stage 3. It takes the classified clauses from
stage 1, pulls the top-3 playbook baselines per clause from the
store, converts them to the agent's :class:`SpotInput` shape, and
runs the spotter with bounded parallelism.

Key design decisions
--------------------

- **Top-k retrieval is per-clause, not per-contract.** Each
  clause's text is embedded and used to query the store. The
  spotter wants the most-similar baseline FOR THIS CLAUSE'S
  TEXT, not the top-3 baselines for the whole contract. This
  is the "right" semantic match (a "term" clause is compared
  against term baselines, not against "definition of
  confidential info" baselines).
- **Counterparty context is loaded once per contract.** The
  matrix is a YAML file, the flat lookup is a dict access. We
  read the matrix once at the top of :func:`run_stage3` and
  pass the relevant verdict to each spot call.
- **Parallelism is bounded.** We use ``asyncio.gather`` with a
  semaphore so a 200-clause contract doesn't fan out 200
  concurrent LLM calls. The bound is 8 — high enough to
  overlap network latency, low enough to respect the gateway's
  rate limits.
- **No exceptions propagate.** A failed spot call (LLM
  unreachable, Pydantic validation, anything) becomes an
  ``unverified=True`` flag with a rationale that names the
  error. The pipeline must produce a flag for every clause,
  even if the LLM is down. The Phase 2 / Phase 3 eval harness
  measures real quality; this stage's job is to keep the
  pipeline alive.

The module exposes one function (:func:`run_stage3`) and one
result dataclass (:class:`Stage3Result`).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.deviation_spotter.schema import (
    BaselineForSpotter,
    DeviationFlag,
    SpotInput,
)
from app.agents.deviation_spotter.spotter import spot_clause
from app.classify.schema import Clause
from app.config import settings
from app.db import get_session_factory
from app.playbook.counterparty import (
    CounterpartyMatrix,
    load_matrix,
    lookup_verdict,
)
from app.playbook.embeddings import embed_text, is_real_provider_available
from app.playbook.store import get_store

logger = logging.getLogger(__name__)


#: Maximum number of concurrent LLM calls. Higher → faster, but
#: more pressure on the gateway's rate limit. 8 is the
#: sweet spot for a 10–20-clause NDA; the orchestrator chunks
#: larger contracts at the contract level, not the global level.
_MAX_CONCURRENT_SPOTS = 8


# --- Result -------------------------------------------------------------


@dataclass
class Stage3Result:
    """The output of :func:`run_stage3`.

    Attributes
    ----------
    contract_filename
        Echoed for the API response / audit trail.
    flags
        One :class:`DeviationFlag` per input clause, in the same
        order as the input ``clauses`` list.
    flagged_count
        Number of flags with ``score > 0``. Convenient for the
        aggregate stage and the API response.
    unverified_count
        Number of flags with ``unverified=True``. The eval
        harness's "citation completeness" metric is
        ``1 - unverified_count / total``.
    no_baseline_count
        Number of flags where the spotter abstained because no
        baseline matched. Surfaced in the UI as a separate
        count.
    matrix_version
        The counterparty matrix version string. Echoed in the
        API response for reproducibility.
    embedding_provider
        The embedding provider used for the top-k queries
        (``"openai-compatible"`` or ``"offline-hash"``). Useful
        for the audit trail (real semantic neighbours vs
        hash-based stand-ins).
    """

    contract_filename: str
    flags: list[DeviationFlag] = field(default_factory=list)
    flagged_count: int = 0
    unverified_count: int = 0
    no_baseline_count: int = 0
    matrix_version: str = ""
    embedding_provider: str = ""


# --- Helpers ------------------------------------------------------------


def _load_matrix_or_default() -> CounterpartyMatrix:
    """Load the counterparty matrix from the configured path.

    Falls back to a minimal default matrix (all-aligned) when the
    YAML is missing or malformed. The fallback is **not** the
    "no matrix" state — the matrix is part of the Phase 2
    contract, and a missing matrix is a config error, not a
    spotter fallback. We log loudly and proceed with the
    default rather than crashing the pipeline.
    """
    try:
        return load_matrix()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to load counterparty matrix from %s: %s. "
            "Falling back to all-aligned default.",
            settings.counterparty_matrix_path,
            exc,
        )
        return CounterpartyMatrix.from_dict(
            {
                "version": "0.0.0-fallback",
                "contract_type": "nda",
                "language": "en",
                "default_counterparty_type": "any",
                "default_verdict": "aligned",
                "clause_verdicts": {},
                "counterparty_overrides": {},
            }
        )


def _matrix_verdict_for_clause(
    matrix: CounterpartyMatrix, clause_type: str
) -> tuple[str, str]:
    """Return ``(verdict_label, counterparty_type)`` for a clause.

    The spotter wants the *label* (``"aligned"`` / ``"minor"`` /
    ...) not the :class:`Verdict` enum — the prompt renders the
    label as plain text. The counterparty type is always
    ``"any"`` in Phase 2 (flat lookup); Phase 5 will pass the
    real counterparty type.
    """
    matrix_verdict = lookup_verdict(matrix, clause_type)
    return matrix_verdict.verdict.label(), matrix_verdict.counterparty_type


def _baselines_to_spot_inputs(
    clause: Clause,
    hits: list[Any],
    matrix: CounterpartyMatrix,
) -> SpotInput:
    """Build a :class:`SpotInput` for a single clause.

    Converts the store's :class:`PlaybookTopKHit` list to the
    agent's :class:`BaselineForSpotter` shape and looks up the
    counterparty matrix verdict for the clause's type.
    """
    baselines = [
        BaselineForSpotter(
            clause_id=h.clause_id,
            type=h.type,
            title=h.title,
            text=h.text,
            source_url=h.source_url,
            similarity=h.similarity,
        )
        for h in hits
    ]
    verdict_label, cp_type = _matrix_verdict_for_clause(
        matrix, clause.type.value
    )
    return SpotInput(
        clause_id=clause.id,
        clause_text=clause.text,
        clause_type=clause.type.value,
        baselines=baselines,
        counterparty_verdict=verdict_label,
        counterparty_type=cp_type,
    )


async def _spot_one(
    spot_input: SpotInput,
    *,
    contract_filename: str,
    semaphore: asyncio.Semaphore,
) -> DeviationFlag:
    """Spot a single clause with bounded concurrency.

    The semaphore caps the number of in-flight LLM calls. The
    actual spot call is sync (it blocks on the OpenAI client),
    so we run it in the default thread pool via
    :func:`asyncio.to_thread`. This is the only way to bound
    concurrency on a sync function from async code without
    pulling in a worker-process pool.
    """
    async with semaphore:
        # `asyncio.to_thread` pushes the sync call to the
        # default executor, so the event loop stays responsive
        # while the LLM call is in flight.
        flag = await asyncio.to_thread(
            spot_clause,
            spot_input,
            contract_filename=contract_filename,
        )
        return flag


# --- Public surface -----------------------------------------------------


async def run_stage3(
    *,
    clauses: list[Clause],
    contract_filename: str = "",
) -> Stage3Result:
    """Execute the spot stage for a list of classified clauses.

    For each clause:

    1. Embed the clause text (real bge-m3 or offline fallback).
    2. Query the playbook store for the top-3 baselines for the
       configured ``(contract_type, language)``. The query uses
       no ``contract_type`` / ``language`` filter when the
       spotter is called for a contract whose
       ``(contract_type, language)`` is not in the playbook
       registry (Phase 2 only ships NDA EN; for other
       combinations we fall back to the top-3 across every
       playbook so the spotter still has *something* to
       compare against — better than crashing on an unknown
       contract type).
    3. Build a :class:`SpotInput` from the clause + the
       baselines + the counterparty matrix verdict.
    4. Call :func:`app.agents.deviation_spotter.spotter.spot_clause`
       with bounded parallelism.

    Returns a :class:`Stage3Result` with one flag per input
    clause (same order as the input list).

    The function does NOT raise on a per-clause failure — every
    clause gets a flag, even if the flag is
    ``score=0, unverified=True, rationale="agent declined"``.
    This is the pipeline contract the spec calls out: a flag
    for every clause, no matter what.
    """
    if not clauses:
        return Stage3Result(contract_filename=contract_filename)

    matrix = _load_matrix_or_default()
    store = get_store()
    factory = get_session_factory()

    # Determine the embedding provider once, for the audit trail.
    # We don't pre-flight the real provider here; the embeddings
    # module handles the fallback internally. We just record
    # which path is configured.
    embedding_provider = (
        "openai-compatible" if is_real_provider_available() else "offline-hash"
    )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SPOTS)
    spot_inputs: list[SpotInput] = []
    no_baseline_ids: set[str] = set()

    # We do the top-k retrieval sequentially (the Postgres
    # connection pool is bounded and the LLM parallelism is the
    # real win). The LLM calls are parallel.
    async with factory() as session:
        for clause in clauses:
            try:
                # Embed the clause text. The embeddings module
                # handles the offline fallback internally.
                emb = embed_text(clause.text)
                hits = await store.topk(
                    session,
                    query_embedding=emb,
                    k=3,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "top-k retrieval failed for %s: %s — "
                    "spotting with no baselines",
                    clause.id,
                    exc,
                )
                hits = []
            if not hits:
                no_baseline_ids.add(clause.id)
            spot_inputs.append(
                _baselines_to_spot_inputs(clause, hits, matrix)
            )

    # Fire all spot calls in parallel, bounded by the semaphore.
    tasks = [
        _spot_one(
            si,
            contract_filename=contract_filename,
            semaphore=semaphore,
        )
        for si in spot_inputs
    ]
    flags: list[DeviationFlag] = await asyncio.gather(*tasks)

    flagged_count = sum(1 for f in flags if f.score > 0)
    unverified_count = sum(1 for f in flags if f.unverified)
    no_baseline_count = sum(
        1 for f in flags if f.rationale == "no matching playbook clause"
    )

    logger.info(
        "Stage 3 spotted %d clauses for %s: flagged=%d, "
        "unverified=%d, no_baseline=%d, embedding_provider=%s",
        len(flags),
        contract_filename or "<unknown>",
        flagged_count,
        unverified_count,
        no_baseline_count,
        embedding_provider,
    )

    return Stage3Result(
        contract_filename=contract_filename,
        flags=flags,
        flagged_count=flagged_count,
        unverified_count=unverified_count,
        no_baseline_count=no_baseline_count,
        matrix_version=matrix.version,
        embedding_provider=embedding_provider,
    )


__all__ = [
    "Stage3Result",
    "run_stage3",
]
