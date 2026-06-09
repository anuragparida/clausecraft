"""Eval-harness fixtures for ``pytest evals/``.

Scope
-----
The eval harness runs the full pipeline (ingest → parse →
classify → dev-spot) on 3 NDA contracts and compares against
hand-written golden YAMLs. The fixtures here exist to make
that run **deterministic, fast, and self-contained**:

- **Cached extraction** — PDF text + per-paragraph metadata
  is cached by file hash, both in-memory and on-disk in
  ``evals/.cache/``. A re-run of the harness on the same
  contracts skips pymupdf entirely on the warm path.
- **Cached embeddings** — every embedding call (the offline
  hash path and the real gateway path) is cached by text
  hash. The offline path is already fast, but the
  SHA-256 + seeded RNG adds up over 30+ clauses per
  contract; the real gateway path is even more expensive
  and is rate-limited.
- **Cached golden YAML loads** — each golden is parsed
  exactly once per pytest session, then reused.
- **Cached mock LLM responses** — the LLM mock returns
  byte-identical responses for the same prompt hash, so a
  re-run hits the in-memory cache and never goes through
  the (mocked) LLM call site twice.
- **Classifier mock** — the classifier calls a real LLM
  unless we patch it. In mock mode we patch the
  classifier's LLM call too, returning the golden's
  ``expected_clauses[].type`` for each clause_id. This is
  the missing piece from the prior runs: only the spotter
  was mocked, so the classifier was hitting the real LLM
  gateway 3x per clause (3 retries, all failing on
  invalid JSON, falling back to rule-based) — which cost
  ~150s per run for nothing.
- **Langfuse no-op** — the spotter writes Langfuse traces.
  In tests we want those to be no-ops, not real HTTP calls.
- **DB session / single event loop** — the harness reuses
  one asyncio event loop for the whole session, avoiding
  the "attached to a different loop" warnings the prior
  runs hit.

Why we mock the LLM rather than use the real one
------------------------------------------------
Two reasons:

1. **Determinism.** A real LLM is non-deterministic. Two
   CI runs on the same golden set would produce different
   F1 numbers and different run reports. The whole point
   of an eval harness is to catch regressions, and that
   requires bit-stable outputs.
2. **CI cost.** Calling a Sonnet-class LLM for every
   contract on every PR is expensive. The mock lets us
   run the eval as part of a fast local test suite.

The harness supports both modes: with the LLM mock
active, the run is a self-test of the harness itself
(does it correctly compare actual flags to expected
flags?). Without the mock (``--run-with-real-llm`` CLI
flag), the harness uses the real LLM and measures real
LLM quality. Phase 2 ships the mock-only mode; the
real-LLM mode is a follow-on card gated on F1
acceptability.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest

# Ensure the backend package is importable. The eval harness
# imports ``app.*`` modules directly; without the sys.path fix
# pytest would fail with ``ModuleNotFoundError: No module
# named 'app'``.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Also make ``evals.*`` importable so test files in this dir
# can use ``from evals.harness import ...`` if they want.
EVALS_DIR = Path(__file__).resolve().parent
if str(EVALS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR.parent))

# Pre-import the shared state module + cache module via
# stable paths. We import them BEFORE any other ``evals``
# module imports so they're registered in ``sys.modules``
# under the canonical names. Subsequent
# ``import evals._state`` from elsewhere resolves to this
# same instance.
from evals import _state  # noqa: E402, F401  -- imported for side effect
from evals import cache  # noqa: E402, F401  -- imported for side effect

logger = logging.getLogger(__name__)


# --- Paths --------------------------------------------------------------


REPO_ROOT_PATH: Path = REPO_ROOT
EVALS_DIR_PATH: Path = EVALS_DIR
CONTRACTS_DIR: Path = REPO_ROOT / "examples" / "contracts"
EXPECTED_DIR: Path = REPO_ROOT / "examples" / "expected"
RUNS_DIR: Path = EVALS_DIR / "runs"


# --- Eval set: 10 contracts (the spec's mandated Phase 2 set) ---------


# The 10-contract eval set as of the 3→10 expansion (card
# t_3050d680). The starter 3 are kept verbatim; 7 more were
# added on 2026-06-08. Layout:
#   public/      nda-001 .. nda-005  (5 public-template-style clean baselines)
#   synthetic/   nda-001, nda-002    (2 stress contracts with hand-injected deviations)
#   hand-curated/ nda-001 .. nda-003  (3 realistic deviation contracts)
# 5 + 2 + 3 = 10.
EVAL_CONTRACTS: list[tuple[str, str]] = [
    ("examples/contracts/public/nda-001.pdf", "examples/expected/public-001.yaml"),
    ("examples/contracts/public/nda-002.pdf", "examples/expected/public-002.yaml"),
    ("examples/contracts/public/nda-003.pdf", "examples/expected/public-003.yaml"),
    ("examples/contracts/public/nda-004.pdf", "examples/expected/public-004.yaml"),
    ("examples/contracts/public/nda-005.pdf", "examples/expected/public-005.yaml"),
    (
        "examples/contracts/synthetic/nda-001.pdf",
        "examples/expected/synthetic-001.yaml",
    ),
    (
        "examples/contracts/synthetic/nda-002.pdf",
        "examples/expected/synthetic-002.yaml",
    ),
    (
        "examples/contracts/hand-curated/nda-001.pdf",
        "examples/expected/hand-curated-001.yaml",
    ),
    (
        "examples/contracts/hand-curated/nda-002.pdf",
        "examples/expected/hand-curated-002.yaml",
    ),
    (
        "examples/contracts/hand-curated/nda-003.pdf",
        "examples/expected/hand-curated-003.yaml",
    ),
]


# --- Real-LLM mode toggle -----------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``--run-with-real-llm``, ``--no-cache``, and ``--language`` flags."""
    parser.addoption(
        "--run-with-real-llm",
        action="store_true",
        default=False,
        help=(
            "Run the eval harness with the real LLM gateway instead "
            "of the deterministic mock. Requires a real "
            "LLM_API_KEY; otherwise the spotter falls back to the "
            "rule-based abstention path (expected)."
        ),
    )
    parser.addoption(
        "--no-cache",
        action="store_true",
        default=False,
        help=(
            "Bypass the on-disk eval cache for this run. Forces a "
            "cold re-extraction / re-embed / re-parse of every "
            "input. The in-memory cache within a single pytest "
            "session is unaffected."
        ),
    )
    parser.addoption(
        "--language",
        action="store",
        default="both",
        choices=("en", "de", "both"),
        help=(
            "Filter the eval set to one language or run both. "
            "Default: both. The per-language F1 split is "
            "reported regardless of the filter; the EN-vs-DE "
            "gap assertions (10% deviation F1, 5% citation "
            "completeness) fire only when both languages are "
            "present in a single run."
        ),
    )


