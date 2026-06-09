"""Tests for the bilingual DE prompt dispatch (Phase 4 card 5).

The card's hard rule: "The switch logic must be **per-clause**, not
per-document. A mixed-language contract (rare but possible) should
still work."

These tests target the three prompt modules' ``build_messages``
functions directly — the agent modules' LLM call sites already
thread ``clause_language`` from the typed inputs, so the per-clause
dispatch is a property of the prompt modules. The test file is
sync-only (the prompt builders are sync) and DB-free (no Postgres
needed).

Test layers
-----------

1. **Classifier prompt** — :func:`app.classify.prompt.build_messages`
   dispatches on ``language`` and emits the EN or DE system prompt
   + the matching few-shot examples + a user-message wrapper
   ("Clause: " / "Klausel: ").
2. **Spotter prompt** — :func:`app.agents.deviation_spotter.prompt.build_messages`
   dispatches on ``SpotInput.clause_language`` (or the explicit
   ``language`` override) and emits the EN or DE system prompt
   + the matching user-message labels. The DE abstention sentinel
   is "kein passender Playbook-Eintrag" (German for "no matching
   playbook clause").
3. **Drafter prompt** — :func:`app.agents.redline_drafter.prompt.build_messages`
   dispatches on ``DrafterInput.clause_language`` (or the explicit
   ``language`` override) and emits the EN or DE system prompt
   + the matching user-message labels. The self-check retry path
   renders the constraint text in the same language.
4. **Mixed-language contract** — the headline acceptance criterion.
   A single contract with one EN clause and one DE clause gets
   the EN prompt for the EN clause and the DE prompt for the DE
   clause. The dispatch is per-clause; the contract is not
   forced to a single language.
5. **Unknown language raises** — the dispatch refuses to silently
   fall back to EN. The "silent EN fallback" is the regression
   the per-clause switch is designed to catch.
6. **Schema field default** — :class:`SpotInput` and
   :class:`DrafterInput` carry ``clause_language: str = "en"`` so
   Phase 2 / Phase 3 callers (which do not pass the field)
   continue to work unchanged.

Why the tests use the prompt module's ``build_messages``
directly and not the agent's LLM call
--------------------------------------------
The LLM call site (e.g. :func:`app.agents.deviation_spotter.spotter._call_llm_for_spot`)
is a thin wrapper that constructs the OpenAI client + delegates
to :func:`build_messages`. Testing the prompt module directly is
faster, deterministic, and pins the dispatch contract without
mocking the OpenAI client.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root = parent of "tests". Backend is a sibling.
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest

from app.agents.deviation_spotter.prompt import (
    build_messages as build_spotter_messages,
)
from app.agents.deviation_spotter.schema import (
    BaselineForSpotter,
    SpotInput,
)
from app.agents.redline_drafter.prompt import (
    build_messages as build_drafter_messages,
)
from app.agents.redline_drafter.schema import (
    DrafterInput,
    SelfCheckConstraint,
)
from app.agents.deviation_spotter.schema import Citation, DeviationFlag
from app.classify.prompt import (
    SUPPORTED_LANGUAGES as CLASSIFIER_LANGUAGES,
    build_messages as build_classifier_messages,
)
from app.agents.deviation_spotter.prompt import (
    SUPPORTED_LANGUAGES as SPOTTER_LANGUAGES,
)
from app.agents.redline_drafter.prompt import (
    SUPPORTED_LANGUAGES as DRAFTER_LANGUAGES,
)


# --- Helper builders ---------------------------------------------------


def _make_baseline(clause_id: str = "haftungsdauer") -> BaselineForSpotter:
    """A realistic-looking baseline for spot/draft tests."""
    return BaselineForSpotter(
        clause_id=clause_id,
        type="term",
        title="Laufzeit der Vertraulichkeitsverpflichtung",
        text=(
            "Die Vertraulichkeitsverpflichtungen bleiben für einen "
            "Zeitraum von drei (3) Jahren ab dem Zeitpunkt der "
            "Offenlegung in Kraft."
        ),
        source_url="https://example.com/playbook/haftungsdauer",
        similarity=0.91,
    )


def _make_flag(
    rationale: str = "Laufzeit von 7 Jahren überschreitet das Maximum",
) -> DeviationFlag:
    """A realistic-looking deviation flag for drafter tests."""
    return DeviationFlag(
        clause_id="c1",
        score=2,
        rationale=rationale,
        baseline_type="term",
        citation=Citation(
            playbook_clause_id="haftungsdauer",
            contract_text_excerpt="sieben (7) Jahren",
        ),
    )


# === Acceptance criterion 1: classifier dispatch =======================


def test_classifier_default_language_is_english():
    """No language argument → EN (backwards-compatible default)."""
    msgs = build_classifier_messages("Some clause text.")
    system = msgs[0]["content"]
    assert "English-language" in system
    assert "Klassifikator" not in system
    # User-message wrapper is "Clause:".
    assert msgs[-1]["content"].startswith("Clause: ")


def test_classifier_explicit_en():
    """``language="en"`` returns the EN system prompt + EN few-shot."""
    msgs = build_classifier_messages("Some clause.", language="en")
    assert "English-language" in msgs[0]["content"]
    # The EN few-shot first example is the "definition_confidential_info" NDA clause.
    assert "Confidential Information means" in msgs[1]["content"]


def test_classifier_explicit_de():
    """``language="de"`` returns the DE system prompt + DE few-shot.

    This is the headline acceptance criterion for the DE prompt
    work: a DE clause gets the DE system prompt, the DE
    few-shot examples, and a DE user-message wrapper.
    """
    msgs = build_classifier_messages(
        "Vertraulichkeitsvereinbarung über drei Jahre", language="de"
    )
    system = msgs[0]["content"]
    # DE system prompt keywords.
    assert "Vertraulichkeitsvereinbarungen" in system
    assert "Vertrauliche Informationen sind" in system
    assert "Klauseltyp" in system
    # The EN-only "English-language" framing must NOT appear.
    assert "English-language" not in system
    # User-message wrapper is "Klausel:".
    assert msgs[-1]["content"].startswith("Klausel: ")
    # The DE few-shot examples use DE legal phrasings.
    # First few-shot is a definition-of-confidential-info NDA clause
    # in DE — the triadic "mündlich, schriftlich oder in elektronischer
    # Form" phrasing German contracts use.
    assert "mündlich, schriftlich" in msgs[1]["content"]


def test_classifier_unknown_language_raises():
    """The dispatch refuses silent EN fallback for unsupported languages.

    The Phase 4 spec calls this out: "the language assertion is the
    most important new assertion in the test — silent EN fallback
    is the regression that assertion targets."
    """
    with pytest.raises(ValueError) as exc_info:
        build_classifier_messages("Some clause.", language="fr")
    assert "Unsupported classifier language" in str(exc_info.value)
    assert "fr" in str(exc_info.value)


def test_classifier_supported_languages_constant():
    """The supported-language set is the documented {"en", "de"}."""
    assert CLASSIFIER_LANGUAGES == frozenset({"en", "de"})


# === Acceptance criterion 2: spotter dispatch =========================


def test_spotter_default_language_pulled_from_clause_language():
    """Spotter reads ``SpotInput.clause_language`` when ``language`` is omitted."""
    si_en = SpotInput(
        clause_id="c1",
        clause_text="term of seven years",
        clause_type="term",
        baselines=[_make_baseline()],
    )
    assert si_en.clause_language == "en"  # backwards-compat default
    msgs = build_spotter_messages(si_en)
    assert "deviation-spotter agent" in msgs[0]["content"]
    assert "Abweichungs-Erkennungs-Agent" not in msgs[0]["content"]


def test_spotter_de_clause_dispatch():
    """A DE clause gets the DE system prompt + DE user-message labels."""
    si_de = SpotInput(
        clause_id="c1",
        clause_text=(
            "Die empfangende Partei hat die Vertraulichkeit für "
            "einen Zeitraum von sieben (7) Jahren ab dem Zeitpunkt "
            "der Offenlegung zu wahren."
        ),
        clause_type="term",
        clause_language="de",
        baselines=[_make_baseline()],
    )
    msgs = build_spotter_messages(si_de)
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    # DE system prompt.
    assert "Abweichungs-Erkennungs-Agent" in system
    # DE clause_type name in the example (lowercase snake_case
    # — the schema enum is language-agnostic).
    assert '"haftungsdauer"' in system  # term-clause_id in the DE example
    assert "Vertraulichkeitsverpflichtungen" in system  # DE term
    assert "deviation-spotter agent" not in system
    # DE user-message labels.
    assert "## Vertragsklausel" in user
    assert "## Wichtigste Playbook-Baselines" in user
    assert "## Gegenpartei-Kontext" in user
    assert "## Aufgabe" in user
    # The EN-style labels must NOT appear.
    assert "## Contract clause" not in user
    assert "## Top playbook baselines" not in user
    # The DE abstention sentinel (in the system prompt's example 3).
    assert "kein passender Playbook-Eintrag" in system


def test_spotter_explicit_language_override():
    """``language=`` keyword overrides ``SpotInput.clause_language``.

    Useful for tests; the agent code never passes the keyword
    (it always reads from the typed input).
    """
    si_en = SpotInput(
        clause_id="c1",
        clause_text="term of seven years",
        clause_type="term",
        baselines=[_make_baseline()],
    )
    msgs = build_spotter_messages(si_en, language="de")
    assert "Abweichungs-Erkennungs-Agent" in msgs[0]["content"]


def test_spotter_unknown_language_raises():
    """No silent EN fallback — the dispatch raises on unknown values."""
    si = SpotInput(
        clause_id="c1",
        clause_text="x",
        clause_type="term",
        clause_language="fr",
        baselines=[],
    )
    with pytest.raises(ValueError) as exc_info:
        build_spotter_messages(si)
    assert "Unsupported spotter language" in str(exc_info.value)


def test_spotter_supported_languages_constant():
    assert SPOTTER_LANGUAGES == frozenset({"en", "de"})


# === Acceptance criterion 3: drafter dispatch =========================


def _make_drafter_input(clause_language: str = "en") -> DrafterInput:
    return DrafterInput(
        flag=_make_flag(),
        clause_text="The receiving party shall maintain confidentiality for seven years.",
        baseline=_make_baseline(),
        extra_context="limit to 5 years for trade secrets",
        clause_language=clause_language,
    )


def test_drafter_default_language_pulled_from_clause_language():
    """Drafter reads ``DrafterInput.clause_language`` when ``language`` is omitted."""
    di_en = _make_drafter_input(clause_language="en")
    msgs = build_drafter_messages(di_en)
    assert "redline-drafter agent" in msgs[0]["content"]
    assert "Entwurfs-Agent" not in msgs[0]["content"]


def test_drafter_de_clause_dispatch():
    """A DE clause gets the DE system prompt + DE user-message labels.

    The DE system prompt reasoning: a ``proposed_text`` rewrite for
    a DE clause must read as native DE legal register (Haftungsdauer,
    Vertragsstrafe, etc.) — not word-for-word EN translation. The
    audit log's ``rationale`` and ``diff_summary`` are also in DE.
    """
    di_de = DrafterInput(
        flag=_make_flag(),
        clause_text=(
            "Die empfangende Partei hat die Vertraulichkeit für "
            "einen Zeitraum von sieben (7) Jahren ab dem Zeitpunkt "
            "der Offenlegung zu wahren."
        ),
        baseline=_make_baseline(),
        extra_context="begrenzt auf 5 Jahre für Geschäftsgeheimnisse",
        clause_language="de",
    )
    msgs = build_drafter_messages(di_de)
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    # DE system prompt.
    assert "Entwurfs-Agent" in system
    assert "deutsche Rechtssprache" in system
    assert "redline-drafter agent" not in system
    # DE user-message labels.
    assert "## Akzeptierte Abweichungs-Flagge" in user
    assert "## Ursprüngliche Klausel" in user
    assert "## Zugeordnete Playbook-Baseline" in user
    assert "## Aufgabe" in user
    # DE extra-context block.
    assert "## Zusätzlicher Kontext vom Nutzer" in user
    assert "begrenzt auf 5 Jahre" in user
    # The EN-style labels must NOT appear.
    assert "## Accepted deviation flag" not in user
    assert "## Original clause" not in user


def test_drafter_self_check_retry_in_de():
    """The self-check retry path renders the constraint text in DE.

    A DE clause that hits the self-check loop gets the DE retry
    header, the DE "your previous proposal introduced a new
    deviation" intro, and the DE score labels (konform /
    geringfügig / wesentlich / inakzeptabel) in the constraint
    text. The mismatch of language between the system prompt and
    the constraint would be the kind of regression a unit test
    on the retry path catches.
    """
    di_de = DrafterInput(
        flag=_make_flag(),
        clause_text=(
            "Die empfangende Partei hat die Vertraulichkeit für "
            "sieben (7) Jahren ab Offenlegung zu wahren."
        ),
        baseline=_make_baseline(),
        clause_language="de",
    )
    constraint = SelfCheckConstraint(
        previous_proposed_text="fünf (5) Jahren ab Offenlegung",
        conflicting_flag=DeviationFlag(
            clause_id="c1",
            score=2,
            rationale="Immer noch über dem Maximum",
            baseline_type="term",
            citation=Citation(
                playbook_clause_id="haftungsdauer",
                contract_text_excerpt="fünf (5)",
            ),
        ),
    )
    msgs = build_drafter_messages(di_de, self_check_constraint=constraint)
    user = msgs[1]["content"]
    assert "## Selbstprüfungs-Wiederholung" in user
    assert "Ihr vorheriger Vorschlag hat eine NEUE Abweichung" in user
    # DE score label for score=2 is "wesentlich (2)".
    assert "wesentlich (2)" in user
    # The EN-style retry header must NOT appear.
    assert "## Self-check retry" not in user


def test_drafter_unknown_language_raises():
    di = _make_drafter_input()
    with pytest.raises(ValueError) as exc_info:
        build_drafter_messages(di, language="fr")
    assert "Unsupported drafter language" in str(exc_info.value)


def test_drafter_supported_languages_constant():
    assert DRAFTER_LANGUAGES == frozenset({"en", "de"})


# === Acceptance criterion 4: mixed-language contract ===================


def test_mixed_language_contract_dispatch():
    """The headline acceptance criterion.

    A single contract with one EN clause and one DE clause gets
    the EN prompt for the EN clause and the DE prompt for the DE
    clause. The dispatch is per-clause; the contract is not forced
    to a single language.
    """
    # EN clause
    en_clause = "The receiving party shall maintain confidentiality for three (3) years."
    en_msgs = build_classifier_messages(en_clause, language="en")
    assert "English-language" in en_msgs[0]["content"]
    assert en_msgs[-1]["content"].startswith("Clause: ")

    # DE clause
    de_clause = (
        "Die empfangende Partei hat die Vertraulichkeit für drei (3) "
        "Jahre ab dem Zeitpunkt der Offenlegung zu wahren."
    )
    de_msgs = build_classifier_messages(de_clause, language="de")
    assert "Vertraulichkeitsvereinbarungen" in de_msgs[0]["content"]
    assert de_msgs[-1]["content"].startswith("Klausel: ")

    # The two clauses share a single ``build_classifier_messages``
    # entry point but get language-specific output. This is the
    # per-clause dispatch the spec calls out.
    assert en_msgs[0]["content"] != de_msgs[0]["content"]


def test_mixed_language_spotter_contract_dispatch():
    """The spotter also dispatches per-clause for mixed contracts."""
    en_si = SpotInput(
        clause_id="c1",
        clause_text="term of three years",
        clause_type="term",
        clause_language="en",
        baselines=[_make_baseline()],
    )
    de_si = SpotInput(
        clause_id="c2",
        clause_text="Laufzeit von drei Jahren",
        clause_type="term",
        clause_language="de",
        baselines=[_make_baseline()],
    )
    en_msgs = build_spotter_messages(en_si)
    de_msgs = build_spotter_messages(de_si)
    assert "deviation-spotter agent" in en_msgs[0]["content"]
    assert "Abweichungs-Erkennungs-Agent" in de_msgs[0]["content"]
    assert "## Contract clause" in en_msgs[1]["content"]
    assert "## Vertragsklausel" in de_msgs[1]["content"]


def test_mixed_language_drafter_contract_dispatch():
    """The drafter also dispatches per-clause for mixed contracts."""
    en_di = _make_drafter_input(clause_language="en")
    de_di = DrafterInput(
        flag=_make_flag(),
        clause_text="Vertraulichkeitsklausel",
        baseline=_make_baseline(),
        clause_language="de",
    )
    en_msgs = build_drafter_messages(en_di)
    de_msgs = build_drafter_messages(de_di)
    assert "redline-drafter agent" in en_msgs[0]["content"]
    assert "Entwurfs-Agent" in de_msgs[0]["content"]


# === Acceptance criterion 5: schema field defaults ====================


def test_spot_input_clause_language_default_is_en():
    """Backwards compat: Phase 2 callers construct ``SpotInput`` without
    the new field and get ``clause_language="en"``.
    """
    si = SpotInput(
        clause_id="c1",
        clause_text="x",
        clause_type="term",
        baselines=[],
    )
    assert si.clause_language == "en"


def test_drafter_input_clause_language_default_is_en():
    """Backwards compat: Phase 3 callers construct ``DrafterInput``
    without the new field and get ``clause_language="en"``.
    """
    di = DrafterInput(
        flag=_make_flag(),
        clause_text="x",
        baseline=_make_baseline(),
    )
    assert di.clause_language == "en"
