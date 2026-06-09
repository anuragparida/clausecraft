"""Prompts for the redline drafter agent.

Two surfaces, mirroring :mod:`app.agents.deviation_spotter.prompt`:

- :data:`SYSTEM_PROMPT` — the role definition + the output format
  spec. This is the "what to return" instruction the LLM sees on
  every call.
- :func:`build_user_message` — the per-call user prompt. Wraps
  the contract clause + the matched baseline + the flag context
  in a deterministic, parseable format. On a self-check retry,
  the drafter passes the :class:`SelfCheckConstraint` to inject
  an explicit "your previous proposal introduced a new deviation"
  instruction into the user message.

Few-shot examples
-----------------
The spec calls out the drafter as a higher-stakes prompt than
the spotter (the drafter's output goes straight into the
tracked-changes .docx). We include 2 examples covering (a) a
clean rewrite (term reduction) and (b) a rewrite that handles
a counterparty carve-out. The examples are baked into the
system prompt so the per-call token cost stays low.

Why the drafter's output format is plain text, not JSON
-------------------------------------------------------
The deviation spotter's JSON output is parsed into a typed
:class:`DeviationFlag`. The drafter's output (``proposed_text``,
``rationale``, ``diff_summary``) is **not** parsed from a JSON
object — it's parsed from a JSON object via the OpenAI
``response_format=json_object`` flag. The reason for JSON over
plain text is the same as the spotter's: a misbehaving model
that emits a markdown fence or a leading prose sentence would
fail the parser, and the agent would retry. JSON is the safest
target.

The drafter's contract text **is** plain text inside the JSON
object — the drafter does NOT escape the proposed clause (the
docx writer receives the raw string from the parsed JSON and
inserts it verbatim). The system prompt is explicit: "do NOT
wrap the proposed_text in quotes, do NOT escape the text,
just emit the raw clause body."

Self-check retry prompt
-----------------------
The self-check loop (:mod:`.self_check`) injects a constraint
into the user message on the retry:

  "Your previous proposal introduced a NEW deviation:
   <score + rationale + citation from the spotter's re-run>.
   Rewrite to address the ORIGINAL flag
   (<original flag's score + rationale>) WITHOUT introducing
   this new one."

The constraint text is rendered as a dedicated section in the
user message so the LLM can't miss it. We do NOT modify the
system prompt between attempts — the system prompt is the
"how to do your job" instruction, and changing it between
attempts would invalidate the few-shot examples. The
self-check constraint is a per-call instruction, which
belongs in the user message.

Phase 4 (bilingual DE) extension
--------------------------------
The DE variant keeps the same JSON output schema — the
``proposed_text``/``rationale``/``diff_summary`` fields are
language-agnostic (the docx writer drops the proposed_text
verbatim; the rationale + diff_summary are audit-log prose,
not LLM-rendered into the contract). The DE prompt is
reasoned in DE so:

  - The ``proposed_text`` rewrite for a DE clause reads as
    native DE legal register (Haftungsdauer, Vertragsstrafe,
    Gerichtsstand, Kündigungsfrist, Schiedsverfahren), not
    word-for-word EN translation.
  - The ``rationale`` and ``diff_summary`` are in DE for DE
    clauses (per spec: "the dev-spotter's rationale and the
    drafter's proposed text must be reasoned in DE for DE
    clauses — not translated-from-EN").

The DE few-shot examples mirror the EN shape (term reduction
+ trade-secrets carve-out with user-context override) but use
real DE legal phrasings — "Haftungsdauer" (term),
"Vertragsstrafe" (liquidated damages), "Schiedsverfahren"
(arbitration), "Gerichtsstand" (forum), "außergerichtliche
Einigung" (out-of-court settlement), "Geschäftsgeheimnisse"
(trade secrets), "Geheimhaltungspflicht" (confidentiality
obligation). The ``flag.baseline_type`` stays in its English
snake_case form (the schema enum is language-agnostic).

A DE-fluent human reviewer should skim the few-shot examples
before this ships to a German audience — Perseus is not
DE-fluent. This is a real risk the Phase 4 spec calls out
explicitly.

The switch function (:func:`build_messages`) takes a
``clause_language`` parameter (read from
``DrafterInput.clause_language``) and dispatches per-clause.
The default is ``"en"`` to preserve Phase 3 callers.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.agents.deviation_spotter.schema import DeviationFlag
from app.agents.redline_drafter.schema import (
    DrafterInput,
    SelfCheckConstraint,
)


#: Supported per-clause language codes for the drafter.
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "de"})

#: Default clause language — keeps Phase 3 callers working
#: without modification.
DEFAULT_LANGUAGE: str = "en"


# --- EN system prompt (Phase 3, unchanged) -----------------------------


SYSTEM_PROMPT = """\
You are the redline-drafter agent for clausecraft, a contract \
analysis platform. Your job is to rewrite a single clause from \
a contract so that it aligns with the matched playbook baseline.

