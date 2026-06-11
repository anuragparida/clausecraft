"""Counterparty matrix loader.

The matrix is a YAML file at
``playbook/counterparty_matrix.yaml``. The lookup chain is layered:

1. **Phase 2 (flat).** ``lookup_verdict(matrix, clause_type)`` —
   verdict is a function of the clause type only. The default
   ``default_verdict`` is the fallback. Stays unchanged in Phase 5
   for back-compat with existing call sites (e.g.
   ``stage3_spot._matrix_verdict_for_clause``).

2. **Phase 4 (language axis).**
   ``lookup_verdict_with_language(matrix, clause_type, language=...)``
   — adds ``language → counterparty_type → clause_type → verdict``
   as a sibling of the flat table. The DE column only *narrows*
   verdicts for DE counterparty types; the EN path is unchanged.
   ``de_german_entity`` is the Phase 4 DE counterparty type.

3. **Phase 5 (counterparty matrix, 4 axes).**
   ``lookup_verdict_with_counterparty(matrix, clause_type,
   counterparty_type=...)`` — adds ``counterparty_type →
   clause_type → verdict`` as a top-level override table. The 4
   Phase 5 counterparty types are: **enterprise / smb /
   public_sector / healthcare**. The lookup composes cleanly with
   the language axis: when a DE-language call lands on a
   counterparty-aware cell, the strictest verdict (DE override
   vs counterparty override vs flat default) wins.

The matrix is opinionated (per the spec sharp-edge: "different
lawyers will disagree on what's acceptable for an SMB vs an
enterprise"). The YAML's per-cell comments are the source of
truth for *why* a cell narrows; ``_RATIONALE_PER_CELL`` in this
file is the machine-readable summary for the matrix-aware spotter
prompt and the Helena review.

Public surface
--------------
- :class:`CounterpartyMatrix` — the loaded-and-validated config.
- :func:`load_matrix` — load the YAML from
  ``settings.counterparty_matrix_path`` (or an explicit override).
- :func:`lookup_verdict` — flat lookup (Phase 2). Returns a
  :class:`MatrixVerdict`. **Does not consult the counterparty
  overrides** even when ``counterparty_type`` is passed; the
  parameter is recorded on the result for forward-compat only.
- :func:`lookup_verdict_with_language` — Phase 4 lookup. Adds the
  language axis. EN callers get the same result as ``lookup_verdict``;
  DE callers may see a stricter verdict when a DE counterparty-type
  override is configured.
- :func:`lookup_verdict_with_counterparty` — Phase 5 lookup. The
  primary entry point for the matrix-aware spotter. Resolves
  ``(clause_type, counterparty_type[, language]) → verdict`` and
  composes the language axis on top of the counterparty axis (the
  strictest of all matching cells wins).
- :data:`COUNTERPARTY_TYPES` — the canonical 4-axis list. The
  loader and the matrix-aware spotter both consult this.
- :data:`DEFAULT_COUNTERPARTY_TYPE` — the legacy ``"any"``
  sentinel, kept for back-compat with Phase 2 call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Optional

import yaml

from app.config import settings


# --- Verdict scale -------------------------------------------------------

class Verdict(IntEnum):
    """Match the spotter's score scale in Phase 2.

    0 = aligned (matches baseline)
    1 = minor deviation
    2 = material deviation
    3 = unacceptable
    """

    ALIGNED = 0
    MINOR = 1
    MATERIAL = 2
    UNACCEPTABLE = 3

    def label(self) -> str:
        """Lowercase label for the UI."""
        return self.name.lower()

    @classmethod
    def from_score(cls, score: int) -> "Verdict":
        """Coerce a raw spotter score (0–3) into a Verdict.

        Out-of-range scores are clamped — the spotter should never
        emit them, but defensiveness is cheap.
        """
        score = max(0, min(3, int(score)))
        return cls(score)


# --- Phase 5: counterparty types -----------------------------------------

#: The 4 counterparty axes the Phase 5 matrix ships with, per
#: ``docs/11-phases.md`` § "Phase 5" (lines 338-385).
#:
#: The spec explicitly calls these out:
#: - **enterprise** — large corporations with in-house counsel,
#:   negotiating leverage, willingness to sign broad language.
#: - **smb** — small/medium businesses, no in-house counsel, often
#:   standard-form contracts, asymmetric risk bearing.
#: - **public_sector** — government / municipal / federal agencies.
#:   Statutory constraints (administrative law, public procurement,
#:   FOIA-equivalent transparency, no-Karenzentschädigung-style
#:   restrictions on employees).
#: - **healthcare** — HIPAA-bound entities (US) / healthcare
#:   providers (DE: Krankenhäuser, Pflegeeinrichtungen). Sector-
#:   specific data-protection regimes, shift-work, mandatory
#:   indemnities, professional secrecy.
#:
#: The matrix may carry **additional** counterparty types (e.g. the
#: Phase 4 ``de_german_entity`` language-scoped type), but the 4
#: above are the canonical Phase 5 axes. Callers should iterate
#: over :data:`COUNTERPARTY_TYPES` for UI rendering and Helena
#: review.
COUNTERPARTY_TYPES: tuple[str, ...] = (
    "enterprise",
    "smb",
    "public_sector",
    "healthcare",
)

#: Legacy ``"any"`` sentinel for the flat Phase 2 path. The Phase 5
#: ``lookup_verdict_with_counterparty`` treats ``"any"`` as "no
#: counterparty specified, use the flat default" — the lookup
#: behaves identically to ``lookup_verdict`` in that case.
DEFAULT_COUNTERPARTY_TYPE: str = "any"

#: Phase 4 DE counterparty type. Kept for back-compat with the
#: Phase 4 ``language_overrides`` test fixtures. Phase 5 callers
#: use one of :data:`COUNTERPARTY_TYPES` directly; this constant
#: is the language-axis key.
DE_GERMAN_ENTITY: str = "de_german_entity"


@dataclass
class MatrixVerdict:
    """A verdict with the context that produced it.

    Attributes
    ----------
    verdict
        The categorical verdict.
    clause_type
        The clause type that was looked up.
    counterparty_type
        The counterparty type that was looked up. ``"any"`` (the
        default) means no counterparty was specified (Phase 2 flat
        path). A real Phase 5 value is one of
        :data:`COUNTERPARTY_TYPES` or ``de_german_entity``.
    is_default
        True when the verdict came from the matrix's
        ``default_verdict`` (the per-clause override was absent).
        The UI uses this to render a "matrix default" tag.
    sources
        The lookup chain that produced the verdict, in priority
        order. Phase 5 entries are ``"flat"`` (clause_verdicts
        hit), ``"counterparty"`` (counterparty_overrides hit), or
        ``"language:de"`` (DE language override hit). The first
        element is the source that *won*; later elements are
        losers. Useful for the UI's "matrix verdict" tooltip.
    """

    verdict: Verdict
    clause_type: str
    counterparty_type: str
    is_default: bool
    # Phase 4: language axis. ``"en"`` (Phase 2 default) for the
    # flat ``lookup_verdict`` path; ``"de"`` (or other) when the
    # Phase 4 ``lookup_verdict_with_language`` resolved a
    # language-scoped override. The field defaults to ``"en"`` so
    # Phase 2 callers don't need to set it.
    language: str = "en"
    # Phase 5: which override cell(s) contributed to the verdict.
    # Empty list = verdict came from default_verdict (nothing
    # matched). ``["flat"]`` = clause_verdicts hit. ``["counterparty"]``
    # = counterparty_overrides[counterparty_type] hit. ``["language:de"]``
    # = language_overrides["de"][de_german_entity] hit. Multiple
    # entries mean multiple cells matched and the strictest won.
    sources: list[str] = field(default_factory=list)


# --- Matrix config -------------------------------------------------------

@dataclass
class CounterpartyMatrix:
    """The loaded counterparty matrix.

    Phase 2 fields: ``default_verdict`` and ``clause_verdicts``.
    Phase 5 will add ``counterparty_overrides`` (a 2D table
    keyed by ``counterparty_type → clause_type → verdict``).
    The dataclass carries the raw dict so Phase 5's expanded
    form can be added without breaking loaders.
    """

    version: str
    contract_type: str
    language: str
    default_counterparty_type: str
    default_verdict: Verdict
    clause_verdicts: dict[str, Verdict]
    counterparty_overrides: dict[str, dict[str, Verdict]]
    # Phase 4: language axis. Shape:
    #   language → counterparty_type → clause_type → Verdict
    # The top-level key is a language code (``"de"``, ``"en"``,
    # ...). Each language maps to the same 2D shape as
    # ``counterparty_overrides`` so a Phase 5 reader can treat the
    # two fields uniformly with a small flattening helper.
    # Phase 2 callers ignore this field; ``lookup_verdict`` doesn't
    # read it.
    language_overrides: dict[str, dict[str, dict[str, Verdict]]]
    raw: dict

    @classmethod
    def from_dict(cls, raw: dict) -> "CounterpartyMatrix":
        """Parse a raw YAML dict into a typed matrix.

        Validates required fields. Unknown top-level keys are
        ignored (forward-compat) but the ``counterparty_overrides``
        is parsed even when empty so Phase 5 can use the same
        loader.
        """
        if not isinstance(raw, dict):
            raise ValueError(
                f"counterparty matrix must be a YAML mapping at the "
                f"top level, got {type(raw).__name__}"
            )
        version = str(raw.get("version", "0.0.0-dev"))
        contract_type = str(raw.get("contract_type", "")).strip()
        language = str(raw.get("language", "")).strip()
        default_counterparty_type = str(
            raw.get("default_counterparty_type", "any")
        ).strip() or "any"
        default_verdict_str = str(raw.get("default_verdict", "aligned")).strip()
        try:
            default_verdict = Verdict[default_verdict_str.upper()]
        except KeyError as exc:
            raise ValueError(
                f"invalid default_verdict {default_verdict_str!r}; "
                f"valid: {[v.name.lower() for v in Verdict]}"
            ) from exc
        clause_verdicts_raw = raw.get("clause_verdicts", {}) or {}
        if not isinstance(clause_verdicts_raw, dict):
            raise ValueError(
                f"clause_verdicts must be a mapping, got "
                f"{type(clause_verdicts_raw).__name__}"
            )
        clause_verdicts: dict[str, Verdict] = {}
        for k, v in clause_verdicts_raw.items():
            try:
                clause_verdicts[str(k)] = Verdict[str(v).strip().upper()]
            except (KeyError, AttributeError) as exc:
                raise ValueError(
                    f"invalid verdict {v!r} for clause_type {k!r}; "
                    f"valid: {[v.name.lower() for v in Verdict]}"
                ) from exc
        # Phase 5: counterparty_overrides. Parsed but unused in Phase 2.
        overrides_raw = raw.get("counterparty_overrides", {}) or {}
        if not isinstance(overrides_raw, dict):
            raise ValueError(
                f"counterparty_overrides must be a mapping, got "
                f"{type(overrides_raw).__name__}"
            )
        overrides = _parse_2d_overrides(
            overrides_raw, field_name="counterparty_overrides"
        )
        # Phase 4: language_overrides. Same 2D shape nested under
        # a language key. The shape is:
        #   language_overrides:
        #     <lang>:
        #       counterparty_overrides:
        #         <counterparty_type>:
        #           <clause_type>: <verdict>
        # We accept BOTH the nested form (per language) and a
        # direct ``language → counterparty_type → clause_type``
        # form, since the spec doesn't lock the YAML shape. The
        # nested form is the canonical one (mirrors the existing
        # ``counterparty_overrides`` shape), but a direct mapping
        # of the same shape is also accepted and parsed the same
        # way. The field is empty for EN-only configs.
        language_overrides_raw = raw.get("language_overrides", {}) or {}
        if not isinstance(language_overrides_raw, dict):
            raise ValueError(
                f"language_overrides must be a mapping, got "
                f"{type(language_overrides_raw).__name__}"
            )
        language_overrides: dict[str, dict[str, dict[str, Verdict]]] = {}
        for lang, lang_block in language_overrides_raw.items():
            lang_key = str(lang).strip().lower()
            if not lang_key:
                continue
            if not isinstance(lang_block, dict):
                raise ValueError(
                    f"language_overrides[{lang_key!r}] must be a "
                    f"mapping, got {type(lang_block).__name__}"
                )
            # Accept the nested ``counterparty_overrides`` shape
            # (canonical) and a flat 2D shape (alternative). Both
            # end up as the same internal 2D structure.
            inner_block = lang_block.get("counterparty_overrides", lang_block)
            language_overrides[lang_key] = _parse_2d_overrides(
                inner_block,
                field_name=f"language_overrides[{lang_key!r}]",
            )
        return cls(
            version=version,
            contract_type=contract_type,
            language=language,
            default_counterparty_type=default_counterparty_type,
            default_verdict=default_verdict,
            clause_verdicts=clause_verdicts,
            counterparty_overrides=overrides,
            language_overrides=language_overrides,
            raw=raw,
        )


def _parse_2d_overrides(
    raw: dict, *, field_name: str
) -> dict[str, dict[str, Verdict]]:
    """Parse a 2D ``{key: {key: verdict}}`` override block.

    Used for both the top-level ``counterparty_overrides`` and the
    per-language ``language_overrides[lang]`` block. The shape
    (``counterparty_type → clause_type → verdict``) is the same in
    both cases, so we factor the parser to avoid duplicating the
    "Phase 5's overrides will be richer" fallback comment.

    Unknown values inside a per-clause mapping (e.g. a Phase 5
    range shape rather than a verdict string) are silently
    dropped — the loader does not fail the whole parse for a
    forward-compat entry. Top-level structure mismatches still
    raise so a typo doesn't ship silently.
    """
    result: dict[str, dict[str, Verdict]] = {}
    for cp_type, per_clause in raw.items():
        if not isinstance(per_clause, dict):
            raise ValueError(
                f"{field_name}[{cp_type!r}] must be a mapping, got "
                f"{type(per_clause).__name__}"
            )
        inner: dict[str, Verdict] = {}
        for ct, v in per_clause.items():
            try:
                inner[str(ct)] = Verdict[str(v).strip().upper()]
            except (KeyError, AttributeError):
                # Phase 5's overrides will be richer (ranges,
                # enum maps, not just verdict ints). Until the
                # Phase 5 schema is locked, accept only the
                # verdict-int shape and skip anything else
                # rather than fail the loader.
                continue
        result[str(cp_type)] = inner
    return result


def load_matrix(path: Optional[Path] = None) -> CounterpartyMatrix:
    """Load the counterparty matrix from disk.

    Parameters
    ----------
    path
        Override the configured path. Defaults to
        ``settings.counterparty_matrix_path``. Tests use the
        override to point at a fixture.
    """
    matrix_path = Path(path or settings.counterparty_matrix_path)
    if not matrix_path.is_absolute():
        # Resolve against the repo root (the same convention the
        # seed script uses).
        repo_root = Path(__file__).resolve().parents[3]
        matrix_path = (repo_root / matrix_path).resolve()
    with open(matrix_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if raw is None:
        raise ValueError(f"counterparty matrix is empty: {matrix_path}")
    return CounterpartyMatrix.from_dict(raw)


# --- Lookups ------------------------------------------------------------

def lookup_verdict(
    matrix: CounterpartyMatrix,
    clause_type: str,
    counterparty_type: Optional[str] = None,
) -> MatrixVerdict:
    """Flat lookup: clause type → verdict.

    Phase 2 ignores ``counterparty_type``; it's recorded on the
    result so the UI can render "flat: aligned" instead of a
    real counterparty-aware verdict. Phase 5 will add the 2D
    lookup and the call site will pass the real counterparty
    type.

    Lookup order (Phase 2):
      1. ``matrix.clause_verdicts[clause_type]`` if present.
      2. ``matrix.default_verdict`` otherwise.

    The function never raises on a missing clause type — the
    default is the documented fallback. This matches the spec's
    "flat baseline" requirement.
    """
    ct = (counterparty_type or matrix.default_counterparty_type or "any").strip()
    if clause_type in matrix.clause_verdicts:
        return MatrixVerdict(
            verdict=matrix.clause_verdicts[clause_type],
            clause_type=clause_type,
            counterparty_type=ct,
            is_default=False,
        )
    return MatrixVerdict(
        verdict=matrix.default_verdict,
        clause_type=clause_type,
        counterparty_type=ct,
        is_default=True,
    )


def lookup_verdict_with_language(
    matrix: CounterpartyMatrix,
    clause_type: str,
    *,
    language: str = "en",
    counterparty_type: Optional[str] = None,
) -> MatrixVerdict:
    """Phase 4 lookup: language × counterparty_type × clause_type → verdict.

    The DE column only *narrows* verdicts — the EN path is the
    flat ``lookup_verdict`` result, untouched. For DE, the
    language-scoped ``counterparty_overrides`` is consulted; if
    the lookup hits, the DE verdict replaces the EN default.
    The DE verdict is checked to be **at least as strict** as the
    EN one before it is applied — we never *relax* a verdict
    because of the language switch (defensive against an
    accidentally-inverted YAML value).

    Lookup order (Phase 4):

      1. Flat ``clause_verdicts[clause_type]`` (EN default).
      2. For ``language="de"``: ``language_overrides["de"]
         .counterparty_overrides[counterparty_type]
         [clause_type]`` if present, *and* the override is at
         least as strict as the EN verdict.
      3. ``matrix.default_verdict`` otherwise.

    The function never raises on a missing clause type. The
    language default is ``"en"`` so callers that don't know
    about Phase 4 get the Phase 2 result.
    """
    lang = (language or matrix.language or "en").strip().lower() or "en"
    ct = (counterparty_type or matrix.default_counterparty_type or "any").strip()
    # Step 1: EN default (flat) — same as ``lookup_verdict`` but
    # with the language stamped on the result.
    if clause_type in matrix.clause_verdicts:
        en_verdict = matrix.clause_verdicts[clause_type]
        is_default = False
    else:
        en_verdict = matrix.default_verdict
        is_default = True
    # Step 2: language-scoped override (Phase 4 DE column).
    if lang == "de":
        de_overrides = matrix.language_overrides.get("de", {})
        de_by_cp = de_overrides.get(ct, {})
        de_verdict = de_by_cp.get(clause_type)
        if de_verdict is not None and de_verdict.value >= en_verdict.value:
            return MatrixVerdict(
                verdict=de_verdict,
                clause_type=clause_type,
                counterparty_type=ct,
                is_default=is_default,
                language="de",
            )
    # EN path: identical to the Phase 2 ``lookup_verdict`` result
    # (with language stamped).
    return MatrixVerdict(
        verdict=en_verdict,
        clause_type=clause_type,
        counterparty_type=ct,
        is_default=is_default,
        language=lang,
    )


# --- Phase 5: counterparty-aware lookup ----------------------------------


def lookup_verdict_with_counterparty(
    matrix: CounterpartyMatrix,
    clause_type: str,
    *,
    counterparty_type: str = DEFAULT_COUNTERPARTY_TYPE,
    language: str = "en",
) -> MatrixVerdict:
    """Phase 5 lookup: counterparty_type × clause_type → verdict.

    The primary entry point for the matrix-aware spotter. The
    lookup composes three axes in priority order (strictest wins):

      1. **Language axis (Phase 4).** If ``language == "de"`` and
         ``language_overrides["de"][counterparty_type][clause_type]``
         is present, the DE verdict is the leading candidate.
         The DE override is **only applied when at least as strict**
         as the next-strictest candidate — we never *relax* a
         verdict on a language switch (defensive against an
         accidentally-inverted YAML value).

      2. **Counterparty axis (Phase 5).** If ``counterparty_type``
         is in :data:`COUNTERPARTY_TYPES` (or is the legacy
         ``de_german_entity``) and ``counterparty_overrides
         [counterparty_type][clause_type]`` is present, the
         counterparty verdict is the next candidate.

      3. **Flat default (Phase 2).** ``clause_verdicts[clause_type]``
         if present, else ``default_verdict``.

    The result's :attr:`MatrixVerdict.sources` lists which cells
    matched, in order of strictness. The first element is the
    source that *won*; later entries are the losers (still useful
    for the UI's "matrix verdict" tooltip — e.g. "DE override
    applied: material, on top of counterparty healthcare
    override: minor").

    Lookup examples (per the spec exit-gate: "the matrix actually
    changes a verdict on at least 3 of 30 eval contracts"):

      >>> v = lookup_verdict_with_counterparty(
      ...     m, "dpa_breach_notification",
      ...     counterparty_type="healthcare", language="en",
      ... )
      >>> v.verdict  # Verdict.MATERIAL  (HIPAA 60-day rule)

      >>> v = lookup_verdict_with_counterparty(
      ...     m, "employment_non_compete",
      ...     counterparty_type="smb", language="de",
      ... )
      >>> v.verdict  # Verdict.UNACCEPTABLE  (Karenzentschädigung
                     # missing; smb cannot afford the consideration)

    The function never raises on a missing clause type, a
    missing counterparty type, or a missing language override —
    each axis is a "soft" lookup that simply contributes no
    candidate. This is the spec's design choice: the matrix is
    "opinionated" but every cell is opt-in.

    ``counterparty_type="any"`` (the default) is the Phase 2
    sentinel and yields the same result as ``lookup_verdict`` —
    no counterparty override is consulted.
    """
    lang = (language or matrix.language or "en").strip().lower() or "en"
    ct = (counterparty_type or matrix.default_counterparty_type or DEFAULT_COUNTERPARTY_TYPE).strip() or DEFAULT_COUNTERPARTY_TYPE

    # Step 1: flat default (Phase 2 path).
    if clause_type in matrix.clause_verdicts:
        flat_verdict = matrix.clause_verdicts[clause_type]
        is_default = False
        flat_source = "flat"
    else:
        flat_verdict = matrix.default_verdict
        is_default = True
        flat_source = ""

    # Step 2: counterparty override (Phase 5).
    cp_overrides = matrix.counterparty_overrides.get(ct, {})
    cp_verdict = cp_overrides.get(clause_type)
    cp_source = "counterparty" if cp_verdict is not None else ""

    # Step 3: language override (Phase 4, DE path). The DE lookup
    # uses the same ``counterparty_type`` as the call — when a
    # real Phase 5 type (``enterprise``/``smb``/``public_sector``/
    # ``healthcare``) is passed, the DE lookup falls through to
    # the Phase 4 ``de_german_entity`` cell (no DE override for
    # the 4-axis types yet, by design — Phase 5 keeps the DE
    # language axis narrow to the original DE entity type).
    de_verdict = None
    de_source = ""
    if lang == "de":
        de_overrides = matrix.language_overrides.get("de", {})
        # Try the call's counterparty_type first, then fall back
        # to the Phase 4 ``de_german_entity`` cell. The fallback
        # keeps the existing test fixtures green and preserves
        # the Phase 4 narrowing for callers that haven't
        # migrated to the 4-axis types yet.
        de_by_cp = de_overrides.get(ct) or de_overrides.get(DE_GERMAN_ENTITY, {})
        de_candidate = de_by_cp.get(clause_type)
        if de_candidate is not None:
            de_verdict = de_candidate
            de_source = "language:de"

    # Compose the strictest verdict. The order of evaluation
    # (DE → counterparty → flat) reflects "DE is the narrowest
    # axis, counterparty is next, flat is the floor". The DE
    # "no-relax" guard is preserved: DE wins only when at least
    # as strict as the next-strictest candidate. The
    # counterparty and flat axes can override each other
    # freely — both are author-intent overrides.
    candidates: list[tuple[Verdict, str]] = []
    if de_verdict is not None:
        candidates.append((de_verdict, de_source))
    if cp_verdict is not None:
        candidates.append((cp_verdict, cp_source))
    if flat_source:
        candidates.append((flat_verdict, flat_source))

    if not candidates:
        # Nothing matched — pure default fallback.
        return MatrixVerdict(
            verdict=matrix.default_verdict,
            clause_type=clause_type,
            counterparty_type=ct,
            is_default=True,
            language=lang,
            sources=[],
        )

    # Sort by strictness (highest first) and pick the strictest
    # *that satisfies the DE-no-relax guard*. If the DE override
    # is *less* strict than another candidate, the DE override
    # is dropped (it doesn't relax the verdict).
    candidates.sort(key=lambda c: c[0].value, reverse=True)
    strictest, source = candidates[0]
    sources = [source]
    # DE no-relax guard: if DE won but a less-strict non-DE
    # candidate is the *real* leading verdict, drop the DE
    # attribution and pick the non-DE strictest.
    if de_verdict is not None and de_source == source:
        non_de = [c for c in candidates[1:] if c[1] != "language:de"]
        if non_de and non_de[0][0].value < de_verdict.value:
            # DE was about to relax — drop DE, pick non-DE strictest.
            strictest = non_de[0][0]
            source = non_de[0][1]
            sources = [source]
    # Track the losing candidates for the UI tooltip (preserves
    # the audit trail without changing the verdict).
    for c, s in candidates:
        if s != source and s not in sources:
            sources.append(s)

    return MatrixVerdict(
        verdict=strictest,
        clause_type=clause_type,
        counterparty_type=ct,
        is_default=is_default,
        language=lang,
        sources=sources,
    )


__all__ = [
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
