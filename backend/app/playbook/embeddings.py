"""Embeddings for the playbook store.

Phase 2: bge-m3 via the configured LLM gateway. We use the same
OpenAI-compatible client the classifier uses (the gateway is
OpenRouter; the embeddings endpoint is
``{base_url}/embeddings``). The model is configurable so Phase 4
can swap to a multilingual variant without code changes.

Why an offline fallback
-----------------------
The Phase 2 smoke test must be runnable end-to-end (seed + insert
+ topk) without network access. The configured gateway may also
be temporarily unavailable (rate limit, payment fail, egress
block). The fallback produces a deterministic, hash-seeded
``embedding_dim``-dimensional vector for any input string, so:

- The pipeline still demonstrates the contract: ``embed → store
  → topk cosine similarity``.
- The store is populated with real semantic neighbours when the
  real provider is up, and with deterministic vectors when it
  is not.
- Tests can run with ``EMBEDDING_PROVIDER=offline`` and get
  reproducible results.

The fallback is *not* semantically meaningful — it is a stand-in
so the rest of the system has something to operate on. The
``is_real_provider_available()`` helper and the ``provider`` field
on every returned vector make the path visible to callers; the
Phase 2 / Phase 3 dev agents and the eval harness log a warning
when the offline path is hit.

Calling pattern
---------------
The store uses :func:`embed_text` and :func:`embed_texts` —
single-text and batched. Both return numpy arrays (so the store
can hand the vector to pgvector without conversion overhead) and
populate the ``provider`` field so callers can log which path
ran.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


# --- Provider state -----------------------------------------------------

@dataclass
class EmbeddingResult:
    """A single text's embedding.

    Attributes
    ----------
    embedding
        ``embedding_dim``-dimensional float32 vector. Always
        ``np.ndarray`` of shape ``(embedding_dim,)`` so the
        pgvector store can serialise it directly.
    provider
        ``"openai-compatible"`` (real bge-m3) or
        ``"offline-hash"`` (deterministic fallback).
    model
        The model identifier used (e.g. ``"baai/bge-m3"``). For
        the offline path, the configured ``embedding_model``
        setting is still recorded so the audit trail says what
        would have been used.
    """

    embedding: np.ndarray
    provider: str
    model: str


# --- Public API ---------------------------------------------------------

def is_real_provider_available() -> bool:
    """True when the embedding provider is configured and the
    gateway looks reachable.

    "Available" here is a *configuration* check, not a connectivity
    check: we don't ping the gateway from this function (that would
    add latency to every embed call). A real probe happens lazily
    inside :func:`_embed_via_openai_compatible` on the first call —
    if the probe fails, we fall back to the offline path and log a
    warning. The function is what the seed script and the smoke
    test consult to decide whether to log a "bge-m3 unreachable"
    warning at the top of the run.
    """
    key = (settings.embedding_api_key or "").strip()
    if not key or _looks_like_placeholder(key):
        return False
    if "example.invalid" in (settings.embedding_base_url or ""):
        return False
    return True


def embed_text(text: str) -> EmbeddingResult:
    """Embed a single text string.

    Falls back to the offline path on any error (logged at WARNING).
    The return value is always populated.
    """
    return embed_texts([text])[0]


def embed_texts(texts: Sequence[str]) -> list[EmbeddingResult]:
    """Embed a batch of strings.

    Batching: the OpenAI-compatible client accepts a list of
    strings in a single ``/embeddings`` call. We do that when the
    real provider is available. The offline path is per-text
    (it's pure-Python hashing; no batching wins here).
    """
    texts = list(texts)
    if not texts:
        return []

    if is_real_provider_available():
        try:
            return _embed_via_openai_compatible(texts)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "bge-m3 embedding call failed (%s); falling back to "
                "offline hash embeddings. Set EMBEDDING_PROVIDER=offline "
                "to skip the probe entirely.",
                exc,
            )

    # Offline path: one EmbeddingResult per text, deterministic.
    return [
        EmbeddingResult(
            embedding=_offline_embedding(t),
            provider="offline-hash",
            model=settings.embedding_model,
        )
        for t in texts
    ]


# --- Real provider (OpenAI-compatible) ---------------------------------

def _embed_via_openai_compatible(
    texts: list[str],
) -> list[EmbeddingResult]:
    """Call the gateway's ``/embeddings`` endpoint.

    Uses the ``openai`` client with a configurable ``base_url``
    and ``model``. The gateway in this project is OpenRouter;
    OpenRouter exposes the standard OpenAI embeddings endpoint
    under ``/api/v1/embeddings``.

    The response is parsed for ``data[i].embedding`` and returned
    as a list of :class:`EmbeddingResult`. We do NOT do
    post-processing (L2 normalisation, truncation) here — pgvector's
    ``<=>`` cosine operator assumes unit vectors, but pgvector
    0.8 also supports ``vector_norm`` on the input side. We let the
    store decide.
    """
    from openai import OpenAI  # type: ignore[import-not-found]

    client = OpenAI(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
    )
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=list(texts),
        encoding_format="float",
    )
    out: list[EmbeddingResult] = []
    for item in response.data:
        vec = np.asarray(item.embedding, dtype=np.float32)
        if vec.shape != (settings.embedding_dim,):
            raise ValueError(
                f"embedding dim mismatch from gateway: got "
                f"{vec.shape[0]}, expected {settings.embedding_dim}. "
                f"Check EMBEDDING_DIM and the configured model."
            )
        out.append(
            EmbeddingResult(
                embedding=vec,
                provider="openai-compatible",
                model=settings.embedding_model,
            )
        )
    return out


# --- Offline fallback ---------------------------------------------------

def _offline_embedding(text: str) -> np.ndarray:
    """Deterministic hash-seeded pseudo-embedding of length
    ``embedding_dim``.

    Construction: SHA-256 of the text is the seed for a NumPy
    default RNG. The RNG produces ``embedding_dim`` floats in
    ``[-1, 1]``. The vector is L2-normalised so cosine similarity
    against any other offline vector is well-defined.

    Properties:

    - Identical inputs produce identical vectors (idempotent).
    - Different inputs produce approximately orthogonal vectors
      on average (cosine ≈ 0 for random pairs), which is the
      same "shape" of behaviour a real embedding model exhibits
      on unrelated inputs.
    - No I/O, no globals, safe to call from tests and from
      parallel seeders.

    The function is intentionally *not* deterministic-across-
    processes in the cryptographic sense (the seed is a SHA-256
    hash, but the RNG is a standard ``default_rng``). That is
    fine: we only need the same process to produce stable
    vectors, so the seeded topk results are reproducible.
    """
    if not text:
        # Empty text → zero vector. pgvector's cosine op returns
        # 0 for a zero vector (undefined, but consistent).
        return np.zeros(settings.embedding_dim, dtype=np.float32)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Convert the first 8 bytes of the digest to an int64 seed.
    seed = int.from_bytes(digest[:8], byteorder="big", signed=False)
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(settings.embedding_dim).astype(np.float32)
    # L2 normalise so cosine similarity is bounded in [-1, 1].
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return vec / norm


# --- Helpers ------------------------------------------------------------

def _looks_like_placeholder(value: str) -> bool:
    """A key containing 'placeholder' or '...' is not real.

    Mirrors the heuristic in
    :mod:`app.classify.classifier._looks_like_real_key` and
    :mod:`app.observability._looks_like_placeholder` so the
    three subsystems agree on what "no real key configured"
    means.
    """
    if not value:
        return True
    lowered = value.lower()
    if "placeholder" in lowered:
        return True
    if "***" in value:
        return True
    if value.startswith("llm-pl"):
        # The seed-style placeholders that look like "llm-pl...-key"
        if "..." in value or value.endswith("-key"):
            return True
    return False


__all__ = [
    "EmbeddingResult",
    "embed_text",
    "embed_texts",
    "is_real_provider_available",
    # For tests only — not part of the public API.
    "_offline_embedding",
    "_looks_like_placeholder",
]