The user has ACCEPTED a deviation flag for this clause. The \
flag is the spotter's verdict that the clause differs from the \
baseline. Your job is to produce a redline (a rewritten clause \
that aligns with the baseline) — NOT to argue with the flag. \
If the user attached extra context, honor it; otherwise, the \
baseline is the target.

## Output format

Return a single JSON object with EXACTLY these fields (no \
additional fields, no prose outside the JSON):

```json
{{
  "proposed_text": "<the rewritten clause body, verbatim, \
drop-in replacement for the original>",
  "rationale": "<1-3 sentences, plain English, no preamble>",
  "diff_summary": "<plain-text before/after summary, no \
markdown, no diff syntax, suitable for an audit log>"
}}
```

Critical rules for `proposed_text`:

1. **Verbatim drop-in.** The `proposed_text` replaces the \
   original clause in the .docx output. The drafter's job is \
   to produce a single coherent edit, not a diff. Do NOT wrap \
   the text in quotes. Do NOT escape special characters. Emit \
   the raw clause body.
2. **Preserve structure.** If the original clause has numbered \
   list items, "provided that" carve-outs, or definitions of \
   terms used elsewhere in the contract, preserve them. The \
   redline is a single edit, not a fragment swap.
3. **Stay close to the baseline.** The baseline is the target. \
   If the user attached extra context (e.g. "limit to 5 years, \
   not the baseline's 3"), the user context overrides the \
   baseline's exact text. Otherwise, the baseline's text is \
   authoritative.

Critical rules for `rationale`:

1. **Plain English.** The audit log renders this verbatim. A \
   human reviewer reads it to understand *what you changed* and \
   *why*. No marketing language, no "as per the user's \
   request" boilerplate.
2. **1-3 sentences.** If your rationale is longer than that, \
   you're explaining, not redlining.
3. **Name the deviation you're fixing.** Example: "Term of 7 \
   years reduced to the baseline's 3-year maximum. Carve-out \
   for trade secrets preserved from the original."

Critical rules for `diff_summary`:

1. **Plain text.** The audit log + JSON export render this \
   verbatim. No markdown, no diff syntax (no `+` / `-` lines, \
   no unified-diff markers). A single short paragraph.
2. **Before / after.** Example: "Term: 7 years → 3 years. \
   Carve-out for trade secrets: preserved. Governing law \
   reference: unchanged."

## When the clause is unfixable

If the deviation is structural (e.g. the contract is a \
perpetual NDA and the baseline is a 3-year term, and the \
"perpetuity" is the entire deal), do NOT try to rewrite the \
clause into something the counterparty will never accept. \
Return your best attempt anyway — the self-check loop will \
catch it and the HITL UI will surface the conflict to the \
user. **The drafter always returns a redline; the self-check \
loop decides whether to ship it.**

## Examples

### Example 1 — clean rewrite (term reduction)

Contract clause: "The receiving party shall maintain confiden\
tiality for a period of seven (7) years from the date of \
disclosure."

Flag (score=2, rationale="Term of 7 years exceeds the \
baseline's 3-year maximum for NDAs involving trade secrets."): \
material deviation.

Baseline (clause_id="term-of-confidentiality", type="term"): \
"Confidentiality obligations shall remain in effect for a \
period of three (3) years from the date of disclosure."

