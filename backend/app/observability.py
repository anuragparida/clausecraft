"""Langfuse observability — Phase 0 stub.

The real Langfuse client is initialized lazily and falls back to a
no-op when the configured keys are obviously placeholders. This lets
the rest of the codebase import ``trace`` / ``get_tracer`` without
needing a real Langfuse instance to boot.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# When True, real Langfuse tracing is wired up. When False, every
# tracing call becomes a no-op that just logs at DEBUG.
_langfuse_enabled: bool = False
_langfuse_client: Any = None


def _looks_like_placeholder(value: str) -> bool:
    """Heuristic: a key containing 'placeholder' or '...n' is not real."""
    lowered = value.lower()
    return "placeholder" in lowered or "...n" in lowered or "***" in value


def init_langfuse(
    host: str,
    public_key: str,
    secret_key: str,
) -> Any:
    """Initialize the Langfuse client. Returns the client (real or no-op).

    Safe to call multiple times — the first successful init wins.
    """
    global _langfuse_enabled, _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client
    if _looks_like_placeholder(public_key) or _looks_like_placeholder(secret_key):
        logger.info(
            "Langfuse keys look like placeholders; running in no-op tracing mode "
            "(host=%s). Real keys must be supplied to enable tracing.",
            host,
        )
        _langfuse_client = _NoopLangfuse()
        _langfuse_enabled = False
        return _langfuse_client

    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]

        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        _langfuse_client = client
        _langfuse_enabled = True
        logger.info("Langfuse client initialized (host=%s)", host)
        return client
    except Exception:  # noqa: BLE001
        logger.exception("Failed to initialize Langfuse; falling back to no-op.")
        _langfuse_client = _NoopLangfuse()
        _langfuse_enabled = False
        return _langfuse_client


class _NoopSpan:
    """Context manager that does nothing and accepts arbitrary kwargs."""

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def update(self, **_kwargs: Any) -> None:
        return None

    def end(self, **_kwargs: Any) -> None:
        return None


class _NoopLangfuse:
    """Drop-in replacement for ``langfuse.Langfuse`` when tracing is off."""

    def trace(self, *_args: Any, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()

    def span(self, *_args: Any, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()

    def generation(self, *_args: Any, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def is_tracing_enabled() -> bool:
    """True if a real Langfuse client is wired up."""
    return _langfuse_enabled


def get_langfuse() -> Any:
    """Return the active Langfuse client (real or no-op).

    Safe to call from anywhere — the first call initialises the
    client with the configured host/keys. Subsequent calls return
    the cached singleton.
    """
    global _langfuse_client
    if _langfuse_client is None:
        # Lazy import to avoid a circular dep with app.config.
        from app.config import settings

        return init_langfuse(
            host=settings.langfuse_host,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )
    return _langfuse_client
