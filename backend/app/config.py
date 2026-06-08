"""Centralized config for the clausecraft backend.

All env vars are loaded once at import time via pydantic-settings. Use
``from app.config import settings`` anywhere you need a config value.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings. Read from process env / .env at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://clausecraft:clausecraft@localhost:15432/clausecraft",
        description="Async SQLAlchemy URL (asyncpg driver).",
    )

    # --- Langfuse (stubbed in Phase 0) ---
    langfuse_host: str = Field(default="http://localhost:13000")
    langfuse_public_key: str = Field(default="pk-lf-placeholder")
    langfuse_secret_key: str = Field(default="sk-lf-placeholder")

    # --- LLM (clausecraft internal) ---
    # Routing policy (2026-06-07, per Anurag):
    #   - LLM text calls → MiniMax subscription we already have.
    #     MiniMax exposes both an Anthropic-compatible endpoint
    #     (``/anthropic/v1/messages``, what Honcho uses) and an
    #     OpenAI-compatible endpoint (``/v1/chat/completions``,
    #     what the openai Python SDK needs). The deviation
    #     spotter uses the openai SDK (see
    #     ``app.agents.deviation_spotter.spotter._call_llm_for_spot``),
    #     so we point at the OpenAI-compatible path.
    #   - Embeddings → OpenRouter qwen3-embedding-8b (explicitly
    #     allowlisted on the OpenRouter key, per Anurag).
    #   - Local hosting skipped: a Sonnet-class LLM is far too
    #     large for the <2GB budget; an 8B embedding model is also
    #     outside budget. Both routed to remote gateways.
    # When ``llm_api_key`` is a placeholder the classifier and
    # spotter fall back to deterministic rule-based / keyword
    # passes so the pipeline still produces non-null outputs.
    llm_api_key: str = Field(default="placeholder-not-a-real-key")
    llm_base_url: str = Field(default="https://api.minimax.io/v1")
    llm_model: str = Field(default="MiniMax-M3")

    # --- Embeddings (Phase 2: playbook store) ---
    # OpenRouter ``/embeddings`` endpoint, model pinned to
    # ``qwen/qwen3-embedding-8b`` (the only embedding model
    # allowlisted on this OpenRouter account).
    # Default dimension is **1024**, chosen because:
    #   (a) pgvector's HNSW index refuses columns over 2000
    #       dimensions; 1024 is well under the cap and still
    #       big enough to be a high-quality semantic space.
    #   (b) the qwen3-embedding family natively defaults to
    #       4096 (probed against OpenRouter on 2026-06-07),
    #       which would force us off HNSW onto halfvec. We
    #       request ``dimensions=embedding_dim`` explicitly in
    #       ``app.playbook.embeddings._embed_via_openai_compatible``
    #       to pin the output length.
    # The store asserts the gateway returns vectors of exactly
    # this length and raises a clean ValueError otherwise.
    # The previous default (bge-m3 / 1024d) was a dead end — the
    # account's privacy guardrails 404'd all bge-m3 endpoints
    # (see kanban t_d8e69387 report). qwen3-embedding-8b is the
    # only embedding model this account exposes.
    embedding_api_key: str = Field(default="placeholder-not-a-real-key")
    embedding_base_url: str = Field(default="https://openrouter.ai/api/v1")
    embedding_model: str = Field(default="qwen/qwen3-embedding-8b")
    embedding_dim: int = Field(default=1024, ge=64, le=4096)

    # --- Playbook / counterparty (Phase 2) ---
    # Version string for the active playbook baseline. Used by the
    # seed script to populate ``playbook_versions.version``. Bumping
    # this on a real release makes the new clauses appear under a
    # new (contract_type, language, version) row without disturbing
    # the old one — the eval harness pins a specific version.
    playbook_version: str = Field(default="0.0.0-dev")
    # Path to the counterparty matrix YAML. Resolved relative to
    # the repo root by the loader. The docker-compose entrypoint
    # sets the absolute in-container path (``/playbook/...``).
    counterparty_matrix_path: str = Field(
        default="playbook/counterparty_matrix.yaml"
    )
    # Root directory containing the playbook YAML baselines. Used
    # by the seed script. The default works for ``python -m
    # backend.app.playbook.seed`` run from the repo root AND from
    # inside the docker container (which bind-mounts the playbook
    # directory at ``/playbook``).
    playbook_baselines_root: str = Field(
        default="playbook"
    )

    # --- Audit log (Phase 3) ---
    # Single-operator identifier written into ``decided_by`` on
    # every audit event. The spec calls for the authenticated
    # user identifier; until a real auth layer lands, the config
    # value is authoritative. The audit writer accepts an
    # explicit override (the future ``session.user_id`` path),
    # but defaults to this value everywhere.
    audit_decided_by: str = Field(
        default="clausecraft-operator",
        description="Operator id written into audit_events.decided_by when the writer has no override.",
    )

    # --- Server ---
    backend_port: int = Field(default=18000)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so the env is parsed exactly once per process."""
    return Settings()


settings = get_settings()
