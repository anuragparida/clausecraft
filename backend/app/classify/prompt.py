"""Classifier prompt — Phase 1 (EN) + Phase 4 (DE).

The system prompt + 2 few-shot examples the classifier sends to the
LLM. Kept in a module (not a YAML or DB) because Phase 1 has no
prompt-management infrastructure; Phase 2 (eval harness) will grow
one.

The few-shot examples cover two distinct cases:

1. A "definition of confidential information" clause — the most
   common NDA clause, and the one the LLM most reliably mislabels
   as ``term`` when the clause body mentions a "period of N years".
2. A "governing law" clause — short, jurisdiction-named, easy to
   confuse with ``notices`` or ``entire_agreement``.

Phase 4 (bilingual DE) extension
--------------------------------
The DE variant keeps the same clause-type taxonomy — the spec is
explicit: "the Pydantic schemas and English clause type enums stay
the same — the language detection is a per-clause
``language: "de" | "en"`` field." The DE system prompt is reasoned
in DE (not translated-from-EN) so the classifier does not
back-translate DE legal phrasings into EN idiom, which is the
problem the Phase 4 spec calls out:

    "DE legal terminology is its own dialect. 'Vertraulichkeits­
    vereinbarung' vs 'NDA,' 'Schadensersatz' vs 'Haftung,'
    'Kündigung' vs 'Termination.' The classifier and spotter
    prompts need DE-fluent reviewers. If Perseus isn't DE-fluent
    (likely), this is a spot where a human in the loop helps."

The few-shot examples in DE mirror the EN examples in structure
(definition-of-confidential-info + governing-law) but use real DE
legal phrasings (Vertraulichkeitsvereinbarung, Vertragsstrafe,
Schiedsstelle, Gerichtsstand, etc.), not literal word-for-word EN
translations. **A DE-fluent human reviewer should look at the
few-shot examples before this ships to a German audience** —
Perseus is not DE-fluent and the example phrasing reflects a
legalese style, not a native-speaker's ear.

The switch function (:func:`build_messages`) takes a
``language`` parameter and dispatches per-clause. The default is
``"en"`` to preserve the Phase 1 / Phase 2 / Phase 3 callers.
"""

from __future__ import annotations

from app.classify.schema import ClauseType


# === EN system prompt (Phase 1, unchanged) ==============================

# Keep the system prompt short but specific. We name every valid
# enum value (excluding ``unknown``) and explain the confidence rule.
#
# Phase 5 note: as of 2026-06-09 the active system prompt is still
# NDA-only — the new ``dpa_*`` and ``employment_*`` values are
# recognised by the parser (Pydantic-validated ``ClauseType`` enum)
# but the classifier's per-call prompt is not yet updated to
# surface them. This is intentional: the matrix-aware spotter
# prompt work is owned by a separate card. The full taxonomy lives
# in ``docs/15-clause-taxonomy-phase5.md`` (kanban ``t_8337687f``).
SYSTEM_PROMPT = """You are a contract-clause classifier for English-language \
Non-Disclosure Agreements (NDAs). You will be given the text of a single \
clause extracted from a larger NDA. Your job is to assign it exactly one \
clause type from the following taxonomy:

{definition_confidential_info} — defines what counts as "Confidential \
Information" (e.g. "Confidential Information means any non-public \
information disclosed by one party to the other...")

{term} — specifies how long the obligation lasts (e.g. "This Agreement \
shall remain in effect for a period of three (3) years...")

{governing_law} — names the jurisdiction whose laws govern the \
agreement (e.g. "This Agreement shall be governed by the laws of the \
State of New York...")

{injunctive_relief} — acknowledges that breach may cause irreparable \
harm warranting injunction (e.g. "The parties acknowledge that monetary \
damages may be inadequate and that injunctive relief shall be available...")

{residual_knowledge} — permits retention of information in unaided \
memory (e.g. "Nothing herein shall restrict the use of residual \
knowledge retained in the memory of personnel...")

{return_of_materials} — requires return or destruction of confidential \
materials on request (e.g. "Upon termination, each party shall return or \
destroy all Confidential Information...")

{non_solicit} — restricts solicitation of employees or customers \
(e.g. "For a period of twelve months, neither party shall solicit the \
other's employees...")

{non_compete} — restricts competing business activity (rare in NDAs, \
but possible)

{indemnity} — shifts liability for breach (e.g. "The disclosing party \
shall indemnify the receiving party for any losses...")

{limitation_of_liability} — caps or excludes damages

{assignment} — governs transfer of rights (e.g. "Neither party may \
assign this Agreement without prior written consent...")

{entire_agreement} — declares the document the complete agreement \
between the parties

{severability} — addresses the effect of an unenforceable provision

{notices} — sets the channel/address for formal notices

{counterparts} — permits execution in counterparts (e.g. "This \
Agreement may be executed in counterparts...")

Return a JSON object with:
- "type": one of the values above (or "unknown" if none fit ≥40% confidence)
- "confidence": a float between 0.0 and 1.0

Rules:
- The "type" field must be exactly one of the values listed.
- "confidence" is your own estimate of how certain you are. 0.0 means \
you're guessing; 1.0 means the clause text is a textbook example of \
the type. Never return a value outside [0.0, 1.0].
- Do NOT include the text of the clause in your response. Only the \
"type" and "confidence" fields.
""".format(
    definition_confidential_info=ClauseType.DEFINITION_CONFIDENTIAL_INFO.value,
    term=ClauseType.TERM.value,
    governing_law=ClauseType.GOVERNING_LAW.value,
    injunctive_relief=ClauseType.INJUNCTIVE_RELIEF.value,
    residual_knowledge=ClauseType.RESIDUAL_KNOWLEDGE.value,
    return_of_materials=ClauseType.RETURN_OF_MATERIALS.value,
    non_solicit=ClauseType.NON_SOLICIT.value,
    non_compete=ClauseType.NON_COMPETE.value,
    indemnity=ClauseType.INDEMNITY.value,
    limitation_of_liability=ClauseType.LIMITATION_OF_LIABILITY.value,
    assignment=ClauseType.ASSIGNMENT.value,
    entire_agreement=ClauseType.ENTIRE_AGREEMENT.value,
    severability=ClauseType.SEVERABILITY.value,
    notices=ClauseType.NOTICES.value,
    counterparts=ClauseType.COUNTERPARTS.value,
)


