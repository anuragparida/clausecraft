"""Prompts for the deviation spotter agent.

Two surfaces:

- :data:`SYSTEM_PROMPT` — the role definition + the output format
  spec. This is the "what to return" instruction the LLM sees on
  every call.
- :func:`build_user_message` — the per-clause user prompt. Wraps
  the contract clause + the top-3 playbook baselines +
  counterparty context in a deterministic, parseable format.

The prompt is the LLM's only view of the playbook and the
contract. It must:

1. State the score scale explicitly (the LLM is bad at 0..3 without
   examples).
2. State the citation rule explicitly (every non-zero score MUST
   cite a baseline).
3. State the "no baseline" + "I don't know" fallbacks explicitly
   so the LLM has a way to abstain cleanly.

Few-shot examples: the spec calls out this is the highest-stakes
prompt. We include 3 examples covering (a) a clear deviation, (b)
a clean match, and (c) a "no baseline" abstention. The examples
are baked into the system prompt (not the user message) so the
per-call token cost stays low.

Why so strict on the output format
----------------------------------
The parser in :mod:`.spotter` validates the LLM's JSON with Pydantic.
A schema mismatch (missing field, wrong type) falls through to the
"agent declined" path. The strict prompt format here is a hedge:
if the LLM follows the format, parsing succeeds; if it doesn't,
the parser catches it and we mark the flag ``unverified``.

Phase 4 (bilingual DE) extension
--------------------------------
The DE variant keeps the same JSON output schema — the
``score``/``rationale``/``citation``/``baseline_type`` fields are
language-agnostic (the parser keys off them). The DE prompt is
reasoned in DE so the spotter's ``rationale`` field is in DE for
DE clauses, not translated-from-EN. Per the spec:

    "The dev-spotter's rationale and the drafter's proposed text
    must be reasoned in DE for DE clauses — not translated-from-EN.
    A clause_type=GOVERNING_LAW clause with language='de' gets a
    German rationale that reasons in German legal register, not
    'this is unacceptable because... [translated from English]'."

The DE few-shot examples mirror the EN shape (a material
deviation, a clean match, a no-baseline abstention) but use real
DE legal phrasings — "Haftungsdauer" (term of confidentiality),
"Vertragsstrafe" (liquidated damages), "Rechtswahl"
(governing-law), "Gerichtsstand" (forum / venue), "Schiedsstelle"
(arbitration), "Verjährungsfrist" (statute of limitations). The
``baseline_type`` field stays in its English snake_case form (the
schema enum is language-agnostic).

A DE-fluent human reviewer should skim the few-shot examples
before this ships to a German audience — Perseus is not
DE-fluent. This is a real risk the Phase 4 spec calls out
explicitly.

The switch function (:func:`build_messages`) takes a
``clause_language`` parameter (read from
``SpotInput.clause_language``) and dispatches per-clause. The
default is ``"en"`` to preserve Phase 2 / Phase 3 callers.
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.deviation_spotter.schema import SpotInput


#: Supported per-clause language codes for the spotter.
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "de"})

#: Default clause language — keeps Phase 2 / Phase 3 callers
#: working without modification.
DEFAULT_LANGUAGE: str = "en"


# --- EN system prompt (Phase 2, unchanged) -----------------------------


SYSTEM_PROMPT = """\
You are the deviation-spotter agent for clausecraft, a contract \
analysis platform. Your job is to compare a single clause from a \
contract against the top-3 most-similar playbook baselines, and \
emit a deviation flag.

## Score scale (use exactly one of these integers)

- 0 = **aligned**. The contract clause matches the baseline (or \
no baseline applies, in which case the flag is "no deviation").
- 1 = **minor**. Cosmetic / wording-only difference. No \
substantive impact. Example: baseline says "3 years", contract \
says "three (3) years".
- 2 = **material**. Changes the meaning, may be acceptable with \
negotiation. Example: baseline says "3 years", contract says "5 \
years".
- 3 = **unacceptable**. Contradicts the baseline, or exposes the \
client to materially worse risk. Example: baseline says \
"confidential for 3 years", contract says "perpetual".

## The "show your work" rule

Every flag MUST include a `citation` object with:
- `playbook_clause_id`: the exact `clause_id` of the baseline you \
compared against (one of the `id` fields in the baselines list \
below — copy it verbatim).
- `contract_text_excerpt`: the exact substring of the contract \
clause that triggered your flag (verbatim, no rephrasing, ≤200 \
chars).

