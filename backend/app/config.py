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

    # --- LLM (Phase 1: classifier only) ---
    # Uses an OpenAI-compatible client so the same code path works with
    # Anthropic-via-OpenRouter, OpenAI directly, or a local gateway.
    # When the key is a placeholder the classifier falls back to a
    # deterministic rule-based pass so the pipeline still produces
    # non-null types for the 5 test contracts.
    llm_api_key: str = Field(default="placeholder-not-a-real-key")
    llm_base_url: str = Field(default="https://openrouter.ai/api/v1")
    llm_model: str = Field(default="anthropic/claude-3.5-sonnet")

    # --- Embeddings (Phase 2: playbook store) ---
    # Uses the same OpenAI-compatible client as the LLM calls
    # above. Default points at the OpenRouter ``/embeddings``
    # endpoint, which exposes bge-m3 (``baai/bge-m3``) among
    # others. The dimension is the bge-m3 native dimension; the
    # store asserts the gateway returns vectors of this length.
    embedding_api_key: str = Field(default="placeholder-not-a-real-key")
    embedding_base_url: str = Field(default="https://openrouter.ai/api/v1")
    embedding_model: str = Field(default="baai/bge-m3")
    embedding_dim: int = Field(default=1024, ge=64, le=4096)

    # --- Playbook / counterparty (Phase 2) ---
    playbook_version: str = Field(default="0.0.0-dev")
    counterparty_matrix_path: str = Field(
        default="playbook/counterparty_matrix.yaml"
    )

    # --- Server ---
    backend_port: int = Field(default=18000)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so the env is parsed exactly once per process."""
    return Settings()


settings = get_settings()