# --- Fixtures ------------------------------------------------------------


@pytest.fixture(scope="session")
def language_filter(request: pytest.FixtureRequest) -> str:
    """The ``--language`` option: ``"en"``, ``"de"``, or ``"both"`` (default).

    The eval_contracts fixture applies this filter so the
    main harness test sees only the contracts in the
    active language. The per-contract smoke tests read
    this option at test time and skip themselves when
    filtered out (they're parametrised at collection time
    over the full eval set; the filter is runtime).
    """
    return str(request.config.getoption("--language"))


@pytest.fixture(scope="session")
def eval_contracts(
    language_filter: str,
) -> list[tuple[Path, Path]]:
    """The 10 eval-set contracts as absolute paths, filtered by language.

    Returns a list of ``(contract_pdf, expected_yaml)`` tuples.
    The language filter (``--language=en|de|both``) is
    applied at fixture-resolution time by reading each
    golden YAML's ``language`` field. The default
    ``"both"`` returns the full 10-contract set; ``"en"``
    or ``"de"`` restrict to that language. When the filter
    excludes every contract (e.g. ``--language=de`` and no
    DE YAMLs exist yet), the list is empty — the harness
    test still runs and the gap assertion is skipped (the
    gap is undefined with one or zero languages).
    """
    pairs: list[tuple[Path, Path]] = []
    for contract_rel, expected_rel in EVAL_CONTRACTS:
        contract_path = REPO_ROOT / contract_rel
        expected_path = REPO_ROOT / expected_rel
        assert contract_path.is_file(), (
            f"Eval contract missing: {contract_path}. The 10-contract "
            f"eval set is part of the spec; missing files are a "
            f"setup error."
        )
        assert expected_path.is_file(), (
            f"Eval golden YAML missing: {expected_path}. The 10 "
            f"eval-set golden YAMLs are hand-written; missing "
            f"files are a setup error."
        )
        # Apply the language filter. The golden YAML is the
        # single source of truth for the contract's language
        # (kept in sync with the per-clause ``language`` field
        # in the actual output).
        if language_filter != "both":
            golden = cache.golden_yaml(expected_path)
            contract_language = golden.get("language", "en")
            if contract_language != language_filter:
                continue
        pairs.append((contract_path, expected_path))
    return pairs