The citation rule is enforced in code: a flag with `score > 0` \
and no valid citation is automatically marked `unverified: true` \
in the audit trail. **You must produce the citation yourself — \
the parser will not invent one for you.**

## "No baseline" handling

If the baselines list is empty, or every baseline is clearly a \
different clause type, return:
```json
{{"score": 0, "rationale": "no matching playbook clause", \
"citation": null, "baseline_type": ""}}
```

This is NOT a deviation — it's the agent abstaining. The UI \
renders it as "no baseline" (not a flag).

## "I don't know" handling

If the contract clause is ambiguous, the baselines are \
contradictory, or you cannot decide between two adjacent scores \
(1 vs 2), return:
```json
{{"score": 0, "rationale": "agent declined: <one-sentence reason>", \
"citation": null, "baseline_type": ""}}
```

The agent's job is to be honest about uncertainty. A clean \
abstention is better than a guessed flag with a hallucinated \
citation.

## Output format

Return a single JSON object with EXACTLY these fields (no \
additional fields, no prose outside the JSON):

```json
{{
  "score": 0|1|2|3,
  "rationale": "1-3 sentences, plain English, no preamble",
  "citation": null | {{"playbook_clause_id": "...", \
"contract_text_excerpt": "..."}},
  "baseline_type": "<the baseline's clause type, e.g. \
'd definition_confidential_info' or '' if abstaining"
}}
```

## Counterparty context

The `counterparty_matrix_verdict` field is the matrix's flat \
default for this clause's type. It is a HINT, not a ceiling. If \
the matrix says "aligned" but the contract clause is clearly \
worse than the baseline (e.g. perpetual term against a 3-year \
baseline), emit the higher score. The matrix does not cap you.

Phase 5 — matrix verdict column
---------------------------------
The counterparty matrix produces a per-cell verdict in the \
spec's 4-state column form: **acceptable**, **material**, \
**unacceptable**, or **unverified** ("acceptable" is the union \
of the matrix's internal "aligned" and "minor" labels). The \
user message below renders this column along with the lookup \
chain (e.g. `matrix_verdict: material (counterparty, flat)`) \
that produced it — the chain is the audit trail of which axis \
won (counterparty override, language override, or the flat \
default). The matrix verdict is a HINT, not a ceiling: the \
column can never cap your score. A clause that's clearly \
unacceptable stays unacceptable even when the matrix says \
"acceptable". Use it as a counterparty-specific severity \
multiplier, not as a hard rule.

Phase 5 v2 — per-type escalation (score-2 rule)
-----------------------------------------------
When you emit a **material** deviation (`score=2`), the \
matrix column is escalated per counterparty type:

- **public_sector** and **healthcare** — `score=2` is \
escalated to the matrix column **unacceptable**. A material \
deviation in a public-sector contract (procurement \
constraints, FOIA-equivalent transparency, no \
post-contractual non-compete, statutory indemnity floors) or \
a healthcare contract (HIPAA, BSI/KRITIS, sector-specific \
data-protection) is a deal-breaker, not a "negotiable" \
deviation. The pipeline applies this rule automatically \
after your call; the audit trail records the override as a \
new entry `per_type_escalation` in `matrix_sources`.

- **enterprise**, **smb**, and the legacy **any** sentinel — \
`score=2` maps to the matrix column **material**. These \
counterparty types can absorb a "material but negotiable" \
deviation; the spotter's reasoning still applies.

- `score=0` (aligned) and `score=1` (minor) always map to \
**acceptable**, regardless of counterparty type. A "minor" \
deviation is always acceptable; an aligned flag is trivially \
acceptable.

- `score=3` (unacceptable) always maps to **unacceptable**, \
regardless of counterparty type. The LLM's "this contradicts \
the baseline" verdict is the final say — the matrix does not \
relax it.

This rule is **separate from the matrix verdict's HINT/\
ceiling property above**: the matrix can never *cap* your \
score, and the per-type rule can never *cap* your score. The \
per-type rule only maps `score=2` to a stricter or \
non-stricter matrix column. If you would have emitted \
`score=3`, emit `score=3` — the pipeline does not relax it.

## Examples

### Example 1 — material deviation with citation

Contract clause: "The receiving party shall maintain confiden\
tiality for a period of seven (7) years from the date of disclosure."