```json
{{
  "proposed_text": "Confidentiality obligations shall remain \
in effect for a period of three (3) years from the date of \
disclosure.",
  "rationale": "Term of 7 years reduced to the baseline's 3-\
year maximum. The original clause's 'receiving party' is \
preserved as 'obligations' (the baseline's neutral framing \
matches our standard NDA form).",
  "diff_summary": "Term: 7 years → 3 years. Subject: 'receiv\
ing party' → 'obligations' (neutral framing per baseline). \
Other: unchanged."
}}
```

### Example 2 — rewrite honoring user context (term override)

Contract clause: "Confidentiality obligations shall remain in \
effect for a period of three (3) years from the date of \
disclosure, except for trade secrets, which shall remain \
confidential for a period of seven (7) years from the date of \
disclosure."

Flag (score=2): material deviation (carve-out for trade \
secrets exceeds the 3-year term).

Baseline: "Confidentiality obligations shall remain in \
effect for a period of three (3) years from the date of \
disclosure."

Extra context from user: "Acceptable for our use case if the \
trade-secrets carve-out is limited to 5 years."

```json
{{
  "proposed_text": "Confidentiality obligations shall remain \
in effect for a period of three (3) years from the date of \
disclosure, except for trade secrets, which shall remain \
confidential for a period of five (5) years from the date of \
disclosure.",
  "rationale": "Trade-secrets carve-out limited to 5 years \
per the user's extra context. The 3-year base term matches \
the baseline. The carve-out structure (except-for-trade-\
secrets) is preserved from the original.",
  "diff_summary": "Term: 3 years (base, matches baseline) + \
5 years (trade-secrets carve-out, per user context) — was 3 \
+ 7. Carve-out structure: preserved."
}}
```
"""


# --- DE system prompt (Phase 4) ----------------------------------------
#
# Reasoning in DE legal register. The output JSON schema is
# identical; only the language of the prose fields + the
# `proposed_text` rewrite change. The drafter's `proposed_text`
# is the rewritten clause — for a DE clause, this must read as
# native DE legal register, not translated-from-EN.
DE_SYSTEM_PROMPT = """\
Sie sind der Redline-Entwurfs-Agent für clausecraft, eine \
Plattform zur Vertragsanalyse. Ihre Aufgabe ist es, eine \
einzelne Klausel aus einem Vertrag so umzuschreiben, dass sie \
mit der zugeordneten Playbook-Baseline übereinstimmt.

Der Nutzer hat eine Abweichungs-Flagge für diese Klausel \
AKZEPTIERT. Die Flagge ist die Bewertung des Spotters, dass die \
Klausel von der Baseline abweicht. Ihre Aufgabe ist es, eine \
Redline zu erstellen (eine umgeschriebene Klausel, die mit der \
Baseline übereinstimmt) — NICHT, die Flagge in Frage zu stellen. \
Wenn der Nutzer zusätzlichen Kontext beigefügt hat, berücksichti\
gen Sie diesen; andernfalls ist die Baseline das Ziel.

## Ausgabeformat

Geben Sie ein einzelnes JSON-Objekt zurück mit GENAU diesen \
Feldern (keine zusätzlichen Felder, keine Prosa außerhalb des \
JSON):

```json
{{
  "proposed_text": "<der umgeschriebene Klauseltext, wörtlich, \
als direkter Ersatz für das Original>",
  "rationale": "<1-3 Sätze, schlichte deutsche Rechtssprache, \
ohne Einleitung>",
  "diff_summary": "<Klartext-Vorher-Nachher-Zusammenfassung, \
kein Markdown, keine Diff-Syntax, geeignet für ein Audit-Protokoll>"
}}
```

Kritische Regeln für `proposed_text`:

1. **Wörtlicher Ersatz.** Der `proposed_text` ersetzt die \
   ursprüngliche Klausel in der .docx-Ausgabe. Ihre Aufgabe ist \
   es, eine einzige zusammenhängende Änderung zu erstellen, \
   keinen Diff. Umschließen Sie den Text NICHT mit Anführungs­\
   zeichen. Entwerten Sie KEINE Sonderzeichen. Geben Sie den \
   rohen Klauseltext aus.
2. **Struktur bewahren.** Wenn die ursprüngliche Klausel \
   nummerierte Listenelemente, "sofern"-Einschränkungen oder \
   Definitionen enthält, die an anderer Stelle im Vertrag \
   verwendet werden, bewahren Sie diese. Die Redline ist eine \
   einzige Änderung, kein Fragmentaustausch.