# Two few-shot examples. Each is (clause_text, expected_type).
FEW_SHOT_EXAMPLES: list[dict[str, str]] = [
    {
        "role": "user",
        "content": (
            "Clause: \"Confidential Information means any non-public "
            "technical, business, or financial information disclosed by "
            "one party to the other, whether orally or in writing, that "
            "is marked as confidential or that a reasonable person "
            "would understand to be confidential.\""
        ),
    },
    {
        "role": "assistant",
        "content": '{"type": "definition_confidential_info", "confidence": 0.97}',
    },
    {
        "role": "user",
        "content": (
            "Clause: \"This Agreement shall be governed by and "
            "construed in accordance with the laws of the State of "
            "California, without regard to its conflict of laws "
            "principles.\""
        ),
    },
    {
        "role": "assistant",
        "content": '{"type": "governing_law", "confidence": 0.98}',
    },
]


# === DE system prompt (Phase 4) ========================================
#
# Reasoning: The DE prompt is in DE, not EN. The taxonomy value names
# stay in their English snake_case form (the schema enum is
# language-agnostic), but the role framing, the category
# descriptions, the example phrasings, and the confidence rule
# description are all in DE legal register. The DE clause type names
# in the role descriptions use the real German legal vocabulary —
# "Vertraulichkeitsinformation" (definition), "Vertragsdauer" (term),
# "Rechtswahl" / "Gerichtsstand" (governing_law), "Unterlassungs­
# anspruch" (injunctive_relief), "Restwissen" (residual_knowledge),
# "Rückgabe von Unterlagen" (return_of_materials), "Abwerbeverbot"
# (non_solicit), "Wettbewerbsverbot" (non_compete), "Schadensersatz"
# (indemnity), "Haftungsbeschränkung" (limitation_of_liability),
# "Abtretung" (assignment), "Schlussbestimmungen / Vollständig­
# keitsklausel" (entire_agreement), "Salvatorische Klausel"
# (severability), "Mitteilungen" (notices), "Vertragsausfertigungen"
# (counterparts).
#
# These are the phrasings a German Rechtsanwalt would expect, not
# word-for-word translations. A DE-fluent human reviewer should
# skim before this ships.
DE_SYSTEM_PROMPT = """Sie sind ein Klassifikator für Vertragsklauseln in \
deutschsprachigen Vertraulichkeitsvereinbarungen (NDAs / Geheimhaltungs­\
vereinbarungen). Ihnen wird der Text einer einzelnen Klausel aus einer \
größeren Vereinbarung vorgelegt. Ihre Aufgabe ist es, der Klausel genau \
einen Klauseltyp aus der folgenden Taxonomie zuzuweisen:

{definition_confidential_info} — definiert, was als "Vertrauliche \
Information" gilt (z. B. "Vertrauliche Informationen sind alle nicht \
öffentlichen technischen, geschäftlichen oder finanziellen Informatio­\
nen, die von einer Partei an die andere weitergegeben werden...")

{term} — legt die Dauer der Verpflichtung fest (z. B. "Diese Verein­\
barung bleibt für einen Zeitraum von drei (3) Jahren in Kraft...")

{governing_law} — benennt die Rechtsordnung, deren Gesetze die \
Vereinbarung regeln (z. B. "Diese Vereinbarung unterliegt deutschem \
Recht unter Ausschluss des UN-Kaufrechts...")

{injunctive_relief} — stellt klar, dass eine Verletzung einen \
irreparablen Schaden verursachen kann, der einen Unterlassungsanspruch \
rechtfertigt (z. B. "Die Parteien erkennen an, dass ein Unterlassungs­\
anspruch zur Verhinderung weiterer Verstöße in Betracht kommt...")

{residual_knowledge} — erlaubt die Nutzung von Informationen im \
ungestützten Gedächtnis (z. B. "Diese Vereinbarung beschränkt nicht \
die Nutzung von Restwissen, das im Gedächtnis der Mitarbeiter verbleibt...")

{return_of_materials} — verlangt die Rückgabe oder Vernichtung \
vertraulicher Unterlagen auf Verlangen (z. B. "Bei Beendigung hat jede \
Partei alle Vertraulichen Informationen zurückzugeben oder zu vernichten...")

{non_solicit} — beschränkt die Abwerbung von Mitarbeitern oder Kunden \
(z. B. "Für einen Zeitraum von zwölf Monaten darf keine Partei die \
Mitarbeiter der anderen Partei abwerben...")

{non_compete} — beschränkt konkurrierende Geschäftstätigkeit (in NDAs \
selten, aber möglich)

{indemnity} — verlagert die Haftung für Pflichtverletzungen (z. B. "Die \
preisgebende Partei hat die empfangende Partei von etwaigen Schäden \
freizustellen...")

{limitation_of_liability} — begrenzt oder schließt Schadensersatz­ \
ansprüche aus

{assignment} — regelt die Übertragung von Rechten (z. B. "Keine Partei \
darf diese Vereinbarung ohne vorherige schriftliche Zustimmung an Dritte \
abtreten...")

{entire_agreement} — erklärt das Dokument zur vollständigen Vereinbarung \
zwischen den Parteien (Vollständigkeitsklausel)

{severability} — regelt die Wirkung einer nicht durchsetzbaren \
Bestimmung (Salvatorische Klausel)

{notices} — bestimmt den Kanal / die Anschrift für förmliche \
Mitteilungen

{counterparts} — erlaubt den Abschluss in Mehrfachausfertigung \
(z. B. "Diese Vereinbarung kann in Mehrfachausfertigung unterzeichnet \
werden...")

Geben Sie ein JSON-Objekt zurück mit:
- "type": einer der oben genannten Werte (oder "unknown", falls kein \
Wert mit einer Konfidenz von ≥40 % passt)
- "confidence": ein Float-Wert zwischen 0.0 und 1.0

Regeln:
- Das Feld "type" muss exakt einem der aufgelisteten Werte entsprechen.
- "confidence" ist Ihre eigene Einschätzung, wie sicher Sie sind. \
0.0 bedeutet, Sie raten; 1.0 bedeutet, der Klauseltext ist ein \
Lehrbuchbeispiel dieses Typs. Niemals einen Wert außerhalb von \
[0.0, 1.0] zurückgeben.
- Fügen Sie den Text der Klausel NICHT in Ihre Antwort ein. Nur die \
Felder "type" und "confidence".
""".format(
    definition_confidential_info=ClauseType.DEFINITION_CONFIDENTIAL_INFO.value,
    term=ClauseType.TERM.value,
    governing_law=ClauseType.GOVERNING_LAW.value,
    injunctive_relief=ClauseType.INJUNCTIVE_RELIEF.value,
    residual_knowledge=ClauseType.RESIDUAL_KNOWLEDGE.value,
    return_of_materials=ClauseType.RETURN_OF_MATERIALS.value,
    non_solicit=ClauseType.NON_SOLICIT.value,
    non_compete=ClauseType.NON_COMPETE.value,
    indemnity=ClauseType.INDEMNITY.value,
    limitation_of_liability=ClauseType.LIMITATION_OF_LIABILITY.value,
    assignment=ClauseType.ASSIGNMENT.value,
    entire_agreement=ClauseType.ENTIRE_AGREEMENT.value,
    severability=ClauseType.SEVERABILITY.value,
    notices=ClauseType.NOTICES.value,
    counterparts=ClauseType.COUNTERPARTS.value,
)