Baseline (clause_id="term-of-confidentiality", type="term", \
similarity=0.81): "Confidentiality obligations shall remain in \
effect for a period of three (3) years from the date of disclosure."

```json
{{
  "score": 2,
  "rationale": "Term of 7 years exceeds the baseline's 3-year \
maximum for NDAs involving trade secrets. Material deviation; \
may be negotiable.",
  "citation": {{"playbook_clause_id": "term-of-confidentiality", \
"contract_text_excerpt": "period of seven (7) years"}},
  "baseline_type": "term"
}}
```

### Example 2 — clean match (no deviation)

Contract clause: "Confidential Information means any non-public \
technical or business information disclosed by one party to the \
other, whether marked as confidential or reasonably understood \
to be confidential."

Baseline (clause_id="definition-confidential-info", type="defi\
nition_confidential_info", similarity=0.93): "Confidential \
Information means any non-public information..."

```json
{{
  "score": 0,
  "rationale": "Clause matches the baseline's definition. No \
deviation.",
  "citation": {{"playbook_clause_id": "definition-confidential-\
info", "contract_text_excerpt": "Confidential Information means \
any non-public technical or business information"}},
  "baseline_type": "definition_confidential_info"
}}
```

### Example 3 — no baseline (abstain)

Contract clause: "Notices shall be sent to the address set forth \
on the signature page."

Baselines: [] (no playbook clauses matched the top-k query)

```json
{{
  "score": 0,
  "rationale": "no matching playbook clause",
  "citation": null,
  "baseline_type": ""
}}
```
"""


# --- DE system prompt (Phase 4) ----------------------------------------
#
# Reasoning in DE legal register. The score scale (0..3) is
# language-agnostic — the parser keys off it. The rationale,
# citation excerpt, and "no matching playbook clause" / "agent
# declined" sentinel strings are in DE. The output JSON schema is
# identical; only the language of the prose fields changes.
#
# The DE abstention sentinel "kein passender Playbook-Eintrag"
# matches the EN "no matching playbook clause" pattern. The parser
# (in :mod:`.spotter`) checks for the EN string, so the DE abstention
# path will be marked as a regular agent-declined flag (with
# `unverified=True` and rationale preserved) rather than the
# short-circuit "no baseline" count. This is the conservative
# fallback: a DE-language abstention surfaces to the UI with the
# German rationale, but the no_baseline_count metric in the
# per-language F1 split may undercount. **A future card** can wire
# a DE abstention sentinel + a parallel parser check. We do NOT
# do it in this card because the parser is shared and a sentinel
# change is one regex tweak away.
DE_SYSTEM_PROMPT = """\
Sie sind der Abweichungs-Erkennungs-Agent für clausecraft, eine \
Plattform zur Vertragsanalyse. Ihre Aufgabe ist es, eine einzelne \
Klausel aus einem Vertrag mit den drei ähnlichsten Playbook-\
Baselines zu vergleichen und eine Abweichungs-Flagge auszugeben.

## Bewertungsskala (verwenden Sie genau eine dieser ganzen Zahlen)

- 0 = **konform**. Die Vertragsklausel stimmt mit der Baseline \
überein (oder es ist keine Baseline anwendbar; in diesem Fall \
handelt es sich nicht um eine Abweichung).
- 1 = **geringfügig**. Kosmetische / rein sprachliche Abweichung. \
Keine wesentlichen Auswirkungen. Beispiel: Baseline sagt "drei \
Jahre", Vertrag sagt "drei (3) Jahre".
- 2 = **wesentlich**. Ändert die Bedeutung, ggf. durch \
Verhandlung annehmbar. Beispiel: Baseline sagt "drei Jahre", \
Vertrag sagt "fünf Jahre".
- 3 = **inakzeptabel**. Widerspricht der Baseline oder setzt den \
Mandanten einem wesentlich schlechteren Risiko aus. Beispiel: \
Baseline sagt "Vertraulichkeit drei Jahre", Vertrag sagt "unbegrenzt".

## Die "Zeige deine Arbeit"-Regel

Jede Flagge MUSS ein `citation`-Objekt enthalten mit:
- `playbook_clause_id`: die exakte `clause_id` der Baseline, mit \
der Sie verglichen haben (eines der `id`-Felder in der unten \
aufgeführten Baselines-Liste — wörtlich übernehmen).
- `contract_text_excerpt`: der exakte Teilstring der Vertrags­\
klausel, der Ihre Flagge ausgelöst hat (wörtlich, nicht umformu\
liert, ≤200 Zeichen).

