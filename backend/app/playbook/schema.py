"""Pydantic models for the on-disk playbook baselines.

The shape is locked: every YAML file under
``playbook/baselines/<contract-type>-<language>/`` must parse into a
:class:`PlaybookBaseline`. The seed script enforces this at load
time — a malformed YAML aborts the seed and the whole run.

Field provenance is required, not optional. Every baseline must
have a real public source URL, a retrieval date, and a license
note. This is the rule the spec calls out: "Each carries provenance
(URL + retrieval date + license)."

The ``type`` field is a string that must match one of the
:class:`~app.classify.schema.ClauseType` enum values. We do NOT
import that enum here to keep the playbook package free of the
classifier's import-time side effects (Langfuse init, OpenAI
client construction) — the validation happens at seed time with
an explicit error message.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BaselineClause(BaseModel):
    """A single baseline clause in a playbook.

    Attributes
    ----------
    clause_id
        Stable, kebab-cased identifier. Forms the second half of the
        ``(playbook_id, clause_id)`` primary key in the database.
        Should be human-recognisable (e.g. ``"term-of-confidentiality"``,
        not ``"clause_3"``).
    type
        Lowercase snake_case clause type. Must be one of the
        :class:`~app.classify.schema.ClauseType` enum values. The
        seed script validates this against the enum explicitly so
        a typo surfaces a clean error rather than a Pydantic
        ValidationError from the store.
    language
        ISO-639-1 two-letter code. ``"en"`` for the Phase 2 EN
        baselines, ``"de"`` for the Phase 4 DE baselines.
    title
        Short human-readable title. Shown in the UI's deviation
        table.
    text
        The canonical baseline clause language. This is the
        "reference" the deviation spotter compares the contract
        clause against.
    source_url
        Public URL where the baseline text was retrieved. Required
        — the spec is explicit that every baseline is traceable
        to a public source.
    retrieval_date
        ISO-8601 calendar date the text was retrieved. Useful for
        reproducibility when a public template changes.
    license
        License of the source material. Either an SPDX identifier
        (``"CC0-1.0"``, ``"CC-BY-4.0"``) or a short prose note
        (``"public template, no copyright notice"``).
    notes
        Optional free-form notes. Not loaded into the database
        — kept in the YAML for human readers.
    """

    clause_id: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., min_length=1, max_length=64)
    language: str = Field(..., min_length=2, max_length=8)
    title: str = Field(..., min_length=1, max_length=512)
    text: str = Field(..., min_length=1)
    source_url: str = Field(..., min_length=1, max_length=2048)
    retrieval_date: date
    license: str = Field(..., min_length=1, max_length=512)
    notes: Optional[str] = Field(default=None, max_length=4096)

    @field_validator("type")
    @classmethod
    def _lowercase_type(cls, v: str) -> str:
        """Type must be lowercase snake_case to match the enum values."""
        v = v.strip()
        if not v.replace("_", "").isalnum() or v != v.lower():
            raise ValueError(
                f"clause type must be lowercase snake_case, got {v!r}"
            )
        return v

    @field_validator("language")
    @classmethod
    def _iso_language(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) < 2 or len(v) > 8:
            raise ValueError(
                f"language must be a 2-8 char ISO code, got {v!r}"
            )
        return v


class PlaybookBaseline(BaseModel):
    """A single YAML file's worth of baselines.

    In Phase 2 each YAML contains exactly one :class:`BaselineClause`.
    The wrapper is here for forward-compatibility: Phase 5 (DPA,
    Employment) may pack multiple related baselines into a single
    file (e.g. all five ``governing_law`` variants). The seed
    script handles both shapes transparently.
    """

    clauses: list[BaselineClause] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str) -> "PlaybookBaseline":
        """Load a single YAML file into a :class:`PlaybookBaseline`.

        The file is allowed to contain either a top-level mapping
        (one clause) or a top-level ``clauses:`` list. The mapping
        shape is the common case; the list shape is reserved for
        the multi-clause files Phase 5 may introduce.
        """
        import yaml

        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if raw is None:
            return cls(clauses=[])
        if isinstance(raw, dict) and "clauses" in raw:
            return cls(clauses=[BaselineClause(**c) for c in raw["clauses"]])
        if isinstance(raw, dict):
            return cls(clauses=[BaselineClause(**raw)])
        if isinstance(raw, list):
            return cls(clauses=[BaselineClause(**c) for c in raw])
        raise ValueError(
            f"unsupported playbook YAML shape in {path}: "
            f"top-level value is {type(raw).__name__}"
        )