@pytest.fixture(scope="session")
def eval_run_id() -> str:
    """The run id used to name the run report."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@pytest.fixture(scope="session")
def eval_run_report_path(eval_run_id: str) -> Path:
    """The path the harness writes its run report to."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR / f"{eval_run_id}.json"


@pytest.fixture(scope="session")
def real_llm_mode(request: pytest.FixtureRequest) -> bool:
    """``True`` when the harness should call the real LLM."""
    return bool(request.config.getoption("--run-with-real-llm"))


@pytest.fixture(scope="session")
def no_cache_mode(request: pytest.FixtureRequest) -> bool:
    """``True`` when the harness should bypass the on-disk cache."""
    return bool(request.config.getoption("--no-cache"))


# --- Session-scoped event loop -----------------------------------------
#
# The prior runs hit a "Future attached to a different loop" warning
# on the asyncpg pool: each ``asyncio.run(...)`` call in the harness
# created a fresh event loop, but the AsyncAdaptedQueuePool had
# connections bound to a now-closed loop. We solve that by giving the
# whole session ONE event loop, and the harness reuses it via
# ``asyncio.run_coroutine_threadsafe`` from a worker thread, OR
# by deferring to ``loop.run_until_complete`` from inside a synchronous
# test that runs the coroutine on the session-scoped loop directly.
#
# The harness's per-contract runner currently uses
# ``asyncio.run(...)``; we replace that with
# ``loop.run_until_complete(coro)`` below.


