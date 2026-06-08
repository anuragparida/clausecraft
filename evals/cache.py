"""Process-wide caches for the eval harness.

The harness re-runs the pipeline against the same 3 contracts
every time. Without caching, every run pays for:

- PDF text extraction (pymupdf parse, paragraph metadata build)
- Embedding lookups (even on the offline-hash path, the SHA-256
  and the seeded RNG work costs a few ms per call)
- Golden YAML parsing (3 small files, but parsing isn't free)
- Mock LLM dispatch (a tiny per-call cost, but adds up over
  7+21+7 = ~35 clauses per run)

We cache all of these. The cache lives in two places:

- **In-memory dicts** — fastest, scoped to the current Python
  process. Re-runs in the same pytest session hit these for
  free.
- **On-disk JSON files** in ``evals/.cache/`` — survives
  across pytest invocations. PDF text, embeddings, and golden
  YAMLs land here, keyed by their input hash. A fresh
  ``pytest evals/harness.py`` run on a warm cache takes a
  few seconds; on a cold cache (first run after ``make
  clean``) it takes the full ~30s of the real pipeline.

The cache keys are content-addressed (SHA-256 of the input
bytes or text), so a contract PDF changing on disk
invalidates that key automatically. There is no manual
invalidation step.

Why a custom cache rather than e.g. ``functools.lru_cache``
on the underlying functions:
- We want the disk layer too (process restart survival).
- We want to clear the cache deliberately (e.g. when the
  eval set version bumps, the ``CONTRACT_SET_VERSION``
  constant in harness.py changes, and the on-disk files
  keyed by hash of contract bytes are still valid — but
  the user might want to nuke them). ``evals/.cache/`` is
  trivial to ``rm -rf`` between runs.
- The cached values are simple JSON-serialisable shapes
  (strings, lists of strings, lists of float32 lists). No
  need for pickle / dill.

Hard rules from the kanban card: this is *not* a layer of
correctness, it's a layer of speed. A regression in the
cache (wrong key, stale value) should be caught by the
harness's correctness assertions, not by the cache itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Root of the on-disk cache. Settable via the
#: ``CLAUSECRAFT_EVAL_CACHE`` env var so a CI job can point
#: at a faster filesystem (e.g. tmpfs) without code changes.
_CACHE_DIR_ENV = "CLAUSECRAFT_EVAL_CACHE"

#: Default location: ``evals/.cache/`` next to the harness.
#: The directory is git-ignored (see ``evals/.cache/.gitignore``).
_DEFAULT_CACHE_DIR = (
    Path(__file__).resolve().parent / ".cache"
)


# --- Internal state -----------------------------------------------------


_lock = threading.Lock()
_pdf_text_cache: dict[str, str] = {}
_pdf_paragraphs_cache: dict[str, list[dict[str, Any]]] = {}
_embedding_cache: dict[str, list[float]] = {}
_golden_yaml_cache: dict[str, dict[str, Any]] = {}
_prompt_response_cache: dict[str, dict[str, Any]] = {}


def _cache_dir() -> Path:
    """Resolve the on-disk cache directory, creating it if needed."""
    path = Path(os.environ.get(_CACHE_DIR_ENV, str(_DEFAULT_CACHE_DIR)))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _key(prefix: str, payload: bytes | str) -> str:
    """Build a content-addressed cache key.

    ``prefix`` namespaces the key (so a PDF-text key can't
    collide with an embedding key). ``payload`` is hashed
    with SHA-256; both bytes and str are accepted.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _disk_path(key: str) -> Path:
    """Resolve the on-disk JSON file for ``key``."""
    return _cache_dir() / f"{key}.json"


def _read_disk(key: str) -> Optional[Any]:
    """Return the on-disk value for ``key`` (or ``None`` if missing/corrupt)."""
    path = _disk_path(key)
    if not path.is_file():
        return None
    try:
        with path.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("cache: failed to read %s (%s); treating as miss", path, exc)
        return None


