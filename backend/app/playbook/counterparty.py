"""Counterparty matrix loader.

The matrix is a YAML file at
``playbook/counterparty_matrix.yaml``. Phase 2 ships a *flat* lookup:
the verdict is a function of the clause type only, not the
counterparty type. Phase 5 introduces a 2D lookup
``(clause_type, counterparty_type) → verdict``.

Public surface
--------------
- :class:`CounterpartyMatrix` — the loaded-and-validated config.
- :func:`load_matrix` — load the YAML from
  ``settings.counterparty_matrix_path`` (or an explicit override).
- :func:`lookup_verdict` — flat lookup. Returns a
  :class:`Verdict` whose shape is forward-compatible with Phase 5
  (it will gain a ``counterparty_type`` field).
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
        overrides: dict[str, dict[str, Verdict]] = {}
        for cp_type, per_clause in overrides_raw.items():
            if not isinstance(per_clause, dict):
                raise ValueError(
                    f"counterparty override for {cp_type!r} must be a "
                    f"mapping, got {type(per_clause).__name__}"
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
            overrides[str(cp_type)] = inner
        return cls(
            version=version,
            contract_type=contract_type,
            language=language,
            default_counterparty_type=default_counterparty_type,
            default_verdict=default_verdict,
            clause_verdicts=clause_verdicts,
            counterparty_overrides=overrides,
            raw=raw,
        )


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


__all__ = [
    "CounterpartyMatrix",
    "MatrixVerdict",
    "Verdict",
    "load_matrix",
    "lookup_verdict",
]
