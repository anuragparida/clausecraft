"""Counterparty matrix loader.

The matrix is a YAML file at
``playbook/counterparty_matrix.yaml``. Phase 2 ships a *flat* lookup:
the verdict is a function of the clause type only, not the
counterparty type. Phase 5 introduces a 2D lookup
``(clause_type, counterparty_type) → verdict``.

Phase 4 stacks a *language* axis on top of the 2D table:
``language → counterparty_type → clause_type → verdict``. The DE
column only narrows verdicts for DE counterparty types — the EN
path is unchanged. ``lookup_verdict`` stays Phase-2-shaped so the
existing call sites (e.g. ``stage3_spot._matrix_verdict_for_clause``)
don't need to know about the DE column. A new
``lookup_verdict_with_language`` is the Phase 4 entry point.

Public surface
--------------
- :class:`CounterpartyMatrix` — the loaded-and-validated config.
- :func:`load_matrix` — load the YAML from
  ``settings.counterparty_matrix_path`` (or an explicit override).
- :func:`lookup_verdict` — flat lookup (Phase 2). Returns a
  :class:`MatrixVerdict` whose shape is forward-compatible with
  Phase 5 (it will gain a ``counterparty_type`` field).
- :func:`lookup_verdict_with_language` — Phase 4 lookup. Adds the
  language axis. EN callers get the same result as ``lookup_verdict``;
  DE callers may see a stricter verdict when a DE counterparty-type
  override is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
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
        The counterparty type that was looked up. In Phase 2 this
        is always ``"any"`` (flat lookup). Phase 5 will pass a
        real counterparty type.
    is_default
        True when the verdict came from the matrix's
        ``default_verdict`` (the per-clause override was absent).
        The UI uses this to render a "matrix default" tag.
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


__all__ = [
    "CounterpartyMatrix",
    "MatrixVerdict",
    "Verdict",
    "load_matrix",
    "lookup_verdict",
    "lookup_verdict_with_language",
]
