"""Playbook package — Phase 2.

Modules:

- ``schema``     — Pydantic models for the on-disk YAML baseline files.
- ``store``      — Postgres + pgvector storage layer. Idempotent upsert
                   by ``(playbook_id, clause_id)`` and the top-k
                   cosine-similarity helper.
- ``embeddings`` — bge-m3 integration via the configured LLM gateway
                   (OpenAI-compatible client). Includes a deterministic
                   offline fallback so the rest of the pipeline runs
                   end-to-end when the gateway is unreachable.
- ``seed``       — Idempotent seeder that reads every YAML under
                   ``playbook/baselines/`` and inserts into the store.
- ``counterparty`` — Matrix config loader. Phase 2 ships a flat
                  lookup; Phase 5 promotes the 2D ``counterparty_type
                  → clause_type → verdict`` table to a first-class
                  source of truth (4 axes: ``enterprise``, ``smb``,
                  ``public_sector``, ``healthcare``). Phase 4 stacks
                  a *language* axis on top, with the DE column
                  narrowing verdicts for DE counterparty types
                  (additive — EN path unchanged).

Public surface: this package re-exports the high-level helpers so
``python -m backend.app.playbook.seed`` and tests can ``from
app.playbook import ...`` without reaching into submodules.
"""

from app.playbook.counterparty import (
    COUNTERPARTY_TYPES,
    DEFAULT_COUNTERPARTY_TYPE,
    DE_GERMAN_ENTITY,
    CounterpartyMatrix,
    MatrixVerdict,
    Verdict,
    load_matrix,
    lookup_verdict,
    lookup_verdict_with_counterparty,
    lookup_verdict_with_language,
)
from app.playbook.embeddings import (
    EmbeddingResult,
    embed_text,
    embed_texts,
    is_real_provider_available,
)
from app.playbook.schema import BaselineClause, PlaybookBaseline
from app.playbook.store import (
    PlaybookStore,
    PlaybookTopKHit,
    get_store,
)

__all__ = [
    # schema
    "BaselineClause",
    "PlaybookBaseline",
    # embeddings
    "EmbeddingResult",
    "embed_text",
    "embed_texts",
    "is_real_provider_available",
    # store
    "PlaybookStore",
    "PlaybookTopKHit",
    "get_store",
    # counterparty
    "COUNTERPARTY_TYPES",
    "DEFAULT_COUNTERPARTY_TYPE",
    "DE_GERMAN_ENTITY",
    "CounterpartyMatrix",
    "MatrixVerdict",
    "Verdict",
    "load_matrix",
    "lookup_verdict",
    "lookup_verdict_with_counterparty",
    "lookup_verdict_with_language",
]