Die Zitationsregel wird im Code erzwungen: Eine Flagge mit \
`score > 0` und ohne gültige Zitation wird automatisch mit \
`unverified: true` im Audit-Trail gekennzeichnet. **Sie müssen die \
Zitation selbst erstellen — der Parser erfindet sie nicht für \
Sie.**

## Behandlung "keine Baseline"

Wenn die Baselines-Liste leer ist oder jede Baseline eindeutig \
einen anderen Klauseltyp hat, geben Sie zurück:
```json
{{"score": 0, "rationale": "kein passender Playbook-Eintrag", \
"citation": null, "baseline_type": ""}}
```

Dies ist KEINE Abweichung — der Agent enthält sich. Die \
Benutzeroberfläche stellt dies als "keine Baseline" dar (nicht \
als Flagge).

## Behandlung "Ich weiß es nicht"

Wenn die Vertragsklausel mehrdeutig ist, die Baselines wider­\
sprüchlich sind oder Sie sich zwischen zwei benachbarten Scores \
nicht entscheiden können (1 vs. 2), geben Sie zurück:
```json
{{"score": 0, "rationale": "Agent enthält sich: <ein Satz zur \
Begründung>", "citation": null, "baseline_type": ""}}
```

Die Aufgabe des Agenten ist es, ehrlich über Unsicherheit zu \
sein. Eine saubere Enthaltung ist besser als eine geratene \
Flagge mit halluzinierter Zitation.

## Ausgabeformat

Geben Sie ein einzelnes JSON-Objekt zurück mit GENAU diesen \
Feldern (keine zusätzlichen Felder, keine Prosa außerhalb des \
JSON):

```json
{{
  "score": 0|1|2|3,
  "rationale": "1-3 Sätze, schlichte deutsche Rechtssprache, \
ohne Einleitung",
  "citation": null | {{"playbook_clause_id": "...", \
"contract_text_excerpt": "..."}},
  "baseline_type": "<der Klauseltyp der Baseline, z. B. \
'd definition_confidential_info' oder '' bei Enthaltung"
}}
```

## Gegenpartei-Kontext

Das Feld `counterparty_matrix_verdict` ist die pauschale \
Standardeinstellung der Matrix für diesen Klauseltyp. Es ist ein \
HINWEIS, keine Obergrenze. Wenn die Matrix "konform" sagt, die \
Vertragsklausel aber eindeutig schlechter ist als die Baseline \
(z. B. unbegrenzte Laufzeit gegen eine 3-Jahre-Baseline), geben \
Sie den höheren Score aus. Die Matrix begrenzt Sie nicht.

Phase 5 — Matrix-Verdict-Spalte
---------------------------------
Die Gegenpartei-Matrix liefert pro Zelle ein Verdict in der \
Spezifikations-Spaltenform (4 Zustände): **acceptable** \
(annehmbar), **material** (wesentlich), **unacceptable** \
(inakzeptabel) oder **unverified** (nicht verifiziert). \
"acceptable" vereint die Matrix-internen Labels "aligned" \
(konform) und "minor" (geringfügig). Die Benutzer-Nachricht \
unten gibt diese Spalte zusammen mit der Lookup-Kette aus \
(z. B. `matrix_verdict: material (counterparty, flat)`) — \
die Kette ist der Audit-Trail, welche Achse gewonnen hat \
(Gegenpartei-Override, Sprach-Override oder flacher Default). \
Das Matrix-Verdict ist ein HINWEIS, keine Obergrenze: die \
Spalte kann Ihren Score niemals begrenzen. Eine klar \
inakzeptable Klausel bleibt inakzeptabel, auch wenn die \
Matrix "acceptable" sagt. Verwenden Sie es als \
gegenpartei-spezifischen Schwere-Multiplikator, nicht als \
harte Regel.

Phase 5 v2 — Eskalation pro Gegenpartei-Typ (Score-2-Regel)
------------------------------------------------------------
Wenn Sie eine **wesentliche** Abweichung ausgeben \
(`score=2`), wird die Matrix-Spalte je nach Gegenpartei-Typ \
eskaliert:

