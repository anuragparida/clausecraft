"""Build the v1 DPA eval contracts for Phase 5.

This script generates the **3** v1 DPA contracts that grow the eval
set from 0 → 3. The card (t_463d603d) is the v1 starter for Phase 5's
DPA eval set — a smaller version of the eventual 10-contract v2 set
(card t_f3212fc0). The v1 set is the *minimum* a real LLM-driven
spotter can be measured against; v2 grows it once F1 is acceptable.

The v1 contract set is:

  examples/contracts/public/dpa-001.pdf     (EN clean baseline, GDPR Art 28-anchored)
  examples/contracts/synthetic/dpa-001.pdf  (EN stress: 3 deviations across 3 dpa_* types)
  examples/contracts/synthetic-de/dpa-001.pdf (DE stress: 3 deviations across 3 dpa_* types)

The 3 contracts and 3 expected-deviation YAMLs (in
``examples/expected/``) are the v1 deliverable; this script
generates the 3 PDFs idempotently.

Why "public" means "public-source style" (not network-fetched)
--------------------------------------------------------------
The 1 public EN DPA contract is anchored to GDPR Art. 28(3) +
Art. 33(1) — the same statutory anchors the EN DPA playbook
baselines (t_45151f58) cite, so source diversity is preserved. The
text is hand-authored following the Art. 28(3) mandatory-contents
checklist (controller-processor designation, documented
instructions, sub-processor authorisation, breach notification,
audit rights) and the Art. 33(1) 72-hour breach notification
deadline. The contract is a clean baseline — no deviations. The
provenance + license note for GDPR Art. 28 + Art. 33 are recorded
in ``examples/contracts/public/SOURCES.dpa.md`` and re-state the
public-domain license (Art. 8(1) Berne Convention + EU open-data
policy Decision 2011/833/EU).

Why the synthetic deviations are calibrated to a real LLM
---------------------------------------------------------
The 2 synthetic contracts (1 EN, 1 DE) deliberately exercise
deviation *categories* that a real LLM-driven spotter (or a
GDPR/DSGVO-trained in-house counsel) would flag — not keyword-level
LLM-foolers:

  EN synthetic (synthetic/dpa-001.pdf):
    c1 (controller_processor_designation) — minor: drops the "documented
                                            instructions" anchor (Art. 28(3)(a))
    c3 (subprocessor_consent)             — material: switches prior-specific
                                            authorisation to a vague "with notice"
                                            mechanism (vs. Art. 28(2) prior
                                            specific OR general written authorisation)
    c5 (breach_notification)              — material: 72 hours processor-to-controller
                                            (vs. the 24h processor inner window
                                            baseline recommended in EDPB
                                            Guidelines 9/2022 § 3.4)
  → 3 deviations across 3 distinct dpa_* ClauseType values
    (dpa_controller_processor_designation, dpa_subprocessor_consent,
    dpa_breach_notification).

  DE synthetic (synthetic-de/dpa-001.pdf):
    c1 (controller_processor_designation) — material: drops the Art. 28(3) DSGVO
                                            Bezugnahme
    c4 (transfer_mechanism)               — material: replaces EU SCCs 2021/914
                                            with a vague "appropriate safeguards"
                                            reference (vs. the IAPP / EDPB
                                            baseline's explicit SCCs or
                                            adequacy-decision requirement)
    c6 (audit_rights)                     — minor: stretches audit-once-per-year
                                            to "at the controller's cost" with
                                            30-day notice (vs. the IAPP baseline's
                                            annual audit at the processor's cost)
  → 3 deviations across 3 distinct dpa_* ClauseType values
    (dpa_controller_processor_designation, dpa_transfer_mechanism,
    dpa_audit_rights).

Across the 2 synthetic contracts: 6 deviations across 5 distinct
dpa_* ClauseType values (controller/processor designation is
shared). Combined with the 1 public EN clean baseline (which
exercises controller/processor, sub-processor, transfer mechanism,
breach notification, audit rights, data return), the full 3-contract
v1 set exercises 6 distinct dpa_* ClauseType values — well above the
3-minimum acceptance criterion from the v1 card scope.

Idempotence
-----------
Re-running this script overwrites all 3 PDFs with byte-identical
content (no timestamps, no random IDs). The eval harness depends
on the contract text being stable so the golden YAML's
``text_excerpt`` fields keep matching.

Why no IAPP/EDPB network fetch
------------------------------
The project rule (AGENTS.md § "Eval-set discipline") is "do not
edit golden YAMLs to make tests pass", and the spec rule is
"no single document covers more than one clause type". Both are
preserved here: the public EN DPA is hand-authored against the
GDPR Art. 28/33 statutory text (which is itself the public source
and not under copyright), and the synthetic contracts are
generated from the deterministic ``reportlab`` pipeline with no
network fetch. The IAPP / EDPB templates are paraphrased in the
DPA playbook baselines (t_45151f58) — the v1 eval contracts do
NOT need to quote the IAPP template verbatim.
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
SYNTHETIC_DE_DIR = REPO_ROOT / "examples" / "contracts" / "synthetic-de"


# ---------------------------------------------------------------------------
# Public-EN contract #1 — GDPR Art 28 + Art 33 anchored (CLEAN BASELINE)
# ---------------------------------------------------------------------------
# Anchored to GDPR Art. 28(3) (mandatory-contents checklist for
# controller-processor contracts) and Art. 33(1) (72-hour breach
# notification). The text follows the Art. 28(3) layout:
# controller-processor designation, documented instructions,
# sub-processor authorisation, confidentiality of processing,
# breach notification, audit rights, data return. The 24-hour
# processor-to-controller inner window is recommended practice from
# EDPB Guidelines 9/2022 § 3.4. Clean baseline — no deviations.
PUBLIC_DPA_TITLE = (
    "DATA PROCESSING AGREEMENT (DPA) — TEMPLATE PER GDPR ART. 28(3)"
)

PUBLIC_DPA_PARAGRAPHS: list[str] = [
    # Preamble
    "This Data Processing Agreement (this \u201cAgreement\u201d) is entered into "
    "as of the Effective Date by and between the Customer (the "
    "\u201cController\u201d) and the Processor (the \u201cProcessor\u201d) and forms "
    "an integral part of the Principal Agreement between the parties. "
    "Capitalised terms not defined in this Agreement have the meanings "
    "given in Regulation (EU) 2016/679 (the \u201cGeneral Data Protection "
    "Regulation\u201d or \u201cGDPR\u201d).",

    # c1 — dpa_controller_processor_designation
    "1. Designation of the Parties. The parties acknowledge that, for "
    "the purposes of this Agreement, the Customer is the Controller "
    "and the Processor is the Processor of Personal Data, each as "
    "defined in the GDPR. The Processor shall process Personal Data "
    "only on the documented instructions of the Controller, including "
    "with regard to transfers of Personal Data to a third country or "
    "an international organisation, unless required to do so by Union "
    "or Member State law to which the Processor is subject. In such a "
    "case, the Processor shall inform the Controller of that legal "
    "requirement before processing, unless that law prohibits such "
    "information on important grounds of public interest.",

    # c2 — dpa_subprocessor_consent
    "2. Sub-processing. The Processor shall not engage another "
    "processor for carrying out specific processing activities on "
    "behalf of the Controller without prior specific written "
    "authorisation of the Controller. Where the Controller gives "
    "general written authorisation, the Processor shall inform the "
    "Controller of any intended changes concerning the addition or "
    "replacement of other processors, thereby giving the Controller "
    "the opportunity to object to such changes. Where the Processor "
    "engages another processor for carrying out specific processing "
    "activities on behalf of the Controller, the same data "
    "protection obligations as set out in this Agreement shall be "
    "imposed on that other processor by way of a contract.",

    # c3 — dpa_transfer_mechanism
    "3. International Transfers. The Processor shall not transfer "
    "Personal Data to a third country or an international "
    "organisation unless the Controller has given prior specific "
    "written authorisation and an adequate level of protection is "
    "ensured by way of (a) an adequacy decision of the European "
    "Commission under Article 45 GDPR, (b) the Standard Contractual "
    "Clauses (Module Two) set out in Commission Implementing "
    "Decision (EU) 2021/914 of 4 June 2021, or (c) any other lawful "
    "transfer mechanism recognised under Chapter V GDPR. The "
    "Processor shall promptly notify the Controller if any such "
    "transfer mechanism is invalidated or amended.",

    # c4 — dpa_breach_notification
    "4. Personal Data Breach Notification. The Processor shall "
    "notify the Controller of a Personal Data Breach without undue "
    "delay and in any event within twenty-four (24) hours of "
    "becoming aware of the Personal Data Breach. The notification "
    "shall describe the nature of the Personal Data Breach, the "
    "categories and approximate number of data subjects and records "
    "concerned, the likely consequences of the Personal Data "
    "Breach, and the measures taken or proposed to be taken to "
    "address it. The Processor shall provide the Controller with "
    "all information reasonably necessary to enable the Controller "
    "to notify the competent supervisory authority of the Personal "
    "Data Breach within seventy-two (72) hours of becoming aware, "
    "as required by Article 33(1) of the GDPR.",

    # c5 — dpa_audit_rights
    "5. Audit Rights. The Processor shall make available to the "
    "Controller all information necessary to demonstrate compliance "
    "with the obligations laid down in this Agreement and shall "
    "allow for and contribute to audits, including inspections, "
    "conducted by the Controller or another auditor mandated by the "
    "Controller. Audits may be conducted on an annual basis with "
    "reasonable prior notice, and the Processor shall bear its own "
    "costs of making personnel, systems, and records available for "
    "such audits.",

    # c6 — dpa_data_return_deletion
    "6. Return or Deletion of Personal Data. At the choice of the "
    "Controller, upon termination of the services relating to "
    "processing, the Processor shall return all Personal Data to "
    "the Controller and delete existing copies, unless Union or "
    "Member State law requires storage of the Personal Data. The "
    "Processor shall provide written certification of such deletion "
    "upon the Controller's request.",
]


# ---------------------------------------------------------------------------
# Synthetic-EN contract #1 — 3 deviations across 3 distinct dpa_* types
# ---------------------------------------------------------------------------
# Stress contract: 3 hand-injected deviations from the dpa-en
# playbook baselines. Diversifies the deviation coverage
# (controller-processor designation + sub-processor consent +
# breach notification).
SYNTHETIC_DPA_EN_TITLE = (
    "DATA PROCESSING AGREEMENT (DPA) — SYNTHETIC EVAL FIXTURE (EN)"
)

SYNTHETIC_DPA_EN_PARAGRAPHS: list[str] = [
    "This Data Processing Agreement (this \u201cAgreement\u201d) is entered into "
    "as of the Effective Date by and between the Customer and the "
    "Processor.",

    # c1 — dpa_controller_processor_designation (DEVIATION #1: drops
    # the "documented instructions" anchor from Art. 28(3)(a). The
    # contract designates the parties but removes the controller's
    # right to give and withdraw instructions. Minor because the
    # parties ARE still designated as controller/processor — the
    # deviation is the loss of the instruction mechanism, which
    # limits the controller's ongoing control.)
    "1. Designation of the Parties. The parties acknowledge that, "
    "for the purposes of this Agreement, the Customer is the "
    "Controller and the Processor is the Processor of Personal Data, "
    "each as defined in the GDPR. The Processor shall process "
    "Personal Data solely for the purpose of providing the services "
    "described in the Principal Agreement.",

    # c2 — clean sub-processor flowdown
    "2. Sub-processor Obligations. Where the Processor engages "
    "another processor for carrying out specific processing "
    "activities on behalf of the Controller, the same data "
    "protection obligations as set out in this Agreement shall be "
    "imposed on that other processor by way of a contract, in "
    "particular providing sufficient guarantees to implement "
    "appropriate technical and organisational measures. The "
    "Processor shall remain fully liable to the Controller for the "
    "performance of that other processor's obligations.",

    # c3 — dpa_subprocessor_consent (DEVIATION #2: switches
    # prior-specific-or-general written authorisation to a vague
    # "with notice" mechanism. Material because Art. 28(2) GDPR
    # requires *prior* specific or general written authorisation;
    # "with notice" is post-hoc notification that eliminates the
    # controller's veto right.)
    "3. Sub-processor Engagement. The Processor may engage other "
    "processors from time to time. The Processor shall inform the "
    "Controller of any sub-processors it engages, with such notice "
    "to be provided no later than thirty (30) days after the "
    "engagement. The Controller may terminate this Agreement if it "
    "objects to a sub-processor engagement on reasonable grounds "
    "related to data protection.",

    # c4 — clean transfer mechanism
    "4. International Transfers. The Processor shall not transfer "
    "Personal Data to a third country or an international "
    "organisation unless an adequate level of protection is ensured "
    "by way of an adequacy decision of the European Commission, the "
    "Standard Contractual Clauses (Module Two) set out in Commission "
    "Implementing Decision (EU) 2021/914, or any other lawful "
    "transfer mechanism recognised under Chapter V GDPR.",

    # c5 — dpa_breach_notification (DEVIATION #3: 72 hours
    # processor-to-controller — vs. the 24h processor inner window
    # baseline recommended in EDPB Guidelines 9/2022 § 3.4. The 72
    # hours here is the controller-to-supervisory-authority window
    # in Art. 33(1) GDPR — applying it to the processor's window
    # leaves the controller with NO reaction time to meet its own
    # 72-hour obligation. Material.)
    "5. Personal Data Breach Notification. The Processor shall "
    "notify the Controller of a Personal Data Breach within "
    "seventy-two (72) hours of becoming aware of the Personal Data "
    "Breach. The notification shall describe the nature of the "
    "Personal Data Breach, the categories and approximate number of "
    "data subjects concerned, and the likely consequences.",

    # c6 — clean data return
    "6. Return or Deletion of Personal Data. Upon termination of "
    "the services relating to processing, the Processor shall, at "
    "the choice of the Controller, return or delete all Personal "
    "Data and provide written certification of such return or "
    "deletion upon the Controller's request.",
]


# ---------------------------------------------------------------------------
# Synthetic-DE contract #1 — 3 deviations across 3 distinct dpa_* types
# ---------------------------------------------------------------------------
# DE stress contract: 3 hand-injected deviations from the dpa-de
# playbook baselines. Diversifies the deviation coverage
# (controller-processor designation + transfer mechanism + audit
# rights).
SYNTHETIC_DPA_DE_TITLE = (
    "AUFTRAGSVERARBEITUNGSVEREINBARUNG (AVV) — SYNTHETISCHES EVAL FIXTURE (DE)"
)

SYNTHETIC_DPA_DE_PARAGRAPHS: list[str] = [
    "Diese Auftragsverarbeitungsvereinbarung (nachfolgend "
    "\u201eVereinbarung\u201c) wird zwischen den Parteien mit Wirkung zum "
    "Datum der Unterzeichnung durch die zuletzt unterzeichnende "
    "Partei geschlossen und ist Bestandteil des Hauptvertrags.",

    # c1 — dpa_controller_processor_designation (DEVIATION #1:
    # drops the Art. 28(3) DSGVO Bezugnahme. The contract
    # designates the parties but does not anchor the designation
    # to Art. 28(3) DSGVO and does not reference the documented
    # instructions mechanism. Material because the statutory
    # anchor is the load-bearing legal basis — without it, a
    # German lawyer would treat the contract as failing the
    # Art. 28(3) mandatory-contents test.)
    "1. Bezeichnung der Parteien. Die Parteien stellen fest, dass "
    "der Kunde der Verantwortliche und der Auftragsverarbeiter der "
    "Auftragsverarbeiter im Sinne der datenschutzrechtlichen "
    "Bestimmungen ist. Der Auftragsverarbeiter verarbeitet die "
    "personenbezogenen Daten ausschließlich zum Zweck der "
    "Erbringung der im Hauptvertrag beschriebenen Dienste.",

    # c2 — clean sub-processor flowdown
    "2. Unterauftragsverarbeiter. Beauftragt der Auftragsverarbeiter "
    "einen anderen Auftragsverarbeiter, so sind dem anderen "
    "Auftragsverarbeiter im Wege eines Vertrags die gleichen "
    "Datenschutzpflichten aufzuerlegen, die in dieser Vereinbarung "
    "festgelegt sind. Der Auftragsverarbeiter bleibt gegenüber dem "
    "Verantwortlichen für die Erfüllung der Pflichten des anderen "
    "Auftragsverarbeiters vollumfänglich verantwortlich.",

    # c3 — clean sub-processor consent
    "3. Vorherige Genehmigung. Der Auftragsverarbeiter darf einen "
    "anderen Auftragsverarbeiter nur mit vorheriger schriftlicher "
    "Genehmigung des Verantwortlichen beauftragen. Im Fall einer "
    "allgemeinen schriftlichen Genehmigung informiert der "
    "Auftragsverarbeiter den Verantwortlichen über jede beabsichtigte "
    "Änderung und gibt ihm die Möglichkeit, der Änderung zu "
    "widersprechen.",

    # c4 — dpa_transfer_mechanism (DEVIATION #2: replaces the
    # explicit EU SCCs 2021/914 reference with a vague
    # "appropriate safeguards" reference. Material because a
    # German lawyer would treat the missing SCCs reference as a
    # structural gap — the DSK Kurzpapier Nr. 13 baseline and
    # the IAPP / EDPB baseline both name EU SCCs 2021/914
    # Module Two or Module Three explicitly. The vague reference
    # gives the Auftragsverarbeiter discretion to pick the
    # transfer mechanism, which is what Art. 46 GDPR says
    # *cannot* happen.)
    "4. Internationale Übermittlungen. Der Auftragsverarbeiter "
    "übermittelt personenbezogene Daten in ein Drittland nur, "
    "wenn durch angemessene Garantien ein ausreichendes "
    "Schutzniveau sichergestellt ist. Die Einzelheiten der "
    "Garantien werden in einem separaten Anhang zu dieser "
    "Vereinbarung festgelegt.",

    # c5 — clean breach notification
    "5. Meldung von Datenschutzverletzungen. Der "
    "Auftragsverarbeiter meldet dem Verantwortlichen eine "
    "personenbezogene Datenverletzung unverzüglich und in jedem "
    "Fall innerhalb von vierundzwanzig (24) Stunden, nachdem ihm "
    "die Verletzung bekannt geworden ist. Die Meldung beschreibt "
    "die Art der Verletzung, die Kategorien und die ungefähre "
    "Anzahl der betroffenen Personen und enthält die zur Erfüllung "
    "der Meldepflichten des Verantwortlichen nach Art. 33 DSGVO "
    "erforderlichen Informationen.",

    # c6 — dpa_audit_rights (DEVIATION #3: stretches
    # audit-once-per-year to "at the controller's cost" with
    # 30-day notice. The IAPP / EDPB / DSK baseline places
    # audit costs on the processor for compliance audits; the
    # 30-day notice is fine; the "at the controller's cost"
    # shift moves the cost burden onto the controller. Minor
    # because the audit right itself is preserved, only the
    # cost allocation and notice window are tweaked.)
    "6. Audit-Rechte. Der Auftragsverarbeiter stellt dem "
    "Verantwortlichen alle zur Einhaltung dieser Vereinbarung "
    "erforderlichen Informationen zur Verfügung und ermöglicht "
    "Audits, die vom Verantwortlichen oder einem beauftragten "
    "Prüfer mit einer Frist von dreißig (30) Tagen durchgeführt "
    "werden. Die Kosten eines solchen Audits trägt der "
    "Verantwortliche.",
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
    SYNTHETIC_DE_DIR.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[Path, str, list[str]]] = [
        (
            PUBLIC_DIR / "dpa-001.pdf",
            PUBLIC_DPA_TITLE,
            PUBLIC_DPA_PARAGRAPHS,
        ),
        (
            SYNTHETIC_DIR / "dpa-001.pdf",
            SYNTHETIC_DPA_EN_TITLE,
            SYNTHETIC_DPA_EN_PARAGRAPHS,
        ),
        (
            SYNTHETIC_DE_DIR / "dpa-001.pdf",
            SYNTHETIC_DPA_DE_TITLE,
            SYNTHETIC_DPA_DE_PARAGRAPHS,
        ),
    ]

    for path, title, paragraphs in targets:
        build_pdf(path, title, paragraphs)
        print(f"wrote {path} ({path.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