def _write_disk(key: str, value: Any) -> None:
    """Persist ``value`` to ``key``. Silently swallow IO errors so a
    read-only cache directory doesn't break the harness — we just
    degrade to in-memory caching."""
    try:
        path = _disk_path(key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w") as f:
            json.dump(value, f, separators=(",", ":"))
        tmp.replace(path)
    except OSError as exc:
        logger.debug("cache: failed to write %s (%s); continuing in-memory", key, exc)


# --- Public API ---------------------------------------------------------


def clear_all() -> None:
    """Drop both the in-memory and on-disk caches.

    Used by the harness's ``--no-cache`` flag and by
    contributor scripts that want a clean run. The disk
    cache is removed wholesale (faster than per-key deletes
    when the user wants a clean slate).
    """
    with _lock:
        _pdf_text_cache.clear()
        _pdf_paragraphs_cache.clear()
        _embedding_cache.clear()
        _golden_yaml_cache.clear()
        _prompt_response_cache.clear()
    cache_dir = _cache_dir()
    if cache_dir.is_dir():
        for path in cache_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                pass


def pdf_text(pdf_bytes: bytes) -> str:
    """Cached PDF text extraction.

    ``pdf_bytes`` is hashed; identical inputs return identical
    outputs across runs and processes. The cached value is
    the joined text (no per-paragraph metadata) — see
    :func:`pdf_paragraphs` for the structured form.
    """
    key = _key("pdf_text", pdf_bytes)
    with _lock:
        cached = _pdf_text_cache.get(key)
    if cached is not None:
        return cached
    disk = _read_disk(key)
    if disk is not None and isinstance(disk, str):
        with _lock:
            _pdf_text_cache[key] = disk
        return disk
    # Cache miss: the actual extraction lives in
    # ``app.ingest.pdf``; the harness is responsible for calling
    # this cache and populating it. This module is the *storage
    # layer* — the harness wraps the ingest call. See
    # ``evals.conftest._cached_extract_pdf``.
    raise RuntimeError(
        "evals.cache.pdf_text called as a miss-populator. "
        "Use evals.conftest's cached extractor wrapper instead."
    )


def store_pdf_text(pdf_bytes: bytes, text: str) -> None:
    """Populate the PDF text cache (called by the cached wrapper)."""
    key = _key("pdf_text", pdf_bytes)
    with _lock:
        _pdf_text_cache[key] = text
    _write_disk(key, text)


def pdf_paragraphs(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Cached PDF paragraphs (text + per-paragraph metadata)."""
    key = _key("pdf_paragraphs", pdf_bytes)
    with _lock:
        cached = _pdf_paragraphs_cache.get(key)
    if cached is not None:
        return cached
    disk = _read_disk(key)
    if disk is not None and isinstance(disk, list):
        with _lock:
            _pdf_paragraphs_cache[key] = disk
        return disk
    raise RuntimeError(
        "evals.cache.pdf_paragraphs called as a miss-populator. "
        "Use evals.conftest's cached extractor wrapper instead."
    )


def store_pdf_paragraphs(pdf_bytes: bytes, paragraphs: list[dict[str, Any]]) -> None:
    key = _key("pdf_paragraphs", pdf_bytes)
    with _lock:
        _pdf_paragraphs_cache[key] = paragraphs
    _write_disk(key, paragraphs)


def embedding(text: str) -> list[float]:
    """Cached embedding vector for ``text`` (as a list of floats)."""
    key = _key("embedding", text)
    with _lock:
        cached = _embedding_cache.get(key)
    if cached is not None:
        return cached
    disk = _read_disk(key)
    if disk is not None and isinstance(disk, list):
        with _lock:
            _embedding_cache[key] = disk
        return disk
    raise RuntimeError(
        "evals.cache.embedding called as a miss-populator. "
        "Use the cached wrapper in evals.conftest instead."
    )


def store_embedding(text: str, vector: list[float]) -> None:
    key = _key("embedding", text)
    with _lock:
        _embedding_cache[key] = vector
    _write_disk(key, vector)


def golden_yaml(path: Path) -> dict[str, Any]:
    """Cached golden YAML load (parses once, reuses the dict)."""
    p = Path(path).resolve()
    key = str(p)
    with _lock:
        cached = _golden_yaml_cache.get(key)
    if cached is not None:
        return cached
    import yaml  # local import; not all callers need yaml

    with p.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(
            f"Golden YAML at {p} did not parse as a dict; got {type(data).__name__}"
        )
    with _lock:
        _golden_yaml_cache[key] = data
    return data


def prompt_response(prompt_hash: str) -> Optional[dict[str, Any]]:
    """Return the cached LLM mock response for a prompt hash, or None."""
    with _lock:
        return _prompt_response_cache.get(prompt_hash)


def store_prompt_response(prompt_hash: str, response: dict[str, Any]) -> None:
    """Persist a mock LLM response keyed by prompt hash.

    Used by the classifier + spotter mock fixtures so a re-run
    returns byte-identical responses for the same input. The
    prompt hash is built by the caller (typically
    ``hashlib.sha256(prompt.encode()).hexdigest()``).
    """
    with _lock:
        _prompt_response_cache[prompt_hash] = response


def stats() -> dict[str, int]:
    """Return a snapshot of the in-memory cache sizes (for diagnostics)."""
    with _lock:
        return {
            "pdf_text": len(_pdf_text_cache),
            "pdf_paragraphs": len(_pdf_paragraphs_cache),
            "embeddings": len(_embedding_cache),
            "golden_yamls": len(_golden_yaml_cache),
            "prompt_responses": len(_prompt_response_cache),
        }


__all__ = [
    "clear_all",
    "pdf_text",
    "store_pdf_text",
    "pdf_paragraphs",
    "store_pdf_paragraphs",
    "embedding",
    "store_embedding",
    "golden_yaml",
    "prompt_response",
    "store_prompt_response",
    "stats",
]
