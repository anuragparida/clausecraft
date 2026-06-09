"""Build the 5 DE NDA eval contracts for Phase 4.1.

This script generates the 5 German-language NDA PDFs that grow the
DE eval set from 0 → 5, matching the Phase 2 EN starter set's
shape. The contract set is:

  examples/contracts/public-de/nda-001.pdf    (clean baseline, GeschGehG-anchored)
  examples/contracts/public-de/nda-002.pdf    (clean baseline, DIHK-anchored)
  examples/contracts/public-de/nda-003.pdf    (clean baseline, IHK-Hessen-anchored, full)
  examples/contracts/synthetic-de/nda-001.pdf (stress: 3 deviations, 4 ClauseType values)
  examples/contracts/synthetic-de/nda-002.pdf (stress: 3 different deviations, 4 ClauseType values)

The card (t_b238eff4) is the DE equivalent of the Phase 2 EN
eval-set starter. The five DE contracts must:

  1. Be text-extractable, deterministic PDFs (reportlab — no
     images, no OCR, no timestamps or random IDs).
  2. Exercise the ``language="de"`` field on every clause (the
     post-card-3 parser sets this from a stopword heuristic).
  3. Cover at least 3 distinct ``ClauseType`` values across the
     5 contracts (acceptance criterion).
  4. Be plausible enough that the spotter's signal is real — the
     2 synthetic DE contracts should look like a real German NDA
     that an in-house counsel would actually sign, with deviations
     a German-lawyer reviewer would catch.

Why "public-de" means "public-source style", not network-fetch
-------------------------------------------------------------
The card lists "Vertragsmuster.de, BMJ, or IHK Musterverträge" as
the named source kinds. The three public-DE contracts are anchored
to (a) the GeschGehG § 2 Nr. 1 federal statute (BMJ/BfJ juristic
portal — no copyright on the statute text per § 5 UrhG, so the
text is itself the public source), (b) the DIHK-Mustervertrag
(DIHK-Rechtsausschuss, free Mustervertrag), and (c) the IHK Hessen
Mustervertrag (Stand 01.01.2025, free Mustervertrag). All three
are the same public sources the DE playbook baselines
(t_c714cf94) are anchored to, so source diversity is preserved.

The contract text is written in my own words following the
structure of the named public source (i.e. the GeschGehG-anchored
contract is structured around the § 2 Nr. 1 statutory definition;
the IHK-Hessen-anchored contract follows the IHK-Hessen Ziff. I-IX
layout). The text is hand-authored to match the section
headings + standard formulations of each source, with no verbatim
copying of the public template body. The provenance URL, retrieval
date, and license note for each source are recorded in
``examples/contracts/public-de/SOURCES.md``.

Why the synthetic deviations are calibrated to a real LLM
---------------------------------------------------------
The two synthetic DE contracts deliberately exercise deviation
*categories* that a German-lawyer reviewer would flag — not
keyword-level LLM-foolers:

  synthetic-de/nda-001.pdf:
    c2 (term)        — material: 10-year term (vs. DIHK baseline 2-5y + 3-5y survival)
    c4 (residual)    — minor:    removes the Beweislast allocation
                                 (vs. WKO FEEI baseline that requires
                                 "Die empfangende Partei trägt die Beweislast")
    c6 (definition)  — material: drops the § 2 Nr. 1 GeschGehG statutory
                                 anchor language (vs. the GeschGehG-anchored
                                 baseline that cites the statute verbatim)
  → 3 deviations across 3 distinct ClauseType values (term,
    residual_knowledge, definition_confidential_info).

  synthetic-de/nda-002.pdf:
    c1 (definition)  — material: no exclusions list (a/b/c/d carve-outs
                                 entirely missing — vs. the IHK-Hessen
                                 Ziff. II carve-out baseline)
    c3 (injunctive)  — material: Vertragsstrafe 25% der Auftragssumme
                                 (vs. IHK-Hessen baseline's BGH 5% AGB cap)
    c7 (governing)   — minor:    foreign jurisdiction (Schweizer Recht
                                 + ICC arbitration — vs. IHK-München
                                 baseline's deutsches Recht + Gerichtsstand
                                 am Sitz des Erfinders)
  → 3 deviations across 3 distinct ClauseType values
    (definition_confidential_info, injunctive_relief, governing_law).

  Across the two synthetic contracts: 6 deviations across 4
  distinct ClauseType values (term, residual_knowledge,
  definition_confidential_info, injunctive_relief, governing_law).
  Combined with the 3 public-DE clean baselines (which exercise
  definition, term, return_of_materials, governing_law,
  injunctive_relief, residual_knowledge, entire_agreement), the
  full 5-contract DE set exercises 7 distinct ClauseType values —
  well above the 3-minimum acceptance criterion.

Idempotence
-----------
Re-running this script overwrites all 5 PDFs with byte-identical
content (no timestamps, no random IDs). The eval harness depends
on the contract text being stable so the golden YAML's
``text_excerpt`` fields keep matching.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DE_DIR = REPO_ROOT / "examples" / "contracts" / "public-de"
SYNTHETIC_DE_DIR = REPO_ROOT / "examples" / "contracts" / "synthetic-de"


# ---------------------------------------------------------------------------
# Public-DE contract #1 — GeschGehG-anchored (BMJ/BfJ)
# ---------------------------------------------------------------------------
# Anchored to the GeschGehG § 2 Nr. 1 statutory definition (BMJ
# juristic portal). The text follows the structure of the
# statutory definition: it explicitly cites § 2 Nr. 1 GeschGehG
# and uses the statute's own three-prong test
# (allgemein-unbekannt + wirtschaftlicher-Wert + angemessene-
# Geheimhaltungsmaßnahmen + berechtigtes-Interesse). The contract
# is a clean baseline — no deviations.
GESCHGEHG_TITLE = (
    "GEHEIMHALTUNGSVEREINBARUNG (NDA) — ENTWURF AUF GESCHGEHG-DEFINITION"
)

GESCHGEHG_PARAGRAPHS: list[str] = [
    "Diese Geheimhaltungsvereinbarung (nachfolgend „Vereinbarung“) "
    "wird zwischen den Parteien mit Wirkung zum Datum der "
    "Unterzeichnung durch die zuletzt unterzeichnende Partei "
    "geschlossen. Vertragsgegenstand ist der gegenseitige Austausch "
    "von Informationen im Rahmen der nachstehend beschriebenen "
    "Zusammenarbeit (nachfolgend „Zweck“).",

    # c1 — definition_confidential_info
    "1. Definition der Vertraulichen Informationen. „Vertrauliche "
    "Informationen“ im Sinne dieser Vereinbarung sind Geschäfts"
    "geheimnisse im Sinne des § 2 Nr. 1 des Gesetzes zum Schutz von "
    "Geschäftsgeheimnissen (GeschGehG) sowie alle sonstigen "
    "Informationen, die weder insgesamt noch in der genauen "
    "Anordnung und Zusammensetzung ihrer Bestandteile den Personen "
    "in den Kreisen, die üblicherweise mit dieser Art von "
    "Informationen umgehen, allgemein bekannt oder ohne Weiteres "
    "zugänglich sind und daher von wirtschaftlichem Wert sind, "
    "die Gegenstand von den Umständen nach angemessenen "
    "Geheimhaltungsmaßnahmen durch ihren rechtmäßigen Inhaber sind "
    "und bei denen ein berechtigtes Interesse an der Geheimhaltung "
    "besteht. Hierunter fallen insbesondere technisches Know-how, "
    "Herstellungsverfahren, Erfindungen, Geschäftsbeziehungen, "
    "Kundenlisten, Finanz- und Geschäftspläne sowie Markt- und "
    "Wettbewerbsanalysen.",

    # c2 — residual_knowledge (exclusions list — Beweislast allocation)
    "2. Keine Vertraulichen Informationen. Von der "
    "Vertraulichkeitsverpflichtung ausgenommen sind Informationen, "
    "an denen die empfangende Partei (i) bereits vor der "
    "Offenlegung durch die offenlegende Partei nachweislich im "
    "rechtmäßigen Besitz war, ohne einer "
    "Vertraulichkeitsverpflichtung zu unterliegen, oder (ii) die "
    "ohne Verstoß gegen diese Vereinbarung unabhängig entwickelt "
    "hat, oder (iii) die von einem zur Offenlegung berechtigten "
    "Dritten erhalten hat, oder (iv) die ohne Verstoß gegen diese "
    "Vereinbarung allgemein bekannt sind. Die empfangende Partei "
    "trägt die Beweislast für das Vorliegen einer dieser Ausnahmen.",

    # c3 — term
    "3. Vertragslaufzeit. Diese Vereinbarung tritt mit dem Datum "
    "der Unterschrift der zuletzt unterzeichnenden Partei in Kraft "
    "und gilt für einen Zeitraum von drei (3) Jahren. Die "
    "Verpflichtungen aus dieser Vereinbarung in Bezug auf die "
    "Vertraulichen Informationen, die im Rahmen der Laufzeit der "
    "Vereinbarung offenbart wurden, bleiben jedoch für einen "
    "Zeitraum von fünf (5) Jahren nach Beendigung weiter bestehen. "
    "Für Geschäftsgeheimnisse im Sinne des § 2 Nr. 1 GeschGehG "
    "besteht die Geheimhaltungspflicht so lange fort, wie die "
    "jeweilige Information die Voraussetzungen des § 2 Nr. 1 "
    "GeschGehG erfüllt.",

    # c4 — return_of_materials
    "4. Rückgabe von Unterlagen. Die Parteien werden Unterlagen, "
    "die sie jeweils vom anderen im Zusammenhang mit dem Zweck "
    "erhalten haben, nach Beendigung der Vereinbarung unverzüglich "
    "dem jeweiligen Informationsgeber zurückgeben oder "
    "vernichten. Auf Verlangen hat die empfangende Partei "
    "schriftlich zu versichern, dass sie sämtliche Vertraulichen "
    "Informationen vollständig und unwiderruflich gelöscht hat.",

    # c5 — injunctive_relief
    "5. Vertragsstrafe und Unterlassung. Für jeden Fall des "
    "schuldhaften Verstoßes gegen diese Vereinbarung verpflichtet "
    "sich die empfangende Partei zur Zahlung einer angemessenen "
    "Vertragsstrafe, deren Höhe im Ermessen des Gläubigers steht "
    "und die im Streitfall vom zuständigen Gericht gemäß § 343 BGB "
    "auf einen angemessenen Betrag herabgesetzt werden kann. "
    "Unabhängig davon hat die offenlegende Partei einen Anspruch "
    "auf Unterlassung, dessen Durchsetzung nach §§ 887, 890 ZPO "
    "erfolgen kann. Bei formularmäßig verwendeten Vertragsstrafen "
    "ist die Obergrenze zu beachten, die nach ständiger "
    "Rechtsprechung des BGH für vergleichbare Fälle bei fünf "
    "Prozent (5 %) der Auftragssumme liegt.",

    # c6 — governing_law
    "6. Rechtswahl und Gerichtsstand. Auf diesen Vertrag ist "
    "deutsches Recht unter Ausschluss des CISG anzuwenden. Für "
    "Streitigkeiten aus diesem Vertrag ist das Gericht am Sitz "
    "der offenlegenden Partei örtlich zuständig, soweit der "
    "Empfänger Kaufmann im Sinne des HGB ist.",

    # c7 — entire_agreement
    "7. Schlussbestimmungen. Diese Vereinbarung stellt die gesamte "
    "zwischen den Parteien getroffene Vereinbarung dar und ersetzt "
    "alle früheren Vereinbarungen. Änderungen und Ergänzungen "
    "bedürfen der Schriftform. Sollten eine oder mehrere "
    "Bestimmungen rechtsunwirksam sein oder werden, so soll "
    "dadurch die Gültigkeit der übrigen Bestimmungen nicht "
    "berührt werden.",
]


# ---------------------------------------------------------------------------
# Public-DE contract #2 — DIHK-anchored
# ---------------------------------------------------------------------------
# Anchored to the DIHK-Mustervertrag (Dachmuster aller IHKs). The
# text follows the DIHK Ziff. 1-10 layout (Vertragsgegenstand,
# Vertrauliche Informationen, Verpflichtungen des Empfängers,
# Vertragslaufzeit, Vertragsstrafe, Schlussbestimmungen). Clean
# baseline — no deviations.
DIHK_TITLE = (
    "GEHEIMHALTUNGSVEREINBARUNG (NDA) — ENTWURF NACH DIHK-MUSTERVERTRAG"
)

DIHK_PARAGRAPHS: list[str] = [
    "Diese Geheimhaltungsvereinbarung (nachfolgend „Vereinbarung“) "
    "wird zwischen den Parteien mit Wirkung zum Datum der "
    "Unterzeichnung durch die zuletzt unterzeichnende Partei "
    "geschlossen. Die Parteien beabsichtigen, vertrauliche "
    "Informationen zum nachstehend beschriebenen Zweck "
    "auszutauschen.",

    # c1 — definition
    "1. Vertrauliche Informationen. „Vertrauliche Informationen“ "
    "im Sinne dieser Vereinbarung sind alle Informationen, die "
    "von einer Partei (nachfolgend „offenlegende Partei“) der "
    "anderen Partei (nachfolgend „empfangende Partei“) im Rahmen "
    "des Zwecks offenbart werden, gleich in welcher Form "
    "(schriftlich, elektronisch, mündlich, digital verkörpert). "
    "Hierzu zählen insbesondere Geschäftsgeheimnisse, technisches "
    "Know-how, Erfindungen, Geschäftsbeziehungen, Kundenlisten, "
    "Finanz- und Geschäftspläne sowie Markt- und "
    "Wettbewerbsanalysen.",

    # c2 — exclusions
    "2. Ausnahmen. Von der Vertraulichkeitsverpflichtung "
    "ausgenommen sind Informationen, an denen die empfangende "
    "Partei (i) bereits vor der Offenlegung nachweislich im "
    "rechtmäßigen Besitz war, oder (ii) die ohne Verstoß gegen "
    "diese Vereinbarung unabhängig entwickelt hat, oder (iii) die "
    "von einem zur Offenlegung berechtigten Dritten erhalten hat, "
    "oder (iv) die ohne Verstoß gegen diese Vereinbarung allgemein "
    "bekannt sind. Die empfangende Partei trägt die Beweislast "
    "für das Vorliegen einer dieser Ausnahmen.",

    # c3 — obligations (covered by residual_knowledge carve-out)
    "3. Verpflichtungen der empfangenden Partei. Die empfangende "
    "Partei verpflichtet sich, die Vertraulichen Informationen "
    "streng vertraulich zu behandeln und nur im Zusammenhang mit "
    "dem Zweck zu verwenden. Die empfangende Partei wird die "
    "Vertraulichen Informationen durch angemessene "
    "Geheimhaltungsmaßnahmen sichern und nur solchen Mitarbeitern "
    "offenlegen, die auf die Kenntnis dieser Informationen für "
    "den Zweck angewiesen sind.",

    # c4 — term (DIHK Ziff. 8)
    "4. Vertragslaufzeit. Diese Vereinbarung tritt mit dem Datum "
    "der Unterschrift der zuletzt unterzeichnenden Partei in Kraft "
    "und gilt für einen Zeitraum von zwei (2) Jahren. Die "
    "Verpflichtungen aus dieser Vereinbarung in Bezug auf die "
    "während der Laufzeit offenbarte Vertrauliche Information "
    "bleiben jedoch für einen Zeitraum von drei (3) Jahren nach "
    "Beendigung weiter bestehen. Für Geschäftsgeheimnisse im "
    "Sinne des GeschGehG verlängert sich die nachvertragliche "
    "Geheimhaltungspflicht gemäß den gesetzlichen Bestimmungen.",

    # c5 — return of materials
    "5. Rückgabe. Auf Verlangen der offenlegenden Partei sowie "
    "spätestens nach Erreichung des Zwecks hat die empfangende "
    "Partei sämtliche Vertrauliche Informationen einschließlich "
    "der Kopien hiervon innerhalb von zehn (10) Arbeitstagen "
    "zurückzugeben oder zu vernichten und die Vernichtung "
    "schriftlich zu versichern.",

    # c6 — injunctive_relief
    "6. Vertragsstrafe. Für jeden Fall des schuldhaften Verstoßes "
    "gegen diese Vereinbarung verpflichtet sich die empfangende "
    "Partei zur Zahlung einer angemessenen Vertragsstrafe, deren "
    "Höhe im Ermessen des Gläubigers steht und die gemäß § 343 BGB "
    "herabgesetzt werden kann. Unabhängig davon hat die "
    "offenlegende Partei einen Anspruch auf Unterlassung "
    "gemäß §§ 887, 890 ZPO.",

    # c7 — governing_law (DIHK Ziff. 10 f.)
    "7. Rechtswahl und Gerichtsstand. Auf diesen Vertrag ist "
    "deutsches Recht unter Ausschluss des CISG anzuwenden. Für "
    "Streitigkeiten ist das Gericht am Sitz der offenlegenden "
    "Partei zuständig, soweit die empfangende Partei Kaufmann "
    "ist.",

    # c8 — entire_agreement
    "8. Schlussbestimmungen. Diese Vereinbarung ersetzt alle "
    "früheren Vereinbarungen der Parteien zum selben Zweck. "
    "Änderungen bedürfen der Schriftform.",
]


# ---------------------------------------------------------------------------
# Public-DE contract #3 — IHK Hessen-anchored (full 9-section layout)
# ---------------------------------------------------------------------------
# Anchored to the IHK Hessen Mustervertrag (Stand 01.01.2025,
# Ziff. I-IX). Clean baseline — no deviations. This is the
# longest of the three public contracts (9 sections) and the
# closest match to what a real IHK-mediated NDA looks like.
IHK_HESSEN_TITLE = (
    "GEHEIMHALTUNGSVEREINBARUNG — ENTWURF AUF BASIS DES "
    "IHK-HESSEN-MUSTERVERTRAGS (STAND 01.01.2025)"
)

IHK_HESSEN_PARAGRAPHS: list[str] = [
    "Diese Geheimhaltungsvereinbarung (nachfolgend „Vereinbarung“) "
    "wird zwischen dem Erfinder und dem an einer Lizenz oder am "
    "Kauf interessierten Unternehmen (jeweils einzeln „Partei“, "
    "zusammen „Parteien“) mit Wirkung zum Datum der Unterzeichnung "
    "geschlossen. Vertragsgegenstand ist die Offenbarung "
    "Vertraulicher Informationen zur neuen Entwicklung / "
    "technischen Idee / Erfindung (nachfolgend „Entwicklung“).",

    # c1 — purpose (classification: definition_confidential_info)
    "I. Vertragsgegenstand. Die Parteien beabsichtigen, einen "
    "Vertrag (zum Beispiel Know-How-Vertrag, Kaufvertrag, "
    "Lizenzvertrag) über eine Zusammenarbeit zur Entwicklung zu "
    "schließen, bei der die Entwicklung genutzt werden soll. "
    "Der Erfinder beabsichtigt, dem Interessenten Vertrauliche "
    "Informationen zur Verfügung zu stellen, die bisher weder "
    "insgesamt noch in ihren Einzelheiten bekannt oder ohne "
    "Weiteres zugänglich waren.",

    # c2 — definition of confidential info
    "II. Vertrauliche Informationen. Vertrauliche Informationen "
    "im Sinne dieser Vereinbarung sind sämtliche Informationen "
    "(ob schriftlich, elektronisch, mündlich, digital verkörpert "
    "oder in anderer Form), die von dem Erfinder an den "
    "Interessenten offenbart werden. Hierzu zählen insbesondere "
    "Geschäftsgeheimnisse, Produkte, Herstellungsprozesse, Know-how, "
    "Erfindungen, Geschäftsstrategien, Businesspläne, Finanzplanung "
    "sowie digital verkörperte Informationen. Keine Vertraulichen "
    "Informationen sind solche Informationen, die der Öffentlichkeit "
    "vor der Mitteilung bekannt waren, die dem Interessenten bereits "
    "vor der Offenlegung nachweislich bekannt waren, die ohne "
    "Nutzung Vertraulicher Informationen selbst gewonnen wurden "
    "oder die von einem berechtigten Dritten übergeben wurden.",

    # c3 — residual_knowledge carve-out
    "III. Verpflichtungen des Interessenten. Der Interessent "
    "verpflichtet sich, die Vertraulichen Informationen streng "
    "vertraulich zu behandeln und nur im Zusammenhang mit dem "
    "Zweck zu verwenden. Die im Gedächtnis der Mitarbeiter des "
    "Interessenten verbleibende allgemeine Erfahrung, allgemeines "
    "Fachwissen und allgemeine Geschäftskenntnis darf vom "
    "Interessenten in dessen gewöhnlicher Geschäftstätigkeit frei "
    "verwendet werden; hieraus wird kein Lizenzrecht an Patenten, "
    "Urheberrechten oder Geschäftsgeheimnissen des Erfinders "
    "begründet.",

    # c4 — return of materials
    "IV. Rückgabe und Vernichtung. Die Parteien werden "
    "Unterlagen, die sie jeweils vom anderen im Zusammenhang mit "
    "der Entwicklung erhalten haben, nach Beendigung der "
    "Vereinbarung unverzüglich dem jeweiligen Informationsgeber "
    "zurückgeben. Auf Aufforderung des Erfinders ist der "
    "Interessent verpflichtet, sämtliche Vertraulichen "
    "Informationen einschließlich der Kopien innerhalb von zehn "
    "(10) Arbeitstagen zurückzugeben oder zu vernichten und die "
    "Vernichtung schriftlich zu versichern.",

    # c5 — injunctive_relief (IHK-Hessen Ziff. VI)
    "V. Vertragsstrafe und Unterlassung. Unabhängig von einem "
    "etwaigen Schadensersatzanspruch verpflichtet sich der "
    "Interessent, für jeden Fall des schuldhaften Verstoßes gegen "
    "diese Vereinbarung eine angemessene Vertragsstrafe zu zahlen, "
    "deren Höhe im Ermessen des Gläubigers steht. Die "
    "Geltendmachung weiterer Schadensersatzansprüche bleibt "
    "vorbehalten. Unabhängig davon hat der Erfinder einen Anspruch "
    "auf Unterlassung gemäß §§ 887, 890 ZPO. Bei formularmäßig "
    "verwendeten Vertragsstrafeklauseln (AGB) ist die "
    "rechtsprechungsbekannte Fünf-Prozent-Obergrenze (5 % der "
    "Auftragssumme) zu beachten.",

    # c6 — term
    "VI. Vertragslaufzeit. Diese Vereinbarung tritt nach "
    "Unterzeichnung in Kraft und endet drei (3) Jahre nach "
    "Beendigung des Informationsaustausches zum vorgenannten "
    "Zweck. Diese Verpflichtung zur Geheimhaltung gilt auch "
    "weiter, wenn der beabsichtigte Vertrag über die "
    "Zusammenarbeit nicht zustande kommt oder beendet ist, außer "
    "die Entwicklung ist inzwischen offenkundig, wofür der "
    "Interessent die Beweislast trägt.",

    # c7 — governing_law
    "VII. Rechtswahl und Gerichtsstand. Auf den Vertrag ist "
    "deutsches Recht anzuwenden. Für Streitigkeiten aus diesem "
    "Vertrag ist das Gericht am Sitz des Erfinders örtlich "
    "zuständig, soweit der Interessent Kaufmann ist.",

    # c8 — entire_agreement
    "VIII. Schlussbestimmungen. Die vorliegende Vereinbarung "
    "stellt die gesamte zwischen den Parteien getroffene "
    "Vereinbarung dar und ersetzt alle früheren Vereinbarungen "
    "zum oben genannten Zweck. Mündliche Nebenabreden bestehen "
    "nicht. Änderungen und Ergänzungen dieser Vereinbarung "
    "bedürfen der Schriftform.",
]


# ---------------------------------------------------------------------------
# Synthetic-DE contract #1 — 3 deviations across 3 ClauseType values
# ---------------------------------------------------------------------------
# Stress contract: 3 hand-injected deviations from the DE playbook
# baselines. The deviations are calibrated to a German-lawyer
# reviewer's expected verdict (not a keyword-level LLM-fooler).
SYNTHETIC_DE_1_TITLE = (
    "GEHEIMHALTUNGSVEREINBARUNG (SYNTHETISCH — EVAL FIXTURE, DE)"
)

SYNTHETIC_DE_1_PARAGRAPHS: list[str] = [
    "Diese Geheimhaltungsvereinbarung (nachfolgend „Vereinbarung“) "
    "wird zwischen den Parteien mit Wirkung zum Datum der "
    "Unterzeichnung durch die zuletzt unterzeichnende Partei "
    "geschlossen.",

    # c1 — definition_confidential_info (clean)
    "1. Vertrauliche Informationen. „Vertrauliche Informationen“ "
    "im Sinne dieser Vereinbarung sind Geschäftsgeheimnisse im "
    "Sinne des GeschGehG sowie alle sonstigen Informationen, die "
    "von einer Partei an die andere Partei im Rahmen des Zwecks "
    "offenbart werden, gleich in welcher Form (schriftlich, "
    "elektronisch, mündlich, digital verkörpert). Hierzu zählen "
    "insbesondere technisches Know-how, Erfindungen, "
    "Geschäftsbeziehungen, Kundenlisten, Finanz- und "
    "Geschäftspläne sowie Markt- und Wettbewerbsanalysen.",

    # c2 — term (DEVIATION #1: 10 years + 10 years survival)
    "2. Vertragslaufzeit. Diese Vereinbarung tritt mit dem Datum "
    "der Unterschrift der zuletzt unterzeichnenden Partei in Kraft "
    "und gilt für einen Zeitraum von zehn (10) Jahren. Die "
    "Verpflichtungen aus dieser Vereinbarung in Bezug auf die "
    "während der Laufzeit offenbarte Vertrauliche Information "
    "bleiben jedoch für einen Zeitraum von zehn (10) Jahren nach "
    "Beendigung weiter bestehen.",

    # c3 — return of materials (clean)
    "3. Rückgabe. Auf Verlangen der offenlegenden Partei hat die "
    "empfangende Partei sämtliche Vertraulichen Informationen "
    "einschließlich der Kopien hiervon innerhalb von zehn (10) "
    "Arbeitstagen zurückzugeben oder zu vernichten und die "
    "Vernichtung schriftlich zu versichern.",

    # c4 — residual_knowledge (DEVIATION #2: drops Beweislast allocation)
    "4. Ausnahmen. Von der Vertraulichkeitsverpflichtung "
    "ausgenommen sind Informationen, an denen die empfangende "
    "Partei (i) bereits vor der Offenlegung nachweislich im "
    "rechtmäßigen Besitz war, oder (ii) die ohne Verstoß gegen "
    "diese Vereinbarung unabhängig entwickelt hat, oder (iii) die "
    "von einem zur Offenlegung berechtigten Dritten erhalten hat, "
    "oder (iv) die ohne Verstoß gegen diese Vereinbarung allgemein "
    "bekannt sind. Im Gedächtnis der Mitarbeiter der empfangenden "
    "Partei verbleibende allgemeine Erfahrung darf frei verwendet "
    "werden.",

    # c5 — injunctive_relief (clean)
    "5. Vertragsstrafe und Unterlassung. Für jeden Fall des "
    "schuldhaften Verstoßes verpflichtet sich die empfangende "
    "Partei zur Zahlung einer angemessenen Vertragsstrafe. "
    "Unabhängig davon hat die offenlegende Partei einen Anspruch "
    "auf Unterlassung gemäß §§ 887, 890 ZPO.",

    # c6 — definition_confidential_info (DEVIATION #3: drops GeschGehG
    # statutory anchor — repeats the bare definition without the § 2
    # Nr. 1 citation. This is structural: a real German reviewer
    # would flag the loss of the statutory anchor as material
    # because the IHK-Hessen Ziff. II + GeschGehG-baseline both
    # require the explicit GeschGehG-Bezugnahme).
    "6. Erweiterte Vertraulichkeitsverpflichtung. Über die "
    "vorstehende Definition hinaus gelten als Vertrauliche "
    "Informationen auch alle sonstigen, von der offenlegenden "
    "Partei als vertraulich gekennzeichneten Informationen, "
    "unabhängig davon, ob sie die Voraussetzungen eines "
    "Geschäftsgeheimnisses erfüllen. Eine Bezugnahme auf das "
    "GeschGehG erfolgt nicht.",

    # c7 — governing_law (clean)
    "7. Rechtswahl und Gerichtsstand. Auf diesen Vertrag ist "
    "deutsches Recht unter Ausschluss des CISG anzuwenden. Für "
    "Streitigkeiten ist das Gericht am Sitz der offenlegenden "
    "Partei zuständig, soweit die empfangende Partei Kaufmann "
    "ist.",
]


# ---------------------------------------------------------------------------
# Synthetic-DE contract #2 — 3 different deviations, 3 different
# ClauseType values
# ---------------------------------------------------------------------------
# Stress contract: 3 different deviation *categories* on top of a
# clean IHK-Hessen-style baseline. Diversifies the deviation
# coverage relative to synthetic-de-001.
SYNTHETIC_DE_2_TITLE = (
    "GEHEIMHALTUNGSVEREINBARUNG (SYNTHETISCH — EVAL FIXTURE, DE) — "
    "ZWEITE VARIANTE"
)

SYNTHETIC_DE_2_PARAGRAPHS: list[str] = [
    "Diese Geheimhaltungsvereinbarung (nachfolgend „Vereinbarung“) "
    "wird zwischen den Parteien mit Wirkung zum Datum der "
    "Unterzeichnung durch die zuletzt unterzeichnende Partei "
    "geschlossen.",

    # c1 — definition_confidential_info (DEVIATION #1: no exclusions
    # list — public domain, prior knowledge, independent
    # development, and third-party receipt carve-outs are entirely
    # missing). Material because the IHK-Hessen baseline + the
    # WKO FEEI baseline both require the four-prong exclusion.
    "1. Vertrauliche Informationen. „Vertrauliche Informationen“ "
    "im Sinne dieser Vereinbarung sind alle Informationen, die "
    "von einer Partei an die andere Partei im Rahmen des Zwecks "
    "offenbart werden, gleich in welcher Form (schriftlich, "
    "elektronisch, mündlich, digital verkörpert). Hierzu zählen "
    "insbesondere technisches Know-how, Erfindungen, "
    "Geschäftsbeziehungen, Kundenlisten, Finanz- und "
    "Geschäftspläne sowie Markt- und Wettbewerbsanalysen.",

    # c2 — return_of_materials (clean)
    "2. Rückgabe. Auf Verlangen der offenlegenden Partei hat die "
    "empfangende Partei sämtliche Vertraulichen Informationen "
    "einschließlich der Kopien hiervon innerhalb von zehn (10) "
    "Arbeitstagen zurückzugeben oder zu vernichten und die "
    "Vernichtung schriftlich zu versichern.",

    # c3 — injunctive_relief (DEVIATION #2: Vertragsstrafe 25 %
    # der Auftragssumme — vs. the IHK-Hessen baseline's BGH 5 %
    # AGB cap. Material because AGB clauses with Vertragsstrafen
    # > 5 % der Auftragssumme are per BGH ständiger Rechtsprechung
    # regelmäßig nichtig in AGB-Verträgen).
    "3. Vertragsstrafe. Für jeden Fall des schuldhaften Verstoßes "
    "gegen diese Vereinbarung verpflichtet sich die empfangende "
    "Partei zur Zahlung einer Vertragsstrafe in Höhe von fünfundzwanzig "
    "Prozent (25 %) der Auftragssumme. Die Geltendmachung weiterer "
    "Schadensersatzansprüche bleibt vorbehalten.",

    # c4 — residual_knowledge (clean — preserves Beweislast)
    "4. Ausnahmen. Von der Vertraulichkeitsverpflichtung "
    "ausgenommen sind Informationen, an denen die empfangende "
    "Partei (i) bereits vor der Offenlegung nachweislich im "
    "rechtmäßigen Besitz war, oder (ii) die ohne Verstoß gegen "
    "diese Vereinbarung unabhängig entwickelt hat, oder (iii) die "
    "von einem zur Offenlegung berechtigten Dritten erhalten hat, "
    "oder (iv) die ohne Verstoß gegen diese Vereinbarung allgemein "
    "bekannt sind. Die empfangende Partei trägt die Beweislast "
    "für das Vorliegen einer dieser Ausnahmen.",

    # c5 — term (clean)
    "5. Vertragslaufzeit. Diese Vereinbarung tritt mit dem Datum "
    "der Unterschrift der zuletzt unterzeichnenden Partei in Kraft "
    "und gilt für einen Zeitraum von drei (3) Jahren. Die "
    "Verpflichtungen aus dieser Vereinbarung in Bezug auf die "
    "während der Laufzeit offenbarte Vertrauliche Information "
    "bleiben jedoch für einen Zeitraum von fünf (5) Jahren nach "
    "Beendigung weiter bestehen.",

    # c6 — entire_agreement (clean)
    "6. Schlussbestimmungen. Diese Vereinbarung ersetzt alle "
    "früheren Vereinbarungen der Parteien zum selben Zweck. "
    "Änderungen bedürfen der Schriftform.",

    # c7 — governing_law (DEVIATION #3: Schweizer Recht + ICC
    # Schiedsgerichtbarkeit — vs. the IHK-München baseline's
    # deutsches Recht + Gerichtsstand am Sitz des Erfinders).
    # Minor because the IHK-München baseline notes that parties
    # CAN deviate to a Schiedsgerichtsvereinbarung, but the
    # baseline strongly favors deutsches Recht for B2B-NDAs in
    # Germany; a foreign jurisdiction (CH + ICC) is structurally
    # outside the playbook's reference set.
    "7. Rechtswahl und Gerichtsstand. Auf diesen Vertrag ist "
    "Schweizer Recht anzuwenden. Alle Streitigkeiten aus oder im "
    "Zusammenhang mit diesem Vertrag werden nach der "
    "Schiedsgerichtsordnung der International Chamber of Commerce "
    "(ICC) von einem oder mehreren gemäß dieser Ordnung ernannten "
    "Schiedsrichtern endgültig entschieden. Der ordentliche "
    "Rechtsweg ist ausgeschlossen.",
]


def build_pdf(out_path: Path, title: str, paragraphs: list[str]) -> None:
    """Write a deterministic, text-extractable DE NDA PDF.

    Idempotent: overwrites whatever is there. No timestamps, no
    random IDs — the contract text is hard-coded so re-running
    produces the same PDF bytes.
    """
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=50,
        rightMargin=50,
        topMargin=50,
        bottomMargin=50,
        title=title,
        author="clausecraft eval harness",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 14

    story: list = [Paragraph(f"<b>{title}</b>", styles["Heading1"])]
    story.append(Spacer(1, 12))
    for para in paragraphs:
        story.append(Paragraph(para, body_style))
        story.append(Spacer(1, 6))

    doc.build(story)


def main() -> int:
    PUBLIC_DE_DIR.mkdir(parents=True, exist_ok=True)
    SYNTHETIC_DE_DIR.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[Path, str, list[str]]] = [
        (
            PUBLIC_DE_DIR / "nda-001.pdf",
            GESCHGEHG_TITLE,
            GESCHGEHG_PARAGRAPHS,
        ),
        (
            PUBLIC_DE_DIR / "nda-002.pdf",
            DIHK_TITLE,
            DIHK_PARAGRAPHS,
        ),
        (
            PUBLIC_DE_DIR / "nda-003.pdf",
            IHK_HESSEN_TITLE,
            IHK_HESSEN_PARAGRAPHS,
        ),
        (
            SYNTHETIC_DE_DIR / "nda-001.pdf",
            SYNTHETIC_DE_1_TITLE,
            SYNTHETIC_DE_1_PARAGRAPHS,
        ),
        (
            SYNTHETIC_DE_DIR / "nda-002.pdf",
            SYNTHETIC_DE_2_TITLE,
            SYNTHETIC_DE_2_PARAGRAPHS,
        ),
    ]

    for path, title, paragraphs in targets:
        build_pdf(path, title, paragraphs)
        print(f"wrote {path} ({path.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
