"""Process-global eval harness state.

This module exists to be imported by both ``evals/conftest.py``
(loaded by pytest as a conftest) and ``evals/harness.py`` (loaded
as a normal module by the harness's tests). When the same Python
module is imported by two different paths (e.g. ``conftest`` vs
``evals.conftest``), Python sees them as two different module
instances — even though they point to the same file on disk. A
plain module-level dict in ``evals/conftest.py`` would therefore
be duplicated, and state set in one instance wouldn't be visible
to the other.

A separate, dedicated module avoids the duplication: pytest
imports it once, the harness imports it once, and they both
refer to the same module instance because the import path is
always ``evals._state``.

Why we need a "current contract" state at all
---------------------------------------------
The autouse mock fixture in ``evals/conftest.py`` monkey-patches
the spotter's LLM call. The patched stub needs to know which
contract is currently being processed (each contract has its
own golden-driven payload), but the stub doesn't have access to
the test's local variables. The harness sets the contract key
in module state at the start of each per-contract pipeline run;
the stub reads it.

Public surface
--------------
- :func:`set_current_contract_key` — set the active contract.
- :func:`get_current_contract_key` — read the active contract.
- :data:`_current_contract_key` — the raw state dict. Don't
  touch it directly; use the helpers.
"""

from __future__ import annotations

#: Process-global state. The key is always a string — the
#: contract path relative to the repo root (e.g.
#: ``"examples/contracts/synthetic/nda-001.pdf"``).
#:
#: Empty string means "no contract is active" — the mock stub
#: then returns "no deviation" for every clause (a clean
#: baseline).
_current_contract_key: dict[str, str] = {"value": ""}


def set_current_contract_key(contract_key: str) -> None:
    """Set the contract key the autouse mock fixture should use.

    Called by the harness at the start of each per-contract
    pipeline run. The mock stub reads this via
    :func:`get_current_contract_key` so it returns the right
    golden-driven payload.

    Parameters
    ----------
    contract_key
        The contract path relative to the repo root, e.g.
        ``"examples/contracts/synthetic/nda-001.pdf"``. Empty
        string resets the state.
    """
    _current_contract_key["value"] = contract_key


def get_current_contract_key() -> str:
    """Return the contract key the autouse mock fixture should use.

    Empty string when the harness hasn't set one. The mock stub
    falls back to "no expected deviation" for every clause when
    the key is empty.
    """
    return _current_contract_key["value"]


__all__ = [
    "set_current_contract_key",
    "get_current_contract_key",
]