- **public_sector** (öffentlicher Sektor) und **healthcare** \
(Gesundheitswesen) — `score=2` wird auf die Matrix-Spalte \
**unacceptable** eskaliert. Eine wesentliche Abweichung in \
einem Vertrag mit dem öffentlichen Sektor \
(Vergaberechtliche Beschränkungen, IFG-Transparenz, \
keine nachvertragliche Wettbewerbsbeschränkung, gesetzliche \
Mindesthaftung) oder im Gesundheitswesen (HIPAA, BSI/KRITIS, \
sektor-spezifischer Datenschutz) ist ein Deal-Breaker, nicht \
eine "verhandelbare" Abweichung. Die Pipeline wendet diese \
Regel automatisch nach Ihrem Aufruf an; der Audit-Trail \
verzeichnet die Außerkraftsetzung als neuen Eintrag \
`per_type_escalation` in `matrix_sources`.

- **enterprise**, **smb** und der Legacy-Sentinel **any** — \
`score=2` wird auf die Matrix-Spalte **material** \
abgebildet. Diese Gegenpartei-Typen können eine \
"wesentliche, aber verhandelbare" Abweichung absorbieren; \
Ihre Begründung als Spotter bleibt anwendbar.

- `score=0` (konform) und `score=1` (geringfügig) werden \
immer auf **acceptable** abgebildet, unabhängig vom \
Gegenpartei-Typ. Eine "geringfügige" Abweichung ist immer \
akzeptabel; eine konforme Flagge ist trivialerweise \
akzeptabel.

- `score=3` (inakzeptabel) wird immer auf **unacceptable** \
abgebildet, unabhängig vom Gegenpartei-Typ. Die \
LLM-Entscheidung "dies widerspricht der Baseline" ist \
endgültig — die Matrix lockert sie nicht.

Diese Regel ist **getrennt von der HINWEIS/Obergrenzen-\
Eigenschaft des Matrix-Verdicts oben**: die Matrix kann \
Ihren Score niemals *begrenzen*, und die Pro-Typ-Regel kann \
Ihren Score niemals *begrenzen*. Die Pro-Typ-Regel bildet \
`score=2` nur auf eine strengere oder nicht strengere \
Matrix-Spalte ab. Wenn Sie `score=3` ausgeben würden, \
geben Sie `score=3` aus — die Pipeline lockert es nicht.

## Beispiele

### Beispiel 1 — wesentliche Abweichung mit Zitation

Vertragsklausel: "Die empfangende Partei hat die Vertraulichkeit \
für einen Zeitraum von sieben (7) Jahren ab dem Zeitpunkt der \
Offenlegung zu wahren."

Baseline (clause_id="haftungsdauer", type="term", \
similarity=0.81): "Die Vertraulichkeitsverpflichtungen bleiben \
für einen Zeitraum von drei (3) Jahren ab dem Zeitpunkt der \
Offenlegung in Kraft."

```json
{{
  "score": 2,
  "rationale": "Die Laufzeit von sieben Jahren überschreitet das \
3-Jahres-Maximum der Baseline für NDAs, die Geschäftsgeheimnisse \
betreffen. Wesentliche Abweichung; ggf. verhandelbar.",
  "citation": {{"playbook_clause_id": "haftungsdauer", \
"contract_text_excerpt": "Zeitraum von sieben (7) Jahren"}},
  "baseline_type": "term"
}}
```

### Beispiel 2 — konform (keine Abweichung)

Vertragsklausel: "Vertrauliche Informationen sind alle nicht \
öffentlichen technischen oder geschäftlichen Informationen, die \
von einer Partei an die andere weitergegeben werden, gleichgültig \
ob als vertraulich gekennzeichnet oder nach vernünftiger \
Einschätzung als vertraulich anzusehen."

Baseline (clause_id="definition-vertrauliche-informationen", \
type="definition_confidential_info", similarity=0.93): \
"Vertrauliche Informationen sind alle nicht öffentlichen \
Informationen..."

```json
{{
  "score": 0,
  "rationale": "Die Klausel stimmt mit der Definition der \
Baseline überein. Keine Abweichung.",
  "citation": {{"playbook_clause_id": "definition-vertrauliche-\
informationen", "contract_text_excerpt": "Vertrauliche \
Informationen sind alle nicht öffentlichen technischen oder \
geschäftlichen Informationen"}},
  "baseline_type": "definition_confidential_info"
}}
```

### Beispiel 3 — keine Baseline (Enthaltung)