# Two DE few-shot examples. Same shape as the EN ones (definition +
# governing_law) but with real DE legal phrasings. These mirror the
# 2-public-source DE NDA shape: a mutual NDA with §1 as the
# definition-of-confidential-info clause (with the standard
# "mündlich, schriftlich, elektronisch" triadic phrasing German
# contracts use) and §10 as the governing-law clause referencing
# the Bundesrepublik Deutschland and the courts of Berlin.
DE_FEW_SHOT_EXAMPLES: list[dict[str, str]] = [
    {
        "role": "user",
        "content": (
            "Klausel: \"Vertrauliche Informationen sind alle nicht "
            "öffentlichen technischen, geschäftlichen oder finanziellen "
            "Informationen, die von einer Partei an die andere Partei "
            "offengelegt werden, gleichgültig ob mündlich, schriftlich "
            "oder in elektronischer Form, und die als vertraulich "
            "gekennzeichnet sind oder die ein verständiger Dritter "
            "als vertraulich einstufen würde.\""
        ),
    },
    {
        "role": "assistant",
        "content": '{"type": "definition_confidential_info", "confidence": 0.97}',
    },
    {
        "role": "user",
        "content": (
            "Klausel: \"Diese Vereinbarung unterliegt deutschem Recht "
            "unter Ausschluss des Übereinkommens der Vereinten Nationen "
            "über Verträge über den internationalen Warenkauf (UN-Kaufrecht). "
            "Ausschließlicher Gerichtsstand für alle Streitigkeiten aus "
            "oder im Zusammenhang mit dieser Vereinbarung ist Berlin, "
            "soweit dies gesetzlich zulässig ist.\""
        ),
    },
    {
        "role": "assistant",
        "content": '{"type": "governing_law", "confidence": 0.97}',
    },
]


