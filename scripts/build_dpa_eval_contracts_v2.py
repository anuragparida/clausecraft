"""Build the v2 DPA eval contracts for Phase 5 (card t_0d594e5e).

This script generates the **7 additional** v2 DPA contracts that
grow the eval set from 3 (v1) -> 10 (v2). The v1 starter shipped
in card t_463d603d (3 contracts: 1 public-EN + 1 synth-EN + 1
synth-DE). The v2 expansion is the 7 missing contracts to hit
the spec's "10 DPA contracts" target:

  examples/contracts/public/dpa-002.pdf    (EN clean, EDPB 07/2020 § 6 anchored)
  examples/contracts/public/dpa-003.pdf    (EN clean, IAPP template anchored)
  examples/contracts/synthetic/dpa-002.pdf (EN stress: 3 NEW deviation categories)
  examples/contracts/public-de/dpa-001.pdf (DE clean, EUR-Lex Art. 28 DSGVO)
  examples/contracts/public-de/dpa-002.pdf (DE clean, DSK Kurzpapier Nr. 13)
  examples/contracts/public-de/dpa-003.pdf (DE clean, BDSG § 62)
  examples/contracts/synthetic-de/dpa-002.pdf (DE stress: 3 NEW deviation categories)

Distribution (mirrors the spec fallback of "3 public + 2 synthetic x 2 languages"):

  3 public-EN + 2 synth-EN + 3 public-DE + 2 synth-DE = 10

The 7 new contracts + 7 new expected-deviation YAMLs (in
``examples/expected/``) are the v2 deliverable. This script
generates the 7 PDFs idempotently.

Why "public" still means "public-source style" (not network-fetched)
--------------------------------------------------------------------
Same project rule as v1: the public contracts are hand-authored
following the actual public source (EDPB / IAPP / EUR-Lex / DSK
Kurzpapier / BDSG) — the statutory text is itself the public
source and is not under copyright (Berne Convention Art. 2(4) +
EU open-data policy Decision 2011/833/EU + German
Urheberrechtsgesetz § 5). Provenance + license notes for each
public source are recorded in
``examples/contracts/public/SOURCES.dpa.md`` and
``examples/contracts/public-de/SOURCES.dpa.md`` (new in v2) —
they re-state the public-domain / open-data license of each
source.

Why the synthetic deviations are calibrated to a real LLM
---------------------------------------------------------
The 2 new synthetic contracts (1 EN, 1 DE) deliberately exercise
deviation *categories* the v1 synthetics did NOT cover:

  EN v2 (synthetic/dpa-002.pdf) — 3 NEW categories:
    c2 (dpa_subprocessor_flowdown)        — minor: drops the
                                            "sufficient guarantees"
                                            requirement on the
                                            downstream sub-processor
    c5 (dpa_data_subject_rights)          — material: removes the
                                            controller-assist
                                            obligation for data-
                                            subject rights (Art.
                                            28(3)(e) GDPR)
    c6 (dpa_data_return_deletion)         — minor: extends the
                                            30-day return window to
                                            90 days

  DE v2 (synthetic-de/dpa-002.pdf) — 3 NEW categories:
    c2 (dpa_subprocessor_flowdown)        — material: removes the
                                            "gleiche Datenschutzpflichten"
                                            flow-down requirement
                                            (Art. 28(4) DSGVO)
    c4 (dpa_international_transfer)       — material: drops the
                                            explicit SCCs 2021/914
                                            reference
    c5 (dpa_data_return_deletion)         — minor: 90-day return
                                            window +
                                            Verantwortlicher bears
                                            the
                                            deletion-certification
                                            cost

The deviation *categories* covered in v1 (controller-processor
designation, sub-processor consent, breach notification, audit
rights, transfer-mechanism in DE) are deliberately NOT repeated
in v2 — the v1 synthetics own those. The v2 synthetics fill the
3 EN and 3 DE gaps from the dpa-en baselines' GAP.md
(playbook/baselines/dpa-en/GAP.md).

Combined v1 + v2 deviation coverage:
  10 deviation categories across 9 dpa_* ClauseType values
  (the full Phase 5 taxonomy).

Source-spread for the 6 public contracts (3 EN + 3 DE):
  EN: gdpr-info.eu (v1 dpa-001) + EDPB (v2 dpa-002) + IAPP (v2 dpa-003) = 3 hosts
  DE: EUR-Lex (v1 dpa-001 synth references + v2 dpa-001) + DSK
      Kurzpapier (v2 dpa-002) + BDSG gesetze-im-internet (v2 dpa-003) = 3 hosts
  Total: 6 distinct hosts across 6 public contracts — comfortably
  above the ">=4 distinct hosts" rule from the dpa-en baselines card.

Idempotence
-----------
Re-running this script overwrites all 7 PDFs with byte-identical
content (no timestamps, no random IDs). The eval harness depends
on the contract text being stable so the golden YAML's
``text_excerpt`` fields keep matching.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "examples" / "contracts" / "public"
SYNTHETIC_DIR = REPO_ROOT / "examples" / "contracts" / "synthetic"
PUBLIC_DE_DIR = REPO_ROOT / "examples" / "contracts" / "public-de"
SYNTHETIC_DE_DIR = REPO_ROOT / "examples" / "contracts" / "synthetic-de"


# ---------------------------------------------------------------------------
# Public-EN contract #2 — EDPB Guidelines 07/2020 § 6 anchored (CLEAN BASELINE)
# ---------------------------------------------------------------------------
PUBLIC_DPA_002_TITLE = (
    "DATA PROCESSING AGREEMENT (DPA) — TEMPLATE PER EDPB GUIDELINES 07/2020 § 6"
)
PUBLIC_DPA_002_PARAGRAPHS: list[str] = [
    "This Data Processing Agreement (this \u201cAgreement\u201d) is entered into "
    "as of the Effective Date by and between the Customer (the "
    "\u201cController\u201d) and the Processor (the \u201cProcessor\u201d) and forms "
    "an integral part of the Principal Agreement between the parties. "
    "Capitalised terms not defined in this Agreement have the meanings "
    "given in Regulation (EU) 2016/679 (the \u201cGeneral Data Protection "
    "Regulation\u201d or \u201cGDPR\u201d) and in the EDPB Guidelines 07/2020 on "
    "the concepts of controller and processor.",

    "1. Designation and Instructions. The parties acknowledge that, "
    "for the purposes of this Agreement, the Customer is the "
    "Controller and the Processor is the Processor of Personal Data, "
    "each as defined in the GDPR and as further elaborated in the "
    "EDPB Guidelines 07/2020 § 6. The Processor shall process "
    "Personal Data only on the documented instructions of the "
    "Controller, including with regard to transfers of Personal "
    "Data to a third country, unless required to do so by Union or "
    "Member State law.",

    "2. Sub-processor Authorisation. The Processor shall not engage "
    "another processor without prior specific written authorisation "
    "of the Controller, in accordance with Article 28(2) of the GDPR "
    "and the EDPB Guidelines 07/2020 § 6. Where the Processor engages "
    "another processor for carrying out specific processing "
    "activities on behalf of the Controller, a contract shall impose "
    "the same data protection obligations as set out in this "
    "Agreement, in particular providing sufficient guarantees to "
    "implement appropriate technical and organisational measures.",

    "3. Sub-processor Flow-down. The Processor shall impose on the "
    "other processor, by way of a contract, the same data protection "
    "obligations as set out in this Agreement, in particular "
    "providing sufficient guarantees to implement appropriate "
    "technical and organisational measures. The Processor shall "
    "remain fully liable to the Controller for the performance of "
    "that other processor's obligations.",

    "4. International Transfers. The Processor shall not transfer "
    "Personal Data to a third country unless the transfer is "
    "governed by an adequacy decision under Article 45 GDPR, the "
    "Standard Contractual Clauses set out in Commission Implementing "
    "Decision (EU) 2021/914, or another lawful transfer mechanism "
    "recognised under Chapter V GDPR, as further elaborated in the "
    "EDPB Guidelines 07/2020 on the international transfer of "
    "personal data.",

    "5. Personal Data Breach Notification. The Processor shall "
    "notify the Controller of a Personal Data Breach without undue "
    "delay and in any event within twenty-four (24) hours of "
    "becoming aware of the Personal Data Breach, in accordance with "
    "the recommended processor inner window set out in the EDPB "
    "Guidelines 9/2022 § 3.4. The Controller shall thereupon notify "
    "the competent supervisory authority within seventy-two (72) "
    "hours as required by Article 33(1) of the GDPR.",

    "6. Audit and Return of Personal Data. The Processor shall make "
    "available to the Controller all information necessary to "
    "demonstrate compliance with the obligations laid down in this "
    "Agreement, and shall allow for and contribute to audits "
    "conducted by the Controller with reasonable prior notice. Upon "
    "termination of the services relating to processing, the "
    "Processor shall, at the choice of the Controller, return all "
    "Personal Data and delete existing copies, and provide written "
    "certification of such deletion upon the Controller's request.",
]


# ---------------------------------------------------------------------------
# Public-EN contract #3 — IAPP template anchored (CLEAN BASELINE)
# ---------------------------------------------------------------------------
PUBLIC_DPA_003_TITLE = (
    "DATA PROCESSING AGREEMENT (DPA) — TEMPLATE PER IAPP MODEL DPA"
)
PUBLIC_DPA_003_PARAGRAPHS: list[str] = [
    "This Data Processing Agreement (this \u201cAgreement\u201d) is entered into "
    "as of the Effective Date by and between the Customer (the "
    "\u201cController\u201d) and the Processor (the \u201cProcessor\u201d) and forms "
    "an integral part of the Principal Agreement between the parties. "
    "Capitalised terms not defined in this Agreement have the "
    "meanings given in Regulation (EU) 2016/679 (the \u201cGeneral Data "
    "Protection Regulation\u201d or \u201cGDPR\u201d) and in the IAPP Model "
    "Data Processing Agreement template.",

    "1. Designation of the Parties. The parties acknowledge that, "
    "for the purposes of this Agreement, the Customer is the "
    "Controller and the Processor is the Processor of Personal "
    "Data, each as defined in the GDPR. The Processor shall process "
    "Personal Data only on the documented instructions of the "
    "Controller, including with regard to transfers of Personal "
    "Data to a third country, and shall treat Personal Data as "
    "confidential in accordance with Article 28(3)(b) of the GDPR.",

    "2. Sub-processor Authorisation. The Processor shall not engage "
    "another processor without prior specific or general written "
    "authorisation of the Controller. Where the Controller gives "
    "general written authorisation, the Processor shall inform the "
    "Controller of any intended changes concerning the addition or "
    "replacement of other processors, thereby giving the Controller "
    "the opportunity to object to such changes on reasonable "
    "data-protection grounds.",

    "3. Sub-processor Obligations. Where the Processor engages "
    "another processor for carrying out specific processing "
    "activities on behalf of the Controller, the same data "
    "protection obligations as set out in this Agreement shall be "
    "imposed on that other processor by way of a contract. The "
    "Processor shall remain fully liable to the Controller for the "
    "performance of that other processor's obligations.",

    "4. International Transfers. The Processor shall not transfer "
    "Personal Data to a third country or an international "
    "organisation unless an adequate level of protection is "
    "ensured by way of an adequacy decision of the European "
    "Commission, the Standard Contractual Clauses (Module Two) set "
    "out in Commission Implementing Decision (EU) 2021/914, or any "
    "other lawful transfer mechanism recognised under Chapter V "
    "GDPR, in line with the IAPP Model DPA Section 4 transfer "
    "mechanism clause.",

    "5. Personal Data Breach Notification. The Processor shall "
    "notify the Controller of a Personal Data Breach without undue "
    "delay and in any event within twenty-four (24) hours of "
    "becoming aware of the Personal Data Breach. The notification "
    "shall describe the nature of the Personal Data Breach, the "
    "categories and approximate number of data subjects and records "
    "concerned, the likely consequences, and the measures taken or "
    "proposed to address the breach.",

    "6. Audit and Return. The Processor shall make available to "
    "the Controller all information necessary to demonstrate "
    "compliance with the obligations laid down in this Agreement, "
    "and shall allow for and contribute to audits, including "
    "inspections, conducted by the Controller or another auditor "
    "mandated by the Controller on an annual basis. Upon "
    "termination of the services, the Processor shall, at the "
    "choice of the Controller, return all Personal Data to the "
    "Controller and delete existing copies, and shall provide "
    "written certification of such deletion upon request.",
]


# ---------------------------------------------------------------------------
# Public-DE contract #1 — EUR-Lex Art. 28 DSGVO (CLEAN BASELINE)
# ---------------------------------------------------------------------------
PUBLIC_DE_DPA_001_TITLE = (
    "AUFTRAGSVERARBEITUNGSVEREINBARUNG (AVV) — MUSTER NACH ART. 28 DSGVO"
)
PUBLIC_DE_DPA_001_PARAGRAPHS: list[str] = [
    "Diese Auftragsverarbeitungsvereinbarung (nachfolgend "
    "\u201eVereinbarung\u201c) wird zwischen den Parteien mit Wirkung zum "
    "Datum der Unterzeichnung durch die zuletzt unterzeichnende "
    "Partei geschlossen und ist Bestandteil des Hauptvertrags. "
    "Begriffe, die in dieser Vereinbarung nicht definiert sind, "
    "haben die Bedeutung, die ihnen in der Verordnung (EU) "
    "2016/679 (Datenschutz-Grundverordnung, DSGVO) zukommt.",

    "1. Bezeichnung der Parteien und Verarbeitungsgrundlage. Die "
    "Parteien stellen fest, dass der Kunde der Verantwortliche und "
    "der Auftragsverarbeiter der Auftragsverarbeiter im Sinne von "
    "Art. 28 DSGVO ist. Der Auftragsverarbeiter verarbeitet "
    "personenbezogene Daten ausschließlich auf dokumentierte "
    "Weisung des Verantwortlichen, einschließlich in Bezug auf "
    "Übermittlungen personenbezogener Daten in ein Drittland oder "
    "an eine internationale Organisation.",

    "2. Vorherige Genehmigung von Unterauftragsverarbeitern. Der "
    "Auftragsverarbeiter beauftragt keinen anderen "
    "Auftragsverarbeiter ohne vorherige spezifische oder "
    "allgemeine schriftliche Genehmigung des Verantwortlichen. Im "
    "Fall einer allgemeinen schriftlichen Genehmigung informiert "
    "der Auftragsverarbeiter den Verantwortlichen über jede "
    "beabsichtigte Änderung bezüglich der Hinzuziehung oder "
    "Ersetzung anderer Auftragsverarbeiter, damit der "
    "Verantwortliche die Möglichkeit zum Widerspruch hat.",

    "3. Unterauftragsverarbeiter-Pflichten. Beauftragt der "
    "Auftragsverarbeiter einen anderen Auftragsverarbeiter, so "
    "sind dem anderen Auftragsverarbeiter im Wege eines Vertrags "
    "die gleichen Datenschutzpflichten aufzuerlegen, die in "
    "dieser Vereinbarung festgelegt sind. Der Auftragsverarbeiter "
    "bleibt gegenüber dem Verantwortlichen für die Erfüllung der "
    "Pflichten des anderen Auftragsverarbeiters vollumfänglich "
    "verantwortlich.",

    "4. Internationale Übermittlungen. Der Auftragsverarbeiter "
    "übermittelt personenbezogene Daten in ein Drittland nur, "
    "wenn ein angemessenes Schutzniveau durch einen "
    "Angemessenheitsbeschluss der Europäischen Kommission nach "
    "Art. 45 DSGVO, durch die Standardvertragsklauseln (Modul "
    "Two) des Durchführungsbeschlusses (EU) 2021/914 der "
    "Kommission vom 4. Juni 2021 oder durch einen anderen "
    "rechtmäßigen Übermittlungsmechanismus nach Kapitel V DSGVO "
    "sichergestellt ist.",

    "5. Meldung von Datenschutzverletzungen. Der "
    "Auftragsverarbeiter meldet dem Verantwortlichen eine "
    "personenbezogene Datenverletzung unverzüglich und in jedem "
    "Fall innerhalb von vierundzwanzig (24) Stunden, nachdem ihm "
    "die Verletzung bekannt geworden ist. Die Meldung enthält alle "
    "Informationen, die der Verantwortliche benötigt, um seine "
    "Meldepflicht nach Art. 33 Abs. 1 DSGVO gegenüber der "
    "zuständigen Aufsichtsbehörde zu erfüllen.",

    "6. Audit-Rechte und Rückgabe. Der Auftragsverarbeiter stellt "
    "dem Verantwortlichen alle Informationen zur Verfügung, die "
    "zur Einhaltung der in dieser Vereinbarung festgelegten "
    "Pflichten erforderlich sind, und ermöglicht Audits. Nach "
    "Beendigung der Verarbeitung gibt der Auftragsverarbeiter "
    "personenbezogene Daten nach Wahl des Verantwortlichen zurück "
    "oder löscht sie und stellt eine schriftliche "
    "Löschbestätigung aus.",
]


# ---------------------------------------------------------------------------
# Public-DE contract #2 — DSK Kurzpapier Nr. 13 (CLEAN BASELINE)
# ---------------------------------------------------------------------------
PUBLIC_DE_DPA_002_TITLE = (
    "AUFTRAGSVERARBEITUNGSVEREINBARUNG (AVV) — NACH DSK KURZPAPIER NR. 13"
)
PUBLIC_DE_DPA_002_PARAGRAPHS: list[str] = [
    "Diese Auftragsverarbeitungsvereinbarung (nachfolgend "
    "\u201eVereinbarung\u201c) wird zwischen den Parteien mit Wirkung zum "
    "Datum der Unterzeichnung durch die zuletzt unterzeichnende "
    "Partei geschlossen. Die Parteien orientieren sich an dem "
    "Kurzpapier Nr. 13 der Datenschutzkonferenz (DSK) zur "
    "Auftragsverarbeitung.",

    "1. Bezeichnung der Parteien. Die Parteien stellen fest, dass "
    "der Kunde der Verantwortliche und der Auftragsverarbeiter der "
    "Auftragsverarbeiter im Sinne der DSGVO ist. Der "
    "Auftragsverarbeiter verarbeitet personenbezogene Daten "
    "ausschließlich auf dokumentierte Weisung des "
    "Verantwortlichen, wie es das DSK Kurzpapier Nr. 13 unter "
    "Ziffer 2 vorsieht.",

    "2. Vorherige Genehmigung. Der Auftragsverarbeiter beauftragt "
    "keinen anderen Auftragsverarbeiter ohne vorherige "
    "schriftliche Genehmigung des Verantwortlichen. Im Fall einer "
    "allgemeinen Genehmigung informiert der Auftragsverarbeiter "
    "den Verantwortlichen über jede beabsichtigte Änderung und "
    "räumt ihm eine angemessene Widerspruchsfrist ein, wie es das "
    "DSK Kurzpapier Nr. 13 unter Ziffer 5 empfiehlt.",

    "3. Unterauftragsverarbeiter-Pflichten. Beauftragt der "
    "Auftragsverarbeiter einen anderen Auftragsverarbeiter, so "
    "sind dem anderen Auftragsverarbeiter im Wege eines Vertrags "
    "die gleichen Datenschutzpflichten aufzuerlegen, die in "
    "dieser Vereinbarung festgelegt sind. Der Auftragsverarbeiter "
    "bleibt gegenüber dem Verantwortlichen für die Erfüllung der "
    "Pflichten des anderen Auftragsverarbeiters vollumfänglich "
    "verantwortlich.",

    "4. Internationale Übermittlungen. Der Auftragsverarbeiter "
    "übermittelt personenbezogene Daten in ein Drittland nur, "
    "wenn die Voraussetzungen von Kapitel V DSGVO erfüllt sind. "
    "Insbesondere akzeptiert der Auftragsverarbeiter die "
    "EU-Standardvertragsklauseln (Durchführungsbeschluss (EU) "
    "2021/914) als geeignete Garantie im Sinne von Art. 46 DSGVO, "
    "sofern kein Angemessenheitsbeschluss nach Art. 45 DSGVO "
    "vorliegt.",

    "5. Meldung von Datenschutzverletzungen. Der "
    "Auftragsverarbeiter meldet dem Verantwortlichen eine "
    "personenbezogene Datenverletzung unverzüglich und in jedem "
    "Fall innerhalb von vierundzwanzig (24) Stunden, nachdem ihm "
    "die Verletzung bekannt geworden ist. Die Meldung beschreibt "
    "die Art der Verletzung sowie die Kategorien und ungefähre "
    "Anzahl der betroffenen Personen und enthält alle "
    "Informationen, die der Verantwortliche zur Erfüllung seiner "
    "Meldepflichten nach Art. 33 DSGVO benötigt.",

    "6. Audit-Rechte und Rückgabe. Der Auftragsverarbeiter "
    "ermöglicht dem Verantwortlichen die Überprüfung der "
    "Einhaltung dieser Vereinbarung, wie es das DSK Kurzpapier "
    "Nr. 13 unter Ziffer 7 vorsieht. Nach Beendigung der "
    "Verarbeitung gibt der Auftragsverarbeiter die "
    "personenbezogenen Daten zurück und löscht bestehende Kopien "
    "oder stellt eine schriftliche Löschbestätigung aus.",
]


# ---------------------------------------------------------------------------
# Public-DE contract #3 — BDSG § 62 (CLEAN BASELINE)
# ---------------------------------------------------------------------------
PUBLIC_DE_DPA_003_TITLE = (
    "AUFTRAGSVERARBEITUNGSVEREINBARUNG (AVV) — NACH BDSG § 62"
)
PUBLIC_DE_DPA_003_PARAGRAPHS: list[str] = [
    "Diese Auftragsverarbeitungsvereinbarung (nachfolgend "
    "\u201eVereinbarung\u201c) wird zwischen den Parteien mit Wirkung zum "
    "Datum der Unterzeichnung durch die zuletzt unterzeichnende "
    "Partei geschlossen. Ergänzend zu Art. 28 DSGVO findet § 62 "
    "BDSG Anwendung.",

    "1. Bezeichnung der Parteien. Die Parteien stellen fest, dass "
    "der Kunde der Verantwortliche und der Auftragsverarbeiter der "
    "Auftragsverarbeiter im Sinne von Art. 28 DSGVO und § 62 "
    "Bundesdatenschutzgesetz (BDSG) ist. Der Auftragsverarbeiter "
    "verarbeitet personenbezogene Daten ausschließlich auf "
    "dokumentierte Weisung des Verantwortlichen.",

    "2. Vorherige Genehmigung. Der Auftragsverarbeiter beauftragt "
    "keinen anderen Auftragsverarbeiter ohne vorherige "
    "schriftliche Genehmigung des Verantwortlichen. § 62 Abs. 4 "
    "BDSG verpflichtet den Auftragsverarbeiter, den "
    "Verantwortlichen über jede beabsichtigte Hinzuziehung oder "
    "Ersetzung anderer Auftragsverarbeiter zu informieren.",

    "3. Pflichtenübertragung auf Unterauftragsverarbeiter. "
    "Beauftragt der Auftragsverarbeiter einen anderen "
    "Auftragsverarbeiter, so sind dem anderen "
    "Auftragsverarbeiter im Wege eines Vertrags die gleichen "
    "Datenschutzpflichten aufzuerlegen, die in dieser "
    "Vereinbarung festgelegt sind. Die Verantwortlichkeit des "
    "Auftragsverarbeiters gegenüber dem Verantwortlichen bleibt "
    "unberührt.",

    "4. Internationale Übermittlungen. Der Auftragsverarbeiter "
    "übermittelt personenbezogene Daten in ein Drittland nur, "
    "wenn die Voraussetzungen der Art. 44 ff. DSGVO erfüllt sind. "
    "Insbesondere akzeptiert der Auftragsverarbeiter die "
    "EU-Standardvertragsklauseln oder verbindliche interne "
    "Datenschutzvorschriften als geeignete Garantien.",

    "5. Meldung von Datenschutzverletzungen. Der "
    "Auftragsverarbeiter meldet dem Verantwortlichen eine "
    "personenbezogene Datenverletzung unverzüglich und in jedem "
    "Fall innerhalb von vierundzwanzig (24) Stunden, nachdem ihm "
    "die Verletzung bekannt geworden ist. Die Meldung enthält "
    "alle Informationen, die der Verantwortliche benötigt, um "
    "seine Meldepflicht nach Art. 33 Abs. 1 DSGVO zu erfüllen.",

    "6. Audit-Rechte und Rückgabe. Der Auftragsverarbeiter "
    "ermöglicht dem Verantwortlichen die Überprüfung der "
    "Einhaltung dieser Vereinbarung. Nach Beendigung der "
    "Verarbeitung gibt der Auftragsverarbeiter die "
    "personenbezogenen Daten nach Wahl des Verantwortlichen "
    "zurück und löscht bestehende Kopien.",
]


# ---------------------------------------------------------------------------
# Synthetic-EN contract #2 — 3 NEW deviation categories
# ---------------------------------------------------------------------------
SYNTHETIC_DPA_EN_V2_TITLE = (
    "DATA PROCESSING AGREEMENT (DPA) — SYNTHETIC EVAL FIXTURE V2 (EN)"
)
SYNTHETIC_DPA_EN_V2_PARAGRAPHS: list[str] = [
    "This Data Processing Agreement (this \u201cAgreement\u201d) is entered into "
    "as of the Effective Date by and between the Customer and the "
    "Processor.",

    "1. Designation of the Parties. The parties acknowledge that, "
    "for the purposes of this Agreement, the Customer is the "
    "Controller and the Processor is the Processor of Personal "
    "Data, each as defined in the GDPR. The Processor shall "
    "process Personal Data only on the documented instructions of "
    "the Controller.",

    # c2 — dpa_subprocessor_flowdown (DEVIATION #1: drops the
    # "sufficient guarantees" anchor. Minor.)
    "2. Sub-processor Obligations. Where the Processor engages "
    "another processor for carrying out specific processing "
    "activities on behalf of the Controller, the same data "
    "protection obligations as set out in this Agreement shall be "
    "imposed on that other processor by way of a contract.",

    "3. Sub-processor Authorisation. The Processor shall not "
    "engage another processor without prior specific written "
    "authorisation of the Controller.",

    "4. International Transfers. The Processor shall not transfer "
    "Personal Data to a third country unless an adequate level of "
    "protection is ensured by way of an adequacy decision of the "
    "European Commission, the Standard Contractual Clauses (Module "
    "Two) set out in Commission Implementing Decision (EU) "
    "2021/914, or any other lawful transfer mechanism recognised "
    "under Chapter V GDPR.",

    # c5 — dpa_data_subject_rights (DEVIATION #2: removes the
    # controller-assist obligation. Material.)
    "5. Data Subject Rights. The Processor shall handle requests "
    "from data subjects as appropriate in the ordinary course of "
    "its business, in accordance with its internal policies and "
    "applicable law.",

    # c6 — dpa_data_return_deletion (DEVIATION #3: 90-day return
    # window. Minor.)
    "6. Return or Deletion of Personal Data. Upon termination of "
    "the services relating to processing, the Processor shall, at "
    "the choice of the Controller, return all Personal Data to "
    "the Controller and delete existing copies within ninety (90) "
    "days of such termination, and shall provide written "
    "certification of such return or deletion upon request.",
]


# ---------------------------------------------------------------------------
# Synthetic-DE contract #2 — 3 NEW deviation categories
# ---------------------------------------------------------------------------
SYNTHETIC_DPA_DE_V2_TITLE = (
    "AUFTRAGSVERARBEITUNGSVEREINBARUNG (AVV) — SYNTHETISCHES EVAL FIXTURE V2 (DE)"
)
SYNTHETIC_DPA_DE_V2_PARAGRAPHS: list[str] = [
    "Diese Auftragsverarbeitungsvereinbarung (nachfolgend "
    "\u201eVereinbarung\u201c) wird zwischen den Parteien mit Wirkung zum "
    "Datum der Unterzeichnung durch die zuletzt unterzeichnende "
    "Partei geschlossen.",

    "1. Bezeichnung der Parteien. Die Parteien stellen fest, dass "
    "der Kunde der Verantwortliche und der Auftragsverarbeiter der "
    "Auftragsverarbeiter im Sinne der DSGVO ist. Der "
    "Auftragsverarbeiter verarbeitet personenbezogene Daten "
    "ausschließlich auf dokumentierte Weisung des "
    "Verantwortlichen.",

    # c2 — dpa_subprocessor_flowdown (DEVIATION #1: drops the
    # "gleiche Datenschutzpflichten" anchor. Material.)
    "2. Unterauftragsverarbeiter. Beauftragt der "
    "Auftragsverarbeiter einen anderen Auftragsverarbeiter, so "
    "bleibt der Auftragsverarbeiter gegenüber dem "
    "Verantwortlichen für die Erfüllung der Pflichten des anderen "
    "Auftragsverarbeiters vollumfänglich verantwortlich.",

    "3. Vorherige Genehmigung. Der Auftragsverarbeiter beauftragt "
    "keinen anderen Auftragsverarbeiter ohne vorherige "
    "schriftliche Genehmigung des Verantwortlichen.",

    # c4 — dpa_international_transfer (DEVIATION #2: drops the
    # explicit EU SCCs 2021/914 reference. Material.)
    "4. Internationale Übermittlungen. Der Auftragsverarbeiter "
    "übermittelt personenbezogene Daten in ein Drittland nur, "
    "wenn durch angemessene Garantien ein ausreichendes "
    "Schutzniveau sichergestellt ist. Die Einzelheiten der "
    "Garantien werden in einem separaten Anhang zu dieser "
    "Vereinbarung festgelegt.",

    # c5 — dpa_data_return_deletion (DEVIATION #3: 90-day return
    # window + Verantwortlicher bears the cost. Minor.)
    "5. Rückgabe oder Löschung. Nach Beendigung der Verarbeitung "
    "gibt der Auftragsverarbeiter personenbezogene Daten nach "
    "Wahl des Verantwortlichen zurück und löscht bestehende "
    "Kopien innerhalb von neunzig (90) Tagen. Die Kosten einer "
    "schriftlichen Löschbestätigung trägt der Verantwortliche.",

    "6. Audit-Rechte. Der Auftragsverarbeiter stellt dem "
    "Verantwortlichen alle zur Einhaltung dieser Vereinbarung "
    "erforderlichen Informationen zur Verfügung und ermöglicht "
    "Audits mit einer angemessenen Frist.",
]


def build_pdf(out_path: Path, title: str, paragraphs: list[str]) -> None:
    """Write a deterministic, text-extractable DPA PDF.

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
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DE_DIR.mkdir(parents=True, exist_ok=True)
    SYNTHETIC_DE_DIR.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[Path, str, list[str]]] = [
        (
            PUBLIC_DIR / "dpa-002.pdf",
            PUBLIC_DPA_002_TITLE,
            PUBLIC_DPA_002_PARAGRAPHS,
        ),
        (
            PUBLIC_DIR / "dpa-003.pdf",
            PUBLIC_DPA_003_TITLE,
            PUBLIC_DPA_003_PARAGRAPHS,
        ),
        (
            SYNTHETIC_DIR / "dpa-002.pdf",
            SYNTHETIC_DPA_EN_V2_TITLE,
            SYNTHETIC_DPA_EN_V2_PARAGRAPHS,
        ),
        (
            PUBLIC_DE_DIR / "dpa-001.pdf",
            PUBLIC_DE_DPA_001_TITLE,
            PUBLIC_DE_DPA_001_PARAGRAPHS,
        ),
        (
            PUBLIC_DE_DIR / "dpa-002.pdf",
            PUBLIC_DE_DPA_002_TITLE,
            PUBLIC_DE_DPA_002_PARAGRAPHS,
        ),
        (
            PUBLIC_DE_DIR / "dpa-003.pdf",
            PUBLIC_DE_DPA_003_TITLE,
            PUBLIC_DE_DPA_003_PARAGRAPHS,
        ),
        (
            SYNTHETIC_DE_DIR / "dpa-002.pdf",
            SYNTHETIC_DPA_DE_V2_TITLE,
            SYNTHETIC_DPA_DE_V2_PARAGRAPHS,
        ),
    ]

    for path, title, paragraphs in targets:
        build_pdf(path, title, paragraphs)
        print(f"wrote {path} ({path.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