3. **Bleiben Sie nahe an der Baseline.** Die Baseline ist das \
   Ziel. Wenn der Nutzer zusätzlichen Kontext beigefügt hat \
   (z. B. "begrenzt auf 5 Jahre, nicht die 3 der Baseline"), hat \
   der Nutzerkontext Vorrang vor dem genauen Text der Baseline. \
   Andernfalls ist der Text der Baseline maßgeblich.

Kritische Regeln für `rationale`:

1. **Schlichte deutsche Rechtssprache.** Das Audit-Protokoll \
   gibt dies wörtlich wieder. Ein menschlicher Prüfer liest es, \
   um zu verstehen, *was Sie geändert haben* und *warum*. Keine \
   Marketingsprache, kein "auf Wunsch des Nutzers"-Standardtext.
2. **1-3 Sätze.** Wenn Ihre Begründung länger ist, erklären Sie \
   zu viel, statt zu redlinen.
3. **Benennen Sie die Abweichung, die Sie beheben.** Beispiel: \
   "Laufzeit von 7 Jahren auf das 3-Jahres-Maximum der Baseline \
   reduziert. Die Geschäftsgeheimnisse-Ausnahme aus dem Original \
   bleibt erhalten."

Kritische Regeln für `diff_summary`:

1. **Klartext.** Das Audit-Protokoll und der JSON-Export geben \
   dies wörtlich wieder. Kein Markdown, keine Diff-Syntax (keine \
   `+`/`-`-Zeilen, keine Unified-Diff-Markierungen). Ein einziger \
   kurzer Absatz.
2. **Vorher / nachher.** Beispiel: "Laufzeit: 7 Jahre → 3 Jahre. \
   Geschäftsgeheimnisse-Ausnahme: erhalten. Rechtswahl-Bezug: \
   unverändert."

## Wenn die Klausel nicht reparierbar ist

Wenn die Abweichung strukturell ist (z. B. der Vertrag ist eine \
unbefristete Geheimhaltungsvereinbarung und die Baseline ist eine \
3-Jahres-Laufzeit, und die "Unbefristetheit" ist der Kern des \
Geschäfts), versuchen Sie NICHT, die Klausel in etwas umzuschrei\
ben, das die Gegenseite niemals akzeptieren wird. Geben Sie trotz\
dem Ihren besten Versuch ab — die Selbstprüfungs-Schleife wird \
dies abfangen und die HITL-Benutzeroberfläche wird den Konflikt \
dem Nutzer anzeigen. **Der Entwurfs-Agent gibt immer eine Redline \
zurück; die Selbstprüfungs-Schleife entscheidet, ob sie ausgege\
ben wird.**

## Beispiele

### Beispiel 1 — saubere Umschreibung (Laufzeit-Reduktion)

Vertragsklausel: "Die empfangende Partei hat die Vertraulichkeit \
für einen Zeitraum von sieben (7) Jahren ab dem Zeitpunkt der \
Offenlegung zu wahren."

Flagge (score=2, Begründung="Die Laufzeit von 7 Jahren über­\
schreitet das 3-Jahres-Maximum der Baseline für NDAs, die \
Geschäftsgeheimnisse betreffen."): wesentliche Abweichung.

Baseline (clause_id="haftungsdauer", type="term"): "Die Vertraulich­\
keitsverpflichtungen bleiben für einen Zeitraum von drei (3) \
Jahren ab dem Zeitpunkt der Offenlegung in Kraft."

```json
{{
  "proposed_text": "Die Vertraulichkeitsverpflichtungen bleiben \
für einen Zeitraum von drei (3) Jahren ab dem Zeitpunkt der \
Offenlegung in Kraft.",
  "rationale": "Die Laufzeit von 7 Jahren wurde auf das 3-Jahres-\
Maximum der Baseline reduziert. Die 'empfangende Partei' aus \
der Originalklausel wurde beibehalten, da die neutrale Formulie\
rung der Baseline ('Verpflichtungen') unserem Standard-NDA-Formu\
lar entspricht.",
  "diff_summary": "Laufzeit: 7 Jahre → 3 Jahre. Subjekt: 'empfan\
gende Partei' → 'Verpflichtungen' (neutrale Formulierung gemäß \
Baseline). Sonstiges: unverändert."
}}
```