@pytest.fixture(scope="session")
def session_event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """A single asyncio event loop for the whole pytest session.

    Yields the running loop. Tests should use ``run_async(coro)`` (a
    helper below) to schedule coroutines on this loop instead of
    calling ``asyncio.run`` (which would create a new loop and break
    the asyncpg pool).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()


def run_async(loop: asyncio.AbstractEventLoop, coro: Any) -> Any:
    """Run a coroutine on ``loop`` and return its result.

    A sync test can call this to drive an async pipeline without
    spawning a new event loop. ``run_until_complete`` blocks the
    caller (the test) until the coroutine returns; that's the same
    semantics as ``asyncio.run`` but on a loop we control.
    """
    return loop.run_until_complete(coro)


# --- Cached wrappers ----------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _install_caches(no_cache_mode: bool) -> Iterator[None]:
    """Auto-use: install cache-backed wrappers for the expensive layers.

    Patches (only when ``real_llm_mode`` is off, since the real-LLM
    path doesn't benefit from a cached mock):

    - ``app.ingest.pdf.extract_pdf`` → cache by file hash, then call
      the real extractor on miss and store the result.
    - ``app.playbook.embeddings.embed_texts`` → cache by text hash,
      return list-of-floats on hit. The downstream caller converts
      back to ``np.ndarray`` (the public API takes lists; this is
      how the real LLM-backed provider also returns embeddings in
      some gateways).
    - ``app.classify.classifier._call_llm_for_classification`` →
      mock that returns the golden's expected ``(type, confidence)``
      for the given clause_id. Cached by prompt hash so a re-run
      is free.
    - ``app.agents.deviation_spotter.spotter._call_llm_for_spot`` →
      mock that returns the golden's expected flag for the given
      clause_id. Cached by prompt hash.

    The ``--no-cache`` flag clears the on-disk cache up front, so
    a cold run goes through the underlying extractors exactly once
    per input. The in-memory cache is unaffected — re-runs within
    a single pytest session still hit it.
    """
    if no_cache_mode:
        cache.clear_all()

    # --- 1. PDF text extraction -------------------------------------
    from app.ingest import pdf as pdf_mod
    from app.ingest import (
        extract_pdf as reexported_extract_pdf,
    )

    real_extract_pdf = pdf_mod.extract_pdf
    real_reexported_extract_pdf = reexported_extract_pdf

    def _reconstruct_pdfdoc(text: str) -> Any:
        """Build a PdfDocument from a cached text blob.

        The harness only reads ``full_text``, ``pages`` (for
        the chunker), and ``char_count``; the scan detector
        is content-based so re-running it on the cached text
        is safe.
        """
        from app.ingest.pdf import (
            PdfDocument,
            PdfPage,
            is_scanned_pdf,
        )
        char_count = len(text)
        scanned = is_scanned_pdf(text)
        warning = (
            f"PDF appears to be scanned (only {char_count} "
            f"extractable chars; threshold is "
            f"{pdf_mod.SCAN_CHAR_THRESHOLD}). OCR is not "
            f"implemented in Phase 1 — the contract will be "
            f"returned with minimal or empty clause text."
            if scanned
            else ""
        )
        return PdfDocument(
            pages=[PdfPage(page_number=1, text=text)],
            full_text=text,
            is_scanned=scanned,
            scanned_warning=warning,
            char_count=char_count,
        )

    def _cached_extract_pdf(data: bytes) -> Any:
        # Try in-memory then on-disk cache. We have to do this
        # manually because the cache module's public API is
        # store-only + miss-only-populator. The simplest
        # pattern is a "read-through" wrapper: try the cache
        # first, fall through to the real extractor on miss,
        # then store the result.
        from evals import cache as _cache
        import hashlib as _hl

        cache_key = f"pdf_text:{_hl.sha256(data).hexdigest()[:32]}"
        with _cache._lock:  # noqa: SLF001 -- intentional cache hit
            hit = _cache._pdf_text_cache.get(cache_key)
        if hit is None:
            disk = _cache._read_disk(cache_key)  # noqa: SLF001
            if isinstance(disk, str):
                hit = disk
                with _cache._lock:  # noqa: SLF001
                    _cache._pdf_text_cache[cache_key] = disk
        if hit is not None:
            return _reconstruct_pdfdoc(hit)
        # Cache miss: extract and store.
        result = real_extract_pdf(data)
        _cache.store_pdf_text(data, result.full_text)
        return result

    # Patch BOTH the underlying module and the re-exported
    # symbol in ``app.ingest`` so the call site
    # (``app.pipeline.stage1_ingest._ingest``) hits the
    # cached version regardless of how it imported
    # ``extract_pdf``. The pipeline module binds
    # ``extract_pdf`` at import time, so we also patch
    # its local reference.
    pdf_mod.extract_pdf = _cached_extract_pdf
    if hasattr(reexported_extract_pdf, "__module__"):
        import app.ingest as _ingest_pkg

        _ingest_pkg.extract_pdf = _cached_extract_pdf

    try:
        from app.pipeline import stage1_ingest as stage1_mod

        real_stage1_extract_pdf = stage1_mod.extract_pdf
        stage1_mod.extract_pdf = _cached_extract_pdf
    except (ImportError, AttributeError):
        real_stage1_extract_pdf = None

    # --- Embedding cache --------------------------------------------
    # The embeddings layer is the per-clause bottleneck in
    # stage3 (one embed_text per clause, even on the
    # offline-hash path — the SHA-256 + seeded RNG cost
    # adds up over 30+ clauses). We wrap embed_texts so a
    # text we've seen before returns the cached vector
    # without recomputing.
    from app.playbook import embeddings as emb_mod

    real_embed_texts = emb_mod.embed_texts
    real_embed_text = emb_mod.embed_text

    def _cached_embed_texts(texts):
        # texts is a Sequence[str]; return a list[EmbeddingResult].
        results = []
        misses = []
        miss_indices = []
        import numpy as _np
        from evals import cache as _cache
        import hashlib as _hl

        for i, t in enumerate(texts):
            digest = _hl.sha256(t.encode("utf-8")).hexdigest()[:32]
            cache_key = f"embedding:{digest}"
            with _cache._lock:  # noqa: SLF001
                hit = _cache._embedding_cache.get(cache_key)
            if hit is None:
                disk = _cache._read_disk(cache_key)  # noqa: SLF001
                if isinstance(disk, list):
                    hit = disk
                    with _cache._lock:  # noqa: SLF001
                        _cache._embedding_cache[cache_key] = disk
            if hit is not None:
                results.append(
                    (i, emb_mod.EmbeddingResult(
                        embedding=_np.asarray(hit, dtype=_np.float32),
                        provider="offline-hash",
                        model=emb_mod.settings.embedding_model,
                    ))
                )
            else:
                misses.append(t)
                miss_indices.append(i)
        # For misses, call the real embedder in one batch and
        # store the results.
        if misses:
            miss_results = real_embed_texts(misses)
            for j, t in enumerate(misses):
                idx = miss_indices[j]
                er = miss_results[j]
                # Persist as a list of floats.
                vec_list = er.embedding.tolist()
                _cache.store_embedding(t, vec_list)
                results.append((idx, er))
        # Sort by original index and return just the values.
        results.sort(key=lambda x: x[0])
        return [r for _, r in results]

    def _cached_embed_text(text):
        results = _cached_embed_texts([text])
        return results[0] if results else None

    emb_mod.embed_texts = _cached_embed_texts
    emb_mod.embed_text = _cached_embed_text

    # Also patch the symbol in app.playbook.store and
    # app.pipeline.stage3_spot (both bind at import time).
    try:
        from app.playbook import store as store_mod

        real_store_embed_text = getattr(store_mod, "embed_text", None)
        if real_store_embed_text is not None:
            store_mod.embed_text = _cached_embed_text
    except (ImportError, AttributeError):
        real_store_embed_text = None
    try:
        from app.pipeline import stage3_spot as stage3_mod

        real_stage3_embed_text = stage3_mod.embed_text
        stage3_mod.embed_text = _cached_embed_text
    except (ImportError, AttributeError):
        real_stage3_embed_text = None

    try:
        yield
    finally:
        pdf_mod.extract_pdf = real_extract_pdf
        if hasattr(reexported_extract_pdf, "__module__"):
            import app.ingest as _ingest_pkg

            _ingest_pkg.extract_pdf = real_reexported_extract_pdf
        if real_stage1_extract_pdf is not None:
            from app.pipeline import stage1_ingest as stage1_mod

            stage1_mod.extract_pdf = real_stage1_extract_pdf
        emb_mod.embed_texts = real_embed_texts
        emb_mod.embed_text = real_embed_text
        if real_store_embed_text is not None:
            from app.playbook import store as store_mod

            store_mod.embed_text = real_store_embed_text
        if real_stage3_embed_text is not None:
            from app.pipeline import stage3_spot as stage3_mod

            stage3_mod.embed_text = real_stage3_embed_text


@pytest.fixture(scope="session", autouse=True)
def _patch_llm_for_mock_mode(
    real_llm_mode: bool,
    mock_payloads: dict[str, Any],
) -> Iterator[None]:
    """Auto-use: patch the classifier + spotter LLM calls in mock mode.

    The mock is **golden-driven**: for each contract, the
    classifier mock returns the golden's expected ``(type,
    confidence)`` per clause_id, and the spotter mock returns
    the golden's expected flag per clause_id. The mock is
    cached by prompt hash so a re-run is byte-identical and
    free.

    The harness sets the active contract key at the start of
    each per-contract pipeline run (via
    :func:`evals._state.set_current_contract_key`); the mock
    reads it back. The classifier doesn't see the contract
    key, so the classifier mock uses the contract key from
    state too.

    In ``--run-with-real-llm`` mode this fixture is a no-op.
    """
    if real_llm_mode:
        yield
        return

    from app.agents.deviation_spotter import spotter as spotter_mod
    from app.classify import classifier as classifier_mod

    real_classify = classifier_mod._call_llm_for_classification
    real_spot = spotter_mod._call_llm_for_spot
    real_key_check_classify = classifier_mod._looks_like_real_key
    real_key_check_spot = spotter_mod._looks_like_real_key

    def _stub_classify(
        clause_text: str,
        *,
        contract_filename: str,
        language: str = "en",
    ) -> tuple[str, float]:
        """Mock classifier: return the golden's expected type for the active contract.

        The classifier is called with ``clause_text`` and
        ``contract_filename``. We look up the active contract
        key (set by the harness) in the mock payload, then
        match ``clause_text`` against the golden's
        ``expected_clauses[].text_excerpt`` (substring match
        is sufficient because the golden excerpts are pinned
        short snippets). The mock returns the golden's
        ``expected_clauses[].type`` (as a string) and a
        confidence of 1.0 — the harness is golden-driven,
        so any real-LLM disagreement would be a harness bug,
        not a spotter bug.

        Phase 4: the real classifier's signature gained a
        ``language`` kwarg (card t_4c21627c wires the DE
        prompt switch off the per-clause ``language``
        field). The mock accepts the kwarg with a default
        so the harness doesn't break when the real
        classifier's signature evolves. The mock payload is
        keyed on contract path, not language, so the
        ``language`` value is informational only here.
        """
        contract_key = _state.get_current_contract_key()
        clause_payload = mock_payloads.get("classify", {}).get(contract_key, [])
        # Find the first golden clause whose text_excerpt is a
        # substring of the clause_text.
        for entry in clause_payload:
            excerpt = entry.get("text_excerpt", "")
            if excerpt and excerpt in clause_text:
                return entry["type"], 1.0
        # No match: return ``unknown`` so the harness records
        # an FP (over-prediction against the golden). This
        # keeps the harness honest in mock mode.
        return "unknown", 0.0

    def _stub_spot(spot_input: Any) -> dict[str, Any]:
        """Mock spotter: return the golden's expected flag for this clause.

        Looks up the current contract key, then the clause_id
        in that contract's golden payload. If the golden
        says this clause should be flagged, returns the
        expected score / rationale / citation / baseline_type.
        If the golden has no entry for this clause, returns
        ``score=0`` with a "no deviation" rationale.
        """
        contract_key = _state.get_current_contract_key()
        payload = mock_payloads.get("spot", {}).get(contract_key, [])
        for entry in payload:
            if entry["clause_id"] == spot_input.clause_id:
                return {
                    "score": entry["score"],
                    "rationale": entry["rationale"],
                    "citation": entry["citation"],
                    "baseline_type": entry["baseline_type"],
                }
        return {
            "score": 0,
            "rationale": "aligned with playbook baseline",
            "citation": None,
            "baseline_type": spot_input.clause_type,
        }

    def _stub_key_check(value: str) -> bool:  # noqa: ARG001
        return True  # always treat as real in mock mode

    classifier_mod._call_llm_for_classification = _stub_classify
    spotter_mod._call_llm_for_spot = _stub_spot
    classifier_mod._looks_like_real_key = _stub_key_check
    spotter_mod._looks_like_real_key = _stub_key_check
    try:
        yield
    finally:
        classifier_mod._call_llm_for_classification = real_classify
        spotter_mod._call_llm_for_spot = real_spot
        classifier_mod._looks_like_real_key = real_key_check_classify
        spotter_mod._looks_like_real_key = real_key_check_spot
        _state.set_current_contract_key("")


# --- Mock payload builders (the "golden-driven" payloads) --------------


def _excerpt_for_clause_id(golden: dict[str, Any], clause_id: str) -> str:
    """Return the ``text_excerpt`` for ``clause_id`` from the golden."""
    for clause in golden.get("expected_clauses") or []:
        if clause.get("id") == clause_id:
            excerpt = clause.get("text_excerpt")
            if isinstance(excerpt, str) and excerpt.strip():
                return excerpt.strip()[:2000]
    return f"[excerpt missing for {clause_id}]"


def _baseline_type_for_clause_id(playbook_clause_id: str) -> str:
    """Map a playbook clause_id (from the golden YAML) to a ClauseType."""
    mapping = {
        "definition-of-confidential-information": "definition_confidential_info",
        "term-of-confidentiality": "term",
        "residual-knowledge": "residual_knowledge",
    }
    return mapping.get(playbook_clause_id, "unknown")


@pytest.fixture(scope="session")
def mock_payloads(eval_contracts: list[tuple[Path, Path]]) -> dict[str, Any]:
    """Build the per-contract mock payloads for both classifier and spotter.

    The classifier payload is keyed by contract and contains a
    list of ``(text_excerpt, type)`` entries — the classifier
    mock matches the clause text against the excerpt and
    returns the type.

    The spotter payload is keyed by contract and contains a
    list of ``(clause_id, score, rationale, citation,
    baseline_type)`` entries — the spotter mock returns the
    flag for the matching clause_id.
    """
    classify_payload: dict[str, list[dict[str, Any]]] = {}
    spot_payload: dict[str, list[dict[str, Any]]] = {}

    for contract_path, expected_path in eval_contracts:
        golden = cache.golden_yaml(expected_path)
        contract_key = str(contract_path.relative_to(REPO_ROOT))

        # Classifier payload: text_excerpt + type for each
        # expected clause. The mock matches the contract's
        # clause text against these excerpts and returns the
        # matching type.
        classify_payload[contract_key] = [
            {
                "text_excerpt": clause["text_excerpt"],
                "type": clause["type"],
            }
            for clause in (golden.get("expected_clauses") or [])
            if "text_excerpt" in clause and "type" in clause
        ]

        # Spotter payload: clause_id + score + rationale +
        # citation + baseline_type for each expected deviation.
        spot_payload[contract_key] = []
        for dev in golden.get("expected_deviations") or []:
            pid = dev["citation"]["playbook_clause_id"]
            excerpt = _excerpt_for_clause_id(golden, dev["clause_id"])
            spot_payload[contract_key].append(
                {
                    "clause_id": dev["clause_id"],
                    "score": dev["severity"],
                    "rationale": dev["rationale"],
                    "citation": {
                        **dev["citation"],
                        "contract_text_excerpt": excerpt,
                    },
                    "baseline_type": _baseline_type_for_clause_id(pid),
                }
            )

    return {"classify": classify_payload, "spot": spot_payload}


@pytest.fixture(scope="session")
def assert_run_report() -> Any:
    """A helper that asserts a run report exists and has the right shape.

    Phase 4: the report shape now includes
    ``aggregate_by_language``, ``gap_assertions``, and
    ``language_filter``. The legacy ``aggregate`` field is
    preserved (still required). The contract-count check
    is against the **active** eval set, not the full
    10-contract list, so a ``--language=en`` run produces
    a 5-contract report and a ``--language=both`` run
    produces a 10-contract report. The
    ``expected_contracts`` field of the report (computed
    by the harness and re-derived here from the contract
    paths) is the source of truth.
    """

    def _assert(report_path: Path, expected_n_contracts: int | None = None) -> dict[str, Any]:
        assert report_path.is_file(), (
            f"Run report not found at {report_path}. The harness "
            f"must write a JSON report at the end of the run."
        )
        with report_path.open() as f:
            data = json.load(f)
        for key in (
            "run_id",
            "started_at",
            "ended_at",
            "contracts",
            "aggregate",
            "aggregate_by_language",
            "gap_assertions",
            "language_filter",
        ):
            assert key in data, f"Run report missing key {key!r}: {list(data.keys())}"
        agg = data["aggregate"]
        for key in (
            "retrieval_f1",
            "classification_f1",
            "deviation_f1",
            "severity_mismatch_count",
            "citation_completeness",
        ):
            assert key in agg, f"Run report aggregate missing key {key!r}"
        # The per-language split must contain at least one
        # language — but only when the run actually ran
        # contracts. A ``--language=de`` run on the current
        # EN-only eval set produces an empty active set, so
        # the per-language aggregate is also empty (no
        # language produced any metrics). The run report's
        # ``language_filter`` field is the source of truth
        # for which languages were filtered.
        agg_by_lang = data["aggregate_by_language"]
        assert isinstance(agg_by_lang, dict)
        if len(data["contracts"]) > 0:
            assert len(agg_by_lang) >= 1, (
                f"aggregate_by_language must contain >=1 language "
                f"when the run produced contracts; got "
                f"{list(agg_by_lang.keys())!r}"
            )
        for lang, lang_agg in agg_by_lang.items():
            for key in (
                "retrieval_f1",
                "classification_f1",
                "deviation_f1",
                "severity_mismatch_count",
                "citation_completeness",
            ):
                assert key in lang_agg, (
                    f"Run report aggregate_by_language[{lang!r}] "
                    f"missing key {key!r}"
                )
        # Gap assertions shape: when both EN and DE are
        # present, the dict has ``deviation_f1``,
        # ``citation_completeness``, ``languages_compared``,
        # ``all_passed``. When fewer languages are present,
        # it has ``languages_compared``, ``skipped=True``,
        # ``skip_reason``.
        gap = data["gap_assertions"]
        assert "languages_compared" in gap, (
            f"gap_assertions missing 'languages_compared': {list(gap.keys())}"
        )
        if gap.get("skipped"):
            assert "skip_reason" in gap, (
                "skipped gap_assertions must include 'skip_reason'"
            )
        else:
            for key in ("deviation_f1", "citation_completeness", "all_passed"):
                assert key in gap, (
                    f"non-skipped gap_assertions missing key {key!r}: "
                    f"{list(gap.keys())}"
                )
            for metric_key in ("deviation_f1", "citation_completeness"):
                m = gap[metric_key]
                for k in ("en", "other", "other_language", "drop", "threshold", "passed"):
                    assert k in m, (
                        f"gap_assertions[{metric_key!r}] missing key "
                        f"{k!r}: {list(m.keys())}"
                    )
        # language_filter is one of the valid choices.
        assert data["language_filter"] in ("en", "de", "both"), (
            f"language_filter must be 'en'|'de'|'both', got "
            f"{data['language_filter']!r}"
        )
        # Contract count matches the active (filtered) eval set.
        assert isinstance(data["contracts"], list)
        if expected_n_contracts is not None:
            assert len(data["contracts"]) == expected_n_contracts, (
                f"Run report should have {expected_n_contracts} "
                f"contracts (active eval set), got {len(data['contracts'])}. "
                f"Either the harness double-counted or the language "
                f"filter wasn't applied."
            )
        else:
            # Fallback for the original Phase 2 assertion: the
            # report must have the same number of contracts as
            # the full unfiltered eval set. Kept for backwards
            # compat with callers that don't pass an explicit
            # expected count.
            assert len(data["contracts"]) == len(EVAL_CONTRACTS), (
                f"Run report should have {len(EVAL_CONTRACTS)} contracts, "
                f"got {len(data['contracts'])}"
            )
        return data

    return _assert
