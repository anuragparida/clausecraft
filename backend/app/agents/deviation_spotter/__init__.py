"""Deviation spotter — the first real agent (Phase 2).

The spotter compares a single classified clause against the top-3
playbook baselines (returned by :func:`app.playbook.store.topk`) and
emits a :class:`DeviationFlag` with:

- ``score`` — 0 (aligned) | 1 (minor) | 2 (material) | 3 (unacceptable)
- ``rationale`` — the spotter's reasoning (short, 1–3 sentences)
- ``citation`` — a pointer to the playbook clause the spotter
  compared against, plus the exact contract text excerpt that
  triggered the flag. **Required for any non-zero score.** A flag
  with a non-zero score and no citation is treated as ``unverified``
  and surfaced in the UI as such.
- ``unverified`` — ``True`` when the spotter could not produce a
  citation (LLM refused, output failed to parse, no baseline
  matched, etc.). The flag is still returned; the UI renders the
  "unverified" badge.

The "show your work" rule is enforced in three places:

1. The Pydantic schema requires the ``citation`` field on
   :class:`DeviationFlag` (typed, not Optional — but the value can
   be ``None``).
2. The system prompt asks for it and explains the format.
3. The parser in :mod:`.spotter` flips ``unverified=True`` when the
   LLM returns a non-zero score without a citation. **This is
   defense in depth: even if the LLM hallucinates a citation, the
   code path verifies it points to a real clause_id from the
   top-k list.**

Public surface
--------------
- :class:`DeviationFlag` — the spotter's output model.
- :class:`Citation` — the embedded citation model.
- :func:`spot_clause` — the agent's single-call entry point. Takes
  a :class:`SpotInput` (clause + baselines + counterparty) and
  returns a :class:`DeviationFlag`.
- :func:`spot_clauses` — the parallel orchestration helper (used
  by :mod:`app.pipeline.stage3_spot`).
"""

from app.agents.deviation_spotter.schema import (
    Citation,
    DeviationFlag,
    SpotInput,
)
from app.agents.deviation_spotter.spotter import (
    spot_clause,
    spot_clauses,
)

__all__ = [
    "Citation",
    "DeviationFlag",
    "SpotInput",
    "spot_clause",
    "spot_clauses",
]