### Beispiel 2 — Umschreibung unter Berücksichtigung des Nutzer­\
kontexts (Laufzeit-Überschreibung)

Vertragsklausel: "Die Vertraulichkeitsverpflichtungen bleiben \
für einen Zeitraum von drei (3) Jahren ab dem Zeitpunkt der \
Offenlegung in Kraft, mit Ausnahme von Geschäftsgeheimnissen, \
die für einen Zeitraum von sieben (7) Jahren ab dem Zeitpunkt \
der Offenlegung vertraulich zu behandeln sind."

Flagge (score=2): wesentliche Abweichung (Geschäftsgeheimnisse-\
Ausnahme überschreitet die 3-Jahres-Laufzeit).

Baseline: "Die Vertraulichkeitsverpflichtungen bleiben für einen \
Zeitraum von drei (3) Jahren ab dem Zeitpunkt der Offenlegung in \
Kraft."

Zusätzlicher Nutzerkontext: "Für unseren Anwendungsfall akzep­\
tabel, wenn die Geschäftsgeheimnisse-Ausnahme auf 5 Jahre begrenzt \
wird."

```json
{{
  "proposed_text": "Die Vertraulichkeitsverpflichtungen bleiben \
für einen Zeitraum von drei (3) Jahren ab dem Zeitpunkt der \
Offenlegung in Kraft, mit Ausnahme von Geschäftsgeheimnissen, \
die für einen Zeitraum von fünf (5) Jahren ab dem Zeitpunkt der \
Offenlegung vertraulich zu behandeln sind.",
  "rationale": "Die Geschäftsgeheimnisse-Ausnahme wurde gemäß \
dem Nutzerkontext auf 5 Jahre begrenzt. Die 3-Jahres-Basislauf­\
zeit entspricht der Baseline. Die Struktur der Ausnahme (mit \
Ausnahme von Geschäftsgeheimnissen) wurde aus dem Original \
übernommen.",
  "diff_summary": "Laufzeit: 3 Jahre (Basis, entspricht der \
Baseline) + 5 Jahre (Geschäftsgeheimnisse-Ausnahme, gemäß Nutzer\
kontext) — war 3 + 7. Struktur der Ausnahme: erhalten."
}}
```
"""


# --- Self-check retry instruction --------------------------------------


def _format_flag_for_constraint(
    label: str,
    flag: DeviationFlag,
    *,
    score_labels: dict[int, str],
    citation_label: str,
    no_citation_label: str,
    baseline_type_label: str,
) -> str:
    """Render a :class:`DeviationFlag` for the self-check constraint.

    The constraint text appears in the user message on the retry.
    The drafter needs the spotter's score + rationale + citation
    so it can understand the new deviation and avoid it.

    The format is a labelled bullet list (not a JSON dump) so the
    LLM can parse it reliably. We avoid backticks / code fences
    here — the surrounding user message has its own code fences
    and nested fences are a parser-fragility risk.

    The label and citation labels are language-specific so the
    constraint text reads in the same language as the drafter's
    system prompt.
    """
    score_label = score_labels.get(flag.score, f"unknown ({flag.score})")
    parts = [
        f"{label} score: {score_label}",
        f"{label} rationale: {flag.rationale}",
    ]
    if flag.citation is not None:
        parts.append(
            f"{label} citation: clause_id={flag.citation.playbook_clause_id}, "
            f"excerpt=\"{flag.citation.contract_text_excerpt}\""
        )
    else:
        parts.append(f"{label} citation: {no_citation_label}")
    if flag.baseline_type:
        parts.append(f"{label} baseline_type: {flag.baseline_type}")
    else:
        parts.append(f"{label} {baseline_type_label}: (none)")
    return "\n".join(parts)


_EN_SCORE_LABELS: dict[int, str] = {
    0: "aligned (0)",
    1: "minor (1)",
    2: "material (2)",
    3: "unacceptable (3)",
}
_DE_SCORE_LABELS: dict[int, str] = {
    0: "konform (0)",
    1: "geringfügig (1)",
    2: "wesentlich (2)",
    3: "inakzeptabel (3)",
}


# --- User prompt --------------------------------------------------------


def build_user_message(
    drafter_input: DrafterInput,
    *,
    self_check_constraint: Optional[SelfCheckConstraint] = None,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """Return the per-call user message for the drafter.

    The message has five parts, in this order:

    1. **The accepted flag** — the spotter's verdict the user
       approved. The drafter reads the score + rationale to
       understand *why* the clause was flagged.
    2. **The original clause** — the text the drafter rewrites.
    3. **The matched baseline** — the target the rewrite aligns
       toward. The drafter's prompt renders the baseline as a
       JSON block (matching the spotter's format) so the LLM
       sees the same shape.
    4. **Extra context** — the user's free-form context from
       the HITL review (if any). The drafter surfaces this in
       the rationale.
    5. **Self-check constraint** — only on the retry. The
       previous attempt's text + the spotter's new flag, so
       the drafter knows what to avoid in attempt #2.

    On a self-check retry, the parts are reordered: the
    constraint moves to position 1 (after the section header)
    so the LLM can't miss it. The rest of the message is
    identical to a first-attempt call.

    The ``language`` parameter switches the section labels
    ("Accepted deviation flag" / "Original clause" / "Matched
    playbook baseline" / "Task" / "Self-check retry") between
    EN and DE. The clause text, baseline text, flag text, and
    user-provided extra_context are passed through verbatim.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported drafter language: {language!r}. "
            f"Supported: {sorted(SUPPORTED_LANGUAGES)}."
        )
    if language == "de":
        header_flag = "## Akzeptierte Abweichungs-Flagge"
        header_clause = "## Ursprüngliche Klausel (umzuschreiben)"
        header_baseline = "## Zugeordnete Playbook-Baseline (das Ziel)"
        header_baseline_text = (
            "## Baseline-Klauseltext (zur besseren Lesbarkeit)"
        )
        header_task = "## Aufgabe"
        header_retry = (
            "## Selbstprüfungs-Wiederholung — Ihr vorheriger Versuch hat "
            "den Spotter nicht bestanden"
        )
        extra_block_header = "## Zusätzlicher Kontext vom Nutzer"
        extra_block_intro = (
            "Der Nutzer hat beim Akzeptieren dieser Flagge den "
            "folgenden Kontext beigefügt. Berücksichtigen Sie ihn in "
            "der Redline:"
        )
        flag_score_label = "Flaggen-Score"
        flag_rationale_label = "Flaggen-Begründung"
        baseline_type_label = "Baseline-Typ"
        citation_label = "Zitation"
        no_citation_label = "(keine)"
        retry_intro = (
            "Ihr vorheriger Vorschlag hat eine NEUE Abweichung "
            "eingeführt. Der Spotter wurde erneut darauf ausgeführt "
            "und hat folgendes geflaggt:"
        )
        original_flag_intro = (
            "Die URSPRÜNGLICHE Flagge, die der Nutzer akzeptiert hat "
            "(die Sie beheben sollen), war:"
        )
        previous_proposal_intro = (
            "Ihr vorheriger Vorschlag (der die neue Abweichung "
            "eingeführt hat):"
        )
        task_first_attempt = (
            "Schreiben Sie die ursprüngliche Klausel so um, dass sie "
            "mit der Baseline übereinstimmt. Wenn zusätzlicher Kontext "
            "beigefügt ist, berücksichtigen Sie ihn (der Nutzerkontext "
            "hat Vorrang vor dem genauen Text der Baseline). Geben Sie "
            "NUR das JSON-Objekt zurück — `proposed_text`, `rationale`, "
            "`diff_summary` — ohne Prosa, ohne Markdown, ohne Erklärung "
            "außerhalb des JSON."
        )
        task_retry = (
            "Schreiben Sie die ursprüngliche Klausel so um, dass sie die "
            "URSPRÜNGLICHE Flagge behebt, OHNE die oben genannte neue "
            "Abweichung einzuführen. Bleiben Sie nahe an der Baseline. "
            "Wenn die neue Abweichung auf einen strukturellen Konflikt "
            "hinweist (z. B. die Baseline erfordert eine 3-Jahres-Laufzeit "
            "und die neue Abweichung erfordert eine unbegrenzte Laufzeit, "
            "und der ursprüngliche Nutzerkontext löst dies nicht auf), "
            "geben Sie trotzdem Ihren besten Versuch ab — die Selbstprüfungs­"
            "schleife wird den Konflikt dem Nutzer anzeigen."
            "\n\nGeben Sie NUR das JSON-Objekt zurück — `proposed_text`, "
            "`rationale`, `diff_summary` — ohne Prosa, ohne Markdown, ohne "
            "Erklärung außerhalb des JSON."
        )
        score_labels = _DE_SCORE_LABELS
        conflict_label = "Widersprüchliche Spotter-Flagge"
        original_label = "Ursprüngliche akzeptierte Flagge"
    else:
        header_flag = "## Accepted deviation flag"
        header_clause = "## Original clause (to be redlined)"
        header_baseline = "## Matched playbook baseline (the target)"
        header_baseline_text = "## Baseline clause text (rendered for readability)"
        header_task = "## Task"
        header_retry = "## Self-check retry — your previous attempt failed the spotter"
        extra_block_header = "## Extra context from the user"
        extra_block_intro = (
            "The user attached the following context when "
            "accepting this flag. Honor it in the redline:"
        )
        flag_score_label = "flag score"
        flag_rationale_label = "flag rationale"
        baseline_type_label = "baseline_type"
        citation_label = "citation"
        no_citation_label = "(none)"
        retry_intro = (
            "Your previous proposal introduced a NEW deviation. The "
            "spotter was re-run on it and flagged the following:"
        )
        original_flag_intro = (
            "The ORIGINAL flag the user accepted (which you are "
            "supposed to be fixing) was:"
        )
        previous_proposal_intro = (
            "Your previous proposal (which introduced the new "
            "deviation):"
        )
        task_first_attempt = (
            "Rewrite the original clause so it aligns with the "
            "baseline. If extra context is attached, honor it "
            "(the user context overrides the baseline's exact "
            "text). Return ONLY the JSON object — `proposed_text`, "
            "`rationale`, `diff_summary` — with no prose, no "
            "markdown, no explanation outside the JSON."
        )
        task_retry = (
            "Rewrite the original clause so it addresses the "
            "ORIGINAL flag WITHOUT introducing the new deviation "
            "above. Stay close to the baseline, but if the new "
            "deviation points to a structural conflict (e.g. the "
            "baseline requires a 3-year term and the new deviation "
            "requires a perpetual term, and the user's original "
            "context doesn't resolve it), produce your best attempt "
            "anyway — the self-check loop will surface the conflict "
            "to the user."
            "\n\nReturn ONLY the JSON object — `proposed_text`, "
            "`rationale`, `diff_summary` — with no prose, no "
            "markdown, no explanation outside the JSON."
        )
        score_labels = _EN_SCORE_LABELS
        conflict_label = "Conflicting spotter flag"
        original_label = "Original accepted flag"

    flag = drafter_input.flag
    baseline = drafter_input.baseline

    baseline_payload: dict[str, Any] = {
        "id": baseline.clause_id,
        "type": baseline.type,
        "title": baseline.title,
        "text": baseline.text,
        "source_url": baseline.source_url,
        "similarity": round(float(baseline.similarity), 4),
    }
    baseline_json = json.dumps(baseline_payload, indent=2, ensure_ascii=False)
    # Escape triple-backticks in the clause text to avoid closing
    # the JSON block early. Same pattern as the spotter.
    safe_clause = drafter_input.clause_text.replace("```", "ʼʼʼ")
    safe_baseline = baseline.text.replace("```", "ʼʼʼ")

    if self_check_constraint is None:
        # First attempt — standard prompt shape.
        extra_block = ""
        if drafter_input.extra_context:
            extra_block = (
                f"\n{extra_block_header}\n\n"
                f"{extra_block_intro}\n\n"
                f"> {drafter_input.extra_context}\n"
            )
        # Score label for the flag is the same shape as the
        # constraint's score label so the drafter sees a
        # consistent vocabulary across attempts.
        flag_score = score_labels.get(
            flag.score, f"unknown ({flag.score})"
        )
        return (
            f"{header_flag}\n\n"
            f"- {flag_score_label}: {flag.score} ({flag_score})\n"
            f"- {flag_rationale_label}: {flag.rationale}\n"
            f"- {baseline_type_label}: {flag.baseline_type or '(none)'}\n"
            + (
                f"- {citation_label}: clause_id="
                f"{flag.citation.playbook_clause_id}, "
                f"excerpt=\"{flag.citation.contract_text_excerpt}\"\n"
                if flag.citation is not None
                else f"- {citation_label}: {no_citation_label}\n"
            )
            + extra_block
            + f"\n{header_clause}\n\n"
            "```\n"
            f"{safe_clause}\n"
            "```\n\n"
            f"{header_baseline}\n\n"
            "```json\n"
            f"{baseline_json}\n"
            "```\n\n"
            f"{header_baseline_text}\n\n"
            "```\n"
            f"{safe_baseline}\n"
            "```\n\n"
            f"{header_task}\n\n"
            f"{task_first_attempt}"
        )

    # Self-check retry — constraint at the top so the drafter
    # can't miss it.
    conflict_text = _format_flag_for_constraint(
        conflict_label,
        self_check_constraint.conflicting_flag,
        score_labels=score_labels,
        citation_label=citation_label,
        no_citation_label=no_citation_label,
        baseline_type_label=baseline_type_label,
    )
    original_flag_text = _format_flag_for_constraint(
        original_label,
        flag,
        score_labels=score_labels,
        citation_label=citation_label,
        no_citation_label=no_citation_label,
        baseline_type_label=baseline_type_label,
    )
    safe_previous = self_check_constraint.previous_proposed_text.replace(
        "```", "ʼʼʼ"
    )
    return (
        f"{header_retry}\n\n"
        f"{retry_intro}\n\n"
        f"{conflict_text}\n\n"
        f"{original_flag_intro}\n\n"
        f"{original_flag_text}\n\n"
        f"{previous_proposal_intro}\n\n"
        "```\n"
        f"{safe_previous}\n"
        "```\n\n"
        f"{header_baseline}\n\n"
        "```json\n"
        f"{baseline_json}\n"
        "```\n\n"
        f"{header_task}\n\n"
        f"{task_retry}"
    )


def _score_label(score: int) -> str:
    """Human-readable label for a deviation score (0..3)."""
    return {
        0: "aligned",
        1: "minor",
        2: "material",
        3: "unacceptable",
    }.get(score, f"unknown ({score})")


# --- Messages -----------------------------------------------------------


def build_messages(
    drafter_input: DrafterInput,
    *,
    self_check_constraint: Optional[SelfCheckConstraint] = None,
    language: str | None = None,
) -> list[dict[str, str]]:
    """Return the chat messages list for a single drafter call.

    Mirrors the spotter's :func:`app.agents.deviation_spotter.prompt.build_messages`
    shape: a single system message + a single user message. The
    system prompt is identical between attempts (the self-check
    constraint goes in the user message). The few-shot examples
    in the system prompt are calibrated for first-attempt calls
    but the retry path is rare enough (≤10% of accepted flags in
    our rough estimate) that we don't bother swapping examples.

    The ``language`` parameter is read from
    :attr:`DrafterInput.clause_language` when omitted. The
    dispatch is per-clause: a mixed-language contract picks the
    EN system prompt + EN user-message labels for
    ``language="en"`` clauses and the DE system prompt + DE
    user-message labels for ``language="de"`` clauses. An
    unknown ``language`` raises :class:`ValueError` (no silent
    EN fallback — that's the bug the per-clause switch is
    designed to catch).
    """
    lang = (
        language if language is not None else drafter_input.clause_language
    )
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported drafter language: {lang!r}. "
            f"Supported: {sorted(SUPPORTED_LANGUAGES)}."
        )
    if lang == "de":
        system_prompt = DE_SYSTEM_PROMPT
    else:
        system_prompt = SYSTEM_PROMPT
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": build_user_message(
                drafter_input,
                self_check_constraint=self_check_constraint,
                language=lang,
            ),
        },
    ]


__all__ = [
    "DEFAULT_LANGUAGE",
    "DE_SYSTEM_PROMPT",
    "SUPPORTED_LANGUAGES",
    "SYSTEM_PROMPT",
    "build_messages",
    "build_user_message",
]
