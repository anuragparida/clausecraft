"""Test the embeddings module — offline path, real path, batch path."""

from __future__ import annotations

import numpy as np
import pytest

from app.config import settings
from app.playbook import (
    EmbeddingResult,
    embed_text,
    embed_texts,
    is_real_provider_available,
)


def test_offline_embedding_is_deterministic():
    """The same input always produces the same vector."""
    a = embed_texts(["hello world", "hello world"])
    assert a[0].provider == "offline-hash"
    np.testing.assert_array_equal(a[0].embedding, a[1].embedding)


def test_offline_embedding_is_l2_normalised():
    """The offline vector has unit L2 norm — cosine similarity is well-defined."""
    e = embed_text("a sample clause about the term of an NDA")
    norm = float(np.linalg.norm(e.embedding))
    assert 0.999 <= norm <= 1.001, f"expected unit norm, got {norm}"


def test_offline_embedding_dim_matches_settings():
    """Vector length matches ``settings.embedding_dim``."""
    e = embed_text("test")
    assert e.embedding.shape == (settings.embedding_dim,)


def test_empty_text_produces_zero_vector():
    """Empty text doesn't crash the offline path."""
    e = embed_text("")
    assert e.embedding.shape == (settings.embedding_dim,)
    # The zero vector is preserved (not normalised to nan).
    assert np.all(e.embedding == 0.0)


def test_batch_embed_returns_one_per_input():
    """Batched call returns a list of the same length as the input."""
    texts = ["alpha", "beta", "gamma"]
    out = embed_texts(texts)
    assert len(out) == 3
    for i, t in enumerate(texts):
        assert isinstance(out[i], EmbeddingResult)
        assert out[i].embedding.shape == (settings.embedding_dim,)


@pytest.mark.skipif(
    not is_real_provider_available(),
    reason="no real embedding provider configured",
)
def test_real_provider_dim_matches_settings():
    """If the gateway is reachable, it returns vectors of the configured dim."""
    e = embed_text("test real path")
    assert e.provider == "openai-compatible"
    assert e.embedding.shape == (settings.embedding_dim,)
    # Real embeddings are NOT expected to be L2-normalised by
    # every gateway. We don't assert norm here.