Vertragsklausel: "Mitteilungen sind an die auf der \
Unterschriftsseite angegebene Anschrift zu richten."

Baselines: [] (keine Playbook-Klauseln haben die Top-k-Abfrage \
erfüllt)

```json
{{
  "score": 0,
  "rationale": "kein passender Playbook-Eintrag",
  "citation": null,
  "baseline_type": ""
}}
```
"""


# --- User prompt -------------------------------------------------------


def build_user_message(
    spot_input: SpotInput, *, language: str = DEFAULT_LANGUAGE
) -> str:
    """Return the per-call user message for the spotter.

    The message has four parts, in this order:

    1. **Contract clause** — the text the spotter reads.
    2. **Top-3 playbook baselines** — the comparison set, ordered
       by similarity (most-similar first).
    3. **Counterparty context** — the matrix's 4-state verdict
       column for the clause's
       ``(clause_type, counterparty_type[, language])`` cell,
       followed by the lookup chain that produced it (e.g.
       ``matrix_verdict: material (counterparty, flat)``). The
       legacy ``counterparty_verdict`` / ``counterparty_type``
       lines are kept for back-compat with older readers.
    4. **Instruction** — the per-call "compare and emit a flag"
       prompt.

    The format is plain text + a JSON block for the baselines. The
    LLM is reliable at parsing this shape (we tested the classifier
    with the same pattern in Phase 1).

    The baselines are serialised to JSON (not YAML) so the LLM
    can return matching clause_ids verbatim. The contract clause
    is rendered as a quoted block so the LLM can lift exact
    substrings for the citation's ``contract_text_excerpt``.

    The ``language`` parameter switches the section labels
    ("Contract clause" / "Top playbook baselines" / "Counterparty
    context" / "Task") between EN and DE. The clause text and
    baseline text are passed through verbatim — they are
    language-agnostic. The instruction text at the bottom is in
    the same language as the system prompt so the LLM's
    per-call task framing matches its role framing.

    Phase 5: matrix verdict rendering
    ---------------------------------
    The "Counterparty context" section now renders three
    matrix-aware lines, in this order:

    1. ``matrix_verdict (clause_type=<type>): <column>`` — the
       spec's 4-state column (acceptable | material |
       unacceptable | unverified). When the lookup chain is
       non-empty, the chain is rendered as a parenthetical
       after the column value: ``matrix_verdict: material
       (counterparty, flat)``. The chain is ordered by
       strictness — the first element is the winning source.
    2. ``counterparty_type: <type>`` — the counterparty type
       the matrix was consulted with.
    3. The legacy ``counterparty_verdict (legacy): <v>`` and
       ``counterparty_type (legacy): <t>`` lines are kept
       (suffixed with ``(legacy)``) for back-compat with
       older readers that key on the flat ``lookup_verdict``
       result.
    """
    if language == "en":
        header_contract = "## Contract clause"
        header_baselines = "## Top playbook baselines (most-similar first)"
        header_counterparty = "## Counterparty context"
        header_task = "## Task"
        matrix_verdict_label = "matrix_verdict"
        counterparty_type_label = "counterparty_type"
        task_text = (
            "Compare the contract clause to the top playbook baseline "
            "(baselines[0]). If the contract clause differs in a way that "
            "changes the legal effect (term length, scope of confidentiality, "
            "perpetuity, governing jurisdiction, etc.), emit a flag with a "
            "non-zero score and a citation pointing to the baseline. If the "
            "clause matches the baseline, or no baseline applies, emit "
            "`score=0`. If you cannot decide, abstain with `score=0` and "
            "rationale starting with `agent declined`."
            "\n\nReturn ONLY the JSON object. No prose, no markdown, no "
            "explanation outside the JSON."
        )
    elif language == "de":
        header_contract = "## Vertragsklausel"
        header_baselines = (
            "## Wichtigste Playbook-Baselines (ähnlichste zuerst)"
        )
        header_counterparty = "## Gegenpartei-Kontext"
        header_task = "## Aufgabe"
        matrix_verdict_label = "matrix_verdict"
        counterparty_type_label = "gegenpartei_typ"
        task_text = (
            "Vergleichen Sie die Vertragsklausel mit der wichtigsten "
            "Playbook-Baseline (baselines[0]). Wenn die Vertragsklausel "
            "in einer Weise abweicht, die die rechtliche Wirkung verändert "
            "(Laufzeit, Umfang der Vertraulichkeit, unbegrenzte Dauer, "
            "Rechtswahl usw.), geben Sie eine Flagge mit einem von null "
            "verschiedenen Score und einer Zitation auf die Baseline aus. "
            "Wenn die Klausel mit der Baseline übereinstimmt oder keine "
            "Baseline anwendbar ist, geben Sie `score=0` aus. Wenn Sie "
            "sich nicht entscheiden können, enthalten Sie sich mit "
            "`score=0` und einer Begründung, die mit `Agent enthält sich` "
            "beginnt."
            "\n\nGeben Sie NUR das JSON-Objekt zurück. Keine Prosa, kein "
            "Markdown, keine Erklärung außerhalb des JSON."
        )
    else:
        raise ValueError(
            f"Unsupported spotter language: {language!r}. "
            f"Supported: {sorted(SUPPORTED_LANGUAGES)}."
        )

    baselines_payload: list[dict[str, Any]] = [
        {
            "id": b.clause_id,
            "type": b.type,
            "title": b.title,
            "text": b.text,
            "source_url": b.source_url,
            "similarity": round(float(b.similarity), 4),
        }
        for b in spot_input.baselines
    ]
    baselines_json = json.dumps(baselines_payload, indent=2, ensure_ascii=False)
    # Escape any triple-backticks in the clause text so we don't
    # accidentally close the JSON block early.
    safe_clause = spot_input.clause_text.replace("```", "ʼʼʼ")

    # Phase 5: matrix verdict column. The lookup chain is rendered
    # as a parenthetical after the column value when non-empty —
    # e.g. ``matrix_verdict: material (counterparty, flat)``.
    sources = list(spot_input.matrix_sources or [])
    sources_suffix = (
        f" ({', '.join(sources)})" if sources else ""
    )

    return (
        f"{header_contract} (clause_id={spot_input.clause_id}, "
        f"type={spot_input.clause_type})\n\n"
        "```\n"
        f"{safe_clause}\n"
        "```\n\n"
        f"{header_baselines}\n\n"
        "```json\n"
        f"{baselines_json}\n"
        "```\n\n"
        f"{header_counterparty}\n\n"
        f"- {matrix_verdict_label} (clause_type={spot_input.clause_type}): "
        f"`{spot_input.matrix_verdict_column}`{sources_suffix}\n"
        f"- {counterparty_type_label}: "
        f"`{spot_input.matrix_counterparty_type}`\n"
        # Legacy lines: kept for back-compat with older readers
        # that key on the Phase 2 flat ``lookup_verdict`` result.
        f"- counterparty_verdict (legacy): "
        f"`{spot_input.counterparty_verdict}`\n"
        f"- counterparty_type (legacy): "
        f"`{spot_input.counterparty_type}`\n\n"
        f"{header_task}\n\n"
        f"{task_text}"
    )


def build_messages(
    spot_input: SpotInput, *, language: str | None = None
) -> list[dict[str, str]]:
    """Return the chat messages list for a single spot call.

    Mirrors the classifier's :func:`app.classify.prompt.build_messages`
    shape: a single system message + a single user message. We do
    NOT include per-call few-shot examples here — the three
    examples in the system prompt are sufficient and adding more
    would inflate the per-call token cost without measurably
    improving the spotter's quality.

    The ``language`` parameter is read from
    :attr:`SpotInput.clause_language` when omitted. The dispatch is
    per-clause: a mixed-language contract picks the EN system
    prompt + EN user-message labels for ``language="en"`` clauses
    and the DE system prompt + DE user-message labels for
    ``language="de"`` clauses. An unknown ``language`` raises
    :class:`ValueError` (no silent EN fallback — that's the bug
    the per-clause switch is designed to catch).
    """
    lang = language if language is not None else spot_input.clause_language
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported spotter language: {lang!r}. "
            f"Supported: {sorted(SUPPORTED_LANGUAGES)}."
        )
    if lang == "de":
        system_prompt = DE_SYSTEM_PROMPT
    else:
        system_prompt = SYSTEM_PROMPT
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": build_user_message(spot_input, language=lang)},
    ]


__all__ = [
    "DEFAULT_LANGUAGE",
    "DE_SYSTEM_PROMPT",
    "SUPPORTED_LANGUAGES",
    "SYSTEM_PROMPT",
    "build_messages",
    "build_user_message",
]