# === Supported languages ===============================================
#
# The supported set is hard-coded so a future addition (e.g. "fr")
# is a deliberate, tested change. ``"en"`` is the default for
# backwards compatibility — every Phase 1 / Phase 2 / Phase 3
# caller passes nothing and gets EN.
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "de"})

DEFAULT_LANGUAGE: str = "en"


def build_messages(
    clause_text: str, *, language: str = DEFAULT_LANGUAGE
) -> list[dict[str, str]]:
    """Return the chat messages list for a single classification call.

    The shape is OpenAI-compatible: ``[{"role": "system", ...}, ...]``.
    The caller adds the user message containing the clause text.

    ``language`` is the per-clause language field on
    :class:`app.classify.schema.Clause`. The dispatch is per-clause,
    not per-document: a mixed-language contract picks the EN prompt
    for ``language="en"`` clauses and the DE prompt for
    ``language="de"`` clauses.

    An unknown ``language`` value raises :class:`ValueError` —
    silently falling back to EN is the bug the per-clause switch is
    designed to catch (the Phase 4 spec calls out "the language
    assertion is the most important new assertion in the test" —
    silent EN fallback is the regression that assertion targets).

    The user-message wrapper also switches: ``Clause: "<text>"`` for
    EN clauses, ``Klausel: "<text>"`` for DE clauses. This is the
    small touch that signals to the model "the rest of this
    conversation is in DE" — without it, a DE-trained model on a DE
    system prompt sees an EN-style final user message and sometimes
    back-translates. Mirrors the few-shot user-message phrasing.
    """
    if language == "en":
        system_prompt = SYSTEM_PROMPT
        few_shot = FEW_SHOT_EXAMPLES
        user_prefix = "Clause"
    elif language == "de":
        system_prompt = DE_SYSTEM_PROMPT
        few_shot = DE_FEW_SHOT_EXAMPLES
        user_prefix = "Klausel"
    else:
        raise ValueError(
            f"Unsupported classifier language: {language!r}. "
            f"Supported: {sorted(SUPPORTED_LANGUAGES)}."
        )
    return [
        {"role": "system", "content": system_prompt},
        *few_shot,
        {"role": "user", "content": f"{user_prefix}: \"{clause_text}\""},
    ]


# Backwards-compat alias for callers that pass the prompt module's
# own ``DEFAULT_LANGUAGE`` import. Not part of the public surface;
# internal use only.
build_messages.__defaults__ = (DEFAULT_LANGUAGE,)  # type: ignore[attr-defined]
